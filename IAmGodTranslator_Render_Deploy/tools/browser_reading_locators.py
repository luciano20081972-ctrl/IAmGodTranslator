"""Browser qualification of stable reading positions on isolated synthetic content."""
import argparse
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from qa_v11_rc2_postgres_auth import TEST_USERS, auth_headers

NOVEL = "seed-large-000"
PROGRESS_PATH = "/api/account/progress"
GUEST_KEY = f"gt-reader-position-v1:guest:{NOVEL}:1:english"
LEGACY_KEY = f"gt-reader-scroll:{NOVEL}:1:english"
DESKTOP = {"width": 1366, "height": 768}
MOBILE = {"width": 390, "height": 844}
ANCHOR = 6
PARAGRAPHS = ".reader-text [data-paragraph-index]"


def chapter_url(base_url, chapter=1):
    return f"{base_url}/#/reader/{NOVEL}/{chapter}/english"


def open_chapter(page, base_url, chapter=1):
    page.goto(chapter_url(base_url, chapter), wait_until="domcontentloaded")
    page.locator(PARAGRAPHS).first.wait_for()
    assert page.locator("#readerChapterHeading").inner_text() == f"Chapter {chapter}"


def scroll_to_paragraph(page, index):
    page.locator(PARAGRAPHS).nth(index).evaluate("""paragraph => {
        const rect = paragraph.getBoundingClientRect();
        const line = Math.min(120, Math.round(innerHeight / 4));
        window.scrollTo(0, scrollY + rect.top + rect.height / 4 - line);
    }""")


def wait_for_anchor(page, index):
    page.wait_for_function("""index => {
        const rect = document.querySelector(`.reader-text [data-paragraph-index="${index}"]`)?.getBoundingClientRect();
        const line = Math.min(120, Math.round(innerHeight / 4));
        return rect && Math.abs((line - rect.top) / rect.height - 0.25) < 0.06;
    }""", arg=index)


def wait_for_percent(page, expected):
    page.wait_for_function("""expected => {
        const total = document.documentElement.scrollHeight - innerHeight;
        return total > 0 && Math.abs(scrollY / total * 100 - expected) < 1;
    }""", arg=expected)


def input_value(page, selector, value):
    page.locator(selector).evaluate("""(input, value) => {
        input.value = value;
        input.dispatchEvent(new Event('input', {bubbles: true}));
    }""", value)


def observe_errors(page, results):
    page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
    page.on("console", lambda msg: results["console_errors"].append(
        {"text": msg.text, "url": msg.location.get("url", "")}) if msg.type == "error" else None)


def check_guest(browser, base_url, results):
    with browser.new_context(viewport=DESKTOP) as context:
        page = context.new_page()
        observe_errors(page, results)
        progress_requests = []
        page.on("request", lambda request: progress_requests.append(request.method)
                if urlsplit(request.url).path == PROGRESS_PATH else None)
        open_chapter(page, base_url)
        page.wait_for_function("Boolean(navigator.serviceWorker.controller)")
        scroll_to_paragraph(page, ANCHOR)
        page.wait_for_function("key => JSON.parse(localStorage.getItem(key))?.locator?.paragraph_index === 6", arg=GUEST_KEY)
        saved = page.evaluate("key => JSON.parse(localStorage.getItem(key))", GUEST_KEY)
        assert saved["locator"]["version"] == 1 and set(saved["locator"]) == {
            "version", "novel_id", "chapter_number", "source", "content_hash",
            "paragraph_index", "paragraph_offset", "progression",
        }

        page.reload(wait_until="domcontentloaded")
        wait_for_anchor(page, ANCHOR)
        old_line = page.locator(PARAGRAPHS).nth(ANCHOR).evaluate("(node) => getComputedStyle(node).fontSize")
        input_value(page, "#readerMenuFontSize", 27)
        assert page.locator(PARAGRAPHS).nth(ANCHOR).evaluate("(node) => getComputedStyle(node).fontSize") != old_line
        wait_for_anchor(page, ANCHOR)
        page.set_viewport_size(MOBILE)
        wait_for_anchor(page, ANCHOR)
        page.set_viewport_size(DESKTOP)
        wait_for_anchor(page, ANCHOR)

        page.goto(f"{base_url}/#/settings/reader")
        line_height = 'input[data-pref="readerLineHeight"]'
        page.locator(line_height).first.wait_for(state="attached")
        input_value(page, line_height, 2.1)
        page.locator('input[data-pref="readerTone"][value="sepia"]').evaluate("input => input.click()")
        open_chapter(page, base_url)
        wait_for_anchor(page, ANCHOR)
        assert page.locator("body").get_attribute("data-reader-tone") == "sepia"

        page.locator('#readerMenuPanel [data-go="2"]').evaluate("button => button.click()")
        page.wait_for_function("document.querySelector('#readerChapterHeading')?.textContent === 'Chapter 2'")
        assert page.evaluate("scrollY") < 10
        open_chapter(page, base_url)
        wait_for_anchor(page, ANCHOR)
        assert not progress_requests, "guest reader contacted the account progress API"

        context.set_offline(True)
        offline = context.new_page()
        offline.on("pageerror", lambda error: results["page_errors"].append(str(error)))
        open_chapter(offline, base_url)
        wait_for_anchor(offline, ANCHOR)
        assert offline.get_by_text("Offline copy", exact=True).is_visible()

    results["guest"] = {
        "paragraph_index": ANCHOR, "reload": "PASS", "font_size": "PASS", "line_spacing": "PASS",
        "desktop_mobile_desktop": "PASS", "appearance": "PASS", "chapter_navigation": "PASS",
        "offline_reopen": "PASS", "account_progress_requests": progress_requests,
    }
    return saved


def check_fallback(browser, base_url, saved, results):
    with browser.new_context(viewport=DESKTOP) as context:
        page = context.new_page()
        observe_errors(page, results)
        page.add_init_script(f"""if (!localStorage.getItem({json.dumps(LEGACY_KEY)}))
            localStorage.setItem({json.dumps(LEGACY_KEY)}, "37");""")
        open_chapter(page, base_url)
        wait_for_percent(page, 37)
        for change in ({"version": 2}, {"paragraph_index": 100000}, {"content_hash": "0" * 64},
                       {"source": "reference"}, {"progression": .80}):
            invalid = {**saved, "scroll_percent": 37, "locator": {**saved["locator"], "progression": .37, **change}}
            page.evaluate("([key, value]) => localStorage.setItem(key, JSON.stringify(value))", [GUEST_KEY, invalid])
            page.reload(wait_until="domcontentloaded")
            wait_for_percent(page, 37)
    results["fallback"] = {"legacy_percent": 37, "rejected": ["version", "paragraph index", "chapter revision", "source", "progression mismatch"]}


def check_accounts(browser, base_url, results):
    normal, translator = auth_headers("normal"), auth_headers("translator")
    user_id = TEST_USERS["normal"][0]
    chapter_one = chapter_url(base_url)
    with (browser.new_context(viewport=DESKTOP, extra_http_headers=normal) as desktop,
          browser.new_context(viewport=MOBILE, extra_http_headers=normal, is_mobile=True) as mobile):
        page = desktop.new_page()
        observe_errors(page, results)
        progress_reads = []
        page.on("request", lambda request: progress_reads.append(request.url)
                if urlsplit(request.url).path == PROGRESS_PATH and request.method == "GET" else None)
        with page.expect_response(lambda r: urlsplit(r.url).path == PROGRESS_PATH and r.request.method == "GET"):
            open_chapter(page, base_url)
        page.wait_for_function("activeReaderPosition?.userId === 'rc2-user'")
        with page.expect_response(lambda r: urlsplit(r.url).path == PROGRESS_PATH and r.request.method == "PUT") as saving:
            scroll_to_paragraph(page, ANCHOR)
        response = saving.value.json()
        assert response["ok"] and response["progress"]["locator"]["paragraph_index"] == ANCHOR
        assert response["progress"]["source"] == "english"
        open_chapter(page, base_url, 2)
        open_chapter(page, base_url)
        wait_for_anchor(page, ANCHOR)
        assert progress_reads == [f"{base_url}{PROGRESS_PATH}?novel_id={NOVEL}"]
        assert page.request.get(f"{base_url}{PROGRESS_PATH}?novel_id={NOVEL}", headers=translator).json()["progress"] is None

        desktop_page = page
        page = mobile.new_page()
        observe_errors(page, results)
        page.goto(chapter_one, wait_until="domcontentloaded")
        wait_for_anchor(page, ANCHOR)
        assert page.evaluate("innerWidth") == MOBILE["width"]
        assert page.evaluate("id => activeReaderPosition.userId === id", user_id)
        with page.expect_response(lambda r: urlsplit(r.url).path == PROGRESS_PATH and r.request.method == "PUT") as saving:
            scroll_to_paragraph(page, ANCHOR + 1)
        assert saving.value.json()["progress"]["locator"]["paragraph_index"] == ANCHOR + 1
        # Headless Chromium keeps both pages visible. Deliver the foreground event
        # explicitly while using the actual account API and independent local stores.
        with desktop_page.expect_response(lambda r: urlsplit(r.url).path == PROGRESS_PATH and r.request.method == "GET"):
            desktop_page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        wait_for_anchor(desktop_page, ANCHOR + 1)
        assert len(progress_reads) == 2
        # Attempting a protected source through the normal Reader falls back safely.
        page.goto(f"{base_url}/#/reader/partial-novel/1/reference")
        page.locator(".reader-text").get_by_text("English partial 1", exact=True).wait_for()
        assert "Reference partial 1" not in page.locator(".reader-text").inner_text()
        assert not page.locator('[data-source="reference"]').count()

    with browser.new_context(viewport=DESKTOP, extra_http_headers=translator) as authorized:
        page = authorized.new_page()
        observe_errors(page, results)
        page.goto(f"{base_url}/#/reader/partial-novel/1/reference", wait_until="domcontentloaded")
        page.locator(".reader-text").get_by_text("Reference partial 1", exact=True).wait_for()
        assert page.locator('[data-source="reference"]').count() > 0
    results["accounts"] = {"authenticated_write": "PASS", "second_device_mobile_restore": "PASS",
                           "account_isolation": "PASS", "navigation_progress_reads": 1, "foreground_progress_reads": 1,
                           "foreground_refresh": "PASS", "source_variant_permissions": "PASS"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    results = {"page_errors": [], "console_errors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=os.environ["GT_VERIFY_CHROMIUM"])
            try:
                saved = check_guest(browser, args.base_url, results)
                check_fallback(browser, args.base_url, saved, results)
                check_accounts(browser, args.base_url, results)
            finally:
                browser.close()
        assert not results["page_errors"] and not results["console_errors"], results
    finally:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
