# JARVIS — Voice-First Multi-Agent AI Assistant
## Complete Implementation Plan (Locked Design)

**Document version:** 1.0
**Date:** 2026-08-04
**Intended implementer:** Any competent AI coding model or human engineer. No design decisions are left to the implementer.

---

## 0. Rules for the Implementing Agent (READ FIRST)

This document is a **locked specification**. It exists so that the finished system matches the intended design exactly, regardless of who or what implements it.

1. **Do not redesign.** Every architectural choice, library, module name, file path, tool name, agent name, prompt, port, and schema in this document is a decision that has already been made. Treat them as requirements, not suggestions.
2. **Do not skip phases or gates.** Each phase ends with an explicit **Exit Gate**. All gate items must pass before starting the next phase. If a gate fails, fix the current phase — never "come back to it later."
3. **Do not substitute libraries or services.** If a specified service appears unavailable, stop and follow the contingency written in this document (§10 Risk Table). Do not improvise an alternative.
4. **Version drift rule (the only allowed adaptation).** Library APIs evolve. If a specified import path, class name, or parameter signature does not match the installed version of a library, you may adapt the *wiring only* (import paths, parameter names, constructor shapes) to match the installed version. You may **never** adapt the *architecture* (which components exist, how they connect, what they are named, what they do). Every such adaptation must be recorded in `DEVIATIONS.md` using the format in §11.
5. **Pin what works.** At the end of Phase 0, freeze all resolved dependency versions into `requirements-lock.txt` / `package-lock.json`. All later phases use those frozen versions.
6. **Test commands are contracts.** Every phase lists exact commands and expected outputs. Run them verbatim. "It seems to work" is not a gate pass.
7. **When this document and a library's documentation conflict on architecture, this document wins. When they conflict on syntax, the installed library wins (and a deviation is recorded).**

---

## 1. Product Overview

**JARVIS** is a voice-first personal AI assistant that runs locally and is used from a web browser. The user talks to it naturally; it speaks back in a selectable voice; and it delegates specialized work to a team of sub-agents, each backed by MCP (Model Context Protocol) skill servers.

### 1.1 Core capabilities (v1)

| # | Capability | Delivered by |
|---|-----------|--------------|
| 1 | Natural voice conversation (speech in, speech out) | Deepgram STT + LLM + ElevenLabs TTS, orchestrated by Pipecat |
| 2 | Voice of the user's choosing, switchable live | ElevenLabs voice library / voice cloning + runtime voice switching |
| 3 | Interruptions (barge-in) — user can talk over the agent | Pipecat VAD-based interruption |
| 4 | Multi-agent delegation to specialists | Supervisor agent + 4 sub-agents |
| 5 | Time, dates, reminders | `mcp-time` + `mcp-reminders` skill servers (Scheduler agent) |
| 6 | Persistent notes & long-term memory | `mcp-notes` skill server, SQLite (Librarian agent) |
| 7 | Web research & weather | `mcp-web` skill server (Analyst agent) |
| 8 | Local machine status | `mcp-system` skill server (Systems agent) |
| 9 | Web client with transcript, mic control, voice picker, agent activity | React + Pipecat Client SDK |
| 10 | Proactive spoken reminders | Reminder watcher injecting into the live conversation |

### 1.2 Explicit non-goals (v1)

- No phone/telephony integration.
- No smart-home device control (the architecture supports adding it later as a new MCP server + sub-agent; do not build it now).
- No multi-user support, accounts, or authentication. Single local user.
- No mobile app. Desktop browser only (Chrome/Edge).
- No always-listening wake word in the core plan (optional stretch goal, §9.3).
- No vision/camera features.

### 1.3 The target experience (what "done" feels like)

The user opens `http://localhost:5173`, clicks **Connect**, and says:

> "Jarvis, what's on my plate tomorrow — and remind me to call the dentist at 9 AM."

Jarvis replies aloud, within ~1–2 seconds:

> "Tomorrow you have two reminders set. I'll add a 9 AM reminder to call the dentist. Done."

The user then says: *"Actually, make it 9:30."* — Jarvis updates it. Then: *"Remember that my dentist is Dr. Patel on Main Street."* — stored to long-term memory. Then: *"Use the other voice."* — Jarvis switches voices mid-conversation and confirms in the new voice.

The full scripted version of this demo is the **Master Acceptance Test** in §8.

---

## 2. Locked Architecture

### 2.1 System diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         BROWSER (React client)                      │
│  mic ──► PipecatClient (SmallWebRTCTransport) ──► WebRTC audio      │
│  speaker ◄── PipecatClientAudio ◄── WebRTC audio                    │
│  UI: Connect | mic toggle | transcript | voice picker | agent feed  │
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

### 2.2 The agent topology

One **Supervisor** (the only voice-facing agent) and four **SubAgents** (text-only workers):

| Agent | Role | Owns tools from | Speaks to user? |
|-------|------|-----------------|-----------------|
| **Supervisor** | Understands intent, answers small talk directly, delegates specialist work, speaks everything | all (rarely calls tools directly) | Yes |
| **Scheduler** | Time, dates, reminders, planning | `mcp-time`, `mcp-reminders` | No (returns text to Supervisor) |
| **Librarian** | Long-term memory, notes, "remember that…", recall | `mcp-notes` | No |
| **Analyst** | Research, current events, weather | `mcp-web` | No |
| **Systems** | Machine health, diagnostics | `mcp-system` | No |

**Delegation mechanism (locked):** The Supervisor has exactly one special non-MCP tool, `delegate_task(agent_name, task)`. When the user's request needs a specialist, the Supervisor:

1. First emits a short spoken acknowledgment (≤ 10 words, e.g. *"Let me check your schedule."*) — this is a hard rule in the Supervisor's system prompt, and it prevents dead air while tools run.
2. Calls `delegate_task` with a **self-contained** task string (the sub-agent does not see the conversation history; the Supervisor must include all needed facts in `task`).
3. The `SubAgent.run()` method executes its own LLM tool-calling loop (same LLM provider, own system prompt, only its allowed MCP tools) and returns a final plain-text result (≤ 60 words, enforced by prompt).
4. The Supervisor receives the result and speaks it naturally, in its own voice/personality. It may rephrase for speech but must not alter facts.

For multi-part requests ("check the weather AND remind me…"), the Supervisor calls `delegate_task` multiple times sequentially (the standard tool-calling loop handles this), then summarizes all results in one spoken reply.

### 2.3 Why this architecture (rationale — informational, not to be re-litigated)

- **Cascaded pipeline (STT → LLM → TTS), not speech-to-speech:** superior tool-calling reliability, full control of the voice (voice switching/cloning), easier debugging, lower cost. This is the whole point of a "controller" system.
- **Pipecat as the voice framework:** production-grade streaming pipeline with built-in VAD, interruption handling, first-class MCP client, and a local development runner with a prebuilt test UI. No external realtime infrastructure needed (peer-to-peer WebRTC on localhost).
- **MCP for every skill:** skills become discoverable, independently testable processes. Adding a future skill = add one MCP server + update one config — no changes to the pipeline.
- **Sub-agents as text workers behind one tool:** keeps the voice path single-threaded and simple; sub-agents are trivially unit-testable without audio.
- **SQLite, stdlib-only persistence:** zero external services to run; the whole system works offline except for the four cloud APIs (Deepgram, ElevenLabs, LLM, Tavily).

---

## 3. Locked Technology Decisions

| Layer | Decision | Exact choice | Notes |
|-------|----------|--------------|-------|
| Language (backend) | Python | 3.11 or 3.12 | Pipecat requires ≥ 3.11 |
| Package manager (backend) | `uv` | latest | Fallback to `python -m venv` + `pip` only if `uv` cannot be installed; record in DEVIATIONS.md |
| Voice framework | Pipecat | `pipecat-ai` PyPI package | Extras: `deepgram`, `elevenlabs`, `openai`, `silero`, `mcp`, `runner`, `webrtc` |
| Transport | SmallWebRTC (P2P) | `SmallWebRTCTransport` | No third-party WebRTC account needed; server-side via Pipecat dev runner |
| STT | Deepgram Flux | `DeepgramFluxSTTService`, model `flux-general-en` | Built-in intelligent turn detection. Contingency: `DeepgramSTTService` with model `nova-3` (see §10) |
| VAD | Silero | `SileroVADAnalyzer` via Pipecat | Used for interruptions and local VAD |
| LLM provider | Any OpenAI-compatible API | Default: OpenAI, model `gpt-4.1-mini` | `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` configure the voice Supervisor/orchestrator. Sub-agents and background jobs use the model registry; the original same-provider assumption is superseded by the model-routing plan. |
| TTS | ElevenLabs | `ElevenLabsTTSService`, model `eleven_flash_v2_5` | Flash = ~75 ms synthesis latency, required for real-time feel |
| MCP server SDK | Official MCP Python SDK | package `mcp[cli]`, `mcp.server.fastmcp.FastMCP` | stdio transport for all local servers |
| MCP client (bot side) | Pipecat `MCPClient` | `pipecat.services.mcp_service.MCPClient` | Extra `pipecat-ai[mcp]` |
| Persistence | SQLite | stdlib `sqlite3` | Single file `data/jarvis.db`; no ORM |
| Config | pydantic-settings + `.env` | `jarvis/config.py` | Validated at startup; fail fast with clear errors |
| Logging | stdlib `logging` | structured, level from env | No third-party logging libs |
| Language (web client) | TypeScript + React | Vite template `react-ts` | Node 18+ |
| Voice client SDK | Pipecat Client SDK | `@pipecat-ai/client-js`, `@pipecat-ai/client-react`, `@pipecat-ai/small-webrtc-transport` | No Daily/other transport |
| Web search | Tavily | `tavily-python` | Free tier; used only inside `mcp-web` |
| Weather | Open-Meteo | HTTPS, no API key | Geocoding + forecast endpoints |
| Machine status | psutil | PyPI | Used only inside `mcp-system` |
| Testing (backend) | pytest + pytest-asyncio | latest | Plus scripted manual acceptance checklists |
| Process orchestration | Single bot process | MCP servers spawned as stdio children | No docker-compose, no services manager in v1 |
| Ports | Bot 7860, web client 5173 | fixed | Pipecat runner default and Vite default |

