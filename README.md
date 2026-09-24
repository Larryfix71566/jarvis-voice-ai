# Mortimer — Voice AI Agent Controller

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the maintained system
map, model-route ownership and runtime verification commands, and
[docs/REPO_MAP.md](docs/REPO_MAP.md) for where things live. Implementation
plans and acceptance evidence are under `docs/plans/` and `docs/acceptance/`;
superseded documents are in `docs/archive/`.

## 1. What this is

Mortimer is an Ironman-style voice assistant that runs entirely on your machine: you speak, it listens, thinks, acts, and answers out loud in a voice you choose. A single voice-facing **Supervisor** agent understands your intent and delegates specialist work to six text-only sub-agents — Scheduler, Librarian, Analyst, Systems, Developer, and App Builder (`config/agents.yaml`) — whose skills live in separate MCP (Model Context Protocol) server processes. State persists to local SQLite, and the only cloud dependencies are the speech/LLM/search APIs (plus GitHub, if you enable app development or self-edit PRs).

The client is the native macOS app **MortimerHost** (`macos/MortimerHost`, built on the shared `macos/JarvisKit` package). Its default layout is the **Command Console** (layout 2); `Debug ▸ Use previous layout` switches to the earlier layouts without a rebuild. The React/Vite web console in `web/` is **frozen** (2026-09-04, `web/README.md`): it still runs by hand as a fallback but gets no new features and is not started by the launcher.

