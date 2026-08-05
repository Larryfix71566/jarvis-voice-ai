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
- Installed reality: pipecat 1.4.0 — Flux STT lives at `pipecat.services.deepgram.flux.stt` with standalone `DeepgramFluxSTTSettings(model=...)` from `pipecat.services.deepgram.flux.base`; `ToolsSchema` lives at `pipecat.adapters.schemas.tools_schema` and its `standard_tools` takes `FunctionSchema` objects (`pipecat.adapters.schemas.function_schema`), not raw dicts. ElevenLabsTTSSettings matches the plan (voice/model/stability/similarity_boost fields present). STT "keywords" tuning maps to the Flux settings `keyterm` field
- Adaptation: updated imports in `jarvis/bot/pipeline.py`; the locked OpenAI delegate_task schema is converted to `FunctionSchema` (same name/description/properties/required); STT/TTS settings values unchanged
- Architecture impact: none
