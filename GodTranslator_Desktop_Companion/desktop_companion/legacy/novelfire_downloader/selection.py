from __future__ import annotations

import re


def parse_chapter_selection(start: int | None = None, end: int | None = None, specific: str = "") -> list[int]:
    chapters: set[int] = set()
    if start is not None and end is not None:
        if start <= 0 or end <= 0:
            raise ValueError("Chapter numbers must be positive.")
        if end < start:
            raise ValueError("End chapter must be greater than or equal to start chapter.")
        chapters.update(range(start, end + 1))

    text = (specific or "").strip()
    if text:
        for part in re.split(r"[,;\s]+", text):
            if not part:
                continue
            if "-" in part:
                left, right = part.split("-", 1)
                a = int(left.strip())
                b = int(right.strip())
                if a <= 0 or b <= 0 or b < a:
                    raise ValueError(f"Invalid chapter range: {part}")
                chapters.update(range(a, b + 1))
            else:
                value = int(part)
                if value <= 0:
                    raise ValueError(f"Invalid chapter number: {part}")
                chapters.add(value)

    return sorted(chapters)


def filename_for_chapter(chapter: int, max_chapter: int | None = None, minimum_width: int = 4) -> str:
    width = max(minimum_width, len(str(max_chapter or chapter)))
    return f"{chapter:0{width}d}.txt"

