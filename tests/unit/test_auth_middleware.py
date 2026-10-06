"""Whole-app bearer-auth coverage for the admin sidecar."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from jarvis import auth
from jarvis.admin.server import app
from jarvis.auth import VerifyUnavailable
from jarvis.authmw import BearerAuthMiddleware
from jarvis.db import get_conn, now_iso, run_migrations

# Includes Skills endpoints and main's workflow/status routes.
EXPECTED_SIDECAR_ROUTES = 82
WORKSPACE_SOURCE_PATHS = {'/api/development/source/associate', '/api/development/source/prepare',
                          '/api/development/source/tool'}
MAIN_STATUS_PATHS = {
    "/api/workflows", "/api/status/models", "/api/status/services",
    "/api/status/overview", "/api/status/build", "/api/status/location",
    "/api/status/logs", "/api/status/catalog",
    "/api/status/subscription/probe", "/api/status/github",
}


def _path_for(route: APIRoute) -> str:
    path = route.path
    for name in route.param_convertors:
        path = path.replace("{" + name + "}", "sample")
    return path


def test_every_sidecar_route_requires_bearer_token(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    routes = [route for route in app.routes if isinstance(route, APIRoute)]
    assert len(routes) == EXPECTED_SIDECAR_ROUTES
    assert MAIN_STATUS_PATHS <= {route.path for route in routes}
    assert WORKSPACE_SOURCE_PATHS <= {route.path for route in routes}
    assert all(route.methods == {'POST'} for route in routes if route.path in WORKSPACE_SOURCE_PATHS)

    client = TestClient(app, raise_server_exceptions=False)
    for route in routes:
        method = min(route.methods or {"GET"})
        response = client.request(method, _path_for(route))
        assert response.status_code == 401, (method, route.path, response.text)
        assert response.headers["www-authenticate"] == 'Bearer realm="jarvis"'
        assert response.json()["ok"] is False


def test_cors_wraps_auth_for_preflight_and_unauthorized_response(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "cors.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    client = TestClient(app)
    origin = "http://localhost:5173"

    unauthorized = client.get("/api/health", headers={"Origin": origin})
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == origin

    preflight = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "DELETE" in preflight.headers["access-control-allow-methods"]
    assert "Authorization" in preflight.headers["access-control-allow-headers"]


def test_valid_bearer_reaches_admin_route(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "valid.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    token = auth.mint_token()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO client_tokens (user_id, name, token_hash, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("larry", "test-client", auth.hash_token(token), now_iso()),
        )
        conn.commit()

    response = TestClient(app).get(
        "/api/health", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_bare_options_is_not_treated_as_preflight(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "options.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    response = TestClient(app).options("/api/health")
    assert response.status_code == 401


def test_auth_kill_switch_allows_loopback_request(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "false")
    assert TestClient(app).get("/api/health").status_code == 200


def test_database_lock_maps_to_retryable_503(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "busy.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    monkeypatch.setattr("jarvis.authmw.verify_bearer", lambda _header: (_ for _ in ()).throw(VerifyUnavailable()))
    response = TestClient(app).get(
        "/api/health", headers={"Authorization": "Bearer jvt_" + "a" * 43}
    )
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"


@pytest.mark.asyncio
async def test_websocket_scope_is_rejected_without_entering_app(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    called = False
    messages = []

    async def inner(*_args):
        nonlocal called
        called = True

    async def send(message):
        messages.append(message)

    middleware = BearerAuthMiddleware(inner)
    await middleware({"type": "websocket", "path": "/ws", "headers": []}, None, send)
    assert messages == [{"type": "websocket.close", "code": 4401}]
    assert called is False


@pytest.mark.asyncio
async def test_authenticated_identity_scopes_runtime_and_runlog_owner(monkeypatch, tmp_path):
    from jarvis import tenant
    from jarvis.db import get_conn, run_migrations
    from jarvis.runlog.store import RunLogger

    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("JARVIS_USER_ID", "process-owner")
    db_path = tmp_path / "identity.db"
    conn = get_conn(db_path)
    run_migrations(conn)
    conn.close()
    monkeypatch.setattr(
        "jarvis.authmw.verify_bearer",
        lambda _header: SimpleNamespace(user_id="request-owner", name="test"),
    )
    observed = {}

    async def child():
        return tenant.current_user_id()

    async def inner(_scope, _receive, _send):
        observed["owner"] = tenant.current_user_id()
        observed["child_owner"] = await asyncio.create_task(child())
        runlog = RunLogger(
            "developer-run-1", "developer", "Developer", "safe test task",
            db_path=db_path, root=tmp_path / "logs",
        )
        runlog.start()
        runlog.finish("done")

    async def send(_message):
        pass

    middleware = BearerAuthMiddleware(inner)
    await middleware(
        {"type": "websocket", "path": "/ws", "headers": [
            (b"authorization", b"Bearer test-token"),
        ]},
        None,
        send,
    )

    assert observed == {"owner": "request-owner", "child_owner": "request-owner"}
    assert tenant.current_user_id() == "process-owner"
    conn = get_conn(db_path)
    try:
        row = conn.execute(
            "SELECT agent, user_id FROM agent_runs WHERE run_id=?",
            ("developer-run-1",),
        ).fetchone()
    finally:
        conn.close()
    assert tuple(row) == ("developer", "request-owner")


def test_admin_main_exits_before_uvicorn_on_bind_refusal(tmp_path, monkeypatch):
    import logging

    import uvicorn

    import jarvis.admin.server as admin_server

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "main.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("JARVIS_REMOTE_BIND_ENABLED", "true")
    monkeypatch.setenv("JARVIS_BIND_HOST", "100.64.1.2")
    run_migrations()
    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **_kwargs: pytest.fail("must not bind"))
    with pytest.raises(SystemExit) as exc:
        admin_server.main()
    assert exc.value.code == 2


def test_admin_main_local_auth_only_binds_loopback(tmp_path, monkeypatch):
    import uvicorn

    import jarvis.admin.server as admin_server

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "local-auth.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.delenv("JARVIS_REMOTE_BIND_ENABLED", raising=False)
    monkeypatch.setenv("JARVIS_BIND_HOST", "0.0.0.0")
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda _app, **kwargs: captured.update(kwargs))
    admin_server.main()
    assert captured["host"] == "127.0.0.1"
