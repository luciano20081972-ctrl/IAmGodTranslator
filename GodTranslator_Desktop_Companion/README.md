# GodTranslator Desktop Companion v11

GodTranslator Desktop Companion is the Windows desktop side of GodTranslator v11. It supports local novel acquisition, Playwright/browser downloads, Recovery Requests, automatic pack creation, and explicit website sync.

The website remains the live source of truth for PostgreSQL data, Library, Reader, accounts, translation jobs, Admin, backups, restore, and production records. The desktop companion stores only local job state, downloads, pack history, settings, logs, connection profiles, and cached metadata under:

```text
%LOCALAPPDATA%\GodTranslatorDesktop
```

## Framework

The desktop shell uses CustomTkinter. It was selected because it keeps the project in Python, works well with the existing Playwright downloader, supports a modern dark Windows interface, and is lighter than shipping a full browser shell for this first milestone.

## Exact Commands For Luciano

Open PowerShell or Command Prompt:

```bat
cd /d C:\Users\lucia\Documents\Codex\2026-06-27\https-chatgpt-com-c-6a3f403a-8d04\GodTranslator_Desktop_Companion
SETUP_ONCE.bat
RUN_GODTRANSLATOR_DESKTOP.bat
```

Run tests:

```bat
cd /d C:\Users\lucia\Documents\Codex\2026-06-27\https-chatgpt-com-c-6a3f403a-8d04\GodTranslator_Desktop_Companion
.venv\Scripts\python.exe -m unittest discover -s tests
```

Optional public website health test:

```bat
set GT_DESKTOP_TEST_WEBSITE=1
.venv\Scripts\python.exe -m unittest tests.test_foundation.DesktopCompanionFoundationTests.test_public_website_health_when_enabled
```

## v11 Included

- Modern CustomTkinter shell with navigation:
  - Dashboard
  - Downloads
  - Library
  - New Novel
  - Recovery
  - Packs
  - Sync
  - Activity
  - Settings
  - Advanced Logs
- Existing NovelFire downloader source copied into `desktop_companion/legacy/novelfire_downloader` for reuse.
- Source-adapter structure with initial `NovelFireAdapter`.
- Persistent local job state in `%LOCALAPPDATA%\GodTranslatorDesktop\jobs.json`.
- Recovery Request parsing and validation.
- Recovery job creation from request chapters without manual range entry.
- GodTranslator-compatible Reference Recovery Pack creation.
- Pack checksum validation and explicit secret exclusions.
- Website health and desktop API tests.
- Pack upload preview and execute client.
- Persistent upload queue and Sync Center status.
- Automatic Original, Reference, English, and Mixed pack build support.
- Source adapter registry for NovelFire plus future 69Shuba, Qidian, Royal Road, and ScribbleHub adapters.
- Bounded browser queue. The default is one active Playwright/browser job at a time; additional jobs remain queued and start when a slot is free.
- Explicit Preview then Execute Import flow. Preview can upload a pack, but the import is not applied until the user chooses Execute Import.
- Fixture-only tests.

## Safety Defaults

- Skip existing files.
- Resume existing jobs.
- Preview imports before apply.
- Add missing data only.
- Never include passwords, API keys, cookies, browser profiles, access tokens, refresh tokens, logs, or local databases in packs.
- Never store plaintext website passwords in config files.
- Manual bearer tokens are kept in memory only for the current desktop session. A production device-authorization token flow is documented before any durable credential storage is added.

## Current Upload Status

The v11 website exposes Desktop Companion endpoints for health, auth check, sync status, import history, pack preview, and pack execution. The companion previews before executing imports and uses add-missing behavior by default.

## Packaging And Updates

The companion should be packaged as a signed Windows app or installer after release QA. Auto-update must not be silent: it should show the version, release notes, checksum/signature status, and rollback instructions before replacing local software. Browser profiles, downloads, local logs, queued jobs, and upload state must remain under `%LOCALAPPDATA%\GodTranslatorDesktop` and must not be bundled into a release package.
