from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database


def main() -> int:
    db = Database("sqlite:///data/v10-local.db")
    db.initialize()
    db.initialize()
    checks: dict[str, object] = {
        "schema_idempotent": True,
        "backend": db.config.backend,
        "ping": db.ping(),
        "requirements_valid": (ROOT / "requirements.txt").read_text(encoding="utf-8").strip() != "{}",
        "counts": db.verification_counts("i-am-god"),
        "library_total": db.library("i-am-god")["total"],
        "chapters": {},
    }

    for chapter in (1, 100, 906):
        result = db.chapter_text("i-am-god", chapter, "original")
        checks["chapters"][str(chapter)] = {"original_ok": result["ok"], "length": len(result["text"])}
        assert result["ok"], f"Chapter {chapter} Original did not load"

    checks["chapter_1_reference"] = db.chapter_text("i-am-god", 1, "reference")["ok"]
    checks["chapter_1_ai"] = db.chapter_text("i-am-god", 1, "ai")["ok"]
    checks["chapter_906_ai_status"] = db.chapter_text("i-am-god", 906, "ai")["status"]

    for name in ("original", "originals", "reference", "references", "ai", "ai_translations", "English", "chapters"):
        path = ROOT / "data" / name
        if path.exists():
            shutil.rmtree(path)

    checks["after_runtime_delete"] = {
        str(chapter): db.chapter_text("i-am-god", chapter, "original")["ok"]
        for chapter in (1, 100, 906)
    }

    restarted = Database("sqlite:///data/v10-local.db")
    checks["restart"] = {
        "ping": restarted.ping(),
        "chapter_1": restarted.chapter_text("i-am-god", 1, "original")["ok"],
        "chapter_100": restarted.chapter_text("i-am-god", 100, "original")["ok"],
        "chapter_906": restarted.chapter_text("i-am-god", 906, "original")["ok"],
    }

    try:
        with restarted.connect() as conn:
            conn.execute(
                f"INSERT INTO {restarted.table('chapters')} (novel_id, chapter_number, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("i-am-god", 1, "duplicate", "now", "now"),
            )
        checks["unique_enforced"] = False
        raise AssertionError("UNIQUE(novel_id, chapter_number) was not enforced")
    except sqlite3.IntegrityError:
        checks["unique_enforced"] = True

    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
