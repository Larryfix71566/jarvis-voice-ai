# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Mortimer (internal package name `jarvis`) is a local-first voice AI agent: speech in, agentic reasoning, speech out. A single voice-facing **Supervisor** LLM understands intent and delegates to five text-only sub-agents (Scheduler, Librarian, Analyst, Systems, Developer), each backed by one or more MCP skill servers running as separate processes. State is local SQLite; the only cloud dependencies are the speech/LLM/search APIs (and GitHub, if app-development or self-edit features are enabled).

*(`jarvis/` and all `JARVIS_*` env vars are stable internal identifiers — do not rename them. Everything user-facing says "Mortimer".)*

## Commands

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install -r requirements-lock.txt   # frozen deps (requirements.txt has loose minimums)
cp .env.example .env                       # then fill in keys
python scripts/check_env.py                # verify keys/connectivity
python scripts/init_db.py                  # run DB migrations

# Run (one command for the whole stack: bot + admin sidecar + web)
./scripts/mortimer.sh
# or individually:
./scripts/run_bot.sh          # Pipecat bot, :7860
./scripts/run_admin.sh        # admin sidecar (owns self-edit service), :7861
./scripts/run_web.sh          # Vite React console, :5173 (first run: npm install)
./scripts/run_wakeword.sh     # optional local wake-word sidecar, :7862
python3 -m jarvis.cli         # text-only REPL, no browser needed

# Tests
pytest tests/unit tests/integration -q          # no external calls
RUN_LIVE=1 pytest tests/integration -q          # hits real APIs, needs .env keys
pytest tests/unit/test_delegate.py -q           # single file
pytest tests/unit/test_delegate.py::test_name -q  # single test
RUN_LIVE=1 python -m tests.evals.routing_eval   # Supervisor routing accuracy eval, must score >=90%
ls tests/acceptance/                            # manual per-phase checklists

# Run log — review sub-agent delegation history
python -m jarvis.runlog                                     # last 20 runs
python -m jarvis.runlog --agent developer --status failed --since 2d
python -m jarvis.runlog --run <run_id>                       # full detail
python -m jarvis.runlog --json                               # machine-readable

# Web client
cd web && npm run build     # strict TS + production build (CI gate)
cd web && npm run lint      # oxlint
cd web && npm run dev       # dev server

