# GodTranslator v11 Implementation Plan

Phase 0 establishes a controlled implementation plan for `v11.0.0-platform-evolution`. This plan is intentionally not a rewrite. It preserves v10 production behavior, documents the current surface area, and defines phase-by-phase implementation gates.

## Baseline Verification

- Starting production branch: `origin/main`.
- Starting production SHA: `5bf03d2e45210556c0f8cb14f61244541f6026a9`.
- Roadmap branch: `v11.0.0-platform-vision`.
- Expected roadmap foundation SHA: `f70c39394851099d603caac3f4bd9e7a4bd78f86`.
- Implementation branch: `v11.0.0-platform-evolution`.
- Implementation branch base: `origin/main`.
- Roadmap foundation was cherry-picked onto the implementation branch as `6cb757f0f29954b90965139fc0faddc714645c55`.
- `main` is not modified by this branch.
- Production deployment is not part of v11 implementation work.

## Production-Facing Architecture Inventory

### Existing And Complete

- PostgreSQL-first database abstraction with schema-qualified table names.
- Additive table creation and additive column migrations.
- Public Library, Novel Detail, Chapter List, Reader, Compare, History, Bookmarks, Favorites, and Settings routes.
- Admin login/session handling and Supabase account foundation.
- Account preferences, reading progress, reading history, bookmarks, and favorites.
- `chapter_editions` table and English-edition compatibility for existing AI translations.
- Content Import Center with JSON/file-pack preview and execute flows.
- Recovery preview/apply workflow separated from Content Import.
- Translation job creation, item persistence, pause/resume/stop/retry, leases, heartbeats, restart recovery, telemetry, and bounded worker claims.
- Admin overview, DB health, missing diagnostics, user list, translation performance, backups, restore preview, and content edition management.
- Lightweight backup manifest endpoint and JSON error handling from the production hotfix.
- Desktop website API foundation for health, auth check, sync status, import history, pack preview, and pack execute.
- Desktop Companion downloader implementation exists in the repository.

### Existing But Incomplete

- Runtime version hygiene was completed during RC1 blocker repair: backend, app label, HTML cache query strings, and desktop API labels now report `11.0.0`.
- Top navigation exists, but it does not match the v11 target. Theme is still top-level, and profile behavior is too limited.
- Command palette exists, but settings commands are mixed into the normal result list rather than separated as explicit commands.
- Home already has dashboard sections, but it is not yet the full role-aware reading dashboard.
- Settings exists, but only Appearance, Library, Reader, Accessibility, and Account are implemented.
- Reader has edition switching, bookmarks, progress persistence, focus mode, chapter drawer, keyboard shortcuts, and settings sheet, but not the full v11 reader feature set.
- Library has search, filters, cards, favorites, and coverage, but not collections/shelves/pinned/status views.
- Translation selector supports large jobs through 500, All, Custom, and ranges, but not v11 presets through 1000 or full profile UX.
- Import handles new rows and manifestless/simple imports, but not drag-and-drop, rollback planning, checksums, or background progress.
- Recovery can fill missing content, but Desktop recovery request round-trip remains incomplete as a unified product flow.
- Backup manifest is safe, but full platform backups are still synchronous and can build large payloads in memory after explicit action.
- Admin is broad, but lacks audit log, system health page depth, and some mobile operations polish.
- Desktop sync foundation exists, but secure device authorization and full sync state lifecycle are incomplete.

### Missing

- Collections/shelves data model and UI.
- Notifications data model, preferences, and surfaces.
- Audit log table and event recording.
- Backup background jobs with table progress and bounded streaming/chunked payload creation.
- Persistent cross-device reader setting sync beyond current account preferences.
- Highlights/notes data model and reader UI.
- Translation profile management UI and profile persistence beyond current settings scaffolding.
- Device authorization/token flow for Desktop Companion.
- Global Search API that covers novels, authors, tags, chapters, jobs, imports, recovery, and commands efficiently.
- Mobile bottom navigation and full accessibility audit automation.

### Deferred With Justification

- Comments: explicitly future-facing and should not block v11 platform foundation.
- Silent desktop auto-update: unsafe without signing, rollback, and user consent design.
- Provider-specific discount claims or batching optimizations: deferred unless backed by a real provider feature and measured performance gain.
- Full offline cache: requires storage quotas, invalidation, privacy rules, and should follow reader persistence foundations.
- Transactional rollback execution for imports: only safe after import history and change journaling are designed.

