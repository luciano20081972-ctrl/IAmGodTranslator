# GodTranslator v11.5 Reader Capability Matrix

Values: `STRONG`, `PARTIAL`, `MISSING`, `NOT APPLICABLE`, `UNKNOWN`.

`UNKNOWN` includes the reason in the cell.

| Capability | GodTranslator | Readium | Foliate-js | Komga | Kavita | BookLore | Calibre-Web | epub.js | Other best candidate discovered |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Library | STRONG | PARTIAL | NOT APPLICABLE | STRONG | STRONG | STRONG | STRONG | NOT APPLICABLE | Thorium: PARTIAL |
| Cover display | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | STRONG | STRONG | PARTIAL | BookLore: STRONG |
| Metadata | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | STRONG | STRONG | PARTIAL | OPDS 2.0: STRONG |
| TOC | PARTIAL | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | Readium WebPub Manifest: STRONG |
| Search | STRONG | PARTIAL | STRONG | STRONG | STRONG | STRONG | STRONG | PARTIAL | MiniSearch: STRONG |
| Chapter search | STRONG | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | MiniSearch: STRONG |
| In-book full-text search | PARTIAL | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | PARTIAL | PARTIAL | Foliate-js: STRONG |
| Progress | PARTIAL | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | Readium Locators: STRONG |
| Bookmarks | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | PARTIAL | Web Annotation: STRONG |
| Highlights | PARTIAL | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | PARTIAL | PARTIAL | Web Annotation: STRONG |
| Annotations | PARTIAL | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | PARTIAL | PARTIAL | W3C Web Annotation: STRONG |
| Reader themes | STRONG | STRONG | PARTIAL | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Fonts | PARTIAL | STRONG | PARTIAL | PARTIAL | STRONG | PARTIAL | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Font size | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | Readium CSS: STRONG |
| Line spacing | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Margins | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Max text width | STRONG | STRONG | STRONG | PARTIAL | STRONG | STRONG | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Dark theme | STRONG | STRONG | PARTIAL | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Sepia theme | STRONG | STRONG | PARTIAL | PARTIAL | STRONG | PARTIAL | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Scroll reading | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | Browser native: STRONG |
| Paginated reading | MISSING | STRONG | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | STRONG | Foliate-js: STRONG |
| Keyboard navigation | PARTIAL | STRONG | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | PARTIAL | Thorium: STRONG |
| Mobile navigation | STRONG | PARTIAL | PARTIAL | STRONG | STRONG | STRONG | PARTIAL | PARTIAL | Kavita: STRONG |
| Chapter preloading | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | UNKNOWN: not confirmed in docs | PARTIAL | PARTIAL | Current GodTranslator neighbor prefetch: PARTIAL |
| Reading-position persistence | PARTIAL | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | STRONG | Readium Locators: STRONG |
| CFI/location support | MISSING | STRONG | STRONG | NOT APPLICABLE | PARTIAL | PARTIAL | PARTIAL | STRONG | EPUB CFI: STRONG |
| CJK | PARTIAL | STRONG | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | CSS writing-mode/line-break: STRONG |
| RTL | PARTIAL | STRONG | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | Readium CSS: STRONG |
| Vertical writing | MISSING | STRONG | PARTIAL | UNKNOWN: product docs do not emphasize | STRONG | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | PARTIAL | CSS writing-mode: STRONG |
| Accessibility | PARTIAL | STRONG | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | UNKNOWN: needs current audit | axe-core plus manual review: STRONG |
| TTS | MISSING | PARTIAL | STRONG | UNKNOWN: not confirmed in docs | PARTIAL | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | Web Speech API: PARTIAL |
| Dictionary lookup | MISSING | PARTIAL | STRONG | UNKNOWN: not confirmed in docs | PARTIAL | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | KOReader: STRONG |
| Offline reading | MISSING | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | Workbox plus IndexedDB: STRONG |
| Explicit chapter downloads | PARTIAL | NOT APPLICABLE | NOT APPLICABLE | PARTIAL | PARTIAL | PARTIAL | PARTIAL | NOT APPLICABLE | Desktop Companion: STRONG |
| EPUB import | PARTIAL | STRONG | STRONG | PARTIAL | STRONG | STRONG | STRONG | STRONG | foliate-js: STRONG |
| EPUB export | MISSING | PARTIAL | MISSING | PARTIAL | PARTIAL | PARTIAL | STRONG | MISSING | EPUBCheck-backed custom export: STRONG |
| EPUB validation | MISSING | PARTIAL | MISSING | MISSING | MISSING | UNKNOWN: not confirmed in docs | MISSING | MISSING | EPUBCheck: STRONG |
| OPDS | MISSING | STRONG | PARTIAL | STRONG | PARTIAL | STRONG | STRONG | NOT APPLICABLE | OPDS 2.0: STRONG |
| Device synchronization | MISSING | PARTIAL | MISSING | STRONG | PARTIAL | STRONG | STRONG | MISSING | KOReader/Kobo sync concepts: STRONG |
| Continuous reading | PARTIAL | PARTIAL | PARTIAL | STRONG | STRONG | PARTIAL | PARTIAL | PARTIAL | Kavita: STRONG |
| Estimated reading time | PARTIAL | PARTIAL | UNKNOWN: not confirmed in docs | PARTIAL | STRONG | PARTIAL | UNKNOWN: not confirmed in docs | UNKNOWN: not confirmed in docs | Custom GodTranslator metrics: PARTIAL |

## Summary

- GodTranslator is strongest where reading intersects translation: Original, AI, Reference, paragraph actions, permissions, and source-aware navigation.
- Readium is the strongest architecture and standards source.
- Foliate-js is the strongest browser EPUB/pagination prototype candidate.
- Komga, Kavita, BookLore, Calibre-Web, Thorium, and KOReader are most valuable as product references.
- EPUBCheck is the clear validation tool for EPUB conformance.
- Web Annotation is the correct model to study before highlights and notes expand.
