"""Status spec T3.1 (L11) — the supervised, process-scoped SkillRegistry.

Integration, because every test here spawns a real MCP child over stdio
(tests/unit/test_registry.py is spawn-free by design).

The first two tests reproduce fact 3.4 with the raw SDK, exactly the way the
pre-T3.1 registry used it; the rest prove the owner-task design fixes both:
  (a) after the child dies, ClientSession.call_tool raises
      anyio.ClosedResourceError forever — nothing reconnects;
  (c) exiting stdio_client/ClientSession from a different task than the one
      that entered them fails with "Attempted to exit cancel scope in a
      different task" (the old registry logged it as registry_stop_error).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

import anyio
import psutil
import pytest
import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jarvis.skills import shared
from jarvis.skills.registry import REPO_ROOT, SkillRegistry

TIME_MODULE = "mcp_servers.mcp_time.server"
TIME_ENTRY = {"name": "mcp-time", "command": "python",
              "args": ["-m", TIME_MODULE], "env": {}}
BOGUS_ENTRY = {"name": "mcp-bogus", "command": "python",
               "args": ["-c", "import sys; sys.exit(1)"], "env": {}}


def _write_config(tmp_path: Path, servers: list[dict]) -> Path:
    path = tmp_path / "servers.yaml"
    path.write_text(yaml.safe_dump({"servers": servers}))
    return path


def _child_pids(module: str = TIME_MODULE) -> list[int]:
    pids = []
    for proc in psutil.Process().children(recursive=True):
        try:
            if module in " ".join(proc.cmdline()):
                pids.append(proc.pid)
        except psutil.Error:
            continue
    return pids


def _kill_children(module: str = TIME_MODULE) -> list[int]:
    """SIGKILL the child. Not reaped here: asyncio's child watcher owns
    that, and stealing the exit status only produces warnings."""
    pids = _child_pids(module)
    assert pids, f"no live {module} child to kill"
    for pid in pids:
        os.kill(pid, signal.SIGKILL)
    return pids


async def _settle() -> None:
    """Let the parent observe the child's EOF, the way a user's next
    request arrives seconds after a crash (P3 acceptance 2)."""
    await asyncio.sleep(1.0)


def _alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


async def _gone(pids: list[int], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_alive(p) for p in pids):
            return True
        await asyncio.sleep(0.1)
    return False


def _params() -> StdioServerParameters:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return StdioServerParameters(command=sys.executable, args=["-m", TIME_MODULE],
                                 env=env, cwd=str(REPO_ROOT))


@pytest.fixture
async def time_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "sup.db"))
    reg = SkillRegistry(_write_config(tmp_path, [TIME_ENTRY]))
    await reg.start()
    yield reg
    await reg.stop()


# --------------------------------------------------------------------------- #
# Fact 3.4, reproduced with the raw SDK (the pre-T3.1 usage)
# --------------------------------------------------------------------------- #

async def test_fact_3_4a_a_dead_child_fails_every_later_call():
    """(a) Nothing in the SDK reconnects: two calls after the kill, two
    ClosedResourceErrors. This is what made `registry.call` return
    "<tool> failed: ClosedResourceError." forever."""
    stack = AsyncExitStack()
    try:
        read, write = await stack.enter_async_context(stdio_client(_params()))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        assert not (await session.call_tool("get_current_time", {})).isError
        _kill_children()
        await _settle()
        for _ in range(2):
            with pytest.raises(anyio.ClosedResourceError):
                await asyncio.wait_for(session.call_tool("get_current_time", {}), 10)
    finally:
        # Closing over a dead child raises an ExceptionGroup
        # (BrokenResourceError from the stdin writer); _serve absorbs the
        # same thing in its owner task.
        try:
            await stack.aclose()
        except Exception:  # noqa: BLE001
            pass


async def test_fact_3_4c_exiting_from_another_task_fails():
    """(c) Contexts entered in one task cannot be exited from another. The
    old registry entered them in start()'s task and closed them in
    stop()'s, which is exactly this."""
    entered = asyncio.Event()
    box: dict = {}

    async def opener():
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(stdio_client(_params()))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        box["stack"] = stack
        entered.set()

    await asyncio.create_task(opener())
    await entered.wait()
    pids = _child_pids()
    try:
        with pytest.raises(RuntimeError, match="different task"):
            await box["stack"].aclose()
    finally:
        for pid in pids:                     # the failed exit leaks the child
            if psutil.pid_exists(pid):
                psutil.Process(pid).kill()


