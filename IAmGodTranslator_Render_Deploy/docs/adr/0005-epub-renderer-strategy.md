# ADR 0005: EPUB Renderer Strategy

Status: PROPOSED

## Context

GodTranslator does not need immediate EPUB rendering in production, but v12 may require EPUB import/export and validated portable translations. Candidates include Readium concepts, foliate-js, epub.js, and custom rendering.

## Options

1. Build EPUB parsing/rendering from scratch.
2. Adopt epub.js immediately.
3. Benchmark foliate-js and Readium-style architecture in isolation first.
4. Delay EPUB entirely.

## Decision

Benchmark foliate-js and Readium-style architecture in isolation before production adoption.

## Rationale

foliate-js appears stronger for modern browser EPUB capabilities than adopting epub.js by default, but no production choice should be made without benchmark evidence, license review, rollback, and fixtures.

## Consequences

- v11.5 does not import an EPUB renderer.
- Future EPUB work needs EPUBCheck validation and sanitization.
- Current plain-text Reader remains production behavior.

## Rollback

Remove EPUB lab/prototype files and keep text/pack import.
