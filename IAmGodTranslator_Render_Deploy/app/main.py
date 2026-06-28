from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.services import PROJECT_ROOT, TranslationService


load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

app = FastAPI(title="IAmGodTranslator", version="1.0.0")
service = TranslationService()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def resume_jobs() -> None:
    resumed = service.resume_incomplete_jobs()

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


@app.get("/api/jobs")
async def list_jobs() -> dict[str, object]:
    return {"jobs": service.list_jobs()}


@app.post("/api/jobs")
async def create_job(
    chinese: Annotated[list[UploadFile], File(description="Chinese TXT files or ZIP archives")],
    references: Annotated[
        list[UploadFile] | None,
        File(description="Optional NovelFire reference TXT files or ZIP archives"),
    ] = None,
    max_total_budget: Annotated[str | None, Form()] = None,
    max_cost_per_chapter: Annotated[str | None, Form()] = None,
    stop_when_budget_reached: Annotated[bool, Form()] = True,
    test_chapter_only: Annotated[bool, Form()] = True,
    show_estimate_before_starting: Annotated[bool, Form()] = True,
    retry_failed_chapters: Annotated[int, Form()] = 1,
) -> JSONResponse:
    try:
        job = await service.create_job(
            chinese,
            references,
            settings={
                "max_total_budget": max_total_budget,
                "max_cost_per_chapter": max_cost_per_chapter,
                "stop_when_budget_reached": stop_when_budget_reached,
                "test_chapter_only": test_chapter_only,
                "show_estimate_before_starting": show_estimate_before_starting,
                "retry_failed_chapters": retry_failed_chapters,
            },
        )
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
    try:
        job = service.get_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    service.start_job(job_id)
    return {"status": "queued"}


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str) -> FileResponse:
    try:
        zip_path = service.build_download_zip(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if zip_path is None:
        raise HTTPException(status_code=404, detail="No translated chapters are available yet.")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


@app.get("/api/jobs/{job_id}/estimate-report")
async def download_estimate_report(job_id: str) -> FileResponse:
    try:
        report = service.estimate_report(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if report is None:
        raise HTTPException(status_code=404, detail="Estimate report not found.")

    return FileResponse(
        report,
        media_type="text/markdown; charset=utf-8",
        filename=report.name,
    )


@app.get("/api/jobs/{job_id}/chapters/{chapter}/download")
async def download_chapter(job_id: str, chapter: int) -> FileResponse:
    try:
        output = service.chapter_output(job_id, chapter)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if output is None:
        raise HTTPException(status_code=404, detail="Translated chapter not found.")

    return FileResponse(
        output,
        media_type="text/plain; charset=utf-8",
        filename=output.name,
    )
