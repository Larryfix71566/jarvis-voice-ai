"""T2.4 — the sidecar's /api/status/* routes: kill switch, error wrapper,
and I1 (no key material in any response)."""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

import jarvis.admin.server as srv
from jarvis import ambient_weather, keyhealth
from jarvis.status import build as B
from jarvis.status import catalog as C
from jarvis.status import location as Loc
from jarvis.status import logs as Lg
from jarvis.status import models as M
from jarvis.status import overview as O
from jarvis.status import services as S

KEY = "sk-ant-api03-FIXTURE-SECRET-VALUE-0123456789"

# route -> (module, attribute the route calls)
ROUTES = {
    "/api/status/models": (M, "model_access_status"),
    "/api/status/services": (S, "service_health"),
    "/api/status/overview": (O, "system_overview"),
    "/api/status/build": (B, "app_build_status"),
    "/api/status/location": (Loc, "current_location"),
    "/api/status/logs?source=bot&query=x&since_minutes=5&limit=3": (Lg, "log_search"),
    "/api/status/catalog?provider=all&force=false": (C, "catalog_status"),
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("JARVIS_STATUS_TOOLS_ENABLED", raising=False)
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "status.db"))
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                 "MOONSHOT_API_KEY", "GITHUB_TOKEN", "TAVILY_API_KEY"):
        monkeypatch.setenv(name, KEY)
    keyhealth.reset_for_tests()
    yield TestClient(srv.app)
    keyhealth.reset_for_tests()
    ambient_weather._clear_cache_for_tests()


@pytest.mark.parametrize("path", list(ROUTES))
def test_disabled_switch(client, monkeypatch, path):
    module, attr = ROUTES[path]

    def must_not_run(*a, **k):
        raise AssertionError("ran while disabled")

    monkeypatch.setattr(module, attr, must_not_run)
    for value in ("false", "0", "no", "off"):
        monkeypatch.setenv("JARVIS_STATUS_TOOLS_ENABLED", value)
        res = client.get(path)
        assert res.status_code == 200
        assert res.json() == {"ok": False, "error": "status tools are disabled"}


@pytest.mark.parametrize("path", list(ROUTES))
def test_error_wrapper(client, monkeypatch, path):
    module, attr = ROUTES[path]

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(module, attr, boom)
    res = client.get(path)
    assert res.status_code == 200
    body = res.json()
    assert body == {"ok": False, "error": "disk on fire"}
    assert "Traceback" not in res.text


def test_logs_route_passes_parameters(client, monkeypatch):
    seen = {}

    def fake(source, query, *, since_minutes, limit):
        seen.update(source=source, query=query, since_minutes=since_minutes, limit=limit)
        return {"ok": True, "lines": []}

    monkeypatch.setattr(Lg, "log_search", fake)
    body = client.get("/api/status/logs?source=admin&query=boot&since_minutes=15&limit=7").json()
    assert body == {"ok": True, "lines": []}
    assert seen == {"source": "admin", "query": "boot", "since_minutes": 15, "limit": 7}


def test_build_route_uses_repo_root(client, monkeypatch):
    seen = []
    monkeypatch.setattr(B, "app_build_status", lambda root: seen.append(root) or {"ok": True})
    assert client.get("/api/status/build").json() == {"ok": True}
    assert seen == [srv.REPO_ROOT]


def _assert_no_key(res):
    assert res.status_code == 200
    assert KEY not in res.text
    assert "FIXTURE-SECRET" not in res.text


def test_models_route_has_no_key_material(client):
    with keyhealth._lock:
        keyhealth._verdicts["ANTHROPIC_API_KEY"] = "ok"
    res = client.get("/api/status/models")
    _assert_no_key(res)
    body = res.json()
    assert body["ok"] is True
    assert body["source"] == "registry"
    assert any(p["key_present"] for p in body["profiles"])


def test_services_route_has_no_key_material(client, monkeypatch):
    monkeypatch.setattr(S, "_http_probe", lambda target: (False, "connection refused"))
    res = client.get("/api/status/services")
    _assert_no_key(res)
    body = res.json()
    assert body["ok"] is True
    assert {r["name"] for r in body["services"]} >= {"bot", "admin", "vault", "costs"}


def test_overview_route_has_no_key_material(client):
    res = client.get("/api/status/overview")
    _assert_no_key(res)
    assert res.json()["ok"] is True


def test_build_route_has_no_key_material(client):
    res = client.get("/api/status/build")
    _assert_no_key(res)
    assert res.json()["ok"] is True


