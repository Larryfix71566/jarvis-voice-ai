# Mortimer — Sub-Agent Run Logging

**Status:** APPROVED 2026-08-12 by Larry. **Revision 2** — implementation not
yet started.
**Scope decided by:** Larry, 2026-08-12 (four-question scoping round; answers
recorded in §2).
**Supersedes nothing.** Additive to everything shipped through
`MORTIMER_INTERFACE_UPGRADE_PLAN.md` and `MORTIMER_STAR_LAYOUT_PLAN.md`.

**Revision 2 (2026-08-12)** — an audit of revision 1 against §0.1 ("every
design decision is already made") found six places where an implementing
model would have had to invent one. All six are now closed. Nothing in the
approved *scope* (§2) changed; these are specification gaps, not new work.

| # | Gap in revision 1 | Closed by |
|---|---|---|
| 1 | §5.3 made `mcp_call` a `RunLogger` method while §5.2/D3 put only a `str` in the ContextVar — `SkillRegistry` had no route to the instance. Three incompatible workarounds were possible, one of which silently dropped MCP events from the JSONL. | **D3 rewritten** — the ContextVar holds the `RunLogger` instance. §5.2, §5.3, §5.6 aligned. |
| 2 | `agent_runs.session_id` was a column and a constructor kwarg that nothing ever populated. | **D16** — explicit keyword-only thread through `build_delegate_tool` → `SubAgent.run` → `RunLogger`. §5.5 updated. |
| 3 | §5.7 said to pass `enabled` in from `SubAgent`; §5.3's constructor had no such parameter. | **D17** + the fixed constructor signature in §5.3. |
| 4 | `tool_result.ok` was required but underivable — `SkillRegistry.call()` returns a bare string. | **D18** — documented prefix heuristic at the `SubAgent` layer, exact signal recorded on the `mcp_call` event one layer down. |
| 5 | JSONL record *types* were named but their *fields* never specified, with three separate consumers reading them. | **D19** + new **§5.3a** fixing all six record shapes. |
| 6 | `RunLogger` connection lifecycle unspecified; `since` parsing duplicated between CLI and API with no defined type. | **D20** — per-write connections, one shared `parse_since()`. |

Revision 2 also tightened §5.10 (CLI output contract), §5.11 (query
normalization), §5.12 (panel interfaces mirror §5.3a as a discriminated
union), and §7 (a regression test per closed gap).

---

## §0 Constraints for the implementing model

1. **Every design decision is already made.** They are in §3, lettered D1–D15,
   each with its rationale. If you find yourself choosing between two
   approaches, re-read §3 — the choice is there. If it genuinely is not,
   stop and ask rather than inventing one.
2. **This must never break the voice path.** Every write this plan adds is
   best-effort: it is wrapped, its failure is logged once at WARNING, and it
   is then dropped. A logging failure must never propagate into a sub-agent
   run, a delegation, or the pipeline. This mirrors the existing contract in
   `jarvis/memory.py` and `_persist()` in `jarvis/bot/transcript_log.py`.
3. **Do not change any existing public signature** except where §5 says so
   explicitly, and do not change any existing observable behavior — no new
   UI messages on the data channel, no changes to what the Supervisor sees,
   no changes to sub-agent replies.
4. **The stable-identifier rule from CLAUDE.md still holds.** `jarvis/` and
   `JARVIS_*` stay; everything user-facing says "Mortimer".
5. **Additive schema only.** New tables, new migration appended to the
   `MIGRATIONS` list. Never edit an already-applied migration string.
6. Work through §5 in order. Each step leaves the tree green.

---

## §1 Background: what is actually wrong today

Verified by reading the source, not assumed.

1. **Sub-agent runs leave essentially no durable trace.** `SubAgent._loop`
   (`jarvis/agents/base.py`) already emits `agent_start`, `agent_tool`,
   `agent_tool_result`, and `agent_done` events carrying the task text, tool
   names, tool arguments, and tool results. **None of it is persisted.** The
   events go to `make_agent_event_handler` in `jarvis/bot/pipeline.py`, which
   forwards a subset to the UI over the data channel and prints a one-line
   summary to stdout. The status card fades after `DONE_FADE_MS = 8000`, and
   the record is gone.

2. **The only durable sub-agent log lines are two.** `logger.info(
   "subagent_done agent=%s latency_ms=%d")` and an exception traceback on
   failure. No task, no tools, no arguments, no results, no session id, no
   way to tell two concurrent runs apart.

3. **`conversations` holds Supervisor turns only.** `jarvis/bot/transcript_log.py`
   persists `user` and `assistant` rows; `jarvis/agents/supervisor.py` does
   the same for the CLI path. Sub-agent internals never reach SQLite. This is
   also why `jarvis/memory.py`'s extraction — which reads only that table —
   is blind to everything the specialists actually did.

4. **Parallel delegation shipped without correlation IDs.** `build_delegate_tool`
   allows up to `JARVIS_MAX_PARALLEL_DELEGATIONS` (default 3) concurrent
   sub-agent runs. Their log lines and events interleave in a flat stream with
   no shared key. There is currently no way to reconstruct which tool call
   belonged to which delegation.

5. **Failures are lossy by construction.** `SubAgent.run()` never raises; it
   returns `"FAILED: <reason>"`, which is handed straight back to the
   Supervisor as tool output and absorbed into the conversation. The
   underlying exception type, the tool arguments that caused it, and the
   MCP-layer error text are not recorded anywhere durable.
   `SkillRegistry.call()` has the same shape: it returns
   `"<tool> failed: <TypeName>."` and logs one WARNING without arguments.

6. **`logs/bot.log` is wiped on every restart.** `scripts/mortimer.sh` starts
   components with `nohup ... > logs/bot.log 2>&1 &` — a truncating redirect.
   Restarting Mortimer destroys the previous session's stdout, which is where
   the `TURN`, `[AGENT]`, `[session]`, and `USER:`/`BOT:` lines live.
   `scripts/latency_probe.py` takes a log path as its argument and therefore
   only ever sees the current run.

7. **Most of this codebase's diagnostics are `print()`, not `logging`.**
   `transcript_log.py`, `pipeline.py`'s `bot_event_log`, and the session
   banner all use `print(..., flush=True)`. A Python `logging` file handler
   would not capture any of them. This constrains how the file-rotation part
   of the fix must be built — see D11.

**What is *not* wrong:** `logs/` is gitignored, `get_conn()` already opens
WAL mode (so the admin sidecar can read while the bot writes), and the
migration runner is already idempotent and ordered. None of that needs
changing.

---

## §2 What we are building

Four scoping answers, given 2026-08-12:

| Question | Answer |
|---|---|
| Scope | **Sub-agents + MCP calls.** Supervisor turns stay in `conversations` as they are. |
| Storage | **SQLite index + JSONL payloads.** |
| Review surface | **CLI *and* a console Runs panel.** |
| Retention | **Rotation + age-based pruning. Redaction deferred.** |

Concretely, after this phase:

- Every delegation gets a `run_id`, threaded from `delegate_task` through the
  sub-agent loop down to each MCP tool call.
- Every run writes one `agent_runs` row and N `agent_events` rows to SQLite,
  plus one `logs/agents/<date>/<run_id>.jsonl` file holding the untruncated
  payloads.
- `python -m jarvis.runlog` answers "what did the Developer do, and why did it
  fail" from the terminal.
- A **Runs** button in the console topbar opens a browsable run history.
- Restarting Mortimer no longer destroys the previous log; runs older than the
  retention window are pruned automatically.

Explicitly **out of scope** (do not build these):

- Redaction of secrets from logged arguments/results (D14).
- Logging Supervisor turns or self-edit runs into the run log.
- Any change to memory extraction, the skills/procedures idea, or the
  Developer-card layout issue. Those are separate work.
- Deleting runs from the UI (D15).

---

## §3 Decisions already made (with rationale)

**D1 — The `run_id` is generated in `delegate_task`'s handler, one per
delegation.** UUID4, `str`. Generated at the top of `handler()` in
`jarvis/agents/delegate.py`, before the `delegate_start` event fires and
before the semaphore is acquired.
*Rationale:* one delegation is exactly one unit a human wants to review. The
`delegate_start` event already fires before the semaphore so the UI shows
"working" immediately; generating there means a queued-but-not-yet-running
delegation still has an identity. `SubAgent.run()` also accepts an optional
`run_id` and generates its own if absent, so direct calls (CLI, tests,
`sub_agent_evals.py`) still produce a complete log.

**D2 — `run_id` is added to every event dict as an additive field.** Existing
consumers (`bot_event_log`, `make_agent_event_handler`, the UI) read specific
keys and ignore unknown ones, so this changes no behavior.
*Rationale:* keeps the event stream the single description of a run, and lets
a future UI feature link a status card to its run detail with no further work.

**D3 — MCP-layer correlation uses a `contextvars.ContextVar`, not a new
parameter on `SkillRegistry.call()`. The ContextVar holds the live
`RunLogger` instance, not the run id string.** A module
`jarvis/runlog/context.py` owns
`current_run_logger: ContextVar[RunLogger | None]`. `SubAgent.run()` sets it
for the duration of the run; `SkillRegistry.call()` reads it and calls
`logger.mcp_call(...)` directly.
*Rationale:* four reasons. (a) `SkillRegistry`'s public surface is a locked
Phase 2 contract ("Exposes exactly …") and several tests construct it
directly. (b) `contextvars` propagate correctly into `asyncio` tasks, so
concurrent delegations each see their own value with no plumbing. (c) MCP
calls made from outside a sub-agent see `None` and are skipped, rather than
breaking. (d) **Holding the instance rather than the id is what lets
`mcp_call` be a real method on the run's own buffer**, so MCP events reach
the JSONL payload alongside everything else. If the ContextVar held only a
string, `SkillRegistry` would have no route to the buffer and MCP events
would silently land in SQLite only — defeating D4's "lose nothing" rule for
exactly the layer where failure detail matters most.

*Consequence to respect:* `RunLogger` is therefore touched from more than one
call site within a run, but always from the same `asyncio` task chain, so no
locking is required. The run id remains available anywhere via
`get_run_logger().run_id`; `jarvis/runlog/context.py` also exposes a
convenience `get_run_id() -> str | None` that returns it (or `None`) so
callers that only want the id — the `logger.warning` lines in §5.6 — do not
have to reach through the instance.

**D4 — Logging happens at the source, inside `SubAgent._loop` and
`SkillRegistry.call()` — never off the `on_event` stream.**
*Rationale:* the event stream is lossy on purpose. `agent_tool_result`
truncates results to `TOOL_RESULT_EVENT_MAX = 20_000` chars before emitting,
and `make_agent_event_handler` drops results that `build_display_payload`
judges not display-worthy. Logging off it would persist a lossy copy of
exactly the data you need when debugging a failure.

**D5 — Two-tier storage.** SQLite holds structured, bounded, queryable
fields. Full payloads (complete tool arguments, complete tool results, the
complete final reply) go to one JSONL file per run.
Previews stored in SQLite are capped at **`PREVIEW_CHARS = 2000`**.
*Rationale:* keeps `jarvis.db` small and fast to query while losing nothing.
A single large tool result (web search, git diff, file read) would otherwise
bloat a row and, via the FTS triggers on neighbouring tables, the whole file.

**D6 — Every run-log write is best-effort and silent on failure.** Wrap in
`try/except Exception`, log once at WARNING with the run_id, continue.
*Rationale:* constraint §0.2. A disk-full or permissions problem must degrade
Mortimer to "no logs," never to "no voice."

**D7 — Writes are synchronous `sqlite3` from the async path, and the JSONL
file is written once at run end, not appended per event.**
*Rationale:* synchronous SQLite matches the existing convention (`_persist()`
in `transcript_log.py` already does exactly this inside the pipeline) and a
local WAL insert is sub-millisecond. Buffering the JSONL in memory and doing
one `write_text()` at run end keeps syscalls out of the tool-call hot path.
The buffer is bounded — see D8.

**D8 — Buffer bounds.** A run buffers at most **`MAX_BUFFERED_EVENTS = 200`**
events and **`MAX_PAYLOAD_BYTES = 5_000_000`** of payload. On exceeding
either, further payloads are replaced with the literal string
`"<dropped: run payload cap exceeded>"` and the run's JSONL gains a final
`{"type": "truncated", ...}` record. SQLite rows are unaffected.
*Rationale:* `MAX_TOOL_ITERATIONS = 5` bounds a normal run to well under 200
events, so this cap only fires on pathological runs — where it prevents a
runaway tool from exhausting memory.

**D9 — Status taxonomy and orphan handling.** `agent_runs.status` is written
as `running` on insert, then updated to exactly one of:
- `ok` — the run returned a reply not starting with `FAILED:`
- `timeout` — the reply equals `base.TIMEOUT_MESSAGE`
- `failed` — any other reply starting with `FAILED:`

A run whose process died mid-flight stays `running` forever. **Readers (CLI
and API) display any `running` row whose `started_at` is older than
`ORPHAN_AFTER_S = 300` as `orphaned`. The stored row is never rewritten.**
*Rationale:* no background reaper, no startup hook, no risk of a genuinely
long-running job being mislabeled in storage. Purely a presentation rule, so
it is idempotent and cannot corrupt data.

**D10 — Retention pruning runs once at bot startup.** Controlled by
`JARVIS_RUNLOG_RETENTION_DAYS`, default **30**. Deletes `agent_runs` and
`agent_events` rows with `started_at` older than the window, and removes
`logs/agents/<date>/` directories older than the window. Best-effort; logs a
single INFO line with counts. Setting the value to `0` disables pruning.
*Rationale:* startup is the only moment guaranteed to happen regularly, to be
outside the latency-critical path, and to require no scheduler.

**D11 — Log-file rotation happens in `scripts/mortimer.sh`, not in
`jarvis/logging_config.py`.** Before starting components, the script rotates
`logs/<name>.log` → `logs/<name>.log.1` → … keeping
**`LOG_GENERATIONS = 5`**, then starts with `>>` (append) instead of `>`.
*Rationale:* §1.7 — the majority of Mortimer's runtime diagnostics are
`print()` to stdout, which a Python `logging.FileHandler` would not capture.
Only shell-side redirection sees all of it. This also fixes the
restart-wipes-the-log bug with no Python changes and keeps
`scripts/latency_probe.py logs/bot.log` working exactly as before.

**D12 — Three review surfaces, all read-only:**
- **CLI:** `python -m jarvis.runlog` with `--agent`, `--status`, `--since`,
  `--limit`, `--run <id>`, `--json`.
- **Admin sidecar:** `GET /api/runs` (filtered list) and
  `GET /api/runs/{run_id}` (detail, including the JSONL payload).
- **Console:** `RunsPanel.tsx`, opened by a topbar button, following the
  existing `MemoryPanel` + `.git-popover` pattern exactly.

*Rationale for the sidecar owning the HTTP surface:* the admin server already
reads `jarvis.db` directly for `/api/memory`, already has the CORS allowance
for `:5173`, and is already the pattern every console panel uses. Putting run
endpoints on the bot instead would add an HTTP surface to the voice process
for no benefit.

**D13 — The module is `jarvis/runlog/`, and the vocabulary is "run log" /
"agent run" throughout.** Not `jarvis/logging/` (shadows stdlib on the import
path) and not anything containing "skill".
*Rationale:* `mcp_servers/*/skill.yaml`, `jarvis/skills/registry.py`, and
`scripts/check_skills.py` already use "skill" to mean "an MCP server." A
second meaning would confuse every future reader, human or model.

**D14 — No redaction in this phase.** Tool arguments and results are stored
verbatim. `logs/` is gitignored and `data/*.db` is gitignored, so nothing
reaches the repository. This is a **known, accepted gap**, and §9 records it.
*Rationale:* redaction rules written before seeing real log volume are
guesswork. Revisit once there is a corpus to inspect.

**D15 — The Runs panel is read-only.** No delete button, no re-run button.
*Rationale:* deletion is what retention pruning is for; a re-run button would
be a new action surface with its own confirmation-gate questions, which is out
of scope.

**D16 — `session_id` is threaded as an explicit parameter, not via the
ContextVar.** `build_delegate_tool(...)` gains a keyword-only
`session_id: str | None = None`; `build_pipeline` passes
`session_id=runtime.session_id`; the delegate handler passes it into
`agent.run(...)`, which gains a keyword-only `session_id: str | None = None`
and hands it to the `RunLogger`.
*Rationale:* `session_id` is known statically at pipeline-build time and never
changes for the life of a session, so a ContextVar would be machinery for
nothing. Callers that do not supply it (the CLI REPL in
`jarvis/agents/supervisor.py`, `tests/evals/sub_agent_evals.py`, direct unit
tests) get `NULL`, which is correct — those runs genuinely have no voice
session. Without this thread, `agent_runs.session_id` would always be `NULL`
and the `idx_agent_runs_session` index would be dead weight.

**D17 — The kill switch is a `RunLogger` constructor parameter.** The full
signature is fixed in §5.3 and includes `enabled: bool = True`. `SubAgent`
passes `enabled=self._settings.jarvis_runlog_enabled`. When `False`, every
method returns immediately, `start()` performs no insert, and `finish()`
writes no file.
*Rationale:* keeps `RunLogger` free of any dependency on `Settings` or global
config, so unit tests can construct one with three positional arguments and no
environment. This resolves the contradiction between the old §5.3 signature
and §5.7.

**D18 — `tool_result.ok` uses the documented prefix heuristic, and the
authoritative signal lives on the `mcp_call` event.** `SubAgent` derives
`ok = not result.startswith(f"{tool_name} failed:")` and
`not result.startswith("Unknown tool ")` and
`not result.startswith(f"Tool '{tool_name}' is not available")` — the three
failure strings `SkillRegistry.call()` can return. `SkillRegistry` itself
knows the true outcome and records it on its own `mcp_call` event, which is
never a heuristic.
*Rationale:* `call()` returns a bare string by locked Phase 2 contract, so a
caller genuinely cannot do better than string matching, and changing the
return type is out of scope. Rather than pretend the heuristic is exact, the
plan places an exact signal one layer down where it is free. A reader
comparing a `tool_result` marked `ok=1` against an `mcp_call` marked `ok=0` is
seeing a tool that failed in a way its own text disguised — which is useful
information, not a defect. The implementing model must add a comment in
`base.py` saying exactly this, so the imprecision is never mistaken for a bug.

**D19 — The JSONL payload schema is fixed.** Every line is one JSON object
with a `type` field and a `seq` field (integer, starting at 0, incrementing
across all records in the run including `run_start` and `run_end`). Exact
shapes are in §5.3a. Consumers (CLI §5.10, API §5.11, panel §5.12) must read
only these fields.
*Rationale:* three separate consumers read this file. An unspecified format
would have produced three incompatible readers.

**D20 — One SQLite connection per write, and `since` is normalized to an ISO
string at the edge.** `RunLogger` opens a connection per write via
`get_conn()` and closes it, matching `_persist()` in
`jarvis/bot/transcript_log.py`. A shared `parse_since(value: str | None) ->
str | None` in `jarvis/runlog/store.py` converts `Nd`/`Nh`/`Nm`/ISO-8601 into
a UTC ISO string; both the CLI and the admin endpoint call it, and
`list_runs(since=...)` accepts only the normalized ISO string.
*Rationale:* per-write connections avoid holding a handle across `await`
points (a long-running run would otherwise pin a connection for its whole
lifetime, and WAL readers would see a stale snapshot). One parser in one place
means the CLI and the panel cannot disagree about what `2d` means.

---

## §4 Files that will change

**New:**

| Path | Purpose |
|---|---|
| `jarvis/runlog/__init__.py` | Public re-exports |
| `jarvis/runlog/context.py` | `current_run_id` ContextVar + helpers (D3) |
| `jarvis/runlog/store.py` | `RunLogger` class; SQLite + JSONL writes; read helpers |
| `jarvis/runlog/prune.py` | Retention pruning (D10) |
| `jarvis/runlog/cli.py` | `python -m jarvis.runlog` (D12) |
| `jarvis/runlog/__main__.py` | Thin `from .cli import main; main()` |
| `web/src/components/RunsPanel.tsx` | Console review panel |
| `web/src/runs.css` | Panel styling |
| `tests/unit/test_runlog_store.py` | Store write/read, previews, caps, status taxonomy |
| `tests/unit/test_runlog_context.py` | ContextVar isolation under concurrency |
| `tests/unit/test_runlog_prune.py` | Retention window behavior |
| `tests/integration/test_runlog_end_to_end.py` | Delegation → rows + JSONL |
| `tests/acceptance/run-logging.md` | Manual checklist |

**Modified:**

| Path | Change |
|---|---|
| `jarvis/db.py` | `MIGRATION_0006` + `MIGRATIONS` entry |
| `jarvis/config.py` | 2 new settings |
| `jarvis/agents/base.py` | `run_id` param; source-level logging; sets ContextVar |
| `jarvis/agents/delegate.py` | Generates `run_id`; adds it to events |
| `jarvis/skills/registry.py` | Records `mcp_call` events |
| `jarvis/bot/pipeline.py` | Startup prune; `run_id` passthrough |
| `jarvis/admin/server.py` | `GET /api/runs`, `GET /api/runs/{run_id}` |
| `web/src/App.tsx` | Topbar button + panel mount |
| `scripts/mortimer.sh` | Log generation rotation; `>>` redirect |
| `.env.example` | 2 new vars, documented |
| `CLAUDE.md` | Run log section |

---

## §5 Implementation steps

### 5.1 — Schema (`jarvis/db.py`)

Append `MIGRATION_0006` and add `("0006_agent_runs", MIGRATION_0006)` to the
end of the `MIGRATIONS` list. Do not modify any existing migration string.

```sql
CREATE TABLE IF NOT EXISTS agent_runs (
  run_id TEXT PRIMARY KEY,
  session_id TEXT,
  agent TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  task TEXT NOT NULL,
  status TEXT NOT NULL,              -- running | ok | failed | timeout
  started_at TEXT NOT NULL,
  ended_at TEXT,
  latency_ms INTEGER,
  tool_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,                        -- the FAILED: reason, else NULL
  reply_preview TEXT,                -- first PREVIEW_CHARS of the reply
  payload_path TEXT                  -- repo-relative path to the JSONL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent  ON agent_runs(agent, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status, started_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_session ON agent_runs(session_id);

CREATE TABLE IF NOT EXISTS agent_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  type TEXT NOT NULL,                -- tool_call | tool_result | mcp_call
  tool TEXT,
  server TEXT,                       -- MCP server name; mcp_call only
  ok INTEGER,                        -- 1 | 0 | NULL
  latency_ms INTEGER,
  args_preview TEXT,
  result_preview TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id, seq);
```

No FTS table and no triggers. Full-text search over run logs is not in scope;
the JSONL files are greppable and the SQLite previews are `LIKE`-searchable.

### 5.2 — `jarvis/runlog/context.py`

Exactly this surface (D3 — the ContextVar holds the **instance**):

```
current_run_logger: ContextVar[RunLogger | None]     # default None
get_run_logger() -> RunLogger | None
get_run_id() -> str | None            # convenience: logger.run_id, else None
run_logger_scope(logger: RunLogger | None) -> AbstractContextManager[None]
```

`run_logger_scope` is a `@contextmanager` that sets the var, yields, and
resets it via the token in a `finally`. Passing `None` is legal and means
"explicitly no run" — used by tests.

**Import direction:** this module must **not** import `store.py` at runtime
(that would be a cycle, since `store.py` has no need of it but
`jarvis/runlog/__init__.py` imports both). Type the ContextVar with a
`TYPE_CHECKING`-guarded import and a string annotation. No logging in this
module.

### 5.3 — `jarvis/runlog/store.py`

Module constants (these are the tuning knobs — see §6):

```
PREVIEW_CHARS      = 2000     # D5
MAX_BUFFERED_EVENTS = 200     # D8
MAX_PAYLOAD_BYTES   = 5_000_000  # D8
ORPHAN_AFTER_S      = 300     # D9
RUNLOG_DIR          = Path("logs/agents")
```

**`class RunLogger`** — one instance per run, created by `SubAgent.run()`
(§5.4, not `_loop`).

Constructor — this exact signature (D17):

```python
RunLogger(
    run_id: str,
    agent: str,
    display_name: str,
    task: str,
    *,
    session_id: str | None = None,
    enabled: bool = True,
    db_path: str | Path | None = None,
    root: Path | None = None,
)
```

`db_path` and `root` exist so tests can point at a temp DB and temp directory;
production passes neither. `root` defaults to the process CWD (the repo root
in every supported launch path), and `RUNLOG_DIR` is resolved against it.
`enabled=False` makes every method a no-op (D17).

Public attributes: `run_id`, `agent`, `session_id`, `payload_path`.

Methods, all of which must swallow every exception (D6) — wrap each body in
`try/except Exception`, log once at WARNING as
`runlog_write_failed run_id=%s op=%s error=%s`, and return:

- `start()` — inserts the `agent_runs` row with `status='running'`,
  `started_at=now_iso()`, `payload_path` computed as
  `logs/agents/<YYYY-MM-DD>/<run_id>.jsonl` (date from `started_at`, UTC).
  Buffers a `run_start` record.
- `tool_call(tool, arguments)` — inserts an `agent_events` row
  (`type='tool_call'`, `args_preview` = `json.dumps(arguments, default=str)`
  truncated to `PREVIEW_CHARS`), buffers the full arguments.
- `tool_result(tool, result, latency_ms, ok)` — inserts `type='tool_result'`
  with `result_preview` truncated, buffers the full result. `ok` is the
  heuristic from D18.
- `mcp_call(tool, server, ok, latency_ms, error=None)` — inserts
  `type='mcp_call'` and buffers an `mcp_call` record. Called by
  `SkillRegistry.call()`, which reaches this instance through the ContextVar
  (D3).
- `finish(reply)` — derives `status` per D9, updates the `agent_runs` row
  (`ended_at`, `latency_ms`, `tool_count`, `error`, `reply_preview`), buffers
  a `run_end` record, then writes the JSONL file **once** (D7), creating the
  date directory as needed. Idempotent: guarded by a `_finished` flag, so the
  second call returns immediately (§5.4 requires this).

**Sequence numbering:** a single `_seq` counter, starting at `0`, shared by
every buffered record *and* every `agent_events.seq` value. `run_start` is
always `seq=0`. This means `agent_events.seq` values are non-contiguous
(they skip the `run_start`/`run_end` numbers), which is intended — it lets a
reader interleave SQLite rows and JSONL records into one ordered timeline.

`tool_count` is the number of `tool_call` events recorded, not the number of
iterations.

`error` is populated only when `status != 'ok'`, and holds the full reply
string truncated to `PREVIEW_CHARS` (the reply *is* the error in the
`FAILED: …` contract).

**Connection handling (D20):** every write calls `get_conn(self._db_path)`,
executes, commits, and closes. Never hold a connection across an `await`.

### 5.3a — The JSONL payload schema (D19)

One JSON object per line. `seq` is the shared counter from §5.3. Times are
`now_iso()` UTC strings. These five shapes are exhaustive; do not invent
others.

```jsonc
{"type":"run_start","seq":0,"run_id":"<uuid>","agent":"developer",
 "display_name":"Developer","session_id":"<uuid|null>","task":"<full text>",
 "started_at":"<iso>"}

{"type":"tool_call","seq":1,"tool":"git_status","arguments":{...},
 "at":"<iso>"}

{"type":"tool_result","seq":2,"tool":"git_status","ok":true,
 "latency_ms":142,"result":"<full untruncated text>","at":"<iso>"}

{"type":"mcp_call","seq":3,"tool":"git_status","server":"mcp_git",
 "ok":true,"latency_ms":138,"error":null,"at":"<iso>"}

{"type":"run_end","seq":9,"status":"ok","latency_ms":2310,
 "tool_count":2,"reply":"<full untruncated text>","error":null,
 "ended_at":"<iso>"}
```

Plus one optional record, appended only when a D8 cap trips:

```jsonc
{"type":"truncated","seq":<n>,"reason":"events"|"bytes",
 "dropped_after_seq":<n>,"at":"<iso>"}
```

When a cap has tripped, subsequent `arguments`, `result`, and `reply` values
are replaced with the literal string
`"<dropped: run payload cap exceeded>"`. SQLite previews are unaffected —
they are bounded by `PREVIEW_CHARS` regardless.

**Read helpers** (used by both the CLI and the admin endpoints, so the orphan
rule from D9 and the `since` parsing from D20 live in exactly one place):

```
parse_since(value: str | None) -> str | None     # "2d"|"6h"|"30m"|ISO -> ISO
list_runs(agent=None, status=None, since=None, limit=50,
          db_path=None) -> list[dict]
get_run(run_id, db_path=None, root=None) -> dict | None
_display_status(row, now) -> str                 # applies D9 orphan rule
```

`since` passed to `list_runs` must already be normalized — callers call
`parse_since` first. An unparseable value makes `parse_since` return `None`
(meaning "no lower bound"); it never raises.

`list_runs` returns dicts whose `status` field has already had the orphan rule
applied, newest first, ordered by `started_at DESC`. Filtering by
`status='orphaned'` is supported and is applied **after** the orphan rule, in
Python, not in SQL.

`get_run` returns `{"run": {...}, "events": [...], "payload": [...]}` where
`payload` is the parsed JSONL (empty list if the file is missing — pruned or
never written) and a malformed line is skipped rather than raising.

### 5.4 — `jarvis/agents/base.py`

New signature (D1, D16) — both new parameters keyword-only:

```python
async def run(self, task: str, on_event: EventCallback | None = None, *,
              run_id: str | None = None,
              session_id: str | None = None) -> str:
```

When `run_id` is `None`, generate `str(uuid.uuid4())` (D1).

`run()` — not `_loop` — does all of the following, in this order:

1. Resolve `run_id`, construct the `RunLogger` with
   `enabled=self._settings.jarvis_runlog_enabled` (D17) and the resolved
   `session_id` (D16), and call `start()`.
2. Enter `run_logger_scope(runlog)` (D3) around the **entire**
   `asyncio.wait_for(...)` call, so the ContextVar is set for every MCP call
   the loop makes, including ones still in flight when a timeout fires.
3. In the success path, call `runlog.finish(reply)` before returning.
4. In **both** `except` branches (`asyncio.TimeoutError` and the bare
   `Exception`), call `runlog.finish(TIMEOUT_MESSAGE)` / `finish(f"FAILED:
   {exc}")` respectively before returning — matching exactly the string the
   method returns, so `agent_runs.status` and `error` agree with what the
   Supervisor actually received.

**Why this matters:** `_loop` can be abandoned mid-flight by the `wait_for`
in `run()`, so a `finish()` placed inside `_loop` would never execute on the
timeout path and the run would sit at `status='running'` forever. `finish()`
is idempotent (§5.3), so the success path calling it and a later `except`
branch calling it again is safe.

`_loop` gains only the per-tool instrumentation: it takes the `RunLogger` as
a parameter and calls `runlog.tool_call(name, arguments)` immediately before
each `self._registry.call(...)`, times the call with `time.perf_counter()`,
and calls `runlog.tool_result(name, result, latency_ms, ok)` immediately
after, with `ok` derived per D18. Add the D18 comment there explaining why
the flag is a heuristic and where the exact one lives.

The existing `logger.info("subagent_done agent=%s latency_ms=%d")` line gains
`run_id=%s` (D11 note: message-string only, not `LOG_FORMAT`). The
`logger.warning` and `logger.exception` lines in `run()` gain the same.

Emit `run_id` on every event dict `_emit` produces (D2).

### 5.5 — `jarvis/agents/delegate.py`

`build_delegate_tool` gains a keyword-only `session_id: str | None = None`
(D16). It is captured by the closure and passed through on every delegation.

At the top of `handler()`, generate `run_id = str(uuid.uuid4())`. Add
`"run_id": run_id` to the `delegate_start` and `delegate_done` event dicts.
Call `agent.run(task, on_event, run_id=run_id, session_id=session_id)`.

The `Unknown agent` early-return path does **not** create a run — there is no
agent and nothing ran.

`jarvis/bot/pipeline.py`'s `build_pipeline` passes
`session_id=runtime.session_id` into `build_delegate_tool`. Any other caller
of `build_delegate_tool` (tests) may omit it.

### 5.6 — `jarvis/skills/registry.py`

In `call()`, wrap the existing `session.call_tool` block with a
`time.perf_counter()` measurement. After resolving the outcome — success,
timeout, exception, or `isError` — do:

```python
runlog = get_run_logger()
if runlog is not None:
    runlog.mcp_call(tool_name, server, ok=..., latency_ms=..., error=...)
```

When `get_run_logger()` returns `None`, **skip the write entirely** — an MCP
call outside a delegation has no run to attach to. This is the normal case
for the Supervisor's own direct tool calls and must not log a warning.

`ok` here is exact, not a heuristic (D18): `False` for the timeout branch, the
exception branch, and the `isError` branch; `True` otherwise. `error` carries
the same one-line reason the function returns, or `None` on success.

The unknown-tool and not-available-in-context early returns happen before any
MCP call is made, so they record **no** `mcp_call` event. `SubAgent` still
records a `tool_result` with `ok=False` for them via D18's prefix rule.

Do not change `call()`'s signature or its return values. Its existing
`logger.warning("tool_call_failed ...")` line gains `run_id=%s` sourced from
`get_run_id()`.

**Import direction:** import `get_run_logger`/`get_run_id` from
`jarvis.runlog.context` at module top. Verified safe: `context.py` imports
only `contextvars` (plus a `TYPE_CHECKING` import per §5.2), and
`store.py` imports `jarvis.db`, which imports nothing from `jarvis.skills`.
Do **not** import `jarvis.runlog.store` here. Verification step 4 in §7
guards this.

### 5.7 — `jarvis/config.py`

Two new `Settings` fields, placed with the other `jarvis_*` entries:

```
jarvis_runlog_enabled: bool = True
jarvis_runlog_retention_days: int = 30
```

When `jarvis_runlog_enabled` is `False`, `RunLogger` methods return
immediately without touching disk. This is the kill switch. It is wired by
`SubAgent.run()` passing `enabled=self._settings.jarvis_runlog_enabled` into
the constructor (D17) — `RunLogger` itself never reads `Settings` or the
environment, so unit tests can construct one with no config at all.

### 5.8 — `jarvis/runlog/prune.py` and pipeline wiring

`prune(retention_days, db_path=None, root=None) -> dict` deletes expired rows
and date directories (D10) and returns `{"runs_deleted": n, "dirs_deleted": n}`.
Returns zeros immediately when `retention_days <= 0`.

Call it once from `run_session` in `jarvis/bot/pipeline.py`, in the setup
region **before** the pipeline is built — not in the `finally` block, and not
inside any per-turn path. Wrap in `try/except`, log one INFO line with the
counts.

### 5.9 — `scripts/mortimer.sh`

Add a `rotate_log()` shell function that, for each of `bot`, `admin`, `web`:
shifts `logs/<name>.log.4` → `.5`, `.3` → `.4`, … `logs/<name>.log` → `.1`,
keeping `LOG_GENERATIONS=5`. Call it after `mkdir -p logs` and before the
`nohup` lines. Change all three redirects from `>` to `>>`.

Update the usage comment at the top of the file to mention rotation, and
update the closing `Logs:` hint to mention that previous runs are in `.1`–`.5`.

### 5.10 — `jarvis/runlog/cli.py`

```
python -m jarvis.runlog                          # last 20 runs, newest first
python -m jarvis.runlog --agent developer --status failed --since 2d
python -m jarvis.runlog --run <run_id>           # full detail incl. payload
python -m jarvis.runlog --json                   # machine-readable
```

`--since` is passed through `store.parse_since()` (D20) — the CLI does not
parse it itself. `--status` accepts `ok`, `failed`, `timeout`, `running`,
`orphaned`. `--limit` defaults to `20`.

The list view is a fixed-width table with these columns in this order: local
time (`HH:MM:SS`), run_id (first 8 chars), agent, status, latency (`1234ms`
or `-`), tool count, task (truncated to fit `shutil.get_terminal_size()`,
falling back to 100 columns).

The detail view prints the run header, then each `agent_events` row in `seq`
order, then the full JSONL payload records in `seq` order. When
`payload_path`'s file is missing it prints `(payload pruned or unavailable)`
rather than failing.

`--json` prints `list_runs(...)` output for the list view and `get_run(...)`
output for `--run`, via `json.dumps(..., indent=2, default=str)`, and
suppresses all table formatting.

Colorless plain text. No new dependencies. `main()` returns an exit code:
`0` normally, `1` when `--run <id>` matches nothing.

### 5.11 — `jarvis/admin/server.py`

Two endpoints, following the shape of the existing `/api/memory` handler
(direct call into the module, returns a plain dict, no auth — the sidecar is
localhost-only):

```
GET /api/runs?agent=&status=&since=&limit=50   -> {"ok": true, "runs": [...]}
GET /api/runs/{run_id}                          -> {"ok": true, "run": {...},
                                                    "events": [...], "payload": [...]}
```

`GET /api/runs/{run_id}` returns `{"ok": false, "error": "not found"}` with
HTTP 200 for an unknown id, matching the sidecar's existing convention of
returning `ok: false` rather than raising HTTP errors.

Both endpoints call `store.parse_since()` on the raw query value before
calling `list_runs` (D20) — the normalization must not be reimplemented here.
`limit` is clamped to `1..200` server-side. Query parameters are all
optional; empty strings are treated as absent.

The `payload` array in the detail response is the JSONL records exactly as
specified in §5.3a — no reshaping, no renaming. The panel depends on those
field names.

### 5.12 — `web/src/components/RunsPanel.tsx` + `web/src/runs.css`

Model this on `MemoryPanel.tsx` exactly: `const API = "http://localhost:7861"`,
a `refresh` callback, an `unreachable` state for when the sidecar is down, and
the same visual language.

Layout: a filter row (agent dropdown populated from `AGENT_LAYOUT` in
`web/src/agentLayout.ts` — reuse it, do not hardcode a second list; status
dropdown with the same five values as the CLI; a refresh button), then a list
of run rows. Clicking a row expands it inline to show the events and payload
from `/api/runs/{run_id}`, fetched lazily on first expand and cached in
component state.

Each collapsed row shows: status dot, agent display name, relative time
("4m ago"), latency, and the task truncated to one line. Each expanded row
adds the `agent_events` list (seq, type, tool, ok, latency) and, below it, the
JSONL payload rendered as a `<pre>` block per record.

TypeScript interfaces must mirror §5.3a's field names exactly. Declare them as
a discriminated union on `type` so `tsc` catches any drift between the panel
and the payload writer.

Status colors reuse the existing CSS variables already used by
`agentstatus.css`: `--green` for `ok`, `--red` for `failed`, `--text-dim` for
`timeout`/`orphaned`, `--accent` for `running`.

Panel sizing follows `.git-popover` (§5.13) — do not introduce a new
positioning scheme. The run list scrolls internally rather than growing the
popover.

### 5.13 — `web/src/App.tsx`

Add `runsOpen` state, a topbar button (`📋 Runs`, `title="Sub-agent run
history"`) placed after the `🧠 Memory` button, and a `{runsOpen && (<div
className="git-popover"><RunsPanel /></div>)}` block alongside the existing
three. Import `runs.css` where the other panel CSS files are imported.

### 5.14 — Docs

- `.env.example`: add both new vars with one-line comments.
- `CLAUDE.md`: add a **Run log** paragraph under *Architecture* describing the
  `run_id` → `agent_runs`/`agent_events`/JSONL chain, and add the CLI
  invocation to the *Commands* block.

---

## §6 Where the tuning knobs live

All of these live as module-level constants in `jarvis/runlog/store.py`,
marked with a `⚙ TUNING KNOB` comment. Adjust there only; do not scatter
copies into callers:

`PREVIEW_CHARS`, `MAX_BUFFERED_EVENTS`, `MAX_PAYLOAD_BYTES`, `ORPHAN_AFTER_S`.

`LOG_GENERATIONS` is a shell variable at the top of `scripts/mortimer.sh`.

Retention is a user-facing setting, not a knob:
`JARVIS_RUNLOG_RETENTION_DAYS` in `.env`.

---

## §7 Verification

**Automated — must all pass:**

1. `pytest tests/unit tests/integration -q` — green, including the new files.
2. `cd web && npm run build` — strict TS, zero errors.
3. `cd web && npm run lint` — zero warnings, zero errors.
4. `python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"` —
   the CI import smoke check, extended to cover the new package. Confirms no
   import cycle (§5.6).
5. `python scripts/init_db.py` on a **fresh** `data/` — migration 0006 applies
   cleanly from empty, and applying twice is a no-op.

**New tests must cover, at minimum:**

- `test_runlog_store.py`: a full run writes one `agent_runs` row and the
  expected `agent_events` rows; previews are truncated at `PREVIEW_CHARS`
  while the JSONL holds the untruncated value; each of the four statuses in
  D9 is derived correctly from its reply string; `finish()` twice is a no-op;
  a write failure (point `db_path` at an unwritable location) does not raise;
  `enabled=False` writes neither a row nor a file (D17); every JSONL record
  matches its §5.3a shape and the `seq` counter is strictly increasing across
  the whole run (D19); `parse_since` handles `2d`/`6h`/`30m`/ISO/garbage
  (D20); `_display_status` returns `orphaned` past `ORPHAN_AFTER_S` **without
  rewriting the stored row** (D9).
- `test_runlog_context.py`: two concurrent `run_logger_scope` blocks in
  separate `asyncio` tasks each observe their own `RunLogger` — this is the
  regression test for the parallel-delegation correlation bug from §1.4.
  Also: `get_run_logger()` outside any scope returns `None`, and the var is
  reset after the scope exits even when the body raises.
- `test_runlog_prune.py`: rows and directories inside the window survive,
  those outside are removed, `retention_days=0` is a no-op.
- `test_runlog_end_to_end.py` (integration): a real delegation through
  `build_delegate_tool` with a stub registry produces a queryable run whose
  `run_id` matches the one on the `delegate_start` event; `session_id` is
  populated when `build_delegate_tool` was given one and `NULL` when it was
  not (D16); a stub registry that records `mcp_call` through the ContextVar
  produces `mcp_call` rows **and** `mcp_call` records in the JSONL (D3 —
  this is the regression test for the hole this revision closed); a
  sub-agent whose `_loop` exceeds the timeout still lands `status='timeout'`
  rather than being stranded at `running` (§5.4).

**Manual — `tests/acceptance/run-logging.md`, to be written in this phase:**

- Trigger each of the five sub-agents; confirm one run row each, correct
  agent, non-zero latency, task text intact.
- Trigger a **failing** run (e.g. a web request with `TAVILY_API_KEY` unset);
  confirm `status='failed'`, `error` populated, and that the MCP-layer failure
  detail is visible in the run detail — the specific thing that was
  unrecoverable before this work.
- Trigger a **parallel** delegation (two specialists in one request); confirm
  two distinct runs, each with its own tool events and no cross-contamination.
- Restart Mortimer; confirm `logs/bot.log.1` now holds the previous session
  and `logs/bot.log` starts fresh.
- Confirm `python -m jarvis.runlog --status failed` surfaces the failure above.
- Confirm the Runs panel opens, filters, expands a run, and shows the same
  data as the CLI.
- Confirm the four existing panels (Repo, Edit, Memory, transcript drawer)
  and the star layout still behave exactly as before.

---

## §8 Rollback

Set `JARVIS_RUNLOG_ENABLED=false` in `.env` and restart. Every `RunLogger`
method becomes a no-op; no tables are dropped and nothing else changes. This
is the reason for the kill switch in §5.7.

Full revert is a single `git revert` of the phase branch. Migration 0006
leaves two empty tables behind, which is harmless — do not write a down
migration.

---

## §9 Risk

| Risk | Severity | Mitigation |
|---|---|---|
| **Secrets land in the run log.** Tool arguments and results are stored verbatim (D14). A tool that echoes a token, or a file read that touches `.env`, will persist it under `logs/` and in `jarvis.db`. | **Medium — accepted, not solved** | `logs/` and `data/*.db` are gitignored, so nothing reaches the repo. Recorded here as an explicit follow-up: a redaction pass should be scoped once there is a real corpus to inspect. |
| Synchronous SQLite writes in the async tool loop add latency. | Low | Local WAL inserts are sub-millisecond and this matches the existing `_persist()` convention. If it ever shows up in `latency_probe.py` output, move `RunLogger` writes to a thread executor — the class boundary makes that a local change. |
| Disk growth from JSONL payloads. | Low | `MAX_PAYLOAD_BYTES` caps a single run; retention pruning caps the corpus. |
| An import cycle between `jarvis.runlog` and `jarvis.skills`. | Low | Verified by inspection (§5.6) and guarded by verification step 4. |
| The `finish()`-on-timeout path is easy to get wrong and would silently leave `running` rows. | Medium | §5.4 now prescribes the exact placement (`run()`, not `_loop`, `finish()` in both `except` branches); D9's orphan rule makes the symptom visible rather than invisible; `test_runlog_store.py` covers double-`finish()` and `test_runlog_end_to_end.py` covers the timeout path landing `status='timeout'`. |
| Holding a `RunLogger` in a ContextVar means it is mutated from two call sites (`SubAgent` and `SkillRegistry`) within one run. | Low | Both sites are on the same `asyncio` task chain, so writes are serialized by the event loop and no locking is needed. Recorded here because it is the one non-obvious consequence of D3's revision-2 rewrite; `test_runlog_context.py` covers task isolation. |
| The Runs panel duplicates the agent list a third time. | Low | §5.12 requires importing `AGENT_LAYOUT` from `web/src/agentLayout.ts`. `tests/unit/test_agents_yaml_frontend_parity.py` already guards that file. |

---

## §10 Approval

- [x] Larry has read §2 (scope) and §3 (decisions) and approves. — 2026-08-12
- [x] Revision 2 requested and applied: close all six specification gaps so
      the plan can be implemented without design degradation. — 2026-08-12
- [x] Implementation may begin, all phases, without per-phase approval.

*(Approval covers the scope in §2 only. The three deferred items — redaction,
Supervisor-turn logging, and the skills/procedures work — are separate
decisions.)*
