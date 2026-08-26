# GodTranslator v11.6 Cycle 2 Runtime and Downloader Diagnosis

Branch: `codex/iagt-self-hosted-performance-downloader-p3r-ui`

Starting SHA: `083c7f13c21b4722939733545d78493b043ebf76`

Expected `origin/main`: `2e471d882a6e8da0d6157ac68a22aefa3db1c8af`

## Runtime Findings

Local runtime was reproduced with a repository-local virtual environment:

```powershell
python -m venv .venv-cycle2
.\.venv-cycle2\Scripts\python.exe -m pip install -r IAmGodTranslator_Render_Deploy\requirements.txt -r GodTranslator_Desktop_Companion\requirements.txt
```

FastAPI launched successfully against isolated SQLite:

```powershell
$env:DATABASE_URL='sqlite:///C:/Users/lucia/AppData/Local/Temp/iagt-v11-6-cycle2.sqlite'
$env:AUTH_ENABLED='false'
$env:TRANSLATION_AUTOSTART='false'
.\.venv-cycle2\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8007
```

Observed startup issue: FastAPI reports `on_event` deprecation warnings. This is non-blocking for Cycle 2 and should be migrated to lifespan handling in a later backend-maintenance pass.

Docker was not available on the local PATH, so Docker Compose/self-hosted container behavior was not validated from this workspace.

## Performance Findings

| Metric | Result | Notes |
| --- | ---: | --- |
| `/` local response | 15.55 ms, 1,140 wire bytes | HTML shell compressed and `no-cache`. |
| `/healthz` | 8.70 ms, 82 bytes | `no-store`; under gzip threshold. |
| `/api/health` | 5.80 ms, 82 bytes | `no-store`; under gzip threshold. |
| `/api/desktop/health` | 6.15 ms, 609 bytes | `no-store`; under gzip threshold. |
| `/manifest.webmanifest` | 3.27 ms, 357 bytes | Cacheable for 1 hour. |
| `/sw.js` | 22.36 ms, 1,712 bytes | `no-cache`; updateable. |
| `/static/app.js?v=11.6.0` | 69.53 ms, 64,760 gzip wire bytes | Static cache header present. |
| `/static/styles.css?v=11.6.0` | 22.68 ms, 15,839 gzip wire bytes | Static cache header present. |
| Browser Home first load before duplicate-fetch fix | 1,561.60 ms, 20 requests | Empty local DB; included duplicate `/api/novels`. |
| Browser Home first load after duplicate-fetch fix | 658.34 ms, 18 requests | Empty local DB; no duplicate API path on first navigation. |
| Browser duplicate API signal | `/api/novels` requested twice before fix, once after fix | Fixed by in-flight cached GET dedupe and normal Home cache use. |

The strongest measured website issue in this cycle was duplicate route-start metadata fetching. The `cachedApi` helper now deduplicates in-flight GETs by URL so Home/route startup does not launch duplicate identical requests before the cache is populated.

## PWA Findings

- Manifest endpoint, icon, theme color, start URL, and standalone display are present.
- Service worker installs and activates in local Chromium.
- Browser smoke verified one service worker registration and controller ownership after reload.
- API responses observed by the browser kept `Cache-Control: no-store`.
- The service worker only handles same-origin GETs, bypasses `/api/`, `/auth/`, and `/admin/`, and cleans old cache versions on activation.
- Service worker script is served with `no-cache, must-revalidate`.

Unverified: iPhone Safari Add to Home Screen, private HTTPS behavior, and service-worker update behavior after a real server deployment.

## Desktop Companion Failure Map

