"""RemindersWatcher unit tests (plan Phase 7 Tests — locked).

Fake registry returning due reminders -> exactly one context injection per
due row; none when empty; none when disconnected.
"""

import json

from jarvis.bot.reminders_watcher import CONTEXT_TEMPLATE, RemindersWatcher


class FakeRegistry:
    def __init__(self, reminders=None, raises=False, raw=None):
        self.reminders = reminders or []
        self.raises = raises
        self.raw = raw
        self.calls = []

    async def call(self, tool_name, arguments, server_names=None):
        self.calls.append((tool_name, arguments, server_names))
        if self.raises:
            raise RuntimeError("PRIVATE_CANARY_reminder_exception_4d2a")
        if self.raw is not None:
            return self.raw
        return json.dumps({"reminders": self.reminders})


def make_watcher(registry, connected=True):
    injections = []

    async def inject(text):
        injections.append(text)

    watcher = RemindersWatcher(
        registry, inject=inject, is_connected=lambda: connected)
    return watcher, injections


DUE = [
    {"id": 1, "message": "call the dentist", "due_at": "2026-08-05T09:00:00"},
    {"id": 2, "message": "stretch", "due_at": "2026-08-05T09:05:00"},
]


async def test_one_injection_per_due_row():
    registry = FakeRegistry(reminders=DUE)
    watcher, injections = make_watcher(registry, connected=True)
    await watcher.tick_once()
    assert injections == [
        CONTEXT_TEMPLATE.format(message="call the dentist"),
        CONTEXT_TEMPLATE.format(message="stretch"),
    ]
    assert registry.calls == [("get_due_reminders", {}, ["mcp-reminders"])]


async def test_no_injection_when_empty():
    registry = FakeRegistry(reminders=[])
    watcher, injections = make_watcher(registry, connected=True)
    await watcher.tick_once()
    assert injections == []


async def test_no_call_no_injection_when_disconnected():
    """Disconnected: rows must NOT be fetched (fetching marks delivered)."""
    registry = FakeRegistry(reminders=DUE)
    watcher, injections = make_watcher(registry, connected=False)
    await watcher.tick_once()
    assert injections == []
    assert registry.calls == []  # accumulate for the next connect


async def test_registry_failure_never_crashes_or_logs_exception_message(caplog):
    registry = FakeRegistry(raises=True)
    watcher, injections = make_watcher(registry, connected=True)
    await watcher.tick_once()  # must not raise
    assert injections == []
    assert "PRIVATE_CANARY_reminder_exception_4d2a" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


async def test_failure_sentence_result_never_crashes_or_logs_response_body(caplog):
    registry = FakeRegistry(raw="PRIVATE_CANARY_reminder_body_4d2a")
    watcher, injections = make_watcher(registry, connected=True)
    await watcher.tick_once()  # must not raise
    assert injections == []
    assert "PRIVATE_CANARY_reminder_body_4d2a" not in caplog.text
    assert "invalid reminder JSON" in caplog.text


async def test_dedup_is_delivered_flag_not_watcher_state():
    """Second tick with the server now returning empty -> no re-injection."""
    registry = FakeRegistry(reminders=DUE)
    watcher, injections = make_watcher(registry, connected=True)
    await watcher.tick_once()
    assert len(injections) == 2
    registry.reminders = []  # server-side delivered flag did the dedup
    await watcher.tick_once()
    assert len(injections) == 2  # unchanged


async def test_start_and_stop():
    import asyncio
    registry = FakeRegistry(reminders=DUE)
    watcher, injections = make_watcher(registry, connected=True)
    watcher._interval_s = 0.01
    watcher.start()
    await asyncio.sleep(0.05)
    await watcher.stop()
    assert injections  # ran at least one tick
    assert watcher._task is None
