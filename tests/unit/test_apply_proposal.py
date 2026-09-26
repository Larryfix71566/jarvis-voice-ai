"""W8 (MORTIMER_VOICE_WORKFLOWS_PLAN.md, Larry 2026-09-25: option A) —
scripts/apply_proposal.py end to end: a real git origin, a real Mortimer
proposal branch, and a fake `gh` that answers `pr view` and records
`pr create` / `pr close`. Nothing reaches GitHub."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jarvis.selfedit import proposals

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "apply_proposal.py"
BRANCH = "mortimer/selfedit/20260925-add-b-0123456789ab"
BASE_REQS = "a==1\n"
NEW_REQS = "a==1\nb==2\n"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
state = json.load(open(os.environ["FAKE_GH_STATE"]))
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
if args[:2] == ["pr", "view"]:
    print(json.dumps(state["view"]))
elif args[:2] == ["pr", "create"]:
    if state.get("create_fails"):
        sys.exit("could not create")
    print("https://github.com/o/r/pull/99")
elif args[:2] == ["pr", "close"]:
    if state.get("close_fails"):
        sys.exit("could not close")
else:
    sys.exit("unexpected gh call: %r" % args)
'''


def git(*args, cwd, env=None):
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "Larry", "GIT_AUTHOR_EMAIL": "larry@example.invalid",
                       "GIT_COMMITTER_NAME": "Larry", "GIT_COMMITTER_EMAIL": "larry@example.invalid",
                       "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    (tmp_path / "gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
    origin = tmp_path / "origin.git"
    git("init", "-q", "--bare", str(origin), cwd=tmp_path)
    prod = tmp_path / "prod"
    git("clone", "-q", str(origin), str(prod), cwd=tmp_path)
    (prod / "requirements.txt").write_text(BASE_REQS)
    (prod / "docs").mkdir()
    (prod / "docs" / "README.md").write_text("docs\n")
    git("add", "-A", cwd=prod)
    git("commit", "-q", "-m", "base", cwd=prod)
    git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=prod)
    mortimer = tmp_path / "mortimer"
    git("clone", "-q", str(origin), str(mortimer), cwd=tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(FAKE_GH)
    (bindir / "gh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_STATE", str(tmp_path / "gh-state.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(tmp_path / "gh-log.jsonl"))
    return {"tmp": tmp_path, "origin": origin, "prod": prod, "mortimer": mortimer}


def publish(world, files: dict[str, str], *, branch=BRANCH, number=7, executable=(), **view):
    """Mortimer's side: a branch off main carrying `files`, and the PR view."""
    m = world["mortimer"]
    git("checkout", "-q", "-B", branch, "origin/main", cwd=m)
    for path, text in files.items():
        (m / path).parent.mkdir(parents=True, exist_ok=True)
        (m / path).write_text(text)
        (m / path).chmod(0o755 if path in executable else 0o644)
    git("add", "-A", cwd=m)
    git("commit", "-q", "-m", "self-edit: add b", cwd=m)
    git("push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}", cwd=m)
    head = git("rev-parse", "HEAD", cwd=m)
    state = {"view": {"number": number, "state": "OPEN", "headRefName": branch, "headRefOid": head,
                      "baseRefName": "main", "title": "self-edit: add b",
                      "url": f"https://github.com/o/r/pull/{number}",
                      "files": [{"path": p} for p in files]}}
    state["view"].update(view)
    (world["tmp"] / "gh-state.json").write_text(json.dumps(state))
    # What the service's command would carry had its edit API written these.
    world["digest"] = proposals.set_digest({p: proposals.content_digest(t) for p, t in files.items()
                                            if proposals.is_proposal_path(p)})
    return head


def run_script(world, number=7, digest=None, answer="y\n"):
    """Larry types `answer` at the script's approval prompt."""
    proc = subprocess.run([sys.executable, str(SCRIPT), str(number), digest or world["digest"]], cwd=world["prod"],
                          capture_output=True, text=True, env=os.environ.copy(), input=answer)
    log = world["tmp"] / "gh-log.jsonl"
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return proc, calls


