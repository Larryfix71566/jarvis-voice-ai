"""ResearchWatcher (MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R7).

Modeled directly on jarvis/bot/plan_watcher.py's PlanWatcher — same
start()/stop()/_run()/tick_once() shape, same polling-an-HTTP-endpoint
seam (fetch_job), same log-and-keep-going discipline. A background site
comparison finishes in the SIDECAR, which has no voice; this watcher polls
GET /api/research/job and announces a TERMINAL state transition (done or
error) exactly once, keyed by (started_at, state) so a disconnect/
reconnect that missed the exact tick still only announces once.

Deliberately does NOT duplicate G12's ProgressWatcher — that covers "still
working" pings for any in-flight run generically; this watcher only
announces research's own terminal states and pushes the finished
comparison through the display pipeline (research_report pseudo-tool,
jarvis/bot/display.py), the same plan_ready convention PlanWatcher
established.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any, Awaitable, Callable

from mcp_servers.mcp_selfedit.logic import ADMIN_URL_ENV, DEFAULT_ADMIN_URL

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 5.0

DONE_TEMPLATE = "The comparison is ready ({credits} credits used) — it's on your display."
ERROR_TEMPLATE = "The site comparison failed: {error}"

SpeakFn = Callable[[str], Awaitable[None]]
DisplayFn = Callable[[dict], Awaitable[None]]
ConnectedFn = Callable[[], bool]
FetchJobFn = Callable[[], Awaitable[dict[str, Any] | None]]

_TERMINAL_STATES = frozenset({"done", "error"})


async def _default_fetch_job(admin_url: str) -> dict[str, Any] | None:
    import httpx  # local import: keeps module import light for tests

    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{admin_url}/api/research/job")
        return resp.json()


class ResearchWatcher:
    """Polls the site-comparison job and announces done/error exactly once
    per (started_at, state) transition."""

    def __init__(
        self,
        speak: SpeakFn,
        push_display: DisplayFn,
        is_connected: ConnectedFn,
        interval_s: float = DEFAULT_INTERVAL_S,
        admin_url: str | None = None,
        fetch_job: FetchJobFn | None = None,
    ):
        self._speak = speak
        self._push_display = push_display
        self._is_connected = is_connected
        self._interval_s = interval_s
        self._admin_url = admin_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL
        self._fetch_job = fetch_job or (
            lambda: _default_fetch_job(self._admin_url)
        )
        self._task: asyncio.Task | None = None
        self._announced: set[tuple[Any, str]] = set()

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
        try:
            data = await self._fetch_job()
        except Exception as exc:  # noqa: BLE001 — sidecar offline/unreachable
            logger.warning("research_watcher call failed: %s", exc)
            return
        if not isinstance(data, dict) or not data.get("ok"):
            return
        job = data.get("job") or {}
        state = job.get("state")
        started_at = job.get("started_at")
        if state not in _TERMINAL_STATES or started_at is None:
            return
        key = (started_at, state)
        if key in self._announced:
            return
        self._announced.add(key)
        await self._announce(state, job)

    async def _announce(self, state: str, job: dict[str, Any]) -> None:
        if state == "done":
            await self._speak(DONE_TEMPLATE.format(credits=job.get("credits_used", "?")))
            await self._push_research_report(job)
        elif state == "error":
            await self._speak(ERROR_TEMPLATE.format(
                error=job.get("error") or "unknown error",
            ))

    async def _push_research_report(self, job: dict[str, Any]) -> None:
        # R6/R7 — reuses jarvis/bot/display.py's existing app-message
        # machinery via a pseudo-tool name, `research_report`, rather than
        # a second display code path.
        from jarvis.bot.display import build_display_payload
        import json

        data = {
            "ok": True,
            "comparison": job.get("comparison") or "",
            "urls": job.get("urls") or [],
            "sites": job.get("sites") or [],
            "credits_used": job.get("credits_used"),
            "model": job.get("model"),
            "saved_path": job.get("saved_path"),
        }
        payload = build_display_payload(
            "analyst", "Analyst", "research_report", {}, json.dumps(data),
        )
        if payload is not None:
            await self._push_display(payload)
