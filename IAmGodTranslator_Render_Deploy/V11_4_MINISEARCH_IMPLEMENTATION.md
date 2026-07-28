# GodTranslator v11.4 MiniSearch Implementation

Branch: `v11.4.0-minisearch-library-and-chapters`

Base main: `c5c3bc290e67207820b5c9f9577ff329e98cda0f`

## Scope

GodTranslator v11.4 adds MiniSearch-powered metadata search to the existing Library and chapter-list interfaces. The integration is deliberately frontend-only: no backend architecture, database schema, authentication, Supabase configuration, translation scheduling, or production data behavior changed.

## Library

Library search now builds a MiniSearch index from already-loaded novel metadata. Existing Library filters still apply first, then search ranking is applied to the filtered set. Existing sort options remain available; when a query is active, MiniSearch score is primary and the selected sort provides deterministic tie-breaking.

Indexed Library fields:

- `id`
- `title`
- `alternate`
- `author`
- `description`
- `status`
- `language`
- `tags`
- `counts`
- `source`

The Library UI now includes an accessible search label, a clear search button, and live result-count status text.

## Chapter List

The chapter list now loads the current novel/view chapter metadata up to the existing API limit of 5,000 rows, builds a local MiniSearch index, ranks the matching metadata client-side, and paginates the ranked results through the existing 50-row pager.

Indexed chapter fields:

- `number`
- `title`
- `displayLabel`
- `status`
- `flags`

The chapter index excludes chapter body text and Reference text. It only uses metadata already returned by the existing authorized chapter-list endpoint.

## Privacy Boundary

The search adapter does not index:

- full Original chapter text
- full English chapter text
- full AI chapter text
- Reference text
- prompts
- provider request or response bodies
- API keys
- passwords
- database URLs
- cookies
- tokens
- admin-only backup content

Reference availability is used only as a visible metadata flag when the existing endpoint already exposes that flag to the current role. Non-authorized users continue to receive scrubbed metadata from the backend.

## Fallback Behavior

If the MiniSearch browser artifact does not load, search falls back to local substring matching over the same allow-listed metadata fields. A single diagnostic warning is emitted only when local debug search mode is enabled with `gt-debug-search=1` or `gt-debug=1`.

## Vendoring

No npm workflow exists in the tracked production deploy tree, so MiniSearch was vendored as a local static browser artifact.

Vendored files:

- `static/vendor/minisearch/minisearch-7.2.0.min.js`
- `static/vendor/minisearch/LICENSE`

Sources verified:

- npm tarball: https://registry.npmjs.org/minisearch/-/minisearch-7.2.0.tgz
- version-pinned browser artifact: https://cdn.jsdelivr.net/npm/minisearch@7.2.0/dist/umd/index.min.js
- project repository: https://github.com/lucaong/minisearch

Checksums:

- npm tarball SHA256: `cb3b8126a3ea65d6b387787294f0792b0ea4a40b70f8f37688066a5638e0218a`
- vendored browser artifact SHA256: `8a05b42785db448f2c19e24a6a2107204c825565fe4f95aa69b79652baf26e82`
- vendored license SHA256: `70d37354d6395629fb99edb28cb37a5d356ffa24a48cd02a5def5b83a300a899`

Verification method:

1. Downloaded the official `minisearch@7.2.0` npm tarball from the npm registry.
2. Confirmed the tarball contains `package/dist/umd/index.js` and `package/LICENSE.txt`.
3. Downloaded the version-pinned jsDelivr minified UMD artifact generated from `minisearch@7.2.0/dist/umd/index.js`.
4. Confirmed the UMD wrapper exposes `MiniSearch` on `globalThis`.
5. Copied the minified browser artifact and MIT license into `static/vendor/minisearch/`.
6. Recorded SHA256 checksums for the npm tarball, vendored browser artifact, and vendored license.

## Performance Notes

Indexes are rebuilt only when the underlying loaded metadata signature changes. Typing in a search field reuses the existing index and updates only ranking/filtering results. This keeps Library and chapter search responsive while preserving the existing page routing and pagination model.

Expected index sizes:

- Library: one document per authorized loaded novel.
- Chapter list: one document per loaded chapter metadata row for the selected novel/view, up to the existing endpoint limit of 5,000.

## QA

Focused v11.4 QA script:

- `python IAmGodTranslator_Render_Deploy/tools/qa_v11_4_minisearch.py`

Required release checks:

- `git diff --check`
- `node --check IAmGodTranslator_Render_Deploy/static/app.js`
- `python -m py_compile IAmGodTranslator_Render_Deploy/app/main.py`
- `python -m py_compile IAmGodTranslator_Render_Deploy/tools/qa_v11_4_minisearch.py`

## Verdict

MiniSearch integration is complete for Library and chapter-list metadata search. No OpenAI calls, production data writes, database migrations, API changes, or translation scheduler changes are part of this implementation.
