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
    res = logic.prepare_commit("nothing", ["a.txt"])
    assert res["ok"] is False


def test_commit_flow(repo):
    (repo / "a.txt").write_text("two\n")
    st = logic.git_status()
    assert st["clean"] is False

    draft = logic.prepare_commit("update a", ["a.txt"])
    assert draft["ok"] is True
    assert "update a" in draft["summary"]

    res = logic.commit(draft["action_id"])
    assert res["ok"] is True
    assert logic.git_status()["clean"] is True
    assert "update a" in git(repo, "log", "-1", "--pretty=%s")


def test_commit_rejects_unknown_or_reused_id(repo):
    assert logic.commit(9999)["ok"] is False
    (repo / "a.txt").write_text("two\n")
    draft = logic.prepare_commit("x", ["a.txt"])
    assert logic.commit(draft["action_id"])["ok"] is True
    # second use of the same id must fail — a draft executes exactly once
    assert logic.commit(draft["action_id"])["ok"] is False


def test_expired_draft_rejected(repo, monkeypatch):
    (repo / "a.txt").write_text("two\n")
    draft = logic.prepare_commit("x", ["a.txt"])
    monkeypatch.setattr(logic, "DRAFT_TTL_SECONDS", -1)
    assert logic.commit(draft["action_id"])["ok"] is False
    rows = logic.list_actions()["actions"]
    assert rows[0]["status"] == "expired"


def test_push_flow(repo):
    (repo / "a.txt").write_text("two\n")
    assert logic.prepare_push()["ok"] is False  # nothing to push yet
    d = logic.prepare_commit("c2", ["a.txt"])
    logic.commit(d["action_id"])

    draft = logic.prepare_push()
    assert draft["ok"] is True
    assert "1 commit" in draft["summary"]
    res = logic.push(draft["action_id"])
    assert res["ok"] is True
    assert logic.git_status()["ahead"] == 0


def test_push_uses_explicit_refspec_so_upstream_mismatch_cannot_fail_it(repo):
    """2026-08-23 / 2026-08-30 (live): a branch cut from main inherits
    origin/main as upstream, and a bare `git push` then refuses with 'the
    upstream branch of your current branch does not match the name of your
    current branch'. The push must name its branch."""
    git(repo, "checkout", "-b", "feature/x", "--track", "origin/main")
    (repo / "b.txt").write_text("b\n")
    d = logic.prepare_commit("feature commit", ["b.txt"])
    logic.commit(d["action_id"])
    draft = logic.prepare_push()
    assert draft["ok"] is True
    res = logic.push(draft["action_id"])
    assert res["ok"] is True, res
    remote_heads = git(repo, "ls-remote", "--heads", "origin", "feature/x")
    assert "refs/heads/feature/x" in remote_heads
    assert git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/feature/x"


def test_push_refuses_if_head_moved_since_the_draft(repo):
    """A confirm must never push a branch the user did not preview."""
    (repo / "a.txt").write_text("two\n")
    d = logic.prepare_commit("c2", ["a.txt"])
    logic.commit(d["action_id"])
    draft = logic.prepare_push()
    git(repo, "checkout", "-b", "elsewhere")
    res = logic.push(draft["action_id"])
    assert res["ok"] is False
    assert "HEAD moved" in res["error"]
    assert "main" in res["error"] and "elsewhere" in res["error"]


def test_stale_lock_reported_precisely_not_auto_deleted(repo):
    """MORTIMER_AGENT_TRUST_PLAN.md D15: a held index.lock must produce the
    precise path/age/remove-command message, and the file itself must be
    left in place — no auto-deletion, even though this test's lock is
    trivially "stale" by wall-clock age."""
    (repo / "a.txt").write_text("two\n")
    lock_path = repo / ".git" / "index.lock"
    lock_path.write_text("")
    try:
        res = logic.prepare_commit("blocked by lock", ["a.txt"])
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
        res = logic.prepare_commit("blocked by old lock", ["a.txt"])
        assert res["ok"] is False
        assert "older than expected" in res["error"]
    finally:
        lock_path.unlink(missing_ok=True)


def test_recent_lock_has_no_stale_note(repo):
    (repo / "a.txt").write_text("two\n")
    lock_path = repo / ".git" / "index.lock"
    lock_path.write_text("")
    try:
        res = logic.prepare_commit("blocked by fresh lock", ["a.txt"])
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
    d = logic.prepare_commit("audited", ["a.txt"])
    logic.commit(d["action_id"])
    rows = logic.list_actions()["actions"]
    assert rows[0]["tool"] == "git_commit"
    assert rows[0]["status"] == "committed"


