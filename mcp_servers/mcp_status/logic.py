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


# ---- P4 (status spec T4.4): these leave the machine through the sidecar.

def _trim_catalog(payload: Any) -> Any:
    """status_catalog's lists are nested (one model list per provider):
    cap each at MAX_LIST_ITEMS, recording the provider's full count."""
    out = _trim(payload)
    if not isinstance(out, dict) or not isinstance(out.get("results"), list):
        return out
    results = []
    for r in out["results"]:
        models = r.get("models") if isinstance(r, dict) else None
        if isinstance(models, list) and len(models) > MAX_LIST_ITEMS:
            r = {**r, "models": models[:MAX_LIST_ITEMS], "models_total": len(models)}
        results.append(r)
    return {**out, "results": results}


def status_catalog(provider: str = "all", force: bool = False,
                   client: Any = None) -> dict[str, Any]:
    c = _client(client, EXTERNAL_TIMEOUT_S)
    params = {"provider": provider or "all", "force": "true" if force else "false"}
    try:
        return _trim_catalog(c.get("/api/status/catalog", params=params))
    except Exception:  # noqa: BLE001
        return dict(SIDECAR_DOWN)


def status_subscription(which: str, model: str = "", force: bool = False,
                        client: Any = None) -> dict[str, Any]:
    c = _client(client, EXTERNAL_TIMEOUT_S)
    body: dict[str, Any] = {"which": which, "force": bool(force)}
    if model:
        body["model"] = model  # exactly as given: no alias mapping
    try:
        return _trim(c.post("/api/status/subscription/probe", json=body))
    except Exception:  # noqa: BLE001
        return dict(SIDECAR_DOWN)


def github_prs(state: str = "open", limit: int = 10, client: Any = None) -> dict[str, Any]:
    c = _client(client)
    params = {"kind": "prs", "state": state, "limit": limit}
    return _get(lambda: c.get("/api/status/github", params=params))


def github_pr_checks(number: int, client: Any = None) -> dict[str, Any]:
    c = _client(client)
    params = {"kind": "checks", "number": number}
    return _get(lambda: c.get("/api/status/github", params=params))
