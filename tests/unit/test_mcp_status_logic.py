"""T2.6 — mcp-status logic: a thin client of the sidecar's /api/status/*."""

from __future__ import annotations

import inspect

import pytest

from mcp_servers.mcp_status import logic


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.calls = []
        self.payload = payload if payload is not None else {"ok": True, "x": 1}
        self.error = error

    def get(self, path, params=None):
        self.calls.append((path, params))
        if self.error is not None:
            raise self.error
        return self.payload

    def post(self, path, json=None):  # pragma: no cover — status never posts
        raise AssertionError("status tools never write")


@pytest.mark.parametrize("fn,path", [
    (logic.status_models, "/api/status/models"),
    (logic.status_services, "/api/status/services"),
    (logic.status_overview, "/api/status/overview"),
    (logic.status_build, "/api/status/build"),
])
def test_path_per_tool(fn, path):
    client = FakeClient()
    assert fn(client=client) == {"ok": True, "x": 1}
    assert client.calls == [(path, None)]


def test_log_search_passes_params():
    client = FakeClient({"ok": True, "lines": ["a"]})
    out = logic.log_search("bot", "session", 30, 5, client=client)
    assert out == {"ok": True, "lines": ["a"]}
    assert client.calls == [("/api/status/logs", {"source": "bot", "query": "session",
                                                  "since_minutes": 30, "limit": 5})]


def test_log_search_defaults():
    client = FakeClient()
    logic.log_search("admin", client=client)
    assert client.calls[0][1] == {"source": "admin", "query": "", "since_minutes": 60,
                                  "limit": 50}


def test_sidecar_json_is_returned_unchanged():
    payload = {"ok": False, "error": "status tools are disabled"}
    assert logic.status_models(client=FakeClient(payload)) == payload


def test_transport_failure_is_a_result():
    out = logic.status_services(client=FakeClient(error=ConnectionError("refused")))
    assert out == {"ok": False, "error": "the admin sidecar is not reachable."}


def test_long_lists_are_trimmed():
    payload = {"ok": True, "lines": list(range(500)), "short": [1, 2]}
    out = logic.log_search("bot", client=FakeClient(payload))
    assert len(out["lines"]) == logic.MAX_LIST_ITEMS
    assert out["short"] == [1, 2]
    assert out["trimmed"] == {"lines": 500}


def test_default_client_is_the_selfedit_admin_client(monkeypatch):
    made = []

    class Spy(FakeClient):
        def __init__(self, timeout=10.0, **kw):
            super().__init__()
            made.append(timeout)

    monkeypatch.setattr(logic, "AdminClient", Spy)
    logic.status_build()
    assert made == [10.0]
    from mcp_servers.mcp_selfedit.logic import AdminClient

    assert logic.__dict__.get("AdminClient") is Spy
    monkeypatch.undo()
    assert logic.AdminClient is AdminClient
    assert logic.EXTERNAL_TIMEOUT_S == 28.0


def test_tool_order_and_signatures():
    from mcp_servers.mcp_status import server

    src = inspect.getsource(server)
    order = [src.index(f"def {n}(") for n in
             ("status_models", "status_services", "status_overview", "status_build",
              "log_search")]
    assert order == sorted(order)
    params = inspect.signature(logic.log_search).parameters
    assert list(params)[:4] == ["source", "query", "since_minutes", "limit"]
    assert not any("path" in p for p in params)
