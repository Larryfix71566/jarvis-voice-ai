"""T2.3 — current_location() and the additive `source` on
ambient_weather._resolve_location."""

from __future__ import annotations

import pytest

from jarvis import ambient_weather
from jarvis.status.location import current_location


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    ambient_weather._clear_cache_for_tests()
    for name in ("JARVIS_WEATHER_LAT", "JARVIS_WEATHER_LON", "JARVIS_WEATHER_LABEL"):
        monkeypatch.delenv(name, raising=False)
    yield
    ambient_weather._clear_cache_for_tests()


def _geo(url):
    assert url == ambient_weather.GEO_URL
    return {"status": "success", "lat": 34.07, "lon": -84.29, "city": "Alpharetta"}


def _no_fetch(url):
    raise AssertionError("no network expected")


def test_location_reports_source_env(monkeypatch):
    monkeypatch.setenv("JARVIS_WEATHER_LAT", "40.7")
    monkeypatch.setenv("JARVIS_WEATHER_LON", "-74.0")
    monkeypatch.setenv("JARVIS_WEATHER_LABEL", "Home")
    out = current_location(fetch=_no_fetch)
    assert out == {"ok": True, "lat": 40.7, "lon": -74.0, "label": "Home", "source": "env"}


def test_location_reports_source_device():
    ambient_weather.set_device_location(33.75, -84.39, "Atlanta")
    out = current_location(fetch=_no_fetch)
    assert out["ok"] is True
    assert out["source"] == "device"
    assert out["label"] == "Atlanta"
    assert isinstance(out["age_s"], int) and out["age_s"] >= 0


def test_location_reports_source_ip():
    out = current_location(fetch=_geo)
    assert out == {"ok": True, "lat": 34.07, "lon": -84.29, "label": "Alpharetta",
                   "source": "ip"}


def test_location_unavailable():
    def fail(url):
        raise OSError("offline")

    assert current_location(fetch=fail) == {"ok": False, "error": "no location available"}


def test_resolve_location_source_is_additive():
    loc = ambient_weather._resolve_location(_geo)
    assert {"lat", "lon", "label"} <= set(loc)
