# Render Free + Supabase Setup

GodTranslator can stay on Render Free while Supabase stores long-term data. Render may sleep when inactive, but uploaded chapters, covers, backups, prompts, exports, accounts, bookmarks, ratings, and reading history should live in Supabase when Supabase is active.

## 1. Create Supabase

1. Create a Supabase project.
2. Create private Storage buckets:
   - `novel-files`
   - `covers`
   - `backups`
   - `exports`
3. Copy these values from Supabase:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `DATABASE_URL`

For `DATABASE_URL` on Render, use Supabase Connect -> Connection Pooling / Supavisor. Choose the Transaction pooler or Session pooler connection string. Do not use the direct connection string on Render if it resolves to IPv6, because Render may show `Network is unreachable`.

## 2. Add Render Environment Variables

Set these on Render:

```env
STORAGE_BACKEND=supabase
DATA_DIR=data
SUPABASE_URL=your Supabase project URL
SUPABASE_ANON_KEY=your Supabase anon key
SUPABASE_SERVICE_ROLE_KEY=your Supabase service role key
SUPABASE_BUCKET=novel-files
DATABASE_URL=your Supabase pooler/Supavisor Postgres connection string
OPENAI_API_KEY=your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
PYTHON_VERSION=3.12.7
ADMIN_PASSWORD=choose a private admin password
SESSION_SECRET=choose a long random secret
SITE_URL=https://iamgodtranslator.onrender.com
DISABLE_STARTUP_REMOTE_SYNC=true
```

Never commit `.env`, API keys, database passwords, or service role keys. The service role key is used only by the FastAPI backend.

## 3. Deploy

1. Redeploy the Render service.
2. Open `/api/storage`.
3. Confirm:
   - storage backend is `supabase`
   - Supabase is configured
   - database backend is `postgres`
   - storage warnings are clear or understood
4. Open Admin -> Storage Health.
5. Click `Migrate Local Data to Supabase` if local data needs to be copied up.
6. Use the smaller ZIP exports/imports for Original, Reference, AI Translation, and Prompts.
7. Admin -> Backups can start a background Full Backup job. It creates a manifest ZIP and, when possible, uploads the completed ZIP to the private `backups` bucket after the local file is complete.
8. Full restore uses an admin-only background job. Upload a backup ZIP, run dry-run first, review the report, then confirm a real restore if needed.

## 4. Notes

Render Free may sleep when inactive. That is acceptable for personal/testing use because Supabase stores the durable data. Later, when traffic or users exist, upgrade Render to Starter. If Supabase Free limits or pauses become a problem, upgrade Supabase.

Keep `DISABLE_STARTUP_REMOTE_SYNC=true` on Render Free. The app will bind to `$PORT` first and use Supabase during normal API requests/imports, instead of scanning or restoring remote storage during startup.

Automatic novel ingestion from external websites is intentionally not included. Only import content you own, have permission to use, or are legally allowed to process.

## Backup Job Notes

Full backups are asynchronous so a large backup does not block the web request that starts it. The backup ZIP includes a `manifest.json`, `backup_info.json`, novel metadata, original chapters, reference chapters, AI translations, prompts, and covers. It does not include `.env`, logs, sessions, databases, runtime job files, generated release ZIPs, or secrets.

Full restore is also asynchronous. Restore validates `manifest.json` and maps only canonical paths:

- `novels/{novel_id}/originals/{chapter}.txt`
- `novels/{novel_id}/references/{chapter}.txt`
- `novels/{novel_id}/ai_translations/{chapter}.txt`
- `novels/{novel_id}/prompts/{chapter}.txt`

If a backup has no manifest, the app allows dry-run only and skips uncertain files. Restore never deletes files. Existing files are handled by the selected conflict mode.

If a process restarts during a backup, the interrupted job is marked `stale` on the next startup. Start a new backup job after the app is healthy.

Content audit/repair tools are admin-only and conservative. They report old or suspicious paths and can refresh the local novel index, but they do not automatically move uncertain reference/AI files.

## v8.1 Translate and Google Login Notes

Translate tools are admin-only. Use Translation Health first, then Cost Estimate, then Start Batch. Estimates and dry-runs do not call OpenAI. Real translation requires `OPENAI_API_KEY` and should use `OPENAI_MODEL=gpt-4o-mini` unless you intentionally choose another model.

Batch settings default to missing AI translations only, no overwrite, and concurrency 1. Concurrency 2 or 3 may spend faster and may hit rate limits.

Google login has a safe disabled placeholder in this build. The UI checks `/api/auth/google/status` and shows a disabled button unless OAuth is fully enabled. Keep `GOOGLE_CLIENT_SECRET` only in Render environment variables; never expose it to static JavaScript.
