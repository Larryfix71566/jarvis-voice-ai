"""Status spec T3.1 — supervision logic of SkillRegistry and the
process-scoped holder in jarvis/skills/shared.py. Spawn-free: the real
child-process behaviour is in tests/integration/test_registry_supervision.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from jarvis.skills import shared
from jarvis.skills.registry import SkillRegistry, _ServerHandle, _is_transport_error


def make_tool(name):
    return SimpleNamespace(name=name, description="d",
                           inputSchema={"type": "object", "properties": {}})


def ok_result(text):
    return SimpleNamespace(isError=False, structuredContent=None,
                           content=[SimpleNamespace(text=text)])


class FakeSession:
    def __init__(self, text="ok", exc=None):
        self.text, self.exc, self.calls = text, exc, 0

    async def call_tool(self, name, arguments):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return ok_result(self.text)


def registry_with(server="mcp-time", tool="get_current_time", session=None,
                  state="up"):
    reg = SkillRegistry(config_path="unused.yaml")
    h = _ServerHandle(name=server, entry={"name": server}, state=state)
    h.tools = {tool: make_tool(tool)}
    reg._handles = {server: h}
    reg._known_tools = {tool: server}
    if state == "up":
        h.session = session
        reg._sessions = {server: session}
        reg._tools = {tool: (server, h.tools[tool])}
    return reg, h


class TestTransportErrors:
    @pytest.mark.parametrize("exc", [
        anyio.ClosedResourceError(), anyio.BrokenResourceError(), anyio.EndOfStream(),
        McpError(ErrorData(code=-32000, message="Connection closed")),
    ])
    def test_recognised(self, exc):
        assert _is_transport_error(exc)

    @pytest.mark.parametrize("exc", [
        McpError(ErrorData(code=-32602, message="Invalid params")),
        RuntimeError("crash"), ValueError("x"),
    ])
    def test_not_transport(self, exc):
        assert not _is_transport_error(exc)


class TestCallSupervision:
    async def test_transport_error_restarts_and_retries_once(self, monkeypatch):
        dead = FakeSession(exc=anyio.ClosedResourceError())
        fresh = FakeSession(text="12:00")
        reg, h = registry_with(session=dead)
        seen = []

        async def fake_restart(server, failed_session=None, only_if_down=False):
            seen.append((server, failed_session))
            h.session = fresh
            reg._sessions[server] = fresh
            return True

        monkeypatch.setattr(reg, "_restart", fake_restart)
        assert await reg.call("get_current_time", {}) == "12:00"
        assert seen == [("mcp-time", dead)]
        assert dead.calls == 1 and fresh.calls == 1

    async def test_failed_restart_names_the_server_and_error(self, monkeypatch):
        reg, h = registry_with(session=FakeSession(exc=anyio.ClosedResourceError()))

        async def fake_restart(server, failed_session=None, only_if_down=False):
            return False

        monkeypatch.setattr(reg, "_restart", fake_restart)
        result = await reg.call("get_current_time", {})
        assert result == ("get_current_time failed: mcp-time stopped and could "
                          "not be restarted (ClosedResourceError: ).")

    async def test_a_retry_that_fails_again_does_not_restart_twice(self, monkeypatch):
        reg, h = registry_with(session=FakeSession(exc=anyio.ClosedResourceError()))
        restarts = []

        async def fake_restart(server, failed_session=None, only_if_down=False):
            restarts.append(server)
            again = FakeSession(exc=anyio.BrokenResourceError())
            h.session = again
            reg._sessions[server] = again
            return True

        monkeypatch.setattr(reg, "_restart", fake_restart)
        result = await reg.call("get_current_time", {})
        assert restarts == ["mcp-time"]
        assert "stopped and could not be restarted" in result

    async def test_ordinary_exception_is_not_a_restart(self, monkeypatch):
        reg, _ = registry_with(session=FakeSession(exc=RuntimeError("crash")))

        async def boom(*a, **k):
            raise AssertionError("must not restart on a tool's own error")

        monkeypatch.setattr(reg, "_restart", boom)
        assert await reg.call("get_current_time", {}) == "get_current_time failed: RuntimeError."

    async def test_down_server_tool_is_unavailable_not_unknown(self, monkeypatch):
        reg, h = registry_with(state="down")
        h.last_error = "ClosedResourceError: "
        background = []
        monkeypatch.setattr(reg, "_restart_in_background", background.append)

        result = await reg.call("get_current_time", {})
        assert result == ("get_current_time failed: mcp-time is unavailable "
                          "(ClosedResourceError: ); it restarts automatically.")
        assert background == ["mcp-time"]

    async def test_down_server_tool_still_respects_scope(self):
        reg, _ = registry_with(state="down")
        result = await reg.call("get_current_time", {}, server_names=["mcp-notes"])
        assert result == "Tool 'get_current_time' is not available in this context."

    async def test_unknown_tool_is_still_unknown(self):
        reg, _ = registry_with(state="down")
        result = await reg.call("nope", {})
        assert result == "Unknown tool 'nope'. Available: none."

    async def test_background_restart_respects_backoff(self, monkeypatch):
        import time
        reg, h = registry_with(state="down")
        h.restarts = [time.monotonic()] * 3
        created = []
        monkeypatch.setattr("asyncio.create_task", lambda *a, **k: created.append(a))
        reg._restart_in_background("mcp-time")
        assert created == []


class TestStatusAndStop:
    def test_status_shape(self):
        reg, h = registry_with(session=FakeSession())
        assert reg.status() == {"mcp-time": {
            "state": "up", "last_error": "", "restarts_last_60s": 0, "tools": 1}}

    async def test_stop_clears_everything_and_is_idempotent(self):
        reg, _ = registry_with(session=FakeSession())
        await reg.stop()
        await reg.stop()
        assert reg._sessions == {} and reg._tools == {} and reg.status() == {}
        assert (await reg.call("get_current_time", {})).startswith("Unknown tool")


class FakeRegistry:
    instances: list = []

    def __init__(self, config_path):
        self.config_path = config_path
        self.started = 0
        self.stopped = 0
        FakeRegistry.instances.append(self)

    async def start(self):
        self.started += 1

    async def stop(self):
        self.stopped += 1


class TestShared:
    @pytest.fixture(autouse=True)
    def _fresh(self, monkeypatch):
        monkeypatch.delenv("JARVIS_REGISTRY_SHARED_ENABLED", raising=False)
        FakeRegistry.instances = []
        shared._reset_for_tests()
        yield
        shared._reset_for_tests()

    @pytest.mark.parametrize("value,expected", [
        (None, True), ("true", True), ("", True),
        ("false", False), ("0", False), ("no", False), (" OFF ", False),
    ])
    def test_shared_enabled(self, monkeypatch, value, expected):
        if value is not None:
            monkeypatch.setenv("JARVIS_REGISTRY_SHARED_ENABLED", value)
        assert shared.shared_enabled() is expected

    async def test_started_once_and_reused(self, tmp_path):
        a = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        b = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        assert a is b
        assert len(FakeRegistry.instances) == 1
        assert a.started == 1 and a.stopped == 0

    async def test_a_failed_start_is_not_cached(self, tmp_path):
        class Collides(FakeRegistry):
            async def start(self):
                raise ValueError("Tool name collision: ...")

        with pytest.raises(ValueError):
            await shared.get_shared_registry(tmp_path / "c.yaml", factory=Collides)
        reg = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        assert reg.started == 1

    async def test_shutdown_stops_and_forgets(self, tmp_path):
        a = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        await shared.shutdown_shared_registry()
        await shared.shutdown_shared_registry()          # idempotent
        assert a.stopped == 1
        b = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        assert b is not a

    async def test_a_different_loop_never_reuses_the_registry(self, tmp_path, caplog):
        a = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        shared._shared_loop = object()                   # as if started on another loop
        b = await shared.get_shared_registry(tmp_path / "c.yaml", factory=FakeRegistry)
        assert b is not a
        assert "registry_shared_loop_changed" in caplog.text
