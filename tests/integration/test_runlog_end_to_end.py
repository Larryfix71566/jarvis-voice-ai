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
- caller cancellation terminates the run record instead of leaving it
  stranded at 'running'.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from jarvis.agents.base import CANCELLED_MESSAGE, SubAgent
from jarvis.agents.delegate import build_delegate_tool
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.context import get_run_logger
from jarvis.runlog.store import get_run, list_runs
from jarvis.tenant import user_id_scope


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
        self.tool_schemas = []

    async def create(self, *, model, messages, tools=None):
        self.requests.append(messages)
        self.tool_schemas.append(tools)
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


@pytest.fixture(autouse=True)
def initialized_non_sensitive_turn():
    # Runtime-created agent tasks inherit this holder in production. Give
    # the integration tests the same explicit ordinary-turn context so the
    # fail-closed unset-context path remains covered separately.
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


class TestDelegationProducesQueryableRun:
    async def test_bounded_creator_uses_real_developer_run_and_never_generic_tools(
        self, db_path,
    ):
        registry = StubRegistryWithRunlog()
        agent = make_agent(
            [
                ("tool", "creator_read", {"path": "skills/sample/SKILL.md"}),
                ("text", "draft complete"),
            ],
            name="developer", registry=registry,
        )
        tool_specs = [{
            "type": "function",
            "function": {"name": "creator_read", "description": "read scoped file",
                         "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                        "required": ["path"], "additionalProperties": False}},
        }]
        called = []
        created = []
        with user_id_scope("creator-owner"):
            reply = await agent.run(
                "Draft a small skill.",
                session_id="00000000-0000-0000-0000-000000000001",
                system_prompt_override="fixed creator policy",
                tool_specs_override=tool_specs,
                tool_executor=lambda name, args: called.append((name, args)) or {"ok": True},
                on_run_created=lambda run_id: created.append(run_id) or True,
            )
        assert reply == "draft complete"
        assert len(created) == 1
        run = get_run(created[0])["run"]
        assert run["agent"] == "developer"
        assert run["user_id"] == "creator-owner"
        assert run["session_id"] == "00000000-0000-0000-0000-000000000001"
        assert called == [("creator_read", {"path": "skills/sample/SKILL.md"})]
        assert registry.calls == []
        assert agent._client.chat.completions.tool_schemas[0] == tool_specs

    async def test_failed_run_association_prevents_any_model_or_tool_call(self, db_path):
        agent = make_agent(
            [("tool", "creator_read", {"path": "skills/sample/SKILL.md"})],
            name="developer",
        )
        tool_calls = []
        reply = await agent.run(
            "Draft a skill.",
            session_id="00000000-0000-0000-0000-000000000001",
            system_prompt_override="fixed creator policy",
            tool_specs_override=[{"type": "function", "function": {"name": "creator_read",
                "parameters": {"type": "object", "properties": {}}}}],
            tool_executor=lambda *_args: tool_calls.append(True),
            on_run_created=lambda _run_id: False,
        )
        assert reply.startswith("FAILED: creator run could not be durably associated")
        assert agent._client.chat.completions.requests == []
        assert tool_calls == []

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
        # MORTIMER_PLANNING_PATHWAY_PLAN.md P3 — settings.openai_model
        # threads through SubAgent.run() -> RunLogger -> the row.
        assert detail["run"]["model"] == "test-model"

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

    async def test_cancellation_finishes_run_record_and_propagates(
        self, db_path,
    ):
        agent = make_agent([("sleep", 2.0)])
        task = asyncio.create_task(
            agent.run("slow", run_id="cancelled-run", session_id="sess-cancelled")
        )
        for _ in range(100):
            if agent._client.chat.completions.requests:
                break
            await asyncio.sleep(0)
        assert agent._client.chat.completions.requests

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        detail = get_run("cancelled-run", db_path=db_path)
        assert detail["run"]["status"] == "cancelled"
        assert detail["run"]["reply_preview"] == CANCELLED_MESSAGE
        assert detail["run"]["session_id"] == "sess-cancelled"

    async def test_cancellation_during_tool_suppresses_followup_and_success_event(
        self, db_path,
    ):
        class BlockingRegistry(StubRegistryWithRunlog):
            def __init__(self):
                super().__init__()
                self.started = asyncio.Event()
                self.cancelled = False

            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments))
                self.started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True

        registry = BlockingRegistry()
        agent = make_agent(
            [("tool", "fake_tool", {}), ("text", "must not be reached")],
            registry=registry,
        )
        events = []
        task = asyncio.create_task(
            agent.run(
                "run the tool", run_id="cancelled-tool-run",
                session_id="sess-cancelled-tool", on_event=events.append,
            )
        )
        await asyncio.wait_for(registry.started.wait(), timeout=1)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert registry.cancelled
        assert len(agent._client.chat.completions.requests) == 1
        assert not any(event.get("type") == "agent_done" for event in events)
        detail = get_run("cancelled-tool-run", db_path=db_path)
        assert detail["run"]["status"] == "cancelled"
        assert detail["run"]["reply_preview"] == CANCELLED_MESSAGE