**Dependency freeze:** after Phase 0 installation succeeds and its gate passes, generate `requirements-lock.txt` (`uv pip freeze > requirements-lock.txt` or `pip freeze`) and `web/package-lock.json`. Later phases must not upgrade anything.

---

## 4. Prerequisites & API Key Acquisition

The system needs exactly **four cloud accounts** (all have free tiers sufficient for development) and **one keyless API**.

| Service | Get key at | Env var | Free tier (dev-sufficient) | Required? |
|---------|-----------|---------|----------------------------|-----------|
| Deepgram | https://console.deepgram.com | `DEEPGRAM_API_KEY` | $200 signup credit | **Yes** |
| ElevenLabs | https://elevenlabs.io → Developers → API Keys | `ELEVENLABS_API_KEY` | 10k credits/month | **Yes** |
| OpenAI (or compatible) | https://platform.openai.com/api-keys | `OPENAI_API_KEY` | pay-as-you-go (low cost for dev) | **Yes** |
| Tavily | https://app.tavily.com | `TAVILY_API_KEY` | 1,000 credits/month | **Yes** |
| Open-Meteo | no key | — | free, rate-limited | built-in |

**LLM provider alternatives for the voice Supervisor (allowed, config-only):** any OpenAI-compatible Chat Completions endpoint may be used by setting `OPENAI_BASE_URL` and `OPENAI_MODEL` (e.g. Moonshot/Kimi `https://api.moonshot.ai/v1`, DeepSeek `https://api.deepseek.com/v1`, or a local Ollama `http://localhost:11434/v1`). The provider **must** support function/tool calling. If the chosen provider's tool calling proves unreliable at the Phase 2 gate, switch back to the OpenAI default — do not re-architect. Other workloads resolve through the registry profiles described by the current architecture reference.

**Voice selection:** ElevenLabs default library voices are sufficient for the core plan. Optionally, the user may create an Instant Voice Clone in the ElevenLabs web UI (Voice Lab) and paste the resulting voice ID into `config/voices.yaml` (Phase 5). Cloning requires only a few minutes of recorded audio and the owner's consent.

**Local machine requirements:** macOS or Linux (Windows via WSL2), 8 GB RAM, Chrome or Edge for the client, a working microphone.

---

## 5. Repository Layout (exact — do not reorganize)

```
jarvis/
├── README.md                      # written in Phase 8
├── DEVIATIONS.md                  # created in Phase 0, appended any time §0 rule 4 is invoked
├── requirements.txt               # Phase 0 (loose minimums)
├── requirements-lock.txt          # Phase 0 gate (frozen)
├── .env.example                   # Phase 0
├── .env                           # gitignored, user-created
├── .gitignore
├── pytest.ini
├── data/
│   └── jarvis.db                  # created by migrations, gitignored
├── config/
│   ├── mcp_servers.yaml           # MCP server registry (paths, env)
│   ├── voices.yaml                # voice catalog (Phase 5)
│   └── agents.yaml                # sub-agent roster + routing metadata (Phase 3)
├── jarvis/
│   ├── __init__.py
│   ├── config.py                  # pydantic-settings Settings
│   ├── logging_config.py          # stdlib logging setup
│   ├── db.py                      # sqlite helpers + migrations
│   ├── prompts.py                 # ALL system prompts (single source of truth)
│   ├── skills/
│   │   ├── __init__.py
│   │   └── registry.py            # SkillRegistry: MCP client manager
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                # SubAgent class
│   │   ├── supervisor.py          # Supervisor logic (used by CLI and bot)
│   │   └── delegate.py            # delegate_task tool implementation
│   ├── cli.py                     # text REPL (Phases 2–3) — python -m jarvis.cli
│   └── bot/
│       ├── __init__.py
│       ├── bot.py                 # Pipecat entry point (runner-compatible)
│       ├── pipeline.py            # build_pipeline(transport, runtime) 
│       ├── transcript_log.py      # TranscriptLogger processor
│       ├── reminders_watcher.py   # proactive reminder injector (Phase 7)
│       └── voice_switch.py        # app-message voice switching (Phase 5)
├── mcp_servers/
│   ├── mcp_time/
│   │   ├── logic.py               # pure functions (unit-tested)
│   │   └── server.py              # FastMCP wrappers
│   ├── mcp_notes/
│   │   ├── logic.py
│   │   └── server.py
│   ├── mcp_reminders/
│   │   ├── logic.py
│   │   └── server.py
│   ├── mcp_web/
│   │   ├── logic.py
│   │   └── server.py
│   └── mcp_system/
│       ├── logic.py
│       └── server.py
├── scripts/
│   ├── check_env.py               # validates keys + connectivity (Phase 0 gate)
│   ├── init_db.py                 # runs migrations
│   ├── run_bot.sh                 # Phase 4
│   ├── run_web.sh                 # Phase 6
│   └── latency_probe.py           # Phase 7 latency measurement
├── tests/
│   ├── conftest.py
│   ├── unit/                      # one file per module, mirroring package names
│   ├── integration/               # MCP-over-stdio tests, registry tests
│   ├── evals/
│   │   ├── routing_eval.py        # Phase 3 routing accuracy (automated)
│   │   └── cases.yaml             # eval dataset
│   └── acceptance/                # per-phase scripted checklists (markdown)
└── web/                           # Phase 6 (Vite react-ts)
    ├── package.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── components/
        │   ├── ConnectButton.tsx
        │   ├── Transcript.tsx
        │   ├── VoicePicker.tsx
        │   ├── AgentActivity.tsx
        │   └── MicControls.tsx
        └── jarvisClient.ts        # PipecatClient singleton
```

---

## 6. Configuration System (locked)

### 6.1 Environment variables (`.env.example` — exact contents)

```dotenv
# --- LLM (OpenAI-compatible) ---
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini

# --- Speech ---
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=

# --- Skills ---
TAVILY_API_KEY=

# --- Runtime ---
JARVIS_DB_PATH=data/jarvis.db
JARVIS_LOG_LEVEL=INFO
JARVIS_BOT_PORT=7860
JARVIS_WEBRTC_ENDPOINT=http://localhost:7860/api/offer
JARVIS_TIMEZONE=America/New_York
JARVIS_USER_NAME=Boss
JARVIS_NAME=Jarvis
```

### 6.2 `jarvis/config.py`

A single `Settings(BaseSettings)` pydantic-settings class exposing every variable above, plus derived helpers (`db_path: Path`). Validation rules:

- Missing `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, or `ELEVENLABS_API_KEY` → startup error listing exactly which are missing.
- `TAVILY_API_KEY` missing → warning only; `mcp-web` starts in degraded mode (`web_search` returns "search unavailable" instead of raising).
- `JARVIS_TIMEZONE` must be a valid IANA name (`zoneinfo.ZoneInfo(value)` at validation).

### 6.3 `config/mcp_servers.yaml` (exact schema)

```yaml
servers:
  - name: mcp-time
    command: python
    args: ["-m", "mcp_servers.mcp_time.server"]
    env: {}
  - name: mcp-notes
    command: python
    args: ["-m", "mcp_servers.mcp_notes.server"]
    env:
      JARVIS_DB_PATH: "${JARVIS_DB_PATH}"
  - name: mcp-reminders
    command: python
    args: ["-m", "mcp_servers.mcp_reminders.server"]
    env:
      JARVIS_DB_PATH: "${JARVIS_DB_PATH}"
      JARVIS_TIMEZONE: "${JARVIS_TIMEZONE}"
  - name: mcp-web
    command: python
    args: ["-m", "mcp_servers.mcp_web.server"]
    env:
      TAVILY_API_KEY: "${TAVILY_API_KEY}"
  - name: mcp-system
    command: python
    args: ["-m", "mcp_servers.mcp_system.server"]
    env: {}
