# GodTranslator v10.2 Auth Setup

GodTranslator supports public guest reading plus optional Supabase Auth accounts.

## Environment Variables

Server-only:

```text
ADMIN_PASSWORD
ADMIN_EMAILS
DATABASE_URL
DB_SCHEMA=godtranslator_v10
```

Public Supabase Auth config sent to the browser:

```text
AUTH_ENABLED=true
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_AUTH_REDIRECT_URL
```

Never expose:

- `DATABASE_URL`
- Supabase service-role keys
- Google OAuth client secret
- `ADMIN_PASSWORD`
- user access or refresh tokens

## Email And Password

Enable Email provider in Supabase Auth. Users can sign up, sign in, reset password, and sign out from `#/account`.

## Google Login

Enable Google provider in Supabase Auth and configure the Google OAuth client in Supabase.

Allowed redirect URLs:

```text
http://127.0.0.1:8001/auth/callback
https://iamgodtranslator.onrender.com/auth/callback
```

The browser receives only `SUPABASE_PUBLISHABLE_KEY`, never a Google secret.

## Roles

Roles are resolved server-side.

- `guest`: browse and read public chapters
- `user`: personal preferences, progress, bookmarks, favorites, history
- `translator`: Translate workspace, Job Center, comparison tools
- `admin`: all permissions, novel management, Recovery, Admin, backup/export

`ADMIN_EMAILS` bootstraps admin role server-side. Users cannot self-promote from browser payloads.

Recovery diagnostic, request export, preview, import, and backup/export endpoints are admin-only. Translator access does not grant Recovery or Admin operations.

## Render Configuration

Add these in the Render service Environment tab:

```text
DATABASE_URL: Supabase pooled Postgres connection string
DB_SCHEMA=godtranslator_v10
ADMIN_PASSWORD: private emergency password
ADMIN_EMAILS=you@example.com
AUTH_ENABLED=true
SUPABASE_URL=<your Supabase project URL>
SUPABASE_PUBLISHABLE_KEY=<your publishable anon key>
SUPABASE_AUTH_REDIRECT_URL=https://iamgodtranslator.onrender.com/auth/callback
OPENAI_MODEL=gpt-4o-mini
OPENAI_MODEL_REGISTRY=gpt-4o-mini,gpt-4o
```

Only add `OPENAI_API_KEY` when you are ready to run real translations. It is not needed for browsing, accounts, estimates, recovery, or mock QA.

## Supabase Provider Configuration

In Supabase:

1. Open Authentication.
2. Enable Email provider for email/password accounts.
3. Enable Google provider only after adding a Google OAuth client.
4. Add redirect URLs:

```text
http://127.0.0.1:8001/auth/callback
https://iamgodtranslator.onrender.com/auth/callback
```

## Google OAuth Configuration

In Google Cloud Console:

1. Create an OAuth web client.
2. Add the Supabase callback URL shown in Supabase's Google provider page.
3. Paste the Google client ID and secret into Supabase, not into GodTranslator.
4. GodTranslator receives only Supabase's publishable key.

## Troubleshooting

- If Account says features are not configured, check `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `AUTH_ENABLED`.
- If Google returns a redirect error, verify both local and production callback URLs.
- If an admin email does not become admin, verify `ADMIN_EMAILS` spelling and sign out/in again.
- If emergency admin login fails, verify `ADMIN_PASSWORD`.
- If Auth works but account preferences fail, verify `DATABASE_URL` and `DB_SCHEMA`.
