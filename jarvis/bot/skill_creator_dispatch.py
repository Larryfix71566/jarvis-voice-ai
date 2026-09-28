"""Live-session registry for internal Skills creator dispatch requests."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Callable

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.tenant import user_id_scope


@dataclass(frozen=True)
class ActiveDeveloperSession:
    owner_id: str
    dispatch: Callable[..., Any]
    sensitive_turn: SensitiveTurn | None


_lock = threading.RLock()
_sessions: dict[str, ActiveDeveloperSession] = {}


def register_session(session_id: str, owner_id: str, dispatch: Callable[..., Any]) -> None:
    if not session_id or not owner_id or not callable(dispatch):
        raise ValueError("invalid_developer_session")
    with _lock:
        _sessions[session_id] = ActiveDeveloperSession(
            owner_id, dispatch, current_sensitive_turn.get(),
        )


def unregister_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)


def active_session(session_id: str) -> ActiveDeveloperSession | None:
    with _lock:
        return _sessions.get(session_id)


async def dispatch_creator(
    session_id: str,
    owner_id: str,
    *,
    task: str,
    system_prompt: str,
    tool_specs: list[dict],
    tool_executor: Callable[[str, dict], Any],
    on_run_created: Callable[[str], Any],
    event_filter: Callable[[dict], dict | None] | None = None,
) -> str:
    session = active_session(session_id)
    if session is None or session.owner_id != owner_id:
        raise LookupError("developer_session_unavailable")
    if session.sensitive_turn is None or session.sensitive_turn.is_armed():
        raise PermissionError("creator_session_privacy_unavailable")
    # The route is authenticated as service-bot, but RunLogger ownership must
    # remain the verified human owner of the live bot session.
    token = current_sensitive_turn.set(session.sensitive_turn)
    try:
        with user_id_scope(owner_id):
            result = session.dispatch(
                task,
                system_prompt=system_prompt,
                tool_specs=tool_specs,
                tool_executor=tool_executor,
                on_run_created=on_run_created,
                event_filter=event_filter,
            )
            if asyncio.iscoroutine(result):
                return await result
            return str(result)
    finally:
        current_sensitive_turn.reset(token)
