# GodTranslator V12 Product Completion Roadmap

V12 means the core workflows are production-ready. It does not mean the product stops evolving.

## Completion Definition

V12 should include:

- Stable Library and polished Reader.
- Original, AI, and Reference variants with role-aware privacy.
- Reliable translation jobs, profiles, retries, resume, cancellation, and budget controls.
- Search, bookmarks, progress, and mobile Reader.
- Glossary/terminology foundation and translation consistency tooling.
- Import/export path with EPUB validation if EPUB is included.
- Offline/PWA baseline if offline reading is included.
- Backup/recovery, authentication, roles, Admin, and Translator Workspace.
- Accessibility, security, performance, diagnostics, automated tests, and documentation baselines.

## Roadmap

| Stage | Deliverables | Dependencies | Resources reused | Custom code required | Estimate | Risks | Exit criteria |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v11.5 | Reader technology intelligence, registry, ADRs, lab benchmark, third-party policy | v11.4 MiniSearch | Readium, Foliate, OPDS, EPUBCheck, Web Annotation research | Docs, registry validator, synthetic lab | 1 sprint | Research may expose checksum/license blockers | Registry validates; architecture direction documented. |
| v11.6 | Reader typography and publication adapter foundation | v11.5 | Readium CSS, WebPub Manifest | Adapter endpoints/objects, CSS variable refinement | 1-2 sprints | Visual regression, over-abstraction | Existing Reader unchanged externally; adapter fixtures pass. |
| v11.7 | Reading locator foundation | v11.6 | Readium Locators, EPUB CFI concepts | Hybrid locator generation, progress migration preview | 1-2 sprints | Legacy progress drift, migration complexity | New locators coexist with current progress. |
| v11.8 | Offline/PWA shell | v11.7 preferred | Workbox, MDN PWA | Service worker, cache policy, logout cleanup | 1-2 sprints | Private content caching risk | App shell works offline; no private chapter cache without approval. |
| v11.9 | Offline chapter storage and sync | v11.8 | Dexie or idb | Authorized downloads, conflict handling, sync queue | 2-3 sprints | Privacy, storage pressure, stale permissions | Explicit offline chapters resume safely and clear on logout. |
| v11.10 | Annotations/highlights/Reader tools | v11.7 | Web Annotation model | Tables/API/UI for highlights, notes, bookmarks, issue targets | 2-3 sprints | Selector drift, mobile menu clutter | Notes/highlights survive resize and navigation. |
| v11.11 | EPUB import/export and validation | v11.6-v11.10 | EPUBCheck, Readium/Foliate prototypes | Export pipeline, import sanitizer, manifest mapping | 3-5 sprints | Malicious EPUB, invalid output, file size | EPUBCheck passes; untrusted HTML is sanitized or rejected. |
| v11.12 | Translation evaluation/memory/Reader integration | v11.10 | GodTranslator-native | Evaluator, memory, glossary popup, alignment tools | 3-5 sprints | Provider cost, alignment quality | Reader-linked evaluation and glossary workflows pass fixtures. |
| v11.13 | Source ingestion/job reliability/observability | v11.12 | Desktop Companion, import system | Improved import telemetry, retry diagnostics, admin dashboards | 2-4 sprints | Operational complexity | Failed jobs recover with clear diagnostics. |
| v11.14 | Accessibility/security/performance hardening | all previous | axe-core, Playwright, Lighthouse CI, DOMPurify if needed | CI budgets, security fixtures, docs | 2-4 sprints | Baseline failures need triage | Serious/critical accessibility and security gates pass. |
| v12.0-rc1 | Release candidate | v11.14 | All validated resources | Bug fixes only | 1-2 sprints | Late regression | RC QA complete with no release blockers. |
| v12.0 | Functionally complete release | rc1 | Existing deployment | Controlled release | 1 sprint | Production deploy risk | Main fast-forwarded after validated release gate. |

## Dependency Graph

```text
v11.5 intelligence
  -> v11.6 publication/typography
    -> v11.7 locators
      -> v11.10 annotations
      -> v11.8 offline shell
        -> v11.9 offline chapter storage
    -> v11.11 EPUB import/export
v11.10 + v11.11
  -> v11.12 translation Reader integration
v11.12
  -> v11.13 reliability/observability
all stages
  -> v11.14 hardening
  -> v12.0-rc1
  -> v12.0
```

## Estimates

- Aggressive: 10-14 weeks, assuming one focused implementer, minimal scope creep, and no major EPUB/offline blockers.
- Realistic: 18-24 weeks, allowing focused QA, accessibility/security remediation, and at least one release-candidate cycle.
- Conservative: 32-40 weeks, allowing deeper EPUB/offline work, translation memory/evaluation complexity, production hotfix interruptions, and device interoperability changes.

## v12 Non-Goals

- Replacing FastAPI/Postgres/Supabase.
- Migrating to a generic ebook-server stack.
- Copying GPL/AGPL implementations.
- Supporting every ebook format before EPUB is validated.
- Exposing provider internals to normal readers.
