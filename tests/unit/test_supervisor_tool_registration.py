"""Direct-tool registration and its log line (jarvis/bot/pipeline.py).

MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item E. Nothing anywhere recorded the
Supervisor calling a DIRECT tool. agent_tool belongs to the sub-agents
(jarvis/agents/base.py) and so never fires on a turn that delegated
nothing — exactly the turn worth seeing. A turn that reached for
ui_control instead of delegating looked, in the logs, identical to a turn
that simply answered.

adapt_to_pipecat was a closure inside build_pipeline until today, which is
why this behaviour had no test; lifting it to module scope is what makes
these possible.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from jarvis.agents.supervisor import Orchestrator
from jarvis.bot.pipeline import adapt_to_pipecat, register_supervisor_tool
from jarvis.db import get_conn, run_migrations
from jarvis.runlog import get_run
from jarvis.runlog.context import get_run_logger
from jarvis.runlog.store import RunLogger


class FakeParams:
    """Stands in for pipecat's FunctionCallParams (D-009)."""

    def __init__(self, arguments, tool_call_id="voice-call-1"):
        self.arguments = arguments
        self.tool_call_id = tool_call_id
        self.results = []

    async def result_callback(self, result):
        self.results.append(result)


class FakeLLM:
    def __init__(self):
        self.registered = []

    def register_function(self, name, handler):
        self.registered.append((name, handler))


@pytest.fixture
def persistent_runlogs(monkeypatch, tmp_path):
    db_path = tmp_path / "supervisor-runlog.sqlite3"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    payload_root = tmp_path / "payloads"
    created = []

    def make_runlogger(*args, **kwargs):
        logger = RunLogger(
            *args, db_path=db_path, root=payload_root, **kwargs,
        )
        created.append(logger)
        return logger

    monkeypatch.setattr("jarvis.bot.pipeline.RunLogger", make_runlogger)
    return db_path, payload_root, created


async def test_the_handler_still_gets_arguments_and_returns_via_callback():
    # The locked D-009 contract: (arguments dict) -> confirmation str, with
    # the result delivered through params.result_callback.
    seen = []

    async def handler(arguments):
        seen.append(arguments)
        return "Voice switched to Rachel."

    wrapper = adapt_to_pipecat("set_voice", handler)
    params = FakeParams({"voice": "rachel"})
    await wrapper(params)
    assert seen == [{"voice": "rachel"}]
    assert params.results == ["Voice switched to Rachel."]


async def test_calling_a_direct_tool_is_logged_with_its_name(caplog):
    async def handler(arguments):
        return "ok"

    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        await adapt_to_pipecat("ui_control", handler)(FakeParams({}))
    assert "supervisor_tool tool=ui_control" in caplog.text


async def test_the_log_line_precedes_the_handler_so_a_failure_still_shows(
        caplog):
    # A tool that raises is the case most worth having in the log; logging
    # after the call would lose exactly those.
    async def handler(arguments):
        raise RuntimeError("tool blew up")

    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        with pytest.raises(RuntimeError):
            await adapt_to_pipecat("view_screen", handler)(FakeParams({}))
    assert "supervisor_tool tool=view_screen" in caplog.text


def test_registration_uses_one_spelling_of_the_name():
    # Passing the name twice invites a handler registered under the wrong
    # one, which fails only at call time and only in production.
    llm = FakeLLM()

    async def handler(arguments):
        return "ok"

    register_supervisor_tool(llm, "remember", handler)
    assert [name for name, _ in llm.registered] == ["remember"]


async def test_the_registered_wrapper_logs_the_name_it_was_registered_under(
        caplog):
    llm = FakeLLM()

    async def handler(arguments):
        return "ok"

    register_supervisor_tool(llm, "show_commands", handler)
    _, wrapper = llm.registered[0]
    with caplog.at_level(logging.INFO, logger="jarvis.bot.pipeline"):
        await wrapper(FakeParams({}))
    assert "supervisor_tool tool=show_commands" in caplog.text


