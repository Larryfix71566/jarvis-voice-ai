"""MemorySweepWatcher (MORTIMER_MEMORY_PROCEDURES_PLAN.md D2/D3).

Periodically folds the live session into long-term memory while it is still
running, not just at teardown — so an unclean disconnect (crash, closed
tab, kill -9) loses at most one sweep interval's worth of conversation
instead of everything discussed.

Modeled directly on jarvis/bot/reminders_watcher.py's RemindersWatcher: same
start()/stop()/_run()/tick_once() shape, same asyncio.create_task loop, same
try/except-and-log-and-keep-going discipline. Unlike RemindersWatcher, this
watcher has no is_connected gate and injects nothing into the conversation —
it purely calls update_memory_from_session on each tick.

update_memory_from_session already re-reads the last MAX_TRANSCRIPT_ROWS
fresh on every call and replaces (not appends) the summary row and each
fact by key (jarvis/memory.py D3) — calling it repeatedly on overlapping
transcript windows is naturally idempotent at the data layer. The only new
cost of sweeping is repeated LLM calls, bounded by the sweep interval.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from jarvis.config import Settings
from jarvis.memory import MEMORY_EXTRACTION_TIMEOUT_S, update_memory_from_session

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 300.0


class MemorySweepWatcher:
    """Periodically folds one live session's transcript into long-term
    memory. Never raises — every tick is best-effort."""

    def __init__(
        self,
        settings: Settings,
        session_id: str,
        interval_s: float = DEFAULT_INTERVAL_S,
    ):
        self._settings = settings
        self._session_id = session_id
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self.tick_once()

    async def tick_once(self) -> None:
        """One sweep cycle. Public for tests; never raises.

        Mirrors the D1 split at the teardown call site exactly, so a
        mid-session sweep timeout is exactly as visible in the logs as a
        teardown timeout.
        """
        try:
            await asyncio.wait_for(
                update_memory_from_session(self._settings, self._session_id),
                timeout=MEMORY_EXTRACTION_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "memory_sweep_timeout session=%s", self._session_id
            )
        except Exception:  # noqa: BLE001 — memory must never break the pipeline
            logger.exception(
                "memory_sweep_failed session=%s", self._session_id
            )
