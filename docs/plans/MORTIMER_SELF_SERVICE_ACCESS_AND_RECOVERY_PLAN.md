# Mortimer — self-service access and sub-agent recovery plan

**Status:** DRAFT for Larry's approval, 2026-09-22. Nothing implemented.
Written against `main` @ `88b206f`, with evidence from the runtime checkout's
logs (`~/jarvis-voice-ai-clean/logs/`, `data/jarvis.db` `agent_runs` since
2026-09-08). Every blocker below cites the run or log line it came from.
Run-log times (`agent_runs.started_at`) are UTC; `bot.launchd.log` times
are local (EDT).

**Governing requirement (Larry, 2026-09-22):** assume the user is not
technical and cannot run terminal commands. If Mortimer's own processes can
read a piece of data, the interface must be able to answer from it. Handing
the user a command is a defect, except when the data lives only somewhere
Mortimer cannot reach, such as a page behind the user's own browser login.

---

## 1. Evidence: what blocked us

### 1.1 Missing access (the user was sent to the terminal or told "I can't")

| # | Date, run | Request | What stopped it |
|---|---|---|---|
| B1 | 09-13 `20:47` developer; 09-22 runs `251fe71b`, `7e235029`, `dfbac8e3`, `42d88905` | Which models are available and working; what the subscriptions include | No tool reads key status, key health, provider catalogs or subscription status. Mortimer handed over `curl` commands that would have returned 401: the keys are in `data/secrets.vault`, and `.env` holds none of them. It also told Larry that models "don't exist in your subscriptions" after reading only `config/upgrade_models.yaml`. |
| B2 | 09-13 `20:52` developer | Add 8 new OpenRouter models to the registry | `config/upgrade_models.yaml` is Tier 0 (`self_edit_allowlist.json:33`), so the only path is a human PR. |
| B3 | 09-09 `00:48`, `01:00` developer | Sync a self-edit branch rejected as non-fast-forward; list open PRs | No tool can pull or rebase a session branch, and no tool reads GitHub PRs. |
| B4 | 09-09 `01:20`–`01:23` developer | Did `bundle.sh` finish, and is the app rebuilt? | "the `logs` read failed and I have no shell/timestamp tool". There is no build-status or log-read tool. |
| B5 | 09-09 `01:04`, `01:24` developer | Look at the screen | `screencapture` was missing from the launchd PATH. Fixed in #79 (the plist PATH now ends `:/usr/sbin:/sbin`), but no health check would catch a recurrence. |
| B6 | 09-13 `21:42` systems, `21:59` scheduler; 09-14 `23:49` analyst | Where am I? What's my timezone? Weather here? | `jarvis/ambient_weather.py` already resolves device location, then IP geolocation (`_resolve_location`), but no agent tool exposes it. |
| B7 | 09-11 `19:11` developer; 09-16 ×3 and 09-18 `16:09` librarian | Draw my memory graph | The developer has no memory graph tool. The librarian's `memory_graph_view` fails whenever the requested focus has no node, instead of drawing an overview. The 09-18 run used up its 5-round budget. |
| B8 | 09-13 `22:44`, `22:50`, `22:49`; 09-17 `00:18` analyst | NFL and MLB scores | Web search returned mixed, stale snippets, and there is no structured scores source. |
| B9 | 09-18 `17:52`, `17:53` developer | A self-edit touching core files | Tier B requires a `plan_path`, and the agent stopped instead of offering to write the plan. This is correct policy with a poor recovery path. |

### 1.2 Sub-agents becoming unusable after an error

