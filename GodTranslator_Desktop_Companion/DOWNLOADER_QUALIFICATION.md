# DL-R1 downloader workflow

English Wikisource is supported for canonical work pages with numbered `Chapter_N` subpages and transcribed chapter bodies. The desktop app retrieves the work title and author and discovers the chapter URLs listed on that work. It accepts the published chapter number in the matching chapter title. One local HTTP worker fetches the selected chapters sequentially. Choose work you are authorized to download and keep within its source policy.

The Downloader writes UTF-8 chapter files and a metadata checkpoint in the existing local download folder. A subsequent selection for the same work skips entries whose source and SHA-256 match the checkpoint. To update the work, discover again and select the desired range using the same title and output folder. If a chapter file was changed outside the app, keep a copy and move it aside before retrying. Failed and interrupted runs retain verified files. Startup recovers active jobs as paused.

The `Packs` folder inside a job's directory holds its validated ZIP. The pack builder checks the saved files against the checkpoint and uses an atomic replacement. Use **Send to GodTranslator** from the job to preview that pack. The Sync view shows the estimated import result. **Execute Import** asks for confirmation and uses add-missing behavior. A preview is tied to its pack checksum and website. If either changes, create a fresh preview. The website remains the canonical library.

The website acquisition source list is a fixture contract. A server download worker and phone acquisition are follow-up scope. NovelFire uses the bundled Playwright browser when selected, with startup diagnostics for a missing installation. Live NovelFire and legacy generic Direct HTTP extraction require separate validation. Paid providers require explicit enablement and their own credentials.

## Windows acceptance

Use a Windows test desktop and a disposable IAGT instance with an authorized administrator account.

1. Check out the qualified DL-R1 commit. Run `SETUP_ONCE.bat` and then `RUN_GODTRANSLATOR_DESKTOP.bat` from the Desktop Companion directory.
2. In Sync, save the disposable instance URL and the administrator bearer token for the current session. Run Test Connection and Authenticate.
3. In **New / Update Novel**, enter `https://en.wikisource.org/wiki/The_Wonderful_Wizard_of_Oz` and select **Discover Chapters**. Verify the title, author and available range. Select chapters `1-3`, provider **Auto**, and variant **english**. Use a new output folder.
4. Start the download. Verify the Downloads view changes from running to completed and shows three written chapter files. Open the output folder and verify that all three files have chapter text. Repeat the same selection and verify three skips. Use the Downloads controls to pause a fresh job after its first file and resume it, then verify the first file's checksum is unchanged.
5. From the completed job, select **Send to GodTranslator**. Confirm the preview shows three chapters before choosing **Execute Import**. Open the imported novel and read all three chapters. Preview and execute the same pack again to verify idempotence.
6. Record Windows and Python versions, commit and tree, job and import summaries, and hashes for the three files and pack. Keep credentials and unrelated local files out of evidence.

## Limits and recovery

The supported path limits responses to 2 MiB, caps one selection at 1,000 chapters, and uses one active Wikisource worker per application instance. Requests use a 15-second socket timeout and retry eligible failures up to three times. The app spaces chapter requests by at least a second and interrupts waits on cancellation. Local activity logs rotate after approximately 1 MiB. Packs are capped at 64 MiB and 3,001 members.

Save the existing download folder, metadata checkpoints, packs, and job files before switching application versions. The change adds no server database migration. An earlier desktop build can still read the text and pack files. Keep the job and its metadata together for a later resume with DL-R1.
