# IAmGodTranslator Web v1

FastAPI web app for translating Chinese web novel chapters into English while reusing the existing translator backend modules.

## Features

- Upload Chinese `.txt` chapters or a `.zip` of chapters.
- Upload optional NovelFire `.txt` references or a `.zip` of references.
- Build and persist a per-job translation queue.
- Translate queued chapters through the OpenAI Responses API.
- Save generated prompts and English translations per job.
- Download individual translated chapters or all completed chapters as a ZIP.
- Estimate cost before translation with `gpt-4o-mini` as the default cheapest model.
- Mobile-friendly HTML/CSS/JavaScript frontend with no React, Vue, or Angular.
- PWA manifest and service worker for iPhone Safari "Add to Home Screen".

## Preserved Backend Modules

The web app still uses:

- `modules/chapter.py`
- `modules/context.py`
- `modules/prompt_builder.py`
- `modules/prompt_writer.py`
- `modules/save_translation.py`
- `modules/api.py`
- `modules/memory.py`
- `modules/glossary.py`
- `modules/queue.py`
- `modules/style.py`

## Local Setup

Use Python 3.12 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o-mini
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
DATA_DIR=
```

Run the app:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Render Free Deployment

The release includes `render.yaml`, so Render can deploy it directly from a GitHub repo.

1. Create a new GitHub repository.
2. Upload this release ZIP contents to the repository root.
3. Do not commit `.env`.
4. In Render, choose **New +** then **Blueprint** if using `render.yaml`, or **Web Service** for manual setup.
5. Connect the GitHub repository.
6. If using manual setup:
   - Runtime: `Python`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Instance type: `Free`
7. Add environment variables in Render:
   - `OPENAI_API_KEY`: your OpenAI API key
   - `OPENAI_MODEL`: `gpt-4o-mini`
   - `DATA_DIR`: `/var/data/IAmGodTranslator`
   - `LOG_LEVEL`: `INFO`
8. Add a Render persistent disk mounted at `/var/data` if your Render service plan supports disks.
9. Deploy.
10. After deploy, open the Render URL and verify `/api/health` returns:

```json
{"status":"ok"}
```

Render instances without a persistent disk use ephemeral local storage. For long translation jobs, use a persistent disk mounted at `/var/data` with `DATA_DIR=/var/data/IAmGodTranslator`.

## iPhone Home Screen

On iPhone Safari:

1. Open the deployed app URL.
2. Tap the Share button.
3. Tap **Add to Home Screen**.
4. Launch from the Home Screen icon.

The app includes Apple web app meta tags, `manifest.json`, an SVG icon, and `service-worker.js`.

## Data Layout

Uploaded jobs are stored under:

```text
<DATA_DIR or ./data>/jobs/<job_id>/
  Chinese/
  NovelFire/
  Prompts/
  English/
  Logs/
  Output/
  state.json
```

Each job gets its own copy of `memory.json`, `glossary.json`, and `style.json`.
The app keeps persistent copies of `memory.json`, `glossary.json`, and `style.json` under `<DATA_DIR>/config/`.
Full job backups are saved under `<DATA_DIR>/backups/` when downloaded.

## Notes

- `OPENAI_API_KEY` is read from `.env` locally or from the hosting environment in production.
- Secrets are never hardcoded.
- Default safety settings stop at one test chapter, use `gpt-4o-mini`, and allow at most one retry for failed chapters.
- Queue state is persisted to both `state.json` and `Logs/translation_queue.json`.
- Queued or running jobs are resumed automatically on app startup.
- `/api/storage` reports storage mode and saved file counts.
- Each job can download English translations, saved prompts, or a full backup ZIP.
- Backup ZIPs can be restored from the web UI.
