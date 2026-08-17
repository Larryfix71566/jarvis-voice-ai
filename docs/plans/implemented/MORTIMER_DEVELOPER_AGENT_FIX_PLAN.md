# MORTIMER DEVELOPER AGENT FIX — implementation plan

**What the logs show** (from `data/jarvis.db` `agent_runs`/`agent_events`
and `logs/agents/2026-08-16/*.jsonl`, examined 2026-08-16): of 19
Developer runs, 6 failed, 2 timed out, 2 orphaned. The failures are not
model flakiness — they decompose into exactly three root causes, each
reproducible from a specific run:

**RC1 — protocol violation on parallel tool calls (runs `7473b493`,
`33ef825a`, both fatal 400s).** The model issued ~21 tool calls in one
assistant message. `SubAgent._loop` (`jarvis/agents/base.py`) appends
each tool-response message and, per MORTIMER_AGENT_TRUST_PLAN.md D3,
injects a `system`-role constraint message immediately after each
FAILED tool response — *inside the per-call loop*. With parallel calls
the transcript becomes `assistant(tool_calls×21) → tool₁ → system →
tool₂ → …`, and the OpenAI-compatible endpoint (Anthropic here — the
`toolu_` ids) requires every tool response to follow the assistant
message contiguously. The first interleaved system message orphans the
remaining 20 tool_call_ids; the next completion call returns 400
`"tool_call_ids did not have response messages"` and the run dies.
Single-call turns — every existing test — can never trip this.

**RC2 — `mcp-repo`'s root is a literal `${JARVIS_REPO_ROOT}` (the 21
"does not exist" failures that fed RC1).** `config/mcp_servers.yaml`
passes `JARVIS_REPO_ROOT: "${JARVIS_REPO_ROOT}"`, but that variable is
defined nowhere (not `.env`, not the run scripts), and
`expand_env_vars` (documented behavior) leaves unknown `${VAR}`s as the
literal string. The child process therefore gets the env value
`${JARVIS_REPO_ROOT}`, `_repo_root()` sees it non-empty and returns
`Path("${JARVIS_REPO_ROOT}")` — a nonexistent relative directory — and
every `repo_read_file` truthfully reports `"X does not exist"` in ~2ms.
This also explains the earlier "create a folder/markdown file" failures
(`11afb736`, `9671a959`): writes resolved against the same phantom
root. `mcp-git` is unaffected (its only yaml env var, `JARVIS_DB_PATH`,
is actually set).

**RC3 — 45s hard timeout kills plan-writing tasks (runs `28a9997e`,
`33123ffe`).** `DEFAULT_TIMEOUT_S = 45.0` in `base.py` bounds every
delegation; "create a comprehensive implementation plan document" is a
legitimate Developer task that cannot finish in 45s. The `SubAgent`
constructor already accepts `timeout_s`, but nothing wires a per-agent
value from `config/agents.yaml`.

(The 2 `orphaned` runs are the bot process being restarted mid-run —
`reconcile_orphaned_runs()` marking them is working as designed; no
action.)

**Ground rule (same as every plan in this repo):** every decision below
has already been made. Implement it exactly as written; if something is
genuinely undecided, that is a defect in this document — stop and
report it rather than choosing.

---

## §1 Decisions

### F1 — Batch-safe D3: constraints after the tool block, never inside it

In `SubAgent._loop`, the per-call `messages.append({"role": "system",
...})` moves OUT of the tool_calls loop. During the loop, failures are
collected as `(tool_name, error)` pairs; after ALL tool-response
messages for the batch have been appended (contiguity restored), ONE
system message is appended covering every failure in the batch:

- one failure → exactly today's `TOOL_FAILURE_CONSTRAINT_TEMPLATE`
  text, unchanged;
