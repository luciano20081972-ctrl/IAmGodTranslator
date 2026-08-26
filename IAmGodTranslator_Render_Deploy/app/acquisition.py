from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable, Protocol


class AcquisitionStatus(StrEnum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    DISCOVERING = "DISCOVERING"
    DOWNLOADING = "DOWNLOADING"
    NORMALIZING = "NORMALIZING"
    READY_FOR_IMPORT = "READY_FOR_IMPORT"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DESKTOP_REQUIRED = "DESKTOP_REQUIRED"


class ChapterRequestMode(StrEnum):
    ALL = "all"
    MISSING = "missing"
    RANGE = "range"
    EXPLICIT = "explicit"
    RECOVERY_REQUEST = "recovery_request"


class ExecutionStrategy(StrEnum):
    HTTP = "HTTP"
    PLAYWRIGHT = "PLAYWRIGHT"
    DESKTOP_ONLY = "DESKTOP_ONLY"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RateLimitPolicy:
    min_interval_seconds: float = 2.0
    max_concurrency: int = 1
    retryable_statuses: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)
    max_retries: int = 2
    backoff_seconds: float = 1.5


@dataclass(frozen=True)
class HostPolicy:
    source: str
    allowed_hosts: tuple[str, ...]
    allow_http: bool = False
    allow_subdomains: bool = False


@dataclass
class AcquisitionJob:
    id: str
    source: str
    input_url: str
    canonical_url: str = ""
    source_novel_id: str = ""
    requested_mode: ChapterRequestMode = ChapterRequestMode.EXPLICIT
    requested_chapters: list[int] = field(default_factory=list)
    requested_range: tuple[int, int] | None = None
    status: AcquisitionStatus = AcquisitionStatus.PENDING
    execution_strategy: ExecutionStrategy = ExecutionStrategy.HTTP
    retry_count: int = 0
    progress_percent: float = 0.0
    current_chapter: int | None = None
    discovered_chapter_count: int = 0
    completed_chapter_count: int = 0
    failed_chapter_count: int = 0
    cancellation_requested: bool = False
    error_classification: str = ""
    diagnostic_message: str = ""
    resumability: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_mode"] = self.requested_mode.value
        payload["status"] = self.status.value
        payload["execution_strategy"] = self.execution_strategy.value
        return payload


@dataclass(frozen=True)
class SourceNovel:
    source: str
    source_novel_id: str
    canonical_url: str
    title: str
    author: str = ""
    description: str = ""
    language: str = "unknown"


@dataclass(frozen=True)
class SourceChapterRef:
    source_chapter_id: str
    chapter_number: int
    title: str
    url: str


@dataclass(frozen=True)
class AcquiredChapter:
    source: str
    source_novel_id: str
    source_chapter_id: str
    source_url: str
    chapter_number: int
    title: str
    raw_content: str
    normalized_content: str
    language: str
    content_sha256: str
    acquired_at: str
    validation_status: str = "valid"


class SourceAdapter(Protocol):
    name: str
    display_name: str
    allowed_hosts: tuple[str, ...]
    execution_strategy: ExecutionStrategy
    rate_limit_policy: RateLimitPolicy

    def can_handle(self, url: str) -> bool: ...
    def normalize_url(self, url: str) -> str: ...
    def identify_novel(self, url: str) -> str: ...
    def fetch_metadata(self, url: str, client: "AcquisitionHttpClient") -> SourceNovel: ...
    def list_chapters(self, url: str, client: "AcquisitionHttpClient") -> list[SourceChapterRef]: ...
    def fetch_chapter(self, chapter: SourceChapterRef, client: "AcquisitionHttpClient") -> AcquiredChapter: ...
    def normalize_chapter(self, raw_content: str) -> str: ...
    def validate_chapter(self, chapter: AcquiredChapter) -> None: ...
    def health_check(self, client: "AcquisitionHttpClient") -> dict[str, Any]: ...


@dataclass(frozen=True)
class SafeUrl:
    original: str
    normalized: str
    scheme: str
    hostname: str
    port: int | None


class UrlSafetyError(ValueError):
    pass


def normalize_hostname(hostname: str | None) -> str:
    if not hostname:
        raise UrlSafetyError("missing_hostname")
    host = hostname.strip().rstrip(".").lower()
    if not host:
        raise UrlSafetyError("missing_hostname")
    if any(token in host for token in ("%", "/", "\\")):
        raise UrlSafetyError("invalid_hostname")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise UrlSafetyError("invalid_hostname") from exc


def host_allowed(hostname: str, policy: HostPolicy) -> bool:
    allowed = tuple(normalize_hostname(host) for host in policy.allowed_hosts)
    if hostname in allowed:
        return True
    return bool(policy.allow_subdomains and any(hostname.endswith(f".{host}") for host in allowed))


