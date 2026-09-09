"""Unit tests for SkillRegistry's GL9 run_id injection (MORTIMER_GRAPH_LAYER_
PLAN.md §5 step 11(e), contract G2). Builds the registry without starting
any real MCP servers — only config parsing, then fakes _sessions/_tools
directly, since call()/openai_tools() never touch process spawning."""

from __future__ import annotations

import pytest

from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger
from jarvis.skills.registry import REPO_ROOT, SkillRegistry


class _Content:
    text = '{"ok": true}'


class _Result:
    isError = False
    content = [_Content()]
    structuredContent = None


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return _Result()


class FakeTool:
    def __init__(self, name, schema):
        self.name, self.description, self.inputSchema = name, "", schema


@pytest.fixture()
def reg():
    r = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")   # parses config only
    r._sessions = {"mcp-selfedit": FakeSession()}
    r._tools = {
        "selfedit_start": ("mcp-selfedit", FakeTool("selfedit_start", {
            "type": "object",
            "properties": {"goal": {"type": "string"}, "run_id": {"type": "string"}},
            "required": ["goal", "run_id"],
        })),
        "plan_status": ("mcp-selfedit", FakeTool("plan_status", {
            "type": "object", "properties": {"run_id": {"type": "string"}},
        })),
    }
    return r


async def test_call_overwrites_model_supplied_run_id(reg):
    with run_logger_scope(RunLogger("abc", "developer", "Developer", "t", enabled=False)):
        await reg.call("selfedit_start", {"goal": "g", "run_id": "evil"})
    session = reg._sessions["mcp-selfedit"]
    assert session.calls[-1] == ("selfedit_start", {"goal": "g", "run_id": "abc"})


async def test_call_outside_run_sends_empty_string(reg):
    await reg.call("selfedit_start", {"goal": "g", "run_id": "evil"})
    session = reg._sessions["mcp-selfedit"]
    assert session.calls[-1] == ("selfedit_start", {"goal": "g", "run_id": ""})


async def test_tool_not_in_set_untouched(reg):
    await reg.call("plan_status", {"run_id": "keep"})
    session = reg._sessions["mcp-selfedit"]
    assert session.calls[-1] == ("plan_status", {"run_id": "keep"})


async def test_openai_tools_strips_run_id_property_and_required(reg):
    schemas = {s["function"]["name"]: s["function"] for s in reg.openai_tools()}
    start_params = schemas["selfedit_start"]["parameters"]
    assert "run_id" not in start_params["properties"]
    assert start_params["required"] == ["goal"]

    status_params = schemas["plan_status"]["parameters"]
    assert "run_id" in status_params["properties"]

    # Deep copy — the original tool schema objects are untouched.
    original = reg._tools["selfedit_start"][1].inputSchema
    assert "run_id" in original["properties"]
    assert original["required"] == ["goal", "run_id"]
