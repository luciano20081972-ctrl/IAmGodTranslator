# GodTranslator v10.1.0 Full App Restoration

GodTranslator v10.1.0 restores the full product shell on top of the v10 database-first foundation.

PostgreSQL remains the live source of truth:

- `godtranslator_v10.novels`
- `godtranslator_v10.chapters`
- `godtranslator_v10.translation_jobs`
- `godtranslator_v10.translation_job_items`
- `godtranslator_v10.import_jobs`
- `godtranslator_v10.import_job_items`

The app does not use v9 chapter indexes, counts files, hydration, startup restore, startup storage sync, path guessing, or Supabase Storage as the live reader source.

## Application

Routes:

- `#/library`
- `#/novels`
- `#/chapters/i-am-god`
- `#/reader/i-am-god/1/ai`
- `#/translate/i-am-god`
- `#/recovery/i-am-god`
- `#/admin`

Restored workflows:

- Polished multi-novel Library with covers, counts, progress, search, filters, and sorting.
- Novel management for create, edit, archive, and unarchive.
- Chapter Library with search, status filters, pagination, availability badges, Reader links, and Translate links.
- Reader with AI / Reference / Original modes, previous/next, chapter selector, and font control.
- Translate workspace with estimates, budget controls, persistent jobs, pause/resume/stop/retry, and explicit run-next execution.
- Recovery workspace from v10.0.6 for safe Reference preview/import.
- Admin dashboard with system overview, database health, missing data, translation jobs, import jobs, and database-first backup export.

## Translation Safety

Chinese `original_text` is always the translation source.

`reference_text` is optional style guidance only. A chapter with Original text and no Reference text remains eligible for translation.

OpenAI is called only when an authenticated admin explicitly runs a real translation item. Automated QA should use `POST /api/translation/jobs/{job_id}/run-next?mock=true`.

## Admin Auth

Set:

```text
ADMIN_PASSWORD
```

Admin sessions use a signed HttpOnly cookie. Cookies are marked Secure when the request is HTTPS and use SameSite=Lax.

## Local Smoke Test

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
ADMIN_PASSWORD
OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
```

Use the Supabase pooled Postgres connection string for `DATABASE_URL`. `DB_SCHEMA` defaults to `godtranslator_v10`.

## Recovery

Diagnose missing Reference chapters:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --diagnose
```

Dry-run candidate files:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --dry-run
```

Apply only missing Reference fields:

```powershell
python tools/recover_missing_references.py --database-url "$env:DATABASE_URL" --novel-id i-am-god --start 1 --end 434 --input "PATH_TO_REFERENCE_FILES" --apply
```

Existing non-empty Reference text is never overwritten by default.

