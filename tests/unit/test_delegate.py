"""Unit tests for jarvis/agents/delegate.py (plan Phase 3 Tests)."""

import pytest
import yaml

from jarvis.agents.delegate import build_delegate_tool
from jarvis.prompts import render_agent_catalog

from tests.unit.test_orchestrator import FakeSubAgent

AGENTS = {n: FakeSubAgent(n)
          for n in ("scheduler", "librarian", "analyst", "systems", "developer")}


class TestSchema:
    def test_schema_matches_locked_spec(self):
        schema, _ = build_delegate_tool(AGENTS)
        fn = schema["function"]
        assert schema["type"] == "function"
        assert fn["name"] == "delegate_task"
        assert "self-contained" in fn["description"]
        props = fn["parameters"]["properties"]
        assert props["agent_name"]["enum"] == [
            "scheduler", "librarian", "analyst", "systems", "developer"]
        assert fn["parameters"]["required"] == ["agent_name", "task"]


class TestHandler:
    async def test_routes_to_named_agent_and_returns_result(self):
        agents = {**AGENTS}
        _, handler = build_delegate_tool(agents)
        result = await handler({"agent_name": "scheduler", "task": "set alarm"})
        assert result == "done"
        assert agents["scheduler"].tasks == ["set alarm"]

    async def test_unknown_agent_returns_plain_error(self):
        _, handler = build_delegate_tool(AGENTS)
        result = await handler({"agent_name": "chef", "task": "cook"})
        assert result == ("Unknown agent 'chef'. Available: "
                          "scheduler, librarian, analyst, systems, developer.")

    async def test_events_forwarded(self):
        events = []
        _, handler = build_delegate_tool(AGENTS, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        types = [e["type"] for e in events]
        assert types[0] == "delegate_start"
        assert types[-1] == "delegate_done"
        assert events[0]["agent"] == "analyst"

    async def test_delegate_done_marks_success(self):
        events = []
        _, handler = build_delegate_tool(AGENTS, on_event=events.append)
        await handler({"agent_name": "analyst", "task": "weather"})
        done = events[-1]
        assert done["ok"] is True
        assert done["detail"] == ""

    async def test_delegate_done_marks_failure_with_detail(self):
        agents = {"analyst": FakeSubAgent("analyst", result="FAILED: web_search down")}
        events = []
        _, handler = build_delegate_tool(agents, on_event=events.append)
        result = await handler({"agent_name": "analyst", "task": "news"})
        assert result.startswith("FAILED:")
        done = events[-1]
        assert done["type"] == "delegate_done"
        assert done["ok"] is False
        assert done["detail"] == "FAILED: web_search down"


class TestAgentsYaml:
    def test_repo_agents_yaml_matches_locked_schema(self):
        from pathlib import Path

        path = (Path(__file__).resolve().parents[2]
                / "config" / "agents.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries = data["sub_agents"]
        assert [e["name"] for e in entries] == [
            "scheduler", "librarian", "analyst", "systems", "developer"]
        for e in entries:
            assert e["display_name"] and e["description"]
            assert e["mcp_servers"], e["name"]
        assert entries[0]["mcp_servers"] == ["mcp-time", "mcp-reminders"]

    def test_catalog_rendering_format(self):
        catalog = render_agent_catalog([
            {"name": "scheduler", "display_name": "Scheduler",
             "description": "Time stuff."}])
        assert catalog == "- scheduler (Scheduler): Time stuff."
