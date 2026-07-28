# GodTranslator v11.3 Dead-Code Audit

Branch: `v11.3.0-code-cleanup-and-open-source-audit`
Baseline main: `c1d7558b1cdfaba64ff7cd0fc730774f02e2d222`
Scope: conservative website cleanup and audit only. No database, authentication, Supabase, production data, deployment, or API response-format changes.

## Active Entry Points

| Area | Active entry point | Notes |
|---|---|---|
| FastAPI startup | `IAmGodTranslator_Render_Deploy/app/main.py` | `app = FastAPI(...)`; Render starts `uvicorn app.main:app` via `Procfile`/`render.yaml`. |
| Database/storage | `IAmGodTranslator_Render_Deploy/app/db.py` | SQLite/PostgreSQL abstraction, migrations, backup tables, translation scheduler persistence. |
| Recovery | `IAmGodTranslator_Render_Deploy/app/recovery.py` | Admin/recovery import parsing and diagnostics. |
| Content import | `IAmGodTranslator_Render_Deploy/app/content_import.py` | Simple and pack import payload parsing. |
| Web shell | `IAmGodTranslator_Render_Deploy/templates/index.html` | Single-page app shell, brand config, JS/CSS asset references. |
| Frontend app | `IAmGodTranslator_Render_Deploy/static/app.js` | Hash router, Reader, Library, Settings, Admin, Translator Workspace, Content Import UI. |
| Frontend styles | `IAmGodTranslator_Render_Deploy/static/styles.css` | v11/v11.2 responsive and reader-first presentation. |
| Deployment | `IAmGodTranslator_Render_Deploy/Procfile`, `render.yaml`, `requirements.txt` | Render production startup and dependencies. |
| QA tools | `IAmGodTranslator_Render_Deploy/tools/*.py`, `qa_v11_rc1_browser_smoke.js` | Release and phase-specific smoke/static checks. |
| Desktop Companion | `GodTranslator_Desktop_Companion/**` | Local desktop app, not Render-deployed. |

## Candidate Table

