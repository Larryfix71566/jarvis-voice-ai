"""Tests for mcp_repo logic (MORTIMER_AGENT_TRUST_PLAN.md D10-D12).

D11's resolve_repo_path adversarial table is the load-bearing part of this
file — every row corresponds to a named attack or edge case called out in
the plan, including the sibling-root regression ('/repo' vs '/repo-evil')
that a naive str.startswith containment check would let through.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_servers.mcp_repo import logic
from mcp_servers.mcp_repo.logic import RepoPathError, resolve_repo_path


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    (r / "README.md").write_text("hello\n")
    (r / "src").mkdir()
    (r / "src" / "app.py").write_text("print('hi')\n")
    (r / ".git").mkdir()
    (r / ".git" / "config").write_text("secret\n")
    (r / ".env").write_text("KEY=secret\n")
    (r / ".env.example").write_text("KEY=\n")
    (r / "id_rsa").write_text("private\n")
    (r / "config").mkdir()
    (r / "config" / "agents.yaml").write_text("sub_agents: []\n")
    (r / "CLAUDE.md").write_text("# guidance\n")
    (r / "requirements.txt").write_text("x==1\n")
    (r / ".github").mkdir()
    (r / ".github" / "workflows").mkdir()
    (r / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (r / "scripts").mkdir()
    (r / "scripts" / "run.sh").write_text("echo hi\n")

    # A sibling directory whose name string-prefix-matches the repo root —
    # the exact bug an is_relative_to check must avoid.
    sibling = tmp_path / "repo-evil"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("nope\n")

    monkeypatch.setenv("JARVIS_REPO_ROOT", str(r))
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
    return r


# ------------------------------------------------- D11 adversarial table


class TestResolveRepoPath:
    def test_simple_file_ok(self, repo):
        resolved = resolve_repo_path(repo, "README.md")
        assert resolved == (repo / "README.md").resolve()

    def test_nested_file_ok(self, repo):
        resolved = resolve_repo_path(repo, "src/app.py")
        assert resolved == (repo / "src" / "app.py").resolve()

    def test_repo_root_itself_ok(self, repo):
        resolved = resolve_repo_path(repo, ".")
        assert resolved == repo.resolve()

    def test_empty_path_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "")

    def test_whitespace_only_path_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "   ")

    def test_absolute_path_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "/etc/passwd")

    def test_nul_byte_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "README.md\x00.txt")

    def test_dotdot_traversal_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "../repo-evil/secret.txt")

    def test_dotdot_traversal_deep_rejected(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "src/../../repo-evil/secret.txt")

    def test_sibling_root_string_prefix_not_confused(self, repo):
        # Regression: '/repo-evil/x' string-startswith '/repo' but must NOT
        # be treated as contained. Passing a path already inside repo-evil
        # via traversal must fail even though the string prefix matches.
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "../repo-evil/secret.txt")

    def test_git_dir_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, ".git/config")

    def test_git_dir_denied_nested(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "a/b/.git/config")

    def test_env_file_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, ".env")

    def test_env_nested_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "web/.env")

    def test_env_example_explicitly_allowed(self, repo):
        resolved = resolve_repo_path(repo, ".env.example")
        assert resolved == (repo / ".env.example").resolve()

    def test_id_rsa_glob_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "id_rsa")

    def test_key_extension_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "secrets/prod.key")

    def test_data_dir_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "data/jarvis.db")

    def test_vault_glob_denied_outside_data(self, repo):
        # MORTIMER_CREDENTIAL_VAULT_PLAN.md S8: data/ is already a denied
        # segment; the *.vault glob covers a misplaced vault file too.
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "misplaced/secrets.vault")


class TestRepoRootHardening:
    """MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F2: a literal ${VAR} leaked
    through config must never become the repo root."""

    def _real_root(self):
        from mcp_servers.mcp_repo import logic

        return Path(logic.__file__).resolve().parents[2]

    def test_literal_placeholder_falls_back(self, monkeypatch):
        from mcp_servers.mcp_repo.logic import _repo_root

        monkeypatch.setenv("JARVIS_REPO_ROOT", "${JARVIS_REPO_ROOT}")
        assert _repo_root() == self._real_root()

    def test_empty_and_whitespace_fall_back(self, monkeypatch):
        from mcp_servers.mcp_repo.logic import _repo_root

        monkeypatch.setenv("JARVIS_REPO_ROOT", "")
        assert _repo_root() == self._real_root()
        monkeypatch.setenv("JARVIS_REPO_ROOT", "   ")
        assert _repo_root() == self._real_root()

    def test_real_value_respected(self, monkeypatch, tmp_path):
        from mcp_servers.mcp_repo.logic import _repo_root

        monkeypatch.setenv("JARVIS_REPO_ROOT", str(tmp_path))
        assert _repo_root() == tmp_path

    def test_node_modules_denied(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "web/node_modules/foo/index.js")

    def test_symlink_escape_denied(self, repo, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("nope\n")
        link = repo / "escape"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks not supported in this environment")
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "escape")

    def test_symlinked_dir_escape_denied(self, repo, tmp_path):
        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "f.txt").write_text("nope\n")
        link = repo / "escape_dir"
        try:
            link.symlink_to(outside_dir)
        except OSError:
            pytest.skip("symlinks not supported in this environment")
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "escape_dir/f.txt")

    def test_uppercase_segment_denied_case_insensitive(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, ".GIT/config")

    def test_dotdot_exact_segment_rejected_even_without_traversal_result(self, repo):
        with pytest.raises(RepoPathError):
            resolve_repo_path(repo, "..")


# --------------------------------------------------------------- reads


class TestRepoReadFile:
    def test_reads_file(self, repo):
        res = logic.repo_read_file("README.md")
        assert res["ok"] is True
        assert res["content"] == "hello\n"
        assert res["path"] == "README.md"

    def test_missing_file(self, repo):
        res = logic.repo_read_file("nope.txt")
        assert res["ok"] is False

    def test_denied_path_returns_error_not_exception(self, repo):
        res = logic.repo_read_file(".env")
        assert res["ok"] is False
        assert "not readable" in res["error"]

    def test_directory_rejected(self, repo):
        res = logic.repo_read_file("src")
        assert res["ok"] is False

    def test_size_cap_enforced(self, repo, monkeypatch):
        big = repo / "big.txt"
        big.write_text("x" * 100)
        monkeypatch.setattr(logic, "REPO_READ_MAX_BYTES", 10)
        res = logic.repo_read_file("big.txt")
        assert res["ok"] is False
        assert "byte limit" in res["error"]

    def test_binary_file_reports_error_not_garbage(self, repo):
        binf = repo / "bin.dat"
        binf.write_bytes(b"\xff\xfe\x00\x01")
        res = logic.repo_read_file("bin.dat")
        assert res["ok"] is False


class TestRepoListFiles:
    def test_lists_repo_root(self, repo):
        res = logic.repo_list_files()
        assert res["ok"] is True
        assert "README.md" in res["files"]
        assert "src/app.py" in res["files"]

    def test_denied_dirs_excluded(self, repo):
        res = logic.repo_list_files()
        assert not any(f == ".git" or f.startswith(".git/") for f in res["files"])
        assert not any(f.startswith(".env") and f != ".env.example" for f in res["files"])

    def test_subdir_scoping(self, repo):
        res = logic.repo_list_files(subdir="src")
        assert res["files"] == ["src/app.py"]

    def test_pattern_filter(self, repo):
        res = logic.repo_list_files(pattern="*.py")
        assert res["files"] == ["src/app.py"]

    def test_invalid_subdir_errors(self, repo):
        res = logic.repo_list_files(subdir=".git")
        assert res["ok"] is False


class TestRepoSearch:
    def test_finds_match(self, repo):
        res = logic.repo_search("hello")
        assert res["ok"] is True
        assert any(m["path"] == "README.md" for m in res["matches"])

    def test_empty_query_rejected(self, repo):
        res = logic.repo_search("")
        assert res["ok"] is False

    def test_denied_dirs_skipped(self, repo):
        res = logic.repo_search("secret")
        assert not any(m["path"].startswith(".git") for m in res["matches"])
        assert not any(m["path"] == ".env" for m in res["matches"])

    def test_result_cap(self, repo, monkeypatch):
        monkeypatch.setattr(logic, "REPO_SEARCH_MAX_RESULTS", 1)
        (repo / "a.txt").write_text("needle\n")
        (repo / "b.txt").write_text("needle\n")
        res = logic.repo_search("needle")
        assert len(res["matches"]) <= 1


# --------------------------------------------------------- writes (D12)


class TestRepoWriteFile:
    def test_preview_writes_nothing(self, repo):
        target = repo / "new.txt"
        res = logic.repo_write_file("new.txt", "content\n")
        assert res["ok"] is True
        assert res["pending"] is True
        assert not target.exists()

    def test_preview_reports_create_vs_overwrite(self, repo):
        res_create = logic.repo_write_file("new.txt", "x")
        assert res_create["action"] == "create"
        res_overwrite = logic.repo_write_file("README.md", "x")
        assert res_overwrite["action"] == "overwrite"

    def test_denied_read_path_rejected_at_preview(self, repo):
        res = logic.repo_write_file(".env", "x")
        assert res["ok"] is False

    def test_denied_write_only_path_rejected(self, repo):
        res = logic.repo_write_file("config/agents.yaml", "x")
        assert res["ok"] is False
        assert "not writable" in res["error"]

    def test_denied_write_only_path_case_insensitive(self, repo):
        res = logic.repo_write_file("CLAUDE.md", "x")
        assert res["ok"] is False

    def test_denied_write_segment_github(self, repo):
        res = logic.repo_write_file(".github/workflows/ci.yml", "x")
        assert res["ok"] is False

    def test_denied_write_segment_scripts(self, repo):
        res = logic.repo_write_file("scripts/new.sh", "x")
        assert res["ok"] is False

    def test_denied_write_glob_requirements(self, repo):
        res = logic.repo_write_file("requirements.txt", "x")
        assert res["ok"] is False

    def test_denied_write_glob_lockfile(self, repo):
        res = logic.repo_write_file("package-lock.json", "x")
        assert res["ok"] is False

    def test_readable_but_not_writable_path_still_readable(self, repo):
        # config/agents.yaml is readable (not in the READ deny list) but
        # not writable — the two deny lists are independent.
        read_res = logic.repo_read_file("config/agents.yaml")
        assert read_res["ok"] is True
        write_res = logic.repo_write_file("config/agents.yaml", "x")
        assert write_res["ok"] is False


class TestRepoCommitWrite:
    def test_full_create_flow(self, repo):
        preview = logic.repo_write_file("new.txt", "hello world\n")
        assert preview["ok"] is True
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is True
        assert (repo / "new.txt").read_text() == "hello world\n"

    def test_full_overwrite_flow(self, repo):
        preview = logic.repo_write_file("README.md", "changed\n")
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is True
        assert (repo / "README.md").read_text() == "changed\n"

    def test_creates_parent_dirs_inside_repo(self, repo):
        preview = logic.repo_write_file("new/nested/dir/file.txt", "x\n")
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is True
        assert (repo / "new" / "nested" / "dir" / "file.txt").read_text() == "x\n"

    def test_unknown_action_id_rejected(self, repo):
        res = logic.repo_commit_write(999999)
        assert res["ok"] is False
        assert "unknown" in res["error"] or "already used" in res["error"]

    def test_action_id_single_use(self, repo):
        preview = logic.repo_write_file("new.txt", "x\n")
        first = logic.repo_commit_write(preview["action_id"])
        assert first["ok"] is True
        second = logic.repo_commit_write(preview["action_id"])
        assert second["ok"] is False
        assert "already used" in second["error"]

    def test_expired_action_rejected(self, repo, monkeypatch):
        preview = logic.repo_write_file("new.txt", "x\n")
        monkeypatch.setattr(logic, "REPO_WRITE_ACTION_TTL_S", -1)
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is False
        assert "expired" in res["error"]

    def test_revalidated_at_commit_time_not_trusted_from_preview(self, repo):
        # Simulates the between-calls symlink-swap window: the path was
        # valid at preview time, but by commit time it resolves outside
        # the repo. Call 2 must re-run resolve_repo_path, not trust the
        # stored resolved path from call 1.
        preview = logic.repo_write_file("swap.txt", "x\n")
        target = repo / "swap.txt"
        outside = repo.parent / "outside.txt"
        outside.write_text("nope\n")
        try:
            target.symlink_to(outside)
        except OSError:
            pytest.skip("symlinks not supported in this environment")
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is False

    def test_write_is_atomic_no_partial_file_on_failure(self, repo, monkeypatch):
        preview = logic.repo_write_file("atomic.txt", "content\n")

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(os, "replace", boom)
        res = logic.repo_commit_write(preview["action_id"])
        assert res["ok"] is False
        assert not (repo / "atomic.txt").exists()
        # temp file must not be left behind either
        leftovers = [p for p in repo.iterdir() if p.name.startswith(".atomic.txt.tmp")]
        assert leftovers == []
