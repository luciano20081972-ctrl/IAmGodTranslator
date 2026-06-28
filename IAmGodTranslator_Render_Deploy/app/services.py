from __future__ import annotations

import asyncio
import inspect
import io
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from modules.api import DEFAULT_MODEL, translate
from modules.chapter import parse_chapter
from modules.context import build_context
from modules.cost_estimator import (
    build_cost_estimate,
    default_settings,
    estimate_chapter_tokens,
    parse_budget,
    write_estimate_report,
)
from modules.prompt_builder import build_prompt
from modules.prompt_writer import save_prompt
from modules.queue import build_queue, save_queue
from modules.save_translation import save_translation


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_RENDER_DATA_DIR = Path("/var/data/IAmGodTranslator")
BASELINE_FILES = ("memory.json", "glossary.json", "style.json")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
MAX_BACKUP_BYTES = int(os.getenv("MAX_BACKUP_BYTES", str(500 * 1024 * 1024)))
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-*]+")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def safe_filename(name: str | None, fallback: str = "upload.txt") -> str:
    raw = Path((name or fallback).replace("\\", "/")).name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw).strip()
    return cleaned or fallback


def unique_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename

    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix

    for index in range(2, 10_000):
        candidate = folder / f"{stem}-{index}{suffix}"

        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Unable to create unique filename for {filename}")


def resolve_data_dir() -> Path:
    configured = os.getenv("DATA_DIR")

    if configured:
        return Path(configured).expanduser()

    if os.getenv("RENDER") and DEFAULT_RENDER_DATA_DIR.parent.exists():
        return DEFAULT_RENDER_DATA_DIR

    return DEFAULT_DATA_DIR


