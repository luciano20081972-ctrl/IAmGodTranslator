# ADR 0001: Reader Architecture Direction

Status: PROPOSED

## Context

GodTranslator has a custom Reader that supports Original, AI, and Reference variants, bookmarks, progress, settings, mobile navigation, and paragraph actions. Mature digital-reading projects and standards already solve many generic reader problems better than a bespoke implementation.

## Options

1. Continue building every Reader capability from scratch.
2. Replace the Reader with a full external reader stack.
3. Keep the GodTranslator Reader shell and introduce standards-backed adapters.

## Decision

Use option 3. Keep the GodTranslator Reader shell and add standards-backed adapters for publication metadata, locators, typography, annotations, offline storage, and EPUB support over time.

## Rationale

GodTranslator's differentiated value is translation-aware reading, not generic ebook infrastructure. Adapter-first architecture preserves existing product behavior and avoids database rewrites.

## Consequences

- Generic reader problems must be researched before custom implementation.
- New resources must be registered before adoption.
- Some work moves into isolated prototypes before production release.

## Rollback

Keep current direct FastAPI chapter APIs and frontend Reader rendering as the fallback until adapters are fully proven.
