# Mortimer — Reliable Automatic Memory + Procedures-as-Hints

**Status:** Part A (D1–D8) and Part B (D9–D24) both APPROVED 2026-08-13 by
Larry and IMPLEMENTED.
**Scope decided by:** Larry, 2026-08-12 (two-question scoping round: both
issues in one plan — §2).
**Depends on:** `MORTIMER_RUN_LOGGING_PLAN.md` (shipped) — Part B of this
plan reads sub-agent run outcomes from `jarvis/runlog`, which did not exist
before that work.

---

## §0 Constraints for the implementing model

1. Every design decision is already made. They are in §3, lettered D1–D24
   (Part A: D1–D8; Part B: D9–D24), each with rationale. If a choice seems
   open, re-read §3.
2. **Memory and procedures are advisory context only.** Neither part of
   this plan may cause the Supervisor or a sub-agent to skip its own
   reasoning or bypass an existing confirmation gate. A procedure is a
   *hint in a prompt*, never a substitute for calling the real tool.
3. **A failure anywhere in this plan must never break the voice pipeline
   or a delegation.** Every new write path is best-effort, wrapped, logged
   once, and degrades to doing nothing. This mirrors `jarvis/memory.py`'s
   existing contract and the run-logging plan's D6 — do not weaken it.
4. **Naming: never use the word "skill" for the new procedures concept.**
   `mcp_servers/*/skill.yaml`, `jarvis/skills/registry.py`, and
   `scripts/check_skills.py` already use "skill" to mean "an MCP server."
   This plan's new concept is called a **procedure** throughout — table
   names, module names, prompts, everything.
5. Additive schema only — new migration appended to `MIGRATIONS`, never
   edit an already-applied one.
6. After implementation, `RUN_LIVE=1 python -m tests.evals.routing_eval`
   must still score ≥ 90% (Part A adds a new Supervisor-facing tool, which
   changes the tool-choice space it reasons over).
7. Work through §5 in order (Part A fully, then Part B). Each step leaves
   the tree green.

---

## §1 Background: what is actually wrong today

**Part A — memory extraction fails silently.**

1. `jarvis/bot/pipeline.py`'s `run_session`, in its `finally` block:
   ```python
   try:
       await asyncio.wait_for(
           update_memory_from_session(settings, runtime.session_id),
           timeout=30,
       )
   except Exception:  # noqa: BLE001
       pass
   ```
   `update_memory_from_session` itself already catches every internal
   failure and logs it (`logger.exception("memory_update_failed ...")`) —
   that part of the system is fine. The gap is this outer `except`: the
   *only* thing it can catch is `asyncio.TimeoutError` from the 30-second
   cap (since the inner function never raises past its own try/except),
   and that specific failure — the extraction call was still running when
   the session tore down — is swallowed with zero log line. There is
   currently no way to tell, from the logs, whether a session's memory
   fold-in happened, timed out, or errored.
2. Extraction only runs once, at session teardown. A session that never
   tears down cleanly (browser tab closed, crash, `kill -9`) loses
   everything discussed in it — `MORTIMER_RUN_LOGGING_PLAN.md`'s D11 found
   the same "process death loses data" shape in log rotation; the fix
   pattern here is the same idea applied to memory: a periodic sweep,
   not just an end-of-session write.
3. `update_memory_from_session` reads only the `conversations` table —
   Supervisor-level dialogue. Sub-agent activity (what a delegation
   actually did) is invisible to it, which is also why Part B does not
   try to extend this function to cover procedures — see D9.
4. There is no way for the Supervisor to force an immediate write when the
   user says something unambiguously worth remembering right now
   ("remember that I prefer metric units") — it waits for session end or
   the next periodic sweep (once Part A ships).

**Part B — there is no reuse of prior successful work.**

5. Every delegation starts from zero: `SubAgent._loop` builds
   `messages = [system, user]` fresh every time (`jarvis/agents/base.py`),
   with no memory of how a similar task was handled before, even when the
   exact same kind of task has succeeded identically many times.
6. As of `MORTIMER_RUN_LOGGING_PLAN.md`, every delegation's task text, tool
   sequence, and outcome is already captured durably
   (`agent_runs`/`agent_events` + JSONL payload) — this is new
   infrastructure this plan can build on rather than duplicate.

---

## §2 What we are building

**Part A:**
- Fix the silent swallow: log the timeout, add a periodic mid-session
  memory sweep (not just end-of-session), and add an explicit `remember`
  tool the Supervisor can call for immediate, high-confidence writes.

**Part B:**
- After a sub-agent run finishes (success or failure), match its task
  against existing **procedures** for that agent (SQLite FTS5, no LLM call
  on this path). If it matches, update that procedure's success/failure
  counters. If a successful run matches nothing, create a new *candidate*
  procedure in the background (one small LLM call, non-blocking). A
  candidate becomes **active** — and only then eligible to be injected as
  a hint — after `PROCEDURE_PROMOTE_AFTER` net successes, mirroring the
  existing `PROMOTE_AFTER` pattern for behavioral observations
  (`jarvis/memory.py`). An active procedure whose failures start to
  outweigh successes is automatically **deprecated** (counters stay,
  never deleted) and stops being injected.
- At the start of a delegation, `SubAgent._loop` runs the same FTS5 match
  (cheap, synchronous, no LLM call) against **active** procedures only; a
  match is injected as one short hint message before the task, and the
  sub-agent still reasons and still calls real tools normally.

