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

    async def fake_update(settings, session_id, **kwargs):
        # Phase 2 kill switch (MORTIMER_OPTIMIZATION_PLAN.md): tick_once
        # now passes extract_facts_and_observations=... as a kwarg. Most
        # of these tests only care about the (settings, session_id) call
        # shape, so the wrapper accepts and discards it; the dedicated
        # test below asserts on its actual value.
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


# --- Phase 2 kill switch (MORTIMER_OPTIMIZATION_PLAN.md) -------------------


class TestKillSwitchWiring:
    """tick_once must derive extract_facts_and_observations from
    JARVIS_MEMORY_EXTRACTION_V2 via jarvis.memory.memory_extraction_v2_enabled
    -- not hardcode it -- so the two sides stay inverse: V2 on means the new
    per-exchange worker is authoritative and this sweep narrows to
    summary-only (flag False); V2 off means today's full legacy extraction
    (flag True)."""

    def _patch_capturing(self, monkeypatch):
        import jarvis.bot.memory_watcher as watcher_module

        captured = {}

        async def fake_update(settings, session_id, **kwargs):
            captured["kwargs"] = kwargs
            return True

        monkeypatch.setattr(watcher_module, "update_memory_from_session", fake_update)
        return captured

    async def test_v2_enabled_by_default_narrows_to_summary_only(self, monkeypatch):
        monkeypatch.delenv("JARVIS_MEMORY_EXTRACTION_V2", raising=False)
        captured = self._patch_capturing(monkeypatch)

        watcher = MemorySweepWatcher(_FakeSettings(), "sess-6", interval_s=999)
        await watcher.tick_once()

        assert captured["kwargs"]["extract_facts_and_observations"] is False

    async def test_v2_disabled_keeps_full_legacy_extraction(self, monkeypatch):
        monkeypatch.setenv("JARVIS_MEMORY_EXTRACTION_V2", "false")
        captured = self._patch_capturing(monkeypatch)

        watcher = MemorySweepWatcher(_FakeSettings(), "sess-7", interval_s=999)
        await watcher.tick_once()

        assert captured["kwargs"]["extract_facts_and_observations"] is True
