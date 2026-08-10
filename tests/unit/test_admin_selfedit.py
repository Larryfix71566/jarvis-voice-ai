"""Unit tests for the admin sidecar's async upgrade-run endpoints."""

from __future__ import annotations

import threading
import time

import pytest
import yaml
from fastapi.testclient import TestClient

import jarvis.admin.server as srv


REGISTRY = {
    "default": "kimi-k2",
    "profiles": [
        {
            "name": "kimi-k2",
            "label": "Kimi K2.7 Code",
            "provider": "moonshot",
            "model": "kimi-k2.7-code",
            "base_url": "https://api.moonshot.ai/v1",
            "api_key_env": "MOONSHOT_API_KEY",
            "temperature": None,
        },
        {
            "name": "claude-opus",
            "label": "Claude Opus 5",
            "provider": "anthropic",
            "model": "claude-opus-5",
            "base_url": "https://api.anthropic.com/v1/",
            "api_key_env": "ANTHROPIC_API_KEY",
            "temperature": 0.2,
        },
    ],
}


@pytest.fixture(autouse=True)
def reset_run_job():
    with srv._run_lock:
        srv._run_job.update(
            state="idle", goal=None, profile=None, summary=None,
            started_at=None, finished_at=None,
        )
    yield


@pytest.fixture
def registry_file(tmp_path, monkeypatch):
    p = tmp_path / "upgrade_models.yaml"
    p.write_text(yaml.safe_dump(REGISTRY))
    monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_UPGRADE_PROFILE", raising=False)
    return p


class FakeAgent:
    """UpgradeAgent stand-in: instant or gated scripted run."""

    crash = False
    gate: threading.Event | None = None

    def __init__(self, service, profile=None):
        self.profile = profile

    def model_label(self):
        return f"{self.profile or 'kimi-k2'} (fake-model)"

    def run(self, goal):
        if FakeAgent.gate is not None:
            FakeAgent.gate.wait(timeout=5)
        if FakeAgent.crash:
            raise RuntimeError("boom")
        return {"ok": True, "summary": f"planned {goal!r}"}


def _install_fake_agent(monkeypatch, crash=False, gate=None):
    FakeAgent.crash = crash
    FakeAgent.gate = gate
    monkeypatch.setattr(srv, "_make_agent", lambda service, profile: FakeAgent(service, profile))


def _wait_for_job(client, state, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get("/api/selfedit/run").json()["job"]
        if job["state"] == state:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job never reached {state}: {job}")


@pytest.fixture
def client(registry_file):
    return TestClient(srv.app)


def test_models_endpoint_lists_profiles(client, monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-x")
    j = client.get("/api/selfedit/models").json()
    assert j["ok"] is True
    by_name = {m["name"]: m for m in j["models"]}
    assert by_name["kimi-k2"]["key_present"] is True
    assert by_name["kimi-k2"]["default"] is True
    assert by_name["claude-opus"]["key_present"] is False


def test_run_is_async_and_completes(client, monkeypatch):
    _install_fake_agent(monkeypatch)
    r = client.post("/api/selfedit/run", json={"goal": "add a clock", "profile": "claude-opus"})
    j = r.json()
    assert j["ok"] and j["started"]
    assert j["profile"] == "claude-opus (fake-model)"
    job = _wait_for_job(client, "done")
    assert job["summary"] == "planned 'add a clock'"
    assert job["profile"] == "claude-opus (fake-model)"


def test_second_run_refused_while_running_and_writes_gated(client, monkeypatch):
    gate = threading.Event()
    _install_fake_agent(monkeypatch, gate=gate)
    j = client.post("/api/selfedit/run", json={"goal": "one"}).json()
    assert j["started"] is True
    try:
        again = client.post("/api/selfedit/run", json={"goal": "two"}).json()
        assert again["ok"] is False and "already in progress" in again["error"]
        for ep in ("validate", "submit", "revert"):
            blocked = client.post(f"/api/selfedit/{ep}").json()
            assert blocked["ok"] is False and "in progress" in blocked["error"]
    finally:
        gate.set()
    _wait_for_job(client, "done")


def test_unknown_profile_rejected_synchronously(client, monkeypatch):
    # Real _make_agent → real UpgradeAgent → resolve_profile raises.
    j = client.post("/api/selfedit/run", json={"goal": "x", "profile": "gpt-99"}).json()
    assert j["ok"] is False
    assert "unknown upgrade model profile" in j["error"]
    assert "kimi-k2" in j["error"]
    assert client.get("/api/selfedit/run").json()["job"]["state"] == "idle"


def test_empty_goal_rejected(client):
    j = client.post("/api/selfedit/run", json={"goal": "   "}).json()
    assert j["ok"] is False and "goal" in j["error"]


def test_agent_crash_settles_job_as_error(client, monkeypatch):
    _install_fake_agent(monkeypatch, crash=True)
    client.post("/api/selfedit/run", json={"goal": "explode"})
    job = _wait_for_job(client, "error")
    assert "boom" in job["summary"]


def test_run_status_endpoint_shape(client, monkeypatch):
    _install_fake_agent(monkeypatch)
    client.post("/api/selfedit/run", json={"goal": "check shape"})
    _wait_for_job(client, "done")
    j = client.get("/api/selfedit/run").json()
    assert j["ok"] is True
    assert set(j["job"]) >= {"state", "goal", "profile", "summary", "started_at", "finished_at"}
    assert "status" in j
