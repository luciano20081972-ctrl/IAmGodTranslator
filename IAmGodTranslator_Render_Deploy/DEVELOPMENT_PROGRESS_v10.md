# GodTranslator v10 Development Progress

## v10.2.0 Premium Product Evolution

Branch: `v10.2.0-premium-product-evolution`

### Checkpoint 1 - Audit And Reference Range Fix

Completed:

- Created `V10_2_VISUAL_EVOLUTION_AUDIT.md`.
- Added additive novel fields `reference_target_start` and `reference_target_end`.
- Added server-side `Database.reference_range(...)` with a safe I Am God fallback of `1-434`.
- Updated Admin missing-data logic so chapters after the configured Reference range are not counted as missing Reference.
- Updated Recovery diagnostics to use the same novel-specific Reference range.
- Added Reference target start/end fields to the admin Novel form.
- Admin Missing Data now displays the active Reference target range.

QA:

- Python syntax passed for `app/db.py`, `app/main.py`, and `app/recovery.py`.
- JavaScript syntax passed for `static/app.js`.
- Fixture with 908 chapters, 906 Originals, Reference target range `1-434`, and only Chapter 362 missing Reference passed:
  - Missing Original: `176`, `177`
  - Missing Reference: `362`
  - Recovery Reference rows in range: `433`

Safety:

- No main branch changes.
- No production deploy.
- No OpenAI calls.
- No v9/public schema changes.

### Checkpoint 2 - Design System And Application Shell

Completed:

- Bumped frontend cache strings to `10.2.0`.
- Bumped FastAPI `/api/health` version to `10.2.0`.
- Added a v10.2 application shell with global search/command palette trigger, job center trigger, personalization trigger, and account chip.
- Made primary navigation authorization-aware: public users see Library/Chapters; admin-only routes appear after admin session is confirmed.
- Added Settings routes:
  - `#/settings/appearance`
  - `#/settings/reader`
  - `#/settings/account`
- Added guest-safe local personalization for themes, accents, density, card size, motion, blur, reader font, line height, paragraph spacing, reading width, reader tone, and text alignment.
- Added theme/accent CSS tokens and mobile bottom-navigation behavior.
- Added command palette search for commands, novels, and loaded chapter metadata.
- Added toast notifications for preference changes.

QA:

- Python syntax passed.
- JavaScript syntax passed.
- Shell scan confirmed v10.2 cache strings, `primaryNav`, command dialog, and settings styles.

Notes:

- Supabase Auth and database-backed user preferences are intentionally deferred to Checkpoint 3.

## v10.1.0 Full App Restoration

Branch: `v10.1.0-full-app-restoration`

Target package: `GodTranslator_v10_1_0_Full_App_Restoration.zip`

### v9/V10 Feature Inventory

KEEP AND REBUILD:

- Library, novel cards, multi-novel navigation, chapter library, reader, translation workspace, translation estimates, budget controls, persistent job status, admin dashboard, recovery center, backup/export entry points, authentication, and responsive navigation.

KEEP WITH CHANGES:

- Translation execution now writes directly to `godtranslator_v10.chapters.ai_text` and uses `translation_jobs` / `translation_job_items`.
- Backup/export is generated from PostgreSQL instead of filesystem/Supabase Storage.
- Covers are supported as URLs first through novel metadata.
- Pricing is centralized server-side and labelled approximate.
- Recovery keeps the v10.0.6 safe Reference import workflow.

DROP AS LEGACY:

- `chapter_index.json`, `counts.json`, startup hydration, startup remote sync, storage reader fallback, path guessing, rebuild-index/hydrate controls, local filesystem as live source, and old v9 NovelManager/storage architecture.

### Completed

- Added safe additive metadata/job migrations inside `godtranslator_v10`.
- Restored a polished app shell with routes for Library, Novels, Chapters, Reader, Translate, Recovery, and Admin.
- Added Novel CRUD/archive APIs protected by admin auth.
- Added database-first translation estimate and persistent job APIs.
- Added mock-safe translation item execution for QA and real run-next execution for explicit admin action.
- Added budget stop and per-chapter budget skip guards.
- Added restart safety: running jobs/items are paused/reset on startup instead of being automatically rerun.
- Added database-first backup ZIP export.
- Kept v10.0.6 recovery preview/import APIs.
- Replaced prototype UI styling with dark charcoal/teal product styling.
- Updated frontend cache query strings to `10.1.0`.

### QA Results

