"""Integration tests for SkillRegistry against the real MCP servers over
stdio (plan Phase 2 Tests). No external APIs required."""

import json

import pytest
import yaml

from jarvis.skills.registry import REPO_ROOT, SkillRegistry

ALL_SERVERS = [
    "mcp-time", "mcp-notes", "mcp-reminders", "mcp-web", "mcp-system",
    "mcp-git", "mcp-apps", "mcp-repo", "mcp-runlog", "mcp-selfedit",
    "mcp-screen",
]
# time 4, notes 7, reminders 5, web 3, system 2, git 8, apps 5, repo 5,
# selfedit 5. notes went 6 -> 7 when search_sessions (FTS5 conversation
# search) shipped; its skill.yaml and server.py were updated then but this
# count was not, and the mismatch only surfaced once the branch merged
# alongside a main that still carried the old number. repo (5) added by
# MORTIMER_AGENT_TRUST_PLAN.md D10-D12: repo_read_file, repo_list_files,
# repo_search, repo_write_file, repo_commit_write.
TOTAL_TOOLS = 60  # ...+2 (2026-08-21: mcp-memory's memory_review_list/_resolve)
                  # ...+1 (B2: mcp-selfedit's selfedit_verify_appearance)


@pytest.fixture
async def registry(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "reg.db"))
    from jarvis.db import run_migrations
    run_migrations()
    reg = SkillRegistry(REPO_ROOT / "config" / "mcp_servers.yaml")
    await reg.start()
    yield reg
    await reg.stop()


async def test_starts_all_servers_and_discovers_tools(registry):
    assert registry.server_names == ALL_SERVERS
    assert len(registry.openai_tools()) == TOTAL_TOOLS


async def test_tools_schema_shape(registry):
    for tool in registry.openai_tools():
        assert tool["type"] == "function"
        assert set(tool["function"]) == {"name", "description", "parameters"}
        assert tool["function"]["parameters"]["type"] == "object"


async def test_server_filtering(registry):
    time_tools = registry.openai_tools(["mcp-time"])
    assert len(time_tools) == 4
    assert {t["function"]["name"] for t in time_tools} == {
        "get_current_time", "resolve_date_expression", "date_add", "date_diff",
    }
    assert set(registry.tools_for(["mcp-notes"])) == {
        "create_note", "list_notes", "search_notes", "get_note", "update_note",
        "delete_note", "search_sessions",
    }


async def test_call_real_tool_round_trip(registry):
    result = await registry.call("get_current_time", {})
    payload = json.loads(result)
    assert {"iso", "human", "timezone", "unix"} <= set(payload)


async def test_call_note_round_trip_through_stdio(registry):
    created = json.loads(await registry.call(
        "create_note", {"title": "Registry note", "body": "via SkillRegistry",
                        "tags": "test"}))
    found = json.loads(await registry.call("search_notes", {"query": "Registry"}))
    assert any(n["id"] == created["id"] for n in found["notes"])


async def test_repo_read_round_trip_through_stdio(registry):
    """MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F2: a registry-spawned
    mcp-repo must resolve the REAL repo root. The yaml used to pass
    `JARVIS_REPO_ROOT: "${JARVIS_REPO_ROOT}"`, which expand_env_vars
    left as literal text when the variable was unset — every read then
    reported "does not exist" against a phantom root. This exact
    round-trip would have caught it before it reached a live run."""
    result = json.loads(await registry.call("repo_read_file",
                                            {"path": "README.md"}))
    assert result.get("ok") is True, result
    assert "Mortimer" in result.get("content", "")


async def test_unknown_tool_returns_string_not_raise(registry):
    result = await registry.call("definitely_not_a_tool", {})
    assert "Unknown tool" in result


async def test_stop_is_idempotent(registry):
    await registry.stop()
    await registry.stop()


async def test_tool_name_collision_raises_at_start(tmp_path):
    config = {
        "servers": [
            {"name": "time-a", "command": "python",
             "args": ["-m", "mcp_servers.mcp_time.server"], "env": {}},
            {"name": "time-b", "command": "python",
             "args": ["-m", "mcp_servers.mcp_time.server"], "env": {}},
        ]
    }
    config_path = tmp_path / "dup.yaml"
    config_path.write_text(yaml.safe_dump(config))
    reg = SkillRegistry(config_path)
    with pytest.raises(ValueError, match="collision.*time-a.*time-b"):
        await reg.start()
    await reg.stop()
