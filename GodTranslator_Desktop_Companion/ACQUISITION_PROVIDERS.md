# GodTranslator Desktop Acquisition Providers

This cycle adds an explicit acquisition-provider layer while keeping the existing downloader in charge of jobs, checkpoints, pause/resume/stop, retries, deduplication, pack creation, Update Novel, and sync.

## Providers

- `auto`: default policy. Prefer existing source-specific/direct acquisition before cloud providers.
- `direct_http`: local HTTP fetch for simple public pages.
- `browser`: existing local browser automation path, exposed through source adapter browser mode.
- `firecrawl`: cloud/API acquisition backend for JavaScript-heavy or structured extraction.
- `apify`: cloud/API acquisition backend for approved Actor-based acquisition.

## Capability Model

Providers advertise explicit capabilities instead of pretending every backend can do everything:

- single-page fetch
- discovery and chapter discovery
- JavaScript rendering
- bounded crawl
- structured output
- Markdown and HTML output
- cancellation
- async jobs
- external credit use
- local browser use
- retry/progress support
- domain and path scoping

## Secrets

Configure secrets outside the repository and outside frontend JavaScript:

- `FIRECRAWL_API_KEY`
- `FIRECRAWL_BASE_URL` optional, for compatible hosted/self-hosted endpoints
- `APIFY_API_TOKEN`
- `APIFY_CHAPTER_ACTOR_ID`
- `APIFY_ALLOWED_ACTORS`, comma-separated allowlist

Do not place provider tokens in screenshots, logs, packs, exported jobs, or browser-visible code.

## Auto Policy

Auto should remain deterministic and cost-aware:

1. source-specific adapter when reliable;
2. direct HTTP extraction;
3. local browser automation;
4. Firecrawl when JavaScript rendering or structured extraction is needed;
5. Apify when an approved Actor is the best fit.

Cloud providers must not be used automatically when a free local path already succeeds unless the operator explicitly enables that policy. The default Desktop policy is:

- `allow_cloud_providers=false`
- `allow_firecrawl_auto=false`
- `allow_apify_auto=false`
- `prefer_free_local=true`
- `cloud_fallback_only=true`

Explicitly choosing Firecrawl or Apify is treated as an operator action and still requires valid server/Desktop-side credentials.

## Firecrawl

Use Firecrawl Scrape for known chapter URLs. This is cheaper and more direct than launching a full Crawl for one chapter.

Use Firecrawl Map for chapter-list discovery when a source index page is hard to parse locally. Link results are filtered through allowed-domain and allowed-path scopes before becoming chapter candidates.

Use Firecrawl Crawl only when it materially improves acquisition and only with explicit limits:

- allowed domain
- allowed path prefix
- maximum pages/chapters
- timeout
- cancellation
- no unrestricted whole-domain crawl

Structured extraction may request fields such as `novel_title`, `chapter_title`, `chapter_number`, `chapter_body`, `next_chapter_url`, and `previous_chapter_url`, but deterministic parsing remains preferred when it is reliable.

## Apify

Apify runs only configured, allowlisted Actors. Normal UI input never controls arbitrary Actor IDs.

Actor output is normalized into the same chapter model as direct, browser, and Firecrawl acquisition. Dataset rows must contain usable text/HTML and cannot bypass deduplication or pack validation.

## Failure Classes

Provider failures are normalized as:

- `configuration_missing`
- `authentication_failed`
- `quota_exhausted`
- `rate_limited`
- `timeout`
- `network`
- `blocked/restricted`
- `parse_failed`
- `empty_content`
- `provider_internal`
- `canceled`
- `unsupported_source`

Only retry retryable failures. Do not rotate endlessly across providers for permanent failures.

## Security Restrictions

The provider layer must not implement features intended to defeat authentication, CAPTCHAs, paywalls, access controls, private content restrictions, or explicit authorization boundaries. Normal public-page fetching, JavaScript rendering, structured extraction, timeouts, retries, cancellation, and bounded crawling are allowed.

Provider source URLs are checked before cloud acquisition. Localhost, loopback, link-local, RFC1918 private networks, and metadata endpoints are rejected unless a future explicit operator policy allows a specific local development target.

## Retry And Fallback

Retryable classes include network failures, timeouts, rate limits, provider internal failures, crawl failures, and temporary Actor failures.

Permanent failures include missing configuration, bad credentials, explicit restrictions, unsupported sources, empty content, malformed provider responses, cancellation, and job removal.