| # | Evidence | Mechanism |
|---|---|---|
| R1 | 09-22 `21:53:04` and `21:53:07`: `delegate_retry_guard_refused agent=analyst overlap=0.75`, twice. Mortimer: "We'll need to wait a moment before trying Alpharetta again." | The analyst failed on a misheard place ("Alfreda"). Larry corrected it, and the guard (`delegate.py`, 120 s window, overlap ≥ 0.5) refused the corrected task because it shared 3 of its 4 tokens with the failed one. The guard cannot tell a retry of the same approach from a retry with corrected input. |
| R2 | Runs with `Unknown tool '…'. Available: none` on 08-31, 09-07 and 09-09 (`f370d29e`, 18 s after `[session] client disconnected` at 20:17:45) | The registry belongs to one session. Teardown stopped it while a detached delegation was still running. **Partly fixed** by item 11 (`drain_detached`, 120 s, in `af2d0cf`, deployed and observed working on 09-18 18:22). Still unhandled: runs longer than 120 s, and the finished result has nowhere to go once the session is gone. |
| R3 | `jarvis/skills/registry.py` `start()` / `call()` | Startup is all-or-nothing: one server that fails to start stops every server. There is no restart when an MCP child dies mid-session; every later call fails until the client reconnects. A mid-session child death has not been observed in logs (0 matches for "Connection closed"); this comes from reading the code. |
| R4 | `jarvis/keyhealth.py` `start_background_probe()`, run once at boot | A key refused at boot stays marked unusable, and is announced as broken, until the bot restarts, even after it has been fixed. |
| R5 | 8 `ran out of tool-call rounds` in the logs; 09-18 librarian used 13 tools against a budget of 5 | The librarian and three other agents have the default `MAX_TOOL_ITERATIONS = 5`. An exhausted run stops and relies on a handoff. |
| R6 | 44 `client disconnected` since 09-11; 7 `/ws-client` connects in 25 minutes on 09-18 | Frequent reconnects multiply R2 and cause repeated greetings. The cause is unknown and needs instrumenting before anything is changed. |

---

## 2. Workstreams

### A. Stop handing the user commands (prompt policy)

- **A1.** `AGENT_DISCIPLINE` (`jarvis/prompts.py` ~194): a sub-agent that lacks a tool writes `MISSING-TOOL: <capability>`, not a command for the user. `NEEDS-INPUT:` stays for information that only exists in Larry's head: a choice, a preference, a name.
- **A2.** `HANDOFF_ADDENDUM` (~487): `show_commands` only when Larry asks for commands, or when the data is reachable only through his own browser session. Otherwise say what is missing and offer "want the developer to add that?"
- **A3.** Supervisor rule: the registry says what is *configured*, not what an account *offers*. Never state what a subscription contains unless a catalog or subscription tool answered.
- **A4.** Routing-eval cases pinning each of these, using the 09-22 utterances verbatim.

### B. Read-only access tools: new server `mcp-status`

Wired to the Supervisor as direct tools (no delegation, like `cost_summary`) and to `systems` and `developer`. Everything is read-only. No tool ever returns key material; all output is secret-free, like `/api/model-routes`. Calls to outside services are marked external, so they are blocked on sensitive turns (add the server to `EXTERNAL_TOOL_SERVERS`).

| Tool | Answers | Built from |
|---|---|---|
| `model_access_status` | Configured models, key present, key health, default and fallbacks | `available_models()`, `keyhealth.verdict()` and `detail()`, the `/api/model-routes` payload |
| `provider_model_catalog(provider)` | What Anthropic, OpenRouter and Moonshot offer now, compared with the registry: new, missing, renamed | **New.** In-process `GET` to each provider's model-list endpoint, keys loaded from the vault. Model IDs and dates only. One-hour cache. |
| `subscription_status(which)` | Whether the Claude and Codex subscriptions are signed in and answering; which models were probed | `jarvis/subscription.py` `_run_claude` / `_run_codex` (the same path as `scripts/verify_model_access.py`). Uses a little quota, so it runs **only when asked**; the tool description says so. |
| `service_health` | Whether bot, sidecar, vault, extractor and costs are up and on which version; launchd state | `/api/health`, port checks `:7860 :7861 :8484 :8487`, the source revision recorded at deploy (not `git rev-parse HEAD`: the runtime checkout is a detached HEAD `2ccf66c` with 09-17 files copied over it, so HEAD misreports what is running) |
| `system_overview` | "What's your configuration?" | `/api/architecture`, `/api/knowledge`, `config/agents.yaml`, `config/mcp_servers.yaml` |
| `build_status` | Whether the app was rebuilt, when, and from which commit | `.build/MortimerHost.app` modification time, bundle provenance written by `macos/MortimerHost/scripts/bundle.sh` |
| `log_search(source, query, since, limit)` | "Why did that fail?" | Bounded tail and grep over `logs/` only. Sensitive turns are redacted through the same guard the run log uses. A fixed list of sources, never an arbitrary path. |
| `location_current` | Where am I, which timezone | `ambient_weather._resolve_location` (device location, then IP) |
| `github_read(kind)` | Open PRs, PR state, CI checks for Mortimer's own repo | `mcp_apps/github.py` `GitHubClient` credentials, read-only REST |

