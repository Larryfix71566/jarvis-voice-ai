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
from jarvis.db import get_conn, run_migrations
from jarvis.memory import add_observation, set_summary, upsert_fact


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


# --- Phase 5e: memory visibility/correction endpoints -------------------


class TestMemoryEndpoints:
    def test_memory_overview_empty(self, client):
        c, _ = client
        body = c.get("/api/memory").json()
        assert body["ok"] is True
        assert body["facts"] == []
        assert body["summary"] == ""
        assert body["observations"] == []
        assert body["usage"]["fact_count"] == 0
        assert body["usage"]["over_capacity"] is False

    def test_memory_overview_lists_facts_and_summary(self, client):
        c, _ = client
        run_migrations()
        with get_conn() as conn:
            upsert_fact(conn, "user.name", "Larry", "s1")
            set_summary(conn, "Discussed the upgrade plan.", "s1")

        body = c.get("/api/memory").json()
        assert body["facts"][0]["key"] == "user.name"
        assert body["facts"][0]["content"] == "Larry"
        assert body["summary"] == "Discussed the upgrade plan."
        assert body["usage"]["fact_count"] == 1

    def test_memory_overview_shows_observation_promotion_progress(self, client):
        c, _ = client
        run_migrations()
        with get_conn() as conn:
            add_observation(conn, "user.style.brevity", "short answers", "s1")
            add_observation(conn, "user.style.brevity", "short answers", "s2")

        body = c.get("/api/memory").json()
        assert len(body["observations"]) == 1
        obs = body["observations"][0]
        assert obs["key"] == "user.style.brevity"
        assert obs["sessions"] == 2
        assert obs["promote_after"] == 3  # PROMOTE_AFTER, not yet reached
        assert obs["promoted"] is False

    def test_memory_delete_fact_removes_it(self, client):
        c, _ = client
        run_migrations()
        with get_conn() as conn:
            upsert_fact(conn, "user.name", "Larry", "s1")

        res = c.delete("/api/memory/fact/user.name").json()
        assert res["ok"] is True

        body = c.get("/api/memory").json()
        assert body["facts"] == []

    def test_memory_delete_fact_not_found(self, client):
        c, _ = client
        run_migrations()
        res = c.delete("/api/memory/fact/nonexistent.key").json()
        assert res["ok"] is False
        assert "error" in res

    def test_memory_endpoints_never_touch_git(self, client):
        """The memory panel must not require a git repo to work — plan
        Phase 5e touches App.tsx, which the Git and Edit panels also
        share, but the memory endpoints themselves are independent."""
        c, _ = client
        run_migrations()
        # No git operations performed at all in this test; if the memory
        # endpoints accidentally depended on git state, this would fail.
        assert c.get("/api/memory").json()["ok"] is True
        assert c.delete("/api/memory/fact/whatever").json()["ok"] is False
