# GodTranslator v10.4 Platform Roadmap

GodTranslator should become a complete personal web-novel platform for collecting, importing, translating, managing, backing up, and reading multiple novels. It should not remain a one-novel website, and v10.4 should not become an uncontrolled expansion. The near-term focus is translation reliability and measured performance.

## Product Systems

### 1. Reading Platform

Essential:
- Home, Library, Novel Detail, Reader, Continue Reading, reading history, bookmarks, favorites, personalization, cross-device progress, search, and discovery.
- Preserve the v10.3 public reading experience, Reference privacy, and account-aware progress.

Important later:
- Better discovery filters, richer reading stats, per-novel reading preferences, and smarter resume/recommendation surfaces.

Optional long-term:
- Public shelves, optional sharing, comments, and collaborative reading lists.

### 2. Novel Management Platform

Essential:
- Add and edit novels, covers and metadata, chapter imports, source tracking, translation status, missing-data diagnostics, exports, and archiving.
- Preserve PostgreSQL in `godtranslator_v10` as the live source of truth.

Important later:
- Novel-specific profiles, glossaries, source provenance, import history, validation reports, and safer bulk edits.

Optional long-term:
- Connector-based imports, scheduled source checks, and collaborative catalog curation.

### 3. Translation Platform

Essential:
- Translation profiles, style guides, glossaries, Reference-guided translation, parallel jobs, cost/time estimates, job monitoring, retry/recovery, comparison, model selection, and scheduled/economy jobs.
- Preserve job persistence, chapter-level saves, budget limits, pause/resume/cancel, and safe retry behavior.

Important later:
- Quality review workflows, glossary filtering by chapter, prompt versioning, benchmark comparisons, adaptive concurrency, and model/provider comparison reports.

Optional long-term:
- Batch-provider integrations, scheduled overnight queues, reviewer assignments, and optional human edit tracking.

### 4. Operations Platform

Essential:
- Accounts and roles, Admin workspace, database health, backups, safe restore, novel recovery, activity history, diagnostics, security, and auditability.
- Preserve authorization boundaries and backup/restore protections.

Important later:
- Audit logs for admin actions, backup schedules, restore approval records, performance history, and operational alerts.

Optional long-term:
- Multi-user administration, shared workspaces, and optional publishing controls.

## Phased Roadmap

## Phase 1: Translation Reliability and Performance

Goal:
Measure the real production translation path, expose timing diagnostics, prove fake-provider parallelism, and fix confirmed internal bottlenecks.

User benefit:
Jobs stop looking like a black box. The user can see whether time is spent waiting for workers, provider responses, retries, saves, or oversized prompts.

Technical requirements:
- Per-item timing for queue wait, claim, chapter load, prompt build, provider wait, save, total duration, retry delay, and attempt count.
- Job-level aggregate diagnostics: active/peak workers, average provider latency, average chapter duration, throughput, retry/rate-limit/timeout counts, token/character averages, Reference usage, and ETA.
- Admin Translation Performance panel.
- Deterministic fake-provider overlap QA.
- Retry/backoff behavior that does not hold scarce global worker slots while sleeping.

Dependencies:
- Existing translation job tables.
- Existing Admin authorization.
- Existing fake provider and scheduler tests.

Risks:
- Real provider latency, OpenAI rate limits, and Render process limits cannot be proven without controlled real benchmarks.
- Instrumentation must avoid storing chapter text, prompts, API keys, auth headers, or provider content bodies.

Definition of done:
- No OpenAI calls in QA.
- Fake provider proves overlapping provider waits.
- Admin can inspect safe performance metrics.
- Confirmed internal bottlenecks are fixed or explicitly documented.

Scope classification:
- Essential for v10.4.

## Phase 2: Import/Export and Multi-Novel Management

Goal:
Make multiple novels first-class, with reliable imports, exports, metadata, source tracking, and archive controls.

User benefit:
The platform can manage a real library rather than a single title.

Technical requirements:
- Import preview and apply flows for Original, Reference, and AI where appropriate.
- Export packages per novel and full-platform backups.
- Source URL/provenance fields and validation reports.
- Missing-data diagnostics per novel.

Dependencies:
- Stable backup/restore payloads.
- Existing novel/chapter tables.
- Admin-only write controls.

Risks:
- Bulk import mistakes can overwrite valuable text if defaults are not conservative.
- Source sites vary widely and should not be scraped automatically without explicit future design.

Definition of done:
- Add/edit/import/export flows are safe on fixture data.
- Existing text is never overwritten by default.
- Multi-novel Library and Admin flows remain responsive.

Scope classification:
- Essential after performance.

## Phase 3: Translation Quality Tools and Glossary Management

Goal:
Improve translation quality through profile, glossary, style, review, and comparison tools.

User benefit:
Translations become more consistent across chapters and novels.

Technical requirements:
- Saved translation profiles.
- Per-novel glossaries and style guides.
- Relevant glossary filtering by chapter.
- Comparison view for Original, Reference, and AI.
- Review notes and retry selected chapters.

Dependencies:
- Prompt-size diagnostics from Phase 1.
- Per-novel metadata/profile storage.

Risks:
- Large glossaries can slow jobs and increase cost if not filtered.
- Quality features can bloat prompts if not measured.

Definition of done:
- Glossary/style payload size is visible before launch.
- Review/retry does not duplicate completed chapters.
- Missing Reference never blocks translation.

Scope classification:
- Important later.

## Phase 4: Reading and Library Expansion

Goal:
Deepen the reader and library surfaces after translation operations are reliable.

User benefit:
The app becomes a daily reading platform, not only an admin tool.

Technical requirements:
- Improved library search/filtering.
- More reading history controls.
- Per-novel progress and reading preferences.
- Better mobile reader navigation.
- Optional reading analytics.

Dependencies:
- Multi-novel management.
- Account preferences and progress sync.

Risks:
- Reader polish can distract from operational reliability if done too early.
- Public pages must continue hiding Reference metadata.

Definition of done:
- Reading improvements are measurable and do not regress privacy.

Scope classification:
- Important later.

## Phase 5: Automation, Collaboration, and Optional Sharing

Goal:
Add optional automation and collaboration once the single-user personal platform is stable.

User benefit:
Advanced users can schedule work, share selected output, and collaborate safely.

Technical requirements:
- Scheduled jobs.
- Optional background worker service.
- Audit logs.
- Optional sharing permissions.
- Notifications or status summaries.

Dependencies:
- Reliable job persistence.
- Safe roles and auditability.
- Operational performance metrics.

Risks:
- Collaboration introduces privacy and moderation requirements.
- Scheduled provider calls require strict budget and rate-limit controls.

Definition of done:
- Automation is opt-in, budget-bounded, auditable, and reversible.

Scope classification:
- Optional long-term.

## v10.4 Guardrails

Essential:
- Measure before claiming speed improvements.
- Keep PostgreSQL as sole live source of truth.
- Keep schema `godtranslator_v10`.
- Preserve v10.3 reading, auth, backup, restore, and job controls.
- Do not call OpenAI in normal QA.

Important later:
- Adaptive concurrency based on real metrics.
- Dedicated worker service if translation volume grows.

Optional long-term:
- Sharing, collaboration, and automation beyond personal use.