Location also goes to `analyst` and `scheduler` (B6). `github_read` also goes to `developer` (B3).

### C. Unblock the actions that were refused

- **C1 (B2): model additions without a hand-edited PR.** Implement `docs/plans/MORTIMER_MODEL_REGISTRY_SPLIT_PLAN.md`, which is already approved in outline. Adding a model then becomes a Tier-A `model_profiles.yaml` edit reviewed in the Edit tab, while endpoints and keys stay Tier 0. Pair it with `provider_model_catalog`, so "add the new OpenRouter models" can be staged from real catalog data. Update the plan first for what #80 changed: `model_routing.py` now reads `upgrade_models.yaml` directly, and the registry has 14 profiles.
- **C2 (B3): `selfedit_sync`.** Inside the sandbox session, fetch the session branch's remote and rebase onto it (merge if the rebase conflicts), re-validate, then allow `selfedit_finish` to push. It never touches Larry's checkout.
- **C3 (B7): memory graph falls back to an overview.** When no node matches the focus, draw the top-N most-connected nodes and say the focus had no match, instead of returning FAILED. Give the developer `memory_graph_view`.
- **C4 (B8): structured sports scores.** Add `sports_scores(league, date)` to `mcp-web` from a structured scoreboard source. **Untested:** which source is stable and allowed needs a check before building. Fall back to search with an explicit "unconfirmed" label.
- **C5 (B9): core-tier recovery.** When `selfedit_start` refuses a Tier-B goal for lack of a plan, the developer offers `plan_start` with the same goal, and the adopted plan flows into `plan_path`. This is a prompt change plus one test; policy is unchanged.

### D. Sub-agents must never be left unusable

- **D1 (R1): make the retry guard input-aware.** Keep its purpose: stop a reworded retry of the *same approach*. Change three things:
  1. **Exempt any retry that adds new content.** If the new task contains a token of 4 or more characters that the failed task lacked, the input changed (for example `alpharetta` versus `alfreda`), so let it run.
  2. **Block only after two near-identical failures.** Arm the guard on the second consecutive near-identical failure, not the first. Key it by task fingerprint, not by agent, so one failed task never blocks unrelated work for that agent.
  3. **Change the refusal message.** It tells the Supervisor to try a different approach or ask the user. It must never tell anyone to "wait", because waiting changes nothing.

  Tests: the exact 09-22 Alfreda to Alpharetta sequence runs; three identical failed retries still get refused on the third.
- **D2 (R2, R3): process-scoped, supervised registry.**
  - **Start once per process.** The registry starts at bot boot, not per session. Sessions borrow it, and teardown no longer stops it, which removes R2 entirely along with the 120 s drain as a correctness mechanism.
  - **Supervise each server.** When a child process dies, restart it once, rediscover its tools and retry the call. After a second failure, mark only that server down, report `"<server> is down: <reason>"` from the affected tools, and try restarting it on the next call after a backoff.
  - **Isolate startup failures.** A server that fails to start is logged and marked down; every other server still starts.
  - **Env and sensitive-turn rules are unchanged.** `build_child_env` stays per server, and the sensitive-turn check stays per call, so per-session state still lives in the ContextVar, not the registry.
