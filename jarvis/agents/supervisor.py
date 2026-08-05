"""Orchestrator: the Supervisor brain (plan Phase 2, step 2.3).

Text-level LLM conversation loop with OpenAI-style function calling over
the SkillRegistry's MCP tools. Phase 2 runs it in "direct" scope: the
Supervisor calls MCP tools itself. Phase 3 narrows the toolset to
delegate_task only (delegating mode).

Locked behavior:
- temperature omitted by default (provider default applies; D-003 —
  kimi-k2.x rejects any temperature other than 1). Pass explicitly to
  override on providers that support it.
- Hard cap of 6 tool iterations; on cap the reply is STUCK_MESSAGE.
- History persisted to the conversations table (user/assistant rows),
  trimmed to the last 40 messages; orphaned leading tool messages after a
  trim are dropped so the message list stays API-valid.
- Every turn logs: turn_complete user_len=%d latency_ms=%d tool_calls=%d
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from openai import AsyncOpenAI

from jarvis.db import get_conn, now_iso
from jarvis.prompts import SUPERVISOR_PROMPT

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6
MAX_HISTORY_MESSAGES = 40
STUCK_MESSAGE = "I'm sorry, I got stuck working on that. Please try rephrasing."


class Orchestrator:
    def __init__(
        self,
        settings: Any,
        registry: Any,
        session_id: str,
        allowed_servers: list[str] | None = None,
        client_factory: Callable[[Any], Any] | None = None,
        temperature: float | None = None,
    ):
        self._settings = settings
        self._registry = registry
        self._session_id = session_id
        self._allowed_servers = allowed_servers
        self._temperature = temperature
        if client_factory is not None:
            self._client = client_factory(settings)
        else:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        # Phase 2: no agent catalog yet (plan step 2.3 / Appendix A.4).
        self._system_prompt = SUPERVISOR_PROMPT.format(
            jarvis_name=settings.jarvis_name,
            user_name=settings.jarvis_user_name,
            timezone=settings.jarvis_timezone,
            agent_catalog="(none yet — call tools directly)",
            voice_catalog="(none configured yet)",
        )
        self._history: list[dict] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def reset(self, session_id: str) -> None:
        """Start a fresh conversation under a new session id."""
        self._session_id = session_id
        self._history = []

    async def chat(self, user_text: str) -> str:
        start = time.perf_counter()
        tool_calls_total = 0
        self._history.append({"role": "user", "content": user_text})
        self._persist("user", user_text)

        reply = STUCK_MESSAGE
        for _ in range(MAX_TOOL_ITERATIONS):
            extra: dict[str, Any] = {}
            if self._temperature is not None:
                extra["temperature"] = self._temperature
            response = await self._client.chat.completions.create(
                model=self._settings.openai_model,
                messages=self._messages(),
                **extra,
                **self._tools_kwarg(),
            )
            message = response.choices[0].message
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if not tool_calls:
                reply = message.content or ""
                break
            self._history.append(self._assistant_message(message))
            for tool_call in tool_calls:
                tool_calls_total += 1
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                result = await self._registry.call(
                    tool_call.function.name, arguments, self._allowed_servers
                )
                self._history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

        self._history.append({"role": "assistant", "content": reply})
        self._persist("assistant", reply)
        self._trim_history()
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "turn_complete user_len=%d latency_ms=%d tool_calls=%d",
            len(user_text), latency_ms, tool_calls_total,
        )
        return reply

    def _messages(self) -> list[dict]:
        return [{"role": "system", "content": self._system_prompt}, *self._history]

    def _tools_kwarg(self) -> dict:
        tools = self._registry.openai_tools(self._allowed_servers)
        return {"tools": tools} if tools else {}

    @staticmethod
    def _assistant_message(message: Any) -> dict:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        }

    def _trim_history(self) -> None:
        if len(self._history) > MAX_HISTORY_MESSAGES:
            self._history = self._history[-MAX_HISTORY_MESSAGES:]
        while self._history and self._history[0]["role"] == "tool":
            self._history.pop(0)

    def _persist(self, role: str, content: str) -> None:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (self._session_id, role, content, now_iso()),
            )
