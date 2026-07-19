from __future__ import annotations

import json
import os
import sys
import tempfile
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


def main() -> None:
    try:
        import fastapi  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AssertionError("FastAPI must be installed for this startup QA.") from exc

    from app import main as app_main

    if app_main.VERSION != "10.6.2":
        raise AssertionError(f"expected version 10.6.2, got {app_main.VERSION}")

    routes = [route for route in app_main.app.routes if getattr(route, "path", "")]
    by_key = {route_key(route): route for route in routes}
    expected_routes = {
        ("/api/admin/backups/manifest", ("GET",)),
        ("/api/admin/backups/download", ("GET",)),
        ("/api/admin/backups/create", ("POST",)),
        ("/api/admin/backups/jobs", ("GET",)),
        ("/api/admin/backups/jobs/{job_id}", ("GET",)),
    }
    missing = sorted(f"{path} {','.join(methods)}" for path, methods in expected_routes if (path, methods) not in by_key)
    if missing:
        raise AssertionError(f"backup routes missing: {missing}")

    mixed_response_routes = [
        ("/api/admin/backups/manifest", ("GET",)),
        ("/api/admin/backups/download", ("GET",)),
        ("/api/admin/backups/create", ("POST",)),
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
    if not isinstance(health, dict) or health.get("version") != "10.6.2":
        raise AssertionError(f"health did not return expected JSON-compatible payload: {health}")

    print(json.dumps({
        "ok": True,
        "version": app_main.VERSION,
        "routes_checked": len(expected_routes),
        "response_model_none_checked": len(mixed_response_routes),
        "health": health,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
