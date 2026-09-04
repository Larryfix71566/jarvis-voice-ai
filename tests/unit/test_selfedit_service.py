"""Unit tests for the self-edit service (plan section 3).

Runs against a throwaway git repo with a bare 'origin' so the real session
lifecycle (branch from origin/main, rollback tag, sandbox-only writes) is
exercised without touching the actual repository or the network.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jarvis.selfedit.service import VALIDATE_PYTEST_TIMEOUT_S, SelfEditService

ALLOWLIST = {
    "allow": ["web/src/**", "docs/**"],
    # Tier B: jarvis/** is editable with ceremony; Tier 0 keeps the loop
    # itself and the wake word (this fixture's stand-in for "human-only").
    "core": ["jarvis/**"],
    "deny": ["jarvis/wakeword.py", "jarvis/selfedit/**", ".github/**", "**/.env*"],
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
    (work / "jarvis/bot").mkdir()
    (work / "jarvis/bot/display.py").write_text("SURFACE = 'window'\n")
    (work / "config").mkdir()
    (work / "config" / "self_edit_allowlist.json").write_text(json.dumps(ALLOWLIST))
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return work


@pytest.fixture()
def service(repo: Path) -> SelfEditService:
    return SelfEditService(repo_root=repo, github_token=None)


def _user_branch(service: SelfEditService) -> str:
    _c, out = service._git("branch", "--show-current", cwd=service.repo_root)
    return out


def test_start_session_creates_sandbox_branch_and_tag(service: SelfEditService) -> None:
    res = service.start_session("Add a status panel")
    assert res["ok"], res
    assert res["branch"].startswith("jarvis/self-edit/")
    assert res["rollback_tag"].startswith("pre-selfedit-")
    # The session branch is checked out in the WORKTREE, never in the
    # user's checkout (Larry 2026-08-30: "every time we do a self edit we
    # break git").
    assert service.work_root is not None and service.work_root.is_dir()
    assert str(service.work_root).startswith(str(service.repo_root / "data" / "selfedit_worktrees"))
    _c, wt_branch = service._git("branch", "--show-current", cwd=service.work_root)
    assert wt_branch == res["branch"]
    assert _user_branch(service) == "main"


def test_start_session_leaves_a_dirty_user_tree_alone(service: SelfEditService) -> None:
    """The old service refused a dirty tree and the developer would then
    'clean it up' for the user (2026-08-30 it deleted a directory). With an
    isolated worktree the user's uncommitted work is simply not involved."""
    (service.repo_root / "web/src/App.tsx").write_text("dirty\n")
    (service.repo_root / "scratch.txt").write_text("untracked\n")
    res = service.start_session("anything")
    assert res["ok"], res
    assert (service.repo_root / "web/src/App.tsx").read_text() == "dirty\n"
    assert (service.repo_root / "scratch.txt").exists()
    # ...and the worktree starts from origin/main, not from the dirty tree.
    assert (service.work_root / "web/src/App.tsx").read_text() == "export default 1;\n"


def test_session_never_moves_the_user_off_their_branch(service: SelfEditService) -> None:
    """The regression that lost the native-client tree: a feature branch
    checked out in the user's tree must survive start, edit, and revert
    untouched — no checkout, no reset."""
    _git(service.repo_root, "checkout", "-b", "feat/my-work")
    (service.repo_root / "web/src/Mine.tsx").write_text("mine\n")
    _git(service.repo_root, "add", "-A")
    _git(service.repo_root, "commit", "-m", "my work")
    res = service.start_session("some goal")
    assert res["ok"], res
    assert _user_branch(service) == "feat/my-work"
    service.propose_edit("web/src/App.tsx", "export default 7;\n", "edit")
    assert _user_branch(service) == "feat/my-work"
    # The edit landed in the worktree only.
    assert (service.repo_root / "web/src/App.tsx").read_text() == "export default 1;\n"
    assert (service.work_root / "web/src/App.tsx").read_text() == "export default 7;\n"
    service.revert()
    assert _user_branch(service) == "feat/my-work"
    assert (service.repo_root / "web/src/Mine.tsx").exists()


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
    # Bypass the service and dirty a forbidden file directly IN THE
    # SESSION WORKTREE (the user's tree is not part of the session).
    (service.work_root / "jarvis/wakeword.py").write_text("broken\n")
    res = service.validate()
    allowlist_check = next(c for c in res["checks"] if c["name"] == "allowlist")
    assert not allowlist_check["ok"]
    assert "jarvis/wakeword.py" in allowlist_check["output"]


