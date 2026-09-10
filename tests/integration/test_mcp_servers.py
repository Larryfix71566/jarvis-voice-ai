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
        "delete_note", "search_sessions",
    },
    "mcp_servers.mcp_reminders.server": {
        "set_reminder", "list_reminders", "complete_reminder", "cancel_reminder",
        "get_due_reminders",
    },
    # 2026-08-25 — research_compare_start/status/save shipped with the
    # site-research feature (commit 5609692) but this set was never
    # updated, so this assertion has been failing since that merge: the
    # feature work verified `pytest tests/unit` only. If a tool is added
    # to a server, it belongs here in the same commit.
    "mcp_servers.mcp_web.server": {
        "web_search", "get_weather", "get_weather_radar",
        "research_compare_start", "research_status", "research_save",
    },
    "mcp_servers.mcp_system.server": {"get_system_status", "get_top_processes"},
    "mcp_servers.mcp_repo.server": {
        "repo_read_file", "repo_list_files", "repo_search",
        "repo_write_file", "repo_commit_write",
    },
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


async def test_mcp_notes_server(tmp_path, monkeypatch):
    db = tmp_path / "int_notes.db"
    # GC1: restore the DB path so subsequent tests cannot inherit this fixture.
    monkeypatch.setenv("JARVIS_DB_PATH", str(db))
    run_migrations()
    tools, payload = await _call(
        "mcp_servers.mcp_notes.server", "create_note",
        {"title": "Integration note", "body": "via stdio", "tags": "test"},
        {"JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_notes.server"]
    assert payload["id"] == 1
    assert "Note saved" in payload["message"]


async def test_mcp_notes_search_sessions_over_stdio(tmp_path, monkeypatch):
    """Plan Phase 5a: search_sessions finds FTS5-indexed conversation rows
    via the real stdio MCP round trip, not just the direct logic.py call."""
    db = tmp_path / "int_notes_search.db"
    # GC1: restore the DB path so subsequent tests cannot inherit this fixture.
    monkeypatch.setenv("JARVIS_DB_PATH", str(db))
    run_migrations()
    from jarvis.db import get_conn, now_iso

    with get_conn(db) as conn:
        conn.execute(
            "INSERT INTO conversations (session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("s-int-1", "user", "the garage door code is four four eight two",
             now_iso()),
        )

    tools, payload = await _call(
        "mcp_servers.mcp_notes.server", "search_sessions",
        {"query": "garage door", "limit": 5},
        {"JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_notes.server"]
    assert "results" in payload
    assert len(payload["results"]) == 1
    assert payload["results"][0]["session_id"] == "s-int-1"
    assert "garage" in payload["results"][0]["snippet"].lower()


async def test_mcp_reminders_server(tmp_path, monkeypatch):
    db = tmp_path / "int_reminders.db"
    # GC1: restore the DB path so subsequent tests cannot inherit this fixture.
    monkeypatch.setenv("JARVIS_DB_PATH", str(db))
    run_migrations()
    tools, payload = await _call(
        "mcp_servers.mcp_reminders.server", "set_reminder",
        {"message": "integration reminder", "due_expression": "in 2 hours"},
        {"JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_reminders.server"]
    assert payload["id"] == 1
    assert "Reminder set for" in payload["message"]


@pytest.mark.live
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


async def test_mcp_repo_server_read(tmp_path):
    """D10-D11 over the real stdio round trip: tool set is exactly the
    five repo_* tools (never app_*, confirming the two servers stay
    separate — see mcp_repo/logic.py's module docstring), and a read
    returns real file content from a throwaway repo."""
    repo_dir = tmp_path / "int_repo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("integration hello\n")
    db = tmp_path / "int_repo.db"
    tools, payload = await _call(
        "mcp_servers.mcp_repo.server", "repo_read_file",
        {"path": "README.md"},
        {"JARVIS_REPO_ROOT": str(repo_dir), "JARVIS_DB_PATH": str(db)},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_repo.server"]
    assert payload["ok"] is True
    assert payload["content"] == "integration hello\n"


async def test_mcp_repo_server_write_gate_over_stdio(tmp_path):
    """Retired tools refuse over the actual MCP transport, without host writes."""
    repo_dir = tmp_path / "int_repo_write"
    repo_dir.mkdir()
    db = tmp_path / "int_repo_write.db"
    extra_env = {"JARVIS_REPO_ROOT": str(repo_dir), "JARVIS_DB_PATH": str(db)}

    _, preview = await _call(
        "mcp_servers.mcp_repo.server", "repo_write_file",
        {"path": "new.txt", "content": "written via stdio\n"}, extra_env,
    )
    assert preview["ok"] is False
    assert preview["code"] == "sandbox_required"
    assert "action_id" not in preview
    assert not (repo_dir / "new.txt").exists()

    _, committed = await _call(
        "mcp_servers.mcp_repo.server", "repo_commit_write",
        {"action_id": 1}, extra_env,
    )
    assert committed["ok"] is False
    assert committed["code"] == "sandbox_required"
    assert not (repo_dir / "new.txt").exists()
    assert not db.exists()


async def test_server_startup_does_not_check_for_dependency_updates(monkeypatch):
    """GC1: a real stdio startup must work with DNS forbidden, not wait on PyPI."""
    monkeypatch.delenv("FASTMCP_CHECK_FOR_UPDATES", raising=False)
    params = _params("mcp_servers.mcp_time.server")
    params.args = ["-c", """
import runpy
import socket

def forbidden_dns(*args, **kwargs):
    raise AssertionError('MCP startup must not contact dependency registries')

socket.getaddrinfo = forbidden_dns
runpy.run_module('mcp_servers.mcp_time.server', run_name='__main__')
"""]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            assert {tool.name for tool in (await session.list_tools()).tools} == EXPECTED_TOOLS[
                "mcp_servers.mcp_time.server"
            ]
