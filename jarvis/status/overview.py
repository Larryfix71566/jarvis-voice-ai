"""`system_overview()` — Mortimer's configuration at a glance (spec T2.3).

Agents and MCP servers are read with the same plain `yaml.safe_load` the
loaders use (no agent is constructed); workloads come from the one access
config loader; every flag is read by its EXISTING reader, never a generic
parser (R8). `knowledge_overview()` is the body of the sidecar's
`/api/knowledge` handler, moved here so the endpoint and the overview share
it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_PATH = REPO_ROOT / "config" / "agents.yaml"
MCP_SERVERS_PATH = REPO_ROOT / "config" / "mcp_servers.yaml"


def _flag_readers() -> dict[str, Callable[[], bool]]:
    from jarvis import clipboard, graphs, keyhealth, speaker
    from jarvis.agents.base import model_routing_env_enabled
    from jarvis.bot.ui_control import ui_control_enabled
    from jarvis.council.council import _council_enabled
    from jarvis.memory_automation import memory_automation_enabled
    from jarvis.status import status_enabled
    from mcp_servers.mcp_screen.logic import screen_enabled

    return {
        "JARVIS_UI_CONTROL_ENABLED": ui_control_enabled,
        "JARVIS_SCREEN_ENABLED": screen_enabled,
        "JARVIS_CLIPBOARD_ENABLED": clipboard.clipboard_enabled,
        "JARVIS_SPEAKER_GATE_ENABLED": speaker.enabled,
        "JARVIS_MEMORY_AUTOMATION_ENABLED": memory_automation_enabled,
        "JARVIS_MODEL_ROUTING_ENABLED": model_routing_env_enabled,
        "JARVIS_KEY_HEALTH_ENABLED": keyhealth.enabled,
        "JARVIS_GRAPHS_ENABLED": graphs.graphs_enabled,
        "JARVIS_COUNCIL_ENABLED": _council_enabled,
        "JARVIS_STATUS_TOOLS_ENABLED": status_enabled,
    }


def flags() -> dict[str, str]:
    return {name: ("on" if reader() else "off")
            for name, reader in _flag_readers().items()}


def _agents(path: Path) -> list[dict[str, Any]]:
    from jarvis.agents.base import MAX_TOOL_ITERATIONS

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        {
            "name": entry["name"],
            "display_name": entry.get("display_name", entry["name"]),
            "model_profile": entry.get("model_profile"),
            "mcp_servers": list(entry.get("mcp_servers") or []),
            "max_iterations": int(entry.get("max_iterations", MAX_TOOL_ITERATIONS)),
        }
        for entry in data.get("sub_agents") or []
    ]


def _mcp_servers(path: Path) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [str(s["name"]) for s in data.get("servers") or [] if isinstance(s, dict)]


def _workloads() -> dict[str, dict[str, Any]]:
    from jarvis.model_routing import ModelRouteError, load_access_config

    try:
        access = load_access_config()
    except ModelRouteError:
        return {}
    return {
        str(name): {"profile": w.get("profile"), "route": w.get("route", "direct_api")}
        for name, w in sorted((access.get("workloads") or {}).items())
        if isinstance(w, dict)
    }


def knowledge_overview() -> dict:
    """K5 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — the four layers, with
    counts, in one read-only call.

    The specific thing this exists to prevent: on 2026-08-18 the store
    held 180 facts and ~14 reached the Supervisor, and that was
    discoverable ONLY by reading a `memory_context_facts_dropped` log
    line. Truncation must be visible in the console, not archaeology.
    `dropped` is computed by rendering the context and comparing — the
    same code path the prompt uses, so the number cannot drift from
    reality."""
    from jarvis import memory as memory_module
    from jarvis.db import get_conn as _get_conn
    from jarvis.db import run_migrations

    run_migrations()

    tiers: dict[str, int] = {}
    archived = 0
    live = 0
    try:
        with _get_conn() as conn:
            for tier, n in conn.execute(
                "SELECT COALESCE(tier,'project'), COUNT(*) FROM memories "
                "WHERE kind='fact' AND archived_at IS NULL GROUP BY 1"
            ):
                tiers[str(tier)] = int(n)
            live = sum(tiers.values())
            archived = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE kind='fact' "
                "AND archived_at IS NOT NULL"
            ).fetchone()[0]
            procedures = {
                str(st): int(n)
                for st, n in conn.execute(
                    "SELECT status, COUNT(*) FROM procedures GROUP BY 1"
                )
            }
    except Exception:  # noqa: BLE001 — a panel must never break the sidecar
        logger.exception("knowledge_overview_read_failed")
        return {"ok": False, "error": "could not read the knowledge store"}

    # How many facts actually reach the prompt right now.
    logging.disable(logging.WARNING)
    try:
        rendered = memory_module.render_memory_context()
    finally:
        logging.disable(logging.NOTSET)
    reaching = len([l for l in rendered.splitlines() if l.startswith("- ")])

    try:
        from jarvis.workflows import load_workflows

        workflows = [
            {"name": w.name, "source": w.source, "has_done_when": bool(w.done_when)}
            for w in load_workflows()
        ]
    except Exception:  # noqa: BLE001
        workflows = []

    # K3 skills. Both numbers matter and they are deliberately separate:
    # `on_disk` is what has been imported, `enabled` is what has been
    # reviewed and is actually loaded. A large gap is the normal, safe
    # state after importing a community pack — not a defect to fix.
    try:
        from jarvis.agent_skills import discover, enabled_names, load_skills

        found = discover()
        skills = {
            "on_disk": len(found),
            "invalid": len([1 for _, s, _ in found if s is None]),
            "registered": len(enabled_names()),
            "enabled": [
                {"name": s.name, "has_scripts": s.has_scripts}
                for s in load_skills()
            ],
        }
    except Exception:  # noqa: BLE001
        skills = {"on_disk": 0, "invalid": 0, "registered": 0, "enabled": []}

    return {
        "ok": True,
        "memory": {
            "live": live,
            "archived": archived,
            "tiers": tiers,
            "reaching_prompt": reaching,
            # The honest number: facts stored that the Supervisor never
            # sees, because `system` is excluded and the rest are capped.
            "not_reaching_prompt": max(0, live - reaching),
            "context_chars": len(rendered),
        },
        "procedures": procedures,
        "skills": skills,
        "workflows": workflows,
    }


def system_overview(*, agents_path: Path = AGENTS_PATH,
                    mcp_servers_path: Path = MCP_SERVERS_PATH,
                    knowledge: Callable[[], dict] = knowledge_overview) -> dict[str, Any]:
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agents": _agents(agents_path),
        "mcp_servers": _mcp_servers(mcp_servers_path),
        "workloads": _workloads(),
        "flags": flags(),
        "knowledge": knowledge(),
    }
