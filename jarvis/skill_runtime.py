"""Short-lived, content-free evidence from the voice SkillRegistry.

This receipt attests only that a live voice process discovered an MCP tool.
It does not attest that the tool call succeeds, that a provider is available,
or that credentials/routes are valid.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from uuid import UUID

from jarvis.tenant import is_valid_user_id

MAX_RUNTIME_SESSIONS = 8
MAX_TOOLS = 256
RUNTIME_TTL_S = 45.0
_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class RuntimeInventory:
    runtime_id: str
    owner_id: str
    tools: frozenset[str]
    complete: bool
    received_at: float


_lock = threading.Lock()
_inventories: dict[str, RuntimeInventory] = {}
# If a fresh runtime cannot be admitted because the bounded table is full, an
# intersection over only the retained sessions is incomplete evidence. Keep a
# short-lived overflow marker so readiness stays unknown until the missing
# runtime has either begun reporting successfully or its last report is stale.
_overflow_received_at: float | None = None


def validate_runtime_inventory(runtime_id: str, tools: object, complete: object) -> tuple[str, frozenset[str], bool]:
    """Validate the small public inventory before it enters process state."""
    try:
        normalized_id = str(UUID(runtime_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid_runtime_id") from None
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS:
        raise ValueError("invalid_runtime_tools")
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, str) or not _TOOL_NAME.fullmatch(tool):
            raise ValueError("invalid_runtime_tools")
        names.append(tool)
    if len(names) != len(set(names)):
        raise ValueError("duplicate_runtime_tool")
    if not isinstance(complete, bool):
        raise ValueError("invalid_runtime_completeness")
    return normalized_id, frozenset(names), complete


def update_runtime_inventory(
    runtime_id: str, tools: list[str], complete: bool, *, active: bool,
    owner_id: str = "local",
) -> None:
    """Record or remove one authenticated voice process inventory."""
    global _overflow_received_at
    if not is_valid_user_id(owner_id):
        raise ValueError("invalid_runtime_owner")
    normalized_id, names, is_complete = validate_runtime_inventory(runtime_id, tools, complete)
    now = time.monotonic()
    with _lock:
        _prune(now)
        if not active:
            existing = _inventories.get(normalized_id)
            if existing is not None and existing.owner_id != owner_id:
                raise ValueError("runtime_owner_mismatch")
            _inventories.pop(normalized_id, None)
            return
        existing = _inventories.get(normalized_id)
        if existing is not None and existing.owner_id != owner_id:
            raise ValueError("runtime_owner_mismatch")
        if normalized_id not in _inventories and len(_inventories) >= MAX_RUNTIME_SESSIONS:
            _overflow_received_at = now
            raise ValueError("runtime_capacity_exceeded")
        _inventories[normalized_id] = RuntimeInventory(
            normalized_id, owner_id, names, is_complete, now,
        )


def runtime_owner(runtime_id: str) -> str | None:
    """Return the owner of a currently fresh authenticated runtime session."""
    try:
        normalized_id = str(UUID(runtime_id))
    except (ValueError, TypeError, AttributeError):
        return None
    now = time.monotonic()
    with _lock:
        _prune(now)
        inventory = _inventories.get(normalized_id)
        return inventory.owner_id if inventory is not None else None


def current_runtime_tools() -> frozenset[str] | None:
    """Return tools present in every fresh active runtime, else unknown.

    Intersecting sessions is conservative: a catalog badge cannot promise a
    tool that is missing from one currently connected voice session.
    """
    now = time.monotonic()
    with _lock:
        _prune(now)
        if (_overflow_received_at is not None
                and now - _overflow_received_at <= RUNTIME_TTL_S):
            return None
        inventories = tuple(_inventories.values())
    if not inventories or any(not inventory.complete for inventory in inventories):
        return None
    available = set(inventories[0].tools)
    for inventory in inventories[1:]:
        available.intersection_update(inventory.tools)
    return frozenset(available)


def _prune(now: float) -> None:
    global _overflow_received_at
    expired = [key for key, value in _inventories.items()
               if now - value.received_at > RUNTIME_TTL_S]
    for key in expired:
        _inventories.pop(key, None)
    if (_overflow_received_at is not None
            and now - _overflow_received_at > RUNTIME_TTL_S):
        _overflow_received_at = None


def clear_runtime_inventories() -> None:
    """Test seam; production lifecycle removes entries through expiry/stop."""
    global _overflow_received_at
    with _lock:
        _inventories.clear()
        _overflow_received_at = None
