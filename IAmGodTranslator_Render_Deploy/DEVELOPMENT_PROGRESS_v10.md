# GodTranslator v10 Development Progress

## Current Version Target

GodTranslator_v10_0_2_Isolated_Postgres_Schema_Fix.zip

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
