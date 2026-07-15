from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.setdefault("DB_SCHEMA", "godtranslator_v10")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

from app.db import Database
from app import main as app_main


def build_database() -> Database:
    path = Path(tempfile.gettempdir()) / f"gt-v10-5-quality-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    db.save_novel_metadata("demo", {"id": "demo", "title": "Demo", "model": "gpt-4o-mini", "status": "active"})
    db.upsert_chapter(
        "demo",
        1,
        "Chapter 1",
        ("Original TermA paragraph. " * 80).strip(),
        ("Reference TermA paragraph. " * 30).strip(),
        None,
    )
    db.upsert_chapter(
        "demo",
        2,
        "Chapter 2",
        ("Original TermB paragraph. " * 70).strip(),
        None,
        "Existing AI chapter two.",
    )
    db.save_glossary_entry("demo", {"category": "characters", "source_term": "TermA", "preferred_translation": "Name A", "locked": True})
    for index in range(90):
        db.save_glossary_entry("demo", {"category": "items", "source_term": f"Unused{index}", "preferred_translation": f"Unused {index}"})
    return db


def complete_job_item(db: Database, job_id: str, text: str, worker: str = "qa-worker") -> dict[str, Any]:
    claim = db.claim_translation_item(job_id, worker, lease_seconds=60)
    assert claim.get("status") == "claimed", claim
    assert "TermA => Name A" in claim["settings"].get("glossary", "") or claim["chapter_number"] == 2
    assert "Unused89" not in claim["settings"].get("glossary", "")
    return db.finish_translation_item(
        job_id,
        int(claim["item_id"]),
        worker,
        result={"text": text, "input_tokens": 120, "output_tokens": 180, "actual_cost": 0.002},
        metrics={
            "prompt_instruction_tokens": 80,
            "prompt_original_tokens": 220,
            "prompt_reference_tokens": 90,
            "prompt_estimated_output_tokens": 180,
            "provider_wait_seconds": 0.01,
        },
    )


def database_feature_test() -> dict[str, Any]:
    db = build_database()
    profiles = db.translation_profiles()
    natural = next(profile for profile in profiles if profile["name"] == "Natural English Novel")
    job = db.create_translation_job(
        "demo",
        [1],
        {"profile_id": natural["id"], "batch_size": 1, "use_reference": True, "smart_glossary_enabled": True},
    )
    complete_job_item(db, str(job["id"]), "Translated AI chapter one.")
    history = db.translation_history("demo", 1)
    quality = db.translation_quality_workspace("demo")
    review = db.save_quality_review("demo", 1, {"status": "needs_retranslation", "score": 48, "warnings": ["awkward_voice"], "notes": "QA mark"}, reviewer_id="qa")
    detail_hidden = db.translation_quality_detail("demo", 1, include_reference=False)
    detail_visible = db.translation_quality_detail("demo", 1, include_reference=True)
    preview_chapters = db.retranslation_chapters("demo", {"mode": "low-quality"}, [])
    retranslation = db.create_translation_job(
        "demo",
        [1],
        {"profile_id": natural["id"], "batch_size": 1, "only_untranslated": False, "use_reference": False},
    )
    complete_job_item(db, str(retranslation["id"]), "Retranslated AI chapter one.", worker="qa-worker-2")
    new_history = db.translation_history("demo", 1)
    monitor = db.translation_monitor("demo")
    costs = db.translation_cost_analysis("demo")
    passed = (
        len(profiles) >= 5
        and len(history) == 1
        and quality["summary"]["translated"] >= 2
        and quality["chapters"][0]["profile_name"] == "Natural English Novel"
        and review["status"] == "needs_retranslation"
        and detail_hidden["reference"]["hidden"] is True
        and detail_visible["reference"]["ok"] is True
        and 1 in preview_chapters
        and len(new_history) >= 2
        and monitor["queue"]["active_jobs"] >= 0
        and costs["summary"]["total_cost"] > 0
    )
    return {
        "passed": passed,
        "profiles": len(profiles),
        "history_versions": len(new_history),
        "quality_summary": quality["summary"],
        "low_quality_chapters": preview_chapters,
        "cost_summary": costs["summary"],
    }


def api_feature_test() -> dict[str, Any]:
    db = build_database()
    natural = next(profile for profile in db.translation_profiles() if profile["name"] == "Natural English Novel")
    job = db.create_translation_job("demo", [1], {"profile_id": natural["id"], "batch_size": 1})
    complete_job_item(db, str(job["id"]), "Translated AI chapter one.")
    app_main.database = db
    app_main.translation_runner = app_main.TranslationRunner(db)
    from fastapi.testclient import TestClient

    with TestClient(app_main.app) as client:
        unauthorized = client.get("/api/admin/translation/monitor")
        login = client.post("/api/admin/login", json={"password": "qa-admin-password"})
        profiles = client.get("/api/translation/profiles")
        glossary = client.get("/api/novels/demo/glossary")
        quality = client.get("/api/novels/demo/quality")
        detail = client.get("/api/novels/demo/quality/1")
        review = client.put("/api/novels/demo/quality/1/review", json={"status": "good", "score": 82})
        prompt = client.post(
            "/api/admin/translation/prompt-inspector",
            json={"novel_id": "demo", "selection_mode": "specific", "chapters": "1", "profile_id": natural["id"], "use_reference": True},
        )
        monitor = client.get("/api/admin/translation/monitor?novel_id=demo")
        costs = client.get("/api/admin/translation/costs?novel_id=demo")
        retranslate = client.post("/api/translation/retranslation/preview", json={"novel_id": "demo", "mode": "low-quality"})
    prompt_json = prompt.json()
    prompt_text = prompt_json.get("prompt", "")
    passed = (
        unauthorized.status_code == 401
        and login.status_code == 200
        and profiles.status_code == 200
        and glossary.status_code == 200
        and quality.status_code == 200
        and detail.status_code == 200
        and detail.json()["reference"]["ok"] is True
        and review.status_code == 200
        and prompt.status_code == 200
        and prompt_json["privacy"]["provider_request_sent"] is False
        and "Translation profile: Natural English Novel." in prompt_text
        and "TermA => Name A" in prompt_text
        and "OPENAI_API_KEY" not in json.dumps(prompt_json)
        and monitor.status_code == 200
        and costs.status_code == 200
        and retranslate.status_code == 200
        and retranslate.json()["overwrite_existing_ai"] is False
    )
    return {
        "passed": passed,
        "unauthorized_status": unauthorized.status_code,
        "profile_count": len(profiles.json().get("profiles", [])),
        "prompt_sections": prompt_json.get("sections", []),
        "monitor_status": monitor.status_code,
        "cost_status": costs.status_code,
    }


def main() -> None:
    results = {
        "database_features": database_feature_test(),
        "api_features": api_feature_test(),
        "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "database_url_present": bool(os.getenv("DATABASE_URL")),
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    failures = [name for name, result in results.items() if isinstance(result, dict) and not result.get("passed")]
    if results["openai_key_present"] or results["database_url_present"]:
        failures.append("environment_isolation")
    if failures:
        raise SystemExit(f"Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
