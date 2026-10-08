"""CC7a.4 guarded native weather reuse; no device/provider/model calls."""
import asyncio
import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.bot.weather_reuse import (
    MAX_DISPATCH_METADATA, WeatherReuseBridge, current_weather_reuse,
    local_weather_subject_key, named_weather_subject_key, valid_weather_source,
    weather_display_metadata, weather_reuse_scope,
)
from jarvis.bot.weather_tool import build_local_weather_tool
from jarvis.privacy_policy import DataPolicy, make_tool_execution_scope, validate_tool_result
from jarvis.skills.registry import SkillRegistry, _ServerHandle, _ToolSourceContract


SOURCE = {
    "weather": {"city": "Atlanta", "requested_city": "Atlanta", "units": "imperial",
                "current": {"temperature_f": 70, "condition": "Clear"},
                "daily": [{"date": f"2026-10-{8 + i:02d}", "max_f": 75, "min_f": 60}
                          for i in range(7)], "lat": 33.75, "lon": -84.39,
                "human": "In Atlanta it is clear."},
    "radar": {"city": "Atlanta", "ts": 12, "tiles": ["https://public.example/radar.png"]},
    "subject_aliases": ["atlanta"],
}
DEVICE = {"ok": True, "source": "device", "lat": 33.75, "lon": -84.39,
          "accuracy_m": 40, "label": "Atlanta, GA"}


@pytest.fixture(autouse=True)
def ordinary_turn(monkeypatch):
    monkeypatch.setenv("JARVIS_UNITS", "imperial")
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def hit(source=None, ts=0, fresh_until=900):
    return {"status": "hit", "code": "cache_hit", "weather_source": copy.deepcopy(source or SOURCE),
            "ts": ts, "fresh_until": fresh_until}


class Session:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(isError=False, structuredContent=self.value, content=[])


def registry_for(tool="get_weather", *, pinned=True, value=None):
    registry = SkillRegistry("unused.yaml")
    session = Session(value or SOURCE["weather"])
    server = "mcp-web"
    entry = {"name": server, "command": "python", "args": ["-m", "mcp_servers.mcp_web.server"], "env": {}}
    registry._tools[tool] = (server, SimpleNamespace(name=tool))
    registry._sessions[server] = session
    registry._handles[server] = _ServerHandle(server, entry, state="up", session=session)
    if pinned:
        registry._source_contracts[server] = _ToolSourceContract(server, entry["args"][1], session)
    return registry, session


async def classified(registry, tool="get_weather", arguments=None, privacy="approved_external"):
    arguments = arguments or {"city": "Atlanta", "days": 1}
    scope = make_tool_execution_scope("weather-run", "weather-task", "weather-call", tool,
                                     arguments, DataPolicy(privacy, "input"))
    envelope = await registry.call_classified(tool, arguments, execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)
    return policy, json.loads(content)


def test_subject_identity_is_full_normalized_query_and_fresh_fix_not_label():
    assert named_weather_subject_key("  ＡTLANTA\t GA  ") == "weather:named:atlanta ga"
    assert named_weather_subject_key("Atlanta") != named_weather_subject_key("Atlanta, GA")
    key = local_weather_subject_key(DEVICE)
    assert key == local_weather_subject_key({**DEVICE, "label": "Different label"})
    assert key != local_weather_subject_key({**DEVICE, "lat": 33.7502})
    assert key != local_weather_subject_key({**DEVICE, "source": "ip"})
    assert key != local_weather_subject_key({**DEVICE, "accuracy_m": 5000})
    assert local_weather_subject_key({**DEVICE, "lat": float("nan")}) is None
    assert named_weather_subject_key("x" * 121) is not None
    assert named_weather_subject_key("x" * 201) is None