def test_revert_removes_worktree_and_branch(service: SelfEditService) -> None:
    service.start_session("temporary")
    worktree = service.work_root
    branch = service.branch
    service.propose_edit("web/src/App.tsx", "export default 9;\n", "temp")
    res = service.revert()
    assert res["ok"]
    assert _user_branch(service) == "main"
    assert (service.repo_root / "web/src/App.tsx").read_text() == "export default 1;\n"
    assert not worktree.exists()
    code, _out = service._git("rev-parse", "--verify", branch, cwd=service.repo_root)
    assert code != 0, "session branch should be deleted"
    _c, worktrees = service._git("worktree", "list", cwd=service.repo_root)
    assert "selfedit_worktrees" not in worktrees
    assert service.status()["active"] is False
    assert service.work_root is None


def test_a_second_session_can_start_after_revert(service: SelfEditService) -> None:
    """Teardown must be complete enough that the same slug can be reused —
    a leftover worktree registration would make every retry of a goal
    fail with 'already exists'."""
    assert service.start_session("same goal")["ok"]
    service.revert()
    res = service.start_session("same goal")
    assert res["ok"], res
    service.revert()


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
    tests_dir = service.work_root / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    res = service.validate()
    pytest_check = next(c for c in res["checks"] if c["name"] == "pytest")
    assert pytest_check["ok"], pytest_check


def test_validate_pytest_gate_fails_on_broken_test(service: SelfEditService) -> None:
    service.start_session("add failing test")
    tests_dir = service.work_root / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_broken.py").write_text("def test_broken():\n    assert False\n")
    res = service.validate()
    pytest_check = next(c for c in res["checks"] if c["name"] == "pytest")
    assert not pytest_check["ok"]
    assert res["ok"] is False


def test_pytest_gate_timeout_is_900() -> None:
    """GC1b (gap-closure plan, 2026-09-04): 2,150+ tests; the self-edit run
    that convened council round e48cfbe1 timed out at the old 300 s ("pytest:
    timed out after 300s"). CI runs the same `pytest tests/unit` command with
    no timeout, so the gate and CI must not disagree about what passing
    means -- the fix is headroom, never a faster subset."""
    assert VALIDATE_PYTEST_TIMEOUT_S == 900


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


class TestCapabilityChangeFlag:
    """Larry 2026-08-21: "when those self change edits are present they
    have to be highlighted so they can't go thru quietly." The same day
    mcp_servers/** and the two wiring configs joined the allowlist, moving
    the privilege-escalation gate to the human merging the PR — which only
    works if the PR (and the spoken submit summary) announce the class."""

    def _svc(self):
        from jarvis.selfedit.service import SelfEditService
        svc = SelfEditService()
        svc.branch = "jarvis/self-edit/test"
        svc.goal = "add a memory review tool to the librarian"
        return svc

    def test_is_capability_path(self):
        from jarvis.selfedit.service import is_capability_path
        assert is_capability_path("config/agents.yaml")
        assert is_capability_path("config/mcp_servers.yaml")
        assert is_capability_path("mcp_servers/mcp_memory/logic.py")
        assert not is_capability_path("web/src/App.css")
        assert not is_capability_path("jarvis/prompts.py")
        assert not is_capability_path("config/voices.yaml")

    def test_pr_body_flags_a_capability_change(self):
        svc = self._svc()
        svc.proposals = [
            {"path": "mcp_servers/mcp_new/logic.py", "rationale": "r", "diff": ""},
            {"path": "config/agents.yaml", "rationale": "r", "diff": ""},
        ]
        block = "\n".join(svc._capability_change_block())
        assert "CAPABILITY CHANGE" in block
        assert "config/agents.yaml" in block
        assert "mcp_servers/mcp_new/logic.py" in block
        assert "line by line" in block

    def test_a_non_capability_change_gets_no_block(self):
        svc = self._svc()
        svc.proposals = [
            {"path": "web/src/App.css", "rationale": "r", "diff": ""},
            {"path": "jarvis/prompts.py", "rationale": "r", "diff": ""},
        ]
        assert svc._capability_change_block() == []

    def test_capability_block_cannot_be_omitted_by_missing_rationale(self):
        """Mirror of the visual block's no-intent rule: the flag depends
        only on WHICH paths changed, never on what the agent wrote about
        them — the agent least careful about a grant is exactly the one
        whose grant must not slip through."""
        svc = self._svc()
        svc.proposals = [{"path": "config/mcp_servers.yaml",
                          "rationale": "", "diff": ""}]
        block = "\n".join(svc._capability_change_block())
        assert "CAPABILITY CHANGE" in block


