"""End-to-end self-edit: stage → confirm → write → finish → pull request.

MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE9. This is the test that had never
existed. Sixteen self-edit attempts ran in production between 2026-08-20
and 2026-09-07 with no automated rehearsal of the chain, which is how nine
plumbing defects accumulated unseen — every one of them was found by
reading logs and database tables, not by anything red.

What is REAL here: the FastAPI routes, SelfEditService, the git worktree,
the allowlist gate, the backend-import gate, the pytest gate (a real
nested `python -m pytest` over the temp repo's own one-test suite), the
commit, and the push to a bare "origin" on disk.

What is faked: exactly one thing — `urllib.request.urlopen`, so no HTTP
reaches github.com. `_open_pr` itself runs for real, which is the point:
the captured request body is the PR body the loop would actually open,
including the SE6 validation table.

Not covered here: the Swift gate. The temp repo has no macos/ directory,
so `swift_packages_for` returns nothing and no toolchain is required to
run this file. TestSwiftGate in tests/unit/test_selfedit_service.py pins
that half; §8 V3/V4 is where a real `swift build` runs.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
import jarvis.selfedit.service as selfedit_service
from jarvis.admin.server import app
from jarvis.selfedit.service import SelfEditService


ALLOWLIST = {
    "allow": ["docs/**", "tests/**"],
    "core": ["jarvis/**"],
    "deny": ["jarvis/vault.py", ".github/**"],
}


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def _reset_jobs():
    """Both job slots are process state; a leaked one fails the next test."""
    with srv._run_lock:
        srv._run_job.update(
            state="idle", goal=None, profile=None, summary=None,
            started_at=None, finished_at=None, submitted=False, pr_url=None,
        )
    with srv._finish_lock:
        srv._finish_job.update(
            state="idle", checks=None, pr_url=None, notice=None, run_id=None,
            started_at=None, finished_at=None,
        )
    with srv._staging_lock:
        srv._selfedit_stagings.clear()
    yield
    with srv._staging_lock:
        srv._selfedit_stagings.clear()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A throwaway repo that can pass the real gates.

    It needs its own importable `jarvis` package: the backend-import gate
    runs `python -c "import jarvis, jarvis.config, jarvis.cli"` with cwd
    set to the SESSION WORKTREE and a whitelisted env that carries no
    PYTHONPATH, so the real checkout is not on the path and the temp tree
    must satisfy the import itself. It also needs a passing test, because
    pytest exits non-zero when it collects nothing.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)],
                   check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)],
                   check=True, capture_output=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "checkout", "-b", "main")

    (work / "jarvis").mkdir()
    (work / "jarvis" / "__init__.py").write_text("")
    (work / "jarvis" / "config.py").write_text("SETTING = 1\n")
    (work / "jarvis" / "cli.py").write_text("def main():\n    return 0\n")
    (work / "tests" / "unit").mkdir(parents=True)
    (work / "tests" / "unit" / "test_smoke.py").write_text(
        "def test_smoke():\n    assert True\n"
    )
    (work / "docs").mkdir()
    (work / "docs" / "README.md").write_text("# docs\n\nOne line.\n")
    (work / "allow.json").write_text(json.dumps(ALLOWLIST))
    # NOT decoration. validate() unions untracked, non-ignored files into
    # the diff it gates (2026-09-07: propose_edit writes without staging,
    # so a CREATED file was invisible to every gate). The pytest gate then
    # leaves __pycache__ behind IN the worktree, so on a SECOND validate —
    # the repair path — those .pyc files would enter `changed`, match
    # jarvis/** as core, and fire the core-imports gate over a repo that
    # has no jarvis.bot. The real repo ignores __pycache__/ (.gitignore:24);
    # a fixture that does not is simply an unrealistic repo. Measured: with
    # this file the repair validates clean, without it core_imports fails.
    (work / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n")

    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return work


@pytest.fixture()
def service(repo: Path, monkeypatch) -> SelfEditService:
    svc = SelfEditService(
        repo_root=repo,
        allowlist_path=repo / "allow.json",
        github_token="test-token",
        github_repo="larryfix/jarvis-voice-ai-clean",
        # A LOCAL base ref: start_session fetches only for an origin/ base,
        # and this repo's "origin" is a directory, not a network.
        base_ref="main",
    )
    monkeypatch.setattr(srv, "_selfedit_service", svc)
    return svc


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def github(monkeypatch) -> dict:
    """Fake ONLY the HTTP call. _open_pr still builds the real body."""
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["auth"] = req.headers.get("Authorization")
        return _FakeResponse({"html_url": "https://github.com/x/y/pull/42"})

    monkeypatch.setattr(
        selfedit_service.urllib.request, "urlopen", fake_urlopen,
    )
    return captured


def _wait_for_finish(client, state: str, timeout: float = 180.0) -> dict:
    """The pytest gate is a real nested pytest run; give it room."""
    deadline = time.time() + timeout
    finish = None
    while time.time() < deadline:
        finish = client.get("/api/selfedit/run").json()["finish"]
        if finish["state"] in ("done", "failed", "error"):
            break
        time.sleep(0.05)
    assert finish is not None and finish["state"] == state, finish
    return finish


def test_a_voice_self_edit_reaches_a_pull_request(service, github):
    """The whole chain, as a voice turn drives it."""
    c = TestClient(app)

    staged = c.post("/api/selfedit/stage", json={
        "goal": "add a review note to docs/README.md",
        "target_paths": ["docs/README.md"],
        "run_id": "run-e2e",
    }).json()
    assert staged["ok"] is True, staged
    assert staged["core_change"] is False

    opened = c.post("/api/selfedit/run", json={
        "staging_id": staged["staging_id"], "author": True,
    }).json()
    assert opened["ok"] is True, opened
    # No planner was launched: the developer authors this one.
    assert opened["started"] is False
    session = opened["session"]
    assert session["branch"].startswith("jarvis/self-edit/")
    assert session["target_paths"] == ["docs/README.md"]
    assert session["run_id"] == "run-e2e"

    read = c.get("/api/selfedit/file", params={"path": "docs/README.md"}).json()
    assert read["ok"] is True and "One line." in read["content"]

    wrote = c.post("/api/selfedit/write", json={
        "path": "docs/README.md",
        "content": read["content"] + "\nReviewed 2026-09-07.\n",
        "rationale": "record the review date",
    }).json()
    assert wrote["ok"] is True, wrote
    assert "Reviewed 2026-09-07." in wrote["diff"]

    started = c.post("/api/selfedit/finish", json={}).json()
    assert started == {"ok": True, "started": True, "state": "validating"}

    finish = _wait_for_finish(c, "done")
    assert finish["pr_url"] == "https://github.com/x/y/pull/42"
    assert finish["run_id"] == "run-e2e"

    # every real gate ran, and each recorded its wall clock
    names = [ch["name"] for ch in finish["checks"]]
    assert names == ["allowlist", "backend_imports", "pytest"], names
    assert all(ch["ok"] for ch in finish["checks"]), finish["checks"]
    assert all(isinstance(ch.get("seconds"), float) for ch in finish["checks"])
    # core_imports did NOT run: a docs edit is routine
    assert "core_imports" not in names

    # the PR the loop would actually have opened
    assert github["method"] == "POST"
    assert github["url"].endswith("/repos/larryfix/jarvis-voice-ai-clean/pulls")
    assert github["auth"] == "Bearer test-token"
    body = github["body"]
    assert body["head"] == session["branch"]
    assert body["base"] == "main"           # pr_base strips a leading origin/
    assert "docs/README.md" in body["body"]
    assert "record the review date" in body["body"]
    # SE6 — with a feature-branch base, CI runs nothing, so the body is the
    # only record that anything was validated.
    assert "Validation (sidecar gates)" in body["body"]
    assert "| pytest | ✓ |" in body["body"]
    assert "SWIFT CHANGE" not in body["body"]   # no macos/ path changed

    # the branch and the rollback tag really reached "origin"
    heads = _git(service.repo_root, "ls-remote", "--heads", "origin")
    assert session["branch"] in heads
    tags = _git(service.repo_root, "ls-remote", "--tags", "origin")
    assert "pre-selfedit-" in tags

    # the session is closed and the worktree is gone
    assert service.branch is None
    status = c.get("/api/selfedit/run").json()["status"]
    assert status["active"] is False


def test_a_red_gate_opens_no_pull_request_and_keeps_the_session(service, github):
    """The failure path is the one that has actually happened. Validation
    must stop the submit, and must leave the session open so the next turn
    can repair it — the loop's dead end was what sent edits to the
    unvalidated path instead."""
    c = TestClient(app)

    staged = c.post("/api/selfedit/stage", json={
        "goal": "add a test to tests/unit",
        "target_paths": ["tests/unit/test_added.py"],
    }).json()
    opened = c.post("/api/selfedit/run", json={
        "staging_id": staged["staging_id"], "author": True,
    }).json()
    assert opened["ok"] is True, opened

    wrote = c.post("/api/selfedit/write", json={
        "path": "tests/unit/test_added.py",
        "content": "def test_added():\n    assert False\n",
        "rationale": "a test that fails",
    }).json()
    assert wrote["ok"] is True, wrote

    c.post("/api/selfedit/finish", json={})
    finish = _wait_for_finish(c, "failed")

    assert finish["pr_url"] is None
    assert github == {}, "no pull request may be opened on a red gate"
    failed = [ch for ch in finish["checks"] if not ch["ok"]]
    assert [ch["name"] for ch in failed] == ["pytest"]
    assert "test_added" in failed[0]["output"]

    # still open, with the proposal intact, for the repair turn
    assert service.branch is not None
    status = c.get("/api/selfedit/run").json()["status"]
    assert status["active"] is True
    assert [p["path"] for p in status["proposals"]] == ["tests/unit/test_added.py"]
    assert status["validated_ok"] is False

    # and the repair really works: fix the file, finish again, PR opens
    c.post("/api/selfedit/write", json={
        "path": "tests/unit/test_added.py",
        "content": "def test_added():\n    assert True\n",
        "rationale": "fix the assertion",
    })
    c.post("/api/selfedit/finish", json={})
    repaired = _wait_for_finish(c, "done")
    assert repaired["pr_url"] == "https://github.com/x/y/pull/42"
    # The repair's gate list must match the first run's: a second validate
    # runs in a worktree the first one left artefacts in, and anything the
    # gates themselves produced must not read as part of the change.
    assert [ch["name"] for ch in repaired["checks"]] == [
        "allowlist", "backend_imports", "pytest",
    ], repaired["checks"]


def test_the_allowlist_still_refuses_a_denied_path_through_the_write_route(service):
    """SE2 changed WHO writes, not WHAT may be written."""
    c = TestClient(app)
    staged = c.post("/api/selfedit/stage", json={
        "goal": "add a review note to docs/README.md",
        "target_paths": ["docs/README.md"],
    }).json()
    c.post("/api/selfedit/run", json={
        "staging_id": staged["staging_id"], "author": True,
    })
    refused = c.post("/api/selfedit/write", json={
        "path": "jarvis/vault.py", "content": "KEY = 1\n", "rationale": "no",
    }).json()
    assert refused["ok"] is False
    assert "allowlist" in refused["error"]
    assert not (service.tree / "jarvis" / "vault.py").exists()
