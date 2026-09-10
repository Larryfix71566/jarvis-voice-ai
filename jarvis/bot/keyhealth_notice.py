"""KeyHealthNotice (gap-closure plan GC5, 2026-09-04).

jarvis.keyhealth already reddens the Agents tab chip when a specialist's
API credential is refused (SubAgent.model_unusable), but the chip is only
seen when the drawer is open -- a voice user's only reliable surface is a
spoken sentence. This watcher polls the session's sub-agents and speaks
that sentence once per connection, and once more when the credential
recovers. Modeled on jarvis/bot/reminders_watcher.py's RemindersWatcher
(start/stop/tick_once).

Scope: once per CONNECTION, not once ever. `_last_spoken` lives on the
instance, and the instance lives with the session (constructed in
run_session, stopped in its `finally`), so a reconnect re-announces a
still-broken key by design -- a user reconnecting has not necessarily
heard the earlier sentence.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Awaitable, Callable, Iterable

from jarvis.prompts import KEYHEALTH_RECOVERED_TEMPLATE, KEYHEALTH_TEMPLATE

logger = logging.getLogger(__name__)

KEYHEALTH_NOTICE_INTERVAL_S = 30.0  # §6

InjectFn = Callable[[str], Awaitable[None]]
ConnectedFn = Callable[[], bool]

# One (name, detail) pair per unusable agent -- sorted so equality checks
# against the previously-spoken state are stable regardless of dict order.
_UnusableSet = tuple[tuple[str, str], ...]


class KeyHealthNotice:
    def __init__(
        self,
        inject: InjectFn,
        agents: Iterable[Any],
        is_connected: ConnectedFn,
        interval_s: float = KEYHEALTH_NOTICE_INTERVAL_S,
    ):
        self._inject = inject
        self._agents = list(agents)
        self._is_connected = is_connected
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._last_spoken: _UnusableSet = ()

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
        """One poll cycle; transient failures retry, cancellation propagates."""
        try:
            await self._tick_once()
        except Exception as exc:
            logger.warning("Key-health notice poll failed: %s", type(exc).__name__)

    async def _tick_once(self) -> None:
        if not self._is_connected():
            return
        unusable: _UnusableSet = tuple(sorted(
            {(a.name, a.model_unusable_detail) for a in self._agents if a.model_unusable}
        ))
        if unusable and unusable != self._last_spoken:
            names = ", ".join(name for name, _ in unusable)
            detail = unusable[0][1][:120]
            await self._inject(KEYHEALTH_TEMPLATE.format(agents=names, detail=detail))
            self._last_spoken = unusable
        elif not unusable and self._last_spoken:
            await self._inject(KEYHEALTH_RECOVERED_TEMPLATE)
            self._last_spoken = ()
