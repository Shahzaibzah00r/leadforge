"""Shared utilities: logging, normalization, fetch helpers, progress I/O, MX verify."""

from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
from datetime import datetime

import requests
import tldextract
from dns import resolver as dns_resolver
from dns.exception import DNSException
from fake_useragent import UserAgent

from . import config
from .config import EMAIL_RE, FETCH_TIMEOUT

try:
    from curl_cffi import requests as curl_requests

    HAS_CURL_CFFI = True
except Exception:
    HAS_CURL_CFFI = False
    curl_requests = None  # type: ignore[misc]


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


_ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def get_rotated_headers() -> dict[str, str]:
    return {
        "User-Agent": _ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def normalize_domain(url: str) -> str:
    ext = tldextract.extract(url)
    return getattr(ext, "top_domain_under_public_suffix", ext.registered_domain).lower()


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def get_city_from_text(text: str) -> str:
    t = text.lower()
    for city in config.CITIES:
        if city.lower() in t:
            return city
    return ""


def matches_niche(name: str) -> bool:
    name_lower = name.lower()
    for kw in config.NICHE_KEYWORDS:
        if kw in name_lower:
            return True
    return False


def score_lead(data: dict) -> int:
    """Count how many core fields are populated."""
    s = 0
    if data.get("business_name"):
        s += 1
    if data.get("website"):
        s += 1
    if data.get("phone"):
        s += 1
    if data.get("email"):
        s += 1
    if data.get("full_address") or data.get("city") or data.get("state"):
        s += 1
    return s


def is_generic_title(title: str) -> bool:
    """Reject page titles that are clearly not business names."""
    return title.strip().lower() in config.GENERIC_TITLES


def verify_mx(domain: str) -> bool:
    """Check whether a domain has MX records using dnspython."""
    if not domain or "." not in domain:
        return False
    try:
        answers = dns_resolver.resolve(domain, "MX", lifetime=5)
        return len(answers) > 0
    except DNSException:
        return False
    except Exception:
        return False


def guess_common_emails(domain: str) -> list[str]:
    """Generate and verify common email prefixes for a domain."""
    from .config import COMMON_EMAIL_PREFIXES

    emails: list[str] = []
    for prefix in COMMON_EMAIL_PREFIXES:
        email = f"{prefix}@{domain}"
        if verify_mx(domain):
            emails.append(email)
    return emails


def whois_email(domain: str) -> list[str]:
    """Try to extract admin/tech emails from whois data."""
    try:
        import subprocess
        result = subprocess.run(
            ["whois", domain],
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = result.stdout
        found = set(EMAIL_RE.findall(text))
        # Filter out registrar abuse emails and keep likely business emails
        filtered: list[str] = []
        for e in found:
            el = e.lower()
            if any(x in el for x in ("abuse", "noc", "security", "dns", "iana")):
                continue
            if "@" in el and "." in el.split("@", 1)[1]:
                filtered.append(el)
        return filtered
    except Exception:
        return []


def search_domain_email(domain: str) -> list[str]:
    """Search DuckDuckGo for emails associated with a domain."""
    try:
        query = f"{domain} email contact"
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        resp = requests.get(url, headers=get_rotated_headers(), timeout=FETCH_TIMEOUT)
        if resp.status_code == 200:
            text = resp.text
            # Look for emails in the search results
            found = set(EMAIL_RE.findall(text))
            # Keep only emails matching the target domain
            matched = [e.lower() for e in found if domain.lower() in e.lower()]
            # Verify MX before returning
            verified = []
            for e in matched:
                d = e.split("@", 1)[1]
                if verify_mx(d):
                    verified.append(e)
            return verified
    except Exception:
        pass
    return []


# Cloudflare challenge/interstitial detection
# Only strong HTML markers — headers like cf-ray appear on *every* Cloudflare-proxied site.
_CF_CHALLENGE_MARKERS = [
    "cf-im-under-attack",
    "challenge-platform",
    "jschl-answer",
    "__cf_bm",
    "managed by cloudflare",
    "ddos protection by cloudflare",
    "challenge-form",
    "cf-browser-verification",
    "cf-challenge-running",
    "cf-chl-widget-",
]


def is_cloudflare_block(html: str, headers: dict) -> bool:
    """Detect actual Cloudflare challenge/block pages (not normal CDN-proxied sites)."""
    server = headers.get("Server", "").lower()
    is_cf_server = "cloudflare" in server

    html_lower = html.lower()
    has_challenge_marker = any(marker in html_lower for marker in _CF_CHALLENGE_MARKERS)

    # Only flag as blocked if we see challenge HTML content.
    # CDN headers alone (cf-ray, etc.) are NOT enough — they appear on normal pages.
    if has_challenge_marker:
        return True

    # Fallback: if the Server header says Cloudflare AND the body is very short,
    # it might be a bare block page without the usual challenge markers.
    if is_cf_server and len(html) < 800:
        return True

    return False


def fetch_requests(url: str) -> str | None:
    """Fast requests fetch with stealth headers, random delay, CF detection, and curl_cffi fallback.

    curl_cffi is ONLY used when the failure looks like a Cloudflare block or hard 403/503.
    Network errors (timeout, DNS, connection refused) are not retried because curl_cffi
    cannot fix those.
    """
    time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))

    # Fast path: standard requests
    try:
        resp = requests.get(
            url,
            headers=get_rotated_headers(),
            timeout=config.FETCH_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 200 and len(resp.text) > 200:
            if is_cloudflare_block(resp.text, dict(resp.headers)):
                # CF block detected - try curl_cffi
                pass
            else:
                return resp.text
        elif resp.status_code in (403, 503, 429, 401):
            # Might be CF or rate limit - try curl_cffi
            pass
        else:
            return None
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        # Network issues - curl_cffi won't help; fail fast
        return None
    except requests.exceptions.RequestException as exc:
        log(f"  Request error for {url}: {exc}")
        return None

    # Fallback: curl_cffi with Chrome impersonation (only for CF-like blocks)
    if HAS_CURL_CFFI and curl_requests is not None:
        try:
            resp = curl_requests.get(
                url,
                headers=get_rotated_headers(),
                timeout=config.FETCH_TIMEOUT,
                impersonate="chrome124",
            )
            if resp.status_code == 200 and len(resp.text) > 200:
                if is_cloudflare_block(resp.text, dict(resp.headers)):
                    log(f"  Cloudflare block persists for {url}")
                    return None
                log(f"  curl_cffi recovered {url}")
                return resp.text
        except Exception as exc:
            log(f"  curl_cffi error for {url}: {exc}")

    return None


def fetch_with_fallback(base_url: str) -> list[tuple[str, str]]:
    """Fetch homepage; if it fails or is too short, try fallback paths.
    Returns list of (url, html) tuples.
    """
    results: list[tuple[str, str]] = []
    homepage = fetch_requests(base_url)
    if homepage:
        results.append((base_url, homepage))
    else:
        log(f"  Homepage failed for {base_url}; trying fallbacks...")
        for path in config.FALLBACK_PATHS:
            from urllib.parse import urljoin

            fb_url = urljoin(base_url, path)
            html = fetch_requests(fb_url)
            if html:
                results.append((fb_url, html))
                break
    return results


def load_progress() -> dict:
    pf = config.get_progress_file()
    if pf.exists():
        with open(pf, "r", encoding="utf-8") as f:
            return json.load(f)
    # Backward compat: only fall back to old generic progress.json for the default region
    if config.COUNTRY.upper() in ("USA", "US", "UNITED STATES") and config.STATE == "Arizona":
        old_pf = config.OUTPUT_DIR / "progress.json"
        if old_pf.exists():
            with open(old_pf, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "chamber_letters_done": [],
        "chamber_done": [],
        "queries_done": [],
        "urls_seen": [],
        "processed_urls": [],
        "candidates": [],
        "leads": [],
        "rejected": [],
        "errors": [],
    }


def save_progress(progress: dict) -> None:
    pf = config.get_progress_file()
    with open(pf, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, default=str)
