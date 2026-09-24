"""T2.5 — the system_status direct tool (fake HTTP client)."""

from __future__ import annotations

import httpx
import pytest

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.bot.status_tool import (
    PROTECTED_TURN_REFUSAL,
    SIDECAR_DOWN,
    SYSTEM_STATUS_SCHEMA,
    TOPIC_PATHS,
    build_system_status_tool,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, calls, payload, status_code=200, error=None):
        self.calls, self.payload, self.status_code, self.error = calls, payload, status_code, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, path, params=None):
        self.calls.append(path)
        if self.error is not None:
            raise self.error
        return FakeResponse(self.payload, self.status_code)


def _tool(payload=None, status_code=200, error=None):
    calls, factories = [], []

    def factory(base_url, timeout):
        factories.append((base_url, timeout))
        return FakeClient(calls, payload if payload is not None else {"ok": True},
                          status_code, error)

    _, handler = build_system_status_tool("http://sidecar:1", client_factory=factory)
    return handler, calls, factories


@pytest.fixture(autouse=True)
def _unarmed_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    yield
    current_sensitive_turn.reset(token)


def test_schema_enum_includes_p4_topics():
    enum = SYSTEM_STATUS_SCHEMA["function"]["parameters"]["properties"]["topic"]["enum"]
    assert enum == ["models", "catalog", "subscription", "services", "overview",
                    "build", "location"]
    assert SYSTEM_STATUS_SCHEMA["function"]["parameters"]["required"] == ["topic"]


@pytest.mark.parametrize("topic", ["models", "services", "overview", "build", "location"])
async def test_each_topic_calls_the_right_path(topic):
    handler, calls, factories = _tool({"ok": True, "services": [], "agents": [],
                                       "profiles": [], "providers": []})
    out = await handler({"topic": topic})
    assert calls == [f"/api/status/{topic}"]
    assert TOPIC_PATHS[topic] == f"/api/status/{topic}"
    assert factories == [("http://sidecar:1", 10.0)]
    assert out.startswith("Source:")


async def test_admin_url_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("JARVIS_ADMIN_URL", "http://from-env:9")
    seen = []

    def factory(base_url, timeout):
        seen.append(base_url)
        return FakeClient([], {"ok": True})

    _, handler = build_system_status_tool(client_factory=factory)
    await handler({"topic": "build"})
    assert seen == ["http://from-env:9"]


@pytest.mark.parametrize("topic", ["catalog", "subscription"])
async def test_sensitive_turn_refusal(topic):
    handler, calls, _ = _tool()
    holder = current_sensitive_turn.get()
    holder.armed = True
    out = await handler({"topic": topic, "which": "claude"})
    assert out == PROTECTED_TURN_REFUSAL
    assert out == "system_status failed: protected turn cannot call external tool server."
    assert calls == []


@pytest.mark.parametrize("topic", ["catalog", "subscription"])
async def test_p4_topics_not_available_yet(topic):
    handler, calls, _ = _tool()
    out = await handler({"topic": topic})
    assert out == "system_status failed: not available until the catalog phase ships."
    assert calls == []


async def test_local_topics_still_answer_on_a_protected_turn():
    handler, calls, _ = _tool({"ok": True, "label": "Alpharetta", "source": "device"})
    current_sensitive_turn.get().armed = True
    out = await handler({"topic": "location"})
    assert "Alpharetta" in out
    assert calls == ["/api/status/location"]


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"),
                                   OSError("down")])
async def test_sidecar_down_returns_the_sentence(error):
    handler, _, _ = _tool(error=error)
    out = await handler({"topic": "services"})
    assert out == SIDECAR_DOWN == "system_status failed: the admin sidecar is not reachable."


async def test_real_transport_down_never_raises():
    _, handler = build_system_status_tool("http://127.0.0.1:9")
    assert await handler({"topic": "models"}) == SIDECAR_DOWN


async def test_disabled_sidecar_is_relayed():
    handler, _, _ = _tool({"ok": False, "error": "status tools are disabled"})
    assert await handler({"topic": "models"}) == "system_status failed: status tools are disabled."


async def test_http_error_status():
    handler, _, _ = _tool({"detail": "Not Found"}, status_code=404)
    assert await handler({"topic": "build"}) == (
        "system_status failed: the admin sidecar answered HTTP 404.")


async def test_unknown_topic():
    handler, calls, _ = _tool()
    assert await handler({"topic": "weather"}) == "system_status failed: unknown topic 'weather'."
    assert calls == []
