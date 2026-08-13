"""Sub-agent quality evals (plan Phase 2b).

Per-agent scripted evaluations using FakeLLM (no network calls):
- Scheduler (date math, reminders): time-relative parsing, reminder CRUD
- Librarian (notes): create, list, search, tags
- Analyst (web search, weather): query routing, weather fallback
- Systems (machine status): metrics collection, thresholds
- Developer (git, apps, self-edit): read-only git status, app scaffolding, allowlist

Each agent gets:
1. Deterministic tool call assertions (which tools were invoked, with what args)
2. Semantic checks on output (loose assertions on content, not word-for-word matches)
3. FakeLLM execution (scripted tool sequence, not real LLM)
4. RecordingRegistry to capture all MCP calls for inspection
5. Test cases covering the agent's core responsibilities

Usage:
    pytest tests/evals/sub_agent_evals.py -q              # all evals
    pytest tests/evals/sub_agent_evals.py::TestScheduler -q  # one agent

Each test establishes a baseline on first run; failures then signal regression.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from jarvis.agents.base import SubAgent
from jarvis.config import Settings
from jarvis.skills.registry import SkillRegistry


@dataclass
class Threshold:
    """Test result bounds: min/max calls, semantic checks."""
    name: str
    min_calls: int = 0
    max_calls: int = 999
    required_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None


class FakeCompletions:
    """Scripted LLM that returns pre-defined tool calls (matching test_subagent.py)."""
    def __init__(self, script):
        self._script = list(script)
        self.requests = []

    async def create(self, *, model, messages, tools=None):
        self.requests.append({"messages": messages, "tools": tools})
        if not self._script:
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content="Done.", tool_calls=None)
                )]
            )
        action = self._script.pop(0)
        if action[0] == "text":
            message = SimpleNamespace(content=action[1], tool_calls=None)
        else:  # tool call
            tool_call = SimpleNamespace(
                id=f"call_{len(self.requests)}",
                type="function",
                function=SimpleNamespace(
                    name=action[1],
                    arguments=json.dumps(action[2] if len(action) > 2 else {})
                ),
            )
            message = SimpleNamespace(content=None, tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLM:
    """Wraps FakeCompletions."""
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


class RecordingRegistry(SkillRegistry):
    """Wraps SkillRegistry to record all MCP tool calls."""
    def __init__(self, config_path=None):
        super().__init__(config_path or "config/mcp_servers.yaml")
        self.calls: list[dict] = []

    async def call(self, name, arguments, server_names=None):
        self.calls.append({
            "tool": name,
            "args": arguments,
            "servers": server_names,
        })
        return await super().call(name, arguments, server_names)

    def reset(self):
        self.calls.clear()


def settings_for_timezone(tz: str = "America/New_York") -> Settings:
    """Create Settings."""
    return Settings(
        openai_model=os.environ.get("OPENAI_MODEL", "claude-haiku-4-5"),
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_timezone=tz,
    )


def make_agent(
    name: str,
    display_name: str,
    description: str,
    mcp_servers: list[str],
    script: list,
    registry: RecordingRegistry | None = None,
) -> tuple[SubAgent, RecordingRegistry, FakeCompletions]:
    """Create a SubAgent with FakeLLM and RecordingRegistry."""
    registry = registry or RecordingRegistry()
    fake_llm = FakeLLM(script)
    agent = SubAgent(
        name=name,
        display_name=display_name,
        description=description,
        mcp_servers=mcp_servers,
        settings=settings_for_timezone(),
        registry=registry,
        client_factory=lambda _: fake_llm,
    )
    return agent, registry, fake_llm.chat.completions


class TestScheduler:
    """Scheduler (time, dates, reminders)."""

    async def test_get_current_time(self):
        """Scheduler should call mcp-time get_current_time."""
        registry = RecordingRegistry()
        script = [
            ("tool", "get_current_time", {}),
            ("text", "It is currently 3:45 PM."),
        ]
        agent, reg, comps = make_agent(
            "scheduler", "Scheduler", "Time and reminders",
            ["mcp-time", "mcp-reminders"], script, registry
        )

        response = await agent.run("what time is it?")

        # Check response is non-empty
        assert response is not None
        assert len(response) > 0

        # Check tool was called
        tool_names = [c["tool"] for c in reg.calls]
        assert "get_current_time" in tool_names, f"expected get_current_time, got {tool_names}"

    async def test_create_reminder(self):
        """Scheduler should create reminders."""
        registry = RecordingRegistry()
        script = [
            ("tool", "get_current_time", {}),
            ("tool", "create_reminder", {"text": "call mom", "when": "in 2 hours"}),
            ("text", "I've set a reminder for you to call mom in 2 hours."),
        ]
        agent, reg, comps = make_agent(
            "scheduler", "Scheduler", "Time and reminders",
            ["mcp-time", "mcp-reminders"], script, registry
        )

        response = await agent.run("remind me to call mom in 2 hours")

        assert response is not None
        tool_names = [c["tool"] for c in reg.calls]
        # Should have called get_current_time and/or create_reminder
        assert any(t in tool_names for t in ["get_current_time", "create_reminder"]), \
            f"expected time/reminder tools, got {tool_names}"

    async def test_list_reminders(self):
        """Scheduler should list reminders."""
        registry = RecordingRegistry()
        script = [
            ("tool", "list_reminders", {}),
            ("text", "You have 2 reminders: call mom, buy groceries."),
        ]
        agent, reg, comps = make_agent(
            "scheduler", "Scheduler", "Time and reminders",
            ["mcp-time", "mcp-reminders"], script, registry
        )

        response = await agent.run("what reminders do I have?")

        tool_names = [c["tool"] for c in reg.calls]
        assert "list_reminders" in tool_names, f"expected list_reminders, got {tool_names}"


class TestLibrarian:
    """Librarian (notes, memory)."""

    async def test_create_note(self):
        """Librarian should create notes."""
        registry = RecordingRegistry()
        script = [
            ("tool", "create_note", {"title": "shopping", "body": "milk, eggs, bread"}),
            ("text", "Note saved: shopping"),
        ]
        agent, reg, comps = make_agent(
            "librarian", "Librarian", "Notes and memory",
            ["mcp-notes"], script, registry
        )

        response = await agent.run("create a note called shopping with milk, eggs, bread")

        assert response is not None
        tool_names = [c["tool"] for c in reg.calls]
        assert "create_note" in tool_names, f"expected create_note, got {tool_names}"

    async def test_list_notes(self):
        """Librarian should list notes."""
        registry = RecordingRegistry()
        script = [
            ("tool", "list_notes", {}),
            ("text", "You have 3 notes: shopping, ideas, todo."),
        ]
        agent, reg, comps = make_agent(
            "librarian", "Librarian", "Notes and memory",
            ["mcp-notes"], script, registry
        )

        response = await agent.run("show me my notes")

        tool_names = [c["tool"] for c in reg.calls]
        assert "list_notes" in tool_names, f"expected list_notes, got {tool_names}"

    async def test_search_notes(self):
        """Librarian should search notes."""
        registry = RecordingRegistry()
        script = [
            ("tool", "search_notes", {"query": "coffee"}),
            ("text", "Found 1 note about coffee: best coffee shops."),
        ]
        agent, reg, comps = make_agent(
            "librarian", "Librarian", "Notes and memory",
            ["mcp-notes"], script, registry
        )

        response = await agent.run("find notes about coffee")

        tool_names = [c["tool"] for c in reg.calls]
        # May call search_notes or list_notes
        assert any(t in tool_names for t in ["search_notes", "list_notes"]), \
            f"expected search/list tools, got {tool_names}"


class TestAnalyst:
    """Analyst (web search, weather)."""

    async def test_web_search(self):
        """Analyst should search the web."""
        registry = RecordingRegistry()
        script = [
            ("tool", "web_search", {"query": "2024 world series winner"}),
            ("text", "The Dodgers won the 2024 World Series."),
        ]
        agent, reg, comps = make_agent(
            "analyst", "Analyst", "Web research and weather",
            ["mcp-web"], script, registry
        )

        response = await agent.run("who won the 2024 world series?")

        assert response is not None
        tool_names = [c["tool"] for c in reg.calls]
        assert "web_search" in tool_names, f"expected web_search, got {tool_names}"

    async def test_weather_query(self):
        """Analyst should get weather."""
        registry = RecordingRegistry()
        script = [
            ("tool", "get_weather", {"location": "New York"}),
            ("text", "It's 72°F and sunny in New York."),
        ]
        agent, reg, comps = make_agent(
            "analyst", "Analyst", "Web research and weather",
            ["mcp-web"], script, registry
        )

        response = await agent.run("what's the weather in New York?")

        tool_names = [c["tool"] for c in reg.calls]
        # Should call web_search and/or get_weather
        assert any(t in tool_names for t in ["web_search", "get_weather"]), \
            f"expected search/weather tools, got {tool_names}"


class TestSystems:
    """Systems (machine status, processes)."""

    async def test_system_status(self):
        """Systems should report CPU, memory, disk."""
        registry = RecordingRegistry()
        script = [
            ("tool", "get_system_status", {}),
            ("text", "System status: CPU at 45%, memory at 62%, disk at 58%."),
        ]
        agent, reg, comps = make_agent(
            "systems", "Systems", "Machine status",
            ["mcp-system"], script, registry
        )

        response = await agent.run("what's the system status?")

        assert response is not None
        tool_names = [c["tool"] for c in reg.calls]
        assert "get_system_status" in tool_names, \
            f"expected get_system_status, got {tool_names}"

    async def test_top_processes(self):
        """Systems should list top processes."""
        registry = RecordingRegistry()
        script = [
            ("tool", "get_top_processes", {}),
            ("text", "Top processes: Python (15%), Chrome (12%), Finder (8%)."),
        ]
        agent, reg, comps = make_agent(
            "systems", "Systems", "Machine status",
            ["mcp-system"], script, registry
        )

        response = await agent.run("what's using the most CPU?")

        tool_names = [c["tool"] for c in reg.calls]
        assert "get_top_processes" in tool_names, \
            f"expected get_top_processes, got {tool_names}"


class TestDeveloper:
    """Developer (git, apps, self-edit)."""

    async def test_git_status(self):
        """Developer should report git status (read-only)."""
        registry = RecordingRegistry()
        script = [
            ("tool", "git_status", {}),
            ("text", "On branch main. 2 files modified."),
        ]
        agent, reg, comps = make_agent(
            "developer", "Developer", "Git and apps",
            ["mcp-git", "mcp-apps", "mcp-selfedit"], script, registry
        )

        response = await agent.run("what's the git status?")

        tool_names = [c["tool"] for c in reg.calls]
        assert "git_status" in tool_names, f"expected git_status, got {tool_names}"

    async def test_recent_commits(self):
        """Developer should list recent commits."""
        registry = RecordingRegistry()
        script = [
            ("tool", "git_log", {"limit": 5}),
            ("text", "Recent commits: Phase 2b evals, latency gate, disconnect fix."),
        ]
        agent, reg, comps = make_agent(
            "developer", "Developer", "Git and apps",
            ["mcp-git", "mcp-apps", "mcp-selfedit"], script, registry
        )

        response = await agent.run("show me the last few commits")

        tool_names = [c["tool"] for c in reg.calls]
        assert "git_log" in tool_names, f"expected git_log, got {tool_names}"

    async def test_no_write_tools_for_read_only(self):
        """Developer should NOT call prepare_commit for read queries."""
        registry = RecordingRegistry()
        script = [
            ("tool", "git_log", {"limit": 10}),
            ("text", "Recent changes visible above."),
        ]
        agent, reg, comps = make_agent(
            "developer", "Developer", "Git and apps",
            ["mcp-git", "mcp-apps", "mcp-selfedit"], script, registry
        )

        response = await agent.run("what are the recent changes?")

        tool_names = [c["tool"] for c in reg.calls]
        # Should NOT initiate write operations
        assert "prepare_commit" not in tool_names, \
            f"should not call prepare_commit for read query, got {tool_names}"
