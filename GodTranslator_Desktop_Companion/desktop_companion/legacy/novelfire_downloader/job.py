from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable

from .browser_engine import BrowserEngine
from .discovery import discover_chapter_links, format_url_template
from .extractor import extract_chapter
from .http_engine import HttpEngine
from .manifest import create_godtranslator_zip, load_manifest, save_manifest, save_metadata
from .selection import filename_for_chapter
from .validation import blocked_reason, validate_chapter, valid_existing_file


LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, int, int, int, str], None]
VerifyFn = Callable[[str], None]


@dataclass
class DownloadOptions:
    novel_url: str = ""
    url_template: str = ""
    chapters: list[int] = field(default_factory=list)
    output_dir: Path = Path("downloads")
    skip_existing: bool = True
    create_zip: bool = False
    save_titles: bool = True
    delay: float = 3.0
    timeout: int = 25
    retry_count: int = 2
    browser_mode: bool = True
    browser_profile_dir: Path | None = None
    min_chars: int = 500


def find_chapters(options: DownloadOptions, log: LogFn, browser: BrowserEngine | None = None) -> dict[int, str]:
    if options.url_template:
        return {chapter: format_url_template(options.url_template, chapter) for chapter in options.chapters}
    if not options.novel_url:
        raise ValueError("Paste a NovelFire novel page URL or provide an Advanced URL template.")
    owned_browser = False
    if browser is None and options.browser_mode:
        profile_dir = options.browser_profile_dir or Path(__file__).resolve().parents[1] / "browser_profile"
        browser = BrowserEngine(profile_dir, timeout=max(60, options.timeout))
        owned_browser = True
    try:
        if browser is not None:
            log("Opening visible Chrome browser for rendered chapter discovery...")
            html = browser.get_text(options.novel_url)
        else:
            engine = HttpEngine(timeout=options.timeout, retries=options.retry_count, delay=0)
            html = engine.get_text(options.novel_url)
    finally:
        if owned_browser and browser is not None:
            browser.close()
    reason = blocked_reason(html)
    if reason:
        raise ValueError(f"Novel page appears blocked or unavailable: {reason}. Enable Browser Mode and complete normal verification in Chrome if needed.")
    links = discover_chapter_links(options.novel_url, html)
    selected = {chapter: links[chapter] for chapter in options.chapters if chapter in links}
    missing = [chapter for chapter in options.chapters if chapter not in selected]
    if missing:
        log(f"Chapter links not found for: {', '.join(map(str, missing))}")
    return selected


def run_download(options: DownloadOptions, stop_event: Event, log: LogFn, progress: ProgressFn, verification_callback: VerifyFn | None = None) -> dict[str, int]:
    options.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(options.output_dir)
    manifest["requested_chapters"] = options.chapters
    engine = HttpEngine(timeout=options.timeout, retries=options.retry_count, delay=options.delay)
    profile_dir = options.browser_profile_dir or Path(__file__).resolve().parents[1] / "browser_profile"
    browser = BrowserEngine(profile_dir, timeout=max(60, options.timeout)) if options.browser_mode else None
    title_metadata: dict[str, dict[str, str]] = {}
    total = len(options.chapters)
    success = failed = skipped = 0
    try:
        urls = find_chapters(options, log, browser=browser)
        for index, chapter in enumerate(options.chapters, start=1):
            if stop_event.is_set():
                log("Stopped safely by user.")
                break
            filename = filename_for_chapter(chapter, max(options.chapters) if options.chapters else chapter)
            output_path = options.output_dir / filename
            progress(index - 1, total, success, failed, skipped, f"Chapter {chapter}")
            if options.skip_existing and valid_existing_file(output_path, chapter, options.min_chars):
                skipped += 1
                manifest["skipped_chapters"] = sorted(set(manifest.get("skipped_chapters", []) + [chapter]))
                log(f"Skipped existing valid file: {filename}")
                continue
            url = urls.get(chapter)
            if not url:
                failed += 1
                manifest.setdefault("failed_chapters", {})[str(chapter)] = {"error": "chapter URL not found"}
                log(f"Failed Chapter {chapter}: URL not found")
                continue
            try:
                if browser:
                    html = browser.get_text(url, verification_callback)
                else:
                    html = engine.get_text(url)
                reason = blocked_reason(html)
                if reason:
                    if browser and verification_callback:
                        log(f"Verification needed for Chapter {chapter}: {reason}")
                        verification_callback(url)
                        html = browser.get_text(url, verification_callback)
                        reason = blocked_reason(html)
                    if reason:
                        raise ValueError(f"Blocked, login, or verification page detected: {reason}")
                extracted = extract_chapter(html)
                validate_chapter(chapter, extracted.title, extracted.text, url, options.min_chars)
                output_path.write_text(extracted.text, encoding="utf-8")
                success += 1
                manifest.setdefault("chapters", {})[str(chapter)] = {
                    "title": extracted.title,
                    "file": filename,
                    "source_url": url,
                    "character_count": len(extracted.text),
                }
                manifest["successful_chapters"] = sorted(set(manifest.get("successful_chapters", []) + [chapter]))
                manifest.get("failed_chapters", {}).pop(str(chapter), None)
                title_metadata[str(chapter)] = {"title": extracted.title, "file": filename, "source_url": url}
                save_manifest(options.output_dir, manifest)
                log(f"Downloaded Chapter {chapter}: {filename} ({len(extracted.text)} chars)")
                engine.polite_delay()
            except Exception as exc:
                failed += 1
                manifest.setdefault("failed_chapters", {})[str(chapter)] = {"error": str(exc), "source_url": url}
                save_manifest(options.output_dir, manifest)
                log(f"Failed Chapter {chapter}: {exc}")
            progress(index, total, success, failed, skipped, f"Chapter {chapter}")
        if options.save_titles:
            save_metadata(options.output_dir, "NovelFire Novel", options.novel_url or options.url_template, manifest.get("chapters", {}))
        if options.create_zip:
            zip_path = create_godtranslator_zip(options.output_dir)
            log(f"Created ZIP: {zip_path}")
        return {"success": success, "failed": failed, "skipped": skipped}
    finally:
        if browser:
            browser.close()
