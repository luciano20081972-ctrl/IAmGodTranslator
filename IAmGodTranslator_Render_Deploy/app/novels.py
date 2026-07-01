from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.services import TranslationService, safe_filename, unique_path, utc_now
from app.storage import SupabaseStorage, supabase_config
from modules.chapter import chapter_from_filename, parse_chapter, read_text


logger = logging.getLogger(__name__)

DEFAULT_NOVEL_ID = "i-am-god"
DEFAULT_NOVEL_TITLE = "I Am God"
REMOTE_PREFIXES = {"original": "originals", "reference": "references", "ai": "ai_translations", "prompt": "prompts"}
LEGACY_REMOTE_PREFIXES = {
    "original": ("Original", "original", "Originals", "originals"),
    "reference": ("Reference", "reference", "References", "references"),
    "ai": ("AI", "ai", "Translations", "translations", "AI_Translations", "ai_translations"),
    "prompt": ("Prompts", "prompts"),
}
COVER_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_APP_SETTINGS = {
    "name": "GodTranslator",
    "subtitle": "Novel Library",
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
        self.remote_error: str | None = None
        self.disable_startup_remote_sync = (os.getenv("DISABLE_STARTUP_REMOTE_SYNC") or "true").lower() != "false"
        self._startup_phase = True
        self.remote = self.build_remote_storage()
        self.novels_dir.mkdir(parents=True, exist_ok=True)
        self.restore_remote_snapshot()
        self.ensure_default_novel()
        self.migrate_legacy_jobs()
        self._startup_phase = False

    def build_remote_storage(self) -> SupabaseStorage | None:
        if (os.getenv("STORAGE_BACKEND") or "local").lower() != "supabase":
            return None
        try:
            return SupabaseStorage()
        except ValueError as exc:
            self.remote_error = str(exc)
            logger.warning("Supabase storage disabled: %s", exc)
            return None

    def restore_remote_snapshot(self) -> None:
        if self.remote is None:
            return
        if self.disable_startup_remote_sync:
            logger.info("Skipping Supabase remote snapshot restore during startup.")
            return
        try:
            self.remote.download_tree("app", self.data_dir / "app")
            self.remote.download_tree("novels", self.novels_dir)
        except Exception:
            logger.exception("Failed to restore Supabase storage snapshot")

    def sync_all_to_remote(self) -> dict[str, int]:
        if self.remote is None:
            return {"copied": 0, "failed": 0}
        counts = {"copied": 0, "failed": 0}
        for root, prefix in ((self.data_dir / "app", "app"), (self.novels_dir, "novels")):
            result = self.remote.upload_tree(root, prefix)
            counts["copied"] += result["copied"]
            counts["failed"] += result["failed"]
        return counts

    def remote_health(self) -> dict[str, Any]:
        config = supabase_config()
        warnings = []
        if (os.getenv("STORAGE_BACKEND") or "local").lower() == "supabase":
            if not config.url:
                warnings.append("SUPABASE_URL is missing.")
            if not config.service_role_key:
                warnings.append("SUPABASE_SERVICE_ROLE_KEY is missing.")
            if not config.anon_key:
                warnings.append("SUPABASE_ANON_KEY is missing. Backend storage can still work, but client auth/OAuth setup may need it later.")
            warnings.append("Render Free may sleep, but data persists in Supabase when Supabase storage/database are active.")
            warnings.append("Supabase Free may pause after inactivity; keep backups and check project activity.")
        if self.remote_error:
            warnings.append(self.remote_error)
        if self.remote is None:
            return {"configured": config.configured, "active": False, "reachable": False, "bucket": config.bucket, "buckets": {}, "warnings": warnings}
        try:
            health = self.remote.health()
            if not health.get("upload_test"):
                warnings.append(str(health.get("upload_error") or "Supabase upload test failed. Check bucket permissions and service role key."))
            return {"configured": config.configured, "active": True, **health, "warnings": warnings}
        except Exception as exc:
            warnings.append(f"Supabase Storage check failed: {exc.__class__.__name__}")
            return {"configured": config.configured, "active": True, "reachable": False, "bucket": config.bucket, "buckets": {}, "warnings": warnings}

    def migrate_to_supabase(self) -> dict[str, Any]:
        if self.remote is None:
            raise ValueError("Supabase storage is not configured.")
        report: dict[str, Any] = {"originals": 0, "references": 0, "ai_translations": 0, "prompts": 0, "covers": 0, "backups": 0, "other": 0, "skipped": 0, "conflicts": 0, "errors": []}
        roots = [self.data_dir / "app", self.novels_dir]
        for root in roots:
            if not root.exists():
                continue
            prefix = "app" if root.name == "app" else "novels"
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                remote_path = f"{prefix}/{path.relative_to(root).as_posix()}"
                try:
                    existing = self.remote.read_bytes(remote_path)
                    data = path.read_bytes()
                    if existing is not None:
                        if existing == data:
                            report["skipped"] += 1
                        else:
                            report["conflicts"] += 1
                        continue
                    self.remote.write_bytes(remote_path, data)
                    lower = remote_path.lower()
                    if "/original/" in lower or "/originals/" in lower:
                        report["originals"] += 1
                    elif "/reference/" in lower or "/references/" in lower:
                        report["references"] += 1
                    elif "/ai/" in lower or "/ai_translations/" in lower or "/english/" in lower:
                        report["ai_translations"] += 1
                    elif "/prompts/" in lower:
                        report["prompts"] += 1
                    elif "/cover/" in lower or "/covers/" in lower:
                        report["covers"] += 1
                    elif "/backups/" in lower or lower.endswith(".zip"):
                        report["backups"] += 1
                    else:
                        report["other"] += 1
                except Exception as exc:
                    report["errors"].append(f"{path.name}: {exc.__class__.__name__}")
        self.write_novel_index()
        return report

    def sync_to_remote(self, novel_id: str | None = None) -> None:
        if self.remote is None:
            return
        if self._startup_phase and self.disable_startup_remote_sync:
            logger.info("Skipping Supabase remote sync during startup.")
            return
        try:
            if novel_id:
                self.remote.upload_tree(self.novel_dir(novel_id), f"novels/{novel_id}")
                self.write_counts_cache(novel_id)
                self.write_novel_index()
            else:
                self.remote.upload_tree(self.data_dir / "app", "app")
        except Exception:
            logger.exception("Failed to sync local files to Supabase")

    def write_novel_index(self) -> None:
        if self.remote is None:
            return
        index = [{"novel_id": item["novel_id"], "title": item.get("title", "")} for item in self.iter_metadata()]
        self.remote.write_text("novels/index.json", json.dumps(index, indent=2, ensure_ascii=False))

    def remote_json(self, path: str) -> dict[str, Any] | list[Any] | None:
        if self.remote is None:
            return None
        try:
            text = self.remote.read_text(path)
            return json.loads(text) if text else None
        except Exception as exc:
            logger.warning("Supabase JSON read failed for %s: %s", path, exc.__class__.__name__)
            return None

    def write_remote_json(self, path: str, data: dict[str, Any] | list[Any]) -> None:
        if self.remote is None:
            return
        try:
            self.remote.write_text(path, json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            logger.exception("Supabase JSON write failed for %s", path)

    def hydrate_remote_index(self) -> list[dict[str, Any]]:
        if self.remote is None:
            return []
        raw_index = self.remote_json("novels/index.json") or self.remote_json("app/novels/index.json")
        items = [item for item in raw_index if isinstance(item, dict) and item.get("novel_id")] if isinstance(raw_index, list) else []
        if not items:
            try:
                metadata_paths = [path for prefix in ("novels", "app/novels") for path in self.remote.list_paths(prefix) if path.endswith("/metadata.json")][:200]
                items = []
                for path in metadata_paths:
                    parts = path.split("/")
                    if path.startswith("app/novels/") and len(parts) >= 4:
                        items.append({"novel_id": parts[2]})
                    elif path.startswith("novels/") and len(parts) >= 3:
                        items.append({"novel_id": parts[1]})
            except Exception as exc:
                logger.warning("Supabase novel index listing failed: %s", exc.__class__.__name__)
                return []
        hydrated: list[dict[str, Any]] = []
        for item in items[:200]:
            novel_id = str(item["novel_id"])
            metadata = self.remote_json(f"novels/{novel_id}/metadata.json") or self.remote_json(f"app/novels/{novel_id}/metadata.json")
            if not isinstance(metadata, dict):
                metadata = {
                    "novel_id": novel_id,
                    "title": str(item.get("title") or novel_id.replace("-", " ").title()),
                    "summary": "",
                    "tags": [],
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "source_language": "Chinese",
                    "target_language": "English",
                    "settings": {"model": "gpt-4o-mini", "retry_failed_chapters": 1, "stop_when_budget_reached": True, "batch_size": 25},
                }
            self.write_json(self.metadata_path(novel_id), metadata)
            hydrated.append(metadata)
        return hydrated

    def remote_category_paths(self, novel_id: str, category: str) -> list[str]:
        if self.remote is None:
            return []
        prefixes = [f"novels/{novel_id}/{REMOTE_PREFIXES[category]}"]
        prefixes.extend(f"app/novels/{novel_id}/{legacy}" for legacy in LEGACY_REMOTE_PREFIXES.get(category, ()))
        paths: list[str] = []
        seen: set[str] = set()
        for prefix in prefixes:
            try:
                for path in self.remote.list_paths(prefix):
                    if path.lower().endswith(".txt") and path not in seen:
                        paths.append(path)
                        seen.add(path)
            except Exception as exc:
                logger.warning("Supabase %s listing failed for %s at %s: %s", category, novel_id, prefix, exc.__class__.__name__)
        return paths[:5000]

    def remote_category_counts(self, novel_id: str) -> dict[str, dict[str, int]]:
        canonical: dict[str, int] = {}
        legacy: dict[str, int] = {}
        if self.remote is None:
            return {"canonical": {}, "legacy": {}}
        for category in REMOTE_PREFIXES:
            try:
                canonical_paths = [path for path in self.remote.list_paths(f"novels/{novel_id}/{REMOTE_PREFIXES[category]}") if path.lower().endswith(".txt")]
            except Exception:
                canonical_paths = []
            legacy_paths: list[str] = []
            for legacy_prefix in LEGACY_REMOTE_PREFIXES.get(category, ()):
                try:
                    legacy_paths.extend(path for path in self.remote.list_paths(f"app/novels/{novel_id}/{legacy_prefix}") if path.lower().endswith(".txt"))
                except Exception:
                    continue
            canonical[category] = len({self.chapter_number_from_remote(path) for path in canonical_paths} - {None})
            legacy[category] = len({self.chapter_number_from_remote(path) for path in legacy_paths} - {None})
        return {"canonical": canonical, "legacy": legacy}

    def chapter_number_from_remote(self, path: str) -> int | None:
        return chapter_from_filename(Path(path.replace("\\", "/").split("/")[-1]))

    def remote_counts(self, novel_id: str) -> dict[str, Any]:
        cached = self.remote_json(f"novels/{novel_id}/counts.json")
        legacy_cached = self.remote_json(f"app/novels/{novel_id}/counts.json")
        if isinstance(cached, dict) and "counts" in cached and any(int(value or 0) for value in cached["counts"].values() if isinstance(value, int)):
            return cached
        if isinstance(legacy_cached, dict) and "counts" in legacy_cached:
            counts = legacy_cached["counts"]
            normalized = {
                "originals": int(counts.get("originals") or counts.get("original") or counts.get("original_files") or 0),
                "references": int(counts.get("references") or counts.get("reference") or counts.get("reference_files") or 0),
                "ai_translations": int(counts.get("ai_translations") or counts.get("ai") or counts.get("translated_chapters") or 0),
                "prompts": int(counts.get("prompts") or 0),
                "updated_at": legacy_cached.get("updated_at") or utc_now(),
            }
            if any(normalized[key] for key in ("originals", "references", "ai_translations", "prompts")):
                return {"novel_id": novel_id, "counts": normalized, "updated_at": normalized["updated_at"], "source": "legacy_counts"}
        counts = {
            "originals": len({self.chapter_number_from_remote(path) for path in self.remote_category_paths(novel_id, "original")} - {None}),
            "references": len({self.chapter_number_from_remote(path) for path in self.remote_category_paths(novel_id, "reference")} - {None}),
            "ai_translations": len({self.chapter_number_from_remote(path) for path in self.remote_category_paths(novel_id, "ai")} - {None}),
            "prompts": len({self.chapter_number_from_remote(path) for path in self.remote_category_paths(novel_id, "prompt")} - {None}),
            "updated_at": utc_now(),
        }
        self.write_remote_json(f"novels/{novel_id}/counts.json", {"novel_id": novel_id, "counts": counts, "updated_at": counts["updated_at"]})
        return {"novel_id": novel_id, "counts": counts, "updated_at": counts["updated_at"]}

    def local_counts(self, novel_id: str) -> dict[str, int]:
        folders = self.folders(novel_id)
        chapters = self.chapters(novel_id, include_remote=False)
        translated = sum(1 for chapter in chapters if chapter.get("status") == "translated")
        original_valid = len(self.chapter_numbers_for_folder(folders["original"]))
        return {
            "originals": original_valid,
            "references": len(self.chapter_numbers_for_folder(folders["reference"])),
            "ai_translations": translated,
            "prompts": sum(1 for chapter in chapters if chapter.get("prompt_path")),
            "remaining": max(0, original_valid - translated),
        }

    def active_counts(self, novel_id: str) -> dict[str, int]:
        local = self.local_counts(novel_id)
        remote = self.remote_counts(novel_id).get("counts", {}) if self.remote is not None else {}
        originals = max(local.get("originals", 0), int(remote.get("originals") or 0))
        references = max(local.get("references", 0), int(remote.get("references") or 0))
        ai = max(local.get("ai_translations", 0), int(remote.get("ai_translations") or 0))
        prompts = max(local.get("prompts", 0), int(remote.get("prompts") or 0))
        return {"originals": originals, "references": references, "ai_translations": ai, "prompts": prompts, "remaining": max(0, originals - ai)}

    def write_counts_cache(self, novel_id: str) -> dict[str, Any]:
        counts = self.active_counts(novel_id)
        payload = {"novel_id": novel_id, "counts": counts, "updated_at": utc_now()}
        self.write_json(self.novel_dir(novel_id) / "counts.json", payload)
        self.write_remote_json(f"novels/{novel_id}/counts.json", payload)
        return payload

    def rebuild_index(self, novel_id: str | None = None) -> dict[str, Any]:
        ids = [novel_id] if novel_id else [str(item["novel_id"]) for item in self.iter_metadata()]
        report: dict[str, Any] = {"ok": True, "novels": [], "warnings": []}
        for item_id in ids:
            try:
                if self.remote is not None:
                    self.hydrate_remote_metadata(item_id)
                report["novels"].append(self.write_counts_cache(item_id))
            except Exception as exc:
                report["warnings"].append(f"{item_id}: {exc.__class__.__name__}")
        self.write_novel_index()
        return report

    def deep_discovery(self, novel_id: str = DEFAULT_NOVEL_ID) -> dict[str, Any]:
        if self.remote is None:
            return {"ok": False, "warnings": ["Supabase storage is not configured."], "suggested_action": "Configure Supabase storage first."}
        warnings: list[str] = []
        canonical_paths: dict[str, int] = {}
        legacy_paths: dict[str, int] = {}
        for category in REMOTE_PREFIXES:
            try:
                canonical_paths[category] = len([path for path in self.remote.list_paths(f"novels/{novel_id}/{REMOTE_PREFIXES[category]}") if path.lower().endswith(".txt")])
            except Exception as exc:
                canonical_paths[category] = 0
                warnings.append(f"Canonical {category} scan failed: {exc.__class__.__name__}")
            count = 0
            for legacy_prefix in LEGACY_REMOTE_PREFIXES.get(category, ()):
                try:
                    count += len([path for path in self.remote.list_paths(f"app/novels/{novel_id}/{legacy_prefix}") if path.lower().endswith(".txt")])
                except Exception:
                    continue
            legacy_paths[category] = count
        backup_zips = self.supabase_backup_zips(novel_id)
        cover_files = self.remote_files_for_prefixes([f"novels/{novel_id}", f"app/novels/{novel_id}/Cover"], {".jpg", ".jpeg", ".png", ".webp"}, limit=50)
        metadata_files = [path for path in (f"novels/{novel_id}/metadata.json", f"app/novels/{novel_id}/metadata.json", f"app/novels/{novel_id}/index.json") if self.remote.read_bytes(path) is not None]
        if any(legacy_paths.values()) and not any(canonical_paths.values()):
            warnings.append("Files found in legacy Supabase paths. Migration recommended.")
            suggested = "Run Migrate Legacy Paths dry-run, then confirm migration if the report looks correct."
        elif backup_zips and not any(canonical_paths.values()):
            warnings.append("Canonical chapter folders are empty, but Supabase backup ZIPs were found.")
            suggested = "Restore from the newest Supabase backup ZIP dry-run, then confirm restore."
        else:
            suggested = "Rebuild Supabase Index if counts look stale."
        return {
            "ok": True,
            "buckets": self.remote.health().get("buckets", {}),
            "canonical_paths": canonical_paths,
            "legacy_paths": legacy_paths,
            "backup_zips": backup_zips,
            "cover_files": cover_files,
            "metadata_files": metadata_files,
            "suggested_action": suggested,
            "warnings": warnings,
        }

    def remote_files_for_prefixes(self, prefixes: list[str], suffixes: set[str], limit: int = 200) -> list[str]:
        if self.remote is None:
            return []
        found: list[str] = []
        seen: set[str] = set()
        for prefix in prefixes:
            try:
                for path in self.remote.list_paths(prefix):
                    if path not in seen and Path(path).suffix.lower() in suffixes:
                        found.append(path)
                        seen.add(path)
                        if len(found) >= limit:
                            return found
            except Exception:
                continue
        return found

    def supabase_backup_zips(self, novel_id: str = DEFAULT_NOVEL_ID) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if self.remote is not None:
            for path in self.remote_files_for_prefixes([f"app/novels/{novel_id}/Backups", "app/Backups", "Backups"], {".zip"}, limit=200):
                candidates.append({"bucket": self.remote.bucket, "path": path, "filename": Path(path).name, "restore_supported": True})
        for bucket in ("backups", "exports"):
            try:
                remote = SupabaseStorage(bucket=bucket)
                for path in [item for item in remote.list_paths("") if item.lower().endswith(".zip")][:200]:
                    candidates.append({"bucket": bucket, "path": path, "filename": Path(path).name, "restore_supported": True})
            except Exception:
                continue
        candidates.sort(key=lambda item: item["filename"], reverse=True)
        if candidates:
            candidates[0]["likely_newest"] = True
        return candidates

    def migrate_legacy_paths(self, novel_id: str, dry_run: bool = True, confirm: bool = False, overwrite: bool = False) -> dict[str, Any]:
        if self.remote is None:
            raise ValueError("Supabase storage is not configured.")
        if not dry_run and not confirm:
            raise ValueError("Real migration requires confirm=true.")
        before = self.remote_counts(novel_id).get("counts", {})
        report: dict[str, Any] = {"ok": True, "dry_run": dry_run, "status": "running", "found_legacy_files": 0, "files_to_copy": 0, "copied": 0, "skipped_existing": 0, "ambiguous": 0, "errors": [], "warnings": [], "items": [], "counts_before": before, "counts_after": before, "next_recommended_action": "rebuild_index"}
        mapping = {
            "original": (LEGACY_REMOTE_PREFIXES["original"], f"novels/{novel_id}/originals"),
            "reference": (LEGACY_REMOTE_PREFIXES["reference"], f"novels/{novel_id}/references"),
            "ai": (LEGACY_REMOTE_PREFIXES["ai"], f"novels/{novel_id}/ai_translations"),
            "prompt": (LEGACY_REMOTE_PREFIXES["prompt"], f"novels/{novel_id}/prompts"),
        }
        for category, (legacy_prefixes, target_prefix) in mapping.items():
            for legacy_prefix in legacy_prefixes:
                for source_path in self.remote.list_paths(f"app/novels/{novel_id}/{legacy_prefix}"):
                    if not source_path.lower().endswith(".txt"):
                        continue
                    report["found_legacy_files"] += 1
                    chapter = self.chapter_number_from_remote(source_path)
                    if chapter is None:
                        report["ambiguous"] += 1
                        report["items"].append({"source": source_path, "status": "ambiguous"})
                        continue
                    target_path = f"{target_prefix}/{chapter:04d}.txt"
                    if not overwrite and self.remote.read_bytes(target_path) is not None:
                        report["skipped_existing"] += 1
                        report["items"].append({"source": source_path, "target": target_path, "status": "skipped_existing"})
                        continue
                    report["files_to_copy"] += 1
                    if not dry_run:
                        data = self.remote.read_bytes(source_path)
                        if data is not None:
                            self.remote.write_bytes(target_path, data)
                    report["copied"] += 1
                    report["items"].append({"source": source_path, "target": target_path, "category": category, "status": "would_copy" if dry_run else "copied"})
        for source_path in self.remote_files_for_prefixes([f"app/novels/{novel_id}/Cover"], {".jpg", ".jpeg", ".png", ".webp"}, limit=20):
            target_path = f"novels/{novel_id}/cover{Path(source_path).suffix.lower()}"
            if not overwrite and self.remote.read_bytes(target_path) is not None:
                report["skipped_existing"] += 1
                continue
            report["files_to_copy"] += 1
            if not dry_run:
                data = self.remote.read_bytes(source_path)
                if data is not None:
                    self.remote.write_bytes(target_path, data)
            report["copied"] += 1
            report["items"].append({"source": source_path, "target": target_path, "category": "cover", "status": "would_copy" if dry_run else "copied"})
        for name in ("metadata.json", "counts.json"):
            source_path = f"app/novels/{novel_id}/{name}"
            target_path = f"novels/{novel_id}/{name}"
            data = self.remote.read_bytes(source_path)
            if data is None:
                continue
            if not overwrite and self.remote.read_bytes(target_path) is not None:
                report["skipped_existing"] += 1
                continue
            report["files_to_copy"] += 1
            if not dry_run:
                self.remote.write_bytes(target_path, data, "application/json")
            report["copied"] += 1
            report["items"].append({"source": source_path, "target": target_path, "category": name, "status": "would_copy" if dry_run else "copied"})
        if not dry_run:
            self.hydrate_remote_metadata(novel_id)
            self.write_counts_cache(novel_id)
            self.write_novel_index()
            report["counts_after"] = self.remote_counts(novel_id).get("counts", {})
        if report["files_to_copy"] == 0:
            report["status"] = "completed_no_changes"
            report["next_recommended_action"] = "restore_from_supabase_backup" if self.supabase_backup_zips(novel_id) else "deep_scan_supabase"
            report["warnings"].append("No legacy chapter files were found to migrate. Your active Supabase folders are empty. If a backup ZIP was found, the next step is Restore From Supabase Backup.")
        else:
            report["status"] = "completed" if dry_run else "completed_copied"
        return report

    def hydrate_remote_metadata(self, novel_id: str) -> dict[str, Any] | None:
        metadata = self.remote_json(f"novels/{novel_id}/metadata.json") or self.remote_json(f"app/novels/{novel_id}/metadata.json")
        if isinstance(metadata, dict):
            self.write_json(self.metadata_path(novel_id), metadata)
            return metadata
        return None

    def service_for(self, novel_id: str) -> TranslationService:
        return TranslationService(data_dir=self.novel_dir(novel_id), translator=self.root_service.translator)

    def ensure_default_novel(self) -> dict[str, Any]:
        if self.remote is not None and not self.metadata_path(DEFAULT_NOVEL_ID).exists():
            self.hydrate_remote_index()
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
        self.sync_to_remote(candidate)
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
        self.sync_to_remote(novel_id)
        return self.decorate_novel(metadata)

    def delete_novel(self, novel_id: str) -> None:
        if novel_id == DEFAULT_NOVEL_ID:
            raise ValueError("The migrated I Am God novel cannot be deleted from the API.")
        shutil.rmtree(self.novel_dir(novel_id), ignore_errors=True)
        if self.remote is not None:
            self.remote.delete(f"novels/{novel_id}")
            self.write_novel_index()

    def list_novels(self) -> list[dict[str, Any]]:
        return sorted((self.decorate_novel(item) for item in self.iter_metadata()), key=lambda item: item.get("updated_at") or "", reverse=True)

    def get_novel(self, novel_id: str) -> dict[str, Any]:
        return self.decorate_novel(self.get_metadata(novel_id))

    def library(self, novel_id: str) -> dict[str, Any]:
        return {"novel": self.get_novel(novel_id), "chapters": self.chapters(novel_id)}

    async def upload_original(self, novel_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
        await self.service_for(novel_id)._save_uploads(uploads, self.folders(novel_id)["original"])
        self.touch(novel_id)
        self.sync_to_remote(novel_id)
        return self.library(novel_id)

    async def upload_reference(self, novel_id: str, uploads: list[UploadFile]) -> dict[str, Any]:
        await self.service_for(novel_id)._save_uploads(uploads, self.folders(novel_id)["reference"])
        self.touch(novel_id)
        self.sync_to_remote(novel_id)
        return self.library(novel_id)

    async def import_ai_translations(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "ai-translated-chapters.zip")
        if Path(filename).suffix.lower() != ".zip":
            raise ValueError("AI translated chapters import must be a .zip file.")

        imported = 0
        invalid = 0
        skipped = 0
        warnings: list[str] = []
        ai_dir = self.folders(novel_id)["ai"]
        ai_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(await upload.read())) as archive:
            warnings.extend(self.category_warnings(archive.namelist(), "ai_translations"))
            seen: set[int] = set()
            for member in archive.infolist():
                if member.is_dir():
                    continue

                name = Path(member.filename.replace("\\", "/")).name
                if not re.fullmatch(r"\d{1,6}\.txt", name, re.IGNORECASE):
                    invalid += 1
                    continue

                chapter_number = int(Path(name).stem)
                if chapter_number in seen:
                    skipped += 1
                    continue
                target = ai_dir / f"{chapter_number:04d}.txt"
                with archive.open(member) as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output)
                seen.add(chapter_number)
                imported += 1

        self.touch(novel_id)
        self.sync_to_remote(novel_id)
        return {"imported": imported, "skipped": skipped, "invalid": invalid, "duplicates": skipped, "warnings": warnings, "destination_category": "ai_translations", **self.library(novel_id)}

    async def import_original_zip(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        result = await self.import_chapter_zip(novel_id, upload, "original", "Original Story")
        return {**result, **self.library(novel_id)}

    async def import_reference_zip(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        result = await self.import_chapter_zip(novel_id, upload, "reference", "Reference Translation")
        return {**result, **self.library(novel_id)}

    async def import_chapter_zip(self, novel_id: str, upload: UploadFile, folder_key: str, label: str) -> dict[str, Any]:
        filename = safe_filename(upload.filename, f"{folder_key}-chapters.zip")
        if Path(filename).suffix.lower() != ".zip":
            raise ValueError(f"{label} import must be a .zip file.")

        target_dir = self.folders(novel_id)[folder_key]
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = set(self.chapter_numbers_for_folder(target_dir))
        seen: set[int] = set()
        imported = 0
        duplicates = 0
        invalid = 0
        warnings: list[str] = []
        destination = {"original": "originals", "reference": "references", "ai": "ai_translations"}.get(folder_key, folder_key)

        with zipfile.ZipFile(io.BytesIO(await upload.read())) as archive:
            warnings.extend(self.category_warnings(archive.namelist(), destination))
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = Path(member.filename.replace("\\", "/")).name
                if Path(name).suffix.lower() != ".txt":
                    invalid += 1
                    continue
                number = chapter_from_filename(Path(name))
                if number is None:
                    invalid += 1
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
        self.sync_to_remote(novel_id)
        return {"imported": imported, "duplicates": duplicates, "skipped": duplicates, "invalid": invalid, "warnings": warnings, "destination_category": destination}

    def category_warnings(self, names: list[str], destination: str) -> list[str]:
        checks = {
            "originals": ("reference", "novelfire", "ai", "translation", "translated"),
            "references": ("ai", "machine", "gpt", "translated-ai", "ai_translation", "ai-translations"),
            "ai_translations": ("reference", "novelfire", "original", "chinese", "source"),
        }
        suspicious = []
        needles = checks.get(destination, ())
        for name in names:
            lower = name.replace("\\", "/").lower()
            if any(needle in lower for needle in needles):
                suspicious.append(name)
            if len(suspicious) >= 8:
                break
        if not suspicious:
            return []
        label = {"originals": "Original Chinese", "references": "Reference Translation", "ai_translations": "AI Translation"}.get(destination, destination)
        return [f"ZIP path names look suspicious for {label}: {', '.join(suspicious)}. Files were still written only to {destination}."]

    async def upload_cover(self, novel_id: str, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "cover.png")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("Cover image must be jpg, jpeg, png, or webp.")
        data = await upload.read()
        if len(data) > COVER_MAX_BYTES:
            raise ValueError("Cover image must be 5 MB or smaller.")
        cover_dir = self.folders(novel_id)["cover"]
        cover_dir.mkdir(parents=True, exist_ok=True)
        target = cover_dir / f"cover{suffix}"
        metadata = self.get_metadata(novel_id)
        try:
            target.write_bytes(data)
            if self.remote is not None:
                self.remote.write_bytes(f"novels/{novel_id}/cover{suffix}", data)
            for old_cover in cover_dir.glob("*"):
                if old_cover.is_file() and old_cover != target:
                    old_cover.unlink()
            metadata.setdefault("settings", {})["cover_file"] = str(target.relative_to(self.novel_dir(novel_id)))
            metadata["updated_at"] = utc_now()
            self.write_json(self.metadata_path(novel_id), metadata)
            self.sync_to_remote(novel_id)
        except Exception as exc:
            target.unlink(missing_ok=True)
            logger.warning("Cover upload failed for %s: %s", novel_id, exc.__class__.__name__)
            raise ValueError("Cover upload failed. Storage may be temporarily unavailable; try again.") from exc
        return self.library(novel_id)

    async def upload_app_icon(self, upload: UploadFile) -> dict[str, Any]:
        filename = safe_filename(upload.filename, "app-icon.png")
        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValueError("App icon must be jpg, jpeg, png, or webp.")
        icon_dir = self.data_dir / "app"
        icon_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ("icon.*", "app-icon.*"):
            for old_icon in icon_dir.glob(pattern):
                if old_icon.is_file():
                    old_icon.unlink()
        target = icon_dir / f"icon{suffix}"
        with open(target, "wb") as output:
            output.write(await upload.read())
        self.sync_to_remote()
        return self.app_settings()

    def app_icon_path(self) -> Path | None:
        for path in list((self.data_dir / "app").glob("icon.*")) + list((self.data_dir / "app").glob("app-icon.*")):
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
        self.sync_to_remote()
        return self.app_settings()

    def reset_app_settings(self) -> dict[str, Any]:
        path = self.app_settings_path()
        if path.exists():
            path.unlink()
        if self.remote is not None:
            self.remote.delete("app/settings.json")
        return self.app_settings()

    def create_batch(self, novel_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        batch_size = max(1, min(200, int(settings.get("batch_size") or 25)))
        start_chapter = int(settings.get("start_chapter") or 1)
        end_chapter = int(settings.get("end_chapter") or 999999)
        missing_only = bool(settings.get("missing_only", True))
        overwrite = bool(settings.get("overwrite", False))
        references = self.reference_files_by_number(novel_id)
        candidates = [
            chapter for chapter in self.chapters(novel_id)
            if chapter.get("source_path")
            and start_chapter <= int(chapter.get("chapter") or 0) <= end_chapter
            and (overwrite or not missing_only or not chapter.get("has_translation"))
            and (overwrite or chapter.get("status") != "translated")
        ][:batch_size]
        if start_chapter > end_chapter:
            raise ValueError("Start chapter must be less than or equal to end chapter.")
        if not candidates:
            raise ValueError("No chapters need translation for the selected range/settings.")
        materialized = self.novel_dir(novel_id) / "batch_cache"
        materialized_originals = materialized / "originals"
        materialized_references = materialized / "references"
        materialized_originals.mkdir(parents=True, exist_ok=True)
        materialized_references.mkdir(parents=True, exist_ok=True)
        chinese_files: list[Path] = []
        reference_files: list[Path] = []
        for chapter in candidates:
            number = int(chapter["chapter"])
            source = str(chapter.get("source_path") or "")
            source_path = Path(source)
            if source.startswith("supabase://"):
                text = self.remote_read_chapter(source)
                if text:
                    source_path = materialized_originals / f"{number:04d}.txt"
                    source_path.write_text(text, encoding="utf-8")
            if source_path.is_file():
                chinese_files.append(source_path)
            reference = references.get(number)
            if reference:
                reference_files.append(reference)
            else:
                reference_value = str(chapter.get("reference_path") or "")
                if reference_value.startswith("supabase://"):
                    text = self.remote_read_chapter(reference_value)
                    if text:
                        path = materialized_references / f"{number:04d}.txt"
                        path.write_text(text, encoding="utf-8")
                        reference_files.append(path)
        try:
            job = self.service_for(novel_id).create_job_from_existing_files(chinese_files, reference_files, settings)
        finally:
            shutil.rmtree(materialized, ignore_errors=True)
        self.touch(novel_id)
        self.write_remote_json(f"novels/{novel_id}/metadata.json", self.get_metadata(novel_id))
        self.write_counts_cache(novel_id)
        self.write_novel_index()
        return job

    def start_job(self, novel_id: str, job_id: str) -> None:
        self.service_for(novel_id).start_job(job_id)
        self.touch(novel_id)
        self.sync_to_remote(novel_id)

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
        text = ""
        if isinstance(path_value, str) and path_value.startswith("supabase://"):
            text = self.remote_read_chapter(path_value) or ""
        elif path_value and Path(str(path_value)).exists():
            text = read_text(path_value)
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
        if self.remote is not None:
            for suffix in (".jpg", ".jpeg", ".png", ".webp"):
                remote_path = f"novels/{novel_id}/cover{suffix}"
                try:
                    data = self.remote.read_bytes(remote_path)
                except Exception:
                    data = None
                if data:
                    target = self.folders(novel_id)["cover"] / f"cover{suffix}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    return target
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

    def clear_backup_state(self) -> dict[str, Any]:
        cleared = 0
        for state_path in (self.data_dir / "storage_state.json", self.data_dir / "backup_state.json", self.data_dir / "restore_state.json", self.data_dir / "undo_restore_state.json"):
            if state_path.exists() and state_path.is_file():
                state_path.unlink()
                cleared += 1
        for metadata in self.iter_metadata():
            settings = metadata.get("settings")
            if isinstance(settings, dict):
                changed = False
                for key in ("last_backup_at", "pending_backup", "pending_restore", "undo_restore"):
                    if key in settings:
                        settings.pop(key, None)
                        changed = True
                if changed:
                    self.write_json(self.metadata_path(str(metadata["novel_id"])), metadata)
                    cleared += 1
        return {"cleared": cleared}

    def content_audit(self, novel_id: str) -> dict[str, Any]:
        folders = self.folders(novel_id)
        counts = {
            "originals": len(list(folders["original"].rglob("*.txt"))),
            "references": len(list(folders["reference"].rglob("*.txt"))),
            "ai_translations": len(list(folders["ai"].rglob("*.txt"))),
            "prompts": sum(1 for chapter in self.chapters(novel_id) if chapter.get("prompt_path")),
        }
        samples = {
            "originals": [path.name for path in sorted(folders["original"].rglob("*.txt"))[:5]],
            "references": [path.name for path in sorted(folders["reference"].rglob("*.txt"))[:5]],
            "ai_translations": [path.name for path in sorted(folders["ai"].rglob("*.txt"))[:5]],
        }
        old_paths = []
        unknown_paths = []
        suspicious_files = []
        for path in self.novel_dir(novel_id).rglob("*.txt"):
            rel = path.relative_to(self.novel_dir(novel_id)).as_posix()
            if rel.startswith(("Original/", "Reference/", "AI/", "jobs/")):
                continue
            if any(part.lower() in {"translation", "translations", "translated", "novelfire"} for part in Path(rel).parts):
                old_paths.append(rel)
            else:
                unknown_paths.append(rel)
        duplicate_numbers = []
        seen: dict[tuple[str, int], str] = {}
        for category, folder in (("originals", folders["original"]), ("references", folders["reference"]), ("ai_translations", folders["ai"])):
            for path in folder.rglob("*.txt"):
                number = parse_chapter(path).get("number")
                if number is None:
                    suspicious_files.append(path.relative_to(self.novel_dir(novel_id)).as_posix())
                    continue
                key = (category, int(number))
                if key in seen:
                    duplicate_numbers.append({"category": category, "chapter": int(number), "files": [seen[key], path.name]})
                seen[key] = path.name
        warnings = []
        if old_paths or unknown_paths or suspicious_files or duplicate_numbers:
            warnings.append("Content map may need repair. Review paths before applying changes.")
        return {"ok": True, "novel_id": novel_id, "counts": counts, "samples": samples, "unknown_paths": unknown_paths[:100], "old_paths": old_paths[:100], "suspicious_files": suspicious_files[:100], "duplicates": duplicate_numbers[:100], "warnings": warnings}

    def repair_content_map(self, novel_id: str, options: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(options.get("dry_run", True))
        audit = self.content_audit(novel_id)
        actions: list[dict[str, Any]] = []
        warnings = list(audit.get("warnings", []))
        if options.get("rebuild_index", True):
            actions.append({"action": "rebuild_index", "dry_run": dry_run})
            if not dry_run:
                self.touch(novel_id)
                self.sync_to_remote(novel_id)
        if options.get("move_references_out_of_ai"):
            warnings.append("Automatic reference-vs-AI detection is intentionally conservative. No AI files were moved without explicit certainty.")
        return {"ok": True, "novel_id": novel_id, "dry_run": dry_run, "actions": actions, "audit": audit, "warnings": warnings}

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
        self.sync_to_remote(novel_id)
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

    def remote_marker(self, path: str) -> str:
        return f"supabase://{path}"

    def remote_read_chapter(self, marker: str) -> str | None:
        if self.remote is None or not marker.startswith("supabase://"):
            return None
        path = marker.removeprefix("supabase://")
        try:
            return self.remote.read_text(path)
        except Exception as exc:
            logger.warning("Supabase chapter read failed for %s: %s", path, exc.__class__.__name__)
            return None

    def chapters(self, novel_id: str, include_remote: bool = True) -> list[dict[str, Any]]:
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
        if include_remote and self.remote is not None:
            for category, path_key in (("original", "source_path"), ("reference", "reference_path"), ("ai", "output_path"), ("prompt", "prompt_path")):
                for remote_path in self.remote_category_paths(novel_id, category):
                    number = self.chapter_number_from_remote(remote_path)
                    if number is None:
                        continue
                    current = chapters.setdefault(number, self.base_chapter(number, Path(remote_path).stem))
                    current[path_key] = current.get(path_key) or self.remote_marker(remote_path)
                    if category == "ai":
                        current["status"] = "translated"
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
        active_counts = self.active_counts(novel_id)
        translated = active_counts["ai_translations"]
        original_valid = active_counts["originals"]
        reference_valid = active_counts["references"]
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
                "remaining_chapters": active_counts["remaining"],
                "prompts": active_counts["prompts"],
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
        if self.remote is not None:
            self.hydrate_remote_index()
        metadata = []
        for path in sorted(self.novels_dir.glob("*/metadata.json")):
            try:
                metadata.append(self.read_json(path))
            except (OSError, json.JSONDecodeError):
                continue
        return metadata

    def get_metadata(self, novel_id: str) -> dict[str, Any]:
        if not self.metadata_path(novel_id).exists():
            if self.remote is not None:
                self.hydrate_remote_metadata(novel_id)
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
