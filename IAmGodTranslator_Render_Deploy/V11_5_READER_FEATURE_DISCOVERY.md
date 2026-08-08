# GodTranslator v11.5 Reader Feature Discovery

The goal is not to copy every feature from mature readers. Each feature needs a GodTranslator use case.

| Feature | Source references | Classification | GodTranslator use case |
| --- | --- | --- | --- |
| Continuous reading | Kavita, Komga, BookLore | CORE BEFORE V12 | Move through translated chapters without returning to the chapter list. |
| Durable progress locators | Readium Locators, EPUB CFI | CORE BEFORE V12 | Restore position after font, theme, viewport, or pagination changes. |
| Highlights | Kavita, BookLore, Web Annotation | CORE BEFORE V12 | Mark translation issues, favorite passages, and glossary examples. |
| Notes | BookLore notebook, Web Annotation | USEFUL BEFORE V12 | Add translator or reader notes tied to stable selectors. |
| Reader profiles | Kavita | USEFUL BEFORE V12 | Separate mobile, desktop, night, and bilingual reading preferences. |
| Device-specific settings | Kavita, KOReader | USEFUL BEFORE V12 | Avoid one device's font/margin settings breaking another device. |
| Dictionary lookup | KOReader, Foliate | USEFUL BEFORE V12 | Chinese term lookup, glossary links, and translation-learning support. |
| TTS traversal | Foliate-js, browser APIs | POST-V12 | Needs paragraph/source traversal and voice availability design. |
| Text selection actions | Existing Reader, Kavita/Foliate concepts | CORE BEFORE V12 | Copy, bookmark, highlight, view Original, report translation issue. |
| Chapter preload | Current GodTranslator, reader products | USEFUL BEFORE V12 | Reduce wait between adjacent chapters. |
| Next-chapter preload | Current GodTranslator | USEFUL BEFORE V12 | Continue Reading feels immediate. |
| OPDS | Komga, Calibre-Web, BookLore, OPDS 2.0 | POST-V12 | Authorized external reader/device catalogs. |
| Kobo/KOReader interoperability | Komga, BookLore, KOReader | POST-V12 | Future device reading while preserving privacy and roles. |
| Collections/shelves | Komga, BookLore, Calibre-Web | USEFUL BEFORE V12 | Organize novels by status, source, translation quality, and favorites. |
| Favorites | Komga/Kavita/BookLore | USEFUL BEFORE V12 | Fast access to preferred novels and chapters. |
| Recently added | Digital-library products | USEFUL BEFORE V12 | Import and source acquisition workflows. |
| Recently read | Current GodTranslator + reader products | CORE BEFORE V12 | Continue Reading and cross-device reading. |
| Reading status | Kavita/BookLore | USEFUL BEFORE V12 | Not started, reading, caught up, completed. |
| Completed books | Library products | USEFUL BEFORE V12 | Separate finished translations/readers from active work. |
| Download for offline | PWA/Workbox/Dexie | CORE BEFORE V12 IF OFFLINE IS IN SCOPE | Allow authorized offline chapters with explicit privacy controls. |
| Theme scheduling | Reader apps | POST-V12 | Automatic night mode is useful but not core. |
| Font imports | Kavita | POST-V12 | User-uploaded fonts increase support burden and licensing review. |
| Chapter history | Current local recent state + reader products | USEFUL BEFORE V12 | Jump back after browsing chapters. |
| Jump-back location | Kindle/reader behavior | USEFUL BEFORE V12 | Return after following glossary/source/compare links. |
| Progress synchronization | Reader servers | CORE BEFORE V12 | Consistent account reading across devices. |
| Publication metadata editing | Calibre-Web/BookLore | USEFUL BEFORE V12 | Correct imported novel metadata and edition labels. |
| EPUB export | Calibre ecosystem, EPUB specs | CORE BEFORE V12 IF EXPORT IS IN SCOPE | Portable user-owned translations. |
| EPUB import | Readium/Foliate/Calibre/Kavita | CORE BEFORE V12 IF IMPORT IS IN SCOPE | Bring user-owned sources into GodTranslator. |
| Portable backups | GodTranslator recovery + library products | CORE BEFORE V12 | Preserve content and translation state. |
| Reading statistics | Reader products | POST-V12 | Useful but secondary to translation reliability. |
| Estimated time remaining | Reader products | USEFUL BEFORE V12 | Helps reading flow, but must not clutter Reader. |
| Paged reading | Readium/Foliate/epub.js | USEFUL BEFORE V12 | Optional mode for users who prefer book-like pages. |
| Vertical writing | Readium CSS, CSS writing-mode, Kavita | USEFUL BEFORE V12 | Chinese/Japanese typography support and future multilingual reading. |
| RTL support | Readium CSS | USEFUL BEFORE V12 | Future language expansion. |
| Book search | Foliate-js, BookLore, MiniSearch | USEFUL BEFORE V12 | Search inside a translated novel without server-heavy queries. |
| Translation provenance panel | GodTranslator-specific | CORE BEFORE V12 | Show model/profile/edition when appropriate without exposing admin internals. |

## Highest-Value Gaps Before v12

1. Stable locators for progress and bookmarks.
2. Highlight/note model tied to selectors.
3. Continuous reading across available translated chapters.
4. Offline app shell and explicit authorized chapter downloads.
5. EPUB import/export validation path.
6. Reader accessibility and performance budgets.
