from __future__ import annotations

import logging
import os
import hmac
import hashlib
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.novels import NovelManager
from app.services import PROJECT_ROOT, TranslationService


load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

app = FastAPI(title="IAmGodTranslator", version="2.0.0")
service = TranslationService()
novels = NovelManager(service)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ADMIN_COOKIE = "igt_admin"


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


@app.get("/api/storage")
async def storage_status() -> dict[str, object]:
    status = service.storage_status()
    status["novels"] = len(novels.list_novels())
    status["backend"] = os.getenv("STORAGE_BACKEND", "local").lower()
    status["supabase_enabled"] = novels.remote is not None
    return status


@app.post("/api/admin/storage/sync-supabase")
async def sync_storage_to_supabase(request: Request) -> dict[str, object]:
    require_admin(request)
    if novels.remote is None:
        raise HTTPException(status_code=400, detail="Supabase storage is not enabled.")
    return novels.sync_all_to_remote()


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
    try:
        job = await service.restore_backup(backup)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(job, status_code=201)


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
    zip_path = service.build_backup_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


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
    return novels.library(novel_id)


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
    zip_path = novels.build_backup_zip(novel_id)
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.post("/api/novels/{novel_id}/restore")
async def restore_novel_backup(request: Request, novel_id: str, backup: Annotated[UploadFile, File(description="Full novel backup ZIP")]) -> JSONResponse:
    require_admin(request)
    return JSONResponse(await novels.restore_backup(novel_id, backup), status_code=201)


@app.get("/api/reader/last")
async def get_last_reader() -> dict[str, object]:
    return novels.last_reader()


@app.post("/api/reader/last")
async def save_last_reader(payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    try:
        return novels.save_last_reader(str(payload["novel_id"]), int(payload["chapter"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid reader state.") from exc
