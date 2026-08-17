# Mortimer Interface Upgrade Plan

Status: **DRAFT — awaiting approval. No step in this document has been executed. No code may be written until Larry explicitly approves, in whole or by phase.**

Author's note: this plan is written to be executed by any model or engineer with no context beyond this file, `CLAUDE.md`, and the repository itself. Every file path is absolute or repo-relative and exact. Every claim about current behavior in this document was verified by reading the code at the time of writing — but **verify again before acting**, since the repo may have moved on.

---

## 0. Scope and guardrails (apply to every phase)

### What this plan covers
Six phases, in dependency order: a blocking foundation fix, then latency, then conversational realism, then memory, then context management. Phases are independently approvable and independently revertible.

### Non-negotiable constraints

1. **No existing feature may be disabled, degraded, or removed.** This includes: the voice pipeline, the web console and all its panels, wake word, the self-edit loop, app development, all 8 MCP servers, the CLI REPL, and the delegation model. If a phase appears to require removing something, stop and flag it — that is a plan defect, not something to work around.
2. **`config/agents.yaml` routing semantics must not change.** The Supervisor delegates; sub-agents own their MCP servers. No phase may give the Supervisor direct access to a delegated domain's tools.
3. **`jarvis/prompts.py` remains the single source of truth for all prompts.** No prompt text may be introduced anywhere else.
4. **Memory must never break the voice pipeline.** `jarvis/memory.py`'s existing contract — every public function degrades to a safe empty result on any failure, and never raises into the pipeline — is preserved in every change made to it.
5. **Every phase ends with the full verification block** in §0.4. A phase is not complete until all of it passes.
6. **No secrets in any file.** Use env vars and placeholders.
7. **Self-edit allowlist:** before modifying any file, check whether it appears in `config/self_edit_allowlist.json`. This plan is executed by a human-directed agent, not the self-edit loop, so the allowlist does not restrict it — but if a phase touches a file the self-edit loop can also write, note it in the phase's completion summary so the interaction is understood.

### 0.3 Baseline facts verified at time of writing

These were confirmed by direct inspection. An implementing model should re-verify rather than trust them blindly.

- `data/jarvis.db` exists but contains **zero tables**. `scripts/init_db.py` has never been run on this machine.
- `jarvis/memory.py` is called from exactly three places: `jarvis/agents/supervisor.py:95`, `jarvis/bot/pipeline.py:220`, and `jarvis/bot/pipeline.py:465`.
- `jarvis/db.py` applies migrations from a `MIGRATIONS: list[tuple[str, str]]` list; there are currently four (`0001_init`, `0002_actions`, `0003_memory`, `0004_observations`). Adding a migration means appending a tuple.
- The Supervisor LLM is constructed in `jarvis/bot/pipeline.py` as `OpenAILLMService(api_key=..., base_url=settings.openai_base_url, model=settings.openai_model)`. There is **no prompt caching anywhere in `jarvis/`**.
- Barge-in is enabled via `should_interrupt=True` on `DeepgramFluxSTTService` in `jarvis/bot/pipeline.py`. Nothing currently informs the LLM that its reply was interrupted.
- `jarvis/agents/delegate.py`'s `delegate_task` handler takes a single `agent_name` + `task` and awaits `agent.run(...)`. There is **no parallel delegation** — no `asyncio.gather` or `create_task` in `delegate.py` or `jarvis/agents/base.py`.
- There is **no within-session context compression** anywhere.
- `jarvis/bot/transcript_log.py` prints latency lines in the exact format `TURN user_end->first_audio = <int>ms`, parsed by `scripts/latency_probe.py` via `TURN_RE = re.compile(r"TURN user_end->first_audio = (\d+)ms")`.
- `tests/unit/test_memory.py` is 318 lines and mirrors `jarvis/memory.py`.
- `jarvis/admin/server.py` is a 248-line FastAPI app using `@app.get(...)` / `@app.post(...)`. Closest UI analogues for a new panel: `web/src/components/GitPanel.tsx` and `web/src/components/EditModePanel.tsx`.

### 0.4 Verification block — run at the end of every phase

```bash
cd /Users/larryfix/Documents/jarvis-voice-ai-clean
source .venv/bin/activate

# 1. Backend imports (CI gate 2)
python -c "import jarvis, jarvis.config, jarvis.cli"

# 2. Unit + integration tests, no external calls
pytest tests/unit tests/integration -q

# 3. Skill manifests still match their servers
python scripts/check_skills.py

# 4. Frontend still compiles (CI gate 4) — strict TS
cd web && npm run build && cd ..

# 5. The CLI still starts, loads all 8 MCP servers, and answers
python3 -m jarvis.cli
#    -> ask one question, confirm a sane answer, then /quit
```

Additionally, **only for phases that modify `jarvis/prompts.py`** (Phases 3 and 5c/5d):

```bash
RUN_LIVE=1 python -m tests.evals.routing_eval    # must score >= 90%
```

And **once Phase 2b exists**, for any phase that could alter sub-agent behavior (Phase 1 under Option B, Phase 4, Phase 6, and any future model change):

```bash
RUN_LIVE=1 python -m tests.evals.subagent_eval   # must meet the recorded per-agent thresholds
```

Any phase that fails any item in this block is not complete. Fix or roll back — do not proceed to the next phase.

---

## Phase 0 — Foundation: initialize the database, establish a baseline

**This phase is blocking. No other phase may begin until it is complete.**

> ### ✅ EXECUTED 2026-08-12 — results
>
> **0.1** Backup: `data/jarvis.db.bak-20260812-112106` (4 KB, no tables — nothing to lose).
>
> **0.2 / 0.3** `scripts/init_db.py` applied all four migrations (`0001_init`, `0002_actions`, `0003_memory`, `0004_observations`). All seven tables confirmed present: `actions, conversations, memories, migrations, notes, observations, reminders`. **Root cause of the empty DB: it had simply never been initialized on this machine** — not corruption, not a bug.
>
> **0.4** FTS5 confirmed available → **Phase 5a is viable as written.**
>
> **0.5 — LATENCY BASELINE (2026-08-12, model `claude-haiku-4-5`, 16 turns, single clean session):**
>
> | class | count | p50 | p90 | target |
> |---|---|---|---|---|
> | non-delegated | 10 | **1110 ms** | 1317 ms | p50 OK (≤1200 ms) |
> | delegated | 6 | **1543 ms** | 2074 ms | p50 OK (≤2500 ms) |
> | overall | 16 | **1208 ms** | 1807 ms | p90 OK (≤3500 ms) |
>
> All within existing targets. **This is the number Phase 1 (prompt caching) must beat and Phase 2's CI budget should be derived from.** Measured from `logs/bot.log` via `python scripts/latency_probe.py logs/bot.log`. Note that `mortimer.sh` writes to `logs/bot.log`, not a per-run baseline file.
>
> **Blocker hit and resolved:** `OPENAI_API_KEY` in `.env` held a stale Anthropic key, producing `401 authentication_error` on every turn. The voice path reads `OPENAI_API_KEY` (with `OPENAI_BASE_URL=https://api.anthropic.com/v1/`), **not** `ANTHROPIC_API_KEY` — that variable is only used by the `claude-opus` profile in `upgrade_models.yaml` for the self-edit planner. Mortimer and Hermes now share one Anthropic key; rotating it means updating both `.env` and `~/.hermes/.env`.
>
> **0.6 — FAILED on first attempt, and this uncovered a real bug (now fixed).**
>
> The session wrote 42 `conversations` rows but produced zero memories and zero observations, with **no log line of any kind**. Direct invocation of `update_memory_from_session` on the session id succeeded in 4.8s (3 facts, 3 observations) — proving the extraction path itself was healthy and the failure was in the trigger.
>
> **Root cause:** `on_client_disconnected` (`jarvis/bot/pipeline.py`) only set `client_connected["value"] = False`. It never ended the `PipelineTask`, so `await runner.run(task)` never returned and the `finally` block after it never executed. That block does two things: the session memory fold-in **and** `watcher.stop()`. Consequences were that every session's memory was deferred until process exit (and then only the last session's), and every connection leaked one `RemindersWatcher` polling task.
>
> **Fix applied:** `await task.cancel()` added to the disconnect handler. Safe because one `PipelineTask` is built per WebRTC connection — `jarvis/bot/bot.py` constructs a fresh transport and calls `run_session` per connection, so a reconnect gets a new pipeline rather than reattaching.
>
> **Regression test:** `tests/integration/test_bot_wiring.py::test_client_disconnect_ends_task_and_folds_memory`. Its fake runner blocks until the task ends, mirroring the real `PipelineRunner`, so removing the `cancel()` makes the test **hang and time out** rather than silently pass. Asserts all four cleanup effects: task cancelled, memory folded, watcher stopped, registry stopped.
>
> **Verification:** full §0.4 block passed — imports OK, **415 passed / 3 skipped**, 8 skills validated, `npm run build` clean.
>
> **End-to-end confirmation:** after the fix, a fresh session followed by a browser disconnect produced `memory_updated session=160895fe-513e-48dd-a80f-32102e8f46b7 facts=1 observations=2 promoted=[]` in `logs/bot.log` with no manual invocation. **Phase 0 complete; memory now folds in per session as designed.**
>
> **Note for Phase 5:** three silent failure paths remain in the memory write path — the unlogged early return when a session has no user rows (`memory.py`), and the bare `except Exception: pass` around the fold-in call (`pipeline.py:468`), which swallows both timeouts and errors. Consider addressing observability as part of 5c.

