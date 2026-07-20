# GodTranslator v11.1.0 Reference-First Reader Polish Report

## 1. Starting main SHA

`origin/main` at branch creation and final local verification: `4b3d43eb9a76c01b13b8bdf3ba617591c296f4e5`.

## 2. Branch

`v11.1.0-reference-first-reader-polish`.

## 3. Architecture audit

The existing application already stores chapter text in `chapters` and richer edition records in `chapter_editions`. The v11.1 work keeps that architecture and adds coverage behavior through metadata/policy helpers, not a parallel text store.

## 4. Existing edition model

Readable English is resolved from `chapter_editions` plus legacy `chapters.ai_text`. Reference content remains a distinct source. Existing English editions are preserved and never overwritten by coverage application.

## 5. New coverage policy

Per-novel English coverage policy values are `original_translation_only`, `reference_first`, and `manual`. `i-am-god` defaults to `reference_first`; other novels default conservatively to `original_translation_only` unless configured.

## 6. Resolver priority

The resolver order is:

1. Keep an active readable English edition.
2. Fill missing English from readable Reference when policy is `reference_first`.
3. Mark chapters with Original only as AI-translation candidates.
4. Mark chapters with no Original and no Reference as `blocked_missing_source`.

## 7. Reference-derived edition design

Reference promotion writes a normal readable English edition with `edition_key` `reference-derived`, language `en`, role/type `Reference Derived`, active/default flags, and text identical to the stored Reference text.

## 8. Provenance design

Reference-derived metadata records novel ID, chapter ID/number, language, source kind `reference`, provenance `reference_promoted`, source Reference identifier, source URL/identifier where present, content checksum, workflow actor, active/readable state, modified false, and null model/cost/token values. Chapter bodies are not logged or committed.

## 9. Active-edition behavior

Reference-derived English becomes active only when no readable English already exists. Existing manually selected, manually edited, AI, and alternative English editions are not replaced.

## 10. Translation integration

Admin Translation includes a Build English Coverage panel with preview, no-cost Reference apply, and separate explicit AI job creation. Translation estimates distinguish existing English, Reference fill, Original translation candidates, and blocked chapters. Reference promotion is not labeled as translation and is not charged against OpenAI budget.

## 11. Current I Am God fixture result

Fixture A seeded 908 synthetic chapters with 906 readable English chapters and Reference-only chapters 176 and 177. Preview returned `existing_english: 906`, `reference_fill: 2`, `translation_from_original: 0`, `blocked: 0`. After apply, readable English was 908 and promoted chapters were 176 and 177.

## 12. Future-novel fixture result

Fixture B seeded 900 Original chapters, Reference on chapters 1-480, and no English. Preview returned `reference_fill: 480`, `translation_from_original: 420`, `blocked: 0`.

## 13. Gapped-Reference result

Fixture C seeded Original chapters 1-200 and Reference chapters 1-100 and 102-150. Preview returned `reference_fill: 149`, `translation_from_original: 51`, `blocked: 0`.

## 14. Idempotence result

Running Reference apply repeatedly on the same fixture did not create duplicate English editions and did not alter chapters already covered by readable English.

## 15. Duplicate prevention

Reference promotion checks for any readable English before insert/update, uses a stable `reference-derived` edition key, and preserves a single active/default English edition for each filled chapter.

## 16. Reference privacy

Public Reader source options are English-only. Raw Reference endpoint access remains restricted to admin/translator roles. Public English responses scrub internal edition metadata for non-admin/non-translator users.

## 17. Reader design changes

Reader UI was polished into a quieter editorial shell with improved heading treatment, centered reading column, restrained controls, TOC and settings labels, bottom chapter navigation, role-aware edition/source controls, missing-English retry state, and reduced visual noise.

## 18. Desktop screenshots

Desktop viewport screenshot: `C:\Users\lucia\AppData\Local\Temp\gt-v11-1-reader-screenshots\desktop-1366x768.png`.

## 19. Mobile screenshots

Mobile viewport screenshot: `C:\Users\lucia\AppData\Local\Temp\gt-v11-1-reader-screenshots\mobile-390x844.png`.

## 20. Accessibility result

Static and fixture QA verified accessible Reader controls, keyboard shortcuts guarded while typing, Escape close behavior, visible Reader controls, reduced-motion handling, and non-color-only status text.

## 21. Performance result

Reader requests fetch only the requested chapter body, abort stale navigation fetches, de-duplicate in-flight chapter requests, keep a bounded chapter cache, and avoid Reference prefetch for unauthorized users. The fixture QA covers 100+ synthetic chapters.

## 22. Reading-progress result

Reader progress persists by novel/chapter/source with scroll percentage. Guest progress uses local storage; authenticated progress continues through the existing preferences/progress APIs with debounced writes.

## 23. Bookmark result

Reader bookmarks support add/remove, accessible labels, guest local storage, authenticated backend persistence, and duplicate prevention on repeated clicks.

## 24. Table-of-contents result

The Reader table of contents opens without fetching every chapter body, highlights current chapter state, supports chapter search, closes on desktop/mobile, and navigates without a full browser reload.

## 25. PostgreSQL result

Local SQLite migration and fixture coverage passed. GitHub Actions PostgreSQL 16 gate completed successfully:

- Run ID: `29714612231`
- Job ID: `88265210277`
- Workflow: `GodTranslator v11 RC Release Gate`
- Job: `PostgreSQL migration and auth gate`
- Attempt: `1`
- Validated application-code SHA: `a19c893793b62112eeec7037a4b72e076a00643b`
- Head branch: `v11.1.0-reference-first-reader-polish`
- Run status: `completed`
- Run conclusion: `success`
- Job status: `completed`
- Job conclusion: `success`
- Run created: `2026-07-20T03:25:03Z`
- Job started: `2026-07-20T03:55:13Z`
- Job completed: `2026-07-20T03:56:41Z`

Successful steps included PostgreSQL service startup, empty database initialization, migrations, migration idempotence, v11 static and fixture QA, Reference-first coverage fixtures, authorization matrix, Reference privacy, secret scan, and artifact scan. Warnings were limited to GitHub runner/action deprecation notices and the expected ephemeral PostgreSQL `trust` authentication warning for the isolated CI service. A PostgreSQL foreign-key error appeared in service logs during the rollback/concurrency negative path, while the job result reported rollback and concurrency checks as passed.

## 26. Authorization result

Existing v11 authorization fixture QA passed. Reference privacy remained intact: guests/public readers do not receive raw Reference content or hidden Admin provenance.

## 27. Migrations

Migrations are additive and idempotent. Existing content is not rewritten during migration, and Reference promotion remains an explicit Admin action.

## 28. Security scan

Secret scan passed locally for API keys, passwords, DB URLs, tokens, cookies, bearer headers, and private keys.

## 29. Artifact scan

Tracked artifact scan passed locally for pycache, pyc, env files, venvs, logs, cookies, browser profiles, local DBs, and release ZIPs.

## 30. Known limitations

The v11.0.0 manual authenticated Admin verification remains pending and is not claimed here. The v11.1 PostgreSQL 16 migration/auth gate has completed successfully, and no v11.1 blocker remains.

Final verdict: `READY FOR V11.1 CONTROLLED RELEASE`.

## 31. Exact commands

Local commands run included:

```powershell
python -m py_compile IAmGodTranslator_Render_Deploy\app\main.py IAmGodTranslator_Render_Deploy\app\db.py IAmGodTranslator_Render_Deploy\tools\qa_v11_1_reference_first_reader_polish.py IAmGodTranslator_Render_Deploy\tools\qa_v11_phase2_reader_experience.py
C:\Users\lucia\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check IAmGodTranslator_Render_Deploy\static\app.js
python IAmGodTranslator_Render_Deploy\tools\qa_v11_1_reference_first_reader_polish.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase2_reader_experience.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase4_translation_workspace.py
python IAmGodTranslator_Render_Deploy\tools\qa_v10_6_translation_selector.py
git diff --check
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase1_navigation_home_settings.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase2_reader_experience.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase3_library_novel_dashboard.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase4_translation_workspace.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase5_content_import_editions_recovery.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase6_desktop_sync.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase7_backups_operations.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_phase8_mobile_accessibility_polish.py
python IAmGodTranslator_Render_Deploy\tools\qa_v11_1_reference_first_reader_polish.py
```

FastAPI import and Uvicorn startup were verified with a temporary dependency target and temporary SQLite database, with `/api/health` returning version `11.1.0` and reachable database status.

Final lightweight release-gate checks run after CI success:

```powershell
git status --short
git diff --check
python -m py_compile <27 app/tools Python files>
C:\Users\lucia\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe --check IAmGodTranslator_Render_Deploy\static\app.js
git grep tracked secret scan
git ls-files artifact scan
```

Results: `git diff --check`, Python compile, JavaScript syntax, refined tracked secret scan, and tracked artifact scan passed. `git status --short` showed only the pre-existing untracked `IAmGodTranslator_Render_Deploy/V11_PRODUCTION_RELEASE_REPORT.md`, which was not staged or committed.

## 32. Commit SHAs

- `7f90519`: Add Reference-first English coverage model
- `a7ddb9a`: Redesign and polish Reader experience
- `a19c893`: Add Reader accessibility and Reference coverage QA
- `f9de957`: Finalize GodTranslator v11.1.0 QA report

The release-gate status update commit SHA is recorded in the final task response after commit creation.

## 33. CI run and job IDs

- Run ID: `29714612231`
- Job ID: `88265210277`
- Run URL: `https://github.com/luciano20081972-ctrl/IAmGodTranslator/actions/runs/29714612231`
- Job URL: `https://github.com/luciano20081972-ctrl/IAmGodTranslator/actions/runs/29714612231/job/88265210277`
- Attempt: `1`
- Validated application-code SHA: `a19c893793b62112eeec7037a4b72e076a00643b`
- Queue reason: waited for a GitHub-hosted `ubuntu-latest` runner; no environment approval, billing, permissions, Actions-disabled, self-hosted runner, or policy blocker was reported.
- Captured state: completed, conclusion success

## 34. Confirmation main unchanged

`origin/main` remained `4b3d43eb9a76c01b13b8bdf3ba617591c296f4e5`. No merge to main was performed.

## 35. Confirmation no deployment

No Render deployment was performed.

## 36. Confirmation no OpenAI calls

`OPENAI_API_KEY` was cleared during QA. Reference preview/apply does not call OpenAI. No production translations were run.

## 37. Confirmation no production data modified

QA used isolated synthetic SQLite fixtures and temporary local runtime data only. No production `DATABASE_URL` writes, imports, recoveries, restores, or backups were performed.
