"""Tests for mcp_git logic (upgrade plan U1.5).

Uses real git in a temp repo: init → commit → mutate → draft/commit/push.
Push target is a local bare repo, so no network is involved.
"""

from __future__ import annotations

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


def test_prepare_commit_rejects_clean_tree(repo):
    res = logic.prepare_commit("nothing")
    assert res["ok"] is False


def test_commit_flow(repo):
    (repo / "a.txt").write_text("two\n")
    st = logic.git_status()
    assert st["clean"] is False

    draft = logic.prepare_commit("update a")
    assert draft["ok"] is True
    assert "update a" in draft["summary"]

    res = logic.commit(draft["action_id"])
    assert res["ok"] is True
    assert logic.git_status()["clean"] is True
    assert "update a" in git(repo, "log", "-1", "--pretty=%s")


def test_commit_rejects_unknown_or_reused_id(repo):
    assert logic.commit(9999)["ok"] is False
    (repo / "a.txt").write_text("two\n")
    draft = logic.prepare_commit("x")
    assert logic.commit(draft["action_id"])["ok"] is True
    # second use of the same id must fail — a draft executes exactly once
    assert logic.commit(draft["action_id"])["ok"] is False


def test_expired_draft_rejected(repo, monkeypatch):
    (repo / "a.txt").write_text("two\n")
    draft = logic.prepare_commit("x")
    monkeypatch.setattr(logic, "DRAFT_TTL_SECONDS", -1)
    assert logic.commit(draft["action_id"])["ok"] is False
    rows = logic.list_actions()["actions"]
    assert rows[0]["status"] == "expired"


def test_push_flow(repo):
    (repo / "a.txt").write_text("two\n")
    assert logic.prepare_push()["ok"] is False  # nothing to push yet
    d = logic.prepare_commit("c2")
    logic.commit(d["action_id"])

    draft = logic.prepare_push()
    assert draft["ok"] is True
    assert "1 commit" in draft["summary"]
    res = logic.push(draft["action_id"])
    assert res["ok"] is True
    assert logic.git_status()["ahead"] == 0


def test_audit_rows_recorded(repo):
    (repo / "a.txt").write_text("two\n")
    d = logic.prepare_commit("audited")
    logic.commit(d["action_id"])
    rows = logic.list_actions()["actions"]
    assert rows[0]["tool"] == "git_commit"
    assert rows[0]["status"] == "committed"
