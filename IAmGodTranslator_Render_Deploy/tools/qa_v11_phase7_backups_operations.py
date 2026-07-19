from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from qa_backup_manifest_hotfix import EDITION_SENTINEL, ORIGINAL_SENTINEL, app_main, build_db, use_database


ROOT = Path(__file__).resolve().parents[1]


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def repeated_manifest_fixture() -> dict[str, object]:
    db = build_db("phase7-manifest", chapters=120)
    use_database(db)
    started = time.perf_counter()
    for _ in range(50):
        payload = app_main.platform_backup_manifest()
        manifest = payload["manifest"]
        encoded = json.dumps(payload, ensure_ascii=False)
        require("manifest stays aggregate-only", ORIGINAL_SENTINEL not in encoded and EDITION_SENTINEL not in encoded)
        require("manifest does not expose full-backup checksum", manifest.get("sha256") is None)
        require("manifest is lightweight", manifest.get("kind") == "lightweight_manifest")
    return {"calls": 50, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}


def background_backup_fixture() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        os.environ["GT_BACKUP_WORK_DIR"] = temp
        db = build_db("phase7-job", chapters=24)
        use_database(db)
        job = db.create_backup_job(destination="local")
        app_main.run_platform_backup_job(job["id"], store=False)
        completed = db.backup_job(job["id"])
        require("backup job completed", completed["status"] == "completed")
        require("backup job tracked checksum", bool(completed["sha256"]))
        require("backup job tracked size", int(completed["size_bytes"] or 0) > 0)
        require("backup output file exists", Path(completed["file_path"]).exists())
        require("backup processed rows", int(completed["processed_rows"] or 0) >= int(completed["total_rows"] or 0))
        return {
            "status": completed["status"],
            "progress": completed["progress_percent"],
            "tables": completed["completed_tables"],
            "sha256_prefix": completed["sha256"][:12],
        }


def backup_cancel_fixture() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        os.environ["GT_BACKUP_WORK_DIR"] = temp
        db = build_db("phase7-cancel", chapters=6)
        use_database(db)
        job = db.create_backup_job(destination="local")
        db.update_backup_job(job["id"], cancel_requested=1)
        app_main.run_platform_backup_job(job["id"], store=False)
        cancelled = db.backup_job(job["id"])
        require("backup job cancelled", cancelled["status"] == "cancelled")
        return {"status": cancelled["status"], "cancel_requested": cancelled["cancel_requested"]}


def restore_and_audit_fixture() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        os.environ["GT_BACKUP_WORK_DIR"] = temp
        db = build_db("phase7-restore", chapters=4, large_text=False)
        use_database(db)
        job = db.create_backup_job(destination="local")
        app_main.run_platform_backup_job(job["id"], store=False)
        completed = db.backup_job(job["id"])
        require("restore backup job completed", completed["status"] == "completed")
        backup = json.loads(Path(completed["file_path"]).read_text(encoding="utf-8"))
        preview = db.restore_preview(backup, mode="add-missing")
        require("restore preview is valid", preview["valid"])
        require("restore preview default remains add missing", preview["default_mode"] == "add-missing")
        require("restore preview stages include background", "background_restore" in preview["stages"])
    db.record_audit_event(
        "role_change",
        actor_role="admin",
        target_type="user",
        target_id="fixture-user",
        summary="Role changed",
        metadata={"chapter_text": "do not store", "token": "secret-token", "safe_count": 2},
    )
    event = db.audit_events(limit=1)[0]
    require("audit redacts chapter text", event["metadata"]["chapter_text"] == "[redacted]")
    require("audit redacts token", event["metadata"]["token"] == "[redacted]")
    require("audit preserves safe metadata", event["metadata"]["safe_count"] == 2)
    return {"restore_valid": preview["valid"], "audit_event": event["event_type"]}


def static_checks() -> dict[str, object]:
    main_py = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for route in (
        "/api/admin/backups/jobs",
        "/api/admin/backups/jobs/{job_id}",
        "/api/admin/backups/jobs/{job_id}/cancel",
        "/api/admin/audit-events",
    ):
        index = main_py.find(f'"{route}"')
        require(f"route present {route}", index >= 0)
        require(f"route admin protected {route}", "Depends(require_admin)" in main_py[index : index + 450])
    for text in (
        "Queue Backup Job",
        "/api/admin/backups/jobs",
        "Audit Log",
        "System Health",
        "Restore preview reports add, skip, overwrite, and invalid counts before any apply step.",
        "aggregate SQL only",
        "provider bodies",
    ):
        require(f"admin operations UI text present: {text}", text in app_js)
    return {"routes": 4, "ui": "passed"}


def main() -> None:
    results = {
        "manifest_repeated": repeated_manifest_fixture(),
        "background_backup": background_backup_fixture(),
        "backup_cancel": backup_cancel_fixture(),
        "restore_and_audit": restore_and_audit_fixture(),
        "static": static_checks(),
        "no_openai_key": not bool(os.getenv("OPENAI_API_KEY")),
        "production_database_url": bool(os.getenv("DATABASE_URL")),
    }
    require("OpenAI disabled", results["no_openai_key"])
    require("production DATABASE_URL not used", not results["production_database_url"])
    print(json.dumps({"ok": True, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
