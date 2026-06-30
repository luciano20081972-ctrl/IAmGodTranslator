from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.context import build_context
from modules.prompt_builder import build_prompt
from modules.prompt_writer import save_prompt


def process_chapter(
    chinese: dict[str, Any],
    novelfire: dict[str, Any] | None = None,
    prompt_dir: str | Path = "Prompts",
    memory_path: str | Path = "memory.json",
    glossary_path: str | Path = "glossary.json",
    style_path: str | Path = "style.json",
) -> Path:
    chapter_number = chinese.get("number")

    if chapter_number is None:
        raise ValueError("Cannot build a prompt for a chapter without a chapter number.")

    context = build_context(
        chinese,
        novelfire,
        memory_path=memory_path,
        glossary_path=glossary_path,
    )
    prompt = build_prompt(
        context,
        style_path=style_path,
        memory_path=memory_path,
        glossary_path=glossary_path,
    )

    return save_prompt(int(chapter_number), prompt, output_dir=prompt_dir)
