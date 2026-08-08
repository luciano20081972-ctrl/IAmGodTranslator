# ADR 0002: Publication Model Direction

Status: PROPOSED

## Context

The current app exposes novels and chapters through GodTranslator-specific API responses. Readium Web Publication Manifest provides a mature model for publication metadata, reading order, resources, TOC, and links.

## Options

1. Leave novel/chapter responses unmodeled.
2. Add a destructive database migration to store Readium-style publications.
3. Build a publication adapter over existing data.

## Decision

Prototype a Readium-style publication adapter over existing data.

## Rationale

The adapter can map GodTranslator novels, chapters, and Original/AI/Reference variants into `metadata`, `readingOrder`, `resources`, `toc`, and `links` without production data changes.

## Consequences

- Existing APIs remain stable while the adapter is tested.
- Future EPUB/OPDS/offline work can target one publication abstraction.
- Adapter performance must be measured before any schema change.

## Rollback

Disable the adapter and continue using existing novel/chapter routes.
