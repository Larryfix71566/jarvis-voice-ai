"""Read-only readiness facts for the Skills catalog.

Readiness is deliberately conservative: this module inspects configuration and
secret *presence* only. It never starts MCP servers, calls providers, or reads
secret values into a response. Unknown runtime evidence remains unknown.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from jarvis.agent_skills import (
    read_skill_registry,
    skills_workspace_enabled,
)
from jarvis.skill_catalog import SkillCatalogEntry
from jarvis.yaml_utils import load_unique_yaml_file

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SECRET_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


@dataclass(frozen=True)
class ToolInventory:
    names: frozenset[str] | None
    complete: bool


@dataclass(frozen=True)
class Readiness:
    state: str
    reason_codes: tuple[str, ...]


def configured_tool_inventory(
    *, config_path: Path | None = None, server_root: Path | None = None,
) -> ToolInventory:
    """Read names declared by configured MCP manifests without spawning them.

    A complete inventory can prove a required tool is not configured. It
    cannot prove that the running server discovered or can execute that tool.
    """
    config_file = config_path or (_REPO_ROOT / "config" / "mcp_servers.yaml")
    root = server_root or (_REPO_ROOT / "mcp_servers")
    # The configured boundary itself must be an ordinary file/directory. A
    # symlink at either root would let outside content define the inventory
    # even when each server and manifest child is checked individually.
    if config_file.is_symlink() or root.is_symlink():
        return ToolInventory(None, False)
    try:
        config = load_unique_yaml_file(config_file)
    except (OSError, UnicodeError, yaml.YAMLError):
        return ToolInventory(None, False)
    if not isinstance(config, dict) or not isinstance(config.get("servers"), list):
        return ToolInventory(None, False)

    names: set[str] = set()
    seen_servers: set[str] = set()
    complete = True
    for entry in config["servers"]:
        if not isinstance(entry, dict):
            complete = False
            continue
        server_name = entry.get("name")
        if not isinstance(server_name, str) or not _SERVER_NAME.fullmatch(server_name):
            complete = False
            continue
        if server_name in seen_servers:
            complete = False
            continue
        seen_servers.add(server_name)
        server_path = root / server_name.replace("-", "_")
        manifest_path = server_path / "skill.yaml"
        # Readiness is evidence about the configured MCP inventory root.
        # Following a symlink would let an out-of-root file claim tools as if
        # they were declared by the configured server package.
        if server_path.is_symlink() or manifest_path.is_symlink():
            complete = False
            continue
        try:
            manifest = load_unique_yaml_file(manifest_path)
        except (OSError, UnicodeError, yaml.YAMLError):
            complete = False
            continue
        if not isinstance(manifest, dict) or manifest.get("name") != server_name:
            complete = False
            continue
        tools = manifest.get("tools")
        if not isinstance(tools, list) or any(
            not isinstance(name, str) or not _TOOL_NAME.fullmatch(name)
            for name in tools
        ):
            complete = False
            continue
        names.update(tools)
    return ToolInventory(frozenset(names), complete)


def evaluate_readiness(
    entry: SkillCatalogEntry,
    *,
    tool_inventory: ToolInventory | None,
    credential_presence: Mapping[str, bool] | None,
    credential_authentication: Mapping[str, bool] | None = None,
    runtime_tools: frozenset[str] | None = None,
    revision_pins: Mapping[str, str] | None = None,
    revision_pins_complete: bool = False,
    revision_enforcement: bool | None = None,
    route_compatible: bool | None = None,
    sandbox_available: bool | None = None,
) -> Readiness:
    """Evaluate only evidence supplied by trusted host-owned services.

    `None` means unknown, not unavailable. A package digest is checked by the
    catalog; runtime pin evidence and model-route compatibility must be supplied
    separately before a skill can be called ready.
    """
    blockers: list[str] = []
    unknown: list[str] = []
    if entry.installation != "installed" or entry.revision is None:
        blockers.append("package_invalid")
    blockers.extend(entry.blockers)
    if not entry.enabled:
        blockers.append("skill_disabled")

    if revision_enforcement is False:
        unknown.append("revision_enforcement_disabled")
    elif revision_enforcement is None or revision_pins is None:
        unknown.append("revision_pin_unverified")
    elif entry.skill_id in revision_pins and revision_pins[entry.skill_id] != entry.revision:
        blockers.append("revision_digest_mismatch")
    elif entry.skill_id not in revision_pins and revision_pins_complete:
        blockers.append("revision_pin_missing")
    elif entry.skill_id not in revision_pins:
        unknown.append("revision_pin_unverified")

    for tool_name in entry.required_tools:
        if runtime_tools is not None:
            if tool_name not in runtime_tools:
                blockers.append(f"required_tool_unavailable:{tool_name}")
        elif tool_inventory is None or tool_inventory.names is None:
            unknown.append("tool_inventory_unavailable")
        elif tool_name not in tool_inventory.names:
            if tool_inventory.complete:
                blockers.append(f"required_tool_not_configured:{tool_name}")
            else:
                unknown.append("tool_inventory_incomplete")
        else:
            unknown.append("tool_runtime_unverified")

    for secret_name in entry.required_credentials:
        if not _SECRET_NAME.fullmatch(secret_name):
            blockers.append("invalid_credential_reference")
            continue
        if credential_presence is None or secret_name not in credential_presence:
            unknown.append("credential_presence_unverified")
        elif not credential_presence[secret_name]:
            blockers.append(f"required_credential_missing:{secret_name}")
        elif credential_authentication is not None and credential_authentication.get(secret_name) is False:
            blockers.append(f"required_credential_authentication_failed:{secret_name}")
        elif credential_authentication is None or credential_authentication.get(secret_name) is not True:
            unknown.append("credential_authentication_unverified")

    if route_compatible is False:
        blockers.append("model_route_incompatible")
    elif route_compatible is None:
        unknown.append("model_route_compatibility_unverified")

    if "sandbox_authoring" in entry.capabilities:
        if sandbox_available is False:
            blockers.append("sandbox_unavailable")
        elif sandbox_available is None:
            unknown.append("sandbox_availability_unverified")

    if blockers:
        state = "blocked"
    elif unknown:
        state = "unknown"
    else:
        state = "ready"
    # Stable order and bounded output make the reason list safe for the UI.
    reasons = tuple(dict.fromkeys((blockers if state == "blocked" else []) + unknown))
    return Readiness(state, reasons[:32])


def current_credential_presence(names: tuple[str, ...] | list[str]) -> dict[str, bool]:
    """Return booleans for validated credential names; never return values."""
    result: dict[str, bool] = {}
    for name in names:
        if isinstance(name, str) and _SECRET_NAME.fullmatch(name):
            result[name] = bool(os.environ.get(name))
    return result


def assess_current_readiness(
    entry: SkillCatalogEntry,
    *, tool_inventory: ToolInventory | None = None,
) -> Readiness:
    """Assess current static host evidence without starting external work."""
    _enabled, pins, version, valid = read_skill_registry()
    workspace_active = skills_workspace_enabled()
    # A voice-process receipt is only evidence of a discovered MCP tool. It
    # is deliberately not evidence of invocation success, route compatibility,
    # credential authentication, or package readiness.
    from jarvis.skill_runtime import current_runtime_tools

    return evaluate_readiness(
        entry,
        tool_inventory=tool_inventory or configured_tool_inventory(),
        runtime_tools=current_runtime_tools(),
        credential_presence=current_credential_presence(entry.required_credentials),
        revision_pins=pins if valid and version == 2 else None,
        revision_pins_complete=bool(valid and version == 2),
        revision_enforcement=workspace_active,
    )
