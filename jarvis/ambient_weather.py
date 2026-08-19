"""Current weather for the console's ambient strip (Larry 2026-08-18).

The ambient strip used to show only *last-known* weather, cached as a
side effect of the user asking Mortimer about weather — deliberately
stale, per the engagement plan's "nothing in the ambient layer ever
initiates an API call" rule. Larry overrode that for weather: a weather
chip is only useful if it's current, for the current location. The rule
survives in its original spirit — the CLIENT still never fetches
anything; this module runs inside the admin sidecar, which serves the
result through the existing read-only GET /api/ambient.

Design, matching house conventions (mcp_web's sync/never-raise shape):
- sync functions, plain dicts out, httpx with short timeouts, every
  network failure degrades to None — the chip simply doesn't render,
  and being down must never add an error surface.
- location resolution order: JARVIS_WEATHER_LAT + JARVIS_WEATHER_LON
  env override (with optional JARVIS_WEATHER_LABEL for the display
  name) → DEVICE location posted by the Mac shell (CoreLocation, see
  set_device_location below) → IP geolocation (ip-api.com, no key) →
  give up (None). Device location is what makes the chip follow Larry
  when he travels; IP geolocation is only the fallback for a plain
  browser or a shell without the location entitlement granted.
- weather from Weather.gov (api.weather.gov, free, no API key, US-only),
  falling back to Open-Meteo outside the US or on any failure. Larry
  2026-08-18: "let's go with the plan and modify the earlier work" — the
  stored project decision was Weather.gov for forecast text plus
  RainViewer for radar, and the first cut used Open-Meteo. Weather.gov
  reports Fahrenheit natively (matching user.preference.units), gives a
  human forecast phrase rather than a numeric code, and returns the
  nearest city name for free — which is a better label than the
  IP-geolocation guess. It covers the US only, so Open-Meteo remains the
  fallback rather than being removed.
  NOTE: RainViewer radar tiles are the OTHER half of that decision and
  are NOT implemented here — radar is imagery for a display surface, not
  a one-line ambient chip.
- Weather.gov gives OBSERVATIONS, not forecast periods. This distinction
  cost a real bug (2026-08-18): reading `properties.forecast`'s
  `periods[0].temperature` shows the current PERIOD's forecast — after
  sunset, tonight's LOW — which read 69°F while the macOS widget read
  82°F for the same city. `source` distinguishes them: `weather.gov` is
  an observation, `weather.gov-forecast` is the degraded fallback.
- one module-level cache, WEATHER_CACHE_TTL_S; /api/ambient is polled
  every 60s by the console but the upstream APIs see at most one call
  per TTL.
- kill switch: JARVIS_AMBIENT_WEATHER_ENABLED=false, checked once here.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

import httpx

WEATHER_CACHE_TTL_S = 900  # 15 min
HTTP_TIMEOUT_S = 10.0

GEO_URL = "http://ip-api.com/json/?fields=status,lat,lon,city"
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

FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,weather_code"
    "&temperature_unit=fahrenheit"
)

# WMO weather interpretation codes (Open-Meteo's `weather_code`), mapped
# to short chip-sized text. Grouped per the WMO table; unknown codes fall
# back to "Weather".
_WMO: dict[int, str] = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Drizzle",
    53: "Drizzle",
    55: "Drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm w/ hail",
    99: "Thunderstorm w/ hail",
}


def weather_enabled() -> bool:
    return os.environ.get("JARVIS_AMBIENT_WEATHER_ENABLED", "").strip().lower() not in (
        "false",
        "0",
        "no",
    )


def _fetch_json(url: str) -> Any:
    headers = {"User-Agent": WEATHERGOV_UA} if "weather.gov" in url else {}
    resp = httpx.get(url, timeout=HTTP_TIMEOUT_S, headers=headers)
    resp.raise_for_status()
    return resp.json()


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


def _weathergov_current(lat: float, lon: float, fetch: Callable[[str], Any]) -> Optional[dict]:
    """CURRENT conditions from Weather.gov, or None if unavailable.

    Larry 2026-08-18, from a live mismatch: the console read 69°F while
    the macOS widget read 82°F for the same city at 9:52 PM. Cause — this
    function used `properties.forecast` and took `periods[0].temperature`,
    which is a FORECAST PERIOD, not an observation. After sunset
    `periods[0]` is "Tonight" and its temperature is the overnight LOW.
    The chip was showing tonight's low labelled as the current
    temperature: roughly right by day, badly wrong after dark. (The
    module's original note that this was never verified against the live
    API was correct, and this is what it was warning about.)

    The observation chain is three hops:
      /points/{lat},{lon}          -> observationStations URL + city
      .../stations                 -> station list
      /stations/{id}/observations/latest -> properties.temperature (°C)

    Stations go quiet, so several are tried (STATION_ATTEMPTS). If none
    reports a temperature, this falls back to the FORECAST period rather
    than returning nothing — a forecast temperature is worth more than an
    empty chip, and `source` says which one the caller got so the two are
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


