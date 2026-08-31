from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit
from hashlib import sha256


RETRYABLE_FAILURES = {"rate_limited", "timeout", "network", "dns", "tls", "provider_internal", "crawl_failed", "actor_failed"}
PERMANENT_FAILURES = {
    "configuration_missing",
    "authentication_failed",
    "authorization_failed",
    "quota_exhausted",
    "blocked_or_restricted",
    "unsupported_source",
    "parse_failed",
    "empty_content",
    "invalid_response",
    "canceled",
    "job_removed",
}


class AcquisitionError(RuntimeError):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        provider: str = "",
        retryable: bool | None = None,
        status_code: int | None = None,
        suggested_action: str = "",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.provider = provider
        self.retryable = category in RETRYABLE_FAILURES if retryable is None else retryable
        self.status_code = status_code
        self.suggested_action = suggested_action

    def safe_payload(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "provider": self.provider,
            "safe_message": str(self),
            "retryable": self.retryable,
            "status_code": self.status_code,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_single_page: bool = False
    supports_discovery: bool = False
    supports_chapter_discovery: bool = False
    supports_js_rendering: bool = False
    supports_bounded_crawl: bool = False
    supports_structured_output: bool = False
    supports_markdown: bool = False
    supports_html: bool = False
    supports_cancel: bool = False
    supports_async_jobs: bool = False
    requires_external_credit: bool = False
    requires_local_browser: bool = False
    supports_retry: bool = False
    supports_progress: bool = False
    supports_domain_scope: bool = False
    supports_path_scope: bool = False


@dataclass(frozen=True)
class ProviderPolicy:
    allow_cloud_providers: bool = False
    allow_firecrawl_auto: bool = False
    allow_apify_auto: bool = False
    prefer_free_local: bool = True
    cloud_fallback_only: bool = True


@dataclass
class SourceAcquisitionProfile:
    preferred_provider: str = ""
    successful_provider: str = ""
    last_provider: str = ""
    provider_failure_class: str = ""
    supports_direct: bool | None = None
    requires_js: bool = False
    last_success_at: str = ""
    recent_success_rate: float | None = None


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
    provider_request_id: str = ""
    content_format: str = "markdown"
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    provider_usage: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.text or html_to_text(self.html)


class AcquisitionProvider(Protocol):
    name: str
    display_name: str
    uses_cloud: bool
    capabilities: ProviderCapabilities

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        ...

    def discover_chapters(self, request: AcquisitionRequest, cancel: Any | None = None) -> list["NormalizedChapter"]:
        ...


class UrlLibJsonClient:
    def get_json(self, url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            category = http_failure_category(exc.code)
            raise AcquisitionError(category, f"Provider returned HTTP {exc.code}", status_code=exc.code) from exc
        except TimeoutError as exc:
            raise AcquisitionError("timeout", "Provider request timed out") from exc
        except OSError as exc:
            raise AcquisitionError("network", exc.__class__.__name__) from exc

    def post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            category = http_failure_category(exc.code)
            raise AcquisitionError(category, f"Provider returned HTTP {exc.code}", status_code=exc.code) from exc
        except TimeoutError as exc:
            raise AcquisitionError("timeout", "Provider request timed out") from exc
        except OSError as exc:
            raise AcquisitionError("network", exc.__class__.__name__) from exc

    def delete_json(self, url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        request = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            category = http_failure_category(exc.code)
            raise AcquisitionError(category, f"Provider returned HTTP {exc.code}", status_code=exc.code) from exc
        except TimeoutError as exc:
            raise AcquisitionError("timeout", "Provider request timed out") from exc
        except OSError as exc:
            raise AcquisitionError("network", exc.__class__.__name__) from exc


class FirecrawlProvider:
    name = "firecrawl"
    display_name = "Firecrawl"
    uses_cloud = True
    capabilities = ProviderCapabilities(
        supports_single_page=True,
        supports_discovery=True,
        supports_chapter_discovery=True,
        supports_js_rendering=True,
        supports_bounded_crawl=True,
        supports_structured_output=True,
        supports_markdown=True,
        supports_html=True,
        supports_cancel=True,
        supports_async_jobs=True,
        requires_external_credit=True,
        supports_retry=True,
        supports_progress=True,
        supports_domain_scope=True,
        supports_path_scope=True,
    )

    def __init__(self, api_key: str | None = None, base_url: str | None = None, client: UrlLibJsonClient | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("FIRECRAWL_API_KEY", "")
        self.base_url = (base_url or os.getenv("FIRECRAWL_BASE_URL") or "https://api.firecrawl.dev").rstrip("/")
        self.client = client or UrlLibJsonClient()

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        if not self.api_key:
            raise AcquisitionError("configuration_missing", "FIRECRAWL_API_KEY is not configured", provider=self.name, retryable=False)
        validate_public_source_url(request.source_url, request.allowed_domains, request.path_prefixes)
        started = time.perf_counter()
        if cancel is not None and cancel.is_set():
            raise AcquisitionError("canceled", "Acquisition cancelled", provider=self.name, retryable=False)
        payload = {
            "url": request.source_url,
            "formats": ["markdown", "html", "links", {"type": "json", "schema": chapter_json_schema()}],
            "onlyMainContent": True,
            "timeout": int(request.timeout_seconds * 1000),
        }
        response = self.client.post_json(
            f"{self.base_url}/v2/scrape",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload,
            request.timeout_seconds,
        )
        if response.get("success") is False:
            raise AcquisitionError("invalid_response", "Firecrawl returned unsuccessful response", provider=self.name, retryable=False)
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        text = str(data.get("markdown") or data.get("text") or "")
        html = str(data.get("html") or "")
        structured = data.get("json") if isinstance(data.get("json"), dict) else {}
        if structured:
            text = str(structured.get("chapter_body") or text)
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {}
        title = str(structured.get("chapter_title") or metadata.get("title") or data.get("title") or "")
        canonical = str(metadata.get("sourceURL") or metadata.get("url") or data.get("url") or request.source_url)
        links = normalize_links(data.get("links", []), request.source_url)
        if not (text or html):
            raise AcquisitionError("empty_content", "Firecrawl returned no chapter content", provider=self.name, retryable=False)
        return AcquiredPage(
            source_url=request.source_url,
            canonical_url=canonical,
            provider=self.name,
            title=title,
            text=text,
            html=html,
            discovered_links=filter_scoped_links(links, request)[: request.max_pages],
            elapsed_seconds=round(time.perf_counter() - started, 3),
            provider_request_id=str(metadata.get("scrapeId") or data.get("id") or ""),
            raw_metadata=safe_metadata(metadata),
            provider_usage=safe_metadata(response.get("usage") if isinstance(response.get("usage"), dict) else {}),
        )

    def discover_chapters(self, request: AcquisitionRequest, cancel: Any | None = None) -> list["NormalizedChapter"]:
        if not self.api_key:
            raise AcquisitionError("configuration_missing", "FIRECRAWL_API_KEY is not configured", provider=self.name, retryable=False)
        validate_public_source_url(request.source_url, request.allowed_domains, request.path_prefixes)
        if cancel is not None and cancel.is_set():
            raise AcquisitionError("canceled", "Acquisition cancelled", provider=self.name, retryable=False)
        response = self.client.post_json(
            f"{self.base_url}/v2/map",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            {"url": request.source_url, "limit": request.max_pages, "ignoreQueryParameters": True, "timeout": int(request.timeout_seconds * 1000)},
            request.timeout_seconds,
        )
        links = response.get("links") if isinstance(response.get("links"), list) else []
        chapters: list[NormalizedChapter] = []
        for item in links:
            if isinstance(item, dict):
                url = str(item.get("url") or "")
                title = str(item.get("title") or "")
            else:
                url = str(item)
                title = ""
            if not url:
                continue
            scoped = filter_scoped_links([url], request)
            if not scoped:
                continue
            hint = chapter_hint(title or url)
            if not hint and "chapter" not in url.lower():
                continue
            chapters.append(NormalizedChapter.from_page(AcquiredPage(request.source_url, scoped[0], self.name, title=title, text="", discovered_links=[], warnings=[]), chapter_hint=hint))
        return dedupe_chapters(chapters)[: request.max_pages]

    def bounded_crawl(self, request: AcquisitionRequest, cancel: Any | None = None, poll_interval: float = 0.5, max_polls: int = 20) -> list["NormalizedChapter"]:
        if not self.api_key:
            raise AcquisitionError("configuration_missing", "FIRECRAWL_API_KEY is not configured", provider=self.name, retryable=False)
        validate_public_source_url(request.source_url, request.allowed_domains, request.path_prefixes)
        if not request.allowed_domains or not request.path_prefixes or request.max_pages < 1:
            raise AcquisitionError("blocked_or_restricted", "Firecrawl crawl requires explicit domain, path, and page limits", provider=self.name, retryable=False)
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        start = self.client.post_json(
            f"{self.base_url}/v2/crawl",
            headers,
            {
                "url": request.source_url,
                "includePaths": request.path_prefixes,
                "limit": request.max_pages,
                "crawlEntireDomain": False,
                "allowExternalLinks": False,
                "allowSubdomains": False,
                "ignoreQueryParameters": True,
                "scrapeOptions": {"formats": ["markdown", "html"], "onlyMainContent": True, "timeout": int(request.timeout_seconds * 1000)},
            },
            request.timeout_seconds,
        )
        crawl_id = str(start.get("id") or "")
        if not crawl_id:
            raise AcquisitionError("invalid_response", "Firecrawl crawl did not return a job id", provider=self.name, retryable=False)
        for _ in range(max_polls):
            if cancel is not None and cancel.is_set():
                self.cancel_crawl(crawl_id, request.timeout_seconds)
                raise AcquisitionError("canceled", "Firecrawl crawl cancelled", provider=self.name, retryable=False)
            status = self.client.get_json(f"{self.base_url}/v2/crawl/{crawl_id}", headers, request.timeout_seconds)
            if status.get("status") == "failed":
                raise AcquisitionError("crawl_failed", "Firecrawl crawl failed", provider=self.name)
            if status.get("status") == "completed":
                pages = status.get("data") if isinstance(status.get("data"), list) else []
                chapters = []
                for page_data in pages:
                    if not isinstance(page_data, dict):
                        continue
                    metadata = page_data.get("metadata", {}) if isinstance(page_data.get("metadata"), dict) else {}
                    final_url = str(metadata.get("sourceURL") or page_data.get("url") or request.source_url)
                    if not filter_scoped_links([final_url], request):
                        continue
                    page = AcquiredPage(
                        source_url=request.source_url,
                        canonical_url=final_url,
                        provider=self.name,
                        title=str(metadata.get("title") or page_data.get("title") or ""),
                        text=str(page_data.get("markdown") or page_data.get("text") or ""),
                        html=str(page_data.get("html") or ""),
                        provider_request_id=crawl_id,
                        raw_metadata=safe_metadata(metadata),
                    )
                    chapters.append(NormalizedChapter.from_page(page))
                return dedupe_chapters(chapters)[: request.max_pages]
            time.sleep(poll_interval)
        raise AcquisitionError("timeout", "Firecrawl crawl did not complete before timeout", provider=self.name)

    def cancel_crawl(self, crawl_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
        return self.client.delete_json(f"{self.base_url}/v2/crawl/{crawl_id}", {"Authorization": f"Bearer {self.api_key}"}, timeout_seconds)


class ApifyProvider:
    name = "apify"
    display_name = "Apify"
    uses_cloud = True
    capabilities = ProviderCapabilities(
        supports_single_page=True,
        supports_discovery=True,
        supports_chapter_discovery=True,
        supports_js_rendering=True,
        supports_bounded_crawl=True,
        supports_structured_output=True,
        supports_markdown=True,
        supports_html=True,
        supports_cancel=True,
        supports_async_jobs=True,
        requires_external_credit=True,
        supports_retry=True,
        supports_progress=True,
        supports_domain_scope=True,
        supports_path_scope=True,
    )

    def __init__(self, api_token: str | None = None, actor_id: str | None = None, base_url: str | None = None, client: UrlLibJsonClient | None = None) -> None:
        self.api_token = api_token if api_token is not None else os.getenv("APIFY_API_TOKEN", "")
        self.actor_id = actor_id or os.getenv("APIFY_CHAPTER_ACTOR_ID", "")
        self.base_url = (base_url or os.getenv("APIFY_BASE_URL") or "https://api.apify.com/v2").rstrip("/")
        self.client = client or UrlLibJsonClient()

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        if not self.api_token:
            raise AcquisitionError("configuration_missing", "APIFY_API_TOKEN is not configured", provider=self.name, retryable=False)
        if not is_allowed_apify_actor(self.actor_id):
            raise AcquisitionError("unsupported_source", "Apify Actor is not allowlisted", provider=self.name, retryable=False)
        validate_public_source_url(request.source_url, request.allowed_domains, request.path_prefixes)
        started = time.perf_counter()
        if cancel is not None and cancel.is_set():
            raise AcquisitionError("canceled", "Acquisition cancelled", provider=self.name, retryable=False)
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
            raise AcquisitionError("empty_content", "Apify Actor returned no chapter content", provider=self.name, retryable=False)
        return AcquiredPage(
            source_url=request.source_url,
            canonical_url=canonical,
            provider=self.name,
            title=title,
            text=text,
            html=html,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            provider_request_id=str(item.get("runId") or item.get("id") or ""),
            raw_metadata=safe_metadata(item),
        )

    def discover_chapters(self, request: AcquisitionRequest, cancel: Any | None = None) -> list["NormalizedChapter"]:
        page = self.fetch_page(request, cancel)
        links = normalize_links(page.raw_metadata.get("links", []) or page.discovered_links, request.source_url)
        return dedupe_chapters([
            NormalizedChapter.from_page(AcquiredPage(request.source_url, link, self.name, title="", text=""), chapter_hint=chapter_hint(link))
            for link in filter_scoped_links(links, request)
            if chapter_hint(link)
        ])[: request.max_pages]


class DirectHttpProvider:
    name = "direct_http"
    display_name = "Direct HTTP"
    uses_cloud = False
    capabilities = ProviderCapabilities(
        supports_single_page=True,
        supports_discovery=True,
        supports_chapter_discovery=True,
        supports_html=True,
        supports_retry=True,
        supports_domain_scope=True,
        supports_path_scope=True,
    )

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        validate_public_source_url(request.source_url, request.allowed_domains, request.path_prefixes)
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

    def discover_chapters(self, request: AcquisitionRequest, cancel: Any | None = None) -> list["NormalizedChapter"]:
        page = self.fetch_page(request, cancel)
        links = re.findall(r'href=["\']([^"\']+)["\']', page.html or "", flags=re.IGNORECASE)
        urls = normalize_links(links, page.canonical_url)
        return dedupe_chapters([
            NormalizedChapter.from_page(AcquiredPage(request.source_url, link, self.name, title="", text=""), chapter_hint=chapter_hint(link))
            for link in filter_scoped_links(urls, request)
            if chapter_hint(link)
        ])[: request.max_pages]


class BrowserProvider:
    name = "browser"
    display_name = "Browser"
    uses_cloud = False
    capabilities = ProviderCapabilities(
        supports_single_page=True,
        supports_discovery=True,
        supports_chapter_discovery=True,
        supports_js_rendering=True,
        supports_html=True,
        supports_cancel=True,
        supports_retry=True,
        supports_progress=True,
        supports_domain_scope=True,
        supports_path_scope=True,
        requires_local_browser=True,
    )

    def fetch_page(self, request: AcquisitionRequest, cancel: Any | None = None) -> AcquiredPage:
        raise AcquisitionError(
            "unsupported_source",
            "BrowserProvider is exposed through the existing source adapter browser mode, not standalone generic scraping.",
            provider=self.name,
            retryable=False,
            suggested_action="Use Auto or a source-specific adapter with browser mode enabled.",
        )

    def discover_chapters(self, request: AcquisitionRequest, cancel: Any | None = None) -> list["NormalizedChapter"]:
        raise AcquisitionError(
            "unsupported_source",
            "BrowserProvider chapter discovery is exposed through the existing source adapter browser mode.",
            provider=self.name,
            retryable=False,
            suggested_action="Use Auto or a source-specific adapter with browser mode enabled.",
        )


PROVIDERS: dict[str, type[AcquisitionProvider]] = {
    "direct_http": DirectHttpProvider,
    "browser": BrowserProvider,
    "firecrawl": FirecrawlProvider,
    "apify": ApifyProvider,
}


@dataclass(frozen=True)
class ProviderDecision:
    provider: str
    reason: str
    cloud_allowed: bool


@dataclass(frozen=True)
class NormalizedChapter:
    source_url: str
    canonical_url: str
    chapter_url: str
    chapter_number: float | None
    chapter_title: str
    chapter_body: str
    provider: str
    content_hash: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_page(cls, page: AcquiredPage, chapter_hint: float | None = None) -> "NormalizedChapter":
        body = page.content.strip()
        title = page.title.strip() or inferred_title(page.canonical_url)
        number = chapter_hint if chapter_hint is not None else chapter_hint_from_text(title, page.canonical_url, body)
        return cls(
            source_url=page.source_url,
            canonical_url=page.canonical_url,
            chapter_url=page.canonical_url or page.source_url,
            chapter_number=number,
            chapter_title=title,
            chapter_body=body,
            provider=page.provider,
            content_hash=sha256(body.encode("utf-8")).hexdigest() if body else "",
            warnings=page.warnings,
        )


def choose_provider(
    source_adapter: str,
    requested_provider: str = "auto",
    *,
    browser_mode: bool = True,
    policy: ProviderPolicy | None = None,
    profile: SourceAcquisitionProfile | None = None,
) -> ProviderDecision:
    policy = policy or ProviderPolicy()
    requested_provider = (requested_provider or "auto").lower()
    if requested_provider != "auto":
        return ProviderDecision(requested_provider, "explicit provider requested", requested_provider not in {"firecrawl", "apify"} or policy.allow_cloud_providers)
    if profile and profile.preferred_provider:
        preferred = profile.preferred_provider
        cloud_auto_allowed = (
            preferred == "firecrawl" and policy.allow_cloud_providers and policy.allow_firecrawl_auto
        ) or (
            preferred == "apify" and policy.allow_cloud_providers and policy.allow_apify_auto
        )
        if preferred not in {"firecrawl", "apify"} or cloud_auto_allowed:
            return ProviderDecision(preferred, "source profile preferred provider", preferred not in {"firecrawl", "apify"})
    if source_adapter in {"firecrawl", "apify"}:
        return ProviderDecision(source_adapter, "source adapter is provider-backed", source_adapter not in {"firecrawl", "apify"} or policy.allow_cloud_providers)
    if profile and profile.requires_js and browser_mode:
        return ProviderDecision("browser", "source profile requires JavaScript", True)
    if source_adapter == "novelfire":
        return ProviderDecision("browser" if browser_mode else "direct_http", "source-specific adapter owns acquisition", True)
    if profile and profile.supports_direct is False and browser_mode:
        return ProviderDecision("browser", "direct known unsuitable", True)
    return ProviderDecision("direct_http", "prefer free local provider", True)


def is_allowed_apify_actor(actor_id: str) -> bool:
    allowed = {item.strip() for item in os.getenv("APIFY_ALLOWED_ACTORS", "").split(",") if item.strip()}
    return bool(actor_id and actor_id in allowed)


def http_failure_category(status: int) -> str:
    if status == 401:
        return "authentication_failed"
    if status == 403:
        return "blocked_or_restricted"
    if status == 402:
        return "quota_exhausted"
    if status == 408:
        return "timeout"
    if status == 429:
        return "rate_limited"
    if 500 <= status:
        return "provider_internal"
    return "unsupported_source"


def validate_public_source_url(url: str, allowed_domains: list[str] | None = None, path_prefixes: list[str] | None = None) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AcquisitionError("unsupported_source", "Source URL must be http or https", retryable=False)
    host = parsed.hostname.lower()
    blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "169.254.169.254"}
    if (
        host in blocked_hosts
        or host.startswith("127.")
        or host.startswith("10.")
        or host.startswith("192.168.")
        or re.match(r"^172\.(1[6-9]|2\d|3[0-1])\.", host)
    ):
        raise AcquisitionError("blocked_or_restricted", "Internal network sources are not allowed for cloud acquisition", retryable=False)
    allowed = [item.lower().lstrip(".") for item in (allowed_domains or []) if item]
    if allowed and not any(host == item or host.endswith(f".{item}") for item in allowed):
        raise AcquisitionError("blocked_or_restricted", "Source URL is outside allowed domain scope", retryable=False)
    prefixes = [item for item in (path_prefixes or []) if item]
    if prefixes and not any(parsed.path.startswith(item) for item in prefixes):
        raise AcquisitionError("blocked_or_restricted", "Source URL is outside allowed path scope", retryable=False)


def normalize_links(values: Any, base_url: str) -> list[str]:
    links: list[str] = []
    for item in values if isinstance(values, list) else []:
        raw = item.get("url") if isinstance(item, dict) else item
        if isinstance(raw, str) and raw.strip():
            links.append(urljoin(base_url, raw.strip()))
    return links


def filter_scoped_links(links: list[str], request: AcquisitionRequest) -> list[str]:
    scoped: list[str] = []
    for link in links:
        try:
            validate_public_source_url(link, request.allowed_domains, request.path_prefixes)
            scoped.append(link)
        except AcquisitionError:
            continue
    return scoped


def chapter_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "novel_title": {"type": "string"},
            "chapter_title": {"type": "string"},
            "chapter_number": {"type": ["number", "string", "null"]},
            "chapter_body": {"type": "string"},
            "next_chapter_url": {"type": ["string", "null"]},
            "previous_chapter_url": {"type": ["string", "null"]},
        },
    }


def safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"authorization", "cookie", "set-cookie", "api_key", "token", "password", "secret"}
    return {str(k): v for k, v in metadata.items() if str(k).lower() not in blocked}


def chapter_hint(value: str) -> float | None:
    return chapter_hint_from_text(value, value, "")


def chapter_hint_from_text(*values: str) -> float | None:
    joined = " ".join(values)
    match = re.search(r"(?:chapter|ch\.?)\s*(\d+(?:\.\d+)?)", joined, re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"(?:^|/)(\d{1,5})(?:[./_-]|$)", joined)
    return float(match.group(1)) if match else None


def inferred_title(url: str) -> str:
    part = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return part.replace("-", " ").replace("_", " ").strip().title() or "Untitled Chapter"


def dedupe_chapters(chapters: list[NormalizedChapter]) -> list[NormalizedChapter]:
    seen: set[tuple[str, str, float | None]] = set()
    result: list[NormalizedChapter] = []
    for chapter in chapters:
        key = (chapter.canonical_url.lower(), chapter.chapter_title.lower(), chapter.chapter_number)
        if key in seen:
            continue
        seen.add(key)
        result.append(chapter)
    return result


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
