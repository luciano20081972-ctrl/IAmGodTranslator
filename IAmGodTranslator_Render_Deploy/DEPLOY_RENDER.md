# Render Deployment

## Commands

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Root Directory, if this project is in a subfolder:

```text
IAmGodTranslator_Render_Deploy
```

## Environment Variables

```env
OPENAI_API_KEY=your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
ADMIN_PASSWORD=choose a private admin password
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
DATA_DIR=/var/data/IAmGodTranslator
STORAGE_BACKEND=local
```

Never commit `.env`. Without `ADMIN_PASSWORD`, admin login is disabled and private controls remain hidden.

For Supabase Storage persistence instead of local Render disk storage, set:

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=your Supabase project URL
SUPABASE_SERVICE_ROLE_KEY=your service role key
SUPABASE_BUCKET=novel-data
```

Keep `SUPABASE_SERVICE_ROLE_KEY` only in Render environment variables. It is used by the FastAPI backend and must never be exposed in frontend JavaScript.

## Persistent Disk

For long translation jobs, attach a Render persistent disk mounted at `/var/data` and keep `DATA_DIR=/var/data/IAmGodTranslator`.

The app stores novels under `DATA_DIR/novels/<novel_id>/`. Legacy jobs migrate into `DATA_DIR/novels/i-am-god/jobs/` without deleting the old folders.

## Verify

After deploy, open:

```text
https://your-render-service.onrender.com/api/health
https://your-render-service.onrender.com/api/storage
https://your-render-service.onrender.com/api/novels
```

## iPhone

Open the deployed app in Safari, open a translated chapter in Reader, tap Share, then Add to Home Screen.
