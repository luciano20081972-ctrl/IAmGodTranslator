from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "app.js"
INDEX_HTML = ROOT / "templates" / "index.html"
VENDOR_JS = ROOT / "static" / "vendor" / "minisearch" / "minisearch-7.2.0.min.js"
LICENSE = ROOT / "static" / "vendor" / "minisearch" / "LICENSE"
REPORT = ROOT / "V11_4_MINISEARCH_IMPLEMENTATION.md"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"

EXPECTED_VENDOR_SHA256 = "8a05b42785db448f2c19e24a6a2107204c825565fe4f95aa69b79652baf26e82"
EXPECTED_LICENSE_SHA256 = "70d37354d6395629fb99edb28cb37a5d356ffa24a48cd02a5def5b83a300a899"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


def adapter_block(app_js: str) -> str:
    start = app_js.index("function miniSearchConstructor()")
    end = app_js.index("function numberOrNull")
    return app_js[start:end]


def main() -> None:
    app_js = read(APP_JS)
    index_html = read(INDEX_HTML)
    adapter = adapter_block(app_js)

    require(VENDOR_JS.exists(), "MiniSearch browser artifact is vendored locally")
    require(LICENSE.exists(), "MiniSearch license is vendored locally")
    require(sha256(VENDOR_JS) == EXPECTED_VENDOR_SHA256, "MiniSearch browser artifact checksum matches the recorded release artifact")
    require(sha256(LICENSE) == EXPECTED_LICENSE_SHA256, "MiniSearch license checksum matches the npm package license")
    require("MiniSearch=e()" in read(VENDOR_JS), "Vendored artifact exposes the UMD MiniSearch global")
    license_text = read(LICENSE)
    require("Permission is hereby granted, free of charge" in license_text and "THE SOFTWARE IS PROVIDED" in license_text, "Vendored license contains MIT grant and warranty text")

    require("/static/vendor/minisearch/minisearch-7.2.0.min.js?v=7.2.0" in index_html, "MiniSearch is loaded from local static vendor path")
    require("cdn.jsdelivr.net/npm/minisearch" not in index_html.lower(), "MiniSearch is not loaded from a runtime CDN")

    require("SEARCH_LIBRARY_FIELDS" in app_js and "SEARCH_CHAPTER_FIELDS" in app_js, "Search field allow-lists are explicit")
    require("function buildMiniSearchRuntime" in adapter, "MiniSearch index construction is isolated")
    require("function fallbackSearchDocs" in adapter, "Fallback substring search is available")
    require("warnMiniSearchUnavailable" in adapter, "Missing MiniSearch has a debug-only diagnostic path")
    require("searchLibraryNovels(filteredNovels" in app_js, "Library filters are applied before MiniSearch ranking")
    require("limit=${CHAPTER_SEARCH_INDEX_LIMIT}&offset=0&view=" in app_js, "Chapter metadata is loaded once per view for client-side ranking")
    require("state.chapters = searched.chapters.slice" in app_js, "Chapter search results are paginated after ranking")
    require("chapterSearchStatusText" in app_js and "librarySearchStatus" in app_js, "Search result counts are exposed through live status text")
    require("clearLibrarySearch" in app_js and "clearChapterSearch" in app_js, "Library and chapter searches provide clear controls")

    forbidden_adapter_terms = [
        "reference_text",
        "original_text",
        "ai_text",
        "english_text",
        "prompt",
        "api_key",
        "authorization",
        "cookie",
        "password",
        "token",
    ]
    for term in forbidden_adapter_terms:
        require(term not in adapter.lower(), f"Search adapter does not index sensitive field: {term}")

    require(REPORT.exists(), "v11.4 implementation report exists")
    report_text = read(REPORT)
    require(EXPECTED_VENDOR_SHA256 in report_text, "Implementation report records vendored browser checksum")
    require("registry.npmjs.org/minisearch/-/minisearch-7.2.0.tgz" in report_text, "Implementation report records npm tarball source")
    require(NOTICES.exists(), "third-party notices file exists")
    require("MiniSearch" in read(NOTICES) and "MIT" in read(NOTICES), "third-party notices include MiniSearch and MIT attribution")

    print("V11.4 MiniSearch QA passed.")


if __name__ == "__main__":
    main()
