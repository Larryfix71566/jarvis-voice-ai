"""system_status — the Supervisor's direct status tool (spec T2.5, L1/L2/L8).

A direct tool like cost_summary: no specialist, no delegation, and never a
command for the user to run. It is a thin HTTP client of the admin
sidecar's /api/status/* routes, which hold the vault's keys, the device
location and the key-health verdicts (L2). The spoken answer is built in
code by jarvis.status.summaries (I4), never by a model.

Registered only when jarvis.status.status_enabled() is on (R9): the
registration site in build_pipeline reads the switch, and the menu and the
prompt addendum follow the same boolean.
"""

from __future__ import annotations

import os
from typing import Any, Callable

from jarvis.bot.sensitive_turn import current_sensitive_turn
from jarvis.status.summaries import summarize
from mcp_servers.mcp_selfedit.logic import ADMIN_URL_ENV, DEFAULT_ADMIN_URL

SYSTEM_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "system_status",
        "description": (
            "Mortimer's own live status, read directly (no specialist, no user commands): "
            "models = configured models with key health; catalog = what a provider offers right now; "
            "subscription = whether the Claude or Codex subscription answers (uses a little quota); "
            "services = which background services are up; overview = configuration; "
            "build = whether the Mac app was rebuilt and from which commit; location = where the user is."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": ["models", "catalog", "subscription", "services",
                                                      "overview", "build", "location"]},
                "provider": {"type": "string", "description": "catalog only: a provider id, or 'all'"},
                "which": {"type": "string", "enum": ["claude", "codex"],
                          "description": "subscription only"},
                "model": {"type": "string", "description": "subscription only: exact model to try"},
                "force": {"type": "boolean", "description": "bypass the cache"},
            },
            "required": ["topic"],
        },
    },
}

TOPIC_PATHS = {
    "models": "/api/status/models",
    "services": "/api/status/services",
    "overview": "/api/status/overview",
    "build": "/api/status/build",
    "location": "/api/status/location",
}
# Leave the machine, so refused on a protected turn (I3). They exist in the
# enum from P2 so the schema does not change twice; the endpoints ship in P4.
EXTERNAL_TOPICS = frozenset({"catalog", "subscription"})
NOT_YET = {"ok": False, "error": "not available until the catalog phase ships"}

EXTERNAL_TIMEOUT_S = 30.0
DEFAULT_TIMEOUT_S = 10.0

PROTECTED_TURN_REFUSAL = (
    "system_status failed: protected turn cannot call external tool server."
)
SIDECAR_DOWN = "system_status failed: the admin sidecar is not reachable."


def _default_client(base_url: str, timeout: float) -> Any:
    import httpx

    return httpx.AsyncClient(base_url=base_url, timeout=timeout)


def _turn_is_protected() -> bool:
    holder = current_sensitive_turn.get()
    return holder is not None and holder.is_armed()


def build_system_status_tool(
    admin_url: str | None = None,
    *,
    client_factory: Callable[[str, float], Any] | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for system_status.
    `client_factory(base_url, timeout)` returns an httpx.AsyncClient-like
    async context manager; it is the test seam."""
    factory = client_factory or _default_client

    async def handler(arguments: dict) -> str:
        topic = str((arguments or {}).get("topic") or "").strip()
        if topic in EXTERNAL_TOPICS:
            if _turn_is_protected():
                return PROTECTED_TURN_REFUSAL
            return summarize(topic, NOT_YET)
        path = TOPIC_PATHS.get(topic)
        if path is None:
            return f"system_status failed: unknown topic {topic!r}."
        base = admin_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL
        timeout = EXTERNAL_TIMEOUT_S if topic in EXTERNAL_TOPICS else DEFAULT_TIMEOUT_S
        try:
            async with factory(base, timeout) as client:
                resp = await client.get(path)
        except Exception:  # noqa: BLE001 — transport failure, never raised into the turn
            return SIDECAR_DOWN
        try:
            if resp.status_code != 200:
                return f"system_status failed: the admin sidecar answered HTTP {resp.status_code}."
            payload = resp.json()
            return summarize(topic, payload)
        except Exception:  # noqa: BLE001
            return "system_status failed: the admin sidecar returned no status."

    return SYSTEM_STATUS_SCHEMA, handler
