from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin


RETRYABLE_FAILURES = {"rate_limited", "timeout", "network", "provider_internal"}


class AcquisitionError(RuntimeError):
    def __init__(self, category: str, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = category in RETRYABLE_FAILURES if retryable is None else retryable


@dataclass(frozen=True)
class AcquisitionRequest:
    source_url: str
    chapter_number: int | None = None
    timeout_seconds: float = 30.0
    max_pages: int = 1
    allowed_domains: list[str] = field(default_factory=list)
    path_prefixes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AcquiredPage:
    source_url: str
    canonical_url: str
    provider: str
    title: str = ""
    text: str = ""
    html: str = ""
    discovered_links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    request_count: int = 1

    @property
    def content(self) -> str:
        return self.text or html_to_text(self.html)


class AcquisitionProvider(Protocol):
    name: str
    display_name: str
    uses_cloud: bool

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        ...


class UrlLibJsonClient:
    def post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            category = http_failure_category(exc.code)
            raise AcquisitionError(category, f"Provider returned HTTP {exc.code}") from exc
        except TimeoutError as exc:
            raise AcquisitionError("timeout", "Provider request timed out") from exc
        except OSError as exc:
            raise AcquisitionError("network", exc.__class__.__name__) from exc


class FirecrawlProvider:
    name = "firecrawl"
    display_name = "Firecrawl"
    uses_cloud = True

    def __init__(self, api_key: str | None = None, base_url: str | None = None, client: UrlLibJsonClient | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "")
        self.base_url = (base_url or os.getenv("FIRECRAWL_BASE_URL") or "https://api.firecrawl.dev").rstrip("/")
        self.client = client or UrlLibJsonClient()

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        if not self.api_key:
            raise AcquisitionError("configuration_missing", "FIRECRAWL_API_KEY is not configured", retryable=False)
        started = time.perf_counter()
        if cancel is not None and cancel.is_set():
            raise AcquisitionError("canceled", "Acquisition cancelled", retryable=False)
        payload = {
            "url": request.source_url,
            "formats": ["markdown", "html", "links"],
            "onlyMainContent": True,
        }
        response = self.client.post_json(
            f"{self.base_url}/v2/scrape",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload,
            request.timeout_seconds,
        )
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        text = str(data.get("markdown") or data.get("text") or "")
        html = str(data.get("html") or "")
        title = str(data.get("metadata", {}).get("title") or data.get("title") or "")
        canonical = str(data.get("metadata", {}).get("sourceURL") or data.get("url") or request.source_url)
        links = [str(item) for item in data.get("links", []) if isinstance(item, str)]
        if not (text or html):
            raise AcquisitionError("empty_content", "Firecrawl returned no chapter content", retryable=False)
        return AcquiredPage(
            source_url=request.source_url,
            canonical_url=canonical,
            provider=self.name,
            title=title,
            text=text,
            html=html,
            discovered_links=links[: request.max_pages],
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )


class ApifyProvider:
    name = "apify"
    display_name = "Apify"
    uses_cloud = True

    def __init__(self, api_token: str | None = None, actor_id: str | None = None, base_url: str | None = None, client: UrlLibJsonClient | None = None) -> None:
        self.api_token = api_token if api_token is not None else os.getenv("APIFY_API_TOKEN", "")
        self.actor_id = actor_id or os.getenv("APIFY_CHAPTER_ACTOR_ID", "")
        self.base_url = (base_url or os.getenv("APIFY_BASE_URL") or "https://api.apify.com/v2").rstrip("/")
        self.client = client or UrlLibJsonClient()

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        if not self.api_token:
            raise AcquisitionError("configuration_missing", "APIFY_API_TOKEN is not configured", retryable=False)
        if not is_allowed_apify_actor(self.actor_id):
            raise AcquisitionError("unsupported_source", "Apify Actor is not allowlisted", retryable=False)
        started = time.perf_counter()
        if cancel is not None and cancel.is_set():
            raise AcquisitionError("canceled", "Acquisition cancelled", retryable=False)
        actor_path = self.actor_id.replace("/", "~")
        response = self.client.post_json(
            f"{self.base_url}/acts/{actor_path}/run-sync-get-dataset-items",
            {"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"},
            {"startUrls": [{"url": request.source_url}], "maxPages": request.max_pages},
            request.timeout_seconds,
        )
        items = response if isinstance(response, list) else response.get("items", [])
        item = next((entry for entry in items if isinstance(entry, dict)), {})
        text = str(item.get("markdown") or item.get("text") or item.get("content") or "")
        html = str(item.get("html") or "")
        title = str(item.get("title") or "")
        canonical = str(item.get("canonicalUrl") or item.get("url") or request.source_url)
        if not (text or html):
            raise AcquisitionError("empty_content", "Apify Actor returned no chapter content", retryable=False)
        return AcquiredPage(
            source_url=request.source_url,
            canonical_url=canonical,
            provider=self.name,
            title=title,
            text=text,
            html=html,
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )


class DirectHttpProvider:
    name = "direct_http"
    display_name = "Direct HTTP"
    uses_cloud = False

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request.source_url, timeout=request.timeout_seconds) as response:
                html = response.read().decode("utf-8", errors="replace")
                canonical = response.url or request.source_url
        except TimeoutError as exc:
            raise AcquisitionError("timeout", "Direct HTTP request timed out") from exc
        except OSError as exc:
            raise AcquisitionError("network", exc.__class__.__name__) from exc
        if not html_to_text(html):
            raise AcquisitionError("empty_content", "Direct HTTP returned no readable content", retryable=False)
        return AcquiredPage(request.source_url, canonical, self.name, html=html, elapsed_seconds=round(time.perf_counter() - started, 3))


PROVIDERS: dict[str, type[AcquisitionProvider]] = {
    "direct_http": DirectHttpProvider,
    "firecrawl": FirecrawlProvider,
    "apify": ApifyProvider,
}


def is_allowed_apify_actor(actor_id: str) -> bool:
    allowed = {item.strip() for item in os.getenv("APIFY_ALLOWED_ACTORS", "").split(",") if item.strip()}
    return bool(actor_id and actor_id in allowed)


def http_failure_category(status: int) -> str:
    if status == 401:
        return "authentication_failed"
    if status == 403:
        return "blocked/restricted"
    if status == 408:
        return "timeout"
    if status == 429:
        return "rate_limited"
    if 500 <= status:
        return "provider_internal"
    return "unsupported_source"


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def chapter_url(source_url: str, chapter: int) -> str:
    if "{chapter}" in source_url:
        return source_url.replace("{chapter}", str(chapter))
    if "{chapter:04d}" in source_url:
        return source_url.replace("{chapter:04d}", f"{chapter:04d}")
    return urljoin(source_url.rstrip("/") + "/", f"chapter-{chapter}")
