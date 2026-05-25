"""Command-line entry point and orchestration."""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import threading

from .browser import SearchBrowser
from .config import MAX_CANDIDATES
from .enrichment import enrich_candidate
from .export import export_results
from .sources import build_queries, discover_chambers, discover_search_engines
from .utils import load_progress, log, save_progress

_PROGRESS_LOCK = threading.Lock()


def _override_config(args: argparse.Namespace) -> None:
    """Apply CLI overrides to the config module's globals."""
    from . import config

    if args.state:
        config.STATE = args.state
        config.STATE_ABBR = args.state_abbr or args.state[:2].upper()
    if args.state_abbr:
        config.STATE_ABBR = args.state_abbr
    if args.country:
        config.COUNTRY = args.country
        if config.COUNTRY.upper() not in ("USA", "US", "UNITED STATES"):
            config.CHAMBER_DIRECTORIES = []
    if args.cities:
        config.CITIES = [c.strip() for c in args.cities.split(",") if c.strip()]
    if args.max_candidates:
        config.MAX_CANDIDATES = args.max_candidates
    if args.niche:
        # Restrict to a single niche
        niche_key = args.niche
        if niche_key in config.NICHE_MAP:
            config.NICHE_MAP = {niche_key: config.NICHE_MAP[niche_key]}
            config.NICHE_KEYWORDS = [kw.lower() for kw in config.NICHE_MAP[niche_key]]
    if args.require_email:
        config.REQUIRE_EMAIL = True


def _merge_candidates(progress: dict, new_candidates: list[dict]) -> int:
    """Merge newly discovered candidates into progress, deduping by URL."""
    existing_urls = {c["url"] for c in progress.get("candidates", [])}
    added = 0
    for c in new_candidates:
        if c["url"] not in existing_urls:
            progress.setdefault("candidates", []).append(c)
            existing_urls.add(c["url"])
            added += 1
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="Stealth-enabled niche lead scraper with MX verification.")
    parser.add_argument("--state", default=os.getenv("SCRAPER_STATE"), help="Target state (e.g., Arizona)")
    parser.add_argument("--state-abbr", default=os.getenv("SCRAPER_STATE_ABBR"), help="State abbreviation (e.g., AZ)")
    parser.add_argument("--country", default=os.getenv("SCRAPER_COUNTRY"), help="Target country (e.g., USA, Pakistan)")
    parser.add_argument("--cities", default=os.getenv("SCRAPER_CITIES"), help="Comma-separated city list")
    parser.add_argument("--niche", help="Single niche key to run (e.g., 'Law firms')")
    parser.add_argument("--max-candidates", type=int, default=int(os.getenv("MAX_CANDIDATES", "2000")), help="Max candidates to enrich")
    parser.add_argument("--require-email", action="store_true", default=os.getenv("REQUIRE_EMAIL", "").lower() in ("1", "true", "yes"), help="Only accept leads with a verified email")
    args = parser.parse_args()

    _override_config(args)

    from . import config as cfg

    log(f"Leads Scraper starting — Country: {cfg.COUNTRY}, State: {cfg.STATE}, Cities: {len(cfg.CITIES)}")
    progress = load_progress()

    # Migration: old progress.json without persisted candidate pool
    if not progress.get("candidates") and progress.get("urls_seen"):
        urls = list(dict.fromkeys(progress.get("urls_seen", [])))
        log(f"Migrating old progress: reconstructing {len(urls)} candidates from urls_seen...")
        progress["candidates"] = [
            {"url": url, "source_type": "unknown", "source_url": url}
            for url in urls
        ]
        save_progress(progress)
        log("Migration complete. Saved to region-specific progress file.")

    # PHASE 1 — Chamber discovery (fast, requests-based; US only)
    chamber_candidates = discover_chambers(progress)
    if chamber_candidates:
        added = _merge_candidates(progress, chamber_candidates)
        if added:
            log(f"Phase 1: added {added} new chamber candidates")
        save_progress(progress)

    # PHASE 2 — Search engine discovery (Playwright, slower)
    current_pool_size = len(progress.get("candidates", []))
    if current_pool_size < MAX_CANDIDATES:
        browser = SearchBrowser()
        if browser.start():
            queries = build_queries()
            se_candidates = discover_search_engines(queries, progress, browser)
            if se_candidates:
                added = _merge_candidates(progress, se_candidates)
                if added:
                    log(f"Phase 2: added {added} new search-engine candidates")
                save_progress(progress)
            browser.stop()
        else:
            log("Skipping search engine discovery (browser unavailable).")
    else:
        log("Enough candidates in pool; skipping search engines.")

    all_candidates = progress.get("candidates", [])
    total_candidates = len(all_candidates)
    log(f"Total candidate pool size: {total_candidates}")

    # PHASE 3 — Enrichment (multithreaded)
    leads: list[dict] = progress.get("leads", [])
    rejected: list[dict] = progress.get("rejected", [])
    processed_urls: set[str] = set(progress.get("processed_urls", []))

    to_process = [c for c in all_candidates if c["url"] not in processed_urls]
    already_processed = total_candidates - len(to_process)
    if already_processed:
        log(f"Resuming: {already_processed} already processed, {len(to_process)} remaining")

    if not to_process:
        log("No new candidates to enrich.")
    else:
        log(
            f"Enriching {len(to_process)} candidates with {min(8, len(to_process))} threads..."
        )

    def _enrich_one(cand: dict) -> tuple[dict | None, str, dict]:
        try:
            lead, reason = enrich_candidate(cand)
            return lead, reason, cand
        except Exception as exc:
            return None, f"exception: {exc}", cand

    processed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_enrich_one, c): c for c in to_process}
        for future in concurrent.futures.as_completed(futures):
            if len(leads) >= MAX_CANDIDATES:
                log(f"Reached MAX_CANDIDATES ({MAX_CANDIDATES}). Stopping enrichment.")
                break

            lead, reason, cand = future.result()
            with _PROGRESS_LOCK:
                processed_count += 1
                processed_urls.add(cand["url"])
                if lead:
                    leads.append(lead)
                    progress["leads"] = leads
                    log(
                        f"  -> ACCEPTED ({processed_count}/{len(to_process)}): {lead['business_name'] or 'Unknown'} ({lead['niche'] or 'unknown'})"
                    )
                else:
                    rejected.append(
                        {
                            "url": cand["url"],
                            "source_type": cand.get("source_type", ""),
                            "source_url": cand.get("source_url", ""),
                            "business_name": cand.get("chamber_name", ""),
                            "rejection_reason": reason,
                        }
                    )
                    progress["rejected"] = rejected
                    log(
                        f"  -> REJECTED ({processed_count}/{len(to_process)}): {reason}"
                    )

                progress["processed_urls"] = list(processed_urls)
                if processed_count % 10 == 0:
                    save_progress(progress)

    save_progress(progress)

    # PHASE 4 — Export
    export_results(leads, rejected, progress, total_candidates)
    return 0
