"""Text and schema extractors for emails, phones, addresses, and JSON-LD."""

from __future__ import annotations

import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from .config import (
    COUNTRY,
    EMAIL_RE,
    IMAGE_EXTENSIONS,
    OWNER_RE_PATTERNS,
    PHONE_RE,
    SCHEMA_TYPE_TO_NICHE,
    RELEVANT_SCHEMA_TYPES,
    CITIES,
    STATE_ABBR,
)
from .utils import normalize_phone, verify_mx


def _is_false_positive_email(email: str) -> bool:
    """Reject emails that are actually image filenames or logo placeholders."""
    el = email.lower()
    # Image extensions disguised as TLDs
    if any(el.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return True
    # Common placeholder domains
    if any(el.endswith(d) for d in ("@example.com", "@test.com", "@domain.com", "@email.com", "@yourdomain.com")):
        return True
    # No-reply variants
    if el.startswith(("noreply@", "no-reply@", "donotreply@")):
        return True
    # Logo / image path indicators inside local-part
    local = el.split("@", 1)[0] if "@" in el else el
    if any(x in local for x in ("logo", "image", "img", "avatar", "icon", "banner", "header", "footer", "thumb")):
        return True
    # If the "domain" part has no dot or looks like a file path
    domain = el.split("@", 1)[1] if "@" in el else ""
    if "/" in domain or "?" in domain or "#" in domain:
        return True
    return False


def _deobfuscate_text(text: str) -> str:
    """Replace common email obfuscation patterns with real characters."""
    # HTML entities
    text = text.replace("&#64;", "@").replace("&#46;", ".")
    text = text.replace("&commat;", "@").replace("&period;", ".")
    # Common obfuscations (case-insensitive, with optional surrounding spaces)
    text = re.sub(r"\s*\[at\]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(at\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*{at}\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\[dot\]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(dot\)\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*{dot}\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\sdot\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\sAT\s*", "@", text, flags=re.IGNORECASE)
    return text


def _extract_mailto_emails(soup: BeautifulSoup) -> list[str]:
    """Extract emails from mailto: links."""
    emails: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.lower().startswith("mailto:"):
            # mailto:info@example.com?subject=Hello
            email_part = href[7:].split("?")[0].split("&")[0]
            email_part = unquote(email_part).strip()
            if "@" in email_part and "." in email_part:
                emails.append(email_part.lower())
    return emails


def extract_emails(text: str, soup: BeautifulSoup | None = None, verify_mx_records: bool = False) -> list[str]:
    """Extract emails with regex, mailto links, deobfuscation, false-positive filtering, dedupe, and optional MX verify."""
    all_raw: set[str] = set()

    # 1. Extract from visible text (original)
    all_raw.update(EMAIL_RE.findall(text))

    # 2. Extract from deobfuscated text
    deobfuscated = _deobfuscate_text(text)
    all_raw.update(EMAIL_RE.findall(deobfuscated))

    # 3. Extract from mailto: links
    if soup is not None:
        all_raw.update(_extract_mailto_emails(soup))

    filtered: list[str] = []
    for e in all_raw:
        if _is_false_positive_email(e):
            continue
        filtered.append(e.lower().strip())

    # Deduplicate while preserving first-seen order
    seen: set[str] = set()
    deduped: list[str] = []
    for e in filtered:
        if e not in seen:
            seen.add(e)
            deduped.append(e)

    if verify_mx_records:
        verified: list[str] = []
        for e in deduped:
            domain = e.split("@", 1)[1]
            if verify_mx(domain):
                verified.append(e)
        return verified
    return deduped


def extract_phones(text: str) -> list[str]:
    raw = PHONE_RE.findall(text)
    valid: list[str] = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15:
            valid.append(p)
    return list(set(valid))


def extract_address_from_text(text: str) -> dict | None:
    """Try to extract an address from free-form text using configured cities.
    US-only for now; non-US address formats vary too widely for a simple regex.
    """
    if COUNTRY.upper() not in ("USA", "US", "UNITED STATES"):
        return None
    city_names = "|".join(CITIES)
    m = re.search(
        rf"([\d]+[^,]{{3,80}}?(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Plaza|Plz|Suite|Ste)\.?[^,]{{0,40}}?)\s*,?\s*({city_names})\s*,?\s*{re.escape(STATE_ABBR)}\b\s*(\d{{5}}(?:-\d{{4}})?)",
        text,
        re.IGNORECASE,
    )
    if m:
        return {
            "full_address": f"{m.group(1).strip()}, {m.group(2).strip().title()}, {STATE_ABBR} {m.group(3)}",
            "city": m.group(2).strip().title(),
            "state": STATE_ABBR,
        }
    m2 = re.search(
        rf"([^,]{{10,100}}?),?\s*({city_names}),?\s*{re.escape(STATE_ABBR)}\b[^0-9]{{0,10}}(\d{{5}}(?:-\d{{4}})?)",
        text,
        re.IGNORECASE,
    )
    if m2:
        return {
            "full_address": f"{m2.group(1).strip()}, {m2.group(2).strip().title()}, {STATE_ABBR} {m2.group(3)}",
            "city": m2.group(2).strip().title(),
            "state": STATE_ABBR,
        }
    return None


def extract_owner_name(text: str) -> str:
    for pat in OWNER_RE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return ""


def extract_schema_data(ld: dict, data: dict) -> None:
    if not isinstance(ld, dict):
        return

    types = ld.get("@type", "")
    if isinstance(types, str):
        types = [types]

    if "@graph" in ld:
        for item in ld["@graph"]:
            extract_schema_data(item, data)
    if "mainEntity" in ld and isinstance(ld["mainEntity"], dict):
        extract_schema_data(ld["mainEntity"], data)

    if not any(t in RELEVANT_SCHEMA_TYPES for t in types):
        return

    if not data.get("niche"):
        for t in types:
            if t in SCHEMA_TYPE_TO_NICHE:
                data["niche"] = SCHEMA_TYPE_TO_NICHE[t]
                break

    if not data.get("business_name") and ld.get("name"):
        data["business_name"] = str(ld["name"]).strip()

    if not data.get("phone") and ld.get("telephone"):
        data["phone"] = normalize_phone(str(ld["telephone"]))

    if not data.get("email") and ld.get("email"):
        candidate = str(ld["email"]).lower().strip()
        if not _is_false_positive_email(candidate):
            domain = candidate.split("@", 1)[1] if "@" in candidate else ""
            if verify_mx(domain):
                data["email"] = candidate

    addr = ld.get("address")
    if addr and not data.get("full_address"):
        if isinstance(addr, dict):
            street = addr.get("streetAddress", "")
            city = addr.get("addressLocality", "")
            state = addr.get("addressRegion", "")
            postal = addr.get("postalCode", "")
            parts = [p for p in [street, city, f"{state} {postal}".strip()] if p]
            if parts:
                data["full_address"] = ", ".join(parts)
            if not data.get("city") and city:
                data["city"] = city.title()
            if not data.get("state") and state:
                data["state"] = state.upper()
        elif isinstance(addr, str):
            data["full_address"] = addr

    if not data.get("owner_name"):
        for key in ("founder", "founders", "owner", "employee", "employees"):
            val = ld.get(key)
            if val:
                if isinstance(val, dict) and val.get("name"):
                    data["owner_name"] = str(val["name"]).strip()
                elif (
                    isinstance(val, list)
                    and val
                    and isinstance(val[0], dict)
                    and val[0].get("name")
                ):
                    data["owner_name"] = str(val[0]["name"]).strip()
                break
