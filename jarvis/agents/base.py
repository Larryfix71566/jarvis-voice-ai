"""SubAgent: a text-only specialist LLM loop (plan Phase 3, step 3.1).

Each sub-agent owns a slice of the MCP toolset (its ``mcp_servers``) and a
specialist system prompt (Appendix A.3). It cannot see the Supervisor's
conversation — tasks must be self-contained.

Locked behavior:
- Max 5 tool iterations, hard 45 s timeout (asyncio.wait_for) — on timeout
  return "FAILED: the task took too long; please try again."
- Never raises: failures return "FAILED: <reason>" strings.
- Emits on_event dicts: agent_start / agent_tool / agent_tool_result /
  agent_done. agent_tool_result carries the raw tool result (truncated to
  TOOL_RESULT_EVENT_MAX chars) so the pipeline can forward display-worthy
  output (research, radar, project plans, commit summaries) to the UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import yaml
from openai import AsyncOpenAI

from jarvis.agents.upgrade_agent import (
    UnknownModelProfileError,
    load_model_registry,
    resolve_profile,
)
from jarvis.config import Settings
from jarvis.agent_skills import match_skill
from jarvis.procedures import match_procedure, mark_used
from jarvis.workflows import match_workflow
from jarvis.prompts import AGENT_DISCIPLINE, SUBAGENT_PROMPTS
from jarvis.repo_map import REPO_MAP_MAX_CHARS, load_repo_map_suffix
from jarvis.runlog import RunLogger, get_run_id, run_logger_scope
from jarvis.bot.sensitive_turn import is_sensitive
from jarvis.toolresult import classify_tool_result
from jarvis.usage_ledger import record_completion, provider_from_base_url

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
DEFAULT_TIMEOUT_S = 45.0
# A (Larry 2026-08-18): the per-agent override lives in config/agents.yaml
# as `max_iterations:`, exactly like `timeout_s:` — read-heavy analysis
# ("review the memory framework and tell me how it works") legitimately
# needs more rounds than a conversational lookup, and the observed
# failures were runs that read 9-11 files successfully and then died on
# the cap with every tool call green.
TIMEOUT_MESSAGE = "FAILED: the task took too long; please try again."
STUCK_MESSAGE = "FAILED: the task could not be completed."
# B (Larry 2026-08-18): running out of iterations is NOT the same failure
# as "could not be completed", and saying so matters. Two runs whose tool
# calls all SUCCEEDED returned the generic message above, and the
# Supervisor — given no reason — narrated it to the user as "the codebase
# access is blocked right now", which was pure invention. A reason the
# Supervisor can relay is the fix: same discipline as D6/D7, applied to
# the one channel that still carried no information.
ITERATIONS_EXHAUSTED_MESSAGE = (
    "FAILED: ran out of tool-call rounds ({used} of {used}) before finishing. "
    "Nothing was blocked — the work was incomplete, not refused. "
    "Narrow the task, or raise this agent's max_iterations in config/agents.yaml."
)
# Cap tool results in events so a huge payload can't flood the data channel.
TOOL_RESULT_EVENT_MAX = 20_000

# MORTIMER_AGENT_TRUST_PLAN.md D3 (amended 2026-08-16, MORTIMER_
# DEVELOPER_AGENT_FIX_PLAN.md F1) — appended as a `system`-role message
# immediately after the turn's tool-response BLOCK, never between tool
# responses. The original per-failure placement ("immediately after the
# failed tool's own message") violated the OpenAI protocol's requirement
# that every tool response follow the assistant tool_calls message
# contiguously: on a turn with parallel calls, the first interleaved
# system message orphaned every remaining tool_call_id and the next
# completion call died with a 400 (observed: two live Developer runs,
# 21 parallel repo reads). The freshness property D3 wanted is preserved
# — the constraint is still the last thing the model sees before its
# next turn. This is the direct fix for the fabrication defect in §1.1:
# a failed tool result arrives as a JSON blob that happens to say
# `ok: false` — syntactically indistinguishable, to the model, from
# data. A trailing system-role instruction is unambiguous. The wording
# forbids INFERENCE ("structure, behavior"), not just quotation — do not
# shorten this, a model that is merely told "the call failed" has still
# been observed describing a file it never read.
TOOL_FAILURE_CONSTRAINT_TEMPLATE = (
    "The tool call `{tool_name}` FAILED: {error}. "
    "You did not receive the data you asked for. "
    "You MUST NOT state, summarize, guess, or infer the contents, "
    "structure, or behavior of anything this call was meant to retrieve. "
    "Either retry with corrected arguments, use a different tool, or tell "
    "the user plainly that the call failed and what you therefore could "
    "not determine."
)

# F1 — the multi-failure variant for a parallel-call turn: one line per
# failed tool, then the SAME obligations stated once (built from the same
# wording as the single-failure template — the constraint's substance is
# not forked).
TOOL_FAILURES_BATCH_TEMPLATE = (
    "These tool calls FAILED:\n{failures}\n"
    "You did not receive the data they were meant to retrieve. "
    "You MUST NOT state, summarize, guess, or infer the contents, "
    "structure, or behavior of anything these calls were meant to "
    "retrieve. Either retry with corrected arguments, use a different "
    "tool, or tell the user plainly that the calls failed and what you "
    "therefore could not determine."
)

# MORTIMER_AGENT_TRUST_PLAN.md D4 — the reply used when every tool call in
# a run failed. Scoped to ALL tools failing, never ANY: a run with one
# working call among several failures is handled by D3's per-failure
# constraint plus D5's visible counts, not by a blunt status flip that
# would mark most useful runs failed.
ALL_TOOLS_FAILED_TEMPLATE = (
    "FAILED: every tool call in this run failed ({failed}/{attempted}). "
    "Last error: {error}"
)

# MORTIMER_PLANNING_PATHWAY_PLAN.md P2 — the phantom-completion fix,
# extending D3/D4 one level up. A tool result with `pending: true` at its
# top level is a DRAFT the mcp_repo/mcp_git draft-confirm gate created —
# nothing has actually been written, committed, or pushed. Left alone, a
# model narrates the JSON body ("I've written the file...") exactly the
# way D3 already found it doing for failures: syntactically the body reads
# like success. One message per batch (same batching rule as F1), appended
# after the tool-response block, never between responses.
PENDING_DRAFT_CONSTRAINT = (
    "The call(s) marked pending: true created DRAFTS awaiting the user's "
    "explicit confirmation — NOTHING has been written, committed, or "
    "pushed yet. You MUST describe these as drafts awaiting confirmation. "
    "Never state or imply the file was written or the action was "
    "performed."
)

# P2 backstop — tools whose success actually executes a pending draft
# (as opposed to merely creating one). Mirrors the draft-confirm pattern
# in mcp_repo/mcp_git: `repo_write_file`/`prepare_commit`/`prepare_push`
# create drafts; these three execute them.
DRAFT_EXECUTING_TOOLS = frozenset({"repo_commit_write", "commit", "push"})

EventCallback = Callable[[dict], None]


def _result_is_pending_draft(result: str) -> bool:
    """True iff a tool result's JSON body has `pending: true` at the top
    level (P2). Non-JSON or non-dict bodies are tolerated as not-pending —
    this backstop only recognizes our own draft-gated tools' shape."""
    try:
        body = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(body, dict) and body.get("pending") is True


