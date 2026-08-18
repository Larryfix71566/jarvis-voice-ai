"""delegate_task tool factory (plan Phase 3, step 3.2; concurrency: Phase 4).

Returns the locked OpenAI tool schema plus an async handler that routes a
self-contained task to the named sub-agent.

Concurrency (plan Phase 4): pipecat's LLMService dispatches multiple
delegate_task calls emitted in one assistant turn concurrently by default
(run_in_parallel=True, group_parallel_tools=True — confirmed by reading
pipecat/services/llm_service.py; Mortimer's OpenAILLMService construction in
jarvis/bot/pipeline.py does not override either). SubAgent.run() has no
shared mutable per-instance state (jarvis/agents/base.py builds a fresh
`messages` list per call) and the MCP ClientSession multiplexes concurrent
requests by JSON-RPC id, so no new locking was needed for correctness — only
a bound, since pipecat's own parallel dispatch has none. `max_parallel`
gates actual sub-agent execution with a semaphore; delegate_start still
fires immediately so the UI shows "working" the instant the call arrives,
even if execution is briefly queued behind the cap.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable

from jarvis.agents.base import EventCallback, SubAgent
from jarvis.procedures import _overlap_score, _tokens, learn_from_run

logger = logging.getLogger(__name__)

DEFAULT_MAX_PARALLEL_DELEGATIONS = 3

# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md A2 — the mechanical
# half of the stop rule: the Supervisor prompt asks it not to retry a
# failed delegation with reworded instructions, but a live session
# showed six such retries in a row (one inventing "vault credentials"),
# so a prompt alone cannot be trusted. Reuses the procedures module's
# own symmetric token-overlap scorer — one scoring implementation, not a
# second one invented here.
RETRY_GUARD_WINDOW_S = 120.0
RETRY_GUARD_OVERLAP = 0.5

# Procedures-as-hints (MORTIMER_MEMORY_PROCEDURES_PLAN.md D13): a bare
# asyncio.create_task(...) result has no strong reference anywhere else in
# this module, so without holding one here a background learn_from_run
# task could be garbage-collected — and silently cancelled — before it
# finishes. Module-level so it survives across concurrent delegations;
# add_done_callback discards each task's own reference once it completes.
_background_tasks: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def build_delegate_tool(
    sub_agents: dict[str, SubAgent],
    on_event: EventCallback | None = None,
    max_parallel: int = DEFAULT_MAX_PARALLEL_DELEGATIONS,
    *,
    session_id: str | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for delegate_task."""
    names = list(sub_agents)
    available = ", ".join(names)
    schema = {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": (
                "Delegate a specialist task to a sub-agent. The task must be "
                "fully self-contained; sub-agents cannot see this conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "enum": names},
                    "task": {
                        "type": "string",
                        "description": (
                            "Complete, self-contained instruction including "
                            "all facts needed."
                        ),
                    },
                },
                "required": ["agent_name", "task"],
            },
        },
    }

    semaphore = asyncio.Semaphore(max(1, max_parallel))
    # A2 — per-session, per-agent: (task_tokens, failed_at_monotonic).
    # Session-scoped closure state, same lifetime as the semaphore above.
    last_failure: dict[str, tuple[set[str], float]] = {}

    async def handler(arguments: dict) -> str:
        agent_name = str(arguments.get("agent_name", ""))
        task = str(arguments.get("task", ""))
        agent = sub_agents.get(agent_name)
        if agent is None:
            # No agent, nothing ran — this path does not create a run
            # (run-logging plan §5.5).
            return f"Unknown agent '{agent_name}'. Available: {available}."

        prior = last_failure.get(agent_name)
        if prior is not None:
            prior_tokens, failed_at = prior
            if time.monotonic() - failed_at < RETRY_GUARD_WINDOW_S:
                overlap = _overlap_score(prior_tokens, _tokens(task))
                if overlap >= RETRY_GUARD_OVERLAP:
                    logger.info(
                        "delegate_retry_guard_refused agent=%s overlap=%.2f",
                        agent_name, overlap,
                    )
                    return (
                        f"REFUSED: the {agent_name} agent just failed this "
                        "same task. Report that failure to the user and ask "
                        "how to proceed — do not retry with reworded "
                        "instructions."
                    )
        # run_id generated here, one per delegation (run-logging plan D1):
        # this is the unit a human reviews, and generating it before the
        # semaphore below means a queued-but-not-yet-running delegation
        # still has an identity in the UI and the run log.
        run_id = str(uuid.uuid4())
        if on_event is not None:
            on_event({"type": "delegate_start", "agent": agent_name,
                      "display_name": agent.display_name, "task": task,
                      "run_id": run_id})
        # Cap actual concurrent execution — pipecat's own parallel tool-call
        # dispatch has no limit. A failure inside agent.run() (SubAgent.run()
        # never raises; failures come back as "FAILED: ..." strings) does not
        # affect the semaphore or any sibling delegation.
        async with semaphore:
            result = await agent.run(
                task, on_event=on_event, run_id=run_id, session_id=session_id,
            )
        # D13: spawned unconditionally — D20 makes jarvis_procedures_enabled
        # a single-enforcement-point flag, checked once inside
        # learn_from_run itself (which loads its own settings). A disabled
        # flag still spawns a task, which returns immediately as a no-op;
        # this keeps delegate.py from reaching into SubAgent's private
        # _settings attribute to check the flag redundantly.
        _spawn_background(learn_from_run(run_id, agent_name))
        failed = result.startswith("FAILED:")
        # A2 — a failure arms the guard for this agent; a success clears
        # it (the agent is demonstrably working again).
        if failed:
            last_failure[agent_name] = (_tokens(task), time.monotonic())
        else:
            last_failure.pop(agent_name, None)
        if on_event is not None:
            on_event({"type": "delegate_done", "agent": agent_name,
                      "display_name": agent.display_name,
                      "ok": not failed,
                      "run_id": run_id,
                      # Failure reasons surface in the UI status card;
                      # successful output is spoken/displayed elsewhere.
                      "detail": result[:300] if failed else ""})
        return result

    return schema, handler
