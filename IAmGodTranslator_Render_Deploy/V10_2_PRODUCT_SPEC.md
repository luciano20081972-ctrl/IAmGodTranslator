# GodTranslator v10 Product Spec

## Architecture

GodTranslator v10 keeps the database-first architecture. PostgreSQL in `godtranslator_v10` is the live source of truth for novels, chapters, translation jobs, translation quality reviews, translation history, glossary entries, import jobs, accounts, preferences, reading progress, bookmarks, favorites, and history.

Storage is not used as a live reader source. The app does not use v9 `chapter_index.json`, `counts.json`, hydration, path guessing, startup restore, or startup sync.

## Product Surfaces

- Library: premium dark novel grid, search, filters, progress, favorites, and Continue Reading.
- Novel Detail: cover hero, metadata, progress, quick actions, and recent chapters.
- Chapters: metadata-only chapter list with availability badges and authorized actions.
- Reader: AI, Reference, and Original modes, chapter navigation, bookmark, reader settings, Zen mode, and keyboard shortcuts.
- Translate: staged workspace for chapter selection, reusable profile selection, smart glossary, model/reference choices, budget safety, estimate, and launch.
- Job Center: translation jobs and admin import jobs.
- Quality: completed translation scoring, AI/Original/Reference comparison, review marks, warnings, profile/model/cost/timing metadata, and version restore.
- Compare: side-by-side Original and AI review, with Reference text restricted to Admin visibility.
- Admin: Overview, Quality, Monitor, Costs, Prompt Inspector, Profiles, Glossary, Database, Jobs, Imports, Missing Data, Backups, Diagnostics.
- Recovery: admin-only safe Reference diagnostic, request export, preview, and explicit import.

## Design System

The visual system uses a premium dark novel-library style: obsidian backgrounds, forest and teal accents, atmospheric cards, cover-forward layouts, rounded panels, and dense-but-readable operational tables. Light, forest, midnight, and warm dark themes are available through personalization.

## Navigation And Roles

Navigation is permission-aware:

- Guests: Library, Chapters, Reader
- Signed-in users: guest routes plus Account, History, Bookmarks, Favorites, and personalization
- Translators: Translate, Job Center, Compare
- Admins: all routes plus Novels, Recovery, Admin, backup/export, and diagnostics

Server-side authorization is enforced independently of hidden navigation.

## Accounts And Personalization

Supabase Auth powers optional email/password and Google OAuth accounts. When Auth is missing, public reading and local browser preferences continue to work.

Personalization includes application theme, accent, density, card size, motion, blur, reader font family, line height, paragraph spacing, reading width, reader tone, and text alignment.

Authenticated preferences are saved through `/api/account/preferences`; guest preferences remain in local browser storage.

## Reading Features

Authenticated users have database-backed:

- Continue Reading
- reading progress
- reading history
- bookmarks with notes
- favorites and Library favorite filtering

Progress writes are debounced in the frontend and scoped to the authenticated user on the server.

## Translation Workspace

The Translate workspace is staged:

1. Chapter Selection
2. Translation Profile
3. Model & Reference
4. Budget & Safety
5. Estimate
6. Launch Job

Chapter syntax supports single chapters, comma-separated lists, and ranges. The frontend previews parsed selection before estimate.

Translation Profiles are database-backed and reusable. Shared defaults are Natural English Novel, Faithful Translation, Reference Guided, Fast Draft, and Publication Quality. Translators/admins can duplicate profiles and create custom profiles with writing style, tense, quote style, glossary behavior, Reference preference, title behavior, paragraph preservation, and style guide settings.

Smart Glossary entries are novel-scoped with categories for Characters, Locations, Organizations, Abilities, Items, Titles, and Aliases. Entries include preferred translation, aliases, notes, locked status, usage count, and last-used metadata. Prompt construction includes only relevant entries that match the chapter Original text plus any ad hoc glossary notes.

The model registry is server-side via `/api/models`. Pricing is approximate when configured; unknown pricing is displayed as not configured.

## Jobs And Comparison

Translation jobs are persisted in PostgreSQL and support queued, running, paused, completed, failed, cancelled, and retry-failed flows. The Job Center summarizes jobs and valid actions.

Comparison mode shows Original, Reference, and AI panels side by side for translator/admin review. Missing panels show an unavailable state instead of crashing.

Translation Quality adds score/status review for completed chapters. Review marks are Excellent, Good, Needs Review, and Needs Retranslation. AI text is never automatically overwritten by review actions. Retranslation flows require explicit overwrite confirmation and preserve prior AI versions in translation history.

Admin Prompt Inspector previews prompt sections, estimated tokens, sizes, and approximate cost without calling OpenAI. It does not display API keys, auth headers, provider bodies, or secrets.

## Admin And Operations

Admin uses tabs for Overview, Database, Translation Jobs, Import Jobs, Missing Data, Backups, and Diagnostics. Technical JSON appears only behind details controls.

Missing Reference for I Am God is evaluated only within the configured 1-434 Reference target range.

## Backup And Recovery

Backup/export reads from PostgreSQL and excludes secrets. Recovery preserves v10.0.6 behavior behind admin authorization: diagnose missing Reference, download a recovery request, preview TXT/ZIP uploads, protect existing Reference text, and require explicit apply.

## Local Preview

`run_local_preview.ps1` starts a local Windows preview without creating `.env` or saving pasted secrets. It sets `DB_SCHEMA=godtranslator_v10` for the process and starts Uvicorn on `http://127.0.0.1:8001`.

## Previous-Version Inspiration

Older GodTranslator versions inspired the stronger dark novel-library feel, richer cover-forward cards, public/admin separation, reader mode separation, recovery workflows, and operational tools.

v10.1 supplied the stable restored architecture, chapter list, reader, translation jobs, recovery import, and backup export.

v10.2 adds the product layer: account foundation, personalization, Continue Reading, favorites, history, bookmarks, command palette, premium novel detail, Zen reader, staged Translate, Job Center, and tabbed Admin.

## Security

Admin, Recovery, and translator APIs authorize server-side. Browser navigation is not trusted for permission decisions.

Public config endpoints never return database URLs, service-role keys, Google secrets, admin passwords, OpenAI keys, access tokens, or refresh tokens.

## Translation Rule

Original Chinese remains the source of truth. Reference text is optional style guidance. A chapter with readable Original and missing Reference remains eligible for translation.

## Reference Range

I Am God uses Reference target range 1-434. Chapters above 434 are not counted as missing Reference. The expected accepted missing Reference chapter is 362.
