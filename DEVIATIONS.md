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

### D-007 — 2026-08-06
- Plan reference: Phase 4 step 4.2 (TranscriptLogger duties: USER/JARVIS lines, conversations-table persistence)
- Specified: TranscriptLogger (pipeline processor between the LLM and TTS services) prints finalized user transcripts and persists both roles
- Installed reality: pipecat 1.4.0's `LLMUserContextAggregator` (universal aggregators) CONSUMES `TranscriptionFrame` instead of forwarding it downstream ("Interim transcriptions and translations are consumed here and not pushed downstream, same as final TranscriptionFrame"). Found by the first end-to-end audio run (Phase 4 spoken acceptance): JARVIS lines and TURN lines printed correctly, but no USER line ever appeared and user rows were missing from the conversations table
- Adaptation: user-side transcript logging moved to a task-level observer — `TranscriptObserver(BaseObserver)` in `jarvis/bot/transcript_log.py`, attached via `PipelineTask(pipeline, observers=[...])`. Observers see every frame at every hop without touching pipeline topology; the locked 9-processor order is unchanged and TranscriptLogger keeps its locked position and its assistant-side duties (JARVIS lines, TURN latency lines, assistant persistence). `scripts/spoken_acceptance.py` added as test tooling (plays WAV files over /api/offer using only locked deps) so the Phase 4 spoken checklist can run without a human at the mic
- Architecture impact: none

### D-008 — 2026-08-06
- Plan reference: Phase 4 step 4.3 (greeting on connect), Phase 7 step 7.2 (reminder injection via `aggregators.user().add_message(...)`)
- Specified: inject a user-role context message with `add_message(...)`; the LLM turn follows
- Installed reality: pipecat 1.4.0's `LLMUserAggregator` has no `add_message` — `on_client_connected` raised `AttributeError` (found by the same first end-to-end audio run as D-007; the greeting never fired and the error also killed the voice/catalog push in that handler). The 1.4 API is `add_messages([...])` (plural, sync, context-only) plus `await push_context_frame()` to actually trigger the LLM run downstream. Affects both the greeting and RemindersWatcher context injection (unit tests used fakes, so neither surfaced until live audio)
- Adaptation: both call sites use `add_messages([msg])` + `await push_context_frame()`; locked message contents and handler placement unchanged
- Architecture impact: none

### D-009 — 2026-08-06
- Plan reference: Phase 4 step 4.3 (function registration on the LLM service), Phase 5 step 5.3 (set_voice)
- Specified: `llm.register_function("delegate_task", handler)` where handlers have the `(arguments: dict) -> confirmation str` contract and return the tool result
- Installed reality: pipecat 1.4.0 invokes registered handlers with a single `FunctionCallParams` object (`.arguments`, `.result_callback`, …) and expects the result delivered via `await params.result_callback(result)` — return values are ignored. Found by the same first end-to-end audio run: every delegate_task call errored with `'FunctionCallParams' object has no attribute 'get'`, so acknowledgments were spoken but no agent ever ran. Invisible to the CLI path (the Supervisor drives its own tool loop with the dict contract) and to existing wiring tests (they assert registration, not invocation)
- Adaptation: a small `adapt_to_pipecat` wrapper at the registration site in `jarvis/bot/pipeline.py` unpacks `params.arguments`, awaits the locked dict-contract handler, and forwards its return via `result_callback`. `jarvis/agents/delegate.py` and `jarvis/bot/voice_switch.py` contracts unchanged (Supervisor and unit tests unaffected); regression test `test_registered_handlers_accept_pipecat_params` added
- Architecture impact: none

### D-010 — 2026-08-06
- Plan reference: Phase 4 acceptance item 11 ("Pause 2 s mid-sentence, then continue → turn detection did NOT fire early; single complete transcript"), Phase 4 step 4.2 (VADProcessor(SileroVADAnalyzer) construction)
- Specified: `VADProcessor(SileroVADAnalyzer())` with pipecat defaults; turn detection must not fire early on a 2 s mid-sentence pause
- Installed reality: two independent end-of-turn layers fire on a 2 s pause after a complete clause — (a) Deepgram Flux's server-side EOT (confidence-based; fired even with `eot_threshold=0.9`, so that knob was reverted to default), which only finalizes transcripts mid-turn (harmless — segments accumulate), and (b) pipecat 1.4.0's local `LocalSmartTurnAnalyzerV3`, the actual turn-close decision-maker, which is triggered by `VADUserStoppedSpeakingFrame`. pipecat's default `VAD_STOP_SECS` is 0.2 s, so any 0.2 s silence hands the smart-turn model a complete clause and it answers COMPLETE — the utterance split into two turns ("Remind me to buy milk." / "Tomorrow at seven AM.") in every early run
- Adaptation (wiring only, locked processor class and pipeline position unchanged): `SileroVADAnalyzer(params=VADParams(stop_secs=2.5))`. With a 2.5 s stop window, a 2.0 s pause never reaches the turn analyzer; the turn closes 2.5 s after the final word instead. Verified live: the rebuilt u11 utterance (sample-exact 2.000 s silence, measured with ffmpeg silencedetect — the original TTS-generated file's gap had drifted to 2.699 s) now completes as ONE turn with the full merged intent delegated to Scheduler. Trade-off accepted: every turn's close latency grows by ~2.3 s over the 0.2 s default. Also noted: the acceptance harness `scripts/spoken_acceptance.py` gained per-turn bot-audio recording (`--audio-dir`) for machine-verifiable audible evidence — test tooling only
- Architecture impact: none

### D-011 — 2026-08-06
- Plan reference: Phase 1 §1.4 (mcp-web: "Tavily search"), Phase 4 acceptance item 7
- Specified: `web_search` calls the Tavily REST API (`https://api.tavily.com/search`) via httpx with Bearer auth
- Installed reality: Tavily's AWS WAF started returning a bare `awselb` HTTP 403 for the sandbox's egress IP mid-session (2026-08-06, between 04:38 and 08:27 UTC+8) — the block sits BEFORE authentication (an intentionally invalid key receives the identical 403), so account/key health is irrelevant; the account dashboard showed "operational" throughout. The same source IP reaches Tavily's hosted MCP endpoint (`https://mcp.tavily.com/mcp/`) without restriction
- Adaptation (wiring only, locked tool contract unchanged): `web_search` in `mcp_servers/mcp_web/logic.py` is MCP-transport-first — JSON-RPC `tools/call tavily_search` against the hosted endpoint (SSE-parsed response) — with the original REST call kept as fallback on any MCP-transport failure. Return shape ({"results": [{title,url,snippet}], "answer": str}), the 10 s timeout, the never-raise degradation, and error strings are unchanged; `scripts/check_env.py` probes the MCP endpoint accordingly. Verified live through the bot: "Search the web for today's top tech news." returned real current headlines (SpaceX, Snap, Sila, General Fusion) in the spoken reply
- Architecture impact: none
