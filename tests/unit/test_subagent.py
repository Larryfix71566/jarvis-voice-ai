"""Unit tests for jarvis/agents/base.py (SubAgent) — scripted FakeLLM,
deterministic, no network (plan Phase 3 Tests)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from jarvis.agents.base import (
    STUCK_MESSAGE,
    TIMEOUT_MESSAGE,
    SubAgent,
    load_sub_agents,
)


def make_settings():
    return SimpleNamespace(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_timezone="America/New_York",
    )


class FakeCompletions:
    def __init__(self, script):
        self._script = list(script)
        self.requests = []

    async def create(self, *, model, messages, tools=None):
        self.requests.append({"messages": messages, "tools": tools})
        action = self._script.pop(0) if self._script else self._last
        self._last = action
        if action[0] == "sleep":
            await asyncio.sleep(action[1])
            action = ("text", "late")
        if action[0] == "text":
            message = SimpleNamespace(content=action[1], tool_calls=None)
        else:
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
        self.calls.append((name, arguments, server_names))
        return '{"ok": true}'


def make_agent(script, registry=None, name="scheduler", **kwargs):
    fake = FakeLLM(script)
    agent = SubAgent(
        name=name,
        display_name=name.title(),
        description="d",
        mcp_servers=["mcp-time"],
        settings=make_settings(),
        registry=registry or FakeRegistry(),
        client_factory=lambda settings: fake,
        **kwargs,
    )
    return agent, fake.chat.completions


class TestSubAgentLoop:
    async def test_plain_text_reply(self):
        agent, _ = make_agent([("text", "It is 3 PM.")])
        assert await agent.run("what time") == "It is 3 PM."

    async def test_tool_call_executes_scoped_to_own_servers(self):
        registry = FakeRegistry()
        agent, completions = make_agent(
            [("tool", "get_time", {}), ("text", "It is 3 PM.")],
            registry=registry,
        )
        reply = await agent.run("what time")
        assert reply == "It is 3 PM."
        assert registry.calls == [("get_time", {}, ["mcp-time"])]
        assert completions.requests[0]["tools"][0]["function"]["name"] == "fake_tool"

    async def test_iteration_cap_returns_stuck(self):
        agent, _ = make_agent([("tool", "fake_tool", {})])
        reply = await agent.run("loop forever")
        assert reply == STUCK_MESSAGE

    async def test_timeout_returns_failed_message(self):
        agent, _ = make_agent([("sleep", 5.0)], timeout_s=0.05)
        assert await agent.run("slow task") == TIMEOUT_MESSAGE

    async def test_events_emitted_in_order(self):
        agent, _ = make_agent(
            [("tool", "fake_tool", {"q": 1}), ("text", "done")])
        events = []
        await agent.run("task", on_event=events.append)
        assert [e["type"] for e in events] == [
            "agent_start", "agent_tool", "agent_tool_result", "agent_done"]
        assert events[0]["task"] == "task"
        assert events[1]["tool"] == "fake_tool"
        assert events[2]["tool"] == "fake_tool"
        assert events[2]["arguments"] == {"q": 1}
        assert events[2]["result"] == '{"ok": true}'

    async def test_tool_result_event_truncates_long_results(self):
        class LongRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                return "x" * 50_000

        agent, _ = make_agent(
            [("tool", "fake_tool", {}), ("text", "done")],
            registry=LongRegistry(),
        )
        events = []
        await agent.run("task", on_event=events.append)
        result_event = next(e for e in events if e["type"] == "agent_tool_result")
        assert len(result_event["result"]) == 20_000

    async def test_client_exception_returns_failed(self):
        class Boom:
            async def create(self, **kwargs):
                raise RuntimeError("api down")

        agent, _ = make_agent([("text", "unused")])
        agent._client = SimpleNamespace(
            chat=SimpleNamespace(completions=Boom()))
        reply = await agent.run("task")
        assert reply.startswith("FAILED:")

    async def test_system_prompt_from_appendix_a(self):
        agent, completions = make_agent([("text", "ok")], name="librarian")
        await agent.run("hi")
        system = completions.requests[0]["messages"][0]["content"]
        assert system.startswith("You are the Librarian")
        assert "America/New_York" not in system  # librarian prompt has no tz


class TestLoadSubAgents:
    def test_loads_roster_from_repo_yaml(self):
        agents = load_sub_agents(make_settings(), FakeRegistry(),
                                 client_factory=lambda s: FakeLLM([]))
        assert set(agents) == {"scheduler", "librarian", "analyst", "systems", "developer"}
        assert agents["scheduler"].mcp_servers == ["mcp-time", "mcp-reminders"]
        assert agents["analyst"].display_name == "Analyst"
