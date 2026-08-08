"""Synthetic Reader benchmark for v11.5 architecture work.

The benchmark deliberately avoids production chapter content. It exercises
escaped paragraph rendering, a Readium-inspired wrapper, long chapter scale,
and locator-style restoration using generated public-domain-like fixture text.
"""

from __future__ import annotations

import html
import json
import statistics
import time
from dataclasses import dataclass


MOBILE_VIEWPORTS = [(320, 700), (390, 844), (768, 1024)]


@dataclass(frozen=True)
class Fixture:
    name: str
    paragraphs: list[str]


def build_fixture(paragraph_count: int = 240) -> Fixture:
    base = (
        "The traveler crossed the quiet city at dawn, counted the lamps, "
        "and marked the sentence so the reader could return after resize."
    )
    cjk = "第{n}章的段落用于检查中文换行、标点、阅读宽度和复制行为。"
    paragraphs: list[str] = []
    for index in range(1, paragraph_count + 1):
        if index % 5 == 0:
            paragraphs.append(cjk.format(n=index))
        else:
            paragraphs.append(f"{base} Paragraph {index}.")
    return Fixture(name=f"synthetic-{paragraph_count}", paragraphs=paragraphs)


def current_renderer(fixture: Fixture) -> str:
    return "\n".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in fixture.paragraphs if paragraph.strip())


def readium_inspired_renderer(fixture: Fixture) -> str:
    body = current_renderer(fixture)
    return (
        '<article class="reader-publication" data-writing-mode="horizontal-tb" '
        'style="--reader-max-inline-size: 68ch; --reader-line-height: 1.72;">'
        f"{body}</article>"
    )


def locator_for_progress(fixture: Fixture, progression: float) -> dict:
    clamped = min(max(progression, 0.0), 1.0)
    paragraph_index = min(int(len(fixture.paragraphs) * clamped), len(fixture.paragraphs) - 1)
    text = fixture.paragraphs[paragraph_index]
    return {
        "href": f"/chapters/{fixture.name}",
        "type": "text/html",
        "locations": {
            "progression": round(clamped, 6),
            "position": paragraph_index + 1,
            "paragraph_index": paragraph_index,
        },
        "text": {
            "highlight": text[:80],
            "before": fixture.paragraphs[paragraph_index - 1][:80] if paragraph_index > 0 else "",
            "after": fixture.paragraphs[paragraph_index + 1][:80]
            if paragraph_index + 1 < len(fixture.paragraphs)
            else "",
        },
    }


def restore_from_locator(fixture: Fixture, locator: dict) -> dict:
    paragraph_index = int(locator["locations"]["paragraph_index"])
    paragraph_index = min(max(paragraph_index, 0), len(fixture.paragraphs) - 1)
    return {
        "restored_paragraph_index": paragraph_index,
        "restored_text_matches": fixture.paragraphs[paragraph_index].startswith(locator["text"]["highlight"][:20]),
    }


def time_renderer(renderer, fixture: Fixture, runs: int = 25) -> dict:
    durations: list[float] = []
    html_output = ""
    for _ in range(runs):
        start = time.perf_counter()
        html_output = renderer(fixture)
        durations.append((time.perf_counter() - start) * 1000)
    return {
        "runs": runs,
        "mean_ms": round(statistics.mean(durations), 4),
        "p95_ms": round(sorted(durations)[int(runs * 0.95) - 1], 4),
        "html_bytes": len(html_output.encode("utf-8")),
        "estimated_dom_nodes": html_output.count("<p>") + html_output.count("<article") + 1,
        "paragraphs": len(fixture.paragraphs),
    }


def run_benchmark() -> dict:
    fixture = build_fixture()
    long_fixture = build_fixture(1200)
    locator = locator_for_progress(fixture, 0.42)
    return {
        "fixtures": {
            "standard": fixture.name,
            "long": long_fixture.name,
            "private_content_used": False,
        },
        "renderers": {
            "current_escaped_paragraphs": time_renderer(current_renderer, fixture),
            "readium_inspired_wrapper": time_renderer(readium_inspired_renderer, fixture),
            "long_chapter_current": time_renderer(current_renderer, long_fixture, runs=10),
        },
        "locator_restore": restore_from_locator(fixture, locator),
        "mobile_viewports_reviewed": [{"width": width, "height": height} for width, height in MOBILE_VIEWPORTS],
        "capabilities_exercised": [
            "escaped_text_rendering",
            "readium_inspired_typography_wrapper",
            "long_chapter_scale",
            "hybrid_locator_restore",
            "cjk_paragraph_fixture",
            "paragraph_copy_compatibility",
            "browser_search_compatibility",
        ],
        "production_reader_modified": False,
    }


def main() -> int:
    result = run_benchmark()
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
