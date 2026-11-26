"""Browser smoke for v11.6 Cycle 4 Reader cache, prefetch, and offline reopen."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from playwright.sync_api import sync_playwright


def wait_for_text(page: Any, text: str, timeout: int = 8000) -> None:
    page.get_by_text(text).first.wait_for(timeout=timeout)


def route_requests(page: Any, base_url: str, route: str, expected_text: str = "") -> dict[str, Any]:
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
    if expected_text:
        wait_for_text(page, expected_text)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    page.remove_listener("request", on_request)
    page.remove_listener("console", on_console)
    return {
        "route": route,
        "elapsed_ms": elapsed_ms,
        "requests": requests,
        "chapter_api_requests": [url for url in requests if "/chapters/" in url],
        "progress_writes": [url for url in requests if "/api/account/progress" in url],
        "console_errors": errors,
    }


def run(base_url: str) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.getenv("GT_VERIFY_CHROMIUM"))
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        page = context.new_page()
        page.goto(f"{base_url.rstrip('/')}/#/home", wait_until="networkidle")
        page.evaluate(
            """async () => {
                localStorage.clear();
                if (indexedDB.databases) {
                    for (const db of await indexedDB.databases()) {
                        if (db.name === "iagt-reader-cache-v1") {
                            await new Promise((resolve) => {
                                const request = indexedDB.deleteDatabase(db.name);
                                request.onsuccess = resolve;
                                request.onerror = resolve;
                                request.onblocked = resolve;
                            });
                        }
                    }
                }
            }"""
        )
        first = route_requests(page, base_url, "#/reader/seed-large-000/1/english", "Chapter 1 synthetic paragraph 1")
        page.wait_for_timeout(500)
        cached_after_first = page.evaluate(
            """async () => {
                const db = await new Promise((resolve) => {
                    const request = indexedDB.open("iagt-reader-cache-v1", 1);
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => resolve(null);
                });
                if (!db) return 0;
                return await new Promise((resolve) => {
                    const tx = db.transaction("chapters", "readonly");
                    const request = tx.objectStore("chapters").count();
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => resolve(0);
                });
            }"""
        )
        second = route_requests(page, base_url, "#/reader/seed-large-000/2/english", "Chapter 2 synthetic paragraph 1")
        previous = route_requests(page, base_url, "#/reader/seed-large-000/1/english", "Chapter 1 synthetic paragraph 1")
        for chapter in range(2, 22):
            page.goto(f"{base_url.rstrip('/')}/#/reader/seed-large-000/{chapter}/english", wait_until="networkidle")
            wait_for_text(page, f"Chapter {chapter} synthetic paragraph 1")
        dom_after_soak = page.evaluate("document.querySelectorAll('*').length")
        context.set_offline(True)
        offline_page = context.new_page()
        offline_page.goto(f"{base_url.rstrip('/')}/#/reader/seed-large-000/21/english", wait_until="domcontentloaded")
        try:
            wait_for_text(offline_page, "Chapter 21 synthetic paragraph 1", timeout=15000)
        except Exception:
            pass
        offline_text = offline_page.locator("body").inner_text(timeout=5000)
        offline_cached_records = offline_page.evaluate(
            """async () => {
                const db = await new Promise((resolve) => {
                    const request = indexedDB.open("iagt-reader-cache-v1", 1);
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => resolve(null);
                });
                if (!db) return 0;
                return await new Promise((resolve) => {
                    const tx = db.transaction("chapters", "readonly");
                    const request = tx.objectStore("chapters").count();
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => resolve(0);
                });
            }"""
        )
        browser.close()

    all_errors = first["console_errors"] + second["console_errors"] + previous["console_errors"]
    chapter_2_requests_on_next = [url for url in second["chapter_api_requests"] if "/chapters/2/" in url]
    return {
        "ok": not all_errors and len(chapter_2_requests_on_next) == 0 and dom_after_soak < 700 and "Chapter 21 synthetic paragraph 1" in offline_text,
        "first_chapter_api_requests": first["chapter_api_requests"],
        "next_chapter_api_requests": second["chapter_api_requests"],
        "previous_chapter_api_requests": previous["chapter_api_requests"],
        "cached_records_after_first_chapter": cached_after_first,
        "next_reused_prefetched_chapter_2": len(chapter_2_requests_on_next) == 0,
        "progress_writes_during_guest_navigation": len(first["progress_writes"] + second["progress_writes"] + previous["progress_writes"]),
        "dom_nodes_after_20_chapter_soak": dom_after_soak,
        "offline_cached_reopen": "Chapter 21 synthetic paragraph 1" in offline_text,
        "offline_cached_records": offline_cached_records,
        "offline_text_sample": offline_text[:400],
        "console_errors": all_errors,
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