# Other checks (also run in CI)
python scripts/check_allowlist.py origin/main...HEAD   # self-edit branches stay inside allowlist
python scripts/check_skills.py                          # skill.yaml manifests match servers
python scripts/latency_probe.py path/to/bot.log         # per-turn latency from TURN log lines
python scripts/list_voices.py
```

CI (`.github/workflows/validate.yml`, on PRs to `main`) runs, in order: allowlist enforcement → backend import smoke (`python -c "import jarvis, jarvis.config, jarvis.cli, jarvis.runlog"`) → `pytest tests/unit` (currently non-blocking) → `web/npm run build`.

## Architecture

```
Browser (React/Vite) --WebRTC--> Python bot (Pipecat pipeline) --MCP/stdio--> MCP skill servers
```

**Bot pipeline** (`jarvis/bot/pipeline.py`): `SmallWebRTCTransport` audio in → Silero VAD → `DeepgramFluxSTTService` → context aggregator → `OpenAILLMService` (Supervisor brain, any OpenAI-compatible Chat Completions endpoint with function calling) → `ElevenLabsTTSService` → audio out. Tool calls from the LLM go through the MCP tool layer or `delegate_task(agent, task)`.

**Delegation model**: the Supervisor never calls skill tools directly for delegated domains — it calls `delegate_task`, which hands the task to a `SubAgent` (`jarvis/agents/base.py`, `delegate.py`, `supervisor.py`), which in turn only has access to the MCP servers listed for it in `config/agents.yaml`. This routing config is the single source of truth for "who can do what" — read it before assuming a capability lives elsewhere. `jarvis/prompts.py` is the single source of truth for all system prompts (Supervisor, sub-agents, voice addendum); look there before searching for prompt text elsewhere.

**MCP skill servers** (`mcp_servers/*/`, each with `logic.py` + `server.py`): `mcp_time`, `mcp_notes`, `mcp_reminders`, `mcp_web`, `mcp_system`, `mcp_git`, `mcp_apps`, `mcp_selfedit`. Convention: `logic.py` is pure/testable (network or DB clients injected), `server.py` wires it up as a FastMCP server over stdio. The registry (`jarvis/skills/registry.py`, driven by `config/mcp_servers.yaml`) spawns these as subprocesses and exposes their tools to the bot.

**Self-development loop**: Mortimer can propose edits to its own UI/config, by voice or via the web console's Edit panel. `jarvis/admin/server.py` (the admin sidecar, `:7861`) is the single owner of the self-edit service (`jarvis/selfedit/service.py`); `mcp_selfedit` and the console's Edit panel are both thin HTTP clients of that sidecar — don't duplicate self-edit logic in either. Edits are confined to `config/self_edit_allowlist.json` (deny list always wins; never wake word, agents, CI, dependencies, or the self-edit machinery itself), land on `jarvis/self-edit/*` sandbox branches with a rollback tag, must pass validation (allowlist check, backend import, frontend build) before a PR, and merging always happens on GitHub by a human — Mortimer cannot merge. Planner models for this loop are named profiles in `config/upgrade_models.yaml` (not itself on the allowlist, so the agent can't repoint its own brain); loop bounds (max iterations/minutes) are in `config/upgrade_agent.yaml`.

**App-development**: `mcp_apps` lets the Developer sub-agent scaffold a new private GitHub repo per app (only after user confirmation), tracked in an app registry on the `mortimer-dev` branch. Only `mcp_apps/github.py` should touch the network; `logic.py` takes an injected client, matching the pattern used across the other MCP servers.

**Wake word** (optional, fully local): `jarvis/wakeword/` — `logic.py` (`WakeGate`: pure threshold/cooldown logic), `server.py` (localhost websocket sidecar, `:7862`), `train.py` (trains a custom ONNX model from `say`-generated samples, no cloud). Client hook is `web/src/wakeWord.ts`.

**Config vs. code boundary**: routing (`config/agents.yaml`), server wiring (`config/mcp_servers.yaml`), voices (`config/voices.yaml`), and self-edit bounds/allowlist are all YAML/JSON, not Python — check config first when a behavior seems misrouted or over/under-permissioned rather than assuming it's hardcoded.

**Run log** (`jarvis/runlog/`, MORTIMER_RUN_LOGGING_PLAN.md): every `delegate_task` call gets a `run_id`, generated in `jarvis/agents/delegate.py` and threaded through `SubAgent.run()` (`jarvis/agents/base.py`) down to each MCP call in `SkillRegistry.call()` (`jarvis/skills/registry.py`) via a `contextvars.ContextVar` holding the live `RunLogger` instance (not just the id — this is what lets an MCP-layer failure land in the same record as the sub-agent's own tool call). Each run writes one `agent_runs` row plus N `agent_events` rows (bounded previews, migration `0006_agent_runs` in `jarvis/db.py`) and one untruncated JSONL payload file under `logs/agents/<date>/<run_id>.jsonl`. Review with `python -m jarvis.runlog`, the admin sidecar's `GET /api/runs`/`GET /api/runs/{run_id}`, or the console's Runs panel — all three read the same `jarvis/runlog/store.py` helpers, so they can't disagree. `JARVIS_RUNLOG_ENABLED=false` is the kill switch; `JARVIS_RUNLOG_RETENTION_DAYS` controls pruning, applied once at bot startup.

## Testing conventions

- `tests/unit/` — one file per module, no external calls, mirrors `logic.py`/service structure.
- `tests/integration/` — MCP-over-stdio, registry wiring, bot wiring; some marked `live` (real external APIs, opt in with `RUN_LIVE=1`).
- `tests/evals/routing_eval.py` — live LLM eval of Supervisor routing accuracy; must stay ≥ 90%.
- `tests/acceptance/` — manual scripted checklists per implementation phase, not run by pytest.
- `pytest.ini` sets `asyncio_mode = auto`, so async test functions don't need `@pytest.mark.asyncio`.

## Known deviations and gotchas

- `DEVIATIONS.md` documents wiring-level adaptations from the original implementation plan — check it before assuming the plan doc (`Jarvis_Voice_AI_Agent_Implementation_Plan.md`) reflects current behavior.
- Some providers (e.g. Moonshot/kimi-k2.x) only accept `temperature=1`; Mortimer omits `temperature` by default rather than special-casing providers (D-003).
- First bot boot or test run can hang for minutes on a first-time NLTK `punkt_tab` download inside pipecat; see README §7 for the offline workaround.
- `data/jarvis.db` is gitignored and created by `scripts/init_db.py`; don't expect it to exist in a fresh checkout.