def remote_has(world, ref):
    return bool(git("ls-remote", str(world["origin"]), ref, cwd=world["tmp"]))


SMUGGLED = "--- a/docs/README.md\n+++ b/docs/README.md\n@@ -1 +1 @@\n-docs\n+changed behind the proposal\n"


def proposal_for(target="requirements.txt", before=BASE_REQS, after=NEW_REQS):
    return {proposals.proposal_path(target): proposals.render(target, before, after, "add b")}


def test_an_approved_proposal_lands_on_larrys_branch_and_supersedes_mortimers(world):
    files = {**proposal_for(), "docs/notes.md": "routine part\n"}
    head = publish(world, files)
    prod_head = git("rev-parse", "HEAD", cwd=world["prod"])
    proc, calls = run_script(world)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "APPLIED: https://github.com/o/r/pull/99" in proc.stdout
    shown = proc.stdout[:proc.stdout.index("Type y to approve")]
    assert "+b==2" in shown and "diff --git a/requirements.txt b/requirements.txt" in shown
    assert "Also in the pull request (files Mortimer may write, validated in its sandbox): docs/notes.md" in shown
    o = world["origin"]
    assert git("show", "larry/proposal-7:requirements.txt", cwd=o) + "\n" == NEW_REQS
    assert git("show", "larry/proposal-7:docs/notes.md", cwd=o) == "routine part"
    listed = git("ls-tree", "-r", "--name-only", "larry/proposal-7", cwd=o).splitlines()
    assert not [p for p in listed if p.startswith(proposals.PROPOSAL_DIR)]
    assert git("rev-parse", "larry/proposal-7^", cwd=o) == head
    assert git("log", "-1", "--format=%an", "larry/proposal-7", cwd=o) == "Larry"
    create = next(c for c in calls if c[:2] == ["pr", "create"])
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--head") + 1] == "larry/proposal-7"
    close = next(c for c in calls if c[:2] == ["pr", "close"])
    assert close[2] == "7" and "https://github.com/o/r/pull/99" in close[close.index("--comment") + 1]
    # The checkout it ran from is untouched, and the worktree is gone.
    assert git("rev-parse", "HEAD", cwd=world["prod"]) == prod_head
    assert git("status", "--porcelain", cwd=world["prod"]) == ""
    assert len(git("worktree", "list", cwd=world["prod"]).splitlines()) == 1


def test_a_new_human_only_file_is_created(world):
    target = ".github/workflows/nightly.yml"
    publish(world, {proposals.proposal_path(target): proposals.render(target, None, "on: push\n", "nightly")})
    proc, _ = run_script(world)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert git("show", f"larry/proposal-7:{target}", cwd=world["origin"]) == "on: push"


