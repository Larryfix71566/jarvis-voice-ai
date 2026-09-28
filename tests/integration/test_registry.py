"""Integration tests for SkillRegistry against the real MCP servers over
stdio (plan Phase 2 Tests). No external APIs required."""

import json

import pytest
import yaml

from jarvis.skills.registry import REPO_ROOT, SkillRegistry

ALL_SERVERS = [
    "mcp-time", "mcp-notes", "mcp-memory", "mcp-kb", "mcp-reminders",
    "mcp-web", "mcp-system", "mcp-git", "mcp-apps", "mcp-repo", "mcp-runlog",
    "mcp-selfedit", "mcp-screen", "mcp-status",
]
# time 4, notes 7, reminders 5, web 3, system 2, git 8, apps 5, repo 5,
# selfedit 5. notes went 6 -> 7 when search_sessions (FTS5 conversation
# search) shipped; its skill.yaml and server.py were updated then but this
# count was not, and the mismatch only surfaced once the branch merged
# alongside a main that still carried the old number. repo (5) added by
# MORTIMER_AGENT_TRUST_PLAN.md D10-D12: repo_read_file, repo_list_files,
# repo_search, repo_write_file, repo_commit_write. mcp-kb (3) — the
# knowledge-base service's read-oriented tools (kb_search, kb_read,
# kb_neighbors; kb_write/kb_delete/kb_flush are logic.py-only, called
# directly by jarvis/kb_digest.py, never exposed as MCP tools) — shipped
# without this list or TOTAL_TOOLS being updated (gap-closure plan GC1).
TOTAL_TOOLS = 81  # ...+2 (2026-08-21: mcp-memory's memory_review_list/_resolve)
                  # ...+2 (MORTIMER_GRAPH_LAYER_PLAN.md GL12, 2026-09-04:
                  #   mcp-memory's memory_graph_view, mcp-runlog's graph_view)
                  # ...+1 (B2: mcp-selfedit's selfedit_verify_appearance)
                  # ...+1 (M6, MORTIMER_MEMORY_CAPACITY_PLAN.md: mcp-memory's memory_search)
                  # ...+3 (MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1:
                  #   mcp-web's research_compare_start/research_status/research_save)
                  # ...+3 (mcp-kb: kb_search/kb_read/kb_neighbors, gap-closure plan GC1)
                  # ...+1 net (MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE2,
                  #   2026-09-07: mcp-selfedit gains selfedit_read/_write/
                  #   _finish and loses selfedit_validate/_submit, which
                  #   could never complete under registry CALL_TIMEOUT=30 s)
                  # ...+5 (status spec T2.6, 2026-09-23: mcp-status's
                  #   status_models/_services/_overview/_build, log_search;
                  #   P4 adds four more -> 79)
                  # ...+4 (status spec T4.4, 2026-09-23: mcp-status's
                  #   status_catalog, status_subscription, github_prs,
                  #   github_pr_checks)
                  # ...+1 (status spec P6, 2026-09-23: mcp-web's
                  #   sports_scores)
                  # ...+1 (MORTIMER_VOICE_WORKFLOWS_PLAN.md W10, 2026-09-25:
                  #   mcp-memory's memory_restore)


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
