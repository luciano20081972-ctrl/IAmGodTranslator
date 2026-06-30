from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any


CONTENT_PATTERNS = [
    r"第\s*(\d+)\s*章\s*(.*)",
    r"Chapter\s+(\d+)\s*[:：-]?\s*(.*)",
]

FILENAME_PATTERNS = [
    r"Chapter\s+(\d+)",
    r"第\s*(\d+)\s*章",
    r"^(\d{1,6})\b",
]

logger = logging.getLogger(__name__)


def read_text(path: str | Path) -> str:
    encodings = [
        "utf-8",
        "utf-8-sig",
        "gb18030",
        "gbk",
        "big5",
    ]

    for encoding in encodings:
        try:
            return Path(path).read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            logger.exception("Failed to read chapter file: %s", path)
            return ""

    logger.warning("Could not decode chapter file with known encodings: %s", path)
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def chapter_from_filename(path: str | Path) -> int | None:
    name = Path(path).stem

    for pattern in FILENAME_PATTERNS:
        match = re.search(pattern, name, re.IGNORECASE)

        if match:
            return int(match.group(1))

    return None


def parse_chapter(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = read_text(path)

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    number = chapter_from_filename(path)
    title = path.stem

    for line in lines[:25]:
        for pattern in CONTENT_PATTERNS:
            match = re.search(pattern, line, re.IGNORECASE)

            if match:
                number = int(match.group(1))

                if len(match.groups()) > 1:
                    extracted = match.group(2).strip()

                    if extracted:
                        title = extracted

                break

        if number is not None:
            break

    return {
        "number": number,
        "title": title,
        "text": text,
        "path": str(path),
        "size": len(text),
    }
