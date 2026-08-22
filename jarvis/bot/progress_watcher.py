"""ProgressWatcher (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md
G12, Larry 2026-08-22: "an automated status update every 30 seconds for
agent work... if the agent finishes inside of 30 seconds then no update is
needed" / "these would be verbal updates").

Modeled on jarvis/bot/plan_watcher.py's PlanWatcher — same start()/stop()/
_run()/tick_once() shape, same "sidecar/DB unreachable = skip tick
silently" discipline. Two differences from PlanWatcher's design, both
deliberate:

1. This is a REPEATING ambient ping, not a one-shot per-transition
   announcement. As long as something is still in flight at each tick, a
   new update is spoken; PlanWatcher instead dedupes so a single
   transition is announced exactly once. Larry's own framing ("every 30
   seconds") is periodic, not "notify me once when this starts running".
2. The `while True: await asyncio.sleep(interval); tick()` shape already
   gives the "no update if it finished within 30s" behavior for free — the
   FIRST tick only fires at T+30s, and tick_once() sends nothing when
   nothing is in flight at that moment (whether because it finished, or
   because nothing was ever started).

Two data sources are polled, aggregated into ONE spoken line per tick
(never two separate utterances back to back):
- in-flight `delegate_task` runs — jarvis.runlog.store.list_runs(status=
  "running"), the SAME table the Agents tab and `python -m jarvis.runlog`
  read, so this can never disagree with what the run log itself shows.
- the admin sidecar's self-edit job — GET /api/selfedit/run, the same
  endpoint PlanWatcher's sibling docs describe for planning jobs (this
  polls the SELF-EDIT job specifically, a distinct slot in jarvis/admin/
  server.py from _plan_job).

Text is entirely CANNED, assembled from counters — never model-generated
— for the same reason the Agents-tab activity ticker is: a spoken status
update must never invent progress narrative the tool results didn't
report. TTSSpeakFrame only (never inject_context / push_context_frame),
mirroring the U5 ui/noop precedent: no LLM in this path, so it can never
trigger a further tool call or a fabricated elaboration.

Suppressed (skip the tick outright, never queued for later) whenever the
bot or user is actively speaking — SpeakingStateTracker below is a small
task observer, same D-007/Phase-3 pattern InterruptionNotifier already
uses to see BotStartedSpeakingFrame/BotStoppedSpeakingFrame, which are
born downstream of the TTS service and would not reach a normal
processor-order component.

Kill switch: JARVIS_PROGRESS_UPDATES_ENABLED=false, enforced at the
construction site in jarvis/bot/pipeline.py's run_session (same pattern
as JARVIS_PLAN_WATCHER_ENABLED).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
from typing import Any, Awaitable, Callable

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection

from mcp_servers.mcp_selfedit.logic import ADMIN_URL_ENV, DEFAULT_ADMIN_URL

logger = logging.getLogger(__name__)

# Fixed, no backoff — a deliberate, simple judgment call (see the plan's
# self-audit): Larry asked for "every 30 seconds", not a tapering cadence.
PROGRESS_UPDATE_INTERVAL_S = 30.0

SpeakFn = Callable[[str], Awaitable[None]]
ConnectedFn = Callable[[], bool]
SpeakingFn = Callable[[], bool]
FetchDelegationsFn = Callable[[], Awaitable[list[dict[str, Any]]]]
FetchSelfEditJobFn = Callable[[], Awaitable[dict[str, Any] | None]]


class SpeakingStateTracker(BaseObserver):
    """Tracks whether the bot or user is currently speaking.

    Same task-observer pattern as InterruptionNotifier (jarvis/bot/
    interruption.py) and for the identical reason: BotStartedSpeakingFrame/
    BotStoppedSpeakingFrame are born downstream of the TTS service, so a
    normal in-pipeline processor never sees them. A dedicated tiny observer
    is simpler and more honest than threading a callback through the TTS
    service itself.
    """

    def __init__(self) -> None:
        super().__init__()
        self._bot_speaking = False
        self._user_speaking = False

    def is_busy(self) -> bool:
        return self._bot_speaking or self._user_speaking

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        frame = data.frame
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif isinstance(frame, UserStartedSpeakingFrame):
            self._user_speaking = True
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_speaking = False


def _last_tool_for_run(run_id: str, db_path: Any = None) -> str | None:
    """Best-effort: the most recent tool_result event's tool name for this
    run. Never raises — a status line missing "last was X" is a cosmetic
    loss, not worth failing the whole tick over."""
    from jarvis.db import get_conn

    try:
        conn = get_conn(db_path)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT tool FROM agent_events WHERE run_id = ? AND type = 'tool_result' "
                "ORDER BY seq DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return row["tool"] if row else None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — cosmetic field, must never break the tick
        return None


async def _default_fetch_delegations(session_id: str) -> list[dict[str, Any]]:
    from jarvis.runlog.store import list_runs

    rows = list_runs(status="running", limit=50)
    out = []
    for r in rows:
        if session_id and r.get("session_id") not in (session_id, None, ""):
            continue
        out.append({
            "run_id": r.get("run_id"),
            "display_name": r.get("display_name") or r.get("agent") or "a specialist",
            "tool_count": int(r.get("tool_count") or 0),
            "last_tool": _last_tool_for_run(str(r.get("run_id") or "")),
        })
    return out


async def _default_fetch_selfedit_job(admin_url: str) -> dict[str, Any] | None:
    import httpx  # local import: keeps module import light for tests

    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{admin_url}/api/selfedit/run")
        data = resp.json()
    if not isinstance(data, dict) or not data.get("ok"):
        return None
    job = data.get("job") or {}
    return job if job.get("state") == "running" else None


def _fmt_delegation_line(d: dict[str, Any]) -> str:
    name = d.get("display_name") or "a specialist"
    n = d.get("tool_count", 0)
    calls = "call" if n == 1 else "calls"
    last = d.get("last_tool")
    tail = f", last was {last}" if last else ""
    return f"{name} still working — {n} tool {calls} in{tail}."


def _fmt_selfedit_line(job: dict[str, Any]) -> str:
    profile = job.get("profile") or "the planner"
    return f"Self-edit still running with {profile}."


class ProgressWatcher:
    """Polls in-flight delegations + the self-edit job; speaks ONE
    aggregated canned status line per tick while anything is in flight."""

    def __init__(
        self,
        speak: SpeakFn,
        is_connected: ConnectedFn,
        is_speaking: SpeakingFn,
        session_id: str = "",
        interval_s: float = PROGRESS_UPDATE_INTERVAL_S,
        admin_url: str | None = None,
        fetch_delegations: FetchDelegationsFn | None = None,
        fetch_selfedit_job: FetchSelfEditJobFn | None = None,
    ):
        self._speak = speak
        self._is_connected = is_connected
        self._is_speaking = is_speaking
        self._session_id = session_id
        self._interval_s = interval_s
        self._admin_url = admin_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL
        self._fetch_delegations = fetch_delegations or (
            lambda: _default_fetch_delegations(self._session_id)
        )
        self._fetch_selfedit_job = fetch_selfedit_job or (
            lambda: _default_fetch_selfedit_job(self._admin_url)
        )
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
        """One poll cycle. Public for tests; never raises."""
        if not self._is_connected():
            return
        if self._is_speaking():
            # Suppressed, never queued: the next tick 30s later re-checks
            # from scratch, it does not "catch up" on a skipped one.
            return

        try:
            delegations = await self._fetch_delegations()
        except Exception as exc:  # noqa: BLE001 — DB unreachable, skip silently
            logger.warning("progress_watcher delegations fetch failed: %s", exc)
            delegations = []
        try:
            selfedit_job = await self._fetch_selfedit_job()
        except Exception as exc:  # noqa: BLE001 — sidecar offline, skip silently
            logger.warning("progress_watcher selfedit fetch failed: %s", exc)
            selfedit_job = None

        lines = [_fmt_delegation_line(d) for d in delegations]
        if selfedit_job is not None:
            lines.append(_fmt_selfedit_line(selfedit_job))

        if not lines:
            return  # nothing in flight — the work finished inside the window

        text = " ".join(lines)
        await self._speak(text)
