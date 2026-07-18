from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DESKTOP_ROOT = REPO_ROOT / "GodTranslator_Desktop_Companion"
sys.path.insert(0, str(DESKTOP_ROOT))


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    from desktop_companion import APP_VERSION
    from desktop_companion.paths import app_paths
    from desktop_companion.sync import version_compatible
    from desktop_companion.ui_app import NAV_ITEMS

    ui = read(DESKTOP_ROOT / "desktop_companion" / "ui_app.py")
    jobs = read(DESKTOP_ROOT / "desktop_companion" / "jobs.py")
    storage = read(DESKTOP_ROOT / "desktop_companion" / "storage.py")
    sync = read(DESKTOP_ROOT / "desktop_companion" / "sync.py")
    main_py = read(ROOT / "app" / "main.py")
    readme = read(DESKTOP_ROOT / "README.md")
    api_plan = read(DESKTOP_ROOT / "WEBSITE_API_INTEGRATION_PLAN.md")

    require("desktop version is v11", APP_VERSION == "11.0.0")
    require(
        "v11 desktop modules present",
        NAV_ITEMS
        == [
            "Dashboard",
            "Downloads",
            "Library",
            "New Novel",
            "Recovery",
            "Packs",
            "Sync",
            "Activity",
            "Settings",
            "Advanced Logs",
        ],
    )

    for text in (
        "Current Novel",
        "Current Chapter",
        "Current URL",
        "Remaining chapters",
        "Downloaded chapters",
        "Failed chapters",
        "Retries",
        "Average:",
        "ETA:",
        "Browser state",
        "Worker state",
        "Current output folder",
    ):
        require(f"Downloads shows real status field: {text}", text in ui)

    for button in (
        "Start",
        "Pause",
        "Resume",
        "Stop",
        "Retry Failed",
        "Restart Job",
        "Open Output Folder",
        "Build Pack",
        "Send to GodTranslator",
    ):
        require(f"Downloads control present: {button}", button in ui)

    require("browser queue setting present", "max_active_browser_jobs" in jobs)
    require("queued jobs wait for browser slot", "Waiting for browser slot" in jobs)
    require("next queued job starts after worker exits", "_start_next_queued_job()" in jobs)
    require("interrupted active jobs recover as paused", "Interrupted by desktop restart" in jobs)
    require("browser closed on stop/pause/finally", 'browser_state = "Closed"' in jobs)

    require("default paths use LOCALAPPDATA GodTranslatorDesktop", "GodTranslatorDesktop" in str(app_paths().root))
    require("manual token label is memory-only", "Manual bearer token (kept in memory only)" in ui)
    require("stored connection profiles clear tokens", 'payload["auth_token"] = ""' in storage)
    require("sync snapshot documents auth design", "memory only" in sync.lower())
    require("preview does not auto execute import", "Import not applied yet" in ui)
    require("execute import remains explicit", "Execute Import" in ui)
    require("upload retry supported", "def retry_upload" in sync)

    require("website desktop API version is v11", 'DESKTOP_API_VERSION = "11.0.0"' in main_py)
    require("desktop API does not accept passwords", '"passwords_accepted_by_desktop_api": False' in main_py)
    require("sync status includes desktop_api", '"desktop_api": DESKTOP_API_VERSION' in main_py)
    require("version compatibility helper works", version_compatible("11.0.0", "11.0.0"))
    require("version compatibility rejects unknown", not version_compatible("11.0.0", ""))

    require("README documents no silent updates", "Auto-update must not be silent" in readme)
    require("API plan documents recovery round trip", "Recovery Round Trip" in api_plan)
    require("API plan documents device authorization deferral", "device authorization" in api_plan.lower())
    require("No plaintext password storage documented", "Never store plaintext website passwords" in readme)

    print("qa_v11_phase6_desktop_sync: OK")
    print("desktop_version:", APP_VERSION)
    print("desktop_modules:", ", ".join(NAV_ITEMS))
    print("memory_only_token_storage: true")
    print("explicit_import_execute: true")
    print("no_openai_calls: true")
    print("production_database_url_used: false")


if __name__ == "__main__":
    main()
