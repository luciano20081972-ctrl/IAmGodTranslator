from __future__ import annotations

import json
import os
import re
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
            self._apply_additive_migrations(conn)

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

    def _apply_additive_migrations(self, conn: Any) -> None:
        novel_columns = {
            "author": "TEXT",
            "cover_url": "TEXT",
            "source_url": "TEXT",
            "reference_source_url": "TEXT",
            "reference_target_start": "INTEGER",
            "reference_target_end": "INTEGER",
            "metadata_json": "TEXT",
            "is_archived": "INTEGER NOT NULL DEFAULT 0",
        }
        chapter_columns = {
            "translated_at": "TEXT",
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "actual_cost": "REAL",
        }
        job_columns = {
            "current_chapter": "INTEGER",
            "error": "TEXT",
            "settings_json": "TEXT",
        }
        item_columns = {
            "model": "TEXT",
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "started_at": "TEXT",
            "finished_at": "TEXT",
        }
        for table, columns in (
            ("novels", novel_columns),
            ("chapters", chapter_columns),
            ("translation_jobs", job_columns),
            ("translation_job_items", item_columns),
        ):
            existing = self.columns(conn, table)
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {self.table(table)} ADD COLUMN {column} {definition}")

    def columns(self, conn: Any, table: str) -> set[str]:
        if self.config.backend == "postgres":
            rows = conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = ? AND table_name = ?
                """,
                (self.config.schema, table),
            ).fetchall()
            return {row["column_name"] for row in rows}
        rows = conn.execute(f"PRAGMA table_info({self.table(table)})").fetchall()
        return {row["name"] for row in rows}

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

    def save_novel_metadata(self, novel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        title = (payload.get("title") or novel_id).strip()
        status = (payload.get("status") or "active").strip()
        metadata = payload.get("metadata")
        metadata_json = json.dumps(metadata if isinstance(metadata, dict) else {}, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table('novels')} (
                    id, title, summary, model, status, author, cover_url, source_url,
                    reference_source_url, reference_target_start, reference_target_end,
                    metadata_json, is_archived, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    summary = excluded.summary,
                    model = excluded.model,
                    status = excluded.status,
                    author = excluded.author,
                    cover_url = excluded.cover_url,
                    source_url = excluded.source_url,
                    reference_source_url = excluded.reference_source_url,
                    reference_target_start = excluded.reference_target_start,
                    reference_target_end = excluded.reference_target_end,
                    metadata_json = excluded.metadata_json,
                    is_archived = excluded.is_archived,
                    updated_at = excluded.updated_at
                """,
                (
                    novel_id,
                    title,
                    payload.get("summary"),
                    payload.get("model") or "gpt-4o-mini",
                    status,
                    payload.get("author"),
                    payload.get("cover_url"),
                    payload.get("source_url"),
                    payload.get("reference_source_url"),
                    optional_int(payload.get("reference_target_start")),
                    optional_int(payload.get("reference_target_end")),
                    metadata_json,
                    1 if payload.get("is_archived") else 0,
                    now,
                    now,
                ),
            )
        return self.novel(novel_id) or {}

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
                    n.author, n.cover_url, n.source_url, n.reference_source_url,
                    n.reference_target_start, n.reference_target_end,
                    n.metadata_json, n.is_archived,
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
            return [public_novel_row(row) for row in rows]

    def novel(self, novel_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
            return public_novel_row(row) if row else None

    def archive_novel(self, novel_id: str, archived: bool) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('novels')} SET is_archived = ?, status = ?, updated_at = ? WHERE id = ?",
                (1 if archived else 0, "archived" if archived else "active", utc_now(), novel_id),
            )
        return self.novel(novel_id) or {}

    def reference_range(self, novel_id: str) -> tuple[int | None, int | None]:
        novel = self.novel(novel_id) or {}
        start = optional_int(novel.get("reference_target_start"))
        end = optional_int(novel.get("reference_target_end"))
        if start is None or end is None:
            metadata = novel.get("metadata") if isinstance(novel.get("metadata"), dict) else {}
            start = start if start is not None else optional_int(metadata.get("reference_target_start"))
            end = end if end is not None else optional_int(metadata.get("reference_target_end"))
        if (start is None or end is None) and novel_id == "i-am-god":
            start = 1
            end = 434
        if start is not None and end is not None and start > end:
            start, end = end, start
        return start, end

    def library(self, novel_id: str, limit: int = 2000, offset: int = 0, search: str = "", view: str = "all") -> dict[str, Any]:
        novel = self.novel(novel_id)
        if novel is None:
            return {"novel": None, "total": 0, "chapters": []}
        chapters = self.table("chapters")
        where = ["novel_id = ?"]
        params: list[Any] = [novel_id]
        if search:
            where.append("(CAST(chapter_number AS TEXT) LIKE ? OR LOWER(COALESCE(title, '')) LIKE ?)")
            term = f"%{search.lower()}%"
            params.extend([term, term])
        filters = {
            "translated": "ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0",
            "needs": "original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0)",
            "missing-original": "(original_text IS NULL OR LENGTH(TRIM(original_text)) = 0)",
            "missing-reference": "(reference_text IS NULL OR LENGTH(TRIM(reference_text)) = 0)",
            "errors": "translation_status = 'failed' OR (translation_error IS NOT NULL AND LENGTH(TRIM(translation_error)) > 0)",
        }
        if view in filters:
            where.append(filters[view])
        where_sql = " AND ".join(where)
        with self.connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) AS total FROM {chapters} WHERE {where_sql}", tuple(params)).fetchone()
            rows = conn.execute(
                f"""
                SELECT chapter_number, title, translation_status, translation_error,
                    CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END AS has_original,
                    CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END AS has_reference,
                    CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END AS has_ai
                FROM {chapters}
                WHERE {where_sql}
                ORDER BY chapter_number ASC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
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

    def translation_candidates(self, novel_id: str, chapters: list[int], only_untranslated: bool = True, require_original: bool = True) -> list[dict[str, Any]]:
        if not chapters:
            return []
        placeholders = ",".join("?" for _ in chapters)
        rows_out: list[dict[str, Any]] = []
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number, title,
                    original_text, reference_text, ai_text,
                    original_char_count, reference_char_count, ai_char_count
                FROM {self.table('chapters')}
                WHERE novel_id = ? AND chapter_number IN ({placeholders})
                ORDER BY chapter_number
                """,
                tuple([novel_id] + chapters),
            ).fetchall()
        for row in rows:
            has_original = readable(row["original_text"])
            has_ai = readable(row["ai_text"])
            eligible = (has_original or not require_original) and (not has_ai or not only_untranslated)
            reason = ""
            if require_original and not has_original:
                reason = "missing_original"
            elif only_untranslated and has_ai:
                reason = "already_translated"
            rows_out.append({
                "chapter_number": int(row["chapter_number"]),
                "title": display_chapter_title(int(row["chapter_number"]), row["title"]),
                "has_original": has_original,
                "has_reference": readable(row["reference_text"]),
                "has_ai": has_ai,
                "original_chars": len(row["original_text"] or ""),
                "reference_chars": len(row["reference_text"] or ""),
                "ai_chars": len(row["ai_text"] or ""),
                "eligible": eligible,
                "skip_reason": reason,
            })
        return rows_out

    def all_untranslated_chapters(self, novel_id: str, limit: int = 5000) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                    AND original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0
                    AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0)
                ORDER BY chapter_number
                LIMIT ?
                """,
                (novel_id, limit),
            ).fetchall()
        return [int(row["chapter_number"]) for row in rows]

    def estimate_translation(self, novel_id: str, chapters: list[int], settings: dict[str, Any]) -> dict[str, Any]:
        rows = self.translation_candidates(
            novel_id,
            chapters,
            only_untranslated=bool(settings.get("only_untranslated", True)),
            require_original=True,
        )
        use_reference = bool(settings.get("use_reference", True))
        model = settings.get("model") or (self.novel(novel_id) or {}).get("model") or "gpt-4o-mini"
        pricing = model_pricing(model)
        eligible = [row for row in rows if row["eligible"]]
        input_chars = sum(row["original_chars"] + (row["reference_chars"] if use_reference and row["has_reference"] else 0) for row in eligible)
        input_tokens = max(1, input_chars // 4) if eligible else 0
        output_tokens = max(1, sum(row["original_chars"] for row in eligible) // 5) if eligible else 0
        estimated_cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
        return {
            "ok": True,
            "novel_id": novel_id,
            "model": model,
            "pricing_note": pricing["note"],
            "selected_count": len(chapters),
            "eligible_count": len(eligible),
            "skipped_count": len(rows) - len(eligible),
            "original_readable": sum(1 for row in rows if row["has_original"]),
            "reference_available": sum(1 for row in rows if row["has_reference"]),
            "ai_existing": sum(1 for row in rows if row["has_ai"]),
            "approx_input_tokens": input_tokens,
            "approx_output_tokens": output_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "items": rows,
        }

    def create_translation_job(self, novel_id: str, chapters: list[int], settings: dict[str, Any]) -> dict[str, Any]:
        estimate = self.estimate_translation(novel_id, chapters, settings)
        eligible = [row for row in estimate["items"] if row["eligible"]]
        batch_size = int(settings.get("batch_size") or len(eligible) or 0)
        if batch_size > 0:
            eligible = eligible[:batch_size]
        now = utc_now()
        job_id = str(uuid.uuid4())
        model = estimate["model"]
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table('translation_jobs')} (
                    id, novel_id, status, start_chapter, end_chapter, max_chapters,
                    total_items, completed_items, failed_items, model, max_total_budget,
                    max_per_chapter_budget, estimated_cost, actual_cost, settings_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    novel_id,
                    "queued",
                    min(chapters) if chapters else None,
                    max(chapters) if chapters else None,
                    batch_size,
                    len(eligible),
                    model,
                    settings.get("max_total_budget"),
                    settings.get("max_per_chapter_budget"),
                    estimate["estimated_cost"],
                    json.dumps(settings, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            for row in eligible:
                conn.execute(
                    f"""
                    INSERT INTO {self.table('translation_job_items')} (
                        job_id, novel_id, chapter_number, status, attempts,
                        estimated_cost, model, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                    ON CONFLICT(job_id, chapter_number) DO NOTHING
                    """,
                    (job_id, novel_id, row["chapter_number"], estimate["estimated_cost"] / max(1, len(eligible)), model, now, now),
                )
        return self.translation_job(job_id) or {"id": job_id}

    def translation_jobs(self, novel_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if novel_id:
            where = "WHERE novel_id = ?"
            params.append(novel_id)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM {self.table('translation_jobs')}
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [public_job_row(row) for row in rows]

    def translation_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return None
            items = conn.execute(
                f"""
                SELECT chapter_number, status, attempts, estimated_cost, actual_cost, error, model,
                    input_tokens, output_tokens, started_at, finished_at
                FROM {self.table('translation_job_items')}
                WHERE job_id = ?
                ORDER BY chapter_number
                LIMIT 500
                """,
                (job_id,),
            ).fetchall()
        payload = public_job_row(job)
        payload["items"] = [dict(row) for row in items]
        return payload

    def set_job_status(self, job_id: str, status: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('translation_jobs')} SET status = ?, updated_at = ?, finished_at = CASE WHEN ? IN ('completed','failed','cancelled') THEN ? ELSE finished_at END WHERE id = ?",
                (status, now, status, now, job_id),
            )
        return self.translation_job(job_id) or {}

    def retry_failed_items(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('translation_job_items')} SET status = 'pending', error = NULL, updated_at = ? WHERE job_id = ? AND status = 'failed'",
                (utc_now(), job_id),
            )
            conn.execute(f"UPDATE {self.table('translation_jobs')} SET status = 'queued', updated_at = ? WHERE id = ?", (utc_now(), job_id))
        return self.translation_job(job_id) or {}

    def run_next_translation_item(self, job_id: str, translator: Any) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                raise ValueError("Translation job not found.")
            if job["status"] in {"paused", "cancelled", "completed"}:
                return {"ok": True, "status": job["status"], "message": "Job is not runnable."}
            settings = json.loads(job["settings_json"] or "{}") if job["settings_json"] else {}
            stop_on_budget = bool(settings.get("stop_on_budget", True))
            max_total_budget = job["max_total_budget"]
            if stop_on_budget and max_total_budget is not None and float(job["actual_cost"] or 0) >= float(max_total_budget):
                conn.execute(
                    f"UPDATE {self.table('translation_jobs')} SET status = 'paused', error = 'budget_reached', updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
                updated_job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
                items = conn.execute(
                    f"SELECT chapter_number, status, attempts, estimated_cost, actual_cost, error, model, input_tokens, output_tokens, started_at, finished_at FROM {self.table('translation_job_items')} WHERE job_id = ? ORDER BY chapter_number LIMIT 500",
                    (job_id,),
                ).fetchall()
                payload = public_job_row(updated_job)
                payload["items"] = [dict(row) for row in items]
                return payload
            item = conn.execute(
                f"""
                SELECT *
                FROM {self.table('translation_job_items')}
                WHERE job_id = ? AND status IN ('pending', 'failed')
                ORDER BY chapter_number
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
            if item is None:
                conn.execute(f"UPDATE {self.table('translation_jobs')} SET status = 'completed', finished_at = ?, updated_at = ? WHERE id = ?", (now, now, job_id))
                return {"ok": True, "status": "completed", "message": "No pending items."}
            chapter = conn.execute(
                f"SELECT * FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?",
                (job["novel_id"], item["chapter_number"]),
            ).fetchone()
            conn.execute(
                f"UPDATE {self.table('translation_jobs')} SET status = 'running', started_at = COALESCE(started_at, ?), current_chapter = ?, updated_at = ? WHERE id = ?",
                (now, item["chapter_number"], now, job_id),
            )
            conn.execute(
                f"UPDATE {self.table('translation_job_items')} SET status = 'running', attempts = attempts + 1, started_at = ?, updated_at = ? WHERE id = ?",
                (now, now, item["id"]),
            )
            max_per_chapter_budget = job["max_per_chapter_budget"]
            if max_per_chapter_budget is not None and float(item["estimated_cost"] or 0) > float(max_per_chapter_budget):
                conn.execute(
                    f"UPDATE {self.table('translation_job_items')} SET status = 'skipped', error = 'max_per_chapter_budget_exceeded', finished_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, item["id"]),
                )
            elif chapter is None or not readable(chapter["original_text"]):
                conn.execute(
                    f"UPDATE {self.table('translation_job_items')} SET status = 'skipped', error = 'missing_original', finished_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, item["id"]),
                )
            else:
                use_reference = bool(settings.get("use_reference", True))
                result = translator(chapter["original_text"], chapter["reference_text"] if use_reference else None, settings)
                text = result["text"] if isinstance(result, dict) else str(result)
                input_tokens = int(result.get("input_tokens", 0)) if isinstance(result, dict) else 0
                output_tokens = int(result.get("output_tokens", 0)) if isinstance(result, dict) else 0
                actual_cost = float(result.get("actual_cost", 0)) if isinstance(result, dict) else 0.0
                conn.execute(
                    f"""
                    UPDATE {self.table('chapters')}
                    SET ai_text = ?, ai_char_count = ?, ai_model = ?, translated_at = ?,
                        input_tokens = ?, output_tokens = ?, actual_cost = ?,
                        translation_status = 'translated', translation_error = NULL, updated_at = ?
                    WHERE novel_id = ? AND chapter_number = ?
                    """,
                    (text, len(text), job["model"], now, input_tokens, output_tokens, actual_cost, now, job["novel_id"], item["chapter_number"]),
                )
                conn.execute(
                    f"""
                    UPDATE {self.table('translation_job_items')}
                    SET status = 'completed', input_tokens = ?, output_tokens = ?, actual_cost = ?,
                        model = ?, finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (input_tokens, output_tokens, actual_cost, job["model"], now, now, item["id"]),
                )
            counts = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('pending','running') THEN 1 ELSE 0 END) AS remaining,
                    SUM(COALESCE(actual_cost, 0)) AS actual
                FROM {self.table('translation_job_items')}
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            status = "completed" if int(counts["remaining"] or 0) == 0 and int(counts["failed"] or 0) == 0 else "running"
            conn.execute(
                f"""
                UPDATE {self.table('translation_jobs')}
                SET status = ?, completed_items = ?, failed_items = ?, actual_cost = ?,
                    finished_at = CASE WHEN ? = 'completed' THEN ? ELSE finished_at END,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, int(counts["completed"] or 0), int(counts["failed"] or 0), float(counts["actual"] or 0), status, now, now, job_id),
            )
        return self.translation_job(job_id) or {}

    def admin_overview(self) -> dict[str, Any]:
        with self.connect() as conn:
            novel_count = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table('novels')}").fetchone()["total"]
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END) AS original,
                    SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS reference,
                    SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS ai,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0) THEN 1 ELSE 0 END) AS needs_translation
                FROM {self.table('chapters')}
                """
            ).fetchone()
        return {
            "database": "postgresql" if self.config.backend == "postgres" else "sqlite",
            "schema": self.config.schema,
            "novels": int(novel_count or 0),
            "chapters": int(row["total"] or 0),
            "original": int(row["original"] or 0),
            "reference": int(row["reference"] or 0),
            "ai": int(row["ai"] or 0),
            "needs_translation": int(row["needs_translation"] or 0),
            "recent_jobs": self.translation_jobs(limit=5),
        }

    def mark_interrupted_jobs(self) -> None:
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('translation_jobs')} SET status = 'paused', error = 'interrupted_after_restart', updated_at = ? WHERE status = 'running'",
                (utc_now(),),
            )
            conn.execute(
                f"UPDATE {self.table('translation_job_items')} SET status = 'pending', error = 'interrupted_after_restart', updated_at = ? WHERE status = 'running'",
                (utc_now(),),
            )

    def missing_data(self, novel_id: str) -> dict[str, Any]:
        reference_start, reference_end = self.reference_range(novel_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number,
                    CASE WHEN original_text IS NULL OR LENGTH(TRIM(original_text)) = 0 THEN 1 ELSE 0 END AS missing_original,
                    CASE WHEN reference_text IS NULL OR LENGTH(TRIM(reference_text)) = 0 THEN 1 ELSE 0 END AS missing_reference,
                    translation_error
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                ORDER BY chapter_number
                """,
                (novel_id,),
            ).fetchall()
        return {
            "missing_original": [int(row["chapter_number"]) for row in rows if row["missing_original"]],
            "missing_reference": [
                int(row["chapter_number"])
                for row in rows
                if row["missing_reference"]
                and (reference_start is None or int(row["chapter_number"]) >= reference_start)
                and (reference_end is None or int(row["chapter_number"]) <= reference_end)
            ],
            "reference_target_range": {"start": reference_start, "end": reference_end},
            "translation_errors": [{"chapter_number": int(row["chapter_number"]), "error": row["translation_error"]} for row in rows if readable(row["translation_error"])],
        }

    def import_jobs(self, novel_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if novel_id:
            where = "WHERE novel_id = ?"
            params.append(novel_id)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT id, novel_id, target_mode, status, created_at, updated_at FROM {self.table('import_jobs')} {where} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def backup_payload(self, novel_id: str) -> dict[str, Any]:
        novel = self.novel(novel_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number, title, original_text, reference_text, ai_text,
                    translation_status, translation_error, ai_model, translated_at,
                    input_tokens, output_tokens, actual_cost
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                ORDER BY chapter_number
                """,
                (novel_id,),
            ).fetchall()
        return {
            "format": "godtranslator-v10-novel-backup",
            "created_at": utc_now(),
            "novel": novel,
            "chapters": [dict(row) for row in rows],
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
        "translation_error": row["translation_error"] if "translation_error" in row.keys() else None,
    }


def public_novel_row(row: Any) -> dict[str, Any]:
    payload = dict(row)
    for key in ("chapter_count", "original_count", "reference_count", "ai_count", "is_archived", "reference_target_start", "reference_target_end"):
        if key in payload:
            payload[key] = int(payload[key]) if payload[key] is not None else None
    metadata = payload.get("metadata_json")
    try:
        payload["metadata"] = json.loads(metadata) if metadata else {}
    except Exception:
        payload["metadata"] = {}
    payload.pop("metadata_json", None)
    payload["remaining_count"] = max(0, int(payload.get("original_count") or 0) - int(payload.get("ai_count") or 0))
    return payload


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def public_job_row(row: Any) -> dict[str, Any]:
    payload = dict(row)
    for key in ("total_items", "completed_items", "failed_items", "current_chapter"):
        if key in payload and payload[key] is not None:
            payload[key] = int(payload[key])
    for key in ("estimated_cost", "actual_cost", "max_total_budget", "max_per_chapter_budget"):
        if key in payload and payload[key] is not None:
            payload[key] = float(payload[key])
    settings = payload.get("settings_json")
    try:
        payload["settings"] = json.loads(settings) if settings else {}
    except Exception:
        payload["settings"] = {}
    payload.pop("settings_json", None)
    return payload


def model_pricing(model: str) -> dict[str, Any]:
    # Estimates are intentionally centralized and labelled approximate; real usage is stored from provider responses when available.
    configured = os.getenv("MODEL_PRICE_USD_PER_1M_JSON")
    if configured:
        try:
            prices = json.loads(configured)
            if model in prices:
                return {"input": float(prices[model]["input"]), "output": float(prices[model]["output"]), "note": "Configured approximate pricing."}
        except Exception:
            pass
    defaults = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
    }
    price = defaults.get(model, defaults["gpt-4o-mini"])
    return {"input": price["input"], "output": price["output"], "note": "Approximate server-side pricing; verify before large runs."}


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
