from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

try:
    import fastapi  # noqa: F401
except ModuleNotFoundError:
    from qa_backup_manifest_hotfix import install_fastapi_stubs

    install_fastapi_stubs()

from app.db import Database
from app import main as app_main


def build_db(name: str, chapters: int = 550) -> Database:
    path = Path(tempfile.gettempdir()) / f"gt-v10-6-selector-{name}-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    db.save_novel_metadata("demo", {"id": "demo", "title": "Selector Demo", "model": "gpt-4o-mini", "status": "active"})
    missing_original = {10, 20}
    already_english = set(range(101, 126))
    for chapter in range(1, chapters + 1):
        original = None if chapter in missing_original else (f"Original chapter {chapter}. " * 80).strip()
        english = (f"Existing English chapter {chapter}. " * 50).strip() if chapter in already_english else None
        db.upsert_chapter("demo", chapter, f"Chapter {chapter}", original, None, english)
    return db


def create_job_from_payload(db: Database, payload: dict[str, Any]) -> dict[str, Any]:
    app_main.database = db
    selection = app_main.translation_selection("demo", payload)
    job = db.create_translation_job("demo", selection["chapters"], {**payload, "_selection_diagnostics": selection["diagnostics"]})
    return {"selection": selection, "job": job}


def item_chapters(job: dict[str, Any]) -> list[int]:
    return [int(item["chapter_number"]) for item in job.get("items", [])]


def persisted_item_chapters(db: Database, job_id: str) -> list[int]:
    with db.connect() as conn:
        rows = conn.execute(
            f"SELECT chapter_number FROM {db.table('translation_job_items')} WHERE job_id = ? ORDER BY chapter_number",
            (job_id,),
        ).fetchall()
    return [int(row["chapter_number"]) for row in rows]


def assert_count(label: str, value: int, expected: int) -> None:
    if value != expected:
        raise AssertionError(f"{label}: expected {expected}, got {value}")


def job_creation_matrix() -> dict[str, Any]:
    db = build_db("matrix")
    results: dict[str, Any] = {}
    for count in (25, 50, 100, 200, 500):
        created = create_job_from_payload(
            db,
            {"selection_mode": "next-untranslated", "next_count": count, "translation_mode": "simple", "model": "gpt-4o-mini"},
        )
        chapters = item_chapters(created["job"])
        assert_count(f"next {count}", len(chapters), count)
        if len(chapters) != len(set(chapters)):
            raise AssertionError(f"next {count}: duplicate items")
        results[f"next_{count}"] = len(chapters)

    all_created = create_job_from_payload(
        db,
        {"selection_mode": "all-untranslated", "all_untranslated": True, "translation_mode": "simple", "model": "gpt-4o-mini"},
    )
    all_chapters = persisted_item_chapters(db, all_created["job"]["id"])
    assert_count("all untranslated", len(all_chapters), 523)
    if len(all_chapters) != len(set(all_chapters)):
        raise AssertionError("all untranslated: duplicate items")
    results["all_untranslated"] = len(all_chapters)
    results["all_missing_original"] = all_created["selection"]["diagnostics"]["missing_original_count"]
    results["all_already_english"] = all_created["selection"]["diagnostics"]["already_translated_count"]

    custom = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 37, "next_count_mode": "custom", "translation_mode": "simple", "model": "gpt-4o-mini"},
    )
    assert_count("custom count", len(item_chapters(custom["job"])), 37)
    results["custom_37"] = len(item_chapters(custom["job"]))

    specific = create_job_from_payload(
        db,
        {
            "selection_mode": "specific",
            "chapters": "1-50,75,100-125,1,0,bad,999",
            "translation_mode": "simple",
            "model": "gpt-4o-mini",
        },
    )
    specific_estimate = db.estimate_translation(
        "demo",
        specific["selection"]["chapters"],
        {"model": "gpt-4o-mini", "_selection_diagnostics": specific["selection"]["diagnostics"]},
    )
    chapters = item_chapters(specific["job"])
    assert_count("specific eligible", len(chapters), 50)
    if 10 in chapters or 20 in chapters:
        raise AssertionError("specific: missing Original chapters were not skipped")
    if any(101 <= chapter <= 125 for chapter in chapters):
        raise AssertionError("specific: existing English chapters were not skipped")
    results["specific_eligible"] = len(chapters)
    results["specific_duplicates_removed"] = specific_estimate["duplicates_removed"]
    results["specific_invalid_tokens"] = specific_estimate["invalid_tokens"]
    results["specific_invalid_chapters"] = specific_estimate["invalid_chapter_numbers"]
    return results


