from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PBKDF2_ROUNDS = 260_000


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AppDatabase:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.warning: str | None = None
        self.path = self._sqlite_path()

    def _sqlite_path(self) -> Path:
        if self.database_url:
            if self.database_url.startswith("sqlite:///"):
                return Path(self.database_url.replace("sqlite:///", "", 1)).expanduser()
            self.warning = "DATABASE_URL is configured, but this lightweight build uses SQLite unless a sqlite:/// URL is provided."
        return self.data_dir / "godtranslator.db"

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                CREATE TABLE IF NOT EXISTS novel_bookmarks (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    novel_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, novel_id)
                );
                CREATE TABLE IF NOT EXISTS chapter_bookmarks (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    novel_id TEXT NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, novel_id, chapter_number)
                );
                CREATE TABLE IF NOT EXISTS novel_ratings (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    novel_id TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, novel_id)
                );
                CREATE TABLE IF NOT EXISTS reading_history (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    novel_id TEXT NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'ai',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, novel_id)
                );
                """
            )

    def status(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "warning": self.warning,
            "backend": "sqlite",
        }

    def _password_hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
        return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"

    def _verify_password(self, password: str, stored: str) -> bool:
        try:
            scheme, rounds, salt_hex, digest_hex = stored.split("$", 3)
            if scheme != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError):
            return False

    def _public_user(self, row: sqlite3.Row | None) -> dict[str, object] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "email": row["email"],
            "username": row["username"],
            "role": row["role"],
            "email_verified": bool(row["email_verified"]),
            "disabled": bool(row["disabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_user(self, email: str, username: str, password: str, role: str = "user") -> tuple[dict[str, object], str]:
        email = email.strip().lower()
        username = username.strip() or email.split("@", 1)[0]
        if not EMAIL_RE.match(email):
            raise ValueError("Enter a valid email address.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if role not in {"user", "paid", "admin"}:
            role = "user"
        now = utc_now()
        user_id = secrets.token_urlsafe(18)
        verification_token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO users (id, email, username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, email, username, self._password_hash(password), role, now, now),
            )
            conn.execute(
                "INSERT INTO email_verification_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (hash_token(verification_token), user_id, (datetime.now(UTC) + timedelta(days=2)).isoformat()),
            )
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(user) or {}, verification_token

    def authenticate(self, email: str, password: str) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
        if row is None or row["disabled"] or not self._verify_password(password, row["password_hash"]):
            return None
        return self._public_user(row)

    def create_session(self, user_id: str) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (hash_token(token), user_id, expires_at, utc_now()),
            )
        return token, expires_at

    def user_for_session(self, token: str | None) -> dict[str, object] | None:
        if not token:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token_hash = ? AND sessions.expires_at > ?",
                (hash_token(token), utc_now()),
            ).fetchone()
        return self._public_user(row)

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),))

    def verify_email(self, token: str) -> bool:
        token_hash = hash_token(token)
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_verification_tokens WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if row is None:
                return False
            conn.execute("UPDATE email_verification_tokens SET used_at = ? WHERE token_hash = ?", (now, token_hash))
            conn.execute("UPDATE users SET email_verified = 1, updated_at = ? WHERE id = ?", (now, row["user_id"]))
        return True

    def create_reset_token(self, email: str) -> str | None:
        with self.connect() as conn:
            user = conn.execute("SELECT id FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
            if user is None:
                return None
            token = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (hash_token(token), user["id"], (datetime.now(UTC) + timedelta(hours=2)).isoformat()),
            )
        return token

    def reset_password(self, token: str, password: str) -> bool:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        token_hash = hash_token(token)
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if row is None:
                return False
            conn.execute("UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?", (now, token_hash))
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?", (self._password_hash(password), now, row["user_id"]))
        return True

    def set_novel_bookmark(self, user_id: str, novel_id: str, enabled: bool) -> None:
        with self.connect() as conn:
            if enabled:
                conn.execute("INSERT OR IGNORE INTO novel_bookmarks (user_id, novel_id, created_at) VALUES (?, ?, ?)", (user_id, novel_id, utc_now()))
            else:
                conn.execute("DELETE FROM novel_bookmarks WHERE user_id = ? AND novel_id = ?", (user_id, novel_id))

    def set_chapter_bookmark(self, user_id: str, novel_id: str, chapter_number: int, enabled: bool) -> None:
        with self.connect() as conn:
            if enabled:
                conn.execute("INSERT OR IGNORE INTO chapter_bookmarks (user_id, novel_id, chapter_number, created_at) VALUES (?, ?, ?, ?)", (user_id, novel_id, chapter_number, utc_now()))
            else:
                conn.execute("DELETE FROM chapter_bookmarks WHERE user_id = ? AND novel_id = ? AND chapter_number = ?", (user_id, novel_id, chapter_number))

    def set_rating(self, user_id: str, novel_id: str, rating: int) -> None:
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5.")
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO novel_ratings (user_id, novel_id, rating, created_at, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, novel_id) DO UPDATE SET rating = excluded.rating, updated_at = excluded.updated_at",
                (user_id, novel_id, rating, now, now),
            )

    def save_history(self, user_id: str, novel_id: str, chapter_number: int, mode: str) -> None:
        if mode not in {"original", "reference", "ai"}:
            mode = "ai"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO reading_history (user_id, novel_id, chapter_number, mode, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, novel_id) DO UPDATE SET chapter_number = excluded.chapter_number, mode = excluded.mode, updated_at = excluded.updated_at",
                (user_id, novel_id, chapter_number, mode, utc_now()),
            )

    def library(self, user_id: str) -> dict[str, object]:
        with self.connect() as conn:
            novel_bookmarks = [dict(row) for row in conn.execute("SELECT novel_id, created_at FROM novel_bookmarks WHERE user_id = ? ORDER BY created_at DESC", (user_id,))]
            chapter_bookmarks = [dict(row) for row in conn.execute("SELECT novel_id, chapter_number, created_at FROM chapter_bookmarks WHERE user_id = ? ORDER BY created_at DESC", (user_id,))]
            ratings = [dict(row) for row in conn.execute("SELECT novel_id, rating, updated_at FROM novel_ratings WHERE user_id = ?", (user_id,))]
            history = [dict(row) for row in conn.execute("SELECT novel_id, chapter_number, mode, updated_at FROM reading_history WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))]
        return {"novel_bookmarks": novel_bookmarks, "chapter_bookmarks": chapter_bookmarks, "ratings": ratings, "reading_history": history}

    def rating_for(self, user_id: str, novel_id: str) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT rating FROM novel_ratings WHERE user_id = ? AND novel_id = ?", (user_id, novel_id)).fetchone()
        return int(row["rating"]) if row else None

    def users(self) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [self._public_user(row) or {} for row in rows]

    def update_user_role(self, user_id: str, role: str) -> dict[str, object] | None:
        if role not in {"user", "paid", "admin"}:
            raise ValueError("Role must be user, paid, or admin.")
        with self.connect() as conn:
            conn.execute("UPDATE users SET role = ?, updated_at = ? WHERE id = ?", (role, utc_now(), user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(row)

    def set_user_disabled(self, user_id: str, disabled: bool) -> dict[str, object] | None:
        with self.connect() as conn:
            conn.execute("UPDATE users SET disabled = ?, updated_at = ? WHERE id = ?", (1 if disabled else 0, utc_now(), user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._public_user(row)