class TranslationService:
    def __init__(
        self,
        data_dir: Path | None = None,
        translator: Callable[[str], str] = translate,
    ):
        self.data_dir = data_dir or resolve_data_dir()
        self.jobs_dir = self.data_dir / "jobs"
        self.config_dir = self.data_dir / "config"
        self.backups_dir = self.data_dir / "backups"
        self.translator = translator
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._prepare_storage()

    def _prepare_storage(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        for filename in BASELINE_FILES:
            source = PROJECT_ROOT / filename
            target = self.config_dir / filename

            if source.exists() and not target.exists():
                shutil.copy2(source, target)

    async def create_job(
        self,
        chinese_uploads: list[UploadFile],
        reference_uploads: list[UploadFile] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not chinese_uploads:
            raise ValueError("Upload at least one Chinese TXT file or ZIP.")

        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        folders = self.job_folders(job_dir)

        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)

        self._copy_baseline_files(job_dir)

        await self._save_uploads(chinese_uploads, folders["chinese"])
        await self._save_uploads(reference_uploads or [], folders["novelfire"])

        chinese_chapters = self._parse_folder(folders["chinese"])
        reference_chapters = self._parse_folder(folders["novelfire"])

        if not chinese_chapters:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise ValueError("No Chinese .txt chapters were found in the upload.")

        reference_by_number = {
            chapter["number"]: chapter
            for chapter in reference_chapters
            if chapter.get("number") is not None
        }

        index = self._build_job_index(chinese_chapters, reference_by_number)
        queue = build_queue(index)
        save_queue(queue, folders["logs"] / "translation_queue.json")
        self._write_json(folders["logs"] / "chapter_index.json", index)

        state = self._initial_state(job_id, index, reference_by_number, settings=settings)
        estimate = self._estimate_job(job_dir, state)
        state["estimate"] = estimate
        state["estimate_report"] = str(write_estimate_report(job_dir, estimate))
        self._save_state(job_dir, state)

        logger.info("Created estimated translation job %s with %s chapter(s)", job_id, len(queue))
        return self._public_state(state)

    def create_job_from_existing_files(
        self,
        chinese_files: list[Path],
        reference_files: list[Path] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not chinese_files:
            raise ValueError("Add at least one Original Story chapter before building a queue.")

        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        folders = self.job_folders(job_dir)

        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)

        self._copy_baseline_files(job_dir)

        for file in chinese_files:
            if file.is_file():
                shutil.copy2(file, unique_path(folders["chinese"], file.name))

        for file in reference_files or []:
            if file.is_file():
                shutil.copy2(file, unique_path(folders["novelfire"], file.name))

        chinese_chapters = self._parse_folder(folders["chinese"])
        reference_chapters = self._parse_folder(folders["novelfire"])

        if not chinese_chapters:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise ValueError("No Original Story .txt chapters were found.")

        reference_by_number = {
            chapter["number"]: chapter
            for chapter in reference_chapters
            if chapter.get("number") is not None
        }

        index = self._build_job_index(chinese_chapters, reference_by_number)
        queue = build_queue(index)
        save_queue(queue, folders["logs"] / "translation_queue.json")
        self._write_json(folders["logs"] / "chapter_index.json", index)

        state = self._initial_state(job_id, index, reference_by_number, settings=settings)
        estimate = self._estimate_job(job_dir, state)
        state["estimate"] = estimate
        state["estimate_report"] = str(write_estimate_report(job_dir, estimate))
        self._save_state(job_dir, state)

        logger.info("Created estimated translation job %s from stored novel files", job_id)
        return self._public_state(state)

    def start_job(self, job_id: str) -> None:
        existing = self._tasks.get(job_id)

        if existing and not existing.done():
            return

        self._tasks[job_id] = asyncio.create_task(self._run_job(job_id))

    def update_settings(self, job_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        job_dir = self.job_dir(job_id)
        state = self._load_state(job_dir)

        if state is None:
            raise ValueError("Job not found.")

        state["settings"] = self._normalize_settings(settings)
        self._save_state(job_dir, state)
        return self._public_state(state)

    def resume_incomplete_jobs(self) -> int:
        resumed = 0

        for state_path in self.jobs_dir.glob("*/state.json"):
            try:
                state = self._read_json(state_path)
            except (OSError, json.JSONDecodeError):
                logger.warning("Skipping unreadable job state: %s", state_path)
                continue

            if state.get("status") in {"queued", "running"}:
                self.start_job(state["job_id"])
                resumed += 1

        return resumed

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []

        for state_path in sorted(self.jobs_dir.glob("*/state.json"), reverse=True):
            try:
                state = self._read_json(state_path)
            except (OSError, json.JSONDecodeError):
                logger.warning("Skipping unreadable job state: %s", state_path)
                continue

            jobs.append(self._public_state(state))

        return jobs

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        state_path = self.job_dir(job_id) / "state.json"

        if not state_path.exists():
            return None

        return self._public_state(self._read_json(state_path))

    def chapter_output(self, job_id: str, chapter: int) -> Path | None:
        output = self.job_folders(self.job_dir(job_id))["english"] / f"{chapter:04d}.txt"
        return output if output.exists() else None

    def build_download_zip(self, job_id: str) -> Path | None:
        job_dir = self.job_dir(job_id)
        folders = self.job_folders(job_dir)
        output_files = sorted(folders["english"].glob("*.txt"))

        if not output_files:
            return None

        zip_path = folders["output"] / f"{job_id}-translated-chapters.zip"
        self._zip_files(output_files, zip_path, folders["english"])
        return zip_path

    def build_prompts_zip(self, job_id: str) -> Path | None:
        job_dir = self.job_dir(job_id)
        folders = self.job_folders(job_dir)
        prompt_files = sorted(folders["prompts"].glob("*.txt"))

        if not prompt_files:
            return None

        zip_path = folders["output"] / f"{job_id}-prompts.zip"
        self._zip_files(prompt_files, zip_path, folders["prompts"])
        return zip_path

    def build_backup_zip(self, job_id: str) -> Path | None:
        job_dir = self.job_dir(job_id)

        if not job_dir.exists():
            return None

        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        zip_path = self.backups_dir / f"{job_id}-backup-{timestamp}.zip"
        files = sorted(path for path in job_dir.rglob("*") if path.is_file())
        self._zip_files(files, zip_path, job_dir, prefix=job_id)
        self._write_json(
            self.data_dir / "storage_state.json",
            {
                "last_backup_at": utc_now(),
                "last_backup_file": str(zip_path),
                "job_id": job_id,
            },
        )
        return zip_path

    async def restore_backup(self, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "job-backup.zip")

        if Path(filename).suffix.lower() != ".zip":
            raise ValueError("Backup must be a .zip file.")

        content = await upload.read()

        if len(content) > MAX_BACKUP_BYTES:
            raise ValueError("Backup ZIP is larger than the configured restore limit.")

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("Backup ZIP could not be read.") from exc

        with archive:
            members = [
                member
                for member in archive.infolist()
                if not member.is_dir()
            ]
            self._validate_zip_members(members)

            state_member = next(
                (member for member in members if Path(member.filename).name == "state.json"),
                None,
            )

            if state_member is None:
                raise ValueError("Backup ZIP does not contain a job state.json.")

            state = json.loads(archive.read(state_member).decode("utf-8"))
            original_job_id = str(state.get("job_id") or "")
            job_id = original_job_id if re.fullmatch(r"[a-f0-9]{32}", original_job_id) else uuid.uuid4().hex

            if self.job_dir(job_id).exists():
                job_id = uuid.uuid4().hex

            job_dir = self.job_dir(job_id)
            job_dir.mkdir(parents=True)
            root_parts = Path(state_member.filename).parts[:-1]

            for member in members:
                parts = Path(member.filename).parts
                relative_parts = parts[len(root_parts):] if parts[:len(root_parts)] == root_parts else parts

                if not relative_parts:
                    continue

                output = job_dir.joinpath(*relative_parts)
                output.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as source, open(output, "wb") as target:
                    shutil.copyfileobj(source, target)

        self._normalize_restored_job(job_dir, job_id)
        restored = self._load_state(job_dir)

        if restored is None:
            raise ValueError("Restored backup did not produce a readable job state.")

        return self._public_state(restored)

    def storage_status(self) -> dict[str, Any]:
        chinese_count = 0
        reference_count = 0
        translation_count = 0

        for job_dir in self.jobs_dir.glob("*"):
            if not job_dir.is_dir():
                continue

            folders = self.job_folders(job_dir)
            chinese_count += len(list(folders["chinese"].glob("*.txt")))
            reference_count += len(list(folders["novelfire"].glob("*.txt")))
            translation_count += len(list(folders["english"].glob("*.txt")))

        storage_state_path = self.data_dir / "storage_state.json"
        storage_state = self._read_json(storage_state_path) if storage_state_path.exists() else {}

        return {
            "mode": self._storage_mode(),
            "data_dir": str(self.data_dir),
            "saved_chinese_chapters": chinese_count,
            "saved_novelfire_references": reference_count,
            "saved_translations": translation_count,
            "last_backup_at": storage_state.get("last_backup_at"),
            "last_backup_file": storage_state.get("last_backup_file"),
        }

    def estimate_report(self, job_id: str) -> Path | None:
        job_dir = self.job_dir(job_id)
        report = self.job_folders(job_dir)["output"] / "cost_estimate_report.md"
        return report if report.exists() else None

    def _zip_files(self, files: list[Path], zip_path: Path, root: Path, prefix: str = "") -> None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                arcname = file.relative_to(root).as_posix()

                if prefix:
                    arcname = f"{prefix}/{arcname}"

                archive.write(file, arcname=arcname)

    def _validate_zip_members(self, members: list[zipfile.ZipInfo]) -> None:
        for member in members:
            path = Path(member.filename)

            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Backup ZIP contains an unsafe path.")

            if member.file_size > MAX_BACKUP_BYTES:
                raise ValueError("Backup ZIP contains a file larger than the restore limit.")

    def _normalize_restored_job(self, job_dir: Path, job_id: str) -> None:
        state = self._load_state(job_dir)

        if state is None:
            return

        folders = self.job_folders(job_dir)
        state["job_id"] = job_id

        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)

        for chapter in state.get("chapters", []):
            source_file = chapter.get("source_file")
            reference_file = chapter.get("reference_file")

            if source_file:
                chapter["source_path"] = str(folders["chinese"] / source_file)

            if reference_file:
                chapter["reference_path"] = str(folders["novelfire"] / reference_file)

        report = folders["output"] / "cost_estimate_report.md"
        state["estimate_report"] = str(report) if report.exists() else state.get("estimate_report")
        self._refresh_counts(state)
        self._save_state(job_dir, state)

    def job_dir(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Invalid job id.")

        return self.jobs_dir / job_id

    def job_folders(self, job_dir: Path) -> dict[str, Path]:
        return {
            "chinese": job_dir / "Chinese",
            "novelfire": job_dir / "NovelFire",
            "english": job_dir / "English",
            "prompts": job_dir / "Prompts",
            "logs": job_dir / "Logs",
            "output": job_dir / "Output",
        }

    async def _run_job(self, job_id: str) -> None:
        lock = self._locks.setdefault(job_id, asyncio.Lock())

        async with lock:
            job_dir = self.job_dir(job_id)
            state = self._load_state(job_dir)

            if state is None:
                return

            state["status"] = "running"
            state["started_at"] = state.get("started_at") or utc_now()
            state["error"] = None
            self._save_state(job_dir, state)

            for chapter_state in state["chapters"]:
                if chapter_state["status"] == "completed":
                    continue

                if not self._within_budget(state, chapter_state):
                    chapter_state["status"] = "skipped"
                    chapter_state["error"] = "Skipped by budget settings."
                    self._refresh_counts(state)
                    self._save_state(job_dir, state)
                    break

                max_retries = int(state.get("settings", {}).get("retry_failed_chapters") or 0)

                while True:
                    chapter_state["status"] = "translating"
                    chapter_state["tries"] += 1
                    self._refresh_counts(state)
                    self._save_state(job_dir, state)

                    try:
                        output = await self._translate_chapter(job_dir, chapter_state, state)
                    except Exception as exc:
                        safe_error = self._safe_error_message(exc)
                        logger.error("Job %s chapter %s failed: %s", job_id, chapter_state["chapter"], safe_error)
                        chapter_state["error"] = safe_error
                        state["error"] = safe_error

                        if self._is_authentication_error(exc):
                            chapter_state["status"] = "failed"
                            break

                        if chapter_state["tries"] <= max_retries:
                            chapter_state["status"] = "pending"
                            self._refresh_counts(state)
                            self._save_state(job_dir, state)
                            continue

                        chapter_state["status"] = "failed"
                        break

                    chapter_state["status"] = "completed"
                    chapter_state["error"] = None
                    chapter_state["output_file"] = output.name
                    self._refresh_counts(state)
                    self._save_state(job_dir, state)

                    break

                if chapter_state["status"] == "failed":
                    if state["error"] and self._is_authentication_error(RuntimeError(state["error"])):
                        break
                    continue

                if state.get("settings", {}).get("test_chapter_only"):
                    state["status"] = "test_completed"
                    state["finished_at"] = utc_now()
                    self._save_state(job_dir, state)
                    return

            self._refresh_counts(state)

            if state["counts"]["completed"] == state["counts"]["total"]:
                state["status"] = "completed"
                state["finished_at"] = utc_now()
            elif state["counts"]["failed"] > 0:
                state["status"] = "failed"
                state["finished_at"] = utc_now()
            elif state["counts"].get("skipped", 0) > 0:
                state["status"] = "budget_reached"
                state["finished_at"] = utc_now()
            else:
                state["status"] = "queued"

            self._save_state(job_dir, state)

    async def _translate_chapter(self, job_dir: Path, chapter_state: dict[str, Any], state: dict[str, Any]) -> Path:
        folders = self.job_folders(job_dir)
        chapter_number = int(chapter_state["chapter"])
        chinese = parse_chapter(chapter_state["source_path"])
        chinese["number"] = chapter_number

        novelfire = None
        reference_path = chapter_state.get("reference_path")

        if reference_path:
            novelfire = parse_chapter(reference_path)
            novelfire["number"] = chapter_number

        context = build_context(
            chinese,
            novelfire,
            memory_path=job_dir / "memory.json",
            glossary_path=job_dir / "glossary.json",
        )
        prompt = build_prompt(
            context,
            style_path=job_dir / "style.json",
            memory_path=job_dir / "memory.json",
            glossary_path=job_dir / "glossary.json",
        )
        save_prompt(chapter_number, prompt, output_dir=folders["prompts"])

        model = state.get("settings", {}).get("model") or state.get("model") or DEFAULT_MODEL
        translation_text = await asyncio.to_thread(self._call_translator, prompt, model)
        return save_translation(chapter_number, translation_text, output_dir=folders["english"])

    def _call_translator(self, prompt: str, model: str) -> str:
        signature = inspect.signature(self.translator)
        parameters = signature.parameters.values()

        accepts_model = any(
            parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
            for parameter in parameters
        ) or len(signature.parameters) > 1

        if accepts_model:
            return self.translator(prompt, model)

        return self.translator(prompt)

    async def _save_uploads(self, uploads: list[UploadFile], folder: Path) -> list[Path]:
        saved: list[Path] = []

        for upload in uploads:
            filename = safe_filename(upload.filename)
            content = await upload.read()

            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError(f"{filename} is larger than the configured upload limit.")

            suffix = Path(filename).suffix.lower()

            if suffix == ".zip":
                saved.extend(self._extract_zip(content, folder))
            elif suffix == ".txt":
                path = unique_path(folder, filename)
                path.write_bytes(content)
                saved.append(path)
            else:
                raise ValueError(f"{filename} is not a .txt or .zip file.")

        return saved

    def _extract_zip(self, content: bytes, folder: Path) -> list[Path]:
        saved: list[Path] = []

        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                filename = safe_filename(member.filename)

                if Path(filename).suffix.lower() != ".txt":
                    continue

                if member.file_size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"{filename} inside ZIP is larger than the upload limit.")

                output_path = unique_path(folder, filename)

                with archive.open(member) as source, open(output_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                saved.append(output_path)

        return saved

    def _parse_folder(self, folder: Path) -> list[dict[str, Any]]:
        chapters = []

        for file in sorted(folder.rglob("*.txt")):
            chapter = parse_chapter(file)

            if chapter["number"] is None:
                chapter["number"] = self._next_available_number(chapters)

            chapters.append(chapter)

        return sorted(chapters, key=lambda item: (item["number"], item["title"]))

    def _next_available_number(self, chapters: list[dict[str, Any]]) -> int:
        used = {
            chapter["number"]
            for chapter in chapters
            if chapter.get("number") is not None
        }

        candidate = 1

        while candidate in used:
            candidate += 1

        return candidate

    def _build_job_index(
        self,
        chinese_chapters: list[dict[str, Any]],
        reference_by_number: dict[int, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index = {}

        for chapter in chinese_chapters:
            number = int(chapter["number"])
            reference = reference_by_number.get(number)

            while str(number) in index:
                number += 1

            chapter["number"] = number
            index[str(number)] = {
                "chapter": number,
                "translated": False,
                "chinese": chapter["path"],
                "novelfire": reference["path"] if reference else None,
                "title_cn": chapter["title"],
                "title_en": reference["title"] if reference else None,
            }

        return index

    def _initial_state(
        self,
        job_id: str,
        index: dict[str, dict[str, Any]],
        reference_by_number: dict[int, dict[str, Any]],
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chapters = []

        for item in sorted(index.values(), key=lambda value: value["chapter"]):
            reference = reference_by_number.get(item["chapter"])
            chapters.append({
                "chapter": item["chapter"],
                "title": item["title_cn"],
                "reference_title": item["title_en"],
                "status": "pending",
                "tries": 0,
                "source_file": Path(item["chinese"]).name,
                "source_path": item["chinese"],
                "reference_file": Path(reference["path"]).name if reference else None,
                "reference_path": reference["path"] if reference else None,
                "output_file": None,
                "error": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cheapest_cost": 0,
                "estimated_recommended_cost": 0,
            })

        normalized_settings = self._normalize_settings(settings)

        state = {
            "job_id": job_id,
            "status": "estimated",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "started_at": None,
            "finished_at": None,
            "model": normalized_settings.get("model") or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            "counts": {
                "total": len(chapters),
                "pending": len(chapters),
                "running": 0,
                "completed": 0,
                "failed": 0,
                "skipped": 0,
            },
            "chapters": chapters,
            "settings": normalized_settings,
            "estimate": None,
            "estimate_report": None,
            "error": None,
        }

        return state

    def _estimate_job(self, job_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
        estimate_inputs = []

        for chapter_state in state["chapters"]:
            chapter_number = int(chapter_state["chapter"])
            chinese = parse_chapter(chapter_state["source_path"])
            chinese["number"] = chapter_number
            novelfire = None

            if chapter_state.get("reference_path"):
                novelfire = parse_chapter(chapter_state["reference_path"])
                novelfire["number"] = chapter_number

            context = build_context(
                chinese,
                novelfire,
                memory_path=job_dir / "memory.json",
                glossary_path=job_dir / "glossary.json",
            )
            prompt = build_prompt(
                context,
                style_path=job_dir / "style.json",
                memory_path=job_dir / "memory.json",
                glossary_path=job_dir / "glossary.json",
            )
            token_estimate = estimate_chapter_tokens(prompt, chinese["text"])
            chapter_state["input_tokens"] = token_estimate.input_tokens
            chapter_state["output_tokens"] = token_estimate.output_tokens
            estimate_inputs.append({
                "chapter": chapter_number,
                "title": chapter_state["title"],
                "input_tokens": token_estimate.input_tokens,
                "output_tokens": token_estimate.output_tokens,
            })

        estimate = build_cost_estimate(estimate_inputs)

        for chapter_state, chapter_estimate in zip(state["chapters"], estimate["chapters"], strict=False):
            chapter_state["estimated_cheapest_cost"] = chapter_estimate["cheapest_model_cost"]
            chapter_state["estimated_recommended_cost"] = chapter_estimate["recommended_model_cost"]

        return estimate

    def _copy_baseline_files(self, job_dir: Path) -> None:
        for filename in BASELINE_FILES:
            source = self.config_dir / filename
            target = job_dir / filename

            if source.exists() and not target.exists():
                shutil.copy2(source, target)
            elif not target.exists() and (PROJECT_ROOT / filename).exists():
                shutil.copy2(PROJECT_ROOT / filename, target)

    def _load_state(self, job_dir: Path) -> dict[str, Any] | None:
        state_path = job_dir / "state.json"

        if not state_path.exists():
            return None

        return self._read_json(state_path)

    def _save_state(self, job_dir: Path, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now()
        self._write_json(job_dir / "state.json", state)
        self._write_json(
            self.job_folders(job_dir)["logs"] / "translation_queue.json",
            [
                {
                    "chapter": chapter["chapter"],
                    "status": chapter["status"],
                    "tries": chapter["tries"],
                    "error": chapter["error"],
                }
                for chapter in state.get("chapters", [])
            ],
        )

    def _refresh_counts(self, state: dict[str, Any]) -> None:
        chapters = state["chapters"]
        state["counts"] = {
            "total": len(chapters),
            "pending": sum(1 for chapter in chapters if chapter["status"] == "pending"),
            "running": sum(1 for chapter in chapters if chapter["status"] == "translating"),
            "completed": sum(1 for chapter in chapters if chapter["status"] == "completed"),
            "failed": sum(1 for chapter in chapters if chapter["status"] == "failed"),
            "skipped": sum(1 for chapter in chapters if chapter["status"] == "skipped"),
        }

    def _public_state(self, state: dict[str, Any]) -> dict[str, Any]:
        public = dict(state)
        public["chapters"] = [
            {
                key: value
                for key, value in chapter.items()
                if key not in {"source_path", "reference_path"}
            }
            for chapter in state.get("chapters", [])
        ]
        return public

    def _read_json(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, data: dict[str, Any] | list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _normalize_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        normalized = default_settings()

        if settings:
            normalized.update(settings)

        normalized["max_total_budget"] = parse_budget(normalized.get("max_total_budget"))
        normalized["max_cost_per_chapter"] = parse_budget(normalized.get("max_cost_per_chapter"))
        normalized["stop_when_budget_reached"] = bool(normalized.get("stop_when_budget_reached"))
        normalized["test_chapter_only"] = bool(normalized.get("test_chapter_only"))
        normalized["show_estimate_before_starting"] = bool(normalized.get("show_estimate_before_starting"))
        normalized["retry_failed_chapters"] = max(0, min(1, int(normalized.get("retry_failed_chapters") or 0)))
        return normalized

    def _within_budget(self, state: dict[str, Any], chapter_state: dict[str, Any]) -> bool:
        settings = state.get("settings", {})

        if not settings.get("stop_when_budget_reached", True):
            return True

        chapter_cost = self._estimated_cost_for_settings(state, chapter_state)
        max_per_chapter = settings.get("max_cost_per_chapter")

        if max_per_chapter is not None and chapter_cost > max_per_chapter:
            return False

        max_total = settings.get("max_total_budget")

        if max_total is None:
            return True

        spent = sum(
            self._estimated_cost_for_settings(state, chapter)
            for chapter in state.get("chapters", [])
            if chapter.get("status") == "completed"
        )
        return spent + chapter_cost <= max_total

    def _estimated_cost_for_settings(self, state: dict[str, Any], chapter_state: dict[str, Any]) -> float:
        model = state.get("settings", {}).get("model") or state.get("model") or DEFAULT_MODEL

        if model == "gpt-4o-mini":
            return float(chapter_state.get("estimated_cheapest_cost") or 0)

        return float(chapter_state.get("estimated_recommended_cost") or 0)

    def _safe_error_message(self, exc: Exception) -> str:
        text = SECRET_PATTERN.sub("[redacted-api-key]", str(exc))

        if self._is_authentication_error(exc):
            return "OpenAI authentication failed. Check OPENAI_API_KEY."

        return text or exc.__class__.__name__

    def _is_authentication_error(self, exc: Exception) -> bool:
        name = exc.__class__.__name__.lower()
        text = str(exc).lower()
        return (
            "authentication" in name
            or "invalid api key" in text
            or "incorrect api key" in text
            or "openai_api_key" in text
        )

    def _storage_mode(self) -> str:
        if os.getenv("DATA_DIR"):
            return "persistent-disk"

        if os.getenv("RENDER") and self.data_dir == DEFAULT_RENDER_DATA_DIR:
            return "render-persistent-disk"

        if os.getenv("RENDER"):
            return "render-ephemeral-filesystem"

        return "local-filesystem"
