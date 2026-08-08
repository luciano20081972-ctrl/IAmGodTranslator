# GodTranslator v11.5 Resource Intelligence Report

This report applies provider-style evaluation to digital-reader technologies. Selection is based on fit, architecture, license, maintenance, security, accessibility, performance, rollback, and measurable engineering value, not GitHub stars.

## Research Sources

- Readium: https://readium.org/
- Readium Web Publication Manifest: https://readium.org/webpub-manifest/
- Readium CSS: https://readium.org/css/
- Readium Architecture and Locators: https://readium.org/architecture/
- OPDS 2.0: https://specs.opds.io/opds-2.0
- W3C Web Annotation Data Model: https://www.w3.org/TR/annotation-model/
- EPUBCheck: https://github.com/w3c/epubcheck
- EPUB CFI ISO overview: https://www.iso.org/cms/live/live/en/sites/isoorg/contents/data/standard/06/35/63571.html
- Komga: https://github.com/gotson/komga and https://komga.org/es/docs/guides/opds/
- Kavita: https://wiki.kavitareader.com/guides/readers/epub/
- BookLore: https://github.com/booklore-app/booklore and https://booklore.org/docs
- Calibre-Web: https://github.com/janeczku/calibre-web
- epub.js: https://github.com/futurepress/epub.js/
- foliate-js: https://www.npmjs.com/package/foliate-js
- Thorium Reader: https://github.com/edrlab/thorium-reader
- KOReader: https://github.com/koreader/koreader
- Vivliostyle: https://docs.vivliostyle.org/en/
- MDN writing modes: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/writing-mode
- MDN line breaking: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/line-break
- Workbox: https://developer.chrome.com/docs/workbox/modules
- Dexie: https://dexie.org/docs/Dexie.js
- idb: https://github.com/jakearchibald/idb
- DOMPurify: https://github.com/cure53/DOMPurify/wiki
- axe-core: https://github.com/dequelabs/axe-core
- TanStack Virtual: https://tanstack.com/virtual/v3/docs/introduction
- Uppy: https://uppy.io/

## Scoring Model

| Weight | Criterion |
| --- | --- |
| 25 | Reader-specific fit |
| 15 | Architecture compatibility |
| 10 | Maintenance/activity |
| 10 | License suitability |
| 10 | Security |
| 10 | Accessibility |
| 5 | Mobile/browser compatibility |
| 5 | Performance |
| 5 | Integration effort |
| 5 | Replaceability/rollback |

## Candidate Scores

| Candidate | Score | Category | License posture | Rationale |
| --- | ---: | --- | --- | --- |
| Readium Web Publication Manifest | 90 | Publication architecture | LOW RISK | Directly matches metadata, readingOrder, resources, TOC, and OPDS concepts; ideal for adapter-first design. |
| EPUBCheck | 90 | EPUB validation | LOW RISK | Official validation tool; dev/CI adoption prevents invalid EPUB import/export claims. |
| W3C Web Annotation | 88 | Annotation model | LOW RISK | Strong selector vocabulary for highlights, notes, bookmarks, and translation QA targets. |
| Readium CSS | 86 | Typography/layout | LOW RISK | Ebook-specific CSS for typography, themes, CJK, RTL, vertical writing, and user settings. |
| Readium Locators / EPUB CFI | 86 | Reading position | LOW RISK | Better than scroll percentage for cross-layout restore; needs hybrid migration. |
| axe-core | 86 | Accessibility QA | LOW RISK | Good automated baseline for serious/critical issues; must be paired with manual review. |
| DOMPurify | 85 | HTML sanitization | LOW RISK WITH VERSION PIN | Correct tool for untrusted HTML boundaries; not needed for current escaped text. |
| OPDS 2.0 | 84 | Device/catalog integration | LOW RISK | Standard route to authorized external readers and devices; needs privacy design. |
| Workbox | 82 | Offline shell | LOW RISK | Mature PWA cache/routing tooling; chapter caching requires privacy review. |
| Dexie | 80 | Offline client DB | LOW RISK | Robust IndexedDB abstraction for future offline chapters and sync queues. |
| foliate-js | 78 | EPUB/pagination prototype | LOW RISK FOR PACKAGE | MIT package is promising for EPUB, CFI, pagination, search, annotations, and traversal; benchmark before adoption. |
| idb | 78 | Offline client DB | LOW RISK | Smaller IndexedDB wrapper than Dexie; good serious alternative. |
| Thorium Reader | 77 | Product/reference | LOW RISK REFERENCE | Active Readium-based reader; architecture not directly portable but useful for behavior. |
| Komga | 75 | Library/server reference | LOW RISK REFERENCE | MIT and mature; strong OPDS/library reference but backend stack is not a migration target. |
| TanStack Virtual | 74 | Large lists | LOW RISK | Useful if very large lists outgrow current pagination; benchmark before integration. |
| Kavita | 72 | Product/reference | REVIEW REQUIRED | Strong UX benchmark for reader settings, annotations, and mobile; source reuse constrained by license. |
| BookLore | 70 | Product/reference | REFERENCE ONLY | Strong multi-user library and notebook reference; AGPL source not reusable without explicit review. |
| KOReader | 69 | Device/reference | REFERENCE ONLY | Strong device/dictionary/OPDS reading concepts; AGPL source is reference-only. |
| Calibre-Web | 66 | Python ebook server reference | REFERENCE ONLY | Useful Python-web comparison; GPL source is not copied. |
| Vivliostyle | 62 | Paged media reference | REFERENCE ONLY | Excellent paged media ideas; AGPL core/viewer blocks direct adoption here. |
| epub.js | 58 | EPUB rendering alternative | REVIEW REQUIRED | Known browser EPUB project, but maintenance signals and unresolved issues make it less attractive than foliate-js/Readium for new work. |
| Uppy | 58 | Upload UX | LOW RISK DEFERRED | Useful for import workflows, not Reader architecture. |

