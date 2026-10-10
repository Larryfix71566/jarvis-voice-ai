"""CC7a.4 causal tests compiled from the actual nested pipeline callbacks.

No audio engines, device lookups, MCP children or provider clients are started.
The synthetic native sender acknowledges the production waiters immediately.
"""
import ast
import asyncio
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

import pytest

from jarvis.bot.console_actions import _disclosed_inventory, build_console_action_tool
from jarvis.bot.console_protocol import MAX_MESSAGE, validate_inventory, validate_request
from jarvis.bot.console_session import ConsoleSession
from jarvis.bot.display import WeatherReportMerger, build_display_payload
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn, is_sensitive
from jarvis.bot.weather_reuse import WeatherReuseBridge, current_weather_reuse, weather_reuse_scope


SESSION = "00000000-0000-4000-8000-00000000000a"
GENERATION = "00000000-0000-4000-8000-00000000000b"
KEY = "weather:named:atlanta"
SOURCE = {"weather": {"city": "Atlanta", "requested_city": "Atlanta", "units": "imperial",
    "current": {"temperature_f": 70, "condition": "Clear"},
    "daily": [{"date": f"2026-10-{8 + i:02d}", "max_f": 75, "min_f": 60} for i in range(7)],
    "human": "Clear in Atlanta", "lat": 33.75, "lon": -84.39},
    "radar": {"city": "Atlanta", "ts": 12, "tiles": ["https://public.example/radar.png"]},
    "subject_aliases": ["atlanta"]}


@pytest.fixture(autouse=True)
def ordinary_turn(monkeypatch):
    monkeypatch.setenv("JARVIS_COMMAND_CONSOLE_ENABLED", "true")
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def row(identity=None, *, subject_key=KEY, number=1, subject="Atlanta"):
    return {"id": identity or str(uuid.uuid4()), "subject_key": subject_key, "number": number,
            "kind": "Weather", "title": f"Weather · {subject}", "subject": subject,
            "pinned": False, "unread": False}


def native_reply(request, **overrides):
    return {"type": "console/result", "version": 1, "session_id": SESSION.upper(),
            "generation": GENERATION.upper(), "request_id": request["request_id"].upper(),
            "status": "ok", "code": "inventory", "summary": "Native inventory.", **overrides}


class FastTimeoutAsyncio:
    """Inject an immediate deadline only into the extracted request wait."""
    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def wait_for(self, future, *, timeout):
        await asyncio.sleep(0)
        if future.done():
            return future.result()
        raise asyncio.TimeoutError()


class Harness:
    def __init__(self, *, fast_deadline=False):
        path = Path(__file__).resolve().parents[2] / "jarvis/bot/pipeline.py"
        tree = ast.parse(path.read_text())
        names = {"_weather_candidate_inventory", "_query_native_weather", "await_console_result",
                 "_send_ui_message", "handle_console_result", "_unwrap_client_message", "handle_console",
                 "weather_delegate_handler", "make_agent_event_handler"}
        nodes = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        assert len(nodes) == len(names)
        self.frames, self.waiters = [], {}
        self.inventory = {"revision": 7, "results": [row()]}
        self.cache_reply = {"status": "ok", "code": "cache_hit", "data": {
            "revision": 8, "weather_source": copy.deepcopy(SOURCE), "ts": 0, "fresh_until": 900}}
        self.native = self.default_native
        self.ns = dict(asyncio=FastTimeoutAsyncio() if fast_deadline else asyncio,
            uuid=uuid, json=json, os=os, Any=Any, MAX_MESSAGE=MAX_MESSAGE,
            _disclosed_inventory=_disclosed_inventory, validate_inventory=validate_inventory,
            console_session=ConsoleSession(session_id=SESSION, generation=GENERATION),
            console_inventory_revision={"value": 0}, console_ready={"value": True},
            console_waiters=self.waiters, console_generation=GENERATION,
            runtime=SimpleNamespace(session_id=SESSION), transport=object(),
            weather_query_lock=asyncio.Lock(), _voice_is_sensitive=is_sensitive,
            _log_console_validation_failure=lambda *_: None,
            _logger=SimpleNamespace(info=lambda *_: None), bot_event_log=lambda *_: None,
            WeatherReuseBridge=WeatherReuseBridge, WeatherReportMerger=WeatherReportMerger,
            build_display_payload=build_display_payload, current_weather_reuse=current_weather_reuse,
            weather_reuse_scope=weather_reuse_scope)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), self.ns)
        self.ns["send_app_message"] = self.send

    async def send(self, _transport, request):
        if request.get("type") == "console/request":
            assert request["request_id"] in self.waiters  # Actual future precedes immediate ACK.
            validate_request(request)
        self.frames.append(copy.deepcopy(request))
        await self.native(request)

    async def default_native(self, request):
        if request.get("action") == "inventory":
            await self.reply(request, data=self.inventory)
        elif request.get("action") == "weather_reuse":
            await self.reply(request, **self.cache_reply)

    async def reply(self, request, **overrides):
        await self.ns["handle_console_result"](native_reply(request, **overrides))

    async def publish(self, revision):
        await self.ns["handle_console"]({"type": "console/inventory", "version": 1,
            "session_id": SESSION, "generation": GENERATION, "revision": revision,
            "data": {"results": []}})

    async def lookup(self, **changed):
        return await WeatherReuseBridge(self.ns["_query_native_weather"]).lookup(
            **{"subject_key": KEY, "tool": "get_weather", "days": 1, "units": "imperial", **changed})

    async def settled(self):
        await asyncio.sleep(0)
        assert self.waiters == {}


