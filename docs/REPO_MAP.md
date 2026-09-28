# Repository map

See [ARCHITECTURE.md](ARCHITECTURE.md) for runtime ownership, trust boundaries
and model routing. The [Skills Workspace plan](plans/MORTIMER_SKILLS_WORKSPACE_IMPLEMENTATION_PLAN.md)
and [acceptance status](acceptance/skills-workspace/STATUS.md) are current
references. Keep this injected navigation map below 8,000 characters
(`jarvis/repo_map.py`). Verify branch and paths before editing.

## Top level

- `jarvis/` — Python bot, agents, admin API, status, memory, routing and tools.
- `macos/` — native macOS client: `JarvisKit/`, `MortimerHost/`, `VPIOBench/`.
- `mcp_servers/` — MCP servers, generally `logic.py` (pure logic),
  `server.py` (FastMCP) and `skill.yaml`. `mcp_kb/` is read-only;
  KB writes go through `jarvis/kb_digest.py`. `mcp_status/` is a thin client
  of sidecar status APIs.
- `skills/` — reusable Agent Skill packages configured by `config/skills.yaml`;
  metadata/digests are cataloged, packages are not executed as MCP servers.
- `services/mortimer-vault/` — separate knowledge-base service and CLI;
  documents stay at `MORTIMER_HOME`.
- `sandbox/` — disposable macOS VMs, guarded file access, verification and PRs.
- `config/` — agents, MCP, voices, skill packages, self-edit allowlist,
  model profiles/endpoints/access policy and generated status catalogs.
- `docs/` — `plans/`, `acceptance/`, `reviews/`, `archive/` (history), and
  architecture references.
- `tests/` — `unit/` (offline), `integration/` (wiring and MCP), `evals/`
  (live routing eval), `acceptance/` (manual gates).
- `scripts/` — startup/setup/checks, backup, cost and status jobs; see
  `mortimer.sh`, `run_bot.sh`, `run_admin.sh`, `init_db.py`, `check_env.py`.
- `data/` and `logs/` — runtime-only, gitignored DB/vault/status and run logs.
- `web/` — frozen React/Vite fallback; not launched by `mortimer.sh`.

## Backend paths

- `jarvis/bot/`: `bot.py` (WebRTC `/api/offer`, native WebSocket
  `/ws-client`), `pipeline.py` (STT/Supervisor/TTS), `display.py`,
  `ui_control.py`, `console_{protocol,session,actions}.py`,
  `shared_content*.py`, status and sensitivity tools.
- `jarvis/agents/`: `supervisor.py` (delegation and bounded direct tools), `base.py` (`SubAgent`),
  `delegate.py`, `upgrade_agent.py`, `workspace.py`.
- `jarvis/admin/server.py`: admin sidecar (bearer auth when enabled) (`:7861`) for
  self-edit, planning, workflow/status inspection, Skills catalog/creator,
  Council and app workspaces.
- `jarvis/skills/registry.py`: supervised MCP subprocess registry;
  `shared.py` owns the per-process registry. Keep Skills distinct from
  Workflows: packages are reusable instructions; workflows are operational
  process/status descriptions.
- `jarvis/skill_catalog.py`, `skill_requests.py`,
  `jarvis/bot/skill_creator_dispatch.py`,
  `jarvis/skill_validation_activity.py`: skill metadata,
  owner-scoped creator requests, actual Developer-run association and
  validation events. Never substitute request or sandbox IDs for a Developer
  run ID.
- `jarvis/status/`: sidecar status implementation (services, models, builds,
  logs, subscriptions, GitHub, summaries; `daily.py` is scheduled job).
  `jarvis/bot/status_tool.py` and `mcp_status/` are clients.
- `jarvis/runlog/`: `store.py` run/event persistence and readers; `cli.py`.
- `jarvis/council/`: deliberation/config/scoring; `jarvis/graphs/`: derived
  read-only memory/capability/execution/deliberation graphs.
- `jarvis/selfedit/service.py`: sandbox facade, allowlist, validation and PRs.
- `jarvis/db.py`: SQLite schema/migrations. `jarvis/auth.py` and
  `authmw.py`: authenticated request identity; `tenant.py`: validated,
  request-scoped tenant context. User-scoped APIs must enforce ownership
  server-side; do not trust UI filters or caller-supplied identity.
- `jarvis/vault.py`: encrypted credential store (CLI); `jarvis/prompts.py`:
  prompt source; `jarvis/notices.py`: late-result/status outbox.
- Memory: `memory_extraction.py`, `memory_extraction_worker.py`,
  `memory_automation.py`, `memory_sweep.py`, `memory_model.py`, `memory.py`.
  Consult its plan/status before changing semantics.
- Model execution: `model_routing.py`, `model_execution.py`,
  `privacy_policy.py`, `model_preferences.py`, `saygm.py`,
  `subscription.py`, `anthropic_shim.py`, `effort.py`.
- Privacy/session results: `jarvis/sensitive.py`, `jarvis/bot/sensitive_turn.py`,
  `jarvis/bot/late_result.py` (late-result wrapper handling).
- Host operations: `scripts/backup_db.py` (SQLite snapshots) and
  `scripts/launchd_gen.py` (service/job definitions).
- Ownership: `jarvis/tenant.py` supplies the request-scoped user context.
- Usage/cost: `usage_ledger.py`, `costs_api.py`, `bot/usage_watcher.py`,
  `bot/costs_tool.py`.

## Native client

`MortimerHost` depends on `JarvisKit` by path, so library changes rebuild both.
Self-editable Swift sources require independent-VM `swift build` and
`swift test` plus PR review; bundling/deployment remains a human release step.
Manifests, plists, entitlements, scripts and legacy shell/spike targets are
human-only per the self-edit allowlist.

- `macos/JarvisKit/Sources/JarvisKit/`: `JarvisClient.swift`, `AdminAPI.swift`,
  RTVI protocol/messages, native audio and WebRTC transports, audio/wake-word
  observers and Keychain access.
- `macos/MortimerHost/Sources/MortimerHost/App/`: app, message/UI routers,
  console actions, theme/glass, voice state and sounds.
- `.../Console/`: `ConsoleView` selects layout 2 `CommandConsoleView` (default),
  layout 1 `AdaptiveStageView`, or layout 0 legacy orb/wave.
- `.../Drawer/`: tabs and state; `EditTab` calls `/api/selfedit/*`.
- `.../Display/`: result window, Knowledge Atlas, workspaces, sharing and
  graph image view. `.../Placement/` and `.../Stores/`: screen placement/state.

## Naming discipline

- **Sidecar:** Python admin process on `:7861`; not the side drawer.
- **Drawer:** tabbed native panel (`DrawerView.swift`); not a result window.
- **Display window:** informational result surface (`DisplayWindowView.swift`),
  separate from drawer and console.
- **Skill:** reusable instruction package. **Workflow:** operational process
  sequence/status. They have separate APIs, data and UI semantics.
