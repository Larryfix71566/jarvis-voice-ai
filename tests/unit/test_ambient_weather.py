"""Unit tests for jarvis/ambient_weather.py (Larry 2026-08-18).

All network access is injected via `fetch` — no real HTTP in this suite.
"""

from __future__ import annotations

import pytest

from jarvis import ambient_weather as aw


GEO_OK = {"status": "success", "lat": 33.9, "lon": -84.5, "city": "Marietta"}
FORECAST_OK = {"current": {"temperature_2m": 87.3, "weather_code": 2}}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    aw._clear_cache_for_tests()
    monkeypatch.delenv("JARVIS_AMBIENT_WEATHER_ENABLED", raising=False)
    monkeypatch.delenv("JARVIS_WEATHER_LAT", raising=False)
    monkeypatch.delenv("JARVIS_WEATHER_LON", raising=False)
    monkeypatch.delenv("JARVIS_WEATHER_LABEL", raising=False)
    yield
    aw._clear_cache_for_tests()


def _fetch_for(geo=GEO_OK, forecast=FORECAST_OK, calls=None):
    def fetch(url: str):
        if calls is not None:
            calls.append(url)
        if "ip-api.com" in url:
            return geo
        return forecast

    return fetch


class TestGetWeather:
    def test_happy_path_geo_ip(self):
        result = aw.get_weather(fetch=_fetch_for())
        assert result is not None
        assert result["summary"] == "Partly cloudy"
        assert result["temp_f"] == 87
        assert result["location"] == "Marietta"
        assert isinstance(result["at"], int)

    def test_env_override_skips_geo_ip(self, monkeypatch):
        monkeypatch.setenv("JARVIS_WEATHER_LAT", "40.7")
        monkeypatch.setenv("JARVIS_WEATHER_LON", "-74.0")
        monkeypatch.setenv("JARVIS_WEATHER_LABEL", "Home")
        calls: list[str] = []
        result = aw.get_weather(fetch=_fetch_for(calls=calls))
        assert result is not None
        assert result["location"] == "Home"
        assert all("ip-api.com" not in u for u in calls)
        assert any("latitude=40.7" in u for u in calls)

    def test_malformed_env_override_falls_back_to_geo_ip(self, monkeypatch):
        monkeypatch.setenv("JARVIS_WEATHER_LAT", "not-a-number")
        monkeypatch.setenv("JARVIS_WEATHER_LON", "-74.0")
        result = aw.get_weather(fetch=_fetch_for())
        assert result is not None
        assert result["location"] == "Marietta"

    def test_kill_switch(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AMBIENT_WEATHER_ENABLED", "false")
        calls: list[str] = []
        assert aw.get_weather(fetch=_fetch_for(calls=calls)) is None
        assert calls == []

    def test_geo_failure_returns_none(self):
        assert aw.get_weather(fetch=_fetch_for(geo={"status": "fail"})) is None

    def test_fetch_exception_returns_none_never_raises(self):
        def broken(url: str):
            raise RuntimeError("network down")

        assert aw.get_weather(fetch=broken) is None

    def test_missing_temperature_returns_none(self):
        assert aw.get_weather(fetch=_fetch_for(forecast={"current": {}})) is None

    def test_unknown_wmo_code_degrades_to_generic_label(self):
        result = aw.get_weather(
            fetch=_fetch_for(forecast={"current": {"temperature_2m": 60.0, "weather_code": 42}})
        )
        assert result is not None
        assert result["summary"] == "Weather"

    def test_result_is_cached_within_ttl(self):
        calls: list[str] = []
        fetch = _fetch_for(calls=calls)
        first = aw.get_weather(fetch=fetch)
        n = len(calls)
        second = aw.get_weather(fetch=fetch)
        assert second == first
        assert len(calls) == n  # no new upstream calls

    def test_device_location_beats_geo_ip(self):
        calls: list[str] = []
        aw.set_device_location(40.71, -74.01, "Brooklyn")
        result = aw.get_weather(fetch=_fetch_for(calls=calls))
        assert result is not None
        assert result["location"] == "Brooklyn"
        assert all("ip-api.com" not in u for u in calls)
        assert any("latitude=40.71" in u for u in calls)

    def test_env_override_beats_device_location(self, monkeypatch):
        monkeypatch.setenv("JARVIS_WEATHER_LAT", "10.0")
        monkeypatch.setenv("JARVIS_WEATHER_LON", "20.0")
        monkeypatch.setenv("JARVIS_WEATHER_LABEL", "Pinned")
        aw.set_device_location(40.71, -74.01, "Brooklyn")
        result = aw.get_weather(fetch=_fetch_for())
        assert result is not None
        assert result["location"] == "Pinned"

    def test_stale_device_location_falls_back_to_geo_ip(self, monkeypatch):
        aw.set_device_location(40.71, -74.01, "Brooklyn")
        # Age it past the max: monotonic() moves forward, so rewind the
        # recorded timestamp instead of sleeping.
        aw._device_location["at"] -= aw.DEVICE_LOCATION_MAX_AGE_S + 1
        assert aw.get_device_location() is None
        result = aw.get_weather(fetch=_fetch_for())
        assert result is not None
        assert result["location"] == "Marietta"

    def test_moving_invalidates_the_weather_cache(self):
        calls: list[str] = []
        fetch = _fetch_for(calls=calls)
        aw.set_device_location(40.71, -74.01, "Brooklyn")
        aw.get_weather(fetch=fetch)
        n = len(calls)
        # A trivial jitter must NOT refetch...
        aw.set_device_location(40.711, -74.011, "Brooklyn")
        aw.get_weather(fetch=fetch)
        assert len(calls) == n
        # ...but a real move must.
        aw.set_device_location(33.9, -84.5, "Marietta")
        aw.get_weather(fetch=fetch)
        assert len(calls) > n

    def test_failure_is_cached_too(self):
        calls: list[str] = []

        def broken(url: str):
            calls.append(url)
            raise RuntimeError("down")

        assert aw.get_weather(fetch=broken) is None
        n = len(calls)
        assert aw.get_weather(fetch=broken) is None
        assert len(calls) == n  # a dead network is not re-hammered per poll


# --- Weather.gov primary, Open-Meteo fallback (Larry 2026-08-18) ---------

WX_POINT = {
    "properties": {
        "forecast": "https://api.weather.gov/gridpoints/GSP/50,80/forecast",
        "relativeLocation": {"properties": {"city": "Spartanburg", "state": "SC"}},
    }
}
WX_FORECAST = {
    "properties": {
        "periods": [
            {"name": "This Afternoon", "temperature": 88,
             "temperatureUnit": "F", "shortForecast": "Partly Sunny"}
        ]
    }
}


def _wx_fetch(point=WX_POINT, forecast=WX_FORECAST, calls=None):
    def fetch(url: str):
        if calls is not None:
            calls.append(url)
        if "ip-api.com" in url:
            return GEO_OK
        if "api.weather.gov/points" in url:
            return point
        if "gridpoints" in url:
            return forecast
        return FORECAST_OK  # open-meteo
    return fetch


class TestWeatherGov:
    def test_weathergov_is_preferred(self):
        calls: list[str] = []
        r = aw.get_weather(fetch=_wx_fetch(calls=calls))
        assert r is not None
        assert r["source"] == "weather.gov"
        assert r["summary"] == "Partly Sunny"       # a phrase, not a WMO code
        assert r["temp_f"] == 88
        assert r["location"] == "Spartanburg"        # city comes free
        assert all("open-meteo" not in u for u in calls)

    def test_falls_back_to_open_meteo_outside_the_us(self):
        """Weather.gov 404s outside the US — Open-Meteo stays as the
        global fallback rather than being removed."""
        def fetch(url: str):
            if "ip-api.com" in url:
                return GEO_OK
            if "weather.gov" in url:
                raise RuntimeError("404 not found")
            return FORECAST_OK
        r = aw.get_weather(fetch=fetch)
        assert r is not None
        assert r["source"] == "open-meteo"
        assert r["temp_f"] == 87

    def test_celsius_from_weathergov_is_converted(self):
        forecast = {"properties": {"periods": [
            {"temperature": 20, "temperatureUnit": "C", "shortForecast": "Clear"}]}}
        r = aw.get_weather(fetch=_wx_fetch(forecast=forecast))
        assert r["temp_f"] == 68

    def test_missing_forecast_url_falls_back(self):
        r = aw.get_weather(fetch=_wx_fetch(point={"properties": {}}))
        assert r["source"] == "open-meteo"

    def test_empty_periods_falls_back(self):
        r = aw.get_weather(fetch=_wx_fetch(forecast={"properties": {"periods": []}}))
        assert r["source"] == "open-meteo"

    def test_weathergov_city_beats_the_ip_guess(self):
        """The IP label is only used when Weather.gov gives no city."""
        point = {"properties": {
            "forecast": "https://api.weather.gov/gridpoints/x/1,2/forecast",
            "relativeLocation": {"properties": {}}}}
        r = aw.get_weather(fetch=_wx_fetch(point=point))
        assert r["location"] == "Marietta"  # falls back to the geo label