# --------------------------------------------------------------------------- #
# The owner-task design
# --------------------------------------------------------------------------- #

async def test_dead_child_is_restarted_and_call_succeeds(time_registry, caplog):
    """Both ways a dead child shows up. (1) The parent has already seen EOF:
    call_tool raises ClosedResourceError (fact 3.4a). (2) The call races the
    death: the write crashes the owner task's stdio task group, and the
    request would otherwise wait out CALL_TIMEOUT. Either way the next call
    returns the tool's normal output from a fresh child."""
    assert "iso" in json.loads(await time_registry.call("get_current_time", {}))

    with caplog.at_level(logging.INFO, logger="jarvis.skills.registry"):
        killed = _kill_children()
        await _settle()
        started = time.monotonic()
        after_eof = await time_registry.call("get_current_time", {})
        killed += _kill_children()
        racing = await time_registry.call("get_current_time", {})
        elapsed = time.monotonic() - started

    assert "iso" in json.loads(after_eof), after_eof
    assert "iso" in json.loads(racing), racing
    assert elapsed < 20, "a restart, not a CALL_TIMEOUT wait"
    assert not set(_child_pids()) & set(killed), "a fresh child answered"
    assert caplog.text.count("mcp_server_restarted name=mcp-time ok=True") == 2
    assert "mcp_registry_status" in caplog.text
    status = time_registry.status()["mcp-time"]
    assert status["state"] == "up"
    assert status["restarts_last_60s"] == 2
    assert status["tools"] == 4


async def test_restart_backoff_marks_down_after_three(time_registry):
    for n in range(1, 4):
        _kill_children()
        assert "iso" in json.loads(await time_registry.call("get_current_time", {}))
        assert time_registry.status()["mcp-time"]["restarts_last_60s"] == n

    _kill_children()
    result = await time_registry.call("get_current_time", {})
    assert result.startswith(
        "get_current_time failed: mcp-time stopped and could not be restarted ("), result
    status = time_registry.status()["mcp-time"]
    assert status["state"] == "down"
    assert status["restarts_last_60s"] == 3
    assert status["tools"] == 0
    assert time_registry.openai_tools() == []


async def test_down_server_tools_report_unavailable(time_registry):
    """Four kills inside 60 s. The fourth failing call is the one whose
    restart the backoff refuses; from then on the tool answers "unavailable"
    — never "Unknown tool", which invites the model to guess another name."""
    for _ in range(3):
        _kill_children()
        await time_registry.call("get_current_time", {})
    _kill_children()
    refused = await time_registry.call("get_current_time", {})
    assert "could not be restarted" in refused

    result = await time_registry.call("get_current_time", {})
    assert result.startswith("get_current_time failed: mcp-time is unavailable ("), result
    assert "restart limit reached" in result
    assert result.endswith("it restarts automatically.")
    assert "Unknown tool" not in result
    # Backoff also holds for the background restart: nothing was respawned.
    await asyncio.sleep(0.2)
    assert _child_pids() == []


async def test_start_isolates_a_failing_server(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "iso.db"))
    reg = SkillRegistry(_write_config(tmp_path, [BOGUS_ENTRY, TIME_ENTRY]))
    try:
        with caplog.at_level(logging.WARNING, logger="jarvis.skills.registry"):
            await reg.start()                          # does not raise
        status = reg.status()
        assert status["mcp-bogus"]["state"] == "down"
        assert status["mcp-bogus"]["last_error"]
        assert status["mcp-time"]["state"] == "up"
        assert "mcp_server_start_failed name=mcp-bogus" in caplog.text
        assert "iso" in json.loads(await reg.call("get_current_time", {}))
    finally:
        await reg.stop()


