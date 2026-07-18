# Desktop Companion Roadmap v11

v11 makes the Desktop Companion a first-class acquisition and sync surface:

- One-click website connection and remembered website profile.
- Sync Center with health, pending uploads, failed uploads, queued uploads, and recent imports.
- New Novel workflow from URL to download to pack to website import.
- Modern download queue fields for ETA, speed, worker, retries, and last activity.
- Source adapter registry for current NovelFire and planned future sites.
- Automatic Original, Reference, English, and Mixed pack generation.
- Recovery Request to desktop download to website import flow.

## Milestone 1: Foundation

Delivered in this folder:

- CustomTkinter desktop shell.
- Local data root under `%LOCALAPPDATA%\GodTranslatorDesktop`.
- Persistent job state.
- Recovery Request parsing.
- Recovery job creation.
- Reference Recovery Pack creation.
- Public website health test.
- Existing NovelFire downloader source reused through a source adapter.
- Fixture tests.

## Milestone 2: Download Execution UX

- Background job queue with live progress refresh.
- Pause/resume/retry buttons wired to running workers.
- Visible browser verification instruction panel.
- Browser profile selector.
- HTTP/Playwright source detection screen.
- Failed-chapter retry queue.

## Milestone 3: Pack And Import Workflows

- Pack history view.
- Recovery pack preview/upload/apply wizard.
- Original pack builder.
- New Novel pack builder.
- Import preview result viewer.
- Apply confirmation with add-missing default.

## Milestone 4: Website Sync

- Desktop-safe authentication flow.
- Library cache refresh from website metadata.
- Sync status checks per novel.
- Open imported novel action.
- Import job polling and result summaries.
- Version compatibility, pending upload, failed upload, queued upload, and last sync state.
- Preview-before-execute import workflow.

## Milestone 4 Status

Delivered in v11 foundation:

- Manual bearer token is kept in memory only.
- Sync Center shows connection, version compatibility, upload queue, and recent import state.
- Pack upload supports Preview, Execute Import, Retry, and Open Imported Novel.

Remaining secure-production step:

- Add website-issued desktop device authorization and OS-backed token storage before durable login is enabled.

## Milestone 5: Multi-Source Acquisition

- Source adapter registry UI.
- Additional adapters beyond NovelFire.
- Adapter diagnostics and fixture tests.
- Source-specific extraction rules without hardcoding one future source.

## Non-Goals

- The desktop companion is not the production database.
- It does not run translation jobs.
- It does not manage accounts, Admin roles, backups, or restore.
- It does not bypass CAPTCHA, login, or anti-bot protections.
