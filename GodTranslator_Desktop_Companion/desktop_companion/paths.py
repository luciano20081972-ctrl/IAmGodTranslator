from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    settings_file: Path
    jobs_file: Path
    uploads_file: Path
    connection_profiles_file: Path
    downloads_dir: Path
    manifests_dir: Path
    logs_dir: Path
    packs_dir: Path
    cache_dir: Path
    browser_profiles_dir: Path


def default_app_data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "GodTranslatorDesktop"
    return Path.home() / "AppData" / "Local" / "GodTranslatorDesktop"


def app_paths(root: Path | None = None) -> AppPaths:
    app_root = root or default_app_data_dir()
    return AppPaths(
        root=app_root,
        settings_file=app_root / "settings.json",
        jobs_file=app_root / "jobs.json",
        uploads_file=app_root / "uploads.json",
        connection_profiles_file=app_root / "connection_profiles.json",
        downloads_dir=app_root / "downloads",
        manifests_dir=app_root / "manifests",
        logs_dir=app_root / "logs",
        packs_dir=app_root / "packs",
        cache_dir=app_root / "library_cache",
        browser_profiles_dir=app_root / "browser_profiles",
    )


def ensure_app_dirs(paths: AppPaths) -> None:
    for path in (
        paths.root,
        paths.downloads_dir,
        paths.manifests_dir,
        paths.logs_dir,
        paths.packs_dir,
        paths.cache_dir,
        paths.browser_profiles_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
