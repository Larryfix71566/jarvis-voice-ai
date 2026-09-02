# Mortimer Optimization Plan — Cost, Memory, and Model Routing

Status: Rev 3.2 — 2026-09-01 (Phase 1/1b rewritten: caching needs the native Messages API, the OpenAI-compat layer cannot carry it; see "Rev 3.2 resolutions" at the end. Rev 3.1: conflicts resolved + model-floor policy.)

**Standing policy (Larry, 2026-09-01) — the model floor:** the ONLY agent that may run Haiku is the voice agent (Supervisor). Every other agent — the five specialists and the planner/executor loop — runs at Sonnet-or-equivalent or above. Cost work on those agents is caching, context slimming, effort, and choosing *among* Sonnet-class-and-up models; it is never dropping below the floor. This overrides the earlier "Haiku is correct for the conversational agents" stance in `config/agents.yaml` and CLAUDE.md, and it is bound in CONFIG plus a test (Phase 0b item 5), not stored as a memory fact — a fact only persuades a model, it cannot bind a tool's behaviour (the same lesson as `jarvis_units`).
Scope: sub-agents and supervisor. Voice transport (STT/TTS/realtime) explicitly exempt — stays on native provider connections for latency.

Guiding order: **measure → cache → gate memory writes → route by capability → slim context → batch/local.**
Each phase has exit criteria; no phase starts until the prior phase's exit criteria are met (exceptions noted).

---

## Phase 0a — Diagnostic Findings (completed 2026-09-01)

Live diagnostics run against the repo before any implementation; these
supersede several assumptions the original plan carried.

**Resolved — no action needed:**
- OpenRouter chain works end-to-end in the running bot: vault →
  inject_env → process env → council calls all verified (or-gemini-flash
  won round e48cfbe1; or-grok-4.3 judged it).
- DeepSeek "never seen" was visibility, not failure: `or-deepseek`
  proposed and was scored in that round. Nothing outside the council
  assigns DeepSeek; council internals surface nowhere in the UI (see
  agent-card task below).
- `available_models()` lists all 13 profiles regardless of key presence —
  the picker was never filtering DeepSeek out.

**Root-caused — fixes queued in Phase 0b:**
- **kimi-k3 judge abstentions**: K3 is always-on thinking (probe: 39
  completion tokens to answer "OK"; 36s on a 2.3K-token judge task).
  Real judge workloads (8–15K tokens) project to 90–180s+ against
  `COUNCIL_MEMBER_TIMEOUT_S = 120`. Every K3 judge call in round
  e48cfbe1 timed out; `asyncio.TimeoutError` stringifies empty, hence
  the blank abstain reasons. The codebase already acknowledges this
  failure class for plan drafting (`PLANNING_MEMBER_TIMEOUT_S = 300`)
  but never extended it to judging.
- Same mechanism [likely] explains "kimi called frequently, never
  finishes" in the upgrade loop, where kimi-k3 is the default planner.

**Data points banked:**
- Council round records already carry per-round prompt/completion token
  totals — a baseline cost source that exists before the shim lands.
- An economy model (gemini-flash, mean 7.43) won a real planner round.
  Frontier-for-planning is adopted as default (below) but stays a
  measurable prior: `retry_validated` per round is the ground-truth
  check, revisit after ~a month of rounds.
- Second silent-degradation bug this month with the same shape (KB vault
  before, dead judge now): components failing quietly while the system
  reports success. Visible-abstention UI (below) is the structural
  answer.

## Phase 0b — Immediate Fixes (before or alongside instrumentation)

1. Commit or stash the pre-existing uncommitted `agents.yaml` +
   `pipeline.py` changes — every diff below gets noisier until done.
2. **K3 timeout pair:**
   - `config/upgrade_models.yaml`, kimi-k3 profile: add
     `timeout_s: 240` with a dated comment citing round e48cfbe1.
   - `jarvis/council/council.py` line ~249: honor it —
     `effective = max(timeout_s, float(profile.get("timeout_s", 0)))`
     then `asyncio.wait_for(..., timeout=effective)`. `max()` so a
     profile can buy more rope, never less; the planning pathway's 300s
     floor is untouched.
   - Accepted trade: escalation rounds including K3 as judge can run
     ~4 min wall time. If councils ever enter the interactive loop,
     revisit by pulling K3 from the judge tier instead.
3. **Registry default flip:** `upgrade_models.yaml` `default: kimi-k3` →
   `default: claude-fable-5`, dated comment in house style. K3 stays in
   the registry and council; it stops being the default brain.

   **Blast radius (Rev 3, grep-confirmed):** `registry["default"]` is the
   final fallback for FOUR resolution paths, not one —
   `UpgradeAgent`/`AppBuildAgent` (the self-edit / app-build **edit
   loop**, via `JARVIS_UPGRADE_PROFILE`/`JARVIS_APPBUILD_PROFILE` →
   default), the planning pathway (`JARVIS_PLANNING_PROFILE` → default,
   `admin/server.py:644`), the site-research comparison writer
   (`admin/server.py:428`, same env), and the Edit-panel picker's initial
   selection. So this flip puts the *executor* loop on the most expensive
   profile in the registry until Phase 3 assigns it a Sonnet-class
   profile. That is accepted deliberately — quality-first while the
   ledger measures, exactly the "measure before down-tiering" order this
   plan is built on — with two conditions: (a) the executor rung IS
   measured from day one (the `upgrade_agent.py:469` patch is no longer
   deferred — see Phase 0 task 1), and (b) if `.env` already sets
   `JARVIS_UPGRADE_PROFILE` or `JARVIS_PLANNING_PROFILE`, those win over
   the default and this flip changes nothing for that path — check before
   assuming the flip took effect.
5. **Bind the model floor in config (pulled forward from Phase 3).**
   Policy first, measurement second — a floor is not something the eval
   ladder gets to discover.
   - `config/upgrade_models.yaml`: add the direct `claude-sonnet-5`
     profile (exact YAML in Phase 3) and delete `or-sonnet-5` in the same
     edit (identity-uniqueness test).
   - `config/agents.yaml`: `scheduler`, `librarian`, `analyst`, `systems`
     each gain `model_profile: claude-sonnet-5` and
     `on_profile_fallback: refuse`. `refuse`, not `warn`, deliberately:
     `warn` falls back to the voice model, which is Haiku, which is the
     one outcome the policy forbids — a floor that silently degrades is
     not a floor. Voice still boots on a fresh checkout with one key
     (the Supervisor never goes through this path); only delegations
     refuse, loudly, with the Agents-tab chip red. `developer` already
     sits above the floor (`claude-opus`, `refuse`).
   - Mechanical backstop, `tests/unit/test_model_floor.py`: every
     `sub_agents` entry declares a `model_profile`; the resolved
     profile's `model` string does not match `/haiku/i`; and
     `on_profile_fallback` is `refuse`. The Supervisor
     (`settings.openai_model`) is exempt by construction — it is not in
     `agents.yaml`.
   - Retire the two workflow drafts this replaces
     (`config/workflows/user-preference-model-defaults.yaml`,
     `user-preference-model-selection.yaml`) in the same commit — same
     rule as the units fact: once config binds it, a workflow that only
     persuades is dead weight, and under `MAX_INJECTED = 1` it can
     displace a workflow that still does something.
   - **Interpretation, stated so it can be vetoed in one line:** the
     floor is about AGENTS. The background maintenance rungs
     (`memory_merge`, `memory_classify`, `memory_extraction`,
     `kb_digest`, `procedures_describe`) are not agents — nobody
     delegates to them, they never speak to the user — and stay eligible
     for cheap/local models in Phases 3 and 5. If Larry means the floor
     to cover them too, delete this bullet and the Phase 5 local-model
     item narrows to the Supervisor alone.
   - Cost effect is expected and accepted: four agents move Haiku →
     Sonnet before the baseline is taken, so the baseline measures the
     policy-compliant system, not the one being retired. Patch the
     supervisor + base.py ledger sites first (checklist step 3) so the
     first Sonnet delegations are already recorded.
