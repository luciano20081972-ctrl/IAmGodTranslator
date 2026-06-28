from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.glossary import Glossary
from modules.memory import TranslationMemory
from modules.style import StyleGuide


def build_prompt(
    context: dict[str, Any],
    style_path: str | Path = "style.json",
    memory_path: str | Path = "memory.json",
    glossary_path: str | Path = "glossary.json",
) -> str:
    style = StyleGuide(style_path)
    memory = TranslationMemory(memory_path)
    glossary = Glossary(glossary_path)

    prompt = f"""
You are translating a Chinese web novel into professional English.

Novel:
I Am God

Chapter:
{context['chapter']}

Chapter Title:
{context['title']}

==============================
STYLE GUIDE
==============================

{style.data}

==============================
TRANSLATION MEMORY
==============================

{memory.memory}

==============================
GLOSSARY
==============================

{glossary.data}

==============================
IMPORTANT RULES
==============================

1. Chinese text is the source of truth.
2. NovelFire is only a reference.
3. Preserve all names from the glossary.
4. Produce smooth, natural English.
5. Never summarize.
6. Never skip paragraphs.
7. Keep dialogue formatting.
8. If NovelFire is better stylistically without changing meaning, you may improve the wording.

==============================
CHINESE ORIGINAL
==============================

{context['chinese_text']}

==============================
NOVELFIRE REFERENCE
==============================

{context['novelfire_text']}
"""

    return prompt
