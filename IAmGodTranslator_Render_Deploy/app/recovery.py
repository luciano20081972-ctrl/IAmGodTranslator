from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.db import Database, readable


REFERENCE_START = 1
REFERENCE_END = 1
MAX_UPLOAD_FILES = 2000
MAX_TEXT_BYTES = 2_000_000
MAX_ZIP_BYTES = 50_000_000
MAX_ZIP_UNCOMPRESSED_BYTES = 80_000_000

EXPLICIT_CHAPTER_RE = re.compile(r"\bchapter\s*0*(\d{1,6})(?=\D|$)|第\s*0*(\d{1,6})\s*章", re.IGNORECASE)
SIMPLE_NUMERIC_RE = re.compile(r"^0*(\d{1,6})\.txt$", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    chapter_number: int
    filename: str
    text: str
    sha256: str
    character_count: int


def reference_diagnostic(db: Database, novel_id: str, start: int | None = None, end: int | None = None) -> dict[str, Any]:
    configured_start, configured_end = db.reference_range(novel_id)
    start = start if start is not None else configured_start if configured_start is not None else REFERENCE_START
    end = end if end is not None else configured_end if configured_end is not None else REFERENCE_END
    chapters = db.table("chapters")
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT chapter_number, title,
                CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END AS has_reference
            FROM {chapters}
            WHERE novel_id = ? AND chapter_number BETWEEN ? AND ?
            ORDER BY chapter_number
            """,
            (novel_id, start, end),
        ).fetchall()
        total = conn.execute(
            f"""
            SELECT SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS reference_count
            FROM {chapters}
            WHERE novel_id = ?
            """,
            (novel_id,),
        ).fetchone()["reference_count"]
    missing = [int(row["chapter_number"]) for row in rows if not row["has_reference"]]
    existing = [int(row["chapter_number"]) for row in rows if row["has_reference"]]
    return {
        "novel_id": novel_id,
        "target_mode": "reference",
        "range": {"start": start, "end": end},
        "rows_in_range": len(rows),
        "reference_rows_in_range": len(existing),
        "database_reference_count": int(total or 0),
        "missing_reference_chapters": missing,
        "missing_count": len(missing),
    }


def recovery_request(db: Database, novel_id: str, source_url: str = "", chapter_url_template: str = "") -> dict[str, Any]:
    novel = db.novel(novel_id) or {"title": novel_id}
    diagnostic = reference_diagnostic(db, novel_id)
    return {
        "format": "godtranslator-recovery-request-v1",
        "novel_id": novel_id,
        "novel_title": novel.get("title") or novel_id,
        "target_mode": "reference",
        "source_type": "novelfire",
        "source_url": source_url,
        "chapter_url_template": chapter_url_template,
        "chapters": diagnostic["missing_reference_chapters"],
    }


def parse_uploads(file_payloads: list[tuple[str, bytes]], novel_id: str, db: Database) -> dict[str, Any]:
    diagnostics = reference_diagnostic(db, novel_id)
    missing = set(diagnostics["missing_reference_chapters"])
    existing = set(range(diagnostics["range"]["start"], diagnostics["range"]["end"] + 1)) - missing
    candidates: list[Candidate] = []
    invalid_files: list[dict[str, str]] = []
    empty_files: list[str] = []
    ambiguous_files: list[dict[str, str]] = []
    duplicate_chapters: dict[str, list[str]] = {}
    files_found = 0

    for filename, data in file_payloads:
        if filename.lower().endswith(".zip"):
            if len(data) > MAX_ZIP_BYTES:
                invalid_files.append({"file": filename, "error": "ZIP is too large."})
                continue
            zip_candidates, zip_report = parse_zip(filename, data, novel_id)
            files_found += zip_report["files_found"]
            candidates.extend(zip_candidates)
            invalid_files.extend(zip_report["invalid_files"])
            empty_files.extend(zip_report["empty_files"])
            ambiguous_files.extend(zip_report["ambiguous_files"])
        else:
            files_found += 1
            item = parse_text_file(filename, data, None)
            collect_parse_result(item, candidates, invalid_files, empty_files, ambiguous_files)

    by_chapter: dict[int, list[Candidate]] = {}
    for item in candidates:
        by_chapter.setdefault(item.chapter_number, []).append(item)
    for chapter, items in by_chapter.items():
        if len(items) > 1:
            duplicate_chapters[str(chapter)] = [item.filename for item in items]

    valid_unique = [items[0] for chapter, items in sorted(by_chapter.items()) if len(items) == 1]
    recognized = [item.chapter_number for item in valid_unique]
    already_present = [item.chapter_number for item in valid_unique if item.chapter_number in existing]
    unexpected = [
        item.chapter_number
        for item in valid_unique
        if item.chapter_number < diagnostics["range"]["start"] or item.chapter_number > diagnostics["range"]["end"]
    ]
    would_import = [
        item.chapter_number
        for item in valid_unique
        if item.chapter_number in missing
    ]
    would_import_candidates = [item for item in valid_unique if item.chapter_number in set(would_import)]
    still_missing = sorted(missing - set(would_import))
    preview = {
        "ok": True,
        "novel_id": novel_id,
        "target_mode": "reference",
        "files_found": files_found,
        "recognized_chapters": recognized,
        "recognized_count": len(recognized),
        "missing_reference_targets": diagnostics["missing_reference_chapters"],
        "missing_targets_matched": would_import,
        "already_present_reference_chapters": already_present,
        "unexpected_chapters": unexpected,
        "duplicate_chapter_numbers": duplicate_chapters,
        "empty_files": empty_files,
        "invalid_files": invalid_files,
        "ambiguous_filenames": ambiguous_files,
        "chapters_that_would_be_imported": would_import,
        "would_import_count": len(would_import),
        "already_present_count": len(already_present),
        "still_missing_after_import": still_missing,
        "still_missing_count": len(still_missing),
    }
    job_id = db.create_import_job(novel_id, "reference", preview, would_import_candidates)
    preview["job_id"] = job_id
    return preview


def parse_zip(filename: str, data: bytes, novel_id: str) -> tuple[list[Candidate], dict[str, Any]]:
    candidates: list[Candidate] = []
    report: dict[str, Any] = {"files_found": 0, "invalid_files": [], "empty_files": [], "ambiguous_files": []}
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > MAX_UPLOAD_FILES:
                report["invalid_files"].append({"file": filename, "error": "ZIP contains too many files."})
                return candidates, report
            if sum(info.file_size for info in infos) > MAX_ZIP_UNCOMPRESSED_BYTES:
                report["invalid_files"].append({"file": filename, "error": "ZIP uncompressed size is too large."})
                return candidates, report
            try:
                manifest = load_pack_manifest(zf, novel_id)
            except Exception as exc:
                report["invalid_files"].append({"file": f"{filename}:manifest.json", "error": str(exc)})
                return candidates, report
            for info in infos:
                if not info.filename.lower().endswith(".txt"):
                    continue
                safe_name = safe_zip_name(info.filename)
                if safe_name is None:
                    report["invalid_files"].append({"file": info.filename, "error": "Unsafe ZIP path."})
                    continue
                if is_zip_symlink(info):
                    report["invalid_files"].append({"file": info.filename, "error": "ZIP symlink entries are not allowed."})
                    continue
                if info.file_size > MAX_TEXT_BYTES:
                    report["invalid_files"].append({"file": info.filename, "error": "Text file is too large."})
                    continue
                report["files_found"] += 1
                chapter_from_manifest = manifest.get(info.filename) or manifest.get(safe_name)
                result = parse_text_file(safe_name, zf.read(info), chapter_from_manifest)
                collect_parse_result(result, candidates, report["invalid_files"], report["empty_files"], report["ambiguous_files"])
    except zipfile.BadZipFile:
        report["invalid_files"].append({"file": filename, "error": "Invalid ZIP file."})
    return candidates, report


def load_pack_manifest(zf: zipfile.ZipFile, novel_id: str) -> dict[str, int]:
    try:
        raw = zf.read("manifest.json")
    except KeyError:
        return {}
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid manifest.json: {exc}") from exc
    if manifest.get("format") != "godtranslator-reference-pack-v1":
        raise ValueError("Unsupported manifest format.")
    if manifest.get("novel_id") != novel_id:
        raise ValueError("Manifest novel_id does not match.")
    if manifest.get("target_mode") != "reference":
        raise ValueError("Manifest target_mode must be reference.")
    mapping: dict[str, int] = {}
    chapters = manifest.get("chapters") or {}
    for chapter_text, meta in chapters.items():
        chapter = int(chapter_text)
        file_path = meta.get("file")
        if not file_path:
            raise ValueError(f"Manifest chapter {chapter} has no file.")
        safe_path = safe_zip_name(file_path)
        if safe_path is None:
            raise ValueError(f"Manifest chapter {chapter} has an unsafe file path.")
        try:
            data = zf.read(file_path)
        except KeyError as exc:
            raise ValueError(f"Manifest file not found for chapter {chapter}.") from exc
        sha = hashlib.sha256(data).hexdigest()
        if meta.get("sha256") and meta["sha256"] != sha:
            raise ValueError(f"Manifest SHA-256 mismatch for chapter {chapter}.")
        text = decode_text(data)
        if int(meta.get("character_count", len(text))) != len(text):
            raise ValueError(f"Manifest character count mismatch for chapter {chapter}.")
        mapping[file_path] = chapter
        mapping[safe_path] = chapter
    return mapping


def parse_text_file(filename: str, data: bytes, manifest_chapter: int | None) -> dict[str, Any]:
    if len(data) > MAX_TEXT_BYTES:
        return {"kind": "invalid", "file": filename, "error": "Text file is too large."}
    if b"\x00" in data[:4096]:
        return {"kind": "invalid", "file": filename, "error": "File appears to be binary, not UTF-8 text."}
    try:
        text = decode_text(data)
    except UnicodeDecodeError:
        return {"kind": "invalid", "file": filename, "error": "File is not valid UTF-8."}
    if not readable(text):
        return {"kind": "empty", "file": filename}
    try:
        chapter = detect_chapter_number(filename, manifest_chapter)
    except ValueError as exc:
        return {"kind": "ambiguous", "file": filename, "error": str(exc)}
    return {
        "kind": "candidate",
        "candidate": Candidate(
            chapter_number=chapter,
            filename=filename,
            text=text,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            character_count=len(text),
        ),
    }


def collect_parse_result(result: dict[str, Any], candidates: list[Candidate], invalid: list[dict[str, str]], empty: list[str], ambiguous: list[dict[str, str]]) -> None:
    kind = result["kind"]
    if kind == "candidate":
        candidates.append(result["candidate"])
    elif kind == "invalid":
        invalid.append({"file": result["file"], "error": result["error"]})
    elif kind == "empty":
        empty.append(result["file"])
    elif kind == "ambiguous":
        ambiguous.append({"file": result["file"], "error": result["error"]})


def detect_chapter_number(filename: str, manifest_chapter: int | None) -> int:
    name = Path(filename.replace("\\", "/")).name
    explicit = [int(a or b) for a, b in EXPLICIT_CHAPTER_RE.findall(name)]
    explicit = list(dict.fromkeys(explicit))
    simple = SIMPLE_NUMERIC_RE.fullmatch(name)
    simple_number = int(simple.group(1)) if simple else None
    if manifest_chapter:
        manifest_number = int(manifest_chapter)
        if explicit:
            if len(explicit) > 1:
                raise ValueError(f"Conflicting explicit chapter numbers: {explicit}")
            if explicit[0] != manifest_number:
                raise ValueError("Manifest chapter conflicts with explicit Chapter N in filename.")
        if simple_number and simple_number != manifest_number:
            raise ValueError("Manifest chapter conflicts with numeric filename.")
        return manifest_number
    if explicit:
        if len(explicit) > 1:
            raise ValueError(f"Conflicting explicit chapter numbers: {explicit}")
        return explicit[0]
    if simple_number:
        return simple_number
    numbers = re.findall(r"\d{1,6}", name)
    if numbers:
        raise ValueError("Ambiguous filename: numeric prefix or other number present without explicit Chapter N.")
    raise ValueError("No chapter number found.")


def decode_text(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.decode("utf-8")


def safe_zip_name(name: str) -> str | None:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
        return None
    if path.parts and (":" in path.parts[0] or path.parts[0].startswith("~")):
        return None
    return str(path)


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000
