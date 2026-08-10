# Mortimer — Voice AI Agent Controller

## 1. What this is

Mortimer is an Ironman-style voice assistant that runs entirely on your machine: you speak, it listens, thinks, acts, and answers out loud in a voice you choose. A single voice-facing **Supervisor** agent understands your intent and delegates specialist work to five text-only sub-agents — Scheduler, Librarian, Analyst, Systems, and Developer — whose skills live in separate MCP (Model Context Protocol) server processes. Everything persists to a local SQLite file, and the only cloud dependencies are the speech/LLM/search APIs (plus GitHub, if you enable app development).

```
┌────────────────────────────────────────────────────────────────────┐
│                         BROWSER (React client)                      │
│  mic ──► PipecatClient (SmallWebRTCTransport) ──► WebRTC audio      │
│  speaker ◄── PipecatClientAudio ◄── WebRTC audio                    │
│  UI: centered orb | agent satellites | transcript drawer (T)        │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ WebRTC (P2P, localhost)
┌──────────────────────────────▼─────────────────────────────────────┐
│                  PYTHON BOT  (Pipecat pipeline)                     │
│                                                                     │
│  SmallWebRTCTransport                                               │
│    ├─ input: audio ──► Silero VAD ──► DeepgramFluxSTTService        │
│    │                                          │                     │
│    │                          transcript ──► context aggregator     │
│    │                                          │                     │
│    │                    OpenAILLMService ◄────┘  (SUPERVISOR brain) │
│    │                          │   ▲                                 │
│    │             tool calls ──┘   └──── tool results                │
│    │                          │                                     │
│    │                    ElevenLabsTTSService ──► audio out           │
│    └─ output: audio + app messages (agent activity)                 │
│                                                                     │
│  Tool layer (inside LLM function calling):                          │
│    • MCP tools ──► SkillRegistry ──► MCP skill servers (below)      │
│    • delegate_task(agent, task) ──► SubAgent.run() ──► MCP tools    │
│    • ReminderWatcher (async task, proactive speech)                 │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ MCP protocol over stdio (JSON-RPC)
┌──────────────────────────────▼─────────────────────────────────────┐
│              MCP SKILL SERVERS (separate processes)                 │
│  mcp-time        mcp-notes       mcp-reminders     mcp-web          │
│  (time/dates)    (SQLite notes)  (SQLite reminders) (Tavily+weather)│
│  + mcp-system (psutil machine status)                               │
│  + mcp-apps   (app development: one private GitHub repo per app)    │
│  + mcp-selfedit (voice front-end to the self-development loop)      │
└─────────────────────────────────────────────────────────────────────┘
```

*(Seven skill servers spawned by the registry: `mcp-time`, `mcp-notes`, `mcp-reminders`, `mcp-web`, `mcp-system`, `mcp-apps`, `mcp-selfedit` — plus `mcp-git`, which backs the admin sidecar and the Developer agent's repo tools. `mcp-selfedit` and the console's ✎ Edit panel are both thin clients of the admin sidecar, the single owner of the self-edit service.)*

## 2. Prerequisites

- macOS or Linux (Windows via WSL2), 8 GB RAM, Chrome or Edge, a working microphone
- Python 3.11 or 3.12, Node.js 18+
- Four cloud accounts (free tiers are enough for development) and one keyless API:

| Service | Get key at | Env var | Free tier (dev-sufficient) | Required? |
|---------|-----------|---------|----------------------------|-----------|
| Deepgram | https://console.deepgram.com | `DEEPGRAM_API_KEY` | $200 signup credit | **Yes** |
| ElevenLabs | https://elevenlabs.io → Developers → API Keys | `ELEVENLABS_API_KEY` | 10k credits/month | **Yes** |
| OpenAI (or compatible) | https://platform.openai.com/api-keys | `OPENAI_API_KEY` | pay-as-you-go (low cost for dev) | **Yes** |
| Tavily | https://app.tavily.com | `TAVILY_API_KEY` | 1,000 credits/month | **Yes** |
| Open-Meteo | no key | — | free, rate-limited | built-in |
| openWakeWord (wake word) | no key — `pip install openwakeword` | `JARVIS_WAKEWORD_MODEL` (custom model file) | free, open source, fully local | Optional (stretch) |
| GitHub (app development) | https://github.com/settings/tokens | `GITHUB_TOKEN`, `GITHUB_OWNER` | free | Optional (mcp-apps) |
| Moonshot (Kimi) | https://platform.moonshot.ai | `MOONSHOT_API_KEY` | prepaid, low cost | Optional (default upgrade planner) |
| Anthropic (Claude) | https://console.anthropic.com | `ANTHROPIC_API_KEY` | pay-as-you-go | Optional (upgrade planner) |
| GitHub (self-development) | https://github.com/settings/tokens | `JARVIS_GITHUB_TOKEN` | free | Optional (edit-mode PRs) |

