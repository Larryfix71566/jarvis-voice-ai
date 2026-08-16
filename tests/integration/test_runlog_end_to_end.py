"""Integration test: a real delegation through build_delegate_tool, a real
SubAgent, and a stub MCP registry produces a queryable run (run-logging
plan §7).

Regression coverage called out by the plan's revision 2 audit:
- session_id threads from build_delegate_tool -> SubAgent.run() ->
  RunLogger, and is NULL when not supplied (plan D16).
- a registry that records mcp_call through the ContextVar (as the real
  SkillRegistry.call() does) produces both agent_events rows AND JSONL
  payload records — this is the regression test for the hole closed by
  making the ContextVar hold the RunLogger instance rather than a bare
  run_id string (plan D3).
- a sub-agent whose _loop exceeds the timeout still lands status='timeout'
  rather than being stranded at 'running' forever (plan §5.4).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.agents.base import SubAgent
from jarvis.agents.delegate import build_delegate_tool
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.context import get_run_logger
from jarvis.runlog.store import get_run, list_runs


def make_settings(**overrides):
    base = dict(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_timezone="America/New_York",
        jarvis_runlog_enabled=True,
        # Procedures-as-hints (memory/procedures plan D20): off by default
        # here so this run-logging-focused fixture doesn't also exercise
        # matching — see tests/unit/test_procedures.py and
        # tests/integration/test_procedures_end_to_end.py for that.
        jarvis_procedures_enabled=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeCompletions:
    """Scripted like tests/unit/test_subagent.py's FakeCompletions, minus
    the parts this test doesn't need."""

    def __init__(self, script):
        self._script = list(script)
        self.requests = []

    async def create(self, *, model, messages, tools=None):
        self.requests.append(messages)
        action = self._script.pop(0)
        if action[0] == "sleep":
            await asyncio.sleep(action[1])
            action = ("text", "late")
        if action[0] == "text":
            message = SimpleNamespace(content=action[1], tool_calls=None)
        else:
            raw = json.dumps(action[2])
            tool_call = SimpleNamespace(
                id=f"call_{len(self.requests)}",
                type="function",
                function=SimpleNamespace(name=action[1], arguments=raw),
            )
            message = SimpleNamespace(content=None, tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeLLM:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


class StubRegistryWithRunlog:
    """Stands in for SkillRegistry.call() — deliberately mirrors the real
    one's contract of reading get_run_logger() and recording an mcp_call
    event, so this test exercises the same D3 wiring production code
    does, not a shortcut around it."""

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
        runlog = get_run_logger()
        if runlog is not None:
            runlog.mcp_call(name, "stub_server", ok=True, latency_ms=5)
        return '{"ok": true}'


def make_agent(script, name="scheduler", settings=None, timeout_s=45.0,
               registry=None):
    fake = FakeLLM(script)
    agent = SubAgent(
        name=name, display_name=name.title(), description="d",
        mcp_servers=["stub"], settings=settings or make_settings(),
        registry=registry or StubRegistryWithRunlog(),
        client_factory=lambda s: fake, timeout_s=timeout_s,
    )
    return agent


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "e2e.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(path))
    conn = get_conn(path)
    run_migrations(conn)
    conn.close()
    return path


class TestDelegationProducesQueryableRun:
    async def test_run_id_matches_delegate_start_event_and_is_queryable(
        self, db_path,
    ):
        agent = make_agent([("text", "done")])
        events = []
        schema, handler = build_delegate_tool(
            {"scheduler": agent}, on_event=events.append,
        )
        result = await handler({"agent_name": "scheduler", "task": "do it"})
        assert result == "done"

        start_events = [e for e in events if e["type"] == "delegate_start"]
        assert len(start_events) == 1
        run_id = start_events[0]["run_id"]
        assert run_id

        done_events = [e for e in events if e["type"] == "delegate_done"]
        assert done_events[0]["run_id"] == run_id

        detail = get_run(run_id, db_path=db_path)
        assert detail is not None
        assert detail["run"]["status"] == "ok"
        assert detail["run"]["agent"] == "scheduler"

    async def test_session_id_threads_when_given_and_null_when_not(
        self, db_path,
    ):
        agent_a = make_agent([("text", "done")])
        _, handler_a = build_delegate_tool(
            {"scheduler": agent_a}, session_id="sess-42",
        )
        await handler_a({"agent_name": "scheduler", "task": "t"})

        agent_b = make_agent([("text", "done")])
        _, handler_b = build_delegate_tool({"scheduler": agent_b})
        await handler_b({"agent_name": "scheduler", "task": "t"})

        runs = list_runs(db_path=db_path, limit=10)
        by_agent = {r["agent"]: r for r in runs}
        assert by_agent["scheduler"]["session_id"] in ("sess-42", None)
        session_ids = {r["session_id"] for r in runs}
        assert "sess-42" in session_ids
        assert None in session_ids

    async def test_mcp_call_reaches_both_sqlite_and_jsonl(self, db_path, tmp_path):
        agent = make_agent(
            [("tool", "fake_tool", {}), ("text", "done")],
        )
        events = []
        schema, handler = build_delegate_tool(
            {"scheduler": agent}, on_event=events.append,
        )
        await handler({"agent_name": "scheduler", "task": "t"})
        run_id = next(e for e in events if e["type"] == "delegate_start")["run_id"]

        detail = get_run(run_id, db_path=db_path)
        mcp_events = [e for e in detail["events"] if e["type"] == "mcp_call"]
        assert len(mcp_events) == 1
        assert mcp_events[0]["server"] == "stub_server"

        payload_mcp = [r for r in detail["payload"] if r["type"] == "mcp_call"]
        assert len(payload_mcp) == 1
        assert payload_mcp[0]["server"] == "stub_server"
        assert payload_mcp[0]["ok"] is True

    async def test_timeout_lands_status_timeout_not_stranded_running(
        self, db_path,
    ):
        agent = make_agent([("sleep", 2.0)], timeout_s=0.05)
        events = []
        schema, handler = build_delegate_tool(
            {"scheduler": agent}, on_event=events.append,
        )
        result = await handler({"agent_name": "scheduler", "task": "slow"})
        assert "took too long" in result

        run_id = next(e for e in events if e["type"] == "delegate_start")["run_id"]
        detail = get_run(run_id, db_path=db_path)
        assert detail["run"]["status"] == "timeout"
