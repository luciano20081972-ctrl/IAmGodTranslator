# GodTranslator v10.5 Content Import and Editions Roadmap

v10.5 changes the product model from Recovery-first onboarding to Content-first onboarding.

## Completed In This Release

- Admin Content section.
- Content Import Center with preview and execute.
- New novel creation through import.
- Original, English, Reference, metadata, cover, and glossary import targets.
- Additive `chapter_editions` table.
- Existing AI translations mirrored as English editions with type `AI`.
- Reader tabs changed to English, Original, and protected Reference.
- Library and novel detail counts changed to Original, English, Reference, missing counts, and coverage.
- Recovery generalized to Original, Reference, and English missing-data repair.
- Import pack specification documented.
- Focused fixture QA for new novels, mixed imports, duplicate/overwrite/add-missing behavior, Recovery, Reader English, and migration.

## Follow-Up Phases

### Phase 1: Import UX Hardening

- Background import progress for very large packs.
- Richer per-file validation messages.
- Better pack upload execution from browser-selected ZIP files.

### Phase 2: Edition Management

- Per-chapter default selection controls.
- Bulk default edition rules by novel.
- Human edit workflow for English editions.

### Phase 3: Downloader Integration

- Desktop/downloader export buttons for Original, English, Reference, and Mixed packs.
- Source provenance and checksum history surfaced in Admin.

### Phase 4: Advanced Metadata

- Structured glossary import editor.
- Cover upload/storage integration.
- Metadata conflict review.

## Non-Goals

- No scheduler redesign.
- No authentication redesign.
- No PostgreSQL redesign.
- No production deployment in this branch.
