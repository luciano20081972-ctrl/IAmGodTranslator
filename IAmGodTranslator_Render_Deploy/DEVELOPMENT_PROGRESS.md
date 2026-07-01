# GodTranslator Development Progress

## Current Version Target

GodTranslator_Web_v8_0_4_Online_Restore_Translate_Fix.zip

## Completed Tasks

- Finished v8.0.4 online restore and translate stability pass.
- Separated Local ZIP Restore from Online Supabase Restore in the Backups UI.
- Added a dedicated Online Supabase Restore card with backup details, online dry-run, online confirm, progress, status, raw details, and rebuild/hydrate/refresh actions.
- Confirm Online Restore now calls `POST /api/admin/backups/restore-from-supabase` and never requires a local ZIP file.
- Local ZIP Restore remains local-only and still requires a selected ZIP file.
- Added `GET /api/bootstrap` for fast wake/bootstrap without full scans, backup, restore, or chapter downloads.
- Added `GET /api/admin/recovery/status` for persisted runtime recovery status and last restore job status.
- Updated `/api/storage` so healthy active/canonical Supabase data reports `recommended_recovery_action=none` and says live data is ready.
- Updated `/api/storage` so active=0/canonical=0/legacy=0 plus backup ZIPs recommends `restore_from_supabase_backup`.
- Added JSON batch endpoints: `GET /api/batch/health`, `POST /api/batch/estimate`, `POST /api/batch/start`, `GET /api/batch/jobs`, `GET /api/batch/jobs/{job_id}`, `POST /api/batch/jobs/{job_id}/cancel`, and `POST /api/batch/jobs/{job_id}/retry-failed`.
- Added a Translation Health card in the Translate tab.
- Batch dry-run/start with `dry_run=true` creates an estimate only and does not call OpenAI.
- Batch estimate can materialize `supabase://` source/reference chapter text into temporary local inputs when Render local cache is empty.
- Batch creation no longer syncs generated job/cache folders to Supabase; it updates only metadata, counts, and index.
- Bumped frontend cache/service-worker versions to v78.
- Finished v8.0.3 recovery progress UI pass.
- Replaced the simple Supabase Recovery button cluster with a recovery command center that shows active/canonical/legacy/backup counts, recommended action, step-by-step guidance, action cards, progress bars, raw result details, and a recovery timeline.
- Wired the recovery dashboard to `/api/storage` so the live recommendation can distinguish legacy-path migration from backup ZIP restore.
- Added frontend actions for Deep Scan, Hydrate I Am God, Migrate Dry Run, Confirm Migration, List Backups, Restore Backup Dry Run, Confirm Restore, Rebuild Index, and Refresh Novel Data.
- Added restore-job polling so dry-run/confirm restore actions show progress instead of leaving the user guessing.
- Improved legacy migration reports so a no-files run returns `completed_no_changes`, `found_legacy_files`, `files_to_copy`, warnings, and `next_recommended_action`.
- Updated `/api/storage` to return machine-readable `recommended_recovery_action`, readable `recommended_recovery_label`, and `recommended_recovery_steps`.
- For the live-style state where canonical=0, legacy=0, active=0, and backup ZIPs exist, the recommended recovery action is now `restore_from_supabase_backup`.
- Bumped frontend cache/service-worker versions to v77.
- Finished v8.0.2 Supabase legacy path recovery after live data was found under `app/novels/i-am-god/Original`, `Reference`, `AI`, `Cover`, and `Backups`.
- Added canonical plus legacy Supabase path discovery for originals, references, AI translations, and prompts.
- Added legacy metadata/counts fallback from `app/novels/{novel_id}/metadata.json` and `app/novels/{novel_id}/counts.json`.
- Updated active counts and reader remote markers to use legacy paths when canonical folders are empty.
- Added admin deep discovery endpoint: `GET /api/admin/storage/deep-discovery`.
- Added safe copy-only legacy migration endpoint: `POST /api/admin/storage/migrate-legacy-paths`.
- Added Supabase backup listing endpoint: `GET /api/admin/backups/supabase`.
- Added server-side restore-from-Supabase-backup endpoint: `POST /api/admin/backups/restore-from-supabase`.
- Updated `/api/storage` to include `canonical_supabase_counts`, `legacy_supabase_counts`, `backup_zips_found`, and `recommended_recovery_action`.
- Added Admin `Supabase Recovery` controls for deep scan, hydrate, migrate dry-run/confirm, list backups, and restore newest backup dry-run.
- Added safe `HEAD /` response for Render probes.
- Bumped frontend cache/service-worker versions to v76.
- Finished v8.0 Supabase persistence/hydration fix after Render redeploy reset reports.
- Added lazy Supabase novel index hydration from `novels/index.json` and `novels/{novel_id}/metadata.json`.
- Prevented local default novel creation from overwriting the remote source of truth when local Render cache is empty.
- Added bounded per-novel Supabase category listing for `originals`, `references`, `ai_translations`, and `prompts`.
- Added persistent `novels/{novel_id}/counts.json` count cache and local `counts.json` mirror.
- Updated novel cards/library counts to use active local/Supabase counts instead of empty local cache counts.
- Added reader text fallback for `supabase://` chapter markers when local chapter cache is missing.
- Added safer cover upload handling: jpg/jpeg/png/webp only, 5 MB max size, failure cleanup, readable errors, and remote cover fallback.
- Added admin rebuild endpoints: `POST /api/admin/index/rebuild` and `POST /api/admin/novels/{novel_id}/hydrate-from-supabase`.
- Updated `/api/storage` to report `local_cache_counts`, `supabase_counts`, `database_counts`, and `active_counts_used_by_app`.
- Added admin-side `Rebuild Supabase Index` control.
- Bumped frontend cache/service-worker versions to v75.
- Preserved the v8 fetch recovery work: timeout-based frontend API helper, boot recovery UI, cache clear, and busy-state upload/backup/import handling.
- Added one-time legacy backup converter for old GodTranslator backup ZIPs without `manifest.json`.
- Dry-ran and wrote a v7-compatible converted backup for `i-am-god`.
- Continued from `GodTranslator_Web_v7_0_PARTIAL_Phase_9.zip` without restarting.
- Completed the final visual UI polish pass for admin/public layouts.
- Redesigned the Admin Dashboard into clear sections for Quick Actions, Storage Health, Data Repair, Users/Roles, and Settings.
- Improved responsive header, admin nav, backup/import/restore cards, form grids, long warnings, job rows, and data repair details.
- Kept async backup/restore, Supabase support, imports, Reader, Translate, Admin, Login, Library, bookmarks, ratings, and reading history intact.
- Added public “No chapters imported yet.” messaging on novel cards.
- Kept Manage controls admin-only on public cards.
- Preserved strict Original / Reference / AI category separation.
- Preserved import warnings and destination category reporting.
- Bumped frontend cache/service-worker versions to v73.
- Ran syntax, API, import, backup, restore, content audit, repair, and browser layout QA without OpenAI calls.

