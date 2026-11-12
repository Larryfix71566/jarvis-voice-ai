"""WS-34 B2: Host/Origin allow-list and X-Mortimer-Client header."""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from jarvis import request_guard
from jarvis.authmw import BearerAuthMiddleware
from jarvis.request_guard import RequestGuardMiddleware

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        request_guard.ENABLED_ENV,
        request_guard.ALLOWED_HOSTS_ENV,
        request_guard.ALLOWED_ORIGINS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _run(headers, *, type_="http", method="GET", server=("127.0.0.1", 7861), scheme=None):
    """Drive the middleware with a raw scope. Returns (inner_called, sent)."""
    called = []
    sent = []

    async def inner(scope, receive, send):
        called.append(scope["type"])

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": type_,
        "method": method,
        "path": "/x",
        "scheme": scheme or ("ws" if type_ == "websocket" else "http"),
        "server": server,
        "headers": [(k.lower().encode(), v.encode("latin-1")) for k, v in headers.items()],
    }
    asyncio.run(RequestGuardMiddleware(inner)(scope, None, send))
    return bool(called), sent


def _status(sent):
    for m in sent:
        if m["type"] == "http.response.start":
            return m["status"]
    return None


@pytest.mark.parametrize(
    "host", ["127.0.0.1:7861", "localhost:7861", "LOCALHOST", "[::1]:7861", "127.0.0.5"]
)
def test_loopback_hosts_pass(host):
    assert _run({"host": host})[0]


@pytest.mark.parametrize(
    "host",
    ["evil.example:7861", "localhost.evil.example", "127.0.0.1.nip.io", "localhost.", "", "[::1"],
)
def test_bad_hosts_rejected_without_echo(host):
    called, sent = _run({"host": host})
    assert not called and _status(sent) == 403
    body = b"".join(m.get("body", b"") for m in sent)
    assert b"ok" in body and host.encode() not in body or not host


def test_missing_host_rejected():
    called, sent = _run({})
    assert not called and _status(sent) == 403


def test_listener_address_is_allowed_other_ip_is_not():
    assert _run({"host": "100.64.0.5:7860"}, server=("100.64.0.5", 7860))[0]
    assert not _run({"host": "100.64.0.6:7860"}, server=("100.64.0.5", 7860))[0]
    assert not _run({"host": "100.64.0.6"}, server=None)[0]
    assert _run({"host": "127.0.0.1"}, server=None)[0]


