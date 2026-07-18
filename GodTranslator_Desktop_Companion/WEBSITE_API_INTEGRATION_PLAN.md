# Website API Integration Plan v11

This document reviews the current GodTranslator website API surface available to the desktop companion and identifies missing endpoints needed for full sync.

## Existing Useful Endpoints

Public:

- `GET /api/health`
  - Used by Desktop Companion Test Connection.
- `GET /api/novels`
  - Useful for future library cache.
- `GET /api/novels/{novel_id}`
  - Useful for future novel-specific sync checks.

Admin/session/auth:

- `GET /api/admin/session`
  - Reports whether the current request is admin authenticated.
- `POST /api/admin/login`
  - Existing password login endpoint. Desktop Companion must not send Admin password as a URL parameter and should not store plaintext passwords.
- `POST /api/admin/logout`

Recovery:

- `GET /api/novels/{novel_id}/recovery/request`
  - Downloads a Reference Recovery Request JSON.
- `POST /api/novels/{novel_id}/recovery/preview`
  - Accepts `.zip` or `.txt` uploads through multipart form field `files`.
  - Supports Reference Recovery packs with manifest format `godtranslator-reference-pack-v1`.
  - Creates an import job and returns `job_id`.
- `POST /api/novels/{novel_id}/recovery/import/{job_id}`
  - Applies a previously previewed Reference import job.

Imports:

- `GET /api/import-jobs`
- `GET /api/import-jobs/{job_id}`

## Current Upload Support

Supported now:

- Reference Recovery Pack preview and apply, admin-authenticated.
- Single or multiple text files for Reference recovery, admin-authenticated.
- Desktop API health, auth check, sync status, and import history.
- Desktop pack preview and execution through Content Import.
- Original, Reference, English, Mixed, and New Novel pack formats.
- Version compatibility metadata through `desktop_api`, website `version`, Desktop version, and supported sync states.
- Manual bearer-token support for the current desktop session without writing tokens to local JSON.

Still future work:

- OAuth/device flow designed specifically for desktop apps.
- OS-backed secure token storage.

## Missing API Requirements

### Generic Pack Preview

Available:

```text
POST /api/desktop/import/preview-pack
```

Expected behavior:

- Accept multipart ZIP pack upload.
- Validate `manifest.json`.
- Support target modes: `reference`, `original`, `new_novel`.
- Report add/skip/overwrite/invalid counts.
- Reject secrets, unsafe paths, symlinks, huge files, and mismatched checksums.
- Return a preview job ID.

### Generic Pack Apply

Available:

```text
POST /api/desktop/import/execute-pack
```

Expected behavior:

- Default mode: add missing data only.
- Require explicit confirmation for overwrite.
- Return exact chapters added/skipped/failed.

### Original Import Packs

Needed support for:

- `godtranslator-original-pack-v1`
- Existing non-empty Original text must not be overwritten by default.

### New Novel Import Packs

Needed support for:

- `godtranslator-new-novel-pack-v1`
- Create novel metadata.
- Add Original chapters.
- Optionally add Reference chapters.
- Preview slug conflicts before apply.

### Sync Status

Available:

```text
GET /api/desktop/sync/status?novel_id=...
```

Expected response:

- Novel exists yes/no.
- Chapter counts by source.
- Missing Original/Reference/AI counts.
- Last import job.
- Last backup marker.

### Desktop Authentication

Needed later:

- OAuth/device flow or scoped token creation for desktop companion.
- Token can be stored by Windows Credential Manager or another secure OS-backed store.
- No plaintext Admin passwords in config files.

Current v11 foundation:

- Desktop API accepts existing Admin session cookies or Supabase bearer tokens.
- Desktop Companion does not send passwords to desktop endpoints.
- Manual bearer tokens are memory-only and are discarded on desktop restart.
- Durable auth is intentionally deferred until a device authorization endpoint and OS-backed storage are implemented.

## First Foundation Decision

The desktop companion implements:

- Public `/api/health` connection test.
- Manual token/session entry for authenticated endpoints, kept in memory only.
- Reference Recovery preview/apply client against existing website APIs.
- Generic pack upload queue with Preview, Execute Import, Retry, and Open Imported Novel actions.
- Sync summaries with pending uploads, failed uploads, queued uploads, last sync, Desktop version, Website version, Desktop API version, and compatibility status.

It documents device authorization and signed update packaging as remaining secure-production steps rather than storing unsafe credentials or implementing silent updates.

## Recovery Round Trip

1. Website exports a Recovery Request JSON for missing content.
2. Desktop Companion opens the request.
3. Desktop downloads the missing chapters through the normal visible-browser downloader.
4. Desktop builds a GodTranslator recovery pack.
5. Desktop uploads the pack for preview.
6. Website applies the import only after explicit confirmation.

Recovery remains missing-content-only. It does not create new chapter rows; Content Import handles chapter-row creation.
