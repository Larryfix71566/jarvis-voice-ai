# Mortimer — self-service access and sub-agent recovery: implementation specification

**Status:** IMPLEMENTATION SPECIFICATION, 2026-09-22. Nothing implemented.

- **Implements:** `docs/plans/MORTIMER_SELF_SERVICE_ACCESS_AND_RECOVERY_PLAN.md`, which holds the evidence and the why. This document is the *how*.
- **Written against:** `main` @ `88b206f`.
- **Written for:** any capable coding model (Codex, Claude, or another) working in a normal checkout with a human merging each PR.
- **Goal:** an implementer that follows it task by task needs to make no design decisions. Every decision is either locked here or marked **STOP**, meaning ask Larry.

---

## 0. Rules for the implementer (read before any task)

- **R1. Do not redesign.** Sections 1–2 are locked. If a locked decision looks wrong once you are in the code, stop and write down why (§9). Do not "improve" it silently.
- **R2. One task, one commit; one phase, one PR.** A commit message names its task ID (for example `T1.1`). Phases run in order, and a phase starts only after the previous phase's PR is merged and deployed.
- **R3. Anchor by quoted text, not line numbers.** Line numbers here are correct at `88b206f` and will drift. Every change names the function or quoted string it attaches to; find it by searching.
- **R4. Tests first where a behavior changes.** Write the failing test named in the task, see it fail, then implement. Never weaken, skip or delete an existing assertion to get green. If an existing test pins behavior this spec deliberately changes, the task says so and names the test. Any other failing test is a defect in your change.
- **R5. Every task ends with its Verify block.** Run exactly those commands. A task is done only when they pass. Paste the output into the PR description.
- **R6. Verify external facts on the Mac.** Where a task depends on something outside this repo (a provider endpoint's shape, a CLI flag), it has a **Step 0** that verifies it by running something on Larry's Mac. Record the output in the PR, and if it contradicts the spec, stop (R1).
- **R7. Secrets never cross a boundary.** No tool result, log line, receipt, exception message or notice may contain a key value, an `Authorization`/`x-api-key` header, or a vault payload. Key names (`ANTHROPIC_API_KEY`) are fine.
- **R8. One implementation per fact.** Do not write a second registry loader, a second key probe, a second provider classifier or a second tool-success judge. Reuse the ones named in §3. This is the codebase's most repeated rule (`CLAUDE.md`), and nearly every past regression broke it.
- **R9. Kill switches have exactly one enforcement point** and default as stated. When a switch that gates a **voice (Supervisor) tool** is off, the feature is absent: no tool registered, no schema in the menu, no prompt addendum. MCP tools cannot be unregistered at runtime, so an MCP tool whose feature is off stays registered and returns the sidecar's `"... disabled"` error.
- **R10. Self-edit tiers.** Several files here are Tier 0 (`deny`) in `config/self_edit_allowlist.json`:
  - `jarvis/skills/registry.py`, `jarvis/admin/**`, `jarvis/db.py`
  - `tests/unit/test_requires_env_snapshot.py`, `tests/unit/test_agent_isolation.py`
  - `skills/**`, `macos/**/scripts/**`, `**/*.plist`

  Mortimer's own self-edit loop cannot make these changes. That is expected: this spec is carried out by an external implementer, and every PR is merged by Larry. Do not change the allowlist to make the work possible.
- **R11. Run the full suites before every PR:** `pytest tests/unit -q`, `pytest tests/integration -q`, `python scripts/check_skills.py`, and `swift test` for both packages when Swift changed. Baseline at `88b206f` on Linux (Python 3.11, `requirements-lock.txt`): **unit 2526 passed; integration 110 passed, 4 skipped.**
- **R12. Docs in the same PR.** When behavior changes, update `CLAUDE.md` and `docs/ARCHITECTURE.md` in the same PR. Keep `docs/REPO_MAP.md` ≤ 8000 characters and `docs/ARCHITECTURE.md` ≤ 12000.
  - Those are the injection caps in `jarvis/repo_map.py`, which **silently truncates** past them; no test checks the real files, so measure with Python `len()`, not `wc -c`.
  - At `88b206f`, `docs/ARCHITECTURE.md` is 13,770 characters, already over. The unmerged branch `docs/reconcile-status-88b206f` brings it to 11,493 and `REPO_MAP.md` to 7,468. Merge that branch before P2, or trim both as part of T2.7.

---

## 1. Locked decisions

| ID | Decision | Source |
|---|---|---|
| L1 | The user is not technical. Mortimer never hands the user a terminal command for data its own processes can read. `show_commands` is used only when the user explicitly asks for commands, or when the data exists only outside Mortimer's reach (for example, a page behind the user's own browser login). | Larry, 2026-09-22 |
| L2 | Status data is computed in the **admin sidecar**, which already loads the vault (`inject_env` at module top of `jarvis/admin/server.py`), holds the device location (`POST /api/location`) and owns stateful services. The voice tool and the MCP tools are thin HTTP clients of it, so secrets never enter MCP child processes. | Architecture: same pattern as `mcp_selfedit` → sidecar |
| L3 | Provider coverage is **derived from configuration, never a hardcoded list**. Every provider, route and credential in `config/upgrade_models.yaml`, `config/model_access.yaml`, the voice `OPENAI_*` settings and the service keys is discovered. A provider with no catalog adapter is reported as a coverage gap, and a unit test fails on the real config if one exists. | Larry, 2026-09-22 ("ensure we get everything we have configured") |
| L4 | Provider catalogs are fetched **on request and once daily**. | Larry, 2026-09-22 |
| L5 | Subscription probes (Claude and Codex CLIs) run **on request and once daily**. Each probe uses a small amount of subscription quota. | Larry, 2026-09-22 |
| L6 | The registry split (`docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md`) is carried out as written, with the amendments in P5. | Larry, 2026-09-22 |
| L7 | A structured sports-scores source is added, after the source is verified (P6, Step 0). | Larry, 2026-09-22 |
| L8 | The Supervisor answers status questions with **one direct tool, `system_status`** (no delegation). The developer and systems agents get the same data plus log search and GitHub reads through a new MCP server, `mcp-status`. | This spec |
| L9 | The retry guard keeps its purpose (refuse a reworded retry of a failed approach). It adds exactly one exemption: a **single-word input substitution**, where the new task drops **exactly one** content word of the failed task and adds at least one new one. Checked against every existing refusal fixture in `tests/unit/test_delegate.py`: all still refused; both 09-22 Alpharetta retries exempted. | This spec (refines the plan's D1) |
| L10 | Sub-agents that lack a tool write `MISSING-TOOL:`, not a command for the user. `NEEDS-INPUT:` stays, and is only for a choice that only the user can make. | Larry, 2026-09-22 |
| L11 | One `SkillRegistry` per **process**, not per session. Each MCP server lives in its own owner task, is restarted once when its process dies, and a server that fails to start never stops the others. | Evidence §3.4 |
| L12 | Results that finish after a session ends, and daily-job findings, go to a persistent **notice outbox** and are spoken once, after the greeting, at the next connect. | Evidence §3.5 |
| L13 | No new self-edit capability for sandbox branch syncing until the current failure mode is reproduced (T4.7 is verify-only). | Evidence §3.8 |
| L14 | Mortimer's own display of status (display window cards) is out of scope for this spec. Tools return text for the voice model. | Scope control |

---

## 2. Invariants (must hold after every task)

- **I1.** No key material in any output (R7). A unit test per new module asserts that a fixture key string never appears in any returned payload or log record.
- **I2.** Status tools never write. The one exception is the subscription probe, which spends quota. It is rate-limited (10 minutes per `(which, model)` unless `force=true`), and its tool description says it uses quota.
- **I3.** Anything that leaves the machine is blocked on a sensitive turn: `mcp-status` joins `EXTERNAL_TOOL_SERVERS`. The direct tool `system_status` checks `current_sensitive_turn` itself and refuses the `catalog` and `subscription` topics on an armed turn (GitHub reads exist only in `mcp-status`, which the registry already blocks), using the registry's wording (`"... failed: protected turn cannot call external tool server."`).
- **I4.** Status facts are computed in code; the model only relays them. Summaries are built by pure functions (`jarvis/status/summaries.py`) from payloads, never by an LLM call.
- **I5.** "Configured" and "available" are never merged. Every model-availability statement names its source: `registry`, `catalog:<provider>@<fetched_at>` or `probe:<which>@<time>`.
- **I6.** One registry loader (`jarvis.agents.upgrade_agent.load_model_registry`), one key probe (`scripts/check_env.py:model_key_probe` via `jarvis.keyhealth`), one provider classifier (`jarvis.usage_ledger.provider_from_base_url`), one tool-success judge (`jarvis.toolresult.classify_tool_result`).
- **I7.** Kill switches default **on** except where stated. Each is read in exactly one function.
- **I8.** The structural changes stay reversible by kill switch for one release: the per-session registry (`JARVIS_REGISTRY_SHARED_ENABLED=false`), the substitution exemption (`JARVIS_RETRY_GUARD_SUBSTITUTION_ENABLED=false`), notices (`JARVIS_NOTICES_ENABLED=false`) and the status tools (`JARVIS_STATUS_TOOLS_ENABLED=false`). Prompt wording changes (T1.2, T1.3, T4.8) and the memory-graph fallback (T4.6) are reverted by `git revert`, not by a switch.

---

## 3. Verified facts this spec is built on

Each fact was checked at `88b206f` or on Larry's Mac on 2026-09-22.

- **3.1 The runtime checkout is not on `main`.** `~/jarvis-voice-ai-clean` is a detached HEAD at `2ccf66c`, with 118 modified or untracked files copied over it (roughly the `94a5641` app code).
  - It has **13** registry profiles and **no** `config/model_access.yaml`.
  - `main` has 14, including `codex-subscription` (`model: gpt-6-astra`).
  - So on 2026-09-22 Mortimer truthfully could not see "Codex Astra": the running code predates it.
  - `claude-fable-5-1` (or any "Fable 5.1") is configured nowhere on `main`.
- **3.2 Every configured provider, and how it could be listed today.** Only SAYGM has a catalog function.

  | Provider (source) | Credential | Base URL | Existing list code |
  |---|---|---|---|
  | anthropic (registry: claude-opus, claude-fable-5, claude-sonnet-5; synthesized voice claude-haiku-4-5 in `model_routing._resolve_model_profile`) | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1/` | none |
  | moonshot (registry: kimi-k3, kimi-k2) | `MOONSHOT_API_KEY` | `https://api.moonshot.ai/v1` | none |
  | openrouter (registry: 8 `or-*`) | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | none |
  | voice supervisor (`Settings.openai_*`) | `OPENAI_API_KEY` | `OPENAI_BASE_URL` (in this deployment it points at Anthropic) | none |
  | codex subscription (registry `codex-subscription`, no base_url or key; route `codex_subscription`) | CLI login | `subscription://codex` | none |
  | claude subscription (route `subscription`) | CLI login | `subscription://claude` | none |
  | saygm (route `saygm`) | `SAYGM_API_KEY` | `https://api.saygm.com/v1` | `jarvis.saygm.fetch_catalog()` |
  | local (route `local`) | none | none | adapter raises "local model runtime is not configured" |
  | services: Deepgram, ElevenLabs, Tavily, GitHub (`GITHUB_TOKEN`, `JARVIS_GITHUB_TOKEN`) | as named | n/a | not LLM catalogs |

  - Anthropic's `GET https://api.anthropic.com/v1/models` answers 401 `"x-api-key header is required"` without a key, and 401 `"Invalid bearer token"` with a Bearer header (tested 2026-09-22 from the cloud workspace). It needs `x-api-key`, not Bearer. `CLAUDE.md` ("Key validity") records the same trap for the OpenAI-compatible layer.
  - OpenRouter, Moonshot, OpenAI, SAYGM, ESPN and MLB endpoints were **not reachable** from the cloud workspace (egress). Their shapes are verified in Step 0 on the Mac.
- **3.3 Retry guard.** The state (`last_failure`, `awaiting_user`, `handoff_depth`) is closure-local in `build_delegate_tool` (`jarvis/agents/delegate.py`). Tokens come from `jarvis.procedures._tokens`: lowercase `[a-z0-9]+`, length ≥ 3, stopwords removed. The overlap score divides by the **smaller** set.
  - On 2026-09-22 at 21:53 the failed "Get current weather for Alfreda, Georgia." was followed by "Get current weather for Alpharetta, Georgia." (overlap 0.75), and then by a longer Alpharetta request. **Both were refused** (`delegate_retry_guard_refused agent=analyst overlap=0.75`).
- **3.4 Registry and MCP children.**
  - Construction: `SkillRegistry` is created and started inside `run_session` (`jarvis/bot/pipeline.py`, `registry = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")`) and stopped in its `finally` after `drain_detached`.
  - Measured 2026-09-22 (cloud workspace, `mcp==1.29.0`, `anyio==4.14.2`):
    - **(a)** After an MCP child process is killed, `ClientSession.call_tool` raises `anyio.ClosedResourceError`, and every later `registry.call` returns `"<tool> failed: ClosedResourceError."` forever. Nothing restarts the child.
    - **(b)** 20 concurrent `registry.call`s on one session all succeeded.
    - **(c)** `registry.stop()` called from a different asyncio task than `start()` logs `registry_stop_error: Attempted to exit cancel scope in a different task than it was entered in`. **The contexts must be entered and exited in the same task**, which is why L11 uses owner tasks.
  - `start()` stops everything and re-raises if any single server fails.
- **3.5 Late results.** `late_delivery["fn"]` is never cleared at teardown, and `inject_late_result` has no liveness check. A result that lands after the session ends goes to a dead pipeline, or is logged `delegate_late_result_undeliverable` when no hook exists. It is never spoken.
- **3.6 Key health.**
  - `jarvis.keyhealth.start_background_probe()` is called inside `run_session`, so it runs once per session start. Nothing re-probes during a session.
  - Verdicts: `ok | rejected | unfunded | unreachable | unknown`.
  - `_targets(load_model_registry())` maps `codex-subscription` to `('OPENAI_API_KEY', ('', 'gpt-6-astra'))` (key env defaults to `OPENAI_API_KEY`). `probe_all` then skips it for having no `base_url`. Side effect: the voice key `OPENAI_API_KEY` is never probed.
  - Verdicts live in memory in the process that probed. Only the bot probes today; the admin sidecar has none (no `keyhealth` use under `jarvis/admin/`).
- **3.7 Supervisor tool menu.**
  - The menu is `jarvis/bot/tool_schemas.py:supervisor_tool_schemas(...)`, pinned by `tests/unit/test_tool_schemas.py` (order and an index pin: `[3] is COST_SUMMARY_SCHEMA`).
  - Registration is in `build_pipeline` (`register_supervisor_tool(llm, "cost_summary", ...)` and siblings), pinned by `tests/integration/test_bot_wiring.py::test_six_functions_registered`, an exact sorted list of 10.
- **3.8 Self-edit publication** (`sandbox/publish.py`) never runs `git push`. It publishes through the GitHub REST API with the parent fixed to the session's `source_commit`. The 2026-09-09 "non-fast-forward" failures came from the **retired** worktree implementation (replaced 2026-09-10), and no current-architecture reproduction exists.
- **3.9 Memory graph.**
  - `memory_graph_view` is on `mcp-memory` (librarian). `graph_view` is on `mcp-runlog` (developer) and deliberately excludes `memory` ("memory is the librarian's").
  - `jarvis.graphs.build()` returns `{"ok": False, "error": "no node matches '<focus>' in the <name> graph"}` when the focus is unresolved.
  - The librarian has `max_iterations` 5 (the default).
- **3.10 `AGENT_DISCIPLINE`** is 546 characters against `MAX_AGENT_DISCIPLINE_CHARS = 550`, enforced by `tests/unit/test_prompts.py::TestAgentDiscipline::test_it_fits_the_absolute_budget`.
- **3.11 New-MCP-server checklist.** This is the set of files and tests the code enforces:
  - `mcp_servers/<name>/{__init__,logic,server}.py` + `skill.yaml`. `check_skills.py` needs a bare `@mcp.tool()` directly followed by `def`, and `name` = directory with `_`→`-`.
  - An entry in `config/mcp_servers.yaml`.
  - `tests/integration/test_registry.py`: `ALL_SERVERS` in file order, and `TOTAL_TOOLS` with a changelog comment.
  - `tests/unit/test_requires_env_snapshot.py`: an `EXPECTED` row (**deny** tier).
  - `tests/unit/test_agent_isolation.py`: `OUTBOUND` if the server makes network calls (**deny** tier).
  - `if __name__ == "__main__": mcp.run()`
  - A logic unit test named in `skill.yaml` `test:`.

---

## 4. Architecture

```
                     ┌──────────────────── admin sidecar :7861 (vault loaded) ───────────────────┐
voice: system_status │ GET /api/status/{models,catalog,services,overview,build,location,logs,     │
 (direct tool, httpx)│      github}         POST /api/status/subscription/probe                  │
          │          │        │                                                                  │
          └─────────►│   jarvis/status/*  (pure logic; reuses keyhealth, load_model_registry,    │
mcp-status (thin     │        │           model_routing, saygm, subscription, GitHubClient,       │
 AdminClient) ──────►│        │           ambient_weather location)                              │
 systems, developer  └────────┼──────────────────────────────────────────────────────────────────┘
                              │
launchd com.mortimer.status-daily (06:30) → python -m jarvis.status.daily → data/status/daily-*.json
                                                                           → jarvis/notices.py outbox
bot (process-scoped): SkillRegistry (owner task per MCP server, restart-once) · notices delivered after greeting
```

New package: `jarvis/status/` (core tier)

| Module | Owns |
|---|---|
| `__init__.py` | `status_enabled()`, the single `JARVIS_STATUS_TOOLS_ENABLED` check (default on) |
| `providers.py` | provider discovery from config, and the adapter mapping (L3) |
| `catalog.py` | provider model-list fetchers, cache, registry comparison |
| `subscriptions.py` | CLI subscription probes (moved from `scripts/verify_model_access.py`, R8) |
| `models.py` | `model_access_status()` |
| `services.py` | `service_health()` |
| `overview.py` | `system_overview()` |
| `build.py` | `app_build_status()` |
| `location.py` | `current_location()` |
| `logs.py` | `log_search()` |
| `github.py` | PR and check reads |
| `summaries.py` | pure `summarize(topic, payload) -> str` for the voice tool |
| `daily.py` | the daily job entry point (`python -m jarvis.status.daily`) |

New modules elsewhere:

| File | Tier | Purpose |
|---|---|---|
| `jarvis/notices.py` | core | notice outbox |
| `jarvis/bot/status_tool.py` | core | the direct tool |
| `mcp_servers/mcp_status/` | allow | the MCP server |
| `jarvis/skills/shared.py` | allow (`jarvis/skills/**` is allow, and allow outranks core) | process-scoped registry holder |

---

## 5. Phases and tasks

Every task has five parts:

- **Files:** what it creates or changes, with the self-edit tier.
- **Spec:** exact behavior.
- **Tests:** named tests to add or change.
- **Verify:** commands to run.
- **Done when:** the finish condition.

### P0 — Prerequisite: the runtime runs `main` (Larry executes; the implementer does not)

Why: fact 3.1. Until the runtime checkout is a clean checkout of `main`, every answer about models reflects 09-17 code.

1. Back up the runtime checkout's data files: `data/jarvis.db`, `data/costs.db`, `data/secrets.vault`.
2. In a new directory, clone `main`, copy `data/` and `.env` across, and create `.venv` from `requirements-lock.txt`.
3. Run `python scripts/init_db.py`, then `python scripts/check_env.py`.
4. Point launchd at it: `python scripts/launchd_gen.py --install` from the new checkout.
5. Build the app with `macos/MortimerHost/scripts/bundle.sh`.
6. Keep the old directory for rollback.

**Done when:**
- `git -C <runtime> status --porcelain` is empty.
- `git -C <runtime> rev-parse HEAD` equals `origin/main`.
- The app's `Info.plist` `MortimerSourceRevision` equals the same hash.

---

### P1 — Recovery quick wins (fixes the two failures Larry hit on 2026-09-22)

#### T1.1 Retry guard: input substitution is not a retry

**Files:** `jarvis/agents/delegate.py` (core); `tests/unit/test_delegate.py` (allow).

**Spec:**

1. Add these constants next to the `RETRY_GUARD_*` constants:
   ```python
   RETRY_GUARD_CONTENT_TOKEN_MIN_LEN = 4
   RETRY_GUARD_SUBSTITUTION_ENV = "JARVIS_RETRY_GUARD_SUBSTITUTION_ENABLED"  # default on
   ```
2. Add a pure function next to `_shares_long_identifier`:
   ```python
   def _is_input_substitution(failed: set[str], new: set[str]) -> bool:
       """True when the new task drops EXACTLY ONE content token of the failed
       task and adds at least one content token the failed task lacked. A
       content token has len >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN. A corrected
       input (Alfreda -> Alpharetta) drops one word; a reworded retry either
       keeps every word (a superset) or rewords several (drops two or more)."""
       dropped = {t for t in failed - new if len(t) >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN}
       added = {t for t in new - failed if len(t) >= RETRY_GUARD_CONTENT_TOKEN_MIN_LEN}
       return len(dropped) == 1 and bool(added)
   ```
3. Add a single-point switch, `def _substitution_exemption_enabled() -> bool`. It reads the env var and treats `false`, `0` and `no` as off.
4. In the guard block (after the shared-identifier exemption, before the refusal), add:
   ```python
   elif overlap >= RETRY_GUARD_OVERLAP and _substitution_exemption_enabled() \
           and _is_input_substitution(prior_tokens, task_tokens):
       logger.info("delegate_retry_guard_exempted_substitution agent=%s overlap=%.2f",
                   agent_name, overlap)
   ```
5. In the refusal string, insert this sentence immediately before the fragment `"...stated here. If you "` / `"obtain NEW information..."`. Search for `obtain NEW information`; the source splits that sentence across concatenated string literals. Keep every existing sentence (tests pin them):
   ```
   Never tell the user to wait; waiting changes nothing. Change the approach or the input, or ask the user what to change.
   ```

**Tests** (new, in `TestRetryGuard`):
- `test_corrected_place_name_is_not_a_retry`: fail `"Get current weather for Alfreda, Georgia."` on analyst, then `"Get current weather for Alpharetta, Georgia."` runs.
- `test_longer_corrected_request_is_not_a_retry`: after the same failure, `"Retrieve current weather conditions for Alpharetta in Fulton County, Georgia, including temperature, conditions, humidity"` runs.
- `test_superset_rewording_is_still_refused`: fail `"Get current weather for Alfreda, Georgia."`, then `"Get current weather for Alfreda, Georgia, try harder"` is REFUSED (nothing dropped).
- `test_multi_word_rewording_is_still_refused`: the existing fixture pair in `test_reworded_retry_refused_after_failure` drops five content words; assert `_is_input_substitution` is False for it.
- `test_substitution_exemption_kill_switch`: with the env var set to `false`, the Alpharetta case is refused.
- `test_refusal_forbids_telling_user_to_wait`: `"Never tell the user to wait"` is in the refusal.

All existing `TestRetryGuard*` tests keep passing unchanged.

**Verify:** `pytest tests/unit/test_delegate.py -q`.

**Done when:** the new tests pass, and all existing guard tests pass untouched.

#### T1.2 `MISSING-TOOL:` marker and agent discipline

**Files:** `jarvis/agents/delegate.py` (core); `jarvis/prompts.py` (allow); `tests/unit/test_prompts.py`, `tests/unit/test_delegate.py` (allow).

**Spec:**

1. In `delegate.py`, add `MISSING_TOOL_MARKER = "MISSING-TOOL:"` next to `HANDOFF_MARKER`.
2. In `_execute`'s bookkeeping, compute `missing_tool = MISSING_TOOL_MARKER in result` **before** the guard-arming lines. When it is true, these rules override the `failed` handling, whether or not the result starts with `FAILED:`:
   - Do **not** arm the retry guard (pop `last_failure[agent_name]`).
   - Set `awaiting_user[agent_name] = False`.
   - Append this exact note to `result`:
     ```
     \n\n[The specialist has no tool for this. Say so plainly per rule 10 and offer to have it added through self-development. Do not show or speak commands.]
     ```
3. In `jarvis/prompts.py` `AGENT_DISCIPLINE`, replace **exactly** this sentence:
   ```
   If something is beyond your tools, do not stop at "I cannot": write NEEDS-INPUT: then the exact command and what its result would tell you.
   ```
   with **exactly** this one:
   ```
   Beyond your tools, do not stop at "I cannot": write MISSING-TOOL: and the capability; never a user command. NEEDS-INPUT: only for user choices.
   ```
   The result is exactly 550 characters (measured). Do not change any other sentence.

**Tests:**
- Rewrite `TestAgentDiscipline::test_handoff_survived_and_still_names_the_marker` to assert:
  - `'do not stop at "I cannot"'` is present;
  - `"MISSING-TOOL:"` is present;
  - `"NEEDS-INPUT:"` is present;
  - `"never a user command"` is present;
  - `"exact command"` is **absent**.
  - Rename it `test_missing_tool_replaces_the_command_handoff`.
- New `test_delegate.py::TestMissingTool`:
  - `test_missing_tool_does_not_arm_the_guard`
  - `test_missing_tool_note_appended`
  - `test_missing_tool_is_not_awaiting_user`

**Verify:** `pytest tests/unit/test_prompts.py tests/unit/test_delegate.py -q`.

**Done when:** `len(AGENT_DISCIPLINE) <= 550` and the budget test passes.

#### T1.3 Supervisor handoff wording

**Files:** `jarvis/prompts.py` (allow); `tests/unit/test_prompts.py` (allow).

**Spec:** replace the **first paragraph** of `HANDOFF_ADDENDUM` with exactly:

```
Handing work back to Larry: assume he does not use a terminal. Call show_commands only when he explicitly asks for commands, or when what is needed exists only outside your reach (a page behind his own browser login); never for anything your own tools or specialists can read. When a specialist reports MISSING-TOOL, say plainly it is something you do not have a tool for yet and offer to have it added. If you do show commands, never speak them aloud, set expect_output true when you need what it prints, and never write a shell comment (#) into a command: zsh does not treat it as a comment interactively and will try to glob the rest of the line.
```

Keep the second paragraph (continuation) unchanged.

Also append this sentence to the end of Supervisor rule 10 in `SUPERVISOR_PROMPT`, so it holds even when `JARVIS_CLIPBOARD_ENABLED=false` removes the addendum:

```
Assume the user does not use a terminal: never ask them to run a command or paste its output to get information your tools or specialists can read.
```

**Tests:**
- `TestHandoffAddendum`: the two existing tests still pass (the `"zsh"`, `"continuation"` and `"not a retry"` strings are kept).
- The three rule-10 tests (`test_supervisor_prompt_identity_and_no_hedging_rules`, `test_rule_10s_example_no_longer_names_a_specialist`, `test_the_missing_tool_case_is_still_reported_plainly`) still pass; add `test_rule_10_assumes_no_terminal`.
- Add `test_addendum_forbids_commands_by_default`: asserts `"assume he does not use a terminal"` and `"only when he explicitly asks"`.

**Verify:** `pytest tests/unit/test_prompts.py -q`.

#### T1.4 Librarian budget

**Files:** `config/agents.yaml` (allow).

**Spec:** add `max_iterations: 10` to the `librarian` entry, directly after `on_profile_fallback: refuse`, with this comment:

```
# 2026-09-22: 09-18 memory-graph run used 13 tool calls against the default 5.
```

**Tests:** new `tests/unit/test_subagent.py::test_librarian_budget_is_ten`, which loads the real config.

**Verify:** `pytest tests/unit/test_subagent.py -q`.

**P1 PR acceptance:** R11 suites green. Then Larry, live:

1. Ask "weather in Alfreda Georgia" and let it fail.
2. Say "I meant Alpharetta".
3. Weather is answered, with no "wait".

---

### P2 — Status foundation (read-only data that already exists in Mortimer's processes)

#### T2.1 `jarvis/status/providers.py`: discovery and coverage (L3)

**Files:** new `jarvis/status/__init__.py`, `jarvis/status/providers.py` (core); new `tests/unit/test_status_providers.py` (allow).

**Spec:**

1. Data type:
   ```python
   @dataclass(frozen=True)
   class ProviderRef:
       id: str              # stable: "anthropic", "openrouter", "moonshot", "openai", "saygm",
                            # "claude-subscription", "codex-subscription", "local", "voice",
                            # "deepgram", "elevenlabs", "tavily", "github", "github-selfedit"
       kind: str            # "llm" | "service"
       adapter: str         # one of ADAPTERS keys below, or "UNMAPPED"
       base_url: str | None
       credential_env: str | None
       sources: tuple[str, ...]   # e.g. ("registry:claude-opus", "route:saygm", "settings:OPENAI_BASE_URL")
       profiles: tuple[str, ...]  # registry profile names served by this provider
   ```
2. Adapter table. Every value must be implemented in T4.1, or be one of the non-fetching kinds:
   ```python
   ADAPTERS = {
       "anthropic_models":  "GET {base}/models with x-api-key + anthropic-version",
       "openai_models":     "GET {base}/models with Bearer (OpenAI-compatible)",
       "saygm_catalog":     "jarvis.saygm.fetch_catalog",
       "subscription_probe":"no list API; availability only via jarvis.status.subscriptions",
       "not_configured":    "route exists but has no runtime (local)",
       "service_health":    "not an LLM catalog; reachability only",
   }
   ```
3. `discover_providers(*, registry: dict | None = None, access: dict | None = None, env: Mapping[str, str] = os.environ) -> list[ProviderRef]`. It is deterministic, sorted by `id`, and does no network I/O.
   - **Registry.** Registry profiles come from `load_model_registry()` when `registry` is None. Group profiles that have a `base_url` by `provider_from_base_url(base_url)` (from `jarvis.usage_ledger`). Adapter mapping:
     - `anthropic` → `anthropic_models`
     - `openrouter`, `moonshot`, `openai` → `openai_models`
     - anything else (`provider_from_base_url` returns `"unknown"`) → adapter `"UNMAPPED"`, with id `f"unknown:{urlparse(base_url).hostname}"` so two unknown providers never merge
   - **Profiles without a base URL.** A profile with no `base_url` (today only `codex-subscription`) attaches to the ref for its route: `codex_subscription` when `profile["provider"] == "openai"` and `profile["name"] == "codex-subscription"`. Any other base-less profile goes to an `UNMAPPED` ref with id `f"profile:{name}"`.
   - **Access routes.** Routes come from `jarvis.model_routing.load_access_config()` when `access` is None:
     - `subscription` → `claude-subscription` / `subscription_probe`
     - `codex_subscription` → `codex-subscription` / `subscription_probe`
     - `saygm` → `saygm` / `saygm_catalog` (base_url and credential_env from the route)
     - `local` → `local` / `not_configured`
     - Any other key → `UNMAPPED`.
     - Only the **keys of `access["routes"]`** are read. `direct_api` is synthesized in code and is not a key there; do not read workload routes.
   - **Voice.** `env["OPENAI_BASE_URL"]` (default `https://api.openai.com/v1`) becomes a ref with id `"voice"`, adapter chosen by `provider_from_base_url` the same way as the registry, credential `OPENAI_API_KEY`, and source `settings:OPENAI_BASE_URL`.
   - **Services** (kind `service`, adapter `service_health`): one ref per entry of the fixed mapping `SERVICE_CREDENTIALS`, always emitted:
     ```python
     SERVICE_CREDENTIALS = {
         "deepgram": "DEEPGRAM_API_KEY",
         "elevenlabs": "ELEVENLABS_API_KEY",
         "tavily": "TAVILY_API_KEY",
         "github": "GITHUB_TOKEN",
         "github-selfedit": "JARVIS_GITHUB_TOKEN",
     }
     ```
     This tuple is the only hand-listed part, because these are not model providers.
4. `coverage_gaps(refs) -> list[str]` returns sorted ids whose adapter is `"UNMAPPED"`.

**Tests:**
- `test_real_config_has_no_coverage_gaps`: loads the real config; `coverage_gaps(...) == []`. **This is the L3 tripwire.**
- `test_unknown_provider_is_reported_as_gap`: a fixture registry with `base_url: https://api.newco.ai/v1` → the gap list contains `"unknown:api.newco.ai"`.
- `test_codex_subscription_profile_attaches_to_route`
- `test_voice_ref_follows_openai_base_url`: `OPENAI_BASE_URL` = `https://api.anthropic.com/v1` gives adapter `anthropic_models`.
- `test_no_network`: monkeypatches `urllib.request.urlopen` and `httpx` to raise; discovery still succeeds.
- `test_discovery_is_deterministic`

**Verify:** `pytest tests/unit/test_status_providers.py -q`.

#### T2.2 `jarvis/status/models.py`: `model_access_status()`

**Files:** new module + `tests/unit/test_status_models.py`.

**Spec:** `model_access_status(*, registry=None, access=None, env=os.environ) -> dict` returns:

```python
{"ok": True, "generated_at": iso8601_utc, "source": "registry",
 "default": registry["default"],
 "profiles": [{"name","provider","model","identity","tier","routes": available_routes(p),
               "key_env": p.get("api_key_env"), "key_present": bool,
               "key_health": keyhealth.verdict(key_env) if key_env else "n/a (subscription)",
               "key_health_detail": keyhealth.detail(key_env) if key_env else ""}],
 "workloads": {name: {"profile": w["profile"], "route": w.get("route","direct_api")}},
 "providers": [asdict(ref) for ref in discover_providers(...)],
 "coverage_gaps": coverage_gaps(refs)}
```

- `available_routes` comes from `jarvis.model_routing`.
- No network. `key_health` reads the cached verdicts of **the process it runs in**.
- **The sidecar must hold verdicts too (fact 3.6).** In `jarvis/admin/server.py`, directly after the existing module-top `inject_env()` and the `ReminderNotifier` start block, call `jarvis.keyhealth.start_background_probe()`, and in P3 also `start_refresh_loop()`. Both honor `JARVIS_KEY_HEALTH_ENABLED`. The bot keeps its own probe; two processes probing once each at start is accepted, since each probe is one 16-token call per key.

**Tests:**
- Payload shape.
- The fixture key value never appears in `json.dumps(payload)` (I1).
- Subscription profiles report `"n/a (subscription)"`.

#### T2.3 Services, overview, build, location, logs

**Files:** new `jarvis/status/{services,overview,build,location,logs}.py` + one test file each (core/allow).

`service_health(*, http=_http_probe, launchctl=_launchctl) -> dict`
- HTTP probes, each with a 2 s timeout:
  - `bot` → TCP connect `127.0.0.1:7860`
  - `admin` → reported `up` by construction (the sidecar is serving this request); never self-call it
  - `vault` → `GET http://127.0.0.1:8484/health`
  - `costs` → `GET http://127.0.0.1:8487/costs/summary` expects 200
- Launchd state for every service (including `extractor` and the calendar jobs, which have no port): **move** the per-service `launchctl print` parse out of `scripts/launchd_gen.py:status()` into `jarvis/status/services.py:launchd_state(svc) -> str`, and make `launchd_gen.status()` call it (R8). Output stays `"not loaded"`, `"loaded (pid N)"` or `"loaded (idle)"`; `tests/unit/test_launchd_gen.py` must still pass. If `launchctl` is absent (Linux tests), return `"unknown"`.
- Also returns `"source": {"head": git rev-parse HEAD, "dirty_files": count of git status --porcelain lines}`, run in the repo root with fixed argv. The count is how an overlay checkout like 3.1 shows up honestly.

`system_overview() -> dict`
- Agents: name, display_name, model_profile, mcp_servers, max_iterations (the default when absent). Read with the same `yaml.safe_load` of `config/agents.yaml` that `load_sub_agents` uses; do not construct agents.
- MCP servers: names from `config/mcp_servers.yaml`.
- Workloads (from `load_access_config`).
- `flags`: `{name: "on"|"off"}`, each read by its existing reader or its exact existing rule (never a generic parser, R8):

  | Flag | Reader |
  |---|---|
  | `JARVIS_UI_CONTROL_ENABLED` | on unless `false/0/no` (`pipeline.py` rule) |
  | `JARVIS_SCREEN_ENABLED` | `mcp_servers.mcp_screen.logic.screen_enabled()` |
  | `JARVIS_CLIPBOARD_ENABLED` | `jarvis.clipboard.clipboard_enabled()` |
  | `JARVIS_SPEAKER_GATE_ENABLED` | `jarvis.speaker.enabled()` |
  | `JARVIS_MEMORY_AUTOMATION_ENABLED` | on only if value in `{"1","true","yes"}` (`pipeline.py` rule) |
  | `JARVIS_MODEL_ROUTING_ENABLED` | on only if `== "1"` (`base.py` rule) |
  | `JARVIS_KEY_HEALTH_ENABLED` | `jarvis.keyhealth.enabled()` |
  | `JARVIS_GRAPHS_ENABLED` | `jarvis.graphs.graphs_enabled()` |
  | `JARVIS_COUNCIL_ENABLED` | `jarvis.council.council._council_enabled()` |
  | `JARVIS_STATUS_TOOLS_ENABLED` | `jarvis.status.status_enabled()` |

  `JARVIS_REGISTRY_SHARED_ENABLED` is added to this table in T3.1, when its reader exists.
  - For the two "`pipeline.py`/`base.py` rule" rows, first extract the existing inline check into a named function next to it and call that from both places.
- `knowledge`: the dict the sidecar's `/api/knowledge` handler builds. Refactor that handler's body into a function in `jarvis/status/overview.py` and have the endpoint call it (R8).

`app_build_status(repo_root) -> dict`
- For `macos/MortimerHost/.build/MortimerHost.app`: `exists`, `modified_at` (ISO, local timezone), and from `Contents/Info.plist` (`plistlib`): `MortimerSourceRevision`, `MortimerSourceDirty`, `MortimerBuildConfiguration`.
- Also `repo_head` (same `git rev-parse HEAD`) and `matches_repo_head: bool`.

`current_location(*, fetch=None) -> dict`
- Refactor `jarvis/ambient_weather._resolve_location` to also return `"source": "env" | "device" | "ip"`, and `"age_s"` for device. It is additive, so existing callers ignore the extra keys.
- `current_location` returns that dict plus `ok`, or `{"ok": False, "error": "no location available"}`.
- `tests/unit/test_ambient_weather*.py` must still pass. Add one test per source value.

`log_search(source: str, query: str, *, since_minutes: int = 60, limit: int = 50) -> dict`
- `LOG_SOURCES = {"bot": "logs/bot.launchd.log", "admin": "logs/admin.launchd.log", "extractor": "logs/extractor.launchd.log", "costs": "logs/costs.launchd.log", "vault": "logs/vault.launchd.log", "backup": "logs/backup.launchd.log", "app": "logs/mortimerhost-window.log"}`.
- An unknown source is an error. **No path argument exists.**
- Reads at most the last 5 MB of the file.
- Keeps lines whose leading timestamp (`YYYY-MM-DD HH:MM:SS`, with optional `,mmm` or `.mmm`) is within `since_minutes`. Lines without a timestamp inherit the previous line's time.
- Filters by case-insensitive substring `query` (an empty query matches all lines).
- **Drops** lines containing `"Generating chat from context"` (full LLM contexts).
- **Always drops** conversation lines matching `^\[\d\d:\d\d:\d\d\] (USER|MORTIMER):`. There is no option to include them in this spec.
- Redacts, applied in order:
  - `sk-[A-Za-z0-9_-]{8,}` → `sk-…`
  - `(?i)(bearer|x-api-key)[:= ]+\S+` → `\1 <redacted>`
  - 40+ character hex or base64 runs → `<redacted>`
- Truncates each line to 300 characters and returns the last `limit` lines (max 200).

**Tests:**
- Each function against fixtures: a temporary log with transcript lines, a key-like string and old timestamps.
- `test_log_search_redacts_keys`
- `test_log_search_has_no_path_parameter` (inspect the signature)
- `test_log_search_drops_llm_context_lines`
- `test_service_health_marks_down_on_refused_port`
- `test_build_status_reads_plist_keys` (fixture plist)
- `test_location_reports_source`

#### T2.4 Sidecar endpoints

**Files:** `jarvis/admin/server.py` (**deny**; external implementer only); `tests/unit/test_admin_status.py` (allow).

**Spec:** add these routes. Each returns `{"ok": bool, ...}`, is wrapped in `try/except Exception` returning `{"ok": False, "error": str(exc)}` (no traceback), and first checks `status_enabled()` (returning `{"ok": False, "error": "status tools are disabled"}` when off):

| Method | Path | Calls |
|---|---|---|
| GET | `/api/status/models` | `model_access_status()` |
| GET | `/api/status/services` | `service_health()` |
| GET | `/api/status/overview` | `system_overview()` |
| GET | `/api/status/build` | `app_build_status(REPO_ROOT)` |
| GET | `/api/status/location` | `current_location()` |
| GET | `/api/status/logs?source=&query=&since_minutes=&limit=` | `log_search(...)` |

- `/api/knowledge` now calls the refactored `overview` knowledge function (unchanged response).
- All routes are plain `def` (FastAPI runs them in its threadpool), never `async def`, because they do blocking I/O.
- The P4 endpoints (catalog, subscription, github) are added in P4, not here.

**Tests:** FastAPI `TestClient`, one per route: the disabled switch, the error wrapper, and I1 (key string absent).

**Verify:** `pytest tests/unit/test_admin_status.py tests/unit/test_admin_*.py -q`.

#### T2.5 Direct Supervisor tool `system_status`

**Files:** new `jarvis/bot/status_tool.py` and `jarvis/status/summaries.py` (core); `jarvis/bot/tool_schemas.py`, `jarvis/bot/pipeline.py` (core); `jarvis/prompts.py` (allow). Tests: `tests/unit/test_tool_schemas.py`, `tests/integration/test_bot_wiring.py`, new `tests/unit/test_status_tool.py`, `tests/unit/test_status_summaries.py`.

**Spec:**

1. Schema (`SYSTEM_STATUS_SCHEMA`):
   ```python
   {"type": "function", "function": {
     "name": "system_status",
     "description": ("Mortimer's own live status, read directly (no specialist, no user commands): "
       "models = configured models with key health; catalog = what a provider offers right now; "
       "subscription = whether the Claude or Codex subscription answers (uses a little quota); "
       "services = which background services are up; overview = configuration; "
       "build = whether the Mac app was rebuilt and from which commit; location = where the user is."),
     "parameters": {"type": "object", "properties": {
        "topic": {"type": "string", "enum": ["models","catalog","subscription","services",
                                              "overview","build","location"]},
        "provider": {"type": "string", "description": "catalog only: a provider id, or 'all'"},
        "which": {"type": "string", "enum": ["claude","codex"], "description": "subscription only"},
        "model": {"type": "string", "description": "subscription only: exact model to try"},
        "force": {"type": "boolean", "description": "bypass the cache"}},
       "required": ["topic"]}}}
   ```
   The `catalog` and `subscription` topics return `{"ok": False, "error": "not available until the catalog phase ships"}` until P4 is merged. They exist in the enum from P2 so the schema does not change twice.
2. Handler: `build_system_status_tool(admin_url: str | None = None) -> (schema, async handler(arguments) -> str)`.
   - Uses `httpx.AsyncClient`, with a 30 s timeout for `catalog` and `subscription` and 10 s otherwise.
   - I3: if `current_sensitive_turn.get()` is armed and the topic is `catalog` or `subscription`, return `"system_status failed: protected turn cannot call external tool server."`
   - Otherwise it calls the matching endpoint and returns `summaries.summarize(topic, payload)`.
   - On a transport error it returns `"system_status failed: the admin sidecar is not reachable."` It never raises.
3. `summaries.summarize(topic: str, payload: dict) -> str` is pure, deterministic and at most 1500 characters. Each topic's first line states the source (I5), for example `"Source: registry (configured, not proof of availability)."` or `"Source: OpenRouter catalog fetched 06:30."`
   - **models:** the default; then, for each provider, its profiles with tier and key health; then any coverage gaps, named.
   - **services:** each service up or down, then `source.head` short hash and `dirty_files` if non-zero.
   - **build:** exists, modified time, source revision short hash, `matches_repo_head`.
   - **location:** label and source.
   - **overview:** agent count and names with model; the MCP server count; flags that are off.
4. Menu (`tool_schemas.py`): add a keyword `status: bool = False`, matching every other flag's default, and insert `SYSTEM_STATUS_SCHEMA` **immediately after `COST_SUMMARY_SCHEMA`** when it is true. `build_supervisor_prompt` gets `status: bool = False` too.
5. Registration (`pipeline.py` `build_pipeline`):
   - Compute `status_enabled = jarvis.status.status_enabled()` once, beside `ui_control_enabled`.
   - When true, `register_supervisor_tool(llm, "system_status", handler)` immediately after the `cost_summary` registration.
   - Pass `status=status_enabled` **explicitly** to `supervisor_tool_schemas(...)` and to `build_supervisor_prompt(...)`.
   - `tests/evals/routing_eval.py` keeps calling both without `status` (so False). The eval's Orchestrator prompt has no `STATUS_ADDENDUM`, and menu and prompt must agree. Adding status cases to the routing eval is out of scope.
6. Prompt: add `STATUS_ADDENDUM` to `jarvis/prompts.py`, included by `build_supervisor_prompt(..., status=True)` in the addendum list after `UI_CONTROL_ADDENDUM`. Exact text:
   ```
   Your own status: for questions about your models, what a provider or subscription offers, your services, configuration, the Mac app build, or where the user is, call system_status yourself — never delegate these and never hand the user a command. The model registry lists what is configured, not what an account offers: answer whether a model is available only from a catalog or subscription result, and say which source and when.
   ```

**Tests:**
- `test_tool_schemas.py`:
  - The default menu (all flags False) is unchanged.
  - The all-flags-on ordered list gains `system_status` right after `cost_summary`.
  - The index pin `[3] is COST_SUMMARY_SCHEMA` still holds.
  - Add `("status", ["system_status"])` to the parametrized flag test.
- `test_bot_wiring.py`: these exact-list tests gain `"system_status"` (the switch defaults on in `build_pipeline`):
  - `test_six_functions_registered` (:290)
  - `test_ui_control_kill_switch_unregisters_tool` (:302)
  - `test_screen_vision_kill_switch_unregisters_tools` (:314)
  - Add `test_status_kill_switch_unregisters_tool` mirroring `ui_control`'s.
- `test_prompts.py`: add `("status", STATUS_ADDENDUM)` to the parametrized addendum test.
- `test_status_tool.py`:
  - sensitive-turn refusal
  - sidecar down returns the sentence above
  - each topic calls the right path (fake client)
- `test_status_summaries.py`:
  - each topic has a golden string
  - the source line is present
  - length is at most 1500

**Verify:** `pytest tests/unit/test_tool_schemas.py tests/unit/test_status_tool.py tests/unit/test_status_summaries.py tests/unit/test_prompts.py -q && pytest tests/integration/test_bot_wiring.py -q`.

#### T2.6 MCP server `mcp-status` (developer and systems)

**Files:**
- new `mcp_servers/mcp_status/{__init__.py,logic.py,server.py,skill.yaml}` (allow)
- `config/mcp_servers.yaml`, `config/agents.yaml` (allow)
- `jarvis/skills/registry.py` (**deny**): add `"mcp-status"` to `EXTERNAL_TOOL_SERVERS`
- tests: `tests/integration/test_registry.py`, `tests/unit/test_requires_env_snapshot.py` (**deny**), `tests/unit/test_agent_isolation.py` (**deny**), new `tests/unit/test_mcp_status_logic.py`

**Spec:**
1. `logic.py` reuses `mcp_servers.mcp_selfedit.logic.AdminClient` (R8). It constructs the client with `timeout=28.0` for `status_catalog` and `status_subscription` (under the registry's `CALL_TIMEOUT = 30.0`) and the default 10 s otherwise. Every function takes an injected `client` for tests and returns the sidecar JSON unchanged except for list trimming. Tools, in this order:
   ```python
   status_models() -> dict
   status_services() -> dict
   status_overview() -> dict
   status_build() -> dict
   log_search(source: str, query: str = "", since_minutes: int = 60, limit: int = 50) -> dict
   ```
   In P4, append: `status_catalog(provider: str = "all", force: bool = False)`, `status_subscription(which: str, model: str = "", force: bool = False)`, `github_prs(state: str = "open", limit: int = 10)`, `github_pr_checks(number: int)`.
2. `server.py` follows `mcp_runlog/server.py` exactly:
   - `mcp = FastMCP("mcp-status")`
   - a bare `@mcp.tool()` directly above each `def`
   - docstrings prefixed `"Mortimer status (read-only):"`
   - `if __name__ == "__main__": mcp.run()`
3. `skill.yaml`:
   ```yaml
   name: mcp-status
   version: 0.1.0
   class: standard
   tools: [status_models, status_services, status_overview, status_build, log_search]
   requires_env: []
   optional_env: []
   requires_keychain: []
   scopes: []
   test: "python3 -m pytest tests/unit/test_mcp_status_logic.py -q"
   ```
   `JARVIS_ADMIN_URL` is already in `BASE_ENV_KEYS`.
4. `config/mcp_servers.yaml`: append the entry **after `mcp-screen`** with `command: python`, `args: ["-m", "mcp_servers.mcp_status.server"]` and `env: {}`.
5. `config/agents.yaml`:
   - `systems.mcp_servers: [mcp-system, mcp-screen, mcp-status]`
   - `developer.mcp_servers` gets `mcp-status` appended.
   - Append this to each description:
     ```
     Also reads Mortimer's own live status: models and key health, services, configuration, app build, and logs (status_*, log_search).
     ```

**Tests:**
- `test_registry.py`: `ALL_SERVERS` appends `"mcp-status"`; `TOTAL_TOOLS` 70 → 75 in P2 (79 after P4), with a changelog comment.
- `test_requires_env_snapshot.py`: `EXPECTED["mcp-status"] = ([], [], {})`.
- `test_agent_isolation.py`: add `"mcp-status"` to `OUTBOUND`, **and** update the exact-equality assertion in `test_the_sets_have_not_been_quietly_emptied` (:66) to include it. This is an announced change under R4.
- `test_mcp_status_logic.py`: fake client; path per tool.
- `scripts/check_skills.py` must pass.

**Verify:** `python scripts/check_skills.py && pytest tests/unit -q && pytest tests/integration/test_registry.py -q`.

#### T2.7 Docs for P2

`CLAUDE.md` gets a new paragraph, **"Self-service status (system_status / mcp-status)"**, stating L1, L2, I3, I4 and I5 and naming `JARVIS_STATUS_TOOLS_ENABLED`. Also update:
- `docs/ARCHITECTURE.md`: the diagram line plus one "Where to verify" row. Stay ≤ 12000 characters.
- `docs/REPO_MAP.md`: one line for `jarvis/status/` and one for `mcp_servers/mcp_status/`. It must stay ≤ 8000 characters; trim wording elsewhere if needed.

**P2 PR acceptance** (Larry, live; each answered with no command and no delegation):
- "What models do you have and are they working?"
- "Are all your services up?"
- "Was the app rebuilt?"
- "Where am I?"

---

### P3 — Resilience: sub-agents never left unusable

#### T3.1 Process-scoped, supervised registry (L11)

**Files:** `jarvis/skills/registry.py` (**deny**); new `jarvis/skills/shared.py` (core); `jarvis/bot/pipeline.py` (core). Tests: `tests/unit/test_registry.py`, new `tests/unit/test_registry_supervision.py`, `tests/integration/test_registry.py`, `tests/unit/test_delegate_teardown.py`.

**Spec:**

1. **Server handle and owner task** (inside `registry.py`):
   ```python
   @dataclass
   class _ServerHandle:
       name: str
       entry: dict
       state: str = "starting"          # starting | up | down
       session: ClientSession | None = None
       tools: dict[str, Tool] = field(default_factory=dict)
       last_error: str = ""
       restarts: list[float] = field(default_factory=list)   # monotonic times
       stop: asyncio.Event = field(default_factory=asyncio.Event)
       ready: asyncio.Event = field(default_factory=asyncio.Event)
       task: asyncio.Task | None = None
       lock: asyncio.Lock = field(default_factory=asyncio.Lock)
   ```
   `async def _serve(self, h: _ServerHandle) -> None` is the **only** place `stdio_client` and `ClientSession` contexts are entered and exited:
   - It builds params exactly as today's `_start_server` does (env build, `expand_env_vars`, the `mcp_server_env_unresolved` warning, `PYTHONPATH`, `cwd`).
   - Inside `async with AsyncExitStack() as stack:` it enters the contexts, calls `initialize()` and `list_tools()`, sets `h.session`, `h.tools`, **`self._sessions[h.name] = session`** and `h.state = "up"`, calls `h.ready.set()`, then `await h.stop.wait()`.
   - On any exception: `h.state = "down"`, `h.last_error = f"{type(exc).__name__}: {exc}"[:200]`, `h.session = None`, `self._sessions.pop(h.name, None)`, drop that server's names from `self._tools` (they stay in `self._known_tools`), `h.ready.set()`, and log `mcp_server_down name=%s error=%s`.
   - `call()` keeps reading `self._sessions[server]` and `self._tools` exactly as today, so existing unit tests that assign `_sessions`/`_tools` directly keep working.
   - It never re-raises (fact 3.4c: contexts must close in the task that opened them).
2. **`start()`:**
   - `bridge_settings_to_env()`, then create one handle per config entry.
   - `h.task = asyncio.create_task(self._serve(h), name=f"mcp:{h.name}")`.
   - `await asyncio.gather(*(h.ready.wait() for h in handles))`.
   - Rebuild `self._tools` from **up** handles. A name provided by two up handles still raises `ValueError("Tool name collision: ...")`. Keep that message, since `test_tool_name_collision_raises_at_start` pins it; stop all handles before raising.
   - `self._known_tools` (tool name → server name) is filled from every listing ever seen, so a tool of a down server is recognized.
   - A down server does **not** raise; log `mcp_server_start_failed name=%s error=%s`.
3. **`call()` changes** (everything else unchanged, including the sensitive-turn block, GL9 and runlog events):
   - Tool unknown but in `_known_tools` (its server is down) → return `f"{tool_name} failed: {server} is unavailable ({h.last_error}); it restarts automatically."` Attempt `_restart(server)` in the background (not awaited) if allowed by backoff.
   - `session.call_tool` raises one of `_TRANSPORT_ERRORS = (anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream, McpError)` (for `McpError`, only when `"Connection closed"` is in `str(exc)`) → `ok = await self._restart(server)`:
     - If `ok` and the tool is still offered, retry the call **once** and return its result through the normal path.
     - Otherwise return `f"{tool_name} failed: {server} stopped and could not be restarted ({h.last_error})."`
   - The runlog `mcp_call` event records the final outcome.
4. **`async def _restart(self, server: str) -> bool`:**
   - Under `h.lock`.
   - Backoff: drop `restarts` older than 60 s; if 3 or more remain, set `state = "down"`, remove the server's tools from `self._tools` and its session from `self._sessions`, and return False. Later calls then take the `_known_tools` "unavailable" branch.
   - Otherwise set `h.stop`, `await asyncio.wait_for(h.task, 10)` (swallow the timeout and cancel), create a fresh `stop`/`ready`, start a new owner task, and wait for `ready` up to 30 s.
   - Recompute `self._tools` for that server. If the new tool set differs from the old one, log `mcp_server_tools_changed` and accept the new set. Append the time to `restarts` and log `mcp_server_restarted name=%s ok=%s`.
   - Return `h.state == "up"`.
5. **`stop()`:** set every `stop` event; if the set of live owner tasks is non-empty, `await asyncio.wait(tasks, timeout=10)` (`asyncio.wait` raises on an empty set) and cancel stragglers; then clear `_sessions`/`_tools`. It is idempotent and never raises. Stopping from a different task now works because each owner task closes its own contexts.
6. **`status()`:** `status() -> dict[str, dict]` returns `{name: {"state", "last_error", "restarts_last_60s", "tools": n}}`. It is used by tests and by one log line, `mcp_registry_status`, written after every restart. The sidecar cannot see the bot's registry, so `service_health` does **not** report MCP server states; the developer finds them with `log_search(source="bot", query="mcp_server_")`. Do not add a bot HTTP endpoint in this spec.
7. **`jarvis/skills/shared.py`:**
   ```python
   _shared: SkillRegistry | None = None
   _lock = asyncio.Lock()
   def shared_enabled() -> bool   # JARVIS_REGISTRY_SHARED_ENABLED, default on; single enforcement point
   async def get_shared_registry(config_path: Path, factory=None) -> SkillRegistry  # start once per process via factory(config_path), reuse thereafter
   def _reset_for_tests() -> None
   async def shutdown_shared_registry() -> None
   ```
8. **`pipeline.run_session`:**
   - If `shared_enabled()`: `registry = await get_shared_registry(REPO_ROOT / "config" / "mcp_servers.yaml", factory=SkillRegistry)`. Here `SkillRegistry` is the name as imported in `pipeline.py`, so tests that monkeypatch `bp.SkillRegistry` still control it. Otherwise, the legacy per-session construction.
   - Add `JARVIS_REGISTRY_SHARED_ENABLED` (reader `jarvis.skills.shared.shared_enabled()`) to T2.3's flags table.
   - In `finally`: keep `drain_detached`; call `registry.stop()` **only** when the registry is per-session.
   - **Step 0 (STOP condition):** add a temporary log of `id(asyncio.get_running_loop())` at `run_session` start. Run two sessions on the Mac (connect, disconnect, connect). If the loop ids differ, **STOP**: the runner uses a loop per session, and a process-scoped registry is invalid. Report this and do not proceed.
9. **Process exit:** on stdin EOF the MCP stdio servers exit.
   - **Step 0b:** on the Mac, start the bot, note the child PIDs (`pgrep -f mcp_servers`), kill the bot with SIGTERM, and confirm the children are gone within 5 s.
   - If they are not, also register `shutdown_shared_registry` via `atexit` plus a signal handler in `jarvis/bot/bot.py`'s `__main__` block. Record the outcome in the PR.

**Tests:**
- `tests/integration/test_registry_supervision.py` (integration, because it spawns real children; `tests/unit/test_registry.py` is spawn-free by design):
  - `test_dead_child_is_restarted_and_call_succeeds`: kill the child (psutil, test-only dependency or `os.kill` via the handle's pid) → the next call returns the tool's normal output.
  - `test_restart_backoff_marks_down_after_three`
  - `test_start_isolates_a_failing_server`: a config with mcp-time plus an entry whose `args` are `["-c", "import sys; sys.exit(1)"]` → `start()` succeeds, the bogus server's state is `down`, and mcp-time calls work.
- `test_down_server_tools_report_unavailable`: start mcp-time, then kill its child 4 times inside 60 s → the 4th call returns `"... is unavailable (...)"`, not `"Unknown tool"`.
  - `test_stop_from_another_task_is_clean`: no `registry_stop_error` logged (fact 3.4c).
  - `test_concurrent_calls_share_one_session`: 20 gathered calls all succeed.
- `test_delegate_teardown.py`: `test_stopping_the_registry_under_a_detached_run_orphans_its_tools` is unaffected (it drives the registry directly, not `run_session`). Keep its `registry._sessions == {}` assertion true (`stop()` clears `_sessions`).
- `tests/integration/test_bot_wiring.py`: the four `run_session` tests that monkeypatch `bp.SkillRegistry` (:735, :878, :992, :1129) set `JARVIS_REGISTRY_SHARED_ENABLED=false` via `monkeypatch.setenv`, keeping their `registry_stopped` assertion meaningful. Add `test_shared_registry_survives_session_teardown` (switch on, `FakeRegistry` via the factory, two `run_session` calls, one `start`, zero `stop`), calling `shared._reset_for_tests()` in teardown.
- Integration: `test_starts_all_servers_and_discovers_tools` and `test_tool_name_collision_raises_at_start` unchanged and green.

**Verify:** `pytest tests/unit/test_registry*.py tests/unit/test_delegate_teardown.py -q && pytest tests/integration -q`.

#### T3.2 Notice outbox (L12)

**Files:** `jarvis/db.py` (**deny**): migration `0025_notices`. New `jarvis/notices.py` (core); `jarvis/agents/delegate.py`, `jarvis/bot/pipeline.py` (core). Tests: new `tests/unit/test_notices.py`, updated `tests/unit/test_delegate.py`.

**Spec:**

1. Migration SQL:
   ```sql
   CREATE TABLE IF NOT EXISTS notices (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     created_at TEXT NOT NULL,
     kind TEXT NOT NULL CHECK (kind IN ('late_result','daily_status')),
     source TEXT NOT NULL,
     text TEXT NOT NULL,
     delivered_at TEXT
   );
   CREATE INDEX IF NOT EXISTS idx_notices_pending ON notices(delivered_at, created_at);
   ```
2. `jarvis/notices.py`:
   ```python
   MAX_NOTICE_CHARS = 600
   MAX_DELIVERED_PER_CONNECT = 5
   def add_notice(kind: str, source: str, text: str) -> int
   def take_pending(limit: int = MAX_DELIVERED_PER_CONNECT) -> list[dict]
   def render_for_greeting(items: list[dict]) -> str
   ```
   - `add_notice` truncates text to 600 characters.
   - `take_pending` selects the oldest undelivered, marks them delivered in the same transaction and returns them.
   - `render_for_greeting` returns `""` for an empty list. Otherwise:
     ```
     " While they were away: " + " / ".join(texts) + " Mention these in one or two short sentences after greeting."
     ```
   - Kill switch: `JARVIS_NOTICES_ENABLED` (default on), checked only inside `add_notice` and `take_pending`. When off, `add_notice` returns -1 and `take_pending` returns [].
3. **Liveness and the outbox decision** (all made in `delegate.py` `_deliver`, which knows the agent and the sensitive state):
   - Add `alive: bool = True` to pipeline `Runtime`. Set `runtime.alive = False` as the first statement of the **inner** `finally` that follows `await runner.run(task)` (around `pipeline.py:1620`), before memory fold-in, so results landing during teardown are captured.
   - `inject_late_result` returns `bool`: `False` without touching the pipeline when `not runtime.alive`, `True` after injecting.
   - In the handler, capture `armed = bool(holder and holder.is_armed())` from `current_sensitive_turn` at delegation start and pass it to `_deliver`.
   - In `_deliver`: if there is no hook, or `await`ing the hook returns `False`, call `add_notice("late_result", agent.display_name, text)`. `text` is the finished note, or, when `armed`, exactly `"A background task you asked for finished; ask me for its result."`. This replaces the bare `delegate_late_result_undeliverable` log; keep the log line too.
   - `_deliver` currently spawns `fn(note)` in the background. Change it to spawn a small coroutine that awaits `fn(note)`, checks the returned bool, and calls `add_notice` on `False`.
4. **Greeting:** in `on_client_connected`:
   ```python
   greeting_note = connection_greeting_note(settings.jarvis_timezone) + notices.render_for_greeting(notices.take_pending())
   ```

**Tests:**
- `test_notices.py`:
  - add, take, delivered-once
  - truncation
  - kill switch
  - `render_for_greeting` golden
- `test_delegate.py`:
  - `test_undeliverable_late_result_goes_to_outbox`
  - `test_dead_session_hook_returning_false_goes_to_outbox`
  - `test_sensitive_late_result_is_redacted_in_outbox`
- `tests/unit/test_db.py`: add `"0025_notices"` to `EXPECTED_MIGRATION_IDS` and `"notices"` to `EXPECTED_TABLES` (announced, R4).

**Verify:** `pytest tests/unit/test_notices.py tests/unit/test_delegate.py tests/unit/test_db*.py -q`.

#### T3.3 Key health refresh

**Files:** `jarvis/keyhealth.py`, `jarvis/agents/delegate.py`, `jarvis/bot/pipeline.py` (core). Tests: `tests/unit/test_keyhealth*.py`.

**Spec:**
- `start_refresh_loop(interval_s: float = 600.0) -> threading.Thread | None` is a process singleton (module-level guard), a daemon thread and disabled when `enabled()` is false. Every `interval_s` it re-probes only keys whose verdict is `rejected`, `unfunded` or `unreachable`, using the same `_targets()` and `_load_probe()`.
- `note_success(key_env: str) -> None`: if the current verdict is not `ok`, set it to `ok` with detail `"recovered: a call succeeded"`.
- In `_execute`, when the result is not failed **and** no per-run `model_profile` override was given, call `key = getattr(agent, "api_key_env", "")` and, if `key` is non-empty, `keyhealth.note_success(key)`. `api_key_env` is a read-only property added to `SubAgent` returning `self._api_key_env`. `getattr` keeps the test fakes, which have no such attribute, working.
- Call `start_refresh_loop()` beside `start_background_probe()` in `run_session`, and in the sidecar next to the probe added in T2.2. It is idempotent per process.
- Existing `KeyHealthNotice` then speaks recovery through `KEYHEALTH_RECOVERED_TEMPLATE` with no change.

**Tests:**
- `test_refresh_loop_is_singleton`
- `test_refresh_reprobes_only_bad_keys` (fake probe)
- `test_note_success_recovers_verdict`

**P3 PR acceptance** (Larry, live):
1. Start a long developer task, disconnect the app for 3 minutes, reconnect: the result is spoken after the greeting, and the bot log has no `Available: none`.
2. On the Mac, `pkill -f mcp_servers.mcp_web.server`, then ask for the weather: it is answered, and the log shows `mcp_server_restarted name=mcp-web ok=True`.

---

### P4 — External reads, subscriptions, GitHub, daily job

#### T4.1 Provider catalogs (L3, L4)

**Files:** new `jarvis/status/catalog.py` (core); sidecar route `GET /api/status/catalog?provider=all&force=false` (**deny**). Tests: new `tests/unit/test_status_catalog.py`.

**Step 0 (on the Mac, recorded in the PR):** for each `llm` ref from `discover_providers()` whose adapter fetches, run one fetch with the real vault-loaded key through a throwaway script that uses the fetcher below. Record for each provider the HTTP status, top-level keys, one item's keys, and the pagination fields. Anthropic is confirmed to need `x-api-key` (fact 3.2). If any provider's success shape differs from the parsing rules below, **STOP** (R1).

**Spec:**

```python
@dataclass(frozen=True)
class CatalogResult:
    provider: str; ok: bool; fetched_at: str; source: str      # e.g. "anthropic:/v1/models"
    models: tuple[dict, ...]    # each {"id": str, "display_name": str|None, "created": str|None}
    error_category: str | None  # rejected|unfunded|unreachable|unsupported|not_configured|no_credential
    error: str | None           # sanitized, <= 200 chars, never contains a key or header
def fetch_catalog(ref: ProviderRef, *, force: bool = False, timeout: float = 10.0,
                  http=_default_http, env=os.environ) -> CatalogResult
def fetch_all(refs, *, force=False, per_provider_timeout=8.0, total_timeout=20.0) -> list[CatalogResult]
    # parallel (concurrent.futures.ThreadPoolExecutor); a provider still running at total_timeout
    # is returned as error_category="unreachable", error="timed out"; one failure never stops others
def compare_to_registry(results, registry, *, env=os.environ) -> dict   # below
```

**Fetch rules:**
- `anthropic_models`:
  - `GET {base.rstrip('/')}/models?limit=1000` with headers `x-api-key: <key>` and `anthropic-version: 2023-06-01`.
  - Items are `payload["data"][*]` with `id`, `display_name` and `created_at`.
  - While `payload.get("has_more")`, repeat with `&after_id={payload["last_id"]}`, capped at 10 pages.
- `openai_models`:
  - `GET {base.rstrip('/')}/models` with `Authorization: Bearer <key>`.
  - Items are `payload["data"][*]` with `id`; `created` is epoch seconds converted to ISO when present, and `name` is used as `display_name` when present (OpenRouter).
- `saygm_catalog`: `jarvis.saygm.fetch_catalog(api_key=env.get(ref.credential_env))`. Map `SayGMModel.model` to `id`, and keep `tier`.
- `subscription_probe`: `CatalogResult(ok=False, error_category="unsupported", error="no model list API; use the subscription probe")`.
- `not_configured`: `error_category="not_configured"`.
- Missing credential: `error_category="no_credential"`, and no request is made.

**Status mapping** (identical to `model_key_probe`, R8):
- 401 or 403 → `rejected`
- 402 → `unfunded`
- other non-2xx, network error, or non-JSON → `unreachable`

**Cache:** module dict keyed by provider id, TTL 3600 s; `force=True` bypasses it.

**`compare_to_registry` output**, per provider:
```python
{"configured_available": [profile names whose model id is in the catalog],
 "configured_missing": [profile names whose model id is not in the catalog],
 "offered_not_configured_count": int,
 "offered_not_configured_sample": [up to 25 ids, sorted, newest first when created is known]}
```
- A profile's model id is `profile["model"]`.
- For `voice`, compare against `env["OPENAI_MODEL"]`.

**Tests** (fake `http` only; no network in unit tests):
- `test_anthropic_uses_x_api_key_not_bearer`
- `test_anthropic_pagination`
- `test_openai_compatible_parse`
- `test_status_mapping_matches_key_probe` (401, 402, 403, 500, timeout)
- `test_no_credential_makes_no_request`
- `test_one_provider_failure_does_not_stop_others`
- `test_compare_to_registry`
- `test_cache_and_force`
- `test_error_text_never_contains_key` (I1)

#### T4.2 Subscription probes (L5)

**Files:**
- new `jarvis/status/subscriptions.py` (core)
- `scripts/verify_model_access.py` (core): import `probe_subscription` from the new module and delete its local `_probe_subscription` (R8). Its JSON output must be byte-identical for the same inputs; add a test.
- sidecar route `POST /api/status/subscription/probe` with body `{which, model?, force?}` (**deny**)
- tests: new `tests/unit/test_status_subscriptions.py`

**Step 0 (on the Mac):** the sidecar runs under launchd with `PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin` (`scripts/launchd/com.mortimer.template.plist`). Run `env -i PATH=<that PATH> HOME=$HOME sh -c 'command -v claude; command -v codex'`. If either is not found, **STOP**. The fix (setting `JARVIS_CLAUDE_SUBSCRIPTION_COMMAND`/`JARVIS_CODEX_SUBSCRIPTION_COMMAND` to absolute paths in `.env`) is Larry's to make.

**Spec:**
```python
DEFAULT_PROBE_MODEL = {"codex": <model of registry profile "codex-subscription">, "claude": "claude-sonnet-5"}
PROBE_RATE_LIMIT_S = 600
def probe_subscription(which: Literal["claude","codex"], model: str | None = None, *,
                       force: bool = False, timeout: float = 25.0, runner=None) -> dict
```
- It returns:
  ```python
  {"which", "model", "ok", "response_present": bool,
   "category": None | "authentication" | "model_unavailable" | "timeout"
              | "runtime_environment" | "runtime_error" | "not_installed",
   "installed": bool, "command": str, "probed_at": iso, "cached": bool}
  ```
- The five existing categories and their classification logic are moved **verbatim** from `scripts/verify_model_access.py`'s `_probe_subscription`. `not_installed` is **new**: it is returned, without running anything, when `shutil.which(command)` is None.
- The prompt token stays `MORTIMER_SUBSCRIPTION_PROBE_OK`, exactly as the script asks for it. (The committed 09-20 receipt shows `SUBSCRIPTION_PROBE_OK`; the docs disagreement is being reconciled on the unmerged `docs/reconcile-status-88b206f` branch. Do not change the token here.)
- `scripts/verify_model_access.py` `build_report` keeps its exact output. It maps the new result back to `{"ok", "response_present"}` on success and `{"ok": False, "category"}` on failure, and treats `not_installed` as the pre-existing behavior for a missing command, so its JSON is byte-identical.
- The 25 s timeout keeps the probe under the MCP `CALL_TIMEOUT` of 30 s. The script passes its own 45 s explicitly to preserve its behavior.
- `model` is passed through **exactly as given**. The answer names the exact model tried; no alias mapping is invented.
- Rate limit: per `(which, model)`, reuse the last result for 600 s unless `force`.
- Summary text (T2.5 `summarize("subscription", …)`) says `"This check used a small amount of your <which> subscription."`

**Tests:**
- `test_probe_categories_match_script`: a table of fake runner outcomes gives categories.
- `test_rate_limit_and_force`
- `test_script_output_unchanged`: golden JSON from `build_report` with fake runners, before and after.
- `test_model_passed_through_verbatim`

#### T4.3 GitHub reads

**Files:** `mcp_servers/mcp_apps/github.py` (allow): add read methods. New `jarvis/status/github.py` (core); sidecar route `GET /api/status/github?kind=prs|checks&state=open&limit=10&number=` (**deny**). Tests: `tests/unit/test_mcp_apps_github.py` (extend) and new `tests/unit/test_status_github.py`.

**Spec:**
- `GitHubClient.list_pulls(repo: str, state: str = "open", limit: int = 10) -> list[dict]`:
  - `GET /repos/{owner}/{repo}/pulls?state=&per_page=`
  - Returns `{number, title, state, draft, head, base, updated_at, html_url}`.
- `GitHubClient.pull_checks(repo: str, number: int) -> dict`:
  - Gets the PR's `head.sha`, then `GET /repos/{owner}/{repo}/commits/{sha}/check-runs`.
  - Returns `{sha, checks: [{name, status, conclusion}]}`.
- Neither method writes.
- `jarvis/status/github.py`:
  - Repository from `JARVIS_GITHUB_REPO` (default `Larryfix71566/jarvis-voice-ai`, the same default as `jarvis/selfedit/service.py`), split into owner and repo.
  - Token is `os.environ.get("JARVIS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")`.
  - Construct `GitHubClient(token=..., owner=owner)`.

**Tests:**
- Fake `_request`
- `test_no_write_methods_called`
- `test_token_never_in_output`

#### T4.4 Wire P4 topics into the tools

- `system_status` topics `catalog` and `subscription` now call the new endpoints. The summaries:
  - **catalog:** per provider, OK or the error category; `configured_missing` named; `offered_not_configured_count` with up to 5 sample ids; the source and `fetched_at` time.
  - **subscription:** ok or category; the exact model tried; the quota sentence.
- `mcp-status`: add `status_catalog`, `status_subscription`, `github_prs` and `github_pr_checks`. Update `skill.yaml` `tools` and set `TOTAL_TOOLS` to 79.
- Add to the Supervisor prompt `STATUS_ADDENDUM` (T2.5): nothing new. It already covers these topics.

**Tests:** summaries goldens for both topics, and the registry count.

#### T4.5 Daily status job (L4, L5)

**Files:** new `jarvis/status/daily.py` (core); `scripts/launchd_gen.py` (core); `tests/unit/test_launchd_gen.py` and new `tests/unit/test_status_daily.py` (allow).

**Spec:**

1. `python -m jarvis.status.daily` runs `jarvis.vault.inject_env()` first, as `scripts/verify_model_access.py` does, then:
   1. `refs = discover_providers()`
   2. `catalogs = fetch_all(refs, force=True)`
   3. probes for `claude` and `codex` with their default models (`force=True`)
   4. `jarvis.keyhealth.probe_all()`
   5. `status = model_access_status()`
   6. Write `data/status/daily-YYYY-MM-DD.json` atomically (temp file plus `os.replace`). Add `data/status/` to `.gitignore` in this task, so the runtime checkout stays clean (P0's done-when, T2.3's `dirty_files`). Keys:
      ```
      {"generated_at", "source_head", "coverage_gaps", "catalogs": [asdict], "comparison": compare_to_registry(...),
       "subscriptions": {...}, "key_health": {...}}
      ```
   7. Keep the newest 30 files and delete older ones.
2. Compare with the previous file:
   - `new_offered`: ids in a provider catalog that were not in yesterday's, for providers with a configured profile.
   - `newly_missing`: `configured_missing` entries that were not missing yesterday.
   - `probe_changes`: subscription `ok` flipped.
   - `key_changes`: verdict changed.
   - `coverage_gaps`: any.
3. If any of those is non-empty, `add_notice("daily_status", "daily", text)`. The text is built by the pure function `daily_notice_text(diff) -> str` (≤ 600 characters), for example:
   ```
   Daily check: OpenRouter added 3 models (x-ai/grok-5, …). Codex subscription probe failed: authentication.
   ```
   No notice is written when nothing changed.
4. The exit code is always 0. Failures are recorded inside the file (R-style receipts), because launchd retry storms help nobody.
5. **Launchd** (`scripts/launchd_gen.py`): replace the backup special case with a table, then add the job:
   ```python
   CALENDAR_JOBS = {
     "backup": (["/usr/bin/python3", "scripts/backup_db.py"], 3, 15),
     "status-daily": (["/bin/bash", "-c", "cd {repo} && set -a && . ./.env && set +a && exec .venv/bin/python -m jarvis.status.daily"], 6, 30),
   }
   ALL_SERVICES = (*SERVICES, *CALENDAR_JOBS)
   ```
   - `render()` fills `{repo}` and emits `StartCalendarInterval{Hour, Minute}` from the table.
   - Sourcing `.env` matches `scripts/run_admin.sh` (`set -a; . ./.env`), so the job sees the same `OPENAI_BASE_URL`/`OPENAI_MODEL` as the sidecar.
   - The existing `--hour/--minute` CLI flags keep applying to `backup` only (unchanged behavior).
   - **Step 0:** on the Mac, confirm `<runtime>/.venv/bin/python -c "import jarvis"` works (P0 created `.venv`).

**Tests:**
- `test_launchd_gen.py`:
  - the backup plist is byte-identical to before (golden)
  - the status-daily plist has the expected argv and schedule
- `test_status_daily.py`:
  - fixture previous and current snapshots → `daily_notice_text` golden
  - no-change → no notice
  - retention keeps 30
  - atomic write
  - a failing provider is recorded without an exception

#### T4.6 Memory graph overview fallback

**Files:** `jarvis/graphs/__init__.py` (core); `jarvis/bot/display.py` (core); tests `tests/unit/test_mcp_memory_logic.py`, `tests/unit/test_graphs*.py`, `tests/unit/test_display.py`.

**Spec:**
- In `build()`, when `name == "memory"` and a non-empty focus does not resolve: build the unfocused memory graph (the same call with `focus=""`) and return it with `"ok": True`, plus `"focus_miss": focus.strip()`.
- Other graphs keep today's error.
- `jarvis.graphs.tool_result()` copies `focus_miss` into its returned dict when present. Today it builds a fixed dict, so without this the field never reaches the tool or the display.
- The display formatter `_fmt_graph_view` prefixes `"No memory matched '<focus>'; showing the overview."` when `focus_miss` is present.

**Tests:**
- Replace `test_memory_graph_view_error_passthrough` with `test_memory_graph_unmatched_focus_falls_back_to_overview`.
- Add `test_execution_graph_still_errors_on_unmatched_focus`.

#### T4.7 Self-edit branch freshness (verify-only, L13)

- On the Mac, run one sandbox self-edit to a draft PR.
- Merge an unrelated commit to `main`, and run a second self-edit touching a neighboring file.
- Record whether the second PR's base is stale or conflicting on GitHub.
- **Write the result into the P4 PR description.** No code in this task. If a real failure is observed, open a new plan; do not improvise.

#### T4.8 Core-tier self-edit recovery (prompt)

**Files:** `jarvis/prompts.py` (allow): the developer `self_development` section. Tests: `tests/unit/test_prompts.py`.

**Spec:** append this sentence to the `self_development` section text:

```
If selfedit_start refuses because a core file needs a plan, offer to write one with plan_start for the same goal, and after the user adopts it, start again with that plan_path.
```

**Tests:**
- `TestDeveloperSections::test_no_section_text_was_reworded` still passes. It asserts only `"two-phase"` or `"plan_start"` and no surrounding whitespace, so the new sentence (which contains `plan_start`) satisfies it.
- Add `test_self_development_offers_plan_on_core_refusal`.

**P4 PR acceptance** (Larry, live):
- "Is Fable 5.1 available on my Claude subscription?" is answered from a probe, naming the exact model tried.
- "What new models does OpenRouter have?" is answered from the catalog, with its fetch time.
- "Any open PRs?"
- The next morning's first connect mentions the daily findings only if something changed.

---

### P5 — Registry split (L6)

Execute `docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md` §3–§8 as written, with these amendments. Amendments win where they conflict.

- **A1.** 14 profiles, not 13. `codex-subscription` has no `base_url` or `api_key_env`.
  - Endpoints must support a credential-less endpoint:
    ```yaml
    codex-subscription: {provider: openai, kind: subscription, route: codex_subscription}
    ```
  - D3 (a profile may not declare `base_url`/`api_key_env`) still applies.
  - The joined profile for `codex-subscription` must equal today's (no `base_url`/`api_key_env` keys), and the D6 equality test covers it.
- **A2.** Add these to §2's direct-parse list and convert them to the loader:
  - `jarvis/model_routing.py::_load_model_registry`
  - every `jarvis/status/*` reader (they already use `load_model_registry`; assert it in a test)
- **A3.** The §4a sync job **is** `jarvis/status/daily.py` (T4.5), extended by one step: after the split, also render `model_catalog.<endpoint>.json` from the `CatalogResult`s, with the §4a schema (`identity`, provider model string, `fetched_at`, `source`, and price fields when the provider returns them, otherwise null).
  - It writes them to **`data/status/generated/`** (ignored), never into the tracked `config/generated/`. Writing tracked files would dirty the runtime checkout every day.
  - Moving them into `config/generated/` happens only through the §4a follow-on PR job, which stays out of scope.
  - It never writes `model_endpoints.yaml` or `model_profiles.yaml`.
- **A4.** The voice profile `claude-haiku-4-5` synthesized in `jarvis/model_routing._resolve_model_profile` is unchanged by the split. `discover_providers` already sees Anthropic through the registry and the `voice` ref.
- **A5.** After the split, T2.1's `test_real_config_has_no_coverage_gaps` must still pass against the joined view.

**Acceptance:** the split plan's §8, plus a routine sandbox self-edit PR that adds one profile on an existing endpoint (split plan step 7).

---

### P6 — Sports scores (L7)

**Step 0 (on the Mac; STOP if unmet).**
- For MLB, test `GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD&hydrate=linescore`.
- For NFL, test `GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=YYYYMMDD`.
- Record the status and response shape for a date with finished games.
- Both are **unofficial, undocumented public endpoints**. Neither was reachable from the cloud workspace, so neither is verified. **Larry decides** in the P6 PR whether an unofficial endpoint is acceptable. If he declines one, that league falls back to search (step 3).

**Files:** `mcp_servers/mcp_web/{logic.py,server.py,skill.yaml}` (allow); the analyst prompt in `jarvis/prompts.py` (allow). Tests: `tests/unit/test_mcp_web_logic.py`, `tests/integration/test_mcp_servers.py` (`EXPECTED_TOOLS`), and `tests/integration/test_registry.py` (`TOTAL_TOOLS` +1).

**Spec:**
1. Signature:
   ```python
   sports_scores(league: str, date: str = "") -> dict
   ```
   - `league` is one of `nfl` or `mlb`, extended only by later decision.
   - `date` is `YYYY-MM-DD` in `JARVIS_TIMEZONE`; empty means today.
2. It returns:
   ```python
   {"ok", "league", "date", "source", "fetched_at", "games": [{"away", "home", "away_score", "home_score", "status", "start_local"}]}
   ```
   - `status` is one of `scheduled`, `in_progress` or `final`, mapped from the source's state field as recorded in Step 0.
   - An unsupported league returns `{"ok": False, "error": "no structured source for <league>"}`.
3. Analyst prompt, appended:
   ```
   For game scores or schedules call sports_scores first; if it has no source for that league or fails, search the web and say the result is unconfirmed.
   ```

**Tests:**
- Fixture JSON per source (captured in Step 0 and committed under `tests/fixtures/sports/`) gives the parsed games.
- Status mapping.
- Unsupported league.

---

### P7 — Reconnect instrumentation (no behavior change)

**Files:** `jarvis/bot/pipeline.py` (core), `macos/JarvisKit/Sources/JarvisKit/NativeAudioTransport.swift` (allow).

**Spec:**
- **Server.** In `on_client_disconnected`, log one line:
  ```
  session_disconnect session=<id> duration_s=<n> transport=<ws|webrtc> close_code=<code|unknown>
  ```
  For WebSocket, use the close code if the transport exposes it. Otherwise log `unknown`; do not add dependencies.
- **Client.** Where the WebSocket task completes or fails, `os_log` `closeCode.rawValue` and the `reason` string (UTF-8, truncated to 120), under subsystem `com.mortimer.host`, category `transport`.
- No reconnect logic changes.

**Tests:** one Python test asserting the log line format with a fake transport. Swift: `swift test` stays green, and there is no new Swift test (logging only).

**Acceptance:** after one day of use, `log_search(source="bot", query="session_disconnect", since_minutes=1440)` gives the data for a follow-up plan.

---

## 6. Acceptance map (blocker → proof)

| Blocker (recovery plan §1) | Proven by |
|---|---|
| B1 model and subscription access | P2 acceptance "What models…"; P4 acceptance "Fable 5.1…", "OpenRouter new models" |
| B2 registry additions | P5 step-7 PR |
| B3 GitHub PR reads | P4 "Any open PRs?" (branch sync: T4.7 report) |
| B4 build and log visibility | P2 "Was the app rebuilt?"; developer `log_search` |
| B5 screen PATH regression | `service_health` source row; screen stays covered by #79's PATH (no new work) |
| B6 location | P2 "Where am I?" |
| B7 memory graph | T4.6 test; live "show my memory graph about X" with unknown X shows the overview |
| B8 sports | P6 live "yesterday's MLB scores" |
| B9 core-tier recovery | T4.8 test |
| R1 retry lockout | P1 live Alfreda → Alpharetta |
| R2 / R3 tools vanish or die | P3 acceptance 1 and 2 |
| R4 stale key health | T3.3 tests; live: fix a key, then the recovery sentence within 10 minutes |
| R5 librarian budget | T1.4 |
| R6 reconnect churn | P7 data |

## 7. Kill switches and rollback

| Switch | Default | Off means |
|---|---|---|
| `JARVIS_RETRY_GUARD_SUBSTITUTION_ENABLED` | on | the guard refuses substitutions again (pre-P1) |
| `JARVIS_STATUS_TOOLS_ENABLED` | on | `system_status` is not registered and its addendum is omitted; sidecar status routes return disabled; `mcp-status` tools stay registered and return the sidecar's disabled error (R9) |
| `JARVIS_REGISTRY_SHARED_ENABLED` | on | per-session registry and per-session stop (pre-P3) |
| `JARVIS_NOTICES_ENABLED` | on | no outbox writes or deliveries |
| `JARVIS_KEY_HEALTH_ENABLED` | on (existing) | also disables the refresh loop and the sidecar probe |

Every phase is one PR, so reverting a phase is `git revert <merge>`. P3's migration `0025_notices` is additive; leave the table in place on revert.

## 8. Out of scope

- Status cards in the display window (L14).
- Opening PRs from the daily job (split plan §4a follow-on).
- Automatic changes to which model an agent uses.
- A local-model runtime (`local` route).
- Speaker-gate enablement.
- Anything that writes to a provider account.
- iOS.

## 9. When the spec and the code disagree

Stop the task. In the PR description, write:
- the quoted spec line
- the code evidence (path, quoted text, command output)
- the smallest change to the spec that would resolve it

Do not proceed on that task until Larry answers. Other tasks in the same phase that do not depend on it may continue.
