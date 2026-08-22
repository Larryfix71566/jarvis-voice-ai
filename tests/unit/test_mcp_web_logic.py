"""Unit tests for mcp_servers/mcp_web/logic.py (plan Phase 1 Tests)."""

import httpx
import pytest

from mcp_servers.mcp_web import logic


class FakeResponse:
    def __init__(self, payload, status=200, url="https://x"):
        self._payload = payload
        self.status_code = status
        self._url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", self._url)
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("error", request=req, response=resp)

    def json(self):
        return self._payload


class TestWebSearch:
    def test_happy_path_maps_results(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        payload = {
            "answer": "Short answer.",
            "results": [
                {"title": "A", "url": "https://a", "content": "x" * 400},
                {"title": "B", "url": "https://b", "content": "short"},
            ],
        }
        monkeypatch.setattr(logic.httpx, "post", lambda *a, **k: FakeResponse(payload))
        result = logic.web_search("query", max_results=2)
        assert result["answer"] == "Short answer."
        assert [r["title"] for r in result["results"]] == ["A", "B"]
        assert len(result["results"][0]["snippet"]) == 300

    def test_no_key_degraded_mode(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        result = logic.web_search("anything")
        assert result["error"] == "Web search is unavailable (no API key configured)."

    def test_empty_query_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        assert "error" in logic.web_search("  ")

    def test_http_status_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        monkeypatch.setattr(logic.httpx, "post", lambda *a, **k: FakeResponse({}, 500))
        assert logic.web_search("q")["error"] == "Web search failed (HTTP 500)."

    def test_network_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def boom(*a, **k):
            raise httpx.ConnectError("down")

        monkeypatch.setattr(logic.httpx, "post", boom)
        assert logic.web_search("q")["error"] == "Web search failed: ConnectError."


def _sse(payload: dict) -> str:
    import json as _json

    return "event: message\ndata: " + _json.dumps(payload) + "\n\n"


class FakeMCPSearchResponse(FakeResponse):
    """FakeResponse with an SSE .text body for the hosted MCP endpoint."""

    def __init__(self, inner_results, status=200):
        super().__init__({}, status)
        inner = {"results": inner_results, "answer": "MCP answer."}
        import json as _json

        rpc = {"jsonrpc": "2.0", "id": 1,
               "result": {"content": [{"type": "text", "text": _json.dumps(inner)}]}}
        self.text = _sse(rpc)


class TestWebSearchMCPTransport:
    """D-011: hosted-MCP-first transport with REST fallback."""

    def test_mcp_primary_used_and_mapped(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            assert "mcp.tavily.com" in url  # REST must not be needed
            return FakeMCPSearchResponse([
                {"title": "A", "url": "https://a", "content": "x" * 400},
            ])

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        result = logic.web_search("query", max_results=2)
        assert len(calls) == 1
        assert result["answer"] == "MCP answer."
        assert result["results"][0]["title"] == "A"
        assert len(result["results"][0]["snippet"]) == 300

    def test_mcp_transport_error_falls_back_to_rest(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                raise httpx.ConnectError("waf blocked")
            return FakeResponse({"answer": "REST answer.", "results": []})

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["answer"] == "REST answer."

    def test_mcp_jsonrpc_error_falls_back_to_rest(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        class ErrorBody(FakeResponse):
            text = _sse({"jsonrpc": "2.0", "id": 1,
                         "error": {"code": -32601, "message": "no such tool"}})

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                return ErrorBody({})
            return FakeResponse({"answer": "REST answer.", "results": []})

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["answer"] == "REST answer."

    def test_both_transports_down_reports_rest_error(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

        def fake_post(url, **kwargs):
            if "mcp.tavily.com" in url:
                raise httpx.ConnectError("waf blocked")
            return FakeResponse({}, 403)

        monkeypatch.setattr(logic.httpx, "post", fake_post)
        assert logic.web_search("q")["error"] == "Web search failed (HTTP 403)."


GEO_PAYLOAD = {
    "results": [{
        "name": "Tokyo", "country": "Japan",
        "latitude": 35.69, "longitude": 139.69,
    }]
}
FORECAST_PAYLOAD = {
    "current": {
        "temperature_2m": 30.4, "relative_humidity_2m": 66,
        "weather_code": 2, "wind_speed_10m": 9.1,
    },
    "daily": {
        "time": ["2026-08-04", "2026-08-05"],
        "temperature_2m_max": [33.0, 32.0],
        "temperature_2m_min": [25.0, 24.5],
        "precipitation_probability_max": [20, 55],
        "weather_code": [2, 61],
    },
}


def _fake_get_factory(geo_payload, forecast_payload):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse(geo_payload)
        return FakeResponse(forecast_payload)
    return fake_get


class TestGetWeather:
    """Note: none of these mock the Weather.gov points/stations/forecast
    URLs, so _wg_current gracefully returns None (weathergov_current's own
    try/except swallows the resulting malformed-payload parse) and every
    call here exercises the Open-Meteo FALLBACK path — the same path this
    class always tested, now with W2's added °F fields and W3's `units`
    selection on top. TestGetWeatherUnits and TestGetWeatherWeatherGov
    below cover the primary paths this class doesn't reach."""

    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("tokyo", days=2)
        assert result["city"] == "Tokyo, Japan"
        assert result["source"] == "open-meteo"
        assert result["current"]["condition"] == "partly cloudy"
        assert result["current"]["temperature_c"] == 30.4
        assert len(result["daily"]) == 2
        assert result["daily"][1]["condition"] == "slight rain"
        assert "Tokyo, Japan" in result["human"]

    def test_defaults_to_fahrenheit_primary(self, monkeypatch):
        monkeypatch.delenv("JARVIS_UNITS", raising=False)
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("tokyo", days=2)
        assert result["units"] == "imperial"
        assert "°F" in result["human"]
        assert "°C" not in result["human"]

    def test_honors_metric_setting(self, monkeypatch):
        """W3's falsifiable test at the tool layer: the setting must
        actually change the output, or it is decorative."""
        monkeypatch.setenv("JARVIS_UNITS", "metric")
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("tokyo", days=2)
        assert result["units"] == "metric"
        assert "30.4°C" in result["human"]
        assert "°F" not in result["human"]

    def test_returns_both_unit_sets_regardless_of_setting(self, monkeypatch):
        """W2: the payload shape never varies with the units setting."""
        for units in ("imperial", "metric"):
            monkeypatch.setenv("JARVIS_UNITS", units)
            monkeypatch.setattr(
                logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
            )
            result = logic.get_weather("tokyo", days=2)
            assert result["current"]["temperature_f"] is not None
            assert result["current"]["temperature_c"] is not None
            for d in result["daily"]:
                assert d["max_f"] is not None and d["max_c"] is not None
                assert d["min_f"] is not None and d["min_c"] is not None

    def test_unknown_units_env_value_defaults_to_imperial(self, monkeypatch):
        monkeypatch.setenv("JARVIS_UNITS", "furlongs")
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("tokyo")
        assert result["units"] == "imperial"

    def test_city_not_found(self, monkeypatch):
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory({"results": []}, FORECAST_PAYLOAD)
        )
        assert "couldn't find" in logic.get_weather("Atlantis")["error"]

    def test_empty_city_error(self):
        assert "error" in logic.get_weather("  ")

    def test_geocode_network_error(self, monkeypatch):
        def boom(*a, **k):
            raise httpx.ConnectError("down")
        monkeypatch.setattr(logic.httpx, "get", boom)
        assert logic.get_weather("Tokyo")["error"].startswith("Weather lookup failed")

    def test_forecast_network_error(self, monkeypatch):
        def fake_get(url, params=None, timeout=None):
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            raise httpx.ConnectError("down")
        monkeypatch.setattr(logic.httpx, "get", fake_get)
        assert logic.get_weather("Tokyo")["error"].startswith("Weather forecast failed")

    def test_unknown_wmo_code(self, monkeypatch):
        payload = dict(FORECAST_PAYLOAD)
        payload["current"] = dict(FORECAST_PAYLOAD["current"], weather_code=999)
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, payload)
        )
        result = logic.get_weather("Tokyo")
        assert result["current"]["condition"] == "unknown conditions"

    def test_days_clamped(self, monkeypatch):
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured.update(params or {})
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            return FakeResponse(FORECAST_PAYLOAD)

        monkeypatch.setattr(logic.httpx, "get", fake_get)
        logic.get_weather("Tokyo", days=9)
        assert captured["forecast_days"] == 3


WG_POINT_PAYLOAD = {
    "properties": {
        "relativeLocation": {"properties": {"city": "Spartanburg"}},
        "observationStations": "https://api.weather.gov/gridpoints/GSP/1,2/stations",
        "forecast": "https://api.weather.gov/gridpoints/GSP/1,2/forecast",
    }
}
WG_STATIONS_PAYLOAD = {
    "features": [{"properties": {"stationIdentifier": "KSPA"}}],
}
WG_OBS_PAYLOAD = {
    "properties": {
        "temperature": {"value": 31.1, "unitCode": "wmoUnit:degC"},
        "textDescription": "Partly Cloudy",
    }
}
WG_FORECAST_PAYLOAD = {
    "properties": {
        "periods": [
            {"name": "Today", "isDaytime": True, "temperature": 91,
             "temperatureUnit": "F", "shortForecast": "Sunny"},
            {"name": "Tonight", "isDaytime": False, "temperature": 68,
             "temperatureUnit": "F", "shortForecast": "Clear"},
        ]
    }
}


def _fake_get_weathergov_primary(geo_payload=GEO_PAYLOAD):
    def fake_get(url, params=None, timeout=None, headers=None):
        if "geocoding" in url:
            return FakeResponse(geo_payload)
        if "stations" in url and "observations" not in url:
            return FakeResponse(WG_STATIONS_PAYLOAD)
        if "observations/latest" in url:
            return FakeResponse(WG_OBS_PAYLOAD)
        if "gridpoints" in url and "forecast" in url:
            return FakeResponse(WG_FORECAST_PAYLOAD)
        if "api.weather.gov/points" in url:
            return FakeResponse(WG_POINT_PAYLOAD)
        raise AssertionError(f"unexpected URL in weathergov-primary fake: {url}")
    return fake_get


class TestGetWeatherWeatherGov:
    """W1/W4: the Weather.gov-PRIMARY path, with all three of its URLs
    mocked so weathergov_current actually succeeds (contrast with
    TestGetWeather above, where the absence of these mocks exercises the
    fallback instead)."""

    def test_weathergov_primary_used_when_available(self, monkeypatch):
        monkeypatch.delenv("JARVIS_UNITS", raising=False)
        monkeypatch.setattr(logic.httpx, "get", _fake_get_weathergov_primary())
        result = logic.get_weather("Spartanburg", days=1)
        assert result["source"] == "weather.gov"
        assert result["current"]["temperature_f"] == 88  # 31.1C converted
        assert result["current"]["condition"] == "Partly Cloudy"
        assert result["city"] == "Spartanburg"

    def test_weathergov_daily_forecast_converted_both_ways(self, monkeypatch):
        monkeypatch.setattr(logic.httpx, "get", _fake_get_weathergov_primary())
        result = logic.get_weather("Spartanburg", days=1)
        assert len(result["daily"]) == 1
        assert result["daily"][0]["max_f"] == 91
        assert result["daily"][0]["min_f"] == 68
        assert result["daily"][0]["max_c"] is not None
        assert result["daily"][0]["min_c"] is not None

    def test_source_label_is_never_plain_weather_gov_for_forecast_fallback(self, monkeypatch):
        """W4's mechanical guard, extended to the tool layer: a period
        fallback (no station reporting) is labelled weather.gov-forecast,
        never weather.gov, mirroring the ambient chip's own guard."""
        def fake_get(url, params=None, timeout=None, headers=None):
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            if "stations" in url and "observations" not in url:
                return FakeResponse({"features": []})  # no stations
            if "gridpoints" in url and "forecast" in url:
                return FakeResponse(WG_FORECAST_PAYLOAD)
            if "api.weather.gov/points" in url:
                return FakeResponse(WG_POINT_PAYLOAD)
            raise AssertionError(f"unexpected URL: {url}")

        monkeypatch.setattr(logic.httpx, "get", fake_get)
        result = logic.get_weather("Spartanburg", days=1)
        assert result["source"] == "weather.gov-forecast"
        assert result["source"] != "weather.gov"

    def test_weathergov_current_missing_falls_back_to_open_meteo(self, monkeypatch):
        """Outside the US (or any Weather.gov failure): falls back
        cleanly, source says open-meteo."""
        def fake_get(url, params=None, timeout=None, headers=None):
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            if "api.weather.gov" in url:
                raise httpx.ConnectError("404-like failure")
            return FakeResponse(FORECAST_PAYLOAD)

        monkeypatch.setattr(logic.httpx, "get", fake_get)
        result = logic.get_weather("Tokyo", days=1)
        assert result["source"] == "open-meteo"

    def test_falls_back_to_open_meteo_in_fahrenheit(self, monkeypatch):
        """W4/W2: the Open-Meteo FALLBACK path also carries a correctly
        converted °F figure, not just the °C it fetches natively —
        30.4°C -> 86.7°F exactly."""
        monkeypatch.delenv("JARVIS_UNITS", raising=False)
        monkeypatch.setattr(
            logic.httpx, "get", _fake_get_factory(GEO_PAYLOAD, FORECAST_PAYLOAD)
        )
        result = logic.get_weather("Tokyo", days=1)
        assert result["source"] == "open-meteo"
        assert result["current"]["temperature_c"] == 30.4
        assert result["current"]["temperature_f"] == 86.7


RAINVIEWER_PAYLOAD = {
    "host": "https://tilecache.rainviewer.com",
    "radar": {
        "past": [
            {"time": 1754899200, "path": "/v2/radar/nowcast_abc111"},
            {"time": 1754900000, "path": "/v2/radar/nowcast_abc222"},
        ]
    },
}

# G1: an older/unexpected RainViewer shape with no `path` field at all —
# exercises the fallback to the constructed-ts form.
RAINVIEWER_PAYLOAD_NO_PATH = {
    "host": "https://tilecache.rainviewer.com",
    "radar": {"past": [{"time": 1754899200}, {"time": 1754900000}]},
}


def _fake_radar_get(url, params=None, timeout=None):
    if "geocoding" in url:
        return FakeResponse(GEO_PAYLOAD)
    return FakeResponse(RAINVIEWER_PAYLOAD)


def _fake_radar_get_no_path(url, params=None, timeout=None):
    if "geocoding" in url:
        return FakeResponse(GEO_PAYLOAD)
    return FakeResponse(RAINVIEWER_PAYLOAD_NO_PATH)


class TestRadarTileGrid:
    """Slippy-map math: 3×3 grid around the containing tile."""

    def test_nine_tiles_mid_latitude(self):
        tiles = logic.radar_tile_grid(35.69, 139.69)
        assert len(tiles) == 9

    def test_center_tile_correct_at_origin(self):
        tiles = logic.radar_tile_grid(0.0, 0.0, zoom=6)
        n = 2 ** 6
        assert (n // 2, n // 2) in tiles  # equator/prime meridian tile

    def test_row_major_order(self):
        tiles = logic.radar_tile_grid(35.69, 139.69)
        ys = [y for _, y in tiles]
        assert ys == sorted(ys)
        # first three tiles share the top row
        assert len({y for _, y in tiles[:3]}) == 1

    def test_antimeridian_wraps(self):
        tiles = logic.radar_tile_grid(0.0, 179.99, zoom=6)
        xs = {x for x, _ in tiles}
        assert 0 in xs  # wrapped past x=63 to x=0

    def test_polar_rows_dropped(self):
        tiles = logic.radar_tile_grid(85.0, 0.0, zoom=6)
        assert all(0 <= y < 2 ** 6 for _, y in tiles)
        assert len(tiles) == 6  # top ring row is off the map

    def test_near_pole_no_tiles(self):
        # Past the Mercator limit nothing renders — grid is empty, never invalid.
        tiles = logic.radar_tile_grid(89.9, 0.0, zoom=6)
        assert tiles == []


class TestGetWeatherRadar:
    def test_happy_path(self, monkeypatch):
        monkeypatch.setattr(logic.httpx, "get", _fake_radar_get)
        result = logic.get_weather_radar("tokyo")
        assert result["city"] == "Tokyo, Japan"
        assert result["ts"] == 1754900000  # latest past frame, display stamp only
        assert len(result["tiles"]) == 9
        assert all(
            t.startswith("https://tilecache.rainviewer.com/v2/radar/nowcast_abc222/512/6/")
            for t in result["tiles"]
        )
        assert all(t.endswith("/2/1_1.png") for t in result["tiles"])

    def test_radar_uses_api_path_not_constructed_ts(self, monkeypatch):
        """G1: RainViewer moved to hashed `path`-based tile URLs; a URL
        built from the raw `time` value 410s. Tiles must come from
        frame["path"], and `time` must appear only as `ts`, never inside
        a tile URL."""
        monkeypatch.setattr(logic.httpx, "get", _fake_radar_get)
        result = logic.get_weather_radar("tokyo")
        assert all("/v2/radar/1754900000/" not in t for t in result["tiles"])
        assert all("nowcast_abc222" in t for t in result["tiles"])

    def test_radar_missing_path_falls_back_to_constructed(self, monkeypatch):
        """G1: if a frame lacks `path` (older/unexpected API shape), fall
        back to the old ts-constructed URL rather than erroring."""
        monkeypatch.setattr(logic.httpx, "get", _fake_radar_get_no_path)
        result = logic.get_weather_radar("tokyo")
        assert "error" not in result
        assert len(result["tiles"]) == 9
        assert all(
            t.startswith("https://tilecache.rainviewer.com/v2/radar/1754900000/512/6/")
            for t in result["tiles"]
        )

    def test_basemap_tiles_same_coords_as_radar_tiles(self, monkeypatch):
        """W6: the basemap must use the SAME z/x/y as the radar overlay,
        never recomputed, or the two layers can desync."""
        monkeypatch.setattr(logic.httpx, "get", _fake_radar_get)
        result = logic.get_weather_radar("tokyo")
        assert len(result["basemap_tiles"]) == 9

        def _xy(url: str) -> tuple[str, str]:
            # .../{z}/{x}/{y}.png or .../{z}/{x}/{y}/2/1_1.png
            parts = url.rstrip("/").split("/")
            if parts[-1].endswith(".png") and "_" not in parts[-1]:
                z, x, y_png = parts[-3], parts[-2], parts[-1]
                y = y_png[: -len(".png")]
            else:
                y = parts[-3]
                x = parts[-4]
            return x, y

        radar_coords = {_xy(t) for t in result["tiles"]}
        basemap_coords = {_xy(t) for t in result["basemap_tiles"]}
        assert radar_coords == basemap_coords

    def test_basemap_tiles_are_keyless_carto(self, monkeypatch):
        monkeypatch.setattr(logic.httpx, "get", _fake_radar_get)
        result = logic.get_weather_radar("tokyo")
        assert all("basemaps.cartocdn.com/dark_all" in t for t in result["basemap_tiles"])
        assert all("key" not in t.lower() for t in result["basemap_tiles"])

    def test_empty_city_error(self):
        assert "error" in logic.get_weather_radar("  ")

    def test_city_not_found(self, monkeypatch):
        monkeypatch.setattr(
            logic.httpx, "get",
            _fake_get_factory({"results": []}, RAINVIEWER_PAYLOAD),
        )
        assert "couldn't find" in logic.get_weather_radar("Atlantis")["error"]

    def test_rainviewer_failure(self, monkeypatch):
        def fake_get(url, params=None, timeout=None):
            if "geocoding" in url:
                return FakeResponse(GEO_PAYLOAD)
            raise httpx.ConnectError("down")
        monkeypatch.setattr(logic.httpx, "get", fake_get)
        assert logic.get_weather_radar("Tokyo")["error"].startswith("Radar data failed")
