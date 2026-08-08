# GodTranslator v11.5 Current Reader Architecture Audit

Branch: `v11.5.0-reader-platform-resource-intelligence`

Starting production main: `7b71ad5a32fab6dd40437507847039842c335342`

This audit describes the Reader as it exists before any v11.5 platform adoption. It is based on repository searches across `templates/index.html`, `static/app.js`, `static/styles.css`, backend routes, and database access code.

## Architecture Diagram

```text
Database
  |
  v
FastAPI
  |
  v
Novel/chapter API
  |
  v
Frontend state
  |
  v
Reader renderer
  |
  v
Progress/bookmarks/settings
```

## Code Evidence

| Area | Evidence |
| --- | --- |
| Application shell | `templates/index.html` loads the static app shell and vendored MiniSearch script. |
| Reader entry | `static/app.js` has `openReader`, `renderReader`, `renderReaderText`, `renderReaderMenuPanel`, `renderChapterDrawer`, `openReaderMenu`, and neighbor prefetch helpers. |
| Chapter list | `static/app.js` has `openChapters`, `loadChapters`, `renderChapters`, 50-row pagination, current-chapter detection, and MiniSearch-backed chapter metadata search. |
| Text safety | `renderReaderText` escapes paragraph text with `escapeHtml(clean)` before injecting paragraph markup. |
| Source variants | Reader state switches between `ai`, `original`, and `reference`; Reference is gated by account role/permission state. |
| Progress | Local keys include `gt-reader-scroll:{novel}:{chapter}:{source}` and `gt-chapter-state:{novel}`. Authenticated progress sync uses account progress routes. |
| Bookmarks | Guest bookmarks use `gt-local-bookmarks`; authenticated bookmarks use account bookmark API routes. |
| Preferences | `gt-preferences` stores reader/settings preferences; UI exposes text size, themes, reduced motion, high contrast focus, and comfort reading. |
| Focus Reading | Frontend toggles focus/zen state with data attributes and Reader re-rendering. |
| Paragraph tools | Contextual actions include copy paragraph, bookmark here, highlight, report translation issue, and authorized View Original. |
| Backend chapter API | `GET /api/novels/{novel_id}/chapters/{chapter_number}/{mode}` serves chapter text by mode. |
| Backend Reference boundary | `GET /api/novels/{novel_id}/compare/{chapter_number}` requires translator access; Reference metadata scrubbing uses `can_view_reference` and related helpers. |
| Persistence | Database methods include `library`, `chapter_text`, `save_reading_progress`, `reading_progress`, `bookmarks`, `save_bookmark`, and `delete_bookmark`. |
| MiniSearch | v11.4 vendored MiniSearch powers Library and chapter metadata search with substring fallback. |

## What Is Custom

- Browser Reader state, route handling, rendering, source switching, and scroll restoration.
- Reader menu, Focus Reading, contextual paragraph actions, and guest/authenticated bookmark split.
- Chapter-list pagination and current-chapter highlight.
- Original/AI/Reference source model and permission-sensitive Reference visibility.
- Local reading preference storage and remote reading progress sync.
- Product-specific translation actions and issue-reporting affordances.

## What Works Well

- The Reader keeps GodTranslator-specific source variants visible without exposing Reference to unauthorized users.
- Plain-text chapter rendering is conservative and escapes text before HTML insertion.
- Chapter pagination uses normal page scrolling after Entry 2.2 corrections.
- MiniSearch is isolated behind a fallback, preserving search if the vendored artifact fails.
- Guest reading and authenticated reading both work without requiring a migration.
- The mobile Reader now has restrained bottom navigation, simplified guest menu, focus mode, and safer settings presentation.

## Fragile Areas

- Progress is partly scroll-percentage based. It can drift when font size, viewport, line height, paragraph spacing, or rendering mode changes.
- Bookmarks and paragraph actions do not yet use a durable selector model such as Readium Locators, EPUB CFI, or Web Annotation selectors.
- Reader typography is custom CSS. It has improved visually, but long-term CJK, RTL, vertical writing, and paginated reading are generic ebook problems better informed by reader-specific standards.
- The Reader does not yet have a formal publication model with `metadata`, `readingOrder`, `resources`, `toc`, and `links`.
- Offline reading is not architected; localStorage is not enough for authorized offline chapter storage.
- Accessibility checks are mostly local/manual and should be raised into automated serious/critical baselines.
- Future EPUB import/export would require HTML sanitization, EPUB validation, and robust publication metadata.

## Duplicated Or Hard-To-Maintain Areas

- Chapter selection, Reader drawer selection, and current-position logic are related but implemented as frontend-specific view logic instead of through a publication/navigation model.
- Local and remote bookmarks/progress have separate paths that will become harder to evolve without a locator abstraction.
- Reader settings duplicate generic ebook-reader work: typography, spacing, theme, motion, contrast, and focus behavior.
- Import, content editions, and Reader variants map to publication resources conceptually, but there is no adapter naming that relationship.

## Missing Capabilities

- Stable cross-device and cross-layout locators.
- Full highlights and notes.
- EPUB import/export and EPUBCheck validation.
- OPDS catalog/device interoperability.
- Offline shell and offline chapter storage.
- Dictionary lookup and TTS traversal.
- Formal accessibility CI with axe-core or equivalent.
- Performance budgets for long chapters and large chapter lists.
- Publication manifests and resource integrity checks.

## Existing Implementations To Leave Untouched In v11.5

- Translation scheduler, worker concurrency, budget controls, provider logic, and retry behavior.
- Database schema and production data.
- Authentication, authorization, and Reference privacy logic.
- Admin, Translator Workspace, backup/recovery, and content import behavior.
- MiniSearch production integration, except for governance registry and checksum validation.
- Current Reader UI and CSS, except future release candidates may adapt typography after benchmarks.

## v11.5 Conclusion

The current Reader is a solid product-specific web reader, but its generic ebook-reader foundations should become adapter-driven. GodTranslator should keep custom work where it is differentiated: Original/AI/Reference variants, translation context, glossary, translation evaluation, budget/provider visibility, and recovery. Generic reader problems should be governed by standards and reader-specific projects before new custom code is written.
