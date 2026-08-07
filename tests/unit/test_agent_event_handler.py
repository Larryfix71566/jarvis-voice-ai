"""Unit tests for jarvis/bot/pipeline.py make_agent_event_handler —
the UI agent-activity message feed (satellite cards consume these)."""

import asyncio

from jarvis.bot import pipeline as pipeline_mod


class FakeTransport:
    """send_app_message is monkeypatched, so the transport is never used."""


def make_recorder(monkeypatch):
    sent = []

    async def fake_send(transport, message):
        sent.append(message)

    monkeypatch.setattr(pipeline_mod, "send_app_message", fake_send)
    return sent


class TestAgentEventHandler:
    async def test_working_message_includes_truncated_task(self, monkeypatch):
        sent = make_recorder(monkeypatch)
        handler = pipeline_mod.make_agent_event_handler(FakeTransport())
        handler({"type": "agent_start", "agent": "analyst",
                 "display_name": "Analyst", "task": "x" * 200})
        await asyncio.sleep(0)
        assert sent == [{
            "type": "agent",
            "name": "analyst",
            "state": "working",
            "task": "x" * pipeline_mod.UI_TASK_SUMMARY_CHARS,
        }]

    async def test_done_message_has_no_task(self, monkeypatch):
        sent = make_recorder(monkeypatch)
        handler = pipeline_mod.make_agent_event_handler(FakeTransport())
        handler({"type": "agent_done", "agent": "analyst",
                 "display_name": "Analyst", "latency_ms": 123})
        await asyncio.sleep(0)
        assert sent == [{"type": "agent", "name": "analyst", "state": "done"}]

    async def test_missing_task_omits_task_key(self, monkeypatch):
        sent = make_recorder(monkeypatch)
        handler = pipeline_mod.make_agent_event_handler(FakeTransport())
        handler({"type": "agent_start", "agent": "scheduler",
                 "display_name": "Scheduler"})
        await asyncio.sleep(0)
        assert sent == [{
            "type": "agent", "name": "scheduler", "state": "working",
        }]

    async def test_non_agent_events_are_not_forwarded(self, monkeypatch):
        sent = make_recorder(monkeypatch)
        handler = pipeline_mod.make_agent_event_handler(FakeTransport())
        handler({"type": "delegate_start", "agent": "analyst",
                 "display_name": "Analyst", "task": "research"})
        handler({"type": "agent_tool", "agent": "analyst",
                 "display_name": "Analyst", "tool": "web_search"})
        handler({"type": "delegate_done", "agent": "analyst",
                 "display_name": "Analyst"})
        await asyncio.sleep(0)
        assert sent == []
