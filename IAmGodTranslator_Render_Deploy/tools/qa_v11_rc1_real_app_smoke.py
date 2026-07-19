from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("GT_RC1_BASE_URL", "http://127.0.0.1:8000")
ADMIN_PASSWORD = "rc1-local-admin-password"


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def working_set_bytes(pid: int) -> int | None:
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    process_query_information = 0x0400
    process_vm_read = 0x0010
    handle = ctypes.windll.kernel32.OpenProcess(process_query_information | process_vm_read, False, pid)
    if not handle:
        return None
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        return int(counters.WorkingSetSize) if ok else None
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def mb(value: int | None) -> float | None:
    return round(value / 1024 / 1024, 2) if value is not None else None


def seed_database(db_path: Path) -> None:
    os.environ["GT_SQLITE_PATH"] = str(db_path)
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("OPENAI_API_KEY", None)
    sys.path.insert(0, str(ROOT))
    from app.db import Database  # noqa: PLC0415

    db = Database(f"sqlite:///{db_path}")
    db.initialize()

    db.save_novel_metadata("empty-novel", {"title": "Empty Novel", "metadata": {"expected_chapter_start": None}})
    db.save_novel_metadata("one-chapter", {"title": "One Chapter Novel", "author": "QA"})
    db.upsert_chapter("one-chapter", 1, "Chapter 1", "Original one", None, "English one", ai_model="fixture")

    db.save_novel_metadata("original-only", {"title": "Original Only", "author": "QA"})
    for chapter in range(1, 4):
        db.upsert_chapter("original-only", chapter, f"Chapter {chapter}", f"Original only {chapter}", None, None)

    db.save_novel_metadata("partial-novel", {"title": "Partial Novel", "author": "QA", "reference_source_url": "https://example.invalid/ref"})
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

    db.save_novel_metadata("full-novel", {"title": "Full Novel", "author": "QA"})
    for chapter in range(1, 4):
        db.upsert_chapter("full-novel", chapter, f"Chapter {chapter}", f"Original full {chapter}", f"Reference full {chapter}", f"English full {chapter}", ai_model="fixture")

    db.apply_content_import_payload(
        {
            "novel_id": "full-novel",
            "items": [
                {"chapter_number": 1, "content_type": "english", "edition_type": "Official", "text": "Official edition"},
                {"chapter_number": 1, "content_type": "english", "edition_type": "AI", "text": "AI edition"},
            ],
            "options": {"overwrite_existing": True},
        }
    )
    db.ensure_user_profile("qa-user", "reader@example.invalid", "user", "Reader QA", None)
    db.ensure_user_profile("qa-translator", "translator@example.invalid", "translator", "Translator QA", None)
    db.save_user_preferences("qa-user", {"theme": "light", "collections": [{"id": "qa", "name": "QA", "novel_ids": ["full-novel"]}]})
    db.create_translation_job("partial-novel", [1, 2, 3, 4, 5], {"model": "gpt-4o-mini", "batch_size": 5, "speed_preset": "balanced"})
    db.create_backup_job(destination="local", safe_mode=True)
    db.record_audit_event("qa_seed", actor_role="admin", target_type="fixture", target_id="rc1", summary="RC1 fixture seeded", metadata={"safe": True})


def wait_for_server(session: requests.Session, process: subprocess.Popen[str]) -> float:
    started = time.perf_counter()
    last_error = ""
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited early with code {process.returncode}: {last_error}")
        try:
            response = session.get(f"{BASE_URL}/api/health", timeout=1.0)
            if response.status_code == 200 and response.headers.get("content-type", "").startswith("application/json"):
                return round(time.perf_counter() - started, 3)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"server did not become healthy: {last_error}")


def assert_json(response: requests.Response, status: int | None = None) -> dict[str, Any]:
    if status is not None:
        require(f"{response.request.method} {response.url} status {status}", response.status_code == status)
    require(f"{response.url} json content-type", response.headers.get("content-type", "").startswith("application/json"))
    text = response.text.lower()
    require(f"{response.url} no traceback", "traceback" not in text and "<html" not in text)
    return response.json()


