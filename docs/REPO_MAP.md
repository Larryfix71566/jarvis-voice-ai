# Repository map

Verify paths and the current branch before writing. Keep this map below the
8,000-character prompt cap (`jarvis/repo_map.py`).

## Top-level layout

- `services/mortimer-vault/` — knowledge-base HTTP service, CLI and tests;
  setup: `bash scripts/setup_kb.sh`. Documents remain at `MORTIMER_HOME`.
- `jarvis/` — Python backend: bot pipeline, sub-agents, admin sidecar,
  council, run log, self-edit service. See below.
- `mcp_servers/` — MCP skill servers, each with `logic.py`, `server.py`
  and `skill.yaml`. `mcp_kb/` is read-only; KB writes go through
  `jarvis/kb_digest.py`.
- `macos/` — the native macOS client (Swift, SwiftPM). `JarvisKit/` is
  the shared library, `MortimerHost/` the app that consumes it. This is
  the live interface; `web/` is frozen. See below.
- `web/` — the React/Vite console. FROZEN 2026-09-04 and not served:
  interface work goes to `macos/MortimerHost`.
- `sandbox/` — disposable macOS VMs, guarded files, checks and PRs.
- `config/` — YAML/JSON routing and model config (agents, MCP servers,
  voices, self-edit allowlist, upgrade models/agent bounds). Check here
  first when a capability seems misrouted or over/under-permissioned.
- `docs/` — `plans/` (implementation plans + specs, `plans/implemented/`
  for completed ones), `reviews/` (adopted model reviews). This file.
- `tests/` — `unit/` (no external calls), `integration/` (MCP-over-stdio,
  registry, bot wiring), `evals/` (live routing eval), `acceptance/`
  (manual checklists, not run by pytest).
- `scripts/` — run/setup/check scripts (`mortimer.sh`, `run_bot.sh`,
  `run_admin.sh`, `init_db.py`, `check_env.py`), plus `cost_report.py`,
  `pull_openrouter_activity.py`, `backup_db.py` (SQLite snapshots,
  14 snapshots per database) and `launchd_gen.py` (the launchd plists that
  supervise the bot/admin/reminder-notifier processes).
- `data/` — gitignored: `jarvis.db`, `secrets.vault`,
  `app_workspaces/` (legacy metadata; code lives in VMs).
- `logs/` — gitignored: per-run JSONL under `agents/<date>/`, council
  rounds under `council/<date>/`.

## `jarvis/` backend

- `jarvis/bot/` — `pipeline.py` (Pipecat pipeline: STT → Supervisor LLM
  → TTS), `display.py` (tool-result → UI surface routing),
  `ui_control.py` (voice-controlled drawer/display/mic actions).
- `jarvis/agents/` — `supervisor.py` (Orchestrator, delegate-only
  brain), `base.py` (`SubAgent` — per-agent model/timeout/repo-map),
  `delegate.py` (`delegate_task` tool + retry guard),
  `upgrade_agent.py` (self-edit loop + model registry helpers),
  `workspace.py` (workspace interface; adapter in `sandbox/workspace.py`).
- `jarvis/admin/server.py` — the admin sidecar (`:7861`): self-edit,
  planning, council, sandbox app-workspace endpoints; console Git/
  Memory panels' backend.
- `jarvis/council/` — `council.py` (convene/draft_candidates),
  `scoring.py`, `config.py` (tiers, timeouts, char caps),
  `agreement.py` (judge-quality reporting).
- `jarvis/runlog/` — `store.py` (RunLogger + read helpers), `cli.py`
  (`python -m jarvis.runlog`).
- `jarvis/graphs/` — derived, read-only relationship graphs (memory /
  capability / execution / deliberation) + PNG/SVG renderer; served by the
  sidecar's `/api/graph/*` and two voice tools (`memory_graph_view`,
  `graph_view`). One implementation: nothing else derives an edge.
- `jarvis/selfedit/service.py` — sandbox facade: allowlist, validation, PRs.
- `jarvis/skills/registry.py` — spawns MCP servers as subprocesses,
  exposes their tools.
- `jarvis/prompts.py` — single source of truth for every system prompt.
- `jarvis/db.py` — SQLite schema + migrations (human-only, never
  self-edited).
- `jarvis/tenant.py` — `current_user_id()`: reads `JARVIS_USER_ID`,
  defaults to `"local"` (GC8 — column added everywhere, nothing filters
  reads/writes by it yet).
- `jarvis/vault.py` — encrypted credential store (CLI-only).
- `jarvis/usage_ledger.py` — per-call LLM usage ledger, its own
  `costs.db` (`llm_calls`) (MORTIMER_OPTIMIZATION_PLAN.md Phase 0).
