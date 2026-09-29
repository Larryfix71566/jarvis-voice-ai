"""WS-15 S3: local_weather — weather where the user is now, place resolved
in code (device, then IP, then unavailable), never from memory or a model.
Fake locator/fetchers only: no network, no device."""

from __future__ import annotations

import asyncio
import json

from jarvis.bot import weather_tool as W

WEATHER = {
    "city": "Folly Beach", "source": "weather.gov", "units": "imperial",
    "current": {"temperature_f": 75, "temperature_c": 24, "condition": "Clear",
                "humidity_percent": 68, "wind": "SE 8 mph", "wind_kph": None},
    "daily": [
        {"date": "This Afternoon", "max_f": 82, "min_f": 72, "max_c": 28, "min_c": 22,
         "precip_probability": 10, "condition": "Sunny"},
        {"date": "Wednesday", "max_f": 80, "min_f": 73, "max_c": 27, "min_c": 23,
         "precip_probability": 20, "condition": "Mostly Sunny"},
        {"date": "Thursday", "max_f": 79, "min_f": 71, "max_c": 26, "min_c": 22,
         "precip_probability": 60, "condition": "Showers And Thunderstorms"},
        {"date": "Friday", "max_f": 81, "min_f": 70, "max_c": 27, "min_c": 21,
         "precip_probability": None, "condition": "Chance Rain Showers"},
    ],
    "hourly": [], "alerts": [{"event": "Rip Current Statement"}], "human": "In Folly Beach it's 75°F.",
}
RADAR = {"city": "Folly Beach, United States", "lat": 32.66, "lon": -79.93, "ts": 1790690400,
         "tiles": ["https://t/%d.png" % i for i in range(9)],
         "basemap_tiles": ["https://b/%d.png" % i for i in range(9)]}
DEVICE = {"ok": True, "source": "device", "lat": 32.6611, "lon": -79.928, "accuracy_m": 35,
          "age_s": 0.4, "label": "Folly Beach, SC"}


def _tool(found=DEVICE, weather=WEATHER, radar=RADAR, protected=False, sink=None, calls=None):
    async def locate(protected_flag):
        if calls is not None:
            calls.append("locate")
        if isinstance(found, Exception):
            raise found
        return found

    def fw(lat, lon, label, days):
        if calls is not None:
            calls.append(("weather", lat, lon, label, days))
        return weather

    def fr(lat, lon, label):
        if calls is not None:
            calls.append(("radar", lat, lon, label))
        return radar

    async def push(payload):
        if sink is not None:
            sink.append(payload)

    schema, handler = W.build_local_weather_tool(
        locate=locate, push_display=push, fetch_weather=fw, fetch_radar=fr,
        is_protected=lambda: protected)
    return schema, handler


def _run(handler, args=None):
    return asyncio.run(handler(args or {}))


def test_schema_takes_no_place():
    schema, _ = _tool()
    params = schema["function"]["parameters"]
    assert params["properties"] == {} and params["required"] == []
    assert schema["function"]["name"] == "local_weather"


def test_device_fix_drives_the_lookup_and_names_the_place():
    calls, sink = [], []
    _, handler = _tool(calls=calls, sink=sink)
    text = _run(handler)
    assert ("weather", 32.6611, -79.928, "Folly Beach, SC", 7) in calls
    assert ("radar", 32.6611, -79.928, "Folly Beach, SC") in calls
    assert text.startswith("Weather for Folly Beach, SC (this device's location).")
    assert "approximately" not in text


def test_a_place_argument_is_ignored():
    calls = []
    _, handler = _tool(calls=calls)
    _run(handler, {"city": "Spartanburg, SC"})
    assert all("Spartanburg" not in str(c) for c in calls)


def test_summary_covers_now_today_week_alert_and_card():
    sink = []
    _, handler = _tool(sink=sink)
    text = _run(handler)
    assert "Active alert: Rip Current Statement." in text
    assert "Now 75°F, Clear, humidity 68%, wind SE 8 mph." in text
    assert "high 82°F" in text and "low 72°F" in text and "10% chance of rain" in text
    assert "Next 3 days: highs 79 to 81°F; rain or storms possible Thu, Fri." in text
    assert "weather card with radar was sent to the screen" in text
    assert "do not add any place" in text


def test_card_is_one_weather_report_payload_on_the_window_surface():
    sink = []
    _, handler = _tool(sink=sink)
    _run(handler)
    assert len(sink) == 1
    payload = sink[0]
    assert payload["surface"] == "window"
    assert payload["kind"] == "image"
    assert payload["title"] == "Weather — Folly Beach, SC"
    assert len(payload["images"]) == 9 and len(payload["basemap_images"]) == 9
    assert "**Alert: Rip Current Statement**" in payload["body"]


def test_ip_location_is_said_as_approximate():
    found = {"ok": True, "source": "ip", "lat": 32.78, "lon": -79.93, "label": "Charleston",
             "device_reason": "denied"}
    _, handler = _tool(found=found)
    text = _run(handler)
    assert "approximately Charleston (from the internet connection" in text


def test_low_accuracy_device_fix_is_approximate():
    found = {**DEVICE, "accuracy_m": 5000}
    _, handler = _tool(found=found)
    assert "approximately Folly Beach, SC (this device's location, low accuracy)" in _run(handler)


def test_no_location_asks_and_never_guesses():
    calls = []
    _, handler = _tool(found={"ok": False, "reason": "offline", "device_reason": "denied"}, calls=calls)
    text = _run(handler)
    assert "location isn't available" in text
    assert "Ask the user which place" in text and "Do not guess a place" in text
    assert calls == ["locate"]  # nothing fetched


def test_locator_crash_is_unavailable_not_raised():
    _, handler = _tool(found=RuntimeError("boom"))
    assert "location isn't available" in _run(handler)


def test_protected_turn_calls_nothing():
    calls, sink = [], []
    _, handler = _tool(protected=True, calls=calls, sink=sink)
    assert _run(handler) == W.PROTECTED_TURN_REFUSAL
    assert calls == [] and sink == []


def test_weather_error_is_reported_not_guessed():
    sink = []
    _, handler = _tool(weather={"error": "Weather forecast failed: ConnectError."}, sink=sink)
    text = _run(handler)
    assert text.startswith("local_weather failed: Weather forecast failed: ConnectError.")
    assert sink == []


def test_radar_failure_still_sends_the_forecast_card():
    sink = []
    _, handler = _tool(radar={"error": "Radar data failed: ConnectError."}, sink=sink)
    text = _run(handler)
    assert len(sink) == 1 and sink[0]["images"] == []
    assert "weather card without radar was sent" in text


def test_metric_units():
    weather = {**WEATHER, "units": "metric"}
    _, handler = _tool(weather=weather)
    text = _run(handler)
    assert "Now 24°C" in text and "high 28°C" in text


def test_short_day():
    assert W._short_day("Wednesday") == "Wed"
    assert W._short_day("2026-10-01") == "Thu"
    assert W._short_day("This Afternoon") == "This Afternoon"


def test_card_payload_is_json_safe():
    sink = []
    _, handler = _tool(sink=sink)
    _run(handler)
    json.dumps(sink[0])
