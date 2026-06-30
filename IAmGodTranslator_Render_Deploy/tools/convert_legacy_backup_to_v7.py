from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EXCLUDED_PARTS = {
    ".env",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "logs",
    "log",
    "sessions",
    "session",
    "cookies",
    "cookie",
    "backup_jobs",
    "runtime",
}
EXCLUDED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pyo"}
SECRET_PATTERNS = (
    re.compile(rb"sk-proj-[A-Za-z0-9_-]+"),
    re.compile(rb"OPENAI_API_KEY\s*=\s*sk-[A-Za-z0-9_-]+"),
    re.compile(rb"SUPABASE_SERVICE_ROLE_KEY\s*=\s*eyJ[A-Za-z0-9_-]+"),
    re.compile(rb"postgres(?:ql)?://[^\s:@]+:[^\s@]+@"),
)


@dataclass
class Candidate:
    source: str
    category: str
    chapter: int | None
    output_path: str | None
    warning: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def path_parts(path: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", path.lower()) if part]


def unsafe_or_excluded(path: str) -> str | None:
    normalized = normalize_path(path)
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        return "unsafe path"
    lower_parts = {part.lower() for part in parts}
    if lower_parts & EXCLUDED_PARTS:
        return "excluded runtime/secret path"
    suffix = Path(parts[-1]).suffix.lower()
    if suffix in EXCLUDED_SUFFIXES:
        return "excluded file type"
    if suffix and suffix != ".txt" and not is_cover_path(normalized) and not is_settings_path(normalized):
        return "unsupported file type"
    return None


def is_cover_path(path: str) -> bool:
    lower = path.lower()
    return "/cover" in f"/{lower}" and Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}


def is_settings_path(path: str) -> bool:
    lower = path.lower()
    return "settings" in lower and Path(path).suffix.lower() in {".json", ".txt"}


def detect_chapter(path: str) -> int | None:
    stem = Path(path).stem.lower()
    patterns = (
        r"^(?:0*)(\d{1,6})$",
        r"^chapter[_\-\s]*(\d{1,6})$",
        r"^ch[_\-\s]*(\d{1,6})$",
        r"^第\s*(\d{1,6})\s*章$",
        r".*?第\s*(\d{1,6})\s*章.*",
        r".*?chapter[_\-\s]*(\d{1,6}).*",
        r".*?ch[_\-\s]*(\d{1,6}).*",
    )
    for pattern in patterns:
        match = re.match(pattern, stem, re.IGNORECASE)
        if match:
            number = int(match.group(1))
            return number if number > 0 else None
    return None


def is_large_numeric_stem(path: str) -> bool:
    stem = Path(path).stem
    return bool(re.fullmatch(r"\d{7,}", stem))


def classify(path: str) -> tuple[str | None, str | None]:
    lower = normalize_path(path).lower()
    tokens = set(path_parts(lower))
    joined = "/" + lower

    if "prompt" in tokens or "prompts" in tokens:
        return "prompts", None
    if is_cover_path(path):
        return "covers", None
    if is_settings_path(path):
        return "settings", None

    original = bool(tokens & {"originals", "original", "chinese", "raw", "source", "cn", "zh"}) or "/data/novels/i-am-god/originals/" in joined
    reference = bool(tokens & {"references", "reference", "novelfire", "novel", "fire", "ref"}) or "/data/novels/i-am-god/references/" in joined or "novel_fire" in lower
    ai_strong = bool(tokens & {"ai", "gpt", "openai", "machine"}) or "/ai_translations/" in joined or "translated-chapters" in lower or "ai-translations" in lower
    generic_translation = bool(tokens & {"translations", "translation", "translated"}) or "/data/translations/" in joined

    strong = [name for name, present in (("originals", original), ("references", reference), ("ai_translations", ai_strong)) if present]
    if len(strong) > 1:
        return None, f"ambiguous category signals: {', '.join(strong)}"
    if strong:
        return strong[0], None
    if generic_translation:
        return "ai_translations", "Generic translations folder mapped to AI translations because legacy app used translations for AI."
    return None, "no reliable category signal"


def read_file_safely(archive: zipfile.ZipFile, member: zipfile.ZipInfo, max_bytes: int = 20_000_000) -> bytes | None:
    if member.file_size > max_bytes:
        return None
    data = archive.read(member)
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        return None
    return data


