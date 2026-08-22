"""Shared Weather.gov client — the ONE implementation, reused by BOTH the
ambient chip (jarvis/ambient_weather.py) and the mcp-web weather tool
(mcp_servers/mcp_web/logic.py).

W1 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md, 2026-08-22): before this
module existed, ambient_weather.py had its own Weather.gov client (fixed
2026-08-18, verified live against Larry's machine) and mcp_web/logic.py had
none at all — it used Open-Meteo exclusively and returned Celsius. That
duplication (or rather, the absence of a shared one) is exactly the "one
implementation, not two" failure this codebase repeatedly guards against
elsewhere (classify_tool_result, model_key_probe, load_model_registry). This
module is the extraction: every function here is moved VERBATIM out of
ambient_weather.py, not rewritten, so a behavioral regression cannot hide
behind a rewording — ambient_weather.py's own tests
(tests/unit/test_ambient_weather.py) are the equality check that this
extraction changed nothing about the chip's payload.

Design (unchanged from the original): sync functions, plain dicts out,
short httpx timeouts, every network failure degrades to None/an explicit
fallback — never raises. Weather.gov gives OBSERVATIONS, not forecast
periods, and the two are never allowed to share a `source` label: reading
`properties.forecast`'s `periods[0].temperature` is a FORECAST PERIOD, not
an observation, and after sunset `periods[0]` is "Tonight" — its
temperature is the overnight LOW. A 2026-08-18 live bug (chip read 69°F,
macOS widget read 82°F, same city, same moment) is why `source` distinguishes
`"weather.gov"` (a real observation) from `"weather.gov-forecast"` (the
period fallback) and why that label is treated as a mechanical guard, not
decoration.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

# Weather.gov asks every client to identify itself; an anonymous request
# can be rejected. This is the documented contact-info form.
WEATHERGOV_UA = "(Mortimer personal assistant, github.com/Larryfix71566/jarvis-voice-ai)"
WEATHERGOV_POINTS_URL = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
WEATHERGOV_OBSERVATION_URL = (
    "https://api.weather.gov/stations/{station}/observations/latest"
)
# How many nearby stations to try before giving up on an observation.
# The nearest station is often a small airport that reports irregularly,
# so one attempt is not enough; the list is ordered by distance, so a few
# attempts stay geographically honest while tolerating a quiet station.
STATION_ATTEMPTS = 3


def fetch_headers(url: str) -> dict[str, str]:
    """Weather.gov wants a User-Agent identifying the client; other hosts
    don't need it. Shared so both callers (ambient_weather's httpx.get and
    mcp_web's httpx.get) send the identical header on the identical
    condition."""
    return {"User-Agent": WEATHERGOV_UA} if "weather.gov" in url else {}


def _observation_temp_f(obs: Any) -> Optional[tuple[float, str]]:
    """(°F, conditions) from one /observations/latest payload, or None.

    Pure. Split out because the null case is the common one, not the edge
    case: a station that is offline, or reporting only wind, returns
    `temperature.value: null` and must be skipped rather than treated as
    zero degrees.
    """
    props = (obs or {}).get("properties") or {}
    temp = (props.get("temperature") or {})
    value = temp.get("value")
    if value is None:
        return None
    unit = str(temp.get("unitCode") or "")
    # Observations report Celsius (`wmoUnit:degC`) — unlike the forecast
    # endpoint, which reports Fahrenheit for US offices. Converting on the
    # wrong assumption here is a 30-degree error, so read the unit.
    fahrenheit = float(value) if "degF" in unit else float(value) * 9 / 5 + 32
    return fahrenheit, str(props.get("textDescription") or "").strip()


def weathergov_current(lat: float, lon: float, fetch: Callable[[str], Any]) -> Optional[dict]:
    """CURRENT conditions from Weather.gov, or None if unavailable.

    The observation chain is three hops:
      /points/{lat},{lon}          -> observationStations URL + city
      .../stations                 -> station list
      /stations/{id}/observations/latest -> properties.temperature (°C)

    Stations go quiet, so several are tried (STATION_ATTEMPTS). If none
    reports a temperature, this falls back to the FORECAST period rather
    than returning nothing — a forecast temperature is worth more than an
    empty result, and `source` says which one the caller got so the two are
    never confused.

    Returns None (never raises) outside the US, on a 404, or on any
    malformed response; the caller then falls back to Open-Meteo.
    """
    try:
        point = fetch(WEATHERGOV_POINTS_URL.format(lat=lat, lon=lon))
        props = point.get("properties") or {}
        rel = (props.get("relativeLocation") or {}).get("properties") or {}
        city = str(rel.get("city") or "")

        # --- preferred: a real observation -----------------------------
        stations_url = props.get("observationStations")
        if stations_url:
            try:
                features = (fetch(stations_url).get("features")) or []
                for feature in features[:STATION_ATTEMPTS]:
                    station_id = ((feature or {}).get("properties") or {}).get(
                        "stationIdentifier")
                    if not station_id:
                        continue
                    reading = _observation_temp_f(
                        fetch(WEATHERGOV_OBSERVATION_URL.format(station=station_id)))
                    if reading is None:
                        continue          # station reported no temperature
                    temp_f, conditions = reading
                    return {
                        "summary": conditions or "Weather",
                        "temp_f": round(temp_f),
                        "location": city,
                        "at": int(time.time()),
                        "source": "weather.gov",
                        "station": station_id,
                    }
            except Exception:
                pass  # fall through to the forecast below

        # --- fallback: the forecast period -----------------------------
        # Explicitly labelled `weather.gov-forecast`, never `weather.gov`,
        # so a period temperature can never again be mistaken for an
        # observation by a reader of this payload.
        forecast_url = props.get("forecast")
        if not forecast_url:
            return None
        periods = ((fetch(forecast_url).get("properties") or {}).get("periods")) or []
        if not periods:
            return None
        now = periods[0]
        temp = now.get("temperature")
        if temp is None:
            return None
        if str(now.get("temperatureUnit", "F")).upper() == "C":
            temp = temp * 9 / 5 + 32
        return {
            "summary": str(now.get("shortForecast") or "Weather"),
            "temp_f": round(float(temp)),
            "location": city,
            "at": int(time.time()),
            "source": "weather.gov-forecast",
            "period": str(now.get("name") or ""),
        }
    except Exception:
        return None


def daily_forecast(
    lat: float, lon: float, fetch: Callable[[str], Any], days: int = 1,
) -> Optional[dict]:
    """Multi-day high/low + conditions from Weather.gov's daily forecast
    periods, or None if unavailable. Separate from weathergov_current
    because get_weather (mcp_web) needs BOTH current conditions and a
    short forecast; the ambient chip only ever needed the former, which is
    why this helper is new rather than another verbatim extraction.

    US offices report daytime/nighttime periods in the SAME /forecast
    payload weathergov_current's fallback branch reads — periods[0] is
    "today", periods[1] is "tonight", and so on. `days` worth of calendar
    days are built by pairing a daytime period with the following
    nighttime period (or a lone period, for the last day if unpaired).
    Temperatures are reported in Fahrenheit for US offices, but the unit
    is read from `temperatureUnit` rather than assumed — the same
    read-the-unit discipline `_observation_temp_f` uses for Celsius
    observations.

    Returns {"city": str, "days": [{"date"-like label, "high_f", "low_f",
    "condition"}, ...]} or None. Never raises.
    """
    try:
        point = fetch(WEATHERGOV_POINTS_URL.format(lat=lat, lon=lon))
        props = point.get("properties") or {}
        rel = (props.get("relativeLocation") or {}).get("properties") or {}
        city = str(rel.get("city") or "")
        forecast_url = props.get("forecast")
        if not forecast_url:
            return None
        periods = ((fetch(forecast_url).get("properties") or {}).get("periods")) or []
        if not periods:
            return None

        def _f(period: dict) -> Optional[float]:
            temp = period.get("temperature")
            if temp is None:
                return None
            if str(period.get("temperatureUnit", "F")).upper() == "C":
                temp = temp * 9 / 5 + 32
            return float(temp)

        out: list[dict] = []
        i = 0
        while i < len(periods) and len(out) < max(1, days):
            day = periods[i]
            is_daytime = bool(day.get("isDaytime", True))
            high = _f(day) if is_daytime else None
            low = None if is_daytime else _f(day)
            condition = str(day.get("shortForecast") or "")
            label = str(day.get("name") or "")
            # Pair with the paired night/day period when present.
            if i + 1 < len(periods):
                nxt = periods[i + 1]
                nxt_is_daytime = bool(nxt.get("isDaytime", True))
                if nxt_is_daytime != is_daytime:
                    if is_daytime:
                        low = _f(nxt)
                    else:
                        high = _f(nxt)
                    i += 1
            out.append({
                "label": label,
                "high_f": round(high) if high is not None else None,
                "low_f": round(low) if low is not None else None,
                "condition": condition,
            })
            i += 1
        return {"city": city, "days": out}
    except Exception:
        return None
