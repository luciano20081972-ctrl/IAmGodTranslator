"""Cycle 4 QA for Reader local-first cache and large chapter-list performance."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


def configure_database(path: Path) -> None:
    os.environ["DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    os.environ["AUTH_ENABLED"] = "false"
    os.environ["TRANSLATION_AUTOSTART"] = "false"


def require(label: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def seed(main: Any, chapters: int = 1200) -> str:
    novel_id = "cycle4-reader-scale"
    db = main.database
    db.initialize()
    db.save_novel_metadata(
        novel_id,
        {
            "title": "Cycle 4 Reader Scale Novel",
            "summary": "Synthetic local fixture for Reader performance QA.",
            "author": "Fixture Generator",
            "metadata": {"seeded": True, "cycle": "v11.6-cycle4"},
        },
    )
    for chapter in range(1, chapters + 1):
        text = "\n\n".join(
            f"Chapter {chapter} paragraph {index}. Synthetic Reader performance fixture text."
            for index in range(1, 6)
        )
        main.database.upsert_chapter(novel_id, chapter, f"Chapter {chapter}", text, "", f"English {text}", "fixture")
    return novel_id


def run() -> dict[str, Any]:
    failures: list[str] = []
    db_path = Path(tempfile.gettempdir()) / "iagt-v11-6-cycle4-reader.sqlite"
    configure_database(db_path)
    from fastapi.testclient import TestClient
    from app import main

    novel_id = seed(main)
    client = TestClient(main.app)

    page_one = client.get(f"/api/novels/{novel_id}/library?limit=50&offset=0&view=all").json()
    page_two = client.get(f"/api/novels/{novel_id}/library?limit=50&offset=50&view=all").json()
    search = client.get(f"/api/novels/{novel_id}/library?limit=50&offset=0&view=all&search=Chapter%20100").json()
    chapter_1 = client.get(f"/api/novels/{novel_id}/chapters/1/english").json()
    chapter_2 = client.get(f"/api/novels/{novel_id}/chapters/2/english").json()
    chapter_last = client.get(f"/api/novels/{novel_id}/chapters/1200/english").json()

    app_js = (APP_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    styles = (APP_ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    require("page one returns 50 rows", len(page_one.get("chapters", [])) == 50, failures)
    require("page one total remains 1200", page_one.get("total") == 1200, failures)
    require("page two starts at chapter 51", page_two.get("chapters", [{}])[0].get("chapter_number") == 51, failures)
    require("server search reduces eligible total", 1 <= int(search.get("total") or 0) < 1200, failures)
    require("server search returns chapter 100", any(item.get("chapter_number") == 100 for item in search.get("chapters", [])), failures)
    require("chapter response includes content hash", bool(chapter_1.get("content_hash")) and len(chapter_1.get("content_hash")) == 64, failures)
    require("chapter response includes previous/next neighbors", chapter_2.get("neighbors") == {"previous": 1, "next": 3}, failures)
    require("first chapter previous neighbor is null", chapter_1.get("neighbors", {}).get("previous") is None, failures)
    require("last chapter next neighbor is null", chapter_last.get("neighbors", {}).get("next") is None, failures)
    require("frontend removed 5000-row chapter fetch", "library?limit=5000" not in app_js and "CHAPTER_SEARCH_INDEX_LIMIT" not in app_js, failures)
    require("frontend uses server-side chapter search", "params.set(\"search\"" in app_js and "URLSearchParams" in app_js, failures)
    require("reader persistent cache is bounded", "READER_PERSISTENT_CACHE_LIMIT = 12" in app_js and "READER_PERSISTENT_CACHE_BYTES" in app_js, failures)
    require("reader cache uses IndexedDB", "indexedDB.open(\"iagt-reader-cache-v1\"" in app_js, failures)
    require("reader cache is account namespaced", "user:${state.account.user_id}" in app_js and "\"guest\"" in app_js, failures)
    require("reader cache has hash invalidation", "content_hash" in app_js and "revalidateReaderChapter" in app_js, failures)
    require("reader prefetch reuses chapter fetcher", "fetchReaderChapter(novelId, chapter, source, {prefetch: true})" in app_js, failures)
    require("progress sync is throttled", "READER_PROGRESS_SYNC_INTERVAL_MS = 5_000" in app_js and "queueReaderProgressSync" in app_js, failures)
    require("page lifecycle progress flush exists", "visibilitychange" in app_js and "pagehide" in app_js, failures)
    require("offline cache clear control exists", "clearReaderPersistentCache" in app_js and "Clear Offline Reader Cache" in app_js, failures)
    require("cache note is styled", "reader-cache-note" in styles, failures)

    return {
        "ok": not failures,
        "failures": failures,
        "db_path": str(db_path),
        "chapter_rows_page_one": len(page_one.get("chapters", [])),
        "chapter_rows_page_two": len(page_two.get("chapters", [])),
        "search_total": search.get("total"),
        "content_hash_sample": chapter_1.get("content_hash", "")[:12],
        "neighbors_sample": chapter_2.get("neighbors"),
        "production_content_used": False,
        "production_database_used": False,
        "openai_called": False,
    }


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
