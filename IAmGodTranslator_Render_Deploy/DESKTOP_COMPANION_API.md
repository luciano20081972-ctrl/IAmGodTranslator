# GodTranslator v10.6 Desktop Companion API

v10.6 adds Desktop Companion integration without changing translation scheduling, authentication design, PostgreSQL layout, Recovery, or Content Import.

## Authentication

Desktop endpoints that read or change protected data use the existing admin protection. The Desktop Companion sends a user-provided bearer session token when available and never stores website passwords.

## Public Health

`GET /api/desktop/health`

Returns website health, schema, version, desktop API version, and supported desktop features.

## Protected Desktop Endpoints

- `GET /api/desktop/auth/check`
- `GET /api/desktop/sync/status?novel_id=...`
- `GET /api/desktop/import-history?novel_id=...&limit=20`
- `POST /api/desktop/import/preview-pack`
- `POST /api/desktop/import/execute-pack`

The pack endpoints accept multipart `files` uploads and the same query fields as Content Import:

- `novel_id`
- `novel_title`
- `author`
- `source_url`
- `content_type`
- `overwrite_existing`
- `dry_run`

## Recovery

Recovery remains available through:

- `GET /api/novels/{novel_id}/recovery/request`
- `POST /api/novels/{novel_id}/recovery/preview`
- `POST /api/novels/{novel_id}/recovery/import/{job_id}`

The Desktop Companion can open a Recovery Request, download missing files locally, build a pack, preview import, execute import, and open the imported novel.

## Safety

- Preview before execute remains the default workflow.
- Add-missing remains the default import behavior.
- No production data is modified by tests.
- OpenAI is not called by Desktop Companion sync or import APIs.
