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
        "sports_scores",  # status spec P6 (2026-09-23)
    },
    "mcp_servers.mcp_system.server": {"get_system_status", "get_top_processes"},
    "mcp_servers.mcp_repo.server": {
        "repo_read_file", "repo_list_files", "repo_search",
        "repo_write_file", "repo_commit_write",
    },
    # Status spec T2.6 + T4.4: five P2 reads, four P4 external reads.
    "mcp_servers.mcp_status.server": {
        "status_models", "status_services", "status_overview", "status_build",
        "log_search", "status_catalog", "status_subscription", "github_prs",
        "github_pr_checks",
    },
    # WS-13 P1: one read-only tool; with no credentials forwarded every
    # account answers `not_configured` and nothing is connected to.
    "mcp_servers.mcp_mail.server": {"mail_headlines"},
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


async def test_mcp_status_server():
    """Exact tool set over stdio; with no sidecar listening, a call is the
    "not reachable" result, never a crash (the child holds no secrets)."""
    tools, payload = await _call(
        "mcp_servers.mcp_status.server", "status_models", {},
        extra_env={"JARVIS_ADMIN_URL": "http://127.0.0.1:9"},
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_status.server"]
    assert payload == {"ok": False, "error": "the admin sidecar is not reachable."}


async def test_mcp_mail_server():
    """WS-13 P1 over the real stdio round trip: exactly one tool, and with
    none of the four vault names in the child's environment every account
    is `not_configured` — no socket is opened, no message is returned."""
    env = {name: "" for name in ("MAIL_ATT_USER", "MAIL_ATT_SECURE_MAIL_KEY",
                                 "MAIL_GMAIL_USER", "MAIL_GMAIL_APP_PASSWORD")}
    tools, payload = await _call(
        "mcp_servers.mcp_mail.server", "mail_headlines", {"window_hours": 24},
        extra_env=env,
    )
    assert tools == EXPECTED_TOOLS["mcp_servers.mcp_mail.server"]
    assert payload["ok"] is True
    assert payload["messages"] == []
    assert {a["status"] for a in payload["accounts"]} == {"not_configured"}
    assert {a["key"] for a in payload["accounts"]} == {"att", "gmail"}


# The child for the test below: point the accounts at a local fake IMAP server
# (127.0.0.1, test CA) and run the real server module as __main__, exactly as
# the registry starts it. Nothing else of the server is changed.
_MAIL_CHILD = """
import dataclasses, os, runpy
from mcp_servers.mcp_mail import logic
port = int(os.environ['TEST_FAKE_IMAP_PORT'])
cafile = os.environ['TEST_FAKE_IMAP_CA']
logic.ACCOUNTS = tuple(dataclasses.replace(a, host='localhost', port=port) for a in logic.ACCOUNTS)
_real_context = logic.build_ssl_context
logic.build_ssl_context = lambda cafile_=None: _real_context(cafile=cafile)
runpy.run_module('mcp_servers.mcp_mail.server', run_name='__main__')
"""


async def test_mcp_mail_failure_reason_reaches_the_hosts_stderr(tmp_path):
    """Nov 16: AT&T rejected the login, and the bot's log showed only a failed
    brief. The child's per-account line (mail_account_done ... abort=...) must
    reach the stream the host gives the child for stderr: the registry's
    stdio_client passes the bot's own stderr, which launchd writes to
    logs/bot.launchd.log. stdout is the MCP channel, so the tool call still
    working proves nothing was logged there. No credential value may appear."""
    from tests.unit.mcp_mail_fake_server import FakeIMAPServer, Faults, make_certs

    certs = make_certs(tmp_path)
    srv = FakeIMAPServer(certs, [], faults=Faults(reject_login=True)).start()
    try:
        params = _params("mcp_servers.mcp_mail.server", {
            "MAIL_ATT_USER": "att-user@example.test",
            "MAIL_ATT_SECURE_MAIL_KEY": "att-secret-value",
            "MAIL_GMAIL_USER": "", "MAIL_GMAIL_APP_PASSWORD": "",
            "JARVIS_MAIL_ENABLED": "true",
            "JARVIS_LOG_LEVEL": "INFO",
            "TEST_FAKE_IMAP_PORT": str(srv.port),
            "TEST_FAKE_IMAP_CA": certs.ca_file,
        })
        params.args = ["-c", _MAIL_CHILD]
        errlog_path = tmp_path / "child-stderr.log"
        with errlog_path.open("w") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("mail_headlines",
                                                     {"window_hours": 24, "account": "att"})
        payload = json.loads(result.content[0].text)
    finally:
        srv.stop()

    assert payload["accounts"][0]["status"] == "failed"
    assert payload["accounts"][0]["error"] == "login_rejected"
    assert srv.commands == ["CAPABILITY", "LOGIN"]
    stderr = errlog_path.read_text()
    done = [line for line in stderr.splitlines() if "mail_account_done" in line]
    assert len(done) == 1, stderr
    assert "account=att status=failed" in done[0]
    assert "phase=session abort=login_rejected" in done[0]
    for secret in ("att-user@example.test", "att-secret-value"):
        assert secret not in stderr


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
