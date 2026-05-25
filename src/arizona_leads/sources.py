"""Discovery sources: chamber directories and search engines."""

from __future__ import annotations

import base64
import urllib.parse

from bs4 import BeautifulSoup

from .browser import SearchBrowser
from . import config
from .config import (
    BLOCKLIST_DOMAINS,
    CITIES,
    COUNTRY,
    MAX_CANDIDATES,
    MIN_RESULTS_PER_QUERY,
    NICHE_MAP,
    SEARCH_ENGINE_FAILURE_THRESHOLD,
    SEARCH_ENGINES,
    STATE,
    STATE_ABBR,
)
from .utils import fetch_requests, log, normalize_domain, save_progress


def parse_chamber_address(addr_text: str) -> tuple[str, str, str]:
    city = ""
    state = ""
    full_address = addr_text
    for c in CITIES:
        if c in addr_text:
            parts = addr_text.split(c, 1)
            street = parts[0].rstrip(",").strip()
            rest = parts[1] if len(parts) > 1 else ""
            rest_clean = rest.replace(STATE_ABBR, f", {STATE_ABBR} ", 1).strip()
            rest_clean = rest_clean.replace(", ,", ",").replace("  ", " ")
            full_address = (
                f"{street}, {c}, {rest_clean}" if street else f"{c}, {rest_clean}"
            )
            full_address = full_address.strip().strip(",")
            city = c
            state = STATE_ABBR
            break
    return full_address, city, state


def discover_chamber(base_url: str, progress: dict) -> list[dict]:
    """Scrape a GrowthZone chamber directory (search-by-alpha pages)."""
    candidates: list[dict] = []
    letters = list("abcdefghijklmnopqrstuvwxyz")
    chamber_key = (
        base_url.replace("https://", "").replace("http://", "").replace("/", "_")
    )
    done_key = f"chamber_done_{chamber_key}"
    done_letters = set(progress.get(done_key, []))
    source_label = chamber_key.replace("business.", "").replace("_", "")

    for letter in letters:
        if letter in done_letters:
            continue

        url = f"{base_url}/list/searchalpha/{letter}"
        log(f"[Chamber {source_label}] Fetching letter {letter.upper()} — {url}")
        html = fetch_requests(url)
        if not html:
            log(f"  -> failed to fetch {url}")
            continue

        soup = BeautifulSoup(html, "lxml")
        wrappers = soup.find_all("div", class_="gz-list-card-wrapper")
        log(f"  -> found {len(wrappers)} cards")

        match_count = 0
        for w in wrappers:
            title_tag = w.find(class_="gz-card-title")
            if not title_tag:
                continue
            business_name = title_tag.get_text(strip=True)

            from .utils import matches_niche

            if not matches_niche(business_name):
                continue
            match_count += 1

            phone_tag = w.find(class_="gz-card-phone")
            addr_tag = w.find(class_="gz-card-address")
            website_tag = w.find(class_="gz-card-website")

            phone = phone_tag.get_text(strip=True) if phone_tag else ""
            full_address, city, state = "", "", ""
            if addr_tag:
                full_address, city, state = parse_chamber_address(
                    addr_tag.get_text(strip=True)
                )

            website = ""
            if website_tag:
                a = website_tag.find("a", href=True)
                if a:
                    website = str(a["href"])

            detail_url = ""
            for a in w.find_all("a", href=True):
                href = str(a["href"])
                if "/list/member/" in href:
                    detail_url = urllib.parse.urljoin(url, href)
                    break

            has_website = bool(website)
            candidate_url = website if has_website else detail_url
            if not candidate_url:
                continue

            candidates.append(
                {
                    "url": candidate_url,
                    "source_type": source_label,
                    "source_url": detail_url or url,
                    "chamber_name": business_name,
                    "chamber_phone": phone,
                    "chamber_address": full_address,
                    "chamber_city": city,
                    "chamber_state": state,
                    "chamber_only": not has_website,
                }
            )

        log(f"  -> {match_count} niche matches this page")
        done_letters.add(letter)
        progress[done_key] = list(done_letters)
        save_progress(progress)

    log(f"Chamber {source_label} discovery complete: {len(candidates)} candidates.")
    return candidates


def discover_chambers(progress: dict) -> list[dict]:
    """Run discovery across all configured chamber directories."""
    all_candidates: list[dict] = []
    for chamber_base in config.CHAMBER_DIRECTORIES:
        all_candidates.extend(discover_chamber(chamber_base, progress))
        if len(all_candidates) >= MAX_CANDIDATES:
            log("Enough candidates from chambers; stopping chamber discovery.")
            break
    return all_candidates


