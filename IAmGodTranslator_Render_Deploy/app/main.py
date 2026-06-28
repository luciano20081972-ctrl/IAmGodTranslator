from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
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


@app.get("/api/storage")
async def storage_status() -> dict[str, object]:
    status = service.storage_status()
    status["novels"] = len(novels.list_novels())
    return status


@app.get("/api/jobs")
async def list_jobs() -> dict[str, object]:
    return {"jobs": service.list_jobs()}


@app.post("/api/jobs")
async def create_job(
    chinese: Annotated[list[UploadFile], File(description="Chinese TXT files or ZIP archives")],
    references: Annotated[list[UploadFile] | None, File(description="Optional NovelFire reference TXT files or ZIP archives")] = None,
    max_total_budget: Annotated[str | None, Form()] = None,
    max_cost_per_chapter: Annotated[str | None, Form()] = None,
    stop_when_budget_reached: Annotated[bool, Form()] = True,
    test_chapter_only: Annotated[bool, Form()] = True,
    show_estimate_before_starting: Annotated[bool, Form()] = True,
    retry_failed_chapters: Annotated[int, Form()] = 1,
) -> JSONResponse:
    try:
        job = await service.create_job(chinese, references, settings={"max_total_budget": max_total_budget, "max_cost_per_chapter": max_cost_per_chapter, "stop_when_budget_reached": stop_when_budget_reached, "test_chapter_only": test_chapter_only, "show_estimate_before_starting": show_estimate_before_starting, "retry_failed_chapters": retry_failed_chapters})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(job, status_code=201)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    try:
        job = service.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str) -> dict[str, str]:
    if service.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    service.start_job(job_id)
    return {"status": "queued"}


@app.post("/api/jobs/restore")
async def restore_job_backup(backup: Annotated[UploadFile, File(description="Full job backup ZIP")]) -> JSONResponse:
    try:
        job = await service.restore_backup(backup)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(job, status_code=201)


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    zip_path = service.build_download_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No translated chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/jobs/{job_id}/prompts/download")
async def download_prompts(job_id: str) -> FileResponse:
    zip_path = service.build_prompts_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No saved prompts are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/jobs/{job_id}/backup")
async def download_job_backup(job_id: str) -> FileResponse:
    zip_path = service.build_backup_zip(job_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/jobs/{job_id}/estimate-report")
async def download_estimate_report(job_id: str) -> FileResponse:
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
async def create_novel(payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    return JSONResponse(novels.create_novel(str(payload.get("title") or "Untitled Novel")), status_code=201)


@app.get("/api/novels/{novel_id}")
async def get_novel(novel_id: str) -> dict[str, object]:
    try:
        return novels.get_novel(novel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/novels/{novel_id}")
async def update_novel(novel_id: str, payload: Annotated[dict[str, object], Body()]) -> dict[str, object]:
    try:
        return novels.update_novel(novel_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/novels/{novel_id}")
async def delete_novel(novel_id: str) -> dict[str, str]:
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
async def upload_original(novel_id: str, original: Annotated[list[UploadFile], File(description="Original Story TXT files or ZIP archives")]) -> JSONResponse:
    return JSONResponse(await novels.upload_original(novel_id, original), status_code=201)


@app.post("/api/novels/{novel_id}/upload/reference")
async def upload_reference(novel_id: str, reference: Annotated[list[UploadFile], File(description="Reference Translation TXT files or ZIP archives")]) -> JSONResponse:
    return JSONResponse(await novels.upload_reference(novel_id, reference), status_code=201)


@app.post("/api/novels/{novel_id}/import/ai-translations")
async def import_ai_translations(novel_id: str, translated_zip: Annotated[UploadFile, File(description="AI translated chapters ZIP")]) -> JSONResponse:
    return JSONResponse(await novels.import_ai_translations(novel_id, translated_zip), status_code=201)


@app.post("/api/novels/{novel_id}/import/original")
async def import_original_zip(novel_id: str, original_zip: Annotated[UploadFile, File(description="Original Story ZIP")]) -> JSONResponse:
    try:
        return JSONResponse(await novels.import_original_zip(novel_id, original_zip), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/novels/{novel_id}/import/reference")
async def import_reference_zip(novel_id: str, reference_zip: Annotated[UploadFile, File(description="Reference Translation ZIP")]) -> JSONResponse:
    try:
        return JSONResponse(await novels.import_reference_zip(novel_id, reference_zip), status_code=201)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/novels/{novel_id}/cover")
async def upload_novel_cover(novel_id: str, cover: Annotated[UploadFile, File(description="Novel cover image")]) -> JSONResponse:
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
async def create_novel_batch(novel_id: str, payload: Annotated[dict[str, object], Body()]) -> JSONResponse:
    settings = dict(payload)
    start_now = bool(settings.pop("start_now", False))
    job = novels.create_batch(novel_id, settings)
    if start_now:
        novels.start_job(novel_id, job["job_id"])
    return JSONResponse(job, status_code=201)


@app.post("/api/novels/{novel_id}/jobs/{job_id}/start")
async def start_novel_job(novel_id: str, job_id: str) -> dict[str, str]:
    novels.start_job(novel_id, job_id)
    return {"status": "queued"}


@app.get("/api/novels/{novel_id}/jobs/{job_id}")
async def get_novel_job(novel_id: str, job_id: str) -> dict[str, object]:
    job = novels.service_for(novel_id).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/novels/{novel_id}/download/english")
async def download_novel_english(novel_id: str) -> FileResponse:
    zip_path = novels.build_english_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No translated chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/original")
async def download_novel_original(novel_id: str) -> FileResponse:
    zip_path = novels.build_original_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No Original Story chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/reference")
async def download_novel_reference(novel_id: str) -> FileResponse:
    zip_path = novels.build_reference_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No Reference Translation chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/ai")
async def download_novel_ai(novel_id: str) -> FileResponse:
    zip_path = novels.build_ai_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No AI Translation chapters are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/download/prompts")
async def download_novel_prompts(novel_id: str) -> FileResponse:
    zip_path = novels.build_prompts_zip(novel_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="No saved prompts are available yet.")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.get("/api/novels/{novel_id}/backup")
async def download_novel_backup(novel_id: str) -> FileResponse:
    zip_path = novels.build_backup_zip(novel_id)
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@app.post("/api/novels/{novel_id}/restore")
async def restore_novel_backup(novel_id: str, backup: Annotated[UploadFile, File(description="Full novel backup ZIP")]) -> JSONResponse:
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
