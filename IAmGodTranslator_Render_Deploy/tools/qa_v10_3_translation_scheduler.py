from __future__ import annotations

import tempfile
import threading
import time
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Database


def build_db(name: str, chapters: int = 8, settings: dict[str, Any] | None = None) -> tuple[Database, str]:
    path = Path(tempfile.gettempdir()) / f"gt-v10-3-{name}-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    db.save_novel_metadata("demo", {"id": "demo", "title": "Demo", "model": "gpt-4o-mini", "status": "active"})
    for chapter in range(1, chapters + 1):
        db.upsert_chapter("demo", chapter, f"Chapter {chapter}", f"Original {chapter}", None, None)
    job = db.create_translation_job(
        "demo",
        list(range(1, chapters + 1)),
        {"model": "gpt-4o-mini", "retry_count": 2, "batch_size": chapters, **(settings or {})},
    )
    return db, job["id"]


def finish_claim(db: Database, claim: dict[str, Any], worker_id: str, latency: float = 0.0) -> None:
    if latency:
        time.sleep(latency)
    db.finish_translation_item(
        claim["job_id"],
        int(claim["item_id"]),
        worker_id,
        result={"text": f"Translated {claim['chapter_number']}", "input_tokens": 5, "output_tokens": 8, "actual_cost": 0.001},
    )


def worker_loop(db: Database, job_id: str, worker_id: str, latency: float = 0.01) -> None:
    while True:
        claim = db.claim_translation_item(job_id, worker_id, lease_seconds=30)
        if claim.get("status") == "race_lost":
            time.sleep(0.001)
            continue
        if claim.get("status") != "claimed":
            return
        finish_claim(db, claim, worker_id, latency)


def benchmark(workers: int, chapters: int = 100, latency: float = 0.08) -> dict[str, Any]:
    db, job_id = build_db(f"bench-{workers}", chapters=chapters, settings={"concurrency": workers, "max_workers": workers})
    started = time.perf_counter()
    threads = [threading.Thread(target=worker_loop, args=(db, job_id, f"worker-{i}", latency)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started
    job = db.translation_job(job_id) or {}
    translated = [item for item in job.get("items", []) if item.get("status") == "completed"]
    chapters_seen = [item["chapter_number"] for item in translated]
    return {
        "workers": workers,
        "seconds": round(elapsed, 3),
        "completed": len(translated),
        "failed": int(job.get("failed_items") or 0),
        "duplicate_work": len(chapters_seen) != len(set(chapters_seen)),
        "status": job.get("status"),
    }


def duplicate_claim_test() -> dict[str, Any]:
    db, job_id = build_db("duplicate", chapters=1)
    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []

    def contender(worker_id: str) -> None:
        barrier.wait()
        results.append(db.claim_translation_item(job_id, worker_id, lease_seconds=30))

    threads = [threading.Thread(target=contender, args=(f"worker-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    claimed = [item for item in results if item.get("status") == "claimed"]
    return {"claimed_count": len(claimed), "unique_item_count": len({item.get("item_id") for item in claimed}), "passed": len(claimed) == 1}


def lease_recovery_test() -> dict[str, Any]:
    db, job_id = build_db("lease", chapters=1)
    first = db.claim_translation_item(job_id, "worker-a", lease_seconds=1)
    time.sleep(1.15)
    second = db.claim_translation_item(job_id, "worker-b", lease_seconds=30)
    heartbeat_db, heartbeat_job = build_db("heartbeat", chapters=1)
    held = heartbeat_db.claim_translation_item(heartbeat_job, "worker-a", lease_seconds=2)
    heartbeat_db.heartbeat_translation_item(heartbeat_job, int(held["item_id"]), "worker-a", lease_seconds=5)
    blocked = heartbeat_db.claim_translation_item(heartbeat_job, "worker-b", lease_seconds=2)
    return {
        "expired_claim_recovered": first.get("status") == "claimed" and second.get("status") == "claimed",
        "heartbeat_prevented_reclaim": blocked.get("status") != "claimed",
        "passed": second.get("status") == "claimed" and blocked.get("status") != "claimed",
    }


def pause_resume_cancel_test() -> dict[str, Any]:
    db, job_id = build_db("controls", chapters=3)
    paused = db.set_job_status(job_id, "paused")
    paused_claim = db.claim_translation_item(job_id, "worker-a")
    resumed = db.set_job_status(job_id, "queued")
    resumed_claim = db.claim_translation_item(job_id, "worker-a")
    cancelled = db.set_job_status(job_id, "cancelled")
    cancelled_claim = db.claim_translation_item(job_id, "worker-b")
    return {
        "pause_blocks_claim": paused.get("status") == "paused" and paused_claim.get("status") == "paused",
        "resume_claims": resumed.get("status") == "queued" and resumed_claim.get("status") == "claimed",
        "cancel_blocks_claim": cancelled.get("status") == "cancelled" and cancelled_claim.get("status") == "cancelled",
        "passed": paused_claim.get("status") == "paused" and resumed_claim.get("status") == "claimed" and cancelled_claim.get("status") == "cancelled",
    }


def budget_stop_test() -> dict[str, Any]:
    db, job_id = build_db("budget", chapters=2, settings={"max_total_budget": 0.0, "stop_on_budget": True})
    claim = db.claim_translation_item(job_id, "worker-a")
    job = db.translation_job(job_id) or {}
    return {"claim_status": claim.get("status"), "job_status": job.get("status"), "passed": claim.get("status") == "paused" and job.get("error") == "budget_reached"}


def main() -> None:
    results = {
        "duplicate_claim": duplicate_claim_test(),
        "lease_recovery": lease_recovery_test(),
        "pause_resume_cancel": pause_resume_cancel_test(),
        "budget_stop": budget_stop_test(),
        "benchmarks": [benchmark(1), benchmark(4), benchmark(8)],
    }
    print(results)
    failures = [
        key
        for key, value in results.items()
        if key != "benchmarks" and isinstance(value, dict) and not value.get("passed")
    ]
    if any(item["completed"] != 100 or item["duplicate_work"] for item in results["benchmarks"]):
        failures.append("benchmarks")
    if failures:
        raise SystemExit(f"Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
