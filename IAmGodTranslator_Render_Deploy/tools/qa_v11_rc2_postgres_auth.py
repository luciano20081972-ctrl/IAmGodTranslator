from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import psycopg
import requests
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import Database, PLATFORM_BACKUP_TABLE_NAMES  # noqa: E402


DB_URL = os.environ.get("DATABASE_URL") or ""
ADMIN_PASSWORD = "rc2-admin-password"
ADMIN_SESSION_SECRET = "rc2-admin-session-secret"
TEST_AUTH_SECRET = "rc2-test-auth-secret-never-production"
TEST_USERS = {
    "normal": ("rc2-user", "normal.rc2@example.invalid", "user"),
    "translator": ("rc2-translator", "translator.rc2@example.invalid", "translator"),
    "admin": ("rc2-admin", "admin.rc2@example.invalid", "admin"),
    "removed": ("rc2-removed", "removed.rc2@example.invalid", "removed"),
}


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def quote_ident(value: str) -> str:
    require("safe identifier", value.replace("_", "").isalnum())
    return '"' + value.replace('"', '""') + '"'


def assert_safe_database_url() -> None:
    parsed = urlparse(DB_URL)
    require("DATABASE_URL is required", bool(DB_URL))
    require("DATABASE_URL must be PostgreSQL", parsed.scheme in {"postgres", "postgresql"})
    host = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "::1", "postgres"}
    if host not in local_hosts and os.getenv("GT_RC2_ALLOW_REMOTE_POSTGRES") != "true":
        raise AssertionError(f"Refusing non-local PostgreSQL host for RC QA: {host}")


def pg_query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        return list(conn.execute(sql, params).fetchall())


def pg_execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        conn.execute(sql, params)
        conn.commit()


def drop_schema(schema: str) -> None:
    if schema.startswith("gt_rc2_"):
        pg_execute(f"DROP SCHEMA IF EXISTS {quote_ident(schema)} CASCADE")


def set_schema(schema: str) -> None:
    os.environ["DATABASE_URL"] = DB_URL
    os.environ["DB_SCHEMA"] = schema
    os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
    os.environ["ADMIN_SESSION_SECRET"] = ADMIN_SESSION_SECRET
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["GT_TEST_AUTH_ENABLED"] = "true"
    os.environ["GT_TEST_AUTH_SECRET"] = TEST_AUTH_SECRET
    os.environ["GT_TEST_AUTH_ALLOWED_USER_IDS"] = ",".join(user_id for user_id, _, _ in TEST_USERS.values())
    os.environ["TRANSLATION_AUTOSTART"] = "false"
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_ANON_KEY", None)
    os.environ.pop("SUPABASE_PUBLISHABLE_KEY", None)
    os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    os.environ.pop("SUPABASE_BACKUP_SERVICE_KEY", None)