class SubAgent:
    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        mcp_servers: list[str],
        settings: Settings,
        registry: Any,
        client_factory: Callable[[Any], Any] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_iterations: int = MAX_TOOL_ITERATIONS,
        model_profile: str | None = None,
        inject_repo_map: bool = False,
        on_profile_fallback: str = "warn",
    ):
        self.name = name
        self.display_name = display_name
        self.description = description
        self.mcp_servers = list(mcp_servers)
        self._settings = settings
        self._registry = registry
        self._timeout_s = timeout_s
        self._max_iterations = max(1, int(max_iterations))
        # MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md A1 — the voice
        # model (Haiku) is a dispatcher, never a design/build model. An
        # injected client_factory (the test seam) always wins: profile
        # resolution is skipped entirely so existing tests/fakes need no
        # changes. Resolution failure (unknown profile, missing API key)
        # fails soft, loudly — falls back to the settings client exactly
        # as before A1 existed, with a warning; voice must still boot on
        # a fresh checkout with one key.
        self._model: str = settings.openai_model
        # Larry 2026-08-19 — the Agents tab shows which model is doing the
        # work, and a FALLBACK must be distinguishable from a deliberate
        # assignment there. The warning below already says so in the log;
        # this flag is what carries the same fact to the UI, extending
        # "the resolved model is what gets recorded, never the configured
        # name" (model discipline, Part A) from the run log to the screen.
        self._model_fallback: bool = False
        # K5 — non-empty means every run() refuses immediately with this
        # text instead of silently running on the fallback model.
        self._refuse_reason: str = ""
        # K4 — which credential this agent's model actually rides on,
        # so `model_unusable` can ask jarvis.keyhealth about it at RUN
        # time. Empty for the voice-model path (settings client).
        self._api_key_env: str = ""
        if client_factory is not None:
            self._client = client_factory(settings)
        elif model_profile:
            try:
                registry_data = load_model_registry()
                profile = resolve_profile(registry_data, model_profile)
                key_env = profile.get("api_key_env", "OPENAI_API_KEY")
                if not os.environ.get(key_env):
                    raise UnknownModelProfileError(
                        f"model profile {model_profile!r} needs {key_env}, which is unset"
                    )
                self._client = AsyncOpenAI(
                    api_key=os.environ[key_env], base_url=profile["base_url"]
                )
                self._model = profile["model"]
                self._api_key_env = key_env
            except UnknownModelProfileError as exc:
                self._model_fallback = True
                # K5 — refuse mode, finally implemented. `warn` keeps the
                # long-standing fail-soft behaviour (voice must boot on a
                # fresh checkout with one key). `refuse` is for an agent
                # whose assigned model is the point: a build-grade task
                # silently executed by the voice dispatcher produces
                # plausible-looking work from the wrong model, which is far
                # harder to catch than a refusal.
                if on_profile_fallback == "refuse":
                    self._refuse_reason = (
                        f"model profile {model_profile!r} could not be "
                        f"resolved ({exc}). This agent is configured "
                        f"on_profile_fallback=refuse, so it will not run on "
                        f"the voice model instead. Fix the credential "
                        f"(python scripts/check_keys.py) and retry."
                    )
                logger.warning(
                    "subagent_model_profile_fallback agent=%s profile=%s mode=%s",
                    name, model_profile, on_profile_fallback,
                )
                self._client = AsyncOpenAI(
                    api_key=settings.openai_api_key, base_url=settings.openai_base_url
                )
        else:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        self._system_prompt = SUBAGENT_PROMPTS[name].format(
            timezone=settings.jarvis_timezone
        )
        # Part A — the repo-map suffix is kept SEPARATE as well as appended
        # below, so _system_prompt_for() can reassemble a per-task prompt
        # without re-reading the file. One read per boot, not per run.
        self._repo_map_suffix: str = ""
        # A3/G5 — repo map injection, construction-time (one read per boot,
        # not per run). `load_repo_map_suffix` is the ONE shared read/cap/
        # skip implementation (jarvis/repo_map.py) — UpgradeAgent uses the
        # same function so the two loops can never drift on this logic.
        if inject_repo_map:
            self._repo_map_suffix = load_repo_map_suffix(REPO_MAP_MAX_CHARS)
            self._system_prompt += self._repo_map_suffix

    @property
    def model(self) -> str:
        """The RESOLVED model string this agent will call — the same value
        RunLogger records, never the configured profile name. On a profile
        resolution failure this is the voice model, which is the honest
        answer and the one the Agents tab must show."""
        return self._model

    def _system_prompt_for(self, task: str) -> str:
        """The system prompt this RUN gets.

        Identical to `self._system_prompt` for every agent except the
        developer, whose own text was 4,034 chars of which 68% was two
        confirmation protocols injected on every task including "read this
        YAML file" (MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md
        Part A, approved Larry 2026-08-19).

        Assembled here rather than in __init__ because the choice depends on
        the task, and placed in the same method _loop already uses to pick
        per-run text — procedure hint, skill, workflow. Section selection is
        the fourth such decision, not a fourth mechanism in a fourth file.
        """
        if self.name != "developer":
            return self._system_prompt
        from jarvis.prompts import developer_prompt_for

        base = developer_prompt_for(task).format(
            timezone=self._settings.jarvis_timezone)
        return f"{base}\n{AGENT_DISCIPLINE}{self._repo_map_suffix}"

    @property
    def model_unusable(self) -> bool:
        """True when this agent's model resolved fine but its credential was
        actively refused or could not be billed (K4).

        Read at RUN time, not construction: the startup probe is a
        background thread, so a value captured in __init__ would almost
        always be `unknown`. `unreachable` and `unknown` are both False —
        a network blip must never paint a working agent red, which is the
        same rejected/unreachable discipline github_probe established."""
        if not self._api_key_env:
            return False
        from jarvis import keyhealth
        return keyhealth.is_unusable(self._api_key_env)

    @property
    def model_unusable_detail(self) -> str:
        if not self._api_key_env:
            return ""
        from jarvis import keyhealth
        return keyhealth.detail(self._api_key_env)

    @property
    def refuses(self) -> str:
        """Non-empty when this agent is configured on_profile_fallback=refuse
        AND its model profile failed to resolve. The string is the reason,
        shown to the user verbatim — never a generic failure, because the
        whole point is that "the wrong model did your build work" is the
        thing that must not happen quietly."""
        return self._refuse_reason

    @property
    def model_is_fallback(self) -> bool:
        """True when a `model_profile:` was configured but could not be
        resolved (unknown profile, or its api_key_env unset), so `model`
        is the voice-model fallback rather than the assignment."""
        return self._model_fallback

    def resolve_model_profile(self, profile_name: str) -> tuple[Any | None, str, str]:
        """F6/F7 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md, 2026-08-22)
        — resolve a NAMED, per-run model request into (client, model,
        refused_reason). Exactly the same resolution `__init__` runs for
        a configured `model_profile:`, reused rather than forked (K5's
        `UnknownModelProfileError` path), so a named request and a
        configured default can never disagree about what "resolved"
        means.

        `refused_reason` is non-empty iff resolution failed — an
        unresolvable named request ALWAYS refuses (never falls back to
        this agent's default model), regardless of this agent's own
        `on_profile_fallback` setting: that setting governs an
        infrastructure default, this is a per-run user instruction, and
        silently disobeying it is never correct (F7). On success,
        `client`/`model` are ready to use; on failure both are
        None/"" and `refused_reason` names both the requested profile
        and this agent's own (unaffected) default model, so the caller's
        refusal message can say what did NOT happen.

        Pure with respect to instance state (F8) — never touches
        `self._client`/`self._model`/`self._model_fallback`. Called
        twice per overridden delegation by design (once by
        jarvis.agents.delegate's handler, to know the model BEFORE
        emitting the `delegate_start` event; once inside `run()`, to
        actually execute on it) — deterministic given the same profile
        name and environment, so the duplication costs an extra client
        object construction (no I/O — the network call happens at
        `chat.completions.create`), not a second source of truth.
        """
        try:
            registry_data = load_model_registry()
            profile = resolve_profile(registry_data, profile_name)
            key_env = profile.get("api_key_env", "OPENAI_API_KEY")
            if not os.environ.get(key_env):
                raise UnknownModelProfileError(
                    f"model profile {profile_name!r} needs {key_env}, which is unset"
                )
            client = AsyncOpenAI(
                api_key=os.environ[key_env], base_url=profile["base_url"]
            )
            return client, profile["model"], ""
        except UnknownModelProfileError as exc:
            reason = (
                f"model profile {profile_name!r} could not be resolved "
                f"({exc}) — this run was requested on that model "
                f"specifically, so it was not started on {self._model} "
                f"instead."
            )
            return None, "", reason

    async def run(
        self,
        task: str,
        on_event: EventCallback | None = None,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        model_profile_override: str | None = None,
    ) -> str:
        """Execute a self-contained task. Never raises (plan step 3.1).

        run_id/session_id (plan D1/D16, run-logging plan §5.4): a
        RunLogger is created here — not in _loop — because _loop can be
        abandoned mid-flight by the asyncio.wait_for timeout below, and a
        RunLogger created inside _loop would never see finish() called on
        the timeout path, leaving the row stuck at status='running'
        forever. finish() is idempotent, so calling it from the success
        path and, separately, from an except branch is safe.

        model_profile_override (F6/F7/F8, MORTIMER_GATE_V2_AND_MODEL_
        REQUEST_PLAN.md, 2026-08-22): a NAMED per-run model request —
        set only when the user explicitly asked for a specific model
        (jarvis.agents.delegate's handler is the one caller). Resolved
        via resolve_model_profile() into LOCAL run_client/run_model —
        self._client/self._model/self._model_fallback are never touched
        (F8: barge-in survival runs delegations as detached tasks, so two
        concurrent run() calls can be in flight on one SubAgent instance;
        mutating instance state for one run would corrupt the other). An
        unresolvable override ALWAYS refuses (F7) — see
        resolve_model_profile's docstring for why that is unconditional,
        unlike this agent's own on_profile_fallback setting.
        """
        # K5 — refuse BEFORE anything else: no run row, no model call, no
        # tools. A refusing agent has no assigned model, so there is no
        # work it could honestly attempt; running on the fallback is the
        # exact outcome the setting exists to prevent. The reason is
        # returned verbatim so the Supervisor can relay it — Golden Rule 1
        # and rule 11 both require a stated cause, and "REFUSED:" with no
        # explanation is how the model ends up inventing one.
        if self._refuse_reason:
            logger.warning("subagent_refused agent=%s reason=%s",
                           self.name, self._refuse_reason)
            return f"REFUSED: {self._refuse_reason}"

        run_client, run_model = self._client, self._model
        if model_profile_override:
            override_client, override_model, refused_reason = (
                self.resolve_model_profile(model_profile_override)
            )
            if refused_reason:
                logger.warning(
                    "subagent_override_refused agent=%s profile=%s reason=%s",
                    self.name, model_profile_override, refused_reason,
                )
                return f"REFUSED: {refused_reason}"
            run_client, run_model = override_client, override_model

        resolved_run_id = run_id or str(uuid.uuid4())
        runlog = RunLogger(
            resolved_run_id, self.name, self.display_name, task,
            session_id=session_id,
            enabled=self._settings.jarvis_runlog_enabled,
            # MORTIMER_PLANNING_PATHWAY_PLAN.md P3 — the run's authoring
            # model, recorded once here (settings is only in hand at this
            # call site) and never re-derived downstream. F8: this is now
            # the OVERRIDE-resolved model when one was requested, never
            # self._model — the run log must record what actually ran.
            model=run_model,
            sensitive=is_sensitive(),   # T4a K3 snapshot (review F6)
        )
        runlog.start()
        try:
            with run_logger_scope(runlog):
                reply = await asyncio.wait_for(
                    self._loop(task, on_event, runlog,
                               client=run_client, model=run_model),
                    timeout=self._timeout_s,
                )
            runlog.finish(reply)
            return reply
        except asyncio.TimeoutError:
            logger.warning("subagent_timeout agent=%s run_id=%s",
                            self.name, resolved_run_id)
            runlog.finish(TIMEOUT_MESSAGE)
            return TIMEOUT_MESSAGE
        except Exception as exc:  # noqa: BLE001 — contract: never raise
            logger.exception("subagent_error agent=%s run_id=%s",
                              self.name, resolved_run_id)
            reply = f"FAILED: {exc}"
            runlog.finish(reply)
            return reply

    async def _loop(
        self, task: str, on_event: EventCallback | None, runlog: RunLogger,
        client: Any = None, model: str | None = None,
    ) -> str:
        # F8 — locals, defaulting to the instance's configured client/model
        # when no override was resolved by run(). Every model call below
        # uses these locals, never self._client/self._model directly, so
        # an overridden run can never leak into a concurrent default run
        # on the same SubAgent instance.
        client = client if client is not None else self._client
        model = model if model is not None else self._model
        start = time.perf_counter()
        self._emit(on_event, {"type": "agent_start", "agent": self.name,
                              "display_name": self.display_name, "task": task})
        messages = [
            {"role": "system", "content": self._system_prompt_for(task)},
        ]
        # Procedures-as-hints (MORTIMER_MEMORY_PROCEDURES_PLAN.md D11/D17):
        # single enforcement point for the kill switch (D20) — when
        # disabled, no FTS query runs at all, so there is no latency cost
        # and no hint is ever injected. status="active" (the default) is
        # deliberate here — a candidate or deprecated procedure must never
        # be surfaced as a hint, only match_procedure's dedup caller
        # (jarvis.procedures.learn_from_run) passes status=None.
        if self._settings.jarvis_procedures_enabled:
            try:
                procedure = match_procedure(self.name, task)
            except Exception:  # noqa: BLE001 — matching must never break a run
                logger.exception("procedure_match_failed agent=%s", self.name)
                procedure = None
            if procedure is not None:
                messages.append({
                    "role": "system",
                    "content": (
                        f"A similar task has succeeded before: "
                        f"{procedure['description']}"
                    ),
                })
                mark_used(procedure["id"])

        # K3 skills — authored capability knowledge in the Agent Skills
        # format, injected between the procedure hint and the workflow
        # rule. That position is the whole ordering argument in one line:
        # evidence (what worked once) < reference (how this is done) <
        # requirement (how Larry wants it done), with the strongest claim
        # read last. Matching reads only name+description; the body is
        # read from disk for the ONE skill that matched, which is what
        # progressive disclosure buys. Two gates upstream mean a match is
        # already reviewed: the skill had to be registered by name in
        # config/skills.yaml, and nothing in that module can execute a
        # bundled script. Never raises; kill switch is inside load_skills.
        try:
            skill = match_skill(task)
        except Exception:  # noqa: BLE001
            logger.exception("skill_match_failed agent=%s", self.name)
            skill = None
        if skill is not None:
            messages.append({"role": "system", "content": skill.as_prompt()})
            logger.info("skill_injected agent=%s name=%s", self.name, skill.name)

        # K4 workflows — authored, normative, injected AFTER the procedure
        # hint so the standing instruction is the last thing read before
        # the task. Order matters and is deliberate: a procedure says what
        # worked once, a workflow says what Larry requires; when they
        # disagree the rule should be the fresher context.
        #
        # Guidance only — nothing here executes steps or blocks on
        # done_when. Never raises: a matching failure must not break a
        # run, and the kill switch (JARVIS_WORKFLOWS_ENABLED) is enforced
        # inside load_workflows.
        try:
            workflow = match_workflow(self.name, task)
        except Exception:  # noqa: BLE001
            logger.exception("workflow_match_failed agent=%s", self.name)
            workflow = None
        if workflow is not None:
            messages.append({"role": "system", "content": workflow.as_prompt()})
            logger.info("workflow_injected agent=%s name=%s source=%s",
                        self.name, workflow.name, workflow.source)

        messages.append({"role": "user", "content": task})
        tools = self._registry.openai_tools(self.mcp_servers)
        tools_kwarg = {"tools": tools} if tools else {}

        reply = STUCK_MESSAGE
        # MORTIMER_AGENT_TRUST_PLAN.md D4/D5 — counted across the WHOLE run,
        # not per-iteration, since D4's rule ("every tool call failed") must
        # see calls made across all MAX_TOOL_ITERATIONS rounds.
        tools_attempted = 0
        tools_failed = 0
        last_error: str | None = None
        # P2 — counted across the WHOLE run, same reasoning as D4/D5 above:
        # a draft created in an early iteration and confirmed in a later
        # one must not be double-flagged.
        drafts_created = 0
        drafts_executed = 0
        exhausted = True  # cleared by the no-more-tool-calls break below
        for _ in range(self._max_iterations):
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                **tools_kwarg,
            )
            try:
                record_completion(
                    rung=self.name,
                    provider=provider_from_base_url(str(client.base_url)),
                    model=model,
                    response=response,
                    session_id=runlog.run_id,
                )
            except Exception:
                pass
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                reply = message.content or ""
                exhausted = False  # finished on its own terms, not on the cap
                break
            messages.append(_assistant_message(message))
            # F1: failures collected during the batch; the D3 constraint is
            # appended AFTER every tool response (protocol contiguity),
            # never between them.
            batch_failures: list[tuple[str, str]] = []
            batch_has_pending_draft = False
            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                self._emit(on_event, {"type": "agent_tool", "agent": self.name,
                                      "display_name": self.display_name,
                                      "tool": tool_call.function.name,
                                      # Activity ticker (Larry 2026-08-21):
                                      # the Agents card shows a live line
                                      # per tool call, keyed by run.
                                      "run_id": runlog.run_id})
                tool_name = tool_call.function.name
                runlog.tool_call(tool_name, arguments)
                tool_start = time.perf_counter()
                result = await self._registry.call(
                    tool_name, arguments, self.mcp_servers
                )
                tool_latency_ms = int((time.perf_counter() - tool_start) * 1000)
                # MORTIMER_AGENT_TRUST_PLAN.md D1/D2 — classify_tool_result
                # is the SINGLE place this judgement is made now. It
                # inspects both the three transport-failure prefixes
                # SkillRegistry.call() can return AND the tool's own JSON
                # body (e.g. {"ok": false, "error": "...401..."}), which the
                # previous prefix-only heuristic here could not see — that
                # gap is what let a run log four failed app_read calls as
                # `ok=True` while the sub-agent fabricated their contents
                # (plan §1.1/§1.2). The mcp_call event recorded one layer
                # down in SkillRegistry.call() now uses the same function,
                # so the two layers cannot disagree the way D18's original
                # comment here described.
                outcome = classify_tool_result(tool_name, result)
                runlog.tool_result(tool_name, result, tool_latency_ms, outcome.ok)
                tools_attempted += 1
                if not outcome.ok:
                    tools_failed += 1
                    last_error = outcome.error
                # P2 — mechanical draft accounting, independent of outcome.ok
                # (a pending draft's transport call itself succeeded; it is
                # the ACTION that is incomplete, not the tool call).
                if _result_is_pending_draft(result):
                    drafts_created += 1
                    batch_has_pending_draft = True
                if outcome.ok and tool_name in DRAFT_EXECUTING_TOOLS:
                    drafts_executed += 1
                self._emit(on_event, {
                    "type": "agent_tool_result",
                    "agent": self.name,
                    "display_name": self.display_name,
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result[:TOOL_RESULT_EVENT_MAX],
                    # Activity ticker (Larry 2026-08-21): ok/latency feed
                    # the per-run line the Agents card renders — the same
                    # verdict the run log records (classify_tool_result),
                    # so the card can never disagree with the log.
                    "run_id": runlog.run_id,
                    "ok": outcome.ok,
                    "latency_ms": tool_latency_ms,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                if not outcome.ok:
                    batch_failures.append((tool_name, outcome.error or ""))

            if batch_failures:
                # D3 — the anti-hallucination constraint, injected after the
                # batch's tool-response block (F1: never BETWEEN tool
                # responses — see the template comment above for the 400
                # this placement fixes) so it is the freshest context the
                # model sees before its next turn. A prompt message, not a
                # code path (§0's rule that no confirmation gate is
                # touched) — it constrains the model but cannot guarantee
                # compliance, which is why D4 exists as the mechanical
                # backstop below.
                if len(batch_failures) == 1:
                    name, error = batch_failures[0]
                    content = TOOL_FAILURE_CONSTRAINT_TEMPLATE.format(
                        tool_name=name, error=error,
                    )
                else:
                    content = TOOL_FAILURES_BATCH_TEMPLATE.format(
                        failures="\n".join(
                            f"- `{name}`: {error}"
                            for name, error in batch_failures
                        ),
                    )
                messages.append({"role": "system", "content": content})

            if batch_has_pending_draft:
                # P2 constraint — appended after the tool-response block for
                # the SAME reason D3 is (protocol contiguity; freshest thing
                # the model sees before its next turn). Independent of the
                # D3/F1 failure message above: a batch can contain both a
                # failure and a pending draft, and both messages are added.
                messages.append({"role": "system", "content": PENDING_DRAFT_CONSTRAINT})

        # B — the run used every round without the model ever answering.
        # Say that plainly; the generic STUCK_MESSAGE is what let the
        # Supervisor invent "access is blocked". Only overrides the
        # untouched default, so a real reply the model produced is never
        # clobbered.
        if exhausted and reply == STUCK_MESSAGE:
            reply = ITERATIONS_EXHAUSTED_MESSAGE.format(used=self._max_iterations)

        # D4 — a run in which every attempted tool call failed cannot be
        # reported as successful, regardless of how confident the model's
        # own reply reads. Deliberately does NOT trigger on partial failure
        # (some calls ok, some failed) — that case is handled by D3's
        # per-failure constraint and D5's visible tools_ok/tools_failed
        # counts, not by a blunt status flip.
        if tools_attempted > 0 and tools_failed == tools_attempted:
            reply = ALL_TOOLS_FAILED_TEMPLATE.format(
                failed=tools_failed, attempted=tools_attempted,
                error=last_error or "unknown error",
            )

        # P2 backstop — deliberately count-based and append-only, like D4:
        # it cannot be argued with by the model, and unlike a status flip
        # it does not mark an otherwise-useful run failed. Runs after the
        # D4 override on purpose so an all-failed reply can still be
        # amended (a run can fail every read tool yet still have created an
        # earlier draft in the same batch of iterations).
        if drafts_created > drafts_executed:
            reply = reply + (
                f"\n\n[{drafts_created - drafts_executed} draft(s) are "
                "awaiting your confirmation — nothing has been written "
                "yet.]"
            )

        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info("subagent_done agent=%s latency_ms=%d run_id=%s",
                     self.name, latency_ms, runlog.run_id)
        self._emit(on_event, {"type": "agent_done", "agent": self.name,
                              "display_name": self.display_name,
                              "latency_ms": latency_ms})
        return reply

    def _emit(self, on_event: EventCallback | None, event: dict) -> None:
        """Adds run_id to every event when one is active (plan D2) —
        additive field, existing consumers read specific keys and ignore
        unknown ones."""
        run_id = get_run_id()
        if run_id is not None:
            event = {**event, "run_id": run_id}
        if on_event is not None:
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 — observers must not break agents
                logger.exception("on_event callback failed")


def _merge_vendor_extras(target: dict, model_obj: Any) -> None:
    """Copy provider-specific fields the SDK captured into a history dict.

    The openai SDK's response models are pydantic with extra="allow", so any
    field a provider adds beyond the OpenAI schema lands in `model_extra`.
    Google's Gemini 3 endpoint is the motivating case
    (MORTIMER_VOICE_MODEL_BENCH_PLAN.md V3): it attaches an encrypted
    `thought_signature` to tool calls and REQUIRES it echoed back when the
    conversation history is replayed — dropping it fails the very next
    request with HTTP 400, which is exactly what the hand-built dicts below
    used to do.

    Safe by construction for every other provider: extras are only added
    when the provider actually sent them, and a history is only ever
    replayed to the same client that produced it, so Anthropic/Moonshot/
    OpenRouter responses (no extras) are byte-identical to before.
    """
    extras = getattr(model_obj, "model_extra", None) or {}
    for key, value in extras.items():
        if value is not None:
            target[key] = value


def _assistant_message(message: Any) -> dict:
    result: dict = {
        "role": "assistant",
        "content": message.content,
    }
    tool_calls = []
    for tc in message.tool_calls or []:
        call = {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name,
                         "arguments": tc.function.arguments},
        }
        _merge_vendor_extras(call, tc)
        tool_calls.append(call)
    if tool_calls:
        result["tool_calls"] = tool_calls
    _merge_vendor_extras(result, message)
    return result


def load_sub_agents(
    settings: Settings,
    registry: Any,
    config_path: str | Path | None = None,
    client_factory: Callable[[Any], Any] | None = None,
) -> dict[str, SubAgent]:
    """Build the sub-agent roster from config/agents.yaml (§6.4)."""
    path = Path(config_path) if config_path else (
        Path(__file__).resolve().parents[2] / "config" / "agents.yaml"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    agents: dict[str, SubAgent] = {}
    for entry in data["sub_agents"]:
        agents[entry["name"]] = SubAgent(
            name=entry["name"],
            display_name=entry["display_name"],
            description=entry["description"],
            mcp_servers=entry["mcp_servers"],
            settings=settings,
            registry=registry,
            client_factory=client_factory,
            # MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F3 — optional per-agent
            # timeout from agents.yaml (the routing/capability source of
            # truth); absent = DEFAULT_TIMEOUT_S. Developer's legitimate
            # tasks (multi-file review, plan drafting) need more than the
            # voice-loop default.
            timeout_s=float(entry.get("timeout_s", DEFAULT_TIMEOUT_S)),
            max_iterations=int(entry.get("max_iterations", MAX_TOOL_ITERATIONS)),
            model_profile=entry.get("model_profile"),
            # MORTIMER_KEY_VALIDITY_PLAN.md K5. This key was read by
            # scripts/check_env.py — which warns that a refuse-mode agent
            # with no key "refuses every delegation" — and by NOTHING in
            # jarvis/. The preflight was reporting on a guarantee that did
            # not exist: the agent fell back to the voice model silently,
            # exactly as if the setting were absent. Reassuring the reader
            # about an unimplemented behaviour is worse than not checking.
            on_profile_fallback=str(
                entry.get("on_profile_fallback", "warn")).strip().lower(),
            inject_repo_map=bool(entry.get("inject_repo_map", False)),
        )
    return agents
