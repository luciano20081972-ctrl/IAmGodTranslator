from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import hashlib
import io
import json
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.content_import import payload_from_uploads
from app.db import Database
from app.recovery import parse_uploads


class ContentImportEditionTests(unittest.TestCase):
    def make_db(self) -> Database:
        path = Path(tempfile.mkdtemp()) / "godtranslator-v10-5.db"
        db = Database(f"sqlite:///{path}")
        db.initialize()
        return db

    def test_brand_new_novel_original_and_english_reads_without_translation(self) -> None:
        db = self.make_db()
        payload = {
            "novel": {"title": "Fixture Complete Novel", "author": "QA"},
            "items": [
                {"chapter_number": 1, "content_type": "original", "title": "Arrival", "text": "原文一"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "Official", "title": "Arrival", "text": "English one."},
                {"chapter_number": 2, "content_type": "original", "title": "Departure", "text": "原文二"},
                {"chapter_number": 2, "content_type": "english", "edition_type": "Official", "title": "Departure", "text": "English two."},
            ],
        }
        preview = db.content_import_preview(payload)
        self.assertTrue(preview["can_execute"])
        result = db.apply_content_import_payload(payload)
        self.assertTrue(result["ok"])
        novel_id = result["novel_id"]
        counts = db.verification_counts(novel_id)
        self.assertEqual(counts["original"], 2)
        self.assertEqual(counts["english"], 2)
        self.assertEqual(db.all_untranslated_chapters(novel_id), [])
        chapter = db.chapter_text(novel_id, 1, "english")
        self.assertTrue(chapter["ok"])
        self.assertEqual(chapter["text"], "English one.")
        self.assertEqual(chapter["edition"]["edition_type"], "Official")

    def test_import_modes_original_only_english_only_reference_only_and_mixed(self) -> None:
        db = self.make_db()
        mixed = {
            "novel": {"title": "Mixed Fixture"},
            "items": [
                {"chapter_number": 1, "content_type": "original", "text": "原文"},
                {"chapter_number": 1, "content_type": "reference", "text": "Reference"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "Imported", "text": "English"},
                {"chapter_number": 2, "content_type": "english", "edition_type": "Human", "text": "English only"},
                {"chapter_number": 3, "content_type": "reference", "text": "Reference only"},
            ],
        }
        result = db.apply_content_import_payload(mixed)
        novel_id = result["novel_id"]
        library = db.library(novel_id)
        self.assertEqual(library["total"], 3)
        self.assertTrue(db.chapter_text(novel_id, 1, "original")["ok"])
        self.assertTrue(db.chapter_text(novel_id, 1, "reference")["ok"])
        self.assertTrue(db.chapter_text(novel_id, 2, "english")["ok"])
        self.assertFalse(db.chapter_text(novel_id, 3, "english")["ok"])

    def test_skip_existing_overwrite_and_duplicate_preview(self) -> None:
        db = self.make_db()
        payload = {
            "novel": {"title": "Duplicate Fixture"},
            "items": [
                {"chapter_number": 1, "content_type": "english", "text": "First"},
                {"chapter_number": 1, "content_type": "english", "text": "Duplicate"},
            ],
        }
        preview = db.content_import_preview(payload)
        self.assertEqual(preview["duplicate_count"], 1)
        result = db.apply_content_import_payload({"novel": {"title": "Duplicate Fixture"}, "items": [payload["items"][0]]})
        novel_id = result["novel_id"]
        skipped = db.apply_content_import_payload({
            "novel_id": novel_id,
            "items": [{"chapter_number": 1, "content_type": "english", "text": "Replacement"}],
        })
        self.assertEqual(skipped["summary"]["skipped"], 1)
        overwritten = db.apply_content_import_payload({
            "novel_id": novel_id,
            "items": [{"chapter_number": 1, "content_type": "english", "edition_type": "Edited", "text": "Replacement"}],
            "options": {"overwrite_existing": True},
        })
        self.assertEqual(overwritten["summary"]["updated"], 1)
        self.assertEqual(db.chapter_text(novel_id, 1, "english")["text"], "Replacement")

    def test_recovery_fills_missing_only_without_creating_rows(self) -> None:
        db = self.make_db()
        db.save_novel_metadata("recovery-fixture", {"title": "Recovery Fixture"})
        db.upsert_chapter("recovery-fixture", 1, "Chapter 1", "", "", "", None)
        preview = parse_uploads([("Chapter 1.txt", "Recovered original".encode("utf-8"))], "recovery-fixture", db, target_mode="original")
        result = db.apply_import_job(preview["job_id"])
        self.assertEqual(result["imported_count"], 1)
        self.assertTrue(db.chapter_text("recovery-fixture", 1, "original")["ok"])
        missing_preview = parse_uploads([("Chapter 2.txt", "Should not create".encode("utf-8"))], "recovery-fixture", db, target_mode="english")
        skipped = db.apply_import_job(missing_preview["job_id"])
        self.assertEqual(skipped["imported_count"], 0)
        self.assertFalse(db.chapter_text("recovery-fixture", 2, "english")["ok"])

    def test_legacy_ai_migrates_to_english_edition(self) -> None:
        db = self.make_db()
        db.save_novel_metadata("legacy-ai", {"title": "Legacy AI"})
        with db.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {db.table('chapters')} (
                    novel_id, chapter_number, title, ai_text, ai_char_count,
                    translation_status, created_at, updated_at
                )
                VALUES (?, 1, 'Chapter 1', 'Legacy English', 14, 'translated', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                ("legacy-ai",),
            )
        db.initialize()
        editions = db.english_editions("legacy-ai", 1)
        self.assertEqual(len(editions), 1)
        self.assertEqual(editions[0]["edition_type"], "AI")
        self.assertEqual(db.chapter_text("legacy-ai", 1, "english")["text"], "Legacy English")

    def test_import_pack_preview_and_execute(self) -> None:
        db = self.make_db()
        english = "Packed English"
        raw = english.encode("utf-8")
        manifest = {
            "format": "godtranslator-english-pack-v1",
            "novel_id": "packed-fixture",
            "novel": {"title": "Packed Fixture"},
            "content_type": "english",
            "edition_type": "Official",
            "language": "en",
            "chapters": [
                {
                    "chapter_number": 1,
                    "content_type": "english",
                    "edition_type": "Official",
                    "file": "english/0001.txt",
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            ],
        }
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("english/0001.txt", raw)
        payload = payload_from_uploads([("pack.zip", memory.getvalue())])
        preview = db.content_import_preview(payload)
        self.assertTrue(preview["can_execute"])
        result = db.apply_content_import_payload(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(db.chapter_text("packed-fixture", 1, "english")["text"], english)


if __name__ == "__main__":
    unittest.main()