- Python syntax passed for `app/db.py`, `app/main.py`, and `app/recovery.py`.
- JavaScript syntax passed for `static/app.js`.
- `requirements.txt` is valid and not a placeholder.
- Disposable SQLite/TestClient fixture QA passed:
  - `/api/health` returned version `10.1.0`.
  - Library, chapter list, and reader endpoints worked.
  - Chapter 362-like fixture with Original present and Reference missing remained translation-eligible.
  - Missing Original chapters were skipped.
  - Admin APIs returned 401 while public.
  - Wrong password was rejected and correct password created an HttpOnly session cookie.
  - Create/edit/archive/unarchive novel worked.
  - Translation estimate, job creation, mock item execution, AI write, reader AI reload, pause, resume, stop, and retry endpoint paths worked.
  - Max total budget paused a job with `budget_reached`.
  - Max per-chapter budget skipped an item with `max_per_chapter_budget_exceeded`.
  - Admin overview, DB health, missing data, recovery diagnostic, and backup export worked.
  - Backup ZIP contained `manifest.json` and `novels/i-am-god/backup.json` and did not include the fixture admin password or OpenAI key text.

### Known Risks / Notes

- Browser automation could not be completed in this local run because the in-app browser runtime failed with a Windows `EPERM` permission error while reading `C:\Users\lucia\AppData`.
- No real PostgreSQL write QA was run from Codex in this pass; fixture QA used disposable SQLite to avoid touching production data.
- No OpenAI call was made and no translation was started.
- Production `main` was not merged or deployed during this pass.

### Deploy Notes

- Required Render variables remain `DATABASE_URL`, `DB_SCHEMA=godtranslator_v10`, `PYTHON_VERSION=3.12.7`, `ADMIN_PASSWORD`, `OPENAI_API_KEY`, and `OPENAI_MODEL=gpt-4o-mini`.
- Use Supabase pooled Postgres for `DATABASE_URL`.
- Deploy only after reviewing the feature branch and merging intentionally.

## Current Version Target

GodTranslator_v10_1_0_Full_App_Restoration.zip

## v10.0.2 Isolated PostgreSQL Schema Fix

### Production Finding

The real Supabase PostgreSQL connection succeeded, but precheck failed with `UndefinedColumn`.

The exact old unqualified precheck queries were:

- `SELECT 1 AS found FROM novels WHERE id = ?`
- `SELECT COUNT(*) AS total FROM chapters WHERE novel_id = ?`

Those queries resolved against legacy `public.novels` / `public.chapters` tables instead of v10 tables. The incompatible legacy public table shape caused `UndefinedColumn`.

### Fix

- Added `DB_SCHEMA`, defaulting to `godtranslator_v10`.
- Validated schema/table identifiers with a strict identifier regex.
- Added `CREATE SCHEMA IF NOT EXISTS "godtranslator_v10"` for PostgreSQL initialization.
- Qualified all v10 table queries through `Database.table(...)`:
  - `"godtranslator_v10"."novels"`
  - `"godtranslator_v10"."chapters"`
  - `"godtranslator_v10"."translation_jobs"`
  - `"godtranslator_v10"."translation_job_items"`
- Kept SQLite local QA working with unqualified SQLite table names.
- Added safe schema inspection for PostgreSQL:
  - v10 schema exists
  - v10 novels table exists
  - v10 chapters table exists
  - v10 chapter count
  - public novels table exists
  - public chapters table exists
  - public table count
- Improved database precheck so connection success with schema/query failure reports `database_reachable: true` and `schema_ready: false`.
- Updated QA duplicate-row test to use the v10 table helper instead of raw `chapters`.

### Safety

- No `DROP` statements were added.
- No `ALTER` statements were added.
- No legacy `public` table is modified by v10 initialization.
- No backup import was run in this pass.
- No OpenAI call was made.
- No translation was started.

## v10.0.6 Recovery & Import Center

Completed:

- Added website Recovery & Import route at `#/recovery/i-am-god`.
- Added database-backed recovery diagnostic, Recovery Request JSON download, upload preview, import job status, and explicit apply endpoints.
- Added `godtranslator_v10.import_jobs` and `godtranslator_v10.import_job_items` schema support.
- Added safe Reference-only upload parsing for GodTranslator Reference Pack ZIPs, normal ZIPs, and individual UTF-8 `.txt` files.
- Added filename parsing rules where trusted pack manifest metadata wins, explicit `Chapter N` filenames are supported, numeric names such as `0026.txt` are supported, and ambiguous names are rejected.
- Explicit imports fill only currently empty `reference_text` fields and do not overwrite existing References, Original text, AI text, translation status, translation errors, or AI model.

QA results:

