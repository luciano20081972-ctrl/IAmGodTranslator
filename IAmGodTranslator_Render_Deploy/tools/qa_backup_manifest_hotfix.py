from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tracemalloc
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

from app.db import Database, normalize_backup_job


def install_fastapi_stubs() -> None:
    try:
        import fastapi  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    fastapi = types.ModuleType("fastapi")
    responses = types.ModuleType("fastapi.responses")
    staticfiles = types.ModuleType("fastapi.staticfiles")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str | None = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def mount(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _decorator(self, *args: Any, **kwargs: Any) -> Any:
            def bind(func: Any) -> Any:
                return func

            return bind

        get = post = put = patch = delete = on_event = _decorator

    class Response:
        def set_cookie(self, *args: Any, **kwargs: Any) -> None:
            pass

        def delete_cookie(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Request:
        pass

    class UploadFile:
        pass

    class StaticFiles:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class JSONResponse:
        def __init__(self, content: Any = None, status_code: int = 200, **kwargs: Any) -> None:
            self.content = content
            self.status_code = status_code
            self.body = json.dumps(content or {}).encode("utf-8")

    class StreamingResponse:
        def __init__(self, content: Any, media_type: str | None = None, headers: dict[str, str] | None = None) -> None:
            self.content = content
            self.media_type = media_type
            self.headers = headers or {}
            self.status_code = 200

    class HTMLResponse:
        def __init__(self, content: str = "", **kwargs: Any) -> None:
            self.content = content

    def dependency_marker(*args: Any, **kwargs: Any) -> Any:
        return kwargs.get("default") if "default" in kwargs else None

    fastapi.Body = dependency_marker
    fastapi.Depends = dependency_marker
    fastapi.FastAPI = FastAPI
    fastapi.File = dependency_marker
    fastapi.HTTPException = HTTPException
    fastapi.Query = dependency_marker
    fastapi.Request = Request
    fastapi.Response = Response
    fastapi.UploadFile = UploadFile
    responses.HTMLResponse = HTMLResponse
    responses.JSONResponse = JSONResponse
    responses.StreamingResponse = StreamingResponse
    staticfiles.StaticFiles = StaticFiles
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses
    sys.modules["fastapi.staticfiles"] = staticfiles


install_fastapi_stubs()

from app import main as app_main


ORIGINAL_SENTINEL = "MANIFEST_SHOULD_NOT_RETURN_ORIGINAL_TEXT"
EDITION_SENTINEL = "MANIFEST_SHOULD_NOT_RETURN_EDITION_TEXT"


def build_db(name: str, chapters: int = 908, large_text: bool = True) -> Database:
    path = Path(tempfile.gettempdir()) / f"gt-backup-manifest-hotfix-{name}-{time.time_ns()}.db"
    db = Database(f"sqlite:///{path}")
    db.initialize()
    db.save_novel_metadata("manifest-fixture", {"id": "manifest-fixture", "title": "Manifest Fixture", "model": "gpt-4o-mini", "status": "active"})
    large_original = f"{ORIGINAL_SENTINEL} " + ("original fixture text " * 12000)
    large_reference = "reference fixture text " * 6000
    large_edition = f"{EDITION_SENTINEL} " + ("edition fixture text " * 12000)
    for chapter in range(1, chapters + 1):
        original = large_original if large_text and chapter == 1 else f"Original chapter {chapter}"
        reference = large_reference if large_text and chapter == 2 else f"Reference chapter {chapter}"
        ai_text = large_edition if large_text and chapter == 3 else (f"English chapter {chapter}" if chapter % 2 == 0 else None)
        db.upsert_chapter("manifest-fixture", chapter, f"Chapter {chapter}", original, reference, ai_text, ai_model="qa-fake")
    return db


def use_database(db: Database) -> None:
    app_main.database = db
    app_main.translation_runner.store = db
    app_main.BACKUP_WORKERS.clear()


def response_json(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    content = getattr(response, "content", None)
    if isinstance(content, dict):
        return content
    body = getattr(response, "body", b"")
    if body:
        return json.loads(body.decode("utf-8"))
    if isinstance(content, str):
        return json.loads(content)
    if isinstance(content, bytes):
        return json.loads(content.decode("utf-8"))
    raise AssertionError(f"response did not contain JSON: {type(response).__name__}")


def response_status(response: Any) -> int:
    return int(getattr(response, "status_code", 200))


def wait_for_backup_job(job_id: str, expected: set[str] | None = None, timeout_seconds: float = 15.0) -> dict[str, Any]:
    expected = expected or {"completed"}
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = response_json(app_main.get_backup_job(job_id))
        job = payload["job"]
        if job["status"] in expected:
            return job
        time.sleep(0.05)
    raise AssertionError(f"backup job {job_id} did not reach {sorted(expected)}")


def manifest_endpoint_fixture() -> dict[str, Any]:
    db = build_db("908-large")
    use_database(db)
    started = time.perf_counter()
    payload = app_main.platform_backup_manifest()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    text = json.dumps(payload, ensure_ascii=False)
    manifest = payload["manifest"]
    if manifest["table_counts"]["chapters"] != 908:
        raise AssertionError(f"expected 908 chapters, got {manifest['table_counts']['chapters']}")
    if manifest["chapter_source_counts"]["chapters"] != 908:
        raise AssertionError("chapter source count mismatch")
    if ORIGINAL_SENTINEL in text or EDITION_SENTINEL in text:
        raise AssertionError("manifest response serialized chapter or edition text")
    if manifest.get("sha256") or manifest.get("size_bytes"):
        raise AssertionError("lightweight manifest should not expose full backup checksum or size")
    return {
        "status": 200,
        "elapsed_ms": elapsed_ms,
        "response_bytes": len(text.encode("utf-8")),
        "generated_in_ms": manifest.get("generated_in_ms"),
        "chapters": manifest["chapter_source_counts"]["chapters"],
        "contains_text_sentinels": False,
    }


def repeated_manifest_memory_fixture() -> dict[str, Any]:
    db = build_db("908-large-repeat")
    use_database(db)
    tracemalloc.start()
    started = time.perf_counter()
    max_response_bytes = 0
    for _ in range(50):
        payload = app_main.platform_backup_manifest()
        text = json.dumps(payload, ensure_ascii=False)
        max_response_bytes = max(max_response_bytes, len(text.encode("utf-8")))
        if ORIGINAL_SENTINEL in text or EDITION_SENTINEL in text:
            raise AssertionError("manifest response serialized chapter or edition text during repeat calls")
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if max_response_bytes > 50 * 1024:
        raise AssertionError(f"manifest response exceeded 50KB: {max_response_bytes}")
    if peak > 32 * 1024 * 1024:
        raise AssertionError(f"manifest memory peak exceeded 32MB: {peak}")
    return {
        "calls": 50,
        "elapsed_ms": elapsed_ms,
        "max_response_bytes": max_response_bytes,
        "tracemalloc_peak_bytes": peak,
        "tracemalloc_current_bytes": current,
    }


def http_manifest_fixture() -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError:
        return {"skipped": True, "reason": "fastapi_testclient_unavailable"}
    db = build_db("http-manifest", chapters=906)
    use_database(db)
    with TestClient(app_main.app) as client:
        login = client.post("/api/admin/login", json={"password": "qa-admin-password"})
        if login.status_code != 200:
            raise AssertionError(f"admin login failed over HTTP: {login.status_code}")
        response = client.get("/api/admin/backups/manifest")
    if response.status_code != 200:
        raise AssertionError(f"manifest HTTP status was {response.status_code}")
    payload = response.json()
    text = response.text
    if ORIGINAL_SENTINEL in text or EDITION_SENTINEL in text:
        raise AssertionError("HTTP manifest response serialized chapter or edition text")
    if len(response.content) > 50 * 1024:
        raise AssertionError(f"HTTP manifest response exceeded 50KB: {len(response.content)}")
    return {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "response_bytes": len(response.content),
        "chapters": payload["manifest"]["chapter_source_counts"]["chapters"],
    }


def missing_optional_table_fixture() -> dict[str, Any]:
    db = build_db("missing-optional", chapters=3, large_text=False)
    with db.connect() as conn:
        conn.execute(f"DROP TABLE {db.table('bookmarks')}")
    manifest = db.platform_backup_manifest_summary()["manifest"]
    if manifest["table_counts"]["bookmarks"] is not None:
        raise AssertionError("missing optional table did not report a null count")
    if manifest["table_errors"].get("bookmarks") is None:
        raise AssertionError("missing optional table did not report a safe table error")
    return {"bookmarks_count": manifest["table_counts"]["bookmarks"], "bookmarks_error": manifest["table_errors"]["bookmarks"]}


def explicit_full_backup_fixture() -> dict[str, Any]:
    db = build_db("full-backup", chapters=12)
    use_database(db)
    created_response = app_main.create_backup_job({"store": False})
    if response_status(created_response) != 202:
        raise AssertionError(f"expected queued backup job, got {response_status(created_response)}")
    created = response_json(created_response)
    job = wait_for_backup_job(created["job"]["id"])
    if not job.get("sha256") or not job.get("size_bytes"):
        raise AssertionError("background full backup did not calculate checksum and size")
    path = Path(str(job.get("file_path") or ""))
    if not path.exists():
        raise AssertionError("completed backup job did not leave a local backup file")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("tables") or payload.get("manifest", {}).get("kind") != "full_platform_backup":
        raise AssertionError("backup file payload is incomplete")
    download = app_main.download_platform_backup(job_id=job["id"])
    if getattr(download, "status_code", 200) != 200:
        raise AssertionError(f"download backup failed: {getattr(download, 'status_code', 0)}")
    return {
        "create_status": response_status(created_response),
        "job_status": job["status"],
        "storage_status": job.get("storage", {}).get("status"),
        "download_status": getattr(download, "status_code", 200),
        "backup_bytes": job["size_bytes"],
    }


def duplicate_backup_guard_fixture() -> dict[str, Any]:
    db = build_db("duplicate-guard", chapters=36)
    original_iter = db.iter_platform_backup_rows

    def slow_iter(table_name: str, batch_size: int = 100) -> Any:
        time.sleep(0.05)
        yield from original_iter(table_name, batch_size=batch_size)

    db.iter_platform_backup_rows = slow_iter  # type: ignore[method-assign]
    use_database(db)
    first = app_main.create_backup_job({"store": False})
    second = app_main.create_backup_job({"store": False})
    if response_status(first) != 202:
        raise AssertionError(f"first backup did not queue: {response_status(first)}")
    if response_status(second) != 429:
        raise AssertionError(f"second backup did not return conflict: {response_status(second)}")
    first_payload = response_json(first)
    second_payload = response_json(second)
    job = wait_for_backup_job(first_payload["job"]["id"])
    return {
        "first_status": response_status(first),
        "second_status": response_status(second),
        "second_code": second_payload.get("error", {}).get("code"),
        "completed_job": job["id"],
    }


def postgres_backup_job_json_fixture() -> dict[str, Any]:
    now = datetime.now(UTC)
    normalized = normalize_backup_job(
        {
            "id": uuid.uuid4(),
            "kind": "full_platform_backup",
            "destination": "local",
            "status": "queued",
            "safe_mode": 1,
            "current_table": None,
            "total_tables": 1,
            "completed_tables": 0,
            "total_rows": 10,
            "processed_rows": 0,
            "size_bytes": 0,
            "sha256": None,
            "file_path": None,
            "storage_json": "{}",
            "error": None,
            "cancel_requested": 0,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
        }
    )
    json.dumps({"ok": True, "job": normalized})
    if not isinstance(normalized["id"], str) or not isinstance(normalized["created_at"], str):
        raise AssertionError("PostgreSQL backup job fields were not converted to JSON-safe strings")
    return {"id_json_safe": True, "timestamps_json_safe": True}


class BrokenManifestDatabase(Database):
    def platform_backup_manifest_summary(self) -> dict[str, Any]:
        raise RuntimeError("simulated manifest failure with hidden details")


def json_error_fixture() -> dict[str, Any]:
    use_database(BrokenManifestDatabase("sqlite:///:memory:"))
    manifest = app_main.platform_backup_manifest()
    if response_status(manifest) != 500:
        raise AssertionError(f"expected manifest 500, got {response_status(manifest)}")
    manifest_payload = response_json(manifest)
    if manifest_payload.get("error", {}).get("stage") != "table_counts":
        raise AssertionError("manifest JSON error missing table_counts stage")
    if "hidden details" in json.dumps(manifest_payload):
        raise AssertionError("manifest JSON error exposed exception details")
    return {
        "manifest_error": manifest_payload["error"],
    }


def authorization_fixture() -> dict[str, Any]:
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    for route in ("/api/admin/backups/manifest", "/api/admin/backups/create", "/api/admin/backups/download", "/api/admin/backups/jobs"):
        marker = f'"{route}"'
        route_index = source.find(marker)
        if route_index == -1:
            raise AssertionError(f"route not found: {route}")
        function_slice = source[route_index : route_index + 350]
        if "Depends(require_admin)" not in function_slice:
            raise AssertionError(f"route is not admin-protected: {route}")
    return {"admin_only_routes": 4, "checked": True}


def frontend_error_guards() -> dict[str, Any]:
    source = (Path(__file__).resolve().parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    required = [
        "HTTP ${response.status}: The server returned a non-JSON response",
        "serverError.stage",
        "backupManifestError(error)",
        "loadAdminTabData(tab)",
        "renderBackupJobStatus",
        "Queueing background backup job...",
        "Backup manifest could not be loaded.",
        "Loading backup manifest...",
    ]
    missing = [text for text in required if text not in source]
    if missing:
        raise AssertionError(f"frontend error guard text missing: {missing}")
    return {"json_500_guard": True, "html_non_json_guard": True}


def main() -> None:
    results = {
        "manifest_908_large": manifest_endpoint_fixture(),
        "manifest_50_calls_memory": repeated_manifest_memory_fixture(),
        "http_manifest": http_manifest_fixture(),
        "missing_optional_table": missing_optional_table_fixture(),
        "background_full_backup": explicit_full_backup_fixture(),
        "duplicate_backup_guard": duplicate_backup_guard_fixture(),
        "postgres_backup_job_json": postgres_backup_job_json_fixture(),
        "json_errors": json_error_fixture(),
        "authorization": authorization_fixture(),
        "frontend_error_guards": frontend_error_guards(),
    }
    print(json.dumps({"ok": True, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
