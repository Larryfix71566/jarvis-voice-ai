"""Best-effort short-lived MCP inventory heartbeat for Skills readiness."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from jarvis.tenant import current_user_id
from jarvis.urls import DEFAULT_ADMIN_URL

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 10.0
MAX_REPORTED_TOOLS = 256

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


def inventory_payload(runtime_id: str, tools: list[str], *, active: bool) -> dict[str, Any]:
    """Build a bounded payload; overflow becomes explicitly incomplete."""
    complete = len(tools) <= MAX_REPORTED_TOOLS
    return {
        "schema_version": 1,
        "runtime_id": runtime_id,
        "owner_id": current_user_id(),
        "active": active,
        "complete": complete,
        "tools": sorted(set(tools)) if complete else [],
    }


async def _send_inventory(payload: dict[str, Any], admin_url: str) -> None:
    import httpx

    from jarvis.auth import service_headers

    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.post(
            f"{admin_url.rstrip('/')}/api/skills/runtime-inventory",
            json=payload,
            headers=service_headers(),
        )
        response.raise_for_status()


async def run_skill_runtime_reporter(
    registry: Any,
    runtime_id: str,
    *,
    admin_url: str = DEFAULT_ADMIN_URL,
    interval_s: float = HEARTBEAT_INTERVAL_S,
    send: SendFn | None = None,
) -> None:
    """Publish loaded-tool inventory until cancelled; never affects the bot.

    Exceptions are logged by type only. Shutdown publishes an inactive receipt
    so the sidecar can drop it immediately rather than waiting for expiry.
    """
    send_inventory = send or (lambda payload: _send_inventory(payload, admin_url))
    try:
        while True:
            try:
                tools = registry.tools_for(registry.server_names)
                await send_inventory(inventory_payload(runtime_id, tools, active=True))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # best effort; readiness stays unknown
                logger.info("skill_runtime_inventory_unavailable error_type=%s",
                            type(exc).__name__[:64])
            await asyncio.sleep(interval_s)
    finally:
        try:
            await send_inventory(inventory_payload(runtime_id, [], active=False))
        except Exception as exc:  # shutdown must never affect registry teardown
            logger.info("skill_runtime_inventory_stop_unavailable error_type=%s",
                        type(exc).__name__[:64])