- Python syntax check passed.
- JavaScript syntax check passed.
- FastAPI/TestClient fixture checks passed for health, novels, library, reader, recovery diagnostic, Recovery Request, upload preview, explicit apply, and idempotent second apply.
- Fixture counts before any import matched the verified target state: 908 chapters, 906 Original, 412 Reference, 25 AI, 881 needs translation.
- Reader regression passed for Chapter 1 Original, Chapter 100 Original, Chapter 906 Original, Chapter 176 Original missing, Chapter 176 Reference, and Chapter 906 AI missing.
- Preview correctly handled numeric filenames, messy NovelFire filenames, manifest validation, SHA-256 mismatch rejection, ZIP traversal rejection, duplicate chapter rejection, and empty file rejection.
- Real `C:\Users\lucia\Downloads\nmm.zip` preview-only diagnosis found 412 text files, 412 unique recognized chapters, range 1-434, 0 duplicates, 0 would import, 412 already present, and the known 22 Reference gaps still missing.
- No real Reference import was applied.
- No OpenAI call was made.
- No translation was started.

### Local QA

- Python `py_compile` passed for `app/db.py`, `app/main.py`, `tools/migrate_backup_to_postgres.py`, and `tools/qa_v10_foundation.py`.
- Source scan found no remaining raw v10 SQL references like `FROM chapters`, `FROM novels`, `INSERT INTO chapters`, or `INSERT INTO novels`.
- Local schema idempotency QA passed.
- Local FastAPI/Uvicorn smoke test passed:
  - `/api/health`: 200, version `10.0.2`
  - `/api/novels/i-am-god/library`: total `908`, Original `906`, Reference `412`, AI `25`, missing Original `2`
  - Chapter 1 Original loaded
  - Chapter 176 Original returned `original_missing`
  - Chapter 176 Reference loaded
  - Chapter 906 AI returned `ai_missing`

### Blocked

- This workspace does not have `DATABASE_URL`, so the real Supabase PostgreSQL database-check could not be run locally.
- The expected production command after deploying this package is:
  `python tools/migrate_backup_to_postgres.py --database-check --require-postgres`
- Expected successful production result:
  - `database_reachable: true`
  - `database_type: postgresql`
  - `schema: godtranslator_v10`
  - `schema_ready: true`
  - `existing_chapter_row_count: 0` before import

## v10.0.1 Live Postgres Foundation Validation Pass

### Completed

- Created a clean v10-only virtual environment at `.venv-v10`.
- Installed `requirements.txt` successfully in that environment.
- Fixed the local FastAPI/Pydantic/TestClient runtime issue by validating against the clean v10 environment instead of incompatible older packages.
- Bumped API version to `10.0.1`.
- Added safe database precheck mode:
  - `python tools/migrate_backup_to_postgres.py --database-check`
  - `python tools/migrate_backup_to_postgres.py --database-check --require-postgres`
- The precheck reports only safe metadata and never prints `DATABASE_URL`.
- Added explicit library metrics:
  - `total_chapter_rows`
  - `original_readable`
  - `reference_readable`
  - `ai_readable`
  - `needs_translation`
  - `missing_original`
- Updated dry-run output to include `needs_translation`, `missing_original`, and `missing_original_chapters`.
- Updated Render setup to require only `DATABASE_URL` and `PYTHON_VERSION=3.12.7` for this milestone.

### Runtime Validation

- `pip install -r requirements.txt` completed successfully inside `.venv-v10`.
- `python -m py_compile app/db.py app/main.py tools/migrate_backup_to_postgres.py tools/qa_v10_foundation.py` passed.
- Real FastAPI TestClient tests passed against the migrated local v10 database.
- Real Uvicorn app started locally and served HTTP endpoints.

### Database Precheck Results

- `--database-check --require-postgres` correctly failed because no `DATABASE_URL` is present in this workspace.
- The failure did not fall back to SQLite.
- The failure did not print credentials.
- SQLite precheck against the local validation database reported:
  - database reachable: true
  - schema initialized: true
  - existing novel row: true
  - existing chapter row count: 908

### Local Validation Counts

Using `sqlite:///data/v10-validation.db` as the schema-compatible local validation database:

- total rows: 908
- Original readable: 906
- Reference readable: 412
- AI readable: 25
- needs translation: 881
- missing Original: 2
- missing Original chapters: 176, 177

### FastAPI Endpoint Results

Real local Uvicorn HTTP checks:

- `/api/health`: 200, version `10.0.1`, database `reachable`
- `/api/novels`: 200
- `/api/novels/i-am-god/library`: 200, total `908`, Original `906`, Reference `412`, AI `25`, needs translation `881`, missing Original `2`
- `/api/novels/i-am-god/chapters/1/original`: 200, readable text
- `/api/novels/i-am-god/chapters/100/original`: 200, readable text
- `/api/novels/i-am-god/chapters/906/original`: 200, readable text
- `/api/novels/i-am-god/chapters/176/original`: 200, structured `original_missing`
- `/api/novels/i-am-god/chapters/176/reference`: 200, readable text
- `/api/novels/i-am-god/chapters/177/original`: 200, structured `original_missing`
- `/api/novels/i-am-god/chapters/177/reference`: 200, readable text
- `/api/novels/i-am-god/chapters/906/ai`: 200, structured `ai_missing`

### Blocked