Explicitly **out of scope**: embeddings/vector search (D22), codegen
procedures that write new MCP tools (a materially larger, separate
project), a user-facing procedures review panel (console UI — a
reasonable Phase 2 follow-up once procedures have run for a while and
there's something worth reviewing), and any change to
`config/self_edit_allowlist.json` or privileged-action confirmation gates
(D18 — safety boundary, not touched).

---

## §3 Decisions already made (with rationale)

### Part A — memory reliability

**D1 — Log the timeout in `pipeline.py`'s outer `except`, don't just add a
periodic sweep and call it fixed.** Change:
```python
except asyncio.TimeoutError:
    logger.warning("memory_extraction_timeout session=%s", runtime.session_id)
except Exception:  # noqa: BLE001 — memory must never break shutdown
    logger.exception("memory_extraction_failed session=%s", runtime.session_id)
```
*Rationale:* this is the actual bug — "extraction is failing silently."
Everything else in Part A reduces *how often* this path matters (more
frequent sweeps mean less lost on any one timeout) but does not make the
failure visible. Fixing the log line is the one-line, zero-risk, must-do
first step; each is independently valuable.

**D2 — Periodic mid-session sweep, modeled directly on
`jarvis/bot/reminders_watcher.py`'s `RemindersWatcher`.** New
`jarvis/bot/memory_watcher.py`: `MemorySweepWatcher(settings, session_id,
interval_s)`, same `start()`/`stop()`/`tick_once()` shape, same
`asyncio.create_task` loop, same `try/except` around the tool/extraction
call with a `logger.warning` on failure. Unlike `RemindersWatcher`, it has
no `is_connected` gate and injects nothing into the conversation — it
purely calls `update_memory_from_session(settings, session_id)` on each
tick.
*Rationale:* this exact watcher shape already exists, is already proven in
production, and already solves "run something periodically in the
background without blocking or crashing the pipeline." Inventing a
different mechanism (a raw `asyncio.sleep` loop inlined in `pipeline.py`,
a `contextvars`-based scheduler, etc.) would be new code solving an
already-solved problem in this codebase.

**D3 — `update_memory_from_session` requires no changes to run
mid-session.** It already re-reads the last `MAX_TRANSCRIPT_ROWS` (60)
rows for the session fresh on every call and *replaces* (not appends) the
single summary row and each fact by key — calling it twice on overlapping
transcript windows is naturally idempotent at the data layer. Verified by
reading `_session_transcript`, `upsert_fact` (`ON CONFLICT ... DO UPDATE`),
and `set_summary` (`UPDATE ... WHERE id = ?` on the single existing row).
*Rationale:* this is why D2 is low-risk — the sweep is "call an existing,
already-safe function on a timer," not "build new merge logic." The only
new cost is repeated LLM calls, addressed by D4's interval choice.

**D4 — Sweep interval: `JARVIS_MEMORY_SWEEP_INTERVAL_S`, default `300`
(5 minutes).** New `Settings` field, same placement convention as
`jarvis_max_parallel_delegations`/`jarvis_runlog_retention_days`.
`update_memory_from_session`'s own 30-second timeout (D5) still applies
per call.
*Rationale:* 5 minutes bounds data loss on an unclean disconnect to at
most one interval, while keeping LLM-call frequency low for typical
sessions (most voice sessions are shorter than 5 minutes; the sweep is
insurance for the ones that aren't). A tuning knob, not a hardcoded value,
per this codebase's established convention (`⚙ TUNING KNOB` comments in
`jarvis/runlog/store.py`).

**D5 — `update_memory_from_session`'s existing 30 s cap becomes a named
constant `MEMORY_EXTRACTION_TIMEOUT_S = 30` in `jarvis/memory.py`.**
`update_memory_from_session`'s own signature and internals do not change —
the constant is used the same way the literal `30` is used today: as the
`timeout=` argument to an external `asyncio.wait_for(update_memory_from_session(...),
timeout=MEMORY_EXTRACTION_TIMEOUT_S)` call. Both the existing teardown
call site in `pipeline.py` and the new watcher's `tick_once` (D2/§5.3)
wrap their call this same way, importing the constant rather than each
hardcoding `30`. Not made into a new `Settings` field — it is an internal
safety bound, not something a user needs to tune.
*Rationale:* one named constant in one place is enough; promoting it to a
`.env` setting would be scope creep unrelated to the actual bug (D1) and
this codebase already draws that line elsewhere (`CALL_TIMEOUT` in
`jarvis/skills/registry.py` is a similar internal constant, not a
`Settings` field).

**D6 — New `remember` tool, Supervisor-only (not a sub-agent tool),
wired exactly like `set_voice`
(`jarvis/bot/voice_switch.py`'s `build_set_voice_tool` is the template).**
New `jarvis/bot/remember_tool.py`:
```python
REMEMBER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "remember",
        "description": (
            "Immediately store one durable fact about the user, stated "
            "explicitly and unambiguously in this turn — a preference, "
            "a correction, a standing instruction. Do not use this for "
            "one-off requests, small talk, or anything uncertain; those "
            "are handled by ordinary end-of-session memory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string",
                         "description": "lowercase dotted path, e.g. "
                                        "user.preference.units"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
}

def build_remember_tool(session_id: str) -> tuple[dict, Callable]:
    async def handler(arguments: dict) -> str:
        key = str(arguments.get("key", "")).strip()
        value = str(arguments.get("value", "")).strip()
        if not key or not value:
            return "Nothing to remember — both a key and a value are required."
        with get_conn() as conn:
            upsert_fact(conn, key, value, session_id)
        return f"Got it — I'll remember {key}."
    return REMEMBER_SCHEMA, handler
```
Wired in `build_pipeline` alongside `delegate_schema`/`set_voice_schema`:
`llm.register_function("remember", adapt_to_pipecat(remember_handler))`,
added to the `standard_tools` list.
*Rationale:* `upsert_fact` already has every safety property this needs —
the Phase 5b content scan (`scan_memory_content`), key-based upsert
semantics, `MAX_FACT_CHARS` truncation. Calling it directly, rather than
re-implementing any of that, means `remember` cannot silently diverge from
what end-of-session extraction considers safe to store. Modeling the tool
wiring on `set_voice` (not `delegate_task`) because `remember` is a direct
Supervisor action with no sub-agent involved — the same category `set_voice`
already is.

**D7 — `SUPERVISOR_PROMPT` gains one short paragraph describing when to use
`remember`, reusing `EXTRACTION_PROMPT`'s existing criteria for what counts
as a fact worth keeping** (explicit statement, durable, not one-off) rather
than inventing new wording.
*Rationale:* two independently-worded descriptions of "what's worth
remembering" (one in `EXTRACTION_PROMPT`, a differently-worded one in
`SUPERVISOR_PROMPT`) would drift and could disagree about edge cases. The
`remember` tool's own schema description (D6) already restates this
briefly for the same reason.

**D8 — Rejections from `remember` are silent to the user beyond the
confirmation sentence** (`upsert_fact`'s existing `logger.warning` on a
content-scan rejection is sufficient; the tool still returns a generic
"Got it" style confirmation rather than exposing the rejection reason to
the LLM, which could otherwise repeat rejected content back believing it
needs rephrasing).
*Rationale:* matches how `upsert_fact` already behaves for the
end-of-session path — a rejection is a security/safety event
(prompt-injection or credential pattern), not something to negotiate with
the model that may have produced the flagged text.

### Part B — procedures as hints

**D9 — Procedures are learned from `jarvis.runlog`, not from
`conversations`/session transcripts.** A dedicated background step reads
each finished sub-agent run's `agent_runs`/`agent_events` (via
`jarvis.runlog.store.get_run`), not the Supervisor-level dialogue Part A
reads.
*Rationale:* sub-agent task/tool/outcome data was never in `conversations`
in the first place (this is the exact gap `MORTIMER_RUN_LOGGING_PLAN.md`
closed) — reusing that already-built, already-tested infrastructure is
strictly better than re-deriving the same data from a different, wrong
source. It also cleanly separates two concerns that would otherwise
tangle: user-level memory (what the user told the Supervisor) and
task-level procedures (how a sub-agent got a job done).

