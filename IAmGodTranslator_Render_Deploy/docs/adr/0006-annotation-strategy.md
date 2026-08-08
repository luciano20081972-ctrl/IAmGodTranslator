# ADR 0006: Annotation Strategy

Status: PROPOSED

## Context

GodTranslator has bookmarks and lightweight paragraph actions. Future highlights, notes, glossary examples, translation issues, and evaluation records need durable targets.

## Options

1. Store annotations as raw paragraph numbers.
2. Store annotations as rendered DOM offsets.
3. Use W3C Web Annotation concepts with robust selectors.

## Decision

Design future annotations around W3C Web Annotation concepts.

## Rationale

Web Annotation supports selector-based targets and can represent notes, highlights, bookmarks, and translation QA records without tying data to a transient DOM layout.

## Consequences

- Annotation tables should be additive and privacy-aware.
- Reference-targeted annotations must inherit Reference authorization.
- Migration of existing bookmarks should wait for locator validation.

## Rollback

Continue current bookmark-only behavior.
