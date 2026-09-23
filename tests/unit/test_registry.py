"""Unit tests for jarvis/skills/registry.py — spawn-free, using fake
sessions/tools. Process-spawning coverage lives in tests/integration."""

import json
from types import SimpleNamespace

import pytest

from jarvis.skills.registry import SkillRegistry


def make_tool(name, server, description="desc", schema=None):
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=schema or {"type": "object", "properties": {}},
    )


def make_registry() -> SkillRegistry:
    registry = SkillRegistry(config_path="unused.yaml")
    registry._tools = {
        "get_current_time": ("mcp-time", make_tool("get_current_time", "mcp-time")),
        "create_note": ("mcp-notes", make_tool("create_note", "mcp-notes")),
    }
    return registry


def make_external_registry() -> SkillRegistry:
    registry = SkillRegistry(config_path="unused.yaml")
    registry._tools = {
        "web_search": ("mcp-web", make_tool("web_search", "mcp-web")),
    }
    return registry


class TestOpenaiTools:
    def test_converts_to_function_schema(self):
        tools = make_registry().openai_tools()
        by_name = {t["function"]["name"]: t for t in tools}
        assert set(by_name) == {"get_current_time", "create_note"}
        assert by_name["get_current_time"]["type"] == "function"
        assert by_name["get_current_time"]["function"]["parameters"]["type"] == "object"

    def test_server_filter(self):
        registry = make_registry()
        tools = registry.openai_tools(["mcp-time"])
        assert [t["function"]["name"] for t in tools] == ["get_current_time"]

    def test_tools_for(self):
        registry = make_registry()
        assert registry.tools_for(["mcp-notes"]) == ["create_note"]
        assert registry.tools_for(["mcp-time", "mcp-notes"]) == [
            "get_current_time", "create_note",
        ]
        assert registry.tools_for(["mcp-system"]) == []


class FakeSession:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self._exc:
            raise self._exc
        return self._result


def ok_result(structured=None, text="plain text"):
    return SimpleNamespace(
        isError=False,
        structuredContent=structured,
        content=[SimpleNamespace(text=text)],
    )


class TestCall:
    async def test_unknown_tool_lists_available(self):
        result = await make_registry().call("nope", {})
        assert "Unknown tool 'nope'" in result
        assert "get_current_time" in result

    async def test_structured_content_serialized(self):
        registry = make_registry()
        session = FakeSession(result=ok_result(structured={"iso": "2026-08-04"}))
        registry._sessions = {"mcp-time": session}
        result = await registry.call("get_current_time", {})
        assert json.loads(result) == {"iso": "2026-08-04"}
        assert session.calls == [("get_current_time", {})]

    async def test_text_fallback_when_no_structured(self):
        registry = make_registry()
        registry._sessions = {"mcp-time": FakeSession(result=ok_result(text="hi"))}
        assert await registry.call("get_current_time", {}) == "hi"

    async def test_iserror_result_becomes_failure_string(self):
        registry = make_registry()
        result = SimpleNamespace(
            isError=True, structuredContent=None,
            content=[SimpleNamespace(text="boom")],
        )
        registry._sessions = {"mcp-time": FakeSession(result=result)}
        assert await registry.call("get_current_time", {}) == "get_current_time failed: boom"

    async def test_exception_becomes_failure_string(self):
        registry = make_registry()
        registry._sessions = {"mcp-time": FakeSession(exc=RuntimeError("crash"))}
        result = await registry.call("get_current_time", {})
        assert result == "get_current_time failed: RuntimeError."

    async def test_server_scope_restriction(self):
        registry = make_registry()
        result = await registry.call("create_note", {}, server_names=["mcp-time"])
        assert "not available" in result

    async def test_sensitive_turn_blocks_external_mcp_server_before_invocation(self):
        from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn

        registry = make_external_registry()
        session = FakeSession(result=ok_result(structured={"results": []}))
        registry._sessions = {"mcp-web": session}
        holder = SensitiveTurn()
        holder.arm("financial")
        token = current_sensitive_turn.set(holder)
        try:
            result = await registry.call("web_search", {"query": "private"})
        finally:
            current_sensitive_turn.reset(token)

        assert "protected turn" in result
        assert session.calls == []

    async def test_timeout_becomes_failure_string(self, monkeypatch):
        registry = make_registry()

        async def slow(*a, **k):
            import asyncio
            await asyncio.sleep(60)

        session = FakeSession()
        session.call_tool = slow
        registry._sessions = {"mcp-time": session}
        monkeypatch.setattr("jarvis.skills.registry.CALL_TIMEOUT", 0.01)
        result = await registry.call("get_current_time", {})
        assert "timed out" in result