**D10 — Matching is FTS5 keyword search, not embeddings, for both write-side
dedup and read-side retrieval — the same query, same code path, both
directions.** New virtual table `procedures_fts` over `procedures`, built
exactly like `conversations_fts` in `jarvis/db.py` (external-content table,
three triggers — see D19 for the exact SQL; no backfill `INSERT` is needed
the way `conversations_fts` required one, since `procedures` is a new,
empty table at migration time, not a table with pre-existing rows).
*Rationale:* this codebase already has one FTS5 pattern proven correct in
production (`conversations_fts`) — reusing the identical trigger structure
is lower-risk than introducing a new dependency (an embeddings library, a
vector store) for a feature whose volume (one row per distinct procedure,
likely dozens, not millions) does not need one. Using the *same* query for
both dedup-at-write-time and retrieval-at-read-time is what makes ID drift
impossible: a new candidate can never fail to match the record it should
increment, because the exact matching logic that decided "no existing
procedure fits, create one" is the same logic that will find it next time.

**D11 — Matching happens inside `SubAgent._loop`, before the first LLM
call, using `self.name` (agent) + `task` (verbatim).** Not in
`delegate.py`, not in the Supervisor.
*Rationale:* stated in the original discussion and unchanged here —
procedures are agent-specific (a "resolve a relative date" procedure only
makes sense for the Scheduler), and matching at the Supervisor layer would
add latency to the voice-critical turn for a decision that only matters
once a task has already been routed to a specific specialist.

**D12 — Retrieval is synchronous and in the request path (adds one FTS5
query per delegation); learning/promotion is asynchronous, background,
fire-and-forget, never in the request path.**
*Rationale:* an FTS5 `MATCH` query against a small table is sub-millisecond
— cheap enough to run inline without a latency concern, the same way
`render_memory_context` already runs a SQLite query inline in the pipeline
build path. The LLM call needed to *describe* a brand-new candidate
procedure, by contrast, is exactly the kind of cost this codebase already
keeps out of the live turn (mirrors `update_memory_from_session` being
fire-and-forget at session end) — see D13 for where it runs instead.

**D13 — Learning runs as `asyncio.create_task` in `delegate.py`'s
`handler`, right after `agent.run(...)` returns, holding a reference in a
module-level `set` to prevent garbage collection before completion** (the
standard asyncio gotcha with detached background tasks).
```python
_background_tasks: set[asyncio.Task] = set()

def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
```
Called as `_spawn_background(learn_from_run(run_id, agent_name))` after
`result` is known, before `handler` returns. Does not block the reply.
*Rationale:* `delegate.py` already knows `run_id` and `agent_name` at
exactly the point a run finishes — the natural call site, requiring no new
plumbing to discover which run just completed. The reference-holding
pattern is required because Python has no strong reference to a bare
`asyncio.create_task(...)` result otherwise, and a garbage-collected task
can be silently cancelled mid-flight — a well-known pitfall this decision
exists specifically to avoid.

