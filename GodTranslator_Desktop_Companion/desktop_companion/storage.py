from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DownloadJob, UploadJob, WebsiteConnectionProfile, utc_now
from .paths import AppPaths, ensure_app_dirs


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class CompanionStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        ensure_app_dirs(paths)

    def settings(self) -> dict[str, Any]:
        payload = read_json(self.paths.settings_file, {})
        if not payload:
            payload = {
                "mode": "simple",
                "downloads_folder": str(self.paths.downloads_dir),
                "default_adapter": "novelfire",
                "default_website_url": "https://iamgodtranslator.onrender.com",
                "created_at": utc_now(),
            }
            write_json(self.paths.settings_file, payload)
        return payload

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.settings()
        current.update(payload)
        current["updated_at"] = utc_now()
        write_json(self.paths.settings_file, current)
        return current

    def jobs(self) -> list[DownloadJob]:
        payload = read_json(self.paths.jobs_file, {"jobs": []})
        return [DownloadJob.from_dict(item) for item in payload.get("jobs", []) if isinstance(item, dict)]

    def save_jobs(self, jobs: list[DownloadJob]) -> None:
        write_json(self.paths.jobs_file, {"updated_at": utc_now(), "jobs": [job.to_dict() for job in jobs]})

    def upsert_job(self, job: DownloadJob) -> DownloadJob:
        jobs = [item for item in self.jobs() if item.id != job.id]
        job.updated_at = utc_now()
        jobs.insert(0, job)
        self.save_jobs(jobs)
        return job

    def job(self, job_id: str) -> DownloadJob | None:
        return next((job for job in self.jobs() if job.id == job_id), None)

    def uploads(self) -> list[UploadJob]:
        payload = read_json(self.paths.uploads_file, {"uploads": []})
        return [UploadJob.from_dict(item) for item in payload.get("uploads", []) if isinstance(item, dict)]

    def save_uploads(self, uploads: list[UploadJob]) -> None:
        write_json(self.paths.uploads_file, {"updated_at": utc_now(), "uploads": [upload.to_dict() for upload in uploads]})

    def upsert_upload(self, upload: UploadJob) -> UploadJob:
        uploads = [item for item in self.uploads() if item.id != upload.id]
        upload.updated_at = utc_now()
        uploads.insert(0, upload)
        self.save_uploads(uploads)
        return upload

    def upload(self, upload_id: str) -> UploadJob | None:
        return next((upload for upload in self.uploads() if upload.id == upload_id), None)

    def connection_profiles(self) -> list[WebsiteConnectionProfile]:
        payload = read_json(self.paths.connection_profiles_file, {"profiles": []})
        profiles = []
        for item in payload.get("profiles", []):
            if isinstance(item, dict):
                profiles.append(
                    WebsiteConnectionProfile(
                        name=item.get("name") or "Production",
                        base_url=item.get("base_url") or "https://iamgodtranslator.onrender.com",
                        auth_token=item.get("auth_token") or "",
                        last_health=item.get("last_health") or "Not tested",
                        last_sync_at=item.get("last_sync_at") or "",
                    )
                )
        if not profiles:
            profiles = [WebsiteConnectionProfile()]
            self.save_connection_profiles(profiles)
        return profiles

    def save_connection_profiles(self, profiles: list[WebsiteConnectionProfile]) -> None:
        # Tokens are session tokens entered by the user, never plaintext passwords.
        write_json(self.paths.connection_profiles_file, {"updated_at": utc_now(), "profiles": [profile.__dict__ for profile in profiles]})

    def append_log(self, message: str) -> None:
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        line = f"{utc_now()} {message}\n"
        with (self.paths.logs_dir / "activity.log").open("a", encoding="utf-8") as handle:
            handle.write(line)
