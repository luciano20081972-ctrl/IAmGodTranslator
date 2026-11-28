from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .models import PackResult, TargetMode


MAX_PACK_BYTES = 64 * 1024 * 1024
MAX_PACK_MEMBERS = 3001
SECRET_FILENAMES = {".env", "cookies", "cookies.json", "local state", "web data", "history"}
PACK_FORMATS = {
    "reference": "godtranslator-reference-pack-v1",
    "original": "godtranslator-original-pack-v1",
    "english": "godtranslator-english-pack-v1",
    "mixed": "godtranslator-mixed-pack-v1",
    "new_novel": "godtranslator-new-novel-pack-v1",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_pack(
    source_dir: Path,
    output_dir: Path,
    novel_id: str,
    novel_title: str,
    target_mode: TargetMode = "reference",
    source_type: str = "novelfire",
    source_url: str = "",
    pack_name: str | None = None,
) -> PackResult:
    source_dir = source_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if target_mode not in PACK_FORMATS:
        raise ValueError(f"Unsupported pack target mode: {target_mode}")
    text_files = sorted(path for path in source_dir.rglob("*.txt") if chapter_number_from_file(path) is not None)
    if not text_files:
        raise ValueError("No chapter text files were found.")
    if len(text_files) >= MAX_PACK_MEMBERS or sum(path.stat().st_size for path in text_files) > MAX_PACK_BYTES:
        raise ValueError("Pack exceeds the chapter or 64 MiB content limit. Split it into smaller packs.")
    zip_name = pack_name or f"{novel_id}-{target_mode}-pack.zip"
    if Path(zip_name).name != zip_name or "/" in zip_name or "\\" in zip_name:
        raise ValueError("Pack name must be a file name.")
    zip_path = output_dir / zip_name
    verified = None
    author = ""
    if source_type == "wikisource":
        sidecar = json.loads((source_dir / "metadata.json").read_text(encoding="utf-8"))
        if sidecar.get("source_url") != source_url:
            raise ValueError("Chapter checkpoint belongs to another work.")
        verified = sidecar["chapters"]
        author = str(sidecar.get("author") or "")
    with NamedTemporaryFile(dir=output_dir, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    chapters: dict[str, Any] | list[dict[str, Any]] = [] if target_mode == "mixed" else {}
    total_characters = 0
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            members = set()
            for path in text_files:
                assert_safe_file(path)
                if path.is_symlink() or not path.resolve().is_relative_to(source_dir):
                    raise ValueError("Chapter file is outside the download folder.")
                chapter = chapter_number_from_file(path)
                if chapter is None:
                    continue
                data = path.read_bytes()
                text = data.decode("utf-8")
                content_type = content_type_for_path(path, target_mode)
                archive_name = f"{content_type}/{chapter:04d}.txt" if target_mode == "mixed" else f"chapters/{chapter:04d}.txt"
                if not text.strip():
                    raise ValueError(f"Chapter {chapter} is empty.")
                if archive_name in members:
                    raise ValueError(f"Duplicate chapter {chapter} for {content_type}.")
                members.add(archive_name)
                sha = hashlib.sha256(data).hexdigest()
                if verified is not None:
                    record = verified.get(str(chapter), {})
                    if record.get("file") != path.name or record.get("sha256") != sha:
                        raise ValueError(f"Chapter {chapter} does not match its download checkpoint.")
                total_characters += len(text)
                row = {
                    "file": archive_name,
                    "chapter_number": chapter,
                    "content_type": content_type,
                    "edition_type": "Imported" if target_mode in {"english", "mixed", "new_novel"} else "",
                    "title": title_from_sidecar(source_dir, chapter),
                    "source_url": source_url,
                    "sha256": sha,
                    "character_count": len(text),
                }
                if isinstance(chapters, list):
                    chapters.append(row)
                else:
                    chapters[str(chapter)] = row
                zf.writestr(archive_name, data)
            manifest = {
                "format": PACK_FORMATS[target_mode],
                "pack_format_version": "1.0",
                "novel_id": novel_id,
                "novel": {"id": novel_id, "title": novel_title, "source_url": source_url, "author": author},
                "novel_title": novel_title,
                "target_mode": target_mode,
                "content_type": "mixed" if target_mode == "mixed" else content_type_for_mode(target_mode),
                "source": source_type,
                "source_url": source_url,
                "created_at": now_iso(),
                "chapters": chapters,
                "excluded": ["passwords", "api_keys", "cookies", "browser_profiles", "access_tokens", "refresh_tokens"],
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        validate_pack(temporary)
        temporary.replace(zip_path)
    finally:
        temporary.unlink(missing_ok=True)
    return PackResult(path=zip_path, manifest=manifest, file_count=len(text_files), total_characters=total_characters)


def build_auto_packs(
    source_dir: Path,
    output_dir: Path,
    novel_id: str,
    novel_title: str,
    source_type: str = "novelfire",
    source_url: str = "",
) -> list[PackResult]:
    results: list[PackResult] = []
    for mode in ("original", "reference", "english", "mixed"):
        results.append(
            build_pack(
                source_dir=source_dir,
                output_dir=output_dir,
                novel_id=novel_id,
                novel_title=novel_title,
                target_mode=mode,  # type: ignore[arg-type]
                source_type=source_type,
                source_url=source_url,
                pack_name=f"{novel_id}-{mode}-pack.zip",
            )
        )
    return results


def validate_pack(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_PACK_BYTES:
        raise ValueError("Pack exceeds the 64 MiB transfer limit.")
    with zipfile.ZipFile(path) as zf:
        if len(zf.infolist()) > MAX_PACK_MEMBERS or sum(item.file_size for item in zf.infolist()) > MAX_PACK_BYTES:
            raise ValueError("Pack exceeds the chapter or 64 MiB content limit.")
        names = zf.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Pack contains duplicate ZIP members.")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        chapters = manifest.get("chapters") or {}
        chapter_items = (
            [(str(item.get("chapter_number")), item) for item in chapters if isinstance(item, dict)]
            if isinstance(chapters, list)
            else list(chapters.items())
        )
        if not chapter_items:
            raise ValueError("Pack has no chapter checksums.")
        for chapter, meta in chapter_items:
            file_name = meta.get("file")
            if not file_name:
                raise ValueError(f"Chapter {chapter} has no file.")
            data = zf.read(file_name)
            sha = hashlib.sha256(data).hexdigest()
            if meta.get("sha256") != sha:
                raise ValueError(f"SHA-256 mismatch for chapter {chapter}.")
            text = data.decode("utf-8")
            if int(meta.get("character_count") or 0) != len(text):
                raise ValueError(f"Character count mismatch for chapter {chapter}.")
    return {"ok": True, "manifest": manifest, "chapter_count": len(chapter_items)}


def chapter_number_from_file(path: Path) -> int | None:
    stem = path.stem
    if stem.isdigit():
        return int(stem)
    cjk_match = re.search(r"第\s*0*(\d+)\s*章", stem)
    if cjk_match:
        return int(cjk_match.group(1))
    lowered = stem.lower().replace("_", " ").replace("-", " ")
    parts = lowered.split()
    for index, part in enumerate(parts[:-1]):
        if part in {"chapter", "ch"} and parts[index + 1].isdigit():
            return int(parts[index + 1])
    return None


def content_type_for_mode(target_mode: TargetMode) -> str:
    if target_mode == "new_novel":
        return "original"
    return "english" if target_mode == "english" else str(target_mode)


def content_type_for_path(path: Path, target_mode: TargetMode) -> str:
    if target_mode != "mixed":
        return content_type_for_mode(target_mode)
    parts = {part.lower() for part in path.parts}
    if "english" in parts:
        return "english"
    if "reference" in parts:
        return "reference"
    return "original"


def title_from_sidecar(source_dir: Path, chapter: int) -> str:
    metadata_path = source_dir / "metadata.json"
    if not metadata_path.exists():
        return ""
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        chapter_meta = metadata.get("chapters", {}).get(str(chapter), {})
        return str(chapter_meta.get("title") or "")
    except Exception:
        return ""


def assert_safe_file(path: Path) -> None:
    lowered = path.name.lower()
    if lowered in SECRET_FILENAMES or lowered.endswith((".sqlite", ".db", ".log")):
        raise ValueError(f"Refusing to package unsafe file: {path.name}")
