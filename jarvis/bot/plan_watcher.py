"""PlanWatcher (MORTIMER_CONFIRMATION_AND_CAPABILITY_PLAN.md F4).

Modeled directly on jarvis/bot/reminders_watcher.py's RemindersWatcher —
the watcher that already injects spoken announcements into a live
session, with an is_connected gate — same start()/stop()/_run()/
tick_once() shape and log-and-keep-going discipline
(jarvis/bot/memory_watcher.py shares it too).

Every PLAN_WATCH_INTERVAL_S it GETs the admin sidecar's /api/plan/job
(localhost, cheap; sidecar unreachable = skip tick silently, same as a
reminders_watcher registry-call failure). On a state TRANSITION (dedupe
key: (started_at, state) — each announced at most once, even across a
disconnect/reconnect that missed the exact tick the transition happened
on):

- running -> done (single mode): speak a canned line via TTSSpeakFrame —
  the U5 ui/noop precedent applies here too: no LLM in the path, so this
  can never trigger further tool calls — and push the finished document
  to the display layer via the plan_ready pseudo-tool (jarvis/bot/
  display.py).
- running -> awaiting_choice (council mode): speak that N candidates are
  ready and name them; display is left to plan_status/the drawer (no
  single "document" exists yet to push).
- -> error: speak the error summary once.

Unlike RemindersWatcher this polls an HTTP endpoint, not an MCP tool, so
it takes a `fetch_job` async callable (default: a real httpx call to the
admin sidecar) as the seam for tests — never httpx.Client used directly
in test code.
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

DONE_TEMPLATE = "The {noun} is ready and saved to {basename}. It's on your display."
AWAITING_CHOICE_TEMPLATE = (
    "{n} candidate {noun}s are ready — say which one you'd like: {names}."
)
ERROR_TEMPLATE = "The planning job failed: {error}"

SpeakFn = Callable[[str], Awaitable[None]]
DisplayFn = Callable[[dict], Awaitable[None]]
ConnectedFn = Callable[[], bool]
FetchJobFn = Callable[[], Awaitable[dict[str, Any] | None]]

# States worth announcing at all. "running" and "idle" produce no
# transition event of their own.
_TERMINAL_STATES = frozenset({"done", "awaiting_choice", "error"})


async def _default_fetch_job(admin_url: str) -> dict[str, Any] | None:
    import httpx  # local import: keeps module import light for tests

    async with httpx.AsyncClient(timeout=3.0) as client:
        resp = await client.get(f"{admin_url}/api/plan/job")
        return resp.json()


class PlanWatcher:
    """Polls the planning-pathway job and announces completion/choice/error
    exactly once per (started_at, state) transition."""

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
            return  # accumulate; the dedupe key is unset until we can speak
        try:
            data = await self._fetch_job()
        except Exception as exc:  # noqa: BLE001 — sidecar offline/unreachable
            logger.warning("plan_watcher call failed: %s", exc)
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
        noun = "review" if job.get("review_path") else "plan"
        if state == "done":
            saved_path = job.get("saved_path")
            if saved_path:
                basename = str(saved_path).rsplit("/", 1)[-1]
                await self._speak(DONE_TEMPLATE.format(noun=noun, basename=basename))
                await self._push_plan_ready(job)
            else:
                await self._speak(
                    f"The {noun} is ready but couldn't be auto-saved: "
                    f"{job.get('save_error') or 'unknown error'}."
                )
        elif state == "awaiting_choice":
            candidates = job.get("candidates") or []
            names = ", ".join(c.get("label", "?") for c in candidates)
            await self._speak(AWAITING_CHOICE_TEMPLATE.format(
                n=len(candidates), noun=noun, names=names or "none",
            ))
        elif state == "error":
            await self._speak(ERROR_TEMPLATE.format(
                error=job.get("error") or "unknown error",
            ))

    async def _push_plan_ready(self, job: dict[str, Any]) -> None:
        # F4 — reuses jarvis/bot/display.py's existing app-message
        # machinery via a pseudo-tool name, `plan_ready`, rather than a
        # second display code path.
        from jarvis.bot.display import build_display_payload
        import json

        data = {
            "ok": True,
            "plan": job.get("plan") or "",
            "goal": job.get("goal") or "",
            "review_path": job.get("review_path"),
            "saved_path": job.get("saved_path"),
        }
        payload = build_display_payload(
            "developer", "Developer", "plan_ready", {}, json.dumps(data),
        )
        if payload is not None:
            await self._push_display(payload)
