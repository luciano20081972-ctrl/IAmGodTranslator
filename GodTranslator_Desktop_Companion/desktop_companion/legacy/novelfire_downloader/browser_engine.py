from __future__ import annotations

from pathlib import Path
from typing import Callable

from .validation import blocked_reason


CHALLENGE_REASONS = {"cloudflare", "checking your browser", "just a moment", "captcha", "verify you are human"}


class BrowserEngine:
    def __init__(self, profile_dir: Path, timeout: int = 60, log: Callable[[str], None] | None = None) -> None:
        self.profile_dir = profile_dir
        self.timeout = timeout
        self.log = log
        self._playwright = None
        self._context = None
        self._page = None

    def get_text(self, url: str, verification_callback: Callable[[str], None] | None = None) -> str:
        self._log(f"Opening Browser: {url}")
        page = self.page()
        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        page.wait_for_timeout(1000)
        html = page.content()
        reason = blocked_reason(html)
        if reason in CHALLENGE_REASONS:
            self._log(f"Waiting Cloudflare challenge: {reason}")
            waited = 0
            while waited < self.timeout:
                if verification_callback:
                    verification_callback(url)
                page.wait_for_timeout(2000)
                waited += 2
                html = page.content()
                if blocked_reason(html) not in CHALLENGE_REASONS:
                    self._log("Cloudflare passed")
                    break
        return html

    def page(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Browser Mode requires Playwright. Run SETUP_ONCE.bat first.") from exc

        if self._context is None:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self._playwright = sync_playwright().start()
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                channel="chrome",
                headless=False,
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self._log("Browser launched")
        return self._page

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
            self._page = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._log("Browser closed")

    def __enter__(self) -> "BrowserEngine":
        self.page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _log(self, message: str) -> None:
        if self.log:
            self.log(message)