def test_allowed_hosts_env(monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_ALLOWED_HOSTS", " mortimer.tail1.ts.net , Other.Example ,,*")
    with caplog.at_level("WARNING"):
        assert _run({"host": "MORTIMER.tail1.ts.net:7860"})[0]
        assert _run({"host": "other.example"})[0]
        assert not _run({"host": "evil.example"})[0]
    assert "request_guard_ignored_wildcard_host" in caplog.text


@pytest.mark.parametrize(
    "origin,host,ok",
    [
        (None, "127.0.0.1:7861", True),
        ("http://localhost:5173", "127.0.0.1:7861", True),
        ("http://evil.example", "127.0.0.1:7861", False),
        ("null", "127.0.0.1:7861", False),
        ("http://127.0.0.1:7861", "127.0.0.1:7861", True),
        ("http://127.0.0.1:7861", "127.0.0.1", False),
        ("http://127.0.0.1", "127.0.0.1:80", True),
        ("ftp://x", "127.0.0.1:7861", False),
    ],
)
def test_origin_rules(origin, host, ok):
    headers = {"host": host}
    if origin is not None:
        headers["origin"] = origin
    assert _run(headers)[0] is ok


def test_allowed_origins_env(monkeypatch):
    monkeypatch.setenv("JARVIS_ALLOWED_ORIGINS", "http://localhost:3000,*,null")
    assert _run({"host": "127.0.0.1:7861", "origin": "http://localhost:3000"})[0]
    assert "*" not in request_guard.allowed_browser_origins()


def test_fetch_metadata():
    base = {"host": "127.0.0.1:7861"}
    assert not _run({**base, "sec-fetch-site": "cross-site"})[0]
    assert _run({**base, "sec-fetch-site": "none"})[0]
    assert _run({**base, "sec-fetch-site": "same-origin"})[0]
    assert _run({**base, "sec-fetch-site": "cross-site", "origin": "http://localhost:5173"})[0]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_cross_origin_writes_need_header(method):
    h = {"host": "127.0.0.1:7861", "origin": "http://localhost:5173"}
    called, sent = _run(h, method=method)
    assert not called and _status(sent) == 403
    assert _run({**h, "x-mortimer-client": "test"}, method=method)[0]


@pytest.mark.parametrize("value", ["", "a" * 65, "a b"])
def test_bad_header_values_rejected(value):
    h = {"host": "127.0.0.1:7861", "origin": "http://localhost:5173", "x-mortimer-client": value}
    assert not _run(h, method="POST")[0]


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_native_client_shape_needs_no_header(method):
    assert _run({"host": "127.0.0.1:7861"}, method=method)[0]


def test_same_origin_write_exempt_and_safe_methods():
    assert _run(
        {"host": "127.0.0.1:7861", "origin": "http://127.0.0.1:7861"}, method="POST"
    )[0]
    for m in ("GET", "HEAD", "OPTIONS"):
        assert _run({"host": "127.0.0.1:7861", "origin": "http://localhost:5173"}, method=m)[0]


def test_websocket_rules():
    called, sent = _run({"host": "127.0.0.1:7860"}, type_="websocket")
    assert called and not sent
    called, sent = _run(
        {"host": "127.0.0.1:7860", "origin": "http://evil.example"}, type_="websocket"
    )
    assert not called and sent == [{"type": "websocket.close", "code": 4403}]
    called, sent = _run({"host": "evil.example"}, type_="websocket")
    assert not called and sent[0]["code"] == 4403
    assert _run(
        {"host": "127.0.0.1:7860", "origin": "http://127.0.0.1:7860"}, type_="websocket"
    )[0]


@pytest.mark.parametrize("port", ["\u00b2", "1" * 5000, "0", "65536", "99999", "123456"])
def test_bad_ports_refused_not_raised(port):
    """Codex R3 on #342: a crafted port is a refusal (403 / 4403), never an exception."""
    for type_ in ("http", "websocket"):
        expected = 403 if type_ == "http" else 4403
        called, sent = _run(
            {"host": "127.0.0.1:7861", "origin": f"http://localhost:{port}"}, type_=type_
        )
        assert not called
        assert (_status(sent) if type_ == "http" else sent[0]["code"]) == expected
        called, sent = _run({"host": f"127.0.0.1:{port}"}, type_=type_)
        assert not called
        assert (_status(sent) if type_ == "http" else sent[0]["code"]) == expected
        called, sent = _run({"host": f"[::1]:{port}"}, type_=type_)
        assert not called


def test_edge_ports_still_accepted():
    assert _run({"host": "127.0.0.1:1"})[0]
    assert _run({"host": "127.0.0.1:65535"})[0]


def test_lifespan_passes():
    called = []

    async def inner(scope, receive, send):
        called.append(1)

    asyncio.run(RequestGuardMiddleware(inner)({"type": "lifespan"}, None, None))
    assert called


@pytest.mark.parametrize("value", ["false", "FALSE ", "0", "no"])
def test_kill_switch_off(monkeypatch, value):
    monkeypatch.setenv("JARVIS_REQUEST_GUARD_ENABLED", value)
    assert _run({"host": "evil.example"})[0]


@pytest.mark.parametrize("value", [None, "true", "garbage"])
def test_kill_switch_on(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("JARVIS_REQUEST_GUARD_ENABLED", value)
    assert not _run({"host": "evil.example"})[0]


def test_env_names_read_in_exactly_one_module():
    for name in (
        "JARVIS_REQUEST_GUARD_ENABLED",
        "JARVIS_ALLOWED_HOSTS",
        "JARVIS_ALLOWED_ORIGINS",
    ):
        hits = set()
        for top in ("jarvis", "scripts", "mcp_servers"):
            for p in (REPO / top).rglob("*.py"):
                if name in p.read_text(encoding="utf-8", errors="ignore"):
                    hits.add(p.relative_to(REPO).as_posix())
        assert hits == {"jarvis/request_guard.py"}, (name, hits)


# ---------------------------------------------------------------- admin app


def _admin():
    from jarvis.admin import server

    return server.app


def test_admin_every_route_rejects_bad_host_and_origin():
    app = _admin()
    client = TestClient(app, raise_server_exceptions=False)
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = re.sub(r"\{[^}]+\}", "x", route.path)
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            r = client.request(method, path, headers={"Host": "evil.example"})
            assert r.status_code == 403, (method, route.path)
            if method in ("POST", "DELETE", "PUT", "PATCH"):
                r = client.request(method, path, headers={"Origin": "http://evil.example"})
                assert r.status_code == 403, (method, route.path)
                r = client.request(method, path, headers={"Origin": "http://localhost:5173"})
                assert r.status_code == 403, (method, route.path)


def test_admin_cors_preflight_allows_client_header():
    r = TestClient(_admin()).options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-mortimer-client,content-type",
        },
    )
    assert r.status_code == 200
    assert "x-mortimer-client" in r.headers["access-control-allow-headers"].lower()


