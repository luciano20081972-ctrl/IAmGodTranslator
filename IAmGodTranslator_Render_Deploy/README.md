# IAmGodTranslator Web v3

FastAPI web app for translating and reading web novel chapters while preserving the existing Python translator modules. Version 3 adds public reader pages with admin-only translation, import, backup, and settings controls.

## Features

- Novel Library home with search, sorting, and novel cards.
- Public per-novel dashboard for Chapters and Reader.
- Admin-only Translate, Backups, Settings, imports, restores, downloads, cover upload, and app icon upload.
- Original Story uploads for source chapters.
- Optional Reference Translation uploads for support/reference text.
- Queue and cost estimate before translation.
- Explicit Start Batch button with paid translation warning.
- Online reader with separate Original Story, Reference Translation, and AI Translation modes.
- Download English ZIP, prompts ZIP, single translated chapters, or full novel backup ZIP.
- Restore a full novel backup ZIP.
- Persistent storage through `DATA_DIR`, suitable for Render persistent disks.
- Mobile-friendly PWA with Safari Add to Home Screen support.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set `OPENAI_API_KEY` only in `.env` locally or in the hosting environment.

## Render Settings

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Root Directory: `IAmGodTranslator_Render_Deploy` if this folder is inside a larger repository.

Environment variables:

```env
OPENAI_API_KEY=your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
ADMIN_PASSWORD=choose a private admin password
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
DATA_DIR=/var/data/IAmGodTranslator
```

Do not commit `.env`. Set `ADMIN_PASSWORD` on Render or the admin tools stay hidden and locked. For long jobs, attach a Render persistent disk mounted at `/var/data`.

## Data Layout

```text
<DATA_DIR or ./data>/
  novels/
    i-am-god/
      metadata.json
      Original/
      Reference/
      jobs/
      Backups/
      Output/
```

Legacy `<DATA_DIR>/jobs/*` folders are copied into `novels/i-am-god/jobs/` on startup. The old folders are not deleted.

## iPhone Home Screen

Open the deployed Render URL in Safari, tap Share, choose Add to Home Screen, then launch the app from the Home Screen icon.

## Safety

- Cost estimates do not call OpenAI.
- Uploads and estimates do not start translation automatically.
- Translation starts only after pressing Start Batch and confirming.
- Public visitors can read available chapters but cannot modify data or start paid work.
- Release ZIPs must exclude `.env`, API keys, `.venv`, `__pycache__`, runtime job data, logs, generated prompts, and generated translations.
