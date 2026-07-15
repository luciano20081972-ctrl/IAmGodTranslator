# GodTranslator v10.5 Translation Quality Platform

## Scope

v10.5 adds translation quality and production-experience tools on top of v10.4 performance instrumentation. It does not change the scheduler architecture, backup architecture, auth model, database source of truth, or production deployment flow.

## Delivered

- Translation Quality workspace at `#/quality/{novel_id}` and `#/quality/{novel_id}/{chapter_number}`.
- Review marks: Excellent, Good, Needs Review, and Needs Retranslation.
- Chapter quality metadata: score, Reference availability, profile, model, prompt size, cost, duration, retry count, and warnings.
- AI/Original/Reference comparison with Reference text visible only to Admin in quality/compare views.
- Translation version history with restore; prior AI is preserved before retranslation overwrite.
- Shared Translation Profiles: Natural English Novel, Faithful Translation, Reference Guided, Fast Draft, and Publication Quality.
- Profile duplicate/create endpoints and Admin profile management UI.
- Smart Glossary with categories, aliases, locked terms, usage counts, and relevant-entry-only prompt inclusion.
- Admin Prompt Inspector with prompt sections, estimated tokens, approximate cost, and no provider request.
- Admin Live Translation Monitor with active workers, current chapters, queue, rate limits, timeouts, throughput, ETA, and utilization.
- Admin Cost Analysis with total/average cost, tokens, expensive chapters, and monthly usage.
- Retranslation preview and explicit-confirmation job creation for selected, failed, low-quality, alternate-model, and without-Reference workflows.

## Safety Boundaries

- Chinese `original_text` remains the source of truth.
- `reference_text` remains optional guidance and is not required for eligibility.
- Prompt Inspector does not call OpenAI and does not expose API keys, auth headers, provider bodies, or secrets.
- Smart Glossary sends only matching entries plus ad hoc notes, not the full glossary.
- Retranslation does not overwrite AI by default; explicit confirmation is required.
- Completed translations are saved before telemetry, and telemetry failure is isolated from item completion.
- v10.5 QA uses disposable SQLite and fake/local translation completion only.

## Focused QA

Run:

```powershell
python -B tools/qa_v10_5_translation_quality.py
python -B tools/qa_v10_4_translation_performance.py
python -B tools/qa_v10_3_translation_scheduler.py
```

Recommended environment isolation:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$env:TRANSLATION_AUTOSTART = "false"
```
