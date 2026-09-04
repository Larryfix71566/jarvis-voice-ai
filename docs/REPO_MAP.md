# Repository map

Maintained, may lag reality — verify with tools (`repo_read_file`,
`repo_list_files`, `repo_search`) before writing. Update this file in
the same change whenever a structural move happens (new top-level
module, moved directory) — see CLAUDE.md.

Never assume a branch name; check `git_status` / `repo_search` for the
current branch.

## Top-level layout

- `jarvis/` — Python backend: bot pipeline, sub-agents, admin sidecar,
  council, run log, self-edit service. See below.
- `mcp_servers/` — MCP skill servers, one directory per server, each
  with `logic.py` (pure, testable) + `server.py` (FastMCP wiring) +
  `skill.yaml` (manifest). Includes `mcp_kb/` — read-only tools
  (`kb_search`/`kb_read`/`kb_neighbors`) over the knowledge-base
  service; writes go through `jarvis/kb_digest.py` directly, not MCP.
- `web/` — the React/Vite console (frontend). See below.
- `config/` — YAML/JSON routing and model config (agents, MCP servers,
  voices, self-edit allowlist, upgrade models/agent bounds). Check here
  first when a capability seems misrouted or over/under-permissioned.
- `docs/` — `plans/` (implementation plans + specs, `plans/implemented/`
  for completed ones), `reviews/` (adopted model reviews). This file.
- `tests/` — `unit/` (no external calls), `integration/` (MCP-over-stdio,
  registry, bot wiring), `evals/` (live routing eval), `acceptance/`
  (manual checklists, not run by pytest).
- `scripts/` — run/setup/check scripts (`mortimer.sh`, `run_bot.sh`,
  `run_admin.sh`, `run_web.sh`, `init_db.py`, `check_env.py`, etc.),
  plus `cost_report.py` (prints the cost-ledger summary) and
  `pull_openrouter_activity.py` (pulls OpenRouter usage into it).
- `data/` — gitignored: `jarvis.db` (SQLite), `secrets.vault`,
  `app_workspaces/` (cloned app repos, self-edit-denied).
- `logs/` — gitignored: per-run JSONL payloads under `agents/<date>/`,
  council rounds under `council/<date>/`.

## `jarvis/` backend

- `jarvis/bot/` — `pipeline.py` (Pipecat pipeline: STT → Supervisor LLM
  → TTS), `display.py` (tool-result → UI surface routing),
  `ui_control.py` (voice-controlled drawer/display/mic actions).
- `jarvis/agents/` — `supervisor.py` (Orchestrator, delegate-only
  brain), `base.py` (`SubAgent` — per-agent model/timeout/repo-map),
  `delegate.py` (`delegate_task` tool + retry guard),
  `upgrade_agent.py` (self-edit loop + model registry helpers),
  `app_build_agent.py` (app-build loop, if present — Part D),
  `workspace.py` (the Workspace seam shared by both loops, if present).
- `jarvis/admin/server.py` — the admin sidecar (`:7861`): self-edit,
  planning, council, app-build (if present) job endpoints; console Git/
  Memory panels' backend.
- `jarvis/council/` — `council.py` (convene/draft_candidates),
  `scoring.py`, `config.py` (tiers, timeouts, char caps),
  `agreement.py` (judge-quality reporting).
- `jarvis/runlog/` — `store.py` (RunLogger + read helpers), `cli.py`
  (`python -m jarvis.runlog`).
- `jarvis/selfedit/service.py` — the self-edit sandbox: branch, allow-
  list check, validation gate, PR.
- `jarvis/skills/registry.py` — spawns MCP servers as subprocesses,
  exposes their tools.
- `jarvis/prompts.py` — single source of truth for every system prompt.
- `jarvis/db.py` — SQLite schema + migrations (human-only, never
  self-edited).
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

## `web/src/` console

- `App.tsx` — top-level layout, topbar, RTVI listeners (only two:
  `AgentStatusPanel` for agent lifecycle, `App.tsx` itself for
  `type:"display"`/`type:"ui"` messages — never add a third).
- `components/OrbField.tsx` — the center voice wave + satellites.
- `components/AmbientStrip.tsx` — the upper-left strip: clock, next
  reminder, session summary, cached weather.
- `components/SideDrawer.tsx` — the right-side tabbed drawer (Repo,
  Edit, Memory, Runs, Dev, Output, Log tabs) — see its own tab-body
  components (`GitPanel.tsx`, `EditModePanel.tsx`, `MemoryPanel.tsx`,
  `RunsPanel.tsx`, `DeveloperRunsTab.tsx`, `OutputTab.tsx`,
  `Transcript.tsx`).
- `components/DisplayPanel.tsx` — the floating informational-result
  overlay (weather, research); poppable to a second window.
- `components/DrawerWindowApp.tsx` / `DisplayWindowApp.tsx` — the
  popped-out window roots (separate Vite entries: `drawer.html`,
  `display.html` — their import graphs must never reach
  `jarvisClient.ts` or use a `@pipecat-ai/client-react` hook).
- `popoutWindow.ts` — shared pop-out presence/placement plumbing used
  by both the display and drawer windows.
- `agentRuns.ts`, `displayResults.ts`, `conversationFeed.ts` — the
  RTVI-fed module stores (fed only by `AgentStatusPanel`/`App.tsx`;
  relayed to popped windows via `drawerRelay.ts`, never via a second
  RTVI listener).
- `uiCommands.ts` — voice `ui_control` command dispatch.

## Naming discipline (do not confuse these)

- "sidecar" = the admin Python process on `:7861` (`jarvis/admin/server.py`)
  — never the side drawer, never a popped-out window.
- "drawer" = the tabbed side panel (`SideDrawer.tsx`) — its popped form
  is "the drawer window".
- "display window" = the informational-result popup (`DisplayPanel.tsx`)
  — separate from the drawer window.
