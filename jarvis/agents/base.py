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
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import yaml
from openai import AsyncOpenAI

from jarvis.config import Settings
from jarvis.procedures import match_procedure, mark_used
from jarvis.prompts import SUBAGENT_PROMPTS
from jarvis.runlog import RunLogger, get_run_id, run_logger_scope
from jarvis.toolresult import classify_tool_result

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
DEFAULT_TIMEOUT_S = 45.0
TIMEOUT_MESSAGE = "FAILED: the task took too long; please try again."
STUCK_MESSAGE = "FAILED: the task could not be completed."
# Cap tool results in events so a huge payload can't flood the data channel.
TOOL_RESULT_EVENT_MAX = 20_000

# MORTIMER_AGENT_TRUST_PLAN.md D3 — appended as a `system`-role message
# immediately after a failed tool's `role: "tool"` message. This is the
# direct fix for the fabrication defect in §1.1: a failed tool result
# arrives as a JSON blob that happens to say `ok: false` — syntactically
# indistinguishable, to the model, from data. An adjacent system-role
# instruction is unambiguous. The wording forbids INFERENCE ("structure,
# behavior"), not just quotation — do not shorten this, a model that is
# merely told "the call failed" has still been observed describing a file
# it never read.
TOOL_FAILURE_CONSTRAINT_TEMPLATE = (
    "The tool call `{tool_name}` FAILED: {error}. "
    "You did not receive the data you asked for. "
    "You MUST NOT state, summarize, guess, or infer the contents, "
    "structure, or behavior of anything this call was meant to retrieve. "
    "Either retry with corrected arguments, use a different tool, or tell "
    "the user plainly that the call failed and what you therefore could "
    "not determine."
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

EventCallback = Callable[[dict], None]


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
    ):
        self.name = name
        self.display_name = display_name
        self.description = description
        self.mcp_servers = list(mcp_servers)
        self._settings = settings
        self._registry = registry
        self._timeout_s = timeout_s
        if client_factory is not None:
            self._client = client_factory(settings)
        else:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        self._system_prompt = SUBAGENT_PROMPTS[name].format(
            timezone=settings.jarvis_timezone
        )

    async def run(
        self,
        task: str,
        on_event: EventCallback | None = None,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        """Execute a self-contained task. Never raises (plan step 3.1).

        run_id/session_id (plan D1/D16, run-logging plan §5.4): a
        RunLogger is created here — not in _loop — because _loop can be
        abandoned mid-flight by the asyncio.wait_for timeout below, and a
        RunLogger created inside _loop would never see finish() called on
        the timeout path, leaving the row stuck at status='running'
        forever. finish() is idempotent, so calling it from the success
        path and, separately, from an except branch is safe.
        """
        resolved_run_id = run_id or str(uuid.uuid4())
        runlog = RunLogger(
            resolved_run_id, self.name, self.display_name, task,
            session_id=session_id,
            enabled=self._settings.jarvis_runlog_enabled,
        )
        runlog.start()
        try:
            with run_logger_scope(runlog):
                reply = await asyncio.wait_for(
                    self._loop(task, on_event, runlog), timeout=self._timeout_s
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
    ) -> str:
        start = time.perf_counter()
        self._emit(on_event, {"type": "agent_start", "agent": self.name,
                              "display_name": self.display_name, "task": task})
        messages = [
            {"role": "system", "content": self._system_prompt},
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
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._client.chat.completions.create(
                model=self._settings.openai_model,
                messages=messages,
                **tools_kwarg,
            )
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                reply = message.content or ""
                break
            messages.append(_assistant_message(message))
            for tool_call in tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                self._emit(on_event, {"type": "agent_tool", "agent": self.name,
                                      "display_name": self.display_name,
                                      "tool": tool_call.function.name})
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
                self._emit(on_event, {
                    "type": "agent_tool_result",
                    "agent": self.name,
                    "display_name": self.display_name,
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result[:TOOL_RESULT_EVENT_MAX],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
                if not outcome.ok:
                    # D3 — the anti-hallucination constraint, injected
                    # immediately after the failed tool's own message so it
                    # is the freshest context the model sees before its next
                    # turn. A prompt message, not a code path (§0's rule that
                    # no confirmation gate is touched) — it constrains the
                    # model but cannot guarantee compliance, which is why D4
                    # exists as the mechanical backstop below.
                    messages.append({
                        "role": "system",
                        "content": TOOL_FAILURE_CONSTRAINT_TEMPLATE.format(
                            tool_name=tool_name, error=outcome.error,
                        ),
                    })

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


def _assistant_message(message: Any) -> dict:
    return {
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name,
                             "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ],
    }


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
        )
    return agents