class TestCoreTier:
    """MORTIMER_SELFEDIT_TIERS_PLAN.md — Tier B: core paths are editable,
    with ceremony (extra import gate, CORE CHANGE flag, plan required at
    preview). Tier 0 stays refused by the same tool that refused it before."""

    def test_core_path_is_editable(self, service: SelfEditService) -> None:
        service.start_session("consolidate display output")
        res = service.propose_edit("jarvis/bot/display.py", "SURFACE = 'drawer'\n", "merge")
        assert res["ok"], res
        assert "display.py" in res["diff"]

    def test_tier0_path_is_still_refused(self, service: SelfEditService) -> None:
        service.start_session("rewrite wakeword")
        res = service.propose_edit("jarvis/wakeword.py", "x = 1\n", "nope")
        assert not res["ok"] and "allowlist" in res["error"]

    def test_validate_runs_the_core_import_gate_only_for_core_changes(
        self, service: SelfEditService, monkeypatch
    ) -> None:
        calls: list[list[str]] = []

        def fake_run(argv, cwd, timeout):
            calls.append(list(argv))
            return 0, "ok"
        monkeypatch.setattr(service, "_run", fake_run)

        service.start_session("routine only")
        service.propose_edit("web/src/App.tsx", "export default 5;\n", "ui")
        res = service.validate()
        assert "core_imports" not in [c["name"] for c in res["checks"]]
        service.revert()

        service.start_session("core edit")
        service.propose_edit("jarvis/bot/display.py", "SURFACE = 'drawer'\n", "merge")
        res = service.validate()
        names = [c["name"] for c in res["checks"]]
        assert "core_imports" in names
        core_check = next(c for c in res["checks"] if c["name"] == "core_imports")
        assert core_check["paths"] == ["jarvis/bot/display.py"]
        # The gate imports the pipeline + agent modules, in the SESSION tree.
        # jarvis/selfedit/service.py 2026-09-02 fix: argv[0] is sys.executable,
        # not a bare "python" resolved off PATH (this venv has no `python`
        # binary in some environments -- only `python3` -- and subprocess.run
        # there does not go through a shell).
        smoke = [c for c in calls if c[:2] == [sys.executable, "-c"] and "jarvis.bot.pipeline" in c[2]]
        assert smoke, calls

    def test_pr_body_and_notice_flag_a_core_change(self, service: SelfEditService) -> None:
        service.start_session("core edit")
        service.propose_edit("jarvis/bot/display.py", "SURFACE = 'drawer'\n", "merge")
        block = "\n".join(service._core_change_block())
        assert "CORE CHANGE" in block
        assert "jarvis/bot/display.py" in block
        assert "hold a real conversation" in block

    def test_a_routine_change_gets_no_core_block(self, service: SelfEditService) -> None:
        service.start_session("ui")
        service.propose_edit("web/src/App.tsx", "export default 5;\n", "ui")
        assert service._core_change_block() == []


class TestPreflight:
    """The preview refuses what the planner would only discover after
    confirm + staging + a run (2026-08-30: three such runs)."""

    def test_tier0_goal_is_refused_naming_the_file(self, service: SelfEditService) -> None:
        res = service.preflight("rewrite jarvis/wakeword.py to use a new model", has_plan=True)
        assert res["ok"] is False
        assert "jarvis/wakeword.py" in res["error"]
        assert "human-only" in res["error"]

    def test_core_goal_without_plan_is_refused(self, service: SelfEditService) -> None:
        res = service.preflight("merge results in jarvis/bot/display.py", has_plan=False)
        assert res["ok"] is False
        assert "plan" in res["error"]
        assert res["tiers"]["core"] == ["jarvis/bot/display.py"]

    def test_core_goal_with_plan_passes(self, service: SelfEditService) -> None:
        res = service.preflight("merge results in jarvis/bot/display.py", has_plan=True)
        assert res["ok"] is True
        assert res["tiers"]["core"] == ["jarvis/bot/display.py"]

    def test_routine_goal_passes_without_plan(self, service: SelfEditService) -> None:
        res = service.preflight("tidy docs/README.md spacing", has_plan=False)  # GC4: web/ frozen
        assert res["ok"] is True and res["tiers"]["core"] == []

    def test_goal_naming_no_files_passes_through(self, service: SelfEditService) -> None:
        # Extraction is best-effort; the planner's own allowlist check still
        # governs every write.
        res = service.preflight("make the drawer feel more like glass", has_plan=False)
        assert res["ok"] is True and res["paths"] == []
