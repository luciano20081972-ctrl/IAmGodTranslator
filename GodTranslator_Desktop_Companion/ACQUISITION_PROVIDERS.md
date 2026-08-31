# GodTranslator Desktop Acquisition Providers

This cycle adds an explicit acquisition-provider layer while keeping the existing downloader in charge of jobs, checkpoints, pause/resume/stop, retries, deduplication, pack creation, Update Novel, and sync.

## Providers

- `auto`: default policy. Prefer existing source-specific/direct acquisition before cloud providers.
- `direct_http`: local HTTP fetch for simple public pages.
- `browser`: existing local browser automation path.
- `firecrawl`: cloud/API acquisition backend for JavaScript-heavy or structured extraction.
- `apify`: cloud/API acquisition backend for approved Actor-based acquisition.

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

Cloud providers must not be used automatically when a free local path already succeeds unless the operator explicitly enables that policy.

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

## Deferred Providers

The following were reviewed as potentially useful but deferred until a specific capability gap is measured:

- WebScraping.AI
- Zenscrape
- Simplescraper
- Browse AI
- ScrapingAnt

Adding more cloud providers would increase maintenance, privacy, and quota-management surface without proving a distinct downloader need yet.
