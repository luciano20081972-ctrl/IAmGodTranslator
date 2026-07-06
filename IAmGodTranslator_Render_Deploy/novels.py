from __future__ import annotations

import logging
import os
import hmac
import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.backup_jobs import BackupJobManager
from app.database import AppDatabase
from app.long_jobs import LongJobManager
from app.novels import NovelManager
from app.services import PROJECT_ROOT, TranslationService
from app.storage import SupabaseStorage


load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

app = FastAPI(title="IAmGodTranslator", version="2.0.0")
service = TranslationService()
novels = NovelManager(service)
database = AppDatabase(service.data_dir)
database_error: str | None = None

try:
    database.initialize()
except Exception as exc:  # pragma: no cover - public pages should stay up if the DB is unhealthy.
    database_error = str(exc)
    logging.getLogger(__name__).warning("Database initialization failed: %s", exc)
    if database.backend == "postgres":
        fallback_warning = (
            "Postgres DATABASE_URL failed, so the app is using SQLite fallback. "
            "If this is Supabase on Render, use the Supabase pooler/Supavisor connection string instead of the direct IPv6 connection string."
        )
        try:
            database = AppDatabase(service.data_dir, force_sqlite=True)
            database.warning = fallback_warning
            database.initialize()
            database_error = None
            logging.getLogger(__name__).warning(fallback_warning)
        except Exception as fallback_exc:
            database_error = f"{exc}; SQLite fallback failed: {fallback_exc}"
            logging.getLogger(__name__).warning("SQLite database fallback failed: %s", fallback_exc)

backup_jobs = BackupJobManager(service.data_dir, novels, database, os.getenv("STORAGE_BACKEND", "local").lower())
long_jobs = LongJobManager(service.data_dir)
RECOVERY_STATE: dict[str, object] = {"last_action": None, "last_dry_run_result": None, "selected_backup": None, "restore_job_id": None, "recommended_next_action": None}

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ADMIN_COOKIE = "igt_admin"
AUTH_COOKIE = "gt_session"
GOOGLE_STATE_COOKIE = "gt_google_state"
REQUIRED_STORAGE_FOLDERS = ("novels", "originals", "references", "ai_translations", "prompts", "backups", "uploads", "covers", "settings", "exports", "logs")
BACKUP_DISABLED_MESSAGE = "Legacy synchronous full backup/restore is disabled on Render Free. Use Admin Backups for async full backup and restore jobs."


def start_chapter_index_job(novel_id: str) -> dict[str, object]:
    active = long_jobs.active("chapter-index", novel_id=novel_id)
    if active:
        return active
    return long_jobs.start(
        "chapter-index",
        f"Chapter index rebuild for {novel_id}",
        lambda update, _state: novels.rebuild_chapter_index_progress(novel_id, update),
        metadata={"novel_id": novel_id},
    )


def start_storage_inventory_job(novel_id: str) -> dict[str, object]:
    active = long_jobs.active("storage-inventory", novel_id=novel_id)
    if active:
        return active
    return long_jobs.start(
        "storage-inventory",
        f"Storage inventory rebuild for {novel_id}",
        lambda update, _state: novels.rebuild_storage_inventory_progress(novel_id, update),
        metadata={"novel_id": novel_id},
    )


@app.on_event("startup")
async def startup_lightweight_hydration() -> None:
    try:
        for item in list(novels.iter_metadata())[:50]:
            novel_id = str(item.get("novel_id") or "")
            if not novel_id:
                continue
            novels.hydrate_lightweight_metadata(novel_id)
    except Exception as exc:
        logging.getLogger(__name__).warning("Startup lightweight hydration skipped: %s", exc.__class__.__name__)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


def admin_password() -> str | None:
    password = os.getenv("ADMIN_PASSWORD")
    return password if password else None


def admin_token() -> str:
    secret = os.getenv("SESSION_SECRET") or admin_password() or "admin-disabled"
    return hmac.new(secret.encode("utf-8"), b"i-am-god-translator-admin", hashlib.sha256).hexdigest()


def is_admin(request: Request) -> bool:
    password = admin_password()
    if not password:
        return False
    return hmac.compare_digest(request.cookies.get(ADMIN_COOKIE, ""), admin_token())


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Admin login required.")


def current_user(request: Request) -> dict[str, object] | None:
    if database_error:
        return None
    try:
        return database.user_for_session(request.cookies.get(AUTH_COOKIE))
    except Exception as exc:
        logging.getLogger(__name__).warning("Session lookup failed: %s", exc)
        return None


def require_user(request: Request) -> dict[str, object]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login required.")
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="Account disabled.")
    return user