def analyze(input_path: Path, novel_id: str) -> dict[str, Any]:
    candidates: list[Candidate] = []
    skipped: list[dict[str, str]] = []
    ambiguous: list[dict[str, str]] = []
    unknown: list[str] = []
    warnings: list[str] = []

    with zipfile.ZipFile(input_path) as archive:
        for member in archive.infolist():
            source = normalize_path(member.filename)
            if member.is_dir():
                continue
            reason = unsafe_or_excluded(source)
            if reason:
                skipped.append({"path": source, "reason": reason})
                continue
            category, warning = classify(source)
            if category is None:
                ambiguous.append({"path": source, "reason": warning or "uncertain"})
                continue
            if warning and warning not in warnings:
                warnings.append(warning)
            if category in {"covers", "settings"}:
                out = f"{category}/{Path(source).name}" if category == "settings" else f"covers/{novel_id}/{Path(source).name}"
                candidates.append(Candidate(source, category, None, out, warning))
                continue
            chapter = detect_chapter(source)
            candidates.append(Candidate(source, category, chapter, None, warning))

    assign_sequence_chapters(candidates, warnings)

    for candidate in candidates:
        if candidate.category in {"covers", "settings"}:
            continue
        if candidate.chapter is None:
            skipped.append({"path": candidate.source, "reason": "chapter number could not be detected safely"})
            candidate.output_path = None
            continue
        candidate.output_path = f"novels/{novel_id}/{candidate.category}/{candidate.chapter:04d}.txt"

    dedupe_candidates(candidates, skipped, warnings)
    counts = count_categories(candidates)
    samples = sample_categories(candidates)
    unknown = [item["path"] for item in ambiguous if item["reason"] == "no reliable category signal"]
    return {
        "source_backup": str(input_path),
        "created_at": utc_now(),
        "counts": counts,
        "samples": samples,
        "unknown_total": len(unknown),
        "ambiguous_total": len(ambiguous),
        "skipped_total": len(skipped),
        "unknown_files": unknown[:500],
        "ambiguous_files": ambiguous[:500],
        "skipped_files": skipped[:500],
        "warnings": warnings,
        "candidates": [candidate.__dict__ for candidate in candidates if candidate.output_path],
    }


def assign_sequence_chapters(candidates: list[Candidate], warnings: list[str]) -> None:
    for category in ("originals", "references", "ai_translations", "prompts"):
        group = [item for item in candidates if item.category == category and item.chapter is None]
        if not group:
            continue
        if all(is_large_numeric_stem(item.source) for item in group):
            for index, item in enumerate(sorted(group, key=lambda candidate: candidate.source), start=1):
                item.chapter = index
            warnings.append(f"Large numeric filenames in {category} were sequence-mapped from sorted order.")


def dedupe_candidates(candidates: list[Candidate], skipped: list[dict[str, str]], warnings: list[str]) -> None:
    seen: dict[str, Candidate] = {}
    for candidate in candidates:
        if not candidate.output_path:
            continue
        existing = seen.get(candidate.output_path)
        if existing is None:
            seen[candidate.output_path] = candidate
            continue
        skipped.append({"path": candidate.source, "reason": f"duplicate output path {candidate.output_path}; kept {existing.source}"})
        candidate.output_path = None
    if any("duplicate output path" in item["reason"] for item in skipped):
        warnings.append("Duplicate chapter outputs were skipped; first detected file was kept.")


def count_categories(candidates: list[Candidate]) -> dict[str, int]:
    counts = {"originals": 0, "references": 0, "ai_translations": 0, "prompts": 0, "covers": 0, "settings": 0}
    for candidate in candidates:
        if candidate.output_path:
            counts[candidate.category] = counts.get(candidate.category, 0) + 1
    return counts


def sample_categories(candidates: list[Candidate]) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {key: [] for key in ("originals", "references", "ai_translations", "prompts", "covers", "settings")}
    for candidate in candidates:
        if candidate.output_path and len(samples[candidate.category]) < 12:
            samples[candidate.category].append(candidate.source)
    return samples


def manifest(report: dict[str, Any], novel_id: str, title: str, source_filename: str) -> dict[str, Any]:
    return {
        "app": "GodTranslator",
        "backup_version": "v7",
        "created_at": utc_now(),
        "novel_id": novel_id,
        "title": title,
        "schema_version": 1,
        "path_mapping": {
            "originals": "novels/{novel_id}/originals/{chapter}.txt",
            "references": "novels/{novel_id}/references/{chapter}.txt",
            "ai_translations": "novels/{novel_id}/ai_translations/{chapter}.txt",
            "prompts": "novels/{novel_id}/prompts/{chapter}.txt",
        },
        "counts": report["counts"],
        "source_backup_filename": source_filename,
        "warnings": report["warnings"],
        "no_secrets": True,
        "files": [],
    }


