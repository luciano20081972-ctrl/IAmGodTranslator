from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.db import Database, model_pricing
from app.recovery import parse_uploads, recovery_request, reference_diagnostic


VERSION = "10.2.0"
ROOT = Path(__file__).resolve().parents[1]
SESSION_COOKIE = "gt_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 12

app = FastAPI(title="GodTranslator", version=VERSION)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
database = Database()


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
    user = current_user(request)
    return {"ok": True, "admin": bool(user and user.role == "admin"), "role": user.role if user else "guest"}


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
    user = current_user(request)
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
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="account_required")
    return user


def is_admin_request(request: Request) -> bool:
    user = current_user(request)
    if user and user.role == "admin":
        return True
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


def sign_session(timestamp: int) -> str:
    return f"{timestamp}.{session_signature(timestamp)}"


def session_signature(timestamp: int) -> str:
    secret = os.getenv("ADMIN_SESSION_SECRET") or os.getenv("ADMIN_PASSWORD") or "development-only"
    return hmac.new(secret.encode("utf-8"), str(timestamp).encode("utf-8"), hashlib.sha256).hexdigest()


def current_user(request: Request) -> RequestUser | None:
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
    if valid_admin_cookie(request):
        return RequestUser(user_id="admin-password", email=None, role="admin", display_name="Admin")
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


@app.get("/api/novels")
def list_novels() -> dict[str, object]:
    return {"ok": True, "novels": database.novels()}


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


@app.post("/api/novels/{novel_id}/archive")
def archive_novel(novel_id: str, payload: dict[str, Any] = Body(default={}), _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "novel": database.archive_novel(novel_id, bool(payload.get("archived", True)))}


@app.get("/api/novels/{novel_id}")
def get_novel(novel_id: str) -> dict[str, object]:
    novel = database.novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    counts = database.verification_counts(novel_id)
    return {"ok": True, "novel": novel, "counts": counts}


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
    novel_id: str,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    search: str = "",
    view: str = "all",
) -> dict[str, object]:
    payload = database.library(novel_id, limit=limit, offset=offset, search=search, view=view)
    if payload["novel"] is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, **payload, "counts": database.library_counts(novel_id)}


@app.get("/api/novels/{novel_id}/chapters/{chapter_number}/{mode}")
def chapter_text(novel_id: str, chapter_number: int, mode: str) -> dict[str, object]:
    if mode not in {"original", "reference", "ai"}:
        raise HTTPException(status_code=404, detail="chapter_mode_not_found")
    return database.chapter_text(novel_id, chapter_number, mode)


@app.get("/api/novels/{novel_id}/compare/{chapter_number}")
def compare_chapter(novel_id: str, chapter_number: int, _: None = Depends(require_translator)) -> dict[str, object]:
    return {
        "ok": True,
        "novel_id": novel_id,
        "chapter_number": chapter_number,
        "original": database.chapter_text(novel_id, chapter_number, "original"),
        "reference": database.chapter_text(novel_id, chapter_number, "reference"),
        "ai": database.chapter_text(novel_id, chapter_number, "ai"),
    }


@app.post("/api/translation/estimate")
def translation_estimate(payload: dict[str, Any] = Body(...), _: None = Depends(require_translator)) -> dict[str, object]:
    novel_id = payload.get("novel_id") or "i-am-god"
    chapters = selected_chapters(novel_id, payload)
    return database.estimate_translation(novel_id, chapters, payload)


@app.post("/api/translation/jobs")
def create_translation_job(payload: dict[str, Any] = Body(...), _: None = Depends(require_translator)) -> dict[str, object]:
    novel_id = payload.get("novel_id") or "i-am-god"
    chapters = selected_chapters(novel_id, payload)
    return {"ok": True, "job": database.create_translation_job(novel_id, chapters, payload)}


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
    return {"ok": True, "job": database.set_job_status(job_id, "queued")}


