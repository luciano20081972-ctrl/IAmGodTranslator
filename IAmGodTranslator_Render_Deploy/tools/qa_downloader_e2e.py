"""Exercise real HTTP, worker persistence, checked pack import, and the browser Reader."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch
from urllib.parse import urlsplit

import requests
import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / "GodTranslator_Desktop_Companion")]
from desktop_companion.adapters import wikisource as source
from desktop_companion.jobs import JobManager
from desktop_companion.packs import build_pack, validate_pack
from desktop_companion.paths import app_paths
from desktop_companion.storage import CompanionStore
from desktop_companion.sync import SyncManager
from qa_v11_rc2_postgres_auth import TEST_AUTH_SECRET, TEST_USERS, test_token

WORK = "https://en.wikisource.org/wiki/Synthetic_Work"
TITLE = "Synthèse — 洪水"
CHAPTERS = [1, 2, 3]
BODY = {i: f"Chapter {i} synthetic DL-R1 text. " + f"The fixture lantern number {i} stays bright. " * 8 for i in CHAPTERS}


def expect_failure(fn, needle):
    try:
        fn()
    except Exception as error:
        assert needle.lower() in str(error).lower(), str(error)
    else:
        raise AssertionError(f"Expected rejection containing {needle}")


@contextmanager
def source_server():
    requests_seen = []
    failures = {}
    index = '<div class="mw-parser-output"><h1 id="ws-title">Synthèse — 洪水</h1>'
    index += "".join(f'<a href="/wiki/Synthetic_Work/Chapter_{i}">Part {i}</a>' for i in (3, 1, 1, 2))
    index += '<a href="/wiki/Unrelated/Chapter_7">Other</a><a href="https://example.invalid/wiki/Synthetic_Work/Chapter_8">Other</a></div>'

    class SourceHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests_seen.append(self.path)
            attempt = failures.get(self.path)
            status = attempt.pop(0) if attempt else 200
            body = index
            if self.path.startswith("/wiki/Synthetic_Work/Chapter_"):
                number = int(self.path.rsplit("_", 1)[-1])
                body = f'<header>Navigation only</header><h1 id="ws-title">Chapter {number}: 漢字 Étage</h1>'
                body += f'<div class="prp-pages-output"><p>{BODY[number]}</p></div>'
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if status == 429:
                self.send_header("Retry-After", "0")
            if status == 302:
                self.send_header("Location", "http://127.0.0.1:1/private")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), SourceHandler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        resolver = socket.getaddrinfo

        def fixture_open(request):
            # Only the fixture changes transport routing. Validation, parsing,
            # worker, retries, files and checkpoints all use production code.
            actual = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{urlsplit(request.full_url).path}")
            opened = urllib.request.build_opener(source.NoRedirect()).open(actual, timeout=2)
            opened.url = request.full_url
            return opened

        def resolve(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 443))] if host == source.HOST else resolver(host, *args, **kwargs)

        try:
            with patch.object(source, "open_page", fixture_open), patch.object(socket, "getaddrinfo", resolve):
                yield requests_seen, failures
        finally:
            server.shutdown()
            worker.join(timeout=5)


@contextmanager
def website(folder):
    if os.environ.get("DATABASE_URL"):
        raise RuntimeError("Downloader qualification requires isolated SQLite.")
    os.environ.update(GT_SQLITE_PATH=str(folder/"website.sqlite"), APP_ENV="ci", AUTH_ENABLED="false",
                      TRANSLATION_AUTOSTART="false", GT_TEST_AUTH_ENABLED="1", GT_TEST_AUTH_SECRET=TEST_AUTH_SECRET)
    from app import main
    main.database.initialize()
    for user, email, role in TEST_USERS.values():
        main.database.ensure_user_profile(user, email, role)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        base = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(main.app, log_level="warning"))
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and worker.is_alive() and time.monotonic() < deadline:
                time.sleep(.05)
            assert server.started
            yield base
        finally:
            server.should_exit = True
            worker.join(timeout=5)


def wait_job(manager, job_id, status):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = manager.require_job(job_id)
        if job.status in status and not manager._thread_alive(job_id):
            return job
        time.sleep(.025)
    raise AssertionError(f"Worker did not settle: {job.status}, {job.live_log[-5:]}")


def acquire(folder, report):
    paths = app_paths(folder/"Desktop")
    store = CompanionStore(paths)
    manager = JobManager(store, paths)
    bad = ("file:///etc/passwd", "http://127.0.0.1/book", "https://example.invalid/wiki/Book",
           "https://en.wikisource.org@localhost/wiki/Book", WORK+"/Chapter_1", WORK+"?action=edit")
    for url in bad:
        expect_failure(lambda: manager.create_job(TITLE, url, [1], source_adapter="wikisource"), "Wikisource work URL")
    with source_server() as (requests_seen, failures):
        work = source.discover(WORK, Event(), 0)
        assert work.title == TITLE and list(work.chapters) == CHAPTERS
        bad_chapter = "/wiki/Synthetic_Work/Chapter_2"
        options = dict(source_adapter="wikisource", target_mode="english", delay_seconds=1, novel_id="dl-r1-fixture")
        job = manager.create_job(TITLE, WORK, CHAPTERS, **options)
        manager.start(job.id)
        path = Path(job.output_dir) / "0001.txt"
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert path.exists()
        manager.pause(job.id)
        paused = wait_job(manager, job.id, {"paused"})
        first_digest = source.file_digest(path)
        assert not (Path(job.output_dir)/"0002.txt").exists()
        # Simulate restart recovery against persisted active job state.
        paused.status = "downloading"
        store.upsert_job(paused)
        manager = JobManager(store, paths)
        assert manager.require_job(job.id).status == "paused"
        failures[bad_chapter] = [429, 503]
        manager.resume(job.id)
        finished = wait_job(manager, job.id, {"completed"})
        assert (finished.completed, finished.skipped, finished.retry_events) == (2, 1, 2)
        files = {}
        for number in CHAPTERS:
            file = Path(finished.output_dir)/f"{number:04d}.txt"
            assert file.read_text(encoding="utf-8").strip() == BODY[number].strip()
            files[file.name] = source.file_digest(file)
        assert files["0001.txt"] == first_digest
        pack = Path(finished.packs_built[-1])
        validation = validate_pack(pack)
        assert validation["chapter_count"] == 3
        assert all("漢字" in row["title"] for row in validation["manifest"]["chapters"].values())

        counts_before = len([path for path in requests_seen if "/Chapter_" in path])
        repeat = manager.create_job(TITLE, WORK, [3, 2, 1, 1], **options)
        manager.start(repeat.id)
        repeated = wait_job(manager, repeat.id, {"completed"})
        assert repeated.skipped == 3 and repeated.completed == 0
        assert len([path for path in requests_seen if "/Chapter_" in path]) == counts_before

        # A rate retry can be cancelled without waiting for its full backoff.
        cancelled = manager.create_job("Interrupted copy", WORK, [1, 2], **options)
        manager.start(cancelled.id)
        manager.cancel_job(cancelled.id)
        halted = wait_job(manager, cancelled.id, {"cancelled"})
        assert not list(Path(halted.output_dir).glob("*.txt"))

        failures[bad_chapter] = [403, 302]
        for message in ("HTTP 403", "HTTP 302"):
            expect_failure(lambda: source.retry_fetch(work.chapters[2], Event(), 2, 1, lambda *args: None), message)
        with patch.object(source, "open_page", side_effect=TimeoutError):
            expect_failure(lambda: source.fetch_html(WORK, Event()), "timed out")
        with patch.object(source, "open_page", side_effect=ConnectionResetError):
            expect_failure(lambda: source.fetch_html(WORK, Event()), "network")
        with patch.object(socket, "getaddrinfo", return_value=[(0,0,0,"",("10.0.0.1",443))]):
            expect_failure(lambda: source.fetch_html(WORK, Event()), "non-public")
        with patch.object(source, "MAX_RESPONSE_BYTES", 40):
            expect_failure(lambda: source.fetch_html(WORK, Event()), "2 MiB")
        for html, message in [
            ('<div class="prp-pages-output"><p>No title</p></div>', "matching"),
            ('<h1 id="ws-title">Chapter 2</h1><div class="prp-pages-output"></div>', "no usable"),
            ('<h1 id="ws-title">Chapter 9</h1>', "matching"),
        ]:
            expect_failure(lambda: source.extract(source.BeautifulSoup(html, "html.parser"), 2), message)
        assert sorted(files) == ["0001.txt", "0002.txt", "0003.txt"]
        report.update(discovery=list(work.chapters), title=work.title, source_requests=requests_seen,
                      file_sha256=files, pack_sha256=source.file_digest(pack), pack_count=3,
                      recovered={"success":finished.completed,"skipped":finished.skipped,"retries":finished.retry_events},
                      repeated_skips=3, cancellation=halted.status, negative_source_checks="PASS")

    empty_folder = folder/"empty"
    empty_folder.mkdir()
    expect_failure(lambda: build_pack(empty_folder, folder/"packs", "empty", "Empty"), "No chapter")
    original_pack = pack.read_bytes()
    duplicate = Path(job.output_dir) / "00001.txt"
    duplicate.write_bytes(path.read_bytes())
    expect_failure(lambda: manager.build_pack_for_job(job.id), "download checkpoint")
    expect_failure(lambda: build_pack(Path(job.output_dir), folder/"packs", "duplicate", "Duplicate"), "Duplicate chapter")
    assert pack.read_bytes() == original_pack
    duplicate.unlink()
    tampered = folder/"wrong.zip"
    with zipfile.ZipFile(pack) as original, zipfile.ZipFile(tampered, "w") as changed:
        for name in original.namelist():
            changed.writestr(name, b"invalid body" if name == "chapters/0001.txt" else original.read(name))
    expect_failure(lambda: validate_pack(tampered), "SHA-256 mismatch")
    report["pack_negative_checks"] = "PASS"
    return store, pack


def import_reader(folder, store, pack, report):
    with website(folder) as base:
        sync = SyncManager(store)
        sync.save_profile(base)
        upload = sync.queue_upload(pack, "dl-r1-fixture", "english")
        expect_failure(lambda: sync.execute_upload(upload.id), "Preview")
        expect_failure(lambda: sync.preview_upload(upload.id), "authorization failed")
        user, email, _ = TEST_USERS["admin"]
        sync.save_profile(base, test_token(user,email))
        assert sync.auth_check()["authenticated"]
        missing = sync.queue_upload(folder/"wrong.zip", "dl-r1-fixture", "english")
        expect_failure(lambda: sync.preview_upload(missing.id), "SHA-256 mismatch")

        preview = sync.preview_upload(upload.id)
        assert preview.preview["chapter_count"] == 3 and preview.preview["can_execute"]
        library = lambda: requests.get(base+"/api/novels", timeout=10).json()["novels"]
        assert not any(novel["id"] == "dl-r1-fixture" for novel in library())
        sync.save_profile(base, test_token(user,email,exp_delta=-60))
        expect_failure(lambda: sync.execute_upload(upload.id), "authorization failed")
        assert not any(novel["id"] == "dl-r1-fixture" for novel in library())
        sync.save_profile(base, test_token(user,email))
        assert sync.retry_upload(upload.id).status == "queued"
        sync.preview_upload(upload.id)
        original = pack.read_bytes()
        pack.write_bytes(original + b"changed")
        expect_failure(lambda: sync.execute_upload(upload.id), "Pack changed")
        assert not any(novel["id"] == "dl-r1-fixture" for novel in library())
        pack.write_bytes(original)
        imported = sync.execute_upload(upload.id)
        assert imported.status == "imported", imported.result
        assert imported.result["summary"]["imported"] == 3
        duplicate = sync.queue_upload(pack, "dl-r1-fixture", "english")
        sync.preview_upload(duplicate.id)
        repeated = sync.execute_upload(duplicate.id)
        assert repeated.result["summary"]["imported"] == 0
        assertions = {}
        for number in CHAPTERS:
            url = f"{base}/api/novels/dl-r1-fixture/chapters/{number}/english"
            chapter = requests.get(url,timeout=8).json()
            assert chapter["ok"] and chapter["text"].strip() == BODY[number].strip()
            assert "漢字" in chapter["title"]
            assertions[number] = hashlib.sha256(chapter["text"].encode()).hexdigest()
        reference = requests.get(f"{base}/api/novels/dl-r1-fixture/chapters/1/reference", timeout=8)
        assert reference.status_code == 401

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.environ["GT_VERIFY_CHROMIUM"], headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for number in CHAPTERS:
                page.goto(f"{base}/#/reader/dl-r1-fixture/{number}/english", wait_until="domcontentloaded")
                page.locator(".reader-text").get_by_text(BODY[number].strip(),exact=True).wait_for()
            assert not errors
            browser.close()
        report.update(preview=preview.preview["estimated_import"], imported=imported.result["summary"],
                      duplicate_import=repeated.result["summary"], reader_chapter_sha256=assertions,
                      reference_guest_http_status=reference.status_code, preview_execute_auth_controls="PASS",
                      reader_page_errors=errors)


def main():
    folder = Path(os.environ["GT_VERIFY_SCREENSHOTS"])
    assert folder.resolve() == Path(os.environ["HOME"]).resolve()
    report = {}
    try:
        store, pack = acquire(folder,report)
        import_reader(folder,store,pack,report)
    finally:
        print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
