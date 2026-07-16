from __future__ import annotations

import re
import urllib.parse

from bs4 import BeautifulSoup


CHAPTER_PATTERNS = (
    re.compile(r"\bchapter\s*0*(\d{1,6})\b", re.IGNORECASE),
    re.compile(r"\bch(?:ap)?\.?\s*0*(\d{1,6})\b", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,6})\s*章"),
    re.compile(r"[/_-]0*(\d{1,6})(?:[/_.-]|$)", re.IGNORECASE),
)


def discover_chapter_links(novel_url: str, html: str) -> dict[int, str]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[int, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(novel_url, anchor["href"])
        label = anchor.get_text(" ", strip=True)
        number = parse_chapter_number(f"{label} {href}")
        if number and number not in found:
            found[number] = href
    return dict(sorted(found.items()))


def parse_chapter_number(value: str) -> int | None:
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(value or "")
        if match:
            number = int(match.group(1))
            if number > 0:
                return number
    return None


def format_url_template(template: str, chapter: int) -> str:
    return template.format(chapter=chapter, chapter03=f"{chapter:03d}", chapter04=f"{chapter:04d}")

