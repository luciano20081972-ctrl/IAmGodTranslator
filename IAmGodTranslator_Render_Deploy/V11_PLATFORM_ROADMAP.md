# GodTranslator v11 Platform Roadmap

GodTranslator v11 is the long-term platform evolution for unified reading, translation, import, recovery, backup, and desktop workflows. This roadmap preserves the current PostgreSQL-first architecture and treats every existing v10 feature as production surface that must remain compatible.

## Non-Negotiables

- Preserve PostgreSQL-first storage and additive migrations.
- Preserve existing production data and existing URLs.
- Preserve Reader, Library, Desktop Companion, Content Import, Recovery, Backup, Admin, translation scheduler, workers, background jobs, chapter editions, and telemetry.
- Never require users to re-import novels.
- Never remove functionality to simplify implementation.
- Never load large chapter or edition text when aggregate metadata is sufficient.
- Never perform destructive migrations or manual production data changes.
- Keep API compatibility or provide compatibility layers.

## Product North Star

GodTranslator should feel like a commercial web novel ecosystem, not a developer utility. A new user should quickly understand how to add a novel, import chapters, recover missing content, translate safely at scale, read comfortably, sync with desktop, and manage a library across devices.

The platform should combine the strongest patterns from Kindle, Steam, VS Code, Notion, NovelFire, WebNovel, Calibre, GitHub Desktop, and Discord while staying minimal, fast, responsive, and permission-aware.

## Current Platform Assets

- PostgreSQL schema with chapter rows and `chapter_editions`.
- Background translation jobs with bounded worker claims.
- Reader and Library web surfaces.
- Admin workspace with content, imports, editions, jobs, recovery, backups, database health, users, and diagnostics.
- Content Import and Recovery separation.
- Desktop Companion and downloader foundation.
- Backup manifest/full backup split.
- Performance telemetry and scheduler QA tools.

## Phase Plan

### Phase 1: Platform Consistency And Safety

Goal: remove known rough edges without changing architecture.

- Align visible runtime version labels.
- Audit placeholder/demo/fake preview content.
- Normalize loading, empty, success, failure, retry, and disabled states.
- Fix horizontal overflow and mobile breakpoints.
- Expand cache-busting/version hygiene.
- Add system health and migration-readiness checks.
- Keep backup overview lightweight and move full backup work behind explicit actions.
- Add roadmap-backed acceptance checks for each core area.

### Phase 2: Reading Dashboard And Navigation

Goal: make Home the operational reading dashboard.

- Home sections: Continue Reading, Recently Read, Reading Streak, Pinned Novels, Favorites, Collections, Trending, Latest Updates, Recently Imported, Recently Downloaded, Reading Statistics, Bookmarks, Recent Searches, Recovery Requests, Translation Jobs, Desktop Sync, Announcements, Release Notes, and Quick Resume.
- Collapse sections by role:
  - Guests: reading-first dashboard.
  - Users: reading plus account and personal library.
  - Translators: translation workspace entry points.
  - Admins: operations summary.
- Top navigation target: Logo, Home, Library, Continue Reading, Search, Notifications, Profile.
- Move operational links into profile and admin menus.
- Keep Settings out of Search and Theme out of top-level navigation.

### Phase 3: Reader Flagship Experience

Goal: make Reader the primary product experience.

- Edition support: English, Original, Reference, Official, Imported, Edited, AI.
- Configurable edition priority rules.
- Persist last chapter, scroll, edition, theme, font, spacing, line height, alignment, width, brightness, and device.
- Add Focus Mode, Zen Mode, Fullscreen, continuous reading, infinite scrolling, paged reading, auto-next, mini TOC, chapter search, jump chapter, copy link, estimated reading time, remaining time, and progress.
- Add bookmark, highlight, note, dictionary, compare mode, and side-by-side edition surfaces.
- Prepare for offline cache and future comments without blocking current reader behavior.

### Phase 4: Library And Novel Management

Goal: make Library feel like Kindle plus Calibre for web novels.

- Views: grid, compact, large covers, shelves, collections.
- Metadata filters: tags, genres, authors, status, completed, ongoing, hiatus, dropped, favorites, pinned.
- Add progress bars, translation status, import status, and desktop sync status.
- Add bulk actions where permission-appropriate.
- Make Novel pages commercial-grade with cover, metadata, progress, statistics, collections, reading buttons, import status, translation status, admin tools, and recent activity.

### Phase 5: Translation Performance And UX

Goal: make translation dramatically faster while preserving one persistent item per chapter.

- Keep claim, translate, and save separated.
- Ensure provider waits never hold a DB connection.
- Preserve bounded worker scheduler and no duplicate claims.
- Add persistent workers, shared clients, connection pooling, dynamic concurrency, adaptive retries, and restart preservation.
- Support job sizes 25, 50, 100, 200, 500, 1000, All, and Custom.
- Simple mode exposes common presets.
- Advanced mode exposes workers, parallelism, chunk size, token limits, retry policy, budget, model, and reference strategy.
- Estimates include time, tokens, cost, workers, ETA, and budget margin.
- Translation profiles: Fast, Balanced, High Quality, Reference Guided, Official Style, novel-specific, and custom.
- Translation profile data model should support style guides, glossaries, translation memory, tone, and consistency.

