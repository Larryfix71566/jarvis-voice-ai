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
from typing import Any, Awaitable, Callable

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
            "build = whether the Mac app was rebuilt and from which commit; "
            "location = where the user is right now: the device he is talking through first, "
            "then the internet connection (approximate). Never answer location from memory."
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
# Leave the machine (provider APIs, the subscription CLIs), so refused on a
# protected turn (I3). Wired to the sidecar in P4 (status spec T4.4).
EXTERNAL_TOPICS = frozenset({"catalog", "subscription"})
CATALOG_PATH = "/api/status/catalog"
SUBSCRIPTION_PATH = "/api/status/subscription/probe"

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
    location: Callable[[bool], Awaitable[str]] | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for system_status.
    `client_factory(base_url, timeout)` returns an httpx.AsyncClient-like
    async context manager; it is the test seam. `location(protected)`
    answers topic "location" (MORTIMER_VOICE_WORKFLOWS_PLAN.md D4/D-L6:
    pipeline.py passes the session's device-first resolver); without it
    the sidecar route answers, as before."""
    factory = client_factory or _default_client

    async def handler(arguments: dict) -> str:
        args = arguments or {}
        topic = str(args.get("topic") or "").strip()
        if topic == "location" and location is not None:
            try:
                return await location(_turn_is_protected())
            except Exception:  # noqa: BLE001 — never raised into the turn
                return "Location isn't available: the location lookup failed. Do not guess a place."
        if topic in EXTERNAL_TOPICS and _turn_is_protected():
            return PROTECTED_TURN_REFUSAL
        if topic not in TOPIC_PATHS and topic not in EXTERNAL_TOPICS:
            return f"system_status failed: unknown topic {topic!r}."
        base = admin_url or os.environ.get(ADMIN_URL_ENV) or DEFAULT_ADMIN_URL
        timeout = EXTERNAL_TIMEOUT_S if topic in EXTERNAL_TOPICS else DEFAULT_TIMEOUT_S
        force = bool(args.get("force"))
        try:
            async with factory(base, timeout) as client:
                if topic == "catalog":
                    provider = str(args.get("provider") or "all").strip() or "all"
                    resp = await client.get(CATALOG_PATH, params={
                        "provider": provider, "force": "true" if force else "false"})
                elif topic == "subscription":
                    body: dict[str, Any] = {"which": str(args.get("which") or ""),
                                            "force": force}
                    if args.get("model"):
                        body["model"] = str(args["model"])  # exactly as given
                    resp = await client.post(SUBSCRIPTION_PATH, json=body)
                else:
                    resp = await client.get(TOPIC_PATHS[topic])
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