## Phase Requirement Mapping

### Phase 0: Baseline Audit And Release Plan

| Requirement | Status | Notes |
| --- | --- | --- |
| Verify branch and main ancestry | Existing and complete | Implementation branch is based on `origin/main`; roadmap foundation cherry-picked. |
| Inspect architecture | Existing and complete | Inventory above covers website, database, admin, import, recovery, backups, translation, desktop API, and desktop code. |
| Verify runtime labels | Existing and complete after RC1 QA | `APP_VERSION`, backend, HTML cache strings, and desktop API labels now report `11.0.0`. |
| Identify stale TODOs/dead UI/regressions/duplication | Existing but incomplete | Known baseline issues listed below. |
| Create implementation plan | Existing and complete | This file is the Phase 0 deliverable. |
| Baseline syntax and smoke checks | Existing and complete after QA | See Phase 0 QA section. |

### Phase 1: Navigation, Profile, Settings, And Home

| Requirement | Status | Notes |
| --- | --- | --- |
| Top navigation with Brand, Home, Library, Continue Reading, Search, relevant Activity, Profile | Existing but incomplete | Brand/Home/Library/Search exist; Continue Reading/Profile menu need v11 work; Theme should move out of top nav. |
| Profile menu with account, reading, desktop, settings, translator/admin, admin exit, sign out | Existing but incomplete | Account settings page includes some links; true dropdown/avatar menu missing. |
| Keep sign out and Admin exit separate | Existing but incomplete | Both actions exist, but profile menu separation needs polish. |
| Role-aware Home dashboard | Existing but incomplete | Home already has reading-focused sections and some role logic; needs full section set and admin privacy gates. |
| Settings sections and Basic/Advanced/Expert disclosure | Existing but incomplete | Five sections exist; v11 section list and disclosure model missing. |
| Guest local settings and account server settings | Existing and complete | Existing preferences support local and account persistence. |
| Global Ctrl+K search without mixing settings into normal novel results | Existing but incomplete | Palette exists; command grouping and result separation need work. |
| Mobile/nav/profile/search/no overflow QA | Missing | Requires responsive smoke checks after implementation. |

### Phase 2: Reader Experience

| Requirement | Status | Notes |
| --- | --- | --- |
| English/Original/Reference edition architecture | Existing and complete | Reference is protected server-side by role. |
| Internal edition metadata | Existing and complete | `chapter_editions` stores type/source metadata. |
| Public controls | Existing but incomplete | Several controls exist; Back to Top, progress, richer settings, mobile bottom controls missing. |
| Reader settings themes and typography | Existing but incomplete | Basic theme/font/density settings exist; full theme list and spacing controls missing. |
| Scroll restoration and account progress | Existing and complete | Current reader saves scroll and account progress. Needs cross-device validation. |
| Keyboard and touch-safe mobile | Existing but incomplete | Keyboard shortcuts exist; mobile-specific navigation needs work. |
| Notes/highlights/search foundations | Missing | Requires additive tables and UI. |
| Bounded loading and Reference privacy | Existing and complete | Single chapter body loads; Reference route remains protected. |

### Phase 3: Library, Collections, And Novel Dashboard

| Requirement | Status | Notes |
| --- | --- | --- |
| Library views | Existing but incomplete | Grid/list-like cards exist; compact grid/list/large cover modes need productized controls. |
| Search/sort/filter/favorites | Existing and complete | Current library supports these basics. |
| Pinned/custom collections/shelves/status | Missing | Requires additive persistence. |
| Metadata coverage and privacy | Existing but incomplete | Coverage exists; Reference must remain hidden from public views. |
| Novel Dashboard | Existing but incomplete | Detail page has cover, progress, stats, actions; needs collections, activity, translation summary depth. |
| No hardcoded I Am God | Existing and complete | Current routes are multi-novel. |

### Phase 4: Translation Workspace And Performance