Any OpenAI-compatible Chat Completions endpoint works as the LLM (set
`OPENAI_BASE_URL` / `OPENAI_MODEL`, e.g. Moonshot/Kimi
`https://api.moonshot.ai/v1`, DeepSeek, or a local Ollama). The provider must
support function/tool calling. Anthropic Claude also works through its
OpenAI-compatibility layer (`https://api.anthropic.com/v1/`, model
`claude-haiku-4-5` recommended for low latency) — ready-made blocks for all
of these are commented in `.env.example`.

## 3. Quickstart

```bash
# 1. Python environment + locked dependencies
uv venv && source .venv/bin/activate
uv pip install -r requirements-lock.txt
# (fallback: python3 -m venv .venv && source .venv/bin/activate
#            && pip install -r requirements-lock.txt)

# 2. Configure keys
cp .env.example .env       # then edit .env and fill in your keys

# 3. Sanity-check keys and connectivity
python scripts/check_env.py

# 4. Initialize the database
python scripts/init_db.py

# 5. Start the bot (terminal 1)
./scripts/run_bot.sh

# 6. Start the web console (terminal 2)
./scripts/run_web.sh       # first run installs web dependencies via npm

# 7. Open http://localhost:5173, click Connect, allow the mic, say "Hello Mortimer"
```

A text-only REPL is also available for quick checks without a browser:

```bash
python3 -m jarvis.cli
```

## 4. Using Mortimer

- **Talk naturally.** "What time is it?", "Remind me to call the dentist
  tomorrow at 9 AM", "Remember that Dr. Patel's office is on Main Street",
  "What's the weather in London?", "Search the web for the latest SpaceX
  news", "How is my computer holding up?" Multi-part requests work too:
  "Check the weather in Paris and remind me to pack an umbrella tomorrow."
- **Interrupt anytime.** Start talking while Mortimer speaks and it stops
  within about a second and listens.
- **Push-to-talk:** hold **SPACE** to unmute while held; the mic button
  toggles a persistent mute.
- **Build apps (optional):** "Build me an expense tracker app." The
  Developer previews a new private GitHub repo (proposed name and file
  list) and creates it **only after you confirm**. Each app lives in its
  own repo, scaffolded from a template, and is recorded in Mortimer's app
  registry (`apps/index.json` on the `mortimer-dev` branch). Ask "what
  apps have you built?" to list them. Requires `GITHUB_TOKEN` (a PAT that
  can create repos and read/write contents); without it the app tools
  report a clear unavailable error and everything else keeps working.
- **Edit Mortimer itself (optional):** the self-development loop develops
  changes to Mortimer's own interface — by voice *or* from the console's
  **✎ Edit** panel. Say "Change your interface to add a clock panel — use
  Claude Opus for it" and the Developer previews the run (goal + planner
  model), starts it only after you confirm, and reports progress whenever
  you ask ("how is the edit coming along?"). Proposed edits land as
  reviewable diffs; ask Mortimer to **validate**, then — only after you
  explicitly say so — it **submits a pull request**. Merging always happens
  on GitHub, by you; Mortimer can never merge. The same flow is clickable
  in the ✎ Edit panel (planner dropdown, diffs, Validate / Submit PR /
  Revert buttons).
  - **Planner models** live in `config/upgrade_models.yaml` as named
    profiles (default: `kimi-k3`; `kimi-k2`, `claude-opus`, and
    `gpt-4.1-mini` ship alongside — add your own). Choose one per session
    (spoken or dropdown), set `JARVIS_UPGRADE_PROFILE` to change the
    default for every run, or edit the registry's `default`. A profile is
    usable once its provider key (`MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY`,
    …) is in `.env`; the picker flags profiles whose key is missing.
  - **Safety:** edits are confined to the allowlist
    (`config/self_edit_allowlist.json` — UI sources, non-secret config,
    prompts, skills, docs; never wake word, agents, CI, dependencies, or
    the self-edit machinery itself), land on `jarvis/self-edit/*` sandbox
    branches with a rollback tag, and must pass validation (allowlist,
    backend imports, frontend build) before any PR. PR creation requires
    `JARVIS_GITHUB_TOKEN` scoped to this repo (contents + pull requests
    only, no administration). Keep `main` a protected branch so even the
    token cannot bypass review.
