from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class StyleGuide:

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)

        if self.filename.exists():
            with open(self.filename, "r", encoding="utf-8") as f:
                self.data: dict[str, Any] = json.load(f)
        else:
            self.data = {
                "writing_style": "Natural English novel",
                "tense": "past",
                "quotes": "double",
                "preserve_paragraphs": True,
                "keep_chapter_titles": True,
                "prefer_chinese_meaning": True,
                "use_novelfire_as_reference": True,
                "target_reader": "Native English speaker",
            }

    def save(self) -> None:
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(
                self.data,
                f,
                indent=4,
                ensure_ascii=False,
            )
