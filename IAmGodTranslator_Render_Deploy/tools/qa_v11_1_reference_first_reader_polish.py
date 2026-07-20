from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")

APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
DB_PY = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    from qa_backup_manifest_hotfix import install_fastapi_stubs

    install_fastapi_stubs()

from app.db import Database  # noqa: E402


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def build_db(name: str) -> Database:
    path = Path(tempfile.gettempdir()) / f"gt-v11-1-{name}-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    return db


def seed_novel(db: Database, novel_id: str, chapters: int, *, policy: str = "reference_first") -> None:
    db.save_novel_metadata(
        novel_id,
        {
            "id": novel_id,
            "title": novel_id.replace("-", " ").title(),
            "model": "gpt-4o-mini",
            "status": "active",
            "reference_source_url": "fixture://reference",
            "metadata": {"english_coverage_policy": policy},
        },
    )
    for chapter in range(1, chapters + 1):
        db.upsert_chapter(novel_id, chapter, f"Chapter {chapter}", None, None, None)


def text(label: str, chapter: int) -> str:
    return f"{label} synthetic chapter {chapter}. This fixture text is intentionally short."


def set_chapter(db: Database, novel_id: str, chapter: int, original: bool, reference: bool, english: bool = False) -> None:
    db.upsert_chapter(
        novel_id,
        chapter,
        f"Chapter {chapter}",
        text("Original", chapter) if original else None,
        text("Reference", chapter) if reference else None,
        text("English", chapter) if english else None,
    )


def fixture_current_i_am_god() -> dict[str, Any]:
    db = build_db("i-am-god")
    seed_novel(db, "i-am-god", 908)
    for chapter in range(1, 909):
        if chapter in {176, 177}:
            set_chapter(db, "i-am-god", chapter, original=False, reference=True, english=False)
        else:
            set_chapter(db, "i-am-god", chapter, original=True, reference=True, english=True)
    preview = db.english_coverage_preview("i-am-god")
    require("fixture A existing English", preview["existing_english"] == 906)
    require("fixture A Reference fill", preview["reference_fill"] == 2)
    require("fixture A AI translation", preview["translation_from_original"] == 0)
    require("fixture A blocked", preview["blocked"] == 0)
    require("fixture A chapters 176/177", preview["chapters"]["reference_fill"] == [176, 177])
    estimate = db.estimate_translation("i-am-god", [176, 177], {"model": "gpt-4o-mini"})
    require("Reference estimate no AI", estimate["eligible_count"] == 0 and estimate["reference_fill_count"] == 2)
    result = db.apply_reference_coverage("i-am-god", actor="qa")
    require("Reference promotion two", result["promoted_count"] == 2)
    require("Reference promotion no OpenAI", result["openai_call_count"] == 0 and result["translation_job_created"] is False)
    after = db.verification_counts("i-am-god")
    require("active English after promotion", after["english"] == 908)
    require("Reference preserved", db.chapter_text("i-am-god", 176, "reference")["text"] == text("Reference", 176))
    editions = db.english_editions("i-am-god", 176)
    require("Reference-derived edition created", len(editions) == 1 and editions[0]["edition_type"] == "Reference Derived")
    metadata = editions[0]["metadata"]
    require("Reference provenance", metadata["source_kind"] == "reference" and metadata["provenance"] == "reference_promoted")
    require("Reference checksum", bool(metadata.get("content_sha256")))
    again = db.apply_reference_coverage("i-am-god", actor="qa")
    require("idempotent promotion", again["promoted_count"] == 0)
    require("no duplicate editions", len(db.english_editions("i-am-god", 176)) == 1 and len(db.english_editions("i-am-god", 177)) == 1)
    return {"preview": preview, "after": after, "promoted": result}


def fixture_future_novel() -> dict[str, Any]:
    db = build_db("future")
    seed_novel(db, "future-novel", 900)
    for chapter in range(1, 901):
        set_chapter(db, "future-novel", chapter, original=True, reference=chapter <= 480, english=False)
    preview = db.english_coverage_preview("future-novel")
    require("future Reference fill", preview["reference_fill"] == 480)
    require("future AI translation", preview["translation_from_original"] == 420)
    require("future blocked", preview["blocked"] == 0)
    result = db.apply_reference_coverage("future-novel", actor="qa")
    require("future apply 480", result["promoted_count"] == 480)
    after = db.english_coverage_preview("future-novel")
    require("future after AI 420", after["existing_english"] == 480 and after["translation_from_original"] == 420)
    return preview