async def test_immediate_native_ack_uses_matched_uuid_and_original_zero_timing():
    h = Harness()
    result = await h.lookup(run_id="originating-run")
    assert result.status == "hit" and result.source == SOURCE
    assert result.ts == 0 and result.fresh_until == 900
    query = h.frames[1]
    assert query["target"] == h.inventory["results"][0]["id"] and query["revision"] == 7
    assert query["args"] == {"subject_key": KEY, "tool": "get_weather", "days": 1,
                            "units": "imperial", "run_id": "originating-run", "ordinary_turn": True}
    assert h.ns["console_inventory_revision"]["value"] == 8
    await h.settled()


async def test_large_100_row_native_inventory_projects_exact_key_beyond_the_numbered_tail():
    h = Harness()
    target = str(uuid.uuid4())
    rows = [{**row(subject_key=f"weather:named:unrelated-{i}", number=i + 1 if i < 30 else None),
             "title": "T" * 120, "subject": "S" * 120, "index": i, "can_connections": [],
             "fresh_until": 900, "pinned": i < 20} for i in range(100)]
    rows[80].update(id=target.upper(), subject_key=KEY)
    h.inventory = {"revision": 7, "results": rows, "results_omitted": 25,
        "screens": [{"id": "supporting", "name": "External display", "is_supporting": True}],
        "panels": [{"id": "weather-panel", "kind": "weather", "title": "Weather"}],
        "skills": [{"id": f"skill-{i}", "title": "S" * 120} for i in range(6)]}
    witness = native_reply({"request_id": str(uuid.uuid4())}, data=h.inventory)
    assert len(json.dumps(witness, ensure_ascii=False, separators=(",", ":")).encode()) > MAX_MESSAGE
    assert h.ns["console_session"].revision == 0
    result = await h.lookup()
    assert result.status == "hit" and h.frames[1]["target"] == target
    # A host-only query never updates the model's observed inventory owner.
    assert h.ns["console_session"].revision == 0
    await h.settled()


async def test_host_weather_query_cannot_replace_the_number_list_disclosed_to_voice():
    h = Harness()
    alpha, bravo = str(uuid.uuid4()), str(uuid.uuid4())
    observed = {"revision": 7, "results": [row(alpha, subject_key="weather:named:alpha", subject="Alpha")]}
    latest = {"revision": 7, "results": [row(bravo), row(alpha, subject_key="weather:named:alpha",
                                                                  number=2, subject="Alpha")]}
    async def native(request):
        if request["action"] == "inventory":
            pending = h.waiters[request["request_id"]]
            await h.reply(request, data=latest if hasattr(pending, "_mortimer_weather_subject_key") else observed)
        elif request["action"] == "weather_reuse":
            await h.reply(request, **h.cache_reply)
        elif request["action"] == "result_close":
            await h.reply(request, status="error", code="stale_selection", summary="The console changed.")
    h.native = native
    _, voice = build_console_action_tool(h.ns["_send_ui_message"], session_id=SESSION,
        generation=GENERATION, revision=lambda: h.ns["console_inventory_revision"]["value"],
        await_result=h.ns["await_console_result"])
    await voice({"action": "inventory", "args": {"scope": "results"}})
    assert (await h.lookup()).status == "hit"
    text = await voice({"action": "result_close", "target": "1", "inventory_revision": 7})
    assert "changed" in text and h.frames[-1]["target"] == alpha
    assert h.frames[-1]["revision"] == 7 and h.ns["console_inventory_revision"]["value"] == 8
    await h.settled()