**D14 — `learn_from_run(run_id, agent_name)` (new,
`jarvis/procedures.py`) does, in order:**
1. `detail = jarvis.runlog.store.get_run(run_id)` — reuses existing reader.
2. Run the FTS5 match (D10) for `agent_name` against `detail["run"]["task"]`,
   calling `match_procedure(agent_name, task, status=None)` — `status=None`
   means "match regardless of status," searching `candidate`, `active`,
   **and** `deprecated` rows. This is deliberately not the same call
   `_loop`'s retrieval path makes (D11, always `status="active"`) — dedup
   must find a `deprecated` row too, so a task shape that recurs after one
   deprecation reinforces the existing row's counters instead of spawning
   a duplicate `candidate` for the same shape. A `deprecated` row's
   `status` never changes as a result (D15 — no auto-re-promotion), only
   its counters do.
3. If a match scores above `PROCEDURE_MATCH_THRESHOLD` (⚙ tuning knob):
   increment its `success_count` or `failure_count` (from
   `detail["run"]["status"]`), touch `updated_at`, append `run_id` to
   `source_run_ids` (capped list, oldest dropped past
   `MAX_SOURCE_RUN_IDS`), and apply D15's promotion/deprecation check.
4. If no match and `detail["run"]["status"] != "ok"`: do nothing — a
   candidate is only ever created from a **successful** run (D16).
5. If no match and status is `ok`: make one small LLM call (`AsyncOpenAI`,
   same client-construction pattern as `update_memory_from_session`) to
   produce a short label + description, then `INSERT` a new `candidate`
   row.
Every step wrapped in `try/except Exception`, logged once at WARNING,
never raised — matches D6/D6 of the run-logging plan's own contract this
function is adjacent to.
*Rationale:* one function, one file, one clear order — the implementing
model has no ambiguity about what "learning" means operationally.

**D15 — Promotion/deprecation thresholds.**
`PROCEDURE_PROMOTE_AFTER = 3` (mirrors `jarvis.memory.PROMOTE_AFTER`
exactly, same reasoning: one success is noise, three is a pattern).
A `candidate` becomes `active` when `success_count - failure_count >=
PROCEDURE_PROMOTE_AFTER`. An `active` procedure becomes `deprecated` when
`failure_count >= PROCEDURE_DEPRECATE_AFTER` (⚙ tuning knob, default `3`)
`and failure_count > success_count`. A `deprecated` procedure never
re-promotes automatically — counters keep updating (for auditability) but
`status` only ever changes again by manual intervention (none is built in
this plan; see §2's out-of-scope note on a review panel).
*Rationale:* reusing the exact promotion threshold already established and
already understood (`PROMOTE_AFTER`) for a parallel concept keeps the
system's overall "how much evidence before Mortimer acts on a pattern"
story consistent in one place rather than two differently-tuned versions.
Requiring failures to *outweigh* successes before deprecating (not just
"any failure") avoids one bad outlier run silently killing a procedure
that has otherwise worked nine times out of ten.

**D16 — A candidate is only ever created from a successful run (D14 step
4/5).** Failed runs can only *reinforce a deprecation* of an existing
match (D14 step 3), never originate a brand-new procedure.
*Rationale:* stated in the original discussion's risk section — this is
the direct mitigation for "a skill recorded from a run that appeared to
succeed but was subtly wrong gets silently repeated forever." Requiring a
literal success (from `agent_runs.status`, the same field the run log
already trusts) as the origin of any new procedure, and requiring
*repeated* net success (D15) before it is ever surfaced as a hint, is the
concrete version of "skill-as-hint, promoted by evidence, never a single
observation."

**D17 — Injected hint text is exactly the procedure's `description` field,
prefixed with a fixed sentence, inserted as one additional `system`-role
message between the sub-agent's own system prompt and the task, not
appended to or blended into either.**
```python
messages = [
    {"role": "system", "content": self._system_prompt},
]
if procedure_hint:
    messages.append({
        "role": "system",
        "content": f"A similar task has succeeded before: {procedure_hint}",
    })
messages.append({"role": "user", "content": task})
```
*Rationale:* keeping the hint a separate, clearly-labeled message (rather
than string-concatenating it into the existing system prompt, which is
built once at `SubAgent.__init__` and must stay per-agent, not
per-task — see run-logging plan's own note on why per-task data can't live
in `self._system_prompt`) makes it trivial to omit when no hint applies
(the common case) and impossible to accidentally corrupt the base prompt.

**D18 — Safety: a procedure is a hint, never a bypass, and this plan adds
no new code path around any existing confirmation gate.** A procedure's
`description` is free text describing *what worked*, not a replay
mechanism — the sub-agent still calls `self._registry.call(...)` for every
tool, unchanged, and privileged actions (git push, self-edit submit)
remain exactly as gated as before this plan. No procedure can ever cause a
tool call to happen without the sub-agent's own LLM choosing to make it.
*Rationale:* directly answers the risk flagged in the original discussion
— "any skill encoding a privileged action must still route through the
existing confirmation gate." D17's implementation (a prompt hint, not
code) makes this true by construction rather than by a check that could be
missed.

