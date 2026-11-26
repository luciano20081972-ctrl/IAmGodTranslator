# ADR 0004: Reading Locator Strategy

Status: Accepted for the V12-R1 plain-text Reader

## Context

Current progress restoration uses chapter state and scroll percentage. That is fragile when viewport, font size, line height, paragraph spacing, source variant, or future pagination changes.

## Options

1. Keep scroll percentage only.
2. Use paragraph index only.
3. Use a hybrid locator inspired by Readium Locators, EPUB CFI, and text quote context.

## Decision

The Reader stores a version 1 locator for the displayed novel, chapter and source variant. It records the chapter content hash, the zero-based rendered paragraph index, the fractional offset within that paragraph and overall progression. This keeps chapter text out of progress storage. The chapter and source identify the resource in the current Reader.

After a layout change, the Reader aligns the saved point in the paragraph with the reading line. On a different chapter revision, an unavailable paragraph or an unsupported locator, it restores the existing scroll percentage. This makes reflow within a paragraph approximate and keeps position recovery possible after an edit.

Guest positions stay on the device. Signed-in readers keep a separate device copy and sync through their existing account progress row. The Reader checks for newer account progress when opening a novel and when returning to a visible tab. Ordinary scroll events use the existing batched writes. Legacy device percentages and account records are readable before any new anchor is saved.

## Rationale

Hybrid locators are more robust than one coordinate system and can bridge current plain-text chapters and future EPUB resources.

## Consequences

- Existing progress fields remain as legacy fallback.
- Bookmarks, highlights, notes, and translation issue reports can share one target model later.
- Migration must be additive and reversible.

## Rollback

SQLite and PostgreSQL add a nullable `locator_json` column during initialization. The migration leaves existing rows intact. The prior application can run with the column in place and continue using the legacy fields. An old writer that changes the chapter, source or percentage invalidates the associated anchor. To remove the column, first switch to the prior application and drop only `locator_json` from the configured `reading_progress` table. This discards paragraph anchors and retains legacy progress. The `locator-storage` and `postgres-auth` checks rehearse this sequence with synthetic rows.