def controls_and_budget() -> dict[str, Any]:
    db = build_db("controls", chapters=40)
    created = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 25, "translation_mode": "simple", "model": "gpt-4o-mini"},
    )
    job_id = created["job"]["id"]
    paused = db.set_job_status(job_id, "paused")
    paused_claim = db.claim_translation_item(job_id, "worker-a")
    resumed = db.set_job_status(job_id, "queued")
    resumed_claim = db.claim_translation_item(job_id, "worker-a")
    cancelled = db.set_job_status(job_id, "cancelled")
    cancelled_claim = db.claim_translation_item(job_id, "worker-b")

    budget = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 5, "translation_mode": "simple", "model": "gpt-4o-mini", "max_total_budget": 0.0, "stop_on_budget": True},
    )
    budget_claim = db.claim_translation_item(budget["job"]["id"], "worker-budget")

    interrupted = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 5, "translation_mode": "simple", "model": "gpt-4o-mini"},
    )
    db.set_job_status(interrupted["job"]["id"], "running")
    db.mark_interrupted_jobs()
    recovered = db.translation_job(interrupted["job"]["id"]) or {}
    return {
        "pause_blocks_claim": paused.get("status") == "paused" and paused_claim.get("status") == "paused",
        "resume_claims": resumed.get("status") == "queued" and resumed_claim.get("status") == "claimed",
        "cancel_blocks_claim": cancelled.get("status") == "cancelled" and cancelled_claim.get("status") == "cancelled",
        "budget_stop": budget_claim.get("status") == "paused",
        "restart_recovery": recovered.get("status") == "queued",
    }


def bounded_concurrency() -> dict[str, Any]:
    db = build_db("concurrency", chapters=140)
    created = create_job_from_payload(
        db,
        {"selection_mode": "next-untranslated", "next_count": 100, "translation_mode": "advanced", "concurrency": 4, "max_workers": 4, "model": "gpt-4o-mini"},
    )
    job_id = created["job"]["id"]
    completed: list[int] = []
    lock = threading.Lock()

    def worker(worker_id: str) -> None:
        while True:
            claim = db.claim_translation_item(job_id, worker_id, lease_seconds=30)
            if claim.get("status") == "race_lost":
                continue
            if claim.get("status") != "claimed":
                return
            db.finish_translation_item(
                job_id,
                int(claim["item_id"]),
                worker_id,
                result={"text": f"Translated {claim['chapter_number']}", "input_tokens": 10, "output_tokens": 12, "actual_cost": 0.0001},
            )
            with lock:
                completed.append(int(claim["chapter_number"]))

    threads = [threading.Thread(target=worker, args=(f"worker-{index}",)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    job = db.translation_job(job_id) or {}
    return {
        "completed": len(completed),
        "duplicate_work": len(completed) != len(set(completed)),
        "status": job.get("status"),
        "bounded_workers": 4,
    }


def main() -> None:
    results = {
        "job_creation": job_creation_matrix(),
        "controls": controls_and_budget(),
        "concurrency": bounded_concurrency(),
        "no_openai_key": not bool(os.getenv("OPENAI_API_KEY")),
        "production_database_url": bool(os.getenv("DATABASE_URL")),
    }
    failures = []
    if not all(results["controls"].values()):
        failures.append("controls")
    if results["concurrency"]["completed"] != 100 or results["concurrency"]["duplicate_work"] or results["concurrency"]["status"] != "completed":
        failures.append("concurrency")
    if not results["no_openai_key"] or results["production_database_url"]:
        failures.append("environment")
    print(results)
    if failures:
        raise SystemExit(f"Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
