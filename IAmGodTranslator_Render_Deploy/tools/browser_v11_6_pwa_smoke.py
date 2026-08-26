"""Playwright smoke for the v11.6 app shell and PWA registration."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from playwright.sync_api import sync_playwright


def run(base_url: str) -> dict[str, Any]:
    errors: list[str] = []
    requests: list[str] = []
    responses: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        page = context.new_page()
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url))
        page.on(
            "response",
            lambda response: responses.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "cache_control": response.headers.get("cache-control", ""),
                    "content_encoding": response.headers.get("content-encoding", ""),
                }
            ),
        )

        start = time.perf_counter()
        page.goto(f"{base_url.rstrip('/')}/#/home", wait_until="networkidle")
        first_load_ms = round((time.perf_counter() - start) * 1000, 2)
        first_navigation_requests = list(requests)
        title = page.title()
        manifest_href = page.locator('link[rel="manifest"]').get_attribute("href")

        page.reload(wait_until="networkidle")
        controlled = page.evaluate("Boolean(navigator.serviceWorker && navigator.serviceWorker.controller)")
        registrations = page.evaluate(
            "navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(items => items.length) : Promise.resolve(0)"
        )

        browser.close()

    api_paths: dict[str, int] = {}
    for url in first_navigation_requests:
        if "/api/" not in url:
            continue
        path = "/" + url.split("/", 3)[3]
        api_paths[path] = api_paths.get(path, 0) + 1
    duplicate_api_paths = {path: count for path, count in api_paths.items() if count > 1}
    api_cached = [
        item
        for item in responses
        if "/api/" in item["url"] and "no-store" not in item["cache_control"]
    ]
    return {
        "ok": not errors and title and manifest_href == "/manifest.webmanifest" and registrations >= 1 and not api_cached and not duplicate_api_paths,
        "title": title,
        "first_load_ms": first_load_ms,
        "request_count": len(requests),
        "first_navigation_api_request_counts": api_paths,
        "first_navigation_duplicate_api_paths": duplicate_api_paths,
        "service_worker_controlled_after_reload": controlled,
        "service_worker_registrations": registrations,
        "manifest_href": manifest_href,
        "console_errors": errors,
        "api_responses_without_no_store": api_cached,
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