def test_location_route_has_no_key_material(client, monkeypatch):
    ambient_weather._clear_cache_for_tests()
    monkeypatch.delenv("JARVIS_WEATHER_LAT", raising=False)
    monkeypatch.delenv("JARVIS_WEATHER_LON", raising=False)
    monkeypatch.setattr(ambient_weather, "_fetch_json", lambda url: {
        "status": "success", "lat": 34.0, "lon": -84.3, "city": "Alpharetta"})
    res = client.get("/api/status/location")
    _assert_no_key(res)
    assert res.json()["source"] == "ip"


def test_logs_route_has_no_key_material(client, monkeypatch, tmp_path):
    from datetime import datetime

    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "bot.launchd.log").write_text(
        f"2026-09-22 11:59:00 INFO key_health key={KEY} Authorization: Bearer {KEY}\n")
    monkeypatch.setattr(Lg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(Lg, "_now", lambda: datetime(2026, 9, 22, 12, 0, 0))
    res = client.get("/api/status/logs?source=bot")
    _assert_no_key(res)
    assert res.json()["matched"] == 1


def test_status_routes_are_sync_defs():
    import inspect

    for fn in (srv.status_models, srv.status_services, srv.status_overview,
               srv.status_build, srv.status_location, srv.status_logs,
               srv.status_catalog):
        assert not inspect.iscoroutinefunction(fn)


def test_catalog_route_passes_parameters(client, monkeypatch):
    seen = []

    def fake(provider, *, force):
        seen.append((provider, force))
        return {"ok": True, "results": []}

    monkeypatch.setattr(C, "catalog_status", fake)
    assert client.get("/api/status/catalog").json() == {"ok": True, "results": []}
    client.get("/api/status/catalog?provider=openrouter&force=true")
    assert seen == [("all", False), ("openrouter", True)]


def test_catalog_route_has_no_key_material(client, monkeypatch):
    """Real catalog_status with a fake transport that echoes the key back."""
    C.clear_cache_for_tests()

    def echo(url, headers, timeout):
        raise OSError(f"refused: {headers}")

    monkeypatch.setattr(C, "_default_http", echo)
    from jarvis import saygm

    monkeypatch.setenv("SAYGM_API_KEY", KEY)
    monkeypatch.setattr(saygm, "fetch_catalog", lambda **kw: (_ for _ in ()).throw(
        saygm.SayGMError(f"refused with {kw.get('api_key')}")))
    res = client.get("/api/status/catalog?force=true")
    _assert_no_key(res)
    body = res.json()
    assert body["ok"] is True
    assert {r["provider"] for r in body["results"]} >= {"anthropic", "openrouter", "moonshot"}
    assert all(not r["ok"] for r in body["results"])
    C.clear_cache_for_tests()


def test_subscription_probe_route(client, monkeypatch):
    from jarvis.status import subscriptions as Su

    seen = []

    def fake(which, model, *, force):
        seen.append((which, model, force))
        return {"ok": True, "probe": {"which": which}}

    monkeypatch.setattr(Su, "subscription_status", fake)
    res = client.post("/api/status/subscription/probe", json={"which": "codex"})
    assert res.json() == {"ok": True, "probe": {"which": "codex"}}
    client.post("/api/status/subscription/probe",
                json={"which": "claude", "model": "claude-fable-5-1", "force": True})
    assert seen == [("codex", None, False), ("claude", "claude-fable-5-1", True)]


def test_subscription_probe_route_disabled_and_errors(client, monkeypatch):
    from jarvis.status import subscriptions as Su

    def boom(*a, **k):
        raise RuntimeError("cli exploded")

    monkeypatch.setattr(Su, "subscription_status", boom)
    res = client.post("/api/status/subscription/probe", json={"which": "claude"})
    assert res.json() == {"ok": False, "error": "cli exploded"}
    assert "Traceback" not in res.text
    monkeypatch.setenv("JARVIS_STATUS_TOOLS_ENABLED", "false")
    res = client.post("/api/status/subscription/probe", json={"which": "claude"})
    assert res.json() == {"ok": False, "error": "status tools are disabled"}
    assert not __import__("inspect").iscoroutinefunction(srv.status_subscription_probe)


def test_subscription_probe_route_has_no_key_material(client, monkeypatch):
    import shutil

    from jarvis.status import subscriptions as Su
    from jarvis.subscription import SubscriptionRuntimeError

    Su.clear_cache_for_tests()
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: cmd)

    def runner(model, messages, timeout):
        raise SubscriptionRuntimeError(f"401 bad key {KEY}")

    monkeypatch.setattr(Su, "_default_runner", lambda which: runner)
    res = client.post("/api/status/subscription/probe", json={"which": "claude", "force": True})
    _assert_no_key(res)
    assert res.json()["probe"]["category"] == "authentication"
    Su.clear_cache_for_tests()
