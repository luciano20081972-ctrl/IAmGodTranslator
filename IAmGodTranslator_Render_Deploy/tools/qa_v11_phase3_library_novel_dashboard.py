from __future__ import annotations

import tempfile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import Database, coverage_percent  # noqa: E402

APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")


def require(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)


def coverage_regression_fixture() -> dict[str, object]:
    db_path = Path(tempfile.gettempdir()) / "gt-v11-coverage-regression.db"
    if db_path.exists():
        db_path.unlink()
    db = Database(f"sqlite:///{db_path}")
    db.initialize()

    db.save_novel_metadata("duplicate-editions", {"title": "Duplicate Editions"})
    for chapter in range(1, 4):
        db.upsert_chapter("duplicate-editions", chapter, f"Chapter {chapter}", f"Original {chapter}", None, f"English {chapter}", ai_model="fixture")
    with db.connect() as conn:
        db._upsert_english_edition_conn(conn, "duplicate-editions", 1, "Official one", edition_type="Official", edition_key="official")
        db._upsert_english_edition_conn(conn, "duplicate-editions", 1, "Edited one", edition_type="Edited", edition_key="edited", is_default=False)
    duplicate = db.novel("duplicate-editions")
    require("duplicate editions do not exceed 100", duplicate["translation_coverage"] == 100)
    require("duplicate editions use chapter inventory", duplicate["coverage_chapter_basis"] == 3)

    db.save_novel_metadata("english-without-original", {"title": "English Without Original"})
    for chapter in range(1, 476):
        original = f"Original {chapter}" if chapter <= 99 else None
        db.upsert_chapter("english-without-original", chapter, f"Chapter {chapter}", original, None, f"English {chapter}", ai_model="fixture")
    imported = db.novel("english-without-original")
    require("imported English denominator uses chapter rows", imported["coverage_chapter_basis"] == 475)
    require("imported English coverage capped", imported["translation_coverage"] == 100)
    require("coverage percent helper clamps", coverage_percent(475, 99) == 100)

    db.save_novel_metadata("expected-range", {"title": "Expected Range", "reference_target_start": 1, "reference_target_end": 480})
    for chapter in range(1, 476):
        db.upsert_chapter("expected-range", chapter, f"Chapter {chapter}", f"Original {chapter}", None, f"English {chapter}", ai_model="fixture")
    expected = db.novel("expected-range")
    require("expected range denominator", expected["coverage_chapter_basis"] == 480)
    require("expected range coverage", expected["translation_coverage"] == 99)

    db.save_novel_metadata("zero-no-range", {"title": "Zero No Range"})
    zero = db.novel("zero-no-range")
    require("zero chapters no division", zero["translation_coverage"] == 0 and zero["coverage_chapter_basis"] == 0)

    db.save_novel_metadata("zero-with-range", {"title": "Zero With Range", "reference_target_start": 1, "reference_target_end": 10})
    zero_expected = db.novel("zero-with-range")
    require("zero chapters expected denominator", zero_expected["coverage_chapter_basis"] == 10 and zero_expected["translation_coverage"] == 0)

    return {
        "duplicate_editions": duplicate["translation_coverage"],
        "english_without_original_basis": imported["coverage_chapter_basis"],
        "expected_range_basis": expected["coverage_chapter_basis"],
        "zero_no_range": zero["coverage_chapter_basis"],
        "zero_with_range": zero_expected["coverage_chapter_basis"],
    }


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
    require("coverage denominator helper", "function coverageDenominator" in APP_JS and "coverage_chapter_basis" in APP_JS)
    require("coverage no original denominator label", "English coverage: ${pct}% · ${novel.english_count ?? novel.ai_count ?? 0}/${novel.original_count || 0}" not in APP_JS)

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

    coverage = coverage_regression_fixture()

    print(
        {
            "ok": True,
            "library_views": "passed",
            "filters_and_collections": "passed",
            "novel_dashboard": "passed",
            "coverage_regressions": coverage,
            "reference_privacy": "passed",
            "responsive_static_guards": "passed",
        }
    )


if __name__ == "__main__":
    main()