- **Wake word (optional stretch):** start the local openWakeWord sidecar
  (`./scripts/run_wakeword.sh`), enable the **"Wake word"** toggle, and just
  say **"Mortimer"** — a chime plays and the mic unmutes. Detection is fully
  local: no keys, no cloud, audio never leaves the machine. (Picovoice
  discontinued its free tier in 2026, so openWakeWord replaced it.)
  One-time setup:
  1. `pip install openwakeword websockets` — already in `requirements.txt`
     (the frozen lock predates the sidecar; regenerate it after this lands).
  2. Train a custom **"Mortimer"** model locally (no notebook, no cloud —
     macOS `say` + `afconvert` synthesize the training clips):
     ```bash
     # generate samples with every installed English voice (~10-20 min)
     ./scripts/wakeword_gen_samples_mac.sh
     # one-time training dependency (inference does not need torch)
     uv pip install torch --index-url https://download.pytorch.org/whl/cpu
     # train and export models/mortimer.onnx
     python -m jarvis.wakeword.train
     ```
     The trainer prints held-out scores and a suggested
     `JARVIS_WAKEWORD_THRESHOLD`. Set `JARVIS_WAKEWORD_MODEL` in `.env` if
     you used a non-default `--out` path.
  3. `./scripts/run_wakeword.sh` — sidecar listens on `127.0.0.1:7862`.
- **Switch voices** by saying "Switch your voice to George", or pick from the
  **voice picker** in the console (catalog from `config/voices.yaml`; add your
  own ElevenLabs voice IDs there, including clones).
- **Agent activity:** the command deck shows the four specialists as
  satellites around the orb — a satellite lights up with an animated beam
  to the core while it works, then flashes green as it finishes; the server
  log prints `[AGENT]` lines and per-turn `TURN` latency lines.
- **Transcript on demand:** press **T** (or the **Log** button) to slide the
  full transcript drawer in from the right; the orb's live caption shows the
  latest exchange at a glance.
- **Proactive reminders:** if a reminder comes due while you're connected,
  Mortimer speaks it unprompted (checked every 30 s).
- **CLI commands:** `/tools` (list loaded tools), `/voice` (list voices),
  `/voice <id>` (switch), `/reset` (clear conversation), `/quit`.

## 5. Project layout

