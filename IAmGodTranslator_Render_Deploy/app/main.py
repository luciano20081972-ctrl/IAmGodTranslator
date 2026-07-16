from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import io
import json
import logging
import os
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.db import Database, model_pricing
from app.content_import import payload_from_uploads
from app.recovery import parse_uploads, recovery_request, recovery_diagnostic, reference_diagnostic


VERSION = "10.6.1"
ROOT = Path(__file__).resolve().parents[1]
SESSION_COOKIE = "gt_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 12
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="GodTranslator", version=VERSION)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
database = Database()


class TranslationRunner:
    def __init__(self, store: Database) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._worker_condition = threading.Condition()
        self._active_workers = 0
        self._circuit_until = 0.0

    def start_existing(self) -> None:
        for job_id in self.store.runnable_translation_job_ids():
            self.start(job_id)

    def start(self, job_id: str, mock: bool = False) -> None:
        if not mock and (os.getenv("TRANSLATION_AUTOSTART") or "true").lower() in {"0", "false", "no"}:
            return
        with self._lock:
            thread = self._threads.get(job_id)
            if thread and thread.is_alive():
                return
            thread = threading.Thread(target=self._run_thread, args=(job_id, mock), name=f"gt-translation-{job_id[:8]}", daemon=True)
            self._threads[job_id] = thread
            thread.start()

    def _run_thread(self, job_id: str, mock: bool) -> None:
        try:
            asyncio.run(self._run_job(job_id, mock))
        finally:
            with self._lock:
                current = threading.current_thread()
                if self._threads.get(job_id) is current:
                    self._threads.pop(job_id, None)

    async def _run_job(self, job_id: str, mock: bool) -> None:
        job = self.store.translation_job(job_id) or {}
        concurrency = translation_concurrency(job.get("settings") or {})
        workers = [asyncio.create_task(self._worker(job_id, mock)) for _ in range(concurrency)]
        await asyncio.gather(*workers)
        await asyncio.to_thread(self.store.refresh_translation_job, job_id)

    async def _worker(self, job_id: str, mock: bool) -> None:
        worker_id = f"{threading.get_ident()}-{uuid.uuid4().hex[:8]}"
        while True:
            await self._respect_circuit_breaker()
            await asyncio.to_thread(self._acquire_global_slot)
            retry_pause = 0.0
            try:
                claim = await asyncio.to_thread(self.store.claim_translation_item, job_id, worker_id, translation_lease_seconds())
                if claim.get("status") == "race_lost":
                    continue
                if claim.get("status") != "claimed":
                    return
                item_id = int(claim["item_id"])
                metrics = dict(claim.get("metrics") or {})
                if claim.get("skip_error"):
                    await asyncio.to_thread(
                        self.store.finish_translation_item,
                        job_id,
                        item_id,
                        worker_id,
                        None,
                        None,
                        str(claim["skip_error"]),
                        metrics,
                    )
                    continue
                stop = asyncio.Event()
                heartbeat = asyncio.create_task(self._heartbeat(job_id, item_id, worker_id, stop))
                try:
                    translator = fake_translator_async if mock else openai_translator_async
                    provider_started = time.perf_counter()
                    result = await translator(claim["original_text"], claim.get("reference_text"), claim["settings"])
                    metrics.setdefault("provider_wait_seconds", time.perf_counter() - provider_started)
                    await asyncio.to_thread(
                        self.store.finish_translation_item,
                        job_id,
                        item_id,
                        worker_id,
                        result,
                        None,
                        None,
                        metrics,
                    )
                except Exception as exc:
                    metrics.setdefault("provider_wait_seconds", time.perf_counter() - provider_started)
                    if retryable_provider_error(exc):
                        retry_pause = provider_backoff_seconds(exc)
                        metrics["retry_delay_seconds"] = retry_pause
                        self._open_circuit(retry_pause)
                    await asyncio.to_thread(
                        self.store.finish_translation_item,
                        job_id,
                        item_id,
                        worker_id,
                        None,
                        compact_exception(exc),
                        None,
                        metrics,
                    )
                finally:
                    stop.set()
                    heartbeat.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat
            finally:
                self._release_global_slot()
            if retry_pause:
                await self._respect_circuit_breaker()

    async def _heartbeat(self, job_id: str, item_id: int, worker_id: str, stop: asyncio.Event) -> None:
        interval = max(10, min(60, translation_lease_seconds() // 4))
        while not stop.is_set():
            await asyncio.sleep(interval)
            if stop.is_set():
                return
            ok = await asyncio.to_thread(self.store.heartbeat_translation_item, job_id, item_id, worker_id, translation_lease_seconds())
            if not ok:
                return

    async def _respect_circuit_breaker(self) -> None:
        remaining = self._circuit_until - time.time()
        if remaining > 0:
            await asyncio.sleep(min(remaining, 120))

    def _open_circuit(self, seconds: float) -> None:
        with self._lock:
            self._circuit_until = max(self._circuit_until, time.time() + min(300, max(1, seconds)))

    def _acquire_global_slot(self) -> None:
        with self._worker_condition:
            while self._active_workers >= translation_global_concurrency_limit():
                self._worker_condition.wait(timeout=1.0)
            self._active_workers += 1

    def _release_global_slot(self) -> None:
        with self._worker_condition:
            self._active_workers = max(0, self._active_workers - 1)
            self._worker_condition.notify_all()


translation_runner = TranslationRunner(database)


@dataclass(frozen=True)
class RequestUser:
    user_id: str
    email: str | None
    role: str
    display_name: str | None = None
    avatar_url: str | None = None


@app.on_event("startup")
def startup() -> None:
    database.initialize()
    database.mark_interrupted_jobs()
    translation_runner.start_existing()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/auth/callback", response_class=HTMLResponse)
def auth_callback() -> HTMLResponse:
    return index()


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        reachable = database.ping()
    except Exception as exc:
        return {"ok": False, "version": VERSION, "database": "unreachable", "schema": database.config.schema, "error": exc.__class__.__name__}
    return {"ok": True, "version": VERSION, "database": "reachable" if reachable else "unreachable", "schema": database.config.schema}


@app.get("/api/desktop/health")
def desktop_health() -> dict[str, object]:
    base = health()
    return {
        **base,
        "desktop_api": "10.6.0",
        "supports": [
            "connection_test",
            "desktop_auth_check",
            "pack_preview",
            "pack_execute",
            "sync_status",
            "import_history",
            "recovery_request",
        ],
    }


@app.post("/api/admin/login")
def admin_login(request: Request, response: Response, payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    expected = os.getenv("ADMIN_PASSWORD") or ""
    if not expected:
        raise HTTPException(status_code=503, detail="admin_password_not_configured")
    password = str(payload.get("password") or "")
    if not hmac.compare_digest(password, expected):
        raise HTTPException(status_code=401, detail="invalid_admin_password")
    token = sign_session(int(time.time()))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
    )
    return {"ok": True, "admin": True}


@app.post("/api/admin/logout")
def admin_logout(response: Response) -> dict[str, object]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/admin/session")
def admin_session(request: Request) -> dict[str, object]:
    account = account_user(request)
    emergency_admin = valid_admin_cookie(request)
    effective_role = "admin" if emergency_admin else (account.role if account else "guest")
    return {
        "ok": True,
        "admin": is_admin_request(request),
        "role": effective_role,
        "account_role": account.role if account else "guest",
        "emergency_admin": emergency_admin,
    }


@app.get("/api/auth/config")
def auth_config() -> dict[str, object]:
    url = os.getenv("SUPABASE_URL") or ""
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    enabled = (os.getenv("AUTH_ENABLED") or "true").lower() not in {"0", "false", "no"}
    configured = bool(enabled and url and key)
    return {
        "ok": True,
        "configured": configured,
        "supabase_url": url if configured else "",
        "supabase_publishable_key": key if configured else "",
        "redirect_url": os.getenv("SUPABASE_AUTH_REDIRECT_URL") or "/auth/callback",
        "providers": {"email": configured, "google": configured},
    }


@app.get("/api/account/me")
def account_me(request: Request) -> dict[str, object]:
    user = account_user(request)
    if not user:
        return {"ok": True, "authenticated": False, "role": "guest", "auth": auth_config()}
    profile = database.ensure_user_profile(user.user_id, user.email, user.role, user.display_name, user.avatar_url)
    return {
        "ok": True,
        "authenticated": True,
        "user": sanitize_profile(profile),
        "preferences": database.user_preferences(user.user_id),
    }


@app.put("/api/account/preferences")
def save_account_preferences(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="account_required")
    preferences = payload.get("preferences") if isinstance(payload.get("preferences"), dict) else payload
    saved = database.save_user_preferences(user.user_id, preferences)
    return {"ok": True, "preferences": saved}


@app.get("/api/account/home")
def account_home(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {
        "ok": True,
        "continue_reading": database.reading_progress(user.user_id),
        "history": database.reading_history(user.user_id, limit=10),
        "bookmarks": database.bookmarks(user.user_id),
        "favorites": database.favorites(user.user_id),
    }


@app.put("/api/account/progress")
def save_reading_progress(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    user = require_user(request)
    progress = database.save_reading_progress(
        user.user_id,
        str(payload.get("novel_id") or ""),
        int(payload.get("chapter_number") or 0),
        str(payload.get("source") or "ai"),
        float(payload.get("scroll_percent") or 0),
    )
    return {"ok": True, "progress": progress}


@app.get("/api/account/history")
def account_history(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {"ok": True, "history": database.reading_history(user.user_id, limit=100)}


@app.delete("/api/account/history")
def clear_account_history(request: Request) -> dict[str, object]:
    user = require_user(request)
    database.clear_reading_history(user.user_id)
    return {"ok": True}


@app.get("/api/account/bookmarks")
def account_bookmarks(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {"ok": True, "bookmarks": database.bookmarks(user.user_id)}


@app.put("/api/account/bookmarks")
def save_account_bookmark(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    user = require_user(request)
    bookmark = database.save_bookmark(
        user.user_id,
        str(payload.get("novel_id") or ""),
        int(payload.get("chapter_number") or 0),
        str(payload.get("note") or ""),
    )
    return {"ok": True, "bookmark": bookmark}


@app.delete("/api/account/bookmarks/{novel_id}/{chapter_number}")
def delete_account_bookmark(novel_id: str, chapter_number: int, request: Request) -> dict[str, object]:
    user = require_user(request)
    database.delete_bookmark(user.user_id, novel_id, chapter_number)
    return {"ok": True}


@app.get("/api/account/favorites")
def account_favorites(request: Request) -> dict[str, object]:
    user = require_user(request)
    return {"ok": True, "favorites": database.favorites(user.user_id)}


@app.put("/api/account/favorites/{novel_id}")
def set_account_favorite(novel_id: str, request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, object]:
    user = require_user(request)
    return {"ok": True, "favorite": database.set_favorite(user.user_id, novel_id, bool(payload.get("favorite", True)))}


def require_admin(request: Request) -> None:
    if not is_admin_request(request):
        raise HTTPException(status_code=401, detail="admin_required")


def require_translator(request: Request) -> None:
    user = current_user(request)
    if not user or user.role not in {"translator", "admin"}:
        raise HTTPException(status_code=401, detail="translator_required")


def require_user(request: Request) -> RequestUser:
    user = account_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="account_required")
    return user


def is_admin_request(request: Request) -> bool:
    if valid_admin_cookie(request):
        return True
    user = account_user(request)
    return bool(user and user.role == "admin")


def sign_session(timestamp: int) -> str:
    return f"{timestamp}.{session_signature(timestamp)}"


def session_signature(timestamp: int) -> str:
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("ADMIN_PASSWORD") or "development-only"
    return hmac.new(secret.encode("utf-8"), str(timestamp).encode("utf-8"), hashlib.sha256).hexdigest()


def current_user(request: Request) -> RequestUser | None:
    if valid_admin_cookie(request):
        return RequestUser(user_id="admin-password", email=None, role="admin", display_name="Admin")
    return account_user(request)


def account_user(request: Request) -> RequestUser | None:
    token = bearer_token(request)
    if token:
        supabase_user = validate_supabase_token(token)
        if supabase_user:
            email = supabase_user.get("email")
            role = role_for_email(email)
            profile = database.ensure_user_profile(
                str(supabase_user["id"]),
                email,
                role,
                supabase_user.get("user_metadata", {}).get("name") or supabase_user.get("user_metadata", {}).get("full_name"),
                supabase_user.get("user_metadata", {}).get("avatar_url"),
            )
            return RequestUser(
                user_id=str(profile["user_id"]),
                email=profile.get("email"),
                role=role_for_profile(profile, email),
                display_name=profile.get("display_name"),
                avatar_url=profile.get("avatar_url"),
            )
    return None


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def validate_supabase_token(token: str) -> dict[str, Any] | None:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""
    if not url or not key:
        return None
    request = urllib.request.Request(
        f"{url}/auth/v1/user",
        headers={"apikey": key, "Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def valid_admin_cookie(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        timestamp_text, signature = token.split(".", 1)
        timestamp = int(timestamp_text)
    except Exception:
        return False
    if time.time() - timestamp > SESSION_TTL_SECONDS:
        return False
    return hmac.compare_digest(signature, session_signature(timestamp))


def role_for_email(email: str | None) -> str:
    admin_emails = {item.strip().lower() for item in (os.getenv("ADMIN_EMAILS") or "").split(",") if item.strip()}
    if email and email.lower() in admin_emails:
        return "admin"
    return "user"


def role_for_profile(profile: dict[str, Any], email: str | None) -> str:
    if role_for_email(email) == "admin":
        return "admin"
    role = str(profile.get("role") or "user").lower()
    return role if role in {"user", "translator", "admin"} else "user"


def sanitize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": profile.get("user_id"),
        "email": profile.get("email"),
        "display_name": profile.get("display_name"),
        "avatar_url": profile.get("avatar_url"),
        "preferred_language": profile.get("preferred_language"),
        "role": profile.get("role") or "user",
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


def can_view_reference(request: Request) -> bool:
    user = current_user(request)
    return bool(user and user.role in {"translator", "admin"})


def scrub_reference_metadata(novel: dict[str, Any], request: Request) -> dict[str, Any]:
    if can_view_reference(request):
        return novel
    scrubbed = dict(novel)
    for key in ("reference_count", "reference_source_url", "reference_target_start", "reference_target_end"):
        scrubbed.pop(key, None)
    metadata = scrubbed.get("metadata")
    if isinstance(metadata, dict):
        metadata = dict(metadata)
        metadata.pop("reference_target_start", None)
        metadata.pop("reference_target_end", None)
        scrubbed["metadata"] = metadata
    return scrubbed


@app.get("/api/novels")
def list_novels(request: Request) -> dict[str, object]:
    return {"ok": True, "novels": [scrub_reference_metadata(novel, request) for novel in database.novels()]}


@app.post("/api/novels")
def create_novel(payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    novel_id = slugify(payload.get("id") or payload.get("title") or "")
    if not novel_id:
        raise HTTPException(status_code=400, detail="novel_id_required")
    return {"ok": True, "novel": database.save_novel_metadata(novel_id, payload)}


@app.patch("/api/novels/{novel_id}")
def update_novel(novel_id: str, payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    current = database.novel(novel_id)
    if current is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    merged = {**current, **payload}
    return {"ok": True, "novel": database.save_novel_metadata(novel_id, merged)}


@app.post("/api/admin/content/import/preview")
def preview_content_import(payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    return database.content_import_preview(payload)


@app.post("/api/admin/content/import/execute")
def execute_content_import(payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    return database.apply_content_import_payload(payload)


@app.post("/api/admin/content/import/preview-pack")
async def preview_content_pack(
    files: list[UploadFile] = File(...),
    novel_id: str | None = Query(None),
    novel_title: str | None = Query(None),
    author: str | None = Query(None),
    source_url: str | None = Query(None),
    content_type: str | None = Query(None),
    _: None = Depends(require_admin),
) -> dict[str, object]:
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload.zip", await upload.read()))
    payload = payload_from_uploads(
        payloads,
        {
            "novel_id": novel_id or "",
            "novel": {
                "title": novel_title or "",
                "author": author or "",
                "source_url": source_url or "",
            },
            "content_type": content_type or "",
        },
    )
    preview = database.content_import_preview(payload)
    return {**preview, "pack_warnings": payload.get("warnings", [])}


@app.post("/api/admin/content/import/execute-pack")
async def execute_content_pack(
    files: list[UploadFile] = File(...),
    novel_id: str | None = Query(None),
    novel_title: str | None = Query(None),
    author: str | None = Query(None),
    source_url: str | None = Query(None),
    content_type: str | None = Query(None),
    overwrite_existing: bool = Query(False),
    dry_run: bool = Query(False),
    _: None = Depends(require_admin),
) -> dict[str, object]:
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload.zip", await upload.read()))
    payload = payload_from_uploads(
        payloads,
        {
            "novel_id": novel_id or "",
            "novel": {
                "title": novel_title or "",
                "author": author or "",
                "source_url": source_url or "",
            },
            "content_type": content_type or "",
            "options": {
                "overwrite_existing": overwrite_existing,
                "skip_existing": not overwrite_existing,
                "add_missing": not overwrite_existing,
                "dry_run": dry_run,
                "merge_metadata": True,
                "import_titles": True,
            },
        },
    )
    result = database.apply_content_import_payload(payload)
    return {**result, "pack_warnings": payload.get("warnings", [])}


@app.get("/api/desktop/auth/check")
def desktop_auth_check(request: Request, _: None = Depends(require_admin)) -> dict[str, object]:
    user = current_user(request)
    return {
        "ok": True,
        "authenticated": True,
        "role": user.role if user else "admin",
        "desktop_api": "10.6.0",
    }


@app.get("/api/desktop/sync/status")
def desktop_sync_status(novel_id: str | None = None, _: None = Depends(require_admin)) -> dict[str, object]:
    overview = database.admin_overview()
    novel = database.novel(novel_id) if novel_id else None
    missing = database.missing_data(novel_id) if novel_id and novel else None
    imports = database.import_jobs(novel_id=novel_id, limit=10)
    return {
        "ok": True,
        "version": VERSION,
        "schema": database.config.schema,
        "overview": overview,
        "novel": novel,
        "missing": missing,
        "recent_imports": imports,
        "sync": {
            "pack_preview": "/api/desktop/import/preview-pack",
            "pack_execute": "/api/desktop/import/execute-pack",
            "import_history": "/api/desktop/import-history",
            "recovery_request": "/api/novels/{novel_id}/recovery/request",
        },
    }


@app.get("/api/desktop/import-history")
def desktop_import_history(novel_id: str | None = None, limit: int = 20, _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "jobs": database.import_jobs(novel_id=novel_id, limit=max(1, min(int(limit or 20), 100)))}


@app.post("/api/desktop/import/preview-pack")
async def desktop_preview_content_pack(
    files: list[UploadFile] = File(...),
    novel_id: str | None = Query(None),
    novel_title: str | None = Query(None),
    author: str | None = Query(None),
    source_url: str | None = Query(None),
    content_type: str | None = Query(None),
    _: None = Depends(require_admin),
) -> dict[str, object]:
    return await preview_content_pack(
        files=files,
        novel_id=novel_id,
        novel_title=novel_title,
        author=author,
        source_url=source_url,
        content_type=content_type,
    )


@app.post("/api/desktop/import/execute-pack")
async def desktop_execute_content_pack(
    files: list[UploadFile] = File(...),
    novel_id: str | None = Query(None),
    novel_title: str | None = Query(None),
    author: str | None = Query(None),
    source_url: str | None = Query(None),
    content_type: str | None = Query(None),
    overwrite_existing: bool = Query(False),
    dry_run: bool = Query(False),
    _: None = Depends(require_admin),
) -> dict[str, object]:
    return await execute_content_pack(
        files=files,
        novel_id=novel_id,
        novel_title=novel_title,
        author=author,
        source_url=source_url,
        content_type=content_type,
        overwrite_existing=overwrite_existing,
        dry_run=dry_run,
    )


@app.get("/api/admin/content/editions/{novel_id}")
def list_english_editions(novel_id: str, chapter_number: int | None = None, _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, "novel_id": novel_id, "editions": database.english_editions(novel_id, chapter_number=chapter_number)}


@app.post("/api/admin/content/editions/{novel_id}/{chapter_number}/default")
def set_default_english_edition(novel_id: str, chapter_number: int, payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    try:
        result = database.set_default_english_edition(novel_id, chapter_number, str(payload.get("edition_key") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/novels/{novel_id}/archive")
def archive_novel(novel_id: str, payload: dict[str, Any] = Body(default={}), _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "novel": database.archive_novel(novel_id, bool(payload.get("archived", True)))}


@app.get("/api/novels/{novel_id}")
def get_novel(request: Request, novel_id: str) -> dict[str, object]:
    novel = database.novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    counts = database.verification_counts(novel_id)
    if not can_view_reference(request):
        counts = {key: value for key, value in counts.items() if key != "reference"}
    return {"ok": True, "novel": scrub_reference_metadata(novel, request), "counts": counts}


@app.get("/api/models")
def model_registry() -> dict[str, object]:
    configured = [item.strip() for item in (os.getenv("OPENAI_MODEL_REGISTRY") or "gpt-4o-mini,gpt-4o").split(",") if item.strip()]
    models = []
    for model in configured:
        pricing = model_pricing(model)
        models.append(
            {
                "id": model,
                "display_name": model,
                "description": "OpenAI model configured for controlled novel translation.",
                "enabled": True,
                "pricing": pricing if pricing else {"note": "Pricing not configured."},
            }
        )
    return {"ok": True, "models": models}


@app.get("/api/novels/{novel_id}/library")
def library(
    request: Request,
    novel_id: str,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    search: str = "",
    view: str = "all",
) -> dict[str, object]:
    payload = database.library(novel_id, limit=limit, offset=offset, search=search, view=view)
    if payload["novel"] is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    counts = database.library_counts(novel_id)
    if not can_view_reference(request):
        payload["novel"] = scrub_reference_metadata(payload["novel"], request)
        for chapter in payload["chapters"]:
            chapter.pop("has_reference", None)
        counts.pop("reference_readable", None)
    return {"ok": True, **payload, "counts": counts}


@app.get("/api/novels/{novel_id}/chapters/{chapter_number}/{mode}")
def chapter_text(request: Request, novel_id: str, chapter_number: int, mode: str) -> dict[str, object]:
    if mode not in {"original", "reference", "english", "ai"}:
        raise HTTPException(status_code=404, detail="chapter_mode_not_found")
    if mode == "reference":
        require_translator(request)
    return database.chapter_text(novel_id, chapter_number, mode)


@app.get("/api/novels/{novel_id}/compare/{chapter_number}")
def compare_chapter(novel_id: str, chapter_number: int, _: None = Depends(require_translator)) -> dict[str, object]:
    return {
        "ok": True,
        "novel_id": novel_id,
        "chapter_number": chapter_number,
        "original": database.chapter_text(novel_id, chapter_number, "original"),
        "reference": database.chapter_text(novel_id, chapter_number, "reference"),
        "english": database.chapter_text(novel_id, chapter_number, "english"),
        "ai": database.chapter_text(novel_id, chapter_number, "ai"),
    }


@app.post("/api/translation/estimate")
def translation_estimate(payload: dict[str, Any] = Body(...), _: None = Depends(require_translator)) -> dict[str, object]:
    novel_id = payload.get("novel_id") or default_novel_id()
    selection = translation_selection(novel_id, payload)
    return database.estimate_translation(novel_id, selection["chapters"], {**payload, "_selection_diagnostics": selection["diagnostics"]})


@app.post("/api/translation/jobs")
def create_translation_job(payload: dict[str, Any] = Body(...), _: None = Depends(require_translator)) -> dict[str, object]:
    novel_id = payload.get("novel_id") or default_novel_id()
    selection = translation_selection(novel_id, payload)
    job = database.create_translation_job(novel_id, selection["chapters"], {**payload, "_selection_diagnostics": selection["diagnostics"]})
    translation_runner.start(str(job["id"]))
    return {"ok": True, "job": job}


@app.get("/api/translation/jobs")
def list_translation_jobs(novel_id: str | None = None, _: None = Depends(require_translator)) -> dict[str, object]:
    return {"ok": True, "jobs": database.translation_jobs(novel_id=novel_id)}


@app.get("/api/translation/jobs/{job_id}")
def get_translation_job(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    job = database.translation_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="translation_job_not_found")
    return {"ok": True, "job": job}


@app.post("/api/translation/jobs/{job_id}/pause")
def pause_translation_job(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    return {"ok": True, "job": database.set_job_status(job_id, "paused")}


@app.post("/api/translation/jobs/{job_id}/resume")
def resume_translation_job(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    job = database.set_job_status(job_id, "queued")
    translation_runner.start(job_id)
    return {"ok": True, "job": job}


@app.post("/api/translation/jobs/{job_id}/stop")
def stop_translation_job(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    return {"ok": True, "job": database.set_job_status(job_id, "cancelled")}


@app.post("/api/translation/jobs/{job_id}/retry-failed")
def retry_failed(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    job = database.retry_failed_items(job_id)
    translation_runner.start(job_id)
    return {"ok": True, "job": job}


@app.post("/api/translation/jobs/{job_id}/run-next")
def run_next_translation(job_id: str, mock: bool = Query(False), _: None = Depends(require_translator)) -> dict[str, object]:
    translation_runner.start(job_id, mock=mock)
    return {"ok": True, "job": database.translation_job(job_id) or {"id": job_id}}


@app.get("/api/novels/{novel_id}/recovery/reference")
def reference_recovery_diagnostic(novel_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, **reference_diagnostic(database, novel_id)}


@app.get("/api/novels/{novel_id}/recovery/diagnostic/{target_mode}")
def generic_recovery_diagnostic(novel_id: str, target_mode: str, _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    if target_mode not in {"original", "reference", "english"}:
        raise HTTPException(status_code=404, detail="recovery_mode_not_found")
    return {"ok": True, **recovery_diagnostic(database, novel_id, target_mode)}


@app.get("/api/novels/{novel_id}/recovery/request")
def download_recovery_request(
    novel_id: str,
    source_url: str = Query(""),
    chapter_url_template: str = Query(""),
    target_mode: str = Query("reference"),
    _: None = Depends(require_admin),
) -> JSONResponse:
    novel = database.novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    if target_mode not in {"original", "reference", "english"}:
        raise HTTPException(status_code=404, detail="recovery_mode_not_found")
    source_url = source_url or str(novel.get("reference_source_url") or novel.get("source_url") or "")
    payload = recovery_request(database, novel_id, source_url=source_url, chapter_url_template=chapter_url_template, target_mode=target_mode)
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{novel_id}-{target_mode}-recovery-request.json"'})


@app.post("/api/novels/{novel_id}/recovery/preview")
async def preview_reference_import(novel_id: str, files: list[UploadFile] = File(...), target_mode: str = Query("reference"), _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    if target_mode not in {"original", "reference", "english"}:
        raise HTTPException(status_code=404, detail="recovery_mode_not_found")
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload.txt", await upload.read()))
    return parse_uploads(payloads, novel_id, database, target_mode=target_mode)


@app.get("/api/import-jobs/{job_id}")
def get_import_job(job_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    job = database.import_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_job_not_found")
    return {"ok": True, "job": job}


@app.get("/api/import-jobs")
def list_import_jobs(novel_id: str | None = None, limit: int = 20, _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "jobs": database.import_jobs(novel_id=novel_id, limit=max(1, min(int(limit or 20), 100)))}


@app.post("/api/novels/{novel_id}/recovery/import/{job_id}")
def apply_reference_import(novel_id: str, job_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    job = database.import_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_job_not_found")
    if job["novel_id"] != novel_id:
        raise HTTPException(status_code=400, detail="import_job_novel_mismatch")
    return database.apply_import_job(job_id)


@app.get("/api/admin/overview")
def admin_overview(_: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "overview": database.admin_overview()}


@app.get("/api/admin/db-health")
def admin_db_health(_: None = Depends(require_admin)) -> dict[str, object]:
    inspection = database.inspect_schema()
    return {"ok": True, "health": {"reachable": database.ping(), "schema": database.config.schema, **inspection}}


@app.get("/api/admin/missing/{novel_id}")
def admin_missing(novel_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "missing": database.missing_data(novel_id)}


@app.get("/api/admin/users")
def admin_users(_: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "users": [sanitize_profile(user) for user in database.users()]}


@app.get("/api/admin/translation/performance")
def admin_translation_performance(novel_id: str | None = None, _: None = Depends(require_admin)) -> dict[str, object]:
    diagnostics = database.translation_performance_diagnostics(novel_id=novel_id)
    diagnostics["runtime"] = {
        "global_worker_cap": translation_global_concurrency_limit(),
        "default_concurrency": bounded_int(os.getenv("TRANSLATION_DEFAULT_CONCURRENCY"), 3, 1, 4),
        "lease_seconds": translation_lease_seconds(),
        "benchmark_enabled": benchmark_enabled(),
        "scheduler_location": "FastAPI web process",
    }
    return diagnostics


@app.post("/api/admin/translation/benchmark/estimate")
def admin_translation_benchmark_estimate(payload: dict[str, Any] = Body(default={}), _: None = Depends(require_admin)) -> dict[str, object]:
    if not benchmark_enabled():
        return {
            "ok": False,
            "enabled": False,
            "detail": "controlled_benchmark_disabled",
            "message": "Set TRANSLATION_BENCHMARK_ENABLED=true before running a real provider benchmark.",
        }
    novel_id = str(payload.get("novel_id") or default_novel_id())
    chapters = selected_chapters(novel_id, payload)
    if len(chapters) > 5:
        raise HTTPException(status_code=400, detail="benchmark_sample_limit_5")
    settings = {**payload, "only_untranslated": bool(payload.get("only_untranslated", True))}
    estimate = database.estimate_translation(novel_id, chapters, settings)
    return {
        "ok": True,
        "enabled": True,
        "dry_run": True,
        "overwrite_existing_ai": False,
        "estimate": estimate,
        "message": "Dry-run only. Running a real benchmark requires a separate explicit action and is not implemented in normal QA.",
    }


@app.get("/api/novels/{novel_id}/backup")
def export_backup(novel_id: str, _: None = Depends(require_admin)) -> StreamingResponse:
    payload = database.backup_payload(novel_id)
    if payload["novel"] is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"format": "godtranslator-v10-backup", "version": VERSION, "novel_id": novel_id}, ensure_ascii=False, indent=2))
        zf.writestr(f"novels/{novel_id}/backup.json", json.dumps(payload, ensure_ascii=False, indent=2))
    memory.seek(0)
    return StreamingResponse(memory, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{novel_id}-v10-backup.zip"'})


@app.get("/api/admin/backups/manifest")
def platform_backup_manifest(_: None = Depends(require_admin)) -> dict[str, object] | JSONResponse:
    try:
        return database.platform_backup_manifest_summary()
    except Exception as exc:
        return backup_error_response(
            "table_counts",
            "backup_manifest_failed",
            "Backup manifest could not be loaded.",
            exc,
        )


@app.get("/api/admin/backups/download")
def download_platform_backup(_: None = Depends(require_admin)) -> StreamingResponse | JSONResponse:
    try:
        payload = complete_platform_backup_payload()
    except Exception as exc:
        return backup_error_response("build_full_backup", "backup_build_failed", "Backup could not be created for download.", exc)
    try:
        raw = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    except Exception as exc:
        return backup_error_response("serialize_full_backup", "backup_serialize_failed", "Backup could not be serialized for download.", exc)
    return StreamingResponse(
        io.BytesIO(raw),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{platform_backup_filename(payload)}"'},
    )


@app.post("/api/admin/backups/create")
def create_platform_backup(payload: dict[str, Any] = Body(default={}), _: None = Depends(require_admin)) -> dict[str, object] | JSONResponse:
    try:
        backup = complete_platform_backup_payload()
    except Exception as exc:
        return backup_error_response("build_full_backup", "backup_build_failed", "Backup could not be created.", exc)
    try:
        raw = json.dumps(backup, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    except Exception as exc:
        return backup_error_response("serialize_full_backup", "backup_serialize_failed", "Backup could not be serialized.", exc)
    try:
        storage = store_platform_backup(raw, platform_backup_filename(backup)) if bool(payload.get("store", True)) else {"status": "skipped", "location": None}
    except Exception as exc:
        return backup_error_response("store_backup", "backup_store_failed", "Backup was created but could not be stored.", exc)
    return {"ok": True, "manifest": backup["manifest"], "storage": storage}


@app.post("/api/admin/backups/restore-preview")
def preview_platform_restore(payload: dict[str, Any] = Body(...), _: None = Depends(require_admin)) -> dict[str, object]:
    mode = str(payload.get("mode") or "add-missing")
    backup = payload.get("backup") if isinstance(payload.get("backup"), dict) else payload
    return database.restore_preview(backup, mode=mode)


def complete_platform_backup_payload() -> dict[str, Any]:
    payload = database.platform_backup_payload()
    raw_without_checksum = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    payload["manifest"]["size_bytes"] = len(raw_without_checksum)
    payload["manifest"]["sha256"] = hashlib.sha256(raw_without_checksum).hexdigest()
    return payload


def backup_error_response(stage: str, code: str, message: str, exc: Exception, status_code: int = 500) -> JSONResponse:
    LOGGER.warning("backup endpoint failed at stage=%s code=%s error_type=%s", stage, code, exc.__class__.__name__)
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {"code": code, "message": message, "stage": stage},
            "message": message,
            "stage": stage,
        },
    )


def platform_backup_filename(payload: dict[str, Any]) -> str:
    created = str(payload.get("manifest", {}).get("created_at") or utc_filename_time())
    stamp = "".join(ch if ch.isdigit() else "-" for ch in created).strip("-")[:19].replace("--", "-")
    return f"godtranslator-v10-platform-backup-{stamp}.json"


def utc_filename_time() -> str:
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())


def store_platform_backup(raw: bytes, filename: str) -> dict[str, object]:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_BACKUP_SERVICE_KEY") or ""
    bucket = os.getenv("SUPABASE_BACKUP_BUCKET") or "godtranslator-backups"
    if not url or not service_key:
        return {"status": "not_configured", "location": None}
    object_path = f"platform/{filename}"
    request = urllib.request.Request(
        f"{url}/storage/v1/object/{bucket}/{object_path}",
        data=raw,
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/json",
            "x-upsert": "false",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
        return {"status": "stored", "bucket": bucket, "path": object_path}
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "error": f"storage_http_{exc.code}", "bucket": bucket, "path": object_path}
    except urllib.error.URLError:
        return {"status": "failed", "error": "storage_unreachable", "bucket": bucket, "path": object_path}
    except Exception as exc:
        return {"status": "failed", "error": exc.__class__.__name__, "bucket": bucket, "path": object_path}


def translation_selection(novel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    selection_mode = str(payload.get("selection_mode") or "").lower()
    only_untranslated = bool(payload.get("only_untranslated", True))
    if payload.get("all_untranslated") or selection_mode == "all-untranslated":
        chapters = database.all_untranslated_chapters(novel_id, limit=None, only_untranslated=only_untranslated)
        inventory = database.translation_inventory_summary(novel_id)
        return {
            "chapters": chapters,
            "diagnostics": {
                "mode": "all-untranslated",
                "requested": "all",
                "server_side_selection": True,
                "selected_count": len(chapters),
                "total_chapters": inventory["total_chapters"],
                "available_eligible_count": inventory["available_eligible_count"],
                "missing_original_count": inventory["missing_original_count"],
                "already_translated_count": inventory["already_translated_count"],
                "duplicates_removed": 0,
                "duplicate_chapters": [],
                "invalid_tokens": [],
                "invalid_chapter_numbers": [],
            },
        }
    if selection_mode == "next-untranslated":
        count_value = str(payload.get("next_count") or payload.get("next_count_mode") or "25").lower()
        if count_value == "all":
            chapters = database.all_untranslated_chapters(novel_id, limit=None, only_untranslated=only_untranslated)
            requested: int | str = "all"
        else:
            count = bounded_int(payload.get("next_count"), 25, 1, 5000)
            chapters = database.all_untranslated_chapters(novel_id, limit=count, only_untranslated=only_untranslated)
            requested = count
        inventory = database.translation_inventory_summary(novel_id)
        return {
            "chapters": chapters,
            "diagnostics": {
                "mode": "next-untranslated",
                "requested": requested,
                "server_side_selection": True,
                "selected_count": len(chapters),
                "total_chapters": inventory["total_chapters"],
                "available_eligible_count": inventory["available_eligible_count"],
                "duplicates_removed": 0,
                "duplicate_chapters": [],
                "invalid_tokens": [],
                "invalid_chapter_numbers": [],
            },
        }
    parsed = parse_specific_chapters(str(payload.get("chapters") or ""))
    return {
        "chapters": parsed["chapters"],
        "diagnostics": {
            "mode": "specific",
            "server_side_selection": False,
            **parsed,
        },
    }


def selected_chapters(novel_id: str, payload: dict[str, Any]) -> list[int]:
    return translation_selection(novel_id, payload)["chapters"]


def parse_specific_chapters(text: str) -> dict[str, Any]:
    text = str(text or "").strip()
    chapters: list[int] = []
    seen: set[int] = set()
    duplicate_chapters: set[int] = set()
    invalid_tokens: list[str] = []
    if not text:
        return {"chapters": [], "duplicates_removed": 0, "duplicate_chapters": [], "invalid_tokens": []}
    raw_count = 0
    for part in [chunk.strip() for chunk in text.split(",") if chunk.strip()]:
        if "-" in part:
            pieces = [piece.strip() for piece in part.split("-", 1)]
            if len(pieces) != 2 or not all(piece.isdigit() for piece in pieces):
                invalid_tokens.append(part)
                continue
            start, end = int(pieces[0]), int(pieces[1])
            if start <= 0 or end <= 0:
                invalid_tokens.append(part)
                continue
            values = range(min(start, end), max(start, end) + 1)
        elif part.isdigit() and int(part) > 0:
            values = [int(part)]
        else:
            invalid_tokens.append(part)
            continue
        for chapter in values:
            raw_count += 1
            if chapter in seen:
                duplicate_chapters.add(chapter)
                continue
            seen.add(chapter)
            chapters.append(chapter)
    return {
        "chapters": sorted(chapters),
        "raw_selected_count": raw_count,
        "duplicates_removed": raw_count - len(seen),
        "duplicate_chapters": sorted(duplicate_chapters),
        "invalid_tokens": invalid_tokens,
    }

def default_novel_id() -> str:
    novels = database.novels()
    if not novels:
        raise HTTPException(status_code=400, detail="novel_id_required")
    return str(novels[0]["id"])


def fake_translator(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    prefix = "Mock translation"
    reference_note = "\n\n[Reference guidance available.]" if reference else ""
    text = f"{prefix}\n\n{original.strip()}{reference_note}"
    return {"text": text, "input_tokens": max(1, (len(original) + len(reference or "")) // 4), "output_tokens": max(1, len(text) // 5), "actual_cost": 0.0}


async def fake_translator_async(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    prompt_started = time.perf_counter()
    payload = build_prompt_payload(original, reference, settings)
    prompt_build_seconds = time.perf_counter() - prompt_started
    provider_started_at = datetime.now(UTC).isoformat()
    provider_started = time.perf_counter()
    await asyncio.sleep(float(settings.get("mock_provider_delay_seconds") or 0))
    provider_wait_seconds = time.perf_counter() - provider_started
    provider_finished_at = datetime.now(UTC).isoformat()
    result = fake_translator(original, reference, settings)
    result["metrics"] = {
        **payload["metrics"],
        "prompt_build_seconds": prompt_build_seconds,
        "provider_wait_seconds": provider_wait_seconds,
        "provider_started_at": provider_started_at,
        "provider_finished_at": provider_finished_at,
    }
    return result


_async_openai_client: Any | None = None
_async_openai_key: str | None = None
_openai_client: Any | None = None
_openai_key: str | None = None


def translation_concurrency(settings: dict[str, Any]) -> int:
    default = bounded_int(os.getenv("TRANSLATION_DEFAULT_CONCURRENCY"), 3, 1, 4)
    global_max = translation_global_concurrency_limit()
    per_job_max = bounded_int(settings.get("max_workers"), default, 1, global_max)
    requested = settings.get("concurrency") or settings.get("max_concurrency") or default
    return bounded_int(requested, default, 1, per_job_max)


def translation_global_concurrency_limit() -> int:
    return bounded_int(os.getenv("TRANSLATION_MAX_CONCURRENCY"), 8, 1, 24)


def translation_lease_seconds() -> int:
    return bounded_int(os.getenv("TRANSLATION_ITEM_LEASE_SECONDS"), 900, 120, 3600)


def provider_timeout_seconds(settings: dict[str, Any]) -> int:
    return bounded_int(settings.get("provider_timeout_seconds"), 180, 30, 600)


def benchmark_enabled() -> bool:
    return (os.getenv("TRANSLATION_BENCHMARK_ENABLED") or "").lower() in {"1", "true", "yes"}


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def async_openai_client() -> Any:
    global _async_openai_client, _async_openai_key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if _async_openai_client is None or _async_openai_key != api_key:
        from openai import AsyncOpenAI

        _async_openai_client = AsyncOpenAI(api_key=api_key)
        _async_openai_key = api_key
    return _async_openai_client


def openai_client() -> Any:
    global _openai_client, _openai_key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    if _openai_client is None or _openai_key != api_key:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=api_key)
        _openai_key = api_key
    return _openai_client


async def openai_translator_async(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    model = settings.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    prompt_started = time.perf_counter()
    payload = build_prompt_payload(original, reference, settings)
    prompt = payload["prompt"]
    prompt_build_seconds = time.perf_counter() - prompt_started
    provider_started_at = datetime.now(UTC).isoformat()
    provider_started = time.perf_counter()
    response = await asyncio.wait_for(
        async_openai_client().responses.create(model=model, input=prompt),
        timeout=provider_timeout_seconds(settings),
    )
    provider_wait_seconds = time.perf_counter() - provider_started
    provider_finished_at = datetime.now(UTC).isoformat()
    text = response.output_text
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    pricing = model_pricing(model)
    actual_cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "actual_cost": round(actual_cost, 8),
        "metrics": {
            **payload["metrics"],
            "prompt_build_seconds": prompt_build_seconds,
            "provider_wait_seconds": provider_wait_seconds,
            "provider_started_at": provider_started_at,
            "provider_finished_at": provider_finished_at,
        },
    }


def retryable_provider_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    status = status or getattr(response, "status_code", None)
    name = exc.__class__.__name__.lower()
    return status in {429, 500, 502, 503, 504} or "timeout" in name or "rate" in name


def provider_backoff_seconds(exc: Exception) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = None
    if hasattr(headers, "get"):
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
    try:
        if retry_after:
            return max(1.0, min(120.0, float(retry_after)))
    except (TypeError, ValueError):
        pass
    return random.uniform(1.5, 4.0)


def compact_exception(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    status = status or getattr(response, "status_code", None)
    prefix = f"{exc.__class__.__name__}"
    if status:
        prefix += f" {status}"
    return f"{prefix}: {str(exc) or exc.__class__.__name__}"[:800]


def openai_translator(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    model = settings.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    prompt = build_prompt(original, reference, settings)
    response = openai_client().responses.create(model=model, input=prompt)
    text = response.output_text
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens, "actual_cost": 0.0}


def build_prompt(original: str, reference: str | None, settings: dict[str, Any]) -> str:
    return str(build_prompt_payload(original, reference, settings)["prompt"])


def build_prompt_payload(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    glossary = relevant_glossary(settings.get("glossary") or "", original) if settings.get("glossary") else ""
    guidance = [
        "Translate the Chinese source into natural professional English.",
        "The Chinese original is the source of truth.",
        "Preserve paragraphs and dialogue formatting.",
        "Do not summarize, skip, or add events.",
        "Return only the translated chapter text unless this job explicitly asks for notes.",
    ]
    if reference:
        guidance.append("Use the reference translation only as style guidance when it helps; never translate the reference instead of the original.")
    if settings.get("style_guide"):
        guidance.append(f"Style guide: {settings['style_guide']}")
    if glossary:
        guidance.append(f"Glossary: {glossary}")
    instructions = "\n".join(guidance)
    prompt = "\n".join(guidance) + "\n\nChinese original:\n" + original
    if reference:
        prompt += "\n\nReference translation:\n" + reference
    return {
        "prompt": prompt,
        "metrics": {
            "prompt_instruction_tokens": estimate_text_tokens(instructions),
            "prompt_original_tokens": estimate_text_tokens(original),
            "prompt_reference_tokens": estimate_text_tokens(reference or ""),
            "prompt_estimated_output_tokens": max(1, len(original or "") // 5),
            "original_char_count": len(original or ""),
            "reference_char_count": len(reference or ""),
        },
    }


def estimate_text_tokens(value: str | None) -> int:
    text = value or ""
    return max(0, len(text) // 4)


def relevant_glossary(glossary: str, original: str, max_lines: int = 80) -> str:
    lines = [line.strip() for line in str(glossary or "").splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    original_text = original or ""
    required: list[str] = []
    matched: list[str] = []
    for line in lines:
        lowered = line.lower()
        if lowered.startswith(("!", "global:", "required:")):
            required.append(line)
            continue
        term = line.split("=", 1)[0].split(":", 1)[0].strip()
        if term and term in original_text:
            matched.append(line)
    return "\n".join((required + matched)[:max_lines])


def slugify(value: str) -> str:
    slug = re_sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


def re_sub(pattern: str, replacement: str, value: str) -> str:
    import re

    return re.sub(pattern, replacement, value)
