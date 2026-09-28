"""Tenant identity (gap-closure plan GC8, contract GC-T). Column-only today:
every table carries user_id DEFAULT 'local'; nothing filters by it yet."""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

logger = logging.getLogger(__name__)
DEFAULT_USER_ID = "local"
USER_ID_ENV = "JARVIS_USER_ID"
_VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_request_user_id: ContextVar[str | None] = ContextVar(
    "jarvis_request_user_id", default=None,
)


def is_valid_user_id(value: object) -> bool:
    """Whether a user identifier is safe to use as a tenant key."""
    return isinstance(value, str) and bool(_VALID.fullmatch(value))


@contextmanager
def user_id_scope(user_id: str) -> Iterator[None]:
    """Bind an authenticated owner to the current request/session context.

    Context variables propagate into asyncio tasks created by an authenticated
    bot connection, unlike process-wide ``JARVIS_USER_ID``. This is required
    for per-user run logs and background work in the multi-client bot.
    """
    if not is_valid_user_id(user_id):
        raise ValueError("invalid authenticated user identifier")
    token: Token = _request_user_id.set(user_id)
    try:
        yield
    finally:
        _request_user_id.reset(token)

def current_user_id() -> str:
    scoped = _request_user_id.get()
    if scoped is not None:
        if not is_valid_user_id(scoped):
            # A corrupted authenticated context must fail closed. Falling
            # through to a process-wide identity could cross tenant boundaries.
            raise RuntimeError("authenticated tenant context is invalid")
        return scoped
    raw = (os.environ.get(USER_ID_ENV) or "").strip()
    if not raw:
        return DEFAULT_USER_ID
    if not _VALID.match(raw):
        logger.warning("tenant_user_id_invalid using_default=true")
        return DEFAULT_USER_ID
    return raw
