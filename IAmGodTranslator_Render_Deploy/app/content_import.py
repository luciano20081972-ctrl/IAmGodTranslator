from __future__ import annotations

import io
import json
import hashlib
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any

from app.recovery import decode_text, safe_zip_name


SUPPORTED_PACK_FORMATS = {
    "godtranslator-import-pack-v1",
    "godtranslator-original-pack-v1",
    "godtranslator-english-pack-v1",
    "godtranslator-reference-pack-v1",
    "godtranslator-mixed-pack-v1",
    "godtranslator-downloader-pack-v1",
    "godtranslator-new-novel-pack-v1",
}
SIMPLE_CHAPTER_RE = re.compile(r"\bchapter\s*0*(\d{1,6})(?=\D|$)|第\s*0*(\d{1,6})\s*章", re.IGNORECASE)
SIMPLE_NUMERIC_RE = re.compile(r"^0*(\d{1,6})$", re.IGNORECASE)
SIMPLE_CONTENT_TYPES = {"original", "english", "reference"}


def payload_from_uploads(file_payloads: list[tuple[str, bytes]], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = dict(fallback or {})
    items: list[dict[str, Any]] = []
    novel_payload = fallback.get("novel") if isinstance(fallback.get("novel"), dict) else {}
    novel_id = fallback.get("novel_id") or novel_payload.get("id") or ""
    metadata = fallback.get("metadata") if isinstance(fallback.get("metadata"), dict) else {}
    warnings: list[str] = []
    invalid_files: list[dict[str, str]] = []
    empty_files: list[str] = []
    ambiguous_filenames: list[dict[str, str]] = []

    for filename, data in file_payloads:
        if filename.lower().endswith(".zip"):
            pack = payload_from_zip(filename, data, fallback)
            items.extend(pack.get("items", []))
            if pack.get("novel_id") and not novel_id:
                novel_id = pack["novel_id"]
            if isinstance(pack.get("novel"), dict):
                novel_payload = {**novel_payload, **pack["novel"]}
            if isinstance(pack.get("metadata"), dict):
                metadata = {**metadata, **pack["metadata"]}
            warnings.extend(pack.get("warnings", []))
            invalid_files.extend(pack.get("invalid_files", []))
            empty_files.extend(pack.get("empty_files", []))
            ambiguous_filenames.extend(pack.get("ambiguous_filenames", []))
        elif filename.lower().endswith(".json"):
            try:
                pack = json.loads(data.decode("utf-8"))
            except Exception as exc:
                warnings.append(f"{filename}: invalid JSON ({exc.__class__.__name__})")
                continue
            nested = payload_from_manifest(pack, {}, filename)
            items.extend(nested.get("items", []))
            novel_id = nested.get("novel_id") or novel_id
            novel_payload = {**novel_payload, **(nested.get("novel") or {})}
            metadata = {**metadata, **(nested.get("metadata") or {})}
        else:
            item, problem = simple_text_item(filename, data, fallback)
            if item:
                items.append(item)
            elif problem["error"] == "File is empty.":
                empty_files.append(filename)
                warnings.append(f"{filename}: {problem['error']}")
            else:
                invalid_files.append(problem)
                warnings.append(f"{filename}: {problem['error']}")

    payload = {**fallback, "items": items, "warnings": warnings}
    if invalid_files:
        payload["invalid_files"] = invalid_files
    if empty_files:
        payload["empty_files"] = empty_files
    if ambiguous_filenames:
        payload["ambiguous_filenames"] = ambiguous_filenames
    if novel_id:
        payload["novel_id"] = novel_id
    if novel_payload:
        payload["novel"] = novel_payload
    if metadata:
        payload["metadata"] = metadata
    return payload


def payload_from_zip(filename: str, data: bytes, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            manifest = load_manifest(zf)
            infos = {info.filename: info for info in zf.infolist() if not info.is_dir()}
            if manifest is not None:
                return payload_from_manifest(manifest, infos, filename, zf)
            return payload_from_simple_zip(filename, zf, infos.values(), fallback or {})
    except zipfile.BadZipFile:
        return {"items": [], "warnings": [f"{filename}: invalid ZIP file"]}
    except Exception as exc:
        return {"items": [], "warnings": [f"{filename}: {exc}"]}


def load_manifest(zf: zipfile.ZipFile) -> dict[str, Any] | None:
    try:
        raw = zf.read("manifest.json")
    except KeyError:
        return None
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("format") not in SUPPORTED_PACK_FORMATS:
        raise ValueError("Unsupported GodTranslator pack format.")
    return manifest


def payload_from_manifest(
    manifest: dict[str, Any],
    infos: dict[str, zipfile.ZipInfo],
    filename: str,
    zf: zipfile.ZipFile | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    content_type = manifest_content_type(manifest)
    chapters = manifest.get("chapters") or []
    if isinstance(chapters, dict):
        chapter_iter = [{"chapter_number": key, **(value if isinstance(value, dict) else {})} for key, value in chapters.items()]
    else:
        chapter_iter = [row for row in chapters if isinstance(row, dict)]

    for row in chapter_iter:
        item = {
            "chapter_number": row.get("chapter_number") or row.get("number"),
            "content_type": row.get("content_type") or row.get("target_mode") or content_type,
            "edition_type": row.get("edition_type") or manifest.get("edition_type"),
            "language": row.get("language") or manifest.get("language"),
            "title": row.get("title"),
            "source_url": row.get("source_url"),
            "filename": row.get("file") or row.get("path"),
            "text": row.get("text") or "",
            "sha256": row.get("sha256"),
        }
        if zf and item["filename"]:
            safe = safe_zip_name(str(item["filename"]))
            if safe is None:
                warnings.append(f"{item['filename']}: unsafe ZIP path")
                continue
            try:
                raw = zf.read(str(item["filename"]))
            except KeyError:
                warnings.append(f"{item['filename']}: file missing from ZIP")
                continue
            expected_sha = item.get("sha256")
            actual_sha = hashlib.sha256(raw).hexdigest()
            if expected_sha and expected_sha != actual_sha:
                warnings.append(f"{item['filename']}: SHA-256 mismatch")
                continue
            item["text"] = decode_text(raw)
            item["sha256"] = actual_sha
        items.append(item)

    return {
        "novel_id": manifest.get("novel_id"),
        "novel": manifest.get("novel") if isinstance(manifest.get("novel"), dict) else {},
        "metadata": manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {},
        "items": items,
        "pack_format": manifest.get("format"),
        "pack_filename": filename,
        "warnings": warnings,
    }


def manifest_content_type(manifest: dict[str, Any]) -> str:
    explicit = str(manifest.get("content_type") or manifest.get("target_mode") or "").lower()
    if explicit:
        return "english" if explicit == "ai" else explicit
    fmt = str(manifest.get("format") or "").lower()
    if "original" in fmt:
        return "original"
    if "reference" in fmt:
        return "reference"
    if "english" in fmt:
        return "english"
    return "english"


def payload_from_simple_zip(
    filename: str,
    zf: zipfile.ZipFile,
    infos: Any,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = [f"{filename}: no manifest.json found; using Simple Import filename detection."]
    items: list[dict[str, Any]] = []
    invalid_files: list[dict[str, str]] = []
    empty_files: list[str] = []
    ambiguous_filenames: list[dict[str, str]] = []
    for info in infos:
        if not info.filename.lower().endswith(".txt"):
            continue
        safe_name = safe_zip_name(info.filename)
        if safe_name is None:
            problem = {"file": info.filename, "error": "Unsafe ZIP path."}
            invalid_files.append(problem)
            warnings.append(f"{info.filename}: {problem['error']}")
            continue
        if is_zip_symlink(info):
            problem = {"file": info.filename, "error": "ZIP symlink entries are not allowed."}
            invalid_files.append(problem)
            warnings.append(f"{info.filename}: {problem['error']}")
            continue
        item, problem = simple_text_item(safe_name, zf.read(info), fallback)
        if item:
            items.append(item)
        elif problem["error"] == "File is empty.":
            empty_files.append(safe_name)
            warnings.append(f"{safe_name}: {problem['error']}")
        elif problem["error"] == "Ambiguous chapter number.":
            ambiguous_filenames.append(problem)
            warnings.append(f"{safe_name}: {problem['error']}")
        else:
            invalid_files.append(problem)
            warnings.append(f"{safe_name}: {problem['error']}")
    if not items:
        warnings.append(f"{filename}: no importable .txt chapter files were found.")
    return {
        "items": items,
        "warnings": warnings,
        "invalid_files": invalid_files,
        "empty_files": empty_files,
        "ambiguous_filenames": ambiguous_filenames,
        "simple_import": True,
        "pack_filename": filename,
    }


def simple_text_item(filename: str, data: bytes, fallback: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
    content_type = simple_content_type(fallback.get("content_type") or fallback.get("target_mode") or "english")
    if content_type not in SIMPLE_CONTENT_TYPES:
        content_type = "english"
    chapter_number, ambiguous = chapter_number_from_filename(filename)
    if ambiguous:
        return None, {"file": filename, "error": "Ambiguous chapter number."}
    if chapter_number is None:
        return None, {"file": filename, "error": "Could not detect chapter number."}
    text = decode_text(data)
    if not text.strip():
        return None, {"file": filename, "error": "File is empty."}
    return (
        {
            "chapter_number": chapter_number,
            "content_type": content_type,
            "edition_type": fallback.get("edition_type") or "Imported",
            "language": fallback.get("language") or ("en" if content_type == "english" else ""),
            "title": title_from_filename(filename, chapter_number),
            "filename": filename,
            "text": text,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        {},
    )


def chapter_number_from_filename(filename: str) -> tuple[int | None, bool]:
    name = PurePosixPath(str(filename).replace("\\", "/")).name
    stem = name.rsplit(".", 1)[0]
    matches: list[int] = []
    for match in SIMPLE_CHAPTER_RE.finditer(stem):
        value = match.group(1) or match.group(2)
        if value:
            matches.append(int(value))
    numeric = SIMPLE_NUMERIC_RE.match(stem)
    if numeric:
        matches.append(int(numeric.group(1)))
    unique = sorted(set(matches))
    if len(unique) > 1:
        return None, True
    return (unique[0], False) if unique else (None, False)


def title_from_filename(filename: str, chapter_number: int) -> str:
    stem = PurePosixPath(str(filename).replace("\\", "/")).name.rsplit(".", 1)[0]
    cleaned = re.sub(r"[_-]+", " ", stem).strip()
    return cleaned or f"Chapter {chapter_number}"


def simple_content_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "ai": "english",
        "translation": "english",
        "translated": "english",
        "english_chapter": "english",
        "original_chapter": "original",
        "reference_chapter": "reference",
    }
    return aliases.get(normalized, normalized)


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000
