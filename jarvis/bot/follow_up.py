"""Timed checks for the Supervisor (MORTIMER_VOICE_WORKFLOWS_PLAN.md W12,
Larry 2026-09-25: option B).

Two direct Supervisor tools, so a request that used to get "there's no
timer or wait capability" (logged turns 1343, 1455, 1864, 1904) gets done:

* ``progress_updates(every_seconds)`` — how often the ProgressWatcher's
  canned "still working" line is spoken while a delegation or self-edit is
  in flight (jarvis/bot/progress_watcher.py). 0 turns it off. For the rest
  of this conversation only; the next one starts at the 30 s default.
* ``follow_up(after_seconds, check)`` — a one-shot: when the time is up the
  check comes back to the Supervisor as a context note (the same channel,
  deferral and neutralizer as a barge-in late result — pipeline.py's
  inject_late_result), and the Supervisor runs it then. Nothing is checked
  in between, and a follow-up never repeats; ``after_seconds`` 0 cancels
  every pending one.

Kill switches: JARVIS_FOLLOW_UPS_ENABLED (follow_up) and the existing
JARVIS_PROGRESS_UPDATES_ENABLED (progress_updates, which needs the watcher
to exist). Both default on; each decides registration, the tool menu
(jarvis/bot/tool_schemas.py) and the prompt addendum together.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import os
from typing import Any, Awaitable, Callable

from jarvis.bot.progress_watcher import MAX_PROGRESS_INTERVAL_S, MIN_PROGRESS_INTERVAL_S

logger = logging.getLogger(__name__)

FOLLOW_UPS_ENV = "JARVIS_FOLLOW_UPS_ENABLED"
PROGRESS_UPDATES_ENV = "JARVIS_PROGRESS_UPDATES_ENABLED"
MIN_AFTER_S = 10
MAX_AFTER_S = 1800
MAX_PENDING = 3
MAX_CHECK_CHARS = 300
# When a follow-up comes due while someone is speaking it waits, re-checking
# this often, for at most MAX_SPEAKING_WAIT_S; then it is delivered anyway
# (the note only joins the context — it cannot cut into speech).
SPEAKING_RECHECK_S = 1.0
MAX_SPEAKING_WAIT_S = 60.0


def _switch(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in ("false", "0", "no", "off")


def follow_ups_enabled() -> bool:
    return _switch(FOLLOW_UPS_ENV)


def progress_updates_enabled() -> bool:
    """The same reading pipeline.py has always given this switch, plus
    "off" (accepted by every other switch in this repo)."""
    return _switch(PROGRESS_UPDATES_ENV)


def spoken_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 120:
        return f"{seconds} seconds"
    minutes, rest = divmod(seconds, 60)
    return f"{minutes} minutes" + (f" {rest} seconds" if rest else "")


FOLLOW_UP_NOTE = (
    "[follow-up due] {ago} ago you told the user you would check back on this: "
    "{check}. Do that check now — through the tool or specialist that can answer it, "
    "never from memory — and tell the user what you found in one or two sentences."
)


class FollowUps:
    """One session's pending one-shot follow-ups."""

    def __init__(
        self,
        deliver: Callable[[str], Awaitable[bool]],
        is_speaking: Callable[[], bool],
        *,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._deliver = deliver
        self._is_speaking = is_speaking
        self._sleep = sleep
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple[asyncio.Task, int, str]] = {}

    def pending(self) -> list[dict]:
        return [{"id": fid, "after_seconds": after, "check": check}
                for fid, (_task, after, check) in sorted(self._pending.items())]

    def schedule(self, after_seconds: int, check: str) -> dict:
        check = " ".join((check or "").split())[:MAX_CHECK_CHARS]
        if not check:
            return {"ok": False, "error": "say what to check"}
        if not MIN_AFTER_S <= after_seconds <= MAX_AFTER_S:
            return {"ok": False, "error": f"after_seconds must be {MIN_AFTER_S} to {MAX_AFTER_S} "
                                          "(0 cancels pending follow-ups)"}
        if len(self._pending) >= MAX_PENDING:
            return {"ok": False, "error": f"{MAX_PENDING} follow-ups are already pending"}
        fid = next(self._ids)
        task = asyncio.create_task(self._fire(fid, after_seconds, check))
        self._pending[fid] = (task, after_seconds, check)
        logger.info("follow_up_scheduled id=%d after_s=%d", fid, after_seconds)
        return {"ok": True, "id": fid, "after_seconds": after_seconds, "check": check}

    def cancel_all(self) -> int:
        n = len(self._pending)
        for task, _after, _check in self._pending.values():
            task.cancel()
        self._pending.clear()
        if n:
            logger.info("follow_up_cancelled count=%d", n)
        return n

    async def stop(self) -> None:
        tasks = [task for task, _a, _c in self._pending.values()]
        self.cancel_all()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _fire(self, fid: int, after_seconds: int, check: str) -> None:
        try:
            await self._sleep(after_seconds)
            waited = 0.0
            while self._is_speaking() and waited < MAX_SPEAKING_WAIT_S:
                await self._sleep(SPEAKING_RECHECK_S)
                waited += SPEAKING_RECHECK_S
            self._pending.pop(fid, None)
            note = FOLLOW_UP_NOTE.format(ago=spoken_duration(after_seconds + waited), check=check)
            delivered = await self._deliver(note)
            logger.info("follow_up_due id=%d delivered=%s waited_s=%.0f", fid, delivered, waited)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a follow-up must never break the session
            self._pending.pop(fid, None)
            logger.exception("follow_up_failed id=%d", fid)


