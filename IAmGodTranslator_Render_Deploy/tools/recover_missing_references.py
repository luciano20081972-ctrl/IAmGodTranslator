from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database, readable, utc_now


CHAPTER_PATTERNS = (
    re.compile(r"(?:^|[/\\])0*(\d{1,5})\.txt$", re.IGNORECASE),
    re.compile(r"(?:chapter|chap|ch)[_\-\s]*0*(\d{1,5})", re.IGNORECASE),
    re.compile(r"第\s*0*(\d{1,5})\s*章"),
    re.compile(r"ç¬¬\s*0*(\d{1,5})\s*ç«\s*"),
)


@dataclass(frozen=True)
class CandidateFile:
    source: str
    chapter_number: int
    text: str


def parse_chapter_number(path: str) -> int | None:
    name = path.replace("\\", "/").split("/")[-1]
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group(1))
    return None


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def scan_inputs(paths: list[Path]) -> tuple[list[CandidateFile], dict[str, Any]]:
    report: dict[str, Any] = {
        "files_found": 0,
        "recognized_chapter_numbers": [],
        "empty_files": [],
        "unrecognized_files": [],
    }
    candidates: list[CandidateFile] = []
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*.txt")):
                add_file_candidate(child, child.read_bytes(), candidates, report)
        elif path.is_file() and path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as zf:
                for name in sorted(zf.namelist()):
                    if not name.lower().endswith(".txt") or name.endswith("/"):
                        continue
                    add_file_candidate(Path(f"{path}!{name}"), zf.read(name), candidates, report)
        elif path.is_file():
            add_file_candidate(path, path.read_bytes(), candidates, report)
        else:
            report["unrecognized_files"].append(str(path))
    report["recognized_chapter_numbers"] = sorted({item.chapter_number for item in candidates})
    return candidates, report


def add_file_candidate(path: Path, data: bytes, candidates: list[CandidateFile], report: dict[str, Any]) -> None:
    report["files_found"] += 1
    number = parse_chapter_number(str(path))
    if number is None:
        report["unrecognized_files"].append(str(path))
        return
    text = decode_text(data)
    if not readable(text):
        report["empty_files"].append(str(path))
        return
    candidates.append(CandidateFile(str(path), number, text))


def diagnose(db: Database, novel_id: str, start: int, end: int) -> dict[str, Any]:
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
        total_row = conn.execute(
            f"""
            SELECT SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS total
            FROM {chapters}
            WHERE novel_id = ?
            """,
            (novel_id,),
        ).fetchone()
    existing = [int(row["chapter_number"]) for row in rows if row["has_reference"]]
    missing = [int(row["chapter_number"]) for row in rows if not row["has_reference"]]
    return {
        "ok": True,
        "novel_id": novel_id,
        "range": {"start": start, "end": end},
        "rows_in_range": len(rows),
        "reference_rows_in_range": len(existing),
        "database_reference_count": int(total_row["total"] or 0),
        "missing_reference_chapters": missing,
        "missing_count": len(missing),
    }


def build_plan(db: Database, novel_id: str, start: int, end: int, candidates: list[CandidateFile], overwrite_existing: bool) -> dict[str, Any]:
    diagnostic = diagnose(db, novel_id, start, end)
    missing = set(diagnostic["missing_reference_chapters"])
    by_number: dict[int, list[CandidateFile]] = {}
    for item in candidates:
        by_number.setdefault(item.chapter_number, []).append(item)

    duplicates = {
        str(number): [item.source for item in items]
        for number, items in sorted(by_number.items())
        if len(items) > 1
    }
    matched_missing = sorted(number for number in by_number if number in missing)
    unexpected = sorted(number for number in by_number if number < start or number > end or number not in missing)
    would_insert = sorted(number for number in matched_missing if len(by_number[number]) == 1)
    would_overwrite = sorted(number for number in by_number if number not in missing and start <= number <= end and overwrite_existing and len(by_number[number]) == 1)
    skipped_duplicates = sorted(number for number in matched_missing if len(by_number[number]) > 1)
    return {
        **diagnostic,
        "recognized_chapter_numbers": sorted(by_number),
        "missing_target_chapters_matched": matched_missing,
        "unexpected_chapters": unexpected,
        "duplicates": duplicates,
        "chapters_that_would_be_inserted": would_insert,
        "chapters_that_would_be_overwritten": would_overwrite,
        "skipped_duplicate_target_chapters": skipped_duplicates,
        "overwrite_existing": overwrite_existing,
    }


def apply_plan(db: Database, novel_id: str, start: int, end: int, candidates: list[CandidateFile], overwrite_existing: bool) -> dict[str, Any]:
    plan = build_plan(db, novel_id, start, end, candidates, overwrite_existing)
    by_number = {item.chapter_number: item for item in candidates if len([other for other in candidates if other.chapter_number == item.chapter_number]) == 1}
    targets = list(plan["chapters_that_would_be_inserted"])
    if overwrite_existing:
        targets.extend(plan["chapters_that_would_be_overwritten"])

    chapters = db.table("chapters")
    applied: list[int] = []
    now = utc_now()
    with db.connect() as conn:
        for number in sorted(set(targets)):
            item = by_number[number]
            where_reference_guard = "" if overwrite_existing else "AND (reference_text IS NULL OR LENGTH(TRIM(reference_text)) = 0)"
            result = conn.execute(
                f"""
                UPDATE {chapters}
                SET reference_text = ?,
                    reference_char_count = ?,
                    updated_at = ?
                WHERE novel_id = ?
                  AND chapter_number = ?
                  AND chapter_number BETWEEN ? AND ?
                  {where_reference_guard}
                """,
                (item.text, len(item.text), now, novel_id, number, start, end),
            )
            if getattr(result, "rowcount", 0):
                applied.append(number)

    return {
        "ok": True,
        "mode": "apply",
        "applied_reference_chapters": applied,
        "applied_count": len(applied),
        "post_diagnostic": diagnose(db, novel_id, start, end),
        "plan": plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose and safely recover missing v10 Reference text.")
    parser.add_argument("--database-url", default=None, help="DATABASE_URL or sqlite:///path")
    parser.add_argument("--novel-id", default="i-am-god")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=434)
    parser.add_argument("--input", nargs="*", default=[], help="Reference source folder, ZIP, or .txt file paths")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite-existing", action="store_true", help="Explicitly allow overwriting existing non-empty Reference text.")
    args = parser.parse_args()

    selected = sum(bool(value) for value in (args.diagnose, args.dry_run, args.apply))
    if selected != 1:
        parser.error("Choose exactly one: --diagnose, --dry-run, or --apply")
    if (args.dry_run or args.apply) and not args.input:
        parser.error("--input is required for --dry-run and --apply")

    db = Database(args.database_url)
    if args.diagnose:
        print(json.dumps(diagnose(db, args.novel_id, args.start, args.end), ensure_ascii=False, indent=2))
        return 0

    candidates, scan_report = scan_inputs([Path(value) for value in args.input])
    plan = build_plan(db, args.novel_id, args.start, args.end, candidates, args.overwrite_existing)
    output = {"ok": True, "mode": "dry-run", "scan": scan_report, "plan": plan}
    if args.apply:
        output = {"scan": scan_report, **apply_plan(db, args.novel_id, args.start, args.end, candidates, args.overwrite_existing)}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
