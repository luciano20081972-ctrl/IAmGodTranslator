from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)

from app.db import Database


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


def response_content(response: Any) -> bytes:
    content = getattr(response, "content", b"")
    if hasattr(content, "read"):
        position = content.tell()
        content.seek(0)
        data = content.read()
        content.seek(position)
        return data
    if isinstance(content, str):
        return content.encode("utf-8")
    return content


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
    created = app_main.create_platform_backup({"store": False})
    if not created["manifest"].get("sha256") or not created["manifest"].get("size_bytes"):
        raise AssertionError("full backup create did not calculate checksum and size")
    download = app_main.download_platform_backup()
    if getattr(download, "status_code", 200) != 200:
        raise AssertionError(f"download backup failed: {getattr(download, 'status_code', 0)}")
    download_bytes = response_content(download)
    payload = json.loads(download_bytes.decode("utf-8"))
    if not payload.get("tables") or not payload.get("manifest", {}).get("sha256"):
        raise AssertionError("downloaded backup payload is incomplete")
    return {
        "create_status": 200,
        "storage_status": created.get("storage", {}).get("status"),
        "download_status": getattr(download, "status_code", 200),
        "download_bytes": len(download_bytes),
    }


class BrokenManifestDatabase(Database):
    def platform_backup_manifest_summary(self) -> dict[str, Any]:
        raise RuntimeError("simulated manifest failure with hidden details")


class BrokenBackupDatabase(Database):
    def platform_backup_payload(self) -> dict[str, Any]:
        raise RuntimeError("simulated backup failure with hidden details")


def json_error_fixture() -> dict[str, Any]:
    use_database(BrokenManifestDatabase("sqlite:///:memory:"))
    manifest = app_main.platform_backup_manifest()
    if manifest.status_code != 500:
        raise AssertionError(f"expected manifest 500, got {manifest.status_code}")
    manifest_payload = manifest.content
    if manifest_payload.get("error", {}).get("stage") != "table_counts":
        raise AssertionError("manifest JSON error missing table_counts stage")
    if "hidden details" in json.dumps(manifest_payload):
        raise AssertionError("manifest JSON error exposed exception details")

    use_database(BrokenBackupDatabase("sqlite:///:memory:"))
    create = app_main.create_platform_backup({"store": False})
    download = app_main.download_platform_backup()
    for label, response in {"create": create, "download": download}.items():
        if response.status_code != 500:
            raise AssertionError(f"expected {label} 500, got {response.status_code}")
        payload = response.content
        if payload.get("error", {}).get("stage") != "build_full_backup":
            raise AssertionError(f"{label} JSON error missing build_full_backup stage")
        if "hidden details" in json.dumps(payload):
            raise AssertionError(f"{label} JSON error exposed exception details")
    return {
        "manifest_error": manifest_payload["error"],
        "create_error": create.content["error"],
        "download_error": download.content["error"],
    }


def authorization_fixture() -> dict[str, Any]:
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    for route in ("/api/admin/backups/manifest", "/api/admin/backups/create", "/api/admin/backups/download"):
        marker = f'"{route}"'
        route_index = source.find(marker)
        if route_index == -1:
            raise AssertionError(f"route not found: {route}")
        function_slice = source[route_index : route_index + 350]
        if "Depends(require_admin)" not in function_slice:
            raise AssertionError(f"route is not admin-protected: {route}")
    return {"admin_only_routes": 3, "checked": True}


def frontend_error_guards() -> dict[str, Any]:
    source = (Path(__file__).resolve().parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    required = [
        "HTTP ${response.status}: The server returned a non-JSON response",
        "serverError.stage",
        "backupManifestError(error)",
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
        "missing_optional_table": missing_optional_table_fixture(),
        "explicit_full_backup": explicit_full_backup_fixture(),
        "json_errors": json_error_fixture(),
        "authorization": authorization_fixture(),
        "frontend_error_guards": frontend_error_guards(),
    }
    print(json.dumps({"ok": True, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