def test_admin_middleware_order():
    # The 5xx logger (@app.middleware("http")) is registered later and is outermost.
    classes = [m.cls for m in _admin().user_middleware]
    classes = [c for c in classes if c in (CORSMiddleware, RequestGuardMiddleware, BearerAuthMiddleware)]
    assert classes == [CORSMiddleware, RequestGuardMiddleware, BearerAuthMiddleware]


def test_guard_runs_before_auth(monkeypatch, tmp_path):
    from jarvis import authmw
    from jarvis.db import run_migrations

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    monkeypatch.setattr(authmw, "verify_bearer", lambda *_: pytest.fail("auth reached"))
    r = TestClient(_admin()).get("/api/health", headers={"Host": "evil.example"})
    assert r.status_code == 403


# ------------------------------------------------------------------ bot app


def test_bot_guard_installed_once_before_auth(monkeypatch):
    from fastapi import FastAPI

    from jarvis.bot import server

    monkeypatch.setattr(server, "runner_app", FastAPI())
    server.install_auth()
    server.install_auth()
    mw = [m.cls for m in server.runner_app.user_middleware]
    assert mw.count(RequestGuardMiddleware) == 1
    assert mw.index(RequestGuardMiddleware) < mw.index(BearerAuthMiddleware)


def test_bot_routes_reject_bad_host_and_origin(monkeypatch):
    # Fresh apps so the shared module-level Pipecat app is never started here
    # (a started app refuses add_middleware in later tests).
    from fastapi import FastAPI

    from jarvis.bot import server

    runner = __import__("pipecat.runner.run", fromlist=["app"])
    fresh = FastAPI()
    monkeypatch.setattr(server, "runner_app", fresh)
    monkeypatch.setattr(runner, "app", fresh)
    server.install_auth()
    args = argparse.Namespace(
        allowed_origins=None, transport=None, dialin=True, whatsapp=False,
        folder=None, direct=False, proxy=None, runner_body=None, esp32=False,
        verbose=0, ws_auth="none", host="127.0.0.1", port=7860,
    )
    runner._configure_server_app(args)
    client = TestClient(server.runner_app, raise_server_exceptions=False)
    assert client.get("/status", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/client/", headers={"Host": "evil.example"}).status_code == 403
    assert (
        client.post(
            "/api/offer", json={}, headers={"Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/offer", json={}).status_code != 403


# ----------------------------------------------------------------- costs app


def test_costs_guard():
    from jarvis import costs_api

    client = TestClient(costs_api.app, raise_server_exceptions=False)
    assert client.get("/costs/summary", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/costs/summary").status_code != 403