| Subsystem | Status | Evidence | Fix/Next Step |
| --- | --- | --- | --- |
| App import | WORKING | Desktop unit tests import package. | None. |
| Local data root | WORKING | Tests and code use `%LOCALAPPDATA%\GodTranslatorDesktop`. | Preserve. |
| Job persistence | WORKING | Fixture tests cover queued, paused, resumed, restart recovery. | Preserve. |
| Pack creation | PARTIALLY WORKING | Checksums and secret exclusion pass; `第58章.txt` was not parsed before Cycle 2. | Fixed CJK chapter filename parsing. |
| Website sync client | PARTIALLY WORKING | Endpoints align, but default base URL is legacy Render. | Configure self-hosted URL after HTTPS architecture is known. |
| Authentication | PARTIALLY WORKING | Manual bearer token is memory-only and safe; no durable device flow exists. | Implement device authorization later; do not persist weak credentials. |
| NovelFire adapter | UNVERIFIED | Adapter wraps legacy HTTP/Playwright code; fixture tests pass but no live source test run. | Add source fixtures and selector health checks before live smoke. |
| Playwright package | WORKING | Local venv imports Playwright 1.62.0 and headless Chromium launched a data URL. | Browser binaries present locally; source-site behavior unverified. |
| GUI launch | UNVERIFIED | CustomTkinter installed; no manual GUI smoke was performed in this cycle. | Perform visible Windows GUI smoke in Cycle 3 if needed. |
| Server-side acquisition | NOT IMPLEMENTED | No web/server worker exists in committed code. | Design hybrid pipeline first. |

## API Compatibility

| Desktop Feature | Route | Compatibility | Action |
| --- | --- | --- | --- |
| Health | `GET /api/desktop/health` | Compatible | Stale exact-version QA fixed. |
| Auth check | `GET /api/desktop/auth/check` | Compatible, admin protected | Keep memory-only token until device flow exists. |
| Sync status | `GET /api/desktop/sync/status?novel_id=...` | Compatible | Uses current app version and desktop API version. |
| Import history | `GET /api/desktop/import-history` | Compatible | Limit capped to 100. |
| Pack preview | `POST /api/desktop/import/preview-pack` | Compatible | Admin protected. |
| Pack execute | `POST /api/desktop/import/execute-pack` | Compatible | Admin protected; explicit execution boundary preserved. |
| Recovery preview | `POST /api/novels/{novel_id}/recovery/preview` | Compatible | Admin/translator boundary unchanged. |
| Recovery import | `POST /api/novels/{novel_id}/recovery/import/{job_id}` | Compatible | Existing contract retained. |

## Acquisition Architecture Decision

Decision: **Hybrid**.

Evidence:

- Desktop Companion already has local state, Playwright support, pack creation, sync, and a source-adapter registry.
- The self-hosted Ubuntu server is not available for direct inspection from this workspace, so server-only acquisition would be speculative.
- Some sources may require an interactive browser session or manual verification; Desktop Companion remains useful for those cases.
- Routine non-interactive acquisition should move server-side later so the Windows PC is not mandatory for normal jobs.
- Both paths should feed the same validated import boundary rather than writing scraper output directly into canonical records.

Cycle 3 should add the server-side acquisition contract and one fixture-backed adapter implementation before enabling real source downloads.

## Source Adapter Audit

| Source | Current State | HTTP/Playwright | Notes |
| --- | --- | --- | --- |
| NovelFire / NovelPhoenix | Active adapter wrapping legacy downloader | HTTP and Playwright | Live selector health unverified; no CAPTCHA bypass. |
| 69Shuba | Planned descriptor | Unknown | Needs fixture contract before implementation. |
| Qidian | Planned descriptor | Likely interactive/restricted | Do not bypass access controls or paywalls. |
| Royal Road | Planned descriptor | Likely HTTP feasible | Needs robots/terms review and fixtures. |
| ScribbleHub | Planned descriptor | Likely HTTP feasible | Needs robots/terms review and fixtures. |

## Security Findings

- API/auth/readiness endpoints now use `no-store`.
- Service worker bypasses authenticated and admin paths.
- Desktop manual bearer token remains memory-only.
- No production `DATABASE_URL` was used.
- No OpenAI call was made.
- Server-side downloader must include SSRF allow/deny policy before it accepts arbitrary URLs.

## Cycle 3 Scope

1. Add self-hosted deployment artifacts only after inspecting the actual Caddy/Tailscale/MIL routes.
2. Add a server acquisition job model and adapter contract with fixture-only tests.
3. Add SSRF-safe URL validation for server acquisition.
4. Add one fixture-backed HTTP adapter path before any Playwright server worker.
5. Add Desktop Companion self-hosted URL configuration guidance and device authorization design.
6. Add browser performance profiling for real seeded Library/Reader flows, not just empty DB startup.
