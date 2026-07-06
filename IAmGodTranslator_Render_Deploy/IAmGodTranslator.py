OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
ADMIN_PASSWORD=
SESSION_SECRET=
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
PYTHON_VERSION=3.12.7
# Optional. Leave blank locally to use ./data. Render Free can use data plus Supabase, or a persistent disk path on paid plans.
DATA_DIR=data
# Optional. Leave blank to use SQLite at DATA_DIR/godtranslator.db. sqlite:///... is supported in this lightweight build.
DATABASE_URL=
# Optional. Use local unless set to supabase.
STORAGE_BACKEND=local
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_BUCKET=novel-files
# Keep true on Render Free so Supabase reads/scans never block startup before the web port opens.
DISABLE_STARTUP_REMOTE_SYNC=true
SUPABASE_TIMEOUT_SECONDS=10
SUPABASE_HEALTH_TIMEOUT_SECONDS=5
# Optional account email settings. Do not commit real secrets.
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SITE_URL=https://iamgodtranslator.onrender.com
# Optional Google OAuth. Button stays disabled until all three are configured.
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
