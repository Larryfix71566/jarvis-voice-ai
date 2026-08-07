# Mortimer — Voice AI Agent Controller

## 1. What this is

Mortimer is an Ironman-style voice assistant that runs entirely on your machine: you speak, it listens, thinks, acts, and answers out loud in a voice you choose. A single voice-facing **Supervisor** agent understands your intent and delegates specialist work to four text-only sub-agents — Scheduler, Librarian, Analyst, and Systems — whose skills live in separate MCP (Model Context Protocol) server processes. Everything persists to a local SQLite file, and the only cloud dependencies are the four speech/LLM/search APIs.

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
│              MCP SKILL SERVERS (4 separate processes)               │
│  mcp-time        mcp-notes       mcp-reminders     mcp-web          │
│  (time/dates)    (SQLite notes)  (SQLite reminders) (Tavily+weather)│
│                              + mcp-system (psutil machine status)   │
└─────────────────────────────────────────────────────────────────────┘
```

*(Five skill servers total: `mcp-time`, `mcp-notes`, `mcp-reminders`, `mcp-web`, `mcp-system`.)*

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
│   └── agents.yaml                # sub-agent roster + routing metadata
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
│   │   └── delegate.py            # delegate_task tool implementation
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
│   └── mcp_system/
├── scripts/
│   ├── check_env.py               # validates keys + connectivity
│   ├── init_db.py                 # runs migrations
│   ├── run_bot.sh
│   ├── run_web.sh
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
        ├── components/
        │   ├── ConnectButton.tsx
        │   ├── Orb.tsx                # canvas orb (state-driven dynamics)
        │   ├── OrbField.tsx           # command deck: centered orb + agent satellites
        │   ├── Transcript.tsx
        │   ├── TranscriptDrawer.tsx   # slide-in transcript history (T)
        │   ├── VoicePicker.tsx
        │   ├── GitPanel.tsx           # admin sidecar console
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
| Port in use (7860 or 5173) | An old bot/web process is still running | `pkill -f jarvis.bot.bot` / `pkill -f vite`, or change the port (`JARVIS_BOT_PORT`, `npm run dev -- --port`) |
| Voices not switching | Voice id not in `config/voices.yaml`, or TTS update failed | List valid ids: `python scripts/list_voices.py`; check the bot log for TTS errors |
| Reminders not firing | Client not connected (watcher only delivers while connected), or `due_at` in the future | Reconnect and wait ≤ 30 s; inspect rows: `sqlite3 data/jarvis.db 'select * from reminders'` |
| Wake-word toggle errors | Sidecar not running, `openwakeword` not installed, or model file missing | `pip install openwakeword websockets`; train the "Mortimer" model (see §4 wake-word setup) and set `JARVIS_WAKEWORD_MODEL`; run `./scripts/run_wakeword.sh` |
| Wake word hears nothing / fires constantly | Threshold wrong for your mic/model | Adjust `JARVIS_WAKEWORD_THRESHOLD` (raise to reduce false wakes, lower to increase sensitivity) and restart the sidecar |
| Wake-word training finds too few clips | Sample generator aborted early or a voice failed | Re-run `./scripts/wakeword_gen_samples_mac.sh`; the trainer needs ≥ 20 WAVs per class — check `ls data/wakeword/positive \| wc -l` |
| `invalid temperature` from the LLM | Provider (e.g. kimi-k2.x) only accepts temperature=1 | Leave temperature unset — Mortimer omits it by default (DEVIATIONS.md D-003) |
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
| `config/mcp_servers.yaml` | The five MCP skill servers: command, args, env |
| `config/agents.yaml` | Sub-agent roster: name, display name, routing description, owned MCP servers |
| `config/voices.yaml` | Voice catalog (`id`, `label`, `elevenlabs_voice_id`) + default voice |
| `jarvis/prompts.py` | All system prompts (Supervisor, sub-agents, voice addendum) — single source of truth |