async def test_voice_tool_result_is_correlated_and_runlog_is_redacted(monkeypatch):
    class CapturingRunLogger:
        def __init__(self, *args, **kwargs):
            self.init_args = args
            self.init_kwargs = kwargs
            self.calls = []

        def start(self):
            self.calls.append(("start",))

        def tool_call(self, *args, **kwargs):
            self.calls.append(("tool_call", args, kwargs))

        def tool_result(self, *args, **kwargs):
            self.calls.append(("tool_result", args, kwargs))

        def tool_outcome_unknown(self, *args, **kwargs):
            self.calls.append(("unknown", args, kwargs))

        def finish(self, reply):
            self.calls.append(("finish", reply))

    runlogs = []

    def make_runlog(*args, **kwargs):
        runlog = CapturingRunLogger(*args, **kwargs)
        runlogs.append(runlog)
        return runlog

    monkeypatch.setattr("jarvis.bot.pipeline.RunLogger", make_runlog)

    async def handler(_arguments):
        return '{"ok": true, "result": "done"}'

    params = FakeParams({"body": "private"}, tool_call_id="pipecat-call-9")
    await adapt_to_pipecat(
        "send_message", handler, runlog_enabled=True, session_id="session-4",
    )(params)

    runlog = runlogs[0]
    assert runlog.init_kwargs["session_id"] == "session-4"
    assert runlog.init_kwargs["sensitive"] is True
    tool_call = next(call for call in runlog.calls if call[0] == "tool_call")
    assert tool_call[1][0] == "send_message"
    assert tool_call[2]["tool_call_id"] == "pipecat-call-9"
    result = next(call for call in runlog.calls if call[0] == "tool_result")
    assert result[2]["tool_call_id"] == "pipecat-call-9"
    assert not any(call[0] == "unknown" for call in runlog.calls)
    assert params.results == ['{"ok": true, "result": "done"}']


async def test_voice_tool_cancellation_records_unknown_and_never_returns_late_result(
    monkeypatch,
):
    class CapturingRunLogger:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def start(self):
            pass

        def tool_call(self, *args, **kwargs):
            self.calls.append(("tool_call", args, kwargs))

        def tool_result(self, *args, **kwargs):
            self.calls.append(("tool_result", args, kwargs))

        def tool_outcome_unknown(self, *args, **kwargs):
            self.calls.append(("unknown", args, kwargs))

        def finish(self, reply):
            self.calls.append(("finish", reply))

    runlogs = []

    def make_runlog(*args, **kwargs):
        runlog = CapturingRunLogger(*args, **kwargs)
        runlogs.append(runlog)
        return runlog

    monkeypatch.setattr("jarvis.bot.pipeline.RunLogger", make_runlog)
    started = asyncio.Event()

    async def handler(_arguments):
        started.set()
        await asyncio.Event().wait()
        return "late result"

    params = FakeParams({}, tool_call_id="cancelled-voice-call")
    task = asyncio.create_task(adapt_to_pipecat(
        "write_action", handler, runlog_enabled=True,
    )(params))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    unknown = next(call for call in runlogs[0].calls if call[0] == "unknown")
    assert unknown[1] == ("write_action", "cancelled-voice-call")
    assert unknown[2] == {"reason_code": "cancelled_after_return"}
    assert not any(call[0] == "tool_result" for call in runlogs[0].calls)
    assert params.results == []


async def test_supervisor_tool_persists_correlated_redacted_result_and_mcp_call(
    persistent_runlogs,
):
    db_path, payload_root, created = persistent_runlogs
    private_argument = "PRIVATE_ARGUMENT_CANARY_7f29"
    private_result = "PRIVATE_RESULT_CANARY_7f29"

    async def handler(_arguments):
        get_run_logger().mcp_call("nested_action", "mcp_test", True, 3)
        return private_result

    params = FakeParams(
        {"message": private_argument}, tool_call_id="persistent-call-23",
    )
    await adapt_to_pipecat(
        "send_message", handler, runlog_enabled=True, session_id="session-23",
    )(params)

    assert params.results == [private_result]
    run = get_run(created[0].run_id, db_path, payload_root)
    assert run["run"]["status"] == "ok"
    assert run["run"]["agent"] == "supervisor"
    assert [event["type"] for event in run["events"]] == [
        "tool_call", "mcp_call", "tool_result",
    ]
    call = run["events"][0]
    result = run["events"][2]
    assert call["tool_call_id"] == "persistent-call-23"
    assert result["tool_call_id"] == "persistent-call-23"
    assert call["args_preview"] == "<sensitive>"
    assert result["result_preview"] == "<sensitive>"
    serialized = json.dumps({"events": run["events"], "payload": run["payload"]})
    assert private_argument not in serialized
    assert private_result not in serialized