PROGRESS_UPDATES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "progress_updates",
        "description": (
            "Set how often you speak a short 'still working' line while a task "
            "you started (a delegation or a self-edit) is still running — for "
            "the rest of this conversation. every_seconds from "
            f"{MIN_PROGRESS_INTERVAL_S} to {MAX_PROGRESS_INTERVAL_S}; 0 turns "
            "the lines off. The default is 30. Lines are spoken only while "
            "something is running."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "every_seconds": {"type": "integer",
                                  "description": "seconds between lines; 0 = off"},
            },
            "required": ["every_seconds"],
        },
    },
}

FOLLOW_UP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "follow_up",
        "description": (
            "Check back on something once, after a delay the user asked for "
            "(\"wait sixty seconds then check again\", \"look again in five "
            "minutes\"). When the time is up the check comes back to you and "
            "you run it then. after_seconds from "
            f"{MIN_AFTER_S} to {MAX_AFTER_S}; 0 cancels every pending follow-up. "
            "check says exactly what to look at, self-contained."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "after_seconds": {"type": "integer"},
                "check": {"type": "string",
                          "description": "what to check when it comes due, e.g. "
                                         "'the status of the self-edit run'"},
            },
            "required": ["after_seconds", "check"],
        },
    },
}


def build_progress_updates_tool(holder: dict) -> tuple[dict, Callable[[dict], Awaitable[str]]]:
    """`holder["progress"]` is the session's ProgressWatcher, filled in by
    run_session once it exists (the tool is registered before)."""

    async def handler(arguments: dict) -> str:
        watcher = holder.get("progress")
        if watcher is None:
            return "Progress updates are not running in this session."
        try:
            seconds = int(arguments.get("every_seconds"))
            watcher.set_interval(seconds)
        except (TypeError, ValueError) as exc:
            return f"Not changed: {exc}."
        if seconds == 0:
            return "Progress updates are off for the rest of this conversation."
        return (f"Progress updates are now every {spoken_duration(seconds)} for the rest "
                "of this conversation, spoken only while a task is running.")

    return PROGRESS_UPDATES_SCHEMA, handler


def build_follow_up_tool(holder: dict) -> tuple[dict, Callable[[dict], Awaitable[str]]]:
    """`holder["follow_ups"]` is the session's FollowUps, filled in by
    run_session once the context-injection hook exists."""

    async def handler(arguments: dict) -> str:
        follow_ups = holder.get("follow_ups")
        if follow_ups is None:
            return "Follow-ups are not available in this session."
        try:
            after = int(arguments.get("after_seconds"))
        except (TypeError, ValueError):
            return "Not scheduled: after_seconds must be a whole number of seconds."
        if after == 0:
            n = follow_ups.cancel_all()
            return f"Cancelled {n} pending follow-up{'s' if n != 1 else ''}."
        result = follow_ups.schedule(after, str(arguments.get("check") or ""))
        if not result["ok"]:
            return f"Not scheduled: {result['error']}."
        return (f"Follow-up set: in {spoken_duration(after)} the check comes back to you — "
                f"{result['check']}. Tell the user when you will check; do not check now.")

    return FOLLOW_UP_SCHEMA, handler
