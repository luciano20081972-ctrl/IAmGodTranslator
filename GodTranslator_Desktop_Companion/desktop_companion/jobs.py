from __future__ import annotations

import threading
import time
from pathlib import Path

from .adapters import ADAPTERS
from .models import DownloadJob, new_id, utc_now
from .packs import build_auto_packs
from .paths import AppPaths
from .storage import CompanionStore


class JobManager:
    def __init__(self, store: CompanionStore, paths: AppPaths) -> None:
        self.store = store
        self.paths = paths
        self._stop_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}

    def create_job(
        self,
        novel_title: str,
        source_url: str,
        chapters: list[int],
        output_dir: Path | None = None,
        source_adapter: str = "novelfire",
        target_mode: str = "reference",
        browser_mode: bool = True,
        skip_existing: bool = True,
        resume_existing: bool = True,
        website_url: str = "",
        novel_id: str = "",
        auto_build_packs: bool = True,
        auto_upload: bool = False,
        delay_seconds: float = 3.0,
        retry_count: int = 2,
    ) -> DownloadJob:
        if source_adapter not in ADAPTERS:
            raise ValueError(f"Unsupported source adapter: {source_adapter}")
        folder = output_dir or self.paths.downloads_dir / safe_folder_name(novel_title)
        job = DownloadJob(
            id=new_id("job"),
            novel_title=novel_title,
            source_adapter=source_adapter,
            source_url=source_url,
            output_dir=str(folder),
            chapters=sorted({int(chapter) for chapter in chapters}),
            website_url=website_url,
            novel_id=novel_id or safe_folder_name(novel_title).lower().replace(" ", "-"),
            target_mode=target_mode if target_mode in {"reference", "original", "english", "mixed", "new_novel"} else "reference",
            browser_mode=browser_mode,
            skip_existing=skip_existing,
            resume_existing=resume_existing,
            auto_build_packs=auto_build_packs,
            auto_upload=auto_upload,
            delay_seconds=delay_seconds,
            retry_count=retry_count,
            last_activity="Queued",
        )
        return self.store.upsert_job(job)

    def pause(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        if job.status == "running":
            self.stop(job_id, next_status="paused")
            return self.require_job(job_id)
        job.status = "paused"
        job.last_activity = "Paused"
        return self.store.upsert_job(job)

    def resume(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        job.status = "queued"
        job.last_activity = "Ready to resume"
        return self.store.upsert_job(job)

    def stop(self, job_id: str, next_status: str = "cancelled") -> DownloadJob:
        event = self._stop_events.get(job_id)
        if event:
            event.set()
        job = self.require_job(job_id)
        job.status = next_status if next_status in {"paused", "cancelled"} else "cancelled"
        job.last_activity = "Stopped safely"
        job.finished_at = utc_now()
        return self.store.upsert_job(job)

    def retry_failed(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        failed_chapters = sorted(int(chapter) for chapter in job.errors.keys())
        if failed_chapters:
            job.chapters = failed_chapters
            job.failed = 0
            job.completed = 0
            job.skipped = 0
            job.errors = {}
        job.status = "queued"
        job.last_activity = "Failed chapters queued"
        return self.store.upsert_job(job)

    def start(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        if job.status == "running":
            return job
        event = threading.Event()
        self._stop_events[job_id] = event
        thread = threading.Thread(target=self._run_job, args=(job_id, event), name=f"gt-desktop-{job_id}", daemon=True)
        self._threads[job_id] = thread
        job.status = "running"
        job.started_at = job.started_at or utc_now()
        job.last_activity = "Starting"
        self.store.upsert_job(job)
        thread.start()
        return job

    def _run_job(self, job_id: str, stop_event: threading.Event) -> None:
        job = self.require_job(job_id)
        adapter = ADAPTERS[job.source_adapter]()
        output_dir = Path(job.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        options = adapter.build_options(
            novel_url=job.source_url,
            chapter_url_template="",
            chapters=job.chapters,
            output_dir=output_dir,
            browser_mode=job.browser_mode,
            browser_profile_dir=self.paths.browser_profiles_dir / job.source_adapter,
            delay=job.delay_seconds,
            retry_count=job.retry_count,
            skip_existing=job.skip_existing,
        )
        started = time.perf_counter()

        def log(message: str) -> None:
            current = self.require_job(job_id)
            current.last_activity = message
            self.store.upsert_job(current)
            self.store.append_log(f"{job_id} {message}")

        def progress(index: int, total: int, success: int, failed: int, skipped: int, current: str) -> None:
            current_job = self.require_job(job_id)
            current_job.completed = success
            current_job.failed = failed
            current_job.skipped = skipped
            current_job.current_chapter = parse_current_chapter(current)
            current_job.current_worker = threading.current_thread().name
            current_job.elapsed_seconds = round(time.perf_counter() - started, 2)
            remaining = max(0, total - index)
            if index > 0:
                current_job.estimated_remaining_seconds = round(current_job.elapsed_seconds / index * remaining, 2)
                current_job.download_speed_cpm = round(success / max(current_job.elapsed_seconds / 60, 0.01), 2)
            current_job.last_activity = current
            self.store.upsert_job(current_job)

        try:
            result = adapter.download(options, stop_event, log, progress)
            finished = self.require_job(job_id)
            finished.completed = int(result.get("success") or 0)
            finished.failed = int(result.get("failed") or 0)
            finished.skipped = int(result.get("skipped") or 0)
            finished.status = "failed" if finished.failed else "completed"
            finished.finished_at = utc_now()
            finished.last_activity = "Completed with failures" if finished.failed else "Completed"
            if finished.status == "completed" and finished.auto_build_packs:
                try:
                    packs = build_auto_packs(
                        source_dir=output_dir,
                        output_dir=self.paths.packs_dir,
                        novel_id=finished.novel_id or safe_folder_name(finished.novel_title).lower().replace(" ", "-"),
                        novel_title=finished.novel_title,
                        source_type=finished.source_adapter,
                        source_url=finished.source_url,
                    )
                    finished.packs_built = [str(pack.path) for pack in packs]
                    finished.last_activity = f"Completed and built {len(packs)} packs"
                    if finished.auto_upload and finished.website_url:
                        finished.website_import_status = "queued"
                except Exception as exc:
                    finished.website_import_status = "pack_build_failed"
                    finished.errors["pack_build"] = str(exc)
            self.store.upsert_job(finished)
        except Exception as exc:
            failed = self.require_job(job_id)
            failed.status = "failed"
            failed.last_activity = str(exc)
            failed.errors["job"] = str(exc)
            failed.finished_at = utc_now()
            self.store.upsert_job(failed)

    def require_job(self, job_id: str) -> DownloadJob:
        job = self.store.job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job


def safe_folder_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "-" for ch in value).strip()
    return text[:80] or "Untitled Novel"


def parse_current_chapter(value: str) -> int | None:
    for part in value.split():
        if part.isdigit():
            return int(part)
    return None