- `jarvis/costs_api.py` — HTTP surface over the cost ledger for the
  admin sidecar (`GET /costs/summary`).
- `jarvis/memory_extraction.py` — Phase 2 per-exchange candidate
  extraction + novelty gate ("Extraction Gate").
- `jarvis/memory_extraction_worker.py` — standalone async post-turn
  extraction service (own Procfile entry).
- `jarvis/kb_digest.py` — session-end digester feeding the knowledge-
  base service (mcp-kb / mortimer-vault).
- `jarvis/effort.py` — `output_config.effort` control for native-
  Anthropic (Path B) call sites.
- `jarvis/anthropic_shim.py` — OpenAI-shaped client shim over
  Anthropic's native Messages API (Path B).
- `jarvis/sensitive.py` — financial-detail detection for the
  sensitive-turn guard (T4a, contract K3), stdlib only.
- `jarvis/bot/sensitive_turn.py` — the per-turn sensitive ContextVar
  flag; `is_sensitive()` is FAIL-CLOSED when unset (T4a).
- `jarvis/bot/usage_watcher.py` — pipeline observer hooking LLM calls
  into the cost ledger (Phase 0).
- `jarvis/bot/late_result.py` — strips a late/orphaned delegation's
  internal "relay this to the user" wrapper text before speaking it.
- `jarvis/bot/costs_tool.py` — the `cost_summary` direct Supervisor
  tool (registered unconditionally, no kill switch).
- `jarvis/procedures.py` — learned task-shape hints injected per run.
- `jarvis/toolresult.py` — the one tool-success/failure classifier,
  shared by the registry and the sub-agent loop.

## `macos/` native client

The interface. `MortimerHost` (the app) depends on `JarvisKit` (the
shared library) by path, so a JarvisKit change rebuilds both. Self-edit
may change the Swift **sources** below — gated by `swift build` +
`swift test` in an independent VM, PR flagged SWIFT CHANGE, and inert
until a human runs `macos/MortimerHost/scripts/bundle.sh`. Manifests,
plists, entitlements, `scripts/`, `GlassSpike/` and `MortimerShell/` are
human-only.

- `JarvisKit/Sources/JarvisKit/` — `JarvisClient.swift` (voice session),
  `AdminAPI.swift` (every sidecar call the app makes; the Python side is
  `jarvis/admin/server.py`), `AppMessage.swift`/`ClientMessage.swift`
  (RTVI message shapes — mirror the backend's, change both together),
  plus transport (`RTVITransport` the protocol, with
  `DirectWebRTCTransport` + `Signalling` for remote and
  `NativeAudioTransport` + `PipecatFrameCodec` for a same-Mac bot),
  audio (`AudioEngineIO` owns capture and playout on the native path,
  `AudioActivityObserver` the measured levels behind the wave),
  `WakeWordListener`, `KeychainStore`.
- `MortimerHost/Sources/MortimerHost/App/` — `MortimerHostApp` (entry),
  `AppMessageRouter` (app message → UI state), `UICommandRouter` (voice
  `ui_control` dispatch), `AppTheme`/`AppTuning`/`Glass` (style and
  tunables), `VoiceState`, `Sounds`.
- `.../Console/` — always-visible console: `ConsoleView`, `OrbFieldView`
  and `VoiceWaveView` (the orb), `AmbientStripView`, `TopBarView`,
  `MicControlsView`, `SystemVitalsView`.
- `.../Drawer/` — tabbed drawer, one file per tab: `DrawerView`,
  `EditTab` (drives `/api/selfedit/*`), `RepoTab`, `AgentsTab`,
  `RunsTab`, `MemoryTab`, `CostsTab`, `OutputTab`, `LogTab`, `TabState`.
- `.../Display/` — the result window: `DisplayWindowView`,
  `DisplayContentView`, `DisplayWindowStore`, `GraphImageView` (renders
  graph-layer images).
- `.../Placement/`, `.../Stores/` — placement; view stores.

## `web/src/` console (frozen)

Frozen 2026-09-04. Interface work goes to `macos/MortimerHost`.

## Naming discipline (do not confuse these)

- "sidecar" = the admin Python process on `:7861` (`jarvis/admin/server.py`)
  — never the side drawer, never a popped-out window.
- "drawer" = the tabbed side panel (`DrawerView.swift`) — never the
  console, never a popped-out window.
- "display window" = the informational-result window
  (`DisplayWindowView.swift`) — separate from the drawer.
