"""Unit tests for jarvis/agents/delegate.py (plan Phase 3 Tests; Phase 4
concurrency tests below)."""

import asyncio
import time

import pytest
import yaml

from jarvis.agents.delegate import build_delegate_tool
from jarvis.prompts import render_agent_catalog

from tests.unit.test_orchestrator import FakeSubAgent


class SlowFakeSubAgent:
    """Like FakeSubAgent but sleeps for `delay` seconds, so tests can
    observe whether concurrent delegations actually overlap in time."""

    def __init__(self, name, delay=0.05, result="done"):
        self.name = name
        self.display_name = name.title()
        self.description = f"{name} things."
        self.mcp_servers = []
        self.delay = delay
        self.result = result
        self.tasks = []
        self.started_at: float | None = None
        self.finished_at: float | None = None

    async def run(self, task, on_event=None):
        self.started_at = time.perf_counter()
        self.tasks.append(task)
        await asyncio.sleep(self.delay)
        if self.result.startswith("FAILED"):
            self.finished_at = time.perf_counter()
            return self.result
        self.finished_at = time.perf_counter()
        return self.result

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


class TestParallelDelegation:
    """Plan Phase 4: two independent delegations run concurrently, a
    failure in one does not affect the other, and max_parallel is a real
    cap — not just documentation."""

    async def test_two_independent_delegations_overlap_in_time(self):
        """If calls ran serially, total wall time would be >= 2x delay.
        Run concurrently (via asyncio.gather, as pipecat's own parallel
        tool-call dispatch does), total wall time should stay close to a
        single delay."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.08),
            "analyst": SlowFakeSubAgent("analyst", delay=0.08),
        }
        _, handler = build_delegate_tool(agents, max_parallel=3)

        start = time.perf_counter()
        results = await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "remind me"}),
            handler({"agent_name": "analyst", "task": "weather"}),
        )
        elapsed = time.perf_counter() - start

        assert results == ["done", "done"]
        # Serial would take ~0.16s; concurrent should be well under that.
        assert elapsed < 0.15, f"expected overlap, took {elapsed:.3f}s"

        # Both agents were actually in flight at the same time.
        sched, analyst = agents["scheduler"], agents["analyst"]
        assert sched.started_at < analyst.finished_at
        assert analyst.started_at < sched.finished_at

    async def test_one_failure_does_not_affect_sibling(self):
        """SubAgent.run() never raises (failures come back as 'FAILED:
        ...' strings), and each delegation is independent — a failing
        sibling must not cancel or corrupt the other's result."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.02, result="done"),
            "analyst": SlowFakeSubAgent(
                "analyst", delay=0.02, result="FAILED: web_search down"
            ),
        }
        events = []
        _, handler = build_delegate_tool(
            agents, on_event=events.append, max_parallel=3
        )

        sched_result, analyst_result = await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "remind me"}),
            handler({"agent_name": "analyst", "task": "news"}),
        )

        assert sched_result == "done"
        assert analyst_result == "FAILED: web_search down"

        done_events = {e["agent"]: e for e in events if e["type"] == "delegate_done"}
        assert done_events["scheduler"]["ok"] is True
        assert done_events["analyst"]["ok"] is False

    async def test_max_parallel_caps_concurrent_execution(self):
        """With max_parallel=1, three delegations must run strictly
        serially even though they're all launched at once — proves the
        semaphore, not just pipecat's own dispatch, is what's bounding it."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.05),
            "librarian": SlowFakeSubAgent("librarian", delay=0.05),
            "analyst": SlowFakeSubAgent("analyst", delay=0.05),
        }
        _, handler = build_delegate_tool(agents, max_parallel=1)

        start = time.perf_counter()
        await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "a"}),
            handler({"agent_name": "librarian", "task": "b"}),
            handler({"agent_name": "analyst", "task": "c"}),
        )
        elapsed = time.perf_counter() - start

        # Capped to 1 at a time: ~3x a single delay, not ~1x.
        assert elapsed >= 0.14, f"expected serial execution, took {elapsed:.3f}s"

    async def test_max_parallel_allows_bounded_concurrency(self):
        """With max_parallel=2, two of three delegations should overlap
        (faster than fully serial) while still being capped (slower than
        fully unbounded)."""
        agents = {
            "scheduler": SlowFakeSubAgent("scheduler", delay=0.05),
            "librarian": SlowFakeSubAgent("librarian", delay=0.05),
            "analyst": SlowFakeSubAgent("analyst", delay=0.05),
        }
        _, handler = build_delegate_tool(agents, max_parallel=2)

        start = time.perf_counter()
        await asyncio.gather(
            handler({"agent_name": "scheduler", "task": "a"}),
            handler({"agent_name": "librarian", "task": "b"}),
            handler({"agent_name": "analyst", "task": "c"}),
        )
        elapsed = time.perf_counter() - start

        # Two batches of ~0.05s (2 concurrent, then 1) — well under fully
        # serial (~0.15s), well over fully unbounded (~0.05s).
        assert 0.08 <= elapsed < 0.14, f"expected 2-wide batching, took {elapsed:.3f}s"

    async def test_default_max_parallel_matches_config_default(self):
        """DEFAULT_MAX_PARALLEL_DELEGATIONS must match
        Settings.jarvis_max_parallel_delegations's default so the two
        stay in sync without every caller having to pass it explicitly."""
        from jarvis.agents.delegate import DEFAULT_MAX_PARALLEL_DELEGATIONS
        from jarvis.config import Settings

        default_settings = Settings(
            openai_api_key="x", deepgram_api_key="x", elevenlabs_api_key="x"
        )
        assert (
            DEFAULT_MAX_PARALLEL_DELEGATIONS
            == default_settings.jarvis_max_parallel_delegations
        )


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