6. **Ledger on WAL from the first row** (moved here from "future work"):
   `council.py` and `upgrade_agent.py` write from the admin sidecar
   process; every other site writes from the bot process. Two writer
   processes exist from the first council round, so `usage_ledger._conn()`
   sets `journal_mode=WAL` + `busy_timeout` unconditionally and anchors
   `data/costs.db` to the repo root (not CWD — the two processes are
   launched by different scripts). Already in the Rev 3 `usage_ledger.py`.

---

## Phase 0 — Instrumentation & Baseline Evidence

**Goal:** Replace priors with measurements. Every later phase's savings claim gets verified against this baseline.

**Tasks**
1. **Usage-logging shim.** Thin wrapper at the LLM client factory: logs `ts, rung, provider, model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, reported_cost, session_id` per call to the cost ledger (see Cost Tracking design, separate doc/decision). **Rev 3: 13 call sites, not 11, and a closed rung vocabulary** (`usage_ledger.RUNGS`): the sidecar's own edit-loop completion (`upgrade_agent.py:469` → `selfedit_executor` / `appbuild_executor`, the "double-count" worry was a different-process misread) joins the set, and `council._call_profile` gains a `rung` kwarg so its four callers are labelled truthfully — `council` (escalations), `planning` (draft_candidates + single-mode author), `research` (site comparison). Without this, the entire planner/executor split in Phase 3 would have been invisible in the one report meant to justify it.
2. **OpenRouter activity puller.** Pull per-generation stats for the slice already routed through OpenRouter (model, native token counts, cost, cached_tokens, cache_discount). This settles cache-passthrough behavior for existing routed traffic without waiting on the shim.
3. **Provider console snapshot.** Record current-month Anthropic/OpenAI usage: input:output token ratio, per-model spend. One-time manual pull; establishes the input-dominance number.
4. **Rung frequency mining.** From Mortimer's existing structured logs: calls per session per rung (supervisor turns vs sweep/merge/extraction/council/developer). Denominator for sub-agent share of spend.
5. **Baseline report.** Analyzer joins 1–4: total spend/mo, input vs output share, per-rung share, prefix share of input (system+tools+memory block size vs total), cache hit status on routed calls.

**Assumptions under test**
- A1: input tokens are 70–85% of spend
- A2: majority of each input is repeated prefix
- A3: sub-agents are a meaningful share (~30%) of spend
- A5: prompt caching survives the OpenRouter path (cached_tokens > 0 on routed Claude/Gemini calls)

**Exit criteria:** one week of shim data; baseline report generated; A1/A2/A3/A5 each marked confirmed/refuted with numbers. **Rev 3.2 exception (Larry, 2026-09-01):** Phase 1 starts before this week is up (the kind of exception line 9 allows for); Phases 2–5 still wait for it. Instrumentation itself is complete (all 9 readiness steps, 55afe06..2636cd5).

**Quick win allowed during Phase 0:** run Graphify on the repo and wire the output into the developer agent's context. Zero integration risk, independent of everything else.

---

## Phase 1 — Prompt Caching (Rev 3.2 rewrite, 2026-09-01)

**Goal:** Stop paying full price for the repeated prefix. Projected: largest single lever (prior: 45–65% of total bill; replace with Phase 0 numbers). **Larry, 2026-09-01: starts NOW, ahead of the one-week baseline** — the baseline's "before" column is forfeited on purpose (spend is already ≥$10/day on limited use); Phase 0's ledger still measures the "after", and `cost_report.py`'s cache columns are the proof the lever works at all.

**Why this section was rewritten (the limitation Rev 3.1 missed).** Every Anthropic call in this repo goes through the OpenAI SDK against `https://api.anthropic.com/v1/` — the Supervisor via pipecat's `OpenAILLMService` (`jarvis/bot/pipeline.py:532`), the five sub-agents via `AsyncOpenAI` (`jarvis/agents/base.py:220,246,250`), the executor via `OpenAI` (`jarvis/agents/upgrade_agent.py:388`), council/planning/research via `OpenAI` (`jarvis/council/council.py:225`). Anthropic's OpenAI-compatibility docs state flatly: **prompt caching is not supported through that layer** (and `reasoning_effort` is ignored; `thinking` passes only via `extra_body`). This is the documented cause of the readiness-checklist step-4 finding (`prompt_tokens_details=null`, commit 607588b). Rev 3.1's Phase 1 tasks 1–2 ("reorder assembly, insert breakpoints") therefore cannot work as written: there is nothing in the compat request that carries a breakpoint. **Caching requires the native Messages API on every Anthropic-direct call site.** That is a client-library change, not a prompt change, and it is scoped below so it lands in two independently revertible pieces.

**Facts this design rests on (platform.claude.com, fetched 2026-09-01 — re-check before landing, they move):**
- Minimum cacheable prefix: **Haiku 4.5 = 4,096 tokens**; Sonnet 5 = 1,024; Opus 5 = 512; Fable 5 = 512. Below the minimum the request is accepted and *nothing is cached, silently*.
- Cache hierarchy `tools → system → messages`; a breakpoint caches everything before it. Max 4 breakpoints per request; the request-level `cache_control={"type":"ephemeral"}` ("automatic caching") uses one slot and moves forward each turn. Reads look back ≤20 blocks for an entry a *prior request wrote at a breakpoint* — a prefix that never had a breakpoint on it is never a hit, which is why the shim below puts an explicit marker on the stable system block, not just at the end.
- TTL 5 min (write 1.25×, read 0.10×) or 1 h (write 2.0×, read 0.10×); every read refreshes the TTL free. `config/model_prices.yaml` already carries 1.25/0.10 for the four `anthropic/*` rows — nothing to add.
- Usage fields: `input_tokens` (UNCACHED only), `cache_creation_input_tokens`, `cache_read_input_tokens`. Total input = the three summed.
- Invalidation: any change to tools invalidates everything; system change invalidates system+messages; `output_config.effort` or `thinking` changes always invalidate the messages cache (Phase 1b rule is now a documented requirement, see below).
- The repo's Supervisor system prompt is assembled ONCE per pipeline (`pipeline.py:470-489`: `SUPERVISOR_PROMPT` + addenda + `render_memory_context()`), never per turn, and nothing time-varying is in it (the greeting time at `pipeline.py:940` is a *user* message) — so the Supervisor prefix is session-stable as-is. Rev 3.1 task 1 (reorder) is unnecessary for the Supervisor; it applies to the sub-agent loop only in the sense fixed by shim rule S2 below.

