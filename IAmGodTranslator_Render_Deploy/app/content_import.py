from __future__ import annotations

import io
import json
import hashlib
import zipfile
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


def payload_from_uploads(file_payloads: list[tuple[str, bytes]], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = dict(fallback or {})
    items: list[dict[str, Any]] = []
    novel_payload = fallback.get("novel") if isinstance(fallback.get("novel"), dict) else {}
    novel_id = fallback.get("novel_id") or novel_payload.get("id") or ""
    metadata = fallback.get("metadata") if isinstance(fallback.get("metadata"), dict) else {}
    warnings: list[str] = []

    for filename, data in file_payloads:
        if filename.lower().endswith(".zip"):
            pack = payload_from_zip(filename, data)
            items.extend(pack.get("items", []))
            if pack.get("novel_id") and not novel_id:
                novel_id = pack["novel_id"]
            if isinstance(pack.get("novel"), dict):
                novel_payload = {**novel_payload, **pack["novel"]}
            if isinstance(pack.get("metadata"), dict):
                metadata = {**metadata, **pack["metadata"]}
            warnings.extend(pack.get("warnings", []))
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
            text = decode_text(data)
            content_type = fallback.get("content_type") or "english"
            items.append({"content_type": content_type, "filename": filename, "text": text})

    payload = {**fallback, "items": items, "warnings": warnings}
    if novel_id:
        payload["novel_id"] = novel_id
    if novel_payload:
        payload["novel"] = novel_payload
    if metadata:
        payload["metadata"] = metadata
    return payload


def payload_from_zip(filename: str, data: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            manifest = load_manifest(zf)
            return payload_from_manifest(manifest, {info.filename: info for info in zf.infolist() if not info.is_dir()}, filename, zf)
    except zipfile.BadZipFile:
        return {"items": [], "warnings": [f"{filename}: invalid ZIP file"]}
    except Exception as exc:
        return {"items": [], "warnings": [f"{filename}: {exc}"]}


def load_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = zf.read("manifest.json")
    except KeyError as exc:
        raise ValueError("ZIP pack must include manifest.json") from exc
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
