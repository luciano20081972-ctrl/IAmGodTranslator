# GodTranslator v11.6 Cycle 4 Reader Performance and Local-First Report

Branch: `codex/iagt-self-hosted-performance-downloader-p3r-ui`

Starting Cycle 4 SHA: `018d1615aeb5b70c1862804785dec333747a4bbe`

Expected `origin/main`: `2e471d882a6e8da0d6157ac68a22aefa3db1c8af`

## Scope

Cycle 4 focused only on Reader performance, local-first reading, bounded prefetch, chapter-list scale, and regression safety after the Cycle 3 acquisition security foundation.

No production database was used. No production content was used. No OpenAI call was made. No live novel-source scraping was performed.

## Reader Data Flow

```text
Canonical chapter row
  -> /api/novels/{novel}/chapters/{chapter}/{source}
  -> text + content_hash + existing-row neighbors
  -> readerRequestMap in-flight dedupe
  -> in-memory readerCache
  -> bounded IndexedDB reader cache
  -> Reader render
  -> next-chapter prefetch through the same fetcher
```

The server remains canonical. The local cache is a short-lived reading accelerator and offline fallback for chapters the user has already opened or prefetched.

## Reader Bottlenecks

| Finding | Before | Cycle 4 Result |
| --- | --- | --- |
| Chapter list search | Rendered 50 rows but fetched `/library?limit=5000...` for client-side search | Uses server-side `search`, current `limit`, and current `offset` |
| Reader repeat navigation | In-memory repeat route was fast, but only inside the current browser session | Adds bounded IndexedDB cache for reload/offline continuity |
| Prefetch ownership | Next chapter prefetch existed but could race with a foreground click | Foreground clicks reuse in-flight prefetch requests |
| Progress writes | Scroll progress could write too often while reading | Local progress updates immediately; account sync is throttled and flushed on route/page lifecycle |
| Reader API navigation | Neighbor discovery depended on local chapter arrays | Chapter API now returns previous/next existing-row neighbors |

## Local-First Reader Cache

Implementation: native IndexedDB database `iagt-reader-cache-v1`, object store `chapters`.

Cache key:

```text
{namespace}:{novelId}:{chapterNumber}:{source}
```

Namespace:

- signed-in user: `user:{user_id}`
- guest: `guest`

Limits:

- 12 chapters per namespace
- 2,500,000 bytes per namespace
- 24-hour TTL

Invalidation:

- server chapter responses include a SHA-256 `content_hash`;
- cached chapters are returned immediately when valid;
- online cache hits trigger background revalidation;
- a changed hash refreshes both in-memory and IndexedDB cache.

Authenticated content is not stored with the browser Cache Storage API. Service worker caching remains limited to the app shell and explicitly excludes `/api/` and `/auth/`.

User control: Privacy settings include `Clear Offline Reader Cache`.

## Progress Sync

Reader scroll progress is still stored locally immediately so route changes and refreshes preserve the reading position.

For signed-in users, remote progress sync is queued and throttled to at most once every 5 seconds. Pending progress is flushed on hash-route changes, `visibilitychange` to hidden, and `pagehide`.

The sync payload includes `client_updated_at` for future conflict-aware progress handling. No database migration was added in Cycle 4.

## Large-Library and Large-Chapter Behavior

Synthetic fixture:

| Seed Item | Count |
| --- | ---: |
| Novels | 60 |
| Total chapters | 1,908 |
| Largest novel | `seed-large-000` |
| Largest novel chapters | 1,200 |

Chapter lists now request the current page only:

```text
/api/novels/seed-large-000/library?limit=50&offset=0&view=all
```

Server-side chapter search is used instead of a 5,000-row client search index. Pagination remains 50 mounted rows, which avoided a 1,200-row DOM explosion in the seeded browser profile.

The main remaining large-library pressure is the Library route itself. With 60 seeded novels it still rendered 1,065 DOM nodes. This was measured but not changed because Cycle 4 prioritized the Reader and chapter-list critical path.

## Performance Results

API benchmark, isolated SQLite fixture:

