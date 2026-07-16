from __future__ import annotations

import time

import requests


DEFAULT_USER_AGENT = "Mozilla/5.0 NovelFireLocalDownloader/1.0"


class HttpEngine:
    def __init__(self, timeout: int = 25, retries: int = 2, delay: float = 2.0) -> None:
        self.timeout = timeout
        self.retries = retries
        self.delay = max(0.0, delay)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                response.encoding = response.encoding or response.apparent_encoding or "utf-8"
                return response.text
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2.0 + attempt, 5.0))
        raise RuntimeError(f"HTTP fetch failed for {url}: {last_error}") from last_error

    def polite_delay(self) -> None:
        if self.delay:
            time.sleep(self.delay)