```
jarvis/
├── README.md                      # this file
├── DEVIATIONS.md                  # wiring-level adaptations from the plan
├── requirements.txt               # loose minimums
├── requirements-lock.txt          # frozen dependency set
├── .env.example                   # copy to .env and fill keys
├── .env                           # gitignored, user-created
├── .gitignore
├── pytest.ini
├── data/
│   └── jarvis.db                  # created by migrations, gitignored
├── config/
│   ├── mcp_servers.yaml           # MCP server registry (paths, env)
│   ├── voices.yaml                # voice catalog
│   ├── agents.yaml                # sub-agent roster + routing metadata
│   ├── upgrade_agent.yaml         # upgrade agent loop bounds (+ legacy model slot)
│   ├── upgrade_models.yaml        # planner model registry (NOT self-editable)
│   └── self_edit_allowlist.json   # what the self-edit loop may touch
├── jarvis/
│   ├── __init__.py
│   ├── config.py                  # pydantic-settings Settings
│   ├── logging_config.py          # stdlib logging setup
│   ├── db.py                      # sqlite helpers + migrations
│   ├── prompts.py                 # ALL system prompts (single source of truth)
│   ├── memory.py                  # persistent memory + tendency learning
│   ├── skills/
│   │   ├── __init__.py
│   │   └── registry.py            # SkillRegistry: MCP client manager
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                # SubAgent class
│   │   ├── supervisor.py          # Supervisor logic (used by CLI and bot)
│   │   ├── delegate.py            # delegate_task tool implementation
│   │   └── upgrade_agent.py       # LLM brain of the self-development loop
│   ├── selfedit/
│   │   ├── allowlist.py           # path allow/deny matcher (shared with CI)
│   │   └── service.py             # sandboxed session/edits/validate/submit
│   ├── admin/
│   │   └── server.py              # admin sidecar (:7861) — owns the self-edit
│   │                              #   service; panel + mcp-selfedit are clients
│   ├── cli.py                     # text REPL — python -m jarvis.cli
│   ├── wakeword/                  # openWakeWord sidecar (wake word)
│   │   ├── logic.py               # WakeGate: threshold + cooldown (pure)
│   │   ├── server.py              # localhost websocket sidecar (:7862)
│   │   └── train.py               # local wake-word model trainer
│   └── bot/
│       ├── __init__.py
│       ├── bot.py                 # Pipecat entry point (runner-compatible)
│       ├── pipeline.py            # build_pipeline(transport, runtime)
│       ├── transcript_log.py      # TranscriptLogger processor
│       ├── reminders_watcher.py   # proactive reminder injector
│       └── voice_switch.py        # voice catalog + set_voice tool
├── mcp_servers/
│   ├── mcp_time/                  # logic.py (pure) + server.py (FastMCP)
│   ├── mcp_notes/
│   ├── mcp_reminders/
│   ├── mcp_web/
│   ├── mcp_system/
│   ├── mcp_git/                   # repo ops (admin sidecar + Developer agent)
│   ├── mcp_apps/                  # app development: logic.py (pure, injected
│   │                              #   client) + github.py (only network code)
│   │                              #   + templates/web_app/
│   └── mcp_selfedit/              # voice front-end to the self-development
│                                  #   loop: logic.py (thin HTTP client of the
│                                  #   admin sidecar) + server.py (FastMCP)
├── scripts/
│   ├── check_env.py               # validates keys + connectivity
│   ├── check_allowlist.py         # CI: self-edit branches stay inside the allowlist
│   ├── check_skills.py            # CI: skill.yaml manifests match their servers
│   ├── init_db.py                 # runs migrations
│   ├── mortimer.sh                # one-command stack starter (bot+admin+web)
│   ├── run_bot.sh
│   ├── run_web.sh
│   ├── run_admin.sh               # admin sidecar (:7861)
│   ├── run_wakeword.sh            # optional wake-word sidecar
│   ├── wakeword_gen_samples_mac.sh# generate wake-word training clips (macOS say)
│   └── latency_probe.py           # per-turn latency stats from a bot log
├── tests/
│   ├── conftest.py
│   ├── unit/                      # one file per module
│   ├── integration/               # MCP-over-stdio, registry, bot wiring
│   ├── evals/
│   │   ├── routing_eval.py        # Supervisor routing accuracy (≥ 90%)
│   │   └── cases.yaml
│   └── acceptance/                # per-phase scripted checklists
└── web/                           # Vite React-TS console
    ├── package.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── App.css                    # base HUD theme
        ├── command-deck.css           # command-deck stage/satellite/drawer styles
        ├── editmode.css               # edit mode panel styles
        ├── components/
        │   ├── ConnectButton.tsx
        │   ├── Orb.tsx                # canvas orb (state-driven dynamics)
        │   ├── OrbField.tsx           # command deck: centered orb + agent satellites
        │   ├── Transcript.tsx
        │   ├── TranscriptDrawer.tsx   # slide-in transcript history (T)
        │   ├── VoicePicker.tsx
        │   ├── GitPanel.tsx           # admin sidecar console
        │   ├── EditModePanel.tsx      # self-development edit mode (✎ Edit)
        │   └── MicControls.tsx
        ├── wakeWord.ts                # wake-word sidecar client + chime
        └── jarvisClient.ts            # PipecatClient singleton
```

*(The internal package name `jarvis/` and the `JARVIS_*` environment variable
names are stable identifiers — renaming them would break existing installs
with zero user-visible benefit. Everything user-facing says Mortimer.)*

## 6. Testing

