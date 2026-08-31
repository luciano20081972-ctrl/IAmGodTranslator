from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

import desktop_companion
from desktop_companion.acquisition import (
    AcquisitionError,
    AcquisitionRequest,
    ApifyProvider,
    BrowserProvider,
    FirecrawlProvider,
    ProviderPolicy,
    SourceAcquisitionProfile,
    choose_provider,
)
from desktop_companion.jobs import JobManager
from desktop_companion.models import WebsiteConnectionProfile
from desktop_companion.models import default_website_url, normalize_website_base_url
from desktop_companion.adapters import adapter_descriptors, adapter_names
from desktop_companion.adapters.cloud import CloudChapterAdapter, retry_delay_seconds
from desktop_companion.packs import build_auto_packs, build_pack, validate_pack
from desktop_companion.packs import chapter_number_from_file
from desktop_companion.paths import app_paths
from desktop_companion.recovery import load_recovery_request
from desktop_companion.storage import CompanionStore, read_json
from desktop_companion.sync import SyncManager
from desktop_companion.ui_app import NAV_ITEMS, provider_value
from desktop_companion.website_api import WebsiteClient


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


class FixtureDownloaderAdapter:
    name = "fixture"
    display_name = "Fixture"
    supports_http = True
    supports_playwright = True

    def build_options(self, **kwargs):
        return kwargs

    def download(self, options, stop_event, log, progress):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        total = len(options["chapters"])
        success = failed = skipped = 0
        log("Browser launched")
        for index, chapter in enumerate(options["chapters"], start=1):
            if stop_event.is_set():
                log("Stopped safely by user.")
                break
            progress(index - 1, total, success, failed, skipped, f"Chapter {chapter}")
            log(f"Downloading Chapter {chapter}: https://example.invalid/chapter-{chapter}")
            body = f"Chapter {chapter}\n\n" + ("fixture text " * 80)
            (output_dir / f"{chapter:04d}.txt").write_text(body, encoding="utf-8")
            log(f"Saved Chapter {chapter}: {chapter:04d}.txt ({len(body)} chars)")
            success += 1
            progress(index, total, success, failed, skipped, f"Chapter {chapter}")
        log("Browser closed")
        return {"success": success, "failed": failed, "skipped": skipped}


class SlowFixtureDownloaderAdapter(FixtureDownloaderAdapter):
    def download(self, options, stop_event, log, progress):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        total = len(options["chapters"])
        success = failed = skipped = 0
        log("Browser launched")
        for index, chapter in enumerate(options["chapters"], start=1):
            if stop_event.is_set():
                log("Stopped safely by user.")
                break
            progress(index - 1, total, success, failed, skipped, f"Chapter {chapter}")
            log(f"Downloading Chapter {chapter}: https://example.invalid/chapter-{chapter}")
            time.sleep(0.25)
            body = f"Chapter {chapter}\n\n" + ("fixture text " * 80)
            (output_dir / f"{chapter:04d}.txt").write_text(body, encoding="utf-8")
            log(f"Saved Chapter {chapter}: {chapter:04d}.txt ({len(body)} chars)")
            success += 1
            progress(index, total, success, failed, skipped, f"Chapter {chapter}")
        log("Browser closed")
        return {"success": success, "failed": failed, "skipped": skipped}


class BrokenSetupAdapter(FixtureDownloaderAdapter):
    def build_options(self, **kwargs):
        raise RuntimeError("adapter setup failed")


class FailOnceDownloaderAdapter(FixtureDownloaderAdapter):
    def download(self, options, stop_event, log, progress):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        marker = output_dir / ".chapter-2-failed-once"
        total = len(options["chapters"])
        success = failed = skipped = 0
        log("Browser launched")
        for index, chapter in enumerate(options["chapters"], start=1):
            if stop_event.is_set():
                log("Stopped safely by user.")
                break
            progress(index - 1, total, success, failed, skipped, f"Chapter {chapter}")
            log(f"Downloading Chapter {chapter}: https://example.invalid/chapter-{chapter}")
            if chapter == 2 and not marker.exists():
                marker.write_text("failed", encoding="utf-8")
                failed += 1
                log("Failed Chapter 2: fixture retry gate")
                progress(index, total, success, failed, skipped, f"Chapter {chapter}")
                continue
            body = f"Chapter {chapter}\n\n" + ("fixture text " * 80)
            (output_dir / f"{chapter:04d}.txt").write_text(body, encoding="utf-8")
            log(f"Saved Chapter {chapter}: {chapter:04d}.txt ({len(body)} chars)")
            success += 1
            progress(index, total, success, failed, skipped, f"Chapter {chapter}")
        log("Browser closed")
        return {"success": success, "failed": failed, "skipped": skipped}


class FakeJsonClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.get_payloads = []
        self.delete_calls = []

    def post_json(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return self.payload

    def get_json(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "method": "GET", "timeout": timeout})
        if self.get_payloads:
            return self.get_payloads.pop(0)
        return {}

    def delete_json(self, url, headers, timeout):
        self.delete_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return {"success": True}


class FakeFirecrawlAdapter(FixtureDownloaderAdapter):
    name = "firecrawl"
    display_name = "Firecrawl"
    supports_http = False
    supports_playwright = False

    def download(self, options, stop_event, log, progress):
        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        success = 0
        log("Provider selected: firecrawl")
        for index, chapter in enumerate(options["chapters"], start=1):
            body = f"Chapter {chapter}\n\nFirecrawl acquired text"
            (output_dir / f"{chapter:04d}.txt").write_text(body, encoding="utf-8")
            success += 1
            log(f"Saved Chapter {chapter}: {chapter:04d}.txt via firecrawl")
            progress(index, len(options["chapters"]), success, 0, 0, f"Chapter {chapter}")
        return {"success": success, "failed": 0, "skipped": 0}


class RetryableThenSuccessProvider:
    name = "firecrawl"

    def __init__(self):
        self.calls = 0

    def fetch_page(self, request, cancel=None):
        self.calls += 1
        if self.calls == 1:
            raise AcquisitionError("timeout", "temporary timeout", provider=self.name)
        return type(
            "Page",
            (),
            {
                "title": "Chapter 1",
                "content": "Recovered provider chapter body with enough words for validation after retry.",
                "provider": self.name,
            },
        )()


class PermanentFailureProvider:
    name = "firecrawl"

    def __init__(self):
        self.calls = 0

    def fetch_page(self, request, cancel=None):
        self.calls += 1
        raise AcquisitionError("authentication_failed", "bad key", provider=self.name, retryable=False)


class RetryableCloudAdapter(CloudChapterAdapter):
    name = "retryable_cloud"
    provider_instance = RetryableThenSuccessProvider()

    def provider(self):
        return self.provider_instance


class PermanentFailureCloudAdapter(CloudChapterAdapter):
    name = "permanent_failure_cloud"
    provider_instance = PermanentFailureProvider()

    def provider(self):
        return self.provider_instance


def wait_for_job(store: CompanionStore, job_id: str, statuses: set[str]) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        job = store.job(job_id)
        if job and job.status in statuses:
            return
        time.sleep(0.05)
    job = store.job(job_id)
    raise AssertionError(f"Job did not reach {statuses}; status={job.status if job else 'missing'}")


