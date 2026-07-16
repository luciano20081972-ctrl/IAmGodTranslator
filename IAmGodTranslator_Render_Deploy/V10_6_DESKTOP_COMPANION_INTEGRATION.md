# GodTranslator v10.6 Desktop Companion Integration

v10.6 connects the website and Desktop Companion into one product workflow.

## Desktop

- Connect to Website
- Remember Website
- Test Connection
- Authenticate
- Upload Pack
- Preview Import
- Execute Import
- Open Imported Novel
- Track upload progress

## New Novel Wizard

The desktop flow is:

Home -> New Novel -> Paste Novel URL -> Detect Source -> Download Chapters -> Preview -> Send to GodTranslator -> Website imports automatically -> Open novel in browser.

Normal use does not require manual ZIP handling.

## Download Manager

Download rows show novel, website, current chapter, completed, remaining, failed, retries, ETA, download speed, current worker, last activity, and import status.

Actions include Pause, Resume, Retry Failed, Cancel, and Open Folder.

## Source Adapters

NovelFire is the active adapter. Adapter slots now exist for:

- 69Shuba
- Qidian
- Royal Road
- ScribbleHub

Future adapters can be added without rewriting the downloader core.

## Auto Packs And Sync

Completed downloads can build Original, Reference, English, and Mixed packs. If a website connection exists and auto-upload is enabled, the companion queues upload state for preview and import.

## Recovery

Recovery Requests are one-click from the desktop side: open request, download missing chapters, build a pack, upload, preview, execute, and open the website novel.