```bash
# Unit + integration (no external calls)
pytest tests/unit tests/integration -q

# Live integration (calls the real APIs; requires keys in .env)
RUN_LIVE=1 pytest tests/integration -q

# Supervisor routing eval (live LLM; must score ≥ 90%)
RUN_LIVE=1 python -m tests.evals.routing_eval

# Web client build gate (strict TypeScript + production build)
cd web && npm run build

# Latency report from a bot log (TURN lines)
python scripts/latency_probe.py path/to/bot.log     # or pipe a log via stdin

# Manual acceptance checklists per phase
ls tests/acceptance/
```

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No audio in the browser | ElevenLabs key invalid, out of credits, or free tier blocked (`detected_unusual_activity`) | Check the bot log for TTS errors; verify the key at elevenlabs.io; upgrade or regenerate it; text transcript keeps working meanwhile |
| Mic denied / no transcription | Browser blocked microphone permission | Click the lock icon in the address bar → allow microphone → reload and reconnect |
| 401 from the LLM | Wrong or regenerated `OPENAI_API_KEY` / wrong `OPENAI_BASE_URL` for the provider | Re-check key + base URL pair; run `python scripts/check_env.py` |
| 401 from Deepgram / ElevenLabs | Bad or expired speech keys | Regenerate keys, update `.env`, restart the bot |
| Slow responses | Large LLM model, slow provider, or cold MCP servers | Use a faster `OPENAI_MODEL`; check `TURN` lines / `latency_probe.py`; keep the bot running between turns |
| MCP server won't start | Missing deps after a partial install, or a stale venv | Re-run `pip install -r requirements-lock.txt`; start one manually: `python mcp_servers/mcp_time/server.py` |
| App tools report unavailable | `GITHUB_TOKEN` missing or lacks repo permissions | Create a PAT at github.com/settings/tokens with repo creation + contents read/write, set `GITHUB_TOKEN` and `GITHUB_OWNER` in `.env`, restart the bot |
| Edit mode says the sidecar is offline | Admin sidecar not running | `./scripts/mortimer.sh` starts bot + admin + web together; check `logs/admin.log`; browse to `http://localhost:7861/api/health` |
| Voice edit asks for a key | The chosen planner profile's provider key is missing | Set `MOONSHOT_API_KEY` / `ANTHROPIC_API_KEY` in `.env` and restart the sidecar; the ✎ Edit dropdown flags profiles with missing keys |
| Edit run "crashed" or never finishes | Planner endpoint unreachable, key invalid for that provider, or loop bounds hit | Check `logs/admin.log` for the run traceback; verify the key works against the profile's `base_url`; runs cap at the iteration/time bounds in `config/upgrade_agent.yaml` |
| Submit says validation hasn't passed | Edits changed after the last green validation, or a check is red | Run Validate again and read the check output; allowlist/frontend-build failures tell you exactly what broke |
| Port in use (7860 or 5173) | An old bot/web process is still running | `pkill -f jarvis.bot.bot` / `pkill -f vite`, or change the port (`JARVIS_BOT_PORT`, `npm run dev -- --port`) |
| Voices not switching | Voice id not in `config/voices.yaml`, or TTS update failed | List valid ids: `python scripts/list_voices.py`; check the bot log for TTS errors |
| Reminders not firing | Client not connected (watcher only delivers while connected), or `due_at` in the future | Reconnect and wait ≤ 30 s; inspect rows: `sqlite3 data/jarvis.db 'select * from reminders'` |
| Wake-word toggle errors | Sidecar not running, `openwakeword` not installed, or model file missing | `pip install openwakeword websockets`; train the "Mortimer" model (see §4 wake-word setup) and set `JARVIS_WAKEWORD_MODEL`; run `./scripts/run_wakeword.sh` |
| Wake word hears nothing / fires constantly | Threshold wrong for your mic/model | Adjust `JARVIS_WAKEWORD_THRESHOLD` (raise to reduce false wakes, lower to increase sensitivity) and restart the sidecar |
| Wake-word training finds too few clips | Sample generator aborted early or a voice failed | Re-run `./scripts/wakeword_gen_samples_mac.sh`; the trainer needs ≥ 20 WAVs per class — check `ls data/wakeword/positive \| wc -l` |
| `invalid temperature` from the LLM | Provider (e.g. kimi-k2.x) only accepts temperature=1 | Leave temperature unset — Mortimer omits it by default (DEVIATIONS.md D-003); Moonshot planner profiles omit it too |
| Web build fails with missing module files | Flaky filesystem truncated `node_modules` | Reinstall on a healthy filesystem: `cd web && rm -rf node_modules && npm install --no-bin-links` (D-006) |
| First bot boot or test run hangs for minutes | pipecat downloads NLTK `punkt_tab` on first import; the download stalls on restricted networks | One-time seed: `python -c "import nltk; nltk.download('punkt_tab')"`. If your network blocks raw.githubusercontent.com, download `https://cdn.jsdelivr.net/gh/nltk/nltk_data@gh-pages/packages/tokenizers/punkt_tab.zip` and unzip into `~/nltk_data/tokenizers/` |

