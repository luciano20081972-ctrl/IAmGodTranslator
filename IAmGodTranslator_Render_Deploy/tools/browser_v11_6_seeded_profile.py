"""Browser profile for v11.6 seeded Library/Reader scale checks."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from playwright.sync_api import sync_playwright


def wait_for_route_settle(page: Any) -> None:
    for _ in range(20):
        text = page.locator("body").inner_text(timeout=5000)
        if not any(marker in text for marker in ("Opening ", "Loading chapters", "Opening library")):
            return
        page.wait_for_timeout(250)


def measure_route(page: Any, base_url: str, route: str) -> dict[str, Any]:
    requests: list[str] = []
    errors: list[str] = []

    def on_request(request: Any) -> None:
        requests.append(request.url)

    def on_console(message: Any) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("request", on_request)
    page.on("console", on_console)
    start = time.perf_counter()
    page.goto(f"{base_url.rstrip('/')}/{route}", wait_until="networkidle")
    wait_for_route_settle(page)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    dom_nodes = page.evaluate("document.querySelectorAll('*').length")
    visible_text = page.locator("body").inner_text(timeout=5000)[:300]
    page.remove_listener("request", on_request)
    page.remove_listener("console", on_console)
    api_requests = [url for url in requests if "/api/" in url]
    return {
        "route": route,
        "elapsed_ms": elapsed_ms,
        "request_count": len(requests),
        "api_request_count": len(api_requests),
        "api_paths": sorted({"/" + url.split("/", 3)[3] for url in api_requests}),
        "dom_nodes": dom_nodes,
        "console_errors": errors,
        "visible_text_sample": visible_text,
    }


def run(base_url: str) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        page = context.new_page()
        page.goto(f"{base_url.rstrip('/')}/#/home", wait_until="networkidle")
        page.evaluate("localStorage.clear()")
        routes = [
            "#/home",
            "#/library",
            "#/novel/seed-large-000",
            "#/chapters/seed-large-000",
            "#/reader/seed-large-000/1/english",
            "#/reader/seed-large-000/2/english",
            "#/reader/seed-large-000/1/english",
        ]
        metrics = [measure_route(page, base_url, route) for route in routes]
        page.goto(f"{base_url.rstrip('/')}/#/chapters/seed-large-000", wait_until="networkidle")
        wait_for_route_settle(page)
        chapter_rows = page.locator(".chapter-row").count()
        has_next = page.locator("#nextPage").count() > 0
        if has_next:
            page.evaluate("document.querySelector('#nextPage')?.click()")
            page.wait_for_timeout(500)
        page_two_text = page.locator("body").inner_text(timeout=5000)
        browser.close()
    console_errors = [error for item in metrics for error in item["console_errors"]]
    return {
        "ok": not console_errors and chapter_rows <= 60 and ("Chapter 51" in page_two_text or "Page 2" in page_two_text),
        "condition": "seeded local benchmark",
        "metrics": metrics,
        "chapter_list_rows_visible_or_mounted": chapter_rows,
        "chapter_pagination_next_works": "Chapter 51" in page_two_text or "Page 2" in page_two_text,
        "console_errors": console_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8007")
    args = parser.parse_args()
    result = run(args.base_url)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
