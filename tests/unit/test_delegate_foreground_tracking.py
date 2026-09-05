"""2026-09-05 — the in-flight-delegation guard behind the duplicate-store fix.

Live trace this comes from: a barge-in cancelled a developer delegation at
16:36:36.030; its detached work finished at 16:36:40.112; `inject_late_result`
then pushed a context frame, which re-ran the model at 16:36:43.022 — 0.8 s
after a librarian `delegate_task` was issued and 4.8 s before that call's
result arrived. The model saw its own "Storing that now" with no result and
re-issued the store, producing notes #22 AND #23 from one request.

`foreground_delegation_count()` is what lets the injector tell "nothing is in
flight, safe to force a turn" from "a tool call is outstanding, do not".
"""
from __future__ import annotations

import asyncio
import contextlib

import pytest

from jarvis.agents import delegate as delegate_mod
from jarvis.agents.delegate import foreground_delegation_count


@pytest.fixture(autouse=True)
def _clean_registry():
    delegate_mod._foreground_delegations.clear()
    yield
    delegate_mod._foreground_delegations.clear()


def test_count_is_zero_when_nothing_is_in_flight():
    assert foreground_delegation_count() == 0


def test_count_reflects_each_tracked_run():
    delegate_mod._foreground_delegations.add("run-a")
    assert foreground_delegation_count() == 1
    delegate_mod._foreground_delegations.add("run-b")
    assert foreground_delegation_count() == 2
    delegate_mod._foreground_delegations.discard("run-a")
    assert foreground_delegation_count() == 1


def test_the_same_run_is_not_double_counted():
    # A set, not a counter: re-adding one run_id must not inflate the count,
    # or a late result could be deferred forever.
    delegate_mod._foreground_delegations.add("run-a")
    delegate_mod._foreground_delegations.add("run-a")
    assert foreground_delegation_count() == 1


def test_discard_of_an_unknown_run_is_a_no_op():
    # The finally clause runs on every exit path, including ones where the
    # add never happened; it must never raise.
    delegate_mod._foreground_delegations.discard("never-added")
    assert foreground_delegation_count() == 0


def test_a_cancelled_await_stops_counting_as_foreground():
    """The barge-in case, shaped like the real handler: the add/discard live
    INSIDE the coroutine that awaits the shielded task, so the finally runs
    when pipecat cancels that coroutine. Once the voice turn's await is
    cancelled the turn is no longer waiting on the call, so late results must
    stop deferring — even though the detached work keeps running."""

    async def scenario() -> int:
        started = asyncio.Event()

        async def slow_work() -> str:
            started.set()
            await asyncio.sleep(3600)
            return "done"

        task = asyncio.create_task(slow_work())

        async def voice_turn() -> str:
            delegate_mod._foreground_delegations.add("run-x")
            try:
                return await asyncio.shield(task)
            finally:
                delegate_mod._foreground_delegations.discard("run-x")

        waiter = asyncio.create_task(voice_turn())
        await started.wait()
        await asyncio.sleep(0)
        assert foreground_delegation_count() == 1        # in flight: defer

        waiter.cancel()                                  # the barge-in
        with pytest.raises(asyncio.CancelledError):
            await waiter

        assert not task.done()                           # work survives it
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return foreground_delegation_count()

    assert asyncio.run(scenario()) == 0
