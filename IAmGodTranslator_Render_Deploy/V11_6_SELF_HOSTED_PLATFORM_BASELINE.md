# GodTranslator v11.6 Self-Hosted Platform Baseline

Branch: `codex/iagt-self-hosted-performance-downloader-p3r-ui`

Baseline main: `2e471d882a6e8da0d6157ac68a22aefa3db1c8af`

## Audit Summary

- The website is a FastAPI app serving one static HTML shell, one large JavaScript bundle, one large stylesheet, and a vendored MiniSearch runtime.
- The current Render files are retained for compatibility, but self-hosting is now the primary architectural target.
- No committed Docker Compose/Caddy/Tailscale configuration exists for IAmGodTranslator yet.
- No committed web manifest or service worker existed before this pass.
- Reader navigation already has bounded in-memory chapter request deduplication and neighbor prefetch.
- Translation scheduling is already bounded and database-backed; this pass does not change it.
- Desktop Companion contains persistent local jobs, source adapter seams, Playwright-backed NovelFire download support, pack creation, and website sync endpoints. The remaining server-side acquisition decision should be made after real deployment inspection.

## Baseline Measurements

| Metric | Baseline |
| --- | ---: |
| `static/app.js` uncompressed | 285,476 bytes |
| `static/styles.css` uncompressed | 91,931 bytes |
| `static/app.js` gzip level 6 after this pass | 64,870 bytes, 77.3% smaller than raw |
| `static/styles.css` gzip level 6 after this pass | 16,113 bytes, 82.6% smaller than raw |
| Committed service worker | none |
| Committed web manifest | none |
| Static response compression | none configured in app |
| Explicit API no-store headers | none configured globally |
| Private HTTPS server state | not accessible from this workspace |
| Market Intelligence Lab route state | local project present but untracked; no server mutation performed |

## Implemented Foundation

- Added FastAPI GZip compression for responses larger than 1 KB.
- Added cache headers for static assets while keeping API/auth responses `no-store`.
- Added `/healthz` as a deployment/readiness alias for existing `/api/health`.
- Added a versioned app-shell service worker and web manifest for iPhone/PWA groundwork.
- The service worker caches only the app shell and same-origin static assets; it deliberately excludes `/api/`, `/auth/`, and `/admin/`.
- Added original Dark Hour blue/navy/cyan design tokens and an original SVG app icon. No Persona, Atlus, or SEGA assets are bundled or referenced.

## Architecture Decision

This pass deliberately avoids adopting Dexie, Workbox, server-side Playwright workers, Redis, Celery, or additional frontend libraries. The current evidence supports standard platform primitives first: HTTP compression, explicit cache policy, app-shell caching, and measurement gates.

## Remaining Work

- Inspect the actual Ubuntu VM, Docker Compose, Caddy, and Tailscale state before changing HTTPS routing.
- Measure real Home, Library, novel, chapter, and chapter-next latency with production-like data.
- Add server-side acquisition only after confirming resource limits and SSRF controls.
- Decide whether Desktop-only, server-only, or hybrid acquisition is best after real downloader smoke tests.
- Consider IndexedDB chapter caching after auth/privacy rules are specified.
- Migrate more screens to the Dark Hour visual system incrementally while keeping Reader text calm.