| Requirement | Status | Notes |
| --- | --- | --- |
| Preserve scheduler safety | Existing and complete | Claims, leases, heartbeats, restart recovery, budget stops, and telemetry isolation exist. |
| Job sizes through 1000 and All | Existing but incomplete | Current UI/backend support up to 500, All, Custom, and ranges. |
| Server-side All selection | Existing and complete | Selection happens server-side. |
| Translation presets with backend effects | Existing but incomplete | Modes exist; v11 named presets need real backend mapping. |
| Estimate detail | Existing but incomplete | Current estimate includes many counts and cost fields; Reference and worker details need richer display. |
| Activity Center and persistent job banner | Existing but incomplete | Jobs/activity exist; persistent banner across navigation needs work. |
| Controlled real benchmark disabled by default | Existing and complete | Endpoint is Admin-only and disabled by default. |
| Performance optimization only when measured | Existing and complete as principle | v10.4 telemetry exists; v11 changes must keep fixture measurements. |

### Phase 5: Content Import, Editions, And Recovery

| Requirement | Status | Notes |
| --- | --- | --- |
| New/existing novel and content types | Existing and complete | Original, English, Reference, metadata, cover, glossary supported. |
| Sources including TXT, ZIP, packs | Existing but incomplete | Multiple files and ZIP supported; drag-and-drop/folder via desktop needs polish. |
| Preview detail | Existing but incomplete | Rows to create/content/duplicates/invalids exist; checksum and rollback planning missing. |
| Add-missing default and overwrite confirmation | Existing but incomplete | Options exist; confirmation flow needs stronger UX. |
| Zero-row novel empty state | Existing and complete | v10.5 hotfix added clear state. |
| Admin default English edition | Existing and complete | Endpoint and manager exist. |
| Recovery never creates rows | Existing and complete | Needs continued QA as import evolves. |
| Import history and rollback planning | Existing but incomplete | History exists; rollback planning missing. |

### Phase 6: Desktop Companion And Website Sync

| Requirement | Status | Notes |
| --- | --- | --- |
| Preserve Playwright downloader controls | Existing and complete | Desktop downloader completion exists. |
| Desktop modules | Existing but incomplete | Downloader, packs, settings, logs exist; unified dashboard/sync flows need polish. |
| Multiple queued novels and bounded browsers | Existing but incomplete | Needs explicit audit in desktop code. |
| CAPTCHA handling | Existing and complete as policy | Must not bypass anti-bot; user-visible browser remains required when challenged. |
| Website sync upload/preview/execute | Existing but incomplete | API foundation exists; full sync lifecycle and secure auth missing. |
| Secure desktop token/device auth | Missing | Must be designed before storing any credentials. |
| Recovery round trip | Existing but incomplete | Pieces exist; unified flow missing. |

### Phase 7: Backups, Restore, And Operations

| Requirement | Status | Notes |
| --- | --- | --- |
| Aggregate-only manifest | Existing and complete | Production hotfix implements this. |
| Full backups explicit only | Existing and complete | Create/download are explicit actions. |
| Background full backup jobs | Missing | Needed for Render memory constraints. |
| Bounded/chunked full backup memory | Missing | Current full backup still builds full payload in RAM. |
| Safe restore stages | Existing but incomplete | Preview exists; background apply and verify stages missing. |
| Admin operations center | Existing but incomplete | Many tabs exist; Audit Log/System Health need additions. |
| Safe audit events | Missing | Requires additive table and event writer. |

### Phase 8: Mobile, Accessibility, Notifications, And Polish

| Requirement | Status | Notes |
| --- | --- | --- |
| Mobile bottom navigation and compact header | Missing | Current responsive CSS needs audit before implementation. |
| Reader mobile optimization | Existing but incomplete | Functional, but bottom controls/touch design need work. |
| Admin mobile tables | Existing but incomplete | Responsive tables exist; operational tabs need mobile QA. |
| Accessibility | Existing but incomplete | Semantic HTML and labels exist in places; focus, screen-reader, reduced-motion audit missing. |
| Notifications | Missing | Requires data model, preferences, and surfaces. |
| Micro-UX consistency | Existing but incomplete | Many states exist; raw `alert()` and uneven disabled explanations remain. |
| Visual system | Existing but incomplete | Needs hierarchy, icons, spacing, theme work. |

### Phase 9: Final Integration QA