```
┌────────────────────────────────────────────────────────────────────┐
│             MortimerHost (SwiftUI, macOS) — uses JarvisKit          │
│  NativeAudioTransport: AVAudioEngine (voice processing) mic/speaker │
│  UI: Command Console | drawer (8 tabs) | display window             │
│  (web/ console: FROZEN fallback, WebRTC to /api/offer)              │
└──────────────────────────────┬─────────────────────────────────────┘
       WebSocket /ws-client (PCM + RTVI app messages, same Mac);
       WebRTC /api/offer when JARVIS_FORCE_WEBRTC=true or bot is remote
┌──────────────────────────────▼─────────────────────────────────────┐
│                  PYTHON BOT  (Pipecat pipeline, :7860)              │
│                                                                     │
│  transport in ──► Silero VAD ──► DeepgramFluxSTTService             │
│                                          │                          │
│                          transcript ──► context aggregator          │
│                                          │                          │
│       Supervisor LLM service (OpenAI-compatible or Anthropic)       │
│                          │   ▲                                      │
│             tool calls ──┘   └──── tool results                     │
│                          │                                          │
│                    ElevenLabsTTSService ──► transport out           │
│                                                                     │
│  Tool layer (inside LLM function calling):                          │
│    • direct tools (set_voice, ui_control, view_screen, …)           │
│    • delegate_task(agent, task) ──► SubAgent.run() ──► MCP tools    │
│    • watchers (reminders, plans, research, progress) speak unasked  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ MCP protocol over stdio (JSON-RPC)
┌──────────────────────────────▼─────────────────────────────────────┐
│      MCP SKILL SERVERS (separate processes, config/mcp_servers.yaml)│
│  mcp-time  mcp-notes  mcp-memory  mcp-kb  mcp-reminders  mcp-web    │
│  mcp-system  mcp-git  mcp-apps  mcp-repo  mcp-runlog  mcp-selfedit  │
│  mcp-screen                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

*(Thirteen skill servers are registered in `config/mcp_servers.yaml`; `config/agents.yaml` decides which sub-agent may use which. `mcp-selfedit` and the native app's Edit tab are both thin clients of the admin sidecar (`:7861`), the single owner of the self-edit service. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full runtime map.)*

## 2. Prerequisites

- macOS 26 for the native client (`platforms: [.macOS(.v26)]`, Swift 6.2
  toolchain per `swift-tools-version: 6.2` in `macos/*/Package.swift`), 8 GB
  RAM, a working microphone. The backend alone runs on macOS or Linux.
- Python 3.11 or 3.12. Node.js 18+ only if you run the frozen web console.
- Five cloud accounts (free tiers or low pay-as-you-go spend are enough for development) and one keyless API:

| Service | Get key at | Env var | Free tier (dev-sufficient) | Required? |
|---------|-----------|---------|----------------------------|-----------|
| Deepgram | https://console.deepgram.com | `DEEPGRAM_API_KEY` | $200 signup credit | **Yes** |
| ElevenLabs | https://elevenlabs.io → Developers → API Keys | `ELEVENLABS_API_KEY` | 10k credits/month | **Yes** |
| OpenAI (or compatible) | https://platform.openai.com/api-keys | `OPENAI_API_KEY` | pay-as-you-go (low cost for dev) | **Yes** |
| Tavily | https://app.tavily.com | `TAVILY_API_KEY` | 1,000 credits/month | **Yes** |
| Open-Meteo | no key | — | free, rate-limited | built-in |
| openWakeWord (wake word) | no key — `pip install openwakeword` | `JARVIS_WAKEWORD_MODEL` (custom model file) | free, open source, fully local | Optional (stretch) |
| GitHub (app development) | https://github.com/settings/tokens | `GITHUB_TOKEN`, `GITHUB_OWNER` | free | Optional (mcp-apps) |
| Moonshot (Kimi) | https://platform.moonshot.ai | `MOONSHOT_API_KEY` | prepaid, low cost | Optional (registry profiles) |
| Anthropic (Claude) | https://console.anthropic.com | `ANTHROPIC_API_KEY` | pay-as-you-go | **Yes, for delegation** — every sub-agent runs an Anthropic profile (`claude-sonnet-5` or `claude-opus`) with `on_profile_fallback: refuse`, the registry default planner is `claude-fable-5`, and the memory/background routes default to `claude-sonnet-5`. Voice alone boots without it; delegated work is refused |
| OpenRouter | https://openrouter.ai/keys | `OPENROUTER_API_KEY` | pay-as-you-go | Optional (registry profiles) |
| GitHub (self-development) | https://github.com/settings/tokens | `JARVIS_GITHUB_TOKEN` | free | Optional (edit-mode PRs) |

Any OpenAI-compatible Chat Completions endpoint works for the voice
Supervisor/orchestrator (set `OPENAI_BASE_URL` / `OPENAI_MODEL`, e.g.
Moonshot/Kimi, DeepSeek, or a local Ollama). Anthropic Claude also works
through its OpenAI-compatibility layer (`https://api.anthropic.com/v1/`, model
`claude-haiku-4-5` is the low-latency Supervisor route). Other agents,
planners, research, vision and background memory jobs resolve independently
through the model registry (`config/model_profiles.yaml` + `config/model_endpoints.yaml`) and their endpoint environment variables;
they do not inherit `OPENAI_MODEL`. Ready-made examples are commented in
`.env.example`.

## 3. Quickstart

```bash
# 1. Python environment + locked dependencies
uv venv && source .venv/bin/activate
uv pip install -r requirements-lock.txt
# (fallback: python3 -m venv .venv && source .venv/bin/activate
#            && pip install -r requirements-lock.txt)

# 2. Configure keys
cp .env.example .env       # then edit .env and fill in your keys

# 2b. (Recommended) Move credentials into the encrypted vault —
#     data/secrets.vault, master key in the macOS Keychain. After this,
#     .env holds configuration only; keys never sit in plaintext.
python -m jarvis.vault init
python -m jarvis.vault migrate

# 3. Sanity-check keys and connectivity
python scripts/check_env.py

# 4. Initialize the database
python scripts/init_db.py

# 5. Start the backend: knowledge-base vault (:8484), bot (:7860),
#    memory-extraction worker, admin sidecar (:7861) and costs API (:8487).
#    Re-running it restarts everything; `stop` and `logs` are subcommands.
./scripts/mortimer.sh
#    (or just the bot: ./scripts/run_bot.sh)

# 6. Build, bundle and launch the native app (macOS)
macos/MortimerHost/scripts/bundle.sh          # debug; `bundle.sh release` for release
#    → macos/MortimerHost/.build/MortimerHost.app, then opened. Allow the mic
#      when macOS asks, click Connect, and say "Hello Mortimer".
```

`swift run` or Xcode (`open macos/MortimerHost/Package.swift`) also runs the
app, but as a bare executable it has no menu bar or native full screen, and
the `Debug ▸ Wave level windows` sliders only work in the bundled app (they
write the `com.mortimer.host` defaults domain) — use `bundle.sh` for daily
use. A merged Swift change does nothing until you rebuild (see
`macos/README.md`). Run `bash scripts/setup_kb.sh` once before the first
`mortimer.sh`: the launcher starts the bot only after the knowledge-base
service is listening on :8484 (`scripts/wait_for.sh`, 30 s), so without it the
bot refuses to start (see below).

The frozen web console still runs by hand as a fallback:
`./scripts/run_web.sh`, then open http://localhost:5173 (first run installs
npm dependencies).

A text-only REPL is also available for quick checks without any client:

```bash
python3 -m jarvis.cli
```

### Knowledge-base service

The knowledge-base service and its tests are included in
[`services/mortimer-vault`](services/mortimer-vault/README.md). From the
repository root, install its separate environment with
`bash scripts/setup_kb.sh`; the normal launcher then uses this repository
copy. For manual startup, run `bash scripts/run_kb.sh`.

Existing documents remain at `MORTIMER_HOME` (default `~/Mortimer`); no data
migration is required. Stop the old service before switching to the new
launcher. A fresh installation can initialize an empty knowledge base with
`services/mortimer-vault/.venv/bin/mortimer-vault init`.
The encrypted credential vault (`jarvis/vault.py`) is separate; its secrets
remain on your Mac. See the package README for isolated development data
and test commands.

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
  App Builder previews a new private GitHub repo (proposed name and file
  list) and creates it **only after you confirm**. Each app lives in its
  own repo, scaffolded from a template, and is recorded in Mortimer's app
  registry (`apps/index.json` on the `mortimer-dev` branch). Ask "what
  apps have you built?" to list them. Requires `GITHUB_TOKEN` (a PAT that
  can create repos and read/write contents); without it the app tools
  report a clear unavailable error and everything else keeps working.
- **Edit Mortimer itself (optional):** the self-development loop develops
  changes to Mortimer's own code — including the native app's Swift
  sources — by voice *or* from the native app's **Edit** drawer tab. Say
  "Change your interface to add a clock panel — use Claude Opus for it" and
  the Developer previews the run (goal + planner model), starts it only
  after you confirm, and reports progress whenever you ask ("how is the
  edit coming along?"). Candidate code runs in a disposable offline macOS
  VM (`sandbox/`); an independent verification VM re-runs the checks before
  anything is published, and the result is a **draft** pull request.
  Merging always happens on GitHub, by you; Mortimer can never merge. A
  merged Swift change still needs `bundle.sh` to reach the running app.
  - **Planner models** live in `config/model_profiles.yaml` as named
    profiles, each naming an endpoint in `config/model_endpoints.yaml` (registry `default: claude-fable-5`; Anthropic, Moonshot
    `kimi-k3`/`kimi-k2`, OpenRouter `or-*` and a `codex-subscription`
    profile ship alongside — add your own). Choose one per session (spoken
    or the Edit tab's picker), set `JARVIS_UPGRADE_PROFILE` to change the
    default for every run, or edit the registry's `default`. A profile is
    usable once its provider key (`ANTHROPIC_API_KEY`, `MOONSHOT_API_KEY`,
    `OPENROUTER_API_KEY`, …) is available.
  - **Safety:** edits are confined to `config/self_edit_allowlist.json`
    (three tiers: `allow` routine paths such as prompts, MCP servers,
    config, tests, docs and the Swift `Sources`/`Tests` of `JarvisKit` and
    `MortimerHost`; `core` = the rest of `jarvis/**` and `scripts/**`,
    which needs a plan; `deny` always wins — `sandbox/`, CI, dependency
    manifests, the self-edit service, admin sidecar, model registry, vault
    and Swift packaging). The frozen `web/` tree is refused even though it
    is on the allowlist. Work lands on `mortimer/selfedit/…` branches
    (`mortimer/app-build/…` for app builds, `sandbox/publish.py`) and must
    pass every check in the `mortimer` profile (`sandbox/profiles.py`:
    backend imports, baseline and candidate `pytest tests/unit`, scripted
    sub-agent evals, latency budget, knowledge-base tests, web build, and
    baseline and candidate `swift test` for both Swift packages) before a
    PR. PR creation requires `JARVIS_GITHUB_TOKEN` scoped to this repo
    (contents + pull requests only, no administration). Keep `main` a
    protected branch so even the token cannot bypass review.
- **Wake word (optional stretch):** start the local openWakeWord sidecar
  (`./scripts/run_wakeword.sh`), turn on **Wake word** in the app's mic
  controls, and just say **"Mortimer"** — a chime plays and the mic
  unmutes. The native app feeds the sidecar from its own capture
  (`macos/JarvisKit/Sources/JarvisKit/WakeWordListener.swift`). Detection is
  fully local: no keys, no cloud, audio never leaves the machine. (Picovoice
  discontinued its free tier in 2026, so openWakeWord replaced it.)
  One-time setup:
  1. `openwakeword` and `websockets` are in `requirements.txt` and
     `requirements-lock.txt`.
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
  **voice picker** in the app's mic controls (catalog from `config/voices.yaml`;
  add your own ElevenLabs voice IDs there, including clones).
- **Agent activity:** the drawer's **Agents** tab shows every delegated run
  with the model actually running it and a live tool-call ticker; the
  legacy orb layout (`Debug ▸ Use previous layout`) still shows the agents
  as satellites. The server log prints `[AGENT]` lines and per-turn `TURN`
  latency lines.
- **Transcript on demand:** press **T** to toggle the drawer's **Log** tab
  (Escape closes the drawer). The drawer's eight tabs are Repo, Edit,
  Memory, Runs, Agents, Output, Log and Costs; each can also be opened by
  voice ("show me the runs tab").
- **Proactive reminders:** if a reminder comes due while you're connected,
  Mortimer speaks it unprompted (checked every 30 s).
- **CLI commands:** `/tools` (list loaded tools), `/voice` (list voices),
  `/voice <id>` (switch), `/reset` (clear conversation), `/quit`.

## 5. Project layout

Top level only; [docs/REPO_MAP.md](docs/REPO_MAP.md) is the maintained
"where things live" map and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) the
runtime and ownership reference.

```
jarvis-voice-ai/
├── README.md / CLAUDE.md / ROADMAP.md / DEVIATIONS.md
├── requirements.txt               # loose minimums
├── requirements-lock.txt          # frozen dependency set
├── .env.example                   # copy to .env (config only once the vault holds secrets)
├── Procfile                       # reference inventory of long-lived processes
├── config/                        # routing and model config: agents.yaml, mcp_servers.yaml,
│                                  #   model_profiles.yaml + model_endpoints.yaml (model registry), model_access.yaml,
│                                  #   voices.yaml, self_edit_allowlist.json, skills.yaml, workflows/
├── jarvis/                        # Python backend (package name kept for stability)
│   ├── bot/                       #   Pipecat bot: bot.py (entry), pipeline.py, ws_transport.py
│   │                              #   (native /ws-client), speaker_gate.py, ui_control.py, watchers
│   ├── agents/                    #   SubAgent, delegate_task, Supervisor, upgrade/app-build agents
│   ├── admin/                     #   admin sidecar (:7861) — owns self-edit, planning, jobs
│   ├── selfedit/                  #   self-edit service facade over sandbox/ + allowlist matcher
│   ├── skills/                    #   SkillRegistry: MCP client manager
│   ├── council/  runlog/  graphs/ #   LLM council, run log, derived graphs
│   ├── wakeword/                  #   openWakeWord sidecar (:7862) + trainer
│   └── prompts.py, config.py, memory*.py, vault.py, …
├── mcp_servers/                   # 13 MCP skill servers, each logic.py + server.py + skill.yaml
├── macos/                         # native client (Swift, SwiftPM)
│   ├── JarvisKit/                 #   shared library: voice session, transports, sidecar API, wake word
│   ├── MortimerHost/              #   the app (Command Console, drawer, display); scripts/bundle.sh
│   └── MortimerShell/, GlassSpike/, VPIOBench/   # outgoing shell, spike and bench targets
├── sandbox/                       # disposable macOS VMs, verification, draft-PR publication
├── services/mortimer-vault/       # knowledge-base service (:8484), own venv
├── skills/                        # Agent Skills (SKILL.md), enabled via config/skills.yaml
├── scripts/                       # mortimer.sh (launcher), run_*.sh, check_env.py, init_db.py, …
├── tests/                         # unit/, integration/, evals/, acceptance/
├── docs/                          # ARCHITECTURE.md, REPO_MAP.md, plans/, acceptance/, reviews/, archive/
└── web/                           # React/Vite console — FROZEN 2026-09-04 (web/README.md)
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

# Native client (macOS): library and app test suites
swift test --package-path macos/JarvisKit
swift test --package-path macos/MortimerHost

# Frozen web client build gate (strict TypeScript + production build)
cd web && npm run build

# Latency report from a bot log (TURN lines)
python scripts/latency_probe.py path/to/bot.log     # or pipe a log via stdin

# Manual acceptance checklists per phase
ls tests/acceptance/
```

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No audio | ElevenLabs key invalid, out of credits, or free tier blocked (`detected_unusual_activity`) | Check the bot log for TTS errors; verify the key at elevenlabs.io; upgrade or regenerate it; text transcript keeps working meanwhile |
| Mic denied / no transcription | Microphone permission not granted to the app (or, for the frozen web console, the browser) | Native: allow MortimerHost under System Settings → Privacy & Security → Microphone, then reconnect (the prompt is attributed to the bundled app, so launch it via `bundle.sh`). Web: lock icon in the address bar → allow microphone → reload |
| 401 from the LLM | Wrong or regenerated `OPENAI_API_KEY` / wrong `OPENAI_BASE_URL` for the provider | Re-check key + base URL pair; run `python scripts/check_env.py` |
| 401 from Deepgram / ElevenLabs | Bad or expired speech keys | Regenerate keys, update `.env`, restart the bot |
| Slow responses | Large LLM model, slow provider, or cold MCP servers | Use a faster `OPENAI_MODEL`; check `TURN` lines / `latency_probe.py`; keep the bot running between turns |
| MCP server won't start | Missing deps after a partial install, or a stale venv | Re-run `pip install -r requirements-lock.txt`; start one manually: `python mcp_servers/mcp_time/server.py` |
| App tools report unavailable | `GITHUB_TOKEN` missing or lacks repo permissions | Create a PAT at github.com/settings/tokens with repo creation + contents read/write, set `GITHUB_TOKEN` and `GITHUB_OWNER` in `.env`, restart the bot |
| Edit mode says the sidecar is offline | Admin sidecar not running | `./scripts/mortimer.sh` starts vault, bot, extractor, admin and costs together; check `logs/admin.log`; browse to `http://localhost:7861/api/health` |
| Voice edit asks for a key | The chosen planner profile's provider key is missing | Set `MOONSHOT_API_KEY` / `ANTHROPIC_API_KEY` in `.env` and restart the sidecar |
| Edit run "crashed" or never finishes | Planner endpoint unreachable, key invalid for that provider, or loop bounds hit | Check `logs/admin.log` for the run traceback; verify the key works against the profile's `base_url`; runs cap at the iteration/time bounds in `config/upgrade_agent.yaml` |
| Submit says validation hasn't passed | Edits changed after the last green validation, or a check is red | Validate again and read the failing check's output; every check in the `mortimer` profile (`sandbox/profiles.py`) must pass in the verification VM |
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
| `OPENAI_MODEL` | `gpt-4.1-mini` | Voice Supervisor/orchestrator model only |
| `DEEPGRAM_API_KEY` | — | Speech-to-text key (required) |
| `ELEVENLABS_API_KEY` | — | Text-to-speech key (required) |
| `TAVILY_API_KEY` | — | Web search key (required for Analyst research) |
| `GITHUB_TOKEN` | — | GitHub PAT for app development (optional; enables mcp-apps) |
| `GITHUB_OWNER` | — | GitHub user/org owning app repos (optional; defaults to the token's user) |
| `MOONSHOT_API_KEY` | — | Kimi registry profiles (`kimi-k3`, `kimi-k2`); neither is the registry default |
| `ANTHROPIC_API_KEY` | — | Anthropic registry profiles: every sub-agent (`claude-sonnet-5` / `claude-opus`, refuse on fallback), the registry default planner `claude-fable-5`, and the memory/background routes |
| `JARVIS_UPGRADE_PROFILE` | registry `default` | Override the default upgrade planner profile |
| `JARVIS_PLANNING_PROFILE` | registry `default` | Research/planning profile |
| `JARVIS_VISION_PROFILE` | first eligible registry profile | Screen/shared-content vision profile |
| `JARVIS_MEMORY_PROFILE` | `claude-sonnet-5` | Memory extraction/consolidation/classification profile |
| `JARVIS_MEMORY_AUTOMATION_ENABLED` | `false` | Automated memory classification/maintenance |
| `JARVIS_MEMORY_AUTOMATION_SHADOW` | `true` | Run automated memory policy in shadow (measure without writes); independent of `_ENABLED` |
| `JARVIS_MEMORY_AUTOMATION_STAGE` | `shadow` | Ordered memory rollout gate: `shadow`, `explicit_preferences`, or `corroborated_inferences` |
| `JARVIS_BACKGROUND_PROFILE` | `claude-sonnet-5` | KB digest and procedure-maintenance profile |
| `JARVIS_UPGRADE_MODELS` | `config/model_profiles.yaml` (joined with `model_endpoints.yaml`) | Point at an alternate registry file (a legacy single file is still accepted) |
| `JARVIS_MODEL_ROUTING_ENABLED` | unset (off) | Model Use Enhancements rollout gate; only the value `1` enables the shared model-access policy at routed call sites |
| `JARVIS_GITHUB_TOKEN` | — | PAT for self-edit PRs (contents + pull requests on this repo only) |
| `JARVIS_GITHUB_REPO` | `Larryfix71566/jarvis-voice-ai` | Repo the self-edit service targets |
| `JARVIS_ADMIN_URL` | `http://127.0.0.1:7861` | Where mcp-selfedit reaches the admin sidecar |
| `JARVIS_DB_PATH` | `data/jarvis.db` | SQLite database file |
| `JARVIS_LOG_LEVEL` | `INFO` | Python logging level |
| `JARVIS_BOT_PORT` | `7860` | Bot port (`/ws-client` WebSocket and `/api/offer` WebRTC) |
| `JARVIS_WEBRTC_ENDPOINT` | `http://localhost:7860/api/offer` | Unused: declared in `jarvis/config.py` but read by no code |
| `JARVIS_FORCE_WEBRTC` | off | **Read by the macOS app, not the bot** (its process environment or `defaults write com.mortimer.host JARVIS_FORCE_WEBRTC -bool true`): a same-Mac bot then uses WebRTC instead of the native `/ws-client` WebSocket. The rollback lever |
| `JARVIS_SPEAKER_GATE_ENABLED` | `false` | Tier-2 speaker-verification gate (`jarvis/bot/speaker_gate.py`); opt-in pending its effectiveness protocol |
| `JARVIS_TIMEZONE` | `America/New_York` | User timezone for reminders/dates |
| `JARVIS_USER_NAME` | `Boss` | How Mortimer addresses you |
| `JARVIS_NAME` | `Mortimer` | Assistant's name |
| `JARVIS_WAKEWORD_PORT` | `7862` | Wake-word sidecar websocket port (localhost only) |
| `JARVIS_WAKEWORD_MODEL` | `models/mortimer.onnx` | Custom wake-word model file (sidecar exits if missing) |
| `JARVIS_WAKEWORD_THRESHOLD` | `0.5` | Wake detection score threshold (0–1) |
| `JARVIS_WAKEWORD_COOLDOWN` | `2.0` | Minimum seconds between wake events |
| `JARVIS_INTERRUPTION_NOTICE_ENABLED` | `true` | Tell the Supervisor on the next turn when the user genuinely barged in on a reply (plan Phase 3) |
| `JARVIS_MAX_PARALLEL_DELEGATIONS` | `3` | Cap on concurrently executing `delegate_task` calls when the Supervisor issues several in one turn (plan Phase 4) |

**Config files:**

| File | Purpose |
|---|---|
| `config/mcp_servers.yaml` | The MCP skill servers: command, args, env |
| `config/agents.yaml` | Sub-agent roster: name, display name, routing description, owned MCP servers |
| `config/voices.yaml` | Voice catalog (`id`, `label`, `elevenlabs_voice_id`) + default voice |
| `config/model_endpoints.yaml` | Model endpoints: provider, base_url, key variable name per endpoint, plus the pinned planner (`supervisor:`). Human-only (self-edit deny): the agent cannot re-point its own brain or send a key elsewhere |
| `config/model_profiles.yaml` | Model profile pool: named profiles + default, each naming an endpoint id. Routine — self-edit may add a model on an existing endpoint; a profile carrying a host or key is a load error |
| `config/upgrade_agent.yaml` | Upgrade agent loop bounds (max iterations/minutes) + legacy single-slot model fallback |
| `config/self_edit_allowlist.json` | Paths the self-development loop may read/write; the deny list always wins |
| `jarvis/prompts.py` | All system prompts (Supervisor, sub-agents, voice addendum) — single source of truth |
