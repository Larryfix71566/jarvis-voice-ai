"""Tests for mcp_git logic (upgrade plan U1.5).

Uses real git in a temp repo: init → commit → mutate → draft/commit/push.
Push target is a local bare repo, so no network is involved.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mcp_servers.mcp_git import logic


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n")
    git(r, "add", "-A")
    git(r, "commit", "-m", "init")
    git(r, "remote", "add", "origin", str(remote))
    git(r, "push", "-u", "origin", "main")

    monkeypatch.setenv("JARVIS_REPO_ROOT", str(r))
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
    return r


def test_status_clean(repo):
    st = logic.git_status()
    assert st["branch"] == "main"
    assert st["clean"] is True
    assert st["ahead"] == 0


def test_log(repo):
    out = logic.git_log(5)
    assert any("init" in c for c in out["commits"])


@pytest.mark.parametrize("operation", ["prepare_commit", "commit", "prepare_push", "push"])
def test_retired_operation_never_invokes_git(repo, monkeypatch, operation):
    from jarvis.db import get_conn, now_iso, run_migrations
    import json
    (repo / "a.txt").write_text("two\n")
    git(repo, "add", "a.txt")
    before_index = (repo / ".git/index").read_bytes()
    before_head = git(repo, "rev-parse", "HEAD")
    before_remote = git(repo, "ls-remote", "origin")
    conn = get_conn()
    run_migrations(conn)
    tool = "git_push" if "push" in operation else "git_commit"
    with conn:
        row = conn.execute(
            "INSERT INTO actions (tool, action_class, draft_payload, summary, status, created_at) "
            "VALUES (?, 'privileged', ?, 'old draft', 'pending', ?)",
            (tool, json.dumps({"message":"old", "branch":"main", "files":["a.txt"]}), now_iso()))
    def unexpected(*args, **kwargs):
        raise AssertionError("Retired operation invoked git")
    with monkeypatch.context() as m:
        m.setattr(logic, "_git", unexpected)
        m.setattr(logic, "_git_raw", unexpected)
        if operation == "prepare_commit":
            result = logic.prepare_commit("commit staged file", ["a.txt"])
        elif operation == "prepare_push":
            result = logic.prepare_push()
        else:
            result = getattr(logic, operation)(row.lastrowid)
    assert result["ok"] is False and result["code"] == "sandbox_required"
    assert not result.get("action_id")
    assert (repo / ".git/index").read_bytes() == before_index
    assert git(repo, "rev-parse", "HEAD") == before_head
    assert git(repo, "ls-remote", "origin") == before_remote
    assert logic.list_actions()["actions"][0]["status"] == "pending"


def test_read_only_status_does_not_refresh_index(repo):
    before = (repo / ".git/index").read_bytes()
    os.utime(repo / "a.txt", None)
    logic.git_status()
    assert (repo / ".git/index").read_bytes() == before


class TestRepoRootHardening:
    """MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F2 — mirrors
    test_mcp_repo_logic.py's group; both servers' _repo_root must stay
    immune to a literal ${VAR} leaked through config."""

    def _real_root(self):
        return Path(logic.__file__).resolve().parents[2]

    def test_literal_placeholder_falls_back(self, monkeypatch):
        monkeypatch.setenv("JARVIS_REPO_ROOT", "${JARVIS_REPO_ROOT}")
        assert logic._repo_root() == self._real_root()

    def test_empty_falls_back(self, monkeypatch):
        monkeypatch.setenv("JARVIS_REPO_ROOT", "")
        assert logic._repo_root() == self._real_root()

    def test_real_value_respected(self, monkeypatch, tmp_path):
        monkeypatch.setenv("JARVIS_REPO_ROOT", str(tmp_path))
        assert logic._repo_root() == tmp_path
