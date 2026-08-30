from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["GT_SQLITE_PATH"] = str(Path(tempfile.mkdtemp()) / "godtranslator-fastapi-startup.db")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("ADMIN_PASSWORD", "qa-admin-password")
os.environ.setdefault("TRANSLATION_AUTOSTART", "false")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
os.environ.pop("SUPABASE_BACKUP_SERVICE_KEY", None)


def route_key(route: Any) -> tuple[str, tuple[str, ...]]:
    methods = tuple(sorted(method for method in getattr(route, "methods", set()) if method not in {"HEAD", "OPTIONS"}))
    return str(getattr(route, "path", "")), methods


@contextmanager
def temporary_admin_secret(app_main: Any, password: str = "fixture-secret-password") -> Any:
    original_password = os.environ.pop("ADMIN_PASSWORD", None)
    original_session = os.environ.pop("ADMIN_SESSION_SECRET", None)
    original_password_file = app_main.ADMIN_PASSWORD_SECRET_FILE
    original_session_file = app_main.ADMIN_SESSION_SECRET_FILE
    with tempfile.TemporaryDirectory() as temp:
        secret_dir = Path(temp)
        password_file = secret_dir / "admin_password"
        session_file = secret_dir / "admin_session_secret"
        password_file.write_text(password + "\n", encoding="utf-8")
        session_file.write_text("fixture-session-secret\n", encoding="utf-8")
        app_main.ADMIN_PASSWORD_SECRET_FILE = str(password_file)
        app_main.ADMIN_SESSION_SECRET_FILE = str(session_file)
        try:
            yield password
        finally:
            app_main.ADMIN_PASSWORD_SECRET_FILE = original_password_file
            app_main.ADMIN_SESSION_SECRET_FILE = original_session_file
            if original_password is not None:
                os.environ["ADMIN_PASSWORD"] = original_password
            if original_session is not None:
                os.environ["ADMIN_SESSION_SECRET"] = original_session


def main() -> None:
    try:
        import fastapi  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AssertionError("FastAPI must be installed for this startup QA.") from exc

    from app import main as app_main

    if app_main.VERSION != "11.6.2":
        raise AssertionError(f"expected version 11.6.2, got {app_main.VERSION}")

    routes = [route for route in app_main.app.routes if getattr(route, "path", "")]
    by_key = {route_key(route): route for route in routes}
    expected_routes = {
        ("/api/admin/backups/manifest", ("GET",)),
        ("/api/admin/backups/download", ("GET",)),
        ("/api/admin/backups/create", ("POST",)),
        ("/api/admin/backups/jobs", ("GET",)),
        ("/api/admin/backups/jobs", ("POST",)),
        ("/api/admin/backups/jobs/{job_id}", ("GET",)),
        ("/api/admin/backups/jobs/{job_id}/cancel", ("POST",)),
        ("/api/admin/backups/restore-preview", ("POST",)),
    }
    missing = sorted(f"{path} {','.join(methods)}" for path, methods in expected_routes if (path, methods) not in by_key)
    if missing:
        raise AssertionError(f"backup routes missing: {missing}")

    mixed_response_routes = [
        ("/api/admin/backups/manifest", ("GET",)),
        ("/api/admin/backups/download", ("GET",)),
        ("/api/admin/backups/create", ("POST",)),
        ("/api/admin/backups/jobs", ("POST",)),
        ("/api/admin/backups/jobs/{job_id}", ("GET",)),
    ]
    response_model_failures = [
        path
        for path, methods in mixed_response_routes
        if getattr(by_key[(path, methods)], "response_model", None) is not None
    ]
    if response_model_failures:
        raise AssertionError(f"mixed Response-union routes still have response models: {response_model_failures}")

    health = app_main.health()
    if not isinstance(health, dict) or health.get("version") != "11.6.2":
        raise AssertionError(f"health did not return expected JSON-compatible payload: {health}")

    from fastapi.testclient import TestClient

    with temporary_admin_secret(app_main) as password:
        client = TestClient(app_main.app, base_url="https://testserver")
        valid = client.post("/api/admin/login", json={"password": password})
        if valid.status_code != 200 or not valid.json().get("admin"):
            raise AssertionError(f"admin secret-file login failed: {valid.status_code} {valid.text}")
        protected = client.get("/api/admin/session")
        if protected.status_code != 200 or not protected.json().get("admin"):
            raise AssertionError(f"admin session cookie not accepted: {protected.status_code} {protected.text}")
        invalid = TestClient(app_main.app, base_url="https://testserver").post("/api/admin/login", json={"password": "wrong"})
        if invalid.status_code != 401:
            raise AssertionError(f"invalid admin password should return 401, got {invalid.status_code}")

    print(json.dumps({
        "ok": True,
        "version": app_main.VERSION,
        "routes_checked": len(expected_routes),
        "response_model_none_checked": len(mixed_response_routes),
        "admin_secret_file_login": "passed",
        "health": health,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
