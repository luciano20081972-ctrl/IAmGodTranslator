# GodTranslator v11.6 Cycle 3 Hybrid Acquisition and Seeded Performance Report

Branch: `codex/iagt-self-hosted-performance-downloader-p3r-ui`

Starting SHA: `604b7f0f331534963aabb71bb3dba24bcb84bc30`

Expected `origin/main`: `2e471d882a6e8da0d6157ac68a22aefa3db1c8af`

## Acquisition Architecture

Cycle 3 confirms the v11.6 direction remains **Hybrid acquisition**.

| Capability | Server | Desktop Companion |
| --- | ---: | ---: |
| Static HTTP source | Yes, after source-specific allowlist and fixture coverage | Optional |
| Scheduled acquisition | Future server job | No |
| Interactive browser source | Maybe later after host inspection and resource budgeting | Yes |
| Manual login-required source | No by default | Yes, user-controlled |
| Pack build | Yes/shared boundary later | Yes |
| Import preview | Website | Website |
| Canonical write | Website import API only | Website import API only |

The new server acquisition foundation is intentionally a contract layer, not a live external downloader. It defines:

- `AcquisitionJob` with source, canonical URL, request mode, status, progress, retry, cancellation, execution strategy, and resumability metadata.
- Explicit states: `PENDING`, `VALIDATING`, `DISCOVERING`, `DOWNLOADING`, `NORMALIZING`, `READY_FOR_IMPORT`, `COMPLETED`, `PARTIAL`, `FAILED`, `CANCELLED`, `DESKTOP_REQUIRED`.
- `SourceAdapter` semantics shared with Desktop concepts: URL handling, metadata, chapter listing, chapter fetch, health, allowed hosts, rate policy, and execution strategy.
- Execution strategies: `HTTP`, `PLAYWRIGHT`, `DESKTOP_ONLY`.
- Conservative rate policy defaults: one concurrent fetch, bounded retry count, bounded backoff.

Persistence decision: no new production table or migration in Cycle 3. The job model is durable-persistence-ready, but live server acquisition remains disabled until the self-hosted server and source policies are inspected.

Validated import boundary remains:

```text
Acquire -> Normalize -> Validate -> Hash -> Stage/Pack -> Preview Import -> Execute Import -> Canonical Records
```

Acquisition code must not directly mutate canonical novel/chapter rows.

## SSRF Model

| Threat | Mitigation | Test Result |
| --- | --- | --- |
| `localhost` / loopback | URL parsing plus DNS/IP rejection | PASS |
| RFC1918/private IPs | All resolved IPs inspected with `ipaddress` | PASS |
| IPv6 loopback/private/link-local | IPv6 parsed and rejected | PASS |
| Cloud metadata address | `169.254.169.254` explicitly rejected | PASS |
| Unsupported schemes | Only `https`, plus source-justified `http`, accepted | PASS |
| Userinfo tricks | Username/password rejected | PASS |
| Encoded or malformed hostnames | `%`, slash, and backslash hostname tokens rejected | PASS |
| Mixed-case/trailing-dot bypass | Hostnames normalized to lowercase IDNA without trailing dot | PASS |
| Deceptive suffix domains | Exact host allowlist unless controlled subdomains are enabled | PASS |
| DNS rebinding/mixed DNS | Any forbidden IP in the resolution set rejects the URL | PASS |
| Redirect to forbidden target | Every redirect destination revalidated | PASS |
| Oversized response | Response-size cap enforced | PASS |
| Login/block/error pages | Generic response markers rejected before adapter extraction | PASS |

Residual risk: DNS pinning across long-lived streaming downloads is not implemented yet. Cycle 3 avoids generic live URL fetching and keeps acquisition tied to source-specific host policies.

## Fixture Adapter

`FixtureNovelAdapter` validates the contract without internet access. It supports:

- fixture URL matching and normalization;
- metadata/list/chapter extraction;
- Unicode chapter titles;
- duplicate content detection with stable SHA-256 hashes;
- malformed or suspiciously short chapter rejection;
- redirect, size, content-type, login/block, and HTTP error validation through the shared client.

No live NovelFire, NovelPhoenix, 69Shuba, Qidian, Royal Road, ScribbleHub, or other external novel-source request was made.

