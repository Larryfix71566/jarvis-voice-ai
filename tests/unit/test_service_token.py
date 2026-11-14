"""Internal sidecar clients carry only the explicitly scoped service token."""

from __future__ import annotations

import pytest
import yaml

from jarvis.request_guard import CLIENT_HEADER, _CLIENT_VALUE_RE
from jarvis.skills.registry import build_child_env, REPO_ROOT
from mcp_servers.mcp_selfedit.logic import AdminClient

TOKEN_MANIFESTS = {"mcp-selfedit", "mcp-web", "mcp-apps"}


def _client_value(headers: dict, expected: str) -> None:
    """WS-34 B2: the guard-required client header is present and well formed."""
    assert headers[CLIENT_HEADER] == expected
    assert _CLIENT_VALUE_RE.fullmatch(headers[CLIENT_HEADER])


def test_admin_client_forwards_service_token(monkeypatch):
    import httpx

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setenv("JARVIS_SERVICE_TOKEN", "jvt_test-token")
    monkeypatch.setattr(httpx, "Client", FakeClient)
    AdminClient()
    assert seen["headers"] == {
        CLIENT_HEADER: "mortimer-mcp",
        "Authorization": "Bearer jvt_test-token",
    }
    _client_value(seen["headers"], "mortimer-mcp")


def test_admin_client_omits_header_when_token_unset(monkeypatch):
    import httpx

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    AdminClient()
    # No token: no Authorization, but the client header is still sent.
    assert seen["headers"] == {CLIENT_HEADER: "mortimer-mcp"}
    _client_value(seen["headers"], "mortimer-mcp")


@pytest.mark.parametrize(
    ("module_name", "function_name", "path"),
    [
        ("jarvis.bot.plan_watcher", "_default_fetch_job", "/api/plan/job"),
        ("jarvis.bot.research_watcher", "_default_fetch_job", "/api/research/job"),
        (
            "jarvis.bot.progress_watcher",
            "_default_fetch_selfedit_job",
            "/api/selfedit/run",
        ),
    ],
)
@pytest.mark.asyncio
async def test_watchers_send_bearer_and_check_status(
    module_name, function_name, path, monkeypatch
):
    import importlib
    import httpx

    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            seen["status_checked"] = True

        def json(self):
            return {"ok": True, "job": {"state": "idle"}, "finish": {"state": "idle"}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            seen["url"] = url
            seen["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setenv("JARVIS_SERVICE_TOKEN", "jvt_test-token")
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    module = importlib.import_module(module_name)
    fetch = getattr(module, function_name)
    await fetch("http://admin.test")

    assert seen["url"].endswith(path)
    assert seen["kwargs"]["headers"] == {
        CLIENT_HEADER: "mortimer-bot",
        "Authorization": "Bearer jvt_test-token",
    }
    _client_value(seen["kwargs"]["headers"], "mortimer-bot")
    assert seen["status_checked"] is True


@pytest.mark.parametrize("token", [None, "jvt_status-tool-token"])
def test_system_status_client_sends_service_bearer(monkeypatch, token):
    import httpx

    from jarvis.bot.status_tool import _default_client

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    if token is None:
        monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("JARVIS_SERVICE_TOKEN", token)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    _default_client("http://admin.test", 3.0)

    assert seen["base_url"] == "http://admin.test"
    assert seen["timeout"] == 3.0
    expected = {CLIENT_HEADER: "mortimer-bot"}
    if token:
        expected["Authorization"] = f"Bearer {token}"
    assert seen["headers"] == expected
    _client_value(seen["headers"], "mortimer-bot")


@pytest.mark.parametrize("token", [None, "jvt_reporter-token"])
def test_skill_runtime_reporter_send_carries_client_header(monkeypatch, token):
    import asyncio

    import httpx

    from jarvis.bot.skill_runtime_reporter import _send_inventory

    seen = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            seen["kwargs"] = kwargs
            return FakeResponse()

    if token is None:
        monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("JARVIS_SERVICE_TOKEN", token)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    asyncio.run(_send_inventory({"x": 1}, "http://admin.test"))
    headers = seen["kwargs"]["headers"]
    _client_value(headers, "mortimer-bot")
    assert ("Authorization" in headers) is bool(token)


@pytest.mark.parametrize("which", ["cancel", "dispatch"])
def test_skill_requests_bot_calls_carry_client_header(monkeypatch, which):
    import httpx

    from jarvis import skill_requests

    seen = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "request_id": "r1", "developer_run_id": "run1",
                    "cancelled": True}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setenv("JARVIS_SERVICE_TOKEN", "jvt_sr-token")
    monkeypatch.setattr(httpx, "post", fake_post)
    if which == "dispatch":
        state = {"bot_session_id": "s1", "request_id": "r1"}
        skill_requests._dispatch_developer_creator("u1", state, "brief")
        assert seen["url"].endswith("/internal/skills/creator/dispatch")
    else:
        from jarvis.runlog import store

        monkeypatch.setattr(store, "get_run", lambda _id: {"run": {
            "agent": "developer", "user_id": "u1", "session_id": "s1",
            "status": "running"}})
        skill_requests._cancel_developer_run(
            "u1", {"developer_run_id": "run1", "bot_session_id": "s1",
                   "request_id": "r1"})
        assert seen["url"].endswith("/internal/skills/creator/cancel")
    headers = seen["kwargs"]["headers"]
    _client_value(headers, "mortimer-admin")
    assert headers["Authorization"] == "Bearer jvt_sr-token"


@pytest.mark.parametrize("token", [None, "jvt_health-token"])
def test_service_health_request_carries_client_header(monkeypatch, token):
    import importlib.util
    import urllib.request

    from jarvis.vault import inject_env  # noqa: F401  (module import check)

    spec = importlib.util.spec_from_file_location(
        "service_health_under_test", REPO_ROOT / "scripts" / "service_health.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "inject_env", lambda: None)
    if token is None:
        monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("JARVIS_SERVICE_TOKEN", token)
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def getcode(self):
            return 200

    class FakeOpener:
        def open(self, request, timeout=None):
            captured.append(request)
            return FakeResponse()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: FakeOpener())
    assert mod.status_code("admin") == 200
    headers = {k.lower(): v for k, v in captured[0].header_items()}
    _client_value({CLIENT_HEADER: headers[CLIENT_HEADER.lower()]}, "mortimer-health")
    assert ("authorization" in headers) is bool(token)


def test_service_token_is_scoped_to_three_calling_servers(monkeypatch):
    monkeypatch.setenv("JARVIS_ENV_SCOPING_ENABLED", "true")
    monkeypatch.setenv("JARVIS_SERVICE_TOKEN", "jvt_private-test")
    for manifest_path in (REPO_ROOT / "mcp_servers").glob("*/skill.yaml"):
        manifest = yaml.safe_load(manifest_path.read_text()) or {}
        server_name = manifest["name"]
        has_token = "JARVIS_SERVICE_TOKEN" in (manifest.get("requires_env") or [])
        assert has_token is (server_name in TOKEN_MANIFESTS)
        if server_name not in TOKEN_MANIFESTS:
            env = build_child_env({"name": server_name, "env": {}})
            assert "JARVIS_SERVICE_TOKEN" not in env
