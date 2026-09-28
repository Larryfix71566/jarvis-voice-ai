"""Internal sidecar clients carry only the explicitly scoped service token."""

from __future__ import annotations

import pytest
import yaml

from jarvis.skills.registry import build_child_env, REPO_ROOT
from mcp_servers.mcp_selfedit.logic import AdminClient

TOKEN_MANIFESTS = {"mcp-selfedit", "mcp-web", "mcp-apps"}


def test_admin_client_forwards_service_token(monkeypatch):
    import httpx

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setenv("JARVIS_SERVICE_TOKEN", "jvt_test-token")
    monkeypatch.setattr(httpx, "Client", FakeClient)
    AdminClient()
    assert seen["headers"] == {"Authorization": "Bearer jvt_test-token"}


def test_admin_client_omits_header_when_token_unset(monkeypatch):
    import httpx

    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.delenv("JARVIS_SERVICE_TOKEN", raising=False)
    monkeypatch.setattr(httpx, "Client", FakeClient)
    AdminClient()
    assert seen["headers"] == {}


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
    assert seen["kwargs"]["headers"] == {"Authorization": "Bearer jvt_test-token"}
    assert seen["status_checked"] is True


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