def fixture_gapped_reference() -> dict[str, Any]:
    db = build_db("gapped")
    seed_novel(db, "gapped-reference", 200)
    for chapter in range(1, 201):
        has_reference = 1 <= chapter <= 100 or 102 <= chapter <= 150
        set_chapter(db, "gapped-reference", chapter, original=True, reference=has_reference, english=False)
    preview = db.english_coverage_preview("gapped-reference")
    require("gapped Reference fill", preview["reference_fill"] == 149)
    require("gapped AI translation", preview["translation_from_original"] == 51)
    require("gapped chapter 101 AI", 101 in preview["chapters"]["translation_from_original"])
    return preview


def fixture_no_source() -> dict[str, Any]:
    db = build_db("blocked")
    seed_novel(db, "blocked-novel", 1)
    preview = db.english_coverage_preview("blocked-novel")
    require("blocked missing source", preview["blocked_missing_source"] == 1)
    return preview


def static_reader_and_privacy_checks() -> None:
    require("version app", 'const APP_VERSION = "11.1.0"' in APP_JS)
    require("version backend", 'VERSION = "11.1.0"' in MAIN_PY and 'DESKTOP_API_VERSION = "11.1.0"' in MAIN_PY)
    require("cache keys", "v=11.1.0" in INDEX)
    require("public English source only", 'return canViewReference() ? ["english", "original", "reference"] : ["english"]' in APP_JS)
    require("public edition scrub", 'payload.pop("edition", None)' in MAIN_PY)
    require("Reference endpoint role gate", 'if mode == "reference":' in MAIN_PY and "require_translator(request)" in MAIN_PY)
    require("coverage endpoints", "english-coverage/preview" in MAIN_PY and "english-coverage/apply-reference" in MAIN_PY)
    require("coverage UI", "Build English Coverage" in APP_JS and "Use Reference for" in APP_JS)
    require("no Reference OpenAI cost", "reference_promotion_cost" in DB_PY and "openai_call_count" in DB_PY)
    require("abort stale reader", "readerAbortController.abort()" in APP_JS and "AbortError" in APP_JS)
    require("reader dedupe", "readerRequestMap" in APP_JS)
    require("bounded cache", "READER_CACHE_LIMIT" in APP_JS and "rememberCachePayload" in APP_JS)
    require("guest bookmarks", "gt-local-bookmarks" in APP_JS and "toggleLocalBookmark" in APP_JS)
    require("keyboard T S Escape", 'event.key.toLowerCase() === "t"' in APP_JS and 'event.key.toLowerCase() === "s"' in APP_JS and 'event.key === "Escape"' in APP_JS)
    require("Reader settings sheet controls", "reader-settings-grid" in APP_JS and "AMOLED" in APP_JS)
    require("Reader chrome quiet", 'data-reader-chrome="quiet"' in CSS or "readerChrome" in APP_JS)
    require("TOC search", "filterChapterDrawer" in APP_JS and "data-chapter-row" in APP_JS)


def main() -> None:
    current = fixture_current_i_am_god()
    future = fixture_future_novel()
    gapped = fixture_gapped_reference()
    blocked = fixture_no_source()
    static_reader_and_privacy_checks()
    require("OpenAI absent", not os.environ.get("OPENAI_API_KEY"))
    print(
        {
            "ok": True,
            "fixture_a": {
                "existing_english": current["preview"]["existing_english"],
                "reference_fill": current["preview"]["reference_fill"],
                "after_english": current["after"]["english"],
                "promoted": current["promoted"]["promoted_count"],
            },
            "future_novel": {
                "reference_fill": future["reference_fill"],
                "translation_from_original": future["translation_from_original"],
            },
            "gapped_reference": {
                "reference_fill": gapped["reference_fill"],
                "translation_from_original": gapped["translation_from_original"],
            },
            "blocked_missing_source": blocked["blocked_missing_source"],
            "reader_static": "passed",
            "reference_privacy": "passed",
            "no_openai_key": True,
        }
    )


if __name__ == "__main__":
    main()