- Live Supabase PostgreSQL import/connectivity was not tested because `DATABASE_URL` is not present in this workspace.
- Separate Render test deployment and cold-start verification were not performed from this environment.
- Therefore, the full live milestone is validation-ready but not proven against real Supabase PostgreSQL yet.

### No-Go Confirmation

- No OpenAI call was made.
- No translation was started.
- No frontend reconnection was attempted.
- No v9 folder was modified.

## Scope

This is a new database-first v10 foundation. The v9 codebase remains in `outputs/IAmGodTranslator_Render_Deploy` as legacy-v9 and was not deleted or replaced.

## Architecture Summary

- PostgreSQL is the intended live source of truth for novels, chapters, and translation jobs.
- Supabase Storage is not used for live Reader or Chapters data.
- Render local files are disposable cache only.
- Reader endpoints query the `chapters` table directly.
- Chapters/library endpoints query database rows and derive availability from readable text fields.
- The first-pass local QA used SQLite with the same v10 schema because no live `DATABASE_URL` was available in this workspace.

## Database Schema

Tables added:

- `novels`
- `chapters`
- `translation_jobs`
- `translation_job_items`

Important constraints/indexes:

- `chapters` has `UNIQUE (novel_id, chapter_number)`.
- The chapter table stores a `novel_id` foreign key that references the novel table primary key.
- `chapters_novel_chapter` index on `(novel_id, chapter_number)`.
- `chapters_missing_ai` partial index for readable Original with missing/empty AI text.

Readable text rule:

- value is not `NULL`
- trimmed length is greater than 0

## Migration Tool

Created:

`tools/migrate_backup_to_postgres.py`

Supported modes:

- `--dry-run`
- `--apply`

The tool:

- opens a backup ZIP locally
- detects Original, Reference, and AI folders
- parses chapter numbers from variants such as `0001.txt`, `001.txt`, `1.txt`, `Chapter 1.txt`, `chapter_1.txt`, `chapter-1.txt`, `ch1.txt`, and `第1章.txt`
- deduplicates by `(novel_id, chapter_number)`
- reports duplicates, conflicts, empty files, unrecognized files, and chapter range
- upserts one row per chapter number in apply mode
- never calls OpenAI

## Dry-Run Results

Input:

`../i-am-god-v7-converted-backup.zip`

Results:

- Originals detected: 906
- References detected: 412
- AI translations detected: 25
- Unique chapter numbers found: 908
- Minimum chapter: 1
- Maximum chapter: 908
- Missing chapter numbers: none
- Duplicate filename variants: none
- Conflicting Original files: none
- Conflicting Reference files: none
- Conflicting AI files: none
- Empty files: none
- Unrecognized text files: prompt files only

Explanation for 906 versus 908:

- The backup contains 908 unique chapter rows because chapters 176 and 177 have Reference text but no Original text.
- Readable Original count is 906.

## Apply / Import Results

Local QA database:

`sqlite:///data/v10-local.db`

Imported counts:

- Total chapter rows: 908
- Readable Original: 906
- Readable Reference: 412
- Readable AI: 25
- Needs translation: 881

## Minimal API

Created:

- `GET /api/health`
- `GET /api/novels`
- `GET /api/novels/{novel_id}`
- `GET /api/novels/{novel_id}/library`
- `GET /api/novels/{novel_id}/chapters/{chapter_number}/original`
- `GET /api/novels/{novel_id}/chapters/{chapter_number}/reference`
- `GET /api/novels/{novel_id}/chapters/{chapter_number}/ai`

These endpoints do not scan files, do not read Supabase Storage, do not restore backups, and do not call OpenAI.

## QA Results

Passed:

- Python syntax check for `app` and `tools`.
- `requirements.txt` is valid and is not `{}`.
- Schema initialization ran twice without damage.
- Dry-run completed without writes.
- Apply migration imported one row per chapter number.
- `UNIQUE(novel_id, chapter_number)` was enforced.
- Chapter 1 Original loaded from the database.
- Chapter 100 Original loaded from the database.
- Chapter 906 Original loaded from the database.
- Chapter 1 Reference loaded from the database.
- Chapter 1 AI loaded from the database.
- Chapter 906 AI returned structured `ai_missing`.
- After deleting local runtime chapter-like folders, chapters 1, 100, and 906 still loaded from the database.
- A new `Database` instance after the delete still loaded chapters 1, 100, and 906.
- Source scan found no v9 live-reader patterns such as `remote_path_candidates`, `local_path_candidates`, `chapter_index`, or `counts.json`.
- No OpenAI call was made.
- No translation was started.

Blocked / not fully proven locally:

- A live PostgreSQL/Supabase `DATABASE_URL` was not available in this workspace, so first-pass import and cold-start tests used SQLite as a local schema-compatible stand-in.
- FastAPI TestClient/server execution could not be run in this local tool runtime because the available Python environment does not include compatible FastAPI/Pydantic binaries. The endpoint code is present and deploy dependencies are listed in `requirements.txt`.

