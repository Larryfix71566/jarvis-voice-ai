"""Fail-closed bind-host resolution for the sidecar and the bot (K1, K5, A8).

One implementation, two callers. THE ONLY READ OF JARVIS_BIND_HOST.

The rule, from K1: a non-loopback bind requires BOTH
JARVIS_AUTH_ENABLED=true AND at least one unrevoked client token. When
JARVIS_AUTH_ENABLED is false the bind host is FORCED to loopback
regardless of what was asked for — the kill switch that turns off
authentication must never be the switch that also opens a port.
"""

from __future__ import annotations

import logging
import os
import socket
import sqlite3
import time

from jarvis.auth import auth_enabled, count_active_tokens

logger = logging.getLogger(__name__)

LOOPBACK = "127.0.0.1"
BIND_HOST_ENV = "JARVIS_BIND_HOST"
BIND_STRICT_ENV = "JARVIS_BIND_STRICT"

# How long to wait for a non-loopback host to appear on a local
# interface. Tailscale assigns 100.x.y.z asynchronously at boot, so a
# service starting from a LaunchAgent can legitimately be early. 20s is
# long enough for tailscaled to come up and short enough that
# scripts/mortimer.sh's 25s post-launch sleep is strictly greater than it
# (F6 invariant: the health probe runs after the bind decision resolves).
BIND_WAIT_S = 20.0
BIND_POLL_S = 1.0


def _bind_strict() -> bool:
    """JARVIS_BIND_STRICT, default false (F8). When false, a requested
    non-loopback host that is simply not assigned to an interface (Tailscale
    down) falls back to loopback with a loud ERROR rather than refusing to
    start — losing remote access, not security. When true, that case is a
    hard refusal (exit 2). The 'no unrevoked token' case refuses in BOTH
    modes: that is a real misconfiguration, not an outage."""
    return (os.environ.get(BIND_STRICT_ENV) or "").strip().lower() == "true"


class BindRefused(RuntimeError):
    """Raised instead of binding. Callers log it and exit 2 (K1)."""


def is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in ("localhost", "::1", "[::1]"):
        return True
    return h == "127.0.0.1" or h.startswith("127.")


def _host_is_bindable(host: str) -> bool:
    """Is this address assigned to a local interface right now?

    Asked by attempting a throwaway bind on an ephemeral port, which is
    the exact question uvicorn will ask a moment later. stdlib only.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.bind((host, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _wait_for_host(host: str, timeout_s: float = BIND_WAIT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        if _host_is_bindable(host):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(BIND_POLL_S)


def resolve_bind_host(
    process: str, conn: sqlite3.Connection | None = None
) -> str:
    """Return the host to bind, or raise BindRefused.

    `process` is a label for logs only ("admin-sidecar" or "bot").
    """
    requested = (os.environ.get(BIND_HOST_ENV) or "").strip() or LOOPBACK

    if not auth_enabled():
        if not is_loopback(requested):
            logger.error(
                "bind_forced_loopback process=%s requested=%s reason=auth_disabled",
                process,
                requested,
            )
        return LOOPBACK

    if is_loopback(requested):
        return requested

    active = count_active_tokens(conn)
    if active == 0:
        raise BindRefused(
            f"refusing to bind {process} to {requested}: JARVIS_AUTH_ENABLED "
            f"is true but no unrevoked client token exists. Mint one with "
            f"`python -m jarvis.auth add <name>`, or unset JARVIS_BIND_HOST "
            f"to stay on {LOOPBACK}."
        )

    if not _wait_for_host(requested):
        # F8: the address is simply not present (Tailscale down, logged-out
        # node, expired key). This is an outage, not a security condition.
        if _bind_strict():
            raise BindRefused(
                f"refusing to bind {process} to {requested}: that address is "
                f"not assigned to any local interface after {BIND_WAIT_S:.0f}s "
                f"and JARVIS_BIND_STRICT=true. If it is a Tailscale address, "
                f"check `tailscale status` and `tailscale ip -4`."
            )
        logger.error(
            "bind_fell_back_to_loopback process=%s requested=%s "
            "reason=interface_absent after_s=%.0f (set JARVIS_BIND_STRICT=true "
            "to refuse instead)",
            process,
            requested,
            BIND_WAIT_S,
        )
        return LOOPBACK

    logger.info(
        "bind_resolved process=%s host=%s active_tokens=%d",
        process,
        requested,
        active,
    )
    return requested


def resolve_port(env_name: str, default: int) -> int:
    """Port from an env var, falling back to `default` on anything
    unparseable or out of range. A bad port is a configuration typo, not
    a reason to refuse to start on the address that is already gated."""
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError:
        logger.error("bind_bad_port env=%s value=%r using=%d", env_name, raw, default)
        return default
    if not (1 <= port <= 65535):
        logger.error("bind_bad_port env=%s value=%r using=%d", env_name, raw, default)
        return default
    return port
