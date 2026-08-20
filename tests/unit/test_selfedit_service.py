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


def test_validate_runs_pytest_gate_and_passes(service: SelfEditService) -> None:
    """C2 (MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md): validate() must
    run `pytest tests/unit -q` as its own check, alongside allowlist/import/
    build, not just leave backend behavior unverified once those three
    pass."""
    service.start_session("add passing test")
    tests_dir = service.repo_root / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    res = service.validate()
    pytest_check = next(c for c in res["checks"] if c["name"] == "pytest")
    assert pytest_check["ok"], pytest_check


def test_validate_pytest_gate_fails_on_broken_test(service: SelfEditService) -> None:
    service.start_session("add failing test")
    tests_dir = service.repo_root / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_broken.py").write_text("def test_broken():\n    assert False\n")
    res = service.validate()
    pytest_check = next(c for c in res["checks"] if c["name"] == "pytest")
    assert not pytest_check["ok"]
    assert res["ok"] is False


class TestVisualVerification:
    """MORTIMER_DEVELOPER_SECTIONS_AND_VISUAL_VERIFY_PLAN.md Part B.

    `web/src/**` is on the self-edit allowlist — the interface is the
    PRIMARY self-edit target by design. All four validation gates prove the
    code compiles, imports and passes tests; not one can tell whether the
    console still looks right. Every glass change made 2026-08-18 would have
    passed all four while rendering as anything at all.
    """

    def _svc(self, tmp_path, monkeypatch):
        from jarvis.selfedit.service import SelfEditService
        svc = SelfEditService()
        svc.branch = "jarvis/self-edit/test"
        svc.goal = "make the drawer translucent"
        return svc

    def test_is_visual_path(self):
        from jarvis.selfedit.service import is_visual_path
        assert is_visual_path("web/src/App.css")
        assert is_visual_path("web/public/icon.svg")
        assert not is_visual_path("jarvis/prompts.py")
        assert not is_visual_path("tests/unit/test_x.py")

    def test_pr_body_flags_a_visual_change(self, tmp_path, monkeypatch):
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/sidedrawer.css", "rationale": "r",
                          "diff": "", "visual_intent": "the drawer is translucent"}]
        block = "\n".join(svc._visual_change_block())
        assert "Visual change" in block
        assert "the drawer is translucent" in block
        assert "cannot see the screen" in block

    def test_pr_body_still_warns_without_a_stated_intent(self, tmp_path, monkeypatch):
        """The warning is the useful half. Omitting the block because the
        agent failed to author a sentence would hide a visual change exactly
        when the agent was least careful about it."""
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r",
                          "diff": "", "visual_intent": ""}]
        block = "\n".join(svc._visual_change_block())
        assert "Visual change" in block
        assert "No intended appearance was stated" in block

    def test_a_non_visual_change_gets_no_block(self, tmp_path, monkeypatch):
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "jarvis/prompts.py", "rationale": "r", "diff": ""}]
        assert svc._visual_change_block() == []

    def test_verify_refuses_when_the_branch_does_not_match(self, tmp_path, monkeypatch):
        """A pass claimed against the wrong code is the failure this whole
        check exists to prevent."""
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r",
                          "diff": "", "visual_intent": "it is blue"}]
        monkeypatch.setattr(svc, "_git", lambda *a, **k: (0, "main"))
        result = svc.verify_appearance()
        assert result["ok"] is False
        assert "main" in result["error"]
        assert result["branch"] == "main"

    def test_branch_override_proceeds_but_names_the_branch(self, tmp_path, monkeypatch):
        """A merged PR leaves the user on main WITH the changes, so the
        mismatch is refusable rather than fatal — but an overridden pass must
        never be indistinguishable from a matched one."""
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r",
                          "diff": "", "visual_intent": "it is blue"}]
        monkeypatch.setattr(svc, "_git", lambda *a, **k: (0, "main"))
        result = svc.verify_appearance(
            branch_override=True, view=lambda q, display=1: {"answer": "it is blue"})
        assert result["ok"] is True
        assert result["branch"] == "main"
        assert result["branch_matched"] is False

    def test_verify_refuses_when_no_visual_intent_was_recorded(
            self, tmp_path, monkeypatch):
        """Absent is reported, never invented. A vision model given a
        fabricated question produces agreeable prose about nothing."""
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r",
                          "diff": "", "visual_intent": ""}]
        monkeypatch.setattr(
            svc, "_git", lambda *a, **k: (0, "jarvis/self-edit/test"))
        result = svc.verify_appearance()
        assert result["ok"] is False
        assert "no intended appearance was recorded" in result["error"]

    def test_the_question_contains_the_recorded_intent(self, tmp_path, monkeypatch):
        """Not a generic "does this look ok" — that is the difference
        between a check that can be wrong detectably and one that cannot."""
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r", "diff": "",
                          "visual_intent": "the side drawer is translucent"}]
        monkeypatch.setattr(
            svc, "_git", lambda *a, **k: (0, "jarvis/self-edit/test"))
        asked = {}

        def fake_view(question, display=1):
            asked["q"] = question
            return {"answer": "yes, it is translucent"}

        result = svc.verify_appearance(view=fake_view)
        assert "the side drawer is translucent" in asked["q"]
        assert result["ok"] is True
        # The residual assumption is stated EVERY time, not just on override.
        assert "browser reload is not" in result["assumption"]

    def test_low_confidence_is_surfaced_not_swallowed(self, tmp_path, monkeypatch):
        svc = self._svc(tmp_path, monkeypatch)
        svc.proposals = [{"path": "web/src/App.css", "rationale": "r",
                          "diff": "", "visual_intent": "blue"}]
        monkeypatch.setattr(
            svc, "_git", lambda *a, **k: (0, "jarvis/self-edit/test"))
        result = svc.verify_appearance(
            view=lambda q, display=1: {"answer": "wallpaper", "low_confidence": True})
        assert result["low_confidence"] is True

    def test_verify_is_not_in_the_validate_checks_list(self):
        """It is a CHECK, never a gate. A capture during validate() would
        photograph the PRE-change console, so its green tick would mean
        nothing — and a meaningless green tick is worse than no check."""
        import inspect
        from jarvis.selfedit.service import SelfEditService
        source = inspect.getsource(SelfEditService.validate)
        assert "verify_appearance" not in source
        assert "screen" not in source.lower()