**D19 — Schema.**
```sql
CREATE TABLE IF NOT EXISTS procedures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent TEXT NOT NULL,
  label TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',  -- candidate | active | deprecated
  success_count INTEGER NOT NULL DEFAULT 0,
  failure_count INTEGER NOT NULL DEFAULT 0,
  source_run_ids TEXT NOT NULL DEFAULT '[]', -- JSON array, capped
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_procedures_agent_status
  ON procedures(agent, status);

CREATE VIRTUAL TABLE IF NOT EXISTS procedures_fts USING fts5(
  label, description, agent UNINDEXED,
  content='procedures', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS procedures_fts_ai AFTER INSERT ON procedures BEGIN
  INSERT INTO procedures_fts(rowid, label, description, agent)
  VALUES (new.id, new.label, new.description, new.agent);
END;

CREATE TRIGGER IF NOT EXISTS procedures_fts_ad AFTER DELETE ON procedures BEGIN
  INSERT INTO procedures_fts(procedures_fts, rowid, label, description, agent)
  VALUES ('delete', old.id, old.label, old.description, old.agent);
END;

CREATE TRIGGER IF NOT EXISTS procedures_fts_au AFTER UPDATE ON procedures BEGIN
  INSERT INTO procedures_fts(procedures_fts, rowid, label, description, agent)
  VALUES ('delete', old.id, old.label, old.description, old.agent);
  INSERT INTO procedures_fts(rowid, label, description, agent)
  VALUES (new.id, new.label, new.description, new.agent);
END;
```
Structure copied field-for-field from `conversations_fts`'s three triggers
(`jarvis/db.py` `MIGRATION_0005`) — same external-content pattern, same
delete-then-reinsert shape for `UPDATE`. No backfill `INSERT` is needed
here (unlike `MIGRATION_0005`, which backfilled existing `conversations`
rows) — `procedures` is a brand-new table with no pre-existing rows at
migration time.
New migration `0007_procedures`, appended to `MIGRATIONS`.
*Rationale:* `source_run_ids` (not a join table) because the list is
small, bounded (D14), and read as a unit (audit trail for one procedure) —
never queried "which procedures reference run X," which would justify a
proper join table. `last_used_at` is set whenever a procedure is injected
as a hint (D11's call site), tracked for future staleness review even
though this plan builds no review UI yet.

**D20 — `SubAgent.__init__` gains no new parameters; matching reads
`Settings.jarvis_procedures_enabled` (new field, default `True`) at
`_loop` call time, mirroring the run-logging plan's `jarvis_runlog_enabled`
kill-switch pattern exactly.** When disabled: `_loop` skips the FTS query
entirely (no hint ever injected) and `learn_from_run` becomes a no-op at
its first line. **This is the single enforcement point for the flag** —
`delegate.py`'s background-spawn call site (D13) does not duplicate the
check.
*Rationale:* same rollback story as run-logging (`MORTIMER_RUN_LOGGING_PLAN.md`
§8) — one flag, no schema change, no code removal needed to fully disable
this feature if it misbehaves in practice. One enforcement point (not two)
for the same reason `RunLogger`'s own kill switch lives entirely inside
its `_safe` wrapper rather than being re-checked at every call site — a
second check at the spawn site would also require reaching into
`SubAgent`'s private `_settings` attribute from `delegate.py`, a module
that has never done so before this plan.

**D21 — `PROCEDURE_MATCH_THRESHOLD` and `PROCEDURE_PROMOTE_AFTER` /
`PROCEDURE_DEPRECATE_AFTER` / `MAX_SOURCE_RUN_IDS` are `⚙ TUNING KNOB`
module constants in `jarvis/procedures.py`, adjusted there only** — same
convention as `jarvis/runlog/store.py`'s tuning knobs (plan §6 rule
carried forward).

**D22 — No embeddings/vector search in this plan (deferred, not
rejected).** If FTS5 matching proves too coarse in practice (near-miss
phrasing not matching an obviously-relevant procedure), that is a future,
separately-scoped plan, not a mid-implementation pivot here.
*Rationale:* per §0.1's own rule, this plan makes every decision up front;
introducing an embeddings dependency mid-plan would be exactly the kind of
undecided fork §0 exists to prevent. Deferring cleanly, with the reason
recorded, is preferable to a vague "consider embeddings later" footnote.

