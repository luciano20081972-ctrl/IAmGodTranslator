from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "app" / "main.py").read_text(encoding="utf-8")

from app.content_import import payload_from_uploads  # noqa: E402
from app.db import Database  # noqa: E402
from app.recovery import parse_uploads  # noqa: E402


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def make_db() -> Database:
    path = Path(tempfile.mkdtemp()) / "godtranslator-v11-phase5.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    return db


def main() -> None:
    for text in (
        "AI English edition metadata",
        "Desktop Companion Pack",
        "Mixed / Multi-edition Pack",
        "Metadata JSON",
        "Glossary",
        "AI Edition Imports",
        "Rollback Planning",
        "Make Default",
    ):
        require(f"ui includes {text}", text in APP_JS)
    require("edition type upload params", "edition_type" in APP_JS and "edition_type" in MAIN_PY)
    require("default edition action", "data-default-edition" in APP_JS and "setDefaultEnglishEdition" in APP_JS)
    require("rollback deferred safely", "transactionally" in APP_JS and "Backups & Recovery restore preview" in APP_JS)

    db = make_db()
    ai_payload = payload_from_uploads(
        [("Chapter 001.txt", b"AI English one")],
        {"novel": {"title": "AI Simple"}, "content_type": "ai", "edition_type": "AI"},
    )
    ai_preview = db.content_import_preview(ai_payload)
    require("ai preview executable", ai_preview["can_execute"])
    require("ai preview creates row", ai_preview["rows_to_create_count"] == 1)
    require("ai preview edition count", ai_preview["edition_type_counts"]["AI"] == 1)
    require("ai preview counts as english content", ai_preview["content_to_add"]["english"] == 1)
    ai_result = db.apply_content_import_payload(ai_payload)
    ai_chapter = db.chapter_text(ai_result["novel_id"], 1, "english")
    require("ai import reads as english", ai_chapter["ok"] and ai_chapter["text"] == "AI English one")
    require("ai edition metadata preserved", ai_chapter["edition"]["edition_type"] == "AI")

    sidecar = {
        "novel": {
            "title": "Sidecar Fixture",
            "summary": "Summary",
            "cover_url": "https://example.invalid/cover.jpg",
            "metadata": {"genre": "Fantasy"},
        },
        "glossary": "Term=Meaning",
        "items": [{"chapter_number": 1, "content_type": "original", "text": "Original"}],
    }
    sidecar_result = db.apply_content_import_payload(sidecar)
    novel = db.novel(sidecar_result["novel_id"])
    require("sidecar cover saved", novel["cover_url"] == "https://example.invalid/cover.jpg")
    require("sidecar metadata saved", novel["metadata"]["genre"] == "Fantasy")
    require("sidecar glossary saved", novel["metadata"]["glossary"] == "Term=Meaning")

    editions_payload = {
        "novel": {"title": "Edition Switch"},
        "items": [
            {"chapter_number": 1, "content_type": "english", "edition_type": "Official", "text": "Official"},
            {"chapter_number": 1, "content_type": "english", "edition_type": "AI", "text": "AI"},
        ],
        "options": {"overwrite_existing": True},
    }
    switch_result = db.apply_content_import_payload(editions_payload)
    novel_id = switch_result["novel_id"]
    ai_key = next(edition["edition_key"] for edition in db.english_editions(novel_id, 1) if edition["edition_type"] == "AI")
    db.set_default_english_edition(novel_id, 1, ai_key)
    require("default edition switched", db.chapter_text(novel_id, 1, "english")["edition"]["edition_key"] == ai_key)

    db.save_novel_metadata("recovery-fixture", {"title": "Recovery Fixture"})
    db.upsert_chapter("recovery-fixture", 1, "Chapter 1", "", "", "", None)
    parse_uploads([("Chapter 1.txt", b"Recovered original")], "recovery-fixture", db, target_mode="original")
    parse_uploads([("Chapter 2.txt", b"Should not create")], "recovery-fixture", db, target_mode="english")
    require("recovery did not create absent rows", db.verification_counts("recovery-fixture")["total"] == 1)
    require("content import creates absent rows", db.apply_content_import_payload({"novel_id": "recovery-fixture", "items": [{"chapter_number": 2, "content_type": "english", "text": "Created"}]})["summary"]["imported"] == 1)

    print(
        {
            "ok": True,
            "ai_simple_import": "passed",
            "metadata_cover_glossary": "passed",
            "default_edition": "passed",
            "recovery_separation": "passed",
            "ui_static": "passed",
            "no_openai_key": os.environ.get("OPENAI_API_KEY") is None,
            "production_database_url": bool(os.environ.get("DATABASE_URL")),
        }
    )


if __name__ == "__main__":
    main()
