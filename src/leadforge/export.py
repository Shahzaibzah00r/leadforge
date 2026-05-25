"""Deduplication, WhatsApp checking, and export to CSV / JSON / Markdown."""

from __future__ import annotations

import concurrent.futures
import re
from typing import Optional
import threading
from datetime import datetime

import pandas as pd
import requests
import phonenumbers

from .config import (
    BLOCKLIST_DOMAINS,
    CHAMBER_DOMAINS,
    LEADS_CSV,
    LEADS_JSON,
    LEADS_NO_EMAIL_CSV,
    LEADS_WITH_EMAIL_CSV,
    REJECTED_CSV,
    REPORT_MD,
)
from .utils import get_rotated_headers, log, normalize_domain, verify_mx

_WHATSAPP_CACHE: dict[str, str] = {}
_WHATSAPP_LOCK = threading.Lock()
_GENERIC_EMAIL_RE = re.compile(r"^(info|contact|admin|support|hello)@.*")


def _format_e164(phone: str, default_region: Optional[str] = None) -> Optional[str]:
    """Return E.164 formatted phone string or None if invalid."""
    try:
        if phone.strip().startswith("+"):
            pn = phonenumbers.parse(phone, None)
        else:
            pn = phonenumbers.parse(phone, default_region or "US")
        if not phonenumbers.is_valid_number(pn):
            return None
        return phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        return None


def check_whatsapp(phone: str) -> str:
    """Robust WhatsApp availability check.

    Steps:
    - Validate phone using `phonenumbers` and convert to E.164.
    - Query `https://api.whatsapp.com/send?phone={E164_digits}` (GET).
    - Consider WhatsApp present only if the number is valid and the response
      or final URL indicates WhatsApp (redirects to web.whatsapp.com or contains
      whatsapp markers in the page).
    Returns: "yes" or "no".
    """
    if not phone:
        return "no"

    # Try to format/validate phone
    e164 = _format_e164(phone)
    if not e164:
        return "no"

    digits = re.sub(r"\D", "", e164)

    with _WHATSAPP_LOCK:
        if digits in _WHATSAPP_CACHE:
            return _WHATSAPP_CACHE[digits]

    result = "no"
    try:
        url = f"https://api.whatsapp.com/send?phone={digits}"
        resp = requests.get(url, headers=get_rotated_headers(), timeout=8, allow_redirects=True)

        final_url = getattr(resp, "url", "") or ""
        text = (resp.text or "").lower()

        # Heuristics asserting WhatsApp presence
        if resp.status_code in (200, 301, 302, 303, 307, 308):
            if (
                "web.whatsapp.com" in final_url
                or "api.whatsapp.com" in final_url
                or "phone=" in final_url
                or "whatsapp" in text
            ):
                result = "yes"
            else:
                # As a fallback, check wa.me redirect behavior
                wa_resp = requests.get(f"https://wa.me/{digits}", headers=get_rotated_headers(), timeout=8, allow_redirects=True)
                wa_final = getattr(wa_resp, "url", "") or ""
                if "web.whatsapp.com" in wa_final or "api.whatsapp.com" in wa_final:
                    result = "yes"
                else:
                    result = "no"
        else:
            result = "no"
    except Exception:
        result = "no"

    with _WHATSAPP_LOCK:
        _WHATSAPP_CACHE[digits] = result
    return result


def dedupe_leads(leads: list[dict]) -> tuple[list[dict], int]:
    seen_domains: set[str] = set()
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    unique: list[dict] = []
    duplicates = 0

    for lead in leads:
        domain = normalize_domain(lead.get("website", ""))
        email = lead.get("email", "").lower()
        phone = lead.get("phone", "")

        domain_is_real = (
            domain and domain not in CHAMBER_DOMAINS and domain not in BLOCKLIST_DOMAINS
        )
        email_is_real = (
            email
            and not _GENERIC_EMAIL_RE.match(email)
            and not any(email.endswith(f"@{d}") for d in CHAMBER_DOMAINS)
        )

        dup = False
        if domain_is_real and domain in seen_domains:
            dup = True
        elif email_is_real and email in seen_emails:
            dup = True
        elif phone and phone in seen_phones:
            dup = True

        if dup:
            duplicates += 1
            continue

        if domain_is_real:
            seen_domains.add(domain)
        if email_is_real:
            seen_emails.add(email)
        if phone:
            seen_phones.add(phone)
        unique.append(lead)

    return unique, duplicates


