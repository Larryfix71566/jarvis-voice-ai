"""Pipecat runner integration keeps auth and bind restrictions in force."""

from __future__ import annotations

import sys

import pytest
from fastapi.routing import APIRoute, Mount
from fastapi.testclient import TestClient
from starlette.routing import Route

from jarvis.authmw import BearerAuthMiddleware
from jarvis.bot import server
from jarvis.db import run_migrations


def test_build_argv_strips_caller_bind_overrides():
    assert server.build_argv(
        "127.0.0.1", 7860,
        ["--host", "0.0.0.0", "--port=9000", "--transport", "webrtc"],
    ) == ["--host", "127.0.0.1", "--port", "7860", "--transport", "webrtc"]


def test_install_auth_is_idempotent():
    before = sum(mw.cls is BearerAuthMiddleware for mw in server.runner_app.user_middleware)
    server.install_auth()
    server.install_auth()
    after = sum(mw.cls is BearerAuthMiddleware for mw in server.runner_app.user_middleware)
    assert after == max(1, before)


@pytest.mark.asyncio
async def test_creator_dispatch_uses_verified_owner_context():
    from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
    from jarvis.bot.skill_creator_dispatch import (
        dispatch_creator,
        register_session,
        unregister_session,
    )
    from jarvis.tenant import current_user_id

    observed = {}

    async def dispatch(_task, **_kwargs):
        observed["owner"] = current_user_id()
        return "real-run-id"

    token = current_sensitive_turn.set(SensitiveTurn())
    register_session("session-1", "alice", dispatch)
    current_sensitive_turn.reset(token)
    try:
        result = await dispatch_creator(
            "session-1", "alice", task="private brief", system_prompt="fixed",
            tool_specs=[], tool_executor=lambda *_: None,
            on_run_created=lambda _run_id: None,
        )
    finally:
        unregister_session("session-1")
    assert result == "real-run-id"
    assert observed["owner"] == "alice"
    assert current_user_id() == "local"


def test_creator_events_exclude_private_task_and_tool_data():
    safe = server._safe_creator_event({
        "type": "agent_start", "agent": "developer", "run_id": "run-1",
        "task": "private skill brief",
        "arguments": {"content": "draft source"}, "result": "private output",
    })
    assert safe == {
        "type": "agent_start", "agent": "developer", "run_id": "run-1",
        "task": "Authoring a skill in the scoped sandbox.",
    }
    result = server._safe_creator_event({
        "type": "agent_tool_result", "tool": "edit_propose", "ok": True,
        "result": "private diff", "arguments": {"content": "private"},
    })
    assert result == {"type": "agent_tool_result", "tool": "edit_propose", "ok": True}
    assert server._safe_creator_event({"type": "transcript", "text": "private"}) is None


def test_main_uses_gated_host_and_port(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "false")
    monkeypatch.setenv("JARVIS_BOT_PORT", "7999")
    monkeypatch.setattr(sys, "argv", ["bot.py", "--host", "0.0.0.0", "--port", "9000"])
    captured = {}
    monkeypatch.setattr(server, "runner_main", lambda: captured.setdefault("argv", sys.argv[:]))
    server.main()
    assert captured["argv"] == ["bot.py", "--host", "127.0.0.1", "--port", "7999"]


def test_main_local_auth_only_binds_loopback(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.delenv("JARVIS_REMOTE_BIND_ENABLED", raising=False)
    monkeypatch.setenv("JARVIS_BIND_HOST", "0.0.0.0")
    monkeypatch.setattr(sys, "argv", ["bot.py"])
    captured = {}
    monkeypatch.setattr(server, "runner_main", lambda: captured.setdefault("argv", sys.argv[:]))
    server.main()
    assert captured["argv"][1:3] == ["--host", "127.0.0.1"]


def test_main_exits_before_runner_on_bind_refusal(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    monkeypatch.setattr(server, "service_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(
        server, "resolve_bind_host",
        lambda _process: (_ for _ in ()).throw(server.BindRefused("test refusal")),
    )
    monkeypatch.setattr(server, "runner_main", lambda: pytest.fail("runner must not start"))
    with pytest.raises(SystemExit) as exc:
        server.main()
    assert exc.value.code == 2


def test_every_configured_bot_http_route_and_mount_requires_token(tmp_path, monkeypatch):
    import argparse

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "bot-auth.db"))
    monkeypatch.setenv("JARVIS_AUTH_ENABLED", "true")
    run_migrations()
    server.install_auth()
    runner = __import__("pipecat.runner.run", fromlist=["app"])
    args = argparse.Namespace(
        allowed_origins=None, transport=None, dialin=True, whatsapp=False,
        folder=None, direct=False, proxy=None, runner_body=None, esp32=False,
        verbose=0, ws_auth="none", host="127.0.0.1", port=7860,
    )
    runner._configure_server_app(args)

    routes = [route for route in server.runner_app.routes if isinstance(route, (APIRoute, Route))]
    mounts = [route for route in server.runner_app.routes if isinstance(route, Mount)]
    websocket_routes = [route for route in server.runner_app.routes if type(route).__name__ == "APIWebSocketRoute"]
    assert len(server.runner_app.routes) == 18
    assert {"/internal/skills/creator/dispatch", "/internal/skills/creator/cancel"} <= {
        route.path for route in routes
    }
    assert len(websocket_routes) == 4
    assert len(mounts) == 1

    client = TestClient(server.runner_app, raise_server_exceptions=False)
    for route in routes:
        path = route.path
        for name in route.param_convertors:
            path = path.replace("{" + name + "}", "sample")
        method = sorted(route.methods or {"GET"})[0]
        response = client.request(method, path)
        assert response.status_code == 401, (method, route.path, response.text)
    assert client.get("/client/").status_code == 401
