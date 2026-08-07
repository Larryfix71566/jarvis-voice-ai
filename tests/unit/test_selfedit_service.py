"""Unit tests for the self-edit service (plan section 3).

Runs against a throwaway git repo with a bare 'origin' so the real session
lifecycle (branch from origin/main, rollback tag, sandbox-only writes) is
exercised without touching the actual repository or the network.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from jarvis.selfedit.service import SelfEditService

ALLOWLIST = {
    "allow": ["web/src/**", "docs/**"],
    "deny": ["jarvis/**", ".github/**", "**/.env*"],
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    work = tmp_path / "work"
    _git(tmp_path, "clone", str(origin), str(work))
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "checkout", "-b", "main")
    (work / "web/src").mkdir(parents=True)
    (work / "web/src/App.tsx").write_text("export default 1;\n")
    (work / "jarvis").mkdir()
    (work / "jarvis/wakeword.py").write_text("# hands off\n")
    (work / "config").mkdir()
    (work / "config" / "self_edit_allowlist.json").write_text(json.dumps(ALLOWLIST))
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return work


@pytest.fixture()
def service(repo: Path) -> SelfEditService:
    return SelfEditService(repo_root=repo, github_token=None)


def test_start_session_creates_sandbox_branch_and_tag(service: SelfEditService) -> None:
    res = service.start_session("Add a status panel")
    assert res["ok"], res
    assert res["branch"].startswith("jarvis/self-edit/")
    assert res["rollback_tag"].startswith("pre-selfedit-")
    code, out = service._git("branch", "--show-current")
    assert out == res["branch"]


def test_start_session_refuses_dirty_tree(service: SelfEditService) -> None:
    (service.repo_root / "web/src/App.tsx").write_text("dirty\n")
    res = service.start_session("anything")
    assert not res["ok"]
    assert "not clean" in res["error"]


def test_propose_edit_allowlisted(service: SelfEditService) -> None:
    service.start_session("tweak ui")
    res = service.propose_edit("web/src/App.tsx", "export default 2;\n", "bump")
    assert res["ok"], res
    assert "App.tsx" in res["diff"]


def test_propose_edit_forbidden_path(service: SelfEditService) -> None:
    service.start_session("rewrite wakeword")
    res = service.propose_edit("jarvis/wakeword.py", "x = 1\n", "nope")
    assert not res["ok"]
    assert "allowlist" in res["error"]
    assert (service.repo_root / "jarvis/wakeword.py").read_text() == "# hands off\n"


def test_read_file_respects_allowlist(service: SelfEditService) -> None:
    service.start_session("peek")
    assert service.read_file("web/src/App.tsx")["ok"]
    assert not service.read_file("jarvis/wakeword.py")["ok"]


def test_submit_refused_without_validation(service: SelfEditService) -> None:
    service.start_session("skip validation")
    service.propose_edit("web/src/App.tsx", "export default 3;\n", "change")
    res = service.submit()
    assert not res["ok"]
    assert "validation" in res["error"]


def test_validate_catches_off_allowlist_working_tree_changes(
    service: SelfEditService,
) -> None:
    service.start_session("sneaky")
    # Bypass the service and dirty a forbidden file directly.
    (service.repo_root / "jarvis/wakeword.py").write_text("broken\n")
    res = service.validate()
    allowlist_check = next(c for c in res["checks"] if c["name"] == "allowlist")
    assert not allowlist_check["ok"]
    assert "jarvis/wakeword.py" in allowlist_check["output"]


def test_revert_restores_main_and_cleans_up(service: SelfEditService) -> None:
    service.start_session("temporary")
    service.propose_edit("web/src/App.tsx", "export default 9;\n", "temp")
    res = service.revert()
    assert res["ok"]
    _c, branch = service._git("branch", "--show-current")
    assert branch == "main"
    assert (service.repo_root / "web/src/App.tsx").read_text() == "export default 1;\n"
    assert service.status()["active"] is False


def test_second_session_refused_while_active(service: SelfEditService) -> None:
    service.start_session("first")
    res = service.start_session("second")
    assert not res["ok"]
    assert "already active" in res["error"]
