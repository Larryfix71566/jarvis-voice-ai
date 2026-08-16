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


def test_stale_lock_reported_precisely_not_auto_deleted(repo):
    """MORTIMER_AGENT_TRUST_PLAN.md D15: a held index.lock must produce the
    precise path/age/remove-command message, and the file itself must be
    left in place — no auto-deletion, even though this test's lock is
    trivially "stale" by wall-clock age."""
    (repo / "a.txt").write_text("two\n")
    lock_path = repo / ".git" / "index.lock"
    lock_path.write_text("")
    try:
        res = logic.prepare_commit("blocked by lock")
        assert res["ok"] is False
        assert "git index is locked by" in res["error"]
        assert str(lock_path) in res["error"]
        assert f"rm {lock_path}" in res["error"]
        assert "created" in res["error"] and "ago" in res["error"]
        # D15: never auto-deleted.
        assert lock_path.exists()
    finally:
        lock_path.unlink(missing_ok=True)


def test_old_lock_gets_stale_note(repo, monkeypatch):
    (repo / "a.txt").write_text("two\n")
    lock_path = repo / ".git" / "index.lock"
    lock_path.write_text("")
    old_time = logic._now_utc().timestamp() - 1000
    os.utime(lock_path, (old_time, old_time))
    try:
        res = logic.prepare_commit("blocked by old lock")
        assert res["ok"] is False
        assert "older than expected" in res["error"]
    finally:
        lock_path.unlink(missing_ok=True)


def test_recent_lock_has_no_stale_note(repo):
    (repo / "a.txt").write_text("two\n")
    lock_path = repo / ".git" / "index.lock"
    lock_path.write_text("")
    try:
        res = logic.prepare_commit("blocked by fresh lock")
        assert res["ok"] is False
        assert "older than expected" not in res["error"]
    finally:
        lock_path.unlink(missing_ok=True)


def test_non_lock_git_error_unaffected(repo):
    # commit() with no such action id triggers no git call at all, but a
    # plain git failure (nonexistent branch checkout) must pass through
    # unchanged rather than being misidentified as a lock error.
    code, out = logic._git("checkout", "no-such-branch")
    assert code != 0
    assert "index.lock" not in out
    assert "git index is locked" not in out


def test_audit_rows_recorded(repo):
    (repo / "a.txt").write_text("two\n")
    d = logic.prepare_commit("audited")
    logic.commit(d["action_id"])
    rows = logic.list_actions()["actions"]
    assert rows[0]["tool"] == "git_commit"
    assert rows[0]["status"] == "committed"


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
