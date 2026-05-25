"""Playwright-based browser wrapper with stealth for search-engine scraping."""

from __future__ import annotations

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False

try:
    from playwright_stealth import Stealth

    HAS_STEALTH = True
except Exception:
    HAS_STEALTH = False

from .config import FETCH_TIMEOUT
from .utils import get_rotated_headers, log


class SearchBrowser:
    """Shared Playwright browser for search-engine result pages."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self) -> bool:
        if not HAS_PLAYWRIGHT:
            log("Playwright not available — skipping browser-based search engines.")
            return False
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            headers = get_rotated_headers()
            self.context = self.browser.new_context(
                user_agent=headers["User-Agent"],
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                extra_http_headers={
                    "Accept": headers["Accept"],
                    "Accept-Language": headers["Accept-Language"],
                    "Accept-Encoding": headers["Accept-Encoding"],
                    "DNT": headers["DNT"],
                    "Upgrade-Insecure-Requests": headers["Upgrade-Insecure-Requests"],
                },
            )
            self.page = self.context.new_page()
            if HAS_STEALTH:
                Stealth().apply_stealth_sync(self.page)
            return True
        except Exception as exc:
            log(f"Failed to start Playwright browser: {exc}")
            return False

    def fetch(self, url: str) -> str | None:
        if not self.page:
            return None
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=FETCH_TIMEOUT * 1000)
            self.page.wait_for_timeout(2000)
            return self.page.content()
        except Exception as exc:
            log(f"  browser fetch error for {url}: {exc}")
            return None

    def stop(self) -> None:
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
