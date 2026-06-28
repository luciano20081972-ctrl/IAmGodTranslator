# Render Deployment

## Build Command

```bash
pip install -r requirements.txt
```

## Start Command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Required Environment Variables

Set these in Render under your Web Service settings, in **Environment**:

```env
OPENAI_API_KEY=your OpenAI API key
OPENAI_MODEL=gpt-4o-mini
LOG_LEVEL=INFO
MAX_UPLOAD_BYTES=52428800
DATA_DIR=/var/data/IAmGodTranslator
```

Do not commit `.env`. Add `OPENAI_API_KEY` only in Render's environment variable UI.

## Deploy Steps

1. Create a GitHub repository.
2. Extract this ZIP and upload the files to the repository root.
3. In Render, choose **New +** then **Web Service**.
4. Connect the GitHub repository.
5. Set the build command and start command shown above.
6. Add the environment variables shown above.
7. Add a persistent disk mounted at `/var/data` if your Render service plan supports disks.
8. Deploy.
9. Open `https://your-render-service.onrender.com/api/health`; it should return `{"status":"ok"}`.
10. Open `https://your-render-service.onrender.com/` to use the translator.

## iPhone Safari

1. Open the deployed Render website in Safari on iPhone.
2. Sign in to Render if needed, then open the public app URL.
3. Upload chapters and review the cost estimate before starting translation.

## Add to Home Screen

1. Open the deployed app in Safari.
2. Tap the Share button.
3. Tap **Add to Home Screen**.
4. Keep the suggested name or enter `IAmGodTranslator`.
5. Tap **Add**.

Render services without a persistent disk use ephemeral storage. For long translation jobs, mount a persistent disk at `/var/data` and keep `DATA_DIR=/var/data/IAmGodTranslator`.

## Storage and Backups

- Uploaded Chinese chapters, NovelFire references, queue state, settings, prompts, translations, reports, glossary, and memory are stored under `DATA_DIR`.
- The web UI shows storage mode and saved file counts.
- Use **Download** for English translations, **Prompts** for saved prompts, and **Backup** for a full job ZIP.
- Use **Restore Backup** to upload a full job backup ZIP after a redeploy or migration.
