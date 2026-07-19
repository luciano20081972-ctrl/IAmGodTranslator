from __future__ import annotations

import os
import tempfile
import types
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_fastapi_stubs() -> None:
    try:
        import fastapi  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    class FakeRoute:
        def __init__(self, path: str) -> None:
            self.path = path

    class FakeFastAPI:
        def __init__(self, *args, **kwargs) -> None:
            self.routes: list[FakeRoute] = []

        def mount(self, *args, **kwargs) -> None:
            return None

        def on_event(self, event: str):
            def decorator(func):
                return func

            return decorator

        def _route(self, path: str, *args, **kwargs):
            def decorator(func):
                self.routes.append(FakeRoute(path))
                return func

            return decorator

        get = post = patch = put = delete = _route

    def marker(*args, **kwargs):
        return kwargs.get("default") if "default" in kwargs else None

    class FakeHTTPException(Exception):
        def __init__(self, status_code: int, detail: str = "") -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FakeResponse:
        def set_cookie(self, *args, **kwargs) -> None:
            return None

        def delete_cookie(self, *args, **kwargs) -> None:
            return None

    class FakeJSONResponse(dict):
        def __init__(self, content=None, headers=None, *args, **kwargs) -> None:
            super().__init__(content or {})
            self.headers = headers or {}

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.Body = marker
    fastapi_module.Depends = marker
    fastapi_module.FastAPI = FakeFastAPI
    fastapi_module.File = marker
    fastapi_module.HTTPException = FakeHTTPException
    fastapi_module.Query = marker
    fastapi_module.Request = object
    fastapi_module.Response = FakeResponse
    fastapi_module.UploadFile = object

    responses_module = types.ModuleType("fastapi.responses")
    responses_module.HTMLResponse = str
    responses_module.JSONResponse = FakeJSONResponse
    responses_module.StreamingResponse = object

    staticfiles_module = types.ModuleType("fastapi.staticfiles")
    staticfiles_module.StaticFiles = lambda *args, **kwargs: object()

    sys.modules["fastapi"] = fastapi_module
    sys.modules["fastapi.responses"] = responses_module
    sys.modules["fastapi.staticfiles"] = staticfiles_module


class WebsiteDesktopIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        temp = tempfile.TemporaryDirectory()
        cls._temp = temp
        os.environ["GT_SQLITE_PATH"] = str(Path(temp.name) / "godtranslator-v10-6.db")
        os.environ["TRANSLATION_AUTOSTART"] = "false"
        install_fastapi_stubs()
        from app import main

        cls.main = main
        cls.main.database.initialize()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def test_v10_6_runtime_labels(self) -> None:
        self.assertEqual(self.main.VERSION, "11.0.0")
        health = self.main.desktop_health()
        self.assertTrue(health["ok"])
        self.assertEqual(health["desktop_api"], "11.0.0")
        self.assertFalse(health["auth"]["passwords_accepted_by_desktop_api"])
        self.assertIn("Connected", health["sync_states"])
        self.assertIn("pack_preview", health["supports"])

    def test_desktop_routes_registered(self) -> None:
        routes = {getattr(route, "path", "") for route in self.main.app.routes}
        self.assertIn("/api/desktop/health", routes)
        self.assertIn("/api/desktop/auth/check", routes)
        self.assertIn("/api/desktop/sync/status", routes)
        self.assertIn("/api/desktop/import-history", routes)
        self.assertIn("/api/desktop/import/preview-pack", routes)
        self.assertIn("/api/desktop/import/execute-pack", routes)

    def test_sync_status_uses_isolated_database(self) -> None:
        self.main.database.save_novel_metadata("desktop-fixture", {"title": "Desktop Fixture"})
        self.main.database.upsert_chapter("desktop-fixture", 1, "Chapter 1", "Original", "Reference", "", None)
        payload = self.main.desktop_sync_status("desktop-fixture")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "11.0.0")
        self.assertEqual(payload["desktop_api"], "11.0.0")
        self.assertEqual(payload["novel"]["id"], "desktop-fixture")
        self.assertEqual(payload["missing"]["missing_english"], [1])
        self.assertIn("pack_preview", payload["sync"])
        self.assertIn("Do not send or store an Admin password", payload["sync"]["auth"])

    def test_import_history_limit_is_safe(self) -> None:
        payload = self.main.desktop_import_history(limit=500)
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["jobs"]), 100)


if __name__ == "__main__":
    unittest.main()