| Requirement | Status | Notes |
| --- | --- | --- |
| End-to-end isolated workflows | Missing | Must follow all phase implementations. |
| Full QA suite | Missing | Phase 9 output depends on phases 1-8. |
| `V11_RELEASE_REPORT.md` | Missing | Final QA deliverable only after implementation phases. |
| No deploy/merge/OpenAI/production writes | Existing and complete as rule | Must be re-verified at every phase. |

## Known Baseline Issues

- `templates/index.html` cache strings were updated to `?v=11.0.0` during RC1 QA.
- `/api/desktop/health` now reports `desktop_api: 11.0.0`.
- Header still exposes `Theme` as a top-level action.
- Header account chip links directly to Admin when admin mode is active instead of a true profile menu.
- Command palette includes `Open Settings` in the same command list as primary navigation and novel/chapter results.
- Settings is named `Personalization Studio`, which undersells the v11 settings application goal.
- Settings sections are incomplete: Translation, Desktop, Downloads, Notifications, Keyboard, Privacy, Advanced, and Developer are missing.
- `alert()` is still used in a few workflows, including novel save, recovery import, and account auth errors.
- Translation profile UI text exists, but durable profile management remains incomplete.
- Full platform backup creation is still synchronous and memory-heavy after explicit user action.
- Audit log and notifications are missing.
- Collections and shelves are missing.
- Desktop sync has API foundations but not secure device authorization or full lifecycle state.

## Database Migration Policy

- All v11 migrations must be additive and idempotent.
- Keep `godtranslator_v10` schema unless a specific additive requirement justifies otherwise.
- Candidate additive tables:
  - `collections`
  - `collection_items`
  - `notifications`
  - `audit_events`
  - `reader_highlights`
  - `reader_notes`
  - `desktop_devices`
  - `desktop_sync_jobs`
  - `backup_jobs`
  - `backup_job_items`
- Candidate additive columns:
  - Reader preference fields only if not already covered by preferences JSON.
  - Novel metadata/status fields only when JSON metadata cannot support efficient filtering.
- No destructive migration is currently required.

## QA Strategy By Phase

- Use isolated SQLite fixtures for fast local checks.
- Use PostgreSQL SQL compatibility checks where SQL differs or migrations are involved.
- Use fake providers for translation jobs.
- Keep OpenAI disabled unless a later explicit benchmark task requests it.
- Never use production `DATABASE_URL` for write tests.
- Run syntax checks after every phase:
  - Python compile for touched Python modules/tools.
  - `node --check` for `static/app.js`.
- Run targeted QA after every phase:
  - Desktop integration QA when touching desktop/API.
  - Translation selector/scheduler/performance QA when touching translation.
  - Content import QA when touching import/recovery.
  - Backup manifest/full backup QA when touching backups.
  - Browser/mobile smoke after major UI phases when practical.

## Phase 0 QA Results

- Branch ancestry: `origin/main` is an ancestor of the implementation branch.
- Python compile passed for:
  - `app/main.py`
  - `app/db.py`
  - `app/content_import.py`
  - `app/recovery.py`
  - `tools/qa_v10_6_desktop_integration.py`
  - `tools/qa_v10_6_translation_selector.py`
  - `tools/qa_v10_5_content_import_editions.py`
  - `tools/qa_backup_manifest_hotfix.py`
- JavaScript syntax passed for `static/app.js`.
- Desktop website integration QA passed: 4 tests.
- Backup manifest hotfix QA passed with isolated fixtures; 908 large-text chapters returned a small manifest response and did not serialize chapter/edition text.
- Translation selector QA passed with isolated fixtures for 25/50/100/200/500, All, Custom, ranges, pause/resume/cancel, budget stop, restart recovery, and bounded concurrency.
- Content Import and Editions QA passed: 21 tests.
- No OpenAI key was used by QA.
- No production `DATABASE_URL` was used by write tests.

## Next Phase Acceptance Criteria

Phase 1 is safe to start only if:

- The implementation branch remains ahead of `origin/main` and not merged into `main`.
- The worktree is clean after Phase 0 commit.
- Baseline syntax checks pass.
- No production data, deployment, or OpenAI call occurred.
- Phase 1 changes can be kept to navigation/profile/settings/home without touching translation scheduling, import execution, backup generation, or desktop downloader internals.