```

`${VAR}` placeholders are expanded from the process environment by `SkillRegistry` at load time.

### 6.4 `config/agents.yaml` (Phase 3 — exact schema)

```yaml
sub_agents:
  - name: scheduler
    display_name: Scheduler
    mcp_servers: [mcp-time, mcp-reminders]
    description: "Time, dates, reminders, alarms, scheduling and planning questions."
  - name: librarian
    display_name: Librarian
    mcp_servers: [mcp-notes]
    description: "Long-term memory: store and recall facts, notes, preferences."
  - name: analyst
    display_name: Analyst
    mcp_servers: [mcp-web]
    description: "Web research, current events, weather, lookups."
  - name: systems
    display_name: Systems
    mcp_servers: [mcp-system]
    description: "Local machine status: CPU, memory, disk, battery, uptime."
```

### 6.5 `config/voices.yaml` (Phase 5 — exact schema)

```yaml
default: rachel
voices:
  - id: rachel
    elevenlabs_voice_id: "21m00Tcm4TlvDq8ikWAM"
    label: "Rachel (calm, American female)"
  # Additional voices appended at Phase 5 step 5.4 after listing the user's
  # ElevenLabs library; at least 2 more entries required by the gate.
```

---

## 7. Coding Standards & Testing Policy (locked)

**Python**
- `async` everywhere in the bot/agents path; MCP `logic.py` modules are **synchronous pure functions** (called from async wrappers).
- Full type hints on all public functions. No `Any` unless unavoidable.
- All errors returned to the LLM as **plain sentences** ("I couldn't reach the search service") — never raw exceptions or stack traces. Stack traces go to logs only.
- Every tool function validates its own arguments and returns a structured error string on bad input; never raise through the MCP boundary.
- Imports absolute (`from jarvis.skills.registry import ...`). No circular imports: `prompts.py` and `config.py` import nothing from the package.
- Formatting: `ruff format` defaults. Lint: `ruff check`. (Add `ruff` as a dev dependency in Phase 0.)

**TypeScript**
- Strict mode (`"strict": true`). No `any`.
- Functional components + hooks only.

**Testing policy**
- Every `logic.py` module: **≥ 90% line coverage** by unit tests (measure with `pytest --cov`; add `pytest-cov` in Phase 0).
- Every MCP server: one integration test that starts it over stdio and calls each tool via the official `mcp` client.
- Non-deterministic LLM behavior is tested two ways: (a) plumbing tested with a `FakeLLM` double (deterministic, in unit tests); (b) real-LLM behavior tested by **evals** (`tests/evals/`) with temperature 0 and assertions on *tool-call sequences*, not exact wording. Eval assertions must be robust: assert which tool was called with which normalized arguments, never the exact prose.
- Manual acceptance checklists live in `tests/acceptance/phase-N.md` and are executed by a human at each gate.
- A phase is complete only when: all automated tests pass, the acceptance checklist is fully checked off, and the gate's exact commands produce the expected output.

**Git policy:** initialize git in Phase 0. Commit at the end of every phase with message `phase-N: <name> complete` (only after the gate passes).

---

# PHASES

Each phase follows the same structure: **Goal → Scope → Deliverables → Steps → Tests → Exit Gate**. Do not start a phase until the previous gate has fully passed.

---

## PHASE 0 — Foundation & Environment

**Goal:** A runnable, validated project skeleton. Every later phase assumes this exists.

**Scope:** scaffolding only. No assistant logic.

### Deliverables
- Repo tree from §5 (empty `__init__.py` stubs where needed)
- `.env.example` (exact contents of §6.1), `.gitignore` (ignores `.env`, `data/*.db`, `__pycache__`, `node_modules`, `dist`)
- `requirements.txt`, `pytest.ini`, `jarvis/config.py`, `jarvis/logging_config.py`, `jarvis/db.py` (migrations), `scripts/check_env.py`, `scripts/init_db.py`
- `DEVIATIONS.md` initialized with the header from §11

### Steps

**0.1** Create the directory tree exactly as §5. Initialize git.

**0.2** Install `uv` (https://docs.astral.sh/uv/). Create the environment and install dependencies:
```bash
uv venv --python 3.12
uv pip install \
  "pipecat-ai[deepgram,elevenlabs,openai,silero,mcp,runner,webrtc]" \
  "mcp[cli]" openai pydantic-settings psutil tavily-python httpx \
  pytest pytest-asyncio pytest-cov ruff python-dateutil
```
> If the `webrtc` extra is rejected by the installed pipecat-ai version, install `aiortc` explicitly instead and record the deviation. If `uv` cannot be installed at all, use `python3.12 -m venv .venv && pip install ...` and record the deviation.

**0.3** Write `jarvis/config.py` per §6.2 and `jarvis/logging_config.py` (stdlib logging; format `%(asctime)s %(levelname)s %(name)s: %(message)s`; level from `JARVIS_LOG_LEVEL`).

**0.4** Write `jarvis/db.py` with this exact migration (migration id `0001_init`, applied in order, tracked in a `migrations` table):

```sql
CREATE TABLE IF NOT EXISTS migrations (
  id TEXT PRIMARY KEY, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message TEXT NOT NULL,
  due_at TEXT NOT NULL,              -- ISO 8601, timezone-aware
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | cancelled
  delivered INTEGER NOT NULL DEFAULT 0,     -- 1 once spoken to the user
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,                -- user | assistant | tool
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at);
CREATE INDEX IF NOT EXISTS idx_notes_tags ON notes(tags);
```

`db.py` exposes exactly: `get_conn() -> sqlite3.Connection` (row_factory = `sqlite3.Row`, WAL mode), `run_migrations()`, `now_iso() -> str`.

**0.5** Write `scripts/check_env.py`. It must check, printing one PASS/FAIL line per item:
1. Python ≥ 3.11
2. All required env vars present and non-empty (§6.2 rules)
3. LLM reachable: `GET {OPENAI_BASE_URL}/models` with the API key → HTTP 200
4. Deepgram reachable: `GET https://api.deepgram.com/v1/projects` → HTTP 200
5. ElevenLabs reachable: `GET https://api.elevenlabs.io/v1/voices` → HTTP 200; prints how many voices the account has
6. Tavily reachable: a 1-query search → success (or WARN-degraded per §6.2)
7. Open-Meteo reachable: `GET https://api.open-meteo.com/v1/forecast?latitude=40.71&longitude=-74.00&current=temperature_2m` → HTTP 200
8. `JARVIS_TIMEZONE` valid IANA name
Exit code 0 only if all required checks pass.

**0.6** User creates `.env` from `.env.example` with real keys. Run `python scripts/check_env.py` and `python scripts/init_db.py`.

### Tests (Phase 0)
- `tests/unit/test_config.py`: missing required key raises; bad timezone raises; `${VAR}` expansion helper works.
- `tests/unit/test_db.py`: migrations apply cleanly to a fresh DB; running them twice is idempotent; tables exist.

### Exit Gate 0 (all must pass)
```bash
python scripts/check_env.py          # exits 0, all PASS lines
python scripts/init_db.py            # prints "migrations applied: 0001_init"
ls data/jarvis.db                    # exists
pytest tests/unit -q                 # all green
uv pip freeze > requirements-lock.txt   # committed
git add -A && git commit -m "phase-0: foundation complete"
```

---

## PHASE 1 — MCP Skill Servers

**Goal:** All five skill servers working as standalone MCP processes, fully tested **without any LLM**. This isolates tool correctness from model behavior.

**Architecture rule (locked):** every server has two files. `logic.py` contains synchronous pure functions that take/return plain dicts — this is where all behavior lives and where unit tests aim. `server.py` contains only thin FastMCP wrappers that call `logic.py`. Nothing in `server.py` may contain business logic.

**Template (locked) for every `server.py`:**
```python
from mcp.server.fastmcp import FastMCP
from . import logic

mcp = FastMCP("mcp-<name>")

@mcp.tool()
def <tool>(...):
    """<one-line description used by the LLM — write it carefully>"""
    return logic.<fn>(...)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```
Return values are always `dict[str, Any]` with either result fields or `{"error": "<plain sentence>"}` — never raise.

### 1.1 `mcp-time` (no DB, no network)

Tools (exact names/signatures):

| Tool | Signature | Returns |
|------|-----------|---------|
| `get_current_time` | `()` | `{iso, human, timezone, unix}` — human like `"Tuesday, August 4, 2026, 3:25 PM EDT"` |
| `resolve_date_expression` | `(expression: str)` | Parses relative English ("tomorrow", "next Friday", "in 3 days", "August 20 at 9am") → `{iso, human}`; relative times resolved against now in `JARVIS_TIMEZONE`; returns error dict on unparseable input |
| `date_add` | `(base_iso: str, amount: int, unit: str)` | unit ∈ `minutes|hours|days|weeks` → `{iso, human}` |
| `date_diff` | `(a_iso: str, b_iso: str)` | `{days, hours}` signed |

Implementation: `python-dateutil` parser + `zoneinfo`. All returned ISO strings timezone-aware.

### 1.2 `mcp-notes` (SQLite)

| Tool | Signature | Returns |
|------|-----------|---------|
| `create_note` | `(title: str, body: str, tags: str = "")` | `{id, message: "Note saved: <title>"}` |
| `list_notes` | `(tag: str \| None = None, limit: int = 20)` | `{notes: [{id,title,body,tags,created_at}, ...]}` newest first |
| `search_notes` | `(query: str)` | case-insensitive `LIKE` over title/body/tags → same shape as list_notes |
| `get_note` | `(note_id: int)` | `{note}` or error |
| `update_note` | `(note_id: int, title=None, body=None, tags=None)` | `{message}`; bumps `updated_at` |
| `delete_note` | `(note_id: int)` | `{message}` |

### 1.3 `mcp-reminders` (SQLite)

| Tool | Signature | Returns |
|------|-----------|---------|
| `set_reminder` | `(message: str, due_expression: str)` | Resolves `due_expression` via the same parsing logic as mcp-time (`resolve_date_expression` logic is **copied into this server's logic.py** — MCP servers must not import each other) → `{id, message: "Reminder set for <human time>: <message>"}`; error if time is in the past |
| `list_reminders` | `(status: str = "pending")` | `{reminders: [...]}` ordered by `due_at` |
| `complete_reminder` | `(reminder_id: int)` | `{message}` |
| `cancel_reminder` | `(reminder_id: int)` | `{message}` |
| `get_due_reminders` | `()` | Atomically: selects `pending` rows with `due_at <= now` and `delivered = 0`, sets `delivered = 1` in the same transaction, returns `{reminders: [...]}` |

### 1.4 `mcp-web` (network)

| Tool | Signature | Returns |
|------|-----------|---------|
| `web_search` | `(query: str, max_results: int = 5)` | Tavily search → `{results: [{title, url, snippet}], answer}` (`answer` = Tavily's synthesized short answer); degraded mode (no key) → `{"error": "Web search is unavailable (no API key configured)."}` |
| `get_weather` | `(city: str, days: int = 1)` | Open-Meteo geocoding (`https://geocoding-api.open-meteo.com/v1/search?name=<city>&count=1`) → forecast (`current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=auto&forecast_days=<days 1..3>`) → `{city, current: {...}, daily: [...], human}` where `human` is one English sentence; WMO weather codes mapped via a fixed dict in logic.py |

Use `httpx` with 10 s timeouts; network failure → error dict, never raise.

### 1.5 `mcp-system` (psutil)

| Tool | Signature | Returns |
|------|-----------|---------|
| `get_system_status` | `()` | `{cpu_percent, memory_percent, disk_percent, battery_percent \| null, uptime_hours, human}` — `human` one sentence flagging anything ≥ 85 % |
| `get_top_processes` | `(limit: int = 5)` | `{processes: [{name, cpu_percent, memory_percent}]}` by CPU |

### Tests (Phase 1)
- **Unit:** `tests/unit/test_mcp_<name>_logic.py` for each server — every tool, happy path + at least two error paths each (bad date expression, missing note id, past reminder time, unknown city, etc.). Reminder tests freeze "now" via monkeypatching a `logic._now()` helper. Coverage ≥ 90 % on every `logic.py`.
- **Integration:** `tests/integration/test_mcp_servers.py` — for each server: spawn it over stdio with the official `mcp` client (`mcp.client.stdio.stdio_client` + `ClientSession`), list tools (assert exact tool-name sets), call one happy-path tool, assert result shape.
- **Manual:** run `mcp dev mcp_servers/mcp_notes/server.py`, open the Inspector, call `create_note` then `search_notes` in the browser UI; tick the box in `tests/acceptance/phase-1.md`.

### Exit Gate 1
```bash
pytest tests/unit -q --cov=mcp_servers --cov-report=term-missing     # green, ≥90% per logic.py
pytest tests/integration -q                                          # green
# manual Inspector check ticked in tests/acceptance/phase-1.md
git add -A && git commit -m "phase-1: mcp skill servers complete"
```

---

## PHASE 2 — The Brain (Text Conversation with Tools)

**Goal:** Talk to Jarvis **in text** from the terminal, with the LLM calling MCP tools directly. No voice yet. This phase validates the LLM + tool plumbing before multi-agent routing is layered on in Phase 3.

> **Scope note (locked):** In this phase the Supervisor LLM calls MCP tools *directly*. Phase 3 will narrow its toolset to `delegate_task` only. This is intentional: Phase 2 exists to prove the tool layer with the simplest possible loop.

### Deliverables
- `jarvis/skills/registry.py` — `SkillRegistry`
- `jarvis/prompts.py` — all prompts (Appendix A text, verbatim)
- `jarvis/agents/supervisor.py` — `Orchestrator` class
- `jarvis/cli.py` — text REPL
- Tests per the Phase 2 Tests section below

### Steps

**2.1 — `SkillRegistry`.** Responsibilities, exact API:
```python
class SkillRegistry:
    def __init__(self, config_path: Path): ...          # loads mcp_servers.yaml
    async def start(self) -> None: ...                  # spawns all servers (stdio), initializes sessions, discovers tools
    async def stop(self) -> None: ...                   # terminates children, idempotent
    def openai_tools(self, server_names: list[str] | None = None) -> list[dict]: ...   # OpenAI-format tool schemas, filtered
    async def call(self, tool_name: str, arguments: dict, server_names: list[str] | None = None) -> str: ...  # returns plain-text result (JSON-serialized dict), or the tool's error sentence
    def tools_for(self, server_names: list[str]) -> list[str]: ...  # tool names owned by given servers
```
- Uses the official `mcp` client (`StdioServerParameters`, `stdio_client`, `ClientSession`), one persistent session per server.
- MCP tool schemas are JSON Schema; convert verbatim into OpenAI `{"type": "function", "function": {...}}` wrappers.
- Tool-name collision across servers → raise at `start()` with both names listed.
- Tool call failure (server crash, timeout) → return `"<tool> failed: <one-line reason>"`, never raise into the Orchestrator. Timeout per call: 30 s.

**2.2 — `prompts.py`.** Constants: `SUPERVISOR_PROMPT`, `VOICE_ADDENDUM`, `SUBAGENT_PROMPTS` (dict). Full text in Appendix A — copy verbatim, with `{jarvis_name}`, `{user_name}`, `{agent_catalog}`, `{timezone}` as `str.format` placeholders.

**2.3 — `Orchestrator`** (`jarvis/agents/supervisor.py`):
```python
class Orchestrator:
    def __init__(self, settings: Settings, registry: SkillRegistry,
                 session_id: str, allowed_servers: list[str] | None = None): ...
    async def chat(self, user_text: str) -> str: ...
```
- OpenAI client: `AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)`; model `settings.openai_model`; **temperature 0.3** (constant; evals pass `temperature=0.0` override).
- System prompt = `SUPERVISOR_PROMPT.format(...)` with the agent catalog section omitted in Phase 2 (pass `agent_catalog="(none yet)"`).
- Tool loop: send messages + `registry.openai_tools(allowed_servers)`; while the reply contains tool calls: execute each via `registry.call`, append `tool` messages, re-send. Hard cap **6 iterations**; on cap, final answer = "I'm sorry, I got stuck working on that. Please try rephrasing."
- History: in-memory list, persisted to `conversations` table (user/assistant rows only), trimmed to last 40 messages. `/reset` starts a new `session_id` (uuid4).
- Every `chat()` logs total latency at INFO: `turn_complete user_len=%d latency_ms=%d tool_calls=%d`.

**2.4 — CLI** (`python -m jarvis.cli`): banner, then loop reading input. Commands (exact):
- `/tools` — list discovered tools grouped by server
- `/reset` — new session
- `/quit` — graceful shutdown (`registry.stop()`)
- anything else → `Orchestrator.chat()`; print reply prefixed `Jarvis:` and a gray `[<ms>]` latency line.

### Tests (Phase 2)
- **Unit (`FakeLLM` double):** a stub OpenAI-compatible responder driving `Orchestrator` — assert: tool-call loop executes tools in order and appends results; iteration cap triggers the stuck-message; history trimming works; `/reset` clears session. (The FakeLLM is a hand-rolled object injected into Orchestrator — refactor the client creation behind a factory parameter to allow this. Locked signature addition: `Orchestrator(..., client_factory=None)`.)
- **Integration (real servers, real LLM):** `tests/integration/test_orchestrator_live.py` — marked `@pytest.mark.live`, skipped unless `RUN_LIVE=1`. Cases: "what time is it?" → calls `get_current_time`; "save a note titled Test with body abc, tag smoke" then "search my notes for smoke" → round-trips through SQLite; "set a reminder to stretch in 2 hours" → row exists with sane `due_at`.
- **Manual acceptance (`tests/acceptance/phase-2.md`):** run the CLI and perform the scripted 10-turn checklist (greeting, time question, note create/recall, reminder set/list, weather question, search question, unknown-tool graceful failure, multi-tool request, `/tools` output, `/reset` behavior). All boxes ticked.

### Exit Gate 2
```bash
pytest tests/unit -q                          # green
RUN_LIVE=1 pytest tests/integration -q        # green (uses real keys)
python -m jarvis.cli                          # checklist in tests/acceptance/phase-2.md fully ticked
git add -A && git commit -m "phase-2: text brain complete"
```

---

## PHASE 3 — Supervisor & Sub-Agents (Multi-Agent Routing)

**Goal:** The Supervisor stops calling MCP tools directly and gains the `delegate_task` tool backed by four sub-agents. Everything still text-only via the CLI. This phase is pure Python — no Pipecat — so routing quality is measurable before audio enters the picture.

### Deliverables
- `config/agents.yaml` (exact schema §6.4)
- `jarvis/agents/base.py` — `SubAgent`
- `jarvis/agents/delegate.py` — `delegate_task` tool factory
- `jarvis/agents/supervisor.py` — extended to delegation mode
- `tests/evals/cases.yaml` + `tests/evals/routing_eval.py`

### Steps

**3.1 — `SubAgent`** (`agents/base.py`), exact API:
```python
class SubAgent:
    def __init__(self, name: str, display_name: str, description: str,
                 mcp_servers: list[str], settings: Settings,
                 registry: SkillRegistry, client_factory=None): ...
    async def run(self, task: str, on_event: Callable[[dict], None] | None = None) -> str: ...
```
- System prompt = `SUBAGENT_PROMPTS[name].format(...)` (Appendix A).
- Tool loop identical in shape to Orchestrator's but: tools = `registry.openai_tools(self.mcp_servers)`, max **5 iterations**, hard timeout **45 s** (asyncio.wait_for) → on timeout return `"FAILED: the task took too long; please try again."`.
- `on_event` is called with `{"type": "agent_start"|"agent_tool"|"agent_done", ...}` dicts — this is how the bot will later report activity to the UI. In the CLI, print `[Scheduler] calling set_reminder…` lines.
- Return value: the sub-agent's final message, **≤ 60 words per its prompt contract**. Never raises: failures return `"FAILED: <reason>"` strings.

**3.2 — `delegate_task` factory** (`agents/delegate.py`):
```python
def build_delegate_tool(sub_agents: dict[str, SubAgent], on_event=None) -> tuple[dict, Callable]:
```
Returns `(openai_tool_schema, async_handler)`. Schema (locked):
```json
{
  "type": "function",
  "function": {
    "name": "delegate_task",
    "description": "Delegate a specialist task to a sub-agent. The task must be fully self-contained; sub-agents cannot see this conversation.",
    "parameters": {
      "type": "object",
      "properties": {
        "agent_name": {"type": "string", "enum": ["scheduler", "librarian", "analyst", "systems"]},
        "task": {"type": "string", "description": "Complete, self-contained instruction including all facts needed."}
      },
      "required": ["agent_name", "task"]
    }
  }
}
```
Handler: validates `agent_name` (unknown → `"Unknown agent '<x>'. Available: scheduler, librarian, analyst, systems."`), emits events, calls `SubAgent.run`, returns the result string.

**3.3 — Supervisor delegation mode.** `Orchestrator` gains `mode: Literal["direct", "delegating"]` (constructor param, default `"delegating"`). In delegating mode: tools passed to the LLM = `[delegate_schema]` **only**; system prompt built with the full `agent_catalog` rendered from `agents.yaml` (name, display_name, description). The CLI runs in delegating mode from now on.

**3.4 — Routing eval.** `tests/evals/cases.yaml`: **30 cases**, each `{input, expect: scheduler|librarian|analyst|systems|none, must_call_tools: [...] (optional)}`. Coverage requirements: ≥ 4 cases per agent, ≥ 6 `none` cases (greetings, small talk, clarifying-question situations), ≥ 4 multi-agent cases (expect a list of 2 agents). `routing_eval.py` runs each case through the real Orchestrator (temperature 0), records which agents were delegated to, and reports accuracy. Writing the 30 cases is part of this phase — derive them from Appendix C's starter set and extend.

### Tests (Phase 3)
- **Unit:** SubAgent loop with FakeLLM (tool calls execute, cap enforced, timeout returns FAILED); delegate handler rejects unknown agent; agents.yaml loads and validates against the schema.
- **Eval (real LLM):** `RUN_LIVE=1 python -m tests.evals.routing_eval` → **accuracy ≥ 90 %** (≥ 27/30 correct). If below: tighten descriptions in `agents.yaml` and the Supervisor prompt's routing guidance — do **not** change the mechanism.
- **Manual acceptance (`tests/acceptance/phase-3.md`):** scripted 12-turn CLI checklist, including: single-agent tasks per agent; the multi-hop scenario *"Remind me to call the dentist tomorrow at 9am and save a note that Dr. Patel's office is on Main Street"* (verify both the SQLite reminder row and the note row); a clarification case (*"remind me about the thing"* → asks one question); an out-of-scope refusal.

### Exit Gate 3
```bash
pytest tests/unit -q                                   # green
RUN_LIVE=1 python -m tests.evals.routing_eval          # accuracy ≥ 90%
python -m jarvis.cli                                   # phase-3 checklist fully ticked
git add -A && git commit -m "phase-3: multi-agent supervisor complete"
```

---

## PHASE 4 — Voice In (Speech-to-Text Pipeline)

**Goal:** Speak to Jarvis from the browser and watch it understand and act — replies still text-only (logged server-side). Isolates STT quality, turn detection, and pipeline wiring before TTS is added.

### Deliverables
- `jarvis/bot/bot.py` — runner-compatible entry point
- `jarvis/bot/pipeline.py` — `build_pipeline(transport, runtime)`
- `jarvis/bot/transcript_log.py` — `TranscriptLogger` processor
- `scripts/run_bot.sh`
- `tests/acceptance/phase-4.md`

### Steps

**4.1 — Entry point** (`bot.py`, locked shape):
```python
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments

async def bot(runner_args: RunnerArguments):
    match runner_args:
        case SmallWebRTCRunnerArguments():
            transport = SmallWebRTCTransport(
                webrtc_connection=runner_args.webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=False,          # Phase 4: no TTS yet
                    vad_analyzer=SileroVADAnalyzer(),
                ),
            )
        case _:
            raise RuntimeError("Phase 4 supports SmallWebRTC only")
    await run_session(transport)

if __name__ == "__main__":
    from pipecat.runner.run import main
    main()
```
`run_session(transport)` lives in `pipeline.py` so Phase 5+ changes never touch the entry shape. It builds settings, starts `SkillRegistry`, constructs services, builds context, runs `PipelineRunner`. Any deviation from the class names above (runner API drift) is wiring-only and recorded per §0 rule 4.

**4.2 — Services & pipeline order** (locked):
```
transport.input()
  → DeepgramFluxSTTService(api_key=DEEPGRAM_API_KEY, settings model "flux-general-en")
  → context_aggregator.user()
  → OpenAILLMService(api_key, base_url, model=OPENAI_MODEL)
  → TranscriptLogger
  → context_aggregator.assistant()
```
- Context: `LLMContext(messages=[{"role": "system", "content": SUPERVISOR_PROMPT + "\n" + VOICE_ADDENDUM}], tools=ToolsSchema(standard_tools=[delegate_schema]))`, aggregator = `OpenAILLMContextAggregator`.
- Register exactly **one** Pipecat function on the LLM service: `delegate_task`, handler = the async handler from Phase 3 (`build_delegate_tool(sub_agents, on_event=bot_event_log)`). `bot_event_log` logs `[AGENT] ...` lines to stdout (the UI feed arrives in Phase 6).
- On `on_client_connected`: inject a context user message `"[system] The user just connected. Greet them briefly by name."` so the log shows the greeting path working.
- `TranscriptLogger`: a `FrameProcessor` that (a) prints every finalized user transcription with timestamp, (b) prints assistant text turns, (c) appends both to the `conversations` table with the per-connection `session_id`, (d) prints `TURN user_end→llm_done = <ms>` per turn.

**4.3 — Run & manual test:** `scripts/run_bot.sh` = `cd` to repo root, activate venv, `python -m jarvis.bot.bot`. Open the runner's prebuilt client at `http://localhost:7860/client`, click Connect, allow the mic.

### Tests (Phase 4)
- **Automated:** `tests/integration/test_bot_wiring.py` — constructs the pipeline with mocked transport/STT/LLM (Pipecat test doubles or hand fakes) and asserts: pipeline processor order is exactly as specified; `delegate_task` is registered on the LLM service; TranscriptLogger writes rows for both roles.
- **Manual acceptance (`tests/acceptance/phase-4.md`) — the Spoken Dozen:** speak these 12 utterances and check the server log shows correct transcripts **and** correct agent activity for each:
  1. "Hello Jarvis." (no agent)
  2. "What time is it?" (scheduler)
  3. "Remind me to stretch in two hours." (scheduler; verify row)
  4. "Save a note that the wifi password is swordfish." (librarian; verify row)
  5. "What did I save about wifi?" (librarian recall)
  6. "What's the weather in Tokyo?" (analyst)
  7. "Search the web for today's top tech news." (analyst)
  8. "How's my computer doing?" (systems)
  9. Multi-part: "Check the weather in Paris and remind me to pack an umbrella tomorrow morning." (analyst + scheduler)
  10. Ambiguous: "Remind me about the report." (clarifying question, no agent)
  11. Pause mid-sentence for 2 s, then continue — turn detection must not fire early and truncate you.
  12. Long utterance (≥ 30 s of continuous speech) — transcript must be complete and in order.
- Tolerances: small wording drift acceptable; named entities (times, cities, "swordfish") must be exact. If STT mangles a word consistently, add it to the Deepgram settings `keywords` list (wiring-level tuning; allowed without deviation note).

### Exit Gate 4
```bash
pytest tests/unit tests/integration -q        # green
./scripts/run_bot.sh                          # Spoken Dozen checklist fully ticked
# latency lines present in server log for every turn
git add -A && git commit -m "phase-4: voice input complete"
```

---

## PHASE 5 — Voice Out (TTS, Interruptions, Live Voice Switching)

**Goal:** Full spoken conversation. Jarvis talks back in a selectable voice, can be interrupted, and can switch voices live on command.

### Deliverables
- `config/voices.yaml` populated (≥ 3 voices)
- `jarvis/bot/voice_switch.py` — `set_voice` tool + app-message path
- `pipeline.py` updated (TTS + audio out + interruptions)
- `tests/acceptance/phase-5.md`

### Steps

**5.1 — Add TTS to the pipeline** (locked order):
```
... → OpenAILLMService → TranscriptLogger → ElevenLabsTTSService → transport.output() → context_aggregator.assistant()
```
- `ElevenLabsTTSService(api_key=..., settings=ElevenLabsTTSService.Settings(voice=<default voice id from voices.yaml>, model="eleven_flash_v2_5", stability=0.5, similarity_boost=0.75))`. (Settings-based constructor is the current API; the older `voice_id=`/`params=` kwargs are deprecated — use Settings; record a deviation if the installed version differs.)
- `TransportParams`: `audio_out_enabled=True`, `allow_interruptions=True`, VAD analyzer stays on the input.
- `TranscriptLogger` now also timestamps the first outbound audio per turn and prints `TURN user_end→first_audio = <ms>` (the latency metric the whole project optimizes).

**5.2 — Voice catalog.** Fetch the account's voice library (`GET https://api.elevenlabs.io/v1/voices` with the key — write it as `scripts/list_voices.py` printing `voice_id | name | labels`). Pick 2 additional voices beyond Rachel and append them to `config/voices.yaml` per §6.5. If the user created a clone, add it as a 4th. `id` fields: lowercase single words.

**5.3 — `set_voice` tool (control plane, locked).** The Supervisor's toolset is now exactly two tools: `delegate_task` and `set_voice`. `set_voice` is **not** an MCP tool — it's registered directly on the pipeline LLM (and exposed in the CLI as `/voice <id>`). Schema:
```json
{
  "type": "function",
  "function": {
    "name": "set_voice",
    "description": "Switch the speaking voice. Call when the user asks to change or select a voice.",
    "parameters": {"type": "object", "properties": {"voice": {"type": "string", "description": "Voice id or label from the catalog"}}, "required": ["voice"]}
  }
}
```
Handler (`voice_switch.py`): resolves `voice` against `voices.yaml` (id exact, else case-insensitive label substring; unknown → return `"I don't have a voice called '<x>'. Available: <list>."`), then pushes a `TTSUpdateSettingsFrame` with the new voice into the pipeline and returns `"Voice switched to <label>."` — which the Supervisor then speaks **in the new voice**, serving as audible confirmation. Add the voice catalog summary to the Supervisor system prompt (Appendix A, `{voice_catalog}` placeholder).

**5.4 — App-message path (for the Phase 6 UI, built now):** on `on_app_message`, handle `{"type": "voice/set", "voice": "<id>"}` by calling the same resolution + frame-push logic (no LLM involvement), and reply via app message `{"type": "voice/current", "voice": "<id>"}`.

**5.5 — CLI parity:** `/voice` lists catalog; `/voice <id>` switches (CLI has no audio — it just confirms resolution logic; audio verification happens in the browser).

### Tests (Phase 5)
- **Automated:** voice catalog resolution unit tests (exact id, label substring, unknown, case variants); pipeline wiring test asserts TTS sits between LLM and transport output and that `allow_interruptions` is True.
- **Manual acceptance (`tests/acceptance/phase-5.md`):**
  1. Re-run the **Spoken Dozen** — every reply must now be *heard*, not just logged.
  2. **Voice switching:** "Jarvis, switch to the <other> voice" → confirmation spoken in the new voice; run one more command to be sure it sticks; switch back.
  3. **Interruption:** ask "tell me a long story about space" (unlock length via prompt allowance for this test) → start talking over it 3 s in → Jarvis stops within ~1 s and responds to the new input. Repeat twice.
  4. **Acknowledgment behavior:** ask a scheduler question → Jarvis must say a short acknowledgment *before* the answer (dead air ≤ 1 s between ack end and answer start).
  5. **Latency:** from the server log, compute over the Dozen: median `user_end→first_audio` ≤ **1200 ms** for non-delegated turns, ≤ **2500 ms** for delegated turns. If missed: first check network and LLM provider speed; allowed tuning = smaller `OPENAI_MODEL`, TTS `speed` setting, VAD aggressiveness (wiring-level). Architecture does not change.

### Exit Gate 5
```bash
pytest tests/unit tests/integration -q    # green
./scripts/run_bot.sh                      # phase-5 checklist fully ticked, latency targets met
git add -A && git commit -m "phase-5: voice output complete"
```

---

## PHASE 6 — Web Client (React)

**Goal:** Replace the runner's bare prebuilt UI with Jarvis's own console: connect control, mic control, live transcript, voice picker, agent-activity feed, speaking indicator.

### Deliverables
- `web/` Vite React-TS app per §5 layout
- `scripts/run_web.sh`
- `tests/acceptance/phase-6.md`

### Steps

**6.1 — Scaffold (locked):**
```bash
npm create vite@latest web -- --template react-ts
cd web && npm install
npm install @pipecat-ai/client-js @pipecat-ai/client-react @pipecat-ai/small-webrtc-transport
```
No UI framework, no router, no state library. Styling: one `App.css`, dark theme (background `#0a0f14`, accent `#38bdf8`, text `#e2e8f0`).

**6.2 — Client singleton** (`src/jarvisClient.ts`, locked shape):
```ts
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

export const client = new PipecatClient({
  transport: new SmallWebRTCTransport(),
  enableMic: true,
  callbacks: { /* wired in components via hooks where possible */ },
});