Fallback must be purposeful:

- Direct parse failure can justify Browser.
- Browser rendering failure can justify Firecrawl if cloud fallback is enabled.
- Firecrawl quota or auth failure must not trigger repeated Firecrawl attempts.
- Apify is attempted only when configured, allowlisted, and policy-permitted.

## Observability

Jobs persist safe provider attempt traces:

- provider
- reason selected
- status
- failure category
- retryability
- timestamp

Never persist API keys, authorization headers, cookies, or full provider request bodies.

## Live Smoke Tests

Normal tests use fixtures and do not consume provider credits. Optional live tests require explicit environment flags:

- `IAGT_LIVE_FIRECRAWL_TEST=1`
- `IAGT_LIVE_APIFY_TEST=1`

Missing live credentials is an operator checkpoint, not a unit-test failure.

## Deferred Providers

The following were reviewed as potentially useful but deferred until a specific capability gap is measured:

- WebScraping.AI
- Zenscrape
- Simplescraper
- Browse AI
- ScrapingAnt

Adding more cloud providers would increase maintenance, privacy, and quota-management surface without proving a distinct downloader need yet.

## Resource Matrix

| Resource | Status | Reason |
| --- | --- | --- |
| Direct HTTP | ADOPTED | Lowest-cost public-page fetch path. |
| Browser automation | ADOPTED | Existing JavaScript-capable local acquisition path. |
| Firecrawl | ADOPTED | Required JS/Markdown/structured acquisition backend with scrape/map/crawl capability. |
| Apify | ADOPTED | Approved Actor/dataset backend for sources where an allowlisted Actor is a better fit. |
| WebScraping.AI | DEFERRED | Overlaps with Firecrawl/Apify; no distinct gap proven. |
| ScrapingAnt | DEFERRED | Similar cloud scraping surface; no current need. |
| Zenscrape | DEFERRED | HTTP scraping service without enough distinct chapter workflow value yet. |
| Browse AI | DEFERRED | Browser automation SaaS overlap; credential/maintenance burden. |
| Simplescraper | DEFERRED | Extraction workflow overlap; no immediate advantage. |
| Playwright | ADOPTED | Existing local visual/regression QA and browser automation. |
| TasteSkill | USED AS DESIGN/ARCHITECTURE REFERENCE | Design-audit reference only. |
| Vercel Web Interface Guidelines | USED AS DESIGN/ARCHITECTURE REFERENCE | Framework-agnostic accessibility and UI-quality reference. |
| Context7 | USED AS DEVELOPMENT TOOL | Useful for current docs when available; not project source of truth. |
| SkillUI | DEFERRED | Ambiguous provenance; do not install without exact repository verification. |
| Aceternity UI | USED AS DESIGN/ARCHITECTURE REFERENCE | Interaction inspiration only; no React/Tailwind migration. |
| Strix | DEFERRED | Approved for controlled candidate security gate after an isolated candidate exists. |
| Semgrep | DEFERRED | Useful, but not added before selecting a low-noise local ruleset. |
| Local secret scan | ADOPTED | Offline, privacy-preserving release check. |
| Dependabot/dependency auditing | DEFERRED | Useful monitoring; no auto-merge policy. |
| CodSpeed/Bencher | DEFERRED | Local performance path remains required first. |
| GlitchTip/Sentry | DEFERRED | Privacy review needed before external telemetry. |
| MuMuAINovel | USED AS DESIGN/ARCHITECTURE REFERENCE | Workflow inspiration only. |
| RedInk | USED AS DESIGN/ARCHITECTURE REFERENCE | Batch retry/state inspiration only. |
| OpenHands | REJECTED | Development-agent overlap, not product capability. |
| Manus | REJECTED | Development-agent overlap, not product capability. |
| Spline | REJECTED | Decorative 3D cost without downloader value. |
| Remotion | REJECTED | Video tooling outside this cycle. |
| autoclip_mvp | REJECTED | Video tooling outside this cycle. |
| PersonaLive | REJECTED | Heavy model/GPU concept outside this cycle. |
| Better Auth | REJECTED | Auth migration explicitly out of scope. |
| Next.js | REJECTED | Framework migration explicitly out of scope. |
| Algolia | REJECTED | Hosted search not justified for private novel index. |
| CommandBar | REJECTED | Hosted/third-party command search not justified. |
