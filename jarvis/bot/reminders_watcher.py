"""RemindersWatcher (plan Phase 7, step 7.1 — locked behavior).

Every 30 s, call ``get_due_reminders`` via ``SkillRegistry.call``. If rows
come back AND a client is currently connected, inject one user-side context
message per due row:

    "[system] The following reminders are now due: <message>. Tell the user
    naturally and briefly."

That injection makes Jarvis speak the reminder unprompted.

- The connection check runs BEFORE the tool call: get_due_reminders marks
  rows delivered atomically, so calling it while disconnected would dedupe
  reminders that were never spoken. Disconnected reminders accumulate and
  are delivered on the first tick after (re)connect.
- Dedup is the reminders table ``delivered`` flag (Phase 1 design) — there
  is deliberately no second mechanism here.
- Failures (DB locked, server down, malformed result) log a warning and the
  watcher keeps watching. It never crashes the bot.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 30.0
CONTEXT_TEMPLATE = (
    "[system] The following reminders are now due: {message}. "
    "Tell the user naturally and briefly."
)

InjectFn = Callable[[str], Awaitable[None]]
ConnectedFn = Callable[[], bool]


class RemindersWatcher:
    """Polls for due reminders and injects them into the live conversation."""

    def __init__(
        self,
        registry: Any,
        inject: InjectFn,
        is_connected: ConnectedFn,
        interval_s: float = DEFAULT_INTERVAL_S,
    ):
        self._registry = registry
        self._inject = inject
        self._is_connected = is_connected
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
        """One poll cycle. Public for tests; never raises."""
        if not self._is_connected():
            return  # accumulate; delivered flag must not be set yet
        try:
            result = await self._registry.call(
                "get_due_reminders", {}, ["mcp-reminders"]
            )
        except Exception as exc:  # noqa: BLE001 — registry.call promises not
            # to raise; if it ever does, the watcher still must not crash.
            logger.warning("reminders_watcher call failed: %s", exc)
            return
        try:
            data = json.loads(result)
            reminders = data.get("reminders") or []
        except (json.JSONDecodeError, AttributeError):
            # e.g. the registry's failure sentence — server down/DB locked.
            logger.warning("reminders_watcher unexpected result: %r", result)
            return
        for row in reminders:
            message = str(row.get("message", "")).strip()
            if message:
                await self._inject(CONTEXT_TEMPLATE.format(message=message))
