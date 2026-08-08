# GodTranslator v11.5 Build vs Borrow Matrix

The default rule is: keep GodTranslator-specific translation workflows custom, and borrow or follow standards for mature generic ebook-reader problems.

| Capability | Direction | Candidate | Rationale | Rollback/Fallback |
| --- | --- | --- | --- | --- |
| Library metadata search | ADOPT LIBRARY | MiniSearch | Already integrated in v11.4; local, small, no runtime network dependency, fallback exists. | Substring search fallback. |
| Chapter metadata search | ADOPT LIBRARY | MiniSearch | Same governance as Library search; bounded metadata set. | Existing 50-row pager plus substring filtering. |
| Publication metadata model | FOLLOW STANDARD | Readium Web Publication Manifest | `metadata`, `readingOrder`, `resources`, `toc`, and `links` map naturally to novels, chapters, and source variants. | Keep direct FastAPI novel/chapter responses. |
| Original/AI/Reference variants | KEEP CUSTOM | GodTranslator | This is the product differentiator and permission model. | None; must remain native. |
| Reader typography | ADAPT OPEN-SOURCE COMPONENT | Readium CSS | Strong ebook-specific CSS for typography, themes, CJK, RTL, vertical writing, and user settings. | Current Reader CSS variables. |
| Scroll reading | KEEP CUSTOM | Browser native + current Reader | Current scroll Reader is stable and mobile-reviewed. | Current implementation. |
| Paginated reading | BENCHMARK BEFORE ADOPTION | Foliate-js / Readium concepts | Generic pagination is hard; do not write from scratch without benchmark evidence. | Continue scroll Reader. |
| Reading positions | FOLLOW STANDARD | Readium Locator + EPUB CFI concepts | Current scroll percentage is fragile across layout changes. Hybrid locators are better. | Keep current chapter + percentage fields as legacy. |
| Bookmarks | REBUILD LATER | Readium Locator + Web Annotation selectors | Current bookmarks work but should become selector-backed before notes/highlights grow. | Current account/local bookmarks. |
| Highlights | REBUILD LATER | W3C Web Annotation | Selector-backed highlights avoid tying data to rendered DOM positions. | Current lightweight paragraph highlight behavior. |
| Notes/annotations | FOLLOW STANDARD | W3C Web Annotation | Mature JSON model with selector alternatives. | Keep annotation work out of production until designed. |
| EPUB import | BENCHMARK BEFORE ADOPTION | foliate-js / Readium parser patterns | Needs EPUB HTML sanitization, file handling, resource mapping, and privacy design. | Current text/pack import. |
| EPUB export | BUILD CUSTOM WITH VALIDATOR | EPUB 3.3 + EPUBCheck | Export must encode GodTranslator variants and metadata; validation should be borrowed. | Export disabled until conformance passes. |
| EPUB validation | ADOPT DEV TOOL | EPUBCheck | Official validation prevents false conformance claims. | Manual inspection only while EPUB is absent. |
| OPDS | FOLLOW STANDARD | OPDS 2.0 | Device catalogs should use a standard, authenticated feed. | No OPDS endpoint. |
| Offline app shell | ADOPT LIBRARY | Workbox | Mature service worker routing, precaching, and recipes. | Unregister service worker. |
| Offline chapter storage | ADOPT LIBRARY | Dexie or idb | IndexedDB wrappers prevent custom storage bugs. | Online-only reader. |
| HTML sanitization | ADOPT LIBRARY IF NEEDED | DOMPurify | Current text rendering is escaped. Sanitization is needed only at future untrusted HTML boundaries. | Disable untrusted HTML rendering. |
| Accessibility scanning | ADOPT DEV TOOL | axe-core | Finds serious/critical regressions repeatably, but does not replace manual review. | Manual keyboard/screen-reader checks. |
| Performance budgets | ADOPT DEV TOOL LATER | Lighthouse CI / Playwright metrics | Measure first, then set anti-regression thresholds. | Existing QA scripts. |
| Large chapter lists | BENCHMARK | TanStack Virtual | Only needed if 50-row pagination or server pagination becomes inadequate. | Current 50-row pagination. |
| Upload UX | DEFERRED | Uppy | Useful for future large imports but not Reader architecture. | Native upload controls. |
| TTS traversal | REBUILD LATER | Foliate-js concepts / Web Speech API | Needs source-aware paragraph traversal and permission boundaries. | No TTS. |
| Dictionary lookup | REBUILD LATER | KOReader/Kavita patterns + licensed dictionaries | Valuable for Chinese reading but licensing/data matter. | No dictionary. |
| Translation issue reporting | KEEP CUSTOM | GodTranslator | Must connect to source variants, profiles, and evaluator workflow. | Current report issue action. |
| Regenerate selected paragraph | KEEP CUSTOM | GodTranslator | Provider, budget, audit, and permission boundaries are product-specific. | Do not expose until v12 translation evaluator design. |
| Glossary popup | KEEP CUSTOM WITH STANDARDS | GodTranslator + selector model | Differentiated translation feature, but should use locators/selectors for stability. | Server glossary pages/tools. |

## Decisions To Stop Building Custom

- Publication manifests and resource ordering.
- Durable reading locators.
- Annotation selector vocabulary.
- EPUB validation.
- Generic offline asset caching.
- Generic IndexedDB wrapper.
- Sanitization of imported HTML.
- Automated accessibility scanning.

## Decisions To Keep Custom

- Original/AI/Reference resource selection and privacy.
- Translation jobs, profiles, budgeting, provider comparison, and retry semantics.
- Glossary/terminology, translation memory, evaluation, and provenance.
- Admin/Translator Workspace and recovery/backup systems.
- Source acquisition and content edition import rules.