**D23 — No user-facing procedures review panel in this plan.** `procedures`
rows are inspectable today via `sqlite3 data/jarvis.db` or
`python -m jarvis.runlog --run <id>` (to see which procedure, if any, a
given run's outcome fed into — via a log line, not a stored FK; see D14).
A console panel mirroring `MemoryPanel`/`RunsPanel` is a natural Phase 2
addition once real procedure data exists to look at.
*Rationale:* building a review UI for a table with zero rows in it (on
first deploy) is premature; the memory panel precedent
(`MORTIMER_INTERFACE_UPGRADE_PLAN.md` Phase 5e) was itself built well after
facts/observations had been live for a while.

**D24 — Verification requires re-running the routing eval (§0.6).**
*Rationale:* `remember` (D6) is a new tool in the Supervisor's function set;
`tests/evals/routing_eval.py` asserts on `delegate_task` calls specifically,
but the model's tool-choice distribution can still shift when a new tool
is available. This is the same category of regression risk this codebase
already gates on for any Supervisor-facing change.

---

## §4 Files that will change

**New:**

| Path | Purpose |
|---|---|
| `jarvis/bot/memory_watcher.py` | `MemorySweepWatcher` (D2) |
| `jarvis/bot/remember_tool.py` | `remember` tool schema + handler (D6) |
| `jarvis/procedures.py` | Matching, learning, promotion (D11–D21) |
| `tests/unit/test_memory_watcher.py` | Watcher tick/failure behavior |
| `tests/unit/test_remember_tool.py` | Handler + content-scan rejection |
| `tests/unit/test_procedures.py` | Matching, promotion, deprecation, caps |
| `tests/integration/test_procedures_end_to_end.py` | Delegation → hint injected on a matching second run |
| `tests/acceptance/memory-procedures.md` | Manual checklist |

**Modified:**

| Path | Change |
|---|---|
| `jarvis/bot/pipeline.py` | D1 logging fix; start/stop `MemorySweepWatcher`; wire `remember` tool |
| `jarvis/memory.py` | `MEMORY_EXTRACTION_TIMEOUT_S` named constant (D5) |
| `jarvis/prompts.py` | `SUPERVISOR_PROMPT` gains `remember` guidance (D7) |
| `jarvis/config.py` | `jarvis_memory_sweep_interval_s`, `jarvis_procedures_enabled` |
| `jarvis/db.py` | `MIGRATION_0007_procedures` + `MIGRATIONS` entry |
| `jarvis/agents/base.py` | `_loop` queries + injects a procedure hint (D11/D17) |
| `jarvis/agents/delegate.py` | Spawns `learn_from_run` background task (D13) |
| `.env.example` | 2 new vars, documented |
| `CLAUDE.md` | Procedures section under Architecture |

---

## §5 Implementation steps

### Part A

**5.1 — `jarvis/memory.py`**: add `MEMORY_EXTRACTION_TIMEOUT_S = 30` near
the other module constants; no behavior change here, just naming the
existing value (D5).

**5.2 — `jarvis/config.py`**: add
```python
jarvis_memory_sweep_interval_s: float = 300.0
jarvis_procedures_enabled: bool = True
```
placed with the other `jarvis_*` fields.

**5.3 — `jarvis/bot/memory_watcher.py`** (new): `MemorySweepWatcher`,
built by copying `RemindersWatcher`'s `start`/`stop`/`_run`/`tick_once`
shape (D2) with `is_connected`/`inject` removed and `tick_once` calling
```python
await asyncio.wait_for(
    update_memory_from_session(self._settings, self._session_id),
    timeout=MEMORY_EXTRACTION_TIMEOUT_S,
)
```
inside its own `try/except` — `asyncio.TimeoutError` and any other
`Exception` both caught and logged at WARNING with distinct messages,
mirroring D1's split at the teardown call site exactly (so a mid-session
sweep timeout is exactly as visible in the logs as a teardown timeout).

**5.4 — `jarvis/bot/remember_tool.py`** (new): `REMEMBER_SCHEMA`,
`build_remember_tool(session_id)` exactly as specified in D6.

**5.5 — `jarvis/bot/pipeline.py`**:
- Apply D1's logging fix to the existing teardown `except` block.
- After `watcher = RemindersWatcher(...); watcher.start()`, add
  `memory_watcher = MemorySweepWatcher(settings, runtime.session_id, settings.jarvis_memory_sweep_interval_s); memory_watcher.start()`.
