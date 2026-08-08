# ADR 0003: Typography Engine Direction

Status: PROPOSED

## Context

Reader typography has been polished through v11.2, but CJK, RTL, vertical writing, paginated reading, font settings, margins, line height, and themes are mature ebook-reader concerns.

## Options

1. Keep all typography custom.
2. Replace the GodTranslator visual identity with Readium CSS wholesale.
3. Adapt Readium CSS concepts and variables inside GodTranslator's Reader design.

## Decision

Adapt Readium CSS concepts and variables; do not replace the product identity.

## Rationale

Readium CSS is reader-specific and BSD-licensed. It can improve typography foundations while GodTranslator retains its navigation, source switching, and translation context.

## Consequences

- Future typography changes should cite benchmark evidence.
- CJK/RTL/vertical writing work should align with CSS standards and Readium CSS guidance.
- Visual regressions require Playwright screenshots before production adoption.

## Rollback

Revert to the current `static/styles.css` Reader variables and spacing.