**Estimated Supervisor prefix (grep-measured 2026-09-01, [likely] ±25%):** GOLDEN_RULES ~150 + SUPERVISOR body ~1,900 + VOICE/UI/SCREEN/HANDOFF addenda ~720 + memory context ≤2,000 (`MAX_CONTEXT_CHARS=8000`) + agent/voice catalogs ~300 + tool schemas ~1,500–2,000 ⇒ **~5–7k tokens, above Haiku's 4,096 floor but not by a wide margin.** Task 6's gate measures it for real; if `cache_creation_input_tokens` is 0 on turn 1 the prefix is under the floor and caching starts only once history pushes past it — acceptable, but the plan must *know*, not assume.

### Design — two paths, one kill switch

| Path | Call sites | Mechanism | Revert |
|---|---|---|---|
| **A — Supervisor** | `jarvis/bot/pipeline.py` LLM service block (lines 512–536) | pipecat's native `AnthropicLLMService` (`pipecat/services/anthropic/llm.py`, already installed with 1.4.0; needs the `anthropic` package), `enable_prompt_caching=True`. Its adapter puts `cache_control` on the last TWO user messages (write current turn, look up previous) — the standard moving-window pattern. Universal `LLMContext`/`LLMContextAggregatorPair`/`ToolsSchema` that pipeline.py already uses are the service-agnostic types this service consumes; `register_function`/`adapt_to_pipecat` are generic `LLMService` API. Same shape as the existing Gemini branch two lines above it. | `JARVIS_ANTHROPIC_NATIVE=0` |
| **B — everything else Anthropic-direct** | `jarvis/agents/base.py` (sub-agents), `jarvis/agents/upgrade_agent.py` (executor), `jarvis/council/council.py` (council/planning/research) | New `jarvis/llm_client.py` factory + `jarvis/anthropic_shim.py`: a drop-in object exposing the OpenAI surface these loops already use (`.chat.completions.create(...)` → `openai.types.chat.ChatCompletion`, `.base_url`), translating to/from the native Messages API. The loops, the trust/draft/D3 logic, and every test that scripts `chat.completions.create` stay untouched. | `JARVIS_ANTHROPIC_NATIVE=0` |

`JARVIS_ANTHROPIC_NATIVE`: unset or `"1"` → native on both paths; `"0"` → today's compat path everywhere. One variable, read at client construction, so rollback is a `.env` edit and a restart, never a code change. Both paths key on the route, never on the model string: Path A on `"api.anthropic.com" in settings.openai_base_url`, Path B on `profile["provider"] == "anthropic"` (every profile in `config/upgrade_models.yaml` declares `provider:`; `provider_from_base_url()` is the fallback for the settings client).

**Out of scope, deliberately:** background rungs (`jarvis/memory.py:864`, `memory_sweep.py:352,646`, `kb_digest.py:113`, `procedures.py:358`) and the text-CLI `agents/supervisor.py:69` stay on compat — they run on the Supervisor's Haiku settings with prompts under the 4,096 floor, one-shot, no history; nothing to cache. Revisit in Phase 5 with the rest of the background tier. Non-Anthropic providers: Moonshot direct is automatic caching (nothing to send; task 5 verifies the usage field lands); OpenRouter is task 4.

### Tasks

1. **Dependency.** `requirements.txt`: `pipecat-ai[deepgram,elevenlabs,openai,google,silero,mcp,runner,webrtc,anthropic]` — the extra installs `anthropic`, which both paths import. Regenerate `requirements-lock.txt` the same way it was last generated. `python -c "import anthropic, pipecat.services.anthropic"` is the check.

