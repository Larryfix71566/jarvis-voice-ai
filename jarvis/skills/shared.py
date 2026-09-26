"""One SkillRegistry per PROCESS, not per session (status spec T3.1, L11).

Before this, `run_session` built and started a registry per connection and
stopped it in its teardown — so every reconnect respawned fourteen MCP
children, and a detached delegation that outlived its session lost its tools
("Available: none"). The registry is now started once, by the first session,
and reused by every later one; its owner tasks (jarvis/skills/registry.py)
make stopping it from any task safe.

Kill switch: `JARVIS_REGISTRY_SHARED_ENABLED` (default on), read ONLY in
`shared_enabled()`. Off restores the per-session registry exactly.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable

from jarvis.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

SHARED_ENABLED_ENV = "JARVIS_REGISTRY_SHARED_ENABLED"

_shared: SkillRegistry | None = None
_shared_loop: asyncio.AbstractEventLoop | None = None
_lock = asyncio.Lock()


def shared_enabled() -> bool:
    """Single enforcement point for JARVIS_REGISTRY_SHARED_ENABLED (default on)."""
    value = os.environ.get(SHARED_ENABLED_ENV, "")
    return value.strip().lower() not in ("false", "0", "no", "off")


async def get_shared_registry(
    config_path: Path,
    factory: Callable[[Path], Any] | None = None,
) -> SkillRegistry:
    """Start the process's registry once via `factory(config_path)`; reuse it
    thereafter. A start that raises (tool-name collision) is not cached."""
    global _shared, _shared_loop
    loop = asyncio.get_running_loop()
    async with _lock:
        if _shared is not None and _shared_loop is not loop:
            # Status spec T3.1 Step 0: a runner that uses one loop per
            # session makes a process-scoped registry invalid — its owner
            # tasks live on the old loop. Never hand them to a new loop.
            logger.error(
                "registry_shared_loop_changed old=%d new=%d — starting a new "
                "registry; the process-scoped registry assumes one loop",
                id(_shared_loop), id(loop))
            _shared = None
        if _shared is None:
            registry = (factory or SkillRegistry)(config_path)
            await registry.start()
            _shared, _shared_loop = registry, loop
            logger.info("registry_shared_started loop=%d", id(loop))
        else:
            # Review finding 2: every new session re-attempts servers that
            # are down — including ones that failed the first start().
            revive = getattr(_shared, "revive_down", None)
            if revive is not None:
                revive()
        return _shared


async def shutdown_shared_registry() -> None:
    """Stop the process's registry, if one was started. Never raises."""
    global _shared, _shared_loop
    registry, _shared, _shared_loop = _shared, None, None
    if registry is not None:
        try:
            await registry.stop()
        except Exception as exc:  # noqa: BLE001 — shutdown must not raise
            logger.warning("registry_shared_stop_failed error=%s", exc)


def _reset_for_tests() -> None:
    """Forget the shared registry (without stopping it) and the lock, so each
    test starts from a fresh process state on its own event loop."""
    global _shared, _shared_loop, _lock
    _shared = None
    _shared_loop = None
    _lock = asyncio.Lock()
