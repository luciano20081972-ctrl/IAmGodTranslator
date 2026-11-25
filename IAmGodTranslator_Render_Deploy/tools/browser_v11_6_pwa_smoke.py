"""Playwright smoke for the v11.6 app shell and PWA registration."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from playwright.sync_api import sync_playwright


def upgrade_preserved_reader_data(page: Any) -> bool:
    return page.evaluate("""async () => {
        const keys = await caches.keys();
        if (keys.includes('iagt-app-shell-11.6.1') || !keys.includes('neighbor')) return false;
        const marker = await caches.match('/', {cacheName:'neighbor'});
        if (!marker || await marker.text() !== 'neighbor sentinel') return false;
        if (await readPersistentChapter('sample', 1, 'english') !== null) return false;
        state.account = {user_id:'fixture'};
        try { return (await readPersistentChapter('sample', 1, 'english'))?.text === 'fixture marker'; }
        finally { state.account = null; }
    }""")


def run(base_url: str) -> dict[str, Any]:
    errors: list[str] = []
    requests: list[str] = []
    responses: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=os.getenv("GT_VERIFY_CHROMIUM"))
        context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        if os.getenv("GT_VERIFY_CHROMIUM"):
            context.route("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2",
                          lambda route: route.fulfill(content_type="application/javascript", body=""))
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

        if os.getenv("GT_VERIFY_SCREENSHOTS"):
            page.goto(f"{base_url}/manifest.webmanifest")
            page.evaluate("""async () => {
                await navigator.serviceWorker.register('/fixture-prior-sw.js');
                await navigator.serviceWorker.ready;
                await caches.open('iagt-app-shell-11.6.1');
                const neighbor = await caches.open('neighbor');
                await neighbor.put('/', new Response('neighbor sentinel'));
                const db = await new Promise((resolve, reject) => {
                    const req = indexedDB.open('iagt-reader-cache-v1', 1);
                    req.onupgradeneeded = () => {
                        const store = req.result.createObjectStore('chapters', {keyPath: 'key'});
                        store.createIndex('namespace', 'namespace');
                        store.createIndex('lastAccessedAt', 'lastAccessedAt');
                    };
                    req.onsuccess = () => resolve(req.result);
                    req.onerror = () => reject(req.error);
                });
                await new Promise((resolve, reject) => {
                    const tx = db.transaction('chapters', 'readwrite');
                    tx.objectStore('chapters').put({key:'user:fixture:sample:1:english',
                        namespace:'user:fixture', fetchedAt:Date.now(), payload:{text:'fixture marker'}});
                    tx.oncomplete = resolve;
                    tx.onerror = () => reject(tx.error);
                });
                db.close();
            }""")

        start = time.perf_counter()
        page.goto(f"{base_url.rstrip('/')}/#/home", wait_until="networkidle")
        first_load_ms = round((time.perf_counter() - start) * 1000, 2)
        first_navigation_requests = list(requests)
        title = page.title()
        manifest_href = page.locator('link[rel="manifest"]').get_attribute("href")

        page.wait_for_function("navigator.serviceWorker.controller?.scriptURL === location.origin + '/sw.js'")
        page.reload(wait_until="networkidle")
        controlled = page.evaluate("Boolean(navigator.serviceWorker && navigator.serviceWorker.controller)")
        registrations = page.evaluate(
            "navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(items => items.length) : Promise.resolve(0)"
        )

        if os.getenv("GT_VERIFY_SCREENSHOTS"):
            assert upgrade_preserved_reader_data(page), "worker upgrade did not preserve Cache Storage and Reader isolation"
            page.goto(f"{base_url}/#/settings/privacy")
            page.get_by_role("button", name="Clear Offline Reader Cache").click()
            page.get_by_text("Offline reader cache cleared.", exact=True).wait_for()
            assert page.evaluate("""async () => {
                state.account = {user_id:'fixture'};
                try { return await readPersistentChapter('sample', 1, 'english') === null; }
                finally { state.account = null; }
            }"""), "offline clear retained the fixture record"
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
        "ok": controlled and not errors and title and manifest_href == "/manifest.webmanifest" and registrations >= 1 and not api_cached and not duplicate_api_paths,
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
