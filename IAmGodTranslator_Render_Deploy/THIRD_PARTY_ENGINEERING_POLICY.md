# Third-Party Engineering Policy

This policy applies to libraries, standards, repositories, browser APIs, hosted services, tooling, fixtures, and vendored artifacts used by GodTranslator.

1. Search before building any major generic capability.
2. Prefer reading-specific technology for reader-specific problems.
3. Verify licenses before source-code reuse.
4. Preserve attribution and required notices.
5. Pin production dependencies.
6. Record provenance for every adopted dependency.
7. Verify vendored checksums.
8. Avoid hidden runtime CDN dependencies.
9. Avoid framework migration unless justified by measured benefit.
10. Prefer adapters over destructive rewrites.
11. Require fallbacks where reasonable.
12. Benchmark before replacing working systems.
13. Do not copy GPL/AGPL code without explicit compatibility review.
14. Do not adopt abandoned software solely because it was once popular.
15. Every third-party dependency requires rollback documentation.
16. External network services require privacy review.
17. Private chapter, user, Original, Reference, translation, provider, and production data must not leave existing trust boundaries without explicit approval.
18. Third-party resource decisions belong in `config/resource_registry.json`.

## Required Registry Fields

Each resource entry must record:

- capability/category
- source and version/revision
- license
- status
- intended usage
- runtime or development scope
- vendored path and checksum when applicable
- network dependency
- user-data sharing behavior
- fallback
- rollback
- last-reviewed date
- notes

## Status Definitions

- `ADOPTED`: production or committed dev dependency is actively used.
- `PROTOTYPE`: isolated implementation may be exercised, not production behavior.
- `BENCHMARK`: evaluated in tests/labs only.
- `REFERENCE`: behavior, architecture, or standards are studied; source is not copied.
- `REJECTED`: reviewed and explicitly declined.
- `DEFERRED`: plausible future candidate, no current adoption.

## Review Gates

Before an adopted dependency ships:

1. Registry entry validates.
2. License/notice requirements are documented.
3. Checksums validate for vendored assets.
4. Fallback and rollback are documented.
5. Tests cover normal operation and dependency failure where practical.
6. Privacy review confirms what data, if any, leaves the app.
7. Security review covers known advisories and unsafe input boundaries.
