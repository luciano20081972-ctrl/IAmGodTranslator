"""Seeded local performance profile for v11.6 Library/Reader scale checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


def configure_database(path: Path) -> None:
    os.environ["DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    os.environ["AUTH_ENABLED"] = "false"
    os.environ["TRANSLATION_AUTOSTART"] = "false"


def synthetic_text(chapter: int, paragraphs: int = 10) -> str:
    return "\n\n".join(
        f"Chapter {chapter} synthetic paragraph {index}. This public-domain-like fixture line exists only for performance measurement."
        for index in range(1, paragraphs + 1)
    )


def seed_database(main: Any, novel_count: int, large_chapters: int) -> dict[str, int | str]:
    db = main.database
    db.initialize()
    large_id = "seed-large-000"
    total_chapters = 0
    for index in range(novel_count):
        novel_id = large_id if index == 0 else f"seed-novel-{index:03d}"
        chapter_count = large_chapters if index == 0 else 12
        db.save_novel_metadata(
            novel_id,
            {
                "title": "Seeded Thousand Chapter Novel" if index == 0 else f"Seeded Library Novel {index:03d}",
                "summary": "Synthetic local benchmark data. No copyrighted chapter text is used.",
                "author": "Fixture Generator",
                "metadata": {"seeded": True, "benchmark": "v11.6-cycle3"},
            },
        )
        for chapter in range(1, chapter_count + 1):
            paragraphs = 18 if index == 0 and chapter in {1, 2, large_chapters} else 4
            text = synthetic_text(chapter, paragraphs=paragraphs)
            db.upsert_chapter(novel_id, chapter, f"Chapter {chapter}", text, "", f"English {text}", "fixture")
        total_chapters += chapter_count
    return {"novels": novel_count, "chapters": total_chapters, "largest_novel": large_id, "largest_novel_chapters": large_chapters}


def measure(client: Any, path: str, runs: int = 3) -> dict[str, Any]:
    samples: list[float] = []
    status = 0
    body = b""
    for _ in range(runs):
        start = time.perf_counter()
        response = client.get(path)
        samples.append((time.perf_counter() - start) * 1000)
        status = response.status_code
        body = response.content
    return {
        "path": path,
        "status": status,
        "runs": runs,
        "mean_ms": round(sum(samples) / len(samples), 2),
        "best_ms": round(min(samples), 2),
        "bytes": len(body),
    }


def run(db_path: Path, novel_count: int, large_chapters: int) -> dict[str, Any]:
    configure_database(db_path)
    from fastapi.testclient import TestClient
    from app import main

    seed = seed_database(main, novel_count, large_chapters)
    client = TestClient(main.app)
    large_id = str(seed["largest_novel"])
    metrics = [
        measure(client, "/api/novels"),
        measure(client, f"/api/novels/{large_id}"),
        measure(client, f"/api/novels/{large_id}/library?limit=50&offset=0"),
        measure(client, f"/api/novels/{large_id}/library?limit=50&offset=950"),
        measure(client, f"/api/novels/{large_id}/chapters/1/english"),
        measure(client, f"/api/novels/{large_id}/chapters/2/english"),
        measure(client, f"/api/novels/{large_id}/chapters/{large_chapters}/english"),
    ]
    library_payload = client.get(f"/api/novels/{large_id}/library?limit=50&offset=0").json()
    chapter_payload = client.get(f"/api/novels/{large_id}/chapters/1/english").json()
    chapter_text = chapter_payload.get("text") or chapter_payload.get("chapter", {}).get("text", "")
    return {
        "ok": all(item["status"] == 200 for item in metrics),
        "db_path": str(db_path),
        "seed": seed,
        "metrics": metrics,
        "library_first_page_chapters": len(library_payload.get("chapters", [])),
        "library_total": library_payload.get("total"),
        "chapter_1_text_chars": len(chapter_text),
        "production_content_used": False,
        "production_database_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=str(Path(tempfile.gettempdir()) / "iagt-v11-6-cycle3-seeded.sqlite"))
    parser.add_argument("--novels", type=int, default=60)
    parser.add_argument("--large-chapters", type=int, default=1200)
    args = parser.parse_args()
    result = run(Path(args.db_path), args.novels, args.large_chapters)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
