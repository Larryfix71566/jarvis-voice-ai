"""Invented voice input through actual request/tool/display adapters; no providers."""
import importlib.util
from pathlib import Path

import pytest

from jarvis.bot.pipeline import adapt_to_pipecat, send_app_message
from jarvis.bot.weather_tool import build_local_weather_tool
from jarvis.bot.weather_intent import WeatherIntent, accepted_weather_intent, current_weather_intent
from jarvis.bot.weather_reuse import WeatherReuseBridge


def fixture_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = fixture_module("acceptance_arrival_fixture", "test_current_request_arrival.py")
W = fixture_module("acceptance_weather_fixture", "test_local_weather.py")


def local_tool(transport, operations):
    async def locate(_protected):
        operations.append("locate")
        return W.DEVICE

    def weather(*_):
        operations.append("fetch_weather")
        return W.WEATHER

    def radar(*_):
        operations.append("fetch_radar")
        return W.RADAR

    async def display(payload):
        await send_app_message(transport, {"type": "display", "display": payload})

    return build_local_weather_tool(locate=locate, fetch_weather=weather,
        fetch_radar=radar, push_display=display, is_protected=lambda: False)[1]


@pytest.mark.parametrize("text", [
    "Show weather for Exampleburg.",
    "Show me Exampleburg weather again.",
    "Do I need an umbrella today in Exampleburg?",
    "Is it going to rain today in Exampleburg?",
])
async def test_named_city_cannot_execute_device_weather_or_consume_a_display(text):
    owner, transport = A.fixture()
    frame = await A.user_context(owner, text, "synthetic-named-input")
    await A.bind_call(owner, frame, "named-call")
    operations = []
    params = A.Params("named-call")
    await adapt_to_pipecat("local_weather", local_tool(transport, operations),
        foreground_requests=owner)(params)
    assert operations == [], "An explicit named place must refuse before device/network lookup."
    assert not [m for m in transport.messages if m["type"] == "display"]
    assert "named" in params.results[-1].lower()


async def test_older_named_call_cannot_borrow_the_newer_local_turn_to_pass_the_guard():
    owner, transport = A.fixture()
    old = await A.user_context(owner, "Weather in Exampleburg", "synthetic-named-input")
    await A.bind_call(owner, old, "named-call")
    await A.user_context(owner, "Weather here", "synthetic-local-input")
    operations = []
    await adapt_to_pipecat("local_weather", local_tool(transport, operations),
        foreground_requests=owner)(A.Params("named-call"))
    assert operations == []
    assert not [m for m in transport.messages if m["type"] == "display"]


async def test_local_call_keeps_its_original_owner_after_new_named_turn():
    owner, transport = A.fixture()
    old = await A.user_context(owner, "Weather here", "synthetic-local-input")
    await A.bind_call(owner, old, "local-call")
    old_id = transport.messages[-1]["request_id"]
    await A.user_context(owner, "Weather in Exampleburg", "synthetic-named-input")
    operations = []
    await adapt_to_pipecat("local_weather", local_tool(transport, operations),
        foreground_requests=owner)(A.Params("local-call"))
    assert sorted(operations) == ["fetch_radar", "fetch_weather", "locate"]
    displays = [m["display"] for m in transport.messages if m["type"] == "display"]
    assert len(displays) == 1 and displays[0]["origin_request_id"] == old_id


@pytest.mark.parametrize("text", ["Weather here", "What's the weather?", "Show me current weather",
    "Weather for my location", "Weather for tomorrow", "The weather",
    "Is it going to rain?", "Do I need an umbrella?", "What’s the week look like?",
    "Do I need an umbrella today?", "What does the week look like weather-wise?",
    "Weather right now", "Weather for right now", "Weather for the week"])
def test_local_requests_keep_the_device_resolver(text):
    assert accepted_weather_intent(text) == WeatherIntent("local")


@pytest.mark.parametrize("text,place", [
    ("Show weather for Exampleburg.", "exampleburg"),
    ("Show me Exampleburg weather again.", "exampleburg"),
    ("Can you show me Metroville weather?", "metroville"),
    ("Weather in Exampleburg, South Carolina tomorrow", "exampleburg, south carolina"),
    ("Forecast for St. Louis", "st. louis"),
    ("Do I need an umbrella today in Exampleburg?", "exampleburg"),
    ("Is it going to rain today in Exampleburg?", "exampleburg"),
])
def test_named_requests_preserve_the_accepted_place(text, place):
    assert accepted_weather_intent(text) == WeatherIntent("named", place)


def test_weather_followups_use_only_the_previous_accepted_weather_target():
    first = accepted_weather_intent("Weather in Exampleburg")
    assert accepted_weather_intent("What about there?", first) == first
    assert accepted_weather_intent("And Metroville?", first) == WeatherIntent("named", "metroville")
    other = accepted_weather_intent("Show the roadmap", first)
    assert other.kind == "not_weather"
    assert accepted_weather_intent("What about there?", other).kind == "not_weather"
    assert accepted_weather_intent("Weather there").kind == "unclear"


@pytest.mark.parametrize("text", ["Weather in Exampleburg and Metroville", "Weather in " + "x" * 130,
    "Weather in " + "x" * 4096, "Weather in Exampleburg today and Metroville"])
def test_ambiguous_and_oversized_targets_do_not_grant_local_or_named_execution(text):
    intent = accepted_weather_intent(text)
    assert not intent.permits("weather:local:device:synthetic", "local_weather")
    assert not intent.permits("weather:named:exampleburg", "get_weather")


@pytest.mark.parametrize("subject,tool", [("weather:named:metroville", "get_weather"),
    ("weather:local:device:synthetic", "local_weather"), (None, "get_weather")])
async def test_named_intent_refuses_wrong_subject_before_native_cache_or_fetch(subject, tool):
    calls = []

    async def query(**kwargs):
        calls.append(kwargs)
        return {"status": "miss", "code": "no_matching_result"}

    token = current_weather_intent.set(WeatherIntent("named", "exampleburg"))
    try:
        reply = await WeatherReuseBridge(query, is_protected=lambda: False).lookup(
            subject_key=subject, tool=tool, days=7, units="imperial")
    finally:
        current_weather_intent.reset(token)
    assert reply.status == "refused" and reply.code == "invalid_request"
    assert calls == []


async def test_named_intent_allows_native_cache_query_for_the_requested_city():
    calls = []

    async def query(**kwargs):
        calls.append(kwargs)
        return {"status": "miss", "code": "no_matching_result"}

    token = current_weather_intent.set(WeatherIntent("named", "exampleburg"))
    try:
        reply = await WeatherReuseBridge(query, is_protected=lambda: False).lookup(
            subject_key="weather:named:exampleburg, south carolina", tool="get_weather",
            days=7, units="imperial")
    finally:
        current_weather_intent.reset(token)
    assert reply.status == "miss" and len(calls) == 1


def test_an_explicit_qualifier_cannot_be_changed_by_generated_tool_arguments():
    intent = accepted_weather_intent("Weather in Portland, Maine")
    assert intent.permits("weather:named:portland, maine", "get_weather")
    assert not intent.permits("weather:named:portland, oregon", "get_weather")
    assert not intent.permits("weather:named:portland, maine, oregon", "get_weather")