| Metric | Cycle 3 Baseline | Cycle 4 Result | Notes |
| --- | ---: | ---: | --- |
| `/api/novels` | 23.76 ms mean | 33.62 ms mean | Same payload; variance on local run |
| Novel details | 26.55 ms mean | 17.41 ms mean | Healthy |
| Chapter library page 1 | 26.50 ms mean | 19.88 ms mean | 50-row page |
| Chapter library near offset 950 | 28.51 ms mean | 19.67 ms mean | Stable offset pagination |
| Reader chapter 1 | 12.60 ms mean, 2,156 bytes | 7.20 ms mean, 2,277 bytes | Includes hash/neighbors metadata |
| Reader chapter 2 | 7.77 ms mean | 6.95 ms mean | Healthy |
| Reader chapter 1200 | 6.99 ms mean | 6.88 ms mean | Healthy |

Browser benchmark, Chromium against local seeded server:

| Metric | Cycle 3 Baseline | Cycle 4 Result | Notes |
| --- | ---: | ---: | --- |
| Home route | 29.17 ms, 175 DOM | 25.83 ms, 175 DOM | Stable |
| Library route | 274.05 ms, 1 API, 1,065 DOM | 271.53 ms, 1 API, 1,065 DOM | Not optimized this cycle |
| Novel detail | 271.15 ms, 2 API, 159 DOM | 268.29 ms, 2 API, 159 DOM | Stable |
| Chapter list | 276.03 ms, 1 API, 349 DOM | 272.92 ms, 1 API, 349 DOM | Now requests only 50 rows |
| Reader chapter 1 | 276.25 ms, 2 API, 420 DOM | 276.81 ms, 2 API, 420 DOM | Includes foreground plus prefetch |
| Reader chapter 2 | 8.44 ms, 1 API, 421 DOM | 7.95 ms, 1 API, 421 DOM | Chapter 2 reused prefetch; only chapter 3 fetched |
| Repeat Reader chapter 1 | 6.79 ms, 0 API, 421 DOM | 6.90 ms, 0 API, 421 DOM | Cached route |
| Console errors | 0 | 0 | Clean |

Offline/cache smoke:

| Check | Result |
| --- | --- |
| Chapter 1 foreground request | PASS |
| Chapter 2 prefetch request | PASS |
| Opening Chapter 2 reused cached/prefetched content | PASS |
| Sequential navigation retained bounded cache | PASS, 12 records |
| Offline reopen of cached Chapter 21 | PASS |
| DOM after 20-chapter soak | PASS, 193 nodes |

## Mobile and PWA

PWA smoke against the local seeded server passed:

- service worker registered and controlled reload;
- app shell assets used version `11.6.1`;
- `/api/` and `/auth/` remained excluded from service-worker caching;
- no duplicate API paths;
- no console errors.

Safari-specific validation remains incomplete. Cycle 4 used Chromium/Playwright and desktop-local profiling only. Installed iOS Safari PWA behavior, BFCache edge cases, and real device memory pressure should be validated before treating offline Reader behavior as fully mobile-certified.

## Regression Testing

Passed checks:

- `git diff --check`
- `node --check IAmGodTranslator_Render_Deploy/static/app.js`
- `python -m py_compile` for `app/main.py`, `app/db.py`, v11.6 QA/browser scripts, acquisition QA, scheduler QA, and Desktop Companion test modules
- `tools/qa_v11_6_cycle4_reader_performance.py`
- `tools/profile_v11_6_seeded.py`
- `tools/browser_v11_6_seeded_profile.py`
- `tools/browser_v11_6_reader_cache_smoke.py`
- `tools/profile_v11_6_runtime.py`
- `tools/browser_v11_6_pwa_smoke.py`
- `tools/qa_v11_6_self_hosted_platform.py`
- `tools/qa_v11_6_cycle3_acquisition.py`
- `tools/qa_v11_5_reader_platform.py`
- `tools/qa_v11_phase6_desktop_sync.py`
- `tools/qa_v10_6_desktop_integration.py`
- `tools/qa_v10_6_translation_selector.py`
- `tools/qa_v10_3_translation_scheduler.py`
- Desktop Companion unit tests

Acquisition regression remained green. The Cycle 3 SSRF policy, fixture adapter, disabled live-fetching posture, and Desktop URL configuration were preserved.

## Remaining Work

Recommended Cycle 5 scope:

1. Add Library pagination or incremental rendering if real libraries grow beyond low hundreds of novels.
2. Validate offline Reader behavior on real iPhone Safari, Android Chrome, tablet, and installed PWA contexts.
3. Add conflict-aware progress versioning on the server side if multi-device reading becomes a frequent workflow.
4. Review cache-clear/account-boundary UX for shared devices.
5. Continue acquisition persistence and import staging only after the secure source policy is complete.

## Verdict

READY FOR CYCLE 5
