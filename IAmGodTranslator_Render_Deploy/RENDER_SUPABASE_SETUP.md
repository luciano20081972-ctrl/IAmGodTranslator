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

## 2. Add Render Environment Variables

Set these on Render:

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=your Supabase project URL
SUPABASE_ANON_KEY=your Supabase anon key
SUPABASE_SERVICE_ROLE_KEY=your Supabase service role key
SUPABASE_BUCKET=novel-files
DATABASE_URL=your Supabase Postgres connection string
OPENAI_API_KEY=your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
PYTHON_VERSION=3.12.0
ADMIN_PASSWORD=choose a private admin password
SESSION_SECRET=choose a long random secret
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
5. Click `Migrate Local Data to Supabase`.
6. Download a Full Backup ZIP after migration.

## 4. Notes

Render Free may sleep when inactive. That is acceptable for personal/testing use because Supabase stores the durable data. Later, when traffic or users exist, upgrade Render to Starter. If Supabase Free limits or pauses become a problem, upgrade Supabase.

Automatic novel ingestion from external websites is intentionally not included. Only import content you own, have permission to use, or are legally allowed to process.
