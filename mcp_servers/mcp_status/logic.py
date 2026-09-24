"""mcp-status logic: a thin HTTP client of the admin sidecar's /api/status/*
routes (status spec T2.6, L2/L8).

The status facts are computed in the admin sidecar, which holds the vault's
keys, the device location and the key-health verdicts; this child process
never sees a secret. Reuses mcp_servers.mcp_selfedit.logic.AdminClient
(R8). Every function takes an injected `client` for tests and returns the
sidecar's JSON unchanged except for list trimming.
"""

from __future__ import annotations

from typing import Any, Callable

from mcp_servers.mcp_selfedit.logic import AdminClient

DEFAULT_TIMEOUT_S = 10.0
# For the P4 tools that leave the machine (status_catalog, status_subscription):
# under the registry's CALL_TIMEOUT = 30.0.
EXTERNAL_TIMEOUT_S = 28.0
MAX_LIST_ITEMS = 200
SIDECAR_DOWN = {"ok": False, "error": "the admin sidecar is not reachable."}


def _client(client: Any, timeout: float = DEFAULT_TIMEOUT_S) -> Any:
    return client if client is not None else AdminClient(timeout=timeout)


def _trim(payload: Any) -> Any:
    """Cap every top-level list at MAX_LIST_ITEMS, recording what was cut."""
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    trimmed = {}
    for key, value in payload.items():
        if isinstance(value, list) and len(value) > MAX_LIST_ITEMS:
            out[key] = value[:MAX_LIST_ITEMS]
            trimmed[key] = len(value)
    if trimmed:
        out["trimmed"] = trimmed
    return out


def _get(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _trim(fn())
    except Exception:  # noqa: BLE001 — transport failure is a result, not a crash
        return dict(SIDECAR_DOWN)


def status_models(client: Any = None) -> dict[str, Any]:
    c = _client(client)
    return _get(lambda: c.get("/api/status/models"))


def status_services(client: Any = None) -> dict[str, Any]:
    c = _client(client)
    return _get(lambda: c.get("/api/status/services"))


def status_overview(client: Any = None) -> dict[str, Any]:
    c = _client(client)
    return _get(lambda: c.get("/api/status/overview"))


def status_build(client: Any = None) -> dict[str, Any]:
    c = _client(client)
    return _get(lambda: c.get("/api/status/build"))


def log_search(source: str, query: str = "", since_minutes: int = 60, limit: int = 50,
               client: Any = None) -> dict[str, Any]:
    c = _client(client)
    params = {"source": source, "query": query, "since_minutes": since_minutes,
              "limit": limit}
    return _get(lambda: c.get("/api/status/logs", params=params))
