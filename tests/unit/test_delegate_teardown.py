"""Item 11 (2026-09-17) -- a detached delegation outliving its session.

Barge-in survival runs the sub-agent in a task the voice turn's cancellation
cannot reach. Session teardown used to stop the SkillRegistry underneath
that task regardless, so every tool call it made afterwards came back
"Unknown tool ... Available: none." Measured live on 2026-09-16 11:45; the
tests below reproduce it spawn-free and pin the fix.
"""

import asyncio
from types import SimpleNamespace

import pytest

from jarvis.agents.delegate import build_delegate_tool, drain_detached
from jarvis.skills.registry import SkillRegistry


def make_tool(name, server):
    return SimpleNamespace(name=name, description="desc",
                           inputSchema={"type": "object", "properties": {}})


class FakeSession:
    def __init__(self, text):
        self._text = text
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(isError=False, structuredContent=None,
                               content=[SimpleNamespace(text=self._text)])


def make_registry() -> SkillRegistry:
    registry = SkillRegistry(config_path="unused.yaml")
    registry._tools = {
        "get_current_time": ("mcp-time", make_tool("get_current_time", "mcp-time")),
    }
    registry._sessions = {"mcp-time": FakeSession("12:00")}
    return registry


class ToolUsingFakeAgent:
    """Blocks on `gate`, then makes ONE tool call through the registry --
    the shape of a developer run that is mid-investigation when the
    client disconnects."""

    def __init__(self, name, registry, gate):
        self.name = name
        self.display_name = name.title()
        self.description = f"{name} things."
        self.mcp_servers = ["mcp-time"]
        self.model = "fake-model"
        self.model_is_fallback = False
        self.model_unusable = False
        self.model_unusable_detail = ""
        self.registry = registry
        self.gate = gate
        self.tool_result = None

    async def run(self, task, on_event=None, **kwargs):
        await self.gate.wait()
        self.tool_result = await self.registry.call("get_current_time", {})
        return "done: " + self.tool_result


async def _start_and_orphan(agent, in_flight):
    """Delegate, let the run reach its gate, then cancel the voice turn --
    the barge-in path. Returns the detached task."""
    _, handler = build_delegate_tool({agent.name: agent}, in_flight=in_flight)
    turn = asyncio.create_task(handler({"agent_name": agent.name, "task": "look into it"}))
    for _ in range(8):
        await asyncio.sleep(0)
    assert len(in_flight) == 1, "the run is in flight and tracked"
    run_task = next(iter(in_flight))
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    assert not run_task.done(), "the shield kept the work alive past the turn"
    return run_task


class TestDetachedRunTeardown:
    async def test_stopping_the_registry_under_a_detached_run_orphans_its_tools(self):
        """The defect, reproduced. This is what run_session's finally did
        before the drain existed: stop() first, and the surviving run's
        next tool call finds an empty registry."""
        registry = make_registry()
        gate = asyncio.Event()
        agent = ToolUsingFakeAgent("developer", registry, gate)
        in_flight: set = set()
        run_task = await _start_and_orphan(agent, in_flight)

        await registry.stop()              # teardown, with the run still going
        gate.set()
        await asyncio.wait({run_task}, timeout=2.0)

        assert run_task.done()
        assert agent.tool_result.startswith("Unknown tool 'get_current_time'")
        assert "Available: none" in agent.tool_result, (
            "not a hallucinated name -- the registry was emptied under the run")

    async def test_draining_before_stop_lets_the_run_finish_with_its_tools(self):
        """The fix. Teardown waits for the detached run first, so its tool
        call lands on a live registry."""
        registry = make_registry()
        gate = asyncio.Event()
        agent = ToolUsingFakeAgent("developer", registry, gate)
        in_flight: set = set()
        run_task = await _start_and_orphan(agent, in_flight)

        gate.set()                                    # the run can now proceed
        still_running = await drain_detached(in_flight, timeout=2.0)
        await registry.stop()

        assert still_running == 0
        assert run_task.done()
        assert agent.tool_result == "12:00"
        assert registry._sessions == {}, "and the registry did still get torn down"

    async def test_drain_gives_up_at_the_deadline_and_says_how_many_remain(self):
        """A run that will not finish must not hold teardown forever. The
        count is what run_session logs so the failure is attributable."""
        registry = make_registry()
        gate = asyncio.Event()                        # never set
        agent = ToolUsingFakeAgent("developer", registry, gate)
        in_flight: set = set()
        run_task = await _start_and_orphan(agent, in_flight)

        still_running = await drain_detached(in_flight, timeout=0.05)
        assert still_running == 1
        assert not run_task.done()

        gate.set()                                    # clean up
        await asyncio.wait({run_task}, timeout=2.0)

    async def test_a_delegation_that_completes_normally_leaves_nothing_in_flight(self):
        registry = make_registry()
        gate = asyncio.Event()
        gate.set()
        agent = ToolUsingFakeAgent("developer", registry, gate)
        in_flight: set = set()
        _, handler = build_delegate_tool({agent.name: agent}, in_flight=in_flight)

        result = await handler({"agent_name": agent.name, "task": "look into it"})
        await asyncio.sleep(0)                        # let the done-callbacks run

        assert result == "done: 12:00"
        assert in_flight == set()
        assert await drain_detached(in_flight, timeout=0.01) == 0

    async def test_drain_on_an_empty_set_returns_immediately(self):
        assert await drain_detached(set(), timeout=10.0) == 0
