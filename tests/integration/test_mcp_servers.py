"""Integration tests: spawn each MCP server over stdio with the official
mcp client, assert exact tool sets, call one happy-path tool
(plan Phase 1 Tests)."""

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jarvis.db import run_migrations

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EXPECTED_TOOLS = {
    "mcp_servers.mcp_time.server": {
        "get_current_time", "resolve_date_expression", "date_add", "date_diff",
    },
    "mcp_servers.mcp_notes.server": {
        "create_note", "list_notes", "search_notes", "get_note", "update_note",
        "delete_note",
    },
    "mcp_servers.mcp_reminders.server": {
        "set_reminder", "list_reminders", "complete_reminder", "cancel_reminder",
        "get_due_reminders",
    },
    "mcp_servers.mcp_web.server": {"web_search", "get_weather"},
    "mcp_servers.mcp_system.server": {"get_system_status", "get_top_processes"},
}


def _params(module: str, extra_env: dict | None = None) -> StdioServerParameters:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["JARVIS_TIMEZONE"] = "America/New_York"
    if extra_env:
        env.update(extra_env)
    kwargs = {"command": sys.executable, "args": ["-m", module], "env": env}
    try:
        return StdioServerParameters(cwd=str(REPO_ROOT), **kwargs)
    except TypeError:  # older SDK without cwd support; cwd is inherited
        return StdioServerParameters(**kwargs)


async def _call(module: str, tool: str, arguments: dict,
                extra_env: dict | None = None) -> tuple[set[str], dict]:
    async with stdio_client(_params(module, extra_env)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            result = await session.call_tool(tool, arguments)
            payload = json.loads(result.content[0].text)
            return tools, payload


async def test_mcp_time_server():
    tools, payload = await _call(
        "mcp_servers.mcp_time.server", "get_current_time", {}
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_time.server"]
    assert {"iso", "human", "timezone", "unix"} <= set(payload)


async def test_mcp_notes_server(tmp_path):
    db = tmp_path / "int_notes.db"
    os.environ["JARVIS_DB_PATH"] = str(db)
    run_migrations()
    tools, payload = await _call(
        "mcp_servers.mcp_notes.server", "create_note",
        {"title": "Integration note", "body": "via stdio", "tags": "test"},
        {"JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_notes.server"]
    assert payload["id"] == 1
    assert "Note saved" in payload["message"]


async def test_mcp_reminders_server(tmp_path):
    db = tmp_path / "int_reminders.db"
    os.environ["JARVIS_DB_PATH"] = str(db)
    run_migrations()
    tools, payload = await _call(
        "mcp_servers.mcp_reminders.server", "set_reminder",
        {"message": "integration reminder", "due_expression": "in 2 hours"},
        {"JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_reminders.server"]
    assert payload["id"] == 1
    assert "Reminder set for" in payload["message"]


async def test_mcp_web_server():
    tools, payload = await _call(
        "mcp_servers.mcp_web.server", "get_weather", {"city": "Tokyo", "days": 1}
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_web.server"]
    assert "current" in payload and "human" in payload
    assert payload["current"]["temperature_c"] is not None


async def test_mcp_web_search_degraded_without_key():
    """No TAVILY_API_KEY -> the documented degraded-mode error dict."""
    tools, payload = await _call(
        "mcp_servers.mcp_web.server", "web_search", {"query": "ping"},
        {"TAVILY_API_KEY": ""},
    )
    assert payload["error"] == "Web search is unavailable (no API key configured)."


async def test_mcp_system_server():
    tools, payload = await _call(
        "mcp_servers.mcp_system.server", "get_system_status", {}
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_system.server"]
    assert "cpu_percent" in payload and "human" in payload