def forbidden_ip(ip: str) -> bool:
    address = ipaddress.ip_address(ip)
    metadata = ipaddress.ip_address("169.254.169.254")
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        or address == metadata
    )


def default_resolver(hostname: str) -> list[str]:
    results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in results})


def validate_url(
    url: str,
    policy: HostPolicy,
    resolver: Callable[[str], list[str]] = default_resolver,
) -> SafeUrl:
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UrlSafetyError("unsupported_scheme")
    if parsed.scheme.lower() == "http" and not policy.allow_http:
        raise UrlSafetyError("http_not_allowed")
    if parsed.username or parsed.password:
        raise UrlSafetyError("userinfo_not_allowed")
    hostname = normalize_hostname(parsed.hostname)
    if not host_allowed(hostname, policy):
        raise UrlSafetyError("host_not_allowed")
    ips = resolver(hostname)
    if not ips:
        raise UrlSafetyError("dns_resolution_empty")
    forbidden = [ip for ip in ips if forbidden_ip(ip)]
    if forbidden:
        raise UrlSafetyError(f"forbidden_ip:{','.join(forbidden)}")
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    normalized = urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    return SafeUrl(original=url, normalized=normalized, scheme=parsed.scheme.lower(), hostname=hostname, port=parsed.port)


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        charset = "utf-8"
        content_type = self.headers.get("content-type") or self.headers.get("Content-Type") or ""
        match = re.search(r"charset=([^;\s]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1)
        return self.body.decode(charset, errors="replace").replace("\r\n", "\n").replace("\r", "\n")


Transport = Callable[[str, dict[str, str], float], FetchResponse]


class AcquisitionHttpClient:
    def __init__(
        self,
        policy: HostPolicy,
        resolver: Callable[[str], list[str]] = default_resolver,
        transport: Transport | None = None,
        timeout_seconds: float = 10,
        max_redirects: int = 4,
        max_response_bytes: int = 2_000_000,
        user_agent: str = "IAmGodTranslator acquisition fixture-client/11.6",
        allowed_content_types: tuple[str, ...] = ("text/html", "text/plain", "application/xhtml+xml"),
    ) -> None:
        self.policy = policy
        self.resolver = resolver
        self.transport = transport or self._urllib_transport
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent
        self.allowed_content_types = allowed_content_types

    def get(self, url: str) -> FetchResponse:
        current = validate_url(url, self.policy, self.resolver).normalized
        for _ in range(self.max_redirects + 1):
            response = self.transport(current, {"User-Agent": self.user_agent, "Accept": "text/html,text/plain"}, self.timeout_seconds)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    raise ValueError("redirect_without_location")
                current = validate_url(urllib.parse.urljoin(current, location), self.policy, self.resolver).normalized
                continue
            self._validate_response(response)
            return response
        raise ValueError("redirect_limit_exceeded")

    def _validate_response(self, response: FetchResponse) -> None:
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(f"http_status:{response.status_code}")
        if len(response.body) > self.max_response_bytes:
            raise ValueError("response_too_large")
        content_type = (response.headers.get("content-type") or response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        if content_type and content_type not in self.allowed_content_types:
            raise ValueError(f"unsupported_content_type:{content_type}")
        sample = response.text[:50000].lower()
        for marker in ("cloudflare", "checking your browser", "captcha", "login to continue", "access denied", "page not found"):
            if marker in sample:
                raise ValueError(f"blocked_or_error_page:{marker}")

    def _urllib_transport(self, url: str, headers: dict[str, str], timeout: float) -> FetchResponse:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(self.max_response_bytes + 1)
                return FetchResponse(url=response.geturl(), status_code=response.status, headers=dict(response.headers.items()), body=body)
        except urllib.error.HTTPError as exc:
            return FetchResponse(url=url, status_code=exc.code, headers=dict(exc.headers.items()), body=exc.read(self.max_response_bytes + 1))


class FixtureNovelAdapter:
    name = "fixture_novel"
    display_name = "Fixture Novel"
    allowed_hosts = ("fixture.local",)
    execution_strategy = ExecutionStrategy.HTTP
    rate_limit_policy = RateLimitPolicy(min_interval_seconds=0.1, max_concurrency=1)

    @property
    def policy(self) -> HostPolicy:
        return HostPolicy(source=self.name, allowed_hosts=self.allowed_hosts, allow_http=True)

    def can_handle(self, url: str) -> bool:
        try:
            validate_url(url, self.policy, resolver=lambda _host: ["93.184.216.34"])
            return True
        except Exception:
            return False

    def normalize_url(self, url: str) -> str:
        return validate_url(url, self.policy, resolver=lambda _host: ["93.184.216.34"]).normalized

    def identify_novel(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(self.normalize_url(url))
        slug = parsed.path.strip("/").split("/")[-1] or "fixture"
        return re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-") or "fixture"

    def fetch_metadata(self, url: str, client: AcquisitionHttpClient) -> SourceNovel:
        response = client.get(url)
        title = extract_between(response.text, "<h1", "</h1>") or "Fixture Novel"
        title = strip_tags(title)
        author = strip_tags(extract_between(response.text, 'data-author="', '"') or "")
        return SourceNovel(
            source=self.name,
            source_novel_id=self.identify_novel(url),
            canonical_url=self.normalize_url(url),
            title=title,
            author=author,
            language="en",
        )

    def list_chapters(self, url: str, client: AcquisitionHttpClient) -> list[SourceChapterRef]:
        response = client.get(url.rstrip("/") + "/chapters")
        chapters: list[SourceChapterRef] = []
        for match in re.finditer(r'<a[^>]+data-chapter="(\d+)"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', response.text, re.IGNORECASE | re.DOTALL):
            number = int(match.group(1))
            chapter_url = urllib.parse.urljoin(url, html.unescape(match.group(2)))
            chapters.append(SourceChapterRef(str(number), number, strip_tags(match.group(3)), chapter_url))
        return chapters

    def fetch_chapter(self, chapter: SourceChapterRef, client: AcquisitionHttpClient) -> AcquiredChapter:
        response = client.get(chapter.url)
        title = strip_tags(extract_between(response.text, "<h1", "</h1>") or chapter.title)
        normalized = self.normalize_chapter(extract_between(response.text, "<article", "</article>") or response.text)
        if len(normalized) < 80:
            raise ValueError("chapter_too_short")
        checksum = content_sha256(normalized)
        acquired = AcquiredChapter(
            source=self.name,
            source_novel_id=self.identify_novel(chapter.url),
            source_chapter_id=chapter.source_chapter_id,
            source_url=chapter.url,
            chapter_number=chapter.chapter_number,
            title=title,
            raw_content=response.text,
            normalized_content=normalized,
            language="en",
            content_sha256=checksum,
            acquired_at=utc_now(),
        )
        self.validate_chapter(acquired)
        return acquired

    def normalize_chapter(self, raw_content: str) -> str:
        return normalize_chapter_text(strip_tags(raw_content))

    def validate_chapter(self, chapter: AcquiredChapter) -> None:
        if chapter.validation_status != "valid":
            raise ValueError(f"chapter_invalid:{chapter.validation_status}")
        if len(chapter.normalized_content) < 80:
            raise ValueError("chapter_too_short")
        if chapter.content_sha256 != content_sha256(chapter.normalized_content):
            raise ValueError("chapter_hash_mismatch")

    def health_check(self, client: AcquisitionHttpClient) -> dict[str, Any]:
        return {"ok": True, "source": self.name, "strategy": self.execution_strategy.value}


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_chapter_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in html.unescape(text).splitlines()]
    return "\n\n".join(line for line in lines if line)


def strip_tags(value: str) -> str:
    return normalize_chapter_text(re.sub(r"<[^>]+>", "\n", value or ""))


def extract_between(value: str, start: str, end: str) -> str:
    lower = value.lower()
    start_index = lower.find(start.lower())
    if start_index < 0:
        return ""
    start_close = value.find(">", start_index)
    content_start = start_close + 1 if start_close >= 0 and start.startswith("<") else start_index + len(start)
    end_index = lower.find(end.lower(), content_start)
    if end_index < 0:
        return ""
    return value[content_start:end_index]


def run_fixture_acquisition(url: str, pages: dict[str, FetchResponse]) -> list[AcquiredChapter]:
    adapter = FixtureNovelAdapter()

    def resolver(host: str) -> list[str]:
        return ["93.184.216.34"] if host == "fixture.local" else ["127.0.0.1"]

    def transport(target: str, _headers: dict[str, str], _timeout: float) -> FetchResponse:
        if target not in pages:
            return FetchResponse(target, 404, {"content-type": "text/html"}, b"page not found")
        response = pages[target]
        time.sleep(0)
        return response

    client = AcquisitionHttpClient(adapter.policy, resolver=resolver, transport=transport)
    chapters = adapter.list_chapters(url, client)
    seen_hashes: set[str] = set()
    acquired: list[AcquiredChapter] = []
    for chapter in chapters:
        item = adapter.fetch_chapter(chapter, client)
        if item.content_sha256 in seen_hashes:
            raise ValueError(f"duplicate_content:{chapter.chapter_number}")
        seen_hashes.add(item.content_sha256)
        acquired.append(item)
    return acquired
