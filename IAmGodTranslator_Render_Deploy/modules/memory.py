from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TranslationMemory:

    def __init__(self, filename: str | Path):
        self.filename = Path(filename)

        if self.filename.exists():
            with open(self.filename, "r", encoding="utf-8") as f:
                self.memory = json.load(f)
        else:
            self.memory = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.memory.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def save(self) -> None:
        self.filename.parent.mkdir(parents=True, exist_ok=True)

        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(
                self.memory,
                f,
                indent=4,
                ensure_ascii=False,
            )

    def __len__(self) -> int:
        return len(self.memory)
