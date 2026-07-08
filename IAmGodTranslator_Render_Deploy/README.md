# GodTranslator v10.0.6 Targeted Reference Downloader

This is a new v10 foundation. It does not use the v9 live chapter-index, file-path, hydration, or Supabase Storage reader systems.

Live novel data is stored in PostgreSQL tables:

- `novels`
- `chapters`
- `translation_jobs`
- `translation_job_items`

Reader endpoints use a single database query for chapter text.

The included frontend is a small database-backed reader:

- Library page
- Chapter list
- Reader page with Original / Reference / AI source switching
- No translation controls
- No Supabase Storage reads
- No legacy chapter index or path guessing

## Local smoke test

```powershell
python tools/migrate_backup_to_postgres.py --input ..\i-am-god-v7-converted-backup.zip --novel-id i-am-god --title "I Am God" --database-url sqlite:///data/v10-local.db --apply
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Render

Build command:

```text
pip install -r requirements.txt
```

Start command:

```text
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Required environment variables:

```text
DATABASE_URL
DB_SCHEMA=godtranslator_v10
PYTHON_VERSION=3.12.7
```

Use the Supabase pooled Postgres connection string for `DATABASE_URL`.
`DB_SCHEMA` defaults to `godtranslator_v10`; v10 tables are isolated there and do not use legacy `public` tables.

OpenAI is not required for this milestone.

## Targeted Reference gap recovery

Diagnose missing Reference chapters in the proven v10 range:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --diagnose
```

Dry-run candidate files from a folder, ZIP, or individual `.txt` files:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --dry-run
```

Apply only missing Reference fields:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --apply
```

Existing non-empty Reference text is never overwritten by default. Overwrite behavior requires the explicit `--overwrite-existing` flag.

## Targeted NovelFire downloader for the 22 Reference gaps

The downloader only targets the verified missing chapters:

`26, 53, 111, 118, 123, 124, 141, 151, 155, 156, 171, 203, 204, 263, 323, 336, 357, 362, 372, 384, 410, 416`

Use either the exact NovelFire novel page:

```powershell
python tools/download_missing_novelfire_references.py --novel-url "NOVELFIRE_NOVEL_PAGE_URL" --output reference_gap_recovery_input
```

Or a direct chapter URL template:

```powershell
python tools/download_missing_novelfire_references.py --url-template "https://novelfire.net/.../chapter-{chapter}" --output reference_gap_recovery_input
```

The template supports `{chapter}`, `{chapter03}`, and `{chapter04}`.

If direct fetch fails and local Playwright is available, use browser fallback without bypassing login, paywalls, or challenge pages:

```powershell
python tools/download_missing_novelfire_references.py --url-template "https://novelfire.net/.../chapter-{chapter}" --output reference_gap_recovery_input --browser-fallback
```

Validate downloaded files without importing:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "reference_gap_recovery_input" --dry-run
```

Do not run `--apply` until the dry run shows exactly the 22 missing targets and no duplicates, empty files, or unexpected chapters.