## Changed Files

- `app/__init__.py`
- `app/db.py`
- `app/main.py`
- `tools/migrate_backup_to_postgres.py`
- `tools/qa_v10_foundation.py`
- `requirements.txt`
- `Procfile`
- `render.yaml`
- `.env.example`
- `README.md`
- `DEVELOPMENT_PROGRESS_v10.md`

## Files Intentionally Not Changed

- Legacy v9 folder: `outputs/IAmGodTranslator_Render_Deploy`
- Existing v9 ZIPs
- Existing backup ZIPs
- Existing frontend files
- Translation logic

## Next Step

Deploy v10 with a real Supabase pooled PostgreSQL `DATABASE_URL`, run `tools/migrate_backup_to_postgres.py --apply` against that database, then verify `/api/health` and chapter endpoints against live PostgreSQL before connecting the full frontend.

## v10.0.3 PostgreSQL UPSERT Fix

Completed:

- Fixed the PostgreSQL chapter UPSERT to alias the schema-qualified target table as `target`.
- Replaced existing-row references in the chapter conflict update with `target.title`, `target.original_text`, `target.reference_text`, `target.ai_text`, and `target.ai_model`.
- Removed ambiguous local SQL table-qualified references from the SQLite UPSERT branch.
- Added `tools/qa_v10_postgres_upsert.py` to capture the generated PostgreSQL UPSERT SQL and verify idempotent insert/update behavior.
- Updated the API version to `10.0.3`.

QA results:

- Python syntax check passed for app and tools files.
- `requirements.txt` is non-empty and not `{}`.
- PostgreSQL UPSERT SQL unit check passed: target alias is present and stale table-dot references are absent.
- Insert/new chapter, repeated UPSERT, unique duplicate prevention, COALESCE preservation, and non-empty update checks passed against SQLite.
- Local database-check against `sqlite:///data/v10-local.db` reported `existing_novel_row=true` and `existing_chapter_row_count=908`.
- Live PostgreSQL database-check was not run locally because `DATABASE_URL` is not present in this workspace.
- No OpenAI call was made.
- No translation was started.

Deploy notes:

- Keep `DB_SCHEMA=godtranslator_v10`.
- Use the existing Supabase pooled PostgreSQL `DATABASE_URL`.
- Rerun the backup import with `--apply` only after deploying this fix.

## v10.0.4 Clean Reader Frontend

Completed:

- Added a clean database-backed frontend served by FastAPI at `/`.
- Added static assets under `/static` for the v10 reader only.
- The frontend uses only:
  - `GET /api/novels`
  - `GET /api/novels/{novel_id}/library`
  - `GET /api/novels/{novel_id}/chapters/{chapter_number}/{mode}`
- Added reader source switching for Original, Reference, and AI.
- Added Previous / Next chapter navigation and a chapter selector.
- Added a mobile-friendly dark reader layout with preserved paragraph breaks.
- Added title normalization so body prose is not used as a chapter title.
- Chapter 176 displays as `Chapter 176`.
- Updated the API/frontend version to `10.0.4`.

QA results:

- Python syntax check passed.
- JavaScript syntax check passed with the bundled Node runtime.
- `requirements.txt` is valid and is not `{}`.
- Local FastAPI uvicorn smoke test started and returned `/api/health` 200.
- Local library loaded 908 chapter rows from `sqlite:///data/v10-local.db`.
- Counts were 908 total, 906 Original, 412 Reference, 25 AI, and 881 need translation.
- Chapter 1 Original, Chapter 100 Original, and Chapter 906 Original loaded.
- Chapter 176 Original returned structured `original_missing`.
- Chapter 176 Reference loaded.
- Chapter 906 AI returned structured `ai_missing`.
- Static frontend files were served.
- Source scan found no v9 reader patterns: no Storage fallback, no `chapter_index`, no `counts.json`, and no path guessing.
- No OpenAI call was made.
- No translation was started.

Known notes:

- Local QA used `GT_SQLITE_PATH=data/v10-local.db` because this workspace does not contain the live `DATABASE_URL`.
- Production should continue using the proven pooled PostgreSQL `DATABASE_URL` and `DB_SCHEMA=godtranslator_v10`.

## v10.0.5 Reference Gap Recovery

Completed:

- Added `tools/recover_missing_references.py`.
- Added read-only diagnostic mode for missing Reference chapters in a configured range.
- Added dry-run mode for Reference source folders, ZIPs, and individual `.txt` files.
- Added apply mode that fills missing `reference_text` only.
- Existing non-empty Reference text is preserved by default.
- Overwrite behavior requires the explicit `--overwrite-existing` flag.
- The recovery tool does not modify `original_text`, `ai_text`, translation status, public schema, or v9 tables.
- Updated the API/package version to `10.0.5`.