def export_results(
    leads: list[dict], rejected: list[dict], progress: dict, total_candidates: int
) -> None:
    deduped_leads, dup_count = dedupe_leads(leads)

    log("Checking WhatsApp for discovered phone numbers...")
    phones_to_check = [
        lead.get("phone", "") for lead in deduped_leads if lead.get("phone")
    ]
    unique_phones = list(dict.fromkeys(phones_to_check))
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        pool.map(check_whatsapp, unique_phones)

    for lead in deduped_leads:
        lead["whatsapp"] = check_whatsapp(lead.get("phone", ""))

    # Re-verify MX at export time for any email that lacks mx_status
    for lead in deduped_leads:
        email = lead.get("email", "")
        if email and not lead.get("mx_status"):
            domain = email.split("@", 1)[1]
            lead["domain"] = domain
            lead["mx_status"] = "valid" if verify_mx(domain) else "invalid"
        if not lead.get("target_url"):
            lead["target_url"] = lead.get("website", "")

    columns = [
        "target_url",
        "email",
        "domain",
        "mx_status",
        "business_name",
        "owner_name",
        "phone",
        "whatsapp",
        "city",
        "state",
        "full_address",
        "website",
        "niche",
        "source_type",
        "source_url",
        "notes",
    ]

    with_email = [lead for lead in deduped_leads if lead.get("email")]
    without_email = [lead for lead in deduped_leads if not lead.get("email")]

    for dataset, path in (
        (deduped_leads, LEADS_CSV),
        (with_email, LEADS_WITH_EMAIL_CSV),
        (without_email, LEADS_NO_EMAIL_CSV),
    ):
        df = pd.DataFrame(dataset)
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        if not df.empty:
            df = df[columns]
            df.to_csv(path, index=False)

    df_all = pd.DataFrame(deduped_leads)
    for col in columns:
        if col not in df_all.columns:
            df_all[col] = ""
    if not df_all.empty:
        df_all = df_all[columns]
    df_all.to_json(LEADS_JSON, orient="records", indent=2)

    rej_df = pd.DataFrame(rejected)
    if not rej_df.empty:
        rej_df.to_csv(REJECTED_CSV, index=False)

    lines = [
        "# Leads Scraper — Run Report",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## Summary",
        f"- Total candidate URLs discovered: {total_candidates}",
        f"- Total enriched rows: {len(leads) + len(rejected)}",
        f"- Total accepted leads: {len(deduped_leads)}",
        f"-   With email: {len(with_email)}",
        f"-   Without email: {len(without_email)}",
        f"- Total rejected candidates: {len(rejected)}",
        f"- Duplicates removed at export: {dup_count}",
        "",
        "## Leads by Niche",
    ]

    if not df.empty and "niche" in df.columns:
        for niche, count in df["niche"].value_counts().items():
            lines.append(f"- {niche}: {count}")
    else:
        lines.append("- No leads accepted.")

    lines.extend(["", "## Leads by City"])
    if not df_all.empty and "city" in df_all.columns:
        for city, count in df_all["city"].value_counts().items():
            lines.append(f"- {city}: {count}")
    else:
        lines.append("- No city data.")

    lines.extend(["", "## Data Quality"])
    if not df_all.empty:
        lines.append(f"- With email: {df_all['email'].astype(bool).sum()}")
        lines.append(f"- With phone: {df_all['phone'].astype(bool).sum()}")
        lines.append(f"- With owner_name: {df_all['owner_name'].astype(bool).sum()}")
        lines.append(f"- With valid MX: {(df_all['mx_status'] == 'valid').sum()}")
    else:
        lines.extend(["- With email: 0", "- With phone: 0", "- With owner_name: 0", "- With valid MX: 0"])

    lines.extend(["", "## Errors"])
    errors = progress.get("errors", [])
    lines.append(f"- Total errors: {len(errors)}")
    if errors:
        for err in errors[:10]:
            lines.append(f"  - `{err.get('url', '')}`: {err.get('error', '')}`")
        if len(errors) > 10:
            lines.append(f"  - ... and {len(errors) - 10} more")

    lines.extend(["", "## Top Sources"])
    if not df_all.empty and "source_type" in df_all.columns:
        for src, count in df_all["source_type"].value_counts().items():
            lines.append(f"- {src}: {count}")
    else:
        lines.append("- No data.")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log("Export complete.")
    log(f"  CSV (all)          : {LEADS_CSV.resolve()}")
    log(f"  CSV (with email)   : {LEADS_WITH_EMAIL_CSV.resolve()}")
    log(f"  CSV (no email)     : {LEADS_NO_EMAIL_CSV.resolve()}")
    log(f"  JSON               : {LEADS_JSON.resolve()}")
    log(f"  Report             : {REPORT_MD.resolve()}")
    if REJECTED_CSV.exists():
        log(f"  Rejected           : {REJECTED_CSV.resolve()}")
    log(f"  Accepted           : {len(deduped_leads)} leads ({len(with_email)} with email, {len(without_email)} without)")
