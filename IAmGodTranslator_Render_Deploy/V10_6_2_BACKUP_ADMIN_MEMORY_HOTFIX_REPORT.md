# GodTranslator v10.6.2 Backup/Admin Memory Hotfix Report

## Scope

Emergency production-safe reliability hotfix for the v10.6.1 production line.

This hotfix does not modify chapter content, edition content, translation scheduling, import execution, recovery, restore behavior, database schema, or production data.

## Root Cause

The Admin workspace loaded every major admin endpoint in one broad `Promise.all`, so opening Admin or Backups triggered overview, database health, missing-data recovery, import jobs, translation jobs, backup manifest, users, and translation performance diagnostics together.

The backup manifest endpoint was lightweight, but the full backup create/download endpoints still built a complete platform backup as one Python object, serialized it as one large JSON byte string, and served it through `BytesIO`. On a production database with large chapter bodies, that path could exceed the 512 MB Render memory limit.

## Fixes

- Admin pages now load only the data required for the active Admin tab.
- Admin Overview no longer fetches backup manifest, job lists, users, missing data, database health, or performance diagnostics.
- Backups & Recovery fetches the backup manifest only when the Backups tab is opened.
- `/api/admin/backups/manifest` remains an aggregate-only JSON response and enriches the manifest with small in-process backup job metadata.
- `/api/admin/backups/create` now starts an explicit background backup job and returns small JSON immediately.
- Concurrent full backup attempts return JSON `429 backup_already_running`.
- `/api/admin/backups/download` streams only an already completed background backup file.
- Full backup writing now iterates configured backup tables in bounded batches and writes JSON directly to a temp file.
- Supabase backup upload, when configured, reads from the completed file instead of requiring an in-memory full payload.
- Backup UI shows background progress, disables invalid actions, and only enables download after completion.
- JSON error responses avoid exception details and do not expose credentials.

## QA Results

Focused QA command:

```powershell
python IAmGodTranslator_Render_Deploy/tools/qa_backup_manifest_hotfix.py
```

Result: passed.

Key checks:

- 908-chapter large-text manifest response: 1,727 bytes.
- 50 repeated manifest calls: 393.583 ms total, traced peak 16,215 bytes.
- Manifest did not serialize original or edition text sentinels.
- Missing optional backup tables report safe per-table errors.
- Background full backup job completed on isolated fixture.
- Duplicate backup job request returned JSON 429.
- Backup download streamed completed job file.
- Backup routes are admin-protected by source inspection.
- Frontend has JSON/non-JSON guard handling and lazy Admin loaders.

Additional syntax checks:

```powershell
python -m py_compile IAmGodTranslator_Render_Deploy/app/main.py IAmGodTranslator_Render_Deploy/app/db.py IAmGodTranslator_Render_Deploy/app/recovery.py IAmGodTranslator_Render_Deploy/tools/qa_backup_manifest_hotfix.py
C:\Users\lucia\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check IAmGodTranslator_Render_Deploy/static/app.js
```

Result: passed.

HTTP-level FastAPI test-client check was skipped because this local environment does not have FastAPI, Starlette, Uvicorn, requests, or httpx installed, and this hotfix did not install dependencies.

## Safety Confirmations

- No OpenAI calls.
- No production database writes.
- No production data touched manually.
- No migrations or schema changes.
- No translations, imports, recovery, or restore operations run.
- No v11 branch changes, merges, or deployment.
- No production credentials are recorded in this report.

## Deployment Note

After this hotfix is merged to production main and Render auto-deploys it, create a new verified production backup through Admin > Backups & Recovery.
