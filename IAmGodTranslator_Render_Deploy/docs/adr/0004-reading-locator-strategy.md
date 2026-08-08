# ADR 0004: Reading Locator Strategy

Status: PROPOSED

## Context

Current progress restoration uses chapter state and scroll percentage. That is fragile when viewport, font size, line height, paragraph spacing, source variant, or future pagination changes.

## Options

1. Keep scroll percentage only.
2. Use paragraph index only.
3. Use a hybrid locator inspired by Readium Locators, EPUB CFI, and text quote context.

## Decision

Prototype hybrid locators with resource href, chapter number, paragraph index/id, progression, text quote context, and future CFI when EPUB resources exist.

## Rationale

Hybrid locators are more robust than one coordinate system and can bridge current plain-text chapters and future EPUB resources.

## Consequences

- Existing progress fields remain as legacy fallback.
- Bookmarks, highlights, notes, and translation issue reports can share one target model later.
- Migration must be additive and reversible.

## Rollback

Keep legacy chapter plus scroll percentage as the source of truth.
