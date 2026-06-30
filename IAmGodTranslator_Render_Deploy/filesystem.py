from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.glossary import Glossary
from modules.memory import TranslationMemory


def build_context(
    chinese: dict[str, Any],
    novelfire: dict[str, Any] | None = None,
    memory_path: str | Path = "memory.json",
    glossary_path: str | Path = "glossary.json",
) -> dict[str, Any]:
    memory = TranslationMemory(memory_path)
    glossary = Glossary(glossary_path)

    context = {
        "chapter": chinese["number"],
        "title": chinese["title"],
        "chinese_text": chinese["text"],
        "novelfire_text": "",
        "memory": memory.memory,
        "glossary": glossary.data,
    }

    if novelfire:
        context["novelfire_text"] = novelfire["text"]

    return context
