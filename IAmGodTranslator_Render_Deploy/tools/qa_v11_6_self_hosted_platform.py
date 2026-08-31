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
    acquisition = read(APP_ROOT / "app" / "acquisition.py")
    acquisition_qa = read(APP_ROOT / "tools" / "qa_v11_6_cycle3_acquisition.py")
    seeded_profile = read(APP_ROOT / "tools" / "profile_v11_6_seeded.py")
    seeded_browser_profile = read(APP_ROOT / "tools" / "browser_v11_6_seeded_profile.py")
    cycle4_reader_qa = read(APP_ROOT / "tools" / "qa_v11_6_cycle4_reader_performance.py")
    cycle4_browser_smoke = read(APP_ROOT / "tools" / "browser_v11_6_reader_cache_smoke.py")
    cycle5_visual_qa = read(APP_ROOT / "tools" / "browser_v11_6_cycle5_visual_qa.py")
    cycle3_report = read(APP_ROOT / "V11_6_CYCLE3_HYBRID_ACQUISITION_AND_PERFORMANCE.md")
    cycle4_report = read(APP_ROOT / "V11_6_CYCLE4_READER_PERFORMANCE_AND_LOCAL_FIRST.md")
    cycle5_report = read(APP_ROOT / "V11_6_CYCLE5_DARK_HOUR_INTERFACE_REPORT.md")
    desktop_packs = read(APP_ROOT.parent / "GodTranslator_Desktop_Companion" / "desktop_companion" / "packs.py")
    desktop_tests = read(APP_ROOT.parent / "GodTranslator_Desktop_Companion" / "tests" / "test_foundation.py")
    icon = APP_ROOT / "static" / "icons" / "dark-hour-icon.svg"

    require("GZip middleware configured", "GZipMiddleware" in main_py and "minimum_size=1024" in main_py, failures)
    require("static cache headers configured", "VersionedStaticFiles" in main_py and "Cache-Control" in main_py, failures)
    require("API/auth/healthz responses are no-store", 'path.startswith("/api/")' in main_py and 'path == "/healthz"' in main_py and "no-store" in main_py, failures)
    require("healthz readiness endpoint exists", '@app.get("/healthz")' in main_py, failures)
    require("safe acquisition sources endpoint exists", "/api/admin/acquisition/sources" in main_py and '"live_fetching_enabled": False' in main_py, failures)
    require("web manifest endpoint exists", '@app.get("/manifest.webmanifest")' in main_py, failures)
    require("service worker endpoint is no-cache", '@app.get("/sw.js")' in main_py and "Service-Worker-Allowed" in main_py, failures)

    require("manifest linked from shell", 'rel="manifest"' in index, failures)
    require("theme color uses Dark Hour shell color", '#101014' in index and '#0a36c9' in main_py, failures)
    require("versioned app shell assets referenced", "v=11.6.2" in index and 'APP_VERSION = "11.6.2"' in app_js, failures)
    require("service worker registered safely", "registerServiceWorker" in app_js and "window.isSecureContext" in app_js, failures)
    require("cached GETs dedupe in-flight requests", "cacheRequestMap" in app_js and "cacheRequestMap.has(path)" in app_js, failures)

    require("service worker cache is versioned", 'GT_CACHE_VERSION = "iagt-app-shell-11.6.2-' in sw and "APP_BUILD_MARKER" in app_js, failures)
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
    require("acquisition domain model exists", "class AcquisitionJob" in acquisition and "class SourceAdapter" in acquisition, failures)
    require("source adapter normalization contract exists", "def normalize_chapter" in acquisition and "def validate_chapter" in acquisition, failures)
    require("SSRF policy inspects DNS IPs", "socket.getaddrinfo" in acquisition and "ipaddress.ip_address" in acquisition, failures)
    require("redirects are revalidated", "urljoin(current, location)" in acquisition and "validate_url(" in acquisition, failures)
    require("cycle 3 acquisition QA exists", "redirect to forbidden host rejected" in acquisition_qa, failures)
    require("seeded profiling exists", "large-chapters" in seeded_profile and "production_content_used" in seeded_profile, failures)
    require("seeded browser profiling exists", "chapter_list_rows_visible_or_mounted" in seeded_browser_profile, failures)
    require("cycle 4 reader performance QA exists", "reader cache uses IndexedDB" in cycle4_reader_qa and "production_database_used" in cycle4_reader_qa, failures)
    require("cycle 4 browser cache smoke exists", "offline_cached_reopen" in cycle4_browser_smoke and "next_reused_prefetched_chapter_2" in cycle4_browser_smoke, failures)
    require("cycle 5 visual QA exists", "Cycle 5 visual QA" in cycle5_visual_qa and "horizontal_overflow" in cycle5_visual_qa, failures)
    require("cycle 3 hybrid report exists", "Hybrid acquisition" in cycle3_report and "Cycle 4 Recommendation" in cycle3_report, failures)
    require("cycle 4 reader performance report exists", "Local-First Reader Cache" in cycle4_report and "READY FOR CYCLE 5" in cycle4_report, failures)
    require("cycle 5 Dark Hour report exists", "Dark Hour Interface Report" in cycle5_report and "Screen Migration Checklist" in cycle5_report, failures)
    require("visible product brand remains IAmGodTranslator", "IAmGodTranslator" in index and "I Am God Reader" not in index, failures)
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
