from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database


class CaptureConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "CaptureConnection":
        self.statements.append(sql)
        self.params.append(params)
        return self

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []


def capture_postgres_upsert_sql() -> dict[str, Any]:
    capture = CaptureConnection()
    db = Database("postgresql://unit-test")

    @contextmanager
    def fake_connect() -> Iterator[CaptureConnection]:
        yield capture

    db.connect = fake_connect  # type: ignore[method-assign]
    db.upsert_chapter(
        "qa-novel",
        1,
        "Chapter 1",
        "Original",
        "Reference",
        "AI",
        ai_model="gpt-4o-mini",
    )
    sql = "\n".join(capture.statements)
    required_refs = [
        "target.title",
        "target.original_text",
        "target.reference_text",
        "target.ai_text",
        "target.ai_model",
    ]
    return {
        "postgres_sql_captured": bool(sql),
        "uses_target_alias": " AS target " in sql,
        "has_stale_table_dot_refs": ("chapters" + ".") in sql,
        "required_existing_row_refs_present": {ref: ref in sql for ref in required_refs},
        "sql_preview": [line.strip() for line in sql.splitlines() if line.strip()][:18],
    }


def run_sqlite_idempotency_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{Path(tmp) / 'upsert-qa.db'}")
        db.initialize()
        db.upsert_novel("qa-novel", "QA Novel")
        db.upsert_chapter("qa-novel", 1, "First title", "old original", None, "old ai", ai_model="old-model")
        db.upsert_chapter("qa-novel", 1, None, None, "new reference", None, ai_model=None)

        with db.connect() as conn:
            row_after_partial = dict(conn.execute(f"SELECT * FROM {db.table('chapters')} WHERE novel_id = ? AND chapter_number = ?", ("qa-novel", 1)).fetchone())
            row_count_after_partial = conn.execute(f"SELECT COUNT(*) AS total FROM {db.table('chapters')} WHERE novel_id = ? AND chapter_number = ?", ("qa-novel", 1)).fetchone()["total"]

        db.upsert_chapter("qa-novel", 1, "Updated title", "new original", "new reference 2", "new ai", ai_model="new-model")
        with db.connect() as conn:
            row_after_update = dict(conn.execute(f"SELECT * FROM {db.table('chapters')} WHERE novel_id = ? AND chapter_number = ?", ("qa-novel", 1)).fetchone())
            row_count_after_update = conn.execute(f"SELECT COUNT(*) AS total FROM {db.table('chapters')} WHERE novel_id = ? AND chapter_number = ?", ("qa-novel", 1)).fetchone()["total"]
            try:
                conn.execute(
                    f"INSERT INTO {db.table('chapters')} (novel_id, chapter_number, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("qa-novel", 1, "duplicate", "now", "now"),
                )
                unique_prevented_duplicates = False
            except sqlite3.IntegrityError:
                unique_prevented_duplicates = True

    return {
        "inserted_new_chapter": row_count_after_partial == 1,
        "repeated_upsert_row_count": row_count_after_update,
        "unique_prevented_duplicates": unique_prevented_duplicates,
        "coalesce_preserved_existing": {
            "title": row_after_partial["title"] == "First title",
            "original_text": row_after_partial["original_text"] == "old original",
            "ai_text": row_after_partial["ai_text"] == "old ai",
            "ai_model": row_after_partial["ai_model"] == "old-model",
            "reference_text_added": row_after_partial["reference_text"] == "new reference",
        },
        "newer_non_empty_values_updated": {
            "title": row_after_update["title"] == "Updated title",
            "original_text": row_after_update["original_text"] == "new original",
            "reference_text": row_after_update["reference_text"] == "new reference 2",
            "ai_text": row_after_update["ai_text"] == "new ai",
            "ai_model": row_after_update["ai_model"] == "new-model",
        },
    }


def main() -> int:
    checks = {
        "postgres_upsert_sql": capture_postgres_upsert_sql(),
        "sqlite_idempotency": run_sqlite_idempotency_test(),
    }
    pg = checks["postgres_upsert_sql"]
    sqlite = checks["sqlite_idempotency"]
    assert pg["postgres_sql_captured"]
    assert pg["uses_target_alias"]
    assert not pg["has_stale_table_dot_refs"]
    assert all(pg["required_existing_row_refs_present"].values())
    assert sqlite["inserted_new_chapter"]
    assert sqlite["repeated_upsert_row_count"] == 1
    assert sqlite["unique_prevented_duplicates"]
    assert all(sqlite["coalesce_preserved_existing"].values())
    assert all(sqlite["newer_non_empty_values_updated"].values())
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
