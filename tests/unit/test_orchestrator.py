"""Unit tests for jarvis/agents/supervisor.py (Orchestrator) using a
scripted FakeLLM double — deterministic, no network."""

import json
import sqlite3
from types import SimpleNamespace

import pytest

from jarvis.agents.supervisor import (
    MAX_HISTORY_MESSAGES,
    STUCK_MESSAGE,
    Orchestrator,
)


def make_settings():
    return SimpleNamespace(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_name="Jarvis",
        jarvis_user_name="Boss",
        jarvis_timezone="America/New_York",
        jarvis_units="imperial",
    )


class FakeCompletions:
    """Serves scripted actions; repeats the last action if exhausted."""

    def __init__(self, script):
        self._script = list(script)
        self.requests = []

    async def create(self, *, model, messages, temperature=None, tools=None):
        self.requests.append({"messages": messages, "tools": tools,
                              "temperature": temperature})
        action = self._script.pop(0) if self._script else self._last
        self._last = action
        kind = action[0]
        if kind == "text":
            message = SimpleNamespace(content=action[1], tool_calls=None)
        else:  # ("tool", name, arguments) — arguments dict or raw string
            raw = action[2] if isinstance(action[2], str) else json.dumps(action[2])
            tool_call = SimpleNamespace(
                id=f"call_{len(self.requests)}",
                type="function",
                function=SimpleNamespace(name=action[1], arguments=raw),
            )
            message = SimpleNamespace(content=None, tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    _last = ("text", "fallback")


class FakeLLM:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def openai_tools(self, server_names=None):
        return [{
            "type": "function",
            "function": {"name": "fake_tool", "description": "d",
                         "parameters": {"type": "object", "properties": {}}},
        }]

    async def call(self, name, arguments, server_names=None):
        self.calls.append((name, arguments))
        return '{"ok": true}'

    def tools_for(self, server_names):
        return ["fake_tool"]


def make_orchestrator(script, registry=None, mode="direct", **kwargs):
    fake = FakeLLM(script)
    orch = Orchestrator(
        make_settings(),
        registry or FakeRegistry(),
        session_id="test-session",
        client_factory=lambda settings: fake,
        mode=mode,
        **kwargs,
    )
    return orch, fake.chat.completions


class TestSimpleReply:
    async def test_text_reply_and_history(self, fresh_db):
        orch, completions = make_orchestrator([("text", "Good afternoon, Boss.")])
        reply = await orch.chat("hello")
        assert reply == "Good afternoon, Boss."
        roles = [m["role"] for m in orch.history]
        assert roles == ["user", "assistant"]

    async def test_tools_passed_and_system_prompt_first(self, fresh_db):
        orch, completions = make_orchestrator([("text", "ok")])
        await orch.chat("hi")
        request = completions.requests[0]
        assert request["messages"][0]["role"] == "system"
        assert "Jarvis" in request["messages"][0]["content"]
        assert request["tools"][0]["function"]["name"] == "fake_tool"
        assert request["temperature"] is None  # D-003: omitted by default

    async def test_temperature_forwarded_when_set(self, fresh_db):
        orch, completions = make_orchestrator([("text", "ok")], temperature=0.7)
        await orch.chat("hi")
        assert completions.requests[0]["temperature"] == 0.7


class TestToolLoop:
    async def test_tool_call_executes_and_result_appended(self, fresh_db):
        registry = FakeRegistry()
        orch, completions = make_orchestrator([
            ("tool", "get_current_time", {}),
            ("text", "It is 3 PM."),
        ], registry=registry)
        reply = await orch.chat("what time is it")
        assert reply == "It is 3 PM."
        assert registry.calls == [("get_current_time", {})]
        roles = [m["role"] for m in orch.history]
        assert roles == ["user", "assistant", "tool", "assistant"]
        tool_message = orch.history[2]
        assert tool_message["content"] == '{"ok": true}'
        assert tool_message["tool_call_id"] == "call_1"
        # Second request must include the tool result message.
        second = completions.requests[1]["messages"]
        assert any(m.get("role") == "tool" for m in second)

    async def test_iteration_cap_returns_stuck_message(self, fresh_db):
        registry = FakeRegistry()
        orch, completions = make_orchestrator([("tool", "fake_tool", {})],
                                              registry=registry)
        reply = await orch.chat("loop forever")
        assert reply == STUCK_MESSAGE
        assert len(completions.requests) == 6  # MAX_TOOL_ITERATIONS

    async def test_malformed_arguments_become_empty_dict(self, fresh_db):
        registry = FakeRegistry()
        orch, _ = make_orchestrator([
            ("tool", "fake_tool", "{not valid json"),
            ("text", "done"),
        ], registry=registry)
        await orch.chat("go")
        assert registry.calls == [("fake_tool", {})]


class TestHistoryManagement:
    async def test_trim_to_40_and_no_leading_tool_message(self, fresh_db):
        orch, _ = make_orchestrator([("text", "ok")])
        orch._history = (
            [{"role": "tool", "tool_call_id": "x", "content": "orphan"}]
            + [{"role": "user", "content": f"m{i}"} for i in range(45)]
        )
        await orch.chat("new message")
        assert len(orch.history) <= MAX_HISTORY_MESSAGES
        assert orch.history[0]["role"] != "tool"

    async def test_reset_clears_history_and_session(self, fresh_db):
        orch, _ = make_orchestrator([("text", "ok")])
        await orch.chat("hi")
        assert orch.session_id == "test-session"
        orch.reset("new-session")
        assert orch.session_id == "new-session"
        assert orch.history == []


class TestPersistence:
    async def test_user_and_assistant_rows_written(self, fresh_db):
        from jarvis.db import get_conn

        orch, _ = make_orchestrator([("text", "stored reply")])
        await orch.chat("stored question")
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM conversations WHERE session_id = ? "
                "ORDER BY id",
                ("test-session",),
            ).fetchall()
        assert [(r["role"], r["content"]) for r in rows] == [
            ("user", "stored question"),
            ("assistant", "stored reply"),
        ]


