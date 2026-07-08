from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import Database
from app.recovery import parse_uploads, recovery_request, reference_diagnostic


VERSION = "10.0.6"
ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="GodTranslator", version=VERSION)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
database = Database()


@app.on_event("startup")
def startup() -> None:
    database.initialize()


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        reachable = database.ping()
    except Exception as exc:
        return {"ok": False, "version": VERSION, "database": "unreachable", "error": exc.__class__.__name__}
    return {"ok": True, "version": VERSION, "database": "reachable" if reachable else "unreachable"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/api/novels")
def list_novels() -> dict[str, object]:
    return {"ok": True, "novels": database.novels()}


@app.get("/api/novels/{novel_id}")
def get_novel(novel_id: str) -> dict[str, object]:
    novel = database.novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    counts = database.verification_counts(novel_id)
    return {"ok": True, "novel": novel, "counts": counts}


@app.get("/api/novels/{novel_id}/library")
def library(novel_id: str, limit: int = Query(2000, ge=1, le=5000), offset: int = Query(0, ge=0)) -> dict[str, object]:
    payload = database.library(novel_id, limit=limit, offset=offset)
    if payload["novel"] is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, **payload, "counts": database.library_counts(novel_id)}


@app.get("/api/novels/{novel_id}/chapters/{chapter_number}/{mode}")
def chapter_text(novel_id: str, chapter_number: int, mode: str) -> dict[str, object]:
    if mode not in {"original", "reference", "ai"}:
        raise HTTPException(status_code=404, detail="chapter_mode_not_found")
    return database.chapter_text(novel_id, chapter_number, mode)


@app.get("/api/novels/{novel_id}/recovery/reference")
def reference_recovery_diagnostic(novel_id: str) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    return {"ok": True, **reference_diagnostic(database, novel_id)}


@app.get("/api/novels/{novel_id}/recovery/request")
def download_recovery_request(
    novel_id: str,
    source_url: str = Query("https://novelfire.net/book/i-am-god-lslccf"),
    chapter_url_template: str = Query("https://novelfire.net/book/i-am-god-lslccf/chapter-{chapter}"),
) -> JSONResponse:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    payload = recovery_request(database, novel_id, source_url=source_url, chapter_url_template=chapter_url_template)
    return JSONResponse(
        payload,
        headers={"Content-Disposition": f'attachment; filename="{novel_id}-reference-recovery-request.json"'},
    )


@app.post("/api/novels/{novel_id}/recovery/preview")
async def preview_reference_import(novel_id: str, files: list[UploadFile] = File(...)) -> dict[str, object]:
    if database.novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="novel_not_found")
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        payloads.append((upload.filename or "upload.txt", await upload.read()))
    return parse_uploads(payloads, novel_id, database)


@app.get("/api/import-jobs/{job_id}")
def get_import_job(job_id: str) -> dict[str, object]:
    job = database.import_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_job_not_found")
    return {"ok": True, "job": job}


@app.post("/api/novels/{novel_id}/recovery/import/{job_id}")
def apply_reference_import(novel_id: str, job_id: str) -> dict[str, object]:
    job = database.import_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="import_job_not_found")
    if job["novel_id"] != novel_id:
        raise HTTPException(status_code=400, detail="import_job_novel_mismatch")
    return database.apply_import_job(job_id)
