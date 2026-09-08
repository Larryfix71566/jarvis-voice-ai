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

from jarvis.selfedit.service import (
    BASE_REF_ENV,
    CHILD_ENV_KEEP,
    SWIFT_PACKAGES,
    VALIDATE_PYTEST_TIMEOUT_S,
    VALIDATE_SWIFT_BUILD_TIMEOUT_S,
    VALIDATE_SWIFT_TEST_TIMEOUT_S,
    SelfEditService,
    is_swift_only,
    is_swift_path,
    swift_packages_for,
)

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


def _make_repo(tmp_path: Path, allowlist: dict, extra: dict[str, str] | None = None) -> Path:
    """A throwaway clone of a bare origin, with the files the tests edit."""
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
    (work / "config" / "self_edit_allowlist.json").write_text(json.dumps(allowlist))
    for rel, body in (extra or {}).items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return work


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path, ALLOWLIST)


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


def test_validate_sees_a_newly_created_file(service: SelfEditService) -> None:
    """2026-09-07: propose_edit writes without staging and `git diff` lists
    only tracked changes, so a CREATED file reached submit() having been
    checked by propose_edit alone — the allowlist gate, which exists to be
    an independent check, never saw it. validate() now unions untracked,
    non-ignored files into the diff it gates."""
    service.start_session("new file")
    # Written directly in the worktree, bypassing propose_edit's own check
    # exactly as test_validate_catches_off_allowlist_working_tree_changes does.
    (service.work_root / "jarvis" / "sneaky_new.py").write_text("x = 1\n")
    res = service.validate()
    allowlist_check = next(c for c in res["checks"] if c["name"] == "allowlist")
    assert "jarvis/sneaky_new.py" in allowlist_check["output"]
    # jarvis/** is core in this fixture, so it is reported as core, not
    # forbidden — the point is that the gate SEES it.
    assert allowlist_check["ok"] is True


def test_validate_catches_a_newly_created_forbidden_file(
    service: SelfEditService,
) -> None:
    service.start_session("sneaky new")
    (service.work_root / ".github").mkdir(parents=True, exist_ok=True)
    (service.work_root / ".github" / "evil.yml").write_text("on: push\n")
    res = service.validate()
    allowlist_check = next(c for c in res["checks"] if c["name"] == "allowlist")
    assert allowlist_check["ok"] is False
    assert ".github/evil.yml" in allowlist_check["output"]
    assert res["ok"] is False


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


# --- SE5: the Swift gate (MORTIMER_SELFEDIT_AUTHORING_PLAN.md) ----------

SWIFT_ALLOWLIST = {
    "allow": ["web/src/**", "docs/**", "macos/README.md",
              "macos/JarvisKit/**", "macos/MortimerHost/**"],
    "core": ["jarvis/**"],
    "deny": ["jarvis/wakeword.py", "jarvis/selfedit/**", ".github/**", "**/.env*",
             "macos/**/Package.swift"],
}

SWIFT_FILES = {
    "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift": "public let a = 1\n",
    "macos/MortimerHost/Sources/MortimerHost/App.swift": "let b = 1\n",
    "macos/README.md": "# native client\n",
}


@pytest.fixture()
def swift_service(tmp_path: Path) -> SelfEditService:
    """A service whose allowlist permits Swift sources — what step 8's
    human allowlist row (W0-SWIFT) grants in the real repo."""
    return SelfEditService(
        repo_root=_make_repo(tmp_path, SWIFT_ALLOWLIST, SWIFT_FILES),
        github_token=None,
    )


