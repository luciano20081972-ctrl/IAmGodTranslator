from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .adapters import ADAPTERS
from .models import DownloadJob, new_id, utc_now
from .packs import build_pack
from .paths import AppPaths
from .storage import CompanionStore


ACTIVE_STATUSES = {"starting", "opening_browser", "waiting_cloudflare", "downloading", "retrying"}
CHAPTER_RE = re.compile(r"\bchapter\s+(\d+)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
LOG_LIMIT = 400


@dataclass
class JobControl:
    stop_event: threading.Event
    action: str = ""


class JobManager:
    def __init__(self, store: CompanionStore, paths: AppPaths) -> None:
        self.store = store
        self.paths = paths
        self._lock = threading.Lock()
        self._controls: dict[str, JobControl] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._recover_interrupted_jobs()

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
        resolved_mode = target_mode if target_mode in {"reference", "original", "english", "mixed", "new_novel"} else "reference"
        root_dir, content_dir = self._job_folders(output_dir, novel_title, resolved_mode)
        job = DownloadJob(
            id=new_id("job"),
            novel_title=novel_title,
            source_adapter=source_adapter,
            source_url=source_url,
            output_dir=str(content_dir),
            novel_root_dir=str(root_dir),
            chapters=sorted({int(chapter) for chapter in chapters}),
            website_url=website_url,
            novel_id=novel_id or safe_folder_name(novel_title).lower().replace(" ", "-"),
            target_mode=resolved_mode,
            browser_mode=browser_mode,
            skip_existing=skip_existing,
            resume_existing=resume_existing,
            auto_build_packs=auto_build_packs,
            auto_upload=auto_upload,
            delay_seconds=delay_seconds,
            retry_count=retry_count,
            last_activity="Queued",
            worker_state="Queued",
            browser_state="Not started",
        )
        self._append_live_log(job, "Job queued")
        return self.store.upsert_job(job)

    def pause(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        control = self._controls.get(job_id)
        if control and self._thread_alive(job_id):
            control.action = "pause"
            control.stop_event.set()
            job.worker_state = "Pause requested - finishing current chapter"
            job.last_activity = "Pause requested"
            self._append_live_log(job, "Pause requested")
            return self.store.upsert_job(job)
        job.status = "paused"
        job.worker_state = "Paused"
        job.browser_state = "Closed"
        job.last_activity = "Paused"
        self._append_live_log(job, "Job paused")
        return self.store.upsert_job(job)

    def resume(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        job.status = "queued"
        job.finished_at = None
        job.worker_state = "Ready to resume"
        job.browser_state = "Closed"
        job.last_activity = "Ready to resume"
        self._append_live_log(job, "Resume queued")
        return self.store.upsert_job(job)

    def stop(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        control = self._controls.get(job_id)
        if control and self._thread_alive(job_id):
            control.action = "stop"
            control.stop_event.set()
            job.worker_state = "Stop requested - closing after current operation"
            job.last_activity = "Stop requested"
            self._append_live_log(job, "Stop requested")
            return self.store.upsert_job(job)
        job.status = "stopped"
        job.worker_state = "Stopped"
        job.browser_state = "Closed"
        job.finished_at = utc_now()
        job.last_activity = "Stopped"
        self._append_live_log(job, "Job stopped")
        return self.store.upsert_job(job)

    def retry_failed(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        failed_chapters = sorted(set(job.failed_chapters) | {int(chapter) for chapter in job.errors if str(chapter).isdigit()})
        if failed_chapters:
            job.chapters = failed_chapters
            job.failed = 0
            job.completed = 0
            job.skipped = 0
            job.failed_chapters = []
            job.errors = {}
        job.status = "queued"
        job.finished_at = None
        job.worker_state = "Failed chapters queued"
        job.last_activity = "Failed chapters queued"
        self._append_live_log(job, "Retry failed queued")
        return self.store.upsert_job(job)

    def restart_job(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        job.status = "queued"
        job.completed = 0
        job.failed = 0
        job.skipped = 0
        job.current_chapter = None
        job.current_url = ""
        job.last_downloaded_chapter = None
        job.downloaded_chapters = []
        job.failed_chapters = []
        job.retry_events = 0
        job.errors = {}
        job.finished_at = None
        job.elapsed_seconds = 0.0
        job.estimated_remaining_seconds = None
        job.download_speed_cpm = 0.0
        job.worker_state = "Restart queued"
        job.browser_state = "Closed"
        job.last_activity = "Restart queued"
        job.skip_existing = False
        job.live_log = []
        self._append_live_log(job, "Restart queued")
        return self.store.upsert_job(job)

    def duplicate_job(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        source_root = Path(job.novel_root_dir or Path(job.output_dir).parent)
        duplicate_root = unique_path(source_root.with_name(f"{source_root.name} Copy"))
        return self.create_job(
            novel_title=f"{job.novel_title} Copy",
            source_url=job.source_url,
            chapters=job.chapters,
            output_dir=duplicate_root,
            source_adapter=job.source_adapter,
            target_mode=job.target_mode,
            browser_mode=job.browser_mode,
            skip_existing=job.skip_existing,
            resume_existing=job.resume_existing,
            website_url=job.website_url,
            novel_id=f"{job.novel_id}-copy" if job.novel_id else "",
            auto_build_packs=job.auto_build_packs,
            auto_upload=job.auto_upload,
            delay_seconds=job.delay_seconds,
            retry_count=job.retry_count,
        )

    def delete_job(self, job_id: str) -> None:
        if self._thread_alive(job_id):
            raise ValueError("Stop the job before deleting it.")
        self.store.delete_job(job_id)

    def start(self, job_id: str) -> DownloadJob:
        with self._lock:
            job = self.require_job(job_id)
            if self._thread_alive(job_id):
                return job
            if job.status == "completed":
                return job
            if job.browser_mode and self._active_browser_jobs(exclude_job_id=job_id) >= self.max_active_browser_jobs:
                job.status = "queued"
                job.worker_state = f"Queued - waiting for browser slot ({self.max_active_browser_jobs} max)"
                job.browser_state = "Queued"
                job.last_activity = "Waiting for browser slot"
                self._append_live_log(job, job.last_activity)
                return self.store.upsert_job(job)
            control = JobControl(stop_event=threading.Event())
            self._controls[job_id] = control
            thread = threading.Thread(target=self._run_job, args=(job_id, control), name=f"gt-desktop-{job_id}", daemon=True)
            self._threads[job_id] = thread
            job.status = "starting"
            job.started_at = job.started_at or utc_now()
            job.finished_at = None
            job.worker_state = "Starting"
            job.browser_state = "Not launched"
            job.last_activity = "Starting"
            self._append_live_log(job, "Starting job")
            self.store.upsert_job(job)
            thread.start()
            return job

    def _run_job(self, job_id: str, control: JobControl) -> None:
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
            skip_existing=job.skip_existing if not job.resume_existing else True,
        )
        started = time.perf_counter()

        def log(message: str) -> None:
            current = self.require_job(job_id)
            self._apply_log_message(current, message)
            self.store.upsert_job(current)
            self.store.append_log(f"{job_id} {message}")

        def progress(index: int, total: int, success: int, failed: int, skipped: int, current: str) -> None:
            current_job = self.require_job(job_id)
            current_job.completed = success
            current_job.failed = failed
            current_job.skipped = skipped
            chapter = parse_current_chapter(current)
            if chapter is not None:
                current_job.current_chapter = chapter
            current_job.current_worker = threading.current_thread().name
            current_job.worker_state = "Downloading" if current_job.status in ACTIVE_STATUSES else current_job.worker_state
            current_job.elapsed_seconds = round(time.perf_counter() - started, 2)
            remaining = max(0, total - index)
            if index > 0:
                current_job.estimated_remaining_seconds = round(current_job.elapsed_seconds / index * remaining, 2)
                current_job.download_speed_cpm = round(success / max(current_job.elapsed_seconds / 60, 0.01), 2)
            if current_job.status in {"starting", "opening_browser", "waiting_cloudflare"} and index > 0:
                current_job.status = "downloading"
            current_job.last_activity = current
            self.store.upsert_job(current_job)

        try:
            result = adapter.download(options, control.stop_event, log, progress)
            finished = self.require_job(job_id)
            finished.completed = int(result.get("success") or 0)
            finished.failed = int(result.get("failed") or 0)
            finished.skipped = int(result.get("skipped") or 0)
            finished.elapsed_seconds = round(time.perf_counter() - started, 2)
            if control.action == "pause":
                finished.status = "paused"
                finished.worker_state = "Paused"
                finished.browser_state = "Closed"
                finished.finished_at = None
                finished.last_activity = "Job paused"
                self._append_live_log(finished, "Job paused")
            elif control.action == "stop":
                finished.status = "stopped"
                finished.worker_state = "Stopped"
                finished.browser_state = "Closed"
                finished.finished_at = utc_now()
                finished.last_activity = "Job stopped"
                self._append_live_log(finished, "Job stopped")
            else:
                finished.status = "failed" if finished.failed else "completed"
                finished.worker_state = "Failed" if finished.failed else "Completed"
                finished.browser_state = "Closed"
                finished.finished_at = utc_now()
                finished.last_activity = "Completed with failures" if finished.failed else "Completed"
                self._append_live_log(finished, finished.last_activity)
            if finished.status == "completed" and finished.auto_build_packs:
                try:
                    pack_dir = Path(finished.novel_root_dir or output_dir.parent) / "Packs"
                    pack = build_pack(
                        source_dir=output_dir,
                        output_dir=pack_dir,
                        novel_id=finished.novel_id or safe_folder_name(finished.novel_title).lower().replace(" ", "-"),
                        novel_title=finished.novel_title,
                        target_mode=finished.target_mode,
                        source_type=finished.source_adapter,
                        source_url=finished.source_url,
                    )
                    finished.packs_built = [str(pack.path)]
                    finished.last_activity = "Completed and built 1 pack"
                    self._append_live_log(finished, finished.last_activity)
                    if finished.auto_upload and finished.website_url:
                        finished.website_import_status = "queued"
                except Exception as exc:
                    finished.website_import_status = "pack_build_failed"
                    finished.errors["pack_build"] = str(exc)
                    self._append_live_log(finished, f"Pack build failed: {exc}")
            self.store.upsert_job(finished)
        except Exception as exc:
            failed = self.require_job(job_id)
            if control.action == "pause":
                failed.status = "paused"
                failed.worker_state = "Paused after interruption"
                failed.last_activity = "Job paused"
                self._append_live_log(failed, "Job paused after downloader interruption")
            elif control.action == "stop":
                failed.status = "stopped"
                failed.worker_state = "Stopped after interruption"
                failed.last_activity = "Job stopped"
                self._append_live_log(failed, "Job stopped after downloader interruption")
            else:
                failed.status = "failed"
                failed.worker_state = "Failed"
                failed.last_activity = str(exc)
                failed.errors["job"] = str(exc)
                self._append_live_log(failed, f"Job failed: {exc}")
            failed.browser_state = "Closed"
            failed.finished_at = None if failed.status == "paused" else utc_now()
            self.store.upsert_job(failed)
        finally:
            self._controls.pop(job_id, None)
            self._start_next_queued_job()

    def require_job(self, job_id: str) -> DownloadJob:
        job = self.store.job(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job

    def build_pack_for_job(self, job_id: str) -> DownloadJob:
        job = self.require_job(job_id)
        output_dir = Path(job.output_dir)
        pack_dir = Path(job.novel_root_dir or output_dir.parent) / "Packs"
        pack = build_pack(
            source_dir=output_dir,
            output_dir=pack_dir,
            novel_id=job.novel_id or safe_folder_name(job.novel_title).lower().replace(" ", "-"),
            novel_title=job.novel_title,
            target_mode=job.target_mode,
            source_type=job.source_adapter,
            source_url=job.source_url,
        )
        job.packs_built = sorted(set(job.packs_built + [str(pack.path)]))
        job.website_import_status = "pack_ready"
        job.last_activity = f"Built pack {pack.path.name}"
        self._append_live_log(job, job.last_activity)
        return self.store.upsert_job(job)

    def _job_folders(self, output_dir: Path | None, novel_title: str, target_mode: str) -> tuple[Path, Path]:
        base = output_dir or self.paths.downloads_dir / safe_folder_name(novel_title)
        base = base.expanduser()
        mode_folder = content_folder_for_target(target_mode)
        if base.name.lower() in {"original", "reference", "english"}:
            root = base.parent
            content = base
        elif base.resolve() == self.paths.downloads_dir.resolve():
            root = base / safe_folder_name(novel_title)
            content = root / mode_folder
        else:
            root = base
            content = root / mode_folder
        return root, content

    def _thread_alive(self, job_id: str) -> bool:
        thread = self._threads.get(job_id)
        return bool(thread and thread.is_alive())

    @property
    def max_active_browser_jobs(self) -> int:
        try:
            return max(1, min(4, int(self.store.settings().get("max_active_browser_jobs") or 1)))
        except Exception:
            return 1

    def _active_browser_jobs(self, exclude_job_id: str = "") -> int:
        active = 0
        for job_id, thread in self._threads.items():
            if job_id == exclude_job_id or not thread.is_alive():
                continue
            job = self.store.job(job_id)
            if job and job.browser_mode and job.status in ACTIVE_STATUSES:
                active += 1
        return active

    def _start_next_queued_job(self) -> None:
        queued = [
            job
            for job in sorted(self.store.jobs(), key=lambda item: item.created_at)
            if job.status == "queued" and not self._thread_alive(job.id)
        ]
        if not queued or self._active_browser_jobs() >= self.max_active_browser_jobs:
            return
        for job in queued:
            started = self.start(job.id)
            if started.status == "starting":
                break

    def _recover_interrupted_jobs(self) -> None:
        recovered = []
        for job in self.store.jobs():
            if job.status in ACTIVE_STATUSES:
                job.status = "paused"
                job.worker_state = "Interrupted - ready to resume"
                job.browser_state = "Closed"
                job.last_activity = "Interrupted by desktop restart; ready to resume"
                self._append_live_log(job, "Desktop restarted while job was active")
                recovered.append(job)
            else:
                recovered.append(job)
        if recovered:
            self.store.save_jobs(recovered)

    def _append_live_log(self, job: DownloadJob, message: str) -> None:
        job.live_log = (job.live_log + [f"{utc_now()} {message}"])[-LOG_LIMIT:]

    def _apply_log_message(self, job: DownloadJob, message: str) -> None:
        lower = message.lower()
        job.last_activity = message
        self._append_live_log(job, message)
        chapter = parse_current_chapter(message)
        if chapter is not None:
            job.current_chapter = chapter
        url = parse_url(message)
        if url:
            job.current_url = url
        if "opening browser" in lower or "visible chrome" in lower:
            job.status = "opening_browser"
            job.browser_state = "Opening Browser"
            job.worker_state = "Opening Browser"
        elif "browser launched" in lower:
            job.status = "opening_browser"
            job.browser_state = "Launched"
            job.worker_state = "Opening Browser"
        elif "cloudflare" in lower or "verification" in lower or "challenge" in lower:
            job.status = "waiting_cloudflare"
            job.browser_state = "Waiting Cloudflare"
            job.worker_state = "Waiting Cloudflare"
        elif "downloading chapter" in lower:
            job.status = "downloading"
            job.browser_state = "Active" if job.browser_mode else "HTTP"
            job.worker_state = "Downloading"
        elif "retry chapter" in lower:
            job.status = "retrying"
            job.worker_state = "Retrying"
            job.retry_events += 1
        elif "saved chapter" in lower or "downloaded chapter" in lower:
            if chapter is not None:
                job.last_downloaded_chapter = chapter
                job.downloaded_chapters = sorted(set(job.downloaded_chapters + [chapter]))
                job.failed_chapters = [item for item in job.failed_chapters if item != chapter]
                job.errors.pop(str(chapter), None)
            if job.status != "paused":
                job.status = "downloading"
            job.worker_state = "Downloading"
        elif "failed chapter" in lower:
            if chapter is not None:
                job.failed_chapters = sorted(set(job.failed_chapters + [chapter]))
                job.errors[str(chapter)] = message
            job.worker_state = "Failed chapter"
        elif "skipped existing" in lower:
            job.worker_state = "Skipping existing valid chapter"
        elif "browser closed" in lower:
            job.browser_state = "Closed"
        elif "stopped" in lower:
            job.worker_state = "Stopping"
        elif "paused" in lower:
            job.worker_state = "Pausing"


def safe_folder_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "-" for ch in value).strip()
    return text[:80] or "Untitled Novel"


def content_folder_for_target(target_mode: str) -> str:
    if target_mode == "english":
        return "English"
    if target_mode == "reference":
        return "Reference"
    return "Original"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.name} {index}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.name} {int(time.time())}")


def parse_current_chapter(value: str) -> int | None:
    match = CHAPTER_RE.search(value or "")
    if match:
        return int(match.group(1))
    for part in (value or "").split():
        if part.isdigit():
            return int(part)
    return None


def parse_url(value: str) -> str:
    match = URL_RE.search(value or "")
    return match.group(0).rstrip(").,") if match else ""
