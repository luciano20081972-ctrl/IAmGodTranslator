# GodTranslator v10.4 Translation Performance Audit

This audit documents the production translation path and the v10.4 instrumentation/fixes. It does not claim real OpenAI translation is faster. Real provider performance still requires a controlled Admin benchmark after deployment and explicit approval.

## Current Production Translation Path

1. Job creation
   - `POST /api/translation/jobs` requires translator/admin authorization.
   - The server selects chapters, normalizes settings, estimates cost/time, inserts a `translation_jobs` row, and inserts one `translation_job_items` row per eligible chapter.
   - Existing AI chapters are skipped when `only_untranslated` is true.

2. Worker startup
   - `translation_runner.start(job_id)` starts one daemon thread per job.
   - The thread runs an asyncio event loop.
   - The worker count comes from the normalized job settings and is bounded by the global cap.

3. Item claiming
   - Workers claim one item at a time from PostgreSQL/SQLite.
   - PostgreSQL uses `FOR UPDATE SKIP LOCKED`, so workers should not claim the same item.
   - Claims set item status to `running`, increment attempts, store worker and lease data, and update the parent job to `running`.

4. Chapter loading
   - The claim path loads the chapter row after the item is marked running.
   - Original text is required.
   - Reference text is loaded only when job settings allow Reference.

5. Prompt construction
   - Prompt order is stable rules, optional style guide, relevant glossary, Chinese Original, optional Reference.
   - The Chinese Original is never truncated or summarized.
   - Reference is optional and missing Reference does not block translation.

6. Provider request
   - Production uses `AsyncOpenAI` and `responses.create`.
   - The async client is cached and reused while the API key is unchanged.
   - v10.4 wraps the provider call in a bounded timeout from the preset/settings.

7. Response processing
   - The response output text is saved as the AI chapter.
   - Input/output token usage and estimated cost are recorded when provider usage is available.

8. Database save
   - Save updates the chapter AI text and the job item state in a short database transaction.
   - Chapter-level save behavior is preserved.
   - Parent job counts and status are refreshed after each item.
   - v10.4 commits the chapter/item save before performance telemetry is recorded.

9. Worker claiming next item
   - Workers loop back to claim another pending/retryable item until the job is empty, paused, cancelled, completed, or failed.

10. Job progress update
   - Progress is derived from job item status counts.
   - v10.4 adds safe timing fields and Admin aggregates.

## Confirmed by Code

- Default preset concurrency before v10.4:
  - Careful: 1
  - Balanced: 3
  - Fast: 4
  - Maximum Safe: 6
- Global concurrency cap default: 8.
- PostgreSQL claims use `FOR UPDATE SKIP LOCKED`.
- OpenAI production path uses `AsyncOpenAI`; the older sync client is still present for the manual helper path but is not used by the normal runner.
- The async OpenAI client is reused globally by API key.
- Database connections are short-lived and are not held during provider waits.
- Render startup currently starts the scheduler inside the FastAPI web process.
- Startup marks previously running jobs/items interrupted and returns them to queued/pending.
- v10.3 had no per-item queue/claim/prompt/provider/save timing, making slowdown diagnosis speculative.
- v10.3 retry backoff slept while the worker still held a global worker slot. v10.4 releases the slot before circuit-breaker waiting.
- v10.3 synchronous claim/save/heartbeat calls ran inside async worker tasks. v10.4 moves them through `asyncio.to_thread` so provider coroutines are not delayed by blocking DB I/O.
- Auto Optimize existed as a setting but was not a true adaptive runtime controller. v10.4 exposes effective settings and timing needed for a later adaptive controller; it does not pretend real adaptive optimization is complete.

## Confirmed Production Failure Fixed in v10.4

Production showed:

`psycopg.errors.AmbiguousColumn: column reference "sample_count" is ambiguous`

