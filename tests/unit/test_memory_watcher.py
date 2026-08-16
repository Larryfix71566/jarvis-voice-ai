"""Unit tests for jarvis/bot/memory_watcher.py
(MORTIMER_MEMORY_PROCEDURES_PLAN.md D2/D3, §7 verification).
"""

import asyncio

import pytest

from jarvis.bot.memory_watcher import MemorySweepWatcher


class _FakeSettings:
    pass


def _patch_update(monkeypatch, coro_factory):
    import jarvis.bot.memory_watcher as watcher_module

    async def fake_update(settings, session_id):
        return await coro_factory(settings, session_id)

    monkeypatch.setattr(watcher_module, "update_memory_from_session", fake_update)


async def test_tick_once_calls_update_with_right_args(monkeypatch):
    calls = []

    async def fake_update(settings, session_id):
        calls.append((settings, session_id))
        return True

    _patch_update(monkeypatch, fake_update)

    settings = _FakeSettings()
    watcher = MemorySweepWatcher(settings, "sess-1", interval_s=999)
    await watcher.tick_once()

    assert calls == [(settings, "sess-1")]


async def test_tick_once_swallows_exception_and_logs(monkeypatch, caplog):
    async def fake_update(settings, session_id):
        raise RuntimeError("boom")

    _patch_update(monkeypatch, fake_update)

    watcher = MemorySweepWatcher(_FakeSettings(), "sess-2", interval_s=999)
    await watcher.tick_once()  # must not raise

    assert "memory_sweep_failed" in caplog.text
    assert "sess-2" in caplog.text


async def test_tick_once_swallows_timeout_and_logs(monkeypatch, caplog):
    async def fake_update(settings, session_id):
        raise asyncio.TimeoutError()

    _patch_update(monkeypatch, fake_update)

    watcher = MemorySweepWatcher(_FakeSettings(), "sess-3", interval_s=999)
    await watcher.tick_once()  # must not raise

    assert "memory_sweep_timeout" in caplog.text
    assert "sess-3" in caplog.text


async def test_start_and_stop_runs_ticks(monkeypatch):
    ticks = []

    async def fake_update(settings, session_id):
        ticks.append(session_id)
        return True

    _patch_update(monkeypatch, fake_update)

    watcher = MemorySweepWatcher(_FakeSettings(), "sess-4", interval_s=0.01)
    watcher.start()
    await asyncio.sleep(0.05)
    await watcher.stop()

    assert ticks  # ran at least one tick
    assert watcher._task is None


async def test_stop_before_start_is_safe():
    watcher = MemorySweepWatcher(_FakeSettings(), "sess-5", interval_s=999)
    await watcher.stop()  # must not raise