@pytest.mark.parametrize("rows,expected", [([], "no_matching_result"), ([row(), row()], "ambiguous_result")])
async def test_missing_and_ambiguous_candidates_never_guess_a_target(rows, expected):
    h = Harness()
    h.inventory = {"revision": 7, "results": rows}
    result = await h.lookup()
    assert result.code == expected and len(h.frames) == 1
    assert result.status == ("miss" if not rows else "refused")
    assert h.ns["console_inventory_revision"]["value"] == 7
    await h.settled()


async def test_arrival_between_inventory_and_query_preserves_observed_revision_and_newer_publication():
    h = Harness()
    async def native(request):
        if request["action"] == "inventory":
            await h.reply(request, data=h.inventory)
            await h.publish(9)
        else:
            assert request["action"] == "weather_reuse" and request["revision"] == 7
            await h.reply(request, status="error", code="stale_selection", summary="The console changed.")
    h.native = native
    result = await h.lookup()
    assert result.status == "refused" and result.code == "stale_selection" and result.source is None
    assert h.ns["console_inventory_revision"]["value"] == 9
    await h.settled()


async def test_delayed_cache_hit_ack_does_not_rewind_newer_public_inventory_revision():
    h = Harness()
    async def native(request):
        if request["action"] == "inventory":
            await h.reply(request, data=h.inventory)
        else:
            await h.publish(9)
            await h.reply(request, **h.cache_reply)
    h.native = native
    assert (await h.lookup()).status == "hit"
    assert h.ns["console_inventory_revision"]["value"] == 9
    await h.settled()


@pytest.mark.parametrize("forged", [
    {"session_id": str(uuid.uuid4())}, {"generation": str(uuid.uuid4())},
    {"version": 2}, {"version": True}, {"status": []}, {"status": {}},
    {"status": "unexpected"}, {"request_id": str(uuid.uuid4())},
])
async def test_forged_native_inventory_never_completes_a_query_or_releases_source(forged):
    h = Harness(fast_deadline=True)
    async def native(request):
        await h.reply(request, data=h.inventory, **forged)
        assert not h.waiters[request["request_id"]].done()
    h.native = native
    result = await h.lookup()
    assert result.status == "refused" and result.code == "timeout" and result.source is None
    assert len(h.frames) == 1 and h.ns["console_inventory_revision"]["value"] == 0
    await h.settled()


async def test_internal_inventory_projection_does_not_erase_oversized_non_data_overhead():
    h = Harness(fast_deadline=True)
    async def native(request):
        await h.reply(request, data=h.inventory, summary="X" * (MAX_MESSAGE + 1))
        assert not h.waiters[request["request_id"]].done()
    h.native = native
    result = await h.lookup()
    assert result.status == "refused" and result.code == "timeout" and result.source is None
    assert len(h.frames) == 1
    await h.settled()


async def test_cache_source_under_wire_limit_but_over_cache_field_limit_is_not_released():
    h = Harness()
    source = copy.deepcopy(SOURCE)
    source["weather"]["human"] = "X" * (16 * 1024)
    h.cache_reply["data"]["weather_source"] = source
    witness = native_reply({"request_id": str(uuid.uuid4())}, **h.cache_reply)
    assert len(json.dumps(witness, separators=(",", ":")).encode()) < MAX_MESSAGE
    result = await h.lookup()
    assert result.status == "refused" and result.code == "invalid_reply" and result.source is None
    assert len(h.frames) == 2
    await h.settled()


@pytest.mark.parametrize("during", ["unset", "before", "inventory", "cache"])
async def test_privacy_is_checked_before_first_frame_and_after_each_native_await(during):
    h = Harness()
    token = current_sensitive_turn.set(None) if during == "unset" else None
    if during == "before":
        current_sensitive_turn.get().arm("test", "weather-run")
    async def native(request):
        if (during == "inventory" and request["action"] == "inventory"
                or during == "cache" and request["action"] == "weather_reuse"):
            current_sensitive_turn.get().arm("test", "weather-run")
        await h.default_native(request)
    h.native = native
    try:
        result = await h.lookup()
    finally:
        if token is not None:
            current_sensitive_turn.reset(token)
    assert result.status == "refused" and result.code == "protected_turn" and result.source is None
    assert len(h.frames) == {"unset": 0, "before": 0, "inventory": 1, "cache": 2}[during]
    await h.settled()


