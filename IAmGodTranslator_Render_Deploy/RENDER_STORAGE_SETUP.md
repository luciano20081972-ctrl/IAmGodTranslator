# Render Storage Setup

GodTranslator can run locally with `DATA_DIR=data`. On Render, use a persistent disk so novels, chapters, prompts, covers, settings, backups, and the account database survive restarts.

## Recommended Render Settings

1. Add a Render persistent disk.
2. Set the disk mount path to:
   `/var/data`
3. Set this environment variable:
   `DATA_DIR=/var/data/godtranslator`
4. Optional database setting:
   `DATABASE_URL=sqlite:////var/data/godtranslator/godtranslator.db`
5. Redeploy the service.
6. Open Admin -> Storage Health and confirm the resolved path is under `/var/data`.
7. Download a Full Backup ZIP after every translation batch.

## Environment Variables

Required for translation:

`OPENAI_API_KEY`
`OPENAI_MODEL=gpt-4o-mini`

Required for private admin tools:

`ADMIN_PASSWORD`
`SESSION_SECRET`

Optional account email setup:

`SMTP_HOST`
`SMTP_PORT`
`SMTP_USER`
`SMTP_PASSWORD`
`SMTP_FROM`
`SITE_URL`

Optional future Google OAuth setup:

`GOOGLE_CLIENT_ID`
`GOOGLE_CLIENT_SECRET`
`GOOGLE_REDIRECT_URI`

## Notes

Do not commit `.env` files or secrets. If `DATA_DIR` is accidentally set to `date`, `/api/storage` will show an admin warning. If old local data exists in `date`, `data`, or `Archive`, use the admin-only migration endpoint to copy it into the configured `DATA_DIR` without deleting the original files.
