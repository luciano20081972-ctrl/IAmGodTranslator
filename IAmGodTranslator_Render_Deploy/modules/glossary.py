from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Glossary:

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)

        if self.filename.exists():
            with open(self.filename, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "Characters": {},
                "Places": {},
                "Abilities": {},
                "Organizations": {},
                "Items": {},
                "Titles": {},
            }

    def get(self, category: str, key: str) -> Any:
        return self.data.get(category, {}).get(key)

    def set(self, category: str, key: str, value: Any) -> None:
        if category not in self.data:
            self.data[category] = {}

        self.data[category][key] = value

    def save(self) -> None:
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(
                self.data,
                f,
                indent=4,
                ensure_ascii=False,
            )
