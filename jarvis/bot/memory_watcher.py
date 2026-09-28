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
import os

from jarvis.config import Settings
from jarvis.db import get_conn, now_iso
from jarvis.memory import (
    MEMORY_EXTRACTION_TIMEOUT_S,
    memory_extraction_v2_enabled,
    update_memory_from_session,
)
from jarvis.memory_admission import enqueue_finished_session_exchanges
from jarvis.memory_automation import process_classification_jobs
from jarvis.memory_extraction_worker import process_admission_jobs

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 300.0


def process_automation_jobs(settings: Settings, classifier) -> dict[str, int]:
    """Run one bounded classification batch with a worker-owned DB handle."""
    conn = get_conn()
    try:
        result = process_classification_jobs(
            conn, now_iso=now_iso(), classifier=classifier,
            shadow=bool(getattr(settings, "jarvis_memory_automation_shadow", True)),
            rollout_stage=getattr(settings, "jarvis_memory_automation_stage", "shadow"),
        )
        conn.commit()
        return result
    finally:
        conn.close()


def process_session_admission(settings: Settings, session_id: str) -> dict[str, int]:
    """Stage finished pairs before teardown and process one bounded stage batch."""
    if (not bool(getattr(settings, "jarvis_memory_automation_enabled", False))
            or os.environ.get("JARVIS_MEMORY_AUTOMATION_ENABLED", "false").lower()
            not in {"1", "true", "yes"}):
        return {"staged": 0, "claimed": 0, "extracted": 0, "classified": 0,
                "applied": 0, "failed": 0, "deferred": 0}
    conn = get_conn()
    try:
        staged = enqueue_finished_session_exchanges(
            conn, session_id=session_id, policy_version="b1", now_iso=now_iso(),
        )
        conn.commit()
    finally:
        conn.close()
    result = process_admission_jobs(settings)
    result["staged"] = staged
    return result


class MemorySweepWatcher:
    """Periodically folds one live session's transcript into long-term
    memory. Never raises — every tick is best-effort."""

    def __init__(
        self,
        settings: Settings,
        session_id: str,
        interval_s: float = DEFAULT_INTERVAL_S,
        automation_handler=None,
    ):
        self._settings = settings
        self._session_id = session_id
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._automation_handler = automation_handler

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
                update_memory_from_session(
                    self._settings, self._session_id,
                    # Phase 2 kill switch (MORTIMER_OPTIMIZATION_PLAN.md):
                    # when the new per-exchange worker is authoritative,
                    # this sweep narrows to summary-only so the same
                    # transcript is never re-derived into facts by two
                    # independent paths at once.
                    extract_facts_and_observations=not memory_extraction_v2_enabled(),
                ),
                timeout=MEMORY_EXTRACTION_TIMEOUT_S,
            )
            if (self._automation_handler is not None and
                    os.environ.get("JARVIS_MEMORY_AUTOMATION_ENABLED", "false").lower() in {"1", "true", "yes"}):
                # Model classification is background work. Run both SQLite
                # ownership and provider execution off the live voice loop.
                await asyncio.to_thread(
                    process_automation_jobs, self._settings,
                    self._automation_handler,
                )
        except asyncio.TimeoutError:
            logger.warning("memory_sweep_timeout")
        except Exception as exc:  # noqa: BLE001 — memory must never break the pipeline
            logger.warning("memory_sweep_failed error_type=%s",
                           type(exc).__name__)
