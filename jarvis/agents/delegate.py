"""delegate_task tool factory (plan Phase 3, step 3.2).

Returns the locked OpenAI tool schema plus an async handler that routes a
self-contained task to the named sub-agent.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from jarvis.agents.base import EventCallback, SubAgent

logger = logging.getLogger(__name__)


def build_delegate_tool(
    sub_agents: dict[str, SubAgent],
    on_event: EventCallback | None = None,
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

    async def handler(arguments: dict) -> str:
        agent_name = str(arguments.get("agent_name", ""))
        task = str(arguments.get("task", ""))
        agent = sub_agents.get(agent_name)
        if agent is None:
            return f"Unknown agent '{agent_name}'. Available: {available}."
        if on_event is not None:
            on_event({"type": "delegate_start", "agent": agent_name,
                      "display_name": agent.display_name, "task": task})
        result = await agent.run(task, on_event=on_event)
        if on_event is not None:
            on_event({"type": "delegate_done", "agent": agent_name,
                      "display_name": agent.display_name})
        return result

    return schema, handler