class TestSwiftGate:
    """SE5 — `swift build`/`swift test` run in the session worktree when a
    Swift package changed, and a diff with no Python skips the suite.

    Every test fakes `_run`, so no toolchain is required here; the real
    timings are plan §8 V0b/V0c (10-13 s per package, warm cache)."""

    @staticmethod
    def _fake_run(calls, failing: str | None = None):
        def run(argv, cwd, timeout):
            calls.append({"argv": list(argv), "cwd": str(cwd), "timeout": timeout})
            if failing is not None and " ".join(argv).endswith(failing):
                return 1, "boom"
            return 0, "ok"
        return run

    @staticmethod
    def _swift_calls(calls):
        return [(c["argv"][1], Path(c["cwd"]).name)
                for c in calls if c["argv"][0] == "swift"]

    def test_swift_packages_for_maps_the_dependency_closure(self):
        assert swift_packages_for(
            ["macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift"]
        ) == ["JarvisKit", "MortimerHost"]
        assert swift_packages_for(
            ["macos/MortimerHost/Sources/MortimerHost/App.swift"]
        ) == ["MortimerHost"]
        # both named, in build order, once each
        assert swift_packages_for(
            ["macos/MortimerHost/Sources/MortimerHost/App.swift",
             "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift"]
        ) == ["JarvisKit", "MortimerHost"]

    def test_swift_packages_for_ignores_non_package_macos_paths(self):
        assert swift_packages_for(["macos/README.md"]) == []
        assert swift_packages_for(["macos/GlassSpike/Sources/x.swift"]) == []
        assert swift_packages_for(["jarvis/bot/display.py"]) == []
        assert swift_packages_for([]) == []

    def test_is_swift_path_covers_sources_only(self):
        assert is_swift_path("macos/MortimerHost/Sources/MortimerHost/App.swift")
        assert is_swift_path("macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift")
        # manifests and scripts are a human PR, not a Swift source edit
        assert not is_swift_path("macos/MortimerHost/Package.swift")
        assert not is_swift_path("macos/MortimerHost/scripts/bundle.sh")
        assert not is_swift_path("jarvis/bot/display.py")

    def test_is_swift_only_needs_every_path_under_macos(self):
        assert is_swift_only(["macos/README.md"]) is True
        assert is_swift_only(["macos/MortimerHost/Sources/MortimerHost/App.swift"]) is True
        assert is_swift_only(
            ["macos/MortimerHost/Sources/MortimerHost/App.swift", "docs/x.md"]
        ) is False
        assert is_swift_only([]) is False

    def test_no_swift_gate_without_a_macos_change(self, swift_service, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("docs only")
        swift_service.propose_edit("web/src/App.tsx", "export default 5;\n", "ui")
        res = swift_service.validate()
        assert self._swift_calls(calls) == []
        assert not any(n.startswith("swift_") for n in [c["name"] for c in res["checks"]])

    def test_jarviskit_change_builds_and_tests_both_packages_in_order(
        self, swift_service, monkeypatch
    ):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("jarviskit edit")
        swift_service.propose_edit(
            "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift",
            "public let a = 2\n", "tweak",
        )
        res = swift_service.validate()
        assert self._swift_calls(calls) == [
            ("build", "JarvisKit"), ("test", "JarvisKit"),
            ("build", "MortimerHost"), ("test", "MortimerHost"),
        ]
        names = [c["name"] for c in res["checks"]]
        assert "swift_build:JarvisKit" in names and "swift_test:MortimerHost" in names
        # each gate runs inside the SESSION worktree, never the user's checkout
        for c in calls:
            if c["argv"][0] == "swift":
                assert str(swift_service.work_root) in c["cwd"]
        assert res["ok"] is True, res

    def test_mortimerhost_change_builds_only_mortimerhost(
        self, swift_service, monkeypatch
    ):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("host edit")
        swift_service.propose_edit(
            "macos/MortimerHost/Sources/MortimerHost/App.swift", "let b = 2\n", "tweak",
        )
        swift_service.validate()
        assert self._swift_calls(calls) == [
            ("build", "MortimerHost"), ("test", "MortimerHost"),
        ]

    def test_failed_swift_build_skips_swift_test_for_that_package(
        self, swift_service, monkeypatch
    ):
        calls: list[dict] = []
        monkeypatch.setattr(
            swift_service, "_run", self._fake_run(calls, failing="swift build"),
        )
        swift_service.start_session("jarviskit edit")
        swift_service.propose_edit(
            "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift",
            "public let a = 3\n", "tweak",
        )
        res = swift_service.validate()
        # no `swift test` anywhere: both builds failed
        assert [v for v, _ in self._swift_calls(calls)] == ["build", "build"]
        assert res["ok"] is False
        failed = [c for c in res["checks"] if not c["ok"]]
        assert [c["name"] for c in failed] == [
            "swift_build:JarvisKit", "swift_build:MortimerHost",
        ]

    def test_swift_only_diff_does_not_run_pytest(self, swift_service, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("host edit")
        swift_service.propose_edit(
            "macos/MortimerHost/Sources/MortimerHost/App.swift", "let b = 4\n", "tweak",
        )
        res = swift_service.validate()
        assert not any("pytest" in " ".join(c["argv"]) for c in calls), calls
        check = next(c for c in res["checks"] if c["name"] == "pytest")
        assert check["ok"] is True and check["selected"] is False
        assert "no Python" in check["output"]
        # the import gates still ran — a macos-only diff is not unvalidated
        assert "backend_imports" in [c["name"] for c in res["checks"]]

    def test_a_mixed_diff_runs_pytest(self, swift_service, monkeypatch):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("swift plus docs")
        swift_service.propose_edit(
            "macos/MortimerHost/Sources/MortimerHost/App.swift", "let b = 5\n", "tweak",
        )
        swift_service.propose_edit("docs/notes.md", "note\n", "doc")
        res = swift_service.validate()
        assert any("pytest" in " ".join(c["argv"]) for c in calls)
        assert "selected" not in next(
            c for c in res["checks"] if c["name"] == "pytest"
        )

    def test_a_macos_docs_change_gets_no_swift_gate_and_no_pytest(
        self, swift_service, monkeypatch
    ):
        """macos/README.md is under macos/ but in no package: nothing to
        build, and no Python to test."""
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("macos docs")
        swift_service.propose_edit("macos/README.md", "# updated\n", "doc")
        res = swift_service.validate()
        assert self._swift_calls(calls) == []
        assert not any("pytest" in " ".join(c["argv"]) for c in calls)
        assert res["ok"] is True, res

    def test_every_gate_records_and_logs_its_seconds(
        self, swift_service, monkeypatch, caplog
    ):
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("jarviskit edit")
        swift_service.propose_edit(
            "macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift",
            "public let a = 6\n", "tweak",
        )
        with caplog.at_level("INFO", logger="jarvis.selfedit.service"):
            res = swift_service.validate()
        for check in res["checks"]:
            assert isinstance(check.get("seconds"), float), check
        text = caplog.text
        for name in ("allowlist", "backend_imports", "swift_build:JarvisKit", "pytest"):
            assert f"selfedit_gate name={name}" in text
        assert "seconds=" in text

    def test_the_swift_timeouts_are_hang_guards_not_budgets(self, swift_service, monkeypatch):
        """0.7 — generous until logged seconds say otherwise. V0b/V0c
        measured 10-13 s per package with a warm SwiftPM cache."""
        assert VALIDATE_SWIFT_BUILD_TIMEOUT_S == 1800
        assert VALIDATE_SWIFT_TEST_TIMEOUT_S == 900
        assert list(SWIFT_PACKAGES) == ["JarvisKit", "MortimerHost"]
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("host edit")
        swift_service.propose_edit(
            "macos/MortimerHost/Sources/MortimerHost/App.swift", "let b = 7\n", "t",
        )
        swift_service.validate()
        timeouts = {c["argv"][1]: c["timeout"] for c in calls if c["argv"][0] == "swift"}
        assert timeouts == {"build": 1800, "test": 900}

    def test_last_checks_holds_the_run_and_is_cleared_by_a_new_edit(
        self, swift_service, monkeypatch
    ):
        """SE6 — the PR body reports what ran; a later edit invalidates it
        alongside _validated_ok."""
        calls: list[dict] = []
        monkeypatch.setattr(swift_service, "_run", self._fake_run(calls))
        swift_service.start_session("host edit")
        swift_service.propose_edit(
            "macos/MortimerHost/Sources/MortimerHost/App.swift", "let b = 8\n", "t",
        )
        res = swift_service.validate()
        assert [c["name"] for c in swift_service._last_checks] == [
            c["name"] for c in res["checks"]
        ]
        swift_service.propose_edit("docs/after.md", "later\n", "doc")
        assert swift_service._last_checks == []
        assert swift_service._validated_ok is False


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


# ------------------------------------------------------------------------
# 2026-09-07: the two defects behind "every self-edit hits a blocker".
# Neither is about the planner: the sidecar validated in an environment no
# human runs the suite in, against a base branch no human was running.


class TestValidationEnvironmentIsolation:
    """SelfEditService._run must hand the gates a whitelisted environment.
    The sidecar's own os.environ carries every .env key (run_admin.sh does
    `set -a; . ./.env`) and every vault secret (server.py's inject_env()),
    and two green-in-a-shell tests failed inside validate() on exactly
    those values."""

    def test_gate_subprocesses_do_not_inherit_the_parent_environment(
        self, service: SelfEditService, monkeypatch,
    ) -> None:
        monkeypatch.setenv("JARVIS_ENV_LEAK_SENTINEL", "leaked")
        monkeypatch.setenv("SOME_VAULT_SHAPED_KEY", "secret")
        code, out = service._run(
            [sys.executable, "-c",
             "import os; print(sorted(k for k in os.environ "
             "if k in ('JARVIS_ENV_LEAK_SENTINEL', 'SOME_VAULT_SHAPED_KEY')))"],
            cwd=service.repo_root, timeout=60,
        )
        assert code == 0, out
        assert out.strip() == "[]"

    def test_gate_subprocesses_keep_what_a_shell_needs(
        self, service: SelfEditService,
    ) -> None:
        code, out = service._run(
            [sys.executable, "-c", "import os; print(bool(os.environ.get('PATH')))"],
            cwd=service.repo_root, timeout=60,
        )
        assert code == 0, out
        assert out.strip() == "True"
        assert "PATH" in CHILD_ENV_KEEP and "HOME" in CHILD_ENV_KEEP


class TestConfigurableBaseRef:
    """The base a session is cut from, and the branch its PR targets, are one
    configured value. Before this, every session branched from origin/main
    while the running code lived on an unmerged feature branch: the loop was
    asked to describe files that did not exist in the tree it edited."""

    def test_default_is_origin_main(self, repo: Path, monkeypatch) -> None:
        monkeypatch.delenv(BASE_REF_ENV, raising=False)
        svc = SelfEditService(repo_root=repo, github_token=None)
        assert svc.base_ref == "origin/main"
        assert svc.pr_base == "main"

    def test_env_sets_the_base_and_an_explicit_arg_wins(self, repo: Path, monkeypatch) -> None:
        monkeypatch.setenv(BASE_REF_ENV, "feat/from-env")
        assert SelfEditService(repo_root=repo, github_token=None).base_ref == "feat/from-env"
        explicit = SelfEditService(repo_root=repo, github_token=None, base_ref="origin/other")
        assert explicit.base_ref == "origin/other"
        assert explicit.pr_base == "other"

    def test_pr_base_strips_only_a_leading_origin_prefix(self, repo: Path) -> None:
        assert SelfEditService(repo_root=repo, base_ref="origin/main").pr_base == "main"
        assert SelfEditService(repo_root=repo, base_ref="feat/graph-layer").pr_base == "feat/graph-layer"
        assert SelfEditService(repo_root=repo, base_ref="origin/feat/x").pr_base == "feat/x"

    def test_local_base_ref_cuts_the_session_from_that_branch(self, repo: Path) -> None:
        # A local branch with a commit origin/main does not have.
        _git(repo, "checkout", "-b", "feat/local-only")
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs/NEW_ON_BRANCH.md").write_text("only on the branch\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "branch-only file")
        _git(repo, "checkout", "main")

        svc = SelfEditService(repo_root=repo, github_token=None, base_ref="feat/local-only")
        res = svc.start_session("touch the branch-only doc")
        assert res["ok"], res
        # The worktree sees the branch's file; origin/main never had it.
        assert (svc.work_root / "docs/NEW_ON_BRANCH.md").read_text() == "only on the branch\n"
        # The rollback tag pins the branch tip, not origin/main.
        out = subprocess.run(
            ["git", "rev-parse", f"refs/tags/{res['rollback_tag']}^{{commit}}", "feat/local-only"],
            cwd=repo, capture_output=True, text=True, check=True,
        ).stdout.split()
        assert out[0] == out[1]
        svc.revert()

    def test_open_pr_targets_the_pr_base(self, repo: Path, monkeypatch) -> None:
        captured: dict = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"html_url": "https://example.invalid/pr/1"}).encode()

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _Resp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        svc = SelfEditService(repo_root=repo, github_token="t", github_repo="o/r",
                              base_ref="feat/graph-layer")
        svc.branch = "jarvis/self-edit/20260907-x"
        svc.goal = "x"
        svc.proposals = [{"path": "docs/x.md", "rationale": "r", "diff": ""}]
        pr = svc._open_pr("self-edit: x")
        assert pr["html_url"] == "https://example.invalid/pr/1"
        assert captured["url"] == "https://api.github.com/repos/o/r/pulls"
        assert captured["body"]["base"] == "feat/graph-layer"
        assert captured["body"]["head"] == "jarvis/self-edit/20260907-x"


