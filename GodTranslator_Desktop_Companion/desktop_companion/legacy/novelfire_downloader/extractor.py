from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


CONTENT_SELECTORS = (
    "article",
    "main",
    "#chapter-content",
    ".chapter-content",
    ".chapter-content-inner",
    ".reading-content",
    ".reader-content",
    ".novel-content",
    ".content",
)

REMOVE_SELECTORS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    ".comments",
    ".comment",
    ".ads",
    ".advertisement",
    ".breadcrumb",
    ".chapter-nav",
    ".pagination",
    ".recommend",
)

NOISE_PATTERNS = (
    re.compile(r"^(previous|next)\s+chapter$", re.IGNORECASE),
    re.compile(r"^(login|register|comments?|bookmark|report)$", re.IGNORECASE),
    re.compile(r"^novel\s*fire$", re.IGNORECASE),
    re.compile(r"^chapter\s+list$", re.IGNORECASE),
)


@dataclass(frozen=True)
class ExtractedChapter:
    title: str
    text: str


def extract_chapter(html: str) -> ExtractedChapter:
    soup = BeautifulSoup(html, "html.parser")
    for selector in REMOVE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    title = extract_title(soup)
    container = first_content_container(soup)
    text = text_from_container(container or soup)
    return ExtractedChapter(title=title, text=text)


def extract_title(soup: BeautifulSoup) -> str:
    for selector in ("h1", "h2", ".chapter-title", ".title"):
        node = soup.select_one(selector)
        if node:
            title = clean_line(node.get_text(" ", strip=True))
            if title:
                return title
    if soup.title:
        return clean_line(soup.title.get_text(" ", strip=True))
    return ""


def first_content_container(soup: BeautifulSoup):
    best = None
    best_len = 0
    for selector in CONTENT_SELECTORS:
        for node in soup.select(selector):
            text_len = len(node.get_text(" ", strip=True))
            if text_len > best_len:
                best = node
                best_len = text_len
    return best


def text_from_container(container) -> str:
    paragraphs: list[str] = []
    nodes = container.find_all(["p", "div"], recursive=True) if hasattr(container, "find_all") else []
    for node in nodes:
        text = clean_line(node.get_text(" ", strip=True))
        if is_useful_line(text):
            paragraphs.append(text)
    if not paragraphs:
        raw = container.get_text("\n", strip=True)
        paragraphs = [clean_line(line) for line in raw.splitlines() if is_useful_line(clean_line(line))]
    return "\n\n".join(dedupe_adjacent(paragraphs))


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_useful_line(value: str) -> bool:
    if not value:
        return False
    return not any(pattern.search(value) for pattern in NOISE_PATTERNS)


def dedupe_adjacent(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if not output or output[-1] != value:
            output.append(value)
    return output

