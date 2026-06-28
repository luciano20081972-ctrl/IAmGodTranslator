# IAmGodTranslator Web v2

FastAPI web app for translating web novel chapters while preserving the existing Python translator modules. Version 2 adds a multi-novel library, per-novel storage, online reader, backups, and restore tools.

## Features

- Novel Library home with search, sorting, and novel cards.
- Per-novel dashboard for Chapters, Reader, Translate, Backups, and Settings.
- Original Story uploads for source chapters.
- Optional Reference Translation uploads for support/reference text.
- Queue and cost estimate before translation.
- Explicit Start Batch button with paid translation warning.
- Online reader with Translation, Original Story, Reference Translation, and Prompt tabs.
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
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
DATA_DIR=/var/data/IAmGodTranslator
```

Do not commit `.env`. For long jobs, attach a Render persistent disk mounted at `/var/data`.

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
- Release ZIPs must exclude `.env`, API keys, `.venv`, `__pycache__`, runtime job data, logs, generated prompts, and generated translations.
