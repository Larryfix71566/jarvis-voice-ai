"""Unit tests for the admin sidecar's site-research endpoints
(MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1, R6, R8, R9, R10). Same
TestClient + polling pattern as tests/unit/test_admin_plan.py; crawl_site
and the model call are faked so no network is exercised.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
from jarvis.admin.server import app
from jarvis.db import get_conn, run_migrations

FAKE_PROFILE = {"name": "kimi-k2", "model": "kimi-k2-latest", "provider": "moonshot"}


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db_path = tmp_path / "admin_research_test.db"
    monkeypatch.setenv("JARVIS_DB_PATH", str(db_path))
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    return db_path


@pytest.fixture(autouse=True)
def _reset_research_job(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(srv, "load_model_registry", lambda: {
        "default": "kimi-k2", "profiles": {"kimi-k2": FAKE_PROFILE},
    })
    monkeypatch.setattr(srv, "resolve_profile", lambda registry, name: FAKE_PROFILE)

    async def _fake_call_profile(profile, system_prompt, user_content, timeout_s):
        return "# Comparison\n\nSite A beats Site B on X.", None

    monkeypatch.setattr(srv.council_mod, "_call_profile", _fake_call_profile)

    idle = dict(
        state="idle", urls=None, focus=None, sites=None, comparison=None,
        model=None, credits_used=None, error=None, started_at=None,
        finished_at=None, saved_path=None, save_error=None,
    )
    with srv._research_lock:
        srv._research_job.update(idle)
    yield
    with srv._research_lock:
        srv._research_job.update(idle)


def _wait_for_job(c: TestClient, states=("done", "error"), timeout: float = 2.0) -> dict:
    deadline = time.time() + timeout
    job = {}
    while time.time() < deadline:
        job = c.get("/api/research/job").json()["job"]
        if job["state"] in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job never settled: {job}")


def _fake_crawl(ok_a: bool = True, ok_b: bool = True):
    def _crawl(client, url, focus, api_key, config=None):
        if url == "https://a.com":
            if ok_a:
                return {"ok": True, "url": url, "pages": [{"url": url, "title": "A", "content": "x"}],
                        "credits": 4, "page_count": 1}
            return {"ok": False, "url": url, "error": "timeout", "error_kind": "unreachable"}
        if ok_b:
            return {"ok": True, "url": url, "pages": [{"url": url, "title": "B", "content": "y"}],
                    "credits": 5, "page_count": 1}
        return {"ok": False, "url": url, "error": "not found", "error_kind": "invalid"}
    return _crawl


# ------------------------------------------------------------- happy path

def test_happy_path_both_sites_succeed(monkeypatch):
    monkeypatch.setattr(srv.research_crawl, "crawl_site", _fake_crawl())
    c = TestClient(app)
    res = c.post("/api/research/start", json={
        "urls": ["https://a.com", "https://b.com"], "focus": "pricing",
    }).json()
    assert res == {"ok": True, "started": True}
    job = _wait_for_job(c)
    assert job["state"] == "done"
    assert job["comparison"].startswith("# Comparison")
    assert job["credits_used"] == 9  # R8


# ------------------------------------------------------------------- R9

def test_one_site_failure_still_reports_the_other(monkeypatch):
    """R9 — a comparison must not become a silent one-sided report: the
    job still reaches 'done' with the failing site named in `sites`."""
    monkeypatch.setattr(srv.research_crawl, "crawl_site", _fake_crawl(ok_a=True, ok_b=False))
    c = TestClient(app)
    c.post("/api/research/start", json={"urls": ["https://a.com", "https://b.com"]})
    job = _wait_for_job(c)
    assert job["state"] == "done"
    sites_by_url = {s["url"]: s for s in job["sites"]}
    assert sites_by_url["https://a.com"]["ok"] is True
    assert sites_by_url["https://b.com"]["ok"] is False
    assert sites_by_url["https://b.com"]["error"] == "not found"


def test_both_sites_failing_is_a_terminal_error(monkeypatch):
    monkeypatch.setattr(srv.research_crawl, "crawl_site", _fake_crawl(ok_a=False, ok_b=False))
    c = TestClient(app)
    c.post("/api/research/start", json={"urls": ["https://a.com", "https://b.com"]})
    job = _wait_for_job(c)
    assert job["state"] == "error"
    assert "both sites failed" in job["error"]


# ------------------------------------------------------------------- R8

def test_credits_reported_in_payload_and_summary(monkeypatch):
    monkeypatch.setattr(srv.research_crawl, "crawl_site", _fake_crawl())
    c = TestClient(app)
    c.post("/api/research/start", json={"urls": ["https://a.com", "https://b.com"]})
    job = _wait_for_job(c)
    assert job["credits_used"] == 9

    from mcp_servers.mcp_web import logic as web_logic

    class _AdminClient:
        def get(self, path):
            return {"ok": True, "job": job}

    status = web_logic.research_status(_AdminClient())
    assert "9 credits" in status["summary"]


# ------------------------------------------------------------------- R1

def test_second_start_refused_while_running(monkeypatch):
    started = {"n": 0}

    def _slow_crawl(client, url, focus, api_key, config=None):
        started["n"] += 1
        time.sleep(0.2)
        return {"ok": True, "url": url, "pages": [{"url": url, "title": "x", "content": "y"}],
                "credits": 1, "page_count": 1}

    monkeypatch.setattr(srv.research_crawl, "crawl_site", _slow_crawl)
    c = TestClient(app)
    first = c.post("/api/research/start", json={"urls": ["https://a.com", "https://b.com"]}).json()
    assert first["ok"] is True
    second = c.post("/api/research/start", json={"urls": ["https://c.com", "https://d.com"]}).json()
    assert second["ok"] is False
    assert "already in progress" in second["error"]
    _wait_for_job(c)


# ------------------------------------------------------------------- R6

def test_save_goes_through_the_repo_write_gate(monkeypatch):
    monkeypatch.setattr(srv.research_crawl, "crawl_site", _fake_crawl())
    calls = {}

    def _fake_write(path, content, rationale=""):
        calls["path"] = path
        calls["content"] = content
        return {"ok": True, "pending": True, "action_id": 42, "path": path}

    monkeypatch.setattr(srv.repo_logic, "repo_write_file", _fake_write)
    c = TestClient(app)
    c.post("/api/research/start", json={"urls": ["https://a.com", "https://b.com"]})
    _wait_for_job(c)
    res = c.post("/api/research/save", json={}).json()
    assert res["ok"] is True
    assert res["pending"] is True
    assert res["action_id"] == 42
    assert calls["path"].startswith("docs/research/")
    assert "Comparison by" in calls["content"]
    assert "Credits used" in calls["content"]


def test_save_before_done_is_refused(monkeypatch):
    c = TestClient(app)
    res = c.post("/api/research/save", json={}).json()
    assert res["ok"] is False


# ------------------------------------------------------------------ R10

def test_kill_switch_returns_plain_message(monkeypatch):
    monkeypatch.setenv("JARVIS_RESEARCH_ENABLED", "false")
    c = TestClient(app)
    res = c.post("/api/research/start", json={
        "urls": ["https://a.com", "https://b.com"],
    }).json()
    assert res == {"ok": False, "error": srv.RESEARCH_DISABLED_MESSAGE}
    with srv._research_lock:
        assert srv._research_job["state"] == "idle"  # never touched


def test_missing_tavily_key_is_refused_synchronously(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    c = TestClient(app)
    res = c.post("/api/research/start", json={
        "urls": ["https://a.com", "https://b.com"],
    }).json()
    assert res["ok"] is False
    assert "TAVILY_API_KEY" in res["error"]


def test_requires_exactly_two_urls(monkeypatch):
    c = TestClient(app)
    res = c.post("/api/research/start", json={"urls": ["https://a.com"]}).json()
    assert res["ok"] is False
