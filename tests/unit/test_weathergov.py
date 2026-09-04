"""Unit tests for jarvis/weathergov.py
(W1, MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md) — the shared
Weather.gov client used by both jarvis/ambient_weather.py and
mcp_servers/mcp_web/logic.py.

Most behavioral coverage of weathergov_current lives in
tests/unit/test_ambient_weather.py's TestWeatherGov class, exercised
through jarvis.ambient_weather.get_weather (which now calls straight
through to this module) — that class is the equality check proving the
2026-08-22 extraction changed nothing about the chip's payload. This file
covers what is NEW here: the "one implementation" guard and daily_forecast,
which ambient_weather.py never needed.
"""

from __future__ import annotations

import re
from pathlib import Path

from jarvis import weathergov as wg

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_weathergov_module_is_the_only_implementation():
    """W1: no OTHER module holds an api.weather.gov URL literal — every
    caller goes through jarvis/weathergov.py. Mirrors the shape of
    test_module_imports_nothing_that_executes (agent_skills) — grep the
    source tree rather than trust a docstring claim."""
    offenders = []
    for path in REPO_ROOT.rglob("*.py"):
        if path == REPO_ROOT / "jarvis" / "weathergov.py":
            continue
        # data/ holds self-edit worktrees and app-build clones — full
        # copies of this repo that legitimately contain weathergov.py.
        # They are gitignored scratch, not a second implementation.
        if any(seg in str(path) for seg in ("/.venv/", "/tests/", "/data/")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in re.finditer(r'["\']https://api\.weather\.gov[^"\']*["\']', text):
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {m.group(0)}")
    assert offenders == [], (
        "api.weather.gov URL literal found outside jarvis/weathergov.py:\n"
        + "\n".join(offenders)
    )


def _points(city: str = "Testville") -> dict:
    return {
        "properties": {
            "relativeLocation": {"properties": {"city": city}},
            "forecast": "https://api.weather.gov/gridpoints/X/1,2/forecast",
        }
    }


def _forecast(periods: list[dict]) -> dict:
    return {"properties": {"periods": periods}}


class TestDailyForecast:
    def test_pairs_day_and_night_periods(self):
        def fetch(url):
            if "gridpoints" in url:
                return _forecast([
                    {"name": "Today", "isDaytime": True, "temperature": 85,
                     "temperatureUnit": "F", "shortForecast": "Sunny"},
                    {"name": "Tonight", "isDaytime": False, "temperature": 60,
                     "temperatureUnit": "F", "shortForecast": "Clear"},
                ])
            return _points()

        r = wg.daily_forecast(35.0, -82.0, fetch, days=1)
        assert r is not None
        assert r["city"] == "Testville"
        assert len(r["days"]) == 1
        assert r["days"][0]["high_f"] == 85
        assert r["days"][0]["low_f"] == 60
        assert r["days"][0]["condition"] == "Sunny"

    def test_converts_celsius_periods(self):
        def fetch(url):
            if "gridpoints" in url:
                return _forecast([
                    {"name": "Today", "isDaytime": True, "temperature": 20,
                     "temperatureUnit": "C", "shortForecast": "Mild"},
                ])
            return _points()

        r = wg.daily_forecast(35.0, -82.0, fetch, days=1)
        assert r["days"][0]["high_f"] == 68

    def test_multiple_days(self):
        periods = []
        for i in range(6):
            periods.append({
                "name": f"Day{i}", "isDaytime": i % 2 == 0,
                "temperature": 70 + i, "temperatureUnit": "F",
                "shortForecast": "x",
            })

        def fetch(url):
            if "gridpoints" in url:
                return _forecast(periods)
            return _points()

        r = wg.daily_forecast(35.0, -82.0, fetch, days=3)
        assert len(r["days"]) == 3

    def test_missing_forecast_url_returns_none(self):
        def fetch(url):
            return {"properties": {}}

        assert wg.daily_forecast(35.0, -82.0, fetch) is None

    def test_empty_periods_returns_none(self):
        def fetch(url):
            if "gridpoints" in url:
                return _forecast([])
            return _points()

        assert wg.daily_forecast(35.0, -82.0, fetch) is None

    def test_network_error_returns_none(self):
        def fetch(url):
            raise RuntimeError("boom")

        assert wg.daily_forecast(35.0, -82.0, fetch) is None


class TestFetchHeaders:
    def test_weathergov_url_gets_user_agent(self):
        headers = wg.fetch_headers("https://api.weather.gov/points/1,2")
        assert headers.get("User-Agent") == wg.WEATHERGOV_UA

    def test_other_url_gets_no_header(self):
        assert wg.fetch_headers("https://api.open-meteo.com/v1/forecast") == {}
