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
from typing import Any, Callable

from jarvis.agents.base import EventCallback, SubAgent

logger = logging.getLogger(__name__)

DEFAULT_MAX_PARALLEL_DELEGATIONS = 3


def build_delegate_tool(
    sub_agents: dict[str, SubAgent],
    on_event: EventCallback | None = None,
    max_parallel: int = DEFAULT_MAX_PARALLEL_DELEGATIONS,
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

    async def handler(arguments: dict) -> str:
        agent_name = str(arguments.get("agent_name", ""))
        task = str(arguments.get("task", ""))
        agent = sub_agents.get(agent_name)
        if agent is None:
            return f"Unknown agent '{agent_name}'. Available: {available}."
        if on_event is not None:
            on_event({"type": "delegate_start", "agent": agent_name,
                      "display_name": agent.display_name, "task": task})
        # Cap actual concurrent execution — pipecat's own parallel tool-call
        # dispatch has no limit. A failure inside agent.run() (SubAgent.run()
        # never raises; failures come back as "FAILED: ..." strings) does not
        # affect the semaphore or any sibling delegation.
        async with semaphore:
            result = await agent.run(task, on_event=on_event)
        if on_event is not None:
            failed = result.startswith("FAILED:")
            on_event({"type": "delegate_done", "agent": agent_name,
                      "display_name": agent.display_name,
                      "ok": not failed,
                      # Failure reasons surface in the UI status card;
                      # successful output is spoken/displayed elsewhere.
                      "detail": result[:300] if failed else ""})
        return result

    return schema, handler
