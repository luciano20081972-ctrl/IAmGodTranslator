"""Exercise additive reading-progress storage and rollback on a disposable database."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Database


def fixture_locator(**changes):
    return {
        "version": 1, "novel_id": "locator-fixture", "chapter_number": 1, "source": "english",
        "content_hash": "a" * 64, "paragraph_index": 5, "paragraph_offset": .25, "progression": .45,
        **changes,
    }


def assert_upgrade_rollback(db):
    """Rehearse pre-R1, R1 and rollback states on the same fixture rows."""
    progress = db.table("reading_progress")
    db.save_novel_metadata("locator-fixture", {"title": "Synthetic locator novel"})

    def old_rows(table):
        columns = "user_id, novel_id, chapter_number, source, updated_at, scroll_percent"
        with db.connect() as conn:
            return [dict(row) for row in conn.execute(f"SELECT {columns} FROM {table} ORDER BY user_id").fetchall()]

    with db.connect() as conn:
        conn.execute(f"ALTER TABLE {progress} DROP COLUMN locator_json")
        conn.execute(
            f"INSERT INTO {progress} (user_id, novel_id, chapter_number, source, scroll_percent, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("reader", "locator-fixture", 1, "ai", 31.5, "2026-11-25T00:00:00Z"),
        )
    before = old_rows(progress)
    db.initialize()
    db.initialize()
    assert old_rows(progress) == before, "upgrade changed a legacy progress record"
    assert "locator" not in db.reading_progress("reader", "locator-fixture")

    locator = fixture_locator()
    assert db.save_reading_progress("reader", "locator-fixture", 1, "english", 45, locator)["locator"] == locator
    assert db.reading_progress("reader", "locator-fixture")["locator"] == locator
    with db.connect() as conn:
        # A prior app can continue updating the legacy fields with the new column present.
        conn.execute(f"UPDATE {progress} SET scroll_percent = ? WHERE user_id = ?", (38, "reader"))
    legacy_write = db.reading_progress("reader", "locator-fixture")
    assert legacy_write["scroll_percent"] == 38 and "locator" not in legacy_write

    before_rollback = old_rows(progress)
    with db.connect() as conn:
        conn.execute(f"ALTER TABLE {progress} DROP COLUMN locator_json")
    assert old_rows(progress) == before_rollback, "dropping the optional column changed legacy progress"
    db.initialize()
    assert old_rows(progress) == before_rollback
    assert db.reading_progress("reader", "locator-fixture")["scroll_percent"] == 38


class LocatorStorageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Database(f"sqlite:///{Path(directory.name) / 'fixture.db'}")
        self.db.initialize()

    def test_upgrade_and_rollback_preserve_legacy_progress(self):
        assert_upgrade_rollback(self.db)

    def test_malformed_locator_falls_back_to_legacy_percent(self):
        self.db.save_novel_metadata("locator-fixture", {"title": "Synthetic locator novel"})
        invalid = [
            fixture_locator(version=2), fixture_locator(version=True), fixture_locator(novel_id="other"),
            fixture_locator(chapter_number=2), fixture_locator(chapter_number=True), fixture_locator(source="reference"),
            fixture_locator(content_hash="invalid"), fixture_locator(paragraph_index=-1),
            fixture_locator(paragraph_index=True), fixture_locator(paragraph_offset=float("nan")),
            fixture_locator(paragraph_offset=1), fixture_locator(progression=.5),
            fixture_locator(quote="This text must never be stored"),
        ]
        for locator in invalid:
            with self.subTest(locator=locator):
                progress = self.db.save_reading_progress("reader", "locator-fixture", 1, "english", 45, locator)
                self.assertEqual(progress["scroll_percent"], 45)
                self.assertNotIn("locator", progress)
        with self.db.connect() as conn:
            row = conn.execute(f"SELECT locator_json FROM {self.db.table('reading_progress')}").fetchone()
        self.assertIsNone(row["locator_json"])

    def test_legacy_and_account_scoped_writes(self):
        self.db.save_novel_metadata("locator-fixture", {"title": "Synthetic locator novel"})
        locator = fixture_locator()
        self.db.save_reading_progress("reader-a", "locator-fixture", 1, "english", 45, locator)
        self.assertIsNone(self.db.reading_progress("reader-b", "locator-fixture"))
        self.db.save_reading_progress("reader-b", "locator-fixture", 1, "ai", 20)
        self.assertEqual(self.db.reading_progress("reader-a", "locator-fixture")["locator"], locator)
        self.assertEqual(self.db.reading_progress("reader-b", "locator-fixture")["scroll_percent"], 20)
        self.db.save_reading_progress("reader-a", "locator-fixture", 2, "ai", 10)
        self.assertNotIn("locator", self.db.reading_progress("reader-a", "locator-fixture"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
