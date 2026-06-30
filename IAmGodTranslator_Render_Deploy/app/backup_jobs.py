from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.storage import SupabaseStorage
from modules.chapter import chapter_from_filename, parse_chapter


logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BackupJobManager:
    def __init__(self, data_dir: Path, novels, database, storage_backend: str):
        self.data_dir = data_dir
        self.novels = novels
        self.database = database
        self.storage_backend = storage_backend
        self.jobs_dir = data_dir / "backup_jobs"
        self.output_dir = data_dir / "exports"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}
        self._cancel: set[str] = set()
        self._mark_stale_jobs()

    def _mark_stale_jobs(self) -> None:
        for path in self.jobs_dir.glob("*.json"):
            try:
                job = self._read(path)
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") in {"queued", "running"}:
                job.update({"status": "stale", "finished_at": utc_now(), "message": "Job was interrupted by process restart.", "progress": job.get("progress", 0)})
                self._write(job)

    def start_full_backup(self) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job = {
            "ok": True,
            "job_id": job_id,
            "type": "full_backup",
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "Backup queued.",
            "started_at": utc_now(),
            "finished_at": None,
            "backup_file": None,
            "counts": {},
            "error": None,
            "warnings": [],
        }
        self._write(job)
        thread = threading.Thread(target=self._run_full_backup, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()
        return job

    def start_full_restore(self, data: bytes, filename: str, dry_run: bool = True, conflict_mode: str = "write_missing_only") -> dict[str, Any]:
        if conflict_mode not in {"write_missing_only", "skip_existing", "overwrite_existing"}:
            raise ValueError("Invalid conflict_mode.")
        job_id = uuid.uuid4().hex
        upload_name = filename or "restore-backup.zip"
        upload_path = self.jobs_dir / f"{job_id}-{Path(upload_name).name}"
        upload_path.write_bytes(data)
        job = {
            "ok": True,
            "job_id": job_id,
            "type": "full_restore",
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "Restore queued.",
            "started_at": utc_now(),
            "finished_at": None,
            "backup_file": str(upload_path),
            "dry_run": dry_run,
            "conflict_mode": conflict_mode,
            "counts": self._empty_restore_counts(),
            "error": None,
            "warnings": [],
        }
        self._write(job)
        thread = threading.Thread(target=self._run_full_restore, args=(job_id,), daemon=True)
        self._threads[job_id] = thread
        thread.start()
        return job

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []
        for path in sorted(self.jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                jobs.append(self._read(path))
            except (OSError, json.JSONDecodeError):
                continue
        return jobs[:50]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        path = self.jobs_dir / f"{job_id}.json"
        if not path.exists():
            return None
        return self._read(path)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.get_job(job_id)
        if job is None:
            return None
        if job.get("status") in {"queued", "running"}:
            self._cancel.add(job_id)
            job.update({"status": "cancelled", "finished_at": utc_now(), "message": "Cancellation requested.", "progress": job.get("progress", 0)})
            self._write(job)
        return job

    def latest(self) -> dict[str, Any] | None:
        completed = [job for job in self.list_jobs() if job.get("status") == "complete"]
        return completed[0] if completed else None

    def _run_full_backup(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        try:
            self._update(job, status="running", stage="inventory", progress=5, message="Collecting backup inventory.")
            novel_items = self.novels.iter_metadata()
            backup_name = f"godtranslator_full_backup_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.zip"
            temp_path = self.output_dir / f".{backup_name}.{job_id}.tmp"
            final_path = self.output_dir / backup_name
            manifest: dict[str, Any] = {
                "app": "GodTranslator",
                "backup_version": "7.0-partial",
                "schema_version": 1,
                "created_at": utc_now(),
                "storage_backend": self.storage_backend,
                "database_backend": self.database.status().get("backend"),
                "novel_ids": [item["novel_id"] for item in novel_items],
                "path_mapping": {
                    "originals": "novels/{novel_id}/originals/{chapter_number}.txt",
                    "references": "novels/{novel_id}/references/{chapter_number}.txt",
                    "ai_translations": "novels/{novel_id}/ai_translations/{chapter_number}.txt",
                    "prompts": "novels/{novel_id}/prompts/{chapter_number}.txt",
                },
                "counts": {},
                "files": [],
            }
            total_files = 1 + sum(1 for novel in novel_items for _ in self._backup_files_for(str(novel["novel_id"])))
            written = 0
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                self._write_json_entry(archive, "backup_info.json", {"created_at": utc_now(), "job_id": job_id, "note": "No secrets, sessions, database files, or logs are included."})
                written += 1
                for novel in novel_items:
                    if job_id in self._cancel:
                        raise RuntimeError("Backup cancelled.")
                    novel_id = str(novel["novel_id"])
                    counts = {"originals": 0, "references": 0, "ai_translations": 0, "prompts": 0, "covers": 0}
                    self._write_json_entry(archive, f"novels/{novel_id}/metadata.json", novel)
                    manifest["files"].append({"path": f"novels/{novel_id}/metadata.json", "sha256": hashlib.sha256(json.dumps(novel, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(), "bytes": 0})
                    for source, arcname, kind in self._backup_files_for(novel_id):
                        if job_id in self._cancel:
                            raise RuntimeError("Backup cancelled.")
                        archive.write(source, arcname)
                        counts[kind] = counts.get(kind, 0) + 1
                        digest = hashlib.sha256(source.read_bytes()).hexdigest()
                        manifest["files"].append({"path": arcname, "sha256": digest, "bytes": source.stat().st_size})
                        written += 1
                        if written % 25 == 0:
                            self._update(job, stage="zipping", progress=min(90, int((written / max(total_files, 1)) * 90)), message=f"Added {written} files.")
                    manifest["counts"][novel_id] = counts
                self._write_json_entry(archive, "novels/index.json", [{"novel_id": item["novel_id"], "title": item.get("title", "")} for item in novel_items])
                self._write_json_entry(archive, "manifest.json", manifest)
            temp_path.replace(final_path)
            warnings = []
            if self.novels.remote is not None:
                try:
                    SupabaseStorage(bucket="backups").write_bytes(final_path.name, final_path.read_bytes(), "application/zip")
                except Exception as exc:
                    warnings.append(f"Supabase backup upload failed: {exc.__class__.__name__}")
                    logger.warning("Supabase backup upload failed: %s", exc)
            self._update(job, status="complete", stage="complete", progress=100, message="Backup complete.", finished_at=utc_now(), backup_file=str(final_path), counts=manifest["counts"], warnings=warnings)
        except Exception as exc:
            status = "cancelled" if job_id in self._cancel else "failed"
            self._update(job, status=status, stage=status, finished_at=utc_now(), error=str(exc), message=str(exc))

    def _run_full_restore(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        try:
            backup_path = Path(str(job["backup_file"]))
            self._update(job, status="running", stage="validating", progress=5, message="Validating backup manifest.")
            with zipfile.ZipFile(backup_path) as archive:
                names = set(archive.namelist())
                if "manifest.json" not in names:
                    warnings = ["Backup has no manifest.json. Legacy restore is dry-run only and uncertain files are skipped."]
                    if not job.get("dry_run", True):
                        raise ValueError("Backups without manifest.json can only be dry-run.")
                    restore_items = self._legacy_restore_items(archive)
                else:
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                    restore_items, warnings = self._manifest_restore_items(manifest, names)
                total = max(1, len(restore_items))
                counts = self._empty_restore_counts()
                for index, item in enumerate(restore_items, start=1):
                    if job_id in self._cancel:
                        raise RuntimeError("Restore cancelled.")
                    result = self._restore_item(archive, item, bool(job.get("dry_run", True)), str(job.get("conflict_mode") or "write_missing_only"))
                    counts[result] = counts.get(result, 0) + 1
                    if index % 10 == 0 or index == total:
                        self._update(job, stage="restoring" if not job.get("dry_run", True) else "dry_run", progress=min(95, 5 + int((index / total) * 90)), message=f"Checked {index} of {total} files.", counts=counts, warnings=warnings)
            if not job.get("dry_run", True):
                for novel_id in sorted({str(item["novel_id"]) for item in restore_items}):
                    if self.novels.metadata_path(novel_id).exists():
                        self.novels.touch(novel_id)
                        self.novels.sync_to_remote(novel_id)
                self.novels.write_novel_index()
            message = "Restore dry-run complete." if job.get("dry_run", True) else "Restore complete."
            self._update(job, status="complete", stage="complete", progress=100, message=message, finished_at=utc_now(), counts=counts, warnings=warnings)
        except Exception as exc:
            status = "cancelled" if job_id in self._cancel else "failed"
            self._update(job, status=status, stage=status, finished_at=utc_now(), error=str(exc), message=str(exc))

    def _manifest_restore_items(self, manifest: dict[str, Any], names: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        items: list[dict[str, Any]] = []
        for entry in manifest.get("files", []):
            path = str(entry.get("path") or "").replace("\\", "/")
            item = self._classify_restore_path(path)
            if item is None:
                warnings.append(f"Skipped uncertain manifest path: {path}")
                continue
            if path not in names:
                warnings.append(f"Manifest path missing from ZIP: {path}")
                continue
            items.append(item)
        for path in sorted(names):
            if re.fullmatch(r"novels/[a-z0-9][a-z0-9-]{0,80}/metadata\.json", path) and not any(existing["path"] == path for existing in items):
                item = self._classify_restore_path(path)
                if item is not None:
                    items.append(item)
        return items, warnings[:100]

    def _legacy_restore_items(self, archive: zipfile.ZipFile) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in archive.namelist():
            item = self._classify_restore_path(path.replace("\\", "/"))
            if item is not None:
                items.append(item)
        return items

    def _classify_restore_path(self, path: str) -> dict[str, Any] | None:
        match = re.fullmatch(r"novels/([a-z0-9][a-z0-9-]{0,80})/(originals|references|ai_translations|prompts)/([^/]+\.txt)", path)
        if not match:
            meta = re.fullmatch(r"novels/([a-z0-9][a-z0-9-]{0,80})/metadata\.json", path)
            if meta:
                return {"path": path, "novel_id": meta.group(1), "kind": "metadata", "filename": "metadata.json"}
            return None
        novel_id, kind, filename = match.groups()
        chapter = chapter_from_filename(Path(filename))
        if chapter is None:
            return None
        return {"path": path, "novel_id": novel_id, "kind": kind, "filename": f"{int(chapter):04d}.txt"}

    def _restore_item(self, archive: zipfile.ZipFile, item: dict[str, Any], dry_run: bool, conflict_mode: str) -> str:
        destination = self._restore_destination(item)
        exists = destination.exists()
        if exists:
            if conflict_mode in {"skip_existing", "write_missing_only"}:
                return "skipped" if conflict_mode == "skip_existing" else "conflicts"
        if dry_run:
            return f"{item['kind']}_written" if item["kind"] != "metadata" else "metadata_written"
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = archive.read(str(item["path"]))
        if item["kind"] == "metadata":
            parsed = json.loads(data.decode("utf-8"))
            self.novels.write_json(destination, parsed)
        else:
            destination.write_bytes(data)
        return f"{item['kind']}_written" if item["kind"] != "metadata" else "metadata_written"

    def _restore_destination(self, item: dict[str, Any]) -> Path:
        novel_id = str(item["novel_id"])
        kind = str(item["kind"])
        if kind == "metadata":
            return self.novels.metadata_path(novel_id)
        folder_key = {"originals": "original", "references": "reference", "ai_translations": "ai", "prompts": "output"}[kind]
        if kind == "prompts":
            return self.novels.novel_dir(novel_id) / "jobs" / "restored-prompts" / "Prompts" / str(item["filename"])
        return self.novels.folders(novel_id)[folder_key] / str(item["filename"])

    def _empty_restore_counts(self) -> dict[str, int]:
        return {"originals_written": 0, "references_written": 0, "ai_translations_written": 0, "prompts_written": 0, "metadata_written": 0, "skipped": 0, "conflicts": 0, "warnings": 0}

    def _backup_files_for(self, novel_id: str) -> list[tuple[Path, str, str]]:
        folders = self.novels.folders(novel_id)
        files: list[tuple[Path, str, str]] = []
        for key, folder_key, arc_folder in (("originals", "original", "originals"), ("references", "reference", "references"), ("ai_translations", "ai", "ai_translations")):
            for path in sorted(folders[folder_key].rglob("*.txt")):
                parsed = parse_chapter(path)
                number = parsed.get("number")
                filename = f"{int(number):04d}.txt" if number else path.name
                files.append((path, f"novels/{novel_id}/{arc_folder}/{filename}", key))
        for chapter in self.novels.chapters(novel_id):
            prompt_path = chapter.get("prompt_path")
            if prompt_path and Path(str(prompt_path)).exists():
                path = Path(str(prompt_path))
                files.append((path, f"novels/{novel_id}/prompts/{int(chapter['chapter']):04d}.txt", "prompts"))
        for cover in sorted(folders["cover"].glob("*")):
            if cover.is_file():
                files.append((cover, f"covers/{novel_id}/{cover.name}", "covers"))
        return files

    def _write_json_entry(self, archive: zipfile.ZipFile, name: str, data: Any) -> None:
        archive.writestr(name, json.dumps(data, indent=2, ensure_ascii=False))

    def _update(self, job: dict[str, Any], **updates: Any) -> None:
        job.update(updates)
        self._write(job)

    def _path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _read(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, job: dict[str, Any]) -> None:
        self._path(str(job["job_id"])).write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
