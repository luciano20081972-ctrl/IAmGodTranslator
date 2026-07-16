from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import desktop_companion
from desktop_companion.jobs import JobManager
from desktop_companion.models import WebsiteConnectionProfile
from desktop_companion.adapters import adapter_descriptors, adapter_names
from desktop_companion.packs import build_auto_packs, build_pack, validate_pack
from desktop_companion.paths import app_paths
from desktop_companion.recovery import load_recovery_request
from desktop_companion.storage import CompanionStore, read_json
from desktop_companion.sync import SyncManager
from desktop_companion.ui_app import NAV_ITEMS
from desktop_companion.website_api import WebsiteClient


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"


class DesktopCompanionFoundationTests(unittest.TestCase):
    def test_application_import(self) -> None:
        self.assertEqual(desktop_companion.APP_NAME, "GodTranslator Desktop Companion")

    def test_recovery_request_parsing(self) -> None:
        request = load_recovery_request(FIXTURES / "recovery_request.json")
        self.assertEqual(request.novel_id, "fixture-novel")
        self.assertEqual(request.target_mode, "reference")
        self.assertEqual(request.chapters, [1, 2, 4])
        self.assertEqual(request.missing_count, 3)

    def test_job_persistence_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = app_paths(Path(temp))
            store = CompanionStore(paths)
            manager = JobManager(store, paths)
            job = manager.create_job("Fixture Novel", "https://example.invalid/novel", [1, 2, 3], output_dir=paths.downloads_dir / "fixture")
            self.assertEqual(job.status, "queued")
            manager.pause(job.id)
            self.assertEqual(store.job(job.id).status, "paused")
            manager.resume(job.id)
            self.assertEqual(store.job(job.id).status, "queued")
            payload = read_json(paths.jobs_file, {})
            self.assertEqual(payload["jobs"][0]["id"], job.id)

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

    def test_ui_sections_smoke(self) -> None:
        self.assertEqual(
            NAV_ITEMS,
            [
                "Home",
                "Downloads",
                "New Novel",
                "Sync Center",
                "Recovery Requests",
                "Export & Packs",
                "Desktop Library",
                "Activity",
                "Settings",
                "Logs",
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
            store = CompanionStore(app_paths(Path(temp)))
            sync = SyncManager(store)
            sync.save_profile("https://example.invalid", "session-token")
            with patch.object(WebsiteClient, "desktop_health", return_value={"ok": True, "desktop_api": "10.6.0"}):
                payload = sync.test_connection()
            self.assertTrue(payload["ok"])
            profile = store.connection_profiles()[0]
            self.assertEqual(profile.last_health, "Healthy")
            self.assertNotIn("auth_token", profile.safe_dict())

    def test_connection_profile_does_not_require_password(self) -> None:
        profile = WebsiteConnectionProfile(auth_token="session-token")
        self.assertTrue(profile.safe_dict()["has_token"])
        self.assertNotIn("auth_token", profile.safe_dict())

    def test_public_website_health_when_enabled(self) -> None:
        if os.getenv("GT_DESKTOP_TEST_WEBSITE") != "1":
            self.skipTest("Set GT_DESKTOP_TEST_WEBSITE=1 to run public /api/health check.")
        payload = WebsiteClient().test_connection()
        self.assertTrue(payload.get("ok"))


if __name__ == "__main__":
    unittest.main()