@app.post("/api/translation/jobs/{job_id}/stop")
def stop_translation_job(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    return {"ok": True, "job": database.set_job_status(job_id, "cancelled")}


@app.post("/api/translation/jobs/{job_id}/retry-failed")
def retry_failed(job_id: str, _: None = Depends(require_translator)) -> dict[str, object]:
    return {"ok": True, "job": database.retry_failed_items(job_id)}


@app.post("/api/translation/jobs/{job_id}/run-next")
def run_next_translation(job_id: str, mock: bool = Query(False), _: None = Depends(require_translator)) -> dict[str, object]:
    translator = fake_translator if mock else openai_translator
    return {"ok": True, "job": database.run_next_translation_item(job_id, translator)}


@app.get("/api/novels/{novel_id}/recovery/reference")
def reference_recovery_diagnostic(novel_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, **reference_diagnostic(database, novel_id)}


@app.get("/api/novels/{novel_id}/recovery/request")
def download_recovery_request(
    novel_id: str,
    source_url: str = Query("https://novelfire.net/book/i-am-god-lslccf"),
    chapter_url_template: str = Query("https://novelfire.net/book/i-am-god-lslccf/chapter-{chapter}"),
    _: None = Depends(require_admin),
) -> JSONResponse:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    payload = recovery_request(database, novel_id, source_url=source_url, chapter_url_template=chapter_url_template)
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="{novel_id}-reference-recovery-request.json"'})


@app.post("/api/novels/{novel_id}/recovery/preview")
async def preview_reference_import(novel_id: str, files: list[UploadFile] = File(...), _: None = Depends(require_admin)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload.txt", await upload.read()))
    return parse_uploads(payloads, novel_id, database)


@app.get("/api/import-jobs/{job_id}")
def get_import_job(job_id: str, _: None = Depends(require_admin)) -> dict[str, object]:
    job = database.import_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_job_not_found")
    return {"ok": True, "job": job}


@app.get("/api/import-jobs")
def list_import_jobs(novel_id: str | None = None, _: None = Depends(require_admin)) -> dict[str, object]:
    return {"ok": True, "jobs": database.import_jobs(novel_id=novel_id)}


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


def selected_chapters(novel_id: str, payload: dict[str, Any]) -> list[int]:
    if payload.get("all_untranslated"):
        return database.all_untranslated_chapters(novel_id)
    text = str(payload.get("chapters") or "").strip()
    chapters: set[int] = set()
    for part in [chunk.strip() for chunk in text.split(",") if chunk.strip()]:
        if "-" in part:
            left, right = part.split("-", 1)
            start, end = int(left), int(right)
            chapters.update(range(min(start, end), max(start, end) + 1))
        else:
            chapters.add(int(part))
    return sorted(chapters)


def fake_translator(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    prefix = "Mock translation"
    reference_note = "\n\n[Reference guidance available.]" if reference else ""
    text = f"{prefix}\n\n{original.strip()}{reference_note}"
    return {"text": text, "input_tokens": max(1, (len(original) + len(reference or "")) // 4), "output_tokens": max(1, len(text) // 5), "actual_cost": 0.0}


def openai_translator(original: str, reference: str | None, settings: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    from openai import OpenAI

    model = settings.get("model") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    prompt = build_prompt(original, reference, settings)
    client = OpenAI(api_key=api_key)
    response = client.responses.create(model=model, input=prompt)
    text = response.output_text
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens, "actual_cost": 0.0}


def build_prompt(original: str, reference: str | None, settings: dict[str, Any]) -> str:
    guidance = [
        "Translate the Chinese source into natural professional English.",
        "The Chinese original is the source of truth.",
        "Preserve paragraphs and dialogue formatting.",
        "Do not summarize, skip, or add events.",
    ]
    if reference:
        guidance.append("Use the reference translation only as style guidance when it helps; never translate the reference instead of the original.")
    if settings.get("style_guide"):
        guidance.append(f"Style guide: {settings['style_guide']}")
    if settings.get("glossary"):
        guidance.append(f"Glossary: {settings['glossary']}")
    prompt = "\n".join(guidance) + "\n\nChinese original:\n" + original
    if reference:
        prompt += "\n\nReference translation:\n" + reference
    return prompt


def slugify(value: str) -> str:
    slug = re_sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


def re_sub(pattern: str, replacement: str, value: str) -> str:
    import re

    return re.sub(pattern, replacement, value)
