"""Unit tests for jarvis/runlog/context.py (run-logging plan §7).

This is the regression test for the parallel-delegation correlation bug
this plan fixes (§1.4): concurrent delegations must each see their own
RunLogger through the ContextVar, not a shared/overwritten one.
"""

from __future__ import annotations

import asyncio

import pytest

from jarvis.runlog.context import get_run_id, get_run_logger, run_logger_scope


class FakeRunLogger:
    def __init__(self, run_id: str):
        self.run_id = run_id


def test_get_run_logger_outside_scope_is_none():
    assert get_run_logger() is None
    assert get_run_id() is None


def test_scope_sets_and_resets():
    logger = FakeRunLogger("r1")
    assert get_run_logger() is None
    with run_logger_scope(logger):
        assert get_run_logger() is logger
        assert get_run_id() == "r1"
    assert get_run_logger() is None


def test_scope_resets_even_when_body_raises():
    logger = FakeRunLogger("r1")
    with pytest.raises(ValueError):
        with run_logger_scope(logger):
            assert get_run_logger() is logger
            raise ValueError("boom")
    assert get_run_logger() is None


def test_none_scope_is_legal_and_explicit():
    with run_logger_scope(None):
        assert get_run_logger() is None


@pytest.mark.asyncio
async def test_concurrent_tasks_each_see_their_own_logger():
    """Two concurrent asyncio tasks, each in its own run_logger_scope,
    must never observe the other's RunLogger — this is exactly the
    parallel-delegation scenario in jarvis/agents/delegate.py."""
    seen: dict[str, str | None] = {}

    async def worker(name: str, delay: float) -> None:
        logger = FakeRunLogger(name)
        with run_logger_scope(logger):
            await asyncio.sleep(delay)
            seen[name] = get_run_id()

    await asyncio.gather(
        worker("run-a", 0.02),
        worker("run-b", 0.01),
    )

    assert seen == {"run-a": "run-a", "run-b": "run-b"}
    assert get_run_logger() is None
