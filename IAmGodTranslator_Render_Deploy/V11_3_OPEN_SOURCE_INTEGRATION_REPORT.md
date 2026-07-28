# GodTranslator v11.3 Open-Source Integration Report

Branch: `v11.3.0-code-cleanup-and-open-source-audit`
Goal: research only. No external source code or dependency was imported.

## 1. Executive Summary

The best near-term fit for GodTranslator is incremental adoption of small, focused libraries rather than a frontend framework rewrite. The current product is a FastAPI + plain JavaScript + HTML + CSS application with Supabase/Postgres-compatible storage and Render deployment. Recommendations therefore favor libraries that can be introduced behind existing routes and UI components.

Top five recommendations:

| Category | Project | Recommendation |
|---|---|---|
| Offline/PWA | [GoogleChrome/workbox](https://github.com/googlechrome/workbox) | Prototype |
| Reader rendering/performance | [TanStack/virtual](https://github.com/TanStack/virtual) | Prototype |
| Search | [lucaong/minisearch](https://github.com/lucaong/minisearch) | Adopt |
| Accessibility/UI primitives | [KittyGiraudel/a11y-dialog](https://github.com/KittyGiraudel/a11y-dialog) | Prototype |
| Background jobs/performance | [celery/celery](https://github.com/celery/celery) | Reference only first |

## 2. Current Architecture Constraints

- Frontend is plain JavaScript in `static/app.js`; no React/Vue/Next build pipeline exists.
- Reader state, recent reads, bookmarks, and settings rely on existing API/localStorage contracts.
- Translation jobs already have bounded scheduler behavior and persistent database items.
- Render deploys the FastAPI app; Desktop Companion is local software and not Render-deployed.
- Supabase auth and Postgres migration behavior must remain unchanged unless a future task explicitly scopes backend work.

## 3. Recommended Reusable Repositories

| Project | URL | License | Stars / activity | Language | Dependency footprint | Mobile/browser/accessibility support | Extractable? | Framework migration? | Security/maintenance notes | Benefit | Difficulty | Architecture risk | License risk | Recommendation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Workbox | https://github.com/googlechrome/workbox | MIT | About 12.9k stars; v7.4.1 released May 5, 2026; active Chrome/Aurora ownership noted | JS/TS | Medium if using full Workbox, low if using generated service-worker runtime modules | Strong browser/PWA focus; mobile offline support is the core use case | Yes, service worker strategy can be isolated | No | Must avoid caching authenticated/admin/API responses incorrectly | High | Medium | Medium | Low | Prototype |
| TanStack Virtual | https://github.com/TanStack/virtual | MIT | About 6.9k-7.0k stars; frequent 2026 releases | TS/JS | Medium; core is headless but package ecosystem is broad | Strong large-list rendering; accessible output remains the app's responsibility | Yes, especially `virtual-core` patterns | No if using core ideas; React package would require framework use | TanStack disclosed a 2026 npm incident affecting other packages; current packages were marked safe by maintainers | Medium | Medium | Medium | Low | Prototype |
| MiniSearch | https://github.com/lucaong/minisearch | MIT | About 5.9k stars; npm v7.2.0; high weekly downloads | TypeScript/JS | Low; zero external dependencies | Browser and Node; works offline when index fits memory | Yes | No | Keep indexes scoped to chapter metadata or authorized text only | High | Low | Low | Low | Adopt |
| a11y-dialog | https://github.com/KittyGiraudel/a11y-dialog | MIT | npm v8.1.5; 172k+ weekly downloads; lightweight | TypeScript/JS | Low; 1 dependency per npm metadata | Focus management, ARIA dialog pattern, keyboard behavior | Yes | No | Native `<dialog>` support is now strong, so compare before adopting | Medium | Low | Low | Low | Prototype |
| Celery | https://github.com/celery/celery | BSD-3-Clause/New BSD | About 29k stars; v5.6.3 released Mar 26, 2026 | Python | High; requires broker/backend planning | Backend only | Partly; patterns are reusable even without adopting | No frontend impact | Mature but heavier than current in-process scheduler; avoid unless job scale requires it | Medium | High | High | Low | Reference only |

## 4. Recommended Standalone Libraries

- **MiniSearch**: best direct fit for client-side Library/chapter metadata search. It supports browser usage, fuzzy/prefix matching, boosting, suggestions, and zero dependencies.
- **a11y-dialog**: useful for Reader menu, command palette, Admin modals, and recovery/restore dialogs if native `<dialog>` behavior is insufficient.
- **Workbox**: best option for a controlled PWA/offline prototype. Use deny-lists for admin, auth, recovery, translation jobs, and provider-related APIs.

## 5. Design-Reference-Only Repositories

| Project | URL | License | Reason |
|---|---|---|---|
| epub.js | https://github.com/futurepress/epub.js | FreeBSD/BSD-style license | Strong EPUB rendering concepts, but latest GitHub release shown as 2020 and many open issues. Use as a reference/prototype for EPUB import/export concepts, not as the core Reader replacement. |
| Pagefind | https://github.com/CloudCannon/pagefind | MIT | Excellent static-search architecture, but GodTranslator content is dynamic and permissioned. Useful for docs/static public catalog only. |
| Weblate | https://github.com/WeblateOrg/weblate | GPL-3.0 | Excellent translation workflow and glossary/translation-memory reference, but GPL and large Django architecture make direct integration inappropriate. |

## 6. Rejected Repositories and Reasons

| Project | License | Reason |
|---|---|---|
| Weblate | GPL-3.0 | Strong product reference, but direct code adoption would introduce copyleft obligations and a large architecture mismatch. |
| Translate Toolkit | GPL-2.0-or-later | Useful file-format reference, but GPL obligations and broad dependency surface make it unsuitable for direct import in this app. |
| RQ | BSD-2-Clause | Mature and simple, but default pickle serializer is explicitly unsafe unless configured carefully. Celery is better as a mature reference; current scheduler should remain custom until scaling pressure justifies broker work. |
| FlexSearch | Apache-2.0 | Very fast and feature-rich, but MiniSearch is simpler, zero-dependency, and better aligned with a first client-side search pass. Keep FlexSearch as a later large-index benchmark. |
| Clusterize.js | MIT | Plain JS and tiny, but lower maintenance and less suited than TanStack Virtual for future-proof virtualization patterns. |

## 7. License Analysis

- **Low risk**: MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0 with attribution/license preservation.
- **Medium risk**: FreeBSD/BSD-style projects with older maintenance; still permissive but needs exact license text review before adoption.
- **High risk**: GPL/AGPL projects. GPL can require derivative distribution under GPL terms; AGPL adds network-use source-sharing obligations. Do not import GPL/AGPL code into GodTranslator without explicit legal review.

## 8. Security and Maintenance Analysis

- Workbox is active and maintained under Chrome/Aurora ownership, but caching must avoid sensitive authenticated responses.
- MiniSearch is small and low dependency; the main concern is avoiding unauthorized text indexing.
- a11y-dialog is lightweight and has no known direct Snyk vulnerability in the latest version per package metadata reviewed.
- TanStack Virtual is active, but package provenance should be pinned and audited because TanStack disclosed a 2026 supply-chain incident affecting other TanStack packages.
- Celery is mature and active, but broker/result-backend configuration expands operational security scope.

## 9. Integration Difficulty

| Project | Difficulty | Why |
|---|---|---|
| MiniSearch | Low | Can index existing novel/chapter metadata in browser without backend changes. |
| a11y-dialog | Low | Can wrap existing menu/dialog markup incrementally. |
| Workbox | Medium | Requires service worker registration, cache strategy design, and auth/admin exclusions. |
| TanStack Virtual | Medium | Requires careful scroll-position and accessibility testing. |
| Celery | High | Requires Redis/broker, worker process deployment, monitoring, retry semantics, and migration from current scheduler behavior. |

## 10. Expected Benefit

- MiniSearch: faster Library/chapter search and offline-capable metadata search.
- Workbox: offline shell, cached chapters selected by the user, better mobile resilience.
- a11y-dialog: fewer bespoke focus-trap/menu bugs.
- TanStack Virtual: scalable chapter lists and future long-text rendering experiments.
- Celery: long-term reference for durable job infrastructure if in-process workers become insufficient.

## 11. Recommended Implementation Order

1. Add MiniSearch prototype for Library and chapter metadata search.
2. Add a small PWA manifest and Workbox service-worker prototype for app shell only.
3. Replace bespoke modal/menu focus handling with a11y-dialog or native `<dialog>` hardened by the a11y-dialog patterns.
4. Prototype TanStack Virtual for the chapter list only, not the Reader text, and verify restored scroll positions.
5. Revisit background jobs only after measuring current scheduler pressure; use Celery as the mature reference, not an immediate dependency.

## 12. Features That Should Remain Custom

- Translation scheduler claim/lease semantics.
- Provider request isolation and per-chapter translation item persistence.
- Reference privacy and authorization.
- Recovery and backup safety flows.
- Reader source selection and role-gated Reference display.

## 13. Features That Can Safely Use External Libraries

- Client-side metadata search.
- Accessible dialog/focus-management primitives.
- Service-worker asset caching and offline shell strategy.
- Virtualized chapter list rendering.
- EPUB/Web Publication import/export experiments behind a feature flag.

## 14. Proposed Entry 3 Implementation Plan

1. Write a small architecture note for MiniSearch and Workbox integration boundaries.
2. Add no-runtime-risk search prototype against existing `/api/novels` and `/library` metadata.
3. Add PWA app-shell caching only; explicitly bypass admin/auth/translation/recovery/API mutation routes.
4. Add accessibility regression tests for Reader menu, command palette, guest menu, Admin dialogs, and Settings switches.
5. Measure chapter-list rendering before and after virtualization before deciding whether TanStack Virtual is necessary.

## Final Best Options

| Need | Best option |
|---|---|
| Offline/PWA support | Workbox |
| Reader rendering or EPUB support | TanStack Virtual for rendering performance; epub.js only as EPUB design reference |
| Search | MiniSearch |
| Accessibility/UI primitives | a11y-dialog, with native `<dialog>` comparison |
| Background jobs/performance | Celery as reference; keep current custom scheduler until scaling data justifies migration |

## Sources Reviewed

- Workbox GitHub: https://github.com/googlechrome/workbox
- epub.js GitHub: https://github.com/futurepress/epub.js/
- FlexSearch GitHub: https://github.com/nextapps-de/flexsearch
- MiniSearch GitHub/npm: https://github.com/lucaong/minisearch, https://www.npmjs.com/package/minisearch
- a11y-dialog project/npm: https://kittygiraudel.com/projects/a11y-dialog/, https://www.npmjs.com/package/a11y-dialog
- TanStack Virtual GitHub/release data: https://github.com/TanStack/virtual, https://releasealert.dev/github/TanStack/virtual
- Celery GitHub/PyPI data: https://github.com/celery/celery, https://pepy.tech/projects/celery
- arq GitHub: https://github.com/python-arq/arq
- RQ GitHub/Snyk data: https://github.com/rq/rq, https://security.snyk.io/package/pip/rq
- Weblate release/security data: https://releasealert.dev/github/WeblateOrg/weblate, https://security.snyk.io/package/pip/weblate
- Translate Toolkit license/PyPI: https://docs.translatehouse.org/projects/translate-toolkit/en/latest/license.html, https://pypi.org/project/translate-toolkit/3.16.2/
- Readium Web Publication Manifest: https://readium.org/webpub-manifest/