@pytest.mark.parametrize("case, expect", [
    ("closed", "is closed, not open"),
    ("not_selfedit", "not a Mortimer self-edit branch"),
    ("no_proposal", "carries no human-only proposal"),
    ("moved", "run it again"),
    ("tampered_result", "does not match its Result blob"),
    ("wrong_base", "is not the file"),
    ("second_path", "must change exactly requirements.txt"),
    ("secret_target", "not something a proposal may change"),
    ("credential", "looks like a credential"),
    ("already_applied", "was applied before"),
    # A proposal must change exactly its target: git also applies a
    # traditional (non-git) diff, before or after the checked header.
    ("smuggled_after", "would also change docs/README.md"),
    ("smuggled_in_header", "would also change docs/README.md"),
    ("symlink", "would become mode 120000"),
    ("rename", ""),
    ("routine_target", "is not human-only"),
    ("direct_human_only", "itself changes requirements.txt"),
    # The command names the proposal files the edit API wrote; one that a
    # program added or changed during validation must stop the apply.
    ("extra_proposal", "not the ones Mortimer wrote"),
    ("changed_proposal", "not the ones Mortimer wrote"),
    ("mode_flip", "not the 100644 it may have"),
])
def test_refusals_push_nothing_and_touch_no_pull_request(world, case, expect):
    files = proposal_for()
    patch_path, text = next(iter(files.items()))
    view = {}
    if case == "closed":
        view["state"] = "CLOSED"
    elif case == "not_selfedit":
        view["headRefName"] = "feature/x"
    elif case == "no_proposal":
        files = {"docs/notes.md": "x\n"}
    elif case == "moved":
        view["headRefOid"] = "f" * 40
    elif case == "tampered_result":
        info = proposals.parse(text)
        files = {patch_path: text.replace(info["result"], "0" * 40, 1)}
    elif case == "wrong_base":
        files = {patch_path: proposals.render("requirements.txt", "a==0\n", NEW_REQS, "add b")}
    elif case == "second_path":
        files = {patch_path: text + text[text.index("diff --git"):].replace("requirements.txt", "docs/README.md")}
    elif case == "secret_target":
        files = {proposals.proposal_path(".env"): proposals.render(".env", None, "KEY=1\n", "secret")}
    elif case == "credential":
        token = "ghp_" + "A" * 36
        files = {patch_path: proposals.render("requirements.txt", BASE_REQS, BASE_REQS + token + "\n", "x")}
    elif case == "smuggled_after":
        files = {patch_path: text + SMUGGLED}
    elif case == "smuggled_in_header":
        at = text.index("diff --git")
        files = {patch_path: text[:at] + SMUGGLED + "\n" + text[at:]}
    elif case == "symlink":
        target = ".github/link"
        link = proposals.render(target, None, "../requirements.txt", "link")
        link = link.replace("new file mode 100644", "new file mode 120000").replace(" 100644\n", " 120000\n")
        files = {proposals.proposal_path(target): link}
    elif case == "rename":
        at = text.index("index ")
        files = {patch_path: text[:at] + "similarity index 90%\nrename from docs/README.md\nrename to requirements.txt\n" + text[at:]}
    elif case == "routine_target":
        files = {proposals.proposal_path("docs/README.md"): proposals.render("docs/README.md", "docs\n", "d2\n", "x")}
    elif case == "direct_human_only":
        files = {**files, "requirements.txt": "a==1\nevil==1\n"}
    elif case == "mode_flip":
        files = {patch_path: text.replace(" 100644\n", " 100755\n", 1).replace(
            "diff --git a/requirements.txt b/requirements.txt\n",
            "diff --git a/requirements.txt b/requirements.txt\nold mode 100644\nnew mode 100755\n", 1)}
    elif case in ("extra_proposal", "changed_proposal"):
        approved = proposals.set_digest({patch_path: proposals.content_digest(text)})
        if case == "extra_proposal":
            target = ".github/workflows/x.yml"
            files = {**files, proposals.proposal_path(target): proposals.render(target, None, "on: push\n", "x")}
        else:
            files = {patch_path: proposals.render("requirements.txt", BASE_REQS, "a==1\nother==9\n", "add b")}
    if "headRefName" in view:
        publish(world, files, **{k: v for k, v in view.items() if k != "headRefName"})
        state = json.loads((world["tmp"] / "gh-state.json").read_text())
        state["view"]["headRefName"] = view["headRefName"]
        (world["tmp"] / "gh-state.json").write_text(json.dumps(state))
    else:
        publish(world, files, **view)
    if case == "already_applied":
        git("push", "-q", str(world["origin"]), "origin/main:refs/heads/larry/proposal-7", cwd=world["mortimer"])
    if case in ("extra_proposal", "changed_proposal"):
        world["digest"] = approved
    proc, calls = run_script(world)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "STOPPED:" in proc.stdout and expect in proc.stdout, proc.stdout
    assert "APPLIED" not in proc.stdout
    assert [c[:2] for c in calls] == [["pr", "view"]]
    if case != "already_applied":
        assert not remote_has(world, "refs/heads/larry/proposal-7")
    assert len(git("worktree", "list", cwd=world["prod"]).splitlines()) == 1