class DesktopCompanionFoundationTests(unittest.TestCase):
    def test_application_import(self) -> None:
        self.assertEqual(desktop_companion.APP_NAME, "GodTranslator Desktop Companion")

    def test_direct_http_provider_option_is_real_adapter(self) -> None:
        self.assertIn("direct_http", adapter_names())
        direct = next(item for item in adapter_descriptors() if item.name == "direct_http")
        self.assertEqual(direct.status, "active")
        self.assertEqual(provider_value("Direct"), "direct_http")

    def test_recovery_request_parsing(self) -> None:
        request = load_recovery_request(FIXTURES / "recovery_request.json")
        self.assertEqual(request.novel_id, "fixture-novel")
        self.assertEqual(request.target_mode, "reference")
        self.assertEqual(request.chapters, [1, 2, 4])
        self.assertEqual(request.missing_count, 3)

    def test_job_persistence_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": FixtureDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Fixture Novel", "https://example.invalid/novel", [1, 2, 3], output_dir=paths.downloads_dir / "fixture", source_adapter="fixture")
            self.assertEqual(job.status, "queued")
            manager.pause(job.id)
            self.assertEqual(store.job(job.id).status, "paused")
            manager.resume(job.id)
            wait_for_job(store, job.id, {"completed"})
            self.assertEqual(store.job(job.id).downloaded_chapters, [1, 2, 3])
            payload = read_json(paths.jobs_file, {})
            self.assertEqual(payload["jobs"][0]["id"], job.id)
            self.assertEqual(payload["jobs"][0]["acquisition_provider"], "auto")

    def test_firecrawl_provider_normalizes_scrape_response(self) -> None:
        client = FakeJsonClient({
            "data": {
                "markdown": "# Chapter 7\n\n" + ("Acquired chapter text with enough body for validation. " * 3),
                "metadata": {"title": "Chapter 7", "sourceURL": "https://example.invalid/c7"},
                "links": ["https://example.invalid/c8"],
            }
        })
        page = FirecrawlProvider(api_key="test", client=client).fetch_page(AcquisitionRequest("https://example.invalid/c7", 7))
        self.assertEqual(page.provider, "firecrawl")
        self.assertEqual(page.title, "Chapter 7")
        self.assertIn("Acquired chapter text", page.content)
        self.assertEqual(client.calls[0]["headers"]["Authorization"], "Bearer test")

    def test_firecrawl_requires_server_side_key(self) -> None:
        with self.assertRaises(AcquisitionError) as ctx:
            FirecrawlProvider(api_key="").fetch_page(AcquisitionRequest("https://example.invalid/c1", 1))
        self.assertEqual(ctx.exception.category, "configuration_missing")

    def test_firecrawl_map_discovers_scoped_chapters_without_crawling_whole_domain(self) -> None:
        client = FakeJsonClient({
            "success": True,
            "links": [
                {"url": "https://fiction.example/novel/chapter-1", "title": "Chapter 1"},
                {"url": "https://fiction.example/novel/chapter-2", "title": "Chapter 2"},
                {"url": "https://fiction.example/blog/unrelated", "title": "Blog"},
                {"url": "https://other.example/novel/chapter-3", "title": "Chapter 3"},
            ],
        })
        request = AcquisitionRequest(
            "https://fiction.example/novel/",
            max_pages=10,
            allowed_domains=["fiction.example"],
            path_prefixes=["/novel/"],
        )
        chapters = FirecrawlProvider(api_key="test", client=client).discover_chapters(request)
        self.assertEqual([item.chapter_number for item in chapters], [1.0, 2.0])
        self.assertTrue(client.calls[0]["url"].endswith("/v2/map"))
        self.assertEqual(client.calls[0]["payload"]["limit"], 10)

    def test_firecrawl_bounded_crawl_requires_scope_limits(self) -> None:
        with self.assertRaises(AcquisitionError) as ctx:
            FirecrawlProvider(api_key="test", client=FakeJsonClient({"id": "crawl-1"})).bounded_crawl(
                AcquisitionRequest("https://fiction.example/novel/", max_pages=10)
            )
        self.assertEqual(ctx.exception.category, "blocked_or_restricted")

    def test_firecrawl_bounded_crawl_normalizes_only_scoped_pages(self) -> None:
        client = FakeJsonClient({"id": "crawl-1"})
        client.get_payloads = [{
            "status": "completed",
            "data": [
                {"markdown": "Chapter 1\n\n" + ("First body with enough chapter words for validation. " * 3), "metadata": {"title": "Chapter 1", "sourceURL": "https://fiction.example/novel/chapter-1"}},
                {"markdown": "Chapter 2\n\n" + ("Second body with enough chapter words for validation. " * 3), "metadata": {"title": "Chapter 2", "sourceURL": "https://fiction.example/novel/chapter-2"}},
                {"markdown": "Chapter 3\n\n" + ("Wrong scope with enough chapter words for validation. " * 3), "metadata": {"title": "Chapter 3", "sourceURL": "https://fiction.example/blog/chapter-3"}},
            ],
        }]
        request = AcquisitionRequest(
            "https://fiction.example/novel/",
            max_pages=10,
            allowed_domains=["fiction.example"],
            path_prefixes=["/novel/"],
        )
        chapters = FirecrawlProvider(api_key="test", client=client).bounded_crawl(request, poll_interval=0, max_polls=1)
        self.assertEqual([item.chapter_number for item in chapters], [1.0, 2.0])
        self.assertEqual(chapters[0].provider, "firecrawl")
        self.assertTrue(client.calls[0]["url"].endswith("/v2/crawl"))
        self.assertEqual(client.calls[0]["payload"]["includePaths"], ["/novel/"])
        self.assertFalse(client.calls[0]["payload"]["allowExternalLinks"])
        self.assertTrue(client.calls[1]["url"].endswith("/v2/crawl/crawl-1"))

    def test_firecrawl_bounded_crawl_cancels_remote_job(self) -> None:
        client = FakeJsonClient({"id": "crawl-1"})
        cancel = threading.Event()
        cancel.set()
        request = AcquisitionRequest(
            "https://fiction.example/novel/",
            max_pages=5,
            allowed_domains=["fiction.example"],
            path_prefixes=["/novel/"],
        )
        with self.assertRaises(AcquisitionError) as ctx:
            FirecrawlProvider(api_key="test", client=client).bounded_crawl(request, cancel=cancel, poll_interval=0, max_polls=1)
        self.assertEqual(ctx.exception.category, "canceled")
        self.assertEqual(len(client.delete_calls), 1)
        self.assertTrue(client.delete_calls[0]["url"].endswith("/v2/crawl/crawl-1"))

    def test_provider_scope_blocks_private_network_targets(self) -> None:
        with self.assertRaises(AcquisitionError) as ctx:
            FirecrawlProvider(api_key="test", client=FakeJsonClient({})).fetch_page(AcquisitionRequest("http://127.0.0.1:8000/admin"))
        self.assertEqual(ctx.exception.category, "blocked_or_restricted")

    def test_apify_provider_requires_allowlisted_actor_and_normalizes_dataset(self) -> None:
        client = FakeJsonClient({"data": {"id": "run-1", "defaultDatasetId": "dataset-1"}})
        client.get_payloads = [
            {"data": {"id": "run-1", "status": "SUCCEEDED", "defaultDatasetId": "dataset-1", "usage": {"totalUsd": 0.01}}},
            [{"title": "Chapter 9", "text": "Apify acquired text with enough chapter body for validation.", "url": "https://example.invalid/c9"}],
        ]
        with patch.dict(os.environ, {"APIFY_ALLOWED_ACTORS": "owner/chapter-reader"}):
            page = ApifyProvider(api_token="test", actor_id="owner/chapter-reader", client=client).fetch_page(AcquisitionRequest("https://example.invalid/c9", 9))
        self.assertEqual(page.provider, "apify")
        self.assertEqual(page.title, "Chapter 9")
        self.assertIn("Apify acquired text", page.content)
        self.assertIn("owner~chapter-reader", client.calls[0]["url"])
        self.assertTrue(client.calls[1]["url"].endswith("/actor-runs/run-1"))
        self.assertTrue(client.calls[2]["url"].endswith("/datasets/dataset-1/items?limit=1"))

    def test_apify_provider_aborts_running_actor_on_cancel(self) -> None:
        cancel = threading.Event()

        class CancelAfterStartClient(FakeJsonClient):
            def post_json(self, url, headers, payload, timeout):
                result = super().post_json(url, headers, payload, timeout)
                if url.endswith("/actors/owner~chapter-reader/runs"):
                    cancel.set()
                return result

        client = CancelAfterStartClient({"data": {"id": "run-1", "defaultDatasetId": "dataset-1"}})
        with patch.dict(os.environ, {"APIFY_ALLOWED_ACTORS": "owner/chapter-reader"}):
            with self.assertRaises(AcquisitionError) as ctx:
                ApifyProvider(api_token="test", actor_id="owner/chapter-reader", client=client).fetch_page(AcquisitionRequest("https://example.invalid/c9", 9), cancel=cancel)
        self.assertEqual(ctx.exception.category, "canceled")
        self.assertTrue(client.calls[-1]["url"].endswith("/actor-runs/run-1/abort"))

    def test_apify_rejects_unapproved_actor(self) -> None:
        with patch.dict(os.environ, {"APIFY_ALLOWED_ACTORS": "owner/approved"}):
            with self.assertRaises(AcquisitionError) as ctx:
                ApifyProvider(api_token="test", actor_id="owner/not-approved").fetch_page(AcquisitionRequest("https://example.invalid", 1))
        self.assertEqual(ctx.exception.category, "unsupported_source")

    def test_browser_provider_is_declared_as_real_local_provider(self) -> None:
        provider = BrowserProvider()
        self.assertTrue(provider.capabilities.requires_local_browser)
        self.assertTrue(provider.capabilities.supports_js_rendering)
        with self.assertRaises(AcquisitionError) as ctx:
            provider.fetch_page(AcquisitionRequest("https://example.invalid/chapter-1", 1))
        self.assertEqual(ctx.exception.provider, "browser")
        self.assertIn("source adapter browser mode", str(ctx.exception))
        with self.assertRaises(AcquisitionError) as ctx:
            provider.discover_chapters(AcquisitionRequest("https://example.invalid/chapter-1", 1))
        self.assertEqual(ctx.exception.provider, "browser")

    def test_auto_provider_policy_prefers_free_local_paths(self) -> None:
        policy = ProviderPolicy(allow_cloud_providers=False, prefer_free_local=True)
        decision = choose_provider("novelfire", "auto", browser_mode=True, policy=policy)
        self.assertEqual(decision.provider, "browser")
        self.assertIn("source-specific", decision.reason)
        decision = choose_provider("generic", "auto", browser_mode=False, policy=policy)
        self.assertEqual(decision.provider, "direct_http")

    def test_auto_provider_honors_source_profile_without_spending_cloud_by_default(self) -> None:
        profile = SourceAcquisitionProfile(preferred_provider="firecrawl", requires_js=True)
        blocked = choose_provider("generic", "auto", browser_mode=True, policy=ProviderPolicy(allow_cloud_providers=False), profile=profile)
        self.assertEqual(blocked.provider, "browser")
        allowed = choose_provider("generic", "auto", browser_mode=True, policy=ProviderPolicy(allow_cloud_providers=True, allow_firecrawl_auto=True), profile=profile)
        self.assertEqual(allowed.provider, "firecrawl")

    def test_cloud_provider_metadata_persists_through_job_manager(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"firecrawl": FakeFirecrawlAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Cloud Novel", "https://example.invalid/{chapter}", [1], source_adapter="firecrawl", acquisition_provider="firecrawl")
            manager.start(job.id)
            wait_for_job(store, job.id, {"completed"})
            saved = store.job(job.id)
            self.assertEqual(saved.resolved_provider, "firecrawl")
            self.assertEqual(saved.downloaded_chapters, [1])
            self.assertTrue((Path(saved.output_dir) / "0001.txt").exists())
            self.assertEqual(saved.provider_attempts[0]["status"], "started")
            self.assertTrue(saved.provider_attempts[0]["capabilities"]["requires_external_credit"])
            self.assertEqual(saved.provider_attempts[-1]["status"], "completed")
            self.assertEqual(saved.provider_attempts[-1]["result"]["success"], 1)

    def test_cloud_adapter_retries_retryable_failures_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            RetryableCloudAdapter.provider_instance = RetryableThenSuccessProvider()
            output = Path(temp)
            logs: list[str] = []
            result = RetryableCloudAdapter().download(
                {
                    "novel_url": "https://example.invalid/chapter-{chapter}",
                    "chapter_url_template": "https://example.invalid/chapter-{chapter}",
                    "chapters": [1],
                    "output_dir": output,
                    "delay": 0,
                    "retry_count": 2,
                    "skip_existing": False,
                },
                threading.Event(),
                logs.append,
                lambda *args: None,
            )
            self.assertEqual(result, {"success": 1, "failed": 0, "skipped": 0})
            self.assertIn("Retry Chapter 1: timeout", "\n".join(logs))
            self.assertEqual(RetryableCloudAdapter.provider_instance.calls, 2)

    def test_cloud_adapter_does_not_retry_permanent_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            PermanentFailureCloudAdapter.provider_instance = PermanentFailureProvider()
            logs: list[str] = []
            result = PermanentFailureCloudAdapter().download(
                {
                    "novel_url": "https://example.invalid/chapter-{chapter}",
                    "chapter_url_template": "https://example.invalid/chapter-{chapter}",
                    "chapters": [1],
                    "output_dir": Path(temp),
                    "delay": 0,
                    "retry_count": 2,
                    "skip_existing": False,
                },
                threading.Event(),
                logs.append,
                lambda *args: None,
            )
            self.assertEqual(result, {"success": 0, "failed": 1, "skipped": 0})
            self.assertNotIn("Retry Chapter 1", "\n".join(logs))
            self.assertEqual(PermanentFailureCloudAdapter.provider_instance.calls, 1)

    def test_retry_delay_prefers_retry_after_header(self) -> None:
        exc = AcquisitionError("rate_limited", "rate limited", provider="firecrawl", retry_after_seconds=12)
        self.assertEqual(retry_delay_seconds(exc, attempt=3, base_delay=2), 12)

    def test_resume_retry_restart_dispatch_real_executor_and_remove_keeps_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": SlowFixtureDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Fixture Novel", "https://example.invalid/novel", [1, 2], output_dir=paths.downloads_dir, source_adapter="fixture")
            manager.pause(job.id)
            manager.resume(job.id)
            wait_for_job(store, job.id, {"completed"})
            saved = store.job(job.id)
            self.assertEqual(saved.downloaded_chapters, [1, 2])
            self.assertTrue(Path(saved.output_dir, "0001.txt").exists())
            manager.remove_job(job.id)
            self.assertIsNone(store.job(job.id))
            self.assertTrue(Path(saved.output_dir, "0001.txt").exists())

    def test_adapter_setup_failure_marks_job_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"broken": BrokenSetupAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Broken Novel", "https://example.invalid/novel", [1], source_adapter="broken")
            manager.start(job.id)
            wait_for_job(store, job.id, {"failed"})
            saved = store.job(job.id)
            self.assertEqual(saved.worker_state, "Failed")
            self.assertIn("adapter setup failed", saved.errors["job"])
            self.assertIn("Job failed: adapter setup failed", "\n".join(saved.live_log))
            self.assertEqual(saved.provider_attempts[-1]["status"], "failed")
            self.assertEqual(saved.provider_attempts[-1]["fallback_decision"], "no fallback during adapter setup")

    def test_download_manager_persists_real_adapter_events_and_output_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": FixtureDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job(
                "Fixture Novel",
                "https://example.invalid/novel",
                [1, 2, 3],
                output_dir=paths.downloads_dir,
                source_adapter="fixture",
                target_mode="original",
            )
            self.assertEqual(Path(job.novel_root_dir).name, "Fixture Novel")
            self.assertEqual(Path(job.output_dir).name, "Original")

            manager.start(job.id)
            wait_for_job(store, job.id, {"completed"})
            saved = store.job(job.id)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.downloaded_chapters, [1, 2, 3])
            self.assertEqual(saved.last_downloaded_chapter, 3)
            self.assertEqual(saved.browser_state, "Closed")
            self.assertIn("Downloading Chapter 2", "\n".join(saved.live_log))
            self.assertTrue((Path(saved.novel_root_dir) / "Packs" / "fixture-novel-original-pack.zip").exists())

    def test_download_job_restart_duplicate_and_delete_are_local_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": FixtureDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Fixture Novel", "https://example.invalid/novel", [1], source_adapter="fixture")
            restarted = manager.restart_job(job.id)
            self.assertIn(restarted.status, {"queued", "starting", "downloading"})
            self.assertFalse(restarted.skip_existing)
            wait_for_job(store, job.id, {"completed"})
            duplicate = manager.duplicate_job(job.id)
            self.assertNotEqual(duplicate.id, job.id)
            manager.cancel_job(duplicate.id)
            manager.remove_job(duplicate.id)
            self.assertIsNone(store.job(duplicate.id))

    def test_full_downloader_fixture_update_retry_sync_and_remove(self) -> None:
        imported: dict[tuple[str, str], set[int]] = {}

        class FakeWebsite:
            def _chapters(self, pack_path: Path) -> tuple[dict, list[int]]:
                with zipfile.ZipFile(pack_path) as zf:
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                chapters = manifest.get("chapters") or {}
                numbers = sorted(int(item["chapter_number"]) for item in chapters.values())
                return manifest, numbers

            def preview_content_pack(self, pack_path: Path, novel_id: str = "", content_type: str = "", **kwargs):
                manifest, numbers = self._chapters(pack_path)
                key = (novel_id or manifest["novel_id"], content_type or manifest["content_type"])
                stored = imported.setdefault(key, set())
                duplicates = [chapter for chapter in numbers if chapter in stored]
                new = [chapter for chapter in numbers if chapter not in stored]
                return {"ok": True, "new": len(new), "duplicate": len(duplicates), "invalid": 0, "chapters": numbers}

            def execute_content_pack(self, pack_path: Path, novel_id: str = "", content_type: str = "", **kwargs):
                preview = self.preview_content_pack(pack_path, novel_id, content_type, **kwargs)
                manifest, numbers = self._chapters(pack_path)
                key = (novel_id or manifest["novel_id"], content_type or manifest["content_type"])
                stored = imported.setdefault(key, set())
                before = set(stored)
                stored.update(numbers)
                return {"ok": True, "summary": {"imported": len(stored - before), "duplicates": len(before & set(numbers)), "errors": 0}}

        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": FailOnceDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Fixture Novel", "https://example.invalid/novel", [1, 2, 3], output_dir=paths.downloads_dir, source_adapter="fixture", target_mode="original")
            manager.start(job.id)
            wait_for_job(store, job.id, {"failed"})
            failed = store.job(job.id)
            self.assertEqual(failed.failed_chapters, [2])
            self.assertEqual(failed.downloaded_chapters, [1, 3])

            manager.retry_failed(job.id)
            wait_for_job(store, job.id, {"completed"})
            completed = store.job(job.id)
            self.assertEqual(completed.downloaded_chapters, [1, 2, 3])
            self.assertEqual(sorted(path.name for path in Path(completed.output_dir).glob("*.txt")), ["0001.txt", "0002.txt", "0003.txt"])
            self.assertTrue(completed.packs_built)

            sync = SyncManager(store)
            sync.client = lambda: FakeWebsite()  # type: ignore[method-assign]
            upload = sync.queue_upload(Path(completed.packs_built[-1]), completed.novel_id, "original")
            previewed = sync.preview_upload(upload.id)
            self.assertEqual(previewed.preview["new"], 3)
            imported_once = sync.execute_upload(upload.id)
            self.assertEqual(imported_once.result["summary"], {"imported": 3, "duplicates": 0, "errors": 0})
            second = sync.queue_upload(Path(completed.packs_built[-1]), completed.novel_id, "original")
            second_preview = sync.preview_upload(second.id)
            self.assertEqual(second_preview.preview["duplicate"], 3)
            second_import = sync.execute_upload(second.id)
            self.assertEqual(second_import.result["summary"], {"imported": 0, "duplicates": 3, "errors": 0})

            update = manager.create_update_job(
                "Fixture Novel",
                "https://example.invalid/novel",
                discovered_chapters=[1, 2, 3, 4, 5],
                existing_chapters=sorted(imported[(completed.novel_id, "original")]),
                output_dir=Path(completed.novel_root_dir),
                source_adapter="fixture",
                target_mode="original",
            )
            self.assertEqual(update.chapters, [4, 5])
            manager.start(update.id)
            wait_for_job(store, update.id, {"completed"})
            updated = store.job(update.id)
            self.assertEqual(updated.downloaded_chapters, [4, 5])

            update_upload = sync.queue_upload(Path(updated.packs_built[-1]), updated.novel_id, "original")
            sync.execute_upload(update_upload.id)
            self.assertEqual(sorted(imported[(completed.novel_id, "original")]), [1, 2, 3, 4, 5])

            manager.remove_job(job.id)
            self.assertIsNone(store.job(job.id))
            self.assertEqual(sorted(imported[(completed.novel_id, "original")]), [1, 2, 3, 4, 5])

    def test_browser_jobs_are_bounded_and_queued_jobs_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict("desktop_companion.jobs.ADAPTERS", {"fixture": SlowFixtureDownloaderAdapter}):
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            store.save_settings({"max_active_browser_jobs": 1})
            manager = JobManager(store, paths)
            first = manager.create_job("Fixture One", "https://example.invalid/one", [1], source_adapter="fixture")
            second = manager.create_job("Fixture Two", "https://example.invalid/two", [1], source_adapter="fixture")
            manager.start(first.id)
            time.sleep(0.05)
            queued = manager.start(second.id)
            self.assertEqual(queued.status, "queued")
            self.assertIn("browser slot", queued.worker_state)
            wait_for_job(store, first.id, {"completed"})
            wait_for_job(store, second.id, {"completed"})
            self.assertEqual(store.job(second.id).downloaded_chapters, [1])

    def test_pack_creation_checksum_and_secret_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            result = build_pack(
                source_dir=FIXTURES / "chapters",
                output_dir=out,
                novel_id="fixture-novel",
                novel_title="Fixture Novel",
                target_mode="reference",
                source_url="https://example.invalid/novel/fixture",
            )
            validation = validate_pack(result.path)
            self.assertTrue(validation["ok"])
            self.assertEqual(validation["chapter_count"], 2)
            manifest = validation["manifest"]
            self.assertEqual(manifest["format"], "godtranslator-reference-pack-v1")
            self.assertIn("cookies", manifest["excluded"])
            self.assertIn("api_keys", manifest["excluded"])

    def test_unicode_and_spaced_paths_pack_as_utf8_chapters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="God Translator 空格 ") as temp:
            root = Path(temp) / "Mixed Case Novel" / "Reference"
            root.mkdir(parents=True)
            body = "第58章\n\n" + ("中文段落 with readable fixture text. " * 40)
            chapter_59 = "Chapter 59\n\n" + ("fixture text " * 80)
            (root / "第58章.txt").write_text(body, encoding="utf-8", newline="\n")
            (root / "Chapter 059.txt").write_text(chapter_59, encoding="utf-8", newline="\n")

            self.assertEqual(chapter_number_from_file(root / "Chapter 059.txt"), 59)
            self.assertEqual(chapter_number_from_file(root / "第58章.txt"), 58)

            result = build_pack(
                source_dir=root,
                output_dir=Path(temp) / "Packs With Spaces",
                novel_id="unicode-novel",
                novel_title="Unicode Novel",
                target_mode="reference",
            )
            validation = validate_pack(result.path)
            self.assertTrue(validation["ok"])
            self.assertEqual(validation["chapter_count"], 2)
            self.assertEqual(validation["manifest"]["chapters"]["58"]["character_count"], len(body))
            self.assertEqual(validation["manifest"]["chapters"]["59"]["character_count"], len(chapter_59))

    def test_ui_sections_smoke(self) -> None:
        self.assertEqual(
            NAV_ITEMS,
            [
                "Dashboard",
                "Downloads",
                "Library",
                "New / Update Novel",
                "Recovery",
                "Packs",
                "Sync",
                "Activity",
                "Settings",
                "Advanced Logs",
            ],
        )

    def test_future_source_adapters_are_registered_without_core_rewrite(self) -> None:
        self.assertIn("novelfire", adapter_names())
        self.assertIn("69shuba", adapter_names())
        self.assertIn("qidian", adapter_names())
        self.assertIn("royalroad", adapter_names())
        self.assertIn("scribblehub", adapter_names())
        descriptors = {item.name: item for item in adapter_descriptors()}
        self.assertEqual(descriptors["novelfire"].status, "active")
        self.assertEqual(descriptors["qidian"].status, "planned")

    def test_auto_pack_build_creates_original_reference_english_and_mixed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            results = build_auto_packs(
                source_dir=FIXTURES / "chapters",
                output_dir=out,
                novel_id="fixture-novel",
                novel_title="Fixture Novel",
                source_url="https://example.invalid/novel/fixture",
            )
            formats = {validate_pack(result.path)["manifest"]["format"] for result in results}
            self.assertEqual(
                formats,
                {
                    "godtranslator-original-pack-v1",
                    "godtranslator-reference-pack-v1",
                    "godtranslator-english-pack-v1",
                    "godtranslator-mixed-pack-v1",
                },
            )

    def test_sync_center_queue_preview_execute_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            sync = SyncManager(store)
            pack = build_pack(
                source_dir=FIXTURES / "chapters",
                output_dir=paths.packs_dir,
                novel_id="fixture-novel",
                novel_title="Fixture Novel",
                target_mode="original",
            )
            upload = sync.queue_upload(pack.path, "fixture-novel", "original")
            self.assertEqual(sync.center_snapshot()["queued_uploads"], 1)

            with patch.object(WebsiteClient, "preview_content_pack", return_value={"ok": True, "estimated_import": {"would_import": 2}}), patch.object(
                WebsiteClient,
                "execute_content_pack",
                return_value={"ok": True, "summary": {"imported": 2, "errors": 0}},
            ):
                previewed = sync.preview_upload(upload.id)
                self.assertEqual(previewed.status, "previewed")
                imported = sync.execute_upload(upload.id)
                self.assertEqual(imported.status, "imported")
                self.assertEqual(imported.result["summary"]["imported"], 2)

    def test_connection_profile_tracks_sync_health_without_storing_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            sync = SyncManager(store)
            sync.save_profile("https://example.invalid", "session-token")
            raw = read_json(paths.connection_profiles_file, {})
            self.assertNotIn("session-token", str(raw))
            with patch.object(WebsiteClient, "desktop_health", return_value={"ok": True, "version": "11.6.2", "desktop_api": "11.6.2"}):
                payload = sync.test_connection()
            self.assertTrue(payload["ok"])
            profile = sync.profile()
            self.assertEqual(profile.last_health, "Healthy")
            self.assertEqual(profile.desktop_api_version, "11.6.2")
            self.assertEqual(profile.website_version, "11.6.2")
            self.assertTrue(sync.center_snapshot()["version_compatible"])
            self.assertEqual(store.connection_profiles()[0].auth_token, "")
            self.assertNotIn("auth_token", profile.safe_dict())

    def test_self_hosted_website_url_configuration_precedence_and_validation(self) -> None:
        self.assertEqual(normalize_website_base_url("https://IAGT.tailnet.EXAMPLE./"), "https://iagt.tailnet.example")
        self.assertEqual(normalize_website_base_url("127.0.0.1:8007"), "http://127.0.0.1:8007")
        self.assertEqual(normalize_website_base_url("http://127.0.0.1:8007/"), "http://127.0.0.1:8007")
        with self.assertRaises(ValueError):
            normalize_website_base_url("ftp://example.com")
        with self.assertRaises(ValueError):
            normalize_website_base_url("http://example.com")
        with patch.dict(os.environ, {"GT_WEBSITE_URL": "https://iagt.tailnet.example/"}, clear=False):
            self.assertEqual(default_website_url(), "https://iagt.tailnet.example")

        with tempfile.TemporaryDirectory() as temp:
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            settings = store.settings()
            self.assertEqual(settings["default_website_url"], "http://127.0.0.1:8007")
            sync = SyncManager(store)
            profile = sync.save_profile("https://IAGT.tailnet.EXAMPLE///", "session-token")
            self.assertEqual(profile.base_url, "https://iagt.tailnet.example")
            raw = read_json(paths.connection_profiles_file, {})
            self.assertNotIn("session-token", str(raw))

    def test_connection_profile_does_not_require_password(self) -> None:
        profile = WebsiteConnectionProfile(auth_token="session-token")
        self.assertTrue(profile.safe_dict()["has_token"])
        self.assertNotIn("auth_token", profile.safe_dict())

    def test_upload_auth_rejection_marks_failed_and_retry_requeues(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            sync = SyncManager(store)
            pack = build_pack(
                source_dir=FIXTURES / "chapters",
                output_dir=paths.packs_dir,
                novel_id="fixture-novel",
                novel_title="Fixture Novel",
                target_mode="original",
            )
            upload = sync.queue_upload(pack.path, "fixture-novel", "original")
            with patch.object(WebsiteClient, "preview_content_pack", side_effect=RuntimeError("HTTP 401 admin_required")):
                with self.assertRaises(RuntimeError):
                    sync.preview_upload(upload.id)
            failed = store.upload(upload.id)
            self.assertEqual(failed.status, "failed")
            self.assertIn("401", failed.error)
            retried = sync.retry_upload(upload.id)
            self.assertEqual(retried.status, "queued")
            self.assertEqual(retried.error, "")

    def test_public_website_health_when_enabled(self) -> None:
        if os.getenv("GT_DESKTOP_TEST_WEBSITE") != "1":
            self.skipTest("Set GT_DESKTOP_TEST_WEBSITE=1 to run public /api/health check.")
        payload = WebsiteClient().test_connection()
        self.assertTrue(payload.get("ok"))


if __name__ == "__main__":
    unittest.main()
