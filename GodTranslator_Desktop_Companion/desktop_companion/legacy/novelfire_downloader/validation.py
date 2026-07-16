from __future__ import annotations

import re


BLOCKED_MARKERS = (
    "cloudflare",
    "checking your browser",
    "just a moment",
    "captcha",
    "verify you are human",
    "login to continue",
    "sign in to continue",
    "access denied",
    "error 403",
    "error 404",
    "page not found",
)


def blocked_reason(html_or_text: str) -> str | None:
    sample = (html_or_text or "")[:50000].lower()
    for marker in BLOCKED_MARKERS:
        if marker in sample:
            return marker
    return None


def chapter_number_matches(chapter: int, title: str, text: str, url: str = "") -> bool:
    haystack = f"{title}\n{text[:800]}\n{url}"
    patterns = (
        re.compile(rf"\bchapter\s*0*{chapter}\b", re.IGNORECASE),
        re.compile(rf"\bch(?:ap)?\.?\s*0*{chapter}\b", re.IGNORECASE),
        re.compile(rf"第\s*0*{chapter}\s*章"),
        re.compile(rf"[\\/_.-]0*{chapter}(?:[\\/_.-]|$)", re.IGNORECASE),
    )
    return any(pattern.search(haystack) for pattern in patterns)


def validate_chapter(chapter: int, title: str, text: str, url: str, min_chars: int = 500) -> None:
    if blocked_reason(text):
        raise ValueError(f"Blocked or challenge page detected: {blocked_reason(text)}")
    body = (text or "").strip()
    if len(body) < min_chars:
        raise ValueError(f"Chapter body is too short ({len(body)} characters).")
    if not chapter_number_matches(chapter, title, body, url):
        raise ValueError(f"Downloaded page does not look like chapter {chapter}.")

def valid_existing_file(path, chapter: int, min_chars: int = 500) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return len(text.strip()) >= min_chars and chapter_number_matches(chapter, path.stem, text, str(path))
