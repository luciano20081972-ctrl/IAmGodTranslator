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

    def test_additive_migration_preserves_v10_4_data_and_is_idempotent(self) -> None:
        db = self.make_db()
        db.save_novel_metadata("migration-fixture", {"title": "Migration Fixture"})
        db.upsert_chapter("migration-fixture", 1, "Chapter 1", "Original", "Reference", "Legacy English", "gpt-4o-mini")
        job = db.create_translation_job("migration-fixture", [1], {"only_untranslated": False, "model": "gpt-4o-mini"})
        db.ensure_user_profile("user-1", "reader@example.com", "user", "Reader", None)
        db.save_reading_progress("user-1", "migration-fixture", 1, "ai", 42)
        db.save_bookmark("user-1", "migration-fixture", 1, "note")
        db.set_favorite("user-1", "migration-fixture", True)

        db.initialize()
        db.initialize()

        chapter = db.chapter_text("migration-fixture", 1, "english")
        self.assertEqual(chapter["text"], "Legacy English")
        self.assertEqual(db.chapter_text("migration-fixture", 1, "original")["text"], "Original")
        self.assertEqual(db.chapter_text("migration-fixture", 1, "reference")["text"], "Reference")
        self.assertIsNotNone(db.translation_job(job["id"]))
        self.assertEqual(db.reading_progress("user-1")["chapter_number"], 1)
        self.assertEqual(len(db.bookmarks("user-1")), 1)
        self.assertEqual(len(db.favorites("user-1")), 1)
        self.assertEqual(len(db.english_editions("migration-fixture", 1)), 1)

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
        self.assertEqual(overwritten["summary"]["overwritten"], 1)
        self.assertEqual(db.chapter_text(novel_id, 1, "english")["text"], "Replacement")

    def test_preview_does_not_mutate_database(self) -> None:
        db = self.make_db()
        payload = {
            "novel": {"title": "Preview Only"},
            "items": [{"chapter_number": 1, "content_type": "original", "text": "Original"}],
        }
        preview = db.content_import_preview(payload)
        self.assertTrue(preview["can_execute"])
        self.assertIsNone(db.novel("preview-only"))

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

    def test_legacy_ai_timestamp_migration_is_safe_and_idempotent(self) -> None:
        db = self.make_db()
        db.save_novel_metadata("timestamp-fixture", {"title": "Timestamp Fixture"})
        cases = [
            (1, "Valid timestamp", "2026-02-03T04:05:06+00:00", "2026-01-01T00:00:00+00:00", "2026-02-03T04:05:06+00:00"),
            (2, "Null timestamp", None, "2026-01-02T00:00:00+00:00", "2026-01-02T00:00:00+00:00"),
            (3, "Empty timestamp", "", "2026-01-03T00:00:00+00:00", "2026-01-03T00:00:00+00:00"),
            (4, "Malformed timestamp", "not-a-timestamp", "2026-01-04T00:00:00+00:00", "2026-01-04T00:00:00+00:00"),
            (5, "Partial migration", "bad-partial", "2026-01-05T00:00:00+00:00", "2026-01-05T00:00:00+00:00"),
            (6, "Existing official default", None, "2026-01-06T00:00:00+00:00", "2026-01-06T00:00:00+00:00"),
        ]
        with db.connect() as conn:
            for chapter_number, text, translated_at, created_at, _expected_created_at in cases:
                conn.execute(
                    f"""
                    INSERT INTO {db.table('chapters')} (
                        novel_id, chapter_number, title, ai_text, ai_char_count,
                        translation_status, created_at, updated_at, translated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'translated', ?, ?, ?)
                    """,
                    (
                        "timestamp-fixture",
                        chapter_number,
                        f"Chapter {chapter_number}",
                        text,
                        len(text),
                        created_at,
                        created_at,
                        translated_at,
                    ),
                )
            conn.execute(
                f"""
                INSERT INTO {db.table('chapter_editions')} (
                    novel_id, chapter_number, edition_key, language, edition_type,
                    source_label, text, character_count, is_default, metadata_json, created_at, updated_at
                )
                VALUES (?, 5, 'ai', 'en', 'AI', 'Legacy AI', 'Old partial text', 16, 1, '{{}}',
                    '2026-01-05T00:00:00+00:00', '2026-01-05T00:00:00+00:00')
                """,
                ("timestamp-fixture",),
            )
            conn.execute(
                f"""
                INSERT INTO {db.table('chapter_editions')} (
                    novel_id, chapter_number, edition_key, language, edition_type,
                    source_label, text, character_count, is_default, metadata_json, created_at, updated_at
                )
                VALUES (?, 6, 'official', 'en', 'Official', 'Official import', 'Official text', 13, 1, '{{}}',
                    '2026-01-06T00:00:00+00:00', '2026-01-06T00:00:00+00:00')
                """,
                ("timestamp-fixture",),
            )

        db.initialize()
        db.initialize()

        with db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number, edition_key, text, is_default, created_at
                FROM {db.table('chapter_editions')}
                WHERE novel_id = ?
                ORDER BY chapter_number, edition_key
                """,
                ("timestamp-fixture",),
            ).fetchall()
            ai_texts = conn.execute(
                f"""
                SELECT chapter_number, ai_text
                FROM {db.table('chapters')}
                WHERE novel_id = ?
                ORDER BY chapter_number
                """,
                ("timestamp-fixture",),
            ).fetchall()

        by_chapter = {}
        for row in rows:
            by_chapter.setdefault(row["chapter_number"], []).append(dict(row))
        for chapter_number, text, _translated_at, _created_at, expected_created_at in cases[:5]:
            editions = by_chapter[chapter_number]
            self.assertEqual(len(editions), 1)
            self.assertEqual(editions[0]["edition_key"], "ai")
            self.assertEqual(editions[0]["text"], text)
            self.assertEqual(editions[0]["created_at"], expected_created_at)
            self.assertEqual(editions[0]["is_default"], 1)

        chapter_six = by_chapter[6]
        self.assertEqual(len(chapter_six), 2)
        self.assertEqual(sum(edition["is_default"] for edition in chapter_six), 1)
        self.assertEqual(next(edition for edition in chapter_six if edition["edition_key"] == "ai")["is_default"], 0)
        self.assertEqual({row["ai_text"] for row in ai_texts}, {case[1] for case in cases})

    def test_postgres_legacy_ai_migration_uses_safe_timestamp_helper(self) -> None:
        class FakeConnection:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> "FakeConnection":
                self.statements.append(sql)
                return self

        db = Database("postgresql://fixture")
        conn = FakeConnection()
        db._migrate_ai_text_to_english_editions(conn)
        combined = "\n".join(conn.statements)
        insert_sql = conn.statements[-1]

        self.assertIn('CREATE OR REPLACE FUNCTION "godtranslator_v10"."safe_timestamptz_from_text"', combined)
        self.assertIn("EXCEPTION WHEN OTHERS THEN", combined)
        self.assertIn('"godtranslator_v10"."safe_timestamptz_from_text"(legacy.translated_at, legacy.created_at)', insert_sql)
        self.assertNotIn("COALESCE(translated_at, created_at)", insert_sql)
        self.assertIn("existing_default.edition_key <> 'ai'", insert_sql)

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

    def test_pack_checksum_mismatch_is_rejected_in_preview(self) -> None:
        db = self.make_db()
        manifest = {
            "format": "godtranslator-english-pack-v1",
            "novel_id": "bad-pack",
            "chapters": [{"chapter_number": 1, "content_type": "english", "file": "english/0001.txt", "sha256": "bad"}],
        }
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("english/0001.txt", b"English")
        payload = payload_from_uploads([("bad.zip", memory.getvalue())])
        preview = db.content_import_preview(payload)
        self.assertFalse(preview["can_execute"])
        self.assertIn("SHA-256 mismatch", " ".join(payload.get("warnings", [])))

    def test_default_edition_priority_and_admin_selection(self) -> None:
        db = self.make_db()
        payload = {
            "novel": {"title": "Edition Priority"},
            "items": [
                {"chapter_number": 1, "content_type": "english", "edition_type": "AI", "text": "AI edition"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "Imported", "text": "Imported edition"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "Edited", "text": "Edited edition"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "Official", "text": "Official edition"},
            ],
            "options": {"overwrite_existing": True},
        }
        result = db.apply_content_import_payload(payload)
        novel_id = result["novel_id"]
        self.assertEqual(db.chapter_text(novel_id, 1, "english")["text"], "Official edition")
        lower_priority = db.apply_content_import_payload({
            "novel_id": novel_id,
            "items": [{"chapter_number": 1, "content_type": "english", "edition_type": "AI", "text": "New AI edition"}],
            "options": {"overwrite_existing": True},
        })
        self.assertTrue(lower_priority["ok"])
        self.assertEqual(db.chapter_text(novel_id, 1, "english")["text"], "Official edition")
        ai_key = next(edition["edition_key"] for edition in db.english_editions(novel_id, 1) if edition["edition_type"] == "AI")
        db.set_default_english_edition(novel_id, 1, ai_key)
        self.assertEqual(db.chapter_text(novel_id, 1, "english")["edition"]["edition_key"], ai_key)

    def test_new_novel_pack_format_is_accepted(self) -> None:
        db = self.make_db()
        original = "Packed Original"
        english = "Packed English"
        original_raw = original.encode("utf-8")
        english_raw = english.encode("utf-8")
        manifest = {
            "format": "godtranslator-new-novel-pack-v1",
            "novel_id": "new-novel-pack",
            "novel": {"title": "New Novel Pack"},
            "content_type": "mixed",
            "chapters": [
                {
                    "chapter_number": 1,
                    "content_type": "original",
                    "file": "original/0001.txt",
                    "sha256": hashlib.sha256(original_raw).hexdigest(),
                },
                {
                    "chapter_number": 1,
                    "content_type": "english",
                    "edition_type": "Imported",
                    "file": "english/0001.txt",
                    "sha256": hashlib.sha256(english_raw).hexdigest(),
                },
            ],
        }
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("original/0001.txt", original_raw)
            zf.writestr("english/0001.txt", english_raw)
        payload = payload_from_uploads([("new-novel.zip", memory.getvalue())])
        preview = db.content_import_preview(payload)
        self.assertTrue(preview["can_execute"])
        result = db.apply_content_import_payload(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(db.chapter_text("new-novel-pack", 1, "original")["text"], original)
        self.assertEqual(db.chapter_text("new-novel-pack", 1, "english")["text"], english)

    def test_fully_translated_and_partial_novel_counts(self) -> None:
        db = self.make_db()
        full_payload = {
            "novel": {"title": "Full Fixture"},
            "items": [
                item
                for chapter in range(1, 801)
                for item in (
                    {"chapter_number": chapter, "content_type": "original", "text": f"Original {chapter}"},
                    {"chapter_number": chapter, "content_type": "english", "edition_type": "Imported", "text": f"English {chapter}"},
                )
            ],
        }
        full = db.apply_content_import_payload(full_payload)
        self.assertTrue(full["ok"])
        self.assertEqual(db.verification_counts(full["novel_id"])["english"], 800)
        self.assertEqual(db.all_untranslated_chapters(full["novel_id"]), [])
        self.assertTrue(db.chapter_text(full["novel_id"], 800, "english")["ok"])

        partial_items = []
        for chapter in range(1, 101):
            partial_items.append({"chapter_number": chapter, "content_type": "original", "text": f"Original {chapter}"})
            if chapter <= 40:
                partial_items.append({"chapter_number": chapter, "content_type": "english", "text": f"English {chapter}"})
            if chapter <= 80:
                partial_items.append({"chapter_number": chapter, "content_type": "reference", "text": f"Reference {chapter}"})
        partial = db.apply_content_import_payload({"novel": {"title": "Partial Fixture"}, "items": partial_items})
        counts = db.verification_counts(partial["novel_id"])
        self.assertEqual(counts["original"], 100)
        self.assertEqual(counts["english"], 40)
        self.assertEqual(counts["reference"], 80)
        self.assertEqual(len(db.all_untranslated_chapters(partial["novel_id"])), 60)

    def test_platform_backup_includes_editions_and_restore_preview_understands_them(self) -> None:
        db = self.make_db()
        result = db.apply_content_import_payload({
            "novel": {"title": "Backup Fixture"},
            "items": [{"chapter_number": 1, "content_type": "english", "edition_type": "Imported", "text": "English"}],
        })
        backup = db.platform_backup_payload()
        self.assertIn("chapter_editions", backup["tables"])
        self.assertIn("content_import_items", backup["tables"])
        self.assertTrue(backup["tables"]["chapter_editions"])
        self.assertEqual(backup["manifest"]["chapter_source_counts"]["english"], 1)
        self.assertIn("secrets", backup["manifest"]["excluded"])
        preview = db.restore_preview(backup, mode="add-missing")
        self.assertIn("chapter_editions", preview["changes"])
        self.assertEqual(preview["changes"]["chapter_editions"]["skip_existing"], 1)
        self.assertEqual(result["summary"]["imported"], 1)


if __name__ == "__main__":
    unittest.main()