# --- device location (Mac shell / CoreLocation) --------------------------
#
# The shell POSTs coordinates to the sidecar's /api/location whenever
# CoreLocation reports a meaningful move; the sidecar calls
# set_device_location() and this module prefers that over IP geolocation.
# Kept in memory only — a real location is not written to disk, and a
# shell that stops reporting (quit, permission revoked, laptop moved to a
# network-only session) goes stale and falls back to IP within
# DEVICE_LOCATION_MAX_AGE_S rather than pinning the chip to a place Larry
# has left.

DEVICE_LOCATION_MAX_AGE_S = 3600  # 1 hour

_device_location: Optional[dict] = None  # {"lat","lon","label","at"(monotonic)}


def set_device_location(lat: float, lon: float, label: str = "") -> None:
    """Record the device's own coordinates (called by the sidecar's
    POST /api/location). Invalidates the weather cache when the position
    actually moved, so travelling refreshes the chip instead of showing
    the old city's weather for up to 15 minutes."""
    global _device_location, _cache
    prev = _device_location
    _device_location = {
        "lat": float(lat),
        "lon": float(lon),
        "label": str(label or ""),
        "at": time.monotonic(),
    }
    moved = (
        prev is None
        or abs(prev["lat"] - _device_location["lat"]) > 0.05
        or abs(prev["lon"] - _device_location["lon"]) > 0.05
    )
    if moved:
        _cache = None


def get_device_location() -> Optional[dict]:
    """The device location if one was reported recently, else None."""
    if _device_location is None:
        return None
    if time.monotonic() - _device_location["at"] > DEVICE_LOCATION_MAX_AGE_S:
        return None
    return _device_location


def _resolve_location(fetch: Callable[[str], Any]) -> Optional[dict]:
    """{"lat": float, "lon": float, "label": str} or None."""
    lat_env = os.environ.get("JARVIS_WEATHER_LAT", "").strip()
    lon_env = os.environ.get("JARVIS_WEATHER_LON", "").strip()
    if lat_env and lon_env:
        try:
            return {
                "lat": float(lat_env),
                "lon": float(lon_env),
                "label": os.environ.get("JARVIS_WEATHER_LABEL", "").strip(),
            }
        except ValueError:
            pass  # malformed override — fall through
    device = get_device_location()
    if device is not None:
        return {"lat": device["lat"], "lon": device["lon"], "label": device["label"]}
    try:
        geo = fetch(GEO_URL)
        if geo.get("status") != "success":
            return None
        return {
            "lat": float(geo["lat"]),
            "lon": float(geo["lon"]),
            "label": str(geo.get("city") or ""),
        }
    except Exception:
        return None


# Module-level cache: (fetched_at_monotonic, result-or-None). A failed
# fetch is cached too — a dead network must not turn the 60s ambient
# poll into a hammering retry loop.
_cache: Optional[tuple[float, Optional[dict]]] = None


def get_weather(fetch: Callable[[str], Any] = _fetch_json) -> Optional[dict]:
    """Current weather dict for the ambient chip, or None.

    Shape: {"summary": "Partly cloudy", "temp_f": 87, "location": "Atlanta",
    "at": <unix seconds>} — `location` may be "" when unknown.
    Never raises.
    """
    global _cache
    if not weather_enabled():
        return None
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < WEATHER_CACHE_TTL_S:
        return _cache[1]

    result: Optional[dict] = None
    try:
        loc = _resolve_location(fetch)
        if loc is not None:
            # Weather.gov first (Larry's stored decision): native
            # Fahrenheit, a real forecast phrase, and a city name.
            result = _weathergov_current(loc["lat"], loc["lon"], fetch)
            if result is not None:
                if not result["location"]:
                    result["location"] = loc["label"]
                _cache = (now, result)
                return result
            # Outside the US, or Weather.gov unavailable.
            data = fetch(FORECAST_URL.format(lat=loc["lat"], lon=loc["lon"]))
            current = data.get("current") or {}
            temp = current.get("temperature_2m")
            code = current.get("weather_code")
            if temp is not None:
                result = {
                    "summary": _WMO.get(int(code), "Weather") if code is not None else "Weather",
                    "temp_f": round(float(temp)),
                    "location": loc["label"],
                    "at": int(time.time()),
                    "source": "open-meteo",
                }
    except Exception:
        result = None

    _cache = (now, result)
    return result


def _clear_cache_for_tests() -> None:
    global _cache, _device_location
    _cache = None
    _device_location = None
