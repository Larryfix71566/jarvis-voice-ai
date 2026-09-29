"""WS-15 PR 2: the weather card's structured view (jarvis/bot/weather_card.py).
Pure; no network."""

from __future__ import annotations

from jarvis.bot import weather_card as C

WEATHER = {
    "city": "Folly Beach", "source": "weather.gov", "units": "imperial",
    "lat": 32.6611, "lon": -79.928, "human": "In Folly Beach it's 82°F and Clear.",
    "current": {"temperature_f": 82, "temperature_c": 28, "condition": "Clear",
                "humidity_percent": 72, "wind": "E 10 mph", "wind_kph": None},
    "daily": [
        {"date": "This Afternoon", "max_f": 79, "min_f": 75, "max_c": 26, "min_c": 24,
         "precip_probability": 20, "condition": "Mostly Sunny"},
        {"date": "Saturday", "max_f": 78, "min_f": 70, "max_c": 26, "min_c": 21,
         "precip_probability": 60, "condition": "Showers And Thunderstorms"},
    ],
    "hourly": [{"start": "2026-09-29T15:00:00-04:00", "temp_f": 82, "temp_c": 28,
                "pop": 5, "condition": "Sunny"},
               {"start": "2026-09-29T00:00:00-04:00", "temp_f": 74, "temp_c": 23,
                "pop": None, "condition": "Clear"}],
    "alerts": [{"event": "Rip Current Statement", "headline": "Rip currents likely"}],
}
RAINVIEWER = {"tiles": ["https://tilecache.rainviewer.com/v2/radar/abc123/512/6/31/21/2/1_1.png"],
              "lat": 51.5, "lon": -0.12}


def test_view_is_display_ready_in_the_users_units():
    v = C.weather_view({"weather": WEATHER, "place": {"label": "Folly Beach, SC",
                                                     "source": "device", "approximate": False}})
    assert v["schema"] == 1
    assert v["place"] == {"label": "Folly Beach, SC", "lat": 32.6611, "lon": -79.928,
                          "source": "device", "approximate": False}
    assert v["now"] == {"temp": "82°", "condition": "Clear", "humidity": "72%",
                        "wind": "E 10 mph", "symbol": "sun.max.fill"}
    assert v["days"][0] == {"name": "This Afternoon", "high": "79°", "low": "75°",
                            "pop": "20%", "condition": "Mostly Sunny", "symbol": "cloud.sun.fill"}
    assert v["days"][1]["name"] == "Sat" and v["days"][1]["symbol"] == "cloud.bolt.rain.fill"
    assert [h["label"] for h in v["hourly"]] == ["3 PM", "12 AM"]
    assert v["hourly"][1]["pop"] is None
    assert v["alerts"] == [{"event": "Rip Current Statement", "headline": "Rip currents likely"}]
    assert v["summary"].startswith("In Folly Beach")
    assert v["attribution"] == "Forecast: National Weather Service"


def test_metric_units_use_celsius():
    v = C.weather_view({"weather": {**WEATHER, "units": "metric"}})
    assert v["now"]["temp"] == "28°" and v["days"][0]["high"] == "26°"


def test_named_place_defaults():
    v = C.weather_view({"weather": WEATHER})
    assert v["place"]["label"] == "Folly Beach" and v["place"]["source"] == "named"


def test_iem_radar_inside_the_lower_48():
    radar = C.radar_layers(32.66, -79.93, None)
    assert radar["provider"] == "iem" and radar["max_native_zoom"] == 8
    assert len(radar["frames"]) == 11
    assert radar["frames"][0] == {
        "label": "50 min ago",
        "template": "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/"
                    "nexrad-n0q-m50m-900913/{z}/{x}/{y}.png"}
    assert radar["frames"][-1]["label"] == "now"
    assert radar["frames"][-1]["template"].endswith("/nexrad-n0q-900913/{z}/{x}/{y}.png")


def test_rainviewer_template_outside_the_us():
    radar = C.radar_layers(51.5, -0.12, RAINVIEWER)
    assert radar == {
        "provider": "rainviewer", "max_native_zoom": 7,
        "frames": [{"label": "latest",
                    "template": "https://tilecache.rainviewer.com/v2/radar/abc123/256/{z}/{x}/{y}/2/1_1.png"}],
        "attribution": "Radar: RainViewer"}


def test_no_radar_outside_the_us_without_tiles():
    assert C.radar_layers(51.5, -0.12, None) is None
    assert C.radar_layers(None, None, {"tiles": ["not a tile url"]}) is None


def test_open_meteo_attribution_and_missing_weather():
    v = C.weather_view({"weather": {**WEATHER, "source": "open-meteo"}})
    assert v["attribution"] == "Forecast: Open-Meteo"
    assert C.weather_view({"radar": RAINVIEWER}) is None


def test_symbols():
    assert C.symbol_for("Chance Rain Showers") == "cloud.rain.fill"
    assert C.symbol_for("Partly Cloudy") == "cloud.sun.fill"
    assert C.symbol_for("Overcast") == "cloud.fill"
    assert C.symbol_for("Patchy Fog") == "cloud.fog.fill"
    assert C.symbol_for("") == "cloud.sun.fill"