### Phase 6: Import, Editions, And Recovery

Goal: make content onboarding effortless and recoverable.

- Import Center supports New Novel, Original, English, Reference, Mixed, Desktop Pack, Downloader Pack, ZIP, TXT, folder, drag-and-drop, manifest, and manifestless workflows.
- Brand-new novel path: Create Novel, Select Folder, Preview, Import, Done.
- Automatically create chapter rows, create editions, detect chapter numbers, detect language, detect duplicates, and report checksums.
- Preserve Recovery as missing-edition-only. Recovery must not create chapter rows.
- Recovery supports Original, Reference, English, AI, Desktop Requests, Website Requests, pack generation, and missing diagnostics.
- Import supports validation, warnings, duplicate detection, rollback planning, and import summaries.

### Phase 7: Desktop Companion And Sync

Goal: make desktop a first-class companion, not a side tool.

- Modules: Downloader, Library Cache, Pack Builder, Import Manager, Recovery Manager, Website Sync, Novel Browser, Logs, Activity, Settings, Authentication, Notifications, background downloads, resume after reboot, bandwidth limits, multiple queues, proxy, browser profiles, and Playwright diagnostics.
- Website sync states: Connected, Disconnected, Uploading, Downloading, Pending, Conflicts, Queued, Last Sync, Desktop Version, Website Version.
- Desktop-downloaded chapters should flow naturally into import and recovery workflows.

### Phase 8: Backups And Admin Operations

Goal: make operations professional and memory-safe.

- Backups are split into Overview, Manifest, History, Jobs, Downloads, Cloud, Local, and Restore.
- Never load full backups automatically.
- Full backup creation becomes background-capable with progress by table.
- Admin center includes Overview, Content, Imports, Editions, Novels, Translation, Performance, Jobs, Recovery, Backups, Database, Users, Roles, Diagnostics, Audit Log, and System Health.
- Audit log should avoid secrets, prompts, provider bodies, headers, cookies, tokens, and chapter text.

### Phase 9: Search, Settings, Mobile, And Accessibility

Goal: make the application feel complete on every device.

- Global search covers novels, authors, genres, tags, chapters, jobs, imports, recovery, commands, recent searches, and suggestions.
- Settings sections: Appearance, Reader, Library, Translation, Desktop, Downloads, Notifications, Accessibility, Keyboard, Account, Privacy, Advanced, Developer.
- Each settings section supports Simple, Advanced, and Expert modes.
- Mobile-first layout with bottom navigation, no horizontal scrolling, large tap targets, and touch gestures.
- Accessibility includes keyboard navigation, screen-reader labels, reduced motion, high contrast, large fonts, and color-blind themes.

## Engineering Principles

- Aggregate first, lazy-load details, and never select chapter text for dashboard metadata.
- Keep background jobs resumable, observable, and idempotent.
- Keep migrations additive and safe for existing v10 data.
- Keep restore/import/translation/write actions explicit and permission-aware.
- Keep all large operations background-capable or clearly explicit.
- Prefer small, focused releases over rewrites.
- Add QA tools for each risky workflow and keep them fixture-based by default.

## First Implementation Slices

1. Version and cache hygiene: align backend/frontend labels, expose a single version source, and document release cache behavior.
2. Home dashboard foundation: add role-aware Continue Reading, recent activity, jobs, and desktop sync summaries using aggregate endpoints only.
3. Backup jobs: convert full platform backup creation to a persistent background job with table progress.
4. Translation worker performance: introduce shared provider clients, measurable connection reuse, and stronger concurrency telemetry.
5. Reader persistence: unify last chapter, scroll, edition, and reader settings across devices.
6. Desktop sync contract: define web API and local desktop states before adding new sync features.
7. Import Center polish: drag-and-drop/folder-friendly preview, checksum reporting, and rollback planning.

## Release Gates

Every v11 slice should verify:

- PostgreSQL compatibility.
- Additive migration safety.
- No production data mutation outside explicit user action.
- No OpenAI calls in QA unless explicitly requested.
- No full chapter or edition text loaded in aggregate/dashboard endpoints.
- Admin/translator/user/guest permissions.
- Mobile layout without horizontal overflow.
- Loading, empty, success, failure, retry, and disabled states.
- Restart recovery for background jobs.
- Secret and artifact scan before commit.

## Measurement Targets

- Dashboard endpoints return aggregate metadata without chapter text.
- Backup manifest remains small and fast regardless of chapter text size.
- Translation jobs preserve bounded concurrency and completed work across restarts.
- Reader chapter loads remain fast on large libraries.
- Admin operations report stage-specific safe errors.
- Desktop sync and download states are persisted and recoverable.
