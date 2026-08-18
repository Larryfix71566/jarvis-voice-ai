"""Unit tests for the Workspace seam (MORTIMER_MODEL_DISCIPLINE_AND_MAC_
SHELL_PLAN.md Part D, D1-D4).

D1: SelfEditWorkspace must be behavior-identical to SelfEditService (it's
a subclass with zero overrides) — a couple of smoke tests pin that rather
than re-testing everything test_selfedit_service.py already covers.

D2-D4: AppWorkspace against a throwaway local bare git repo (no real
GitHub network calls) — clone/pull, the deny-list write boundary, the
manifest-driven validate() gate, and PR submission (with _open_pr
stubbed, since opening a real PR needs real GitHub).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jarvis.agents.workspace import (
    AppWorkspace,
    SelfEditWorkspace,
    Workspace,
    _check_app_path,
)
from jarvis.selfedit.service import SelfEditService


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


# --------------------------------------------------------- D1: SelfEditWorkspace


def test_self_edit_workspace_is_a_subclass_of_self_edit_service():
    assert issubclass(SelfEditWorkspace, SelfEditService)


def test_self_edit_workspace_satisfies_workspace_protocol(tmp_path: Path):
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "t@e.com")
    _git(work, "config", "user.name", "T")
    _git(work, "checkout", "-b", "main")
    (work / "config").mkdir()
    (work / "config" / "self_edit_allowlist.json").write_text(
        '{"allow": ["web/src/**"], "deny": []}'
    )
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    ws = SelfEditWorkspace(repo_root=work, github_token=None)
    assert isinstance(ws, Workspace)
    assert ws.describe_boundary()  # non-empty, reads the allowlist file


# ----------------------------------------------------------- D4: write boundary


@pytest.mark.parametrize("path", [
    ".git/config",
    ".github/workflows/ci.yml",
    ".env",
    ".env.production",
    "secrets.vault",
    "../outside.txt",
    "/absolute.txt",
])
def test_check_app_path_denies(path: str):
    with pytest.raises(Exception):
        _check_app_path(path)


@pytest.mark.parametrize("path", ["src/App.tsx", "README.md", "a/b/c.py"])
def test_check_app_path_allows(path: str):
    assert _check_app_path(path) == path


# ------------------------------------------------------------- D2-D3: AppWorkspace


@pytest.fixture()
def app_origin(tmp_path: Path) -> Path:
    """A throwaway bare repo standing in for the app's GitHub remote."""
    origin = tmp_path / "remote" / "demo-app.git"
    origin.parent.mkdir(parents=True)
    _git(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(origin), str(seed))
    _git(seed, "config", "user.email", "t@e.com")
    _git(seed, "config", "user.name", "T")
    _git(seed, "checkout", "-b", "main")
    (seed / "src").mkdir()
    (seed / "src" / "index.js").write_text("console.log(1);\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "init")
    _git(seed, "push", "-u", "origin", "main")
    return origin


@pytest.fixture()
def workspace(app_origin: Path, tmp_path: Path) -> AppWorkspace:
    class FakeClient:
        token = "fake-token"
        def _owner(self) -> str:
            return "fake-owner"

    return AppWorkspace(
        "demo-app", github_client=FakeClient(),
        workspaces_dir=tmp_path / "workspaces",
        remote_url=str(app_origin),
    )


def test_start_session_clones_on_first_build(workspace: AppWorkspace):
    res = workspace.start_session("add a button")
    assert res["ok"], res
    assert res["branch"].startswith("mortimer/app-build/")
    assert (workspace.repo_root / "src" / "index.js").is_file()


def test_start_session_refused_while_active(workspace: AppWorkspace):
    workspace.start_session("first")
    res = workspace.start_session("second")
    assert not res["ok"]
    assert "already active" in res["error"]


def test_propose_edit_and_validate_no_manifest(workspace: AppWorkspace):
    workspace.start_session("tweak")
    res = workspace.propose_edit("src/index.js", "console.log(2);\n", "bump")
    assert res["ok"], res
    result = workspace.validate()
    manifest_check = next(c for c in result["checks"] if c["name"] == "manifest")
    assert manifest_check["ok"]
    assert "NO CHECKS ARE DEFINED" in manifest_check["output"]
    assert result["ok"] is True  # no manifest -> nothing to fail


def test_propose_edit_denies_deny_listed_path(workspace: AppWorkspace):
    workspace.start_session("sneaky")
    res = workspace.propose_edit(".github/workflows/ci.yml", "x", "nope")
    assert not res["ok"]
    assert "boundary" in res["error"]


def test_validate_runs_manifest_commands(workspace: AppWorkspace):
    workspace.start_session("add manifest")
    manifest = "build: [[\"true\"]]\ntest: [[\"false\"]]\n"
    workspace.propose_edit("mortimer.app.yaml", manifest, "add checks")
    result = workspace.validate()
    assert result["ok"] is False  # the "false" command fails
    names = {c["name"] for c in result["checks"]}
    assert any(n.startswith("build:") for n in names)
    assert any(n.startswith("test:") for n in names)


def test_submit_refused_without_validation(workspace: AppWorkspace):
    workspace.start_session("skip validation")
    workspace.propose_edit("src/index.js", "console.log(3);\n", "change")
    res = workspace.submit()
    assert not res["ok"]
    assert "validation" in res["error"]


def test_submit_pushes_and_opens_pr(workspace: AppWorkspace):
    workspace.start_session("real change")
    _git(workspace.repo_root, "config", "user.email", "t@e.com")
    _git(workspace.repo_root, "config", "user.name", "T")
    workspace.propose_edit("src/index.js", "console.log(4);\n", "change")
    result = workspace.validate()
    assert result["ok"]  # no manifest -> passes
    workspace._open_pr = lambda title: {"html_url": "https://example.invalid/pr/1"}
    res = workspace.submit()
    assert res["ok"], res
    assert res["pr_url"] == "https://example.invalid/pr/1"
    assert workspace.branch is None
    assert workspace.status()["active"] is False


def test_revert_restores_base_and_cleans_up(workspace: AppWorkspace):
    workspace.start_session("temp")
    workspace.propose_edit("src/index.js", "console.log(5);\n", "temp")
    res = workspace.revert()
    assert res["ok"]
    assert workspace.branch is None
    assert (workspace.repo_root / "src" / "index.js").read_text() == "console.log(1);\n"


def test_pull_on_second_build(workspace: AppWorkspace, app_origin: Path, tmp_path: Path):
    workspace.start_session("first")
    _git(workspace.repo_root, "config", "user.email", "t@e.com")
    _git(workspace.repo_root, "config", "user.name", "T")
    workspace._open_pr = lambda title: {"html_url": "https://example.invalid/pr/1"}
    workspace.propose_edit("src/index.js", "console.log(6);\n", "change")
    result = workspace.validate()
    assert result["ok"]
    workspace.submit()

    # Simulate the PR having been merged on GitHub by pushing straight to
    # the remote's main from another clone.
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(app_origin), str(other))
    _git(other, "checkout", "-B", "main", "origin/main")
    _git(other, "config", "user.email", "t@e.com")
    _git(other, "config", "user.name", "T")
    (other / "README.md").write_text("hi\n")
    _git(other, "add", "-A")
    _git(other, "commit", "-m", "merged elsewhere")
    _git(other, "push", "origin", "main")

    res = workspace.start_session("second build")
    assert res["ok"], res
    assert (workspace.repo_root / "README.md").is_file()