- In the `finally` block, `await memory_watcher.stop()` alongside the
  existing `await watcher.stop()`, before the final teardown
  `update_memory_from_session` call (which remains — it is the last
  sweep, covering anything since the periodic watcher's last tick).
- Build `remember_schema, remember_handler = build_remember_tool(runtime.session_id)`
  alongside `delegate_schema`/`set_voice_schema`; register via
  `llm.register_function("remember", adapt_to_pipecat(remember_handler))`;
  add `to_function_schema(remember_schema)` to `standard_tools`.

**5.6 — `jarvis/prompts.py`**: add one short paragraph to
`SUPERVISOR_PROMPT` (D7) — after the existing delegation paragraph, before
`VOICE_ADDENDUM` is applied:
```
When the user explicitly states a durable preference, correction, or
standing instruction, call remember immediately with a lowercase dotted
key (e.g. user.preference.units) rather than waiting until later. Do not
use remember for one-off requests or anything uncertain.
```

### Part B

**5.7 — `jarvis/db.py`**: append `MIGRATION_0007_procedures` (D19) and
`("0007_procedures", MIGRATION_0007_procedures)` to `MIGRATIONS`.

**5.8 — `jarvis/procedures.py`** (new): implements, in this order:
- Module constants (D21, `⚙ TUNING KNOB` comments):
  `PROCEDURE_MATCH_THRESHOLD`, `PROCEDURE_PROMOTE_AFTER = 3`,
  `PROCEDURE_DEPRECATE_AFTER = 3`, `MAX_SOURCE_RUN_IDS = 20`.
- `match_procedure(agent: str, task: str, status: str | None = "active", db_path=None) -> dict | None`
  — the shared FTS5 query (D10). `status="active"` (the default) is what
  D11's retrieval path uses; `status=None` matches any status and is what
  D14's dedup path uses explicitly — never rely on the default for the
  dedup call site, pass `status=None` there by name so the choice is
  visible at the call site, not implicit.
- `learn_from_run(run_id: str, agent: str, db_path=None) -> None` — async,
  implements D14 exactly, wrapped per D6/§0.3.
- `_promote_or_deprecate(row, conn) -> None` — D15's threshold logic,
  called from inside `learn_from_run` after counters update.

**5.9 — `jarvis/agents/base.py`**: in `_loop`, before building `messages`
(and only when `self._settings.jarvis_procedures_enabled`), call
`jarvis.procedures.match_procedure(self.name, task)`; if a row comes back,
insert the D17 hint message and update the matched row's `last_used_at`
(best-effort, same `try/except` discipline as everything else in this
file).

**5.10 — `jarvis/agents/delegate.py`**: after `result = await agent.run(...)`
inside the semaphore block, unconditionally call
`_spawn_background(learn_from_run(run_id, agent_name))` (D13). Do not
check `jarvis_procedures_enabled` here — D20 makes this a single-enforcement-
point flag, checked once inside `learn_from_run` itself; a disabled flag
still spawns a task, which returns immediately as a no-op. This keeps
`delegate.py` from reaching into `SubAgent`'s private `_settings`.

**5.11 — Docs**: `.env.example` gets both new vars with one-line comments;
`CLAUDE.md` gets a **Procedures** paragraph under *Architecture*, modeled
on the existing **Run log** paragraph's style, explicitly stating the
naming rule from §0.4.

---

## §6 Where the tuning knobs live

Part A: `MEMORY_EXTRACTION_TIMEOUT_S` in `jarvis/memory.py`;
`JARVIS_MEMORY_SWEEP_INTERVAL_S` is a user-facing `.env` setting, not a
knob.

Part B: `PROCEDURE_MATCH_THRESHOLD`, `PROCEDURE_PROMOTE_AFTER`,
`PROCEDURE_DEPRECATE_AFTER`, `MAX_SOURCE_RUN_IDS` — all in
`jarvis/procedures.py`, adjusted there only (D21).
`JARVIS_PROCEDURES_ENABLED` is the user-facing kill switch, not a knob.

---

## §7 Verification

**Automated — must all pass:**

1. `pytest tests/unit tests/integration -q` — green, including new files.
2. `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog, jarvis.procedures"` —
   extended import smoke check.
3. `python scripts/init_db.py` on a fresh `data/` — migration 0007 applies
   cleanly and idempotently.
4. `RUN_LIVE=1 python -m tests.evals.routing_eval` — must stay ≥ 90%
   (D24) — requires real API keys, run when available.

**New tests must cover, at minimum:**

- `test_memory_watcher.py`: `tick_once` calls `update_memory_from_session`
  with the right args; a raised exception inside a tick is caught and
  logged, the watcher keeps running; `stop()` cancels cleanly.
- `test_remember_tool.py`: a valid key/value calls `upsert_fact` and
  returns a confirmation; missing key or value returns the "nothing to
  remember" message without calling `upsert_fact`; a content-scan
  rejection (reuse `scan_memory_content`'s existing test fixtures) still
  returns a confirmation-shaped string (D8) while nothing is written.
- `test_procedures.py`: a new successful run with no match creates a
  `candidate`; three net successes promote it to `active`; three net
  failures on an active procedure deprecate it and it stops being
  returned by `match_procedure(..., status="active")`; `source_run_ids`
  is capped at `MAX_SOURCE_RUN_IDS`; a failed run never creates a new
  candidate (D16); a success matching an already-`deprecated` row
  (`match_procedure(..., status=None)`) increments its counters without
  reviving its status to `active`/`candidate`, and does not spawn a
  duplicate candidate for the same task shape (D14 step 2/D15);
  `jarvis_procedures_enabled=False` makes every function in the module a
  no-op.
- `test_procedures_end_to_end.py` (integration): run the same kind of task
  through a stubbed `SubAgent` three times; assert no hint is injected on
  runs 1–2 (still a candidate), assert a hint message appears in the
  messages sent to the fake LLM on a subsequent matching task once
  promoted; assert the hint text equals the stored procedure's
  `description`.

**Manual — `tests/acceptance/memory-procedures.md`, written in this
phase, requires a live voice session:**

- Say an explicit preference ("remember that I prefer metric units").
  Confirm `remember` fires (visible in `logs/bot.log`) and the fact
  appears in the Memory panel immediately, not at session end.
- Have a session run past 5 minutes without disconnecting. Confirm a
  periodic sweep log line appears before session end.
- Disconnect uncleanly (close the tab) mid-session, past one sweep
  interval. Confirm the last sweep's facts/summary are present even
  though the teardown path never ran.
- Ask the same kind of question of the same specialist three times across
  separate sessions (e.g. three different weather lookups to the
  Analyst/Systems agent, whichever owns `mcp_web`). Confirm
  `sqlite3 data/jarvis.db "select * from procedures"` shows one
  `candidate` row reach `active` on the third success.
- Confirm a fourth, similar request's sub-agent transcript (via
  `python -m jarvis.runlog --run <id>`, checking the JSONL payload's
  `run_start` messages if logged, or by temporary debug logging) shows the
  hint message present.
- Force three failures against an active procedure (e.g. temporarily
  unset a required API key) and confirm it flips to `deprecated` and stops
  being injected on a subsequent success.
- Confirm ordinary delegations to agents/tasks with no matching procedure
  are completely unaffected — no hint message, no latency regression.

---

## §8 Rollback

Part A: no rollback flag needed for D1 (a logging fix) or D6/D7 (additive
tool, harmless to leave). If the sweep watcher misbehaves, set
`JARVIS_MEMORY_SWEEP_INTERVAL_S` to a very large number as an effective
disable, or remove the two `start()`/`stop()` lines in `pipeline.py` — no
schema to unwind either way.

Part B: `JARVIS_PROCEDURES_ENABLED=false` (D20) — every write and every
read becomes a no-op. Full revert is `git revert` of the phase branch;
migration `0007` leaves two empty tables and a virtual table behind,
harmless, no down-migration written (matches the run-logging plan's own
rollback precedent).

---

## §9 Risk

| Risk | Severity | Mitigation |
|---|---|---|
| A `remember`-written fact is wrong or premature (user was thinking out loud, not stating a preference). | Medium | The Memory panel (existing, shipped) already lets the user delete any fact by key, `remember`-written or not — no new correction path needed, the existing one already covers it. |
| FTS5 keyword matching is too coarse — a genuinely different task matches an unrelated procedure's rank threshold by coincidence. | Medium | `PROCEDURE_MATCH_THRESHOLD` is a tuning knob (D21) precisely so this can be tightened after seeing real match quality; D16/D15's promotion gate means even a bad early match only reinforces a procedure, it does not immediately start being injected — a genuinely bad procedure will also fail more than it succeeds and self-deprecate (D15). |
| Background `learn_from_run` tasks pile up under heavy concurrent delegation load. | Low | Bounded by the same `JARVIS_MAX_PARALLEL_DELEGATIONS` cap that already bounds live delegations; each background task is short (one FTS query, at most one small LLM call) and self-cleans via `add_done_callback`. |
| A new Supervisor-facing tool (`remember`) shifts routing behavior on unrelated cases. | Medium | §0.6/D24 — routing eval re-run is a required, not optional, verification step. |
| `procedures_fts`'s trigger structure is copy-pasted from `conversations_fts` and a subtle bug (e.g. missing an `UPDATE` trigger) goes unnoticed since procedure rows update far less often than conversation rows. | Low | `test_procedures.py` must explicitly test an `UPDATE` path (counter increment) followed by a re-query through `procedures_fts`, not just insert-then-query — call this out in review. |
| Procedures accumulate indefinitely with no pruning (unlike the run log, which has `JARVIS_RUNLOG_RETENTION_DAYS`). | Low | Volume is inherently small (one row per distinct task shape per agent, not one per run) — a `deprecated` row is a permanent, cheap audit record, not a growing log. Revisit only if this assumption proves wrong in practice. |

---

## §10 Approval

- [x] Larry has read §2 (scope) and §3 (decisions) and approves — Part A
  only, 2026-08-13.
- [x] Implementation may begin — Part A implemented same day (steps
  5.1–5.6): `jarvis/memory.py` (`MEMORY_EXTRACTION_TIMEOUT_S`),
  `jarvis/config.py` (`jarvis_memory_sweep_interval_s`),
  `jarvis/bot/memory_watcher.py` (new), `jarvis/bot/remember_tool.py`
  (new), `jarvis/bot/pipeline.py` (D1 logging fix + watcher wiring + tool
  registration), `jarvis/prompts.py` (D7 guidance), `.env.example`.
  `pytest tests/unit tests/integration -q` green (536 passed, 3 skipped;
  the one pre-existing failure — `test_mcp_web_server` — is a live-network
  weather lookup unrelated to this change). Routing eval (§0.6/D24) not yet
  re-run — requires real API keys, run when available.
- [x] Part B (procedures-as-hints) — approved and implemented 2026-08-13:
  `jarvis/db.py` (`MIGRATION_0007_procedures`), `jarvis/procedures.py`
  (new — `match_procedure`, `learn_from_run`, `mark_used`,
  `_promote_or_deprecate`), `jarvis/config.py`
  (`jarvis_procedures_enabled`), `jarvis/agents/base.py` (`_loop` hint
  injection, D11/D17), `jarvis/agents/delegate.py` (`_spawn_background` +
  D13 fire-and-forget `learn_from_run` call), `.env.example`, `CLAUDE.md`.
  One deliberate deviation from the literal spec, documented at the
  deviation site: D10 describes FTS5 matching without giving exact SQL for
  the accept/reject decision (unlike D19's schema, which is exact).
  `match_procedure` uses FTS5 to generate the candidate set, then a
  Python-side stopword-filtered token-overlap ratio (`PROCEDURE_MATCH_THRESHOLD
  = 0.5`) to decide — chosen over raw FTS5 `bm25()` ranking because bm25's
  sign/magnitude degrades unpredictably on this table's small,
  low-document-count corpus (one row per distinct task shape per agent),
  which would have made the threshold nondeterministic in exactly the
  volume regime §9's own risk table describes. Both the dedup and
  retrieval call sites still go through the one function, preserving
  D10's actual requirement (no ID drift between write-side dedup and
  read-side retrieval).
  A second, safety-motivated addition beyond the plan text: `delegate.py`
  spawning `learn_from_run` unconditionally (D13/D20 as written) meant
  every existing test that drives `build_delegate_tool`'s handler would
  silently call the real `jarvis.config.load_settings()` — which reads
  this repo's real `.env` — on every test run. Added an autouse
  `_stub_procedures_learning` fixture in `tests/conftest.py` that no-ops
  `jarvis.agents.delegate.learn_from_run` by default; tests that exercise
  the real function re-patch it locally. No production code changed for
  this — it is a test-suite safety net only.
  `pytest tests/unit tests/integration -q` green (558 passed, 3 skipped;
  the one pre-existing failure — `test_mcp_web_server` — is the same
  unrelated live-network weather lookup noted under Part A).
  `python scripts/init_db.py` on a fresh DB applies migration 0007
  cleanly and idempotently (verified). Routing eval (§0.6/D24) not yet
  re-run — requires real API keys, run when available.
