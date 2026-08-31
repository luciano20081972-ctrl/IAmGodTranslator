from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Callable

from ..acquisition import AcquisitionError, AcquisitionRequest, ApifyProvider, FirecrawlProvider, chapter_url


class CloudChapterAdapter:
    name = "cloud"
    display_name = "Cloud Acquisition"
    supports_http = False
    supports_playwright = False
    provider_type = None

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
    ) -> dict[str, object]:
        return {
            "novel_url": novel_url,
            "chapter_url_template": chapter_url_template or novel_url,
            "chapters": chapters,
            "output_dir": output_dir,
            "delay": delay,
            "retry_count": retry_count,
            "skip_existing": skip_existing,
        }

    def provider(self):
        if self.provider_type is None:
            raise NotImplementedError("Cloud provider is not configured.")
        return self.provider_type()

    def download(self, options: dict[str, object], stop_event: Event, log: Callable[[str], None], progress: Callable[..., None]) -> dict[str, int]:
        provider = self.provider()
        chapters = [int(item) for item in options.get("chapters", [])]
        output_dir = Path(options["output_dir"])
        template = str(options.get("chapter_url_template") or options.get("novel_url") or "")
        skip_existing = bool(options.get("skip_existing", True))
        success = failed = skipped = 0
        log(f"Provider selected: {provider.name}")
        for index, chapter in enumerate(chapters, start=1):
            path = output_dir / f"{chapter:04d}.txt"
            if stop_event.is_set():
                log("Job stopped before next provider fetch")
                break
            if skip_existing and path.exists() and path.read_text(encoding="utf-8", errors="ignore").strip():
                skipped += 1
                log(f"Skipped existing Chapter {chapter}: {path.name}")
                progress(index, len(chapters), success, failed, skipped, f"Chapter {chapter}")
                continue
            url = chapter_url(template, chapter)
            log(f"Downloading Chapter {chapter}: {url}")
            try:
                page = provider.fetch_page(AcquisitionRequest(source_url=url, chapter_number=chapter), cancel=stop_event)
                body = page.content.strip()
                if not body:
                    raise AcquisitionError("empty_content", "Provider returned empty chapter content", retryable=False)
                path.write_text(f"{page.title or f'Chapter {chapter}'}\n\n{body}\n", encoding="utf-8")
                success += 1
                log(f"Saved Chapter {chapter}: {path.name} via {page.provider}")
            except AcquisitionError as exc:
                failed += 1
                log(f"Failed Chapter {chapter}: {exc.category}")
            progress(index, len(chapters), success, failed, skipped, f"Chapter {chapter}")
        return {"success": success, "failed": failed, "skipped": skipped}


class FirecrawlAdapter(CloudChapterAdapter):
    name = "firecrawl"
    display_name = "Firecrawl"
    provider_type = FirecrawlProvider


class ApifyAdapter(CloudChapterAdapter):
    name = "apify"
    display_name = "Apify"
    provider_type = ApifyProvider