class FakeSubAgent:
    """Stands in for SubAgent in delegating-mode tests."""

    def __init__(self, name, result="done", model="fake-model",
                 model_is_fallback=False, override_model="fake-override-model",
                 override_refused=""):
        self.name = name
        self.display_name = name.title()
        self.description = f"{name} things."
        self.mcp_servers = []
        self.result = result
        self.tasks = []
        self.run_kwargs: list[dict] = []
        # Part of SubAgent's public surface since 2026-08-19 —
        # delegate_start reads both so the Agents tab card can show which
        # LLM did the work. Kept as plain attributes rather than
        # properties: the fake only has to answer, not resolve.
        self.model = model
        self.model_is_fallback = model_is_fallback
        # K4: a resolved-but-refused credential. Default False — the
        # measurement is absent in tests, and absent is not unusable.
        self.model_unusable = False
        self.model_unusable_detail = ""
        # F6/F7 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md) — stands in
        # for SubAgent.resolve_model_profile. Set override_refused (a
        # non-empty string) to simulate an unresolvable named request.
        self.override_model = override_model
        self.override_refused = override_refused

    def resolve_model_profile(self, profile_name):
        if self.override_refused:
            return None, "", self.override_refused
        return object(), self.override_model, ""

    async def run(self, task, on_event=None, **kwargs):
        self.tasks.append(task)
        self.run_kwargs.append(kwargs)
        return self.result


def make_delegating(script, sub_agents=None, **kwargs):
    if sub_agents is None:
        sub_agents = {n: FakeSubAgent(n)
                      for n in ("scheduler", "librarian", "analyst", "systems")}
    return make_orchestrator(script, mode="delegating",
                             sub_agents=sub_agents, **kwargs)


class TestDelegatingMode:
    async def test_only_delegate_tool_is_offered(self, fresh_db):
        orch, completions = make_delegating([("text", "ok")])
        await orch.chat("hi")
        tools = completions.requests[0]["tools"]
        assert [t["function"]["name"] for t in tools] == ["delegate_task"]

    async def test_system_prompt_lists_agent_catalog(self, fresh_db):
        orch, completions = make_delegating([("text", "ok")])
        await orch.chat("hi")
        system = completions.requests[0]["messages"][0]["content"]
        assert "- scheduler (Scheduler): scheduler things." in system
        assert "- systems (Systems): systems things." in system

    async def test_delegate_call_routes_to_subagent(self, fresh_db):
        agents = {n: FakeSubAgent(n) for n in ("scheduler", "librarian")}
        orch, _ = make_delegating(
            [("tool", "delegate_task",
              {"agent_name": "scheduler", "task": "what time is it"}),
             ("text", "It is 3 PM, Boss.")],
            sub_agents=agents,
        )
        reply = await orch.chat("what time is it")
        assert agents["scheduler"].tasks == ["what time is it"]
        assert reply == "It is 3 PM, Boss."
        roles = [m["role"] for m in orch.history]
        assert roles == ["user", "assistant", "tool", "assistant"]

    async def test_unknown_tool_name_gets_plain_error(self, fresh_db):
        orch, _ = make_delegating(
            [("tool", "get_time", {}), ("text", "recovered")])
        reply = await orch.chat("hi")
        tool_msg = orch.history[2]
        assert tool_msg["role"] == "tool"
        assert "Unknown tool 'get_time'" in tool_msg["content"]
        assert reply == "recovered"