## Seed Candidate Findings

### Readium

Readium is the best architecture reference. The Web Publication Manifest and architecture documents map cleanly to GodTranslator's existing data through an adapter. The strongest immediate value is conceptual: `metadata`, `readingOrder`, `resources`, `toc`, `links`, locators, and positions.

### Readium CSS

Recommendation: `ADAPT PARTS`. It should inform typography, spacing, user settings, CJK, RTL, and vertical writing, but it should not replace the GodTranslator product identity or navigation.

### foliate-js

Recommendation: `BENCHMARK`. The MIT package is the strongest browser EPUB/pagination prototype candidate discovered. Do not import the whole Foliate app because the app is GPL-licensed and not a direct fit.

### Komga

Komga is a strong MIT digital-library/server reference, especially for OPDS, account libraries, collection UX, progress, and device interoperability. It is not a backend migration target.

### Kavita

Kavita is a useful reader UX benchmark: font settings, line spacing, themes, reading modes, vertical writing, annotations, and continuous reading. Treat code reuse conservatively due license posture.

### BookLore

BookLore is a strong self-hosted multi-user library reference with shelves, metadata, full-text search, OPDS, reader notebook, highlights, notes, and progress. AGPL source means reference-only without explicit compatibility review.

### Calibre-Web

Calibre-Web is the most relevant Python ebook server comparison. Its permissions, OPDS, shelves, metadata, uploads, conversion, and administration patterns are useful to study, but GPL code should not be copied.

### epub.js

epub.js remains important to compare because it is a known browser EPUB renderer with CFI, pagination, and locations concepts. Current adoption should be deferred until a benchmark proves it beats foliate-js or a Readium-based path.

### EPUBCheck

EPUBCheck is the clear validation answer for future EPUB import/export. GodTranslator should not claim EPUB conformance without running it.

### OPDS

OPDS 2.0 is the right future catalog standard. GodTranslator can expose authorized libraries later, but public OPDS must not leak Reference or user-specific reading state.

### EPUB CFI / Readium Locators

The future progress model should be hybrid: chapter/resource href, paragraph index/id, progression, text quote context, and CFI when EPUB resources exist. Current scroll percentage should remain a fallback.

### Web Annotation

Use W3C Web Annotation to design highlights, notes, bookmarks, and translation issue targets. It solves a durable selector problem that custom ad hoc notes would otherwise recreate poorly.

## Better Projects Discovered Beyond The Seed List

- Thorium Reader: strong Readium Desktop reference.
- KOReader: strong e-ink/device, OPDS, dictionary, and sync concept reference.
- Vivliostyle: strong CSS paged-media and publication workflow reference.
- Bibi/bi-epub-reader: lightweight browser EPUB reference, but smaller/staler than preferred options.

## Supporting Resource Findings

- Workbox is the best app-shell/offline routing candidate.
- Dexie and idb are the credible IndexedDB choices.
- DOMPurify should be reserved for untrusted HTML; current escaped text should stay escaped.
- axe-core should be added as an automated baseline in a later QA branch.
- Lighthouse CI is useful after measuring baseline budgets.
- TanStack Virtual is a benchmark candidate only if current pagination becomes insufficient.
- Uppy is a future import UX candidate, not Reader architecture.

## License Categories

### LOW RISK

MiniSearch, Readium CSS, Readium specifications, EPUBCheck, Komga, Thorium Reader, foliate-js package, OPDS 2.0, W3C Web Annotation, Workbox, Dexie, idb, DOMPurify, axe-core, TanStack Virtual, Uppy.

### REVIEW REQUIRED

Kavita, epub.js production adoption, any package with transitive dependencies not yet pinned and audited.

### REFERENCE ONLY

BookLore, Calibre-Web, KOReader, Vivliostyle, full Foliate application, any repository with no license or strong copyleft code not explicitly approved.

## Security Findings

- Current Reader text rendering is safe text if kept as escaped plain text.
- Future EPUB/imported HTML is untrusted HTML and requires sanitization, CSP review, resource loading controls, and fixture tests.
- Novel descriptions and user-provided metadata must be classified before allowing rich HTML.
- Glossary/user notes become user-provided content and need escaping or sanitization depending on render mode.

## Free Resource Findings

- W3C, Readium, OPDS, MDN, Unicode/CSS specifications, EPUBCheck, axe-core, Playwright, public EPUB fixtures, browser APIs, and GitHub Actions provide substantial free tooling.
- No paid service or credential is required for v11.5.

## v11.5 Adoption Decision

Production dependencies added: none.

Dev/QA dependencies added: none.

Production improvements implemented: none beyond governance and isolated tooling.

Low-risk dev tooling added:

- `config/resource_registry.json`
- `tools/validate_resource_registry.py`
- `tools/reader_lab/reader_lab_benchmark.py`
- `tools/qa_v11_5_reader_platform.py`