@pytest.mark.parametrize("tool", ["get_weather", "get_weather_radar"])
async def test_guarded_hit_preserves_classified_envelope_without_mcp_fetch(tool):
    registry, session = registry_for(tool)
    seen = []

    async def query(**request):
        seen.append(request)
        return hit()

    bridge = WeatherReuseBridge(query)
    arguments = {"city": "ATLANTA", **({"days": 1} if tool == "get_weather" else {})}
    with weather_reuse_scope(bridge):
        policy, result = await classified(registry, tool, arguments)
    assert session.calls == [] and len(seen) == 1
    assert seen[0]["subject_key"] == "weather:named:atlanta"
    expected = copy.deepcopy(SOURCE["weather" if tool == "get_weather" else "radar"])
    if tool == "get_weather":
        expected.update(daily=expected["daily"][:1], requested_city=arguments["city"])
    assert result == expected
    assert policy.level == "approved_external"
    metadata = bridge.take_dispatch_metadata(tool=tool, arguments=arguments)
    assert metadata["ts"] == 0 and metadata["fresh_until"] == 900 and metadata["reused"]
    assert bridge.take_dispatch_metadata(tool=tool, arguments=arguments) is None
    assert current_weather_reuse.get() is None


@pytest.mark.parametrize("city", ["Atlanta", "  ＡＴＬＡＮＴＡ  "])
async def test_seven_day_cache_projects_requested_day_and_echo_without_changing_native_original(city):
    from jarvis.skill_step_checks import _weather_current_and_forecast_returned

    source = copy.deepcopy(SOURCE)
    source["weather"]["source"] = "weather.gov"
    source["weather"]["current"].update(temperature_c=(70 - 32) * 5 / 9,
        observed_at=datetime.now(timezone.utc).isoformat())
    for day in source["weather"]["daily"]:
        day.update(max_c=(day["max_f"] - 32) * 5 / 9, min_c=(day["min_f"] - 32) * 5 / 9)
    original = copy.deepcopy(source)
    supplied = hit(source, ts=0, fresh_until=300)
    async def query(**request):
        assert request["subject_key"] == "weather:named:atlanta" and request["days"] == 1
        return supplied
    bridge = WeatherReuseBridge(query)
    raw_outcome = await bridge.lookup(subject_key="weather:named:atlanta", tool="get_weather",
                                      days=1, units="imperial")
    registry, session = registry_for()
    arguments = {"city": city, "days": 1}
    with weather_reuse_scope(bridge):
        policy, result = await classified(registry, arguments=arguments)
    assert policy.level == "approved_external" and session.calls == []
    assert result["daily"] == original["weather"]["daily"][:1]
    assert result["requested_city"] == city
    for field in ("current", "source", "city", "units", "lat", "lon", "human"):
        assert result[field] == original["weather"][field]
    assert source == original and supplied["weather_source"] == original and raw_outcome.source == original
    assert len(raw_outcome.source["weather"]["daily"]) == 7
    assert _weather_current_and_forecast_returned({"tool_name": "get_weather",
        "arguments": arguments, "result": json.dumps(result)})
    metadata = bridge.take_dispatch_metadata(tool="get_weather", arguments=arguments)
    assert metadata["ts"] == 0 and metadata["fresh_until"] == 300 and metadata["reused"]


@pytest.mark.parametrize("echo_present", [False, True])
async def test_cached_radar_echoes_request_only_when_the_original_field_exists(echo_present):
    source = copy.deepcopy(SOURCE)
    if echo_present:
        source["radar"]["requested_city"] = "Atlanta"
    original = copy.deepcopy(source)
    async def query(**_):
        return hit(source)
    registry, session = registry_for("get_weather_radar")
    with weather_reuse_scope(WeatherReuseBridge(query)):
        _, result = await classified(registry, "get_weather_radar", {"city": "ＡＴＬＡＮＴＡ"})
    assert source == original and session.calls == []
    if echo_present:
        assert result["requested_city"] == "ＡＴＬＡＮＴＡ"
    else:
        assert "requested_city" not in result
    for field in ("city", "ts", "tiles"):
        assert result[field] == original["radar"][field]


@pytest.mark.parametrize("privacy", ["confidential", "local_only"])
async def test_private_classified_path_performs_neither_native_query_nor_fetch(privacy):
    registry, session = registry_for()
    calls = []

    async def query(**request):
        calls.append(request)
        return hit()

    with weather_reuse_scope(WeatherReuseBridge(query)):
        _, result = await classified(registry, privacy=privacy)
    assert calls == [] and session.calls == []
    assert result == {"ok": False, "error": "tool_protected"}


