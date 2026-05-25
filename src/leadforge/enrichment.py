"""Candidate enrichment: visit pages and extract lead data with MX-verified emails."""

from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.parse

from bs4 import BeautifulSoup

from . import config
from .config import BLOCKLIST_DOMAINS, FALLBACK_PATHS, NICHE_MAP
from .extractors import (
    extract_address_from_text,
    extract_emails,
    extract_owner_name,
    extract_phones,
    extract_schema_data,
)
from .utils import (
    fetch_requests,
    get_city_from_text,
    guess_common_emails,
    is_generic_title,
    normalize_domain,
    normalize_phone,
    score_lead,
    search_domain_email,
    verify_mx,
    whois_email,
)


def infer_niche_from_query(query: str) -> str:
    q = query.lower()
    for niche, keywords in NICHE_MAP.items():
        for kw in keywords:
            if kw in q:
                return niche
    return ""


def infer_niche_from_text(text: str) -> str:
    t = text.lower()
    for niche, keywords in NICHE_MAP.items():
        for kw in keywords:
            if kw in t:
                return niche
    return ""


def _extract_from_html(html: str, url: str, data: dict) -> tuple[list[str], list[str], str]:
    """Parse HTML and update data dict. Returns (emails, phones, text)."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)

    emails = extract_emails(text, soup=soup, verify_mx_records=True)
    phones = extract_phones(text)

    for script in soup.find_all("script", type="application/ld+json"):
        script_text = script.string
        if not script_text:
            continue
        try:
            payload = json.loads(script_text)
            if isinstance(payload, list):
                for item in payload:
                    extract_schema_data(item, data)
            else:
                extract_schema_data(payload, data)
        except Exception:
            continue

    title = soup.title.get_text(strip=True) if soup.title else ""
    if title:
        title = re.split(r"[\|\-\–\—]", title)[0].strip()
        if title and not data["business_name"] and not is_generic_title(title):
            data["business_name"] = title

    if not data.get("owner_name"):
        owner = extract_owner_name(text)
        if owner:
            data["owner_name"] = owner

    if not data.get("full_address"):
        addr = extract_address_from_text(text)
        if addr:
            data.update(addr)

    return emails, phones, text


def _crawl_parallel(base_url: str, data: dict) -> tuple[list[str], list[str], list[str]]:
    """Fetch homepage first; if no emails, try paths in waves.
    Returns (all_emails, all_phones, all_texts).
    """
    all_emails: list[str] = []
    all_phones: list[str] = []
    all_texts: list[str] = []

    # Step 1: homepage
    homepage_html = fetch_requests(base_url)
    if homepage_html:
        emails, phones, text = _extract_from_html(homepage_html, base_url, data)
        all_emails.extend(emails)
        all_phones.extend(phones)
        all_texts.append(text)

    # Step 2: if homepage failed, try fallbacks sequentially (fast)
    if not homepage_html:
        for path in FALLBACK_PATHS:
            fb_url = urllib.parse.urljoin(base_url, path)
            html = fetch_requests(fb_url)
            if html:
                emails, phones, text = _extract_from_html(html, fb_url, data)
                all_emails.extend(emails)
                all_phones.extend(phones)
                all_texts.append(text)
                break
        return all_emails, all_phones, all_texts

    # Step 3: if homepage loaded but no emails, fire standard paths in parallel
    if not all_emails:
        standard_paths = [
            "/contact", "/contact-us", "/about", "/about-us",
            "/team", "/staff", "/locations", "/our-office",
            "/meet-the-team", "/leadership", "/company",
        ]
        future_to_path: dict[concurrent.futures.Future, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for path in standard_paths:
                page_url = urllib.parse.urljoin(base_url, path)
                future = pool.submit(fetch_requests, page_url)
                future_to_path[future] = page_url

            for future in concurrent.futures.as_completed(future_to_path):
                html = future.result()
                if html:
                    page_url = future_to_path[future]
                    emails, phones, text = _extract_from_html(html, page_url, data)
                    all_emails.extend(emails)
                    all_phones.extend(phones)
                    all_texts.append(text)

    # Step 4: still no emails — try extended paths (privacy, booking, providers, etc.)
    if not all_emails:
        extended_paths = [
            "/privacy", "/privacy-policy", "/book", "/book-appointment",
            "/appointment", "/request-appointment", "/schedule", "/office",
            "/our-doctors", "/meet-the-doctors", "/providers", "/physicians",
            "/dentists", "/attorneys", "/lawyers", "/partners",
        ]
        future_to_path = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for path in extended_paths:
                page_url = urllib.parse.urljoin(base_url, path)
                future = pool.submit(fetch_requests, page_url)
                future_to_path[future] = page_url

            for future in concurrent.futures.as_completed(future_to_path):
                html = future.result()
                if html:
                    page_url = future_to_path[future]
                    emails, phones, text = _extract_from_html(html, page_url, data)
                    all_emails.extend(emails)
                    all_phones.extend(phones)
                    all_texts.append(text)

    return all_emails, all_phones, all_texts


def enrich_candidate(candidate: dict) -> tuple[dict | None, str]:
    """
    Visit a candidate URL and extract lead fields.
    Returns (lead_dict, rejection_reason). Empty rejection_reason means accepted.
    """
    url = candidate["url"]

    # Skip blocked/aggregator domains that slipped into the candidate pool
    domain = normalize_domain(url)
    if domain in BLOCKLIST_DOMAINS:
        return None, "blocklisted_domain"

    data = {
        "business_name": "",
        "owner_name": "",
        "email": "",
        "phone": "",
        "city": "",
        "state": "",
        "full_address": "",
        "website": url,
        "niche": "",
        "source_type": candidate.get("source_type", ""),
        "source_url": candidate.get("source_url", ""),
        "notes": "",
        "domain": "",
        "mx_status": "",
        "target_url": url,
    }

    # Pre-seed with chamber data if available
    if candidate.get("chamber_name"):
        data["business_name"] = candidate["chamber_name"]
    if candidate.get("chamber_phone"):
        data["phone"] = candidate["chamber_phone"]
    if candidate.get("chamber_address"):
        data["full_address"] = candidate["chamber_address"]
    if candidate.get("chamber_city"):
        data["city"] = candidate["chamber_city"]
    if candidate.get("chamber_state"):
        data["state"] = candidate["chamber_state"]

    # Chamber-only candidates have no external website — they cannot have emails.
    # Skip them to focus on leads with actual websites.
    if candidate.get("chamber_only"):
        return None, "chamber_only_no_website"

    all_emails, all_phones, all_texts = _crawl_parallel(url, data)

    # Deduplicate
    unique_emails = []
    seen_emails: set[str] = set()
    for e in all_emails:
        if e not in seen_emails:
            seen_emails.add(e)
            unique_emails.append(e)

    unique_phones = []
    seen_phones: set[str] = set()
    for p in all_phones:
        np = normalize_phone(p)
        if np not in seen_phones:
            seen_phones.add(np)
            unique_phones.append(np)

    if not data.get("email") and unique_emails:
        data["email"] = unique_emails[0]
    if not data.get("phone") and unique_phones:
        data["phone"] = unique_phones[0]

    # Email recovery waterfall: try harder before giving up
    website_domain = normalize_domain(url)
    if not data.get("email") and website_domain and "." in website_domain:
        # Wave 1: common patterns + MX verify
        guessed = guess_common_emails(website_domain)
        if guessed:
            data["email"] = guessed[0]
            data["notes"] += f" | email guessed: {guessed[0]}"

        # Wave 2: whois lookup
        if not data.get("email"):
            whois_emails = whois_email(website_domain)
            if whois_emails:
                data["email"] = whois_emails[0]
                data["notes"] += f" | email from whois: {whois_emails[0]}"

        # Wave 3: search engine fallback
        if not data.get("email"):
            se_emails = search_domain_email(website_domain)
            if se_emails:
                data["email"] = se_emails[0]
                data["notes"] += f" | email from search: {se_emails[0]}"

    if not data.get("niche"):
        data["niche"] = infer_niche_from_query(candidate.get("query", ""))
    if not data.get("niche"):
        combined = " ".join(all_texts)
        data["niche"] = infer_niche_from_text(combined)

    if not data.get("city"):
        data["city"] = get_city_from_text(" ".join(all_texts))

    # Domain + MX status for the primary email
    if data.get("email"):
        domain = data["email"].split("@", 1)[1]
        data["domain"] = domain
        data["mx_status"] = "valid" if verify_mx(domain) else "invalid"
    else:
        data["domain"] = ""
        data["mx_status"] = ""

    # Acceptance: need score >= 2 AND at least phone or email
    if score_lead(data) < 2 or not (data.get("phone") or data.get("email")):
        return None, f"insufficient_data (score={score_lead(data)})"

    # If --require-email is set, reject leads without a verified email
    if config.REQUIRE_EMAIL and not data.get("email"):
        return None, "require_email: no email found"


    data["notes"] = (
        f"Discovered via {candidate.get('source_type', 'unknown')} query: {candidate.get('query', '')}"
    )
    return data, ""