def db_for(schema: str) -> Database:
    set_schema(schema)
    return Database(DB_URL)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def run_app(schema: str, app_env: str = "ci") -> Any:
    port = free_port()
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": DB_URL,
            "DB_SCHEMA": schema,
            "ADMIN_PASSWORD": ADMIN_PASSWORD,
            "ADMIN_SESSION_SECRET": ADMIN_SESSION_SECRET,
            "AUTH_ENABLED": "true",
            "APP_ENV": app_env,
            "GT_TEST_AUTH_ENABLED": "true",
            "GT_TEST_AUTH_SECRET": TEST_AUTH_SECRET,
            "GT_TEST_AUTH_ALLOWED_USER_IDS": ",".join(user_id for user_id, _, _ in TEST_USERS.values()),
            "TRANSLATION_AUTOSTART": "false",
        }
    )
    for key in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_BACKUP_SERVICE_KEY"):
        env.pop(key, None)
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError(f"FastAPI exited early with code {process.returncode}")
            try:
                response = requests.get(f"{base_url}/api/health", timeout=1)
                if response.status_code == 200 and response.json().get("database") == "reachable":
                    break
            except Exception:
                pass
            time.sleep(0.25)
        else:
            raise TimeoutError("FastAPI did not become healthy")
        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def test_token(user_id: str, email: str, *, exp_delta: int = 3600, claimed_role: str | None = None, tamper: bool = False) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "name": email.split("@", 1)[0],
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_delta,
    }
    if claimed_role:
        payload["role"] = claimed_role
    encoded = b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(TEST_AUTH_SECRET.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()
    if tamper:
        signature = "0" + signature[1:]
    return f"gtqa1.{encoded}.{signature}"


def auth_headers(role: str) -> dict[str, str]:
    user_id, email, _ = TEST_USERS[role]
    return {"Authorization": f"Bearer {test_token(user_id, email)}"}


def request_json(method: str, base_url: str, path: str, *, headers: dict[str, str] | None = None, json_payload: Any = None, expected: int | set[int] = 200) -> dict[str, Any]:
    response = requests.request(method, f"{base_url}{path}", headers=headers or {}, json=json_payload, timeout=20)
    expected_set = {expected} if isinstance(expected, int) else expected
    require(f"{method} {path} status {expected_set}, got {response.status_code}", response.status_code in expected_set)
    content_type = response.headers.get("content-type", "")
    require(f"{method} {path} json response", content_type.startswith("application/json"))
    lower = response.text.lower()
    require(f"{method} {path} no traceback", "traceback" not in lower and "<html" not in lower)
    return response.json()


def schema_signature(schema: str) -> dict[str, Any]:
    tables = pg_query(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (schema,),
    )
    indexes = pg_query(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s
        ORDER BY indexname, indexdef
        """,
        (schema,),
    )
    constraints = pg_query(
        """
        SELECT c.conname, c.contype, t.relname AS table_name
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE n.nspname = %s
        ORDER BY t.relname, c.conname
        """,
        (schema,),
    )
    return {
        "tables": [row["table_name"] for row in tables],
        "indexes": indexes,
        "constraints": constraints,
    }


def verify_schema(schema: str) -> dict[str, Any]:
    signature = schema_signature(schema)
    tables = set(signature["tables"])
    missing = sorted(set(PLATFORM_BACKUP_TABLE_NAMES) - tables)
    require("required PostgreSQL tables exist", not missing)
    columns = pg_query(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
        """,
        (schema,),
    )
    column_map: dict[str, set[str]] = {}
    for row in columns:
        column_map.setdefault(row["table_name"], set()).add(row["column_name"])
    required_columns = {
        "novels": {"id", "title", "metadata_json", "is_archived"},
        "chapters": {"novel_id", "chapter_number", "original_text", "reference_text", "ai_text"},
        "chapter_editions": {"novel_id", "chapter_number", "edition_key", "text", "is_default"},
        "translation_jobs": {"id", "novel_id", "status", "completed_items", "failed_items"},
        "translation_job_items": {"job_id", "chapter_number", "status", "lease_expires_at"},
        "user_profiles": {"user_id", "email", "role"},
        "bookmarks": {"user_id", "novel_id", "chapter_number"},
        "backup_jobs": {"id", "status", "total_tables", "completed_tables", "processed_rows"},
    }
    for table, names in required_columns.items():
        require(f"{table} required columns", names.issubset(column_map.get(table, set())))
    duplicate_indexes = pg_query(
        """
        SELECT indexdef, COUNT(*) AS total
        FROM pg_indexes
        WHERE schemaname = %s
        GROUP BY indexdef
        HAVING COUNT(*) > 1
        """,
        (schema,),
    )
    require("no duplicate PostgreSQL indexes", not duplicate_indexes)
    return {
        "table_count": len(tables),
        "index_count": len(signature["indexes"]),
        "constraint_count": len(signature["constraints"]),
    }


def table_rows(schema: str, table: str) -> list[dict[str, Any]]:
    with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
        rows = list(conn.execute(f"SELECT * FROM {quote_ident(schema)}.{quote_ident(table)}").fetchall())
    return [dict(row) for row in rows]


def normalize_for_checksum(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_for_checksum(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_for_checksum(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def checksum_rows(rows: list[dict[str, Any]]) -> str:
    normalized_rows = [normalize_for_checksum(row) for row in rows]
    normalized_rows.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    normalized = json.dumps(normalized_rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def counts_and_checksums(schema: str) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for table in PLATFORM_BACKUP_TABLE_NAMES:
        rows = table_rows(schema, table)
        payload[table] = {"rows": len(rows), "sha256": checksum_rows(rows)}
    return payload


def count_checksum_diffs(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> dict[str, Any]:
    tables = sorted(set(before) | set(after))
    row_count_diffs = {
        table: {"before": before.get(table, {}).get("rows"), "after": after.get(table, {}).get("rows")}
        for table in tables
        if before.get(table, {}).get("rows") != after.get(table, {}).get("rows")
    }
    checksum_diffs = [
        table
        for table in tables
        if before.get(table, {}).get("sha256") != after.get(table, {}).get("sha256")
    ]
    return {"row_count_diffs": row_count_diffs, "checksum_diffs": checksum_diffs}


def seed_users(db: Database) -> None:
    for _, (user_id, email, role) in TEST_USERS.items():
        db.ensure_user_profile(user_id, email, role, f"{role.title()} RC2", None)
    db.save_user_preferences(
        TEST_USERS["normal"][0],
        {
            "theme": "dark",
            "collections": [
                {"id": "favorites", "name": "Favorites", "novel_ids": ["partial-novel", "partial-novel", "full-novel"]},
            ],
        },
    )


def seed_fixture(schema: str, *, include_edge_running: bool = False) -> dict[str, Any]:
    db = db_for(schema)
    db.initialize()
    db.save_novel_metadata("empty-novel", {"title": "Empty Novel", "metadata": {}})
    db.save_novel_metadata("original-only", {"title": "Original Only", "author": "RC2"})
    for chapter in range(1, 4):
        db.upsert_chapter("original-only", chapter, f"Chapter {chapter}", f"Original only {chapter}", None, None)
    db.save_novel_metadata("english-only", {"title": "English Only", "author": "RC2"})
    db.upsert_chapter("english-only", 1, "Chapter 1", None, None, "English without Original")
    db.save_novel_metadata("partial-novel", {"title": "Partial Novel", "author": "RC2", "reference_source_url": "https://example.invalid/reference"})
    for chapter in range(1, 6):
        db.upsert_chapter(
            "partial-novel",
            chapter,
            f"Chapter {chapter}",
            f"Original partial {chapter}",
            f"Reference partial {chapter}" if chapter <= 3 else None,
            f"English partial {chapter}" if chapter <= 2 else None,
            ai_model="fixture" if chapter <= 2 else None,
        )
    db.save_novel_metadata("full-novel", {"title": "Full Novel", "author": "RC2"})
    for chapter in range(1, 4):
        db.upsert_chapter("full-novel", chapter, f"Chapter {chapter}", f"Original full {chapter}", f"Reference full {chapter}", f"English full {chapter}", ai_model="fixture")
    db.save_novel_metadata("gap-novel", {"title": "Gap Novel", "metadata": {"expected_chapter_start": 1, "expected_chapter_end": 8}})
    for chapter in (1, 3, 7):
        db.upsert_chapter("gap-novel", chapter, f"Chapter {chapter}", f"Gap original {chapter}", None, None)
    db.apply_content_import_payload(
        {
            "novel_id": "full-novel",
            "items": [
                {"chapter_number": 1, "content_type": "english", "edition_type": "Official", "text": "Official English full 1"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "AI", "text": "AI English full 1"},
                {"chapter_number": 2, "content_type": "reference", "text": "Imported reference full 2"},
            ],
            "options": {"overwrite_existing": True},
        }
    )
    seed_users(db)
    normal_id = TEST_USERS["normal"][0]
    db.save_reading_progress(normal_id, "partial-novel", 2, "english", 44.5)
    db.save_bookmark(normal_id, "partial-novel", 2, "Keep reading here")
    db.set_favorite(normal_id, "full-novel", True)
    completed = db.create_translation_job("partial-novel", [3], {"model": "gpt-4o-mini", "retry_count": 0})
    claim = db.claim_translation_item(str(completed["id"]), "seed-complete")
    db.finish_translation_item(str(completed["id"]), int(claim["item_id"]), "seed-complete", result={"text": "Completed translation", "input_tokens": 10, "output_tokens": 12, "actual_cost": 0.0001})
    failed = db.create_translation_job("partial-novel", [4], {"model": "gpt-4o-mini", "retry_count": 0})
    claim = db.claim_translation_item(str(failed["id"]), "seed-fail")
    db.finish_translation_item(str(failed["id"]), int(claim["item_id"]), "seed-fail", error="seed provider failure")
    cancelled = db.create_translation_job("partial-novel", [5], {"model": "gpt-4o-mini", "retry_count": 0})
    db.set_job_status(str(cancelled["id"]), "cancelled")
    if include_edge_running:
        running = db.create_translation_job("original-only", [1, 2, 3], {"model": "gpt-4o-mini", "retry_count": 1})
        db.set_job_status(str(running["id"]), "running")
    candidate = SimpleNamespace(
        chapter_number=4,
        filename="Chapter 4.txt",
        sha256=hashlib.sha256(b"Recovered reference").hexdigest(),
        character_count=len("Recovered reference"),
        text="Recovered reference",
        title="Chapter 4",
        source_url="https://example.invalid/chapter-4",
    )
    db.create_import_job("partial-novel", "reference", {"ok": True, "target_mode": "reference"}, [candidate])
    db.apply_content_import_payload(
        {
            "novel": {"title": "Imported RC2 Novel"},
            "items": [{"chapter_number": 1, "content_type": "original", "text": "Imported original one"}],
            "options": {"add_missing": True, "skip_existing": True},
        }
    )
    db.create_backup_job(destination="local", safe_mode=True)
    db.record_audit_event("rc2_seed", actor_role="admin", target_type="fixture", target_id=schema, summary="RC2 fixture seeded", metadata={"safe": True})
    return {
        "partial_original": db.chapter_text("partial-novel", 1, "original")["text"],
        "partial_reference": db.chapter_text("partial-novel", 1, "reference")["text"],
        "full_english": db.chapter_text("full-novel", 1, "english")["text"],
        "preferences": db.user_preferences(normal_id),
    }


def scenario_empty(schema: str) -> dict[str, Any]:
    drop_schema(schema)
    db = db_for(schema)
    db.initialize()
    first = verify_schema(schema)
    before = schema_signature(schema)
    with run_app(schema) as base_url:
        health = request_json("GET", base_url, "/api/health")
        require("empty startup health", health.get("database") == "reachable")
    db.initialize()
    after = schema_signature(schema)
    require("empty migration idempotence", before == after)
    with run_app(schema) as base_url:
        health = request_json("GET", base_url, "/api/health")
        require("empty restart health", health.get("ok") is True)
    return {"startup": "passed", "schema": first, "idempotent": True, "restart": "passed"}


def scenario_v10_fixture(schema: str) -> dict[str, Any]:
    drop_schema(schema)
    seed_values = seed_fixture(schema, include_edge_running=False)
    before_counts = counts_and_checksums(schema)
    before_signature = schema_signature(schema)
    db = db_for(schema)
    db.initialize()
    with run_app(schema) as base_url:
        request_json("GET", base_url, "/api/health")
        request_json("GET", base_url, "/api/novels/full-novel")
        text = request_json("GET", base_url, "/api/novels/full-novel/chapters/1/english")["text"]
        require("existing English accessible", text == seed_values["full_english"])
    after_counts = counts_and_checksums(schema)
    after_signature = schema_signature(schema)
    preservation_diffs = count_checksum_diffs(before_counts, after_counts)
    require(f"v10 row counts preserved: {preservation_diffs['row_count_diffs']}", not preservation_diffs["row_count_diffs"])
    require(f"v10 row checksums preserved: {preservation_diffs['checksum_diffs']}", not preservation_diffs["checksum_diffs"])
    require("v10 no duplicate schema objects", before_signature == after_signature)
    require("preferences preserved", db.user_preferences(TEST_USERS["normal"][0]) == seed_values["preferences"])
    require("original text preserved", db.chapter_text("partial-novel", 1, "original")["text"] == seed_values["partial_original"])
    require("reference text preserved", db.chapter_text("partial-novel", 1, "reference")["text"] == seed_values["partial_reference"])
    return {
        "preserved": True,
        "tables": len(before_counts),
        "row_counts": {name: before_counts[name]["rows"] for name in sorted(before_counts)},
        "checksum_diffs": [],
    }


def scenario_edge(schema: str) -> dict[str, Any]:
    drop_schema(schema)
    seed_fixture(schema, include_edge_running=True)
    db = db_for(schema)
    with run_app(schema) as base_url:
        novels = request_json("GET", base_url, "/api/novels")["novels"]
        states = {novel["id"]: novel.get("chapter_inventory_state") for novel in novels}
        require("zero-row novel state", states.get("empty-novel") == "empty_no_expected_range")
        library = request_json("GET", base_url, "/api/novels/gap-novel/library")
        require("gap novel library accessible", library["counts"]["total_chapter_rows"] == 3)
        request_json("GET", base_url, "/api/novels/original-only/chapters/1/original")
        request_json("GET", base_url, "/api/novels/english-only/chapters/1/english")
    interrupted = [job for job in db.translation_jobs(limit=50) if job.get("error") == "interrupted_after_restart"]
    require("running jobs recovered on startup", bool(interrupted))
    return {"edge_api": "passed", "interrupted_jobs_recovered": len(interrupted)}


def postgres_concurrency(schema: str) -> dict[str, Any]:
    db = db_for(schema)
    job = db.create_translation_job("original-only", [1, 2, 3], {"model": "gpt-4o-mini", "retry_count": 0, "concurrency": 2})
    job_id = str(job["id"])
    completed: list[int] = []
    lock = threading.Lock()

    def worker(worker_id: str) -> None:
        local_db = db_for(schema)
        while True:
            claim = local_db.claim_translation_item(job_id, worker_id, lease_seconds=30)
            if claim.get("status") == "race_lost":
                continue
            if claim.get("status") != "claimed":
                return
            local_db.finish_translation_item(
                job_id,
                int(claim["item_id"]),
                worker_id,
                result={"text": f"Translated {claim['chapter_number']}", "input_tokens": 1, "output_tokens": 1, "actual_cost": 0.0},
            )
            with lock:
                completed.append(int(claim["chapter_number"]))

    threads = [threading.Thread(target=worker, args=(f"pg-worker-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    require("PostgreSQL worker claims no duplicates", sorted(completed) == [1, 2, 3])
    require("PostgreSQL job completed", (db.translation_job(job_id) or {}).get("status") == "completed")

    import_errors: list[str] = []

    def import_worker(text: str) -> None:
        try:
            local_db = db_for(schema)
            local_db.apply_content_import_payload(
                {
                    "novel_id": "concurrent-import",
                    "items": [{"chapter_number": 1, "content_type": "original", "text": text}],
                    "options": {"add_missing": True, "skip_existing": True, "overwrite_existing": False},
                }
            )
        except Exception as exc:
            with lock:
                import_errors.append(type(exc).__name__)

    db.save_novel_metadata("concurrent-import", {"title": "Concurrent Import"})
    imports = [threading.Thread(target=import_worker, args=(f"Concurrent original {index}",)) for index in range(2)]
    for thread in imports:
        thread.start()
    for thread in imports:
        thread.join()
    require(f"concurrent imports no thread errors: {import_errors}", not import_errors)
    with db.connect() as conn:
        chapter_count = conn.execute(f"SELECT COUNT(*) AS total FROM {db.table('chapters')} WHERE novel_id = ? AND chapter_number = 1", ("concurrent-import",)).fetchone()["total"]
    require("concurrent imports kept one chapter row", int(chapter_count) == 1)

    normal_id = TEST_USERS["normal"][0]
    bookmark_threads = [threading.Thread(target=lambda note=note: db_for(schema).save_bookmark(normal_id, "full-novel", 1, note)) for note in ("a", "b")]
    for thread in bookmark_threads:
        thread.start()
    for thread in bookmark_threads:
        thread.join()
    with db.connect() as conn:
        bookmark_count = conn.execute(f"SELECT COUNT(*) AS total FROM {db.table('bookmarks')} WHERE user_id = ? AND novel_id = ? AND chapter_number = ?", (normal_id, "full-novel", 1)).fetchone()["total"]
    require("duplicate bookmark creation deduped", int(bookmark_count) == 1)

    preference_payload = {
        "collections": [{"id": "race", "name": "Race", "novel_ids": ["full-novel", "full-novel", "partial-novel"]}],
    }
    preference_threads = [threading.Thread(target=lambda: db_for(schema).save_user_preferences(normal_id, preference_payload)) for _ in range(2)]
    for thread in preference_threads:
        thread.start()
    for thread in preference_threads:
        thread.join()
    collection = db.user_preferences(normal_id)["collections"][0]
    require("duplicate collection membership deduped in preferences", collection["novel_ids"] == ["full-novel", "partial-novel"])

    progress_threads = [
        threading.Thread(target=lambda chapter=chapter: db_for(schema).save_reading_progress(normal_id, "partial-novel", chapter, "english", 10 * chapter))
        for chapter in (1, 2)
    ]
    for thread in progress_threads:
        thread.start()
    for thread in progress_threads:
        thread.join()
    progress = db.reading_progress(normal_id, "partial-novel") or {}
    require("simultaneous progress update valid", int(progress.get("chapter_number") or 0) in {1, 2})

    stop = threading.Event()

    def active_writer() -> None:
        local_db = db_for(schema)
        index = 0
        while not stop.is_set():
            index += 1
            local_db.set_favorite(normal_id, "full-novel", True)
            local_db.save_reading_progress(normal_id, "partial-novel", 1 + (index % 2), "english", index % 100)

    writer = threading.Thread(target=active_writer)
    writer.start()
    try:
        manifests = [db.platform_backup_manifest_summary() for _ in range(10)]
    finally:
        stop.set()
        writer.join()
    require("backup manifest during writes", all(item.get("ok") for item in manifests))

    before_audit = len(table_rows(schema, "audit_events"))
    try:
        with db.connect() as conn:
            conn.execute(
                f"INSERT INTO {db.table('audit_events')} (event_type, summary, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                ("rollback_probe", "should rollback", "{}", time.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
            conn.execute(f"INSERT INTO {db.table('translation_job_items')} (job_id, novel_id, chapter_number, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), "missing", 1, "pending", time.strftime("%Y-%m-%dT%H:%M:%SZ"), time.strftime("%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        pass
    after_audit = len(table_rows(schema, "audit_events"))
    require("failed write rolled back transaction", before_audit == after_audit)

    return {
        "worker_claims": "passed",
        "imports_same_chapter": "passed",
        "duplicate_bookmarks": "passed",
        "collection_preferences": "deduped",
        "progress_updates": "passed",
        "backup_during_writes": "passed",
        "rollback": "passed",
    }


def auth_matrix(schema: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    normal = auth_headers("normal")
    translator = auth_headers("translator")
    admin = auth_headers("admin")
    removed = auth_headers("removed")
    with run_app(schema) as base_url:
        requests.get(f"{base_url}/", timeout=10).raise_for_status()
        for path in ("/api/novels", "/api/novels/partial-novel", "/api/novels/partial-novel/library?search=Chapter", "/api/novels/partial-novel/chapters/1/original", "/api/novels/partial-novel/chapters/1/english", "/api/admin/session"):
            request_json("GET", base_url, path)
        guest_library = request_json("GET", base_url, "/api/novels/partial-novel/library")
        require("guest library hides reference flags", all("has_reference" not in item for item in guest_library["chapters"]))
        request_json("GET", base_url, "/api/novels/partial-novel/chapters/1/reference", expected=401)
        request_json("POST", base_url, "/api/translation/estimate", json_payload={"novel_id": "partial-novel", "next_count": 1}, expected=401)
        request_json("GET", base_url, "/api/admin/backups/manifest", expected=401)
        results["guest"] = "passed"

        account = request_json("GET", base_url, "/api/account/me", headers=normal)
        require("normal authenticated", account.get("authenticated") is True and account["user"]["role"] == "user")
        request_json("PUT", base_url, "/api/account/progress", headers=normal, json_payload={"novel_id": "partial-novel", "chapter_number": 1, "source": "english", "scroll_percent": 12})
        request_json("PUT", base_url, "/api/account/bookmarks", headers=normal, json_payload={"novel_id": "partial-novel", "chapter_number": 1, "note": "normal"})
        request_json("PUT", base_url, "/api/account/favorites/full-novel", headers=normal, json_payload={"favorite": True})
        request_json("PUT", base_url, "/api/account/preferences", headers=normal, json_payload={"preferences": {"collections": [{"id": "n", "name": "Normal", "novel_ids": ["full-novel", "full-novel"]}]}})
        request_json("GET", base_url, "/api/novels/partial-novel/chapters/1/reference", headers=normal, expected=401)
        request_json("POST", base_url, "/api/translation/estimate", headers=normal, json_payload={"novel_id": "partial-novel", "next_count": 1}, expected=401)
        request_json("GET", base_url, "/api/admin/db-health", headers=normal, expected=401)
        results["normal_user"] = "passed"

        request_json("GET", base_url, "/api/account/me", headers=translator)
        reference = request_json("GET", base_url, "/api/novels/partial-novel/chapters/1/reference", headers=translator)
        require("translator reference access", "Reference partial 1" in reference["text"])
        estimate = request_json("POST", base_url, "/api/translation/estimate", headers=translator, json_payload={"novel_id": "partial-novel", "selection_mode": "next-untranslated", "next_count": 1, "model": "gpt-4o-mini"})
        require("translator estimate", int(estimate.get("eligible_count") or 0) >= 1)
        job = request_json("POST", base_url, "/api/translation/jobs", headers=translator, json_payload={"novel_id": "partial-novel", "selection_mode": "next-untranslated", "next_count": 1, "model": "gpt-4o-mini"})["job"]
        for action in ("pause", "resume", "stop"):
            request_json("POST", base_url, f"/api/translation/jobs/{job['id']}/{action}", headers=translator)
        request_json("GET", base_url, "/api/admin/backups/manifest", headers=translator, expected=401)
        request_json("GET", base_url, "/api/admin/users", headers=translator, expected=401)
        request_json("GET", base_url, "/api/desktop/auth/check", headers=translator, expected=401)
        results["translator"] = "passed"

        request_json("GET", base_url, "/api/admin/db-health", headers=admin)
        request_json("GET", base_url, "/api/admin/users", headers=admin)
        request_json("GET", base_url, "/api/admin/audit-events", headers=admin)
        request_json("GET", base_url, "/api/admin/backups/manifest", headers=admin)
        backup = request_json("POST", base_url, "/api/admin/backups/jobs", headers=admin, json_payload={"store": False, "safe_mode": True})["job"]
        request_json("GET", base_url, f"/api/admin/backups/jobs/{backup['id']}", headers=admin)
        request_json("POST", base_url, "/api/admin/backups/restore-preview", headers=admin, json_payload={"backup": {"manifest": {"format_version": "godtranslator-v10-platform-backup.v1"}, "tables": {"novels": []}}, "mode": "add-missing"})
        request_json("GET", base_url, "/api/admin/translation/performance", headers=admin)
        request_json("GET", base_url, "/api/desktop/auth/check", headers=admin)
        request_json("GET", base_url, "/api/desktop/sync/status?novel_id=partial-novel", headers=admin)
        request_json("POST", base_url, "/api/admin/content/import/preview", headers=admin, json_payload={"novel_id": "partial-novel", "items": [{"chapter_number": 1, "content_type": "original", "text": "Overwrite attempt"}], "options": {"overwrite_existing": False}})
        request_json("GET", base_url, "/api/novels/partial-novel/recovery/reference", headers=admin)
        results["admin"] = "passed"

        request_json("GET", base_url, "/api/account/home", headers=removed, expected=401)
        expired = {"Authorization": f"Bearer {test_token(TEST_USERS['normal'][0], TEST_USERS['normal'][1], exp_delta=-30)}"}
        invalid_signature = {"Authorization": f"Bearer {test_token(TEST_USERS['normal'][0], TEST_USERS['normal'][1], tamper=True)}"}
        unknown = {"Authorization": f"Bearer {test_token('unknown-user', 'unknown@example.invalid')}"}
        altered = {"Authorization": f"Bearer {test_token(TEST_USERS['normal'][0], TEST_USERS['normal'][1], claimed_role='admin')}"}
        for label, headers in (("expired", expired), ("invalid_signature", invalid_signature), ("unknown", unknown), ("altered_role", altered)):
            request_json("GET", base_url, "/api/admin/db-health", headers=headers, expected=401)
            if label != "altered_role":
                request_json("GET", base_url, "/api/account/home", headers=headers, expected=401)
        request_json("GET", base_url, "/api/desktop/auth/check", headers={"Authorization": "Bearer malformed"}, expected=401)
        results["invalid_identity"] = "passed"

        admin_session = requests.Session()
        login = admin_session.post(f"{base_url}/api/admin/login", json={"password": ADMIN_PASSWORD}, timeout=10)
        require("admin cookie login", login.status_code == 200)
        session_payload = admin_session.get(f"{base_url}/api/admin/session", timeout=10).json()
        require("admin session cookie active", session_payload.get("admin") is True)
        require("admin cookie has httponly", "httponly" in login.headers.get("set-cookie", "").lower())
        require("admin cookie has samesite", "samesite=lax" in login.headers.get("set-cookie", "").lower())
        admin_session.get(f"{base_url}/api/admin/db-health", timeout=10).raise_for_status()
        logout = admin_session.post(f"{base_url}/api/admin/logout", timeout=10)
        require("admin logout ok", logout.status_code == 200)
        request_after_logout = admin_session.get(f"{base_url}/api/admin/db-health", timeout=10)
        require("admin logout clears access", request_after_logout.status_code == 401)
        results["csrf_session"] = "cookie session pass; SameSite=Lax and HttpOnly verified"

        request_json("GET", base_url, "/api/novels/partial-novel/library", headers=normal)
        public_novel = request_json("GET", base_url, "/api/novels/partial-novel", headers=normal)
        require("normal counts hide reference", "reference" not in public_novel["counts"])
        require("normal metadata hides reference source", "reference_source_url" not in public_novel["novel"])
        audit = request_json("GET", base_url, "/api/admin/audit-events", headers=admin)["events"]
        audit_text = json.dumps(audit, ensure_ascii=False)
        require("audit logs redact authorization", "Bearer " not in audit_text and TEST_AUTH_SECRET not in audit_text)
        require("audit logs do not expose chapter bodies", "Original partial" not in audit_text and "Reference partial" not in audit_text)
        results["reference_privacy"] = "passed"
        results["audit_privacy"] = "passed"

        db = db_for(schema)
        with db.connect() as conn:
            conn.execute(f"UPDATE {db.table('user_profiles')} SET role = 'user' WHERE user_id = ?", (TEST_USERS["translator"][0],))
        request_json("POST", base_url, "/api/translation/estimate", headers=translator, json_payload={"novel_id": "partial-novel", "next_count": 1}, expected=401)
        results["role_change_effective"] = "passed"

    with run_app(schema, app_env="production") as base_url:
        request_json("GET", base_url, "/api/admin/db-health", headers=admin, expected=401)
    results["test_auth_production_guard"] = "passed"
    return results


def main() -> None:
    assert_safe_database_url()
    version = pg_query("SHOW server_version")[0]["server_version"]
    run_id = uuid.uuid4().hex[:10]
    schemas = {
        "empty": f"gt_rc2_empty_{run_id}",
        "v10": f"gt_rc2_v10_{run_id}",
        "edge": f"gt_rc2_edge_{run_id}",
    }
    results: dict[str, Any] = {
        "postgres_version": version,
        "database_host": urlparse(DB_URL).hostname,
        "schemas": schemas,
        "openai_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "supabase_config_present": any(os.getenv(key) for key in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_BACKUP_SERVICE_KEY")),
    }
    require("OpenAI key absent", not results["openai_key_present"])
    require("production Supabase config absent", not results["supabase_config_present"])
    try:
        results["empty_database"] = scenario_empty(schemas["empty"])
        results["v10_fixture"] = scenario_v10_fixture(schemas["v10"])
        results["edge_state"] = scenario_edge(schemas["edge"])
        results["postgres_concurrency"] = postgres_concurrency(schemas["edge"])
        results["authorization"] = auth_matrix(schemas["edge"])
        results["ok"] = True
        print(json.dumps(results, indent=2, sort_keys=True, default=str))
    finally:
        if os.getenv("GT_RC2_KEEP_SCHEMAS") != "true":
            for schema in schemas.values():
                drop_schema(schema)


if __name__ == "__main__":
    main()
