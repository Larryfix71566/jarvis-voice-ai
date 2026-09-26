"""Orchestrator: the Supervisor brain (plan Phase 2 step 2.3, Phase 3 step 3.3).

Text-level LLM conversation loop with OpenAI-style function calling.
Two modes (constructor param ``mode``):
- "direct" (Phase 2): the Supervisor calls MCP tools itself.
- "delegating" (Phase 3, default): the Supervisor's only tool is
  delegate_task, backed by the sub-agent roster from config/agents.yaml.

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

import inspect
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

from openai import AsyncOpenAI

from jarvis.agents.base import SubAgent, load_sub_agents
from jarvis.agents.base import _assistant_message as _base_assistant_message
from jarvis.agents.delegate import build_delegate_tool
from jarvis.db import get_conn, now_iso
from jarvis.model_catalog import render_model_catalog
from jarvis.prompts import build_supervisor_prompt, render_agent_catalog
from jarvis.memory import render_memory_context
from jarvis.bot.sensitive_turn import arm_from_text, is_sensitive
from jarvis.usage_ledger import record_completion, provider_from_base_url
from jarvis.voice_workflows import (
    TOMBSTONE,
    correction_note,
    is_capability_question,
    is_explicit_command_ask,
    log_capability_gap,
    match_voice_workflow,
    normalize_guard_mode,
    render_guidance,
    reply_violations,
    wrap_delegate_handler,
)

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
        mode: Literal["direct", "delegating"] = "delegating",
        sub_agents: dict[str, SubAgent] | None = None,
        agents_config: str | Path | None = None,
        on_event: Callable[[dict], None] | None = None,
        extra_tools: Sequence[tuple[dict, Callable[[dict], Any]]] | None = None,
        voice_catalog: str | None = None,
        voice: bool = False,
        ui_control: bool = False,
        screen: bool = False,
        clipboard: bool = False,
        status: bool = False,
    ):
        self._settings = settings
        self._registry = registry
        self._on_event = on_event
        self._session_id = session_id
        self._allowed_servers = allowed_servers
        self._temperature = temperature
        self._mode = mode
        # MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item C. Until now delegating
        # mode showed the model exactly one tool, so the routing eval that
        # drives this class scored every decision in a world where
        # delegating was the only thing on offer -- production shows ten.
        # Schema and handler travel as a pair so a caller cannot show a tool
        # it cannot answer. Empty is the default and reproduces the old
        # behaviour exactly; tests/unit/test_orchestrator.py's
        # test_only_delegate_tool_is_offered pins that.
        self._extra_tools = list(extra_tools or ())
        if self._extra_tools and mode != "delegating":
            raise ValueError(
                "extra_tools is only meaningful in delegating mode; in direct "
                "mode the registry supplies the tool list"
            )
        self._extra_handlers: dict[str, Callable[[dict], Any]] = {}
        for schema, handler in self._extra_tools:
            tool_name = schema["function"]["name"]
            if tool_name == "delegate_task":
                # Silently shadowing delegation would make a routing eval
                # score the shadow and report it as delegation.
                raise ValueError("extra_tools may not redefine delegate_task")
            if tool_name in self._extra_handlers:
                raise ValueError(f"duplicate tool in extra_tools: {tool_name!r}")
            self._extra_handlers[tool_name] = handler
        if client_factory is not None:
            self._client = client_factory(settings)
        else:
            self._client = AsyncOpenAI(
                api_key=settings.openai_api_key, base_url=settings.openai_base_url
            )
        if mode == "delegating":
            if sub_agents is None:
                sub_agents = load_sub_agents(
                    settings, registry, agents_config, client_factory
                )
            self._sub_agents = sub_agents
            self._delegate_schema, self._delegate_handler = build_delegate_tool(
                sub_agents, on_event=on_event
            )
            agent_catalog = render_agent_catalog([
                {"name": a.name, "display_name": a.display_name,
                 "description": a.description}
                for a in sub_agents.values()
            ])
        else:
            self._sub_agents = None
            self._delegate_schema = None
            self._delegate_handler = None
            # Phase 2 direct mode (plan step 2.3 / Appendix A.4).
            agent_catalog = "(none yet — call tools directly)"
        # Defaults reproduce the bare SUPERVISOR_PROMPT this line has
        # always produced, byte for byte. The flags exist so the routing
        # eval can ask for the configuration production actually ships
        # (MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item D) instead of scoring a
        # prompt carrying none of the four addenda. cli.py passes nothing
        # and is unaffected.
        self._system_prompt = build_supervisor_prompt(
            jarvis_name=settings.jarvis_name,
            user_name=settings.jarvis_user_name,
            timezone=settings.jarvis_timezone,
            units=settings.jarvis_units,
            agent_catalog=agent_catalog,
            model_catalog=render_model_catalog(),
            voice_catalog=(voice_catalog if voice_catalog is not None
                           else "(none configured yet)"),
            memory_context=render_memory_context(),  # U2.5 persistent memory
            voice=voice,
            ui_control=ui_control,
            screen=screen,
            clipboard=clipboard,
            # Phase 2 D4: the system_status addendum, so the voice-workflow
            # eval can score location questions against what ships.
            status=status,
        )
        self._history: list[dict] = []
        # MORTIMER_VOICE_WORKFLOWS_PLAN.md D15 — the same three hooks
        # pipeline.py runs, so the routing and voice-workflow evals score
        # what ships. getattr defaults are OFF so a bare settings object
        # (tests/unit/test_orchestrator.py make_settings) keeps the pre-plan
        # behaviour byte for byte; load_settings() defaults are ON.
        self._voice_enabled = bool(getattr(settings, "jarvis_voice_workflows_enabled", False))
        self._guard_mode = normalize_guard_mode(
            getattr(settings, "jarvis_reply_guard_mode", "off"))
        self._voice_notes: list[dict] = []
        if self._voice_enabled and self._delegate_handler is not None:
            self._delegate_handler = wrap_delegate_handler(
                self._delegate_handler, session_id=session_id,
                is_sensitive=is_sensitive,
            )

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
        arm_from_text(user_text)               # T4a K3 (P4)
        if not is_sensitive():
            self._persist("user", user_text)

        # MORTIMER_VOICE_WORKFLOWS_PLAN.md D15 — user hook, same rule as
        # VoiceWorkflowInjector: tombstone last turn's notes, then inject.
        for note in self._voice_notes:
            note["content"] = TOMBSTONE
        self._voice_notes.clear()
        if self._voice_enabled:
            wf = match_voice_workflow(user_text=user_text)
            if wf is not None:
                note = {"role": "user", "content": render_guidance(wf)}
                self._history.append(note)
                self._voice_notes.append(note)
                logger.info("voice_workflow_injected hook=user name=%s", wf.name)

        reply, tool_calls_total = await self._tool_loop()

        # D15 — reply guard, same rule as ReplyGuard at whole-reply
        # granularity: one correction per turn; the rejected reply never
        # enters history; a second violation is returned and logged.
        if self._guard_mode != "off" and not is_capability_question(user_text):
            # D-L5 — on a turn where Larry explicitly asked for a command, a
            # hand-off sentence is what he asked for; refusals still count.
            asked = is_explicit_command_ask(user_text)

            def _violations(text: str) -> list[tuple[str, str]]:
                return [v for v in reply_violations(text)
                        if not (asked and v[1] == "handoff")]

            violations = _violations(reply)
            if violations and self._guard_mode == "log":
                logger.info("reply_guard action=logged kind=%s", violations[0][1])
            elif violations:
                sentence, kind = violations[0]
                logger.info("reply_guard action=suppressed kind=%s", kind)
                note = {"role": "user", "content": correction_note(
                    kind, sentence, match_voice_workflow(reply_kinds=[kind]))}
                self._history.append(note)
                self._voice_notes.append(note)
                reply, more_calls = await self._tool_loop()
                tool_calls_total += more_calls
                again = _violations(reply)
                if again:
                    logger.info("reply_guard action=allowed_after_retry kind=%s", again[0][1])
                    log_capability_gap(
                        source="reply_guard", kind=again[0][1], text=again[0][0],
                        user_text=user_text, session_id=self._session_id,
                        sensitive=is_sensitive(),
                    )

        self._history.append({"role": "assistant", "content": reply})
        arm_from_text(reply)                    # T4a K3 (P5), review F2
        if not is_sensitive():
            self._persist("assistant", reply)
        self._trim_history()
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "turn_complete user_len=%d latency_ms=%d tool_calls=%d",
            len(user_text), latency_ms, tool_calls_total,
        )
        return reply

    async def _tool_loop(self) -> tuple[str, int]:
        """One completion/tool loop — moved verbatim out of chat()
        (MORTIMER_VOICE_WORKFLOWS_PLAN.md D15) so the reply guard can
        run it a second time. Returns (reply, tool calls made)."""
        tool_calls_total = 0
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
            # 2026-09-01 (MORTIMER_OPTIMIZATION_PLAN.md Phase 0, step 1 of
            # the readiness checklist — supervisor-only first, before the
            # other 12 sites). Inside the tool-iteration loop deliberately:
            # every round is a real billed completion, not just the final
            # one that breaks the loop. Never raises — cost logging must
            # never break a live voice turn.
            try:
                record_completion(
                    rung="supervisor",
                    provider=provider_from_base_url(str(self._client.base_url)),
                    model=self._settings.openai_model,
                    response=response,
                    session_id=self.session_id,
                )
            except Exception:
                pass
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
                result = await self._execute_tool(
                    tool_call.function.name, arguments
                )
                self._history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        return reply, tool_calls_total

    def _messages(self) -> list[dict]:
        return [{"role": "system", "content": self._system_prompt}, *self._history]

    def _emit_event(self, payload: dict) -> None:
        """Notify the observer, if any. An observer never breaks a turn."""
        if self._on_event is None:
            return
        try:
            self._on_event(payload)
        except Exception:  # noqa: BLE001 — observation is never load-bearing
            logger.exception("on_event handler raised")

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        # Nothing observed the Supervisor's OWN tool calls before this:
        # on_event reached only build_delegate_tool, so a turn that called
        # some other tool instead of delegating left no trace anywhere.
        # agent_tool is the sub-agents' event (jarvis/agents/base.py) and
        # does not fire when nothing is delegated, which is exactly the
        # case worth seeing.
        self._emit_event({"type": "supervisor_tool", "tool": name})
        if self._mode == "delegating":
            if name == "delegate_task":
                return await self._delegate_handler(arguments)
            handler = self._extra_handlers.get(name)
            if handler is not None:
                result = handler(arguments)
                if inspect.isawaitable(result):
                    result = await result
                return result
            return f"Unknown tool '{name}'. Use delegate_task."
        return await self._registry.call(name, arguments, self._allowed_servers)

    def _tools_kwarg(self) -> dict:
        if self._mode == "delegating":
            return {"tools": [self._delegate_schema,
                              *(schema for schema, _ in self._extra_tools)]}
        tools = self._registry.openai_tools(self._allowed_servers)
        return {"tools": tools} if tools else {}

    @staticmethod
    def _assistant_message(message: Any) -> dict:
        # One implementation with SubAgent's loop (jarvis/agents/base.py) —
        # both replay tool-call history, and both must round-trip vendor
        # extras (Gemini thought signatures) or the next request 400s.
        return _base_assistant_message(message)

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