async def test_supervisor_tool_exception_persists_unknown_without_exception_text(
    persistent_runlogs,
):
    db_path, payload_root, _created = persistent_runlogs
    secret = "PRIVATE_EXCEPTION_CANARY_c3a1"

    async def handler(_arguments):
        raise RuntimeError(secret)

    params = FakeParams({}, tool_call_id="exception-call-8")
    with pytest.raises(RuntimeError, match=secret):
        await adapt_to_pipecat(
            "write_action", handler, runlog_enabled=True,
            session_id="session-exception",
        )(params)

    conn = get_conn(db_path)
    run_id = conn.execute(
        "SELECT run_id FROM agent_runs WHERE session_id = ?",
        ("session-exception",),
    ).fetchone()[0]
    conn.close()
    run = get_run(run_id, db_path, payload_root)
    assert run["run"]["status"] == "failed"
    assert run["unresolved_tool_calls"] == [{
        "tool_call_id": "exception-call-8",
        "tool": "write_action",
        "status": "unknown",
    }]
    assert [event["type"] for event in run["events"]] == [
        "tool_call", "tool_outcome_unknown",
    ]
    assert run["events"][1]["result_preview"] == "unknown"
    assert secret not in json.dumps({"events": run["events"], "payload": run["payload"]})
    assert params.results == []


async def test_supervisor_tool_suppresses_result_if_handler_swallows_cancellation(
    persistent_runlogs,
):
    db_path, payload_root, _created = persistent_runlogs
    started = asyncio.Event()

    async def handler(_arguments):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return "late result that must not escape"

    params = FakeParams({}, tool_call_id="swallowed-cancel-call")
    task = asyncio.create_task(adapt_to_pipecat(
        "write_action", handler, runlog_enabled=True,
        session_id="session-swallowed-cancel",
    )(params))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert params.results == []
    conn = get_conn(db_path)
    run_id = conn.execute(
        "SELECT run_id FROM agent_runs WHERE session_id = ?",
        ("session-swallowed-cancel",),
    ).fetchone()[0]
    conn.close()
    run = get_run(run_id, db_path, payload_root)
    assert run["unresolved_tool_calls"][0]["status"] == "unknown"
    assert [event["type"] for event in run["events"]] == [
        "tool_call", "tool_outcome_unknown",
    ]


async def test_supervisor_runlogging_disabled_keeps_tool_behavior_without_persisting(
    persistent_runlogs,
):
    db_path, payload_root, created = persistent_runlogs

    async def handler(_arguments):
        return "still works"

    params = FakeParams({"value": "private"})
    await adapt_to_pipecat("read_only", handler, runlog_enabled=False)(params)

    assert params.results == ["still works"]
    assert len(created) == 1
    conn = get_conn(db_path)
    assert conn.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0
    conn.close()
    assert not payload_root.exists()


def test_supervisor_event_callback_error_logs_only_error_type(caplog):
    orchestrator = object.__new__(Orchestrator)

    def fail(_event):
        raise RuntimeError("PRIVATE_CANARY_supervisor_event_4d2a")

    orchestrator._on_event = fail
    orchestrator._emit_event({"content": "PRIVATE_CANARY_payload_4d2a"})

    assert "PRIVATE_CANARY_supervisor_event_4d2a" not in caplog.text
    assert "PRIVATE_CANARY_payload_4d2a" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
