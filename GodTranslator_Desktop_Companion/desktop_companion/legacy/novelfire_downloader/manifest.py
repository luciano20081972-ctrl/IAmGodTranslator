from __future__ import annotations

import json
import hashlib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "download_manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "requested_chapters": [],
        "successful_chapters": [],
        "failed_chapters": {},
        "skipped_chapters": [],
        "chapters": {},
    }


def save_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = now_iso()
    (output_dir / "download_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def save_metadata(output_dir: Path, novel_title: str, source_url: str, chapters: dict[str, Any]) -> None:
    payload = {
        "novel_title": novel_title,
        "source_url": source_url,
        "created_at": now_iso(),
        "chapters": chapters,
    }
    (output_dir / "metadata.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_reference_pack(
    output_dir: Path,
    novel_id: str = "i-am-god",
    novel_title: str = "I Am God",
    source: str = "novelfire",
    zip_name: str = "godtranslator_reference_pack.zip",
) -> Path:
    zip_path = output_dir / zip_name
    chapters: dict[str, Any] = {}
    text_files = sorted(output_dir.glob("*.txt"))
    for path in text_files:
        try:
            chapter_number = int(path.stem)
        except ValueError:
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        archive_name = f"chapters/{chapter_number:04d}.txt"
        chapters[str(chapter_number)] = {
            "file": archive_name,
            "character_count": len(text),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    manifest = {
        "format": "godtranslator-reference-pack-v1",
        "novel_id": novel_id,
        "novel_title": novel_title,
        "target_mode": "reference",
        "source": source,
        "created_at": now_iso(),
        "chapters": chapters,
    }
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in text_files:
            try:
                chapter_number = int(path.stem)
            except ValueError:
                continue
            zf.write(path, f"chapters/{chapter_number:04d}.txt")
    return zip_path


def create_godtranslator_zip(output_dir: Path, zip_name: str | None = None) -> Path:
    return create_reference_pack(output_dir, zip_name=zip_name or "godtranslator_reference_pack.zip")