@pytest.mark.parametrize("reply", [
    {"status": "refused", "code": "ambiguous_result"},
    {"status": "refused", "code": "stale_selection"},
    {"status": "refused", "code": "timeout"},
    {"status": "miss", "code": "stale_selection"},
    hit(ts=0, fresh_until=901),
    hit(ts=True),
    hit(source={"weather": {"units": "imperial", "current": {}, "daily": []}}),
])
async def test_refused_or_invalid_hit_never_falls_back_to_an_mcp_fetch(reply):
    registry, session = registry_for()

    async def query(**_):
        return reply

    with weather_reuse_scope(WeatherReuseBridge(query)):
        policy, result = await classified(registry)
    assert session.calls == [] and policy.level == "approved_external"
    assert result["ok"] is False and result["error"].startswith("weather_reuse_")


@pytest.mark.parametrize("code", ["no_matching_result", "cache_missing", "cache_expired", "cache_incomplete"])
async def test_genuine_native_miss_uses_original_fetch_and_original_arguments(code):
    registry, session = registry_for()

    async def query(**_):
        return {"status": "miss", "code": code}

    bridge = WeatherReuseBridge(query)
    arguments = {"city": "Atlanta", "days": 3}
    with weather_reuse_scope(bridge):
        policy, result = await classified(registry, arguments=arguments)
    assert session.calls == [("get_weather", arguments)] and result == SOURCE["weather"]
    assert policy.level == "approved_external"
    metadata = bridge.take_dispatch_metadata(tool="get_weather", arguments=arguments)
    assert metadata["ts"] > 0 and metadata["fresh_until"] == metadata["ts"] + 900
    assert metadata["reused"] is False


async def test_query_timeout_and_exception_are_closed_refusals_without_retry():
    registry, session = registry_for()
    for error, category in [(asyncio.TimeoutError(), "timeout"), (ValueError("private error"), "query_failed")]:
        async def query(**_):
            raise error
        with weather_reuse_scope(WeatherReuseBridge(query)):
            _, result = await classified(registry)
        assert result == {"ok": False, "error": "weather_reuse_" + category}
    assert session.calls == []


async def test_privacy_and_source_authority_are_rechecked_after_the_native_await():
    registry, session = registry_for()

    async def query(**_):
        current_sensitive_turn.get().arm("test", "weather-run")
        return hit()

    with weather_reuse_scope(WeatherReuseBridge(query)):
        _, result = await classified(registry)
    assert result == {"ok": False, "error": "weather_reuse_protected_turn"} and session.calls == []
    current_sensitive_turn.get().clear()

    async def replaced(**_):
        registry._source_contracts.clear()
        return hit()

    with weather_reuse_scope(WeatherReuseBridge(replaced)):
        policy, result = await classified(registry)
    assert result["error"] == "weather_reuse_stale_selection"
    assert policy.level == "confidential" and session.calls == []


async def test_unverified_and_non_weather_calls_keep_the_original_route():
    calls = []

    async def query(**request):
        calls.append(request)
        return hit()

    bridge = WeatherReuseBridge(query)
    with weather_reuse_scope(bridge):
        unverified, first = registry_for(pinned=False)
        policy, _ = await classified(unverified)
        current_sensitive_turn.get().clear()  # The unverified call correctly armed privacy.
        ordinary, second = registry_for("web_search", value={"results": []})
        await classified(ordinary, "web_search", {"query": "weather"})
    assert calls == [] and len(first.calls) == len(second.calls) == 1
    assert policy.level == "confidential"


async def test_context_binding_isolated_between_concurrent_runs_and_restored_on_cancel():
    registry, session = registry_for()
    entered = asyncio.Event()
    count = 0

    def own_query(temperature):
        async def query(**_):
            nonlocal count
            count += 1
            if count == 2:
                entered.set()
            await entered.wait()
            source = copy.deepcopy(SOURCE)
            source["weather"]["current"]["temperature_f"] = temperature
            return hit(source)
        return query

    async def run(temperature):
        with weather_reuse_scope(WeatherReuseBridge(own_query(temperature))):
            _, result = await classified(registry)
            return result["current"]["temperature_f"]

    assert await asyncio.gather(run(71), run(82)) == [71, 82]
    assert session.calls == [] and current_weather_reuse.get() is None
    async def cancelled(**_):
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        with weather_reuse_scope(WeatherReuseBridge(cancelled)):
            await classified(registry)
    assert current_weather_reuse.get() is None