Command syntax:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --diagnose
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --dry-run
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --apply
```

QA plan:

- Use the current v10 database only for read-only diagnostics.
- Test apply mode against a temporary copy of the database with synthetic Reference files.
- Verify existing Reference, Original, and AI values are unchanged in the temporary copy except for the 22 missing Reference fields.

QA results:

- Python syntax check passed.
- Diagnostic mode against the current database reported 412 Reference rows and exactly 22 missing Reference chapters in range 1-434.
- Temporary-copy dry run found 22 files and would insert chapters 26, 53, 111, 118, 123, 124, 141, 151, 155, 156, 171, 203, 204, 263, 323, 336, 357, 362, 372, 384, 410, and 416.
- Temporary-copy apply filled 22 Reference fields and raised the Reference count to 434.
- Temporary-copy second apply filled 0 rows, proving idempotency.
- Temporary-copy existing Reference rows stayed byte-for-byte unchanged.
- Temporary-copy Original, AI, title, and translation status values stayed unchanged.
- Chapter 26 and Chapter 416 Reference loaded in the temporary copy after recovery.
- Existing Chapter 27, 414, and 434 Reference values remained present and unchanged.
- Final diagnostic against the current database still reported 412 Reference rows and the same 22 missing chapters, confirming no live/local v10 data was imported in this milestone.
- Source scan found no OpenAI or translation execution calls.

## v10.0.6 Targeted Reference Downloader

Completed:

- Added `tools/download_missing_novelfire_references.py`.
- Downloader targets only the verified 22 missing Reference chapters.
- Output defaults to `reference_gap_recovery_input`.
- Output filenames use the required four-digit format such as `0026.txt` and `0416.txt`.
- Existing valid target files are skipped for resume behavior.
- Downloader supports:
  - `--novel-url` for NovelFire chapter-link discovery.
  - `--url-template` for direct chapter URLs with `{chapter}`, `{chapter03}`, and `{chapter04}`.
  - Optional `--browser-fallback` using Playwright only if direct fetch fails.
- Downloader rejects blocked/challenge/login/error pages, short/empty extracts, and pages whose heading/content does not verify the requested chapter number.
- No database write path exists in the downloader.

Command syntax:

```powershell
python tools/download_missing_novelfire_references.py --novel-url "NOVELFIRE_NOVEL_PAGE_URL" --output reference_gap_recovery_input
python tools/download_missing_novelfire_references.py --url-template "https://novelfire.net/.../chapter-{chapter}" --output reference_gap_recovery_input
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "reference_gap_recovery_input" --dry-run
```

Notes:

- The v10 import reports preserve only backup file paths such as `novels/i-am-god/references/0001.txt`; they do not preserve the exact NovelFire novel URL.
- Because the exact URL was not available in this workspace, live downloading was not run in this milestone.
- The downloader was validated with local HTML fixtures and the recovery dry-run path.

QA results:

- Python syntax check passed.
- `requirements.txt` remained valid and not `{}`.
- Read-only diagnostic against the current local v10 database still reported 412 Reference rows and the same 22 missing chapters.
- Local fixture downloader recovered exactly the 22 target files named `0026.txt` through `0416.txt` as applicable.
- Local fixture recovery dry-run reported 22 files found, 22 matched missing targets, the exact 22 chapters would be inserted, no duplicates, no empty files, and no unexpected chapters.
- Resume check passed: a second downloader run skipped the 22 valid existing files and downloaded 0 files.
- No database write was performed.
- No OpenAI call was made.
- No translation was started.

## v10.2.0 Checkpoint 3 - Account and Supabase Auth Foundation

Completed:

- Classified the interrupted Checkpoint 3 work and preserved the existing partial changes.
- Added additive account tables for profiles, preferences, reading progress/history, bookmarks, favorites, and translation profile foundations in the isolated v10 schema.
- Added `/api/auth/config` with public Supabase Auth configuration only.
- Added `/api/account/me` and `/api/account/preferences` with server-side authenticated-user resolution.
- Added `/auth/callback` so Supabase email/password reset and Google OAuth redirects can return to the app shell.
- Added Supabase email/password, Google OAuth, password reset, persistent session, and sign-out controls in the Account page.
- Added polished account route aliases for `#/account`, `#/login`, `#/signup`, `#/forgot-password`, and `#/reset-password`.
- Kept public reading available when Auth is not configured.
- Kept `ADMIN_PASSWORD` as an emergency admin fallback and added server-side `ADMIN_EMAILS` role bootstrap.

Checkpoint 3 QA:

- Python syntax check passed for all app modules.
- JavaScript syntax check passed.
- FastAPI fixture startup passed.
- Missing Supabase Auth config returned a guest-safe state and did not crash.
- `/api/auth/config` did not expose `DATABASE_URL`, service-role keys, admin password, or token values.
- Guest `/api/account/me` returned guest and anonymous preference save returned 401.
- Mock Supabase bearer token path created a server-side profile, saved preferences, and honored `ADMIN_EMAILS`.
- Bad bearer token fell back to guest.
- Admin password fallback login and session still worked.
- `/auth/callback` returned the SPA shell.
- No OpenAI call was made.
- No translation was started.

## v10.2.0 Checkpoint 4 - Personalization and Private User Experience

Completed:

- Added database-backed personal progress, reading history, bookmarks, and favorites APIs.
- Kept guest preferences in safe browser storage and authenticated preferences in the database.
- Added Library Continue Reading for signed-in users.
- Added History and Bookmarks routes.
- Added favorite toggles and Library Favorites filtering for signed-in users.
- Added reader progress sync and chapter bookmark actions.
- Kept private data ownership server-side by deriving the user from validated Auth tokens only.
- Hid public Translate/Recovery UI links from guests while preserving backend authorization.

Checkpoint 4 QA:

- Python syntax check passed for all app modules.
- JavaScript syntax check passed.
- Fixture authenticated user saved preferences, reading progress, one bookmark, and one favorite.
- `/api/account/home` returned Continue Reading plus private history/bookmark/favorite data for the owner.
- Anonymous `/api/account/home` returned 401.
- Reading history clear succeeded for the authenticated owner.
- Local SQLite fallback and Postgres-oriented UUID bookmark storage paths are both represented safely.
- No OpenAI call was made.
- No translation was started.

## v10.2.0 Checkpoint 5 - Premium Library, Novel, and Reader Experience

Completed:

- Added a real `#/novel/{novel_id}` detail page with cover hero, summary, progress, stats, Continue Reading, Chapters, and authorized Translate/Edit actions.
- Updated novel cards to open the novel detail workspace and use favorite-aware actions.
- Added Continue Reading and Add Novel commands to the command palette with permission-aware visibility.
- Added Reader Zen mode, Reader Settings shortcut, Bookmark button, Back to Novel, and keyboard shortcuts for previous/next chapter, Zen mode, bookmark, and font size.
- Added responsive visual styling for novel hero, recent chapter links, Continue Reading, and Zen mode.
- Kept public users away from visible Translate/Recovery actions while preserving server-side authorization.

Checkpoint 5 QA:

- Python syntax check passed for all app modules.
- JavaScript syntax check passed.
- Fixture smoke test passed for `/api/health`, `/api/novels`, `/api/novels/i-am-god`, `/api/novels/i-am-god/library`, and AI Reader chapter loading.
- SPA asset version stayed at `10.2.0`.
- No OpenAI call was made.
- No translation was started.

## v10.2.0 Checkpoint 6 - Premium Translation Workspace

Completed:

- Added a server-side `/api/models` registry that exposes enabled model IDs and approximate/unknown pricing metadata without secrets.
- Added translator-role authorization for translation estimate/job/job-action APIs while keeping admin access.
- Added side-by-side comparison API and UI for Original, Reference, and AI text.
- Reworked Translate into staged sections: Chapter Selection, Translation Profile, Model & Reference, Budget & Safety, Estimate, and Launch.
- Added parsed chapter preview for inputs such as `26,53,60-70`.
- Added Translation Profile placeholders, Style Guide, Glossary notes, Reference toggle, budget controls, and sticky estimate panel.
- Added Job Center route for translation jobs and admin import job visibility.
- Required a valid estimate before job launch in the frontend.

Checkpoint 6 QA:

- Python syntax check passed for all app modules.
- JavaScript syntax check passed.
- `/api/models` returned configured model metadata.
- Public translation estimate returned 401.
- Admin estimate selected 2 chapters, found 1 eligible, and skipped 1 already translated chapter.
- Translation job creation persisted a queued job with one item.
- Mock `run-next` completed without OpenAI and wrote fixture AI text.
- Reader loaded the fixture AI result.
- Compare returned Original, Reference, and AI panels.
- No real OpenAI call was made.

## v10.2.0 Checkpoint 7 - Premium Admin and Operations

Completed:

- Reworked Admin into tabs: Overview, Database, Translation Jobs, Import Jobs, Missing Data, Backups, and Diagnostics.
- Replaced raw JSON-first admin display with operational cards and hidden technical details.
- Kept Database health clear: connected/healthy state, schema, expected tables, and chapter counts.
- Kept Missing Data concise and tied to the configured Reference range.
- Preserved Recovery entry points, import jobs, translation jobs, and backup/export flows.
- Kept sanitized diagnostics from exposing secret values.

Checkpoint 7 QA:

- Python syntax check passed for all app modules.
- JavaScript syntax check passed.
- Public `/api/admin/overview` returned 401.
- Admin login worked.
- `/api/admin/overview`, `/api/admin/db-health`, translation jobs, import jobs, recovery diagnostic, and backup export returned 200 in fixture QA.
- Missing Reference respected target range 1-434 and reported chapter 362 only in the fixture.
- No OpenAI call was made.
- No translation was started.

## v10.2.0 Checkpoint 8 - Final QA and Release Package

Completed:

- Resumed isolated fixture QA with realistic multi-paragraph chapter text instead of short placeholder text.
- Kept production readable-text validation unchanged.
- Protected Recovery diagnostic and request export endpoints with admin authorization.
- Added a client-side Recovery admin gate before loading Recovery diagnostics.
- Tightened mobile/tablet header navigation so search, nav, and action controls do not overlap or dominate the first viewport.
- Fixed Novel Detail counts by merging the `/api/novels/{novel_id}` verification counts into the detail view model.
- Completed final package documentation pass for README, auth setup, local preview, product spec, and this progress log.

Checkpoint 8 QA:

- Fixture expected state passed: Total `908`, Original `906`, Reference `433`, AI `25`, Needs Translation `881`.
- Missing Original proof: `176`, `177`.
- Missing Reference proof: target range `1-434`, missing count `1`, chapter `362`.
- Reader, account/preferences, reading progress/history, bookmarks/favorites, comparison, recovery preview, admin overview/database/missing data, and backup/export passed against disposable SQLite.
- Authorization matrix passed: guests blocked from private APIs, users blocked from Admin/Recovery/novel management/translation jobs, translators allowed translation features but blocked from Admin/Recovery, admins allowed Admin, spoofed user IDs and roles ignored, self-promotion blocked, private user data scoped to owner.
- Mock translation flow passed for estimate, create job, persist job, Chapter 362 Original-without-Reference eligibility, mock run-next, AI write/readback, pause/resume, interrupted state, cancel, total budget stop, per-chapter budget skip, and Missing Original skip.
- Visual QA screenshots saved under `qa_screenshots_v10_2/` for desktop `1920x1080`, desktop `1366x768`, mobile `390x844`, and tablet `768x1024`.
- Visual QA confirmed no horizontal overflow, no clipped navigation, usable mobile controls, readable text, and Missing Reference UI showing only chapter `362`.
- Visual QA confirmed Novel Detail shows `908` chapters, `906` Original, `433` Reference, `25` AI, and `881` Remaining.
- Security scan passed for source, docs, screenshots, and release ZIP safety checks: no `.env`, database URL value, database password, service-role key, Google secret, OpenAI key, admin password value, access tokens, refresh tokens, cookies, or browser profiles included.
- Performance sanity passed: chapter list APIs return metadata only, pagination works, search and reading progress are debounced, and the UI does not load all 908 chapter bodies.
- No OpenAI call was made.
- No production database was modified.
- Production was not deployed.

## v10.5.0 Checkpoint 1 - Translation Quality Platform

Completed:

- Created branch `v10.5.0-translation-quality-and-production-experience` from `origin/main`.
- Added additive tables for `translation_quality_reviews`, `translation_history`, and `glossary_entries`.
- Seeded shared Translation Profiles: Natural English Novel, Faithful Translation, Reference Guided, Fast Draft, and Publication Quality.
- Added profile selection, duplicate/create flows, and profile metadata persistence in translation job settings.
- Added Smart Glossary with categories, aliases, locked terms, usage counts, and relevant-entry-only prompt injection.
- Added Translation Quality workspace with score/status, warnings, Reference availability, profile/model/cost/timing metadata, review marks, AI/Original/Reference comparison, and history restore.
- Kept Reference text admin-only in quality and compare views.
- Preserved AI version history before retranslation overwrite and after successful translation completion.
- Added Admin Prompt Inspector, Live Translation Monitor, Cost Analysis, Profiles, and Glossary tabs.
- Added retranslation preview and explicit-confirmation job creation so existing AI is not overwritten by default.
- Added focused QA script `tools/qa_v10_5_translation_quality.py`.
- Updated README, product spec, and v10.5 release notes.

Checkpoint 1 QA:

- Python compile passed for `app/main.py`, `app/db.py`, `app/recovery.py`, and v10.3/v10.4/v10.5 QA tools.
- JavaScript syntax check passed for `static/app.js`.
- v10.5 focused QA passed against disposable SQLite with existing local FastAPI dependencies.
- QA verified default profiles, Smart Glossary relevant filtering, translation history, quality review marks, admin-only Reference visibility, prompt inspector privacy, monitor/cost APIs, and retranslation preview safety.
- `DATABASE_URL` and `OPENAI_API_KEY` were removed from the QA environment.
- No OpenAI call was made.
- No production database was modified.
- Production was not deployed.