Confirmed root cause:
- The crash occurred in `record_translation_performance()` during the PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` for `translation_performance`.
- The v10.3 UPSERT accumulated counters with unqualified assignments such as `sample_count = sample_count + 1`.
- In PostgreSQL, that column name can refer to the existing target row or the incoming `EXCLUDED` row, so the statement is ambiguous.

v10.4 fix:
- The UPSERT uses the safely generated table reference from `self.table("translation_performance")` and aliases it as `target`.
- Every accumulated metric is qualified as `target.<column> + EXCLUDED.<column>`.
- Covered columns: `sample_count`, `success_count`, `failure_count`, `total_duration_seconds`, `total_input_chars`, `total_output_chars`, `total_input_tokens`, `total_output_tokens`, `rate_limited_count`, and `timeout_count`.

Why jobs appeared to stall or stop:
- The telemetry write previously ran as part of finishing a translation result. If PostgreSQL raised `AmbiguousColumn`, the worker could fail after the provider result existed but before the scheduler completed normal item finalization.
- A completed chapter save could be rolled back or the worker loop could terminate, leaving the parent job counts stale and making Admin progress look stuck.
- Concurrent workers could also finish near the same time while parent job counts lagged until another refresh.
- Retryable failed items could be counted as failed/no remaining too early, causing a job to flip to failed before a configured retry was claimed.

v10.4 isolation behavior:
- `finish_translation_item()` first saves the chapter AI text, job item status, item timing metrics, and refreshed job counts in the normal transaction.
- After that transaction finishes, `safe_record_translation_performance()` attempts telemetry in a separate guarded call.
- If telemetry fails, the app logs `translation_performance_telemetry_failed`, returns `telemetry_warning = "performance_telemetry_failed"`, and keeps the completed chapter/item saved.
- The worker does not call `finish_translation_item()` a second time for the same item just because telemetry failed.

## Measurable but Not Yet Confirmed

- Real OpenAI provider latency and variance.
- Real rate-limit frequency and 429 backoff pressure.
- Whether the selected model is slower than the previous model.
- Whether Reference-enabled jobs are materially slower for typical chapter sizes.
- Whether large style guides or glossaries are common enough to dominate prompt size.
- Whether Render CPU/network/process limits are throttling useful concurrency.
- Whether live PostgreSQL latency is significant during claim/save phases.
- Whether polling frequency becomes material under many jobs.

## Unlikely Based on Code

- Browser polling does not drive worker scheduling.
- Missing Reference does not block translation when Reference is enabled.
- Provider waits are not serialized by a database transaction.
- The fake scheduler can run concurrent work; v10.4 adds provider-overlap proof for the fake provider path.

## External / Provider Dependent

- OpenAI queueing and model-specific latency.
- OpenAI account rate limits.
- Transient 429, 5xx, timeout, or network failures.
- Render instance sleep/restart behavior.
- Render plan CPU and outbound network limits.

## v10.4 Instrumentation Added

Per translation item:
- Queue wait time.
- Claim duration.
- Chapter-data load time.
- Prompt-build time.
- Provider wait time.
- Save duration.
- Total chapter duration.
- Retry delay.
- Attempt count.
- Original and Reference character counts.
- Prompt token estimates for instructions/glossary, Original, Reference, and output.
- Provider start/end timestamps for overlap proof.

Per job/Admin aggregate:
- Current speed.
- Active workers.
- Peak active workers from provider overlap intervals.
- Average provider latency.
- Average total chapter duration.
- Chapters per minute and recent throughput.
- Retry, 429, timeout, and failure counts.
- Average input/output tokens.
- Average Original and Reference characters.
- Reference usage percentage.
- Estimated remaining time when enough data exists.
- Last activity and health messages via job rows.

Not stored:
- Original chapter text.
- Reference chapter text.
- Translated text inside diagnostics.
- Full prompts.
- API keys.
- Authorization headers.
- Provider response bodies containing content.

## Prompt and Token Efficiency Findings

Current prompt order:
1. Stable translation rules.
2. Optional style guide.
3. Relevant glossary entries.
4. Chinese Original.
5. Optional Reference.

Findings:
- Original text is sent once.
- Reference text is sent once and only when enabled and available.
- The prompt asks for translated chapter text only, not reasoning or commentary.
- Glossary filtering already limits very large glossary payloads to required/global/matched lines.
- v10.4 exposes token estimates for Original, Reference, instructions/glossary, and output.

Risk:
- The estimate-side instruction/glossary token count is approximate. Real provider usage is still stored from provider responses when available.

## Reference Overhead Findings

Confirmed:
- Reference can substantially increase input size when available.
- Reference is optional per job.
- Missing Reference does not block translation.
- Public users cannot view Reference text or counts.

Needs real measurement:
- Whether Reference materially increases wall-clock time on the selected model for the user's chapter set.

## Retry and Backoff Findings

Confirmed:
- Retryable categories include 429, timeout, provider unavailable, network error, and unknown.
- Retry count is bounded by settings.
- v10.3 backoff held a global worker slot during sleep.
- v10.4 opens the circuit breaker, records retry delay, releases the slot, then waits before the next claim.

Remaining risk:
- The circuit breaker is still process-wide. One provider-wide 429 should reduce pressure, but a single transient error can slow unrelated jobs in the same process. Real benchmark data should decide whether to make this per-model or per-job.

## Stalled and Slow Job Detection

v10.4 classifies jobs as:
- healthy
- waiting_for_capacity
- rate_limited
- retrying
- provider_unavailable via failure category text
- stalled
- interrupted
- paused
- completed_with_warnings

User-facing messages include:
- Waiting for an available translation worker.
- Provider rate limit reached; retrying when the backoff window clears.
- A chapter is taking longer than normal; monitor provider timing.
- No active worker heartbeat recently; completed chapters are safe and remaining work can resume.

Safe actions remain:
- Pause.
- Resume.
- Retry Failed.
- Cancel.
- Recover Stalled Items is exposed as a recommended state label for future UI action wiring; existing lease recovery already prevents duplicate completed chapters.

## Controlled Real Benchmark Support

Added:
- Admin-only endpoint: `POST /api/admin/translation/benchmark/estimate`.
- Disabled by default unless `TRANSLATION_BENCHMARK_ENABLED=true`.
- Dry-run estimate only in this implementation.
- Sample limit: 5 chapters.
- Does not overwrite existing AI text.

Not done:
- No real benchmark execution was run.
- No OpenAI call was made.

Recommended first real test later:
- 5 untranslated chapters with similar lengths.
- Balanced mode.
- Reference enabled where available.
- Record total wall-clock time, time to first result, provider latency, active/peak workers, input/output tokens, cost, retries, 429s, and timeouts.

## Render Deployment Architecture Review

Current architecture:
- Scheduler runs inside the FastAPI web service process.
- Startup starts scheduler loops for queued/running jobs.
- Jobs survive restart because state is persisted in PostgreSQL.
- On restart, running jobs/items are marked interrupted and returned to queued/pending.

Risk:
- Multiple Uvicorn worker processes could each start a scheduler loop. PostgreSQL `SKIP LOCKED` protects item claims, but duplicate schedulers add load and complexity.
- Web services can sleep/restart depending on Render plan and settings.
- Long translation jobs are operationally safer in a worker process than inside a request-serving process.

### Option A: Keep Scheduler in the Web Service

Benefits:
- Lowest cost and simplest deployment.
- No new Render service.
- Current PostgreSQL claim model already protects duplicate item claims.

Limits:
- Web process restarts interrupt active provider waits.
- Uvicorn worker count must remain controlled.
- Translation load competes with web traffic.

Safeguards:
- Keep `TRANSLATION_MAX_CONCURRENCY` bounded.
- Keep one effective web worker unless scheduler duplication is explicitly designed.
- Keep lease recovery and restart recovery enabled.
- Use Admin diagnostics to detect stalls and rate limits.

### Option B: Dedicated Background Worker Service

How it works:
- Web service creates jobs and reads job state.
- Worker service claims pending items from PostgreSQL with `SKIP LOCKED`.
- Worker saves chapter-level results and item metrics.
- Web service observes jobs through normal database reads.
- Worker restarts recover via leases and `mark_interrupted_jobs`.

Cost:
- Requires another Render service or process.
- More environment management.

Reliability benefit:
- Translation work no longer competes with web requests.
- Worker can be sized independently.
- Scheduler duplication is easier to reason about.
- Long-running jobs are safer.

Recommendation:
- Stay with Option A for low volume while v10.4 collects real timing data.
- Move to Option B if real jobs are frequent, long, rate-limit heavy, or if the web service becomes sluggish during translation.

## Next Measurement Questions

- What is average provider wait per chapter in production?
- Does Reference increase provider wait materially?
- Are 429s or timeouts common?
- Does Balanced reach 3 active provider waits in real OpenAI calls?
- Is 4 workers materially better than 3 for the user's model/account/Render plan?
- Does Maximum Safe trigger more 429s than useful throughput?
