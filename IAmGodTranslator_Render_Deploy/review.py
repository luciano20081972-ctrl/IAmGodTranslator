from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_queue(index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []

    for chapter in sorted(index.values(), key=lambda x: x["chapter"]):
        if not chapter["translated"]:
            queue.append({
                "chapter": chapter["chapter"],
                "status": "pending",
                "tries": 0,
            })

    return queue


def save_queue(queue: list[dict[str, Any]], filename: str | Path) -> None:
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            queue,
            f,
            indent=4,
            ensure_ascii=False,
        )

    print()
    print("=" * 50)
    print("Translation Queue")
    print("=" * 50)
    print(f"Pending Chapters : {len(queue)}")
    print(f"Saved : {filename}")
