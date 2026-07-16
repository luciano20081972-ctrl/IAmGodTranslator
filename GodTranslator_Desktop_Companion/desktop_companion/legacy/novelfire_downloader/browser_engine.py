from __future__ import annotations

from pathlib import Path
from typing import Callable


class BrowserEngine:
    def __init__(self, profile_dir: Path, timeout: int = 60) -> None:
        self.profile_dir = profile_dir
        self.timeout = timeout
        self._playwright = None
        self._context = None
        self._page = None

    def get_text(self, url: str, verification_callback: Callable[[str], None] | None = None) -> str:
        page = self.page()
        page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
        page.wait_for_timeout(1000)
        return page.content()

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
        return self._page

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
            self._page = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self) -> "BrowserEngine":
        self.page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