def discover_bing(query: str, browser: SearchBrowser) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    url = SEARCH_ENGINES["bing"].format(query=urllib.parse.quote_plus(query))
    html = browser.fetch(url)
    if not html:
        return urls
    soup = BeautifulSoup(html, "lxml")
    for li in soup.find_all("li", class_="b_algo"):
        a = li.find("h2")
        if a:
            a = a.find("a", href=True)
            if a:
                href = str(a["href"])
                if href.startswith("https://www.bing.com/ck/a?"):
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    u = qs.get("u", [""])[0]
                    if u.startswith("a1"):
                        b64 = u[2:]
                        pad = 4 - len(b64) % 4
                        if pad != 4:
                            b64 += "=" * pad
                        try:
                            real_url = base64.urlsafe_b64decode(b64).decode("utf-8")
                            if real_url.startswith("http"):
                                urls.append(("bing", real_url))
                        except Exception:
                            pass
                elif href.startswith("http"):
                    urls.append(("bing", href))
    return urls


def discover_startpage(query: str, browser: SearchBrowser) -> list[tuple[str, str]]:
    """Startpage proxies Google results and has lighter bot detection."""
    urls: list[tuple[str, str]] = []
    url = SEARCH_ENGINES["startpage"].format(query=urllib.parse.quote_plus(query))
    html = browser.fetch(url)
    if not html:
        return urls
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.startswith("http") and "startpage" not in href and "google" not in href:
            urls.append(("startpage", href))
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for src, u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append((src, u))
    return deduped


def discover_search_engines(
    queries: list[str], progress: dict, browser: SearchBrowser
) -> list[dict]:
    candidates: list[dict] = []
    urls_seen: set[str] = set(progress.get("urls_seen", []))
    queries_done: set[str] = set(progress.get("queries_done", []))
    consecutive_failures = 0

    engine_order = ["bing", "startpage"]

    for q in queries:
        if q in queries_done:
            continue
        if len(candidates) >= MAX_CANDIDATES:
            log("Search engine discovery: candidate pool full.")
            break

        log(f"[Search] Discovering: {q}")
        batch: list[tuple[str, str]] = []

        for engine in engine_order:
            if engine == "bing":
                batch.extend(discover_bing(q, browser))
            elif engine == "startpage":
                batch.extend(discover_startpage(q, browser))
            if len(batch) >= MIN_RESULTS_PER_QUERY:
                break

        added = 0
        for source_type, raw_url in batch:
            clean_url = urllib.parse.urldefrag(raw_url)[0]
            if clean_url in urls_seen:
                continue
            urls_seen.add(clean_url)
            domain = normalize_domain(clean_url)
            if domain in BLOCKLIST_DOMAINS:
                continue
            candidates.append(
                {
                    "url": clean_url,
                    "source_type": source_type,
                    "source_url": clean_url,
                    "query": q,
                }
            )
            added += 1

        log(f"  -> added {added} new URLs")
        if added == 0:
            consecutive_failures += 1
            if consecutive_failures >= SEARCH_ENGINE_FAILURE_THRESHOLD:
                log(
                    f"Search engines failed {consecutive_failures} times in a row — aborting SE discovery."
                )
                break
        else:
            consecutive_failures = 0

        queries_done.add(q)
        progress["queries_done"] = list(queries_done)
        progress["urls_seen"] = list(urls_seen)
        save_progress(progress)

    return candidates


def build_queries() -> list[str]:
    """Build search queries based on configured geography."""
    queries: list[str] = []
    state_lower = STATE.lower()
    abbr_lower = STATE_ABBR.lower()
    country_lower = COUNTRY.lower()

    # Generic niche + geography patterns
    for niche, keywords in NICHE_MAP.items():
        for kw in keywords:
            if COUNTRY.upper() in ("USA", "US", "UNITED STATES"):
                queries.append(f"{state_lower} {kw}")
                queries.append(f"{abbr_lower} {kw}")
            else:
                queries.append(f"{country_lower} {kw}")
                queries.append(f"{kw} in {country_lower}")

    # City-level queries (skip if no cities defined or if country-level broad mode desired)
    for niche, keywords in NICHE_MAP.items():
        for kw in keywords:
            for city in CITIES:
                if COUNTRY.upper() in ("USA", "US", "UNITED STATES"):
                    queries.append(f"{city} {kw}")
                    queries.append(f"{city} {abbr_lower} {kw}")
                else:
                    queries.append(f"{city} {country_lower} {kw}")
                    queries.append(f"{kw} in {city} {country_lower}")

    # Intent-style queries
    for niche, keywords in NICHE_MAP.items():
        for kw in keywords:
            if COUNTRY.upper() in ("USA", "US", "UNITED STATES"):
                queries.append(f"{kw} in {state_lower}")
                queries.append(f"best {kw} in {state_lower}")
            else:
                queries.append(f"{kw} in {country_lower}")
                queries.append(f"best {kw} in {country_lower}")

    return list(dict.fromkeys(queries))
