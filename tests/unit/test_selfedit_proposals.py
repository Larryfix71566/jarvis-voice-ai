"""W8 (MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 3, Larry 2026-09-25: option A)
— the proposal file format that jarvis/selfedit/service.py writes and
scripts/apply_proposal.py applies. Round-trips go through real `git apply`."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from jarvis.selfedit import proposals
from jarvis.selfedit.allowlist import DENIED, ROUTINE, Allowlist

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for key, value in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                       "GIT_COMMITTER_EMAIL": "t@e", "GIT_CONFIG_GLOBAL": os.devnull,
                       "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(key, value)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


@pytest.mark.parametrize("before, after, mode", [
    ("one\ntwo\nthree\n", "one\n2\nthree\nfour\n", 0o644),
    ("x\ny", "x\ny\nz\n", 0o644),               # base has no final newline
    ("same\nlast", "same\nLAST", 0o644),        # neither has one
    ("a\n", "a", 0o644),                         # the result loses it
    ("crlf\r\nline\r\n", "crlf\r\nLINE\r\n", 0o644),  # CRLF endings
    ("form\x0cfeed\nx\n", "form\x0cfeed\ny\n", 0o644),  # git does not split on \f; Python does
    ("#!/bin/sh\necho a\n", "#!/bin/sh\necho b\n", 0o755),
    (None, "created\n", 0o644),
])
def test_a_proposal_applies_with_git_and_matches_its_result_blob(repo, before, after, mode):
    target = "dir/file.txt"
    if before is not None:
        (repo / "dir").mkdir()
        (repo / target).write_bytes(before.encode())
        (repo / target).chmod(mode)
        git(repo, "add", "-A")
        assert git(repo, "commit", "-qm", "base").returncode == 0
    text = proposals.render(target, before, after, "why\n it   matters", mode=mode)
    info = proposals.parse(text)
    assert info["target"] == target and info["why"] == "why it matters"
    assert info["base"] == (proposals.NEW_FILE if before is None else proposals.git_blob_sha(before.encode()))
    (repo / "p.patch").write_text(text)
    applied = git(repo, "apply", "--index", "p.patch")
    assert applied.returncode == 0, applied.stderr
    assert (repo / target).read_bytes() == after.encode()
    assert git(repo, "hash-object", target).stdout.strip() == info["result"]
    assert (repo / target).stat().st_mode & 0o777 == mode


def test_a_no_op_is_not_a_proposal():
    with pytest.raises(ValueError):
        proposals.render("a.txt", "x\n", "x\n", "nothing")


@pytest.mark.parametrize("mangle, message", [
    (lambda t: t.replace(proposals.MARKER, "PATCH", 1), "not a human-only proposal"),
    (lambda t: t.replace("Target: a.txt\n", "", 1), "lacks Target"),
    (lambda t: t + t[t.index("diff --git"):].replace("a.txt", "b.txt"), "must change exactly a.txt"),
    (lambda t: t.replace("diff --git a/a.txt b/a.txt", "diff --git a/a.txt b/c.txt", 1), "rename"),
    (lambda t: t.replace("Result: ", "Result: zz", 1), "malformed blob"),
    (lambda t: t.replace(proposals.parse(t)["result"], proposals.parse(t)["base"], 1), "would not change"),
])
def test_parse_refuses_anything_but_one_well_formed_proposal(mangle, message):
    text = proposals.render("a.txt", "x\n", "y\n", "change")
    with pytest.raises(ValueError, match=message):
        proposals.parse(mangle(text))


def test_each_target_has_one_stable_proposal_file():
    first = proposals.proposal_path("jarvis/admin/server.py")
    assert first == proposals.proposal_path("jarvis/admin/server.py")
    assert first.startswith("docs/proposals/jarvis-admin-server-py-") and first.endswith(".patch")
    assert first != proposals.proposal_path("jarvis/admin/server-py")
    assert proposals.is_proposal_path(first) and not proposals.is_proposal_path("docs/plans/x.md")


def test_the_rationale_names_the_target_and_the_file_digest():
    digest = proposals.content_digest("patch text")
    why = proposals.rationale_for("requirements.txt", "pin\n httpx", digest)
    assert why == f"human-only proposal for requirements.txt (sha256 {digest}): pin httpx"
    assert proposals.target_of(why) == "requirements.txt" and proposals.digest_of(why) == digest
    assert proposals.target_of("an ordinary edit") is None and proposals.digest_of("x") is None


def test_the_set_digest_names_every_file_and_its_content():
    one = {"docs/proposals/a.patch": proposals.content_digest("A")}
    two = {**one, "docs/proposals/b.patch": proposals.content_digest("B")}
    assert len(proposals.set_digest(one)) == 12
    assert proposals.set_digest(two) == proposals.set_digest(dict(reversed(list(two.items()))))
    assert proposals.set_digest(one) != proposals.set_digest(two)
    changed = {"docs/proposals/a.patch": proposals.content_digest("A2")}
    assert proposals.set_digest(one) != proposals.set_digest(changed)


def test_the_apply_command_needs_a_well_formed_digest():
    with pytest.raises(ValueError):
        proposals.apply_command("/r", 5, "not-hex")


def test_the_real_allowlist_lets_mortimer_write_proposals_but_not_apply_them():
    allowlist = Allowlist.load(REPO / "config" / "self_edit_allowlist.json")
    assert allowlist.tier(proposals.proposal_path("requirements.txt")) == ROUTINE
    assert allowlist.tier(proposals.APPLY_SCRIPT) == DENIED
    assert allowlist.tier("jarvis/selfedit/proposals.py") == DENIED
    assert allowlist.tier("tests/unit/test_apply_proposal.py") == ROUTINE