class TestPreflightTargetPaths:
    """2026-09-07 (review F5): preflight classifies the files the edit will
    CHANGE when the caller names them, and consults the prose only as the
    fallback. The fixture's tiers: docs/** routine, jarvis/** core,
    jarvis/wakeword.py Tier 0."""

    def test_target_paths_override_a_core_path_the_prose_mentions(self, service) -> None:
        res = service.preflight(
            "add a line about jarvis/bot/display.py to docs/README.md",
            has_plan=False, target_paths=["docs/README.md"],
        )
        assert res["ok"] is True, res
        assert res["paths"] == ["docs/README.md"]
        assert res["tiers"]["core"] == []

    def test_without_target_paths_the_same_goal_is_refused_as_core(self, service) -> None:
        res = service.preflight(
            "add a line about jarvis/bot/display.py to docs/README.md", has_plan=False,
        )
        assert res["ok"] is False
        assert "jarvis/bot/display.py" in res["error"]

    def test_target_paths_catch_a_tier0_target_the_prose_hides(self, service) -> None:
        res = service.preflight(
            "make the wake word detector feel snappier", has_plan=False,
            target_paths=["jarvis/wakeword.py"],
        )
        assert res["ok"] is False
        assert "jarvis/wakeword.py" in res["error"]

    def test_blank_target_paths_fall_back_to_the_prose(self, service) -> None:
        res = service.preflight("tidy docs/README.md spacing", has_plan=False,
                                target_paths=["", "  "])
        assert res["ok"] is True and res["paths"] == ["docs/README.md"]