### Why
`data/jarvis.db` has no tables. That means memory extraction has silently failed after every session to date (the `memory_context_read_failed` error is caught and swallowed by design), and `mcp_notes` / `mcp_reminders` would fail on any write. Every later phase in this plan — especially Phase 5, which builds on the `conversations` and `memories` tables — depends on this being fixed. It also means **no memory data exists yet**, so any tuning of memory behavior is currently speculative.

### Steps

**0.1 — Back up the existing (empty) database.**
```bash
cd /Users/larryfix/Documents/jarvis-voice-ai-clean
cp data/jarvis.db data/jarvis.db.bak-$(date +%Y%m%d-%H%M%S)
```

**0.2 — Run migrations.**
```bash
source .venv/bin/activate
python scripts/init_db.py
```

**0.3 — Verify all five tables now exist.**
```bash
python3 -c "
import sqlite3
c = sqlite3.connect('data/jarvis.db')
tables = sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\"))
print(tables)
expected = {'migrations','notes','reminders','conversations','actions','memories','observations'}
missing = expected - set(tables)
print('MISSING:', missing if missing else 'none')
"
```
All of `migrations, notes, reminders, conversations, actions, memories, observations` must be present.

**0.4 — Confirm FTS5 is available** (required by Phase 5a; find out now, not mid-implementation).
```bash
python3 -c "import sqlite3; sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('FTS5 OK')"
```
If this fails, Phase 5a must be re-planned around an alternative (e.g. `LIKE`-based search or an external index). Record the result.

**0.5 — Establish a latency baseline.** Start the bot, hold a real conversation of at least 10 turns covering several intents (a time question, a note, a web search, a system status check, and at least one multi-part request such as *"check the weather in Paris and remind me to pack an umbrella tomorrow"*), then:
```bash
./scripts/run_bot.sh 2>&1 | tee logs/baseline-$(date +%Y%m%d).log
# after the conversation, in another shell:
python scripts/latency_probe.py logs/baseline-$(date +%Y%m%d).log
```
**Record the output in this file** under a new "Baseline measurements" heading, including date, model, and number of turns. Every later latency claim is measured against this number. Note separately how long the multi-part request took — that is the Phase 4 target.

**0.6 — Confirm memory now works end to end.** Have a short conversation stating a durable preference (e.g. *"I prefer short answers"*), end the session cleanly, then:
```bash
python3 -c "
import sqlite3
c = sqlite3.connect('data/jarvis.db'); c.row_factory = sqlite3.Row
for r in c.execute('SELECT kind, key, content FROM memories'):
    print(dict(r))
for r in c.execute('SELECT key, content FROM observations'):
    print('OBS', dict(r))
"
```
At least one row should exist. If nothing is written, **stop and diagnose before proceeding** — Phase 5 is meaningless until the existing memory path demonstrably works.

### Verification
Full §0.4 block, plus 0.3, 0.4, 0.5, and 0.6 above producing recorded results.

### Rollback
```bash
cp data/jarvis.db.bak-<timestamp> data/jarvis.db
```

### Recommended pause
After Phase 0, **use Mortimer normally for about a week before starting Phase 5 (memory).** The memory improvements in this plan were derived from reading another project's documentation, not from observing Mortimer's own failure modes. A week of real data will likely change which of 5a–5e matter most. Phases 1–4 do not depend on this and can proceed immediately.

---

## Phase 1 — Prompt caching (largest single latency lever)

### Why
The Supervisor's system prompt is large and stable across turns: identity, the specialist roster (`render_agent_catalog`), the voice catalog, memory context, `VOICE_ADDENDUM`, plus tool schemas for `delegate_task`, `set_voice`, and every exposed MCP tool. It is rebuilt identically on every turn and re-sent in full. Caching it reduces time-to-first-token on *every turn* — the metric that most determines whether the interface feels conversational.

### Precondition
Phase 0 complete, with a recorded baseline from 0.5.

### 1a — Investigate before implementing (do not skip)

Mortimer reaches Anthropic through the OpenAI-compatibility layer (`OPENAI_BASE_URL=https://api.anthropic.com/v1/`, `OPENAI_MODEL=claude-haiku-4-5`) using Pipecat's `OpenAILLMService`. **It is not established that this path can express `cache_control`.** Determine, in this order:

1. Read Pipecat's `OpenAILLMService` (in `.venv/lib/python3.12/site-packages/pipecat/services/openai/`) to find whether arbitrary per-message fields or extra body params survive to the wire.
2. Check whether Anthropic's OpenAI-compat endpoint honors caching, and by what mechanism, using current Anthropic documentation.
3. Check whether Pipecat ships a native Anthropic service (`pipecat.services.anthropic`) that supports caching directly, and what it would take to substitute it in `jarvis/bot/pipeline.py`.

**Write the findings into this document before writing any code.** The outcome determines which of the three options below is taken.

### 1b — Choose an implementation path

- **Option A — caching works through the existing compat path.** Add cache markers to the system message. Smallest change; touches only `jarvis/bot/pipeline.py`.
- **Option B — requires Pipecat's native Anthropic service.** Introduce a provider branch in `jarvis/bot/pipeline.py`: when `OPENAI_BASE_URL` points at Anthropic, construct the Anthropic service with caching; otherwise keep `OpenAILLMService` exactly as today. **The existing OpenAI-compatible path must keep working unchanged** — this is an added branch, not a replacement. Note `DEVIATIONS.md` D-003: Mortimer omits `temperature` by default; preserve that.
- **Option C — not achievable.** Record why, and close the phase without code. Do not force it.

Whichever option is taken, it must be selectable/disable-able via config so it can be turned off without a code change. Add a setting to `jarvis/config.py` (suggested: `JARVIS_PROMPT_CACHE_ENABLED`, default `true`) and document it in `README.md` §8's environment variable table.

### 1c — Measure
Repeat the exact 0.5 procedure and compare `latency_probe.py` output against the recorded baseline. **Record before/after numbers in this document.** If there is no measurable improvement, revert — complexity without benefit is not worth carrying.

### Files expected to change
`jarvis/bot/pipeline.py`, `jarvis/config.py`, `README.md`, possibly `.env.example`, plus a unit test asserting the cache setting is honored.

### Verification
Full §0.4 block. Prompts are not modified, so the routing eval is not required — but run it anyway if Option B changes the LLM service, since a different service could alter tool-calling behavior.

### Rollback
Set `JARVIS_PROMPT_CACHE_ENABLED=false`, or revert the commit. The pre-existing `OpenAILLMService` path must remain intact either way.