## Desktop Configuration

Previous behavior: Desktop sync paths still treated a legacy Render URL as the implicit production default.

New behavior:

1. Explicit runtime setting.
2. `GT_WEBSITE_URL` environment variable.
3. `IAMGODTRANSLATOR_URL` environment variable.
4. Stored non-secret Desktop setting.
5. Safe local fallback: `http://127.0.0.1:8007`.

Remote hosts must use HTTPS. Local/dev hosts may use HTTP. Trailing slashes and uppercase/trailing-dot hosts normalize to a canonical base URL. Session tokens remain memory-only and are not persisted in connection profile files.

Render remains compatible but is no longer treated as the only or primary deployment target.

## Seeded Performance

Condition: `seeded local benchmark` using isolated SQLite at `%TEMP%\iagt-v11-6-cycle3-seeded.sqlite`.

Dataset:

| Seed Item | Count |
| --- | ---: |
| Novels | 60 |
| Total chapters | 1,908 |
| Largest novel | `seed-large-000` |
| Largest novel chapters | 1,200 |
| Chapter 1 English text | 2,031 chars |
| Production content used | No |
| Production database used | No |

API profile:

| Metric | Result | Interpretation |
| --- | ---: | --- |
| `/api/novels` | 23.76 ms mean, 64,659 bytes | Acceptable for 60 novels, but payload grows with full library list. |
| Novel details | 26.55 ms mean, 1,200 bytes | Healthy. |
| Chapter library page 1 | 26.50 ms mean, 10,614 bytes | Healthy server response for 50 rows. |
| Chapter library page near 950 | 28.51 ms mean, 10,734 bytes | Offset pagination remains stable locally. |
| Reader chapter 1 | 12.60 ms mean, 2,156 bytes | Healthy. |
| Reader chapter 2 | 7.77 ms mean, 2,156 bytes | Healthy. |
| Reader chapter 1200 | 6.99 ms mean, 2,216 bytes | Healthy. |

Browser profile:

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Home route | 29.17 ms, 175 DOM nodes | Initial view remains small after cache warm-up. |
| Library route | 274.05 ms, 1 API request, 1,065 DOM nodes | Main measured UI pressure is library DOM size at 60 novels. |
| Novel detail | 271.15 ms, 2 API requests, 159 DOM nodes | Healthy. |
| Chapter list | 276.03 ms, 1 API request, 349 DOM nodes | Renders 50 rows, but fetches a 5,000-row search index. |
| Reader chapter 1 | 276.25 ms, 2 API requests, 420 DOM nodes | Bounded, includes next-chapter prefetch. |
| Reader chapter 2 | 8.44 ms, 1 API request, 421 DOM nodes | Fast after route warm-up, prefetches next chapter. |
| Repeat Reader chapter 1 | 6.79 ms, 0 API requests, 421 DOM nodes | Cached repeat access works. |
| Chapter mounted rows | 50 | Current pagination prevents 1,200-row DOM explosion. |
| Chapter Next pagination | PASS | Page 2 navigation worked. |
| Console errors | 0 | Clean. |

## Bottlenecks

Measured bottlenecks and risks:

- Chapter list renders only 50 rows but still requests `limit=5000` to support client-side search.
- Library route renders all 60 novels in the seeded fixture and reached 1,065 DOM nodes.
- Reader one-chapter-ahead prefetch is already present and bounded; repeat chapter access avoided duplicate API requests.

No broad Reader refactor was performed in Cycle 3.

## Performance Fixes

No production behavior performance fix was applied in Cycle 3. The measured data supports a focused Cycle 4 optimization rather than speculative changes.

## Cycle 4 Recommendation

Exact next scope:

1. Replace the chapter-list `limit=5000` search-index fetch with server-side chapter search and 50-row paged results.
2. Keep current 50-row DOM pagination unless measurements show it fails on real devices.
3. Add measured before/after browser profiling for chapter-list search at 1,200+ chapters.
4. Review Library rendering once the expected real novel count is known; consider Library pagination or incremental rendering if the collection grows past low hundreds.
5. Preserve Reader prefetch behavior, but add a small regression test that repeat navigation does not duplicate chapter requests.