| Candidate | File | Symbol or selector | Evidence it is unused | Risk level | Recommended action | Final action |
|---|---|---|---|---|---|---|
| Legacy Home spotlight renderer | `static/app.js` | `renderLibrarySpotlight` | Repository-wide `rg` found only the function definition. Entry 2 Home uses `renderContinueReading`, `renderHomeNovelTile`, `renderRecentlyRead`, and `renderReaderDiscovery` instead. | Low | Remove | Removed |
| Legacy Home reading-stat renderer | `static/app.js` | `renderReadingStats` | Definition-only reference. Entry 2 moved analytics out of primary Home flow. | Low | Remove | Removed |
| Legacy Home recent-updates renderer | `static/app.js` | `renderRecentUpdates` | Definition-only reference. No route or template emits it. | Low | Remove | Removed |
| Legacy Home recently-added renderer | `static/app.js` | `renderRecentlyAdded` | Definition-only reference. New Home shelf orders novels through `orderHomeNovels`. | Low | Remove | Removed |
| Legacy Home next-action renderer | `static/app.js` | `renderNextAction` | Definition-only reference. Entry 2 uses `renderContinueReading` and Read routing instead. | Low | Remove | Removed |
| Old paragraph copy click handler | `static/app.js` | `copyParagraphText` | Definition-only reference. Current contextual menu calls `copyParagraphValue` through `handleParagraphMenuAction`. | Low | Remove | Removed |
| Old title-detail toggle | `static/app.js` | `toggleReaderTitleDetail` | Definition-only reference. Current Reader menu places information in the menu rather than a title-detail toggle. | Low | Remove | Removed |
| Old Reader settings sheet | `static/app.js` | `renderReaderSettingsSheet` | Definition-only reference. Entry 2 Reader uses `renderReaderMenuPanel` and Settings subpages. | Low | Remove | Removed |
| Old chapter input wrapper | `static/app.js` | `parseChapterInput` | Definition-only reference. Active translation selector uses `parseChapterInputDetailed`. | Low | Remove | Removed |
| Old job activity formatter | `static/app.js` | `jobActivityText` | Definition-only reference. Active job table/detail use `jobThroughput` and direct activity fields. | Low | Remove | Removed |
| Old Reader settings sheet styling | `static/styles.css` | `.reader-settings-sheet`, `.reader-settings-preview`, `.reader-settings-grid` | Selectors only matched CSS and the removed `renderReaderSettingsSheet` function. | Low | Remove | Removed |
| Old Reader metadata/tools/copy styling | `static/styles.css` | `.reader-meta`, `.reader-tools`, `.copy-paragraph` | Selectors had no active HTML/JS references after Entry 2 contextual menu. | Low | Remove | Removed |
| Stale Reader QA assertions | `tools/qa_v11_phase2_reader_experience.py` | `data-copy-paragraph`, `copyParagraphText`, `.reader-tools`, `.copy-paragraph`, `.reader-meta` | QA referenced pre-Entry-2 controls that are no longer active. Current Reader uses contextual paragraph actions and `reader-menu-panel`. | Low | Update QA to current behavior | Updated |
| Stale Reader settings QA assertion | `tools/qa_v11_1_reference_first_reader_polish.py` | `reader-settings-grid` | QA referenced removed sheet; current accessible controls live in Reader menu toggles and Settings pages. | Low | Update QA to current behavior | Updated |
| Python backup migration helpers | `app/db.py` | `_legacy_ai_edition_created_at_sql`, legacy migration SQL | Referenced during schema migration/idempotence paths; high blast radius. | High | Preserve | Left untouched |
| Recovery parse helpers | `app/recovery.py` | `detect_chapter_number`, `parse_zip`, `safe_zip_name` | Called through upload/recovery workflows and content import. Dynamic file inputs make static deletion unsafe. | High | Preserve | Left untouched |
| Content import simple/pack helpers | `app/content_import.py` | manifest/simple import helpers | API upload routes depend on these; user-facing import behavior must remain stable. | High | Preserve | Left untouched |
| Admin backup route helpers | `app/main.py` | backup manifest/job/restore helpers | Admin-only and production-critical; not removed even when static references are indirect. | High | Preserve | Left untouched |
| Translation scheduler helpers | `app/main.py`, `app/db.py` | claim/retry/pause/resume helpers | Background job correctness depends on scheduler invariants. | High | Preserve | Left untouched |
| Desktop Companion legacy downloader modules | `GodTranslator_Desktop_Companion/desktop_companion/legacy/**` | NovelFire legacy engine modules | Imported through adapter layer and tested by Desktop Companion foundation tests. | Medium | Preserve for separate desktop audit | Left untouched |
| Old v10/v11 report files | `IAmGodTranslator_Render_Deploy/*.md` | release and roadmap reports | Historical release documentation, not application runtime code. | Medium | Preserve unless user requests documentation pruning | Left untouched |
| v10.3 preview screenshots | `preview_screenshots_v10_3/*.png` | screenshot assets | Tracked historical artifacts. Deleting would be repository-content policy, not code cleanup. | Medium | Preserve unless user requests artifact pruning | Left untouched |

## Cleanup Statistics

| Category | Result |
|---|---:|
| JavaScript lines removed | 88 |
| CSS lines removed | 93 |
| Python lines removed | 1 net line removed across QA assertion updates |
| HTML lines removed | 0 |
| Files removed | 0 |
| Unused imports removed | 0 |
| Duplicate blocks consolidated | 0 |
| Console/debug statements removed | 0 |

## Verification Notes

- Repository-wide searches were used before removal.
- Removed JavaScript symbols had definition-only references in production files.
- Removed CSS selectors had no active HTML/JS references after the corresponding unused function was removed.
- Medium/high-risk API, database, admin, recovery, scheduler, migration, and Desktop Companion code was intentionally preserved.
