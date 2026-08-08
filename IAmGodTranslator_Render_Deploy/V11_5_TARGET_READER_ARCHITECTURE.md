# GodTranslator v11.5 Target Reader Architecture

This target is architectural direction, not a production rewrite. The production database should remain intact until a later branch proves that an adapter can preserve every existing workflow.

## Target Diagram

```text
                         GODTRANSLATOR

                         Library Layer
                              |
                         MiniSearch
                              |
                     Publication Adapter
                              |
              +---------------+----------------+
              |               |                |
          Original        AI Translation     Reference
              |               |                |
              +---------------+----------------+
                              |
                      Publication Model
                              |
                         Reader Engine
                              |
              +---------------+----------------+
              |               |                |
          Typography        Location       Annotation
          / Layout          Model          Model
              |               |                |
              +---------------+----------------+
                              |
                     Progress / Bookmarks
                              |
                         Offline Layer
                              |
                           FastAPI
                              |
                      Postgres/Supabase
```

## Publication Adapter

The adapter should expose existing GodTranslator data through Readium-style concepts without a destructive migration:

- `metadata`: novel title, author, slug, cover, source language, available editions.
- `readingOrder`: ordered chapter resources.
- `resources`: Original, AI English editions, Reference, cover, static assets.
- `toc`: chapter navigation and future arcs/volumes.
- `links`: self, next, previous, Library, authorized export/catalog links.

The adapter can be generated server-side from existing tables and API responses first. A database migration is only justified if repeated adapter computation becomes a measured performance problem.

## Resource Variants

GodTranslator has a model most ebook readers do not:

- Original Chinese
- AI Translation
- Reference Translation

These should be modeled as variants of a chapter resource, not as unrelated chapters. Reference must remain role-gated at the API and frontend layers.

## Reader Engine Direction

Phase 1 should keep the current escaped paragraph renderer and scroll Reader. Future Reader engine work should add capability behind adapters:

1. Readium-inspired typography variables.
2. Hybrid reading locators.
3. Web Annotation-compatible bookmark/highlight selectors.
4. Optional EPUB/pagination prototype using foliate-js or Readium concepts.
5. Offline app shell and authorized chapter storage after privacy review.

## Location Model

Target locator payload:

```json
{
  "href": "/novels/i-am-god/chapters/25/ai",
  "type": "text/html",
  "locations": {
    "chapter_number": 25,
    "paragraph_index": 34,
    "progression": 0.412,
    "position": 1234,
    "cfi": null
  },
  "text": {
    "before": "short context before",
    "highlight": "selected or visible text",
    "after": "short context after"
  }
}
```

The current chapter + scroll percentage remains the legacy fallback until migration is tested.

## Annotation Model

Future highlights, notes, and bookmarks should follow W3C Web Annotation concepts:

- body: note, tag, report, glossary link, translation QA issue.
- target: source variant plus selector.
- selectors: text quote, text position, paragraph id/index, future CFI when EPUB exists.
- privacy: Reference annotations inherit Reference authorization.

## Offline Layer

Offline must be deliberate:

- Workbox for app shell and static assets.
- Dexie or idb for authorized chapter data and sync queue.
- No Reference or private chapter cache without explicit user action and role-aware invalidation.
- Clear cache controls and logout cleanup.

## Security Boundary

The current Reader should remain escaped text. DOMPurify is a future boundary only for imported EPUB HTML or other untrusted markup. It is not a reason to make plain text into HTML.

## Acceptance For Future Architecture Work

- Existing Reader routes still work.
- Original/AI/Reference privacy remains unchanged.
- Progress and bookmarks survive font, viewport, and theme changes better than today.
- New generic reader capabilities are adapter-backed and reversible.
- Third-party resources are registered before production adoption.