- multiple failures → the same template's obligations stated once,
  preceded by one line per failed tool: `"- {tool_name}: {error}"`
  (new `TOOL_FAILURES_BATCH_TEMPLATE`, built from the same wording —
  do not fork the constraint's substance).

D3's freshness property is preserved — the constraint is still the last
thing the model sees before its next turn. Amend the D3 comment in
`base.py` and add one sentence to MORTIMER_AGENT_TRUST_PLAN.md's D3
section: "amended 2026-08-16: injected after the batch's tool-response
block, not between tool responses — interleaving violated the
tool-message contiguity the OpenAI protocol requires when a turn makes
parallel calls."

Tests (`tests/unit/test_subagent.py`): a fake LLM returning one
assistant message with 3 parallel tool calls (mixed ok/failed) — assert
the resulting message sequence is `assistant, tool, tool, tool, system`
with no system message between tool messages, and that every
`tool_call_id` in the assistant message has a matching tool response;
an all-fail parallel case asserting the single batch constraint names
every failed tool.

### F2 — Kill the phantom root; make both repo servers immune

1. `config/mcp_servers.yaml`: DELETE the `env:` block from the
   `mcp-repo` entry (leave `env: {}` like `mcp-time`). The registry
   builds child env as `dict(os.environ)` + entries, so a user-exported
   `JARVIS_REPO_ROOT` still reaches the child without the yaml line —
   the line added nothing but the literal-placeholder hazard.
2. Harden `_repo_root()` in BOTH `mcp_servers/mcp_repo/logic.py` and
   `mcp_servers/mcp_git/logic.py` (same function, same comment saying
   they mirror each other): treat a value that is empty, whitespace, or
   contains `"${"` as unset and fall back to
   `Path(__file__).resolve().parents[2]`. Defense in depth for any
   future `${VAR}` leak through any config path.
3. `.env.example`: document `JARVIS_REPO_ROOT` under "Misc overrides"
   as an optional override that is normally unset.
4. CLAUDE.md "Known deviations and gotchas": one bullet naming the
   trap — `expand_env_vars` leaves unknown `${VAR}` literal by design,
   so a `config/mcp_servers.yaml` env entry referencing an unset
   variable hands the child a literal `${VAR}` string; don't reference
   variables that aren't guaranteed present.

Tests: unit — `_repo_root()` with `JARVIS_REPO_ROOT='${JARVIS_REPO_ROOT}'`
falls back to the real root (both servers' logic modules); integration
(`tests/integration/test_registry.py`) — a registry-spawned `mcp-repo`
`repo_read_file("README.md")` round-trip succeeds (this exact test
would have caught RC2 before it ever reached a live run).

### F3 — Per-agent timeout from config, Developer gets 120s

`config/agents.yaml` gains an optional per-agent `timeout_s` key;
`load_sub_agents` passes it to the `SubAgent` constructor (which
already accepts `timeout_s`); absent = today's `DEFAULT_TIMEOUT_S`
(45.0, unchanged). Set `timeout_s: 120` on `developer` only — its
legitimate tasks (multi-file review, plan drafting) are the outlier;
snappy voice-loop agents stay at 45. The 5-tool-iteration cap is
deliberately NOT raised here — none of the observed failures hit it,
and raising limits speculatively is how budgets stop meaning anything.

Config-vs-code boundary respected: the knob lives in `agents.yaml`
(the routing/capability source of truth), not Python.

Tests: `load_sub_agents` parses `timeout_s` and defaults correctly
(unit, wherever its existing loader tests live).

### F4 — What this plan deliberately does NOT do

- No retry-on-400 wrapper: RC1 is deterministic; fix the transcript,
  don't paper over it.
- No cap on parallel tool calls: with F1 the batch is protocol-safe,
  and 21 parallel reads was a *reasonable* plan for "summarize 21
  files" — the failure was ours, not the model's.
- No change to `expand_env_vars`' unknown-var semantics: its
  leave-literal behavior is documented and load-bearing elsewhere;
  F2's hardening makes the consumers immune instead.
- No orphaned-run changes (working as designed).

---

## §2 Files

**Modified:**
- `jarvis/agents/base.py` — F1 (batch constraint + comment rewrite,
  new `TOOL_FAILURES_BATCH_TEMPLATE`)
- `MORTIMER_AGENT_TRUST_PLAN.md` — F1's one-sentence D3 amendment
- `config/mcp_servers.yaml` — F2.1
- `mcp_servers/mcp_repo/logic.py`, `mcp_servers/mcp_git/logic.py` —
  F2.2 `_repo_root()` hardening
- `.env.example`, `CLAUDE.md` — F2.3/F2.4
- `config/agents.yaml`, `jarvis/agents/base.py` (`load_sub_agents`) —
  F3
- `tests/unit/test_subagent.py`, `tests/unit/test_mcp_repo_logic.py`,
  `tests/unit/test_mcp_git_logic.py`,
  `tests/integration/test_registry.py` — per above

---

## §3 Implementation order

1. F2 (config + hardening + tests) — restores repo reads, the biggest
   user-visible breakage, and is independent of F1.
2. F1 (batch-safe D3 + tests).
3. F3 (timeout wiring + tests).
4. Docs (F2.3/F2.4, trust-plan amendment); full suite; web untouched.

---

## §4 Verification

- [ ] Unit + integration suites green, including the three new test
      groups.
- [ ] Live (Larry): re-issue the exact failing request — "list all
      uncommitted modified files and summarize each" — and confirm the
      Developer reads files successfully and completes without a 400.
- [ ] Live (Larry): "create an implementation plan document …" style
      task completes within the new 120s budget (or fails for a real
      reason, not the clock).
- [ ] `python -m jarvis.runlog --agent developer --since 1d` shows the
      new runs `ok`.

---

## §5 Rollback

F1 is a transcript-ordering change guarded by unit tests — revert
`base.py` to restore old behavior. F2.1/F2.2 revert independently
(re-adding the yaml line reintroduces the bug; the hardening alone
would then mask it — revert both or neither). F3 reverts by deleting
the yaml key.

---

## §6 Approval

**Implementation status (2026-08-16): implemented, §3 steps 1–4
complete.** Full suite green (876 passed, up from 865 — the new F1/F2/F3
test groups). F2's registry round-trip (`repo_read_file("README.md")`
through a spawned mcp-repo) passes — the test that would have caught
RC2. §4's two live items remain for Larry: re-issue the failing
"list/summarize uncommitted files" request and a plan-writing task, then
check `python -m jarvis.runlog --agent developer --since 1d`.

- [ ] Larry approves.
- [ ] Implementation may begin.
