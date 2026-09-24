# Repository map

See [ARCHITECTURE.md](ARCHITECTURE.md) for system ownership and model routes.

Verify paths and the current branch before writing. Keep this map below the
8,000-character prompt cap (`jarvis/repo_map.py`).

## Top-level layout

- `services/mortimer-vault/` — knowledge-base HTTP service, CLI, tests;
  setup `bash scripts/setup_kb.sh`. Documents stay at `MORTIMER_HOME`.
- `jarvis/` — Python backend (see below).
- `mcp_servers/` — MCP skill servers, one directory each: `logic.py`
  (pure) + `server.py` (FastMCP) + `skill.yaml`. `mcp_kb/` is read-only
  (`kb_search`/`kb_read`/`kb_neighbors`); KB writes go through
  `jarvis/kb_digest.py`, not MCP. `mcp_status/` — systems/developer
  status + `log_search`, a thin client of the sidecar's `/api/status/*`.
- `skills/` — Agent Skills (`SKILL.md`), loaded by `jarvis/agent_skills.py`
  only if enabled in `config/skills.yaml`; never executed.
- `macos/` — native macOS client (SwiftPM), the live interface:
  `JarvisKit/` library, `MortimerHost/` app, `VPIOBench/` echo bench.
- `web/` — React/Vite console. FROZEN 2026-09-04; not started by
  `mortimer.sh` (manual fallback `scripts/run_web.sh`).
- `sandbox/` — disposable macOS VMs, guarded files, verification, PRs.
- `config/` — routing/model YAML/JSON (agents, MCP servers, voices,
  skills, self-edit allowlist, `upgrade_models.yaml` registry,
  `model_access.yaml`). Check here first when a capability seems
  misrouted or over/under-permissioned.
- `docs/` — `plans/` (+ `implemented/`), `reviews/`, `acceptance/`,
  `archive/` (superseded; history only). This file.
- `tests/` — `unit/` (no external calls), `integration/` (MCP-over-stdio,
  registry, bot wiring), `evals/` (live routing eval), `acceptance/`
  (manual checklists, not run by pytest).
- `scripts/` — run/setup/check (`mortimer.sh`, `run_bot.sh`,
  `run_admin.sh`, `init_db.py`, `check_env.py`), `cost_report.py`,
  `pull_openrouter_activity.py`, `backup_db.py` (SQLite snapshots, keeps
  14 per database), `launchd_gen.py` (launchd plists: vault, bot,
  extractor, admin, costs + nightly backup; the reminder notifier runs
  inside the admin sidecar).
- `data/` — gitignored: `jarvis.db`, `secrets.vault`,
  `app_workspaces/` (legacy metadata; code lives in VMs).
- `logs/` — gitignored: per-run JSONL `agents/<date>/`, council rounds
  `council/<date>/`.

## `jarvis/` backend

- `jarvis/bot/` — `bot.py` (entry: WebRTC `/api/offer` or native
  WebSocket `/ws-client` via `ws_transport.py`), `pipeline.py` (STT →
  Supervisor LLM → TTS), `display.py` (tool result → UI surface),
  `ui_control.py` (voice drawer/display/mic actions),
  `console_{protocol,session,actions}.py` (Command Console protocol),
  `shared_content*.py` (approved text/image staging).
- `jarvis/agents/` — `supervisor.py` (delegate-only Orchestrator),
  `base.py` (`SubAgent`: model/timeout/repo-map), `delegate.py`
  (`delegate_task` + retry guard), `upgrade_agent.py` (self-edit loop +
  registry helpers), `workspace.py` (adapter in `sandbox/workspace.py`).
- `jarvis/admin/server.py` — admin sidecar (`:7861`): self-edit,
  planning, council, app workspaces; drawer panels' backend.
- `jarvis/council/` — `council.py` (convene/draft_candidates),
  `scoring.py`, `config.py` (tiers, timeouts, caps), `agreement.py`.
- `jarvis/runlog/` — `store.py` (RunLogger + readers), `cli.py`
  (`python -m jarvis.runlog`).
- `jarvis/graphs/` — derived read-only graphs (memory / capability /
  execution / deliberation) + PNG/SVG renderer; sidecar `/api/graph/*`
  and voice tools `memory_graph_view`, `graph_view`. Nothing else
  derives an edge.
- `jarvis/status/` — self-service status computed in the sidecar
  (models, services, overview, build, location, logs, summaries); voice
  tool `jarvis/bot/status_tool.py` (`system_status`).
- `jarvis/selfedit/service.py` — sandbox facade: allowlist, validation, PRs.
- `jarvis/skills/registry.py` — MCP servers, one owner task each,
  restarted on death; `shared.py` keeps one registry per process.