## 8. Configuration reference

**Environment variables** (`.env`; see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | LLM provider key (required) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible Chat Completions endpoint |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Model for Supervisor and all sub-agents |
| `DEEPGRAM_API_KEY` | — | Speech-to-text key (required) |
| `ELEVENLABS_API_KEY` | — | Text-to-speech key (required) |
| `TAVILY_API_KEY` | — | Web search key (required for Analyst research) |
| `GITHUB_TOKEN` | — | GitHub PAT for app development (optional; enables mcp-apps) |
| `GITHUB_OWNER` | — | GitHub user/org owning app repos (optional; defaults to the token's user) |
| `MOONSHOT_API_KEY` | — | Kimi upgrade planner profiles (`kimi-k3` default, `kimi-k2`) |
| `ANTHROPIC_API_KEY` | — | Claude upgrade planner profile (`claude-opus`) |
| `JARVIS_UPGRADE_PROFILE` | registry `default` | Override the default upgrade planner profile |
| `JARVIS_UPGRADE_MODELS` | `config/upgrade_models.yaml` | Point at an alternate planner registry file |
| `JARVIS_GITHUB_TOKEN` | — | PAT for self-edit PRs (contents + pull requests on this repo only) |
| `JARVIS_GITHUB_REPO` | `Larryfix71566/jarvis-voice-ai` | Repo the self-edit service targets |
| `JARVIS_ADMIN_URL` | `http://127.0.0.1:7861` | Where mcp-selfedit reaches the admin sidecar |
| `JARVIS_DB_PATH` | `data/jarvis.db` | SQLite database file |
| `JARVIS_LOG_LEVEL` | `INFO` | Python logging level |
| `JARVIS_BOT_PORT` | `7860` | Bot HTTP/WebRTC port |
| `JARVIS_WEBRTC_ENDPOINT` | `http://localhost:7860/api/offer` | WebRTC offer endpoint (client-side) |
| `JARVIS_TIMEZONE` | `America/New_York` | User timezone for reminders/dates |
| `JARVIS_USER_NAME` | `Boss` | How Mortimer addresses you |
| `JARVIS_NAME` | `Mortimer` | Assistant's name |
| `JARVIS_WAKEWORD_PORT` | `7862` | Wake-word sidecar websocket port (localhost only) |
| `JARVIS_WAKEWORD_MODEL` | `models/mortimer.onnx` | Custom wake-word model file (sidecar exits if missing) |
| `JARVIS_WAKEWORD_THRESHOLD` | `0.5` | Wake detection score threshold (0–1) |
| `JARVIS_WAKEWORD_COOLDOWN` | `2.0` | Minimum seconds between wake events |

**Config files:**

| File | Purpose |
|---|---|
| `config/mcp_servers.yaml` | The MCP skill servers: command, args, env |
| `config/agents.yaml` | Sub-agent roster: name, display name, routing description, owned MCP servers |
| `config/voices.yaml` | Voice catalog (`id`, `label`, `elevenlabs_voice_id`) + default voice |
| `config/upgrade_models.yaml` | Upgrade planner registry: named OpenAI-compatible profiles + default. NOT on the self-edit allowlist — the agent cannot re-point its own brain |
| `config/upgrade_agent.yaml` | Upgrade agent loop bounds (max iterations/minutes) + legacy single-slot model fallback |
| `config/self_edit_allowlist.json` | Paths the self-development loop may read/write; the deny list always wins |
| `jarvis/prompts.py` | All system prompts (Supervisor, sub-agents, voice addendum) — single source of truth |
