"""Tests for scripts/check_skills.py (upgrade plan §3.2, U1-G1/G2)."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "check_skills", ROOT / "scripts" / "check_skills.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mod():
    return load_module()


@pytest.fixture()
def scratch(tmp_path, mod):
    """A minimal valid project tree with one skill and one agent."""
    (tmp_path / "config").mkdir()
    (tmp_path / "mcp_servers" / "mcp_alpha").mkdir(parents=True)
    (tmp_path / "mcp_servers" / "mcp_alpha" / "server.py").write_text(
        "@mcp.tool()\ndef tool_one() -> dict:\n    pass\n"
        "@mcp.tool()\ndef tool_two() -> dict:\n    pass\n"
    )
    (tmp_path / "mcp_servers" / "mcp_alpha" / "skill.yaml").write_text(
        "name: mcp-alpha\nversion: 0.1.0\nclass: standard\n"
        "tools: [tool_one, tool_two]\nrequires_env: []\n"
        "requires_keychain: []\nscopes: []\ntest: \"true\"\n"
    )
    (tmp_path / "config" / "agents.yaml").write_text(
        "sub_agents:\n  - name: a\n    display_name: A\n"
        "    mcp_servers: [mcp-alpha]\n    description: x\n"
    )
    return tmp_path


def test_real_repo_validates(mod):
    assert mod.validate(ROOT) == []


def test_scratch_tree_validates(mod, scratch):
    assert mod.validate(scratch) == []


def test_missing_manifest_fails(mod, scratch):
    (scratch / "mcp_servers" / "mcp_alpha" / "skill.yaml").unlink()
    errors = mod.validate(scratch)
    assert any("missing skill.yaml" in e for e in errors)


def test_missing_skill_dir_fails(mod, scratch):
    (scratch / "config" / "agents.yaml").write_text(
        "sub_agents:\n  - name: a\n    display_name: A\n"
        "    mcp_servers: [mcp-ghost]\n    description: x\n"
    )
    errors = mod.validate(scratch)
    assert any("mcp-ghost" in e and "does not exist" in e for e in errors)


def test_tools_mismatch_fails(mod, scratch):
    p = scratch / "mcp_servers" / "mcp_alpha" / "skill.yaml"
    p.write_text(p.read_text().replace("tool_two", "tool_ghost"))
    errors = mod.validate(scratch)
    assert any("tools mismatch" in e for e in errors)


def test_requires_env_fails_when_unset(mod, scratch, monkeypatch):
    monkeypatch.delenv("JARVIS_TEST_MISSING_VAR", raising=False)
    p = scratch / "mcp_servers" / "mcp_alpha" / "skill.yaml"
    p.write_text(p.read_text().replace("requires_env: []", "requires_env: [JARVIS_TEST_MISSING_VAR]"))
    errors = mod.validate(scratch)
    assert any("JARVIS_TEST_MISSING_VAR" in e for e in errors)


def test_extra_agent_roster_only_validates(mod, scratch):
    """U1-G2: a fifth agent referencing only existing skills validates clean;
    referencing a missing skill fails. No code changes needed."""
    agents = scratch / "config" / "agents.yaml"
    agents.write_text(
        agents.read_text()
        + "  - name: beta\n    display_name: Beta\n"
          "    mcp_servers: [mcp-alpha]\n    description: roster-only addition\n"
    )
    assert mod.validate(scratch) == []

    agents.write_text(
        agents.read_text().replace("mcp-alpha]", "mcp-alpha]\n    mcp_servers_extra: []")
        + "  - name: ghost\n    display_name: Ghost\n"
          "    mcp_servers: [mcp-nope]\n    description: bad ref\n"
    )
    errors = mod.validate(scratch)
    assert any("mcp-nope" in e for e in errors)


def test_run_tests_flag_executes(mod, scratch):
    assert mod.validate(scratch, run_tests=True) == []
    p = scratch / "mcp_servers" / "mcp_alpha" / "skill.yaml"
    p.write_text(p.read_text().replace('test: "true"', 'test: "false"'))
    errors = mod.validate(scratch, run_tests=True)
    assert any("test command failed" in e for e in errors)