- `jarvis/prompts.py` — single source of every system prompt.
- `jarvis/notices.py` — notice outbox: late results, daily status;
  spoken once after the next greeting.
- `jarvis/db.py` — SQLite schema + migrations (human-only).
- `jarvis/tenant.py` — `current_user_id()` from `JARVIS_USER_ID`,
  default `"local"` (column exists; nothing filters by it yet).
- `jarvis/vault.py` — encrypted credential store (CLI-only).
- `jarvis/usage_ledger.py` — per-call LLM usage ledger, `data/costs.db` (`llm_calls`).
- `jarvis/costs_api.py` — sidecar HTTP over the ledger (`GET /costs/summary`).
- `jarvis/memory_extraction.py` — per-exchange candidates/novelty gate.
- `jarvis/memory_extraction_worker.py` — async post-turn extractor.
- `jarvis/memory_automation.py` — memory classification/admission policy.
- `jarvis/memory_model.py` — memory/background registry-profile routes.
- `jarvis/kb_digest.py` — session-end knowledge-base digester.
- `jarvis/effort.py` — native-Anthropic effort control.
- `jarvis/anthropic_shim.py` — OpenAI-shaped native Messages client.
- `jarvis/model_routing.py` — workload/route policy, fail-closed clients.
- `jarvis/model_execution.py` — provider-neutral execution contract.
- `jarvis/privacy_policy.py` — data-policy enforcement.
- `jarvis/saygm.py` — SAYGM catalog, confidential-tier proof.
- `jarvis/subscription.py` — gated Claude/Codex text adapters.
- `jarvis/sensitive.py` — financial-detail detection.
- `jarvis/bot/sensitive_turn.py` — per-turn sensitive flag.
- `jarvis/bot/usage_watcher.py` — pipeline observer for the cost ledger.
- `jarvis/bot/late_result.py` — strips a late delegation's internal
  "relay this" wrapper before speaking.
- `jarvis/bot/costs_tool.py` — `cost_summary` Supervisor tool (always
  registered).
- `jarvis/procedures.py` — learned task-shape hints per run.
- `jarvis/toolresult.py` — the one tool success/failure classifier.

## `macos/` native client

`MortimerHost` depends on `JarvisKit` by path; a JarvisKit change rebuilds
both. Self-edit may change the Swift **sources** below, gated by
`swift build` + `swift test` in an independent VM and a PR flagged SWIFT
CHANGE, inert until a human runs `MortimerHost/scripts/bundle.sh`.
Manifests, plists, entitlements, `scripts/`, `GlassSpike/`,
`MortimerShell/` are human-only.

- `JarvisKit/Sources/JarvisKit/` — `JarvisClient.swift` (voice session),
  `AdminAPI.swift` (sidecar calls), `AppMessage`/`ClientMessage` (RTVI
  shapes; change with the backend), `ConsoleProtocol`, transports
  (`RTVITransport`; `NativeAudioTransport` + `PipecatFrameCodec` for a
  same-Mac bot, default; `DirectWebRTCTransport` + `Signalling` for remote
  or `JARVIS_FORCE_WEBRTC`), `AudioEngineIO`, `AudioActivityObserver`,
  `WakeWordListener`, `KeychainStore`.
- `MortimerHost/Sources/MortimerHost/App/` — `MortimerHostApp`,
  `AppMessageRouter`, `UICommandRouter` (voice `ui_control`),
  `ConsoleAction*`, `AppTheme`/`AppTuning`/`Glass`, `VoiceState`, `Sounds`.
- `.../Console/` — `ConsoleView` picks `layoutVersion`: 2
  `CommandConsoleView` (default), 1 `AdaptiveStageView`, 0 legacy orb
  (`OrbFieldView`/`VoiceWaveView`); `TopBarView`, `MicControlsView`, etc.
- `.../Drawer/` — `DrawerView`, one file per tab (`EditTab` drives
  `/api/selfedit/*`, `RepoTab`, `AgentsTab`, `RunsTab`, `MemoryTab`,
  `CostsTab`, `OutputTab`, `LogTab`), `TabState`.
- `.../Display/` — result window (`DisplayWindowView`, `DisplayWindowStore`),
  `KnowledgeAtlasView`, `Workspace*`, `Share*`, `GraphImageView`.
- `.../Placement/`, `.../Stores/` — placement; view stores.

## Naming discipline (do not confuse these)

- "sidecar" = the admin Python process on `:7861` (`jarvis/admin/server.py`)
  — never the side drawer.
- "drawer" = the tabbed side panel (`DrawerView.swift`) — never the
  console; neither is a popped-out window.
- "display window" = the informational-result window
  (`DisplayWindowView.swift`) — separate from the drawer.
