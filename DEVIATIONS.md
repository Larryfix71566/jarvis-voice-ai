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

---

### D-001 — 2026-08-04
- Plan reference: §3 (Locked Technology Decisions, "MCP server SDK"), Phase 1 server.py template
- Specified: package `mcp[cli]`, servers import `from mcp.server.fastmcp import FastMCP`
- Installed reality: FastMCP graduated to the standalone `fastmcp` package (3.x ships as a meta-package over `fastmcp-slim`); the `fastmcp` 2.x line is incompatible with current `mcp` releases (`McpError` was renamed `MCPError`). Final resolved pair: `mcp==1.29.0` (client) + `fastmcp==3.4.5` (server)
- Adaptation: server.py files import `from fastmcp import FastMCP` (identical API: `FastMCP(name)`, `@mcp.tool()`, `mcp.run(transport="stdio")`); requirements.txt adds `fastmcp>=3.4.5` alongside `mcp[cli]`; client-side imports (`ClientSession`, `StdioServerParameters`, `stdio_client`) verified unchanged
- Architecture impact: none

### D-002 — 2026-08-04
- Plan reference: Phase 0, step 0.2 dependency list
- Specified: dependency list without a YAML parser
- Installed reality: Phase 2+ requires parsing `config/*.yaml` (`SkillRegistry`, agents, voices); `pyyaml` was present only transitively
- Adaptation: added `pyyaml` explicitly to requirements.txt
- Architecture impact: none

### D-003 — 2026-08-05
- Plan reference: Phase 2, step 2.3 (Orchestrator defaults, "temperature 0.3")
- Specified: Supervisor LLM calls send `temperature=0.3` (0.0 in evals)
- Installed reality: the `kimi-k2.x` model family (Moonshot API) rejects any temperature other than 1 with HTTP 400 `invalid temperature: only 1 is allowed for this model`
- Adaptation: `Orchestrator(temperature=None)` default now omits the parameter entirely so the provider default applies; an explicit value is still forwarded for providers that support it. Live tests no longer pass `temperature=0.0`
- Architecture impact: none

### D-004 — 2026-08-05
- Plan reference: Phase 4 step 4.2 (service construction), Phase 5 step 5.1 (TTS Settings)
- Specified: `DeepgramFluxSTTService` importable from `pipecat.services.deepgram.stt` with nested `.Settings(model=...)`; `ToolsSchema` from `pipecat.processors.aggregators.openai_llm_context` taking raw OpenAI tool dicts in `standard_tools`
- Installed reality: pipecat 1.4.0 — Flux STT lives at `pipecat.services.deepgram.flux.stt` with standalone `DeepgramFluxSTTSettings(model=...)` from `pipecat.services.deepgram.flux.base`; `ToolsSchema` lives at `pipecat.adapters.schemas.tools_schema` and its `standard_tools` takes `FunctionSchema` objects (`pipecat.adapters.schemas.function_schema`), not raw dicts. `TransportParams` has NO `vad_analyzer` or `allow_interruptions` fields: VAD is a pipeline processor (`VADProcessor(vad_analyzer=SileroVADAnalyzer())`) and interruptions come from Flux STT's `should_interrupt=True` (default). ElevenLabsTTSSettings matches the plan (voice/model/stability/similarity_boost fields present). STT "keywords" tuning maps to the Flux settings `keyterm` field
- Adaptation: updated imports in `jarvis/bot/pipeline.py`; the locked OpenAI delegate_task schema is converted to `FunctionSchema` (same name/description/properties/required); VADProcessor inserted right after transport.input(); `should_interrupt=True` passed explicitly to the Flux service; bot.py TransportParams keeps audio_in/out only. STT/TTS settings values unchanged
- Architecture impact: none

### D-005 — 2026-08-05
- Plan reference: Phase 6 step 6.3/6.4 (app-message path: client `sendAppMessage` ↔ bot `on_app_message` / server app messages surfaced as `RTVIEvent.ServerMessage`)
- Specified: client calls transport `sendAppMessage({"type":"voice/set","voice":id})`; bot's `on_app_message` receives that raw dict; bot's app messages reach the client as ServerMessage events
- Installed reality: `@pipecat-ai/client-js==1.13.0` has no raw `sendAppMessage` — `sendClientMessage(type, data)` always sends an rtvi-ai labeled RTVIMessage `{"type":"client-message","data":{"t":<type>,"d":{...}}}`; the JS transport drops inbound data-channel messages unless `label==="rtvi-ai"`. Server side (pipecat 1.4.0) is raw both ways: `send_app_message` sends the dict as-is and `on_app_message` receives whatever JSON arrives
- Adaptation (wiring only, locked payload shapes unchanged): (a) bot `send_app_message` wraps payloads in `{"id","label":"rtvi-ai","type":"server-message","data":<payload>}` so client-js surfaces them as ServerMessage; (b) bot `on_app_message` normalizes the client-js `client-message` envelope back to the locked raw shape before handling (raw locked-shape messages still accepted); (c) client calls `client.sendClientMessage("voice/set", {voice:id})`. No RTVIProcessor added — the locked 9-processor pipeline order is unchanged
- Architecture impact: none

### D-006 — 2026-08-05
- Plan reference: Phase 6 step 6.1 scaffold (locked commands `npm install`), Phase 0 lock-file discipline
- Specified: standard `npm install`; `requirements-lock.txt` regenerated from the working environment
- Installed reality: (a) the sandbox mount does not support symlinks, so npm's `.bin` linking fails (ENOTSUP); (b) the previously frozen `requirements-lock.txt` contained mutually inconsistent pairs left by one-at-a-time installs (fastapi 0.116.1 vs starlette 1.3.1; uvicorn[standard] 0.52.1 vs httptools 0.6.4) and could not reinstall cleanly after a sandbox wipe
- Adaptation: (a) web dependencies installed with `npm install --no-bin-links` and package.json scripts invoke tools by explicit node path (`node node_modules/typescript/bin/tsc`, `node node_modules/vite/bin/vite.js`) — `npm run build` / `npm run dev` usage unchanged; (b) lock regenerated from a fresh consistent resolve with pipecat-ai==1.4.0, mcp==1.29.0, fastmcp==3.4.5 kept pinned (fastapi 0.141.1, starlette 1.3.1, httptools 0.8.0); full test suite re-run green against the new set. (c) Phase 8 fresh-clone verification found the freeze had also captured sandbox-preinstalled system packages (e.g. `agent-gw`, not on public PyPI), breaking the locked quickstart on a clean machine: the lock was re-frozen from a clean venv containing ONLY the project's dependency closure (148 packages; e.g. websockets 17.0.1 vs the sandbox's 15.0.1), and the entire gate suite (180 passed, live integration 26 passed, routing eval ≥ 90%) was validated against that closure in a fresh clone. `scripts/run_bot.sh` now prefers `.venv/bin/python` when a venv exists (falls back to python3/user-site)
- Architecture impact: none
