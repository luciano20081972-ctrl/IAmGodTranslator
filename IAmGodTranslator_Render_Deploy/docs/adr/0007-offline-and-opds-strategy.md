# ADR 0007: Offline and OPDS Strategy

Status: PROPOSED

## Context

GodTranslator is currently an online web app. Mature readers often support offline reading, device catalogs, and sync. These features raise privacy and authorization risks because Original, AI, Reference, and user progress can be sensitive.

## Options

1. Implement custom offline caches and device feeds.
2. Use Workbox plus IndexedDB wrappers and follow OPDS 2.0 for catalogs.
3. Avoid offline and device support permanently.

## Decision

Use Workbox for future app-shell caching, Dexie or idb for explicit authorized chapter storage, and OPDS 2.0 concepts for future authenticated device catalogs.

## Rationale

Offline/device capability is valuable, but it must be standard-backed, explicit, role-aware, and reversible.

## Consequences

- No private chapter cache without explicit user action and logout cleanup.
- OPDS must be authenticated and must not leak Reference.
- Offline sync requires conflict handling and permission invalidation.

## Rollback

Unregister service worker, clear offline object stores, and disable OPDS routes.
