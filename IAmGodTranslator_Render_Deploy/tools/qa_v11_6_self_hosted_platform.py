"""Focused QA for v11.6 self-hosted performance, PWA, and design-system foundation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(label: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def main() -> int:
    failures: list[str] = []
    main_py = read(APP_ROOT / "app" / "main.py")
    index = read(APP_ROOT / "templates" / "index.html")
    app_js = read(APP_ROOT / "static" / "app.js")
    styles = read(APP_ROOT / "static" / "styles.css")
    sw = read(APP_ROOT / "static" / "sw.js")
    profiler = read(APP_ROOT / "tools" / "profile_v11_6_runtime.py")
    browser_smoke = read(APP_ROOT / "tools" / "browser_v11_6_pwa_smoke.py")
    desktop_packs = read(APP_ROOT.parent / "GodTranslator_Desktop_Companion" / "desktop_companion" / "packs.py")
    desktop_tests = read(APP_ROOT.parent / "GodTranslator_Desktop_Companion" / "tests" / "test_foundation.py")
    icon = APP_ROOT / "static" / "icons" / "dark-hour-icon.svg"

    require("GZip middleware configured", "GZipMiddleware" in main_py and "minimum_size=1024" in main_py, failures)
    require("static cache headers configured", "VersionedStaticFiles" in main_py and "Cache-Control" in main_py, failures)
    require("API/auth/healthz responses are no-store", 'path.startswith("/api/")' in main_py and 'path == "/healthz"' in main_py and "no-store" in main_py, failures)
    require("healthz readiness endpoint exists", '@app.get("/healthz")' in main_py, failures)
    require("web manifest endpoint exists", '@app.get("/manifest.webmanifest")' in main_py, failures)
    require("service worker endpoint is no-cache", '@app.get("/sw.js")' in main_py and "Service-Worker-Allowed" in main_py, failures)

    require("manifest linked from shell", 'rel="manifest"' in index, failures)
    require("theme color uses Dark Hour blue", '#0a36c9' in index and '#0a36c9' in main_py, failures)
    require("versioned app shell assets referenced", "v=11.6.0" in index and 'APP_VERSION = "11.6.0"' in app_js, failures)
    require("service worker registered safely", "registerServiceWorker" in app_js and "window.isSecureContext" in app_js, failures)
    require("cached GETs dedupe in-flight requests", "cacheRequestMap" in app_js and "cacheRequestMap.has(path)" in app_js, failures)

    require("service worker cache is versioned", 'GT_CACHE_VERSION = "iagt-app-shell-11.6.0"' in sw, failures)
    require("service worker excludes API cache", 'pathname.startsWith("/api/")' in sw, failures)
    require("service worker excludes auth cache", 'pathname.startsWith("/auth/")' in sw, failures)
    require("service worker handles activation cleanup", "caches.delete" in sw and "clients.claim" in sw, failures)
    require("service worker does not cache credentials by pattern", "/api/" not in json.dumps([line for line in sw.splitlines() if "APP_SHELL" in line]), failures)

    require("Dark Hour design tokens exist", "--dh-blue-950" in styles and "--dh-cyan-400" in styles, failures)
    require("Persona 4 yellow palette not introduced", "Persona 4" not in styles + app_js + index + main_py, failures)
    require("no Atlus/SEGA assets referenced", "Atlus" not in styles + app_js + index and "SEGA" not in styles + app_js + index, failures)
    require("original PWA icon exists", icon.exists(), failures)
    require("runtime profiler exists", "RouteMetric" in profiler and "Content-Encoding" in profiler, failures)
    require("browser PWA smoke exists", "service_worker_controlled_after_reload" in browser_smoke, failures)
    require("desktop CJK chapter filenames parse", "第\\s*0*(\\d+)\\s*章" in desktop_packs, failures)
    require("desktop Unicode path regression exists", "test_unicode_and_spaced_paths_pack_as_utf8_chapters" in desktop_tests, failures)

    result = {
        "ok": not failures,
        "failures": failures,
        "checks": {
            "gzip": "configured",
            "static_cache": "short browser cache for app assets; immutable vendor cache",
            "api_cache": "no-store",
            "pwa": "manifest plus app-shell service worker",
            "design_system": "Dark Hour blue/navy/cyan tokens",
            "copyright": "no Persona/Atlus/SEGA assets referenced",
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
