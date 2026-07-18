from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> None:
    for label in (
        "Back to Novel",
        "Chapter List",
        "Previous",
        "Next",
        "Bookmark",
        "Reader Settings",
        "Focus",
        "Back to Top",
    ):
        require(f"reader control {label}", label in APP_JS)

    require("reader progress text", "readerProgressText" in APP_JS and "readerScrollProgress" in APP_JS)
    require("reader progress updates on scroll", "updateReaderProgressUi(percent)" in APP_JS)
    require("estimated reading time", "readerMetrics(payload" in APP_JS and "Read Time" in APP_JS)
    require("chapter progress", "Novel Progress" in APP_JS and "chapterProgress" in APP_JS)
    require("chapter search", "readerTextSearch" in APP_JS and "searchReaderText" in APP_JS)
    require("chapter highlight", "<mark>$1</mark>" in APP_JS)
    require("paragraph copy", "data-copy-paragraph" in APP_JS and "copyParagraphText" in APP_JS)
    require("duplicate heading suppression", "isDuplicateChapterHeading" in APP_JS and "lines.shift()" in APP_JS)
    require("bounded prefetch neighbors only", "prefetchNeighborChapters" in APP_JS and "[neighborChapter(chapterNumber, -1), neighborChapter(chapterNumber, 1)]" in APP_JS)
    require("reference remains role gated", 'return canTranslate() ? ["english", "original", "reference"] : ["english", "original"]' in APP_JS)
    require("single chapter body endpoint", "chapterTextPath(novelId, chapterNumber, source)" in APP_JS)

    for css in (
        ".reader-meta",
        ".reader-progress",
        ".reader-tools",
        ".copy-paragraph",
        ".reader-text mark",
    ):
        require(f"reader css {css}", css in CSS)
    require("mobile reader tool wrapping", ".reader-tools" in CSS and "grid-template-columns: 1fr" in CSS)

    print({
        "ok": True,
        "reader_controls": "passed",
        "reader_progress": "passed",
        "reader_search": "passed",
        "paragraph_copy": "passed",
        "reference_privacy_static": "passed",
        "bounded_loading_static": "passed",
    })


if __name__ == "__main__":
    main()