class TestPrepareCommitNamesItsFiles:
    """MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE1 — prepare_commit stages ONLY
    the files it is given (it used to `git add -A`: actions #22 and #26
    put 61 and 62 files on main under one-line messages), and commit()
    refuses an index that no longer matches the draft."""

    def test_prepare_commit_requires_paths(self, repo):
        (repo / "a.txt").write_text("two\n")
        for paths in ([], None, ["", "  "]):
            res = logic.prepare_commit("msg", paths)
            assert res["ok"] is False
            assert "name the files" in res["error"]
        # nothing was staged by the refusal
        assert git(repo, "diff", "--cached", "--name-only") == ""

    def test_prepare_commit_stages_only_named_paths(self, repo):
        (repo / "a.txt").write_text("two\n")
        (repo / "b.txt").write_text("b\n")
        draft = logic.prepare_commit("only a", ["a.txt"])
        assert draft["ok"] is True, draft
        assert git(repo, "diff", "--cached", "--name-only") == "a.txt"
        assert "1 file(s)" in draft["summary"] and "a.txt" in draft["summary"]
        assert "b.txt" not in draft["summary"]
        res = logic.commit(draft["action_id"])
        assert res["ok"] is True, res
        assert git(repo, "show", "--stat", "--pretty=", "HEAD").count(".txt") == 1
        assert "b.txt" in logic.git_status()["changed_files"]  # still dirty, untouched

    def test_prepare_commit_refuses_an_unchanged_path(self, repo):
        (repo / "a.txt").write_text("two\n")
        res = logic.prepare_commit("msg", ["a.txt", "nope.txt"])
        assert res["ok"] is False
        assert "not changed in the working tree" in res["error"]
        assert res["error"].endswith(": nope.txt")  # only the unchanged one is named
        assert git(repo, "diff", "--cached", "--name-only") == ""

    def test_prepare_commit_refuses_a_directory(self, repo):
        """A directory (or ".") would stage everything under it — `git add
        -A` by another name. Each changed FILE must be named."""
        (repo / "sub").mkdir()
        (repo / "sub" / "x.txt").write_text("x\n")
        for d in ("sub", "sub/", "."):
            res = logic.prepare_commit("msg", [d])
            assert res["ok"] is False, d
            assert "not a directory" in res["error"]
            assert "sub/x.txt" in res["error"]  # the hint names the real file
        assert git(repo, "diff", "--cached", "--name-only") == ""

    def test_prepare_commit_accepts_a_new_file_in_a_new_dir_and_a_space(self, repo):
        """Two real-git facts (2026-09-07): porcelain v1 quotes a path with
        a space, and an untracked file in a new directory collapses to
        `dir/` — both would fail a naive membership test. `-z -uall` sees
        the files as named."""
        (repo / "new dir").mkdir()
        (repo / "new dir" / "my file.txt").write_text("hi\n")
        draft = logic.prepare_commit("spaces", ["new dir/my file.txt"])
        assert draft["ok"] is True, draft
        assert git(repo, "diff", "--cached", "--name-only", "-z").rstrip("\0") == "new dir/my file.txt"

    def test_prepare_commit_refuses_when_unnamed_files_are_already_staged(self, repo):
        """`git commit` commits the whole index. Something staged earlier
        (by hand, or a previous `git add -A`) must be named or unstaged —
        never silently included."""
        (repo / "a.txt").write_text("two\n")
        (repo / "b.txt").write_text("b\n")
        git(repo, "add", "b.txt")
        res = logic.prepare_commit("only a", ["a.txt"])
        assert res["ok"] is False
        assert "did not name" in res["error"] and "b.txt" in res["error"]
        assert "git restore --staged b.txt" in res["error"]

    def test_commit_refuses_when_staged_set_drifted(self, repo):
        (repo / "a.txt").write_text("two\n")
        (repo / "b.txt").write_text("b\n")
        draft = logic.prepare_commit("only a", ["a.txt"])
        assert draft["ok"] is True
        git(repo, "add", "b.txt")  # drift between draft and confirm
        res = logic.commit(draft["action_id"])
        assert res["ok"] is False
        assert "drifted" in res["error"] and "b.txt" in res["error"]
        assert "prepare the commit again" in res["error"]
        # nothing was committed, and the draft is spent
        assert "init" == git(repo, "log", "-1", "--pretty=%s")
        assert logic.list_actions()["actions"][0]["status"] == "failed"
        assert logic.commit(draft["action_id"])["ok"] is False

    def test_prepare_commit_stages_a_deletion(self, repo):
        (repo / "a.txt").unlink()
        draft = logic.prepare_commit("drop a", ["a.txt"])
        assert draft["ok"] is True, draft
        assert logic.commit(draft["action_id"])["ok"] is True
        assert "a.txt" not in git(repo, "ls-files")


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
