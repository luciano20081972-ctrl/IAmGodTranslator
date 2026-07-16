from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator


LOGGER = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def utc_after(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def readable(value: str | None) -> bool:
    return bool(value and value.strip())


MAX_TITLE_LENGTH = 72
MAX_TITLE_WORDS = 10
CHAPTER_TITLE_RE = re.compile(r"^(?:chapter|chap|ch)\s*0*\d+\b|^第\s*0*\d+\s*章", re.IGNORECASE)
CONTENT_TYPES = {"original", "english", "reference", "ai", "metadata", "cover", "glossary"}
ENGLISH_EDITION_PRIORITY = {
    "official": 0,
    "edited": 1,
    "imported": 2,
    "human": 3,
    "ai": 4,
    "machine": 5,
    "community": 6,
}
PLATFORM_BACKUP_APP_VERSION = "10.6.1"
PLATFORM_BACKUP_TABLE_NAMES = [
    "novels",
    "chapters",
    "chapter_editions",
    "translation_jobs",
    "translation_job_items",
    "translation_performance",
    "import_jobs",
    "import_job_items",
    "content_import_items",
    "user_profiles",
    "user_preferences",
    "reading_progress",
    "reading_history",
    "bookmarks",
    "favorites",
    "translation_profiles",
]


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
        chapter_editions = self.table("chapter_editions")
        translation_jobs = self.table("translation_jobs")
        translation_job_items = self.table("translation_job_items")
        import_jobs = self.table("import_jobs")
        import_job_items = self.table("import_job_items")
        content_import_items = self.table("content_import_items")
        user_profiles = self.table("user_profiles")
        user_preferences = self.table("user_preferences")
        reading_progress = self.table("reading_progress")
        reading_history = self.table("reading_history")
        bookmarks = self.table("bookmarks")
        favorites = self.table("favorites")
        translation_profiles = self.table("translation_profiles")
        chapters_novel_chapter = self.index("chapters_novel_chapter")
        chapters_missing_ai = self.index("chapters_missing_ai")
        chapter_editions_lookup = self.index("chapter_editions_lookup")
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
        translation_performance = self.table("translation_performance")
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

        CREATE TABLE IF NOT EXISTS {chapter_editions} (
            id {id_type},
            novel_id TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            edition_key TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            edition_type TEXT NOT NULL DEFAULT 'AI',
            source_label TEXT,
            text TEXT NOT NULL,
            character_count INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (novel_id, chapter_number, edition_key)
        );

        CREATE INDEX IF NOT EXISTS {chapter_editions_lookup}
        ON {chapter_editions}(novel_id, chapter_number, language, is_default);

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
            priority TEXT NOT NULL DEFAULT 'normal',
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
            failure_category TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            worker_id TEXT,
            claimed_at {ts_type},
            heartbeat_at {ts_type},
            lease_expires_at {ts_type},
            started_at {ts_type},
            finished_at {ts_type},
            provider_started_at {ts_type},
            provider_finished_at {ts_type},
            queue_wait_seconds {numeric_type},
            claim_duration_seconds {numeric_type},
            chapter_load_seconds {numeric_type},
            prompt_build_seconds {numeric_type},
            provider_wait_seconds {numeric_type},
            save_duration_seconds {numeric_type},
            total_duration_seconds {numeric_type},
            retry_delay_seconds {numeric_type},
            original_char_count INTEGER,
            reference_char_count INTEGER,
            prompt_instruction_tokens INTEGER,
            prompt_original_tokens INTEGER,
            prompt_reference_tokens INTEGER,
            prompt_estimated_output_tokens INTEGER,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (job_id, chapter_number)
        );

        CREATE TABLE IF NOT EXISTS {translation_performance} (
            id {id_type},
            model TEXT NOT NULL,
            novel_id TEXT,
            sample_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            total_duration_seconds {numeric_type} NOT NULL DEFAULT 0,
            total_input_chars INTEGER NOT NULL DEFAULT 0,
            total_output_chars INTEGER NOT NULL DEFAULT 0,
            total_input_tokens INTEGER NOT NULL DEFAULT 0,
            total_output_tokens INTEGER NOT NULL DEFAULT 0,
            rate_limited_count INTEGER NOT NULL DEFAULT 0,
            timeout_count INTEGER NOT NULL DEFAULT 0,
            updated_at {ts_type} NOT NULL,
            UNIQUE (model, novel_id)
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
            target_content_type TEXT,
            edition_type TEXT,
            language TEXT,
            title TEXT,
            source_url TEXT,
            filename TEXT,
            sha256 TEXT,
            character_count INTEGER NOT NULL DEFAULT 0,
            content_text TEXT,
            status TEXT NOT NULL,
            error TEXT,
            action TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (job_id, chapter_number)
        );

        CREATE TABLE IF NOT EXISTS {content_import_items} (
            id {id_type},
            job_id {job_ref_type} NOT NULL REFERENCES {import_jobs}(id) ON DELETE CASCADE,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER,
            target_content_type TEXT NOT NULL,
            edition_type TEXT,
            language TEXT,
            title TEXT,
            source_url TEXT,
            filename TEXT,
            sha256 TEXT,
            character_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            action TEXT,
            error TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {user_profiles} (
            user_id TEXT PRIMARY KEY,
            email TEXT,
            display_name TEXT,
            avatar_url TEXT,
            preferred_language TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {user_preferences} (
            user_id TEXT PRIMARY KEY,
            preferences_json TEXT NOT NULL,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {reading_progress} (
            user_id TEXT NOT NULL,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'ai',
            scroll_percent {numeric_type} NOT NULL DEFAULT 0,
            updated_at {ts_type} NOT NULL,
            PRIMARY KEY (user_id, novel_id)
        );

        CREATE TABLE IF NOT EXISTS {reading_history} (
            id {id_type},
            user_id TEXT NOT NULL,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'ai',
            progress_percent {numeric_type} NOT NULL DEFAULT 0,
            created_at {ts_type} NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {bookmarks} (
            id {id_type},
            user_id TEXT NOT NULL,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            chapter_number INTEGER NOT NULL,
            note TEXT,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL,
            UNIQUE (user_id, novel_id, chapter_number)
        );

        CREATE TABLE IF NOT EXISTS {favorites} (
            user_id TEXT NOT NULL,
            novel_id TEXT NOT NULL REFERENCES {novels}(id) ON DELETE CASCADE,
            created_at {ts_type} NOT NULL,
            PRIMARY KEY (user_id, novel_id)
        );

        CREATE TABLE IF NOT EXISTS {translation_profiles} (
            id {uuid_type},
            user_id TEXT,
            name TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            is_shared INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at {ts_type} NOT NULL,
            updated_at {ts_type} NOT NULL
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
            "priority": "TEXT NOT NULL DEFAULT 'normal'",
        }
        ts_type = "TIMESTAMPTZ" if self.config.backend == "postgres" else "TEXT"
        item_columns = {
            "model": "TEXT",
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "started_at": ts_type,
            "finished_at": ts_type,
            "failure_category": "TEXT",
            "worker_id": "TEXT",
            "claimed_at": ts_type,
            "heartbeat_at": ts_type,
            "lease_expires_at": ts_type,
            "provider_started_at": ts_type,
            "provider_finished_at": ts_type,
            "queue_wait_seconds": "REAL",
            "claim_duration_seconds": "REAL",
            "chapter_load_seconds": "REAL",
            "prompt_build_seconds": "REAL",
            "provider_wait_seconds": "REAL",
            "save_duration_seconds": "REAL",
            "total_duration_seconds": "REAL",
            "retry_delay_seconds": "REAL",
            "original_char_count": "INTEGER",
            "reference_char_count": "INTEGER",
            "prompt_instruction_tokens": "INTEGER",
            "prompt_original_tokens": "INTEGER",
            "prompt_reference_tokens": "INTEGER",
            "prompt_estimated_output_tokens": "INTEGER",
        }
        import_item_columns = {
            "target_content_type": "TEXT",
            "edition_type": "TEXT",
            "language": "TEXT",
            "title": "TEXT",
            "source_url": "TEXT",
            "action": "TEXT",
        }
        for table, columns in (
            ("novels", novel_columns),
            ("chapters", chapter_columns),
            ("translation_jobs", job_columns),
            ("translation_job_items", item_columns),
            ("import_job_items", import_item_columns),
        ):
            existing = self.columns(conn, table)
            for column, definition in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {self.table(table)} ADD COLUMN {column} {definition}")
        self._migrate_ai_text_to_english_editions(conn)

    def _ensure_postgres_timestamp_helpers(self, conn: Any) -> None:
        if self.config.backend != "postgres":
            return
        conn.execute(
            f"""
            CREATE OR REPLACE FUNCTION {self.table("safe_timestamptz_from_text")}(
                raw_value TEXT,
                fallback_value TIMESTAMPTZ
            )
            RETURNS TIMESTAMPTZ
            LANGUAGE plpgsql
            AS $godtranslator_safe_timestamp$
            DECLARE
                parsed_value TIMESTAMPTZ;
            BEGIN
                IF raw_value IS NULL OR LENGTH(BTRIM(raw_value)) = 0 THEN
                    RETURN fallback_value;
                END IF;

                BEGIN
                    parsed_value := BTRIM(raw_value)::TIMESTAMPTZ;
                EXCEPTION WHEN OTHERS THEN
                    RETURN fallback_value;
                END;

                RETURN COALESCE(parsed_value, fallback_value);
            END;
            $godtranslator_safe_timestamp$
            """
        )

    def _legacy_ai_edition_created_at_sql(self, table_alias: str = "legacy") -> str:
        alias = validate_identifier(table_alias)
        translated_at = f"{alias}.translated_at"
        created_at = f"{alias}.created_at"
        if self.config.backend == "postgres":
            return f"{self.table('safe_timestamptz_from_text')}({translated_at}, {created_at})"
        return (
            "CASE "
            f"WHEN {translated_at} IS NOT NULL "
            f"AND LENGTH(TRIM({translated_at})) > 0 "
            f"AND datetime({translated_at}) IS NOT NULL "
            f"THEN {translated_at} "
            f"ELSE {created_at} "
            "END"
        )

    def _migrate_ai_text_to_english_editions(self, conn: Any) -> None:
        self._ensure_postgres_timestamp_helpers(conn)
        chapters = self.table("chapters")
        editions = self.table("chapter_editions")
        created_at_expr = self._legacy_ai_edition_created_at_sql("legacy")
        conn.execute(
            f"""
            INSERT INTO {editions} (
                novel_id, chapter_number, edition_key, language, edition_type, source_label,
                text, character_count, is_default, metadata_json, created_at, updated_at
            )
            SELECT legacy.novel_id, legacy.chapter_number, 'ai', 'en', 'AI', 'Legacy AI',
                legacy.ai_text, LENGTH(legacy.ai_text),
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM {editions} existing_default
                        WHERE existing_default.novel_id = legacy.novel_id
                        AND existing_default.chapter_number = legacy.chapter_number
                        AND existing_default.language = 'en'
                        AND existing_default.is_default = 1
                        AND existing_default.edition_key <> 'ai'
                    )
                    THEN 0
                    ELSE 1
                END,
                '{{}}', {created_at_expr}, legacy.updated_at
            FROM {chapters} legacy
            WHERE legacy.ai_text IS NOT NULL AND LENGTH(TRIM(legacy.ai_text)) > 0
            ON CONFLICT(novel_id, chapter_number, edition_key) DO UPDATE SET
                text = excluded.text,
                character_count = excluded.character_count,
                is_default = excluded.is_default,
                updated_at = excluded.updated_at
            """
        )

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
        title = clean_chapter_title(chapter_number, title) if normalize_title_text(title) else None
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
                        original_char_count = LENGTH(COALESCE(EXCLUDED.original_text, target.original_text, '')),
                        reference_char_count = LENGTH(COALESCE(EXCLUDED.reference_text, target.reference_text, '')),
                        ai_char_count = LENGTH(COALESCE(EXCLUDED.ai_text, target.ai_text, '')),
                        translation_status = CASE
                            WHEN LENGTH(TRIM(COALESCE(EXCLUDED.original_text, target.original_text, ''))) = 0 THEN 'missing_original'
                            WHEN LENGTH(TRIM(COALESCE(EXCLUDED.ai_text, target.ai_text, ''))) = 0 THEN 'needs_translation'
                            ELSE 'translated'
                        END,
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
                        original_char_count = LENGTH(COALESCE(excluded.original_text, original_text, '')),
                        reference_char_count = LENGTH(COALESCE(excluded.reference_text, reference_text, '')),
                        ai_char_count = LENGTH(COALESCE(excluded.ai_text, ai_text, '')),
                        translation_status = CASE
                            WHEN LENGTH(TRIM(COALESCE(excluded.original_text, original_text, ''))) = 0 THEN 'missing_original'
                            WHEN LENGTH(TRIM(COALESCE(excluded.ai_text, ai_text, ''))) = 0 THEN 'needs_translation'
                            ELSE 'translated'
                        END,
                        ai_model = COALESCE(excluded.ai_model, ai_model),
                        updated_at = excluded.updated_at
                    """,
                    (novel_id, chapter_number, title, original_text, reference_text, ai_text, *counts, status, ai_model, now, now),
                )
            if readable(ai_text):
                self._upsert_english_edition_conn(
                    conn,
                    novel_id,
                    chapter_number,
                    ai_text or "",
                    edition_type="AI",
                    source_label=ai_model or "AI",
                    edition_key="ai",
                    is_default=True,
                    now=now,
                    metadata={"model": ai_model} if ai_model else {},
                )

    def _upsert_english_edition_conn(
        self,
        conn: Any,
        novel_id: str,
        chapter_number: int,
        text: str,
        edition_type: str = "Imported",
        source_label: str | None = None,
        edition_key: str | None = None,
        language: str = "en",
        is_default: bool = True,
        now: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not readable(text):
            return
        now = now or utc_now()
        edition_type = normalize_edition_type(edition_type)
        edition_key = edition_key or edition_key_for(edition_type, source_label)
        should_be_default = bool(is_default)
        if should_be_default:
            current = conn.execute(
                f"""
                SELECT edition_type
                FROM {self.table('chapter_editions')}
                WHERE novel_id = ? AND chapter_number = ? AND language = ? AND is_default = 1
                LIMIT 1
                """,
                (novel_id, chapter_number, language),
            ).fetchone()
            if current and edition_priority(edition_type) > edition_priority(current["edition_type"]):
                should_be_default = False
        if should_be_default:
            conn.execute(
                f"""
                UPDATE {self.table('chapter_editions')}
                SET is_default = 0, updated_at = ?
                WHERE novel_id = ? AND chapter_number = ? AND language = ?
                """,
                (now, novel_id, chapter_number, language),
            )
        conn.execute(
            f"""
            INSERT INTO {self.table('chapter_editions')} (
                novel_id, chapter_number, edition_key, language, edition_type, source_label,
                text, character_count, is_default, metadata_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id, chapter_number, edition_key) DO UPDATE SET
                language = excluded.language,
                edition_type = excluded.edition_type,
                source_label = excluded.source_label,
                text = excluded.text,
                character_count = excluded.character_count,
                is_default = excluded.is_default,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                novel_id,
                chapter_number,
                edition_key,
                language or "en",
                edition_type,
                source_label,
                text,
                len(text),
                1 if should_be_default else 0,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
                now,
            ),
        )

    def english_editions(self, novel_id: str, chapter_number: int | None = None) -> list[dict[str, Any]]:
        where = "novel_id = ?"
        params: list[Any] = [novel_id]
        if chapter_number is not None:
            where += " AND chapter_number = ?"
            params.append(int(chapter_number))
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT novel_id, chapter_number, edition_key, language, edition_type, source_label,
                    character_count, is_default, metadata_json, created_at, updated_at
                FROM {self.table('chapter_editions')}
                WHERE {where}
                ORDER BY chapter_number, is_default DESC, edition_type, edition_key
                """,
                tuple(params),
            ).fetchall()
        editions = [dict(row) for row in rows]
        for edition in editions:
            try:
                edition["metadata"] = json.loads(edition.pop("metadata_json") or "{}")
            except Exception:
                edition["metadata"] = {}
            edition["is_default"] = bool(edition.get("is_default"))
        return editions

    def set_default_english_edition(self, novel_id: str, chapter_number: int, edition_key: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT text, edition_type, source_label
                FROM {self.table('chapter_editions')}
                WHERE novel_id = ? AND chapter_number = ? AND edition_key = ?
                """,
                (novel_id, int(chapter_number), edition_key),
            ).fetchone()
            if row is None:
                raise ValueError("Edition not found.")
            conn.execute(
                f"UPDATE {self.table('chapter_editions')} SET is_default = 0, updated_at = ? WHERE novel_id = ? AND chapter_number = ? AND language = 'en'",
                (now, novel_id, int(chapter_number)),
            )
            conn.execute(
                f"UPDATE {self.table('chapter_editions')} SET is_default = 1, updated_at = ? WHERE novel_id = ? AND chapter_number = ? AND edition_key = ?",
                (now, novel_id, int(chapter_number), edition_key),
            )
            conn.execute(
                f"""
                UPDATE {self.table('chapters')}
                SET ai_text = ?, ai_char_count = ?, translation_status = 'translated',
                    updated_at = ?
                WHERE novel_id = ? AND chapter_number = ?
                """,
                (row["text"], len(row["text"] or ""), now, novel_id, int(chapter_number)),
            )
        return {"novel_id": novel_id, "chapter_number": int(chapter_number), "edition_key": edition_key}

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
                    SUM(CASE WHEN c.ai_text IS NOT NULL AND LENGTH(TRIM(c.ai_text)) > 0 THEN 1 ELSE 0 END) AS ai_count,
                    SUM(CASE WHEN c.ai_text IS NOT NULL AND LENGTH(TRIM(c.ai_text)) > 0 THEN 1 ELSE 0 END) AS english_count
                FROM {novels} n
                LEFT JOIN {chapters} c ON c.novel_id = n.id
                GROUP BY n.id
                ORDER BY n.updated_at DESC
                """
            ).fetchall()
            return [public_novel_row(row) for row in rows]

    def novel(self, novel_id: str) -> dict[str, Any] | None:
        novels = self.table("novels")
        chapters = self.table("chapters")
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT n.id, n.title, n.summary, n.model, n.status, n.created_at, n.updated_at,
                    n.author, n.cover_url, n.source_url, n.reference_source_url,
                    n.reference_target_start, n.reference_target_end,
                    n.metadata_json, n.is_archived,
                    COUNT(c.id) AS chapter_count,
                    SUM(CASE WHEN c.original_text IS NOT NULL AND LENGTH(TRIM(c.original_text)) > 0 THEN 1 ELSE 0 END) AS original_count,
                    SUM(CASE WHEN c.reference_text IS NOT NULL AND LENGTH(TRIM(c.reference_text)) > 0 THEN 1 ELSE 0 END) AS reference_count,
                    SUM(CASE WHEN c.ai_text IS NOT NULL AND LENGTH(TRIM(c.ai_text)) > 0 THEN 1 ELSE 0 END) AS ai_count,
                    SUM(CASE WHEN c.ai_text IS NOT NULL AND LENGTH(TRIM(c.ai_text)) > 0 THEN 1 ELSE 0 END) AS english_count
                FROM {novels} n
                LEFT JOIN {chapters} c ON c.novel_id = n.id
                WHERE n.id = ?
                GROUP BY n.id
                """,
                (novel_id,),
            ).fetchone()
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
        if start is None or end is None:
            with self.connect() as conn:
                row = conn.execute(
                    f"SELECT MIN(chapter_number) AS start, MAX(chapter_number) AS end FROM {self.table('chapters')} WHERE novel_id = ?",
                    (novel_id,),
                ).fetchone()
            start = start if start is not None else optional_int(row["start"] if row else None)
            end = end if end is not None else optional_int(row["end"] if row else None)
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
                    CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END AS has_ai,
                    CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END AS has_english,
                    CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 'AI' ELSE NULL END AS default_english_edition
                FROM {chapters}
                WHERE {where_sql}
                ORDER BY chapter_number ASC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            ).fetchall()
        return {"novel": novel, "total": int(total_row["total"]), "chapters": [public_chapter_row(row) for row in rows]}

    def chapter_text(self, novel_id: str, chapter_number: int, mode: str) -> dict[str, Any]:
        if mode in {"english", "ai"}:
            with self.connect() as conn:
                edition = conn.execute(
                    f"""
                    SELECT edition_key, edition_type, source_label, text
                    FROM {self.table('chapter_editions')}
                    WHERE novel_id = ? AND chapter_number = ? AND language = 'en'
                        AND text IS NOT NULL AND LENGTH(TRIM(text)) > 0
                    ORDER BY is_default DESC,
                        CASE LOWER(edition_type)
                            WHEN 'official' THEN 0
                            WHEN 'edited' THEN 1
                            WHEN 'human' THEN 2
                            WHEN 'imported' THEN 3
                            WHEN 'ai' THEN 4
                            WHEN 'machine' THEN 5
                            WHEN 'community' THEN 6
                            ELSE 9
                        END,
                        updated_at DESC
                    LIMIT 1
                    """,
                    (novel_id, chapter_number),
                ).fetchone()
                row = conn.execute(
                    f"SELECT chapter_number, title, ai_text FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?",
                    (novel_id, chapter_number),
                ).fetchone()
            if row is None:
                return {"ok": False, "status": "chapter_not_found", "message": "Chapter row does not exist.", "text": ""}
            text = edition["text"] if edition else row["ai_text"]
            if not readable(text):
                return {"ok": False, "status": "english_missing", "message": "English text is missing.", "chapter_number": chapter_number, "title": display_chapter_title(chapter_number, row["title"]), "text": ""}
            return {
                "ok": True,
                "status": "ok",
                "chapter_number": chapter_number,
                "title": display_chapter_title(chapter_number, row["title"]),
                "text": text,
                "mode": "english",
                "edition": {
                    "edition_key": edition["edition_key"] if edition else "ai",
                    "edition_type": edition["edition_type"] if edition else "AI",
                    "source_label": edition["source_label"] if edition else "Legacy AI",
                },
            }
        column = {"original": "original_text", "reference": "reference_text"}[mode]
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
                    SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS english,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0) THEN 1 ELSE 0 END) AS needs_translation
                FROM {chapters}
                WHERE novel_id = ?
                """,
                (novel_id,),
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("total", "original", "reference", "ai", "english", "needs_translation")}

    def library_counts(self, novel_id: str) -> dict[str, int]:
        counts = self.verification_counts(novel_id)
        return {
            "total_chapter_rows": counts["total"],
            "original_readable": counts["original"],
            "reference_readable": counts["reference"],
            "ai_readable": counts["ai"],
            "english_readable": counts["english"],
            "needs_translation": counts["needs_translation"],
            "missing_original": max(0, counts["total"] - counts["original"]),
            "missing_english": max(0, counts["total"] - counts["english"]),
            "missing_reference": max(0, counts["total"] - counts["reference"]),
        }

    def create_import_job(self, novel_id: str, target_mode: str, preview: dict[str, Any], candidates: list[Any]) -> str:
        if target_mode not in {"original", "reference", "english"}:
            raise ValueError("Only original, reference, and english recovery jobs are supported.")
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
                        job_id, novel_id, chapter_number, target_content_type, edition_type, language,
                        title, source_url, filename, sha256, character_count,
                        content_text, status, error, action, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id, chapter_number) DO UPDATE SET
                        target_content_type = excluded.target_content_type,
                        edition_type = excluded.edition_type,
                        language = excluded.language,
                        title = excluded.title,
                        source_url = excluded.source_url,
                        filename = excluded.filename,
                        sha256 = excluded.sha256,
                        character_count = excluded.character_count,
                        content_text = excluded.content_text,
                        status = excluded.status,
                        error = excluded.error,
                        action = excluded.action,
                        updated_at = excluded.updated_at
                    """,
                    (
                        job_id,
                        novel_id,
                        int(item.chapter_number),
                        target_mode,
                        "AI" if target_mode == "english" else None,
                        "en" if target_mode == "english" else None,
                        getattr(item, "title", None),
                        getattr(item, "source_url", None),
                        item.filename,
                        item.sha256,
                        int(item.character_count),
                        item.text,
                        "would_import",
                        None,
                        "add_missing",
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
            if job["target_mode"] not in {"original", "reference", "english"}:
                raise ValueError("Only original, reference, and english recovery jobs are supported.")
            target_mode = job["target_mode"]
            target_column = {"original": "original_text", "reference": "reference_text", "english": "ai_text"}[target_mode]
            count_column = {"original": "original_char_count", "reference": "reference_char_count", "english": "ai_char_count"}[target_mode]
            items = conn.execute(
                f"""
                SELECT chapter_number, filename, character_count, content_text, edition_type, language
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
                    SET {target_column} = ?,
                        {count_column} = ?,
                        translation_status = CASE
                            WHEN ? = 'english' THEN 'translated'
                            WHEN original_text IS NULL OR LENGTH(TRIM(original_text)) = 0 THEN 'missing_original'
                            WHEN ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0 THEN 'needs_translation'
                            ELSE translation_status
                        END,
                        updated_at = ?
                    WHERE novel_id = ?
                        AND chapter_number = ?
                        AND ({target_column} IS NULL OR LENGTH(TRIM({target_column})) = 0)
                    """,
                    (item["content_text"], int(item["character_count"] or 0), target_mode, now, job["novel_id"], chapter_number),
                )
                if cursor.rowcount:
                    imported.append(chapter_number)
                    status = "imported"
                    if target_mode == "english":
                        self._upsert_english_edition_conn(
                            conn,
                            job["novel_id"],
                            chapter_number,
                            item["content_text"] or "",
                            edition_type=item["edition_type"] or "Imported",
                            source_label="Recovery",
                            language=item["language"] or "en",
                            is_default=True,
                            now=now,
                        )
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
            "target_mode": target_mode,
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

    def all_untranslated_chapters(self, novel_id: str, limit: int | None = 5000, only_untranslated: bool = True) -> list[int]:
        limit_clause = "LIMIT ?" if limit else ""
        params: tuple[Any, ...] = (novel_id, limit) if limit else (novel_id,)
        untranslated_clause = "AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0)" if only_untranslated else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                    AND original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0
                    {untranslated_clause}
                ORDER BY chapter_number
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [int(row["chapter_number"]) for row in rows]

    def translation_inventory_summary(self, novel_id: str, chapters: list[int] | None = None) -> dict[str, Any]:
        where = "WHERE novel_id = ?"
        params: list[Any] = [novel_id]
        if chapters is not None:
            if not chapters:
                return {
                    "selected_count": 0,
                    "eligible_count": 0,
                    "missing_original_count": 0,
                    "already_translated_count": 0,
                    "invalid_chapter_numbers": [],
                    "available_eligible_count": 0,
                    "total_chapters": 0,
                }
            placeholders = ",".join("?" for _ in chapters)
            where += f" AND chapter_number IN ({placeholders})"
            params.extend(chapters)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number, original_text, ai_text
                FROM {self.table('chapters')}
                {where}
                ORDER BY chapter_number
                """,
                tuple(params),
            ).fetchall()
            available = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                    AND original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0
                    AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0)
                """,
                (novel_id,),
            ).fetchone()
        existing = {int(row["chapter_number"]) for row in rows}
        invalid = sorted(set(chapters or []) - existing)
        missing_original = sum(1 for row in rows if not readable(row["original_text"]))
        already = sum(1 for row in rows if readable(row["ai_text"]))
        eligible = sum(1 for row in rows if readable(row["original_text"]) and not readable(row["ai_text"]))
        return {
            "selected_count": len(chapters) if chapters is not None else len(rows),
            "eligible_count": eligible,
            "missing_original_count": missing_original,
            "already_translated_count": already,
            "invalid_chapter_numbers": invalid,
            "available_eligible_count": int(available["total"] or 0) if available else 0,
            "total_chapters": len(rows),
        }

    def performance_summary(self, model: str, novel_id: str | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    SUM(sample_count) AS sample_count,
                    SUM(success_count) AS success_count,
                    SUM(failure_count) AS failure_count,
                    SUM(total_duration_seconds) AS total_duration_seconds,
                    SUM(total_input_chars) AS total_input_chars,
                    SUM(total_output_chars) AS total_output_chars,
                    SUM(total_input_tokens) AS total_input_tokens,
                    SUM(total_output_tokens) AS total_output_tokens,
                    SUM(rate_limited_count) AS rate_limited_count,
                    SUM(timeout_count) AS timeout_count
                FROM {self.table('translation_performance')}
                WHERE model = ? AND novel_id IN (?, '__all__')
                """,
                (model, novel_id),
            ).fetchone()
        sample_count = int(row["sample_count"] or 0) if row else 0
        success_count = int(row["success_count"] or 0) if row else 0
        total_duration = float(row["total_duration_seconds"] or 0) if row else 0.0
        return {
            "sample_count": sample_count,
            "success_count": success_count,
            "failure_count": int(row["failure_count"] or 0) if row else 0,
            "average_chapter_seconds": total_duration / success_count if success_count else None,
            "average_input_chars": int(row["total_input_chars"] or 0) / sample_count if sample_count else None,
            "average_output_chars": int(row["total_output_chars"] or 0) / success_count if success_count else None,
            "success_rate": success_count / sample_count if sample_count else None,
            "rate_limited_count": int(row["rate_limited_count"] or 0) if row else 0,
            "timeout_count": int(row["timeout_count"] or 0) if row else 0,
        }

    def estimate_translation(self, novel_id: str, chapters: list[int], settings: dict[str, Any]) -> dict[str, Any]:
        settings = normalized_translation_settings(settings)
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
        inventory = self.translation_inventory_summary(novel_id, chapters)
        selection_diagnostics = dict(settings.get("_selection_diagnostics") or {})
        invalid_chapter_numbers = sorted(set(inventory["invalid_chapter_numbers"]) | set(selection_diagnostics.get("invalid_chapter_numbers") or []))
        missing_original_count = int(selection_diagnostics.get("missing_original_count", inventory["missing_original_count"]) or 0)
        already_translated_count = int(selection_diagnostics.get("already_translated_count", inventory["already_translated_count"]) or 0)
        available_eligible_count = int(selection_diagnostics.get("available_eligible_count", inventory["available_eligible_count"]) or 0)
        input_chars = sum(row["original_chars"] + (row["reference_chars"] if use_reference and row["has_reference"] else 0) for row in eligible)
        input_tokens = max(1, input_chars // 4) if eligible else 0
        output_tokens = max(1, sum(row["original_chars"] for row in eligible) // 5) if eligible else 0
        original_tokens = max(0, sum(row["original_chars"] for row in eligible) // 4)
        reference_tokens = max(0, sum(row["reference_chars"] for row in eligible if use_reference and row["has_reference"]) // 4)
        instruction_text = " ".join(
            [
                "Translate the Chinese source into natural professional English.",
                str(settings.get("style_guide") or ""),
                str(settings.get("glossary") or ""),
            ]
        )
        instruction_tokens = max(0, len(instruction_text) // 4)
        estimated_cost = (input_tokens / 1_000_000 * pricing["input"]) + (output_tokens / 1_000_000 * pricing["output"])
        performance = self.performance_summary(model, novel_id)
        speed = speed_estimate(len(eligible), settings, performance)
        return {
            "ok": True,
            "novel_id": novel_id,
            "model": model,
            "translation_mode": settings["translation_mode"],
            "speed_preset": settings["speed_preset"],
            "auto_optimize_speed": settings["auto_optimize_speed"],
            "expected_workers": speed["expected_workers"],
            "duration_estimate": speed,
            "pricing_note": pricing["note"],
            "selected_count": len(chapters),
            "eligible_count": len(eligible),
            "skipped_count": len(rows) - len(eligible),
            "original_readable": sum(1 for row in rows if row["has_original"]),
            "reference_available": sum(1 for row in rows if row["has_reference"]),
            "ai_existing": sum(1 for row in rows if row["has_ai"]),
            "missing_original_count": missing_original_count,
            "already_translated_count": already_translated_count,
            "invalid_chapter_numbers": invalid_chapter_numbers,
            "invalid_chapter_count": len(invalid_chapter_numbers),
            "duplicates_removed": int(selection_diagnostics.get("duplicates_removed") or 0),
            "duplicate_chapters": selection_diagnostics.get("duplicate_chapters") or [],
            "invalid_tokens": selection_diagnostics.get("invalid_tokens") or [],
            "available_eligible_count": available_eligible_count,
            "selection": {
                **selection_diagnostics,
                "selected_count": len(chapters),
                "eligible_count": len(eligible),
                "missing_original_count": missing_original_count,
                "already_translated_count": already_translated_count,
                "invalid_chapter_numbers": invalid_chapter_numbers,
                "invalid_chapter_count": len(invalid_chapter_numbers),
                "available_eligible_count": available_eligible_count,
            },
            "approx_input_tokens": input_tokens,
            "approx_output_tokens": output_tokens,
            "token_breakdown": {
                "original_tokens": original_tokens,
                "reference_tokens": reference_tokens,
                "instruction_glossary_tokens": instruction_tokens,
                "estimated_output_tokens": output_tokens,
            },
            "estimated_cost": round(estimated_cost, 6),
            "items": rows,
        }

    def create_translation_job(self, novel_id: str, chapters: list[int], settings: dict[str, Any]) -> dict[str, Any]:
        settings = normalized_translation_settings(settings)
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
                    max_per_chapter_budget, estimated_cost, actual_cost, priority, settings_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, 0, ?, ?, ?, ?)
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
                    settings.get("priority", "normal"),
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
                ORDER BY CASE WHEN priority = 'high' THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            jobs: list[dict[str, Any]] = []
            for row in rows:
                payload = public_job_row(row)
                items = conn.execute(
                    f"""
                    SELECT chapter_number, status, worker_id, heartbeat_at, lease_expires_at, failure_category
                    FROM {self.table('translation_job_items')}
                    WHERE job_id = ? AND status = 'running'
                    """,
                    (payload["id"],),
                ).fetchall()
                payload["activity"] = job_activity([dict(item) for item in items])
                payload["health"] = job_health(payload, payload["activity"])
                jobs.append(payload)
        return jobs

    def translation_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return None
            items = conn.execute(
                f"""
                SELECT chapter_number, status, attempts, estimated_cost, actual_cost, error, failure_category, model,
                    input_tokens, output_tokens, started_at, finished_at,
                    worker_id, claimed_at, heartbeat_at, lease_expires_at,
                    provider_started_at, provider_finished_at,
                    queue_wait_seconds, claim_duration_seconds, chapter_load_seconds,
                    prompt_build_seconds, provider_wait_seconds, save_duration_seconds,
                    total_duration_seconds, retry_delay_seconds,
                    original_char_count, reference_char_count,
                    prompt_instruction_tokens, prompt_original_tokens, prompt_reference_tokens,
                    prompt_estimated_output_tokens
                FROM {self.table('translation_job_items')}
                WHERE job_id = ?
                ORDER BY chapter_number
                LIMIT 500
                """,
                (job_id,),
            ).fetchall()
        payload = public_job_row(job)
        payload["items"] = [dict(row) for row in items]
        payload["activity"] = job_activity(payload["items"])
        payload["health"] = job_health(payload, payload["activity"], payload["items"])
        return payload

    def set_job_status(self, job_id: str, status: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('translation_jobs')} SET status = ?, updated_at = ?, finished_at = CASE WHEN ? IN ('completed','failed','cancelled') THEN ? ELSE finished_at END WHERE id = ?",
                (status, now, status, now, job_id),
            )
            if status == "cancelled":
                conn.execute(
                    f"""
                    UPDATE {self.table('translation_job_items')}
                    SET status = 'cancelled', worker_id = NULL, claimed_at = NULL,
                        heartbeat_at = NULL, lease_expires_at = NULL, updated_at = ?
                    WHERE job_id = ? AND status IN ('pending', 'running', 'failed')
                    """,
                    (now, job_id),
                )
        return self.translation_job(job_id) or {}

    def retry_failed_items(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE {self.table('translation_job_items')}
                SET status = 'pending', error = NULL, worker_id = NULL, claimed_at = NULL,
                    heartbeat_at = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE job_id = ? AND status = 'failed'
                """,
                (now, job_id),
            )
            conn.execute(f"UPDATE {self.table('translation_jobs')} SET status = 'queued', updated_at = ? WHERE id = ?", (now, job_id))
        return self.translation_job(job_id) or {}

    def run_next_translation_item(self, job_id: str, translator: Any) -> dict[str, Any]:
        worker_id = f"manual-{uuid.uuid4()}"
        claim = self.claim_translation_item(job_id, worker_id)
        if claim.get("status") != "claimed":
            return self.translation_job(job_id) or claim
        if claim.get("skip_error"):
            return self.finish_translation_item(job_id, int(claim["item_id"]), worker_id, skipped_error=str(claim["skip_error"]))
        try:
            result = translator(claim["original_text"], claim.get("reference_text"), claim["settings"])
        except Exception as exc:
            return self.finish_translation_item(job_id, int(claim["item_id"]), worker_id, error=compact_error(exc))
        return self.finish_translation_item(job_id, int(claim["item_id"]), worker_id, result=result)

    def runnable_translation_job_ids(self, limit: int = 25) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id
                FROM {self.table('translation_jobs')}
                WHERE status IN ('queued', 'running')
                ORDER BY CASE WHEN priority = 'high' THEN 0 ELSE 1 END, created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def claim_translation_item(self, job_id: str, worker_id: str, lease_seconds: int = 900) -> dict[str, Any]:
        claim_started = time.perf_counter()
        now = utc_now()
        lease_expires = utc_after(lease_seconds)
        chapter_load_seconds = 0.0
        with self.connect() as conn:
            job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return {"ok": False, "status": "missing", "message": "Translation job not found."}
            if job["status"] in {"paused", "cancelled", "completed", "failed"}:
                return {"ok": True, "status": job["status"], "message": "Job is not currently claimable."}

            settings = json.loads(job["settings_json"] or "{}") if job["settings_json"] else {}
            stop_on_budget = bool(settings.get("stop_on_budget", True))
            max_total_budget = job["max_total_budget"]
            if stop_on_budget and max_total_budget is not None and float(job["actual_cost"] or 0) >= float(max_total_budget):
                conn.execute(
                    f"UPDATE {self.table('translation_jobs')} SET status = 'paused', error = 'budget_reached', updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
                return {"ok": True, "status": "paused", "message": "Budget reached."}

            retry_count = max(0, optional_int(settings.get("retry_count")) or 0)
            if self.config.backend == "postgres":
                item = conn.execute(
                    f"""
                    SELECT *
                    FROM {self.table('translation_job_items')}
                    WHERE job_id = ?
                        AND (
                            status = 'pending'
                            OR (status = 'failed' AND attempts <= ? AND (failure_category IS NULL OR failure_category IN ('rate_limited','timeout','provider_unavailable','network_error','unknown')))
                            OR (status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at < ?) AND attempts <= ?)
                        )
                    ORDER BY CASE
                        WHEN status = 'pending' THEN 0
                        WHEN status = 'running' THEN 1
                        ELSE 2
                    END, chapter_number
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """,
                    (job_id, retry_count, now, retry_count),
                ).fetchone()
            else:
                item = conn.execute(
                    f"""
                    SELECT *
                    FROM {self.table('translation_job_items')}
                    WHERE job_id = ?
                        AND (
                            status = 'pending'
                            OR (status = 'failed' AND attempts <= ? AND (failure_category IS NULL OR failure_category IN ('rate_limited','timeout','provider_unavailable','network_error','unknown')))
                            OR (status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at < ?) AND attempts <= ?)
                        )
                    ORDER BY CASE
                        WHEN status = 'pending' THEN 0
                        WHEN status = 'running' THEN 1
                        ELSE 2
                    END, chapter_number
                    LIMIT 1
                    """,
                    (job_id, retry_count, now, retry_count),
                ).fetchone()
            if item is None:
                refreshed = self._refresh_translation_job_counts(conn, job_id, now)
                return {"ok": True, "status": "empty", "job": refreshed}

            cursor = conn.execute(
                f"""
                UPDATE {self.table('translation_job_items')}
                SET status = 'running',
                    attempts = attempts + 1,
                    error = NULL,
                    worker_id = ?,
                    claimed_at = COALESCE(claimed_at, ?),
                    heartbeat_at = ?,
                    lease_expires_at = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ?
                    AND (
                        status = 'pending'
                        OR (status = 'failed' AND attempts <= ? AND (failure_category IS NULL OR failure_category IN ('rate_limited','timeout','provider_unavailable','network_error','unknown')))
                        OR (status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at < ?) AND attempts <= ?)
                    )
                """,
                (worker_id, now, now, lease_expires, now, now, item["id"], retry_count, now, retry_count),
            )
            if not getattr(cursor, "rowcount", 0):
                return {"ok": True, "status": "race_lost", "message": "Another worker claimed this item first."}
            conn.execute(
                f"""
                UPDATE {self.table('translation_jobs')}
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    current_chapter = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, item["chapter_number"], now, job_id),
            )
            chapter_load_started = time.perf_counter()
            chapter = conn.execute(
                f"SELECT * FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?",
                (job["novel_id"], item["chapter_number"]),
            ).fetchone()
            chapter_load_seconds = time.perf_counter() - chapter_load_started

        max_per_chapter_budget = job["max_per_chapter_budget"]
        if max_per_chapter_budget is not None and float(item["estimated_cost"] or 0) > float(max_per_chapter_budget):
            skip_error = "max_per_chapter_budget_exceeded"
        elif chapter is None or not readable(chapter["original_text"]):
            skip_error = "missing_original"
        else:
            skip_error = None
        use_reference = bool(settings.get("use_reference", True))
        original_text = chapter["original_text"] if chapter is not None else ""
        reference_text = chapter["reference_text"] if chapter is not None and use_reference else None
        claim_duration_seconds = time.perf_counter() - claim_started
        return {
            "ok": True,
            "status": "claimed",
            "job_id": job_id,
            "item_id": int(item["id"]),
            "novel_id": job["novel_id"],
            "chapter_number": int(item["chapter_number"]),
            "model": job["model"],
            "settings": settings,
            "original_text": original_text,
            "reference_text": reference_text,
            "skip_error": skip_error,
            "metrics": {
                "queue_wait_seconds": seconds_between(item["created_at"], now),
                "claim_duration_seconds": claim_duration_seconds,
                "chapter_load_seconds": chapter_load_seconds,
                "original_char_count": len(original_text or ""),
                "reference_char_count": len(reference_text or ""),
            },
        }

    def heartbeat_translation_item(self, job_id: str, item_id: int, worker_id: str, lease_seconds: int = 900) -> bool:
        now = utc_now()
        lease_expires = utc_after(lease_seconds)
        with self.connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE {self.table('translation_job_items')}
                SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
                WHERE job_id = ? AND id = ? AND worker_id = ? AND status = 'running'
                """,
                (now, lease_expires, now, job_id, item_id, worker_id),
            )
        return bool(getattr(cursor, "rowcount", 0))

    def finish_translation_item(
        self,
        job_id: str,
        item_id: int,
        worker_id: str,
        result: Any | None = None,
        error: str | None = None,
        skipped_error: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        save_started = time.perf_counter()
        now = utc_now()
        metrics = dict(metrics or {})
        telemetry: tuple[str, str, float, int, int, int, int, bool, str | None] | None = None
        with self.connect() as conn:
            item = conn.execute(
                f"SELECT * FROM {self.table('translation_job_items')} WHERE job_id = ? AND id = ?",
                (job_id, item_id),
            ).fetchone()
            if item is None:
                return {"ok": False, "status": "stale_claim", "message": "Claimed item no longer exists."}
            if item["status"] != "running" or item["worker_id"] != worker_id:
                return {"ok": False, "status": "stale_claim", "message": "Claim no longer belongs to this worker."}
            if timestamp_expired(item["lease_expires_at"], now):
                return {"ok": False, "status": "stale_claim", "message": "Claim lease expired before save."}

            job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
            if job is None:
                return {"ok": False, "status": "missing", "message": "Translation job not found."}
            if job["status"] == "cancelled":
                return {"ok": True, "status": "cancelled", "message": "Job was cancelled before save."}
            chapter = conn.execute(
                f"SELECT original_text, reference_text FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?",
                (job["novel_id"], item["chapter_number"]),
            ).fetchone()
            original_chars = len(chapter["original_text"] or "") if chapter else 0
            duration_seconds = seconds_between(item["started_at"], now)

            if skipped_error:
                category = skipped_error
                conn.execute(
                    f"""
                    UPDATE {self.table('translation_job_items')}
                    SET status = 'skipped', error = ?, failure_category = ?, worker_id = NULL, claimed_at = NULL,
                        heartbeat_at = NULL, lease_expires_at = NULL, finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (skipped_error, category, now, now, item_id),
                )
                telemetry = (job["model"], job["novel_id"], duration_seconds, original_chars, 0, 0, 0, False, category)
            elif error:
                category = classify_failure_text(error)
                conn.execute(
                    f"""
                    UPDATE {self.table('translation_job_items')}
                    SET status = 'failed', error = ?, failure_category = ?, worker_id = NULL, claimed_at = NULL,
                        heartbeat_at = NULL, lease_expires_at = NULL, finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (error, category, now, now, item_id),
                )
                telemetry = (job["model"], job["novel_id"], duration_seconds, original_chars, 0, 0, 0, False, category)
            else:
                values = translation_result_values(result)
                text = values["text"]
                metrics.update(values.get("metrics") or {})
                conn.execute(
                    f"""
                    UPDATE {self.table('chapters')}
                    SET ai_text = ?, ai_char_count = ?, ai_model = ?, translated_at = ?,
                        input_tokens = ?, output_tokens = ?, actual_cost = ?,
                        translation_status = 'translated', translation_error = NULL, updated_at = ?
                    WHERE novel_id = ? AND chapter_number = ?
                    """,
                    (
                        text,
                        len(text),
                        job["model"],
                        now,
                        values["input_tokens"],
                        values["output_tokens"],
                        values["actual_cost"],
                        now,
                        job["novel_id"],
                        item["chapter_number"],
                    ),
                )
                conn.execute(
                    f"""
                    UPDATE {self.table('translation_job_items')}
                    SET status = 'completed', input_tokens = ?, output_tokens = ?, actual_cost = ?,
                        model = ?, error = NULL, failure_category = NULL, worker_id = NULL, claimed_at = NULL,
                        heartbeat_at = NULL, lease_expires_at = NULL, finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (values["input_tokens"], values["output_tokens"], values["actual_cost"], job["model"], now, now, item_id),
                )
                self._upsert_english_edition_conn(
                    conn,
                    job["novel_id"],
                    int(item["chapter_number"]),
                    text,
                    edition_type="AI",
                    source_label=job["model"],
                    edition_key="ai",
                    is_default=True,
                    now=now,
                    metadata={"model": job["model"], "job_id": job_id},
                )
                telemetry = (job["model"], job["novel_id"], duration_seconds, original_chars, len(text), values["input_tokens"], values["output_tokens"], True, None)
            metrics.setdefault("total_duration_seconds", seconds_between(item["claimed_at"] or item["started_at"], now))
            metrics["save_duration_seconds"] = time.perf_counter() - save_started
            self._store_translation_item_metrics(conn, item_id, metrics)
            refreshed = self._refresh_translation_job_counts(conn, job_id, now)
        if telemetry and not self.safe_record_translation_performance(*telemetry):
            refreshed["telemetry_warning"] = "performance_telemetry_failed"
        return refreshed

    def _store_translation_item_metrics(self, conn: Any, item_id: int, metrics: dict[str, Any]) -> None:
        allowed = {
            "provider_started_at",
            "provider_finished_at",
            "queue_wait_seconds",
            "claim_duration_seconds",
            "chapter_load_seconds",
            "prompt_build_seconds",
            "provider_wait_seconds",
            "save_duration_seconds",
            "total_duration_seconds",
            "retry_delay_seconds",
            "original_char_count",
            "reference_char_count",
            "prompt_instruction_tokens",
            "prompt_original_tokens",
            "prompt_reference_tokens",
            "prompt_estimated_output_tokens",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key in sorted(allowed):
            if key not in metrics:
                continue
            value = metrics.get(key)
            if value is None:
                continue
            assignments.append(f"{key} = ?")
            if key.endswith("_seconds"):
                values.append(round(max(0.0, float(value)), 6))
            elif key.endswith("_tokens") or key.endswith("_count"):
                values.append(max(0, int(value)))
            else:
                values.append(str(value))
        if not assignments:
            return
        values.append(item_id)
        conn.execute(
            f"UPDATE {self.table('translation_job_items')} SET {', '.join(assignments)} WHERE id = ?",
            tuple(values),
        )

    def _refresh_translation_job_counts(self, conn: Any, job_id: str, now: str | None = None) -> dict[str, Any]:
        now = now or utc_now()
        job = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            return {}
        try:
            settings = json.loads(job["settings_json"] or "{}") if job["settings_json"] else {}
        except Exception:
            settings = {}
        retry_count = max(0, optional_int(settings.get("retry_count")) or 0)
        counts = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(CASE
                    WHEN status IN ('pending','running') THEN 1
                    WHEN status = 'failed'
                        AND attempts <= ?
                        AND (failure_category IS NULL OR failure_category IN ('rate_limited','timeout','provider_unavailable','network_error','unknown'))
                    THEN 1
                    ELSE 0
                END) AS remaining,
                SUM(COALESCE(actual_cost, 0)) AS actual
            FROM {self.table('translation_job_items')}
            WHERE job_id = ?
            """,
            (retry_count, job_id),
        ).fetchone()
        current_status = job["status"]
        remaining = int(counts["remaining"] or 0)
        failed = int(counts["failed"] or 0)
        if current_status in {"paused", "cancelled"}:
            status = current_status
        elif remaining == 0:
            status = "failed" if failed else "completed"
        else:
            status = "running"
        conn.execute(
            f"""
            UPDATE {self.table('translation_jobs')}
            SET status = ?, completed_items = ?, failed_items = ?, actual_cost = ?,
                finished_at = CASE WHEN ? IN ('completed','failed','cancelled') THEN COALESCE(finished_at, ?) ELSE finished_at END,
                updated_at = ?
            WHERE id = ?
            """,
            (status, int(counts["completed"] or 0), failed, float(counts["actual"] or 0), status, now, now, job_id),
        )
        row = conn.execute(f"SELECT * FROM {self.table('translation_jobs')} WHERE id = ?", (job_id,)).fetchone()
        return public_job_row(row) if row else {}

    def refresh_translation_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            return self._refresh_translation_job_counts(conn, job_id, utc_now())

    def safe_record_translation_performance(
        self,
        model: str,
        novel_id: str,
        duration_seconds: float,
        input_chars: int,
        output_chars: int,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        failure_category: str | None = None,
    ) -> bool:
        try:
            with self.connect() as conn:
                self.record_translation_performance(
                    conn,
                    model,
                    novel_id,
                    duration_seconds,
                    input_chars,
                    output_chars,
                    input_tokens,
                    output_tokens,
                    success,
                    failure_category,
                )
            return True
        except Exception as exc:
            LOGGER.warning("translation_performance_telemetry_failed: %s", exc.__class__.__name__)
            return False

    def record_translation_performance(
        self,
        conn: Any,
        model: str,
        novel_id: str,
        duration_seconds: float,
        input_chars: int,
        output_chars: int,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        failure_category: str | None = None,
    ) -> None:
        now = utc_now()
        rate_limited = 1 if failure_category == "rate_limited" else 0
        timeout = 1 if failure_category == "timeout" else 0
        performance_table = self.table("translation_performance")
        for scoped_novel_id in (novel_id, "__all__"):
            conn.execute(
                f"""
                INSERT INTO {performance_table} AS target (
                    model, novel_id, sample_count, success_count, failure_count,
                    total_duration_seconds, total_input_chars, total_output_chars,
                    total_input_tokens, total_output_tokens, rate_limited_count,
                    timeout_count, updated_at
                )
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model, novel_id) DO UPDATE SET
                    sample_count = target.sample_count + EXCLUDED.sample_count,
                    success_count = target.success_count + EXCLUDED.success_count,
                    failure_count = target.failure_count + EXCLUDED.failure_count,
                    total_duration_seconds = target.total_duration_seconds + EXCLUDED.total_duration_seconds,
                    total_input_chars = target.total_input_chars + EXCLUDED.total_input_chars,
                    total_output_chars = target.total_output_chars + EXCLUDED.total_output_chars,
                    total_input_tokens = target.total_input_tokens + EXCLUDED.total_input_tokens,
                    total_output_tokens = target.total_output_tokens + EXCLUDED.total_output_tokens,
                    rate_limited_count = target.rate_limited_count + EXCLUDED.rate_limited_count,
                    timeout_count = target.timeout_count + EXCLUDED.timeout_count,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    model,
                    scoped_novel_id,
                    1 if success else 0,
                    0 if success else 1,
                    max(0.0, duration_seconds),
                    max(0, input_chars),
                    max(0, output_chars),
                    max(0, input_tokens),
                    max(0, output_tokens),
                    rate_limited,
                    timeout,
                    now,
                ),
            )

    def translation_performance_diagnostics(self, novel_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        jobs = self.translation_jobs(novel_id=novel_id, limit=limit)
        detailed_jobs = [self.translation_job(str(job["id"])) for job in jobs]
        detailed_jobs = [job for job in detailed_jobs if job]
        items = [item for job in detailed_jobs for item in job.get("items", [])]
        completed = [item for item in items if item.get("status") == "completed"]
        failed = [item for item in items if item.get("status") == "failed"]
        running = [item for item in items if item.get("status") == "running"]
        active_jobs = [job for job in detailed_jobs if job.get("status") in {"queued", "running", "paused"}]
        provider_latencies = [float(item.get("provider_wait_seconds") or 0) for item in completed if item.get("provider_wait_seconds") is not None]
        total_latencies = [float(item.get("total_duration_seconds") or 0) for item in completed if item.get("total_duration_seconds") is not None]
        save_latencies = [float(item.get("save_duration_seconds") or 0) for item in items if item.get("save_duration_seconds") is not None]
        claim_latencies = [float(item.get("claim_duration_seconds") or 0) for item in items if item.get("claim_duration_seconds") is not None]
        prompt_latencies = [float(item.get("prompt_build_seconds") or 0) for item in completed if item.get("prompt_build_seconds") is not None]
        retry_count = sum(max(0, int(item.get("attempts") or 0) - 1) for item in items)
        rate_limited = sum(1 for item in items if item.get("failure_category") == "rate_limited")
        timeout_count = sum(1 for item in items if item.get("failure_category") == "timeout")
        now = datetime.now(UTC)
        recent_completed = [
            item for item in completed
            if parse_timestamp(item.get("finished_at")) and (now - parse_timestamp(item.get("finished_at"))).total_seconds() <= 900
        ]
        recent_minutes = 15 if recent_completed else 0
        peak_workers = peak_provider_overlap(completed)
        active_workers = sum(int(job.get("activity", {}).get("active_workers") or 0) for job in detailed_jobs)
        avg_total = average(total_latencies)
        remaining = sum(max(0, int(job.get("total_items") or 0) - int(job.get("completed_items") or 0) - int(job.get("failed_items") or 0)) for job in active_jobs)
        worker_basis = max(1, peak_workers or active_workers or 1)
        estimated_remaining_seconds = round(remaining * avg_total / worker_basis) if avg_total and remaining else None
        settings_samples = [job.get("settings") or {} for job in detailed_jobs if job.get("settings")]
        effective = effective_settings_summary(settings_samples)
        return {
            "ok": True,
            "novel_id": novel_id,
            "jobs_observed": len(detailed_jobs),
            "items_observed": len(items),
            "simple": {
                "current_speed": chapters_per_minute(completed),
                "active_workers": active_workers,
                "peak_active_workers": peak_workers,
                "average_chapter_time_seconds": round(avg_total, 3) if avg_total is not None else None,
                "estimated_remaining_seconds": estimated_remaining_seconds,
                "recent_failures": len(failed),
            },
            "advanced": {
                "average_queue_wait_seconds": average_metric(items, "queue_wait_seconds"),
                "average_claim_seconds": average(claim_latencies),
                "average_chapter_load_seconds": average_metric(items, "chapter_load_seconds"),
                "average_prompt_build_seconds": average(prompt_latencies),
                "average_provider_wait_seconds": average(provider_latencies),
                "average_save_seconds": average(save_latencies),
                "retry_count": retry_count,
                "rate_limited_count": rate_limited,
                "timeout_count": timeout_count,
                "failed_count": len(failed),
                "average_input_tokens": average_metric(completed, "input_tokens"),
                "average_output_tokens": average_metric(completed, "output_tokens"),
                "average_original_chars": average_metric(items, "original_char_count"),
                "average_reference_chars": average_metric(items, "reference_char_count"),
                "reference_usage_percent": reference_usage_percent(items),
                "chapters_per_minute_recent": round(len(recent_completed) / recent_minutes, 3) if recent_minutes else None,
                "effective_settings": effective,
            },
            "jobs": detailed_jobs[:5],
        }

    def admin_overview(self) -> dict[str, Any]:
        with self.connect() as conn:
            novel_count = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table('novels')}").fetchone()["total"]
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                    SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END) AS original,
                    SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS reference,
                    SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS ai,
                    SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS english,
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
            "english": int(row["english"] or 0),
            "needs_translation": int(row["needs_translation"] or 0),
            "recent_jobs": self.translation_jobs(limit=5),
        }

    def mark_interrupted_jobs(self) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"UPDATE {self.table('translation_jobs')} SET status = 'queued', error = 'interrupted_after_restart', updated_at = ? WHERE status = 'running'",
                (now,),
            )
            conn.execute(
                f"""
                UPDATE {self.table('translation_job_items')}
                SET status = 'pending', error = 'interrupted_after_restart',
                    worker_id = NULL, claimed_at = NULL, heartbeat_at = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )

    def user_profile(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {self.table('user_profiles')} WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def ensure_user_profile(self, user_id: str, email: str | None, role: str = "user", display_name: str | None = None, avatar_url: str | None = None) -> dict[str, Any]:
        existing = self.user_profile(user_id)
        role_to_save = existing.get("role") if existing else role
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table('user_profiles')} (
                    user_id, email, display_name, avatar_url, preferred_language, role, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    email = excluded.email,
                    display_name = COALESCE(excluded.display_name, display_name),
                    avatar_url = COALESCE(excluded.avatar_url, avatar_url),
                    role = excluded.role,
                    updated_at = excluded.updated_at
                """,
                (user_id, email, display_name, avatar_url, role_to_save, now, now),
            )
        return self.user_profile(user_id) or {}

    def user_preferences(self, user_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(f"SELECT preferences_json FROM {self.table('user_preferences')} WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["preferences_json"] or "{}")
        except Exception:
            return {}

    def save_user_preferences(self, user_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        payload = json.dumps(preferences, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table('user_preferences')} (user_id, preferences_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, payload, now, now),
            )
        return self.user_preferences(user_id)

    def save_reading_progress(self, user_id: str, novel_id: str, chapter_number: int, source: str, scroll_percent: float = 0) -> dict[str, Any]:
        source = source if source in {"ai", "reference", "original"} else "ai"
        scroll = max(0.0, min(100.0, float(scroll_percent or 0)))
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table('reading_progress')} (user_id, novel_id, chapter_number, source, scroll_percent, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, novel_id) DO UPDATE SET
                    chapter_number = excluded.chapter_number,
                    source = excluded.source,
                    scroll_percent = excluded.scroll_percent,
                    updated_at = excluded.updated_at
                """,
                (user_id, novel_id, int(chapter_number), source, scroll, now),
            )
            conn.execute(
                f"""
                INSERT INTO {self.table('reading_history')} (user_id, novel_id, chapter_number, source, progress_percent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, novel_id, int(chapter_number), source, scroll, now),
            )
        return self.reading_progress(user_id, novel_id) or {}

    def reading_progress(self, user_id: str, novel_id: str | None = None) -> dict[str, Any] | None:
        where = ["p.user_id = ?"]
        params: list[Any] = [user_id]
        if novel_id:
            where.append("p.novel_id = ?")
            params.append(novel_id)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT p.*, n.title AS novel_title, n.cover_url, c.title AS chapter_title
                FROM {self.table('reading_progress')} p
                JOIN {self.table('novels')} n ON n.id = p.novel_id
                LEFT JOIN {self.table('chapters')} c ON c.novel_id = p.novel_id AND c.chapter_number = p.chapter_number
                WHERE {" AND ".join(where)}
                ORDER BY p.updated_at DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        return personal_progress_row(row) if row else None

    def reading_history(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT h.*, n.title AS novel_title, c.title AS chapter_title
                FROM {self.table('reading_history')} h
                JOIN {self.table('novels')} n ON n.id = h.novel_id
                LEFT JOIN {self.table('chapters')} c ON c.novel_id = h.novel_id AND c.chapter_number = h.chapter_number
                WHERE h.user_id = ?
                ORDER BY h.created_at DESC
                LIMIT ?
                """,
                (user_id, int(limit)),
            ).fetchall()
        return [personal_history_row(row) for row in rows]

    def clear_reading_history(self, user_id: str) -> None:
        with self.connect() as conn:
            conn.execute(f"DELETE FROM {self.table('reading_history')} WHERE user_id = ?", (user_id,))

    def bookmarks(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT b.*, n.title AS novel_title, c.title AS chapter_title
                FROM {self.table('bookmarks')} b
                JOIN {self.table('novels')} n ON n.id = b.novel_id
                LEFT JOIN {self.table('chapters')} c ON c.novel_id = b.novel_id AND c.chapter_number = b.chapter_number
                WHERE b.user_id = ?
                ORDER BY b.updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [personal_bookmark_row(row) for row in rows]

    def save_bookmark(self, user_id: str, novel_id: str, chapter_number: int, note: str | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            if self.config.backend == "postgres":
                conn.execute(
                    f"""
                    INSERT INTO {self.table('bookmarks')} (id, user_id, novel_id, chapter_number, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, novel_id, chapter_number) DO UPDATE SET
                        note = excluded.note,
                        updated_at = excluded.updated_at
                    """,
                    (str(uuid.uuid4()), user_id, novel_id, int(chapter_number), note or "", now, now),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO {self.table('bookmarks')} (user_id, novel_id, chapter_number, note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, novel_id, chapter_number) DO UPDATE SET
                        note = excluded.note,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, novel_id, int(chapter_number), note or "", now, now),
                )
        return next((item for item in self.bookmarks(user_id) if item["novel_id"] == novel_id and item["chapter_number"] == int(chapter_number)), {})

    def delete_bookmark(self, user_id: str, novel_id: str, chapter_number: int) -> None:
        with self.connect() as conn:
            conn.execute(
                f"DELETE FROM {self.table('bookmarks')} WHERE user_id = ? AND novel_id = ? AND chapter_number = ?",
                (user_id, novel_id, int(chapter_number)),
            )

    def favorites(self, user_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT f.user_id, f.novel_id, f.created_at, n.title, n.author, n.cover_url, n.status
                FROM {self.table('favorites')} f
                JOIN {self.table('novels')} n ON n.id = f.novel_id
                WHERE f.user_id = ?
                ORDER BY f.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_favorite(self, user_id: str, novel_id: str, favorite: bool = True) -> dict[str, Any]:
        with self.connect() as conn:
            if favorite:
                conn.execute(
                    f"""
                    INSERT INTO {self.table('favorites')} (user_id, novel_id, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, novel_id) DO NOTHING
                    """,
                    (user_id, novel_id, utc_now()),
                )
            else:
                conn.execute(f"DELETE FROM {self.table('favorites')} WHERE user_id = ? AND novel_id = ?", (user_id, novel_id))
        return {"novel_id": novel_id, "favorite": favorite}

    def users(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT user_id, email, display_name, avatar_url, preferred_language, role, created_at, updated_at
                FROM {self.table('user_profiles')}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def missing_data(self, novel_id: str) -> dict[str, Any]:
        reference_start, reference_end = self.reference_range(novel_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT chapter_number,
                    CASE WHEN original_text IS NULL OR LENGTH(TRIM(original_text)) = 0 THEN 1 ELSE 0 END AS missing_original,
                    CASE WHEN reference_text IS NULL OR LENGTH(TRIM(reference_text)) = 0 THEN 1 ELSE 0 END AS missing_reference,
                    CASE WHEN ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0 THEN 1 ELSE 0 END AS missing_english,
                    translation_error
                FROM {self.table('chapters')}
                WHERE novel_id = ?
                ORDER BY chapter_number
                """,
                (novel_id,),
            ).fetchall()
        return {
            "missing_original": [int(row["chapter_number"]) for row in rows if row["missing_original"]],
            "missing_english": [int(row["chapter_number"]) for row in rows if row["missing_english"]],
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

    def content_import_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        options = normalized_import_options(payload.get("options") if isinstance(payload.get("options"), dict) else payload)
        novel_payload = payload.get("novel") if isinstance(payload.get("novel"), dict) else {}
        novel_id = slugify(str(payload.get("novel_id") or novel_payload.get("id") or novel_payload.get("title") or ""))
        items = normalized_content_import_items(payload)
        chapter_numbers = sorted({int(item["chapter_number"]) for item in items if item.get("chapter_number")})
        existing_by_chapter: dict[int, dict[str, Any]] = {}
        existing_chapter_count = 0
        existing_novel = None
        existing_novel_public: dict[str, Any] | None = None
        if novel_id:
            with self.connect() as conn:
                existing_novel = conn.execute(f"SELECT * FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
                existing_chapter_count = int(
                    conn.execute(
                        f"SELECT COUNT(*) AS total FROM {self.table('chapters')} WHERE novel_id = ?",
                        (novel_id,),
                    ).fetchone()["total"]
                    or 0
                )
                existing_novel_public = public_novel_row(existing_novel) if existing_novel else None
                if chapter_numbers:
                    placeholders = ",".join("?" for _ in chapter_numbers)
                    rows = conn.execute(
                        f"""
                        SELECT chapter_number, title, original_text, reference_text, ai_text
                        FROM {self.table('chapters')}
                        WHERE novel_id = ? AND chapter_number IN ({placeholders})
                        """,
                        tuple([novel_id] + chapter_numbers),
                    ).fetchall()
                    existing_by_chapter = {int(row["chapter_number"]): dict(row) for row in rows}
        expected_start, expected_end = configured_chapter_range(existing_novel_public or novel_payload)
        expected_range_configured = expected_start is not None and expected_end is not None
        expected_chapter_count = (expected_end - expected_start + 1) if expected_range_configured else None

        warnings: list[str] = []
        invalid_files = list(payload.get("invalid_files") if isinstance(payload.get("invalid_files"), list) else [])
        empty_files = list(payload.get("empty_files") if isinstance(payload.get("empty_files"), list) else [])
        ambiguous_filenames = list(payload.get("ambiguous_filenames") if isinstance(payload.get("ambiguous_filenames"), list) else [])
        if not novel_id:
            warnings.append("A novel id or title is required before import can execute.")
        elif existing_novel is None:
            warnings.append("Preview targets a new novel; execute will create it before importing content.")
        if not items:
            warnings.append("No importable content was found.")

        seen: set[tuple[Any, ...]] = set()
        preview_items: list[dict[str, Any]] = []
        duplicate_keys: list[dict[str, Any]] = []
        counters = {"would_import": 0, "would_update": 0, "would_skip": 0, "duplicates": 0, "errors": 0}
        by_type: dict[str, int] = {}
        content_to_add = {"original": 0, "english": 0, "reference": 0}
        content_to_update = {"original": 0, "english": 0, "reference": 0}
        missing_by_type = {"original": [], "english": [], "reference": []}
        new_chapter_numbers: set[int] = set()
        titles: list[dict[str, Any]] = []

        for item in items:
            content_type = item["content_type"]
            by_type[content_type] = by_type.get(content_type, 0) + 1
            key = (
                content_type,
                item.get("chapter_number"),
                item.get("edition_type") if content_type == "english" else "",
                item.get("language") if content_type == "english" else "",
            )
            row_action = "would_import"
            reason = ""
            if key in seen:
                row_action = "duplicate"
                reason = "Duplicate item in import payload."
                counters["duplicates"] += 1
                duplicate_keys.append({"content_type": content_type, "chapter_number": item.get("chapter_number")})
            else:
                seen.add(key)
                if content_type in {"original", "reference", "english"}:
                    chapter_number = int(item["chapter_number"])
                    existing = existing_by_chapter.get(chapter_number)
                    column = {"original": "original_text", "reference": "reference_text", "english": "ai_text"}[content_type]
                    current_text = existing.get(column) if existing else None
                    if not existing:
                        reason = "Chapter row will be created by Content Import Center."
                        new_chapter_numbers.add(chapter_number)
                    elif readable(current_text):
                        if options["overwrite_existing"]:
                            row_action = "would_update"
                            reason = "Existing text will be replaced because overwrite is enabled."
                        else:
                            row_action = "would_skip"
                            reason = "Existing text is preserved by the selected import option."
                            missing_by_type[content_type].append(chapter_number)
                    else:
                        missing_by_type[content_type].append(chapter_number)
                    if item.get("title"):
                        titles.append({"chapter_number": chapter_number, "title": item["title"]})
                else:
                    row_action = "would_update" if existing_novel else "would_import"
                    reason = f"{content_type.title()} data will be merged into novel metadata."
                if row_action == "would_update":
                    counters["would_update"] += 1
                elif row_action == "would_skip":
                    counters["would_skip"] += 1
                else:
                    counters["would_import"] += 1
                if content_type in content_to_add and row_action == "would_import":
                    content_to_add[content_type] += 1
                if content_type in content_to_update and row_action == "would_update":
                    content_to_update[content_type] += 1
            preview_items.append({key: value for key, value in item.items() if key != "text"} | {"action": row_action, "reason": reason})

        rows_to_create = sorted(new_chapter_numbers)
        if rows_to_create:
            warnings.append("New chapters detected; execute will create chapter rows before adding content.")
        return {
            "ok": True,
            "stage": "preview",
            "novel_id": novel_id,
            "novel_title": novel_payload.get("title") or (existing_novel_public or {}).get("title") or titleCase(novel_id),
            "create_new_novel": existing_novel is None,
            "options": options,
            "existing_chapter_count": existing_chapter_count,
            "detected_chapter_count": len(chapter_numbers),
            "chapter_count": len(chapter_numbers),
            "new_chapters_detected": bool(rows_to_create),
            "new_chapter_count": len(rows_to_create),
            "new_chapter_numbers": rows_to_create,
            "rows_to_create": rows_to_create,
            "rows_to_create_count": len(rows_to_create),
            "expected_range_configured": expected_range_configured,
            "expected_chapter_range": {"start": expected_start, "end": expected_end} if expected_range_configured else None,
            "expected_chapter_count": expected_chapter_count,
            "content_type_counts": by_type,
            "content_to_add": content_to_add,
            "content_to_update": content_to_update,
            "missing_chapters": {key: sorted(set(value)) for key, value in missing_by_type.items()},
            "duplicates": duplicate_keys,
            "duplicate_count": counters["duplicates"],
            "invalid_files": invalid_files,
            "empty_files": empty_files,
            "ambiguous_filenames": ambiguous_filenames,
            "chapter_titles": titles[:100],
            "estimated_import": counters,
            "warnings": warnings,
            "items": preview_items[:500],
            "can_execute": bool(novel_id and items and counters["errors"] == 0),
        }

    def apply_content_import_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        preview = self.content_import_preview(payload)
        if not preview["can_execute"]:
            return {"ok": False, "stage": "execute", "preview": preview, "summary": {"imported": 0, "updated": 0, "skipped": 0, "errors": 1}}
        options = preview["options"]
        if options["dry_run"]:
            return {"ok": True, "stage": "dry_run", "preview": preview, "summary": {"imported": 0, "updated": 0, "skipped": 0, "errors": 0}}

        novel_payload = payload.get("novel") if isinstance(payload.get("novel"), dict) else {}
        novel_id = preview["novel_id"]
        now = utc_now()
        items = normalized_content_import_items(payload)
        imported: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        overwritten: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        job_id = str(uuid.uuid4())
        preview_for_storage = {key: value for key, value in preview.items() if key != "items"}

        with self.connect() as conn:
            novel = conn.execute(f"SELECT * FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
            if novel is None:
                conn.execute(
                    f"""
                    INSERT INTO {self.table('novels')} (
                        id, title, summary, model, status, author, cover_url, source_url,
                        reference_source_url, reference_target_start, reference_target_end,
                        metadata_json, is_archived, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        novel_id,
                        novel_payload.get("title") or titleCase(novel_id),
                        novel_payload.get("summary"),
                        novel_payload.get("model") or "gpt-4o-mini",
                        novel_payload.get("status") or "active",
                        novel_payload.get("author"),
                        novel_payload.get("cover_url"),
                        novel_payload.get("source_url"),
                        novel_payload.get("reference_source_url"),
                        optional_int(novel_payload.get("reference_target_start")),
                        optional_int(novel_payload.get("reference_target_end")),
                        json.dumps(novel_payload.get("metadata") if isinstance(novel_payload.get("metadata"), dict) else {}, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            elif options["merge_metadata"] and novel_payload:
                current_metadata = {}
                try:
                    current_metadata = json.loads(novel["metadata_json"] or "{}")
                except Exception:
                    current_metadata = {}
                incoming_metadata = novel_payload.get("metadata") if isinstance(novel_payload.get("metadata"), dict) else {}
                merged_metadata = {**current_metadata, **incoming_metadata}
                conn.execute(
                    f"""
                    UPDATE {self.table('novels')}
                    SET title = COALESCE(?, title),
                        summary = COALESCE(?, summary),
                        author = COALESCE(?, author),
                        cover_url = COALESCE(?, cover_url),
                        source_url = COALESCE(?, source_url),
                        metadata_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        novel_payload.get("title"),
                        novel_payload.get("summary"),
                        novel_payload.get("author"),
                        novel_payload.get("cover_url"),
                        novel_payload.get("source_url"),
                        json.dumps(merged_metadata, ensure_ascii=False),
                        now,
                        novel_id,
                    ),
                )

            conn.execute(
                f"""
                INSERT INTO {self.table('import_jobs')} (id, novel_id, target_mode, status, preview_json, created_at, updated_at)
                VALUES (?, ?, 'content', 'running', ?, ?, ?)
                """,
                (job_id, novel_id, json.dumps(preview_for_storage, ensure_ascii=False), now, now),
            )

            seen: set[tuple[Any, ...]] = set()
            for item in items:
                content_type = item["content_type"]
                chapter_number = optional_int(item.get("chapter_number"))
                status = "skipped"
                action = "skipped"
                error = None
                try:
                    key = (content_type, chapter_number, item.get("edition_type"), item.get("language"))
                    if key in seen:
                        raise ValueError("duplicate_import_item")
                    seen.add(key)
                    if content_type in {"metadata", "cover", "glossary"}:
                        self._apply_novel_sidecar_import_conn(conn, novel_id, item, options, now)
                        action = "updated"
                        status = "updated"
                        updated.append({"content_type": content_type, "chapter_number": chapter_number})
                    else:
                        result = self._apply_chapter_content_import_conn(conn, novel_id, item, options, now)
                        action = result["action"]
                        status = result["status"]
                        target = {"content_type": content_type, "chapter_number": chapter_number}
                        if action == "imported":
                            imported.append(target)
                        elif action == "overwritten":
                            overwritten.append(target)
                        elif action == "updated":
                            updated.append(target)
                        else:
                            skipped.append(target | {"reason": result.get("reason", "")})
                except Exception as exc:
                    status = "error"
                    action = "error"
                    error = compact_error(exc)
                    errors.append({"content_type": content_type, "chapter_number": chapter_number, "error": error})
                conn.execute(
                    f"""
                    INSERT INTO {self.table('content_import_items')} (
                        job_id, novel_id, chapter_number, target_content_type, edition_type, language,
                        title, source_url, filename, sha256, character_count, status, action, error,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        novel_id,
                        chapter_number,
                        content_type,
                        item.get("edition_type"),
                        item.get("language"),
                        item.get("title"),
                        item.get("source_url"),
                        item.get("filename"),
                        item.get("sha256"),
                        int(item.get("character_count") or 0),
                        status,
                        action,
                        error,
                        now,
                        now,
                    ),
                )
            final_status = "completed_with_errors" if errors else "completed"
            conn.execute(
                f"UPDATE {self.table('import_jobs')} SET status = ?, updated_at = ? WHERE id = ?",
                (final_status, now, job_id),
            )
        return {
            "ok": not errors,
            "stage": "execute",
            "job_id": job_id,
            "novel_id": novel_id,
            "summary": {
                "imported": len(imported),
                "updated": len(updated),
                "overwritten": len(overwritten),
                "skipped": len(skipped),
                "errors": len(errors),
                "warnings": len(preview.get("warnings") or []),
            },
            "imported": imported,
            "updated": updated,
            "overwritten": overwritten,
            "skipped": skipped,
            "errors": errors,
        }

    def _apply_chapter_content_import_conn(self, conn: Any, novel_id: str, item: dict[str, Any], options: dict[str, Any], now: str) -> dict[str, Any]:
        chapter_number = int(item["chapter_number"])
        content_type = item["content_type"]
        column = {"original": "original_text", "reference": "reference_text", "english": "ai_text", "ai": "ai_text"}[content_type]
        count_column = {"original": "original_char_count", "reference": "reference_char_count", "english": "ai_char_count", "ai": "ai_char_count"}[content_type]
        existing = conn.execute(
            f"SELECT * FROM {self.table('chapters')} WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, chapter_number),
        ).fetchone()
        text = item["text"]
        title = clean_chapter_title(chapter_number, item.get("title")) if options["import_titles"] and item.get("title") else None
        existing_text_present = bool(existing and readable(existing[column]))
        if existing_text_present and not options["overwrite_existing"]:
            return {"action": "skipped", "status": "skipped_existing", "reason": "existing_content_preserved"}
        if existing is None:
            conn.execute(
                f"""
                INSERT INTO {self.table('chapters')} (
                    novel_id, chapter_number, title, {column}, {count_column},
                    translation_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    novel_id,
                    chapter_number,
                    title,
                    text,
                    len(text),
                    "translated" if column == "ai_text" else ("ready_to_translate" if column == "original_text" else "missing_original"),
                    now,
                    now,
                ),
            )
            action = "imported"
        else:
            assignments: list[str] = []
            params: list[Any] = []
            if title:
                assignments.append("title = COALESCE(?, title)")
                params.append(title)
            assignments.extend(
                [
                    f"{column} = ?",
                    f"{count_column} = ?",
                    """
                    translation_status = CASE
                        WHEN ? = 'ai_text' THEN 'translated'
                        WHEN ? = 'original_text' AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0) THEN 'needs_translation'
                        WHEN ? = 'original_text' THEN 'translated'
                        WHEN original_text IS NULL OR LENGTH(TRIM(original_text)) = 0 THEN 'missing_original'
                        WHEN ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0 THEN 'needs_translation'
                        ELSE 'translated'
                    END
                    """,
                    "updated_at = ?",
                ]
            )
            params.extend([text, len(text), column, column, column, now, novel_id, chapter_number])
            conn.execute(
                f"""
                UPDATE {self.table('chapters')}
                SET {', '.join(assignments)}
                WHERE novel_id = ? AND chapter_number = ?
                """,
                tuple(params),
            )
            action = "overwritten" if existing_text_present and options["overwrite_existing"] else "updated"
        if column == "ai_text":
            self._upsert_english_edition_conn(
                conn,
                novel_id,
                chapter_number,
                text,
                edition_type=item.get("edition_type") or ("AI" if content_type == "ai" else "Imported"),
                source_label=item.get("source_url") or item.get("filename") or "Content Import",
                language=item.get("language") or "en",
                is_default=True,
                now=now,
                metadata={"import_source": item.get("source_url") or item.get("filename") or ""},
            )
        return {"action": action, "status": action}

    def _apply_novel_sidecar_import_conn(self, conn: Any, novel_id: str, item: dict[str, Any], options: dict[str, Any], now: str) -> None:
        novel = conn.execute(f"SELECT metadata_json FROM {self.table('novels')} WHERE id = ?", (novel_id,)).fetchone()
        metadata = {}
        try:
            metadata = json.loads(novel["metadata_json"] or "{}") if novel else {}
        except Exception:
            metadata = {}
        content_type = item["content_type"]
        if content_type == "cover":
            conn.execute(
                f"UPDATE {self.table('novels')} SET cover_url = COALESCE(?, cover_url), updated_at = ? WHERE id = ?",
                (item.get("source_url") or item.get("text"), now, novel_id),
            )
            return
        if content_type == "glossary":
            metadata["glossary"] = item.get("text") or metadata.get("glossary") or ""
        else:
            incoming = parse_json_object(item.get("text"))
            metadata = {**metadata, **incoming} if options["merge_metadata"] else incoming
        conn.execute(
            f"UPDATE {self.table('novels')} SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), now, novel_id),
        )

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

    def platform_backup_payload(self) -> dict[str, Any]:
        tables: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        with self.connect() as conn:
            for name in PLATFORM_BACKUP_TABLE_NAMES:
                try:
                    rows = conn.execute(f"SELECT * FROM {self.table(name)}").fetchall()
                    tables[name] = [dict(row) for row in rows]
                except Exception as exc:
                    tables[name] = []
                    errors[name] = exc.__class__.__name__
        counts = self.admin_overview()
        table_counts = {name: len(rows) for name, rows in tables.items()}
        manifest = {
            "format_version": "godtranslator-v10-platform-backup.v1",
            "app_version": PLATFORM_BACKUP_APP_VERSION,
            "schema": self.config.schema,
            "created_at": utc_now(),
            "table_counts": table_counts,
            "novel_count": table_counts.get("novels", 0),
            "chapter_source_counts": {
                "chapters": counts.get("chapters", 0),
                "original": counts.get("original", 0),
                "english": counts.get("english", counts.get("ai", 0)),
                "ai": counts.get("ai", 0),
                "reference": counts.get("reference", 0),
                "needs_translation": counts.get("needs_translation", 0),
            },
            "excluded": ["secrets", "passwords", "api_keys", "tokens", "cookies", "auth_password_material"],
            "table_errors": errors,
            "size_bytes": 0,
            "sha256": "",
        }
        return {"ok": True, "manifest": manifest, "tables": tables}

    def platform_backup_manifest_summary(self) -> dict[str, Any]:
        started = time.perf_counter()
        table_counts: dict[str, int | None] = {}
        errors: dict[str, str] = {}
        chapter_source_counts = {
            "chapters": 0,
            "original": 0,
            "english": 0,
            "ai": 0,
            "reference": 0,
            "needs_translation": 0,
        }
        with self.connect() as conn:
            for name in PLATFORM_BACKUP_TABLE_NAMES:
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS total FROM {self.table(name)}").fetchone()
                    table_counts[name] = int(row["total"] or 0)
                except Exception as exc:
                    table_counts[name] = None
                    errors[name] = exc.__class__.__name__
            try:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS chapters,
                        SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 THEN 1 ELSE 0 END) AS original,
                        SUM(CASE WHEN reference_text IS NOT NULL AND LENGTH(TRIM(reference_text)) > 0 THEN 1 ELSE 0 END) AS reference,
                        SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS ai,
                        SUM(CASE WHEN ai_text IS NOT NULL AND LENGTH(TRIM(ai_text)) > 0 THEN 1 ELSE 0 END) AS english,
                        SUM(CASE WHEN original_text IS NOT NULL AND LENGTH(TRIM(original_text)) > 0 AND (ai_text IS NULL OR LENGTH(TRIM(ai_text)) = 0) THEN 1 ELSE 0 END) AS needs_translation
                    FROM {self.table('chapters')}
                    """
                ).fetchone()
                chapter_source_counts = {
                    "chapters": int(row["chapters"] or 0),
                    "original": int(row["original"] or 0),
                    "english": int(row["english"] or 0),
                    "ai": int(row["ai"] or 0),
                    "reference": int(row["reference"] or 0),
                    "needs_translation": int(row["needs_translation"] or 0),
                }
            except Exception as exc:
                errors["chapter_source_counts"] = exc.__class__.__name__
        storage_url_configured = bool(os.getenv("SUPABASE_URL"))
        storage_key_configured = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_BACKUP_SERVICE_KEY"))
        manifest = {
            "format_version": "godtranslator-v10-platform-backup-manifest.v1",
            "app_version": PLATFORM_BACKUP_APP_VERSION,
            "schema": self.config.schema,
            "created_at": utc_now(),
            "generated_in_ms": round((time.perf_counter() - started) * 1000, 3),
            "kind": "lightweight_manifest",
            "table_names": PLATFORM_BACKUP_TABLE_NAMES,
            "table_counts": table_counts,
            "novel_count": table_counts.get("novels") or 0,
            "chapter_count": chapter_source_counts["chapters"],
            "chapter_source_counts": chapter_source_counts,
            "excluded": ["secrets", "passwords", "api_keys", "tokens", "cookies", "auth_password_material"],
            "table_errors": errors,
            "backup_storage": {
                "provider": "supabase",
                "configured": storage_url_configured and storage_key_configured,
                "url_configured": storage_url_configured,
                "service_key_configured": storage_key_configured,
                "bucket": os.getenv("SUPABASE_BACKUP_BUCKET") or "godtranslator-backups",
            },
            "latest_full_backup": {
                "available": False,
                "source": "not_tracked",
                "message": "Actual backup size and checksum are available only after Create Backup or Download Local Copy completes.",
            },
            "estimated_size_bytes": None,
            "actual_size_bytes": None,
            "size_bytes": None,
            "sha256": None,
            "checksum_available": False,
        }
        return {"ok": True, "manifest": manifest}

    def restore_preview(self, backup: dict[str, Any], mode: str = "add-missing") -> dict[str, Any]:
        tables = backup.get("tables") if isinstance(backup.get("tables"), dict) else {}
        key_columns = {
            "novels": ["id"],
            "chapters": ["novel_id", "chapter_number"],
            "chapter_editions": ["novel_id", "chapter_number", "edition_key"],
            "translation_jobs": ["id"],
            "translation_job_items": ["id"],
            "translation_performance": ["id"],
            "import_jobs": ["id"],
            "import_job_items": ["id"],
            "content_import_items": ["id"],
            "user_profiles": ["user_id"],
            "user_preferences": ["user_id"],
            "reading_progress": ["user_id", "novel_id"],
            "reading_history": ["id"],
            "bookmarks": ["id"],
            "favorites": ["user_id", "novel_id"],
            "translation_profiles": ["id"],
        }
        changes: dict[str, dict[str, Any]] = {}
        valid_tables = 0
        with self.connect() as conn:
            for name, rows in tables.items():
                if name not in key_columns or not isinstance(rows, list):
                    continue
                valid_tables += 1
                keys = key_columns[name]
                add = skip = overwrite = invalid = 0
                examples: list[dict[str, Any]] = []
                for row in rows:
                    if not isinstance(row, dict) or any(row.get(key) is None for key in keys):
                        invalid += 1
                        continue
                    where = " AND ".join(f"{key} = ?" for key in keys)
                    existing = conn.execute(
                        f"SELECT 1 AS found FROM {self.table(name)} WHERE {where} LIMIT 1",
                        tuple(row.get(key) for key in keys),
                    ).fetchone()
                    identity = {key: row.get(key) for key in keys}
                    if existing:
                        if mode == "overwrite":
                            overwrite += 1
                            if len(examples) < 6:
                                examples.append({"action": "overwrite", "identity": identity})
                        else:
                            skip += 1
                            if len(examples) < 6:
                                examples.append({"action": "skip-existing", "identity": identity})
                    else:
                        add += 1
                        if len(examples) < 6:
                            examples.append({"action": "add", "identity": identity})
                changes[name] = {
                    "rows": len(rows),
                    "add": add,
                    "skip_existing": skip,
                    "overwrite": overwrite,
                    "invalid": invalid,
                    "examples": examples,
                }
        return {
            "ok": True,
            "valid": valid_tables > 0,
            "mode": mode if mode in {"add-missing", "skip-existing", "overwrite"} else "add-missing",
            "stages": ["select", "validate", "compatibility", "dry_run", "exact_changes", "confirm", "background_restore", "verify"],
            "default_mode": "add-missing",
            "compatible": backup.get("manifest", {}).get("format_version") == "godtranslator-v10-platform-backup.v1",
            "changes": changes,
            "will_overwrite_chapter_text": mode == "overwrite",
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
    has_english = bool(row["has_english"] if "has_english" in row.keys() else row["has_ai"])
    return {
        "chapter_number": chapter_number,
        "title": display_chapter_title(chapter_number, row["title"]),
        "has_original": bool(row["has_original"]),
        "has_reference": bool(row["has_reference"]),
        "has_ai": bool(row["has_ai"]),
        "has_english": has_english,
        "default_english_edition": row["default_english_edition"] if "default_english_edition" in row.keys() else ("AI" if has_english else None),
        "translation_status": row["translation_status"],
        "translation_error": row["translation_error"] if "translation_error" in row.keys() else None,
    }


def public_novel_row(row: Any) -> dict[str, Any]:
    payload = dict(row)
    for key in ("chapter_count", "original_count", "reference_count", "ai_count", "english_count", "is_archived", "reference_target_start", "reference_target_end"):
        if key in payload:
            payload[key] = int(payload[key]) if payload[key] is not None else None
    metadata = payload.get("metadata_json")
    try:
        payload["metadata"] = json.loads(metadata) if metadata else {}
    except Exception:
        payload["metadata"] = {}
    payload.pop("metadata_json", None)
    chapter_count = int(payload.get("chapter_count") or 0)
    original_count = int(payload.get("original_count") or 0)
    reference_count = int(payload.get("reference_count") or 0)
    ai_count = int(payload.get("ai_count") or 0)
    payload["english_count"] = int(payload.get("english_count") if payload.get("english_count") is not None else payload.get("ai_count") or 0)
    english_count = int(payload.get("english_count") or 0)
    expected_start, expected_end = configured_chapter_range(payload)
    expected_range_configured = expected_start is not None and expected_end is not None
    expected_chapter_count = (expected_end - expected_start + 1) if expected_range_configured else None
    missing_basis = expected_chapter_count if expected_range_configured else chapter_count
    payload["expected_range_configured"] = expected_range_configured
    payload["expected_chapter_range"] = {"start": expected_start, "end": expected_end} if expected_range_configured else None
    payload["expected_chapter_count"] = expected_chapter_count
    payload["missing_counts_known"] = bool(expected_range_configured or chapter_count > 0)
    payload["chapter_inventory_state"] = (
        "empty_expected_range_configured"
        if chapter_count == 0 and expected_range_configured
        else "empty_no_expected_range"
        if chapter_count == 0
        else "has_chapters"
    )
    payload["empty_state_title"] = "No chapters imported yet" if chapter_count == 0 else ""
    payload["empty_state_detail"] = (
        "Import chapter files or a GodTranslator pack to create the first chapter rows."
        if chapter_count == 0
        else ""
    )
    payload["expected_range_state"] = "configured" if expected_range_configured else "not_set"
    payload["expected_range_label"] = (
        f"{expected_start}-{expected_end}" if expected_range_configured else "Expected range not set"
    )
    payload["missing_unknown_label"] = (
        "" if payload["missing_counts_known"] else "Unknown until chapters are imported or a range is configured."
    )
    payload["missing_original_count"] = max(0, int(missing_basis or 0) - original_count)
    payload["missing_english_count"] = max(0, int(missing_basis or 0) - english_count)
    payload["missing_reference_count"] = max(0, int(missing_basis or 0) - reference_count)
    payload["remaining_count"] = max(0, original_count - english_count)
    payload["translation_coverage"] = coverage_percent(payload.get("english_count"), payload.get("original_count"))
    payload["reading_coverage"] = coverage_percent(payload.get("english_count"), payload.get("chapter_count"))
    return payload


def configured_chapter_range(payload: dict[str, Any]) -> tuple[int | None, int | None]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    start = optional_int(
        payload.get("expected_chapter_start")
        or payload.get("expected_start")
        or payload.get("reference_target_start")
        or metadata.get("expected_chapter_start")
        or metadata.get("expected_start")
        or metadata.get("reference_target_start")
    )
    end = optional_int(
        payload.get("expected_chapter_end")
        or payload.get("expected_end")
        or payload.get("reference_target_end")
        or metadata.get("expected_chapter_end")
        or metadata.get("expected_end")
        or metadata.get("reference_target_end")
    )
    if start is not None and end is not None and start > end:
        start, end = end, start
    return start, end


def personal_progress_row(row: Any) -> dict[str, Any]:
    chapter_number = int(row["chapter_number"])
    return {
        "novel_id": row["novel_id"],
        "novel_title": row["novel_title"],
        "cover_url": row["cover_url"],
        "chapter_number": chapter_number,
        "chapter_title": display_chapter_title(chapter_number, row["chapter_title"]),
        "source": row["source"],
        "scroll_percent": float(row["scroll_percent"] or 0),
        "updated_at": row["updated_at"],
    }


def personal_history_row(row: Any) -> dict[str, Any]:
    chapter_number = int(row["chapter_number"])
    return {
        "novel_id": row["novel_id"],
        "novel_title": row["novel_title"],
        "chapter_number": chapter_number,
        "chapter_title": display_chapter_title(chapter_number, row["chapter_title"]),
        "source": row["source"],
        "progress_percent": float(row["progress_percent"] or 0),
        "created_at": row["created_at"],
    }


def personal_bookmark_row(row: Any) -> dict[str, Any]:
    chapter_number = int(row["chapter_number"])
    return {
        "id": str(row["id"]),
        "novel_id": row["novel_id"],
        "novel_title": row["novel_title"],
        "chapter_number": chapter_number,
        "chapter_title": display_chapter_title(chapter_number, row["chapter_title"]),
        "note": row["note"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalized_import_options(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    mode = str(payload.get("mode") or payload.get("import_mode") or "add_missing").replace("-", "_").lower()
    overwrite = bool(payload.get("overwrite_existing") or payload.get("overwrite")) or mode == "overwrite"
    skip_existing = not overwrite and bool(payload.get("skip_existing", True))
    add_missing = not overwrite and bool(payload.get("add_missing", True))
    return {
        "skip_existing": skip_existing,
        "overwrite_existing": overwrite,
        "add_missing": add_missing,
        "merge_metadata": bool(payload.get("merge_metadata", True)),
        "import_titles": bool(payload.get("import_titles", True)),
        "dry_run": bool(payload.get("dry_run", False)),
    }


def normalized_content_import_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw_items = payload.get("items") if isinstance(payload.get("items"), list) else None
    if raw_items is None:
        raw_items = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item = normalized_content_import_item(raw, payload)
        if item:
            items.append(item)
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    for content_type, rows in content.items():
        if isinstance(rows, list):
            for raw in rows:
                if isinstance(raw, dict):
                    item = normalized_content_import_item({**raw, "content_type": content_type}, payload)
                    if item:
                        items.append(item)
    for sidecar in ("metadata", "cover", "glossary"):
        if sidecar in payload and not isinstance(payload.get(sidecar), (list, dict)):
            item = normalized_content_import_item({"content_type": sidecar, "text": str(payload.get(sidecar) or "")}, payload)
            if item:
                items.append(item)
        elif sidecar == "metadata" and isinstance(payload.get("metadata"), dict):
            item = normalized_content_import_item({"content_type": "metadata", "text": json.dumps(payload["metadata"], ensure_ascii=False)}, payload)
            if item:
                items.append(item)
    return items


def normalized_content_import_item(raw: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    content_type = normalize_content_type(raw.get("content_type") or raw.get("target_mode") or raw.get("type") or payload.get("content_type") or payload.get("target_mode") or "english")
    if content_type not in CONTENT_TYPES:
        return None
    text = str(raw.get("text") if raw.get("text") is not None else raw.get("content") if raw.get("content") is not None else "")
    if content_type in {"original", "english", "reference", "ai", "metadata", "glossary"} and not readable(text):
        return None
    chapter_number = optional_int(raw.get("chapter_number") or raw.get("chapter") or raw.get("number"))
    if content_type in {"original", "english", "reference", "ai"} and chapter_number is None:
        return None
    edition_type = normalize_edition_type(raw.get("edition_type") or raw.get("source") or ("AI" if content_type == "ai" else "Imported"))
    normalized_type = "english" if content_type == "ai" else content_type
    sha = raw.get("sha256") or hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "chapter_number": chapter_number,
        "content_type": normalized_type,
        "edition_type": edition_type,
        "language": str(raw.get("language") or payload.get("language") or ("en" if normalized_type == "english" else "")).strip() or None,
        "title": normalize_title_text(raw.get("title")),
        "source_url": str(raw.get("source_url") or raw.get("url") or "").strip() or None,
        "filename": str(raw.get("filename") or raw.get("file") or "").strip() or None,
        "text": text,
        "sha256": sha,
        "character_count": len(text),
    }


def normalize_content_type(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "ai": "ai",
        "translation": "english",
        "translated": "english",
        "english_chapter": "english",
        "original_chapter": "original",
        "reference_chapter": "reference",
    }
    return aliases.get(normalized, normalized)


def normalize_edition_type(value: Any) -> str:
    normalized = str(value or "Imported").strip().lower().replace("_", " ")
    canonical = {
        "ai": "AI",
        "human": "Human",
        "official": "Official",
        "edited": "Edited",
        "imported": "Imported",
        "machine": "Machine",
        "community": "Community",
    }
    return canonical.get(normalized, title_case(normalized or "Imported"))


def edition_priority(value: Any) -> int:
    return ENGLISH_EDITION_PRIORITY.get(str(value or "").strip().lower(), 99)


def edition_key_for(edition_type: str, source_label: str | None = None) -> str:
    base = f"{edition_type}-{source_label or ''}".strip("-")
    key = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return key[:80] or "imported"


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def coverage_percent(numerator: Any, denominator: Any) -> int:
    denominator = int(denominator or 0)
    if denominator <= 0:
        return 0
    return round(int(numerator or 0) / denominator * 100)


def title_case(value: Any) -> str:
    return str(value or "").replace("-", " ").replace("_", " ").title()


def titleCase(value: Any) -> str:
    return title_case(value)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80]


SPEED_PRESETS: dict[str, dict[str, Any]] = {
    "careful": {"label": "Careful", "concurrency": 1, "max_workers": 2, "retry_count": 2, "timeout_seconds": 240, "description": "Lowest server/API pressure."},
    "balanced": {"label": "Balanced", "concurrency": 3, "max_workers": 4, "retry_count": 2, "timeout_seconds": 180, "description": "Recommended for most translation jobs."},
    "fast": {"label": "Fast", "concurrency": 4, "max_workers": 6, "retry_count": 2, "timeout_seconds": 150, "description": "Higher parallel processing when capacity allows."},
    "maximum-safe": {"label": "Maximum Safe", "concurrency": 6, "max_workers": 8, "retry_count": 1, "timeout_seconds": 120, "description": "Highest safe adaptive throughput currently available."},
}


def normalized_translation_settings(settings: dict[str, Any]) -> dict[str, Any]:
    payload = dict(settings or {})
    mode = str(payload.get("translation_mode") or "simple").lower()
    if mode not in {"simple", "fast", "advanced", "economy"}:
        mode = "simple"
    preset = str(payload.get("speed_preset") or ("careful" if mode == "economy" else "balanced")).lower()
    if preset not in SPEED_PRESETS:
        preset = "balanced"
    preset_config = SPEED_PRESETS[preset]
    auto = bool(payload.get("auto_optimize_speed", True))
    max_workers = optional_int(payload.get("max_workers"))
    concurrency = optional_int(payload.get("concurrency"))
    if mode != "advanced":
        concurrency = preset_config["concurrency"]
        max_workers = preset_config["max_workers"] if auto else preset_config["concurrency"]
    elif concurrency is None:
        concurrency = preset_config["concurrency"]
    hard_max = max(1, min(24, optional_int(payload.get("hard_worker_limit")) or 8))
    per_job_limit = max(1, min(hard_max, max_workers or concurrency or preset_config["concurrency"]))
    payload["translation_mode"] = mode
    payload["speed_preset"] = preset
    payload["speed_preset_label"] = preset_config["label"]
    payload["speed_preset_description"] = preset_config["description"]
    payload["auto_optimize_speed"] = auto
    payload["concurrency"] = max(1, min(per_job_limit, concurrency or preset_config["concurrency"]))
    payload["max_workers"] = per_job_limit
    retry_count = optional_int(payload.get("retry_count"))
    if retry_count is None:
        retry_count = preset_config["retry_count"]
    payload["retry_count"] = max(0, min(5, retry_count))
    payload["provider_timeout_seconds"] = max(30, min(600, optional_int(payload.get("provider_timeout_seconds")) or preset_config["timeout_seconds"]))
    batch_size = optional_int(payload.get("batch_size"))
    payload["batch_size"] = max(1, min(5000, batch_size)) if mode == "advanced" and batch_size else None
    payload["priority"] = "high" if str(payload.get("priority") or "normal").lower() == "high" else "normal"
    payload["use_reference"] = bool(payload.get("use_reference", True))
    payload["only_untranslated"] = bool(payload.get("only_untranslated", True))
    payload["stop_on_budget"] = bool(payload.get("stop_on_budget", True))
    payload["max_total_budget"] = optional_float(payload.get("max_total_budget"))
    payload["max_per_chapter_budget"] = optional_float(payload.get("max_per_chapter_budget"))
    return payload


def speed_estimate(eligible_count: int, settings: dict[str, Any], performance: dict[str, Any]) -> dict[str, Any]:
    workers = max(1, int(settings.get("concurrency") or 1))
    average = performance.get("average_chapter_seconds")
    if not average or int(performance.get("success_count") or 0) < 3:
        return {
            "approximate": True,
            "has_history": False,
            "expected_workers": workers,
            "message": "Time estimate will improve after the first few chapters complete.",
            "low_seconds": None,
            "high_seconds": None,
        }
    base_seconds = eligible_count * float(average) / workers
    return {
        "approximate": True,
        "has_history": True,
        "expected_workers": workers,
        "average_chapter_seconds": round(float(average), 2),
        "low_seconds": round(base_seconds * 0.8),
        "high_seconds": round(base_seconds * 1.3),
    }


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


def translation_result_values(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        text = str(result.get("text") or result.get("output_text") or "")
        input_tokens = int(result.get("input_tokens") or 0)
        output_tokens = int(result.get("output_tokens") or 0)
        actual_cost = float(result.get("actual_cost") or 0)
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        return {"text": text, "input_tokens": input_tokens, "output_tokens": output_tokens, "actual_cost": actual_cost, "metrics": metrics}
    return {"text": str(result or ""), "input_tokens": 0, "output_tokens": 0, "actual_cost": 0.0, "metrics": {}}


def compact_error(exc: Any) -> str:
    text = str(exc) or exc.__class__.__name__
    return text[:800]


def job_activity(items: list[dict[str, Any]]) -> dict[str, Any]:
    now = utc_now()
    running = [item for item in items if item.get("status") == "running"]
    workers = {item.get("worker_id") for item in running if item.get("worker_id")}
    heartbeats = [item.get("heartbeat_at") for item in running if item.get("heartbeat_at")]
    stalled = [item for item in running if timestamp_expired(item.get("lease_expires_at"), now)]
    current_chapters = sorted(int(item.get("chapter_number") or 0) for item in running if item.get("chapter_number"))
    return {
        "active_workers": len(workers),
        "running_items": len(running),
        "current_chapter": current_chapters[0] if current_chapters else None,
        "stalled_items": len(stalled),
        "last_heartbeat_at": max(heartbeats) if heartbeats else None,
    }


def job_health(job: dict[str, Any], activity: dict[str, Any], items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = items or []
    status = str(job.get("status") or "unknown")
    error = str(job.get("error") or "")
    failed_categories = {str(item.get("failure_category") or "") for item in items if item.get("failure_category")}
    idle_seconds = seconds_between(job.get("updated_at"), utc_now())
    failed_items = int(job.get("failed_items") or 0)
    active_workers = int(activity.get("active_workers") or 0)
    stalled_items = int(activity.get("stalled_items") or 0)
    actions: list[str] = []

    if status == "paused":
        state = "paused"
        message = "Job is paused. Resume when ready."
        actions = ["resume", "cancel"]
    elif status == "cancelled":
        state = "cancelled"
        message = "Job was cancelled; completed chapters remain saved."
    elif status == "completed":
        state = "completed_with_warnings" if failed_items else "completed"
        message = "Completed with warnings." if failed_items else "Completed."
        if failed_items:
            actions = ["retry_failed"]
    elif status == "failed":
        state = "failed"
        message = "Job needs attention before continuing."
        actions = ["retry_failed", "cancel"]
    elif "rate" in error.lower() or "rate_limited" in failed_categories:
        state = "rate_limited"
        message = "Provider rate limit reached; retrying when the backoff window clears."
        actions = ["pause", "cancel"]
    elif "timeout" in failed_categories:
        state = "retrying"
        message = "A provider timeout occurred; retryable chapters can continue."
        actions = ["pause", "cancel"]
    elif stalled_items:
        state = "stalled"
        message = "One or more claimed chapters have stale leases and may need recovery."
        actions = ["recover_stalled", "cancel"]
    elif status == "queued":
        state = "waiting_for_capacity"
        message = "Waiting for an available translation worker."
        actions = ["cancel"]
    elif status == "running" and active_workers == 0 and idle_seconds >= 300:
        state = "interrupted"
        message = "No active worker heartbeat recently; completed chapters are safe and remaining work can resume."
        actions = ["resume", "retry_failed", "cancel"]
    elif status == "running" and active_workers == 0:
        state = "waiting_for_capacity"
        message = "Waiting for an available translation worker."
        actions = ["pause", "cancel"]
    elif status == "running" and idle_seconds >= 300:
        state = "slow"
        message = "A chapter is taking longer than normal; monitor provider timing."
        actions = ["pause", "cancel"]
    else:
        state = "healthy"
        message = "Job is running with recent worker activity." if status == "running" else "Job state is normal."
        if status == "running":
            actions = ["pause", "cancel"]

    return {
        "state": state,
        "message": message,
        "idle_seconds": round(idle_seconds, 1),
        "recommended_actions": actions,
    }


def timestamp_expired(value: Any, now_text: str | None = None) -> bool:
    if not value:
        return False
    now = parse_timestamp(now_text or utc_now())
    target = parse_timestamp(value)
    return bool(target and now and target < now)


def seconds_between(start: Any, end: Any) -> float:
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)
    if not start_dt or not end_dt:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds())


def average(values: list[float]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return round(sum(clean) / len(clean), 3) if clean else None


def average_metric(items: list[dict[str, Any]], key: str) -> float | None:
    values = [float(item[key]) for item in items if item.get(key) is not None]
    return average(values)


def reference_usage_percent(items: list[dict[str, Any]]) -> float | None:
    measured = [item for item in items if item.get("reference_char_count") is not None]
    if not measured:
        return None
    used = sum(1 for item in measured if int(item.get("reference_char_count") or 0) > 0)
    return round(used / len(measured) * 100, 1)


def chapters_per_minute(items: list[dict[str, Any]]) -> float | None:
    completed = [item for item in items if parse_timestamp(item.get("finished_at"))]
    if len(completed) < 2:
        return None
    first = min(parse_timestamp(item.get("finished_at")) for item in completed if parse_timestamp(item.get("finished_at")))
    last = max(parse_timestamp(item.get("finished_at")) for item in completed if parse_timestamp(item.get("finished_at")))
    if not first or not last:
        return None
    minutes = max(1 / 60, (last - first).total_seconds() / 60)
    return round(len(completed) / minutes, 3)


def peak_provider_overlap(items: list[dict[str, Any]]) -> int:
    events: list[tuple[datetime, int]] = []
    for item in items:
        start = parse_timestamp(item.get("provider_started_at"))
        end = parse_timestamp(item.get("provider_finished_at"))
        if start and end and end >= start:
            events.append((start, 1))
            events.append((end, -1))
    active = 0
    peak = 0
    for _, delta in sorted(events, key=lambda event: (event[0], -event[1])):
        active += delta
        peak = max(peak, active)
    return peak


def effective_settings_summary(settings_samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not settings_samples:
        return {}
    latest = settings_samples[0]
    return {
        "speed_preset": latest.get("speed_preset"),
        "starting_worker_count": latest.get("concurrency"),
        "maximum_worker_count": latest.get("max_workers"),
        "retry_limit": latest.get("retry_count"),
        "provider_timeout_seconds": latest.get("provider_timeout_seconds"),
        "auto_optimize_speed": latest.get("auto_optimize_speed"),
        "global_worker_cap": optional_int(os.getenv("TRANSLATION_MAX_CONCURRENCY")) or 8,
    }


def classify_failure_text(value: str | None) -> str:
    text = (value or "").lower()
    if "429" in text or "rate" in text:
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "unavailable" in text or "503" in text or "502" in text or "504" in text:
        return "provider_unavailable"
    if "network" in text or "connection" in text:
        return "network_error"
    if "invalid" in text or "400" in text:
        return "invalid_request"
    if "policy" in text or "content" in text:
        return "content_policy"
    if "budget" in text:
        return "budget_exceeded"
    if "missing_original" in text:
        return "missing_original"
    if "cancel" in text:
        return "cancelled"
    return "unknown"


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError:
            return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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
