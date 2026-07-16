from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Callable


class NovelFireAdapter:
    name = "novelfire"
    display_name = "NovelFire"
    supports_http = True
    supports_playwright = True

    def build_options(
        self,
        novel_url: str,
        chapter_url_template: str,
        chapters: list[int],
        output_dir: Path,
        browser_mode: bool,
        browser_profile_dir: Path,
        delay: float = 3.0,
        retry_count: int = 2,
        skip_existing: bool = True,
    ):
        from ..legacy.novelfire_downloader.job import DownloadOptions

        return DownloadOptions(
            novel_url=novel_url,
            url_template=chapter_url_template,
            chapters=chapters,
            output_dir=output_dir,
            skip_existing=skip_existing,
            delay=delay,
            retry_count=retry_count,
            browser_mode=browser_mode,
            browser_profile_dir=browser_profile_dir,
        )

    def detect(self, options: DownloadOptions, log: Callable[[str], None]) -> dict[int, str]:
        from ..legacy.novelfire_downloader.job import find_chapters

        return find_chapters(options, log)

    def download(self, options: DownloadOptions, stop_event: Event, log: Callable[[str], None], progress: Callable[..., None]) -> dict[str, int]:
        from ..legacy.novelfire_downloader.job import run_download

        return run_download(options, stop_event, log, progress)
