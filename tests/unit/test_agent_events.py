"""Unit tests for the UI-bound agent-event mapping in jarvis/bot/pipeline.py.

The agent status window (web console) is fed by make_agent_event_handler:
delegate_* lifecycle -> one status card per delegation, agent_tool ->
progress lines, agent_tool_result -> display payloads. These tests pin the
message shapes the console depends on.
"""

import asyncio
import json

import pytest

from jarvis.bot.pipeline import make_agent_event_handler


@pytest.fixture()
def sent(monkeypatch):
    """Capture every message the handler schedules for the UI."""
    messages = []

    async def fake_send(transport, message):
        messages.append(message)

    monkeypatch.setattr("jarvis.bot.pipeline.send_app_message", fake_send)
    return messages


async def flush():
    # Let the scheduled create_task(send_app_message(...)) run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)


class TestLifecycleCards:
    async def test_delegate_start_sends_working_card(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({"type": "delegate_start", "agent": "analyst",
                 "display_name": "Analyst", "task": "weather in tokyo"})
        await flush()
        assert sent == [{
            "type": "agent", "name": "analyst", "display_name": "Analyst",
            "state": "working", "task": "weather in tokyo",
        }]

    async def test_delegate_start_truncates_long_task(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({"type": "delegate_start", "agent": "developer",
                 "display_name": "Developer", "task": "x" * 500})
        await flush()
        assert len(sent[0]["task"]) == 200

    async def test_delegate_done_success(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({"type": "delegate_done", "agent": "analyst",
                 "display_name": "Analyst", "ok": True, "detail": ""})
        await flush()
        assert sent == [{
            "type": "agent", "name": "analyst", "display_name": "Analyst",
            "state": "done", "ok": True, "detail": "",
        }]

    async def test_delegate_done_failure_carries_detail(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({"type": "delegate_done", "agent": "developer",
                 "display_name": "Developer",
                 "ok": False, "detail": "FAILED: sidecar offline"})
        await flush()
        assert sent[0]["state"] == "done"
        assert sent[0]["ok"] is False
        assert sent[0]["detail"] == "FAILED: sidecar offline"

    async def test_subagent_lifecycle_stays_log_only(self, sent):
        # agent_start/agent_done duplicate the delegate_* lifecycle;
        # the UI must not see them.
        handler = make_agent_event_handler(transport=object())
        handler({"type": "agent_start", "agent": "analyst",
                 "display_name": "Analyst", "task": "t"})
        handler({"type": "agent_done", "agent": "analyst",
                 "display_name": "Analyst", "latency_ms": 123})
        await flush()
        assert sent == []


class TestToolProgress:
    async def test_agent_tool_sends_progress_message(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({"type": "agent_tool", "agent": "developer",
                 "display_name": "Developer", "tool": "selfedit_start"})
        await flush()
        assert sent == [{
            "type": "agent_tool", "name": "developer",
            "display_name": "Developer", "tool": "selfedit_start",
        }]


class TestDisplayPassthrough:
    SEARCH = {"answer": "42.", "results": [
        {"title": "A", "url": "https://a.example", "snippet": "aaa"}]}

    async def test_display_worthy_result_still_forwarded(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "analyst",
            "display_name": "Analyst", "tool": "web_search",
            "arguments": {"query": "meaning"},
            "result": json.dumps(self.SEARCH),
        })
        await flush()
        assert len(sent) == 1
        assert sent[0]["type"] == "display"
        assert sent[0]["display"]["title"] == "Research — meaning"

    async def test_voice_only_result_sends_nothing(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "scheduler",
            "display_name": "Scheduler", "tool": "set_reminder",
            "arguments": {}, "result": '{"ok": true}',
        })
        await flush()
        assert sent == []

    async def test_display_payload_build_is_logged(self, sent, caplog):
        """MORTIMER_AGENT_TRUST_PLAN.md D18: one INFO line whenever a
        display payload is actually built, naming tool/surface/agent/kind,
        so MORTIMER_SIDE_DRAWER_PLAN.md D36's surface routing is
        confirmable from logs alone."""
        handler = make_agent_event_handler(transport=object())
        with caplog.at_level("INFO", logger="jarvis.bot.pipeline"):
            handler({
                "type": "agent_tool_result", "agent": "analyst",
                "display_name": "Analyst", "tool": "web_search",
                "arguments": {"query": "meaning"},
                "result": json.dumps(self.SEARCH),
            })
            await flush()
        matches = [r for r in caplog.records if "display_payload" in r.message]
        assert len(matches) == 1
        assert "tool=web_search" in matches[0].message
        assert "agent=analyst" in matches[0].message
        assert "surface=" in matches[0].message
        assert "kind=" in matches[0].message

    async def test_voice_only_result_is_not_logged_as_display_payload(self, caplog):
        handler = make_agent_event_handler(transport=object())
        with caplog.at_level("INFO", logger="jarvis.bot.pipeline"):
            handler({
                "type": "agent_tool_result", "agent": "scheduler",
                "display_name": "Scheduler", "tool": "set_reminder",
                "arguments": {}, "result": '{"ok": true}',
            })
            await flush()
        assert not any("display_payload" in r.message for r in caplog.records)


def test_no_running_loop_does_not_raise(sent):
    # Sync callers without a running loop (CLI, direct tests) must not crash.
    handler = make_agent_event_handler(transport=object())
    handler({"type": "delegate_start", "agent": "analyst",
             "display_name": "Analyst", "task": "t"})