def smoke_http(session: requests.Session, admin: requests.Session, work_dir: Path, pid: int) -> dict[str, Any]:
    results: dict[str, Any] = {}

    page = session.get(f"{BASE_URL}/", timeout=10)
    require("home template renders", page.status_code == 200 and "GodTranslator" in page.text)
    app_js = session.get(f"{BASE_URL}/static/app.js", timeout=10)
    styles = session.get(f"{BASE_URL}/static/styles.css", timeout=10)
    app_js_type = app_js.headers.get("content-type", "")
    require("static app.js loads", app_js.status_code == 200 and ("javascript" in app_js_type or "ecmascript" in app_js_type))
    require("static styles.css loads", styles.status_code == 200 and "css" in styles.headers.get("content-type", ""))

    health = assert_json(session.get(f"{BASE_URL}/api/health", timeout=10), 200)
    desktop_health = assert_json(session.get(f"{BASE_URL}/api/desktop/health", timeout=10), 200)
    unknown = assert_json(session.get(f"{BASE_URL}/api/no-such-route", timeout=10), 404)
    require("unknown api is controlled", unknown.get("detail") == "Not Found")

    novels = assert_json(session.get(f"{BASE_URL}/api/novels", timeout=10), 200)
    require("novels listed", len(novels.get("novels", [])) >= 4)
    assert_json(session.get(f"{BASE_URL}/api/novels/full-novel", timeout=10), 200)
    library = assert_json(session.get(f"{BASE_URL}/api/novels/partial-novel/library", timeout=10), 200)
    require("guest library hides reference flags", all("has_reference" not in chapter for chapter in library["chapters"]))
    assert_json(session.get(f"{BASE_URL}/api/novels/partial-novel/chapters/1/original", timeout=10), 200)
    assert_json(session.get(f"{BASE_URL}/api/novels/partial-novel/chapters/1/english", timeout=10), 200)
    assert_json(session.get(f"{BASE_URL}/api/novels/partial-novel/chapters/1/reference", timeout=10), 401)
    assert_json(session.post(f"{BASE_URL}/api/translation/estimate", json={"novel_id": "partial-novel", "next_count": 25}, timeout=10), 401)
    assert_json(session.get(f"{BASE_URL}/api/admin/backups/manifest", timeout=10), 401)
    assert_json(session.get(f"{BASE_URL}/api/desktop/auth/check", headers={"Authorization": "Bearer malformed"}, timeout=10), 401)

    login = assert_json(admin.post(f"{BASE_URL}/api/admin/login", json={"password": ADMIN_PASSWORD}, timeout=10), 200)
    require("admin login ok", login.get("admin") is True)
    assert_json(admin.get(f"{BASE_URL}/api/admin/session", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/overview", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/db-health", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/content/editions/full-novel", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/users", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/audit-events", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/desktop/auth/check", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/desktop/sync/status?novel_id=partial-novel", timeout=10), 200)

    estimate_payload = {"novel_id": "partial-novel", "selection_mode": "next-untranslated", "next_count": 5, "model": "gpt-4o-mini", "batch_size": 5}
    estimate = assert_json(admin.post(f"{BASE_URL}/api/translation/estimate", json=estimate_payload, timeout=10), 200)
    require("translation estimate has eligible items", int(estimate.get("eligible_count") or 0) > 0)
    job = assert_json(admin.post(f"{BASE_URL}/api/translation/jobs", json=estimate_payload, timeout=10), 200)["job"]
    job_id = job["id"]
    assert_json(admin.get(f"{BASE_URL}/api/translation/jobs/{job_id}", timeout=10), 200)
    assert_json(admin.post(f"{BASE_URL}/api/translation/jobs/{job_id}/pause", timeout=10), 200)
    assert_json(admin.post(f"{BASE_URL}/api/translation/jobs/{job_id}/resume", timeout=10), 200)
    assert_json(admin.post(f"{BASE_URL}/api/translation/jobs/{job_id}/stop", timeout=10), 200)

    import_payload = {
        "novel": {"title": "HTTP Import Novel"},
        "items": [
            {"chapter_number": 1, "content_type": "original", "text": "HTTP original one"},
            {"chapter_number": 1, "content_type": "english", "edition_type": "Imported", "text": "HTTP English one"},
        ],
        "options": {"skip_existing": True, "add_missing": True},
    }
    preview = assert_json(admin.post(f"{BASE_URL}/api/admin/content/import/preview", json=import_payload, timeout=10), 200)
    require("content import preview executable", preview.get("can_execute") is True)
    import_result = assert_json(admin.post(f"{BASE_URL}/api/admin/content/import/execute", json=import_payload, timeout=10), 200)
    require("content import created novel", bool(import_result.get("novel_id")))

    txt_path = work_dir / "Chapter 4.txt"
    txt_path.write_text("Recovered reference four", encoding="utf-8")
    with txt_path.open("rb") as handle:
        recovery = assert_json(admin.post(f"{BASE_URL}/api/novels/partial-novel/recovery/preview?target_mode=reference", files={"files": ("Chapter 4.txt", handle, "text/plain")}, timeout=10), 200)
    require("recovery preview created job", bool(recovery.get("job_id")))
    assert_json(admin.get(f"{BASE_URL}/api/novels/partial-novel/recovery/request?target_mode=reference", timeout=10), 200)
    apply_recovery = assert_json(admin.post(f"{BASE_URL}/api/novels/partial-novel/recovery/import/{recovery['job_id']}", timeout=10), 200)
    require("recovery imported reference", int(apply_recovery.get("imported_count") or 0) >= 1)

    pack_zip = work_dir / "desktop-pack.zip"
    with zipfile.ZipFile(pack_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Chapter 001.txt", "Desktop pack original")
    with pack_zip.open("rb") as handle:
        assert_json(admin.post(f"{BASE_URL}/api/desktop/import/preview-pack?novel_title=Desktop Pack&content_type=original", files={"files": ("desktop-pack.zip", handle, "application/zip")}, timeout=10), 200)

    before_manifest = working_set_bytes(pid)
    manifest_start = time.perf_counter()
    manifest = assert_json(admin.get(f"{BASE_URL}/api/admin/backups/manifest", timeout=20), 200)
    manifest_elapsed = round(time.perf_counter() - manifest_start, 3)
    after_manifest = working_set_bytes(pid)
    require("backup manifest lightweight", manifest.get("manifest", {}).get("kind") == "lightweight_manifest")

    backup_job = assert_json(admin.post(f"{BASE_URL}/api/admin/backups/jobs", json={"store": False, "safe_mode": True}, timeout=10), 200)["job"]
    for _ in range(80):
        status = assert_json(admin.get(f"{BASE_URL}/api/admin/backups/jobs/{backup_job['id']}", timeout=10), 200)["job"]
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.25)
    require("background backup completed", status["status"] == "completed")
    after_backup = working_set_bytes(pid)

    restore = assert_json(admin.post(f"{BASE_URL}/api/admin/backups/restore-preview", json={"backup": {"manifest": {"format_version": "godtranslator-v10-platform-backup.v1"}, "data": {}}, "mode": "add-missing"}, timeout=10), 200)
    require("restore preview controlled", "valid" in restore or "compatible" in restore)
    after_restore = working_set_bytes(pid)

    assert_json(admin.post(f"{BASE_URL}/api/admin/logout", timeout=10), 200)
    assert_json(admin.get(f"{BASE_URL}/api/admin/db-health", timeout=10), 401)

    results["startup_routes"] = {
        "health": health.get("ok"),
        "desktop_health": desktop_health.get("ok"),
        "unknown_api": unknown.get("detail"),
        "static_assets": True,
        "template": True,
    }
    results["authorization"] = {
        "guest_reference_denied": True,
        "guest_translation_denied": True,
        "guest_admin_denied": True,
        "admin_login_logout": True,
        "malformed_desktop_token_rejected": True,
    }
    results["translation"] = {"estimate_eligible": estimate.get("eligible_count"), "job_created": job_id, "pause_resume_cancel": True}
    results["import_recovery"] = {"import_novel_id": import_result.get("novel_id"), "recovery_imported": apply_recovery.get("imported_count")}
    results["backup"] = {
        "manifest_elapsed_seconds": manifest_elapsed,
        "manifest_response_bytes": len(json.dumps(manifest)),
        "manifest_memory_delta_mb": mb(after_manifest - before_manifest) if before_manifest and after_manifest else None,
        "backup_status": status["status"],
        "backup_memory_delta_from_manifest_mb": mb(after_backup - after_manifest) if after_backup and after_manifest else None,
        "restore_preview_memory_delta_from_backup_mb": mb(after_restore - after_backup) if after_restore and after_backup else None,
    }
    return results


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="gt-v11-rc1-"))
    db_path = temp_root / "rc1.sqlite"
    backup_dir = temp_root / "backups"
    logs_dir = temp_root / "logs"
    backup_dir.mkdir()
    logs_dir.mkdir()
    process: subprocess.Popen[str] | None = None
    try:
        seed_database(db_path)
        env = os.environ.copy()
        env.pop("DATABASE_URL", None)
        env.pop("OPENAI_API_KEY", None)
        env.update(
            {
                "GT_SQLITE_PATH": str(db_path),
                "GT_BACKUP_WORK_DIR": str(backup_dir),
                "ADMIN_PASSWORD": ADMIN_PASSWORD,
                "ADMIN_SESSION_SECRET": "rc1-local-session-secret",
                "TRANSLATION_AUTOSTART": "false",
            }
        )
        uvicorn_exe = Path(sys.executable).with_name("uvicorn.exe")
        command = [str(uvicorn_exe), "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
        started_at = time.perf_counter()
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=(logs_dir / "uvicorn.out.log").open("w", encoding="utf-8"),
            stderr=(logs_dir / "uvicorn.err.log").open("w", encoding="utf-8"),
            text=True,
        )
        session = requests.Session()
        startup_seconds = wait_for_server(session, process)
        idle_memory = working_set_bytes(process.pid)
        smoke = smoke_http(session, requests.Session(), temp_root, process.pid)
        shutdown_started = time.perf_counter()
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        shutdown_seconds = round(time.perf_counter() - shutdown_started, 3)
        stderr_text = (logs_dir / "uvicorn.err.log").read_text(encoding="utf-8", errors="replace")
        stdout_text = (logs_dir / "uvicorn.out.log").read_text(encoding="utf-8", errors="replace")
        combined_logs = f"{stdout_text}\n{stderr_text}".lower()
        require("no traceback in server logs", "traceback" not in combined_logs)
        result = {
            "ok": True,
            "command": "uvicorn app.main:app --host 127.0.0.1 --port 8000",
            "startup_seconds": startup_seconds,
            "startup_wall_seconds": round(time.perf_counter() - started_at, 3),
            "idle_memory_mb": mb(idle_memory),
            "shutdown_seconds": shutdown_seconds,
            "db_path": str(db_path),
            "backup_dir": str(backup_dir),
            "smoke": smoke,
            "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
            "database_url_present": bool(os.environ.get("DATABASE_URL")),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        if os.environ.get("GT_RC1_KEEP_TEMP") != "1":
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