def test_source_bounds_and_explicit_zero_disable_only_reuse_metadata():
    assert weather_display_metadata("weather:named:atlanta", SOURCE, 0)["ts"] == 0
    source = copy.deepcopy(SOURCE)
    source["weather"]["human"] = "é" * (16 * 1024)
    assert valid_weather_source(source) is None
    assert weather_display_metadata("weather:named:atlanta", source, 0) == {"subject_key": "weather:named:atlanta", "ts": 0}
    for value in [float("nan"), float("inf"), True, 10 ** 1000]:
        assert weather_display_metadata("weather:named:atlanta", SOURCE, value) == {"subject_key": "weather:named:atlanta"}
    assert valid_weather_source({**SOURCE, "subject_aliases": [None]}) is None


def test_dispatch_provenance_is_bounded_one_use_and_has_no_weather_bodies():
    bridge = WeatherReuseBridge(lambda **_: None)
    for index in range(MAX_DISPATCH_METADATA + 7):
        bridge.record_dispatch(tool="get_weather", subject_key=named_weather_subject_key(f"place{index}"),
                               run_id=str(index), ts=index)
    assert len(bridge._dispatch) == MAX_DISPATCH_METADATA
    assert bridge.take_dispatch_metadata(tool="get_weather", arguments={"city": "place0"}, run_id="0") is None
    assert all(set(metadata) == {"subject_key", "ts", "fresh_until", "reused"}
               for metadata in bridge._dispatch.values())
    bridge.clear()
    assert bridge._dispatch == {}


async def test_local_hit_uses_new_device_fix_and_native_arrival_without_display_replay():
    calls, displays = [], []

    async def locate(protected):
        calls.append("locate")
        return DEVICE
    async def query(**request):
        calls.append(request)
        return hit()
    def fetch(*_):
        pytest.fail("A confirmed native hit must perform zero provider fetches")
    async def display(payload):
        displays.append(payload)
    _, handler = build_local_weather_tool(locate=locate, push_display=display,
        fetch_weather=fetch, fetch_radar=fetch, reuse=WeatherReuseBridge(query))
    text = await handler({"city": "Remembered place is ignored"})
    assert calls[0] == "locate" and calls[1]["subject_key"] == local_weather_subject_key(DEVICE)
    assert calls[1]["days"] == 7 and displays == []
    assert "Atlanta, GA (this device's location)" in text and "no new weather lookup" in text


async def test_local_refusal_does_not_fetch_and_private_turn_does_not_locate_or_query():
    calls = []
    async def locate(_):
        calls.append("locate")
        return DEVICE
    async def query(**_):
        calls.append("query")
        return {"status": "refused", "code": "stale_selection"}
    def fetch(*_):
        calls.append("fetch")
        return SOURCE["weather"]
    _, handler = build_local_weather_tool(locate=locate, fetch_weather=fetch, fetch_radar=fetch,
                                         reuse=WeatherReuseBridge(query))
    assert "weather_reuse_stale_selection" in await handler({})
    assert calls == ["locate", "query"]
    current_sensitive_turn.get().arm("test", "weather-run")
    assert "protected turn" in await handler({})
    assert calls == ["locate", "query"]


