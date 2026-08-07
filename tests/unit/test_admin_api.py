"""Tests for the admin sidecar API (upgrade plan U1.5-G3).

Verifies the panel endpoints are thin pass-throughs over mcp_git.logic —
the same draft/commit machinery the voice path uses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.admin.server import app


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-b", "main")
    git(r, "config", "user.email", "t@t")
    git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("one\n")
    git(r, "add", "-A")
    git(r, "commit", "-m", "init")
    monkeypatch.setenv("JARVIS_REPO_ROOT", str(r))
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "test.db"))
    return client_for(r), r


def client_for(repo: Path) -> TestClient:
    return TestClient(app)


def test_health(client):
    c, _ = client
    assert c.get("/api/health").json() == {"ok": True}


def test_status_endpoint(client):
    c, _ = client
    body = c.get("/api/git/status").json()
    assert body["branch"] == "main"
    assert body["clean"] is True


def test_log_endpoint(client):
    c, _ = client
    body = c.get("/api/git/log").json()
    assert any("init" in line for line in body["commits"])


def test_commit_via_api_uses_draft_flow(client):
    c, r = client
    (r / "a.txt").write_text("two\n")

    draft = c.post("/api/git/prepare-commit", json={"message": "via api"}).json()
    assert draft["ok"] is True

    # commit without the draft's id is meaningless; with it, it executes
    assert c.post("/api/git/commit", json={"action_id": 9999}).json()["ok"] is False
    res = c.post("/api/git/commit", json={"action_id": draft["action_id"]}).json()
    assert res["ok"] is True
    assert c.get("/api/git/status").json()["clean"] is True


def test_actions_endpoint_lists_audit(client):
    c, r = client
    (r / "a.txt").write_text("two\n")
    draft = c.post("/api/git/prepare-commit", json={"message": "audited"}).json()
    c.post("/api/git/commit", json={"action_id": draft["action_id"]})
    rows = c.get("/api/git/actions").json()["actions"]
    assert rows and rows[0]["tool"] == "git_commit"
    assert rows[0]["status"] == "committed"


def test_docs_disabled():
    c = TestClient(app)
    assert c.get("/docs").status_code == 404
    assert c.get("/openapi.json").status_code == 404