## Remaining / Future Enhancements

- Optional streaming/chunked Supabase upload for extremely large completed backup ZIPs.
- Optional richer import preview before writing ZIP files.
- Optional manual file move/copy tools for uncertain content repair cases.

## Files Changed

- `DEVELOPMENT_PROGRESS.md`
- `static/app.js`
- `static/service-worker.js`
- `static/styles.css`
- `templates/index.html`
- `app/main.py`
- `app/novels.py`
- `tools/convert_legacy_backup_to_v7.py`

## QA Results

- v8.0.4 Python syntax check passed.
- v8.0.4 JavaScript syntax check passed.
- `requirements.txt` exists, is not `{}`, and contains FastAPI, Uvicorn, dotenv, multipart, OpenAI, and psycopg dependencies.
- `/api/health`, `/api/bootstrap`, `/api/storage`, `/api/novels`, and `/api/novels/i-am-god/library` returned 200 in TestClient.
- With active canonical Supabase counts present, `/api/storage` returned `recommended_recovery_action=none`.
- With active/canonical/legacy counts removed but a Supabase backup ZIP present, `/api/storage` returned `recommended_recovery_action=restore_from_supabase_backup`.
- `GET /api/admin/backups/supabase` listed the online Supabase backup after admin login.
- `POST /api/admin/backups/restore-from-supabase` with `dry_run=true` queued and completed without a local file.
- `POST /api/admin/backups/restore-from-supabase` with `confirm=true` queued without a local file.
- Migration dry-run with no legacy files returned `completed_no_changes`.
- Public admin backup/recovery endpoints returned 401.
- Public batch start returned 401.
- Admin login worked with a temporary QA password.
- `GET /api/batch/health` returned JSON.
- `POST /api/batch/estimate` returned JSON and did not call OpenAI.
- `POST /api/batch/start` with `dry_run=true` returned JSON/job data and did not call OpenAI.
- `GET /api/batch/jobs` returned JSON.
- No real translation was started.
- No production data deletion was performed.
- Note: a QA-only fake Supabase remote lacked `upload_tree`, causing one background mock log while an async restore thread ran; production `SupabaseStorage` implements `upload_tree`.
- v8.0.3 Python syntax check passed.
- v8.0.3 JavaScript syntax check passed.
- `/api/health`, `/api/storage`, `/api/novels`, and `/api/novels/i-am-god/library` returned 200 in TestClient.
- Public admin recovery endpoint returned 401.
- Public translate endpoint returned 401.
- Admin login worked with a temporary QA admin password.
- Simulated Supabase state with active/canonical/legacy chapter folders empty and one backup ZIP present.
- `/api/storage` returned `recommended_recovery_action=restore_from_supabase_backup` for that state.
- Admin deep discovery returned one backup ZIP and zero canonical/legacy chapter files.
- Legacy migration dry-run returned `completed_no_changes`, `files_to_copy=0`, and `next_recommended_action=restore_from_supabase_backup`.
- Supabase backup listing returned the backup ZIP.
- Restore-from-Supabase-backup dry-run returned 202 queued and completed through the existing async restore job.
- No OpenAI call was made.
- No translation was started.
- No production data deletion was performed.
- v8.0.2 Python syntax check passed.
- v8.0.2 JavaScript syntax check passed.
- `requirements.txt` exists, is included, is not `{}`, and contains valid FastAPI/Uvicorn/OpenAI/psycopg dependencies.
- Simulated live legacy Supabase layout under `app/novels/i-am-god/Original`, `Reference`, `AI`, `Prompts`, `Cover`, and `Backups`.
- `/api/health`, `/api/storage`, `/api/novels`, and `/api/novels/i-am-god/library` returned 200 with legacy remote data.
- Active counts used legacy files when canonical folders were empty.
- Reader loaded AI Translation text from legacy `app/novels/i-am-god/AI/0001.txt`.
- Public deep discovery returned 401.
- Admin login worked.
- Admin deep discovery returned legacy counts and one backup ZIP.
- Legacy migration dry-run returned a copy report and did not write canonical files.
- Real legacy migration copied legacy files to canonical paths without deleting legacy files.
- Rebuild index returned 200.
- Hydrate from Supabase returned 200 with fake active remote.
- Supabase backup listing returned the legacy backup ZIP.
- Restore from Supabase backup dry-run returned 202 queued through the existing async restore job.
- `HEAD /` returned 200.
- No OpenAI call was made.
- No translation was started.
- No production data deletion was performed.
- Python syntax check passed.
- JavaScript syntax check passed.
- `/api/health`, `/api/storage`, `/api/novels`, and `/api/novels/i-am-god/library` returned 200 in TestClient.
- Public admin rebuild endpoint returned 401.
- Public translate endpoint returned 401.
- Admin login worked with a temporary QA admin password.
- Simulated empty local cache with fake Supabase remote: `/api/novels`/library hydrated I Am God, rebuilt counts, preserved one original, one reference, one AI translation, and one prompt.
- Reader loaded Original Story and AI Translation text from `supabase://` remote markers when local files were missing.
- `POST /api/admin/index/rebuild` returned structured JSON and updated counts.
- `POST /api/admin/novels/i-am-god/hydrate-from-supabase` returns 400 when Supabase is not configured; the enabled-Supabase behavior was covered with fake remote manager hydration.
- Valid cover upload returned 201 and set a cover URL.
- Unsupported cover type returned a readable 400.
- Oversized cover returned a readable 400.
- Original ZIP import wrote originals only.
- Reference ZIP import wrote references only.
- AI ZIP import wrote AI translations only.
- Reader modes remained separate for Original Story, Reference Translation, and AI Translation.
- Full backup job start returned 202 queued in temp QA data.
- `/api/storage` includes `local_cache_counts`, `supabase_counts`, `database_counts`, and `active_counts_used_by_app`.
- Cache references verified at v75; service worker ignores `/api/` requests and only caches successful static responses.
- No OpenAI call was made.
- No translation was started.
- No production data deletion was performed.
- Legacy converter syntax check passed.
- Legacy converter dry-run detected 906 originals, 412 references, 25 AI translations, 241 prompts, and 1 cover.
- Converted backup ZIP contains `manifest.json`, `backup_info.json`, `novels/index.json`, `novels/i-am-god/metadata.json`, and canonical chapter folders.
- Converted backup ZIP secret scan found no OpenAI keys, Supabase service-role keys, or database URLs with embedded passwords.
- Python syntax check passed.
- JavaScript syntax check passed.
- Cache references bumped to v73 with no stale v70/v71/v72 references.
- `/api/health`, `/api/storage`, `/api/storage?deep=true`, `/api/novels`, and `/api/novels/i-am-god/library` returned 200.
- Public translate endpoint returned 401.
- Admin login worked in TestClient and browser UI.
- Original ZIP import wrote originals only.
- Reference ZIP import wrote references only.
- AI ZIP import wrote AI translations only.
- Suspicious import paths still generate warnings.
- Async backup start/status/download passed.
- Async restore dry-run passed.
- Content audit passed.
- Repair dry-run passed.
- Guest layout checked at 1280px and 390px: no horizontal overflow or offscreen visible elements.
- Admin settings layout checked at 1280px, 768px, and 390px: no horizontal overflow or offscreen visible elements.
- Backups/restore layout checked at 1280px, 768px, and 390px: no horizontal overflow or offscreen visible elements.
- Library layout checked at desktop and phone widths: no horizontal overflow or offscreen visible elements.
- No OpenAI call was made.
- No translation was started.
- No data deletion was performed.

