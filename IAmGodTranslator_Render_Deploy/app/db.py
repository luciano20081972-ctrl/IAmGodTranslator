from __future__ import annotations

import os
import re
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def readable(value: str | None) -> bool:
    return bool(value and value.strip())


MAX_TITLE_LENGTH = 72
MAX_TITLE_WORDS = 10
CHAPTER_TITLE_RE = re.compile(r"^(?:chapter|chap|ch)\s*0*\d+\b|^第\s*0*\d+\s*章", re.IGNORECASE)


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    backend: str
    schema: str


class Database:
    def __init__(self, url: str | None = None) -> None:
        self.config = self._config(url)

    def _config(self, url: str | None) -> DatabaseConfig:
        value = (url or os.getenv("DATABASE_URL") or "").strip()
        schema = validate_identifier(os.getenv("DB_SCHEMA") or "godtranslator_v10")
        if value and not value.startswith("sqlite:///"):
            return DatabaseConfig(value, "postgres", schema)
        if value.startswith("sqlite:///"):
            return DatabaseConfig(value.removeprefix("sqlite:///"), "sqlite", schema)
        local = os.getenv("GT_SQLITE_PATH") or "data/godtranslator-v10.db"
        return DatabaseConfig(local, "sqlite", schema)

    def table(self, name: str) -> str:
        safe = validate_identifier(name)
        if self.config.backend == "postgres":
            return f'"{self.config.schema}"."{safe}"'
        return safe

    def index(self, name: str) -> str:
        return validate_identifier(name)

    def _convert_sql(self, sql: str) -> str:
        if self.config.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.config.backend == "postgres":
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(self.config.url, row_factory=dict_row)
            try:
                yield PostgresConnection(conn, self._convert_sql)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        path = Path(self.config.url)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            if self.config.backend == "postgres":
                conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.config.schema}"')
            execute_script(conn, self._schema_sql())

    def ping(self) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            return int(row["ok"] if not isinstance(row, tuple) else row[0]) == 1

    def _schema_sql(self) -> str:
        novels = self.table("novels")
        chapters = self.table("chapters")
        translation_jobs = self.table("translation_jobs")
        translation_job_items = self.table("translation_job_items")
        import_jobs = self.table("import_jobs")
        import_job_items = self.table("import_job_items")
        chapters_novel_chapter = self.index("chapters_novel_chapter")
        chapters_missing_ai = self.index("chapters_missing_ai")
        if self.config.backend == "postgres":
            id_type = "BIGSERIAL PRIMARY KEY"
            uuid_type = "UUID PRIMARY KEY"
            job_ref_type = "UUID"
            ts_type = "TIMESTAMPTZ"
            numeric_type = "NUMERIC"
        else:
            id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
            uuid_type = "TEXT PRIMARY KEY"
            job_ref_type = "TEXT"
            ts_type = "TEXT"
            numeric_type = "REAL"
        return f"""
        CREATE TABLE IF NOT EXISTS {novels} (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            model TEXT,
            status TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {chapters} (
            id {id_type},
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            title TEXT,
            original_text TEXT,
            reference_text TEXT,
            ai_text TEXT,
            original_char_count INTEGER NOT NULL DEFAULT 0,
            reference_char_count INTEGER NOT NULL DEFAULT 0,
            ai_char_count INTEGER NOT NULL DEFAULT 0,
            translation_status TEXT NOT NULL DEFAULT 'missing_original',
            translation_error TEXT,
            ai_model TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (novel_id, chapter_number)
        );

        CREATE INDEX IF NOT EXISTS {chapters_novel_chapter}
        ON {chapters}(novel_id, chapter_number);

        CREATE INDEX IF NOT EXISTS {chapters_missing_ai}
        ON {chapters}(novel_id, chapter_number)
        WHERE original_text IS NOT NULL
        AND LENGTH(TRIM(original_text)) > 0
        AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0);

        CREATE TABLE IF NOT EXISTS {translation_jobs} (
            id {uuid_type},
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            start_chapter INTEGER,
            end_chapter INTEGER,
            max_chapters INTEGER,
            total_items INTEGER NOT NULL DEFAULT 0,
            completed_items INTEGER NOT NULL DEFAULT 0,
            failed_items INTEGER NOT NULL DEFAULT 0,
            model TEXT,
            max_total_budget {numeric_type},
            max_per_chapter_budget {numeric_type},
            estimated_cost {numeric_type},
            actual_cost {numeric_type},
            created_at {ts_type} NOT NULL,
            started_at {ts_type},
            finished_at {ts_type},
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {translation_job_items} (
            id {id_type},
            job_id {job_ref_type} NOT NULL REFERENCES {translation_jobs}(id) ON DELETE CASCADE,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            status TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            estimated_cost {numeric_type},
            actual_cost {numeric_type},
            error TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (job_id, chapter_number)
        );

        CREATE TABLE IF NOT EXISTS {import_jobs} (
            id {uuid_type},
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            target_mode TEXT NOT NULL,
            status TEXT NOT NULL,
            preview_json TEXT NOT NULL,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {import_job_items} (
            id {id_type},
            job_id {job_ref_type} NOT NULL REFERENCES {import_jobs}(id) ON DELETE CASCADE,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            filename TEXT,
            sha256 TEXT,
            character_count INTEGER NOT NULL DEFAULT 0,
            content_text TEXT,
            status TEXT NOT NULL,
            error TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (job_id, chapter_number)
        );
        """

    def upsert_novel(self, novel_id: str, title: str, summary: str | None = None, model: str | None = None, status: str = "active") -> None:
        now = utc_now()
        novels = self.table("novels")
        with self.connect() as conn:
            if self.config.backend == "postgres":
                conn.execute(
                    f"""
                    INSERT INTO {novels} AS existing (id, title, summary, model, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = COALESCE(EXCLUDED.summary, existing.summary),
                        model = COALESCE(EXCLUDED.model, existing.model),
                        status = EXCLUDED.status,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (novel_id, title, summary, model, status, now, now),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO {novels} (id, title, summary, model, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        summary = COALESCE(excluded.summary, summary),
                        model = COALESCE(excluded.model, model),
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (novel_id, title, summary, model, status, now, now),
                )

    def upsert_chapter(self, novel_id: str, chapter_number: int, title: str | None, original_text: str | None, reference_text: str | None, ai_text: str | None, ai_model: str | None = None) -> None:
        now = utc_now()
        title = clean_chapter_title(chapter_number, title)
        status = chapter_status(original_text, ai_text)
        counts = (len(original_text or ""), len(reference_text or ""), len(ai_text or ""))
        chapters = self.table("chapters")
        with self.connect() as conn:
            if self.config.backend == "postgres":
                conn.execute(
                    f"""
                    INSERT INTO {chapters} AS target (
                        novel_id, chapter_number, title, original_text, reference_text, ai_text,
                        original_char_count, reference_char_count, ai_char_count,
                        translation_status, ai_model, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (novel_id, chapter_number) DO UPDATE SET
                        title = COALESCE(EXCLUDED.title, target.title),
                        original_text = COALESCE(EXCLUDED.original_text, target.original_text),
                        reference_text = COALESCE(EXCLUDED.reference_text, target.reference_text),
                        ai_text = COALESCE(EXCLUDED.ai_text, target.ai_text),
                        original_char_count = EXCLUDED.original_char_count,
                        reference_char_count = EXCLUDED.reference_char_count,
                        ai_char_count = EXCLUDED.ai_char_count,
                        translation_status = EXCLUDED.translation_status,
                        ai_model = COALESCE(EXCLUDED.ai_model, target.ai_model),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (novel_id, chapter_number, title, original_text, reference_text, ai_text, *counts, status, ai_model, now, now),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO {chapters} (
                        novel_id, chapter_number, title, original_text, reference_text, ai_text,
                        original_char_count, reference_char_count, ai_char_count,
                        translation_status, ai_model, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                        title = COALESCE(excluded.title, title),
                        original_text = COALESCE(excluded.original_text, original_text),
                        reference_text = COALESCE(excluded.reference_text, reference_text),
                        ai_text = COALESCE(excluded.ai_text, ai_text),
                        original_char_count = excluded.original_char_count,
                        reference_char_count = excluded.reference_char_count,
                        ai_char_count = excluded.ai_char_count,
                        translation_status = excluded.translation_status,
                        ai_model = COALESCE(excluded.ai_model, ai_model),
                        updated_at = excluded.updated_at
                    """,
                    (novel_id, chapter_number, title, original_text, reference_text, ai_text, *counts, status, ai_model, now, now),
                )

    def novels(self) -> list[dict[str, Any]]:
        novels = self.table("novels")
        chapters = self.table("chapters")
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT n.id, n.title, n.summary, n.model, n.status, n.created_at, n.updated_at,
                    COUNT(c.id) AS chapter_count,
                    SUM(CASE WHEN c.original_text IS NOT NULL AND LENGTH(TRIM(c.original_text)) > 0 THEN 1 ELSE 0 END) AS original_count,
                    SUM(CASE WHEN c.reference_text IS NOT NULL AND LENGTH(TRIM(c.reference_text)) > 0 THEN 1 ELSE 0 END) AS reference_count,
                    SUM(CASE WHEN c.ai_text IS NOT NULL AND LENGTH(TRIM(c.ai_text)) > 0 THEN 1 ELSE 0 END) AS ai_count
                FROM {novels} n
                LEFT JOIN {chapters} c ON c.novel_id = n.id
                GROUP BY n.id
                ORDER BY n.updated_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def novel(self, novel_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
            return dict(row) if row else None

    def library(self, novel_id: str, limit: int = 2000, offset: int = 0) -> dict[str, Any]:
        novel = self.novel(novel_id)
        if novel is None:
            return {"novel": None, "total": 0, "chapters": []}
        chapters = self.table("chapters")
        with self.connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) AS total FROM {chapters} WHERE novel_id = ?", (novel_id,)).fetchone()
            rows = conn.execute(
                f"""
                SELECT chapter_number, title, translation_status,
                    CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END AS has_original,
                    CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END AS has_reference,
                    CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END AS has_ai
                FROM {chapters}
                WHERE novel_id = ?
                ORDER BY chapter_number ASC
                LIMIT ? OFFSET ?
                """,
                (novel_id, limit, offset),
            ).fetchall()
        return {"novel": novel, "total": int(total_row["total"]), "chapters": [public_chapter_row(row) for row in rows]}

    def chapter_text(self, novel_id: str, chapter_number: int, mode: str) -> dict[str, Any]:
        column = {"original": "original_text", "reference": "reference_text", "ai": "ai_text"}[mode]
        with self.connect() as conn:
            row = conn.execute(f"SELECT chapter_number, title, {column} AS text FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?", (novel_id, chapter_number)).fetchone()
        if row is None:
            return {"ok": False, "status": "chapter_not_found", "message": "Chapter row does not exist.", "text": ""}
        text = row["text"]
        if not readable(text):
            status = {"original": "original_missing", "reference": "reference_missing", "ai": "ai_missing"}[mode]
            return {"ok": False, "status": status, "message": f"{mode.replace('_', ' ').title()} text is missing.", "chapter_number": chapter_number, "title": display_chapter_title(chapter_number, row["title"]), "text": ""}
        return {"ok": True, "status": "ok", "chapter_number": chapter_number, "title": display_chapter_title(chapter_number, row["title"]), "text": text}

    def verification_counts(self, novel_id: str) -> dict[str, int]:
        chapters = self.table("chapters")
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END) AS original,
                    SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS reference,
                    SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS ai,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0) THEN 1 ELSE 0 END) AS needs_translation
                FROM {chapters}
                WHERE novel_id = ?
                """,
                (novel_id,),
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("total", "original", "reference", "ai", "needs_translation")}

    def library_counts(self, novel_id: str) -> dict[str, int]:
        counts = self.verification_counts(novel_id)
        return {
            "total_chapter_rows": counts["total"],
            "original_readable": counts["original"],
            "reference_readable": counts["reference"],
            "ai_readable": counts["ai"],
            "needs_translation": counts["needs_translation"],
            "missing_original": max(0, counts["total"] - counts["original"]),
        }

    def create_import_job(self, novel_id: str, target_mode: str, preview: dict[str, Any], candidates: list[Any]) -> str:
        if target_mode != "reference":
            raise ValueError("Only reference import jobs are supported.")
        now = utc_now()
        job_id = str(uuid.uuid4())
        import_jobs = self.table("import_jobs")
        import_job_items = self.table("import_job_items")
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {import_jobs} (id, novel_id, target_mode, status, preview_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, novel_id, target_mode, "previewed", json.dumps(preview, ensure_ascii=False), now, now),
            )
            for item in candidates:
                conn.execute(
                    f"""
                    INSERT INTO {import_job_items} (
                        job_id, novel_id, chapter_number, filename, sha256, character_count,
                        content_text, status, error, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, chapter_number) DO UPDATE SET
                        filename = excluded.filename,
                        sha256 = excluded.sha256,
                        character_count = excluded.character_count,
                        content_text = excluded.content_text,
                        status = excluded.status,
                        error = excluded.error,
                        updated_at = excluded.updated_at
                    """,
                    (
                        job_id,
                        novel_id,
                        int(item.chapter_number),
                        item.filename,
                        item.sha256,
                        int(item.character_count),
                        item.text,
                        "would_import",
                        None,
                        now,
                        now,
                    ),
                )
        return job_id

    def import_job(self, job_id: str) -> dict[str, Any] | None:
        import_jobs = self.table("import_jobs")
        import_job_items = self.table("import_job_items")
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {import_jobs} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return None
            items = conn.execute(
                f"""
                SELECT chapter_number, filename, sha256, character_count, status, error
                FROM {import_job_items}
                WHERE job_id = ?
                ORDER BY chapter_number
                """,
                (job_id,),
            ).fetchall()
        payload = dict(job)
        payload["preview"] = json.loads(payload.pop("preview_json"))
        payload["items"] = [dict(item) for item in items]
        return payload

    def apply_import_job(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        import_jobs = self.table("import_jobs")
        import_job_items = self.table("import_job_items")
        chapters = self.table("chapters")
        imported: list[int] = []
        skipped: list[int] = []
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {import_jobs} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise ValueError("Import job not found.")
            if job["target_mode"] != "reference":
                raise ValueError("Only reference import jobs are supported.")
            items = conn.execute(
                f"""
                SELECT chapter_number, filename, character_count, content_text
                FROM {import_job_items}
                WHERE job_id = ? AND status IN ('would_import', 'imported', 'skipped_existing')
                ORDER BY chapter_number
                """,
                (job_id,),
            ).fetchall()
            for item in items:
                chapter_number = int(item["chapter_number"])
                cursor = conn.execute(
                    f"""
                    UPDATE {chapters}
                    SET reference_text = ?,
                        reference_char_count = ?,
                        updated_at = ?
                    WHERE novel_id = ?
                        AND chapter_number = ?
                        AND (reference_text IS NULL OR LENGTH(TRIM(reference_text)) = 0)
                    """,
                    (item["content_text"], int(item["character_count"] or 0), now, job["novel_id"], chapter_number),
                )
                if cursor.rowcount:
                    imported.append(chapter_number)
                    status = "imported"
                else:
                    skipped.append(chapter_number)
                    status = "skipped_existing"
                conn.execute(
                    f"""
                    UPDATE {import_job_items}
                    SET status = ?, updated_at = ?
                    WHERE job_id = ? AND chapter_number = ?
                    """,
                    (status, now, job_id, chapter_number),
                )
            conn.execute(
                f"""
                UPDATE {import_jobs}
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                ("imported", now, job_id),
            )
        return {
            "ok": True,
            "job_id": job_id,
            "novel_id": job["novel_id"],
            "target_mode": "reference",
            "imported_chapters": imported,
            "imported_count": len(imported),
            "skipped_existing_chapters": skipped,
            "skipped_existing_count": len(skipped),
        }

    def precheck(self, novel_id: str) -> dict[str, Any]:
        before = self.inspect_schema()
        self.initialize()
        after = self.inspect_schema()
        with self.connect() as conn:
            novel = conn.execute(f"SELECT 1 AS found FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
            count_row = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table('chapters')} WHERE novel_id = ?", (novel_id,)).fetchone()
        return {
            "database_reachable": True,
            "database_type": "postgresql" if self.config.backend == "postgres" else "sqlite",
            "schema": self.config.schema,
            "schema_ready": bool(after.get("v10_novels_table_exists") and after.get("v10_chapters_table_exists")),
            "schema_initialized": True,
            "backend": self.config.backend,
            "existing_novel_row": bool(novel),
            "existing_chapter_row_count": int(count_row["total"] or 0),
            "inspection_before": before,
            "inspection_after": after,
        }

    def inspect_schema(self) -> dict[str, Any]:
        if self.config.backend != "postgres":
            path = Path(self.config.url)
            exists = path.exists()
            if not exists:
                return {
                    "v10_schema_exists": False,
                    "v10_novels_table_exists": False,
                    "v10_chapters_table_exists": False,
                    "v10_chapter_count": 0,
                    "public_novels_table_exists": False,
                    "public_chapters_table_exists": False,
                    "public_table_count": 0,
                }
            with self.connect() as conn:
                rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                names = {row["name"] for row in rows}
                count = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table('chapters')}").fetchone()["total"] if "chapters" in names else 0
            return {
                "v10_schema_exists": True,
                "v10_novels_table_exists": "novels" in names,
                "v10_chapters_table_exists": "chapters" in names,
                "v10_chapter_count": int(count or 0),
                "public_novels_table_exists": False,
                "public_chapters_table_exists": False,
                "public_table_count": len(names),
            }

        with self.connect() as conn:
            schema = conn.execute("SELECT 1 AS found FROM information_schema.schemata WHERE schema_name = ?", (self.config.schema,)).fetchone()
            tables = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = ?
                """,
                (self.config.schema,),
            ).fetchall()
            table_names = {row["table_name"] for row in tables}
            public_tables = conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
            public_names = {row["table_name"] for row in public_tables}
            count = 0
            if "chapters" in table_names:
                count = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table('chapters')}").fetchone()["total"]
        return {
            "v10_schema_exists": bool(schema),
            "v10_novels_table_exists": "novels" in table_names,
            "v10_chapters_table_exists": "chapters" in table_names,
            "v10_chapter_count": int(count or 0),
            "public_novels_table_exists": "novels" in public_names,
            "public_chapters_table_exists": "chapters" in public_names,
            "public_table_count": len(public_names),
        }


class PostgresConnection:
    def __init__(self, conn: Any, converter: Any) -> None:
        self.conn = conn
        self.converter = converter

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self.conn.execute(self.converter(sql), params)

    def executescript(self, script: str) -> None:
        execute_script(self, script)


def execute_script(conn: Any, script: str) -> None:
    for statement in script.split(";"):
        sql = statement.strip()
        if sql:
            conn.execute(sql)


def chapter_status(original_text: str | None, ai_text: str | None) -> str:
    if not readable(original_text):
        return "missing_original"
    if readable(ai_text):
        return "translated"
    return "ready_to_translate"


def public_chapter_row(row: Any) -> dict[str, Any]:
    chapter_number = int(row["chapter_number"])
    return {
        "chapter_number": chapter_number,
        "title": display_chapter_title(chapter_number, row["title"]),
        "has_original": bool(row["has_original"]),
        "has_reference": bool(row["has_reference"]),
        "has_ai": bool(row["has_ai"]),
        "translation_status": row["translation_status"],
    }


def clean_chapter_title(chapter_number: int, value: str | None) -> str:
    candidate = normalize_title_text(value)
    if is_trustworthy_title(candidate):
        return candidate
    return f"Chapter {chapter_number}"


def display_chapter_title(chapter_number: int, value: str | None) -> str:
    return clean_chapter_title(chapter_number, value)


def normalize_title_text(value: str | None) -> str:
    if not value:
        return ""
    candidate = re.sub(r"\s+", " ", value.replace("\ufeff", " ")).strip()
    if candidate.lower().endswith(".txt"):
        candidate = candidate[:-4].strip()
    return candidate


def is_trustworthy_title(candidate: str) -> bool:
    if not candidate:
        return False
    if "\n" in candidate or "\r" in candidate:
        return False
    if len(candidate) > MAX_TITLE_LENGTH:
        return False
    words = candidate.split()
    if len(words) > MAX_TITLE_WORDS and not CHAPTER_TITLE_RE.search(candidate):
        return False
    if len(words) > 7 and re.search(r"[.!?。！？…]$", candidate) and not CHAPTER_TITLE_RE.search(candidate):
        return False
    return True


def validate_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError("Invalid database schema or table identifier.")
    return value
