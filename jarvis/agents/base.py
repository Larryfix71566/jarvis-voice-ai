"""SubAgent: a text-only specialist LLM loop (plan Phase 3, step 3.1).

Each sub-agent owns a slice of the MCP toolset (its ``mcp_servers``) and a
specialist system prompt (Appendix A.3). It cannot see the Supervisor's
conversation — tasks must be self-contained.

Locked behavior:
- Max 5 tool iterations, hard 45 s timeout (asyncio.wait_for) — on timeout
  return "FAILED: the task took too long; please try again."
- Never raises: failures return "FAILED: <reason>" strings.
- Emits on_event dicts: agent_start / agent_tool / agent_done.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

import yaml
from openai import AsyncOpenAI

from jarvis.config import Settings
from jarvis.prompts import SUBAGENT_PROMPTS

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
DEFAULT_TIMEOUT_S = 45.0
TIMEOUT_MESSAGE = "FAILED: the task took too long; please try again."
STUCK_MESSAGE = "FAILED: the task could not be completed."

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

    async def run(self, task: str, on_event: EventCallback | None = None) -> str:
        """Execute a self-contained task. Never raises (plan step 3.1)."""
        try:
            return await asyncio.wait_for(
                self._loop(task, on_event), timeout=self._timeout_s
            )
        except asyncio.TimeoutError:
            logger.warning("subagent_timeout agent=%s", self.name)
            return TIMEOUT_MESSAGE
        except Exception as exc:  # noqa: BLE001 — contract: never raise
            logger.exception("subagent_error agent=%s", self.name)
            return f"FAILED: {exc}"

    async def _loop(self, task: str, on_event: EventCallback | None) -> str:
        start = time.perf_counter()
        self._emit(on_event, {"type": "agent_start", "agent": self.name,
                              "display_name": self.display_name, "task": task})
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": task},
        ]
        tools = self._registry.openai_tools(self.mcp_servers)
        tools_kwarg = {"tools": tools} if tools else {}

        reply = STUCK_MESSAGE
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
                result = await self._registry.call(
                    tool_call.function.name, arguments, self.mcp_servers
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info("subagent_done agent=%s latency_ms=%d", self.name, latency_ms)
        self._emit(on_event, {"type": "agent_done", "agent": self.name,
                              "display_name": self.display_name,
                              "latency_ms": latency_ms})
        return reply

    @staticmethod
    def _emit(on_event: EventCallback | None, event: dict) -> None:
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