- **D3 (R2): late results survive a reconnect.** A detached run that finishes after its session has ended writes its result to a small outbox (`late_results`, keyed by user). The next session speaks it once after the greeting: "While you were away, the developer finished: …".
- **D4 (R4): refresh key health.** Re-probe a key after any `rejected` or `unfunded` verdict every 10 minutes, and immediately when a call with that key succeeds. Announce recovery using the existing `KEYHEALTH_RECOVERED_TEMPLATE`.
- **D5 (R5): iteration budget.** Set librarian `max_iterations: 10`, based on the 09-18 run's 13 tool calls. For read-only tasks, an exhausted run continues automatically once with its findings (the handoff continuation path, which the run has already earned), without asking Larry.
- **D6 (R6): reconnect churn.** First step is instrumentation only. Log the disconnect reason on both sides (MortimerHost `NativeAudioTransport` close code and the server's cancel cause). Decide on a fix only after one day of data.

---

## 3. Sequence

| Phase | Contents | Why this order |
|---|---|---|
| 1 | D1, D5, A1–A4 | Small, tested edits that remove the two failures Larry hit on 09-22: the retry lockout and being handed curl commands. |
| 2 | B: `mcp-status` with `model_access_status`, `service_health`, `system_overview`, `location_current`, `log_search`, `build_status` | Read-only, in-process data. Answers most B-row questions. |
| 3 | D2, D3, D4 | Structural resilience. D2 is the largest change and touches the bot lifecycle, so it lands on its own. |
| 4 | `provider_model_catalog`, `subscription_status`, `github_read`, C2, C3, C5 | Needs outbound calls or sandbox work. |
| 5 | C1 (registry split), C4 (sports), D6 decision | Depends on phase 4 data or on Larry's decisions. |

Each phase is one PR through the sandbox profile (full unit and integration suites, plus `swift test` where Swift changes) and is deployed before the next begins.

## 4. Acceptance, spoken and checked against the run log

1. "What models do I have access to, and are they working?" answered in one turn, with no command shown and no delegation.
2. "Is Fable 5.1 on my Claude subscription?" answered from `subscription_status` or a catalog result, or with a plain "I don't have a tool that can see that yet", never from the registry.
3. The 09-22 Alfreda to Alpharetta weather sequence succeeds on the corrected retry.
4. Disconnect the app during a developer run of more than 2 minutes. The run finishes with no `Available: none`, and its result is spoken at the next connect.
5. Kill `mcp-web`'s process mid-session. The next analyst weather request restarts it and succeeds.
6. "Where am I?", "Did the rebuild finish?", "Show my memory graph" and "Any open PRs?" all get answers.
7. `grep -c "show_commands" logs/bot.launchd.log` over a week of normal use shows only calls where Larry asked for commands.

## 5. Kill switches

Each has one enforcement point: `JARVIS_STATUS_TOOLS_ENABLED`, `JARVIS_PROVIDER_CATALOG_ENABLED`, `JARVIS_REGISTRY_SUPERVISION_ENABLED` (off means today's per-session registry) and `JARVIS_LATE_RESULTS_ENABLED`.

## 6. Decisions for Larry

1. May `subscription_status` spend a small amount of subscription quota whenever you ask? Recommended: yes, only on request.
2. May `provider_model_catalog` call provider APIs on request, and once a day on a schedule to flag new models? Recommended: on request now, schedule later.
3. Registry: implement the split (C1), or keep a human-reviewed PR for every model addition, now generated automatically from catalog data?
4. Sports scores: add a structured source (C4), or accept search-quality answers labeled "unconfirmed"?

## 7. Unverified (and what settles it)

- Whether the `claude` and `codex` CLIs can **list** a subscription's models without a real prompt. Check each CLI's help and version on the Mac.
- Moonshot's `/v1/models` with the configured key. One call from `provider_model_catalog`.
- The cause of the reconnect churn (D6 instrumentation).
- Whether a mid-session MCP child crash happens in practice (D2's supervision logs will show it).
