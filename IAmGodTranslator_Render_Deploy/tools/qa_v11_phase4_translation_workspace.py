from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOLS))

os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
DB_PY = (ROOT / "app" / "db.py").read_text(encoding="utf-8")

from app.db import normalized_translation_settings  # noqa: E402
from qa_v10_6_translation_selector import build_db, create_job_from_payload, item_chapters, persisted_item_chapters  # noqa: E402


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> None:
    for count in ("25", "50", "100", "200", "500", "1000", "all", "custom"):
        require(f"count option {count}", f'value="{count}"' in APP_JS or f'"{count}"' in APP_JS)
    require("all untranslated server-side copy", "selected from the database when the job is created" in APP_JS)
    require("specific ranges supported", "1-50,75,100-125" in APP_JS and "parseChapterInputDetailed" in APP_JS)
    require("large warning", "Large-job safety check" in APP_JS and "Budget margin" in APP_JS)
    require("all confirmation", "Translate all eligible chapters?" in APP_JS and "confirmAllUntranslated" in APP_JS)
    require("disabled launch explanations", "Launch Job is disabled" in APP_JS and "launchReason" in APP_JS)

    for preset in ("careful", "balanced", "fast", "maximum-safe", "economy", "overnight", "custom"):
        require(f"backend preset {preset}", f'"{preset}":' in DB_PY)
        require(f"ui preset {preset}", f'value="{preset}"' in APP_JS)
    require("custom exposes advanced controls", 'speedPreset?.value !== "custom"' in APP_JS and "useAdvancedControls" in APP_JS)
    require("activity banner shell", 'id="activityBanner"' in INDEX)
    require("activity banner real jobs api", "refreshActivityIndicator" in APP_JS and 'cachedApi("/api/translation/jobs"' in APP_JS)
    require("activity banner css", ".activity-banner" in CSS and ".activity-banner[hidden]" in CSS)

    settings = {preset: normalized_translation_settings({"translation_mode": "simple", "speed_preset": preset}) for preset in ("careful", "balanced", "fast", "maximum-safe", "economy", "overnight")}
    require("economy one worker", settings["economy"]["concurrency"] == 1 and settings["economy"]["max_workers"] == 1)
    require("overnight low pressure retries", settings["overnight"]["concurrency"] == 1 and settings["overnight"]["retry_count"] == 4)
    require("maximum safe higher bound", settings["maximum-safe"]["concurrency"] >= settings["fast"]["concurrency"])
    custom = normalized_translation_settings({"translation_mode": "simple", "speed_preset": "custom", "concurrency": 5, "batch_size": 77, "retry_count": 1, "auto_optimize_speed": True})
    require("custom honors controls", custom["concurrency"] == 5 and custom["batch_size"] == 77 and custom["retry_count"] == 1)
    require("custom disables auto override", custom["auto_optimize_speed"] is False)

    db = build_db("v11-phase4-1000", chapters=1100)
    created = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 1000, "next_count_mode": "1000", "translation_mode": "simple", "speed_preset": "balanced", "model": "gpt-4o-mini"},
    )
    preview_chapters = item_chapters(created["job"])
    chapters = persisted_item_chapters(db, created["job"]["id"])
    require("1000 item job", len(chapters) == 1000)
    require("1000 item job no duplicates", len(chapters) == len(set(chapters)))
    require("1000 item job persistent", created["job"]["total_items"] == 1000 and created["job"]["status"] == "queued")
    require("1000 item detail preview bounded", len(preview_chapters) <= 500)

    all_created = create_job_from_payload(
        db,
        {"selection_mode": "all-untranslated", "translation_mode": "simple", "speed_preset": "economy", "model": "gpt-4o-mini"},
    )
    require("all untranslated server-side", all_created["selection"]["diagnostics"]["server_side_selection"] is True)
    require("all untranslated skips missing/already English", all_created["selection"]["diagnostics"]["missing_original_count"] == 2 and all_created["selection"]["diagnostics"]["already_translated_count"] == 25)

    print(
        {
            "ok": True,
            "counts": "passed",
            "server_side_selection": "passed",
            "speed_presets": "passed",
            "large_job_safety": "passed",
            "activity_banner": "passed",
            "no_openai_key": os.environ.get("OPENAI_API_KEY") is None,
            "production_database_url": bool(os.environ.get("DATABASE_URL")),
        }
    )


if __name__ == "__main__":
    main()