2. **`jarvis/anthropic_shim.py` (new)** — `AnthropicChatShim(api_key, base_url, *, timeout=None, max_retries=None)` and `AsyncAnthropicChatShim(...)`, each with `.chat.completions.create(...)` and `.base_url` (the string passed in, so `provider_from_base_url()` and every existing `str(client.base_url)` caller keep working). Wraps `anthropic.Anthropic`/`AsyncAnthropic(api_key=, timeout=, max_retries=)` — note `max_retries=0` must pass through: `upgrade_agent.py:388-393` depends on it. Translation rules, each a unit test in `tests/unit/test_anthropic_shim.py` (fixtures only, no network):
   - **S1 tools:** OpenAI `{"type":"function","function":{name,description,parameters}}` → `{name, description, input_schema: parameters}`. `tool_choice`: not used by any call site (grep-confirmed) → raise `NotImplementedError` if passed, so a future caller finds out at the call, not in a silent miss.
   - **S2 system:** the LEADING run of `role: system` messages becomes the top-level `system` list, one `{"type":"text","text":…}` block per message in order. `cache_control: {"type":"ephemeral"}` goes on the **first** block (the agent's base prompt — `_system_prompt_for()` in base.py, `self._system_prompt` in upgrade_agent.py, `system_prompt` in council.py — stable per agent per boot) — NOT on the last, because blocks 2..n are the per-task procedure/skill/workflow injections (`base.py:511-555`) that differ run to run. This is the cross-run hit; the request-level `cache_control` (S6) is the within-run hit.
   - **S3 mid-conversation system messages** (`base.py:694,702`, `upgrade_agent.py:567,606` — the D3 constraint, `PENDING_DRAFT_CONSTRAINT`, executor notes): Sonnet 5 rejects `role: system` inside `messages` (only Fable 5/Opus 5/Opus 4.8 accept it). Rule: a non-leading system message becomes a text block appended to the *preceding* user message when one is adjacent (the tool-result turn — Anthropic allows text blocks after `tool_result` blocks), else a new user message; text unchanged, no prefix added. Consecutive same-role messages are merged into one message (strict user/assistant alternation is required).
   - **S4 tool calls:** assistant `tool_calls[i]` → `tool_use{id, name, input=json.loads(arguments)}` block (plus a text block if `content` is non-empty, text first); `role: tool` → `tool_result{tool_use_id, content}` block; consecutive tool messages merge into one user message. Reverse on the way out: `tool_use` block → `ChatCompletionMessageToolCall(id, type="function", function={name, arguments=json.dumps(input)})`, so `_assistant_message(message)` (`base.py`) and the executor's `for tc in tool_calls` loop see exactly what they see today.
   - **S5 response:** `ChatCompletion(id=msg.id, model=msg.model, created=now, object="chat.completion", choices=[Choice(index=0, message=ChatCompletionMessage(role="assistant", content=<joined text blocks or None>, tool_calls=<S4 or None>), finish_reason=<end_turn→"stop", tool_use→"tool_calls", max_tokens→"length", else "stop">)], usage=<S7>)`. `max_tokens` is required natively: default **8192**, overridable by a `max_tokens=` kwarg.
   - **S6 request-level cache_control:** every request also sends `cache_control={"type":"ephemeral"}` (automatic caching, one breakpoint slot) so each loop iteration reads the previous iteration's prefix. Two breakpoints total (S2 + S6) of the four allowed. `ttl: "1h"` is NOT used anywhere in Phase 1 — 2.0× writes only pay off when the same prefix is idle >5 min between reads, and the executor/sub-agent loops iterate in seconds; revisit with `cost_report.py` data, not a guess.
   - **S7 usage (OpenAI-inclusive semantics, so `record_completion` needs one small fix, task 3, and no new shape):** `prompt_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens`; `completion_tokens = output_tokens`; `prompt_tokens_details = PromptTokensDetails(cached_tokens=cache_read_input_tokens)`; plus `usage.cache_creation_input_tokens = <n>` set as an extra attribute (`openai` pydantic models are `extra="allow"`, `.venv/.../openai/_models.py:129`), which `usage_ledger._CACHE_WRITE_ALIASES` already reads.
   - **S8 passthrough:** `temperature` (council/executor profiles set it), `extra_body` (Phase 1b merges `output_config` from here — top-level fields of the native request), `max_tokens`. `stream=True` → `NotImplementedError` (no Path-B caller streams). Unknown kwargs → `TypeError`, never dropped.
   - **S9 errors:** `anthropic.APITimeoutError` → `openai.APITimeoutError(request=exc.request)`; `anthropic.APIConnectionError` → `openai.APIConnectionError(message=str(exc), request=exc.request)`; `anthropic.APIStatusError` → `openai.APIStatusError(str(exc), response=exc.response, body=exc.body)` (carries `status_code`). This is load-bearing: `upgrade_agent.py:416-421` classifies failover on exactly those three `openai` classes and must keep seeing them.

3. **`jarvis/usage_ledger.py`** — two lines, both latent bugs that go live the moment any cache write is reported: (a) `record_completion` line 303: `input_tokens=max(prompt - cached - cache_write, 0)` (today it subtracts only reads, so every cache-write token would be billed at 1.25× AND 1.0×; `compute_cost`'s docstring already defines `input_tokens` as UNCACHED); (b) add `("prompt_tokens_details", "cache_write_tokens")` to `_CACHE_WRITE_ALIASES` — OpenRouter's field name for the same thing (task 4). Unit test: a fake usage with reads+writes yields the right three columns.

4. **OpenRouter-routed Anthropic (`openrouter/anthropic/*` profiles) — the only compat-path caching that exists.** OpenRouter documents `cache_control` passthrough for Anthropic models in OpenAI format, including request-level automatic mode. In `jarvis/llm_client.py` (task 5) the compat client for `provider == "openrouter"` is wrapped so that when `model.startswith("anthropic/")` the request gets `extra_body={"cache_control": {"type": "ephemeral"}}` merged in. Reported back as `usage.prompt_tokens_details.cached_tokens` / `.cache_write_tokens` (hence 3b). **A5 stays a measurement:** `scripts/pull_openrouter_activity.py` already prints the verdict once ≥10 routed calls have `reported_cost`; if reads stay at zero there, those profiles move to the native key per Rev 3.1 task 5 (unchanged). Sticky sessions (Rev 3.1 task 3) are dropped: irrelevant natively (cache is per-workspace, not per-connection) and unverifiable through OpenRouter's routing.

5. **`jarvis/llm_client.py` (new) + the three call sites.**
   - `make_async_client(*, api_key, base_url, provider, model=None, timeout=None, max_retries=None)` and `make_sync_client(...)`. `native_enabled()` reads `JARVIS_ANTHROPIC_NATIVE` (default on). Returns `AsyncAnthropicChatShim` / `AnthropicChatShim` when `provider == "anthropic"` and native is on; `openai.AsyncOpenAI` / `openai.OpenAI` otherwise (task-4 wrapper for openrouter). It calls `openai.AsyncOpenAI(...)` as an *attribute lookup on the module* so `tests/unit/test_upgrade_agent.py:169-174` (patches `openai.OpenAI`) keeps working unchanged.
   - `jarvis/agents/base.py:220,246,250` → `llm_client.make_async_client(api_key=…, base_url=…, provider=profile.get("provider") or provider_from_base_url(base_url))`. The `client_factory` seam is untouched. `tests/unit/test_subagent.py:717-745` patches `base_module.AsyncOpenAI`, which no longer exists after this edit: change that fixture to `monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)` **and** `monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")` (the override profile it uses is Anthropic — with native on it would rightly build a shim). Add the mirror test: same setup with native on asserts `isinstance(agent_override_client, AsyncAnthropicChatShim)`.
   - `jarvis/agents/upgrade_agent.py:373-393` `_build_client(api_key_env, base_url)` gains a third, optional parameter `provider: str | None = None` (falls back to `provider_from_base_url(base_url)`, already imported at line 52) and returns `llm_client.make_sync_client(api_key=os.environ[api_key_env], base_url=base_url, provider=provider, timeout=PLANNER_CALL_TIMEOUT_S, max_retries=0)`. Both callers (`:370-371` boot, `:508-509` failover) pass `self.cfg.get("provider")` — `self.cfg` is the resolved profile dict. Optional keeps `tests/unit/test_upgrade_agent.py:172`'s two-argument call valid.
   - `jarvis/council/council.py:219-225` → `llm_client.make_sync_client(api_key=api_key, base_url=profile.get("base_url"), provider=profile.get("provider"))`. Nothing else in `_sync_call` changes; `record_completion` keeps reading `str(client.base_url)`.
   - Moonshot direct (`provider == "moonshot"`): compat client unchanged; its caching is automatic server-side. The `cached_tokens` alias already in `_CACHED_TOKEN_ALIASES` is the check — one kimi-k3 council call with `JARVIS_DEBUG_USAGE_LEDGER=1` after this lands tells whether the field arrives.

6. **`jarvis/bot/pipeline.py` — Path A.** Between the Gemini branch and the `else` at line 531:
   ```python
   elif "api.anthropic.com" in (settings.openai_base_url or "") and native_enabled():
       from pipecat.services.anthropic.llm import AnthropicLLMService
       llm = AnthropicLLMService(
           api_key=settings.openai_api_key,
           settings=AnthropicLLMService.Settings(
               model=settings.openai_model,
               enable_prompt_caching=True,
           ),
       )
       _logger.info("supervisor_llm_service service=anthropic model=%s prompt_caching=on", settings.openai_model)
   ```
   Lazy import for the same reason the Google branch is lazy. Module docstring line 8 (`-> OpenAILLMService`) gains the third route. `tests/integration/test_bot_wiring.py:102` and `tests/unit/test_speaker_gate.py:563` patch `bp.OpenAILLMService` with a fake — they run with the test Settings' default `openai_base_url` (not Anthropic), so they still take the `else` branch; add one wiring test that sets an Anthropic base URL and asserts the Anthropic service class is constructed with `enable_prompt_caching=True`, and one with `JARVIS_ANTHROPIC_NATIVE=0` asserting `OpenAILLMService`. `thinking` stays `NOT_GIVEN` (off) — latency is the Supervisor's constraint; `max_tokens` keeps the service default 4096.

7. **`jarvis/bot/usage_watcher.py`** — the Anthropic service reports `LLMTokenUsage.prompt_tokens` = native `input_tokens` = **uncached only**, and sets `cache_creation_input_tokens` (an int), whereas `OpenAILLMService` leaves it `None` (`pipecat/services/openai/base_llm.py:460-466`). Today's line 127 (`input_tokens = prompt_tokens - cached`) would double-subtract under Path A. Rule: `if tokens.cache_creation_input_tokens is None:` OpenAI semantics (current code) `else:` `input_tokens=tokens.prompt_tokens, cache_write_tokens=tokens.cache_creation_input_tokens, cache_read_tokens=tokens.cache_read_input_tokens or 0`. The module docstring's KNOWN GAP paragraph (lines 29-40) is now half-true — rewrite it: the gap remains on the compat path, and is closed on the native path. Unit test both branches.

8. **Verification gate — nothing is "done" on config; caching failures are silent by default.** Rewrite `scripts/test_prompt_caching.py` (the Phase 0 diagnostic) to use `jarvis.llm_client.make_async_client(...)` with the real settings and print, for two back-to-back identical-prefix calls: `cache_creation_input_tokens` (turn 1 > 0 proves the prefix cleared the model's floor) and `cache_read_input_tokens` (turn 2 ≈ turn-1 creation proves the hit). Run it once per model actually in use: `claude-haiku-4-5` (Supervisor, 4,096 floor — this is the one that can legitimately come back 0/0 on a small test prompt; the script's filler must exceed 4,096 tokens, not 1,024 as today), `claude-sonnet-5`, `claude-fable-5`. Then live: one voice session of ≥3 turns with `JARVIS_DEBUG_USAGE_LEDGER=1`; `scripts/cost_report.py` must show `cache_read > 0` on `supervisor` rows from turn 2 on, and on `analyst`/`developer` rows after any multi-iteration run. **Alert on cold sessions:** `usage_watcher.py` logs `supervisor_cache_cold turn=N prompt_tokens=…` at WARNING when turn ≥2 of a session reports `cache_read_input_tokens == 0` under Path A — the one log line that turns a silent miss into a visible one.

**Landing order (each its own commit, Larry runs git):** (i) tasks 1+2+3 with unit tests — no live behaviour changes yet, the shim is unused; (ii) task 5 + 4 (Path B live) → gate 8 for sub-agents/council; (iii) tasks 6+7 (Path A live) → gate 8 for the Supervisor, then one normal day of use before calling it done. If (iii) misbehaves in any way that isn't obviously the caching, `JARVIS_ANTHROPIC_NATIVE=0` and report — do not debug the voice path under time pressure.

**Non-goals (unchanged):** do not slim or reword the stable cached block — it costs ~10% of base once cached; capability risk isn't worth pennies. Do not touch the routing eval or the Supervisor prompt text.

**Exit criteria:** `cost_report.py` shows cache reads on >80% of `supervisor` rows in-session (turn ≥2) and on every multi-iteration sub-agent/executor run; `pytest tests/unit -q` green (the pre-existing `test_validate_runs_pytest_gate_and_passes` excepted); measured input-cost reduction reported as $/day against the first week of Phase 0 data that exists (partial baseline, stated as such in the Savings Ledger).

## Phase 1b — Effort Control (added 2026-09-01; Rev 3.2: gate mostly resolved by documentation)

**Goal:** Stop paying default-high adaptive-thinking depth on rungs that don't need it. Claude 5-class models think adaptively at `effort=high` by default, thinking tokens bill as output tokens, and none of the call sites sets effort.

**What Rev 3.2 settles (platform.claude.com, 2026-09-01):**
- The parameter is `output_config: {"effort": "low"|"medium"|"high"|"xhigh"|"max"}`, top-level, Messages API, no beta header. Default `high` everywhere; sending `high` equals omitting it.
- Supported: Sonnet 5, Opus 5, Fable 5 (all agents and council members on Anthropic). **Not listed for Haiku 4.5 — the Supervisor never sends it** (a 400 on the voice path is the one failure mode we cannot afford to discover live).
- Through the compat layer `reasoning_effort` is **ignored** — so effort only exists on the native path (Phase 1 Path B) or through OpenRouter for OpenAI-family models. Rev 3.1's "key shape is inferred" caveat is closed: the shape is documented; what the draft `effort.py` emits for `_ANTHROPIC_STYLE` (`{"output_config": {"effort": level}}`) is correct and the shim merges `extra_body` into the native request (S8).
- **Cache rule is now a requirement, not a safe default:** changing `output_config.effort` between requests invalidates the messages cache (documented). Static per rung, period. Per-message effort (beta, Fable 5.1/Opus 5 only) is out of scope.

**Tasks**
1. Land `jarvis/effort.py` from the Rev 3 draft with its docstring rewritten to the facts above, plus one guard: `extra_body_for(rung, provider, explicit=None, model=None)` returns `{}` when `provider == "anthropic"` and `"haiku" in (model or "").lower()`.
2. `effort:` in `config/agents.yaml` per sub-agent; `effort:` per `upgrade_models.yaml` profile is allowed but not required. Starting values: `low` scheduler/systems; `medium` librarian/analyst; unset (provider default) developer, executor, and council frontier members. Background rungs stay unset (compat path — the field would be ignored anyway).
3. Wire `extra_body_for()` at the Path-B call sites only (`base.py:577`, `upgrade_agent.py:470`, `council.py:236`) — passed as `extra_body=` exactly as the draft's docstring shows. The Supervisor gets nothing (Haiku).
4. **Gate, one session, before any `JARVIS_EFFORT_*` is set broadly:** one `analyst` run at `low` — no 400, `cost_report.py` output tokens visibly lower than the same task at default. (The effort↔cache half of Rev 3.1's gate is answered by the docs; no toggle test needed — the rule is simply never to toggle.)

**Exit criteria:** effort set on scheduler/systems/librarian/analyst; no 400s; measured output-token reduction on those rungs vs their first-week rows; cache hit rate on those rungs unaffected (static effort cannot move it).

---

## Phase 2 — Memory Write-Path Redesign (Extraction Gate)

**Goal:** Stop treating every utterance as memory. Shrink the candidate pool at the source; make the sweep a janitor, not a load-bearing component.

**Design (agreed):** the unit of memory is the *fact*, not the utterance. No inline gate on the latency path.

**Tasks**
1. **Async post-turn extraction worker.** New service (Procfile entry now, launchd later). Consumes finished exchanges (utterance + Mortimer's response + any user correction); emits zero-to-N structured candidates: `content, tier, entities[], provenance(stated|inferred), source_turn`.
2. Commands flow through the same pass — embedded durables ("Mom's birthday June 3") extract even when the command path already executed. Chitchat/queries yield empty lists; the empty list *is* the classification.
3. **Novelty gate at admission.** Candidate's entities matched against the store before write; duplicates increment a recurrence counter on the existing fact instead of inserting.
4. **Staging + promotion.** Identity/people/projects/policies: admit on first mention. Tastes/passing mentions: staging tier; promote on second occurrence; expire unrepeated after N days.
5. Extractor model: start on a cheap tier (candidate for Phase 3 eval); judged on JSON-schema adherence and precision, not fluency.

**Exit criteria:** preference-tier growth rate flattened; sweep merge rung firing rarely; no observed loss of facts Larry actually stated (spot-check via librarian session).

---

## Phase 3 — Model Routing & Down-Tiering

**Goal:** Cheapest model per rung that clears the quality bar. Provider chosen by feature dependency, not loyalty.

**Developer work gets a specific strategy (decided 2026-09-01, made concrete in Rev 3): planner/executor split — mapped onto the THREE mechanisms that already exist, no new agent.**

Rev 2 said "planner" and "executor" without naming which code they were.
The repo already has three distinct things a model does on developer
work, each with its own model-resolution path, and the split is a
*reassignment of those three*, not a fourth:

| Role | Existing mechanism | Process | Model comes from | Phase 3 assignment |
|---|---|---|---|---|
| **Planner** | planning pathway — `POST /api/plan/start`, `council.draft_candidates`, single-mode `PLAN_AUTHOR_PROMPT`; plus E1 escalation rounds (`placement="planner"`) | sidecar | `JARVIS_PLANNING_PROFILE` → registry `default` | **frontier** (default = `claude-fable-5` after Phase 0b) |
| **Executor** | `UpgradeAgent` / `AppBuildAgent` edit loop (`upgrade_agent.py`, `run()` → propose/validate/submit) | sidecar | `JARVIS_UPGRADE_PROFILE` / `JARVIS_APPBUILD_PROFILE` → registry `default` | **`claude-sonnet-5` direct** (new profile, below) — set via the two env vars, **not** by changing `default` |
| **Dispatcher + small edits** | `developer` SubAgent (`config/agents.yaml`, `model_profile: claude-opus` today) — reads, investigations, dictated single-file `repo_write_file` edits, and *launching* `plan_start`/`selfedit_start`/`app_build_start` | bot | `agents.yaml` `model_profile` | stays `claude-opus` through baseline; eval-ladder candidate for `claude-sonnet-5` — the floor, not below it — like every other agent — it is by construction the "single-file, non-design-bearing" executor, since those edits already happen inside it |

Consequences that fall out of the table:
- **The developer SubAgent is NOT split in two.** Supervisor routing is
  untouched, the routing eval is untouched, and "plan-first vs
  execute-directly" is already the developer prompt's own rule
  (`DEVELOPER_CORE` routes multi-file work to `selfedit_start`, small
  dictated edits to `repo_write_file`). Phase 3 changes which *model*
  sits at each of the three seats, not the seats.
- **Executor selection is env, not `default`.** Setting
  `JARVIS_UPGRADE_PROFILE=claude-sonnet-5` and
  `JARVIS_APPBUILD_PROFILE=claude-sonnet-5` leaves `default` free to keep
  meaning "planning-quality", which is what the planning pathway and the
  research writer fall through to. Changing `default` to Sonnet instead
  would silently down-tier plan authoring too.
- **Planner round-one membership.** Two code changes, both in
  `jarvis/council/`: (1) `draft_candidates` gets a config constant
  `PLANNING_DEFAULT_PROPOSER_TIERS = ["frontier"]` used when the caller
  passes no `members` (today it fans out to *all 13* key-present
  profiles — the voice `plan_start` path never passes `members`, so every
  spoken plan request currently buys 13 drafts; the console picker can
  still widen it explicitly); judges stay "whatever usable profiles are
  not proposing", unchanged. (2) `UpgradeAgent._maybe_escalate` starts
  `placement="planner"` rounds at **tier 2** (`COUNCIL_PLANNER_START_TIER
  = 2` in `council/config.py`; scope rounds stay tier 1). With
  `COUNCIL_MAX_ESCALATIONS = 2` and the "tiers strictly ascending, never
  repeating" invariant, that means a planner-placement escalation happens
  **once** per run; a second failure ends the session as a third failure
  does today. [likely] That is the right trade: a frontier council that
  already failed once is not fixed by reconvening the same frontier
  council, and under the split the thing that failed validation is the
  executor's rendering of a plan — the recovery is a human re-plan, not
  a second identical round. If a month of `retry_validated` data says
  otherwise, it is a one-constant change to allow a tier-2 repeat.
- **Preferred proposers:** `claude-fable-5` + `or-deepseek-v4-pro`
  (both `tier: frontier` in the registry today); third-lineage judge
  drawn by the existing partition (`or-grok-4.6` frontier, or
  `or-gpt-5.1` mid via the V8 backfill). The identity-uniqueness rule
  already prevents self-judging. For self-edits, user choice via
  `draft_candidates → record_user_choice` remains the preferred judge.
- **Executor profile — swap, no backfill needed.** Add to
  `config/upgrade_models.yaml`:
  ```yaml
  - name: claude-sonnet-5
    label: "Claude Sonnet 5 — direct Anthropic; the executor tier"
    provider: anthropic
    model: claude-sonnet-5
    identity: anthropic/claude-sonnet-5
    base_url: https://api.anthropic.com/v1/
    api_key_env: ANTHROPIC_API_KEY
    temperature: null      # D-003; same family that rejects it on opus
    tier: mid
  ```
  and **delete** `or-sonnet-5` in the same edit — same `identity`, so
  `tests/unit/test_model_registry.py` fails if both exist. Rev 2's
  "backfill the lost mid-tier judge slot" is withdrawn: the identity AND
  the tier are preserved (both `mid`), only the route changes, so the
  mid judge pool is exactly as deep after the swap as before. Registry
  rule honoured: a model reachable directly does not keep an OpenRouter
  route.
- **The executor's escalation rule is load-bearing.** The invariant is
  NOT "the spec is complete" — no spec is. It is: all irreversible /
  architectural decisions live in the plan, and when reality diverges
  from the spec the executor **stops and reports, never bridges the
  gap.** That paragraph goes into `UpgradeAgent`'s system prompt
  (`jarvis/prompts.py`, the single source of truth) and is injected
  only when a `plan`/`plan_path` was supplied — an unplanned single-file
  self-edit has nothing to diverge from.
- **Spec requirements** for executability (enforced by
  `PLAN_AUTHOR_PROMPT`, not by the executor): exact files/functions
  with signatures, data shapes at boundaries, mechanical acceptance
  criteria (feeds the existing validation gates), explicit non-goals,
  named divergence triggers.
- **Effort alignment (Phase 1b):** planning rung high/max; executor
  rungs medium/low — the spec already did the thinking; developer
  SubAgent per the eval ladder.
- **Instrument escalation rate from day one.** Chronic escalations mean
  under-specified plans (a planner-prompt problem), which looks
  identical to executor incapability unless measured. Two ground truths,
  both already recorded: `retry_validated` per round (did a high-scoring
  plan actually execute clean) and the ledger's `selfedit_executor` /
  `appbuild_executor` rows per run (how much executor spend a plan
  consumed before it landed or died).

**Tasks (all rungs) — under the model floor.** For the five specialists
and the planner/executor seats the ladder is **frontier → Sonnet-class**
and stops there; the "small open-weight" step below applies only to the
Supervisor (Phase 5 local) and the background maintenance rungs.
1. **Per-rung eval sets.** 20–50 real examples per rung mined from logs: utterance→intent, exchange→extracted facts, fact-pair→merge/don't. 
2. **Capability ladder.** Run frontier → mid-tier → small open-weight per rung (simple harness or promptfoo). Pick cheapest passing model; record next tier up as fallback.
3. **Routing config in `agents.yaml`** (commit the pending changes first): per-rung `model, provider, fallback`. Routing changes become config edits, not code changes.
4. **Provider balance rules:**
   - Needs caching or batch → native key (supervisor; async rungs headed to batch).
   - Cheap open-weight models → OpenRouter credits (fee is noise at that price tier).
   - Frontier calls needing neither → OpenRouter BYOK or native; default OpenRouter for failover, native key stays in vault as escape hatch.
5. Priors to test, not trust: intent/entity-matching solved by 1–8B class (Supervisor-local and background rungs only — never an agent); extraction is mid-tier; developer agent stays frontier for planning, Sonnet for execution; council placed by eval within its tier rules.

**Exit criteria:** every rung has an eval-backed model assignment in agents.yaml, none below the floor for an agent (`test_model_floor.py` green); measured agent spend reduction vs baseline coming from caching/effort/context, not tier; zero quality regressions on eval sets.

---

## Interface Task (parallel track, any time after Phase 0b) — Council Roster on the Agent Card

Decided 2026-09-01. Every council round record already carries proposer
profiles, judge profiles, per-judge scores, abstain reasons, winner, mean,
and token totals (`get_round()` returns all of it) — this is a surfacing
task, not a data task.

- Primary chip stays the WINNER's resolved profile (preserves the
  model-discipline rule: the chip names what actually proceeds).
- Below it, a compact roster: proposers with mean scores (winner
  highlighted), judges listed separately, and abstentions VISIBLE with
  reasons — `kimi-k3 ✗ (judge failed)` four times on last night's card
  would have surfaced the timeout bug at a glance. Silent pool
  degradation is the same failure class the launcher work fixed for
  services.
- Round token totals on the card — council card and cost card converge
  on the same numbers.
- Implementation shape: small endpoint over list_rounds/get_round (or
  the existing admin API if rounds are exposed there) + one SwiftUI
  view. Well-bounded, visual, low-risk — a good first task for the
  planner/executor loop itself once Phase 0b + the cost shim land.

## Phase 4 — Context Slimming via Graph Memory

**Goal:** Replace the flat char-budget memory dump (currently 8K chars every turn, full price) with retrieval of only the relevant subgraph. Fixes the near-duplicate blindness structurally.

**Design (Graphify pattern, not the package):** entity-anchored store — facts attach to entity nodes with typed edges and provenance tags (stated/inferred). Token-overlap near-dupes ("dark roast" / "dark coffee") become structurally visible as same-node attachments.

**Tasks**
1. Migrate memory store to entities + edges + provenance (NetworkX + existing vault-backed storage; refactor of memory.py, no new dependency service).
2. Context builder v2: traverse from entities in the current utterance (+ always-on core: identity, standing policies) instead of top-N-by-tier truncation. Hard token budget retained as a ceiling, not the selection mechanism.
3. Phase 2's novelty gate re-pointed at the graph (entity match becomes a node lookup).
4. Keep the volatile memory block **after** the cache breakpoint (it varies per turn by design).

**Exit criteria:** average memory-context tokens per turn reduced ≥50% vs the 8K-char dump with no observed recall failures over a week of use.

**Dependency note:** benefits from Phase 2 being done (clean candidates in, clean graph out), but can start once the extraction worker's entity field is stable.

---

## Phase 5 — Batch, Mac mini, Local Endgame

**Goal:** Squeeze the async tail and align with the hosting migration.

**Tasks**
1. Move latency-insensitive rungs (memory sweep, consolidation, staging promotion review) to native Batch APIs — flat ~50% off those calls. (Not available via OpenRouter; these rungs sit on native keys per Phase 3 rules.)
2. Services → launchd agents on the Mac mini; vault injection verified under launchd (shell-rc env vars do not survive — all keys in vault per standing policy).
3. Local model serving for the rungs the Phase 3 eval showed are small-model-solvable — the Supervisor (intent/dispatch; Larry's stated near-term goal) and background rungs (entity match, possibly extraction). Bill for those → $0. An AGENT moves local only if a local model is demonstrably Sonnet-equivalent on that agent's eval set (plausible for large open-weight models on the Mac mini; not assumed) — the floor applies to local models exactly as to hosted ones.
4. Re-run the Phase 0 analyzer monthly; costs regress silently otherwise.

**Exit criteria:** async rungs on batch or local; monthly cost report trending; total reduction vs Phase 0 baseline reported.

---

## Risks & Watch Items

- **Silent cache failure** (Phase 1): the most expensive quiet bug available — and Rev 3.2 found the whole compat path was one (no request could ever carry a breakpoint). Mitigated by task 8's gate, the `supervisor_cache_cold` WARNING, and `cost_report.py`'s cache columns; never assume from config.
- **Native-client migration touches the live voice path** (Phase 1 Path A): lands last, alone, behind `JARVIS_ANTHROPIC_NATIVE`; any voice regression → flag to 0 and report, no live debugging.
- **Haiku 4.5's 4,096-token cache floor** (Phase 1): a Supervisor prefix that shrinks (memory context emptied, addenda disabled) can drop below it and caching silently stops. `cost_report.py` cache columns on `supervisor` rows are the watch.
- **Extraction over-admission** (Phase 2): a sloppy extractor recreates the bloat one layer down. Precision-weighted eval; staging tier absorbs mistakes.
- **Eval set too small/stale** (Phase 3): 20 examples can flatter a small model. Refresh sets from live logs before any tier demotion of a user-facing rung.
- **Graph migration data loss** (Phase 4): migrate additively — old store read-only until the graph passes a week of parallel operation.
- **agents.yaml + pipeline.py uncommitted changes**: commit or revert before Phase 3 touches routing config. Unreviewed diffs under a refactor is how regressions hide.

## Savings Ledger (fill from measurements)

| Lever | Prior (unvalidated) | Measured baseline share | Measured after | 
|---|---|---|---|
| Caching stable prefix (Rev 3.2: native SDK, Phase 1 pulled ahead of the baseline) | 45–65% of total | partial — Phase 0 rows at landing, days not a week | — |
| Volatile-context slimming | 10–15% of total | — | — |
| Right-sizing agents WITHIN the Sonnet+ band (was "down-tiering") | lower than Rev 2's ~25%; the floor removes the Haiku option and Phase 0b raises four agents first | — | — |
| Batch async rungs | 50% of those calls | — | — |
| Stacked | 75–90% total | — | — |

---

## Rev 3 resolutions (2026-09-01) — what changed from Rev 2 and why

Each item was a conflict either between two parts of Rev 2 or between
Rev 2 and the repo as it actually is (every claim below was grep-verified
against the working tree on Larry's machine).

1. **Two writer processes, not one.** `council.py` (and `upgrade_agent.py`)
   are imported and run by `jarvis/admin/server.py` — the sidecar — while
   the other sites live in the bot. README said "enable WAL if a future
   concurrent writer needs it"; the second writer arrives with the first
   council round. **Resolved:** `usage_ledger._conn()` sets WAL +
   `busy_timeout` unconditionally and anchors the DB path to the repo
   root (two launch scripts, two CWDs). `costs_api.py` reads with a
   timeout for the same reason.
2. **Planner/executor named two systems as if they were one.** Rev 2's
   Phase 3 never said whether "executor" meant the `developer` SubAgent
   (bot, `agents.yaml`) or the `UpgradeAgent` loop (sidecar,
   `upgrade_models.yaml`). **Resolved:** the three-seat table above.
   Planner = planning pathway (`JARVIS_PLANNING_PROFILE` → `default`),
   executor = `UpgradeAgent`/`AppBuildAgent` (`JARVIS_UPGRADE_PROFILE` /
   `JARVIS_APPBUILD_PROFILE`, set explicitly — never via `default`),
   `developer` SubAgent = dispatcher, unsplit, eval-laddered like any rung.
3. **Phase 0b's `default` flip and Phase 3's executor tier pulled in
   opposite directions.** Flipping `default` to Fable puts the executor
   loop on the priciest profile until Phase 3. **Resolved:** accepted as
   the measured interim (quality-first while the ledger fills), made
   honest by (a) patching `upgrade_agent.py:469` now — the "double-count
   with base.py" rationale for deferring it was a different-process
   misread — and (b) stating the flip's full blast radius (edit loop,
   planning, research writer, picker default).
4. **`_call_profile` labelled four workflows "council".** Escalation
   rounds, planning drafts, the single-mode plan author and the research
   comparison writer all route through it. **Resolved:** `rung` kwarg,
   default `"council"`, threaded by the three non-council callers.
   Without it, A3 and the whole Phase 3 justification would have been
   computed from mislabelled rows.
5. **A3's operational definition didn't match its statement.**
   `cost_report.py` computed "sub-agent share" as everything-but-
   supervisor, folding memory sweeps, kb digests, planning and council
   into "sub-agents". **Resolved:** closed rung vocabulary
   (`usage_ledger.RUNGS`) + `cost_report.BUCKETS`; A3 is the five
   specialists, and a separate `A3_non_supervisor_share` keeps the
   broader number visible.
6. **Effort↔cache invalidation asserted as documented while the effort
   key itself was marked inferred.** **Resolved:** same gate, same
   session — toggle effort across two identical turns and record whether
   `cache_read_tokens` collapses. Static-per-rung stays the default
   because it is safe, not because it is proven required.
7. **"Backfill the lost mid-tier judge" after the Sonnet swap.** The swap
   preserves identity and tier; the mid pool depth is unchanged.
   **Withdrawn.**
8. **Planner round-one frontier membership had no mechanism.** Rev 2 said
   "draw the frontier pool from round one" with nothing to implement it.
   **Resolved:** `PLANNING_DEFAULT_PROPOSER_TIERS = ["frontier"]` for
   `draft_candidates` when no `members` are passed (also stops every
   spoken plan request buying 13 drafts), and `COUNCIL_PLANNER_START_TIER
   = 2` for `placement="planner"` escalations — one escalation per run
   under the never-repeat invariant, flagged [likely] and revisitable on
   `retry_validated` evidence.

9. **Model floor (Larry, 2026-09-01, Rev 3.1).** The extracted workflow
   draft `user-preference-model-defaults.yaml` surfaced a standing rule
   the plan contradicted: only the voice agent may run Haiku; every other
   agent is Sonnet-or-better. **Resolved:** bound in config + a test in
   Phase 0b item 5 (four agents → `claude-sonnet-5` direct with `refuse`),
   the Sonnet profile pulled forward from Phase 3, the Phase 3 ladder
   floored at Sonnet for agents, Phase 5 local serving scoped to the
   Supervisor and background rungs, the two model-preference workflow
   drafts retired, and the savings-ledger prior for "down-tiering"
   reduced accordingly. One interpretation flagged for veto: background
   maintenance rungs are not agents and stay below the floor.

Not changed, deliberately: the Phase order, the exit criteria, the
Interface Task, Phases 2/4/5. Nothing there conflicted with the repo.

## Rev 3.2 resolutions (2026-09-01) — Phase 1/1b rewritten for the compat-layer limitation

Trigger: Larry pulled Phase 1 forward ("implement prompt caching now, before
generating cost data") and asked for caching on both the sub-agents and the
voice Supervisor. Checking the mechanism before writing code found that the
plan's Phase 1 could not have worked as written. Every claim below was
verified against platform.claude.com (fetched 2026-09-01) or the working
tree / installed `.venv` on the same day.

1. **Prompt caching is unsupported through the OpenAI-compatibility layer.**
   Anthropic's own compat docs say so outright; Rev 3.1 tasks 1–2 assumed
   breakpoints could be inserted into the existing requests. Every Anthropic
   call site in the repo (Supervisor, five sub-agents, executor, council)
   uses that layer. **Resolved:** Phase 1 is now a native-SDK migration in
   two revertible paths — pipecat's `AnthropicLLMService` for the
   Supervisor (already shipped in the installed pipecat 1.4.0, caching
   built in), and a translating shim (`jarvis/anthropic_shim.py`) behind a
   factory (`jarvis/llm_client.py`) for everything else, so the sub-agent /
   executor / council loops and their tests are untouched. One kill switch,
   `JARVIS_ANTHROPIC_NATIVE=0`, restores today's behaviour everywhere.

2. **Haiku 4.5's cacheable minimum is 4,096 tokens, not 1,024.** The
   Supervisor is the one Haiku rung (model floor, Rev 3.1 §9) and its prefix
   measures ~5–7k tokens — above the floor, but close enough that Phase 1
   task 8 measures it instead of assuming. The Phase 0 diagnostic's 1,024-
   token filler would have reported a false negative on Haiku; it is
   rewritten to exceed 4,096.

3. **Two latent ledger bugs go live with caching.** `record_completion`
   subtracts cache reads but not cache writes from `input_tokens` (writes
   would bill at 1.25× and 1.0×), and `usage_watcher` assumes OpenAI's
   inclusive `prompt_tokens` while pipecat's Anthropic service reports the
   native uncached-only `input_tokens` (would double-subtract). Both fixed
   in Phase 1 tasks 3 and 7 with the semantics written down.

4. **Rev 3.1 task 3 (sticky sessions) dropped.** Native caches are
   per-workspace, not per-connection; through OpenRouter, routing pinning
   is unverifiable. OpenRouter's documented `cache_control` passthrough
   (request-level automatic mode, `prompt_tokens_details.cache_write_tokens`
   /`cached_tokens` reporting) replaces it as task 4; A5 stays a measurement
   via `pull_openrouter_activity.py`.

5. **Phase 1b's gate is mostly answered by documentation.** `output_config.
   effort` is the documented top-level parameter (no beta header) on
   Sonnet 5 / Opus 5 / Fable 5; **not listed for Haiku 4.5** — the
   Supervisor never sends it. `reasoning_effort` through the compat layer is
   *ignored*, so effort only exists on the native path. Effort changes
   invalidate the messages cache: static-per-rung is promoted from "safe
   default" to requirement, and the toggle half of the Rev 3.1 gate is
   removed. The draft `effort.py`'s Anthropic key shape was right.

6. **Baseline trade accepted, stated.** Phase 1 starts before the one-week
   baseline. The Savings Ledger's "before" for caching is whatever Phase 0
   rows exist at landing time (a few days, partial), labelled as such; the
   "after" is measured normally. Phases 2–5 keep their baseline
   requirement.

Not changed, deliberately: Phase 0/0b (complete), Phase 2–5, the Interface
Task, the model floor, and Phase 3's planner/executor table — the executor
simply inherits Path B caching because it builds its client through the
same factory.
