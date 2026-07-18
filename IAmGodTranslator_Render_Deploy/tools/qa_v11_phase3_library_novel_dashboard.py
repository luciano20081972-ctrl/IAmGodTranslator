from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def main() -> None:
    for option in (
        'value="grid"',
        'value="compact"',
        'value="list"',
        'value="covers"',
    ):
        require(f"library view option {option}", option in APP_JS)
    require("library view class persisted", "libraryViewClass()" in APP_JS and "gt-library-view" in APP_JS)

    for filter_value in (
        'value="favorites"',
        'value="pinned"',
        'value="completed"',
        'value="in-progress"',
        'value="want-to-read"',
        'value="paused"',
        'value="collection"',
    ):
        require(f"library filter {filter_value}", filter_value in APP_JS)
    require("archived filter admin-only", '${state.admin ? `<option value="archived"' in APP_JS)

    for key in ("pinnedNovels", "readingStatuses", "collections"):
        require(f"default preference {key}", key in APP_JS)
    require("pin helper", "function togglePinnedNovel" in APP_JS and "data-pin" in APP_JS)
    require("reading status helper", "function setNovelReadingStatus" in APP_JS and "novelReadingStatus" in APP_JS)
    require("collection shelf", "function renderCollectionShelf" in APP_JS and "createCollectionForm" in APP_JS)
    require("collection assignment", "saveNovelCollectionBtn" in APP_JS and "collectionNovelIds(item.id).has(novel.id)" in APP_JS)
    require("account preference sync", "saveRemotePreferences()" in APP_JS and "persistPreferenceState" in APP_JS)

    require("reference helper exists", "function canViewReference()" in APP_JS)
    require("reader reference uses helper", 'if (source === "reference" && canViewReference())' in APP_JS)
    require("chapter table reference uses helper", "const showReference = canViewReference();" in APP_JS)
    require("library reference metrics gated", 'canViewReference() ? metric("Reference"' in APP_JS)
    public_card_section = APP_JS.split("function renderNovelCard", 1)[1].split("function libraryStats", 1)[0]
    require("public cards do not use admin-only reference gate", 'state.admin ? metric("Reference"' not in public_card_section)

    require("novel dashboard controls", "function renderNovelDashboardControls" in APP_JS and "function bindNovelDashboardControls" in APP_JS)
    require("novel dashboard mounted", "${renderNovelDashboardControls(novel)}" in APP_JS)
    require("translation summary", "function renderTranslationSummary" in APP_JS)
    for label in ("Translated", "Remaining", "Estimated Cost", "Estimated Time", "Active Job", "Recent Throughput"):
        require(f"translation summary {label}", label in APP_JS)
    require("translation summary uses real jobs", "/api/translation/jobs?novel_id=" in APP_JS and "jobThroughput(active)" in APP_JS)
    require("no hardcoded I Am God", "I Am God" not in APP_JS)

    for css in (
        ".collection-shelf",
        ".collection-create",
        ".collection-links",
        ".novel-grid.library-view-compact",
        ".novel-grid.library-view-list",
        ".novel-grid.library-view-covers",
        ".novel-dashboard-controls",
        ".card-summary",
        ".tag-row",
    ):
        require(f"css {css}", css in CSS)
    require("mobile dashboard/library collapse", "@media (max-width: 860px)" in CSS and ".novel-dashboard-controls" in CSS)
    require("mobile collection controls", ".collection-create { grid-template-columns: 1fr; }" in CSS)

    print(
        {
            "ok": True,
            "library_views": "passed",
            "filters_and_collections": "passed",
            "novel_dashboard": "passed",
            "reference_privacy": "passed",
            "responsive_static_guards": "passed",
        }
    )


if __name__ == "__main__":
    main()