## Known Risks

- Legacy migration copies files but does not delete legacy paths. This is intentional for safety.
- Restore-from-Supabase-backup uses the existing async restore path; backups without `manifest.json` remain dry-run only.
- Deep discovery lists bounded path sets and does not download large chapter or backup files.
- Supabase hydration is lazy and bounded. If `novels/index.json` is missing, the app lists only `novels/*/metadata.json` paths, then counts one opened novel at a time.
- The hydrate admin endpoint requires Supabase to be configured; local-only mode returns a clear 400.
- Async full backup writes ZIP contents incrementally, but Supabase upload still reads the completed ZIP into memory. For very large backups, streaming upload remains a future improvement.
- Restore without `manifest.json` is dry-run only.
- Content repair reports suspicious categories and refreshes indexes but does not automatically move uncertain files.

## Final Deploy Notes

Deploy `GodTranslator_Web_v8_0_2_Supabase_Legacy_Path_Recovery.zip` to Render with the existing settings. Keep `OPENAI_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and database credentials only in Render environment variables, never in the ZIP. After deploy, open Admin > Supabase Recovery and run Deep Scan Supabase first.

## Next Continuation Instructions

- Do not start translation unless explicitly requested.
- If `/api/storage` shows legacy counts but canonical counts are zero, run Migrate Legacy Paths dry-run, confirm if the report is correct, then Rebuild Supabase Index.
- If only backup ZIPs are found, run Restore From Supabase Backup dry-run first, then confirm restore if the report is correct.
- If Render still shows zero counts after redeploy, check `/api/storage` for `supabase_counts` and `active_counts_used_by_app`.
- If Supabase has files but `supabase_counts` is empty, run Admin > `Rebuild Supabase Index` or POST `/api/admin/index/rebuild`.
