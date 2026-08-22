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
                 "display_name": "Analyst", "task": "weather in tokyo",
                 "model": "claude-haiku-4-5", "model_fallback": False})
        await flush()
        assert sent == [{
            "type": "agent", "name": "analyst", "display_name": "Analyst",
            "state": "working", "run_id": None, "task": "weather in tokyo",
            "model": "claude-haiku-4-5", "model_fallback": False,
            "model_unusable": False, "model_unusable_detail": "",
        }]

    async def test_a_start_without_model_still_sends_a_card(self, sent):
        """Defensive, and the reason the client treats `model` as
        optional: the working card is the primary signal and must never
        depend on the model field being present."""
        handler = make_agent_event_handler(transport=object())
        handler({"type": "delegate_start", "agent": "analyst",
                 "display_name": "Analyst", "task": "t"})
        await flush()
        assert sent[0]["state"] == "working"
        assert sent[0]["model"] is None
        assert sent[0]["model_fallback"] is False

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
        # Activity ticker (2026-08-21): every tool result now ALSO sends
        # one agent_activity line before the display-worthiness check.
        assert len(sent) == 2
        assert sent[0]["type"] == "agent_activity"
        assert sent[0]["tool"] == "web_search"
        assert sent[1]["type"] == "display"
        assert sent[1]["display"]["title"] == "Research — meaning"

    async def test_voice_only_result_sends_activity_but_no_display(self, sent):
        """A voice-only tool result opens no display surface — but it still
        ticks the activity line (2026-08-21), because the Agents card's
        work narrative covers every call, not just display-worthy ones."""
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "scheduler",
            "display_name": "Scheduler", "tool": "set_reminder",
            "arguments": {}, "result": '{"ok": true}',
            "ok": True, "latency_ms": 12,
        })
        await flush()
        assert [m["type"] for m in sent] == ["agent_activity"]
        assert sent[0]["ok"] is True
        assert sent[0]["latency_ms"] == 12

    async def test_selfedit_start_result_carries_planner_model(self, sent):
        """G7 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): the
        Agents-tab card needs to distinguish the developer's OWN dispatch
        model from the model actually doing self-edit work — the latter
        rides the agent_activity message as `planner_model`."""
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "developer",
            "display_name": "Developer", "tool": "selfedit_start",
            "arguments": {}, "result": json.dumps({
                "ok": True, "started": True, "profile": "kimi-k3 (kimi-k3-model)",
                "planner_model": "kimi-k3 (kimi-k3-model)",
            }),
            "ok": True, "latency_ms": 5,
        })
        await flush()
        assert sent[0]["type"] == "agent_activity"
        assert sent[0]["planner_model"] == "kimi-k3 (kimi-k3-model)"

    async def test_selfedit_status_result_carries_planner_model(self, sent):
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "developer",
            "display_name": "Developer", "tool": "selfedit_status",
            "arguments": {}, "result": json.dumps({
                "ok": True, "summary": "Still planning", "job": {},
                "planner_model": "claude-opus (claude-opus-5)",
            }),
            "ok": True, "latency_ms": 5,
        })
        await flush()
        assert sent[0]["planner_model"] == "claude-opus (claude-opus-5)"

    async def test_other_tools_never_carry_planner_model(self, sent):
        """The planner_model field is specific to the two self-edit polling
        tools — it must not leak onto unrelated tool activity lines even if
        their result JSON happens to contain a same-named key."""
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "scheduler",
            "display_name": "Scheduler", "tool": "set_reminder",
            "arguments": {}, "result": json.dumps({
                "ok": True, "planner_model": "should-not-appear",
            }),
            "ok": True, "latency_ms": 5,
        })
        await flush()
        assert "planner_model" not in sent[0]

    async def test_missing_planner_model_omits_field(self, sent):
        """A selfedit_start/status result without a planner_model (e.g. an
        error response) must not send an empty or None field — the client
        treats absence as 'unknown', not 'no planner'."""
        handler = make_agent_event_handler(transport=object())
        handler({
            "type": "agent_tool_result", "agent": "developer",
            "display_name": "Developer", "tool": "selfedit_start",
            "arguments": {}, "result": json.dumps({"ok": False, "error": "no goal"}),
            "ok": False, "latency_ms": 5,
        })
        await flush()
        assert "planner_model" not in sent[0]

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