def safe_email_notice(kind: str, email: str, token: str | None) -> dict[str, object]:
    smtp_ready = all(os.getenv(name) for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM"))
    if smtp_ready:
        logging.getLogger(__name__).info("%s email queued for %s", kind, email)
    else:
        logging.getLogger(__name__).info("%s email not sent because SMTP is not configured for %s", kind, email)
    return {"smtp_configured": smtp_ready, "dev_token_available": bool(token and not smtp_ready)}


def storage_health_report() -> dict[str, object]:
    data_dir = service.data_dir.resolve()
    configured = os.getenv("DATA_DIR")
    warnings: list[str] = []

    if configured and Path(configured).name.lower() == "date":
        warnings.append("DATA_DIR appears to be set to 'date'. Use DATA_DIR=/var/data/godtranslator on Render.")
    if os.getenv("RENDER") and not str(data_dir).replace("\\", "/").startswith("/var/data"):
        warnings.append("Render production storage is not under /var/data. Add a persistent disk and set DATA_DIR=/var/data/godtranslator.")
    if database_error:
        warnings.append(f"Database warning: {database_error}")
    if database.warning:
        warnings.append(database.warning)
    if os.getenv("DATABASE_URL", "").strip().startswith(("postgres://", "postgresql://")):
        warnings.append("If DATABASE_URL uses a direct IPv6 Supabase connection, Render may fail with Network is unreachable. Use Supabase Connection Pooling / Supavisor instead.")
    if (os.getenv("STORAGE_BACKEND") or "local").lower() != "supabase":
        warnings.append("Storage backend is local fallback. Render Free local files may disappear after restart/redeploy.")

    folders: dict[str, bool] = {}
    for name in REQUIRED_STORAGE_FOLDERS:
        folder = data_dir / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
            folders[name] = folder.is_dir()
        except OSError:
            folders[name] = False

    writable = False
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        test_file = data_dir / ".storage-write-test"
        test_file.write_text("ok", encoding="utf-8")
        writable = test_file.read_text(encoding="utf-8") == "ok"
        test_file.unlink(missing_ok=True)
    except OSError as exc:
        warnings.append(f"Storage write test failed: {exc.__class__.__name__}")

    def count(pattern: str) -> int:
        try:
            return sum(1 for path in data_dir.rglob(pattern) if path.is_file())
        except OSError:
            return 0

    local_cache_counts = {
        "originals": count("original/*.txt") + count("originals/*.txt"),
        "references": count("reference/*.txt") + count("references/*.txt"),
        "ai_translations": count("ai/*.txt") + count("english/*.txt") + count("ai_translations/*.txt"),
        "prompts": count("prompts/*.txt"),
        "backups": count("*.zip"),
        "covers_uploads": count("cover.*") + count("covers/*") + count("uploads/*"),
    }
    supabase_counts: dict[str, object] = {}
    canonical_supabase_counts: dict[str, object] = {}
    legacy_supabase_counts: dict[str, object] = {}
    active_counts: dict[str, object] = {}
    backup_zips_found: list[object] = []
    recommended_recovery_action = "none"
    recommended_recovery_label = "No recovery needed."
    recommended_recovery_steps: list[str] = []
    try:
        for item in novels.iter_metadata():
            novel_id = str(item["novel_id"])
            supabase_counts[novel_id] = novels.remote_counts(novel_id).get("counts", {}) if novels.remote is not None else {}
            category_counts = novels.remote_category_counts(novel_id) if novels.remote is not None else {"canonical": {}, "legacy": {}}
            canonical_supabase_counts[novel_id] = category_counts.get("canonical", {})
            legacy_supabase_counts[novel_id] = category_counts.get("legacy", {})
            active_counts[novel_id] = novels.active_counts(novel_id)
        if novels.remote is not None:
            backup_zips_found = novels.supabase_backup_zips()
    except Exception as exc:
        warnings.append(f"Count hydration warning: {exc.__class__.__name__}")
    has_active_counts = any(sum(int(v or 0) for v in counts.values() if isinstance(v, int)) for counts in active_counts.values())
    has_canonical_counts = any(sum(int(v or 0) for v in counts.values()) for counts in canonical_supabase_counts.values())
    has_legacy_counts = any(sum(int(v or 0) for v in counts.values()) for counts in legacy_supabase_counts.values())
    has_local_chapter_files = any(int(local_cache_counts.get(key) or 0) for key in ("originals", "references", "ai_translations"))
    counts_without_readable_files = has_active_counts and not has_local_chapter_files and not has_canonical_counts and not has_legacy_counts
    if novels.remote is not None and any(sum(int(v or 0) for v in counts.values() if isinstance(v, int)) for counts in supabase_counts.values()) and not any(local_cache_counts.values()):
        warnings.append("Local cache is empty but Supabase has files. The app is using Supabase/database counts and can rebuild the local cache on demand.")
    if has_local_chapter_files or has_canonical_counts:
        recommended_recovery_action = "none"
        recommended_recovery_label = "Supabase live data ready. No restore needed."
        recommended_recovery_steps = ["Open the library", "Read chapters normally", "Use Full Backup only for explicit admin backup jobs"]
    elif novels.remote is not None and has_legacy_counts and not has_canonical_counts:
        warnings.append("Canonical chapter folders are empty, but legacy Supabase data/backups were found.")
        warnings.append("Files found in legacy Supabase paths. Migration recommended.")
        recommended_recovery_action = "migrate_legacy_paths"
        recommended_recovery_label = "Legacy Supabase files were found. Run migration dry-run."
        recommended_recovery_steps = ["Run Deep Scan Supabase", "Run Migrate Legacy Paths dry-run", "If files are listed, confirm migration", "Rebuild Supabase Index", "Refresh Novel Data"]
    elif counts_without_readable_files:
        warnings.append("Counts exist, but readable chapter files are missing. Restore from Supabase backup is required.")
        recommended_recovery_action = "restore_from_supabase_backup"
        recommended_recovery_label = "Counts exist, but readable chapter files are missing. Restore from Supabase backup is required."
        recommended_recovery_steps = ["List Supabase backups", "Dry-run the newest backup", "Confirm online restore", "Rebuild Supabase index", "Refresh novel data"]
    elif backup_zips_found and not has_canonical_counts:
        recommended_recovery_action = "restore_from_supabase_backup"
        recommended_recovery_label = "Restore From Supabase Backup"
        recommended_recovery_steps = ["List Supabase backups", "Dry-run the newest backup", "Confirm online restore", "Rebuild Supabase index", "Refresh novel data"]

    report = service.storage_status()
    report.update(
        {
            "configured_data_dir": configured or "data",
            "resolved_data_dir": str(data_dir),
            "writable": writable,
            "warnings": warnings,
            "folders": folders,
            "counts": local_cache_counts,
            "local_cache_counts": local_cache_counts,
            "supabase_counts": supabase_counts,
            "canonical_supabase_counts": canonical_supabase_counts,
            "legacy_supabase_counts": legacy_supabase_counts,
            "database_counts": {},
            "active_counts_used_by_app": active_counts,
            "backup_zips_found": backup_zips_found,
            "recommended_recovery_action": recommended_recovery_action,
            "recommended_recovery_label": recommended_recovery_label,
            "recommended_recovery_steps": recommended_recovery_steps,
            "latest_recovery_state": RECOVERY_STATE,
            "database": database.status(),
        }
    )
    return report


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_local_data() -> dict[str, object]:
    destination = service.data_dir.resolve()
    source_candidates = [
        PROJECT_ROOT / "date",
        PROJECT_ROOT / "data",
        PROJECT_ROOT / "Archive",
        service.data_dir,
    ]
    copied = skipped = conflicts = 0
    errors: list[str] = []
    checked: list[str] = []
    destination.mkdir(parents=True, exist_ok=True)

    for source in dict.fromkeys(path.resolve() for path in source_candidates if path.exists()):
        checked.append(str(source))
        if source == destination or destination in source.parents:
            skipped += 1
            continue
        for file in source.rglob("*"):
            if not file.is_file():
                continue
            try:
                relative = file.relative_to(source)
                target = destination / relative
                if target.exists():
                    if file_digest(file) == file_digest(target):
                        skipped += 1
                    else:
                        conflicts += 1
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
                copied += 1
            except OSError as exc:
                errors.append(f"{file}: {exc.__class__.__name__}")

    return {"source_folders_checked": checked, "destination": str(destination), "copied": copied, "skipped_existing": skipped, "conflicts": conflicts, "errors": errors}


def storage_cleanup_report(dry_run: bool = True, retention_days: int = 7) -> dict[str, object]:
    data_dir = service.data_dir.resolve()
    cutoff = time.time() - max(1, retention_days) * 86400
    allowed_roots = [data_dir / "exports", data_dir / "backup_jobs", data_dir / "logs"]
    report: dict[str, object] = {
        "ok": True,
        "dry_run": dry_run,
        "retention_days": retention_days,
        "would_delete": [],
        "deleted": [],
        "kept": [],
        "total_size": 0,
        "warnings": ["Cleanup never deletes active novels, chapters, translations, covers, metadata, counts, or the latest successful backup."],
        "latest_backup_protected": True,
        "active_data_protected": True,
    }
    for root in allowed_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                item = {"path": str(path.relative_to(data_dir)), "size": stat.st_size}
                if stat.st_mtime <= cutoff or path.suffix.lower() in {".tmp", ".log"}:
                    report["total_size"] = int(report["total_size"]) + stat.st_size
                    if dry_run:
                        report["would_delete"].append(item)
                    else:
                        path.unlink(missing_ok=True)
                        report["deleted"].append(item)
                else:
                    report["kept"].append(item)
            except OSError as exc:
                report["warnings"].append(f"{path.name}: {exc.__class__.__name__}")
    return report


@app.middleware("http")
async def cache_control_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path

    if path in {"/", "/index.html", "/service-worker.js"}:
        response.headers["Cache-Control"] = "no-store, max-age=0"
    elif path in {"/static/app.js", "/static/styles.css"}:
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"

    return response


@app.on_event("startup")
async def resume_jobs() -> None:
    resumed = service.resume_incomplete_jobs() + novels.resume_incomplete_jobs()
    if resumed:
        logging.getLogger(__name__).info("Resumed %s incomplete translation job(s)", resumed)


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    return FileResponse(TEMPLATE_DIR / "index.html")


@app.head("/", include_in_schema=False)
async def head_home() -> Response:
    return Response(status_code=200)


@app.get("/manifest.json", include_in_schema=False)
async def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "service-worker.js", media_type="application/javascript")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/app")
async def app_info() -> dict[str, object]:
    return novels.app_settings()


