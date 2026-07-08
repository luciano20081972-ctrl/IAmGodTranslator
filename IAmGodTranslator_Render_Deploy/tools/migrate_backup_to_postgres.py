from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database, clean_chapter_title, readable


CHAPTER_PATTERNS = (
    re.compile(r"(?:^|[/\\])0*(\d{1,5})\.txt$", re.IGNORECASE),
    re.compile(r"(?:chapter|chap|ch)[_\-\s]*0*(\d{1,5})", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,5})\s*章"),
    re.compile(r"ç¬¬\s*0*(\d{1,5})\s*ç«\s*"),
)

CATEGORY_HINTS = {
    "original": ("originals", "original", "chinese", "raw", "source", "cn", "zh"),
    "reference": ("references", "reference", "novelfire", "novel_fire", "ref"),
    "ai": ("ai_translations", "ai", "translated", "gpt", "openai", "machine", "translations"),
}


@dataclass
class TextFile:
    path: str
    text: str
    title: str | None


@dataclass
class ChapterBucket:
    original: list[TextFile] = field(default_factory=list)
    reference: list[TextFile] = field(default_factory=list)
    ai: list[TextFile] = field(default_factory=list)


def parse_chapter_number(path: str) -> int | None:
    name = path.replace("\\", "/").split("/")[-1]
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group(1))
    return None


def detect_category(path: str) -> str | None:
    parts = [part.lower() for part in path.replace("\\", "/").split("/")[:-1]]
    joined = "/".join(parts)
    scores = {
        category: sum(1 for hint in hints if hint in parts or f"/{hint}/" in f"/{joined}/")
        for category, hints in CATEGORY_HINTS.items()
    }
    if scores["reference"] > 0:
        return "reference"
    if scores["original"] > 0:
        return "original"
    if scores["ai"] > 0:
        return "ai"
    return None


def read_text(zf: zipfile.ZipFile, name: str) -> str:
    data = zf.read(name)
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def title_from_text(path: str, text: str, chapter_number: int) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return clean_chapter_title(chapter_number, stripped)
    return clean_chapter_title(chapter_number, Path(path).stem)


def choose_text(files: list[TextFile]) -> tuple[TextFile | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if not files:
        return None, [], []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    by_text: dict[str, list[str]] = defaultdict(list)
    for item in files:
        by_text[item.text].append(item.path)
    if len(files) > 1:
        for paths in by_text.values():
            if len(paths) > 1:
                duplicates.append({"paths": paths[:20], "count": len(paths)})
        if len(by_text) > 1:
            conflicts.append({"paths": [item.path for item in files[:20]], "variants": len(by_text)})
    return files[0], duplicates, conflicts


def scan_backup(path: Path, novel_id: str) -> dict[str, Any]:
    chapter_buckets: dict[int, ChapterBucket] = defaultdict(ChapterBucket)
    report: dict[str, Any] = {
        "novel_id": novel_id,
        "input": str(path),
        "recognized": {"original": 0, "reference": 0, "ai": 0},
        "unique_chapters": 0,
        "duplicates": {"original": [], "reference": [], "ai": []},
        "conflicts": {"original": [], "reference": [], "ai": []},
        "unrecognized_files": [],
        "empty_files": [],
        "ambiguous_files": [],
        "minimum_chapter": None,
        "maximum_chapter": None,
        "missing_chapter_numbers": [],
        "samples": {"original": [], "reference": [], "ai": []},
    }
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.lower().endswith(".txt"):
                continue
            category = detect_category(name)
            number = parse_chapter_number(name)
            if category is None or number is None:
                report["unrecognized_files"].append(name)
                continue
            text = read_text(zf, name)
            if not readable(text):
                report["empty_files"].append(name)
                continue
            bucket = chapter_buckets[number]
            getattr(bucket, category).append(TextFile(name, text, title_from_text(name, text, number)))
            report["recognized"][category] += 1
            if len(report["samples"][category]) < 8:
                report["samples"][category].append(name)

    normalized: dict[int, dict[str, Any]] = {}
    for number, bucket in sorted(chapter_buckets.items()):
        row: dict[str, Any] = {"chapter_number": number, "title": None, "original_text": None, "reference_text": None, "ai_text": None}
        for category, attr in (("original", "original_text"), ("reference", "reference_text"), ("ai", "ai_text")):
            chosen, duplicates, conflicts = choose_text(getattr(bucket, category))
            report["duplicates"][category].extend({"chapter_number": number, **item} for item in duplicates)
            report["conflicts"][category].extend({"chapter_number": number, **item} for item in conflicts)
            if chosen:
                row[attr] = chosen.text
                row["title"] = row["title"] or chosen.title
        normalized[number] = row

    numbers = sorted(normalized)
    report["unique_chapters"] = len(numbers)
    if numbers:
        report["minimum_chapter"] = numbers[0]
        report["maximum_chapter"] = numbers[-1]
        found = set(numbers)
        report["missing_chapter_numbers"] = [number for number in range(numbers[0], numbers[-1] + 1) if number not in found]
    report["normalized_rows"] = normalized
    report["counts"] = {
        "original": sum(1 for row in normalized.values() if readable(row["original_text"])),
        "reference": sum(1 for row in normalized.values() if readable(row["reference_text"])),
        "ai": sum(1 for row in normalized.values() if readable(row["ai_text"])),
        "needs_translation": sum(1 for row in normalized.values() if readable(row["original_text"]) and not readable(row["ai_text"])),
        "missing_original": sum(1 for row in normalized.values() if not readable(row["original_text"])),
    }
    report["missing_original_chapters"] = [number for number, row in normalized.items() if not readable(row["original_text"])]
    return report


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "normalized_rows"}