export const connect = () =>
  client.connect({ webrtcRequestParams: { endpoint: "http://localhost:7860/api/offer" } });
```

**6.3 — Server→client events (bot side, this phase adds):** in `bot/pipeline.py`, the delegate tool's `on_event` callback now also **sends an app message** through the transport on `agent_start` / `agent_done` (`{"type": "agent", "name": "scheduler", "state": "working"|"done"}`). The app-message send method on the installed SmallWebRTC transport (e.g. `send_app_message` on the output transport/connection) is wiring-level — verify against the installed version and record a deviation if named differently. On client connect, the bot also pushes `{"type": "voice/catalog", "voices": [...], "current": "<id>"}` from `voices.yaml`.

**6.4 — Components (locked behavior):**
- `main.tsx`: `PipecatClientProvider` wrapping `<App/>` and `<PipecatClientAudio/>` (exact pattern from the Pipecat React docs).
- `ConnectButton`: shows transport state (`usePipecatClientTransportState`); Connect/Disconnect; status pill (gray disconnected / amber connecting / green ready).
- `MicControls`: mute/unmute toggle via `client.enableMic(bool)`; **hold Spacebar = push-to-talk** (keydown unmute, keyup mute; ignore auto-repeat); visual mic state.
- `Transcript`: `usePipecatConversation()` messages, user right-aligned, Jarvis left; auto-scroll; timestamps.
- `VoicePicker`: `<select>` populated from the `voice/catalog` app message (listen via `useRTVIClientEvent(RTVIEvent.ServerMessage, ...)`); on change, send app message `{"type":"voice/set","voice":id}` (client transport `sendAppMessage`); optimistic select, reconciled on `voice/current`.
- `AgentActivity`: subscribes to `agent` messages; shows the current agent chip ("⚙ Scheduler working…") and a timestamped history of the last 5; clears "working" on `done`.
- Speaking indicator: central orb pulses while the bot is speaking (RTVI bot started/stopped speaking events); idle = dim ring.
- Error banner: `RTVIEvent.Error` → red banner with the message; auto-dismiss on next successful turn.

### Tests (Phase 6)
- **Automated:** `npm run build` succeeds with strict TS, zero errors.
- **Manual acceptance (`tests/acceptance/phase-6.md`):** with the bot running — connect; speak "what time is it" (transcript lines appear for both sides within ~2 s); voice picker switches voice (audible + server log); agent feed shows Scheduler chip during a reminder request; mute stops transcription; hold-to-talk works; kill and restart the bot, reconnect without refreshing the page (or with one refresh — record which); `npm run build` clean.

### Exit Gate 6
```bash
cd web && npm run build                 # clean
./scripts/run_bot.sh & ./scripts/run_web.sh   # checklist fully ticked
git add -A && git commit -m "phase-6: web client complete"
```

---

## PHASE 7 — Conversational Polish & Proactivity

**Goal:** The details that make it feel like Jarvis: proactive reminders, graceful degradation, measured latency.

### Deliverables
- `jarvis/bot/reminders_watcher.py`
- Error-surface paths in bot + client error banner (already Phase 6; verified here)
- `scripts/latency_probe.py`
- `tests/acceptance/phase-7.md`

### Steps

**7.1 — `RemindersWatcher` (locked):** an asyncio task started with the bot session:
- Every **30 s**, call `get_due_reminders` via `SkillRegistry.call`.
- If rows returned **and a client is currently connected**: inject a user-side context message `"[system] The following reminders are now due: <messages>. Tell the user naturally and briefly."` This produces a spoken, unprompted reminder.
- Dedup is guaranteed by the `delivered` flag (Phase 1 design) — do not add a second mechanism.
- Failures (DB locked, server down) → log warning, keep watching. Never crash the bot.

**7.2 — Graceful degradation matrix (locked behavior — verify each):**

| Failure | Behavior |
|---|---|
| LLM API error mid-turn | Supervisor turn fails → user hears nothing new; client shows error banner; next turn retries normally (context intact) |
| ElevenLabs error | Log error frame; banner shows speech-service error; text transcript still updates |
| Deepgram error | Banner shows transcription error; suggest reconnect |
| Tavily degraded/missing | Analyst returns the "search unavailable" sentence; Supervisor says it plainly and moves on |
| MCP server crash | `SkillRegistry.call` returns failure sentence; Supervisor relays it; `RemindersWatcher` unaffected |
| Reminders while disconnected | They accumulate; on next connect, watcher delivers within 30 s |

**7.3 — `scripts/latency_probe.py`:** parses the bot log and reports per-turn `user_end→first_audio`: count, p50, p90, split by delegated vs non-delegated (a turn is delegated if an `[AGENT]` line falls inside it). Print a table.

**7.4 — Stretch (NOT gated):** wake word. Sketch only: Picovoice Porcupine Web (free tier) runs client-side; on detection, unmute + play a chime; server unchanged. Implement only if everything else is green; any implementation must not alter the server.

### Tests (Phase 7)
- **Automated:** watcher unit test — fake registry returning due reminders → exactly one context injection per due row; none when empty; none when disconnected.
- **Manual acceptance (`tests/acceptance/phase-7.md`):** set a reminder 2 minutes out, keep the session open, confirm Jarvis speaks it unprompted within ~2.5 min and the row shows `delivered=1`; disconnect, set another due reminder, reconnect → delivered within 30 s; simulate each degradation-matrix row that is safely simulable (kill Tavily key, stop an MCP server, revoke ElevenLabs key) and tick the expected behavior; run `latency_probe.py` after a 15-turn session: **p50 ≤ 1200 ms non-delegated, ≤ 2500 ms delegated; p90 ≤ 3500 ms overall.**

### Exit Gate 7
```bash
pytest tests/unit tests/integration -q      # green
python scripts/latency_probe.py             # targets met
# phase-7 checklist fully ticked
git add -A && git commit -m "phase-7: polish and proactivity complete"
```

---

## PHASE 8 — Hardening, Docs & Fresh-Clone Verification

**Goal:** Someone else (or a future model) can clone and run this from the README alone.

### Deliverables
- `README.md` (structure locked below)
- Final `requirements-lock.txt` / `package-lock.json`
- `tests/acceptance/phase-8.md` wrapping §8

### Steps

**8.1 — README.md, exact section order:**
1. What this is (3 sentences) + the §2.1 architecture diagram
2. Prerequisites (keys table from §4)
3. Quickstart: `uv venv … / uv pip install -r requirements-lock.txt` → `cp .env.example .env` (fill keys) → `python scripts/init_db.py` → `./scripts/run_bot.sh` → `./scripts/run_web.sh` → open `http://localhost:5173`
4. Using Jarvis: voice commands tour, `/voice`, push-to-talk, voice picker
5. Project layout (the §5 tree)
6. Testing: how to run unit / integration / evals / acceptance
7. Troubleshooting table (≥ 8 rows: no audio, mic denied, 401s, slow responses, MCP server won't start, port in use, voices not switching, reminders not firing)
8. Configuration reference (every env var + config file)

**8.2 — Fresh-clone verification (the real gate):** clone the repo into a clean directory/machine user, then follow **only the README** — no prior knowledge. Every missing step or ambiguity found gets fixed in the README, then the clone test restarts from scratch.

**8.3 — Run the full Master Acceptance Test (§8) against the fresh clone.**

**8.4 — DEVIATIONS.md audit:** every entry confirmed still accurate and still wiring-level; anything architecture-shaped is a design violation and must be reverted to spec before the gate passes.

### Exit Gate 8
```bash
pytest tests/unit tests/integration -q        # green
RUN_LIVE=1 pytest tests/integration -q        # green
RUN_LIVE=1 python -m tests.evals.routing_eval # ≥ 90%
# Master Acceptance Test fully ticked on the fresh clone
git add -A && git commit -m "phase-8: jarvis v1 complete"
```

---

## 8. Master Acceptance Test — "The Jarvis Demo Script"

Executed at the Phase 8 gate, end-to-end, in the browser, fresh clone. Each row: say it → expected observable result → where to verify.

| # | Say | Expected | Verify |
|---|-----|----------|--------|
| 1 | "Hello Jarvis." | Brief spoken greeting, no delegation | ears + transcript |
| 2 | "What time is it?" | Acknowledgment, then correct current time spoken | ears + log `TURN` ≤ 2500 ms |
| 3 | "Remind me to call the dentist tomorrow at 9 AM." | Confirmation with resolved absolute date/time | `reminders` row, `due_at` correct for `JARVIS_TIMEZONE` |
| 4 | "What's on my schedule tomorrow?" | The dentist reminder spoken back | ears |
| 5 | "Actually, move that to 9:30." | Updated confirmation | `due_at` updated |
| 6 | "Remember that Dr. Patel's office is on Main Street." | Stored confirmation | `notes` row exists |
| 7 | "Where is my dentist's office?" | "Main Street" spoken from memory | ears |
| 8 | "What's the weather in London right now?" | Current conditions + temp in one breath | ears |
| 9 | "Search the web for the latest SpaceX news." | ≤ 60-word spoken brief | ears |
| 10 | "How is my computer holding up?" | CPU/mem/disk spoken; flags anything ≥ 85 % | ears |
| 11 | "Switch to the <other> voice." | Confirmation **in the new voice** | ears |
| 12 | (While Jarvis speaks a long answer) "Jarvis, stop — what's two plus two?" | Speech cuts ≤ 1 s; answers "Four." | ears |
| 13 | "Set a reminder to stand up in 2 minutes." | Confirmation | row exists |
| 14 | *(wait ~2.5 min, stay connected)* | Jarvis speaks the reminder **unprompted** | ears + `delivered=1` |
| 15 | "Thanks, Jarvis." | Short, warm sign-off; no tools called | transcript |

Pass = all 15 rows observed. Record timings from the log next to each row in `tests/acceptance/phase-8.md`.

---

## 9. Latency Budget & Performance Targets

### 9.1 Budget per non-delegated turn (target: ≤ 1200 ms p50)

| Segment | Budget |
|---|---|
| End-of-speech detection (Flux turn detection) | ~300 ms |
| STT finalize + context aggregation | ~50 ms |
| LLM first token (gpt-4.1-mini class) | ~300 ms |
| First sentence aggregation | ~100 ms |
| ElevenLabs Flash first audio | ~150 ms |
| Transport/network (localhost P2P) | ~50 ms |
| **Headroom** | ~250 ms |

Delegated turns add the sub-agent loop (1–3 LLM calls + tool calls): budget **≤ 2500 ms p50**, masked by the mandatory spoken acknowledgment.

### 9.2 Hard targets (gated in Phases 5 & 7)
- p50 `user_end→first_audio`: ≤ 1200 ms non-delegated; ≤ 2500 ms delegated
- p90 overall: ≤ 3500 ms
- Interruption cut-off: ≤ 1000 ms from user speech start to bot silence
- Reminder delivery lag: ≤ 45 s after `due_at`

### 9.3 Stretch goals (explicitly not gated, v1.1 candidates)
- Wake word ("Hey Jarvis") client-side via Picovoice Porcupine Web
- Conversation auto-summarization into long-term memory
- Smart-home MCP server + fifth sub-agent
- Telephony (Pipecat runner already supports Twilio/Telnyx/Plivo/Exotel transports — architecture needs no change)

---

## 10. Risk Table & Contingencies (the only pre-approved plan changes)

| Risk | Trigger | Contingency (exact) |
|---|---|---|
| `DeepgramFluxSTTService` / Flux model unavailable on account | Phase 4: STT errors at connect | Use `DeepgramSTTService` with `settings model "nova-3"`, keep Silero VAD endpointing; record in DEVIATIONS.md |
| ElevenLabs free-tier exhaustion during dev | TTS 429s | Reduce test verbosity; keep gate runs only. If hard-blocked, pause — do **not** swap TTS providers without revisiting this document |
| LLM provider tool-calling unreliable | Phase 2/3 gate failures with malformed/missed tool calls | Switch `OPENAI_BASE_URL`/`OPENAI_MODEL` to OpenAI `gpt-4.1-mini` (the default). Never compensate with prompt hacks |
| MCP Python SDK major-version drift (v2 changes import paths) | Phase 1 import errors | §0 rule 4 applies: adapt imports only; the five-server stdio architecture is untouchable |
| Pipecat API drift (Settings names, runner endpoints) | Any phase: constructor/endpoint mismatch | §0 rule 4: consult installed package (`python -c "help(...)"`, `docs.pipecat.ai`), adapt wiring, record deviation |
| SmallWebRTC fails off-localhost | Testing from another machine | v1 is localhost-only by design (§1.2). Note it; do not add TURN/Daily |
| Routing eval stuck at 80–89 % | Phase 3 | Iterate `agents.yaml` descriptions + supervisor routing rules only. If ≥ 3 iterations fail, escalate to user before touching mechanism |
| Mic permission denied in browser | Phase 4/6 | README troubleshooting row; serve client on `localhost` (secure context) — already the design |

---

## 11. Deviation Policy & `DEVIATIONS.md` Format

`DEVIATIONS.md` header (created in Phase 0):

```markdown
# DEVIATIONS
Wiring-level adaptations required by installed library versions, per plan §0 rule 4.
Architecture deviations are forbidden and must be reverted.

## Entry format
### D-001 — <date>
- Plan reference: <section/phase>
- Specified: <what the plan said>
- Installed reality: <library==version, what it actually requires>
- Adaptation: <the minimal wiring change made>
- Architecture impact: none (must always be "none")
```

Number entries sequentially. The Phase 8 audit re-validates every entry.

---

## Appendix A — System Prompts (verbatim source of truth for `jarvis/prompts.py`)

### A.1 `SUPERVISOR_PROMPT`

```
You are {jarvis_name}, a precise, calm, subtly formal personal AI assistant. You address the user as "{user_name}" occasionally — naturally, not in every sentence. The user's timezone is {timezone}.

You lead a team of specialist agents. You personally handle greetings, small talk, clarifying questions, and delivering results. All specialist work is delegated with the delegate_task tool. Specialists cannot see this conversation, so every task you write must be fully self-contained.

Specialists:
{agent_catalog}

Voice control: you can change your speaking voice with the set_voice tool. Available voices:
{voice_catalog}

Rules:
1. Before every delegate_task call, say one short acknowledgment sentence (10 words or fewer), such as "One moment, checking that now." It will be spoken while the specialist works.
2. For multi-part requests, make one delegate_task call per specialist, then combine all results into a single natural reply.
3. Never invent facts. Times, dates, weather, news, and stored memories come only from specialist results. If a specialist returns FAILED, say so plainly in one sentence and suggest the fix.
4. If a request is missing required information, ask exactly one short clarifying question. Do not guess dates, times, or names.
5. Keep every reply under 40 words unless the user explicitly asks for more.
6. When the user asks to change your voice, call set_voice, then confirm briefly.
7. Refuse harmful requests briefly and politely.
```

### A.2 `VOICE_ADDENDUM` (appended in bot contexts only)

```
You are speaking aloud through a voice interface. Output plain prose only: no markdown, no bullet points, no numbered lists, no emoji, no symbols. Use short sentences. Spell out times and dates naturally, for example "nine thirty AM tomorrow", not "09:30 2026-08-05".
```

### A.3 `SUBAGENT_PROMPTS`

**scheduler:**
```
You are the Scheduler, a specialist for time, dates, and reminders. Timezone: {timezone}.
Always use your tools for date math and for storing or retrieving reminders; never compute dates in your head. When given a relative time ("tomorrow at 9"), resolve it with your tools before storing.
Output contract: one or two short sentences stating exactly what was done or found, including the resolved absolute time. On failure output exactly: FAILED: <reason>. Maximum 60 words. Plain text.
```

**librarian:**
```
You are the Librarian, keeper of long-term memory.
Storing: use create_note with a 3-to-6-word title and comma-separated keyword tags.
Recalling: always try search_notes with two or three keyword variants before reporting that nothing is stored.
Output contract: one or two short sentences with the stored fact(s) or confirmation of what was saved. On failure output exactly: FAILED: <reason>. Maximum 60 words. Plain text.
```

**analyst:**
```
You are the Analyst, a research specialist.
Use web_search for anything about current events or facts you could not know, and get_weather for all weather questions. Never answer current-world questions from your own knowledge.
Output contract: a factual brief of at most 60 words leading with the key numbers or findings. On failure output exactly: FAILED: <reason>. Plain text.
```

**systems:**
```
You are the Systems specialist for the user's local machine.
Use get_system_status for health checks and get_top_processes when usage is high or the user asks what is running. Flag any metric at or above 85 percent.
Output contract: a status brief of at most 50 words. On failure output exactly: FAILED: <reason>. Plain text.
```

### A.4 Rendering rules
- `{agent_catalog}` = one line per agent from `agents.yaml`: `- {name} ({display_name}): {description}`
- `{voice_catalog}` = one line per voice from `voices.yaml`: `- {id}: {label}`
- In Phase 2 (no agents yet), `{agent_catalog}` = `(none yet — call tools directly)` and the Supervisor receives MCP tools directly per the Phase 2 scope note.

---

## Appendix B — Routing Eval Starter Cases (`tests/evals/cases.yaml`, extend to 30)

```yaml
- {input: "what time is it", expect: scheduler}
- {input: "remind me to water the plants in 3 hours", expect: scheduler}
- {input: "what day of the week is August 20th", expect: scheduler}
- {input: "what reminders do I have today", expect: scheduler}
- {input: "remember that my passport expires in March", expect: librarian}
- {input: "save a note with the project wifi password", expect: librarian}
- {input: "when does my passport expire", expect: librarian}
- {input: "what did I save about the wifi", expect: librarian}
- {input: "what's the weather in Berlin", expect: analyst}
- {input: "search the web for the latest AI news", expect: analyst}
- {input: "who won the game last night", expect: analyst}
- {input: "how is my computer doing", expect: systems}
- {input: "what's using all my memory", expect: systems}
- {input: "hello", expect: none}
- {input: "thanks, that's all", expect: none}
- {input: "remind me about the thing", expect: none}        # must ask a clarifying question
- {input: "check the weather in Rome and remind me to pack tonight", expect: [analyst, scheduler]}
- {input: "save a note that the plumber comes Friday and remind me Thursday evening", expect: [librarian, scheduler]}
```
*(Extend to exactly 30, preserving the Phase 3, step 3.4 coverage requirements.)*

---

## Appendix C — Verified References

Key third-party facts in this plan were verified against current documentation at the time of writing:

- Pipecat packaging, Python ≥ 3.11 requirement, per-service extras, and multi-agent posture[^1^]
- `MCPClient` (stdio/SSE/HTTP), `register_tools`, the `pipecat-ai[mcp]` extra, and multi-server tool merging[^2^]
- `ElevenLabsTTSService` Settings-based configuration, default model `eleven_flash_v2_5`, and runtime `TTSUpdateSettingsFrame` voice updates[^3^][^4^]
- Deepgram STT variants including `DeepgramFluxSTTService` with `flux-general-en` turn detection[^5^]
- The development runner: `localhost:7860`, prebuilt client at `/client`, `POST /api/offer`, and the `RunnerArguments` bot entry shape[^6^][^7^]
- The React client SDK packages and the `client.connect({webrtcRequestParams: {endpoint}})` connection pattern[^8^]
- ElevenLabs model latency characteristics (Flash ≈ 75 ms) and Rachel voice ID `21m00Tcm4TlvDq8ikWAM`[^9^]
- Official MCP Python SDK FastMCP stdio server pattern[^10^]

[^1^]: https://docs.pipecat.ai/pipecat/get-started/introduction
[^2^]: https://docs.pipecat.ai/api-reference/server/utilities/mcp/mcp
[^3^]: https://docs.pipecat.ai/api-reference/server/services/tts/elevenlabs
[^4^]: https://reference-server.pipecat.ai/en/stable/api/pipecat.services.elevenlabs.tts.html
[^5^]: https://docs.pipecat.ai/api-reference/server/services/stt/deepgram
[^6^]: https://docs.pipecat.ai/pipecat/deployment/running-bots-locally
[^7^]: https://docs.pipecat.ai/api-reference/server/utilities/runner/guide
[^8^]: https://docs.pipecat.ai/client/guides/building-a-voice-ui
[^9^]: https://www.webfuse.com/elevenlabs-cheat-sheet
[^10^]: https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk
