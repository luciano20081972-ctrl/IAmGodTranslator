"""English Wikisource works with numbered Chapter_N subpages."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from ..acquisition import AcquisitionError, http_failure_category, retry_after_seconds
from ..storage import write_json
from .cloud import CloudChapterAdapter, retry_delay_seconds

HOST = "en.wikisource.org"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TIMEOUT = 15
CHAPTER_LIMIT = 1000
METADATA = "metadata.json"
USER_AGENT = "IAmGodTranslator-Desktop/1.0 (+https://github.com/luciano20081972-ctrl/IAmGodTranslator)"


@dataclass(frozen=True)
class Work:
    url: str
    title: str
    author: str
    chapters: dict[int, str]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def work_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = unquote(parsed.path)
    if (parsed.scheme != "https" or parsed.netloc.lower() != HOST or parsed.query or parsed.fragment
            or not re.fullmatch(r"/wiki/[^/:?#\\]+", path) or "%" in path
            or any(ord(c) < 32 for c in path)):
        raise ValueError("Enter an English Wikisource work URL, such as https://en.wikisource.org/wiki/The_Wonderful_Wizard_of_Oz.")
    return f"https://{HOST}{quote(path, safe='/_(),-')}"


def open_page(request):
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=TIMEOUT)


def fetch_html(url: str, stop_event) -> BeautifulSoup:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != HOST or not parsed.path.startswith("/wiki/") or parsed.query or parsed.fragment:
        raise AcquisitionError("unsupported_source", "URL is outside the Wikisource scope", retryable=False)
    if stop_event.is_set():
        raise AcquisitionError("canceled", "Download interrupted", retryable=False)
    try:
        addresses = socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise AcquisitionError("blocked_or_restricted", "Wikisource resolved to a non-public address", retryable=False)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        deadline = time.monotonic() + TIMEOUT
        with open_page(request) as response:
            if response.url != url or response.headers.get_content_type() != "text/html":
                raise AcquisitionError("invalid_response", "Expected an HTML page at the selected Wikisource URL", retryable=False)
            size = response.headers.get("Content-Length", "")
            if size.isdigit() and int(size) > MAX_RESPONSE_BYTES:
                raise AcquisitionError("response_too_large", "Wikisource page exceeds the 2 MiB limit", retryable=False)
            body = bytearray()
            while len(body) <= MAX_RESPONSE_BYTES:
                if stop_event.is_set():
                    raise AcquisitionError("canceled", "Download interrupted", retryable=False)
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = response.read1(min(64 * 1024, MAX_RESPONSE_BYTES + 1 - len(body)))
                if not chunk:
                    break
                body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise AcquisitionError("response_too_large", "Wikisource page exceeds the 2 MiB limit", retryable=False)
    except urllib.error.HTTPError as exc:
        status = exc.code
        category = http_failure_category(status)
        wait = retry_after_seconds(exc)
        exc.close()
        raise AcquisitionError(category, f"Wikisource returned HTTP {status}", status_code=status,
                               retry_after_seconds=wait, retryable=status == 429 or 500 <= status < 600) from None
    except (TimeoutError, OSError) as exc:
        timeout = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
        raise AcquisitionError("timeout" if timeout else "network",
                               "Wikisource request timed out" if timeout else "Wikisource network request failed") from None
    return BeautifulSoup(body.decode("utf-8", errors="strict"), "html.parser")


def get_text(soup, selector: str) -> str:
    node = soup.select_one(selector)
    return node.get_text(" ", strip=True) if node else ""


def retry_fetch(url, stop_event, retries, delay, on_retry):
    for attempt in range(retries + 1):
        try:
            return fetch_html(url, stop_event)
        except AcquisitionError as error:
            if stop_event.is_set() or not error.retryable or attempt >= retries:
                raise
            wait = max(1.0, retry_delay_seconds(error, attempt, max(1.0, delay)))
            on_retry(error, wait)
            if stop_event.wait(wait):
                raise AcquisitionError("canceled", "Download interrupted", retryable=False) from None


def discover(url, stop_event, retries=1, delay=1.0, on_retry=lambda error, wait: None) -> Work:
    url = work_url(url)
    soup = retry_fetch(url, stop_event, retries, delay, on_retry)
    title = get_text(soup, "#ws-title") or get_text(soup, "h1")
    links = {}
    prefix = unquote(urlsplit(url).path)
    for anchor in soup.select(".mw-parser-output a[href]"):
        target = urlsplit(urljoin(url, anchor["href"]))
        match = re.fullmatch(re.escape(prefix) + r"/Chapter_([1-9][0-9]{0,5})", unquote(target.path))
        if target.scheme == "https" and target.netloc == HOST and not target.query and match:
            number = int(match[1])
            links[number] = f"{url}/Chapter_{number}"
            if len(links) > CHAPTER_LIMIT:
                raise ValueError(f"This work exceeds the {CHAPTER_LIMIT}-chapter discovery limit.")
    if not title or not links:
        raise ValueError("No numbered chapter subpages were found for this Wikisource work.")
    return Work(url, title, get_text(soup, "#ws-author"), dict(sorted(links.items())))


def extract(soup: BeautifulSoup, number: int) -> tuple[str, bytes]:
    title = get_text(soup, "#ws-title")
    if not title or not re.search(rf"\bChapter\s+{number}(?![\d.])\b", title, flags=re.IGNORECASE):
        raise ValueError(f"Chapter {number} is missing its matching Wikisource title.")
    container = soup.select_one(".prp-pages-output")
    paragraphs = [node.get_text(" ", strip=True) for node in container.select("p")] if container else []
    body = "\n\n".join(text for text in paragraphs if text)
    if len(body) < 100:
        raise ValueError(f"Chapter {number} has no usable transcribed chapter body.")
    return title, (body + "\n").encode("utf-8")


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def load_metadata(folder: Path, url: str) -> dict:
    path = folder / METADATA
    if path.exists():
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if metadata.get("source_url") != url or not isinstance(metadata.get("chapters"), dict):
            raise ValueError("This output folder belongs to a different download. Choose a separate folder.")
        return metadata
    if any(folder.glob("*.txt")):
        raise ValueError("This folder contains unverified chapter files. Choose a separate folder to preserve them.")
    return {"source_url": url, "chapters": {}}


def write_chapter(path: Path, data: bytes) -> None:
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(data)
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class WikisourceAdapter(CloudChapterAdapter):
    name = "wikisource"
    display_name = "English Wikisource"
    supports_http = True

    def download(self, options, stop_event, log, progress):
        folder = Path(options["output_dir"])
        url = work_url(str(options["novel_url"]))
        metadata = load_metadata(folder, url)
        rows = metadata["chapters"]
        delay = max(1.0, float(options["delay"]))
        retries = min(3, max(0, int(options["retry_count"])))
        work = discover(url, stop_event, retries, delay,
                        lambda error, wait: log(f"Retry discovery: {error} after {wait:.2f}s"))
        metadata.update(novel_title=work.title, author=work.author)
        success = failed = skipped = 0
        selection = options["chapters"]
        for index, number in enumerate(selection, 1):
            if stop_event.is_set():
                break
            chapter_url = work.chapters.get(number)
            path = folder / f"{number:04d}.txt"
            old = rows.get(str(number), {})
            try:
                if not chapter_url:
                    raise ValueError("Chapter is absent from the source index.")
                if path.exists() and old.get("source_url") == chapter_url and file_digest(path) == old.get("sha256"):
                    skipped += 1
                    log(f"Skipped existing Chapter {number}: verified SHA-256")
                else:
                    if path.exists():
                        raise ValueError("Existing chapter failed verification. Move it aside to preserve it before retrying.")
                    if stop_event.wait(delay):
                        break
                    log(f"Downloading Chapter {number}: {chapter_url}")
                    page = retry_fetch(chapter_url, stop_event, retries, delay,
                                       lambda error, wait: log(f"Retry Chapter {number}: {error} after {wait:.2f}s"))
                    title, data = extract(page, number)
                    if stop_event.is_set():
                        break
                    digest = hashlib.sha256(data).hexdigest()
                    if any(row.get("sha256") == digest for key, row in rows.items() if key != str(number)):
                        raise ValueError("Chapter body duplicates a different downloaded chapter.")
                    rows[str(number)] = {"file": path.name, "title": title, "source_url": chapter_url, "sha256": digest}
                    # Commit the expected hash first. An interruption before the
                    # file rename leaves a missing file that can safely be fetched again.
                    write_json(folder / METADATA, metadata)
                    write_chapter(path, data)
                    if file_digest(path) != digest:
                        raise ValueError("Written chapter failed its checksum.")
                    success += 1
                    log(f"Saved Chapter {number}: {path.name} ({len(data)} bytes)")
            except (AcquisitionError, ValueError, OSError) as error:
                if stop_event.is_set():
                    break
                failed += 1
                log(f"Failed Chapter {number}: {error}")
            progress(index, len(selection), success, failed, skipped, f"Chapter {number}")
        return {"success": success, "failed": failed, "skipped": skipped}