async def test_local_miss_fetches_at_current_fix_and_carries_fetch_not_radar_timing():
    calls, displays = [], []
    async def locate(_):
        calls.append("locate")
        return DEVICE
    async def query(**request):
        calls.append(request)
        return {"status": "miss", "code": "cache_expired"}
    def weather(lat, lon, label, days):
        calls.append(("weather", lat, lon, label, days))
        return SOURCE["weather"]
    def radar(lat, lon, label):
        calls.append(("radar", lat, lon, label))
        return SOURCE["radar"]
    async def display(payload):
        displays.append(payload)
    _, handler = build_local_weather_tool(locate=locate, fetch_weather=weather,
        fetch_radar=radar, push_display=display, reuse=WeatherReuseBridge(query))
    await handler({"city": "Remembered place is ignored"})
    assert calls[:1] == ["locate"] and calls[1]["subject_key"] == local_weather_subject_key(DEVICE)
    assert ("weather", DEVICE["lat"], DEVICE["lon"], DEVICE["label"], 7) in calls
    assert len(displays) == 1 and displays[0]["subject_key"] == local_weather_subject_key(DEVICE)
    assert displays[0]["ts"] != SOURCE["radar"]["ts"]
    assert displays[0]["fresh_until"] == displays[0]["ts"] + 900
    assert displays[0]["weather_source"]["radar"]["ts"] == SOURCE["radar"]["ts"]
    assert displays[0]["data_policy"] == "approved_external"


async def test_changed_local_privacy_during_location_does_not_query_or_fetch():
    calls = []
    async def locate(_):
        current_sensitive_turn.get().arm("test", "weather-run")
        return DEVICE
    async def query(**request):
        calls.append(request)
        return hit()
    def fetch(*_):
        calls.append("fetch")
    _, handler = build_local_weather_tool(locate=locate, fetch_weather=fetch, fetch_radar=fetch,
                                         reuse=WeatherReuseBridge(query))
    assert "protected turn" in await handler({}) and calls == []


async def test_registry_context_does_not_bypass_tool_server_allowlist():
    registry, session = registry_for()
    calls = []
    async def query(**request):
        calls.append(request)
        return hit()
    with weather_reuse_scope(WeatherReuseBridge(query)):
        await registry.call("get_weather", {"city": "Atlanta"}, server_names=["mcp-time"])
    assert calls == [] and session.calls == []


@pytest.mark.parametrize("reply", [
    {"status": "miss", "code": "cache_missing", "weather_source": SOURCE},
    {"status": "miss", "code": "cache_expired", "ts": 0},
    hit(source={**SOURCE, "weather": {**SOURCE["weather"], "units": "metric"}}),
    hit(source={**SOURCE, "subject_aliases": ["Atlanta"]}),
])
async def test_malformed_or_wrong_capability_native_reply_is_not_a_miss(reply):
    registry, session = registry_for()
    async def query(**_):
        return reply
    with weather_reuse_scope(WeatherReuseBridge(query)):
        _, result = await classified(registry)
    assert result == {"ok": False, "error": "weather_reuse_invalid_reply"} and session.calls == []


async def test_bridge_without_an_ordinary_turn_context_refuses_before_native_query():
    called = []
    async def query(**request):
        called.append(request)
        return hit()
    token = current_sensitive_turn.set(None)
    try:
        outcome = await WeatherReuseBridge(query).lookup(subject_key="weather:named:atlanta",
            tool="get_weather", days=1, units="imperial")
    finally:
        current_sensitive_turn.reset(token)
    assert outcome.status == "refused" and outcome.code == "protected_turn" and called == []


async def test_enabled_local_reuse_without_turn_context_refuses_before_device_or_ip_location():
    called = []
    async def locate(_):
        called.append("locate")
        return DEVICE
    async def query(**_):
        called.append("query")
        return hit()
    def fetch(*_):
        called.append("fetch")
    _, handler = build_local_weather_tool(locate=locate, fetch_weather=fetch, fetch_radar=fetch,
        is_protected=lambda: False, reuse=WeatherReuseBridge(query))
    token = current_sensitive_turn.set(None)
    try:
        assert "protected turn" in await handler({})
    finally:
        current_sensitive_turn.reset(token)
    assert called == []


@pytest.mark.parametrize("changed", [{"units": []}, {"tool": {}}, {"days": True}, {"run_id": []}])
async def test_invalid_internal_query_arguments_never_reach_native(changed):
    called = []
    async def query(**request):
        called.append(request)
        return hit()
    request = {"subject_key": "weather:named:atlanta", "tool": "get_weather", "days": 1,
               "units": "imperial", **changed}
    outcome = await WeatherReuseBridge(query).lookup(**request)
    assert outcome.status == "refused" and outcome.code == "invalid_request" and called == []