def apply_migration(report: dict[str, Any], database_url: str | None, title: str, model: str | None) -> dict[str, Any]:
    db = Database(database_url)
    db.initialize()
    db.upsert_novel(report["novel_id"], title=title, model=model, status="active")
    for row in report["normalized_rows"].values():
        db.upsert_chapter(
            report["novel_id"],
            int(row["chapter_number"]),
            row.get("title"),
            row.get("original_text"),
            row.get("reference_text"),
            row.get("ai_text"),
            ai_model=model if readable(row.get("ai_text")) else None,
        )
    return db.verification_counts(report["novel_id"])


def database_check(database_url: str | None, novel_id: str, require_postgres: bool = False) -> dict[str, Any]:
    db = Database(database_url)
    if require_postgres and db.config.backend != "postgres":
        raise RuntimeError("DATABASE_URL is required for live PostgreSQL validation.")
    db.ping()
    try:
        return db.precheck(novel_id)
    except Exception as exc:
        return {
            "database_reachable": True,
            "database_type": "postgresql" if db.config.backend == "postgres" else "sqlite",
            "schema": db.config.schema,
            "schema_ready": False,
            "error": exc.__class__.__name__,
            "message": "Database connection succeeded, but the v10 schema is not compatible or initialized.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a legacy GodTranslator backup ZIP into the v10 database.")
    parser.add_argument("--input", default=None, help="Path to backup ZIP")
    parser.add_argument("--novel-id", default="i-am-god")
    parser.add_argument("--title", default="I Am God")
    parser.add_argument("--database-url", default=None, help="DATABASE_URL or sqlite:///path for local QA")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-check", action="store_true", help="Check database reachability and current v10 row counts without importing.")
    parser.add_argument("--require-postgres", action="store_true", help="Fail instead of using SQLite when validating a live database.")
    parser.add_argument("--report", default=None, help="Optional JSON report path")
    args = parser.parse_args()

    modes = [args.dry_run, args.apply, args.database_check]
    if sum(1 for mode in modes if mode) != 1:
        parser.error("Choose exactly one: --dry-run, --apply, or --database-check")
    if args.database_check:
        try:
            output = database_check(args.database_url, args.novel_id, args.require_postgres)
            output["ok"] = bool(output.get("schema_ready", output.get("schema_initialized", False)))
        except Exception as exc:
            output = {"ok": False, "database_reachable": False, "error": exc.__class__.__name__, "message": "Database precheck failed. Verify DATABASE_URL and network access."}
        if args.report:
            Path(args.report).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get("ok") else 1
    if not args.input:
        parser.error("--input is required for --dry-run and --apply")
    backup = Path(args.input)
    if not backup.exists():
        raise SystemExit(f"Backup ZIP not found: {backup}")
    report = scan_backup(backup, args.novel_id)
    output = public_report(report)
    output["mode"] = "dry_run" if args.dry_run else "apply"
    if args.apply:
        output["database_verification"] = apply_migration(report, args.database_url, args.title, args.model)
    if args.report:
        Path(args.report).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