async def test_not_ready_disconnect_deadline_and_cancel_release_all_existing_waiters():
    h = Harness()
    h.ns["console_ready"]["value"] = False
    assert (await h.lookup()).code == "not_ready" and h.frames == []
    h.ns["console_ready"]["value"] = True
    async def disconnected(_):
        raise ConnectionError("Synthetic disconnected transport")
    h.native = disconnected
    assert (await h.lookup()).code == "query_failed"
    await h.settled()
    deadline = Harness(fast_deadline=True)
    async def absent(_):
        pass
    deadline.native = absent
    assert (await deadline.lookup()).code == "timeout"
    await deadline.settled()
    waiting = Harness()
    sent = asyncio.Event()
    async def no_ack(_):
        sent.set()
    waiting.native = no_ack
    task = asyncio.create_task(waiting.lookup())
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await waiting.settled()


@pytest.mark.parametrize("changed", [{"days": True}, {"days": 8}, {"units": "kelvin"}, {"tool": "web_search"}])
async def test_invalid_internal_query_grammar_sends_no_native_frame(changed):
    h = Harness()
    result = await h.lookup(**changed)
    assert result.status == "refused" and result.code == "invalid_request" and h.frames == []


@pytest.mark.parametrize("code,status", [("cache_expired", "miss"), ("cache_incomplete", "miss"),
    ("cache_missing", "miss"), ("protected_result", "refused"), ("unknown_code", "refused")])
async def test_native_reason_categories_do_not_turn_a_refusal_into_a_fetch(code, status):
    h = Harness()
    h.cache_reply = {"status": "ok" if status == "miss" else "error", "code": code}
    result = await h.lookup()
    assert result.status == status and result.source is None and len(h.frames) == 2
    await h.settled()


async def test_queries_on_one_connection_are_serialized_but_other_connections_are_independent():
    first, other = Harness(), Harness()
    gate, entered = asyncio.Event(), asyncio.Event()
    original = first.native
    async def slow(request):
        if len(first.frames) == 1:
            entered.set()
            await gate.wait()
        await original(request)
    first.native = slow
    a = asyncio.create_task(first.lookup())
    await entered.wait()
    b = asyncio.create_task(first.lookup())
    assert (await other.lookup()).status == "hit"
    assert len(first.frames) == 1
    gate.set()
    assert all(result.status == "hit" for result in await asyncio.gather(a, b))
    assert [frame["action"] for frame in first.frames] == ["inventory", "weather_reuse", "inventory", "weather_reuse"]
    await first.settled()
    await other.settled()


async def test_actual_delegate_wrapper_scopes_detached_tasks_without_mutating_the_shared_registry():
    h = Harness()
    children, observed = [], []
    release = asyncio.Event()
    async def delegate(arguments):
        parent_bridge = current_weather_reuse.get()
        async def child():
            await release.wait()
            assert current_weather_reuse.get() is parent_bridge
            observed.append(parent_bridge)
        children.append(asyncio.create_task(child()))
        return arguments["task"]
    h.ns["delegate_handler"] = delegate
    assert await h.ns["weather_delegate_handler"]({"task": "first"}) == "first"
    assert current_weather_reuse.get() is None
    assert await h.ns["weather_delegate_handler"]({"task": "second"}) == "second"
    assert current_weather_reuse.get() is None
    release.set()
    await asyncio.gather(*children)
    assert len(observed) == 2 and observed[0] is not observed[1]


async def test_actual_event_handler_consumes_provenance_and_flushes_each_requested_city():
    h = Harness()
    handler = h.ns["make_agent_event_handler"](object())
    bridge = WeatherReuseBridge(h.ns["_query_native_weather"])
    async def discard(request):
        pass
    h.native = discard
    with weather_reuse_scope(bridge):
        for city in ("Atlanta", "Alpha"):
            key = f"weather:named:{city.lower()}"
            bridge.record_dispatch(tool="get_weather", subject_key=key, run_id="two-cities", ts=0)
            handler({"type": "agent_tool_result", "tool": "get_weather", "arguments": {"city": city},
                "result": json.dumps({**SOURCE["weather"], "requested_city": city}),
                "run_id": "two-cities", "agent": "analyst"})
            assert bridge.take_dispatch_metadata(tool="get_weather", arguments={"city": city}, run_id="two-cities") is None
        handler({"type": "delegate_done", "run_id": "two-cities", "agent": "analyst", "ok": True})
    await asyncio.sleep(0)
    displays = [frame["display"] for frame in h.frames if frame.get("type") == "display"]
    assert [payload["subject_key"] for payload in displays] == [KEY, "weather:named:alpha"]
    assert all(payload["ts"] == 0 and payload["data_policy"] == "approved_external" for payload in displays)