### Risk
Medium under Option B (swapping the LLM service is a change to the pipeline's core), low under Option A.

---

## Phase 2 — Latency regression gate in CI

### Why
Latency is the product for a voice interface, and it is currently unprotected: CI runs the allowlist check, an import smoke test, unit tests, and the frontend build — nothing checks latency. Adding this gate *before* the remaining feature phases means every later change is measured against it automatically.

### Precondition
Phase 0 complete (baseline recorded). Best done after Phase 1 so the budget reflects the improved number.

### Steps

**2a — Add a budget check to `scripts/latency_probe.py`.** Extend the existing script (do not write a new one) with an optional `--max-p95 <ms>` argument that exits non-zero when the p95 of parsed `TURN user_end->first_audio` values exceeds the budget. Preserve the current human-readable output and the existing `TURN_RE` format exactly — `jarvis/bot/transcript_log.py` emits that format and must not change.

**2b — Add a unit test** in `tests/unit/test_latency_probe.py` (this file already exists — extend it) covering: budget met, budget exceeded, and empty input. Empty input must **not** fail the budget (a log with no turns is not a latency regression).

**2c — Wire into CI** in `.github/workflows/validate.yml` as a new step. Because CI has no microphone and cannot hold a voice conversation, this gate can only run against a **committed sample log fixture**, not live traffic. Add `tests/fixtures/latency_sample.log` and have CI assert the probe parses it and enforces the budget correctly. This is a regression test for *the probe*, not for live latency.

**2d — Document the real measurement ritual** in `README.md`: after any change to the pipeline, run the 0.5 procedure manually and compare against the recorded baseline. Automated CI cannot do this; a documented human step is the honest solution.

### Files expected to change
`scripts/latency_probe.py`, `tests/unit/test_latency_probe.py`, `tests/fixtures/latency_sample.log` (new), `.github/workflows/validate.yml`, `README.md`.

### Verification
Full §0.4 block, plus: deliberately raise the fixture's numbers above the budget and confirm CI-equivalent command fails; restore and confirm it passes.

### Rollback
Remove the CI step. The probe's new flag is additive and harmless.

### Risk
Low. Nothing in the runtime path changes.

---

## Phase 2b — Sub-agent quality evals

*(Numbered 2b rather than renumbering later phases, so cross-references elsewhere in this document stay valid.)*

### Why
`tests/evals/routing_eval.py` measures whether the Supervisor picks the **right agent** (must stay ≥90%). Nothing measures whether the sub-agents then **do their jobs correctly**. There is no coverage asserting that Scheduler resolves "next Friday" to the right date, that Librarian retrieves the note you asked for, that Systems reports real numbers rather than fabricated ones, or that Analyst returns a grounded answer.

That gap makes several later phases unverifiable. Phase 1 Option B swaps the LLM service. Phase 4 changes how delegations execute. Phase 6 alters conversation context. Any of these could degrade sub-agent output with nothing catching it — and the degradation would surface as Mortimer quietly getting worse at real tasks, discovered through daily use rather than CI.

This phase has standalone value regardless of whether per-agent model selection is ever pursued.

### Precondition
Phase 0 complete. Librarian and Scheduler cases exercise `mcp_notes` and `mcp_reminders`, which require real tables.

### Steps

**2b.1 — Study the existing harness before designing anything.** Read `tests/evals/routing_eval.py` and `tests/evals/cases.yaml`. Match their conventions exactly: `RUN_LIVE=1` gating, YAML-defined cases, a scored threshold, invoked as `python -m tests.evals.<name>`. Do not invent a second eval style.

**2b.2 — Define per-agent case sets.** Each case supplies a task exactly as `delegate_task` would deliver it — **fully self-contained**, since sub-agents cannot see the Supervisor's conversation (`jarvis/agents/base.py` docstring). Minimum coverage per agent:

- **scheduler** — relative date resolution ("tomorrow at 9am", "in 3 days", "next Friday"), reminder creation with a correct `due_at`, listing and completing. Assert against the deterministic weekday rules documented in `mcp_servers/mcp_time/logic.py`: a bare or "this" weekday means the next occurrence *including today*; "next <weekday>" means that weekday in the *following* calendar week (weeks start Monday). These rules are the specification — encode them, don't re-derive them.
- **librarian** — store a fact, retrieve it by keyword, update it, confirm search finds the updated version.
- **analyst** — a web search returning a relevant, grounded answer; weather for a named city.
- **systems** — returns real numeric CPU/memory/disk values, not plausible-looking fabrications.
- **developer** — **read-only cases only**: git status and recent log read correctly. No commits, no pushes, no repo creation in an eval, ever.

**2b.3 — Two assertion layers.**
- *Deterministic (primary):* which tools were called, with which arguments. `SubAgent` already emits `agent_tool` and `agent_tool_result` events carrying `arguments` — capture them by passing an `on_event` collector into `agent.run(...)`. This layer is exact, cheap, and catches most regressions.
- *Semantic (secondary):* whether the returned string actually answers the task. Use loose keyword assertions or an LLM judge. Keep it deliberately loose — over-specified wording assertions produce brittle evals that fail on harmless phrasing changes and get ignored.

**2b.4 — Score and set thresholds from the first run, not aspirationally.** Report per-agent and overall scores. Run the eval once against current `main`, then **record the baseline numbers in this document** under Phase 2b. Thresholds are set at or just below observed baseline so the eval detects *regression*, not aspiration.

**2b.5 — Safety constraints (mandatory).**
- Point `JARVIS_DB_PATH` at a throwaway temp database for the duration of the run. `mcp_notes` and `mcp_reminders` write real rows; an eval must never pollute `data/jarvis.db` with test notes and reminders.
- Developer cases are read-only. Never exercise `mcp_apps` repo creation or any `mcp_git` write path.
- Gate behind `RUN_LIVE=1`, consistent with existing evals — this costs real LLM and Tavily tokens on every run.

**2b.6 — Document it.** Add the invocation to `CLAUDE.md`'s commands block beside the existing routing eval, and to `README.md` §6 (Testing).

### Files expected to change
`tests/evals/subagent_eval.py` (new), `tests/evals/subagent_cases.yaml` (new), `CLAUDE.md`, `README.md`.

### Verification
Full §0.4 block. Plus: the eval runs cleanly and produces recorded per-agent baselines. Plus explicit confirmation that `data/jarvis.db` was **not** modified by the run — check row counts in `notes` and `reminders` before and after.

### Rollback
Delete the two new files and revert the doc edits. Purely additive test infrastructure; nothing in the runtime path changes.

### Risk
Low — this phase adds tests, not behavior. The two real pitfalls are brittleness (over-specified assertions that fail on benign changes, causing the eval to be ignored) and cost (live LLM + search calls per run). Both are mitigated by 2b.3's loose semantic layer and `RUN_LIVE=1` gating.

---

## Phase 3 — Interruption awareness

> ### ✅ EXECUTED 2026-08-12 — results
>
> **3a — Interruption signal confirmed by reading pipecat source in `.venv/`:** `DeepgramFluxSTTService(should_interrupt=True)` calls `broadcast_interruption()` on every `StartOfTurn` event (`.venv/.../pipecat/services/deepgram/flux/base.py:593`), which emits `InterruptionFrame` (`SystemFrame`) both upstream and downstream via `broadcast_frame()`. **Important finding not anticipated by the plan:** this fires on *every* new user turn, including the ordinary case where the assistant already finished speaking — not only on genuine barge-in. A naive "note on every InterruptionFrame" implementation would have produced a false-positive note on every single turn, failing the plan's own negative test case. `BotStartedSpeakingFrame`/`BotStoppedSpeakingFrame` are confirmed emitted by the TTS service (`tts_service.py:1687/1689`), downstream of `TranscriptLogger`'s locked position — same D-007 constraint as `TranscriptObserver`, so this needed a task-level observer, not an inline processor.
>
> **3b/3c — Implementation:** new `jarvis/bot/interruption.py` (`InterruptionNotifier`, a `BaseObserver`) tracks assistant-turn-active state via `UserStoppedSpeakingFrame` / `LLMFullResponseEndFrame` / `BotStartedSpeakingFrame` / `BotStoppedSpeakingFrame`, and only treats an `InterruptionFrame` as genuine when the turn was still active at that moment — distinguishing it from the routine per-turn broadcast. mid-speech vs while-thinking distinguished by whether `BotStartedSpeakingFrame` had fired yet. Two short notice strings added to `jarvis/prompts.py` (`INTERRUPTION_NOTICE_MID_SPEECH`, `INTERRUPTION_NOTICE_WHILE_THINKING`). Injection uses a new `inject_silent` helper in `jarvis/bot/pipeline.py::run_session` that calls `aggregators.user().add_messages(...)` **without** `push_context_frame()` — unlike the existing greeting/reminder injection pattern, this deliberately avoids triggering an immediate unprompted spoken reply; the note simply becomes part of context for whenever the next real turn naturally fires.
>
> **3d — Flag added:** `jarvis_interruption_notice_enabled: bool = True` in `jarvis/config.py`, `JARVIS_INTERRUPTION_NOTICE_ENABLED` documented in `.env.example` and `README.md` §8.
>
> **Verification:** `tests/unit/test_interruption.py` (6 cases) — mandatory negative case (completed turn → no note) passes, plus mid-speech, while-thinking, disabled-flag, upstream-direction dedup, and no-double-count-within-one-turn. Full suite: 433 passed, 3 skipped (pre-existing sandbox network limitations, unrelated), 1 pre-existing failure deselected (`test_mcp_web_server`, sandbox has no network egress to Tavily — unrelated to this change). **`RUN_LIVE=1 python -m tests.evals.routing_eval` was NOT run** — this sandbox has no network access to the LLM API (`openai.PermissionDeniedError: Connection blocked by network allowlist`, confirmed when attempting live sub-agent evals earlier in this session). **Must be run from a machine with API access before merging**, since `prompts.py` changed. Manual acceptance checklist added at `tests/acceptance/upgrade-phase-3.md` (not yet run — requires a live voice session).
>
> **Files changed:** `jarvis/bot/interruption.py` (new), `jarvis/prompts.py`, `jarvis/config.py`, `jarvis/bot/pipeline.py`, `.env.example`, `README.md`, `tests/unit/test_interruption.py` (new), `tests/integration/test_bot_wiring.py` (fixture update for new settings field), `tests/acceptance/upgrade-phase-3.md` (new).

### Why
`should_interrupt=True` makes barge-in work mechanically — the assistant stops talking. But the model is never told its reply was cut off; it simply sees a truncated turn. The result is an assistant that gets interrupted and behaves as though nothing happened. Telling it explicitly lets it acknowledge, resume, or adapt, which is a large perceived-quality gain for a small change.

### Precondition
Phase 0 complete.

### Steps

**3a — Find the interruption signal.** Determine how Pipecat surfaces an interruption in this pipeline. Likely candidates: a frame type such as `StartInterruptionFrame` / `UserStartedSpeakingFrame` observable by a processor, or a callback on the transport or STT service. `jarvis/bot/transcript_log.py` is an existing custom `FrameProcessor` in this codebase and is the model to follow for observing frames. **Confirm the actual mechanism by reading Pipecat's source in `.venv/` before writing code.**

**3b — Record that the turn was interrupted**, and whether any assistant audio had already played (interrupted-while-thinking and interrupted-mid-speech are different situations and the note should distinguish them).

**3c — Surface it to the model.** On the next user turn, prepend a short system-role note to the context — for example: *"(Your previous spoken reply was interrupted by the user before it finished.)"* The exact wording must live in `jarvis/prompts.py`, per §0 constraint 3. Keep it short; it is prepended to real turns and costs tokens every time it fires.

**3d — Make it optional.** Add a config flag (suggested `JARVIS_INTERRUPTION_NOTICE_ENABLED`, default `true`) in `jarvis/config.py`, documented in `README.md` §8.

### Files expected to change
`jarvis/bot/pipeline.py` and/or a new small processor beside `jarvis/bot/transcript_log.py`, `jarvis/prompts.py`, `jarvis/config.py`, `README.md`, `.env.example`, plus unit tests.

### Verification
Full §0.4 block **including `RUN_LIVE=1 python -m tests.evals.routing_eval` (≥90%)**, since `prompts.py` changes.

Manual acceptance (add a checklist to `tests/acceptance/`): interrupt mid-sentence and confirm the next reply acknowledges it naturally; interrupt during thinking before audio plays and confirm behavior is sensible; complete a turn without interrupting and confirm **no** note appears (no false positives — this is the important negative case).

### Rollback
Set the flag to `false`, or revert.

### Risk
Low–medium. The risk is false positives — a note appearing when no interruption occurred would confuse the model on every turn. The negative test case above is mandatory.

---

## Phase 4 — Parallel delegation

> ### ✅ EXECUTED 2026-08-12 — results
>
> **4a — Answered by reading pipecat source, not assumed:** `pipecat/services/llm_service.py` (`LLMService.__init__`) defaults to `run_in_parallel: bool = True` and `group_parallel_tools: bool = True`. When the Supervisor emits multiple tool calls in one assistant turn, `run_function_calls()` (line 1301) already branches to `_run_parallel_function_calls()`, which creates one independent `asyncio.Task` per call (line 1331-1337) — no serial awaiting. Mortimer's `OpenAILLMService(...)` construction in `jarvis/bot/pipeline.py` does not override either default. **This means concurrent dispatch was already happening at the framework level before this phase started; nothing in `adapt_to_pipecat` or the prompt needed to change.**
>
> Checked whether the rest of the stack was actually *safe* for that concurrency (not assumed): `SubAgent._loop` (`jarvis/agents/base.py`) builds a fresh local `messages` list per call with no shared mutable per-instance state — two concurrent `.run()` calls on the same `SubAgent` instance don't race. `SkillRegistry.call()` uses one persistent `ClientSession` per MCP server, but the underlying `mcp` SDK's `BaseSession` (`mcp/shared/session.py`) keys in-flight requests by a unique JSON-RPC id with independent response streams — concurrent calls into the same server session are multiplexed safely, not just safe by accident of low collision probability.
>
> Checked the UI (not assumed): `AgentStatusPanel.tsx`'s `runs` state is a list keyed by per-delegation `id`, and `OrbField.tsx`'s `working`/`doneAt` state is a `Record<string, boolean>` keyed by agent name — both already support multiple simultaneously-`working` entries for *different* agent names with zero code changes. (Same-name concurrent delegation would have the newer card replace the older one in `AgentStatusPanel`, but Supervisor prompt rule 2 already limits the model to one `delegate_task` call per specialist per turn, so this case shouldn't arise in normal operation.)
>
> **4b/4c/4d — Implementation:** the only real gap was 4c (no cap existed anywhere). Added `jarvis_max_parallel_delegations: int = 3` to `jarvis/config.py`, `DEFAULT_MAX_PARALLEL_DELEGATIONS = 3` to `jarvis/agents/delegate.py`, and wrapped the actual `agent.run()` call in `build_delegate_tool`'s handler with `asyncio.Semaphore(max_parallel)`. `delegate_start` still fires immediately (unaffected by the semaphore) so the UI shows "working" the instant the call arrives even if execution is briefly queued behind the cap. 4d required no new code: `SubAgent.run()` already never raises (failures return `FAILED: ...` strings), and each handler invocation is an independent coroutine, so a failing sibling was already isolated — verified with a test, not assumed.
>
> **4e — Measure:** could not run a live multi-part voice session in this sandbox (no network egress to the LLM API — same constraint hit in Phase 3). Substituted a scripted timing proof: `tests/unit/test_delegate.py::TestParallelDelegation::test_two_independent_delegations_overlap_in_time` shows two 0.08s-delay fake delegations complete in <0.15s total (would be ~0.16s serial), and `test_max_parallel_caps_concurrent_execution` / `test_max_parallel_allows_bounded_concurrency` show `max_parallel=1` forces ~3x a single delay (strictly serial) while `max_parallel=2` produces bounded 2-wide batching — proving the semaphore is the actual bound, not just documentation. **Live before/after timing from a real multi-part request must still be recorded** — checklist item added at `tests/acceptance/upgrade-phase-4.md`.
>
> **Verification:** `tests/unit/test_delegate.py` — 13 passed (5 new `TestParallelDelegation` cases). Full suite: 438 passed, 3 skipped (pre-existing sandbox network limitations), 1 pre-existing failure deselected (`test_mcp_web_server`, unrelated). **`RUN_LIVE=1 python -m tests.evals.routing_eval` was NOT run** (no LLM API network access in this sandbox) — this phase did not change `jarvis/prompts.py`, so it's lower-priority than after Phase 3, but should still be run before merging as a general regression check. Manual acceptance checklist at `tests/acceptance/upgrade-phase-4.md` (not yet run — requires a live voice session with real specialists).
>
> **Files changed:** `jarvis/agents/delegate.py`, `jarvis/config.py`, `jarvis/bot/pipeline.py`, `.env.example`, `README.md`, `tests/unit/test_delegate.py`, `tests/integration/test_bot_wiring.py` (fixture/spy updates for the new `max_parallel` parameter), `tests/acceptance/upgrade-phase-4.md` (new). **No changes needed** to `web/src/components/AgentStatusPanel.tsx` or `OrbField.tsx` — both already handle concurrent distinct-agent delegation correctly, confirmed by reading the code rather than assumed per the plan's stated risk.

### Why
`delegate_task` handles one agent and one task per call, awaited to completion. A multi-part request like *"check the weather in Paris and remind me to pack an umbrella tomorrow"* — explicitly advertised in `README.md` §4 — currently runs two full sub-agent round trips serially, each an LLM call plus MCP calls. Independent delegations can run concurrently.

### Precondition
Phase 0 complete, with the multi-part timing from 0.5 recorded.

### Steps

**4a — Determine how concurrent tool calls arrive.** Establish whether the Supervisor model emits multiple `delegate_task` calls in one assistant turn, and how Pipecat's function-calling layer dispatches them (sequentially awaited, or concurrently). This determines whether the fix belongs in `jarvis/agents/delegate.py`, in the Pipecat adaptation layer (`adapt_to_pipecat` in `jarvis/bot/pipeline.py`), or in the prompt. **Do not write code before answering this.**

**4b — Implement concurrency at the right layer.** Preserve exactly:
- The existing `delegate_task` schema and its `(arguments dict) -> str` handler contract (`jarvis/bot/pipeline.py` depends on it via `adapt_to_pipecat`).
- The `delegate_start` / `delegate_done` event pairs — `web/src/components/AgentStatusPanel.tsx` and the orb satellites consume these to animate. Concurrent delegations mean **overlapping** event pairs; verify the UI handles two agents lit simultaneously, and fix the UI if it does not. This is a real risk: the satellite animation may assume one active agent.
- Sub-agent isolation: each `SubAgent` only reaches the MCP servers listed for it in `config/agents.yaml`.

**4c — Bound it.** Add a maximum concurrent delegation count (suggested config `JARVIS_MAX_PARALLEL_DELEGATIONS`, default 3) so a pathological request cannot spawn unbounded concurrent LLM calls. Document in `README.md` §8.

**4d — Preserve failure semantics.** Today a failed sub-agent returns a string starting with `FAILED:`. With concurrency, one failure must not cancel siblings; each result is returned independently, and the Supervisor decides what to say.

**4e — Measure.** Re-run the multi-part request from 0.5 and compare against the recorded serial timing. Record before/after.

### Files expected to change
`jarvis/agents/delegate.py`, possibly `jarvis/bot/pipeline.py`, `jarvis/config.py`, `README.md`, `.env.example`, `web/src/components/AgentStatusPanel.tsx` (only if it cannot handle concurrent agents), plus unit tests in `tests/unit/test_delegate.py` covering: two independent delegations run concurrently, one fails and the other still returns, and the concurrency cap is respected.

### Verification
Full §0.4 block. Plus a manual acceptance check in the web console confirming two satellites animate simultaneously and both resolve correctly.

### Rollback
Set `JARVIS_MAX_PARALLEL_DELEGATIONS=1` to restore serial behavior without a code change. Build it so this is true.

### Risk
Medium. Concurrency bugs are subtle, and the UI event contract is a real dependency. The cap-to-1 rollback path is what makes this safe.

---

## Phase 5 — Memory upgrades

**Recommended: begin only after ~1 week of real usage following Phase 0**, so these are tuned against observed behavior rather than inferred needs. Sub-phases are independently approvable. 5a and 5b are the highest value; 5d is the lowest and may be dropped entirely.

### Precondition
Phase 0 complete **and** 0.6 confirmed memory actually writes rows. FTS5 confirmed available (0.4) for 5a.

### 5a — Session search (FTS5 second memory tier)

> #### ✅ EXECUTED 2026-08-12 — results
>
> **Server decision (step 3):** new tool inside `mcp_notes`, not a new `mcp_memory` server. Rationale: the Librarian already owns `mcp-notes` in `config/agents.yaml` (no routing config change needed), and spinning up a ninth subprocess for a single tool has real cost (one more stdio child, one more entry in `config/mcp_servers.yaml`) against no benefit — the tool consumer's mental model is "recall anything," regardless of which table backs it. Trade-off recorded: `mcp-notes` is now a slight misnomer (it touches `conversations` as well as `notes`); revisit if the tool surface under it grows enough to justify a split.
>
> **Migration 0005** (`jarvis/db.py`): FTS5 external-content table (`content='conversations', content_rowid='id'`) with three sync triggers (AFTER INSERT/UPDATE/DELETE) plus a one-time backfill `INSERT` of existing rows. Confirmed via a dedicated test (`test_deleted_conversation_row_removed_from_index`) that the delete trigger actually keeps the index in sync, not just insertion — the plan's own stated gotcha.
>
> **`search_sessions(query, limit=10)`** in `mcp_servers/mcp_notes/logic.py`: ranked via FTS5 `bm25()`, snippets via `snippet()` (12 words of context), results capped at `MAX_SEARCH_RESULTS=20`. Each query token is quoted individually before being ANDed into the `MATCH` expression — this was necessary, not defensive theater: an unquoted query containing FTS5 operator syntax (`-`, `*`, unbalanced `"`, or the literal words `AND`/`OR`/`NOT`) raises `sqlite3.OperationalError` on `MATCH`, which a real user's spoken-then-transcribed query could easily contain. Verified with a dedicated test.
>
> **Prompt decision:** `jarvis/prompts.py`'s Librarian sub-agent prompt was deliberately left unchanged (it still only names `search_notes` explicitly). Touching `prompts.py` would require `RUN_LIVE=1 python -m tests.evals.routing_eval`, which needs LLM API network access this sandbox does not have (same constraint hit in Phases 3 and 4). The tool's own description is written to be self-explanatory enough for the model to reach for it unprompted; whether that holds in practice is now a manual acceptance item (`tests/acceptance/upgrade-phase-5a.md`) rather than an assumption.
>
> **Verification:** `tests/unit/test_mcp_notes_logic.py::TestSearchSessions` — 10 new cases (match, no-match, empty query, limit, limit cap, multi-word AND semantics, special-character safety, snippet/metadata shape, case-insensitivity, delete-sync). `tests/integration/test_mcp_notes_search_sessions_over_stdio` — real stdio round trip. `scripts/check_skills.py` passes (8 skills). Fixed three pre-existing locked-value tests that (correctly) broke on the new migration/tool count: `tests/unit/test_db.py` (migration id list), `tests/integration/test_registry.py` (`TOTAL_TOOLS` 38→39, `tools_for(["mcp-notes"])` set). Full suite: 449 passed, 3 skipped (sandbox network), 1 pre-existing failure deselected (unrelated). Routing eval not run (see above — must be run before merging if the prompt-decision gap turns out to matter in practice).
>
> **Files changed:** `jarvis/db.py` (migration 0005), `mcp_servers/mcp_notes/logic.py`, `mcp_servers/mcp_notes/server.py`, `mcp_servers/mcp_notes/skill.yaml`, `tests/unit/test_mcp_notes_logic.py`, `tests/unit/test_db.py`, `tests/integration/test_mcp_servers.py`, `tests/integration/test_registry.py`, `tests/acceptance/upgrade-phase-5a.md` (new). **No change** to `config/mcp_servers.yaml` or `config/agents.yaml` (Librarian already has the `mcp-notes` grant).

**Why:** `jarvis/memory.py` caps at 30 facts / 1600 context chars and silently drops the rest. Anything older is unreachable — even though the full transcript sits in the `conversations` table. There is currently no way to answer "what did we discuss last month?"

**Steps:**
1. Add `MIGRATION_0005` to `jarvis/db.py` creating an FTS5 virtual table over `conversations` (external-content is preferable: `content='conversations', content_rowid='id'`), plus triggers on INSERT/UPDATE/DELETE to keep it synchronized, plus a one-time backfill of existing rows. Append `("0005_conversation_search", MIGRATION_0005)` to `MIGRATIONS`. **Never edit an existing migration** — the runner tracks applied ids and editing one silently skips it on machines that already ran it.
2. Add a search function returning ranked snippets with session id and timestamp. Cap result count and per-result length.
3. Expose it to the Supervisor as a tool. Per §0 constraint 2, this must go through the delegation model — the natural owner is the **Librarian** (which already owns `mcp_notes`). Follow the existing convention exactly: `logic.py` (pure, testable) + `server.py` (FastMCP over stdio), registered in `config/mcp_servers.yaml`, assigned in `config/agents.yaml`, with a `skill.yaml` manifest that satisfies `python scripts/check_skills.py`. Decide explicitly whether this becomes a new `mcp_memory` server or a new tool inside `mcp_notes`; record the decision and its rationale.
4. Tests: unit tests for the search function (`tests/unit/`), and an MCP-over-stdio integration test (`tests/integration/`) matching existing patterns.

**Verification:** full §0.4 block. `check_skills.py` must pass — it will fail if the manifest and server disagree. Manually confirm the Librarian can recall something from an old session.

**Rollback:** remove the server from `config/mcp_servers.yaml` and `config/agents.yaml`. The migration is additive and can be left in place harmlessly.

**Risk:** low. Additive schema, no change to existing read paths. Main gotcha: FTS5 triggers must stay in sync — test deletion and update, not just insertion.

### 5b — Injection and exfiltration scanning on memory writes

> #### ✅ EXECUTED 2026-08-12 — results
>
> **Pattern decision (step 4):** hand-rolled, not a maintained library — recorded rationale: zero new dependencies, and a maintained scanner package is itself an attack surface / supply-chain dependency to keep current. Traded comprehensiveness for that; noted as a spot to revisit if false negatives show up in practice. `hermes-agent` was not used, per the plan's explicit instruction.
>
> **`scan_memory_content(text) -> str | None`** added to `jarvis/memory.py`: three pattern families — phrasing-based prompt-injection regexes (e.g. "ignore previous instructions", "reveal your system prompt" — multi-word phrases, not single trigger words, specifically to avoid flagging ordinary text that happens to contain "system" or "ignore"), credential/exfiltration regexes (API-key-shaped literals for OpenAI/Anthropic/AWS/GitHub formats, private-key headers, "send this to https://", credentials embedded in URL query strings), and a curated set of zero-width/bidi-override Unicode code points (a known technique for hiding injected text from a human reviewer while an LLM still processes it).
>
> **Wired into all three write paths** (`upsert_fact`, `add_observation`, `set_summary`) — each now scans key+value (or summary text) before writing, logs `memory_write_rejected` with the key and reason on rejection, and returns without writing. `set_summary` specifically leaves the *previous* summary in place rather than overwriting it with unsafe content.
>
> **Verification:** `tests/unit/test_memory.py` — 42 new cases across three classes: `TestScanMemoryContentKnownBad` (15 — all pattern families, plus a totality check that the function never raises on empty/huge/binary input), `TestScanMemoryContentFalsePositiveGuard` (10 — ordinary facts/summaries/observations, including ones that contain trigger words like "system" or "ignore" in ordinary context, all correctly pass), `TestScanWiredIntoWritePaths` (6 — rejection logged and write skipped for all three functions, ordinary content still writes normally, rejection never raises). Weighted toward the false-positive guard per the plan's own risk note. Full suite: 481 passed, 3 skipped (sandbox network), 1 pre-existing failure deselected (unrelated). `prompts.py` not touched — no routing eval required, matching the plan's own verification note.
>
> **Files changed:** `jarvis/memory.py`, `tests/unit/test_memory.py`. No schema, config, or prompt changes.

**Why:** `render_memory_context` output is injected directly into the Supervisor's system prompt. Content flows there from the extraction LLM, which reads session transcripts — which can contain content from `mcp_web` results or anything the user read aloud. Nothing currently screens it. This is a real path from untrusted content into the system prompt.

**Steps:**
1. Add a scanning function to `jarvis/memory.py` (or a small sibling module) checking for prompt-injection patterns, credential/exfiltration patterns, and invisible/bidirectional Unicode.
2. Call it in `upsert_fact`, `add_observation`, and `set_summary` — every write path without exception.
3. **Rejections must be logged, never silent.** Use the existing `logger` with a distinct event name (e.g. `memory_write_rejected`) including the key and reason. A silently-dropped legitimate memory is a worse failure than a logged one.
4. Decide hand-rolled patterns vs. a maintained library and record the rationale. Hand-rolled keeps dependencies at zero; a library outsources an adversarial, evolving pattern list. Either is defensible — **do not add a dependency on `hermes-agent` for this**; its module paths are unstable across releases.
5. Tests in `tests/unit/test_memory.py`: known-bad content rejected, ordinary content accepted (false-positive guard — the more important case), invisible Unicode rejected, and rejection never raising into the caller.

**Verification:** full §0.4 block. `prompts.py` is not modified, so no eval run required.

**Rollback:** revert. No schema change.

**Risk:** low–medium. The risk is over-blocking. Weight tests toward false positives.

### 5c — Capacity handling (stop silent truncation)

> #### ✅ EXECUTED 2026-08-12 — results
>
> **Policy chosen (step 2): prioritization**, the plan's second-preference option, chosen specifically because it requires no `EXTRACTION_PROMPT` change and therefore no routing eval (unavailable in this sandbox — same constraint hit repeatedly this session). Consolidation was ruled out on that basis, not on merit. Surfacing (usage visibility) is layered on top via the Phase 5e memory panel, done separately.
>
> **Implementation:** `render_memory_context`'s fact query now orders `ORDER BY (CASE WHEN key LIKE 'user.%' THEN 0 ELSE 1 END), updated_at DESC` instead of pure `ORDER BY updated_at DESC` — `user.*` facts (explicit user statements: name, preferences, standing instructions) sort ahead of every other fact type as a block, most-recent-first within each tier. A `user.*` fact now survives the `MAX_FACTS` cap even when it's the single oldest row in the table, verified directly with a test that seeds an old `user.name` fact and then floods 35 newer non-user facts past it.
>
> **Both truncation points now log**, not just the char-budget break the plan's Why section called out: the `MAX_FACTS` SQL-level cap (previously silent) and the char-budget loop break (`memory_context_facts_dropped`, with count and up to 10 dropped keys per event — capped to keep the log line bounded even with a large drop), plus a new `memory_context_summary_dropped` event when no budget remains for the running summary (this drop point existed before but had no log line at all).
>
> **Verification:** `tests/unit/test_memory.py::TestCapacityHandling` — 6 new cases: `MAX_FACTS` overflow drops the correct count and logs it, a `user.*` fact survives the cap despite being oldest, `user.*` facts sort ahead of non-user facts generally (not just in the overflow case), char-budget overflow logs the remainder, no log fires when everything fits (negative case), and summary-drop logs when the budget is genuinely exhausted (used `monkeypatch` on `MAX_CONTEXT_CHARS` for a deterministic zero-remaining-budget case rather than relying on fact-length arithmetic to land exactly right). Full suite: 487 passed, 3 skipped (sandbox network), 1 pre-existing failure deselected (unrelated). `prompts.py` not touched — no routing eval required.
>
> **Files changed:** `jarvis/memory.py`, `tests/unit/test_memory.py`. No schema or config changes.

**Why:** `render_memory_context` breaks out of its loop when it exceeds `MAX_CONTEXT_CHARS`, silently dropping facts ordered by recency. Nobody is informed. Silent data loss is the worst failure mode of the five identified.

**Steps:**
1. Log whenever facts are dropped at render time, including how many and which keys.
2. Choose and implement a policy — options, in rough order of preference:
   - Consolidation: when `update_memory_from_session` detects the fact store is near budget, ask the LLM to merge overlapping facts in the same pass. (Changes `EXTRACTION_PROMPT` → requires the eval run.)
   - Prioritization: preserve `user.*` keys ahead of others rather than pure recency. (No prompt change.)
   - Surfacing: expose usage in the memory panel from 5e.
3. Record the chosen policy and why.
4. Tests covering the over-budget path explicitly.

**Verification:** full §0.4 block, **plus the routing eval if `EXTRACTION_PROMPT` is modified.**

**Rollback:** revert.

**Risk:** low.

### 5d — Two-store split (user profile vs. environment notes) — OPTIONAL, LOWEST VALUE

**Why:** separating "who the user is" from "facts about the environment/project" is organizationally cleaner and lets each have its own budget. It is the least valuable of the five and carries the most schema risk.

**Steps:** requires a migration touching the existing `idx_memories_fact_key` unique index (currently `ON memories(key) WHERE kind = 'fact'`), a backfill classifying existing rows, `EXTRACTION_PROMPT` changes to emit two buckets, and `render_memory_context` changes to render two labeled blocks with separate budgets.

**Verification:** full §0.4 block **plus the routing eval** (prompt changes). Additionally verify the migration is idempotent and that existing facts survive the backfill with correct classification.

**Risk:** medium — the only sub-phase touching an existing unique index with a data backfill. **Recommendation: defer indefinitely unless a week of real usage shows the flat namespace is actually causing problems.**

### 5e — Visibility and correction surface

> #### ✅ EXECUTED 2026-08-12 — results
>
> **Backend:** `GET /api/memory` and `DELETE /api/memory/fact/{key}` added to `jarvis/admin/server.py`, both thin pass-throughs — no memory logic duplicated in the sidecar, per the plan's explicit instruction. `PATCH` (optional per the plan) was skipped to control scope; delete-then-let-the-user-restate covers the correction need without an edit UI. Four new read helpers added to `jarvis/memory.py` (`list_facts`, `get_summary_text`, `list_observation_groups`, `memory_usage`) — deliberately separate from `render_memory_context`'s capped/prioritized read path, since the panel's job is showing *everything* so the user can actually audit it, not showing what fits in the Supervisor's context budget. `list_observation_groups` mirrors `promote_observations`' own grouping query exactly, so the panel's "N/PROMOTE_AFTER sessions" readout can never drift out of sync with what actually triggers promotion.
>
> **Frontend:** `web/src/components/MemoryPanel.tsx` (new, modeled on `GitPanel.tsx`'s polling/unreachable-state pattern) + `web/src/memory.css` (new, following `editmode.css`'s dark-panel-container convention with a `memory-` class prefix, imported into `App.tsx` alongside the other panel stylesheets). Wired into `App.tsx` with a `🧠 Memory` toggle button, following the exact `gitOpen`/`editOpen` state pattern already established for the other two panels.
>
> **Capacity display (step 3):** the usage readout renders `N / MAX_FACTS facts` and, when over capacity, an explicit note that `user.*` facts are prioritized and older non-user facts are dropped first — directly surfacing the Phase 5c policy decision rather than just a raw number.
>
> **Sandbox environment note (unrelated to this change, but hit during verification):** the sandbox's `web/node_modules` was missing native `arm64-gnu` bindings for both `rolldown` (vite's bundler) and `oxlint`, causing `npm run build` and `npm run lint` to fail with "Cannot find native binding" before any of this phase's code ran. Root-caused via the error's own suggested fix — `npm install` (no lockfile/node_modules removal needed) — after which both `tsc -b` (strict TypeScript, 0 errors) and a full `vite build` (179 modules, clean bundle) succeeded, and `oxlint` reported 0 errors. This was a pre-existing sandbox setup gap, not something introduced by this session's changes — worth confirming resolved (or already fine) on the actual dev machine, but not a code regression.
>
> **Verification:** `tests/unit/test_admin_api.py::TestMemoryEndpoints` — 6 new cases (empty overview shape, facts+summary listing, observation promotion-progress shape and values, delete removes a fact, delete-not-found returns `ok: false`, and an explicit check that the memory endpoints work with zero git state — the shared-`App.tsx` risk the plan called out is a frontend concern, but this confirms the backend routes have no hidden git dependency). Full backend suite: 493 passed, 3 skipped (sandbox network), 1 pre-existing failure deselected (unrelated). Frontend: `npm run build` and `npm run lint` both clean, confirmed after the sandbox binding fix above. Manual acceptance checklist at `tests/acceptance/upgrade-phase-5e.md` (not yet run — requires opening the actual web console; includes the mandatory shared-panel regression check for Git and Edit panels).
>
> **Files changed:** `jarvis/memory.py` (4 new read helpers), `jarvis/admin/server.py` (2 new routes + docstring update), `web/src/components/MemoryPanel.tsx` (new), `web/src/memory.css` (new), `web/src/App.tsx`, `web/.gitignore` (added `dist_build`, a sandbox-only build-verification artifact this session's `npm run build` runs produced — harmless but not meant to be tracked), `tests/unit/test_admin_api.py`, `tests/acceptance/upgrade-phase-5e.md` (new).
>
> **Phase 5 (all four selected sub-phases) is now complete.** 5d was explicitly not selected, matching the plan's own recommendation to defer it indefinitely absent evidence the flat fact namespace is actually causing problems.

**Why:** there is currently no way to see or correct what Mortimer has learned. The only correction path is `delete_fact` via a spoken "forget that," which requires already knowing the bad fact exists. Given commit `14f6163` ("Stop capability lies from regenerating in memory"), this is an operational gap with precedent.

**Steps:**
1. Backend: add routes to `jarvis/admin/server.py` following its existing style — `GET /api/memory` (facts, observations with promotion counts, summary, usage), `DELETE /api/memory/fact/{key}`, and optionally `PATCH` to edit. Reuse `jarvis/memory.py`'s existing functions (`delete_fact` already exists); do not duplicate logic in the sidecar.
2. Frontend: add `web/src/components/MemoryPanel.tsx` modeled on `GitPanel.tsx` (the closest analogue at ~4.9KB), wired into `App.tsx` with a toggle consistent with the existing ✎ Edit and Git panels. Styling belongs in the existing CSS files, following `editmode.css` conventions.
3. Show capacity usage (pairs with 5c) so it is visible when memory is near budget.
4. Tests: backend routes in `tests/unit/test_admin_api.py` (this file exists — extend it). The frontend is covered by the strict-TS build gate.

**Verification:** full §0.4 block — note item 4 (`npm run build`) is the real gate here. Manually confirm the panel lists memories, deletion works and persists, and **the existing Git and Edit panels still function** (this phase touches `App.tsx`, which they share).

**Rollback:** remove the panel and routes. Purely additive.

**Risk:** low functionally; the main risk is a TS build failure blocking CI, caught immediately by the verification block.

---

## Phase 6 — Within-session context compression

> ### ✅ EXECUTED 2026-08-12 — 6a measured, phase CLOSED WITHOUT CODE
>
> **Data source:** this sandbox cannot hold a live voice session (no network egress to the LLM API, no audio) — the same constraint hit in Phases 3, 4, and 5a. Rather than fabricate synthetic data, `data/jarvis.db` was checked for real usage history first: it contained genuine conversation transcripts from live sessions Larry held with the running Mortimer stack during earlier phases of this work (Phase 0.5's baseline conversation and subsequent testing). Two sessions had enough turns to be useful — 39 messages (17 user turns) and 22 messages (9 user turns) — both real spoken exchanges, not scripted. Neither individually reaches the plan's suggested "30+ turn conversation," but two independently-consistent real samples were judged sufficient given how large the margin turned out to be (see below); a fresh dedicated long session remains available as a confirmation step if desired.
>
> **Instrumentation:** `scripts/context_growth_probe.py` (new) reconstructs cumulative context size turn-by-turn for a given session, using a representative rendered system prompt (`SUPERVISOR_PROMPT` + `VOICE_ADDENDUM` + placeholder catalogs) as the baseline. Token counting was meant to use `tiktoken`'s `cl100k_base` encoding, but this sandbox also has no network egress to fetch tiktoken's encoding file (`openaipublic.blob.core.windows.net` — same proxy-blocked pattern as every other network call this session) — the script falls back to a `~4 chars/token` approximation, clearly labeled in its own output, when tiktoken's download fails. This is a trend estimate, not an exact Anthropic token count; adequate for 6a's actual question (is growth a *problem*, not exactly how many tokens).
>
> **Measured results:**
>
> | session | messages | system baseline | final context | growth | rate |
> |---|---|---|---|---|---|
> | A (real, 17 user turns) | 39 | 978 tok | 1839 tok | 861 tok | 22.1 tok/msg |
> | B (real, 9 user turns) | 22 | 978 tok | 1317 tok | 339 tok | 15.4 tok/msg |
>
> Extrapolating session A's rate (the higher of the two, so this is a conservative/pessimistic projection): a 100-message session (~50 user turns — long for a voice interface) would reach ~3,186 tokens; a 300-message session (~150 user turns, multiple hours of continuous conversation) would reach ~7,601 tokens. Both are trivial against Claude Haiku/Sonnet's 200K-token context window — nowhere close to exhaustion — and small enough in absolute terms that the extra tokens resent each turn are very unlikely to be a meaningful fraction of the round-trip latency already measured in Phase 0 (1100–2500ms, dominated by STT/LLM/TTS pipeline stages, not context size at these scales).
>
> **Decision: close Phase 6 without code**, per the plan's own explicitly permitted outcome in step 6a ("If growth is not actually a problem at realistic session lengths, close this phase without code and record that finding"). Building compression here would add the plan's own flagged **highest risk** in this entire document (bugs that manifest as the assistant forgetting or contradicting itself mid-conversation) to solve a problem the real data shows does not exist at any realistic session length. 6b–6e were not started.
>
> **Confidence caveats, stated plainly:** (1) char-approximation instead of a real tokenizer — directionally reliable but not exact; (2) two real sessions rather than one dedicated 30+ turn session as the plan suggested — mitigated by both samples independently landing in the same order of magnitude (15–22 tok/msg), and by the conclusion's margin being large enough that even a 3–5x underestimate wouldn't change it (300 msgs would need a >25x higher rate than measured to threaten even a small model's context window). If Larry wants stronger certainty before considering this permanently closed, holding one fresh 30+ turn session and re-running `python scripts/context_growth_probe.py --list` / `python scripts/context_growth_probe.py <session_id>` on a machine with tiktoken network access would firm up the numbers — but is not expected to change the conclusion.
>
> **Verification:** `tests/unit/test_context_growth_probe.py` — 6 new cases (system prompt renders, cumulative growth is monotonic, system-prompt baseline is included, unknown session returns empty, session listing orders by turn count, table rendering). Full suite: 499 passed, 3 skipped (sandbox network), 1 pre-existing failure deselected (unrelated). No routing eval needed — `prompts.py` was not modified (the probe only *reads* the existing prompt templates to build a representative baseline).
>
> **Files changed:** `scripts/context_growth_probe.py` (new), `tests/unit/test_context_growth_probe.py` (new). No runtime code touched — this phase, as designed, either closes here or doesn't; it closed here.
>
> **This closes the plan's approved scope.** Phases 0, 1 (closed not-achievable), 2, 2b, 3, 4, 5a/5b/5c/5e, and 6a are all executed and recorded above.

### Why
Nothing compresses context within a session. Memory handles across-session continuity, but a single long voice conversation grows unbounded — latency and cost rise with it, and eventually the context window is exhausted. This degrades exactly when a session is going well.

### Precondition
Phases 0–2 complete (baseline and latency gate in place, since this phase directly affects latency).

### Steps

**6a — Measure first.** Determine actual context growth across a long session before designing anything: instrument token counts per turn, hold a 30+ turn conversation, and record the curve. If growth is not actually a problem at realistic session lengths, **close this phase without code** and record that finding.

**6b — If warranted, design deliberately.** Key decisions, each recorded with rationale: what triggers compression (token threshold vs. turn count); what is preserved verbatim (recent turns) vs. summarized (older ones); whether the system prompt is exempt (it must be — compressing it would break the Phase 1 cache and the tool schemas); and how compression interacts with `update_memory_from_session`, which reads `conversations` at session end and must still see what it needs.

**6c — Constraint:** compression must never drop tool-call/tool-result pairs in a way that leaves the context malformed. Provider APIs reject orphaned tool results.

**6d — Prompt text**, if any, lives in `jarvis/prompts.py`.

**6e — Make it optional** via config (suggested `JARVIS_CONTEXT_COMPRESSION_ENABLED`, default off until proven), documented in `README.md` §8.

### Verification
Full §0.4 block, **plus the routing eval if prompts change**, plus a long-session manual acceptance test confirming the assistant still remembers early-session details after compression fires, and that memory extraction at session end still works correctly.

### Rollback
Disable via config.

### Risk
**Highest in this plan.** Compression touches the live conversation context — bugs manifest as the assistant forgetting or contradicting itself mid-conversation, which is worse than the problem being solved. The measure-first step exists specifically so this may not need to be built at all.

---

## Explicitly out of scope

- **Any runtime dependency on `hermes-agent` inside the voice path.** Investigated and rejected: its memory is emergent behavior of its own agent loop, not a callable service, and consuming it would require routing Mortimer's conversations through Hermes — a harness swap. Separately, five reported-state-vs-runtime mismatches were observed in that build during testing. The existing standalone `--no-agent` Hermes cron job (see `HERMES_INTEGRATION_PLAN.md`) is unaffected by this exclusion and continues to run independently.
- **External memory providers** (Honcho, Mem0, etc.) — dependency surface without corresponding benefit at single-user scale.
- **Replacing Mortimer's inference discipline.** The 3-session promotion threshold (`PROMOTE_AFTER`) and explicit-beats-inferred rule in `jarvis/memory.py` are deliberate, more conservative than the alternatives reviewed, and are **preserved unchanged** by every phase in this plan.

---

## Approval checklist

Nothing in this document may be implemented until each item below is answered.

1. **Phase 0** — approve? (Strongly recommended; everything else depends on it.)
2. **Phase 2b (sub-agent quality evals)** — approve? Recommended early, since it protects Phases 1, 4, and 6 from silent quality regressions that nothing currently detects.
3. **Phases 1–4** — approve all, some, or none? Any ordering preference?
4. **Phase 5** — approve now, or after the recommended week of real usage? Which sub-phases (5a/5b/5c/5d/5e)? Recommendation: 5a + 5b + 5c, defer 5d, 5e when the UI is wanted.
5. **Phase 6** — approve the measure-first step (6a) only, with 6b+ requiring separate approval once data exists?
6. **Approval granularity going forward** — approve each phase individually before it starts, or approve a batch and let it run to completion?

No code will be written until these are answered.