def test_a_failed_pull_request_create_says_the_branch_was_pushed_and_closes_nothing(world):
    publish(world, proposal_for())
    state = json.loads((world["tmp"] / "gh-state.json").read_text())
    state["create_fails"] = True
    (world["tmp"] / "gh-state.json").write_text(json.dumps(state))
    proc, calls = run_script(world)
    assert proc.returncode == 1
    assert "pushed larry/proposal-7, but the pull request did not open" in proc.stdout
    assert not [c for c in calls if c[:2] == ["pr", "close"]]


def test_what_the_service_writes_is_what_the_script_applies(world, tmp_path):
    """The whole W8 path: SelfEditService turns a write to a human-only
    file into a proposal; those exact bytes, published on Mortimer's
    branch, are applied by the script."""
    from jarvis.selfedit.service import SelfEditService
    from tests.sandbox_fakes import FakeRuntime
    allow = tmp_path / "allow.json"
    allow.write_text(json.dumps({"allow": ["docs/**"], "core": [], "deny": ["requirements*.txt"]}))
    runtime = FakeRuntime(world["prod"])
    service = SelfEditService(repo_root=world["prod"], allowlist_path=allow, runtime_factory=lambda: runtime)
    service.start_session("pin b")
    wrote = service.propose_edit("requirements.txt", NEW_REQS, "add b")
    assert wrote["ok"] and wrote["proposal"], wrote
    patch_path = wrote["proposal_file"]
    publish(world, {patch_path: runtime.current.files[patch_path]})
    proc, _ = run_script(world, digest=service.proposal_set_digest())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert git("show", "larry/proposal-7:requirements.txt", cwd=world["origin"]) + "\n" == NEW_REQS


def test_a_failed_close_names_the_pull_request_that_did_open(world):
    publish(world, proposal_for())
    state = json.loads((world["tmp"] / "gh-state.json").read_text())
    state["close_fails"] = True
    (world["tmp"] / "gh-state.json").write_text(json.dumps(state))
    proc, _ = run_script(world)
    assert proc.returncode == 1
    assert "opened https://github.com/o/r/pull/99, but #7 did not close" in proc.stdout


def test_no_git_hook_runs_while_the_branch_is_checked_out(world):
    """The worktree holds Mortimer's branch. A hooks directory inside the
    tree (core.hooksPath=hooks) would otherwise run its code as Larry."""
    marker = world["tmp"] / "hook-ran"
    hook = f"#!/bin/sh\ntouch {marker}\n"
    files = {**proposal_for(), "docs/hooks/pre-commit": hook, "docs/hooks/post-checkout": hook}
    publish(world, files, executable={"docs/hooks/pre-commit", "docs/hooks/post-checkout"})
    git("config", "core.hooksPath", "docs/hooks", cwd=world["prod"])
    proc, _ = run_script(world)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not marker.exists(), "a hook from the branch ran"


@pytest.mark.parametrize("answer", ["n\n", "\n", "yes please\n", ""])
def test_nothing_is_pushed_unless_larry_types_y_after_the_diff(world, answer):
    """Larry's decision (2026-09-25): the command shows the exact change and
    waits for y. Anything else, including no input at all, pushes nothing."""
    publish(world, proposal_for())
    proc, calls = run_script(world, answer=answer)
    assert proc.returncode == 1
    assert "+b==2" in proc.stdout and "STOPPED: not approved; nothing was pushed" in proc.stdout
    assert not remote_has(world, "refs/heads/larry/proposal-7")
    assert [c[:2] for c in calls] == [["pr", "view"]]
    assert len(git("worktree", "list", cwd=world["prod"]).splitlines()) == 1


def test_the_diff_cannot_hide_text_from_larry(world):
    """Terminal control codes and direction overrides in the proposed file
    are printed as escapes, so what he reads is what gets pushed."""
    after = BASE_REQS + "b==2 \x1b[1A\x1b[2Khidden \u202eevil\n"
    publish(world, proposal_for(after=after))
    proc, _ = run_script(world, answer="n\n")
    assert "\x1b" not in proc.stdout and "\u202e" not in proc.stdout
    assert "\\x1b[1A\\x1b[2Khidden \\u202eevil" in proc.stdout
