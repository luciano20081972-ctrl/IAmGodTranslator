"""Cycle 5 visual QA and screenshot capture for the Dark Hour interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROUTES = [
    ("desktop-home", "#/home", {"width": 1366, "height": 900}),
    ("desktop-library", "#/library", {"width": 1366, "height": 900}),
    ("desktop-novel", "#/novel/seed-large-000", {"width": 1366, "height": 900}),
    ("desktop-reader", "#/reader/seed-large-000/1/english", {"width": 1366, "height": 900}),
    ("desktop-search", "#/home", {"width": 1366, "height": 900}, "search"),
    ("desktop-add-novel", "#/novels/add", {"width": 1366, "height": 900}),
    ("desktop-translate", "#/translate/seed-large-000", {"width": 1366, "height": 900}),
    ("desktop-settings", "#/settings", {"width": 1366, "height": 900}),
    ("desktop-admin", "#/admin", {"width": 1366, "height": 900}),
    ("mobile-home-320", "#/home", {"width": 320, "height": 700}),
    ("mobile-library-390", "#/library", {"width": 390, "height": 844}),
    ("mobile-reader-390", "#/reader/seed-large-000/1/english", {"width": 390, "height": 844}),
    ("mobile-nav-320", "#/home", {"width": 320, "height": 700}, "menu"),
    ("mobile-add-novel-390", "#/novels/add", {"width": 390, "height": 844}),
]


def wait_for_route_settle(page: Any) -> None:
    for _ in range(30):
        text = page.locator("body").inner_text(timeout=5000)
        if not any(marker in text for marker in ("Opening ", "Loading ", "Preparing ")):
            return
        page.wait_for_timeout(200)


def run(base_url: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots: list[str] = []
    failures: list[str] = []
    console_errors: list[str] = []
    metrics: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for entry in ROUTES:
            name, route, viewport, *mode = entry
            context = browser.new_context(
                viewport=viewport,
                is_mobile=viewport["width"] < 700,
                device_scale_factor=1,
            )
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(f"{name}: {message.text}") if message.type == "error" else None)
            page.goto(f"{base_url.rstrip('/')}/{route}", wait_until="networkidle")
            wait_for_route_settle(page)
            if mode and mode[0] == "search":
                page.locator("#globalSearchBtn").click()
                page.locator("#commandInput").fill("chapter")
                page.wait_for_timeout(250)
            if mode and mode[0] == "menu":
                page.locator("[data-mobile-menu]").click()
                page.wait_for_timeout(250)
            horizontal_overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            if horizontal_overflow:
                failures.append(f"{name} has horizontal overflow")
            touch_issues = page.evaluate(
                """() => [...document.querySelectorAll('button,a,input,select,textarea')]
                  .filter((node) => {
                    const rect = node.getBoundingClientRect();
                    const closedDetails = node.closest('details:not([open])');
                    const hidden = node.closest('[hidden], [aria-hidden="true"]') || closedDetails;
                    const visible = !hidden && rect.width > 0 && rect.height > 0;
                    return visible && rect.height < 36 && !node.closest('.reader-text');
                  })
                  .map((node) => node.textContent.trim() || node.getAttribute('aria-label') || node.id || node.tagName)
                  .slice(0, 8)
                """
            )
            if touch_issues and viewport["width"] < 700:
                failures.append(f"{name} has small touch targets: {touch_issues}")
            path = output_dir / f"{name}.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots.append(str(path))
            metrics.append(
                {
                    "name": name,
                    "route": route,
                    "viewport": viewport,
                    "dom_nodes": page.evaluate("document.querySelectorAll('*').length"),
                    "horizontal_overflow": horizontal_overflow,
                    "screenshot": str(path),
                }
            )
            context.close()
        browser.close()

    return {
        "ok": not failures and not console_errors,
        "failures": failures,
        "console_errors": console_errors,
        "screenshots": screenshots,
        "metrics": metrics,
        "production_content_used": False,
        "production_database_used": False,
        "openai_called": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8007")
    parser.add_argument("--output-dir", default="IAmGodTranslator_Render_Deploy/qa_screenshots_v11_6_cycle5")
    args = parser.parse_args()
    result = run(args.base_url, Path(args.output_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
