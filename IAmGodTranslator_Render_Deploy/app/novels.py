from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.services import TranslationService, safe_filename, unique_path, utc_now
from modules.chapter import chapter_from_filename, parse_chapter, read_text


DEFAULT_NOVEL_ID = "i-am-god"
DEFAULT_NOVEL_TITLE = "I Am God"
DEFAULT_APP_SETTINGS = {
    "name": "IAmGodTranslator",
    "subtitle": "Novel library",
    "theme": {
        "main_accent": "#68d1b4",
        "highlight": "#d6bf7a",
        "logo_accent": "#68d1b4",
        "card_background": "#111816",
        "page_background": "#080d0c",
        "reader_background": "#0f1513",
        "reader_text": "#efe8d5",
    },
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "novel"


class NovelManager:
    def __init__(self, root_service: TranslationService):
        self.root_service = root_service
        self.data_dir = root_service.data_dir
        self.novels_dir = self.data_dir / "novels"
        self.reader_state_path = self.data_dir / "reader_state.json"
        self.novels_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_default_novel()
        self.migrate_legacy_jobs()

    def service_for(self, novel_id: str) -> TranslationService:
        return TranslationService(data_dir=self.novel_dir(novel_id), translator=self.root_service.translator)

    def ensure_default_novel(self) -> dict[str, Any]:
        if not self.metadata_path(DEFAULT_NOVEL_ID).exists():
            return self.create_novel(DEFAULT_NOVEL_TITLE, novel_id=DEFAULT_NOVEL_ID)
        return self.get_novel(DEFAULT_NOVEL_ID)

    def create_novel(self, title: str, novel_id: str | None = None) -> dict[str, Any]:
        title = title.strip() or "Untitled Novel"
        base_id = slugify(novel_id or title)
        candidate = base_id
        index = 2
        while self.metadata_path(candidate).exists():
            candidate = f"{base_id}-{index}"
            index += 1
        for folder in self.folders(candidate).values():
            folder.mkdir(parents=True, exist_ok=True)
        metadata = {
            "novel_id": candidate,
            "title": title,
            "summary": "",
            "tags": [],
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "source_language": "Chinese",
            "target_language": "English",
            "settings": {
                "model": "gpt-4o-mini",
                "max_total_budget": None,
                "max_cost_per_chapter": None,
                "retry_failed_chapters": 1,
                "stop_when_budget_reached": True,
                "batch_size": 25,
            },
        }
        self.write_json(self.metadata_path(candidate), metadata)
        return self.decorate_novel(metadata)

    def update_novel(self, novel_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        metadata = self.get_metadata(novel_id)
        for key in ("title", "source_language", "target_language", "summary"):
            if isinstance(updates.get(key), str) and updates[key].strip():
                metadata[key] = updates[key].strip()
        if isinstance(updates.get("tags"), list):
            metadata["tags"] = [str(tag).strip() for tag in updates["tags"] if str(tag).strip()][:12]
        elif isinstance(updates.get("tags"), str):
            metadata["tags"] = [tag.strip() for tag in updates["tags"].split(",") if tag.strip()][:12]
        if isinstance(updates.get("settings"), dict):
            metadata.setdefault("settings", {}).update(updates["settings"])
        metadata["updated_at"] = utc_now()
        self.write_json(self.metadata_path(novel_id), metadata)
        return self.decorate_novel(metadata)

    def delete_novel(self, novel_id: str) -> None:
        if novel_id == DEFAULT_NOVEL_ID:
            raise ValueError("The migrated I Am God novel cannot be deleted from the API.")
        shutil.rmtree(self.novel_dir(novel_id), ignore_errors=True)

    def list_novels(self) -> list[dict[str, Any]]:
        return sorted((self.decorate_novel(item) for item in self.iter_metadata()), key=lambda item: item.get("updated_at") or "", reverse=True)

    def get_novel(self, novel_id: str) -> dict[str, Any]:
        return self.decorate_novel(self.get_metadata(novel_id))

    def library(self, novel_id: str) -> dict[str, Any]:
        return {"novel": self.get_novel(novel_id), "chapters": self.chapters(novel_id)}

    async def upload_original(self, novel_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
        await self.service_for(novel_id)._save_uploads(uploads, self.folders(novel_id)["original"])
        self.touch(novel_id)
        return self.library(novel_id)

    async def upload_reference(self, novel_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
        await self.service_for(novel_id)._save_uploads(uploads, self.folders(novel_id)["reference"])
        self.touch(novel_id)
        return self.library(novel_id)

    async def import_ai_translations(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "ai-translated-chapters.zip")
        if Path(filename).suffix.lower() != ".zip":
            raise ValueError("AI translated chapters import must be a .zip file.")

        imported = 0
        ai_dir = self.folders(novel_id)["ai"]
        ai_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(await upload.read())) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                name = Path(member.filename.replace("\\", "/")).name
                if not re.fullmatch(r"\d{1,6}\.txt", name, re.IGNORECASE):
                    continue

                chapter_number = int(Path(name).stem)
                target = ai_dir / f"{chapter_number:04d}.txt"
                with archive.open(member) as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output)
                imported += 1

        self.touch(novel_id)
        return {"imported": imported, **self.library(novel_id)}

    async def import_original_zip(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        result = await self.import_chapter_zip(novel_id, upload, "original", "Original Story")
        return {**result, **self.library(novel_id)}

    async def import_reference_zip(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        result = await self.import_chapter_zip(novel_id, upload, "reference", "Reference Translation")
        return {**result, **self.library(novel_id)}

    async def import_chapter_zip(self, novel_id: str, upload: UploadFile, folder_key: str, label: str) -> dict[str, int]:
        filename = safe_filename(upload.filename, f"{folder_key}-chapters.zip")
        if Path(filename).suffix.lower() != ".zip":
            raise ValueError(f"{label} import must be a .zip file.")

        target_dir = self.folders(novel_id)[folder_key]
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = set(self.chapter_numbers_for_folder(target_dir))
        seen: set[int] = set()
        imported = 0
        duplicates = 0

        with zipfile.ZipFile(io.BytesIO(await upload.read())) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = Path(member.filename.replace("\\", "/")).name
                if Path(name).suffix.lower() != ".txt":
                    continue
                number = chapter_from_filename(Path(name))
                if number is None:
                    continue
                if number in existing or number in seen:
                    duplicates += 1
                    continue
                target = target_dir / f"{number:04d}.txt"
                with archive.open(member) as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output)
                seen.add(number)
                imported += 1

        self.touch(novel_id)
        return {"imported": imported, "duplicates": duplicates}

    async def upload_cover(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "cover.png")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Cover image must be jpg, jpeg, png, or webp.")
        cover_dir = self.folders(novel_id)["cover"]
        cover_dir.mkdir(parents=True, exist_ok=True)
        for old_cover in cover_dir.glob("*"):
            if old_cover.is_file():
                old_cover.unlink()
        target = cover_dir / f"cover{suffix}"
        with open(target, "wb") as output:
            output.write(await upload.read())
        metadata = self.get_metadata(novel_id)
        metadata.setdefault("settings", {})["cover_file"] = str(target.relative_to(self.novel_dir(novel_id)))
        metadata["updated_at"] = utc_now()
        self.write_json(self.metadata_path(novel_id), metadata)
        return self.library(novel_id)

    async def upload_app_icon(self, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "app-icon.png")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("App icon must be jpg, jpeg, png, or webp.")
        icon_dir = self.data_dir / "app"
        icon_dir.mkdir(parents=True, exist_ok=True)
        for old_icon in icon_dir.glob("app-icon.*"):
            if old_icon.is_file():
                old_icon.unlink()
        target = icon_dir / f"app-icon{suffix}"
        with open(target, "wb") as output:
            output.write(await upload.read())
        return self.app_settings()

    def app_icon_path(self) -> Path | None:
        for path in (self.data_dir / "app").glob("app-icon.*"):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                return path
        return None

    def app_settings_path(self) -> Path:
        return self.data_dir / "app" / "settings.json"

    def app_settings(self) -> dict[str, Any]:
        settings = json.loads(json.dumps(DEFAULT_APP_SETTINGS))
        path = self.app_settings_path()
        if path.exists():
            try:
                saved = self.read_json(path)
                settings.update({key: saved[key] for key in ("name", "subtitle") if isinstance(saved.get(key), str)})
                if isinstance(saved.get("theme"), dict):
                    settings["theme"].update({key: str(value) for key, value in saved["theme"].items() if key in settings["theme"]})
            except (OSError, json.JSONDecodeError):
                pass
        icon = self.app_icon_path()
        settings["icon_url"] = f"/api/app-icon?v={int(icon.stat().st_mtime)}" if icon else None
        return settings

    def update_app_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        settings = self.app_settings()
        for key in ("name", "subtitle"):
            if isinstance(updates.get(key), str):
                settings[key] = updates[key].strip() or DEFAULT_APP_SETTINGS[key]
        if isinstance(updates.get("theme"), dict):
            for key in DEFAULT_APP_SETTINGS["theme"]:
                if isinstance(updates["theme"].get(key), str) and updates["theme"][key].strip():
                    settings["theme"][key] = updates["theme"][key].strip()
        self.write_json(self.app_settings_path(), {"name": settings["name"], "subtitle": settings["subtitle"], "theme": settings["theme"]})
        return self.app_settings()

    def reset_app_settings(self) -> dict[str, Any]:
        path = self.app_settings_path()
        if path.exists():
            path.unlink()
        return self.app_settings()

    def create_batch(self, novel_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        batch_size = max(1, min(200, int(settings.get("batch_size") or 25)))
        references = self.reference_files_by_number(novel_id)
        candidates = [
            chapter for chapter in self.chapters(novel_id)
            if chapter.get("source_path") and chapter.get("status") != "translated"
        ][:batch_size]
        chinese_files = [Path(str(chapter["source_path"])) for chapter in candidates]
        reference_files = [references[int(chapter["chapter"])] for chapter in candidates if int(chapter["chapter"]) in references]
        job = self.service_for(novel_id).create_job_from_existing_files(chinese_files, reference_files, settings)
        self.touch(novel_id)
        return job

    def start_job(self, novel_id: str, job_id: str) -> None:
        self.service_for(novel_id).start_job(job_id)
        self.touch(novel_id)

    def resume_incomplete_jobs(self) -> int:
        return sum(self.service_for(item["novel_id"]).resume_incomplete_jobs() for item in self.iter_metadata())

    def chapter(self, novel_id: str, chapter_number: int) -> dict[str, Any] | None:
        return next((chapter for chapter in self.chapters(novel_id) if int(chapter["chapter"]) == chapter_number), None)

    def chapter_text(self, novel_id: str, chapter_number: int, kind: str) -> dict[str, Any] | None:
        chapter = self.chapter(novel_id, chapter_number)
        if chapter is None:
            return None
        path_key = {"english": "output_path", "original": "source_path", "reference": "reference_path", "prompt": "prompt_path"}[kind]
        path_value = chapter.get(path_key)
        text = read_text(path_value) if path_value and Path(str(path_value)).exists() else ""
        return {"chapter": chapter, "text": text}

    def cover_path(self, novel_id: str) -> Path | None:
        metadata = self.get_metadata(novel_id)
        cover_file = metadata.get("settings", {}).get("cover_file")
        if isinstance(cover_file, str):
            path = self.novel_dir(novel_id) / cover_file
            if path.exists():
                return path
        for path in self.folders(novel_id)["cover"].glob("cover.*"):
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                return path
        return None

    def build_english_zip(self, novel_id: str) -> Path | None:
        return self.build_zip_from_chapters(novel_id, "output_path", "english")

    def build_original_zip(self, novel_id: str) -> Path | None:
        return self.build_zip_from_folder(novel_id, "original", "original-story")

    def build_reference_zip(self, novel_id: str) -> Path | None:
        return self.build_zip_from_folder(novel_id, "reference", "reference-translation")

    def build_ai_zip(self, novel_id: str) -> Path | None:
        return self.build_english_zip(novel_id)

    def build_prompts_zip(self, novel_id: str) -> Path | None:
        return self.build_zip_from_chapters(novel_id, "prompt_path", "prompts")

    def build_zip_from_folder(self, novel_id: str, folder_key: str, suffix: str) -> Path | None:
        files = sorted(path for path in self.folders(novel_id)[folder_key].rglob("*.txt") if path.is_file())
        if not files:
            return None
        zip_path = self.folders(novel_id)["output"] / f"{novel_id}-{suffix}.zip"
        self.zip_paths(files, zip_path, base=self.folders(novel_id)[folder_key])
        return zip_path

    def build_zip_from_chapters(self, novel_id: str, key: str, suffix: str) -> Path | None:
        files = [Path(str(chapter[key])) for chapter in self.chapters(novel_id) if chapter.get(key)]
        if not files:
            return None
        zip_path = self.folders(novel_id)["output"] / f"{novel_id}-{suffix}.zip"
        self.zip_paths(files, zip_path)
        return zip_path

    def build_backup_zip(self, novel_id: str) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        zip_path = self.folders(novel_id)["backups"] / f"{novel_id}-backup-{timestamp}.zip"
        files = sorted(path for path in self.novel_dir(novel_id).rglob("*") if path.is_file() and path != zip_path)
        self.zip_paths(files, zip_path, base=self.novel_dir(novel_id), prefix=novel_id)
        self.update_novel(novel_id, {"settings": {"last_backup_at": utc_now()}})
        return zip_path

    async def restore_backup(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "novel-backup.zip")
        if Path(filename).suffix.lower() != ".zip":
            raise ValueError("Backup must be a .zip file.")
        target_dir = self.novel_dir(novel_id).resolve()
        with zipfile.ZipFile(io.BytesIO(await upload.read())) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                parts = member_path.parts[1:] if member_path.parts and member_path.parts[0] == novel_id else member_path.parts
                if not parts or any(part in {"", ".", ".."} for part in parts):
                    continue
                destination = target_dir.joinpath(*parts).resolve()
                if not str(destination).startswith(str(target_dir)):
                    raise ValueError("Backup ZIP contains an unsafe path.")
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(destination, "wb") as output:
                    shutil.copyfileobj(source, output)
        self.touch(novel_id)
        return self.library(novel_id)

    def last_reader(self) -> dict[str, Any]:
        if not self.reader_state_path.exists():
            return {}
        try:
            return self.read_json(self.reader_state_path)
        except (OSError, json.JSONDecodeError):
            return {}

    def save_last_reader(self, novel_id: str, chapter: int) -> dict[str, Any]:
        state = {"novel_id": novel_id, "chapter": chapter, "updated_at": utc_now()}
        self.write_json(self.reader_state_path, state)
        return state

    def chapters(self, novel_id: str) -> list[dict[str, Any]]:
        chapters: dict[int, dict[str, Any]] = {}
        for file in sorted(self.folders(novel_id)["original"].rglob("*.txt")):
            parsed = parse_chapter(file)
            if parsed.get("number") is not None:
                chapters[int(parsed["number"])] = self.base_chapter(int(parsed["number"]), parsed.get("title") or file.stem, source_path=str(file))
        for number, file in self.reference_files_by_number(novel_id).items():
            chapters.setdefault(number, self.base_chapter(number, file.stem))
            chapters[number]["reference_path"] = str(file)
        for file in sorted(self.folders(novel_id)["ai"].rglob("*.txt")):
            parsed = parse_chapter(file)
            number = parsed.get("number")
            if number is None:
                continue
            current = chapters.setdefault(int(number), self.base_chapter(int(number), parsed.get("title") or file.stem))
            current["output_path"] = str(file)
            current["status"] = "translated"
        for job_dir, state in self.raw_jobs(novel_id):
            folders = self.service_for(novel_id).job_folders(job_dir)
            for item in state.get("chapters", []):
                number = int(item["chapter"])
                current = chapters.setdefault(number, self.base_chapter(number, item.get("title") or f"Chapter {number}"))
                current["title"] = current.get("title") or item.get("title") or f"Chapter {number}"
                current["source_path"] = current.get("source_path") or item.get("source_path")
                current["reference_path"] = current.get("reference_path") or item.get("reference_path")
                current["job_id"] = state.get("job_id")
                current["updated_at"] = state.get("updated_at")
                output_path = folders["english"] / (item.get("output_file") or f"{number:04d}.txt")
                prompt_path = folders["prompts"] / f"{number:04d}.txt"
                current["output_path"] = str(output_path) if output_path.exists() else current.get("output_path")
                current["prompt_path"] = str(prompt_path) if prompt_path.exists() else current.get("prompt_path")
                current["status"] = self.merge_status(current["status"], item.get("status"))
        return [self.public_chapter(chapter) for chapter in sorted(chapters.values(), key=lambda item: int(item["chapter"]))]

    def base_chapter(self, number: int, title: str, source_path: str | None = None) -> dict[str, Any]:
        return {"chapter": number, "title": title, "status": "untranslated", "source_path": source_path, "reference_path": None, "output_path": None, "prompt_path": None, "job_id": None, "updated_at": None}

    def public_chapter(self, chapter: dict[str, Any]) -> dict[str, Any]:
        return {**chapter, "has_translation": bool(chapter.get("output_path")), "has_original": bool(chapter.get("source_path")), "has_reference": bool(chapter.get("reference_path")), "has_prompt": bool(chapter.get("prompt_path"))}

    def merge_status(self, current: str, incoming: str | None) -> str:
        labels = {"completed": "translated", "test_completed": "translated", "running": "translating", "estimated": "queued", "pending": "queued", "queued": "queued", "translating": "translating", "failed": "failed", "skipped": "failed"}
        incoming_label = labels.get(incoming or "", incoming or current)
        rank = {"untranslated": 0, "queued": 1, "failed": 2, "translating": 3, "translated": 4}
        return incoming_label if rank.get(incoming_label, 0) >= rank.get(current, 0) else current

    def decorate_novel(self, metadata: dict[str, Any]) -> dict[str, Any]:
        novel_id = metadata["novel_id"]
        chapters = self.chapters(novel_id)
        translated = sum(1 for chapter in chapters if chapter.get("status") == "translated")
        original_valid = len(self.chapter_numbers_for_folder(self.folders(novel_id)["original"]))
        reference_valid = len(self.chapter_numbers_for_folder(self.folders(novel_id)["reference"]))
        jobs = [state for _, state in self.raw_jobs(novel_id)]
        settings = metadata.get("settings", {})
        status = "translating" if any(job.get("status") == "running" for job in jobs) else "ready"
        if status == "ready" and any(chapter.get("status") == "failed" for chapter in chapters):
            status = "needs attention"
        cover_path = self.cover_path(novel_id)
        return {
            **metadata,
            "storage_mode": self.root_service._storage_mode(),
            "data_dir": str(self.data_dir),
            "counts": {
                "total_chapters": len(chapters),
                "original_files": original_valid,
                "reference_files": reference_valid,
                "raw_original_files": len(list(self.folders(novel_id)["original"].rglob("*.txt"))),
                "raw_reference_files": len(list(self.folders(novel_id)["reference"].rglob("*.txt"))),
                "translated_chapters": translated,
                "remaining_chapters": max(0, original_valid - translated),
                "jobs": len(jobs),
            },
            "status": status,
            "current_model": settings.get("model") or "gpt-4o-mini",
            "last_backup_at": settings.get("last_backup_at"),
            "cover_url": f"/api/novels/{novel_id}/cover?v={int(cover_path.stat().st_mtime)}" if cover_path else None,
        }

    def migrate_legacy_jobs(self) -> None:
        target_jobs = self.novel_dir(DEFAULT_NOVEL_ID) / "jobs"
        target_jobs.mkdir(parents=True, exist_ok=True)
        for legacy_job in self.root_service.jobs_dir.glob("*"):
            if legacy_job.is_dir() and (legacy_job / "state.json").exists() and not (target_jobs / legacy_job.name).exists():
                shutil.copytree(legacy_job, target_jobs / legacy_job.name)
        self.mirror_job_sources(DEFAULT_NOVEL_ID)
        self.touch(DEFAULT_NOVEL_ID)

    def mirror_job_sources(self, novel_id: str) -> None:
        folders = self.folders(novel_id)
        for job_dir, _state in self.raw_jobs(novel_id):
            service_folders = self.service_for(novel_id).job_folders(job_dir)
            for source in service_folders["chinese"].glob("*.txt"):
                if not (folders["original"] / source.name).exists():
                    shutil.copy2(source, unique_path(folders["original"], source.name))
            for source in service_folders["novelfire"].glob("*.txt"):
                if not (folders["reference"] / source.name).exists():
                    shutil.copy2(source, unique_path(folders["reference"], source.name))

    def reference_files_by_number(self, novel_id: str) -> dict[int, Path]:
        references = {}
        for file in sorted(self.folders(novel_id)["reference"].rglob("*.txt")):
            number = parse_chapter(file).get("number")
            if number is not None:
                references[int(number)] = file
        return references

    def chapter_numbers_for_folder(self, folder: Path) -> set[int]:
        numbers: set[int] = set()
        for file in sorted(folder.rglob("*.txt")):
            try:
                number = parse_chapter(file).get("number")
            except OSError:
                continue
            if number is not None:
                numbers.add(int(number))
        return numbers

    def raw_jobs(self, novel_id: str) -> list[tuple[Path, dict[str, Any]]]:
        jobs = []
        for state_path in sorted((self.novel_dir(novel_id) / "jobs").glob("*/state.json")):
            try:
                jobs.append((state_path.parent, self.read_json(state_path)))
            except (OSError, json.JSONDecodeError):
                continue
        return jobs

    def iter_metadata(self) -> list[dict[str, Any]]:
        metadata = []
        for path in sorted(self.novels_dir.glob("*/metadata.json")):
            try:
                metadata.append(self.read_json(path))
            except (OSError, json.JSONDecodeError):
                continue
        return metadata

    def get_metadata(self, novel_id: str) -> dict[str, Any]:
        if not self.metadata_path(novel_id).exists():
            raise ValueError("Novel not found.")
        return self.read_json(self.metadata_path(novel_id))

    def touch(self, novel_id: str) -> None:
        metadata = self.get_metadata(novel_id)
        metadata["updated_at"] = utc_now()
        self.write_json(self.metadata_path(novel_id), metadata)

    def folders(self, novel_id: str) -> dict[str, Path]:
        novel_dir = self.novel_dir(novel_id)
        return {"original": novel_dir / "Original", "reference": novel_dir / "Reference", "ai": novel_dir / "AI", "output": novel_dir / "Output", "backups": novel_dir / "Backups", "config": novel_dir / "config", "cover": novel_dir / "Cover"}

    def novel_dir(self, novel_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", novel_id):
            raise ValueError("Invalid novel id.")
        return self.novels_dir / novel_id

    def metadata_path(self, novel_id: str) -> Path:
        return self.novel_dir(novel_id) / "metadata.json"

    def zip_paths(self, files: list[Path], zip_path: Path, base: Path | None = None, prefix: str | None = None) -> None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                if not file.exists():
                    continue
                arcname = file.relative_to(base) if base else Path(file.name)
                if prefix:
                    arcname = Path(prefix) / arcname
                archive.write(file, arcname.as_posix())

    def read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