async def test_stop_from_another_task_is_clean(tmp_path, monkeypatch, caplog):
    """Fact 3.4c fixed: start() in one task, stop() in another — the shape of
    a process-scoped registry, started by the first session and stopped at
    process exit. No cancel-scope error, and the child is gone."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "x.db"))
    reg = SkillRegistry(_write_config(tmp_path, [TIME_ENTRY]))
    await asyncio.create_task(reg.start())             # a task that then ends
    pids = _child_pids()
    assert pids
    with caplog.at_level(logging.DEBUG):
        await asyncio.create_task(reg.stop())          # a different task
    assert "registry_stop_error" not in caplog.text
    assert "different task" not in caplog.text
    assert "mcp_server_down" not in caplog.text
    assert reg._sessions == {} and reg._tools == {}
    assert await _gone(pids), "the child outlived stop()"


async def test_concurrent_calls_share_one_session(time_registry):
    results = await asyncio.gather(*(
        time_registry.call("get_current_time", {}) for _ in range(20)))
    assert all("iso" in json.loads(r) for r in results), results
    assert len(_child_pids()) == 1


async def test_shared_registry_serves_sequential_sessions_on_one_loop(tmp_path, monkeypatch):
    """The runnable stand-in for Step 0 (which only the Mac can run): two
    run_session-style users, one after the other, each in its OWN task that
    ends before the next begins, on one event loop. One start, zero stops,
    and the second user's call is served by owner tasks the first user's
    (finished) task created."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "shared.db"))
    config = _write_config(tmp_path, [TIME_ENTRY])
    starts, stops = [], []

    class CountingRegistry(SkillRegistry):
        async def start(self):
            starts.append(True)
            await super().start()

        async def stop(self):
            stops.append(True)
            await super().stop()

    loop_ids = []

    async def session_user():
        loop_ids.append(id(asyncio.get_running_loop()))
        registry = await shared.get_shared_registry(config, factory=CountingRegistry)
        return registry, await registry.call("get_current_time", {})

    shared._reset_for_tests()
    try:
        first, r1 = await asyncio.create_task(session_user())
        pids = _child_pids()
        second, r2 = await asyncio.create_task(session_user())
        assert first is second
        assert "iso" in json.loads(r1) and "iso" in json.loads(r2)
        assert starts == [True] and stops == []
        assert loop_ids[0] == loop_ids[1]
        assert _child_pids() == pids, "the same child served both sessions"
    finally:
        await shared.shutdown_shared_registry()
        shared._reset_for_tests()
    assert stops == [True]


_BOT_STANDIN = """
import asyncio, os, sys
from pathlib import Path
from jarvis.skills.shared import get_shared_registry

async def main():
    await get_shared_registry(Path(sys.argv[1]))
    print("READY", flush=True)
    await asyncio.Event().wait()

asyncio.run(main())
"""


async def test_children_exit_when_the_parent_is_terminated(tmp_path):
    """Linux stand-in for Step 0b (Mac-only): SIGTERM the process holding
    the shared registry; its MCP children must be gone within 5 s. They sit
    in their own session (the SDK spawns with start_new_session=True), so
    what ends them is stdin EOF when the parent's pipe closes, not the
    signal."""
    config = _write_config(tmp_path, [TIME_ENTRY])
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT),
           "JARVIS_DB_PATH": str(tmp_path / "p.db")}
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _BOT_STANDIN, str(config), cwd=str(REPO_ROOT),
        env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), 60)
        assert line.strip() == b"READY"
        children = [c.pid for c in psutil.Process(proc.pid).children(recursive=True)
                    if TIME_MODULE in " ".join(c.cmdline())]
        assert children, "the stand-in bot spawned no MCP child"
        proc.terminate()
        await asyncio.wait_for(proc.wait(), 10)
        assert await _gone(children, timeout=5.0), "an MCP child outlived its parent"
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
