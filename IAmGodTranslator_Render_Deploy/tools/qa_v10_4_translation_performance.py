from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
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


def temp_db(name: str, chapters: int = 12, settings: dict[str, Any] | None = None) -> tuple[Database, str]:
    path = Path(tempfile.gettempdir()) / f"gt-v10-4-{name}-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    db.save_novel_metadata("demo", {"id": "demo", "title": "Demo", "model": "gpt-4o-mini", "status": "active"})
    for chapter in range(1, chapters + 1):
        db.upsert_chapter(
            "demo",
            chapter,
            f"Chapter {chapter}",
            (f"Original {chapter} text. " * 120).strip(),
            (f"Reference {chapter} text. " * 60).strip() if chapter % 2 == 0 else None,
            None,
        )
    job = db.create_translation_job(
        "demo",
        list(range(1, chapters + 1)),
        {
            "model": "gpt-4o-mini",
            "retry_count": 2,
            "batch_size": chapters,
            "use_reference": True,
            "mock_provider_delay_seconds": 0.08,
            **(settings or {}),
        },
    )
    return db, str(job["id"])


def wait_for_job(db: Database, job_id: str, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = db.translation_job(job_id) or {}
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish")


def runner_benchmark(workers: int, chapters: int = 48, delay: float = 0.08) -> dict[str, Any]:
    db, job_id = temp_db(
        f"bench-{workers}",
        chapters=chapters,
        settings={"translation_mode": "advanced", "speed_preset": "maximum-safe", "concurrency": workers, "max_workers": workers, "mock_provider_delay_seconds": delay},
    )
    runner = app_main.TranslationRunner(db)
    started = time.perf_counter()
    runner.start(job_id, mock=True)
    job = wait_for_job(db, job_id)
    elapsed = time.perf_counter() - started
    completed = [item for item in job.get("items", []) if item.get("status") == "completed"]
    chapters_seen = [item["chapter_number"] for item in completed]
    return {
        "workers": workers,
        "seconds": round(elapsed, 3),
        "completed": len(completed),
        "failed": int(job.get("failed_items") or 0),
        "duplicate_work": len(chapters_seen) != len(set(chapters_seen)),
        "status": job.get("status"),
        "peak_overlap": peak_overlap(completed),
    }


def overlap_proof() -> dict[str, Any]:
    db, job_id = temp_db(
        "overlap",
        chapters=8,
        settings={"translation_mode": "advanced", "speed_preset": "fast", "concurrency": 4, "max_workers": 4, "mock_provider_delay_seconds": 0.22},
    )
    runner = app_main.TranslationRunner(db)
    runner.start(job_id, mock=True)
    job = wait_for_job(db, job_id)
    completed = [item for item in job.get("items", []) if item.get("status") == "completed"]
    timeline = [
        {
            "chapter": item["chapter_number"],
            "provider_start": item.get("provider_started_at"),
            "provider_end": item.get("provider_finished_at"),
            "provider_wait_seconds": item.get("provider_wait_seconds"),
            "claim_seconds": item.get("claim_duration_seconds"),
            "save_seconds": item.get("save_duration_seconds"),
        }
        for item in completed[:4]
    ]
    starts = [parse_time(item["provider_start"]) for item in timeline]
    ends = [parse_time(item["provider_end"]) for item in timeline]
    mathematical_overlap = max(starts) < min(ends)
    return {
        "passed": mathematical_overlap and peak_overlap(completed) >= 4,
        "peak_overlap": peak_overlap(completed),
        "mathematical_overlap": mathematical_overlap,
        "timeline": timeline,
    }


def peak_overlap(items: list[dict[str, Any]]) -> int:
    events: list[tuple[datetime, int]] = []
    for item in items:
        start = item.get("provider_started_at")
        end = item.get("provider_finished_at")
        if start and end:
            events.append((parse_time(start), 1))
            events.append((parse_time(end), -1))
    active = 0
    peak = 0
    for _, delta in sorted(events, key=lambda event: (event[0], -event[1])):
        active += delta
        peak = max(peak, active)
    return peak


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def prompt_breakdown_test() -> dict[str, Any]:
    glossary = "\n".join([f"Term{i}=Translation{i}" for i in range(140)])
    payload = app_main.build_prompt_payload("Term7 原文 " * 50, "Reference " * 25, {"glossary": glossary, "style_guide": "Direct literary English."})
    metrics = payload["metrics"]
    return {
        "passed": metrics["prompt_original_tokens"] > 0 and metrics["prompt_reference_tokens"] > 0 and metrics["prompt_instruction_tokens"] > 0,
        "metrics": metrics,
        "prompt_contains_reference": "Reference translation:" in payload["prompt"],
        "prompt_contains_original": "Chinese original:" in payload["prompt"],
    }


def diagnostics_api_test() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    app_main.database = Database(f"sqlite:///{Path(tempfile.gettempdir()) / f'gt-v10-4-api-{time.time_ns()}.db'}")
    app_main.translation_runner = app_main.TranslationRunner(app_main.database)
    with TestClient(app_main.app) as client:
        app_main.database.initialize()
        app_main.database.save_novel_metadata("demo", {"id": "demo", "title": "Demo", "model": "gpt-4o-mini"})
        app_main.database.upsert_chapter("demo", 1, "Chapter 1", "Original", None, None)
        unauthorized = client.get("/api/admin/translation/performance")
        login = client.post("/api/admin/login", json={"password": "qa-admin-password"})
        authorized = client.get("/api/admin/translation/performance")
        benchmark = client.post("/api/admin/translation/benchmark/estimate", json={"novel_id": "demo", "chapters": "1"})
    return {
        "passed": unauthorized.status_code == 401 and login.status_code == 200 and authorized.status_code == 200 and benchmark.status_code == 200 and benchmark.json().get("enabled") is False,
        "unauthorized_status": unauthorized.status_code,
        "authorized_status": authorized.status_code,
        "benchmark_enabled": benchmark.json().get("enabled"),
    }


def retry_classification_test() -> dict[str, Any]:
    class RateLimitError(Exception):
        status_code = 429

    class TimeoutErrorExample(Exception):
        pass

    rate = RateLimitError("rate limited")
    timeout = TimeoutErrorExample("timeout")
    return {
        "passed": app_main.retryable_provider_error(rate) and app_main.retryable_provider_error(timeout),
        "rate_backoff_seconds": app_main.provider_backoff_seconds(rate),
        "timeout_backoff_seconds": app_main.provider_backoff_seconds(timeout),
    }


def postgres_upsert_sql_test() -> dict[str, Any]:
    db = Database("postgresql://unit-test")
    captured: list[str] = []

    class CaptureConnection:
        def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
            captured.append(db._convert_sql(sql))

    db.record_translation_performance(CaptureConnection(), "gpt-4o-mini", "demo", 1.2, 100, 120, 40, 45, True)
    sql = "\n".join(captured)
    accumulated = [
        "sample_count",
        "success_count",
        "failure_count",
        "total_duration_seconds",
        "total_input_chars",
        "total_output_chars",
        "total_input_tokens",
        "total_output_tokens",
        "rate_limited_count",
        "timeout_count",
    ]
    qualified = all(f"{column} = target.{column} + EXCLUDED.{column}" in sql for column in accumulated)
    ambiguous = any(re.search(rf"{column}\\s*=\\s*{column}\\s*\\+", sql) for column in accumulated)
    return {
        "passed": qualified and not ambiguous and 'INSERT INTO "godtranslator_v10"."translation_performance" AS target' in sql,
        "qualified_columns": qualified,
        "ambiguous_unqualified_columns": ambiguous,
        "uses_target_alias": " AS target" in sql,
    }


def telemetry_failure_isolation_test() -> dict[str, Any]:
    db, job_id = temp_db("telemetry-failure", chapters=4, settings={"concurrency": 2, "max_workers": 2, "mock_provider_delay_seconds": 0.02})

    def broken_telemetry(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated telemetry failure")

    db.record_translation_performance = broken_telemetry  # type: ignore[method-assign]
    runner = app_main.TranslationRunner(db)
    runner.start(job_id, mock=True)
    job = wait_for_job(db, job_id)
    chapters = [db.chapter_text("demo", chapter, "ai") for chapter in range(1, 5)]
    completed = [item for item in job.get("items", []) if item.get("status") == "completed"]
    return {
        "passed": job.get("status") == "completed" and len(completed) == 4 and all(item.get("ok") and item.get("text") for item in chapters),
        "job_status": job.get("status"),
        "completed": len(completed),
        "chapter_ai_saved": [bool(item.get("text")) for item in chapters],
    }


def retry_slot_release_test() -> dict[str, Any]:
    previous_cap = os.environ.get("TRANSLATION_MAX_CONCURRENCY")
    os.environ["TRANSLATION_MAX_CONCURRENCY"] = "1"
    db, job_id = temp_db("retry-slot", chapters=2, settings={"translation_mode": "advanced", "speed_preset": "balanced", "concurrency": 2, "max_workers": 2, "retry_count": 1})
    original_fake = app_main.fake_translator_async
    failed_once = {"value": False}

    class RateLimitError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("rate limited")
            self.response = type("Response", (), {"headers": {"Retry-After": "2"}, "status_code": 429})()

    async def flaky_translator(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
        if "Original 1 text" in original and not failed_once["value"]:
            failed_once["value"] = True
            await app_main.asyncio.sleep(0.05)
            raise RateLimitError()
        return await original_fake(original, reference, {**settings, "mock_provider_delay_seconds": 0.05})

    app_main.fake_translator_async = flaky_translator  # type: ignore[assignment]
    try:
        runner = app_main.TranslationRunner(db)
        started = time.perf_counter()
        runner.start(job_id, mock=True)
        job = wait_for_job(db, job_id, timeout=10)
        elapsed = time.perf_counter() - started
    finally:
        app_main.fake_translator_async = original_fake  # type: ignore[assignment]
        if previous_cap is None:
            os.environ.pop("TRANSLATION_MAX_CONCURRENCY", None)
        else:
            os.environ["TRANSLATION_MAX_CONCURRENCY"] = previous_cap

    items = {int(item["chapter_number"]): item for item in job.get("items", [])}
    chapter_1 = items.get(1, {})
    chapter_2 = items.get(2, {})
    ch1_finished = parse_time(chapter_1["finished_at"]) if chapter_1.get("finished_at") else None
    ch2_finished = parse_time(chapter_2["finished_at"]) if chapter_2.get("finished_at") else None
    return {
        "passed": job.get("status") == "completed" and failed_once["value"] and ch1_finished and ch2_finished and ch2_finished < ch1_finished and elapsed < 4.0,
        "job_status": job.get("status"),
        "elapsed_seconds": round(elapsed, 3),
        "chapter_1_attempts": chapter_1.get("attempts"),
        "chapter_1_retry_delay": chapter_1.get("retry_delay_seconds"),
        "chapter_2_finished_before_chapter_1": bool(ch1_finished and ch2_finished and ch2_finished < ch1_finished),
    }


def reference_breakdown_test() -> dict[str, Any]:
    with_ref = app_main.build_prompt_payload("原文" * 100, "Reference " * 100, {})
    without_ref = app_main.build_prompt_payload("原文" * 100, None, {})
    return {
        "passed": with_ref["metrics"]["prompt_reference_tokens"] > without_ref["metrics"]["prompt_reference_tokens"] == 0,
        "with_reference_tokens": with_ref["metrics"]["prompt_reference_tokens"],
        "without_reference_tokens": without_ref["metrics"]["prompt_reference_tokens"],
    }


def main() -> None:
    overlap = overlap_proof()
    benchmarks = [runner_benchmark(1), runner_benchmark(4), runner_benchmark(8)]
    results = {
        "overlap_proof": overlap,
        "benchmarks": benchmarks,
        "prompt_breakdown": prompt_breakdown_test(),
        "reference_breakdown": reference_breakdown_test(),
        "diagnostics_api": diagnostics_api_test(),
        "retry_classification": retry_classification_test(),
        "postgres_upsert_sql": postgres_upsert_sql_test(),
        "telemetry_failure_isolation": telemetry_failure_isolation_test(),
        "retry_slot_release": retry_slot_release_test(),
        "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "database_url_present": bool(os.getenv("DATABASE_URL")),
    }
    print(json.dumps(results, indent=2))
    failures: list[str] = []
    if not overlap.get("passed"):
        failures.append("overlap_proof")
    if any(item["status"] != "completed" or item["duplicate_work"] or item["failed"] for item in benchmarks):
        failures.append("benchmarks")
    for key in (
        "prompt_breakdown",
        "reference_breakdown",
        "diagnostics_api",
        "retry_classification",
        "postgres_upsert_sql",
        "telemetry_failure_isolation",
        "retry_slot_release",
    ):
        if not results[key].get("passed"):
            failures.append(key)
    if results["openai_key_present"] or results["database_url_present"]:
        failures.append("environment_isolation")
    if failures:
        raise SystemExit(f"Failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
