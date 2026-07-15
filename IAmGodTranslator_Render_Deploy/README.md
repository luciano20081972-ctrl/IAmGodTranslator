# GodTranslator v10.5.0 Translation Quality Platform

GodTranslator v10.5.0 builds on the v10.4 translation-performance release with reusable translation profiles, smart glossary prompting, translation quality review, version history, prompt inspection, live monitoring, and cost analysis.

PostgreSQL remains the live source of truth:

- `godtranslator_v10.novels`
- `godtranslator_v10.chapters`
- `godtranslator_v10.translation_jobs`
- `godtranslator_v10.translation_job_items`
- `godtranslator_v10.translation_quality_reviews`
- `godtranslator_v10.translation_history`
- `godtranslator_v10.glossary_entries`
- `godtranslator_v10.import_jobs`
- `godtranslator_v10.import_job_items`
- `godtranslator_v10.translation_profiles`

The app does not use v9 chapter indexes, counts files, hydration, startup restore, startup storage sync, path guessing, or Supabase Storage as the live reader source.

## Application

Routes:

- `#/library`
- `#/novel/i-am-god`
- `#/novels`
- `#/chapters/i-am-god`
- `#/reader/i-am-god/1/ai`
- `#/compare/i-am-god/1`
- `#/quality/i-am-god`
- `#/quality/i-am-god/1`
- `#/translate/i-am-god`
- `#/jobs`
- `#/recovery/i-am-god`
- `#/admin/overview`
- `#/admin/quality`
- `#/admin/monitor`
- `#/admin/costs`
- `#/admin/prompt`
- `#/admin/profiles`
- `#/admin/glossary`
- `#/admin/database`
- `#/admin/missing`
- `#/settings/appearance`
- `#/settings/reader`
- `#/account`
- `#/history`
- `#/bookmarks`

Restored workflows:

- Polished multi-novel Library with covers, counts, progress, search, filters, and sorting.
- Novel management for create, edit, archive, and unarchive.
- Chapter Library with search, status filters, pagination, availability badges, Reader links, and Translate links.
- Reader with AI / Reference / Original modes, previous/next, chapter selector, and font control.
- Translate workspace with estimates, budget controls, persistent jobs, pause/resume/stop/retry, and explicit run-next execution.
- Reusable Translation Profiles: Natural English Novel, Faithful Translation, Reference Guided, Fast Draft, and Publication Quality, with duplicate/edit support.
- Smart Glossary with categories, aliases, locked terms, usage counts, import endpoint, and relevant-entry-only prompt inclusion.
- Translation Quality workspace with score, status, warnings, profile/model/cost/timing metadata, AI/Original comparison, admin-only Reference visibility, review marks, and version restore.
- Admin Prompt Inspector with estimated prompt sections/tokens/costs and no provider request.
- Live Translation Monitor and Cost Analysis dashboards using v10.4 performance instrumentation.
- Admin-protected Recovery workspace from v10.0.6 for safe Reference diagnostic, request export, preview/import.
- Admin dashboard with system overview, database health, missing data, translation jobs, import jobs, and database-first backup export.
- v10.3 shell with authorization-aware navigation, global search/command palette, activity/account/settings controls, and local guest personalization.
- Supabase Auth foundation for email/password, Google OAuth, account profile discovery, and database-backed preferences when configured.
- Database-backed reading progress, history, bookmarks, and favorites.
- Premium Novel Detail, Reader Zen mode, Job Center, comparison mode, and tabbed Admin operations.

## Translation Safety

Chinese `original_text` is always the translation source.

`reference_text` is optional style guidance only. A chapter with Original text and no Reference text remains eligible for translation.

OpenAI is called only when an authenticated translator/admin explicitly runs a real translation item. Automated QA should use `POST /api/translation/jobs/{job_id}/run-next?mock=true`.

Prompt Inspector previews prompt text and token estimates but does not send provider requests. Prompt diagnostics do not expose API keys, auth headers, provider responses, or secrets.

Retranslation requires explicit confirmation before existing AI is overwritten. Previous AI versions are preserved in `translation_history`.

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
ADMIN_EMAILS
AUTH_ENABLED=true
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_AUTH_REDIRECT_URL
OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_REGISTRY=gpt-4o-mini,gpt-4o
```

Use the Supabase pooled Postgres connection string for `DATABASE_URL`. `DB_SCHEMA` defaults to `godtranslator_v10`.

## Supabase Auth

Public reading works for guests. If Supabase Auth variables are missing, the app shows that account features are not configured and continues to run.

Configure Supabase Auth with:

- Email/password enabled.
- Google provider enabled when using Continue with Google.
- Local redirect URL: `http://127.0.0.1:8001/auth/callback`
- Production redirect URL: `https://iamgodtranslator.onrender.com/auth/callback`

Only publishable Supabase config is sent to the browser. Do not expose `DATABASE_URL`, service-role keys, Google OAuth secret, `ADMIN_PASSWORD`, or `ADMIN_EMAILS`.

## Recovery

Recovery UI and API access require admin authorization. Missing Reference for I Am God is scoped to the configured Reference target range `1-434`; the expected release-state missing Reference chapter is `362`.

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