@app.get("/api/app-icon")
async def app_icon() -> FileResponse:
    icon = novels.app_icon_path()
    if icon is None:
        raise HTTPException(status_code=404, detail="App icon not found.")
    return FileResponse(icon)


@app.get("/api/admin/status")
async def admin_status(request: Request) -> dict[str, object]:
    return {"enabled": bool(admin_password()), "authenticated": is_admin(request)}


@app.post("/api/admin/login")
async def admin_login(request: Request, response: Response, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    password = admin_password()
    if not password:
        raise HTTPException(status_code=403, detail="Admin login is disabled because ADMIN_PASSWORD is not set.")
    if not hmac.compare_digest(str(payload.get("password") or ""), password):
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    response.set_cookie(ADMIN_COOKIE, admin_token(), httponly=True, secure=request.url.scheme == "https", samesite="lax")
    return {"enabled": True, "authenticated": True}


@app.post("/api/admin/logout")
async def admin_logout(response: Response) -> dict[str, object]:
    response.delete_cookie(ADMIN_COOKIE)
    return {"authenticated": False}


@app.post("/api/admin/app-icon")
async def upload_app_icon(request: Request, icon: Annotated[UploadFile, File(description="App/library icon image")]) -> JSONResponse:
    require_admin(request)
    try:
        return JSONResponse(await novels.upload_app_icon(icon), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/admin/app-settings")
async def update_app_settings(request: Request, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    return novels.update_app_settings(payload)


@app.post("/api/admin/app-settings/reset")
async def reset_app_settings(request: Request) -> dict[str, object]:
    require_admin(request)
    return novels.reset_app_settings()


@app.post("/api/auth/register")
async def auth_register(request: Request, response: Response, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    try:
        user, token = database.create_user(
            str(payload.get("email") or ""),
            str(payload.get("username") or ""),
            str(payload.get("password") or ""),
        )
        session, expires_at = database.create_session(str(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=400, detail="An account with that email already exists.") from exc
        raise

    response.set_cookie(AUTH_COOKIE, session, httponly=True, secure=request.url.scheme == "https", samesite="lax", expires=expires_at)
    notice = safe_email_notice("verification", str(user["email"]), token)
    return {"user": user, "email_verification_required": True, "email": notice}


@app.post("/api/auth/login")
async def auth_login(request: Request, response: Response, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    user = database.authenticate(str(payload.get("email") or ""), str(payload.get("password") or ""))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    session, expires_at = database.create_session(str(user["id"]))
    response.set_cookie(AUTH_COOKIE, session, httponly=True, secure=request.url.scheme == "https", samesite="lax", expires=expires_at)
    return {"user": user}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response) -> dict[str, object]:
    database.delete_session(request.cookies.get(AUTH_COOKIE))
    response.delete_cookie(AUTH_COOKIE)
    return {"authenticated": False}


@app.get("/api/auth/me")
async def auth_me(request: Request) -> dict[str, object]:
    user = current_user(request)
    return {"authenticated": bool(user), "user": user}


@app.post("/api/auth/resend-verification")
async def auth_resend_verification(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {"ok": True, "email": safe_email_notice("verification", str(user["email"]), None)}


@app.get("/api/auth/verify-email")
async def auth_verify_email(token: str) -> dict[str, object]:
    if not token or not database.verify_email(token):
        raise HTTPException(status_code=400, detail="Verification link is invalid or expired.")
    return {"verified": True}


@app.post("/api/auth/request-password-reset")
async def auth_request_password_reset(payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    email = str(payload.get("email") or "").strip().lower()
    token = database.create_reset_token(email) if email else None
    notice = safe_email_notice("password reset", email or "unknown", token)
    return {"ok": True, "message": "If that email exists, a password reset link will be sent.", "email": notice}


@app.post("/api/auth/reset-password")
async def auth_reset_password(payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    try:
        ok = database.reset_password(str(payload.get("token") or ""), str(payload.get("password") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=400, detail="Reset link is invalid or expired.")
    return {"reset": True}


@app.get("/api/auth/google/status")
async def google_status() -> dict[str, object]:
    configured = all(os.getenv(name) for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"))
    return {"configured": configured, "enabled": configured, "message": "Google login is available." if configured else "Google login is not configured yet."}


@app.get("/auth/google/login")
async def google_login(request: Request):
    configured = all(os.getenv(name) for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"))
    if not configured:
        return JSONResponse({"ok": False, "enabled": False, "detail": "Google login is not configured yet."}, status_code=503)
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}", status_code=302)
    response.set_cookie(GOOGLE_STATE_COOKIE, state, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=600)
    return response


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    target = "/#/library"
    if error:
        target += "?auth_error=google"
        return RedirectResponse(target, status_code=302)
    expected_state = request.cookies.get(GOOGLE_STATE_COOKIE)
    response = RedirectResponse(target, status_code=302)
    response.delete_cookie(GOOGLE_STATE_COOKIE)
    if not code or not state or not expected_state or not hmac.compare_digest(state, expected_state):
        response.headers["Location"] = "/#/library?auth_error=google_state"
        return response
    try:
        token_request = UrlRequest(
            "https://oauth2.googleapis.com/token",
            data=urlencode({
                "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
                "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
                "grant_type": "authorization_code",
                "code": code,
            }).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(token_request, timeout=15) as token_response:
            token_data = json.loads(token_response.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Google token response did not include an access token.")
        user_request = UrlRequest("https://openidconnect.googleapis.com/v1/userinfo", headers={"Authorization": f"Bearer {access_token}"})
        with urlopen(user_request, timeout=15) as user_response:
            user_data = json.loads(user_response.read().decode("utf-8"))
        email = str(user_data.get("email") or "")
        username = str(user_data.get("name") or user_data.get("given_name") or email.split("@", 1)[0])
        user = database.get_or_create_oauth_user(email, username)
        session, expires_at = database.create_session(str(user["id"]))
        response.set_cookie(AUTH_COOKIE, session, httponly=True, secure=request.url.scheme == "https", samesite="lax", expires=expires_at)
        return response
    except Exception as exc:
        logging.getLogger(__name__).warning("Google login failed: %s", exc.__class__.__name__)
        response.headers["Location"] = "/#/library?auth_error=google"
        return response


@app.get("/api/storage")
async def storage_status() -> dict[str, object]:
    status = storage_health_report()
    status["novels"] = len(list(novels.iter_metadata()))
    status["backend"] = os.getenv("STORAGE_BACKEND", "local").lower()
    status["supabase_enabled"] = novels.remote is not None
    status["supabase"] = novels.remote_health()
    status["database_reachable"] = database_error is None
    return status


@app.get("/api/bootstrap")
async def bootstrap(request: Request) -> dict[str, object]:
    storage = storage_health_report()
    canonical_counts = storage.get("canonical_supabase_counts", {})
    active_counts = storage.get("active_counts_used_by_app", {})
    canonical_data_exists = any(sum(int(v or 0) for v in counts.values()) for counts in canonical_counts.values() if isinstance(counts, dict))
    active_data_exists = any(sum(int(v or 0) for v in counts.values() if isinstance(v, int)) for counts in active_counts.values() if isinstance(counts, dict))
    restore_needed = storage.get("recommended_recovery_action") == "restore_from_supabase_backup"
    if restore_needed:
        active_data_exists = False
    return {
        "ok": True,
        "app_version": app.version,
        "admin": {"enabled": bool(admin_password()), "authenticated": is_admin(request)},
        "user": current_user(request),
        "novels": novels.list_novels(),
        "storage": {
            "backend": os.getenv("STORAGE_BACKEND", "local").lower(),
            "supabase_enabled": novels.remote is not None,
            "active_counts_used_by_app": storage.get("active_counts_used_by_app", {}),
            "canonical_data_exists": canonical_data_exists,
            "active_data_exists": active_data_exists,
            "restore_needed": restore_needed,
            "recommended_recovery_action": storage.get("recommended_recovery_action"),
            "recommended_recovery_label": storage.get("recommended_recovery_label"),
            "warnings": storage.get("warnings", []),
        },
        "recovery": RECOVERY_STATE,
        "message": "Bootstrap is lightweight. It does not run backup, restore, or download chapter text.",
    }


@app.get("/api/admin/recovery/status")
async def recovery_status(request: Request) -> dict[str, object]:
    require_admin(request)
    job = backup_jobs.get_job(str(RECOVERY_STATE.get("restore_job_id"))) if RECOVERY_STATE.get("restore_job_id") else None
    storage = storage_health_report()
    active_counts = storage.get("active_counts_used_by_app", {})
    live_ready = storage.get("recommended_recovery_action") != "restore_from_supabase_backup" and any(sum(int(v or 0) for v in counts.values() if isinstance(v, int)) for counts in active_counts.values() if isinstance(counts, dict))
    return {"ok": True, "recovery": {**RECOVERY_STATE, "restore_job_status": job, "live_data_ready": live_ready, "active_counts": active_counts, "recommended_next_action": "none" if live_ready else RECOVERY_STATE.get("recommended_next_action")}, "storage": storage}


@app.post("/api/admin/storage/migrate-local-data")
async def migrate_storage(request: Request) -> dict[str, object]:
    require_admin(request)
    return migrate_local_data()


@app.post("/api/admin/storage/cleanup/dry-run")
async def cleanup_storage_dry_run(request: Request, payload: Annotated[dict[str, object] | None, Body()] = None) -> dict[str, object]:
    require_admin(request)
    retention_days = int((payload or {}).get("retention_days") or 7)
    return storage_cleanup_report(dry_run=True, retention_days=retention_days)


@app.post("/api/admin/storage/cleanup/run")
async def cleanup_storage_run(request: Request, payload: Annotated[dict[str, object] | None, Body()] = None) -> dict[str, object]:
    require_admin(request)
    payload = payload or {}
    if not bool(payload.get("confirm")):
        raise HTTPException(status_code=400, detail="Cleanup requires confirm=true.")
    retention_days = int(payload.get("retention_days") or 7)
    return storage_cleanup_report(dry_run=False, retention_days=retention_days)


@app.get("/api/admin/content/diagnostic")
async def admin_content_diagnostic(request: Request, novel_id: str = "i-am-god", chapter: int | None = None) -> dict[str, object]:
    require_admin(request)
    if chapter is None:
        return novels.global_content_diagnostic(novel_id)
    if chapter < 1:
        raise HTTPException(status_code=400, detail="Chapter must be 1 or greater.")
    return novels.content_diagnostic(novel_id, chapter)


@app.post("/api/admin/storage/sync-supabase")
async def sync_storage_to_supabase(request: Request) -> dict[str, object]:
    require_admin(request)
    if novels.remote is None:
        raise HTTPException(status_code=400, detail="Supabase storage is not enabled.")
    return novels.sync_all_to_remote()


@app.post("/api/admin/storage/migrate-to-supabase")
async def migrate_to_supabase(request: Request) -> dict[str, object]:
    require_admin(request)
    job = long_jobs.start("migrate-local-to-supabase", "Local to Supabase migration", lambda update, _state: novels.migrate_to_supabase_progress(update))
    return {"ok": True, "job_id": job["job_id"], "status": "queued", "message": "Migration is running as a background job. Poll the job status instead of starting again."}


@app.post("/api/admin/storage/migrate-local-to-supabase/start")
async def migrate_local_to_supabase_start(request: Request) -> JSONResponse:
    require_admin(request)
    job = long_jobs.start("migrate-local-to-supabase", "Local to Supabase migration", lambda update, _state: novels.migrate_to_supabase_progress(update))
    return JSONResponse({"ok": True, "job_id": job["job_id"], "status": "queued"}, status_code=202)


@app.get("/api/admin/storage/migrate-local-to-supabase/jobs/{job_id}")
async def migrate_local_to_supabase_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = long_jobs.read("migrate-local-to-supabase", job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Migration job not found.")
    return job


@app.get("/api/admin/storage/deep-discovery")
async def deep_discovery(request: Request, novel_id: str = "i-am-god") -> dict[str, object]:
    require_admin(request)
    return novels.deep_discovery(novel_id)


@app.get("/api/admin/storage/inventory/summary")
async def storage_inventory_summary(request: Request, novel_id: str = "i-am-god") -> dict[str, object]:
    require_admin(request)
    return novels.storage_inventory_summary(novel_id, use_cached=False)


@app.post("/api/admin/storage/inventory/rebuild/start")
async def storage_inventory_rebuild_start(request: Request, payload: Annotated[dict[str, object] | None, Body()] = None) -> JSONResponse:
    require_admin(request)
    novel_id = str((payload or {}).get("novel_id") or "i-am-god")
    job = start_storage_inventory_job(novel_id)
    return JSONResponse({"ok": True, "job_id": job["job_id"], "status": job.get("status", "queued"), "novel_id": novel_id}, status_code=202)


@app.get("/api/admin/storage/inventory/jobs/{job_id}")
async def storage_inventory_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = long_jobs.read("storage-inventory", job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Storage inventory job not found.")
    return job


@app.post("/api/admin/storage/migrate-legacy-paths")
async def migrate_legacy_paths(request: Request, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    try:
        return novels.migrate_legacy_paths(
            str(payload.get("novel_id") or "i-am-god"),
            dry_run=bool(payload.get("dry_run", True)),
            confirm=bool(payload.get("confirm", False)),
            overwrite=bool(payload.get("overwrite", False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/backups/supabase")
async def list_supabase_backups(request: Request, novel_id: str = "i-am-god") -> dict[str, object]:
    require_admin(request)
    return {"ok": True, "backups": novels.supabase_backup_zips(novel_id)}


@app.post("/api/admin/backups/restore-from-supabase")
async def restore_from_supabase_backup(request: Request, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    require_admin(request)
    bucket = str(payload.get("bucket") or "novel-files")
    path = str(payload.get("path") or "").strip()
    if not path.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Choose a Supabase backup ZIP path.")
    dry_run = bool(payload.get("dry_run", True))
    if not dry_run and not bool(payload.get("confirm", False)):
        raise HTTPException(status_code=400, detail="Real restore requires confirm=true.")
    try:
        remote = novels.remote if novels.remote is not None and getattr(novels.remote, "bucket", "") == bucket else SupabaseStorage(bucket=bucket)
        data = remote.read_bytes(path)
        if data is None:
            raise HTTPException(status_code=404, detail="Supabase backup ZIP not found.")
        job = backup_jobs.start_full_restore(data, Path(path).name, dry_run=dry_run, conflict_mode=str(payload.get("conflict_mode") or "write_missing_only"))
        selected = {"bucket": bucket, "path": path, "filename": Path(path).name}
        RECOVERY_STATE.update({
            "last_action": "online_restore_dry_run" if dry_run else "online_restore_confirm",
            "selected_backup": selected,
            "restore_job_id": job.get("job_id"),
            "recommended_next_action": "confirm_online_restore" if dry_run else "rebuild_index",
        })
        if dry_run:
            RECOVERY_STATE["last_dry_run_result"] = job
        return JSONResponse(job, status_code=202)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/admin/index/rebuild")
async def rebuild_index(request: Request, payload: Annotated[dict[str, object] | None, Body()] = None) -> dict[str, object]:
    require_admin(request)
    novel_id = str((payload or {}).get("novel_id") or "").strip() or None
    return novels.rebuild_index(novel_id)


@app.post("/api/admin/novels/{novel_id}/hydrate-from-supabase")
async def hydrate_novel_from_supabase(request: Request, novel_id: str) -> dict[str, object]:
    require_admin(request)
    if novels.remote is None:
        raise HTTPException(status_code=400, detail="Supabase storage is not enabled.")
    novels.hydrate_remote_metadata(novel_id)
    return novels.rebuild_index(novel_id)


@app.post("/api/admin/novels/{novel_id}/rebuild-chapter-index")
async def rebuild_chapter_index(request: Request, novel_id: str) -> dict[str, object]:
    require_admin(request)
    return novels.rebuild_chapter_index_report(novel_id)


@app.post("/api/admin/novels/{novel_id}/rebuild-chapter-index/start")
async def rebuild_chapter_index_start(request: Request, novel_id: str) -> JSONResponse:
    require_admin(request)
    job = start_chapter_index_job(novel_id)
    return JSONResponse({"ok": True, "job_id": job.get("job_id"), "status": job.get("status", "queued"), "novel_id": novel_id}, status_code=202)


@app.get("/api/admin/novels/{novel_id}/rebuild-chapter-index/jobs/{job_id}")
async def rebuild_chapter_index_job(request: Request, novel_id: str, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = long_jobs.read("chapter-index", job_id)
    if job is None or job.get("novel_id") != novel_id:
        raise HTTPException(status_code=404, detail="Chapter index rebuild job not found.")
    return job


@app.post("/api/admin/storage/clear-backup-state")
async def clear_backup_state(request: Request) -> dict[str, object]:
    require_admin(request)
    cleared = novels.clear_backup_state()
    for path in (service.data_dir / "storage_state.json", service.data_dir / "backup_state.json", service.data_dir / "restore_state.json", service.data_dir / "undo_restore_state.json"):
        if path.exists() and path.is_file():
            path.unlink()
            cleared["cleared"] = int(cleared.get("cleared", 0)) + 1
    return {"ok": True, **cleared}


@app.post("/api/admin/backups/full/start")
async def start_full_backup(request: Request) -> JSONResponse:
    require_admin(request)
    return JSONResponse(backup_jobs.start_full_backup(), status_code=202)


@app.post("/api/admin/backups/full/restore")
async def start_full_restore(
    request: Request,
    backup: Annotated[UploadFile, File(description="Full backup ZIP")],
    dry_run: Annotated[bool, Form()] = True,
    conflict_mode: Annotated[str, Form()] = "write_missing_only",
) -> JSONResponse:
    require_admin(request)
    if not backup.filename or not backup.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Restore upload must be a .zip file.")
    try:
        return JSONResponse(backup_jobs.start_full_restore(await backup.read(), backup.filename, dry_run=dry_run, conflict_mode=conflict_mode), status_code=202)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/backups/jobs")
async def list_backup_jobs(request: Request) -> dict[str, object]:
    require_admin(request)
    return {"ok": True, "jobs": backup_jobs.list_jobs()}


@app.get("/api/admin/backups/jobs/{job_id}")
async def get_backup_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = backup_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Backup job not found.")
    return job


@app.post("/api/admin/backups/jobs/{job_id}/cancel")
async def cancel_backup_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = backup_jobs.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Backup job not found.")
    return job


@app.get("/api/admin/backups/latest")
async def latest_backup(request: Request) -> dict[str, object]:
    require_admin(request)
    return {"ok": True, "backup": backup_jobs.latest()}


@app.get("/api/admin/backups/jobs/{job_id}/download")
async def download_backup_job(request: Request, job_id: str) -> FileResponse:
    require_admin(request)
    job = backup_jobs.get_job(job_id)
    if job is None or job.get("status") != "complete" or not job.get("backup_file"):
        raise HTTPException(status_code=404, detail="Completed backup file not found.")
    path = Path(str(job["backup_file"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Backup file is no longer available locally.")
    return FileResponse(path, media_type="application/zip", filename=path.name)


@app.get("/api/me/library")
async def my_library(request: Request) -> dict[str, object]:
    user = require_user(request)
    return database.library(str(user["id"]))


@app.get("/api/reading-history")
async def get_reading_history(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {"reading_history": database.library(str(user["id"]))["reading_history"]}


@app.post("/api/reading-history")
async def save_reading_history(request: Request, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    user = require_user(request)
    try:
        database.save_history(str(user["id"]), str(payload["novel_id"]), int(payload["chapter_number"]), str(payload.get("mode") or "ai"))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid reading history payload.") from exc
    return {"saved": True}


@app.post("/api/novels/{novel_id}/bookmark")
async def add_novel_bookmark(request: Request, novel_id: str) -> dict[str, object]:
    user = require_user(request)
    database.set_novel_bookmark(str(user["id"]), novel_id, True)
    return {"bookmarked": True}


@app.delete("/api/novels/{novel_id}/bookmark")
async def remove_novel_bookmark(request: Request, novel_id: str) -> dict[str, object]:
    user = require_user(request)
    database.set_novel_bookmark(str(user["id"]), novel_id, False)
    return {"bookmarked": False}


@app.post("/api/novels/{novel_id}/rating")
async def set_novel_rating(request: Request, novel_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    user = require_user(request)
    try:
        rating = int(payload.get("rating") or 0)
        database.set_rating(str(user["id"]), novel_id, rating)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"rating": rating}


@app.get("/api/novels/{novel_id}/rating")
async def get_novel_rating(request: Request, novel_id: str) -> dict[str, object]:
    user = require_user(request)
    return {"rating": database.rating_for(str(user["id"]), novel_id)}


@app.post("/api/novels/{novel_id}/chapters/{chapter_number}/bookmark")
async def add_chapter_bookmark(request: Request, novel_id: str, chapter_number: int) -> dict[str, object]:
    user = require_user(request)
    database.set_chapter_bookmark(str(user["id"]), novel_id, chapter_number, True)
    return {"bookmarked": True}


@app.delete("/api/novels/{novel_id}/chapters/{chapter_number}/bookmark")
async def remove_chapter_bookmark(request: Request, novel_id: str, chapter_number: int) -> dict[str, object]:
    user = require_user(request)
    database.set_chapter_bookmark(str(user["id"]), novel_id, chapter_number, False)
    return {"bookmarked": False}


@app.get("/api/admin/novels/{novel_id}/content-audit")
async def content_audit(request: Request, novel_id: str) -> dict[str, object]:
    require_admin(request)
    return novels.content_audit(novel_id)


@app.post("/api/admin/novels/{novel_id}/repair-content-map")
async def repair_content_map(request: Request, novel_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    return novels.repair_content_map(novel_id, payload)


@app.get("/api/admin/users")
async def list_users(request: Request) -> dict[str, object]:
    require_admin(request)
    return {"users": database.users()}


@app.patch("/api/admin/users/{user_id}/role")
async def change_user_role(request: Request, user_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    try:
        user = database.update_user_role(user_id, str(payload.get("role") or "user"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": user}


@app.patch("/api/admin/users/{user_id}/disabled")
async def change_user_disabled(request: Request, user_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    user = database.set_user_disabled(user_id, bool(payload.get("disabled")))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": user}


@app.get("/api/jobs")
async def list_jobs(request: Request) -> dict[str, object]:
    require_admin(request)
    return {"jobs": service.list_jobs()}


@app.post("/api/jobs")
async def create_job(
    request: Request,
    chinese: Annotated[list[UploadFile], File(description="Chinese TXT files or ZIP archives")],
    references: Annotated[list[UploadFile] | None, File(description="Optional NovelFire reference TXT files or ZIP archives")] = None,
    max_total_budget: Annotated[str | None, Form()] = None,
    max_cost_per_chapter: Annotated[str | None, Form()] = None,
    stop_when_budget_reached: Annotated[bool, Form()] = True,
    test_chapter_only: Annotated[bool, Form()] = True,
    show_estimate_before_starting: Annotated[bool, Form()] = True,
    retry_failed_chapters: Annotated[int, Form()] = 1,
) -> JSONResponse:
    require_admin(request)
    try:
        job = await service.create_job(chinese, references, settings={"max_total_budget": max_total_budget, "max_cost_per_chapter": max_cost_per_chapter, "stop_when_budget_reached": stop_when_budget_reached, "test_chapter_only": test_chapter_only, "show_estimate_before_starting": show_estimate_before_starting, "retry_failed_chapters": retry_failed_chapters})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(job, status_code=201)


@app.get("/api/jobs/{job_id}")
async def get_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    try:
        job = service.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.post("/api/jobs/{job_id}/start")
async def start_job(request: Request, job_id: str) -> dict[str, str]:
    require_admin(request)
    if service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    service.start_job(job_id)
    return {"status": "queued"}


@app.post("/api/jobs/restore")
async def restore_job_backup(request: Request, backup: Annotated[UploadFile, File(description="Full job backup ZIP")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse({"ok": False, "error": BACKUP_DISABLED_MESSAGE}, status_code=409)


@app.get("/api/jobs/{job_id}/download")
async def download_job(request: Request, job_id: str) -> FileResponse:
    require_admin(request)
    zip_path = service.build_download_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No translated chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/jobs/{job_id}/prompts/download")
async def download_prompts(request: Request, job_id: str) -> FileResponse:
    require_admin(request)
    zip_path = service.build_prompts_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No saved prompts are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/jobs/{job_id}/backup")
async def download_job_backup(request: Request, job_id: str) -> FileResponse:
    require_admin(request)
    return JSONResponse({"ok": False, "error": BACKUP_DISABLED_MESSAGE}, status_code=409)


@app.get("/api/jobs/{job_id}/estimate-report")
async def download_estimate_report(request: Request, job_id: str) -> FileResponse:
    require_admin(request)
    report = service.estimate_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Estimate report not found.")
    return FileResponse(report, media_type="text/markdown; charset=utf-8", filename=report.name)


@app.get("/api/jobs/{job_id}/chapters/{chapter}/download")
async def download_chapter(job_id: str, chapter: int) -> FileResponse:
    output = service.chapter_output(job_id, chapter)
    if output is None:
        raise HTTPException(status_code=404, detail="Translated chapter not found.")
    return FileResponse(output, media_type="text/plain; charset=utf-8", filename=output.name)


@app.get("/api/novels")
async def list_novels() -> dict[str, object]:
    return {"novels": novels.list_novels()}


@app.post("/api/novels")
async def create_novel(request: Request, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    require_admin(request)
    return JSONResponse(novels.create_novel(str(payload.get("title") or "Untitled Novel")), status_code=201)


@app.get("/api/novels/{novel_id}")
async def get_novel(novel_id: str) -> dict[str, object]:
    try:
        return novels.get_novel(novel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/novels/{novel_id}")
async def update_novel(request: Request, novel_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    require_admin(request)
    try:
        return novels.update_novel(novel_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/novels/{novel_id}")
async def delete_novel(request: Request, novel_id: str) -> dict[str, str]:
    require_admin(request)
    novels.delete_novel(novel_id)
    return {"status": "deleted"}


@app.get("/api/novels/{novel_id}/library")
async def get_library(novel_id: str) -> dict[str, object]:
    data = novels.library(novel_id)
    if data.get("chapter_index_status") in {"missing", "empty"}:
        counts = data.get("diagnostics", {}).get("counts", {}) if isinstance(data.get("diagnostics"), dict) else {}
        has_counts = max(int(counts.get("originals") or 0), int(counts.get("references") or 0), int(counts.get("ai_translations") or 0)) > 0
        if has_counts and novels.chapter_source_files_available(novel_id):
            job = start_chapter_index_job(novel_id)
            data["chapter_index_status"] = "rebuild_queued" if job.get("status") == "queued" else "rebuilding"
            data["chapter_index_job_id"] = job.get("job_id")
            data["message"] = "Chapter index is being prepared after wake."
    return data


@app.get("/api/novels/{novel_id}/chapters")
async def get_chapters(novel_id: str) -> dict[str, object]:
    return {"chapters": novels.chapters(novel_id)}


@app.get("/api/novels/{novel_id}/chapters/{chapter_number}")
async def get_chapter(novel_id: str, chapter_number: int) -> dict[str, object]:
    chapter = novels.chapter(novel_id, chapter_number)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return chapter


@app.get("/api/novels/{novel_id}/chapters/{chapter_number}/{kind}", response_model=None)
async def get_chapter_text(novel_id: str, chapter_number: int, kind: str) -> dict[str, object] | FileResponse:
    if kind == "download":
        chapter = novels.chapter(novel_id, chapter_number)
        if chapter is None or not chapter.get("output_path"):
            raise HTTPException(status_code=404, detail="Translated chapter not found.")
        return FileResponse(chapter["output_path"], media_type="text/plain; charset=utf-8", filename=f"{chapter_number:04d}.txt")
    if kind not in {"english", "original", "reference", "prompt"}:
        raise HTTPException(status_code=404, detail="Chapter view not found.")
    result = novels.chapter_text(novel_id, chapter_number, kind)
    if result is None:
        raise HTTPException(status_code=404, detail="Chapter not found.")
    return result


@app.post("/api/novels/{novel_id}/upload/original")
async def upload_original(request: Request, novel_id: str, original: Annotated[list[UploadFile], File(description="Original Story TXT files or ZIP archives")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse(await novels.upload_original(novel_id, original), status_code=201)


@app.post("/api/novels/{novel_id}/upload/reference")
async def upload_reference(request: Request, novel_id: str, reference: Annotated[list[UploadFile], File(description="Reference Translation TXT files or ZIP archives")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse(await novels.upload_reference(novel_id, reference), status_code=201)


@app.post("/api/novels/{novel_id}/import/ai-translations")
async def import_ai_translations(request: Request, novel_id: str, translated_zip: Annotated[UploadFile, File(description="AI translated chapters ZIP")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse(await novels.import_ai_translations(novel_id, translated_zip), status_code=201)


@app.post("/api/novels/{novel_id}/import/original")
async def import_original_zip(request: Request, novel_id: str, original_zip: Annotated[UploadFile, File(description="Original Story ZIP")]) -> JSONResponse:
    require_admin(request)
    try:
        return JSONResponse(await novels.import_original_zip(novel_id, original_zip), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/novels/{novel_id}/import/reference")
async def import_reference_zip(request: Request, novel_id: str, reference_zip: Annotated[UploadFile, File(description="Reference Translation ZIP")]) -> JSONResponse:
    require_admin(request)
    try:
        return JSONResponse(await novels.import_reference_zip(novel_id, reference_zip), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/novels/{novel_id}/cover")
async def upload_novel_cover(request: Request, novel_id: str, cover: Annotated[UploadFile, File(description="Novel cover image")]) -> JSONResponse:
    require_admin(request)
    try:
        return JSONResponse(await novels.upload_cover(novel_id, cover), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/novels/{novel_id}/cover")
async def get_novel_cover(novel_id: str) -> FileResponse:
    cover = novels.cover_path(novel_id)
    if cover is None:
        raise HTTPException(status_code=404, detail="Cover image not found.")
    return FileResponse(cover)


@app.post("/api/novels/{novel_id}/translate/batch")
async def create_novel_batch(request: Request, novel_id: str, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    require_admin(request)
    settings = dict(payload)
    start_now = bool(settings.pop("start_now", False))
    job = novels.create_batch(novel_id, settings)
    if start_now:
        novels.start_job(novel_id, job["job_id"])
    return JSONResponse(job, status_code=201)


@app.post("/api/novels/{novel_id}/jobs/{job_id}/start")
async def start_novel_job(request: Request, novel_id: str, job_id: str) -> dict[str, str]:
    require_admin(request)
    novels.start_job(novel_id, job_id)
    return {"status": "queued"}


def batch_novel_id(payload: dict[str, object] | None = None) -> str:
    value = str((payload or {}).get("novel_id") or "").strip()
    if value:
        return value
    items = novels.list_novels()
    return str(items[0]["novel_id"]) if items else "i-am-god"


@app.get("/api/batch/health")
async def batch_health(request: Request) -> dict[str, object]:
    novel_id = batch_novel_id()
    novel = novels.get_novel(novel_id)
    readiness = novels.read_translation_readiness(novel_id)
    warnings = []
    if not os.getenv("OPENAI_API_KEY"):
        warnings.append("OpenAI is not configured. Translation cannot start yet.")
    return {
        "ok": True,
        "enabled": True,
        "admin_authenticated": is_admin(request),
        "novel_id": novel_id,
        "model": os.getenv("OPENAI_MODEL") or novel.get("current_model") or "gpt-4o-mini",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "storage_backend": os.getenv("STORAGE_BACKEND", "local").lower(),
        "database_backend": database.status().get("backend"),
        "supports_estimate": True,
        "supports_queue": True,
        "supports_cancel": True,
        "supports_retry_failed": True,
        "default_concurrency": 1,
        "max_safe_concurrency": 3,
        "missing_only_default": True,
        "overwrite_default": False,
        "counts": novel.get("counts", {}),
        "readiness_cached": readiness is not None,
        "readiness_updated_at": readiness.get("updated_at") if readiness else None,
        "warnings": warnings,
        "message": "Batch health is available. Estimate and dry-run do not call OpenAI.",
    }


@app.post("/api/batch/readiness/start")
async def batch_readiness_start(request: Request, payload: Annotated[dict[str, object] | None, Body()] = None) -> JSONResponse:
    require_admin(request)
    selected = batch_novel_id(payload)
    job = long_jobs.start("translation-readiness", f"Translation readiness for {selected}", lambda update, _state: novels.build_translation_readiness(selected, update))
    return JSONResponse({"ok": True, "job_id": job["job_id"], "status": "queued", "novel_id": selected}, status_code=202)


@app.get("/api/batch/readiness/jobs/{job_id}")
async def batch_readiness_job(request: Request, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = long_jobs.read("translation-readiness", job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Translation readiness job not found.")
    return job


@app.get("/api/batch/readiness")
async def batch_readiness_status(request: Request, novel_id: str | None = None) -> dict[str, object]:
    require_admin(request)
    selected = novel_id or batch_novel_id()
    readiness = novels.read_translation_readiness(selected) or novels.fast_translation_readiness(selected)
    return {
        key: readiness.get(key)
        for key in ("ok", "novel_id", "source", "updated_at", "total_indexed", "original_readable", "ai_existing_readable", "needs_translation", "skipped_no_original", "skipped_already_translated")
    }


def batch_selection(novel_id: str, payload: dict[str, object]) -> dict[str, object]:
    start = int(payload.get("start_chapter") or 1)
    end = int(payload.get("end_chapter") or 999999)
    if start > end:
        raise ValueError("Start chapter must be less than or equal to end chapter.")
    batch_size = max(1, min(200, int(payload.get("batch_size") or 25)))
    missing_only = bool(payload.get("missing_only", True))
    overwrite = bool(payload.get("overwrite", False))
    readiness = novels.read_translation_readiness(novel_id)
    readiness_source = "cached_actual_text"
    if readiness is None:
        readiness = novels.fast_translation_readiness(novel_id)
        readiness_source = "chapter_index_fast"
    if readiness.get("ok") is False:
        raise ValueError(str(readiness.get("message") or "Translation readiness is not prepared yet."))
    records = [
        item for item in readiness.get("chapters", [])
        if start <= int(item.get("chapter") or 0) <= end
    ]
    chapters = [item for item in records if item.get("original_readable")]
    already = [item for item in records if item.get("ai_readable")]
    needs = [item for item in records if item.get("original_readable") and (overwrite or not missing_only or not item.get("ai_readable"))]
    selected = needs[:batch_size]
    missing_originals = [int(item.get("chapter") or 0) for item in records if not item.get("original_readable")]
    sample_missing_ai = [int(item.get("chapter") or 0) for item in records if item.get("original_readable") and not item.get("ai_readable")][:20]
    if not chapters:
        raise ValueError("No readable original chapter text was found. Run Content Diagnostic/Repair first.")
    estimated_input = 0
    estimated_output = 0
    for chapter in selected:
        text_len = int(chapter.get("characters") or 3500)
        estimated_input += max(400, text_len // 2)
        estimated_output += max(600, int(text_len * 0.65))
    low = (estimated_input / 1_000_000 * 0.15) + (estimated_output / 1_000_000 * 0.60)
    high = low * 1.75
    warnings = ["Estimate is approximate.", "Estimate does not call OpenAI.", "Estimate uses cached Translation Readiness. Rebuild readiness after imports/restores."]
    if readiness_source == "chapter_index_fast":
        warnings.append("No actual-text readiness cache exists yet. Rebuild Translation Readiness for stricter readable-file validation.")
    if missing_originals:
        warnings.append(f"{len(missing_originals)} chapter(s) in range have no readable Original Story file.")
    return {
        "novel_id": novel_id,
        "start_chapter": start,
        "end_chapter": end if end != 999999 else None,
        "total_selected": len(chapters),
        "already_translated": len(already),
        "missing_ai_translations": len(needs),
        "estimated_chapters_to_translate": len(selected),
        "original_chapters_indexed": len(records),
        "original_chapters_with_text": len(chapters),
        "original_readable": len(chapters),
        "ai_chapters_indexed": len(records),
        "ai_chapters_with_text": len(already),
        "ai_existing_readable": len(already),
        "already_translated_in_range": len(already),
        "chapters_ready_to_translate": len(selected),
        "needs_translation": len(needs),
        "max_chapters_to_translate_now": batch_size,
        "skipped_no_original": len(missing_originals),
        "skipped_already_translated": len(already),
        "empty_original_chapters": [],
        "missing_original_chapters": missing_originals[:50],
        "sample_missing_ai_chapters": sample_missing_ai,
        "paths_checked": [],
        "readiness_source": readiness_source,
        "readiness_updated_at": readiness.get("updated_at"),
        "estimated_input_tokens": estimated_input,
        "estimated_output_tokens": estimated_output,
        "estimated_cost_low": round(low, 4),
        "estimated_cost_high": round(high, 4),
        "model": str(payload.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"),
        "mode": str(payload.get("mode") or "standard"),
        "warnings": warnings,
        "chapter_numbers": [int(chapter.get("chapter") or 0) for chapter in selected],
    }


@app.post("/api/batch/estimate")
async def batch_estimate(request: Request, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    require_admin(request)
    novel_id = batch_novel_id(payload)
    settings = dict(payload)
    settings.update({"start_now": False, "show_estimate_before_starting": True})
    try:
        estimate = batch_selection(novel_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "dry_run": True, **estimate, "message": "Estimate used Translation Readiness and did not call OpenAI."}, status_code=200)


@app.post("/api/batch/start")
async def batch_start(request: Request, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    require_admin(request)
    novel_id = batch_novel_id(payload)
    settings = dict(payload)
    dry_run = bool(settings.pop("dry_run", False))
    concurrency = int(settings.get("concurrency") or 1)
    if concurrency not in {1, 2, 3}:
        raise HTTPException(status_code=400, detail="Concurrency must be 1, 2, or 3.")
    settings.update({"start_now": False, "show_estimate_before_starting": True})
    try:
        estimate = batch_selection(novel_id, settings)
        settings["chapter_numbers"] = estimate.get("chapter_numbers", [])
        if dry_run:
            return JSONResponse({"ok": True, "dry_run": True, **estimate, "message": "Dry-run used Translation Readiness and did not create a queue or call OpenAI."}, status_code=202)
        job = novels.create_batch(novel_id, settings)
        if not os.getenv("OPENAI_API_KEY"):
            return JSONResponse({"ok": False, **estimate, "job": job, "error": "OPENAI_API_KEY is not configured. Estimate was created, but translation was not started."}, status_code=400)
        novels.start_job(novel_id, job["job_id"])
        return JSONResponse({"ok": True, "dry_run": False, "novel_id": novel_id, "job_id": job["job_id"], "status": "queued"}, status_code=202)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/batch/jobs")
async def batch_jobs(request: Request, novel_id: str | None = None) -> dict[str, object]:
    require_admin(request)
    selected = novel_id or batch_novel_id()
    return {"ok": True, "novel_id": selected, "jobs": novels.service_for(selected).list_jobs()}


@app.get("/api/batch/jobs/{job_id}")
async def batch_job(request: Request, job_id: str, novel_id: str | None = None) -> dict[str, object]:
    require_admin(request)
    selected = novel_id or batch_novel_id()
    job = novels.service_for(selected).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Batch job not found.")
    return job


@app.post("/api/batch/jobs/{job_id}/cancel")
async def batch_cancel(request: Request, job_id: str, payload: Annotated[dict[str, object] | None, Body()] = None) -> dict[str, object]:
    require_admin(request)
    selected = batch_novel_id(payload)
    try:
        job = novels.service_for(selected).cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "novel_id": selected, "job": job, "message": "Translation job cancellation requested."}


@app.post("/api/batch/jobs/{job_id}/retry-failed")
async def batch_retry_failed(request: Request, job_id: str, payload: Annotated[dict[str, object] | None, Body()] = None) -> dict[str, object]:
    require_admin(request)
    selected = batch_novel_id(payload)
    try:
        job = novels.service_for(selected).retry_failed_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "novel_id": selected, "job": job, "message": "Failed chapters were queued for retry."}


@app.get("/api/novels/{novel_id}/jobs/{job_id}")
async def get_novel_job(request: Request, novel_id: str, job_id: str) -> dict[str, object]:
    require_admin(request)
    job = novels.service_for(novel_id).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/novels/{novel_id}/download/english")
async def download_novel_english(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    zip_path = novels.build_english_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No translated chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/original")
async def download_novel_original(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    zip_path = novels.build_original_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No Original Story chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/reference")
async def download_novel_reference(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    zip_path = novels.build_reference_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No Reference Translation chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/ai")
async def download_novel_ai(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    zip_path = novels.build_ai_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No AI Translation chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/prompts")
async def download_novel_prompts(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    zip_path = novels.build_prompts_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No saved prompts are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/backup")
async def download_novel_backup(request: Request, novel_id: str) -> FileResponse:
    require_admin(request)
    return JSONResponse({"ok": False, "error": BACKUP_DISABLED_MESSAGE}, status_code=409)


@app.post("/api/novels/{novel_id}/restore")
async def restore_novel_backup(request: Request, novel_id: str, backup: Annotated[UploadFile, File(description="Full novel backup ZIP")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse({"ok": False, "error": BACKUP_DISABLED_MESSAGE}, status_code=409)


@app.get("/api/reader/last")
async def get_last_reader() -> dict[str, object]:
    return novels.last_reader()


@app.post("/api/reader/last")
async def save_last_reader(payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    try:
        return novels.save_last_reader(str(payload["novel_id"]), int(payload["chapter"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid reader state.") from exc