def write_reports(report: dict[str, Any], output_path: Path, restore_command: str) -> None:
    json_path = output_path.with_name("legacy_conversion_report.json")
    md_path = output_path.with_name("legacy_conversion_report.md")
    safe_report = {key: value for key, value in report.items() if key != "candidates"}
    safe_report["restore_command"] = restore_command
    json_path.write_text(json.dumps(safe_report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Legacy Backup Conversion Report",
        "",
        f"- Source: `{report['source_backup']}`",
        f"- Created: `{report['created_at']}`",
        "",
        "## Counts",
        "",
    ]
    for key, value in report["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {warning}" for warning in report["warnings"]] or ["- None"])
    lines.extend(["", "## Samples", ""])
    for category, paths in report["samples"].items():
        lines.append(f"### {category}")
        lines.extend([f"- `{path}`" for path in paths] or ["- None"])
    lines.extend(["", "## Skipped / Ambiguous", ""])
    lines.append(f"- Unknown files: {report.get('unknown_total', len(report['unknown_files']))}")
    lines.append(f"- Ambiguous files: {report.get('ambiguous_total', len(report['ambiguous_files']))}")
    lines.append(f"- Skipped files: {report.get('skipped_total', len(report['skipped_files']))}")
    lines.extend(["", "## Restore", "", "Use the website Admin -> Backups restore flow. Run dry-run first, then confirm restore.", "", "CLI reference:", "", f"```powershell\n{restore_command}\n```"])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def write_v7_zip(input_path: Path, output_path: Path, report: dict[str, Any], novel_id: str, title: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()
    man = manifest(report, novel_id, title, input_path.name)
    candidates = [Candidate(**item) for item in report["candidates"]]

    with zipfile.ZipFile(input_path) as source_zip, zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        backup_info = {"created_at": utc_now(), "source_backup_filename": input_path.name, "note": "Converted legacy backup. No secrets, sessions, database files, or logs are included."}
        output_zip.writestr("backup_info.json", json.dumps(backup_info, indent=2, ensure_ascii=False))
        index = [{"novel_id": novel_id, "title": title}]
        output_zip.writestr("novels/index.json", json.dumps(index, indent=2, ensure_ascii=False))
        metadata = {"novel_id": novel_id, "title": title, "summary": "", "tags": [], "created_at": utc_now(), "updated_at": utc_now(), "source_language": "Chinese", "target_language": "English", "settings": {"model": "gpt-4o-mini"}}
        output_zip.writestr(f"novels/{novel_id}/metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))

        for candidate in candidates:
            member = get_zipinfo(source_zip, candidate.source)
            data = read_file_safely(source_zip, member)
            if data is None or candidate.output_path is None:
                continue
            output_zip.writestr(candidate.output_path, data)
            man["files"].append({"path": candidate.output_path, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        output_zip.writestr("manifest.json", json.dumps(man, indent=2, ensure_ascii=False))
    temp_path.replace(output_path)


def get_zipinfo(archive: zipfile.ZipFile, normalized_name: str) -> zipfile.ZipInfo:
    try:
        return archive.getinfo(normalized_name)
    except KeyError:
        for member in archive.infolist():
            if normalize_path(member.filename) == normalized_name:
                return member
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a legacy GodTranslator backup ZIP to a v7 manifest backup ZIP.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--novel-id", required=True)
    parser.add_argument("--title", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        print(f"Input backup not found: {args.input}", file=sys.stderr)
        return 2
    report = analyze(args.input, args.novel_id)
    restore_command = f'Upload "{args.output}" in Admin -> Backups -> Restore Full Backup ZIP. Run dry-run first, then confirm restore.'
    write_reports(report, args.output, restore_command)
    if args.write:
        write_v7_zip(args.input, args.output, report, args.novel_id, args.title)
        print(f"Wrote v7 backup: {args.output}")
    else:
        print("Dry-run complete. No v7 backup ZIP was written.")
    print(json.dumps({"counts": report["counts"], "warnings": report["warnings"], "unknown": report["unknown_total"], "ambiguous": report["ambiguous_total"], "skipped": report["skipped_total"]}, indent=2, ensure_ascii=False))
    print(f"Report JSON: {args.output.with_name('legacy_conversion_report.json')}")
    print(f"Report MD: {args.output.with_name('legacy_conversion_report.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
