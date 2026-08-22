"""mcp-web: Tavily search + weather pure logic (plan Phase 1, §1.4).

Sync functions, plain dicts in/out, 10s httpx timeouts, network failures
return {"error": ...} — never raise. TAVILY_API_KEY absent -> degraded
mode error dict (plan §6.2).

D-011: the Tavily search transport is MCP-first. Tavily's AWS WAF blocks
some egress IPs on api.tavily.com (bare awselb 403 before auth), while
their hosted MCP endpoint mcp.tavily.com serves the same key/account from
the same source IP. web_search therefore tries the MCP JSON-RPC endpoint
first and falls back to the classic REST API; the locked return contract
({"results": [{title,url,snippet}], "answer": str}) is unchanged.

W1/W2/W3/W4 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md, 2026-08-22):
get_weather is now Weather.gov-PRIMARY (via the shared jarvis.weathergov
client — the SAME implementation jarvis/ambient_weather.py uses, never a
second one), Open-Meteo remains the fallback for outside the US or any
Weather.gov failure. Geocoding still uses Open-Meteo's keyless geocoder
(Weather.gov has none) — that hop is unchanged. The payload always carries
BOTH temperature_f/max_f/min_f AND temperature_c/max_c/min_c (W2 — additive,
so the payload's SHAPE never varies with the setting) plus a `units` field
naming which is primary, read from JARVIS_UNITS (W3 — a config setting,
bridged from Settings via bridge_settings_to_env exactly like
JARVIS_TIMEZONE, never a memory fact: a fact carrying this rule was live on
2026-08-20 while this tool still returned Celsius, because nothing in this
code path ever read it). `source` names exactly which upstream answered
(W4): "weather.gov" (a real observation), "weather.gov-forecast" (period
fallback — NEVER conflated with an observation, a distinction that cost a
real 13-degree bug in the ambient chip on 2026-08-18), or "open-meteo".

get_weather_radar adds keyless precipitation radar via RainViewer's public
tile API: the tool returns tile URLs (never binary) and the frontend's
DisplayPanel stitches them into a seamless 3×3 map. W6 adds a keyless CARTO
dark basemap underneath, at the SAME tile coordinates, since RainViewer
tiles are transparent precipitation overlays with nothing to composite onto
otherwise.
"""

from __future__ import annotations

import json
import math
import os

import httpx

from jarvis.weathergov import daily_forecast as _wg_daily_forecast
from jarvis.weathergov import fetch_headers as _wg_fetch_headers
from jarvis.weathergov import weathergov_current as _wg_current

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_MCP_URL = "https://mcp.tavily.com/mcp/"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
RAINVIEWER_URL = "https://api.rainviewer.com/public/weather-maps.json"
CARTO_BASEMAP_URL = "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
TIMEOUT = 10.0

VALID_UNITS = ("imperial", "metric")
DEFAULT_UNITS = "imperial"


def _configured_units() -> str:
    """W3: read straight from env (this is a subprocess — no Settings
    object here), bridged from JARVIS_UNITS by bridge_settings_to_env
    exactly like JARVIS_TIMEZONE already is. An unrecognized/missing value
    defaults to imperial rather than raising — this tool must not go down
    because of a malformed setting; jarvis.config's own validator is what
    actually enforces the value at the source."""
    v = os.environ.get("JARVIS_UNITS", DEFAULT_UNITS).strip().lower()
    return v if v in VALID_UNITS else DEFAULT_UNITS


def _f_to_c(f):
    return round((f - 32) * 5 / 9, 1) if f is not None else None


def _c_to_f(c):
    return round(c * 9 / 5 + 32, 1) if c is not None else None


def _weathergov_fetch(url: str):
    resp = httpx.get(url, timeout=TIMEOUT, headers=_wg_fetch_headers(url))
    resp.raise_for_status()
    return resp.json()

# WMO weather interpretation codes -> short English conditions.
WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _condition(code: int | None) -> str:
    return WMO_CODES.get(code if code is not None else -1, "unknown conditions")


def _search_via_rest(query: str, max_results: int, api_key: str) -> dict:
    """Classic REST transport (fallback when the MCP endpoint fails)."""
    resp = httpx.post(
        TAVILY_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "max_results": max_results, "include_answer": True},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


class _MCPTransportError(Exception):
    """Raised when the hosted MCP endpoint cannot serve the search."""


def _parse_sse_json(text: str) -> dict:
    """Extract the JSON-RPC message from an MCP streamable-HTTP SSE body."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[len("data:"):].strip())
    raise _MCPTransportError("no data line in SSE body")


def _search_via_mcp(query: str, max_results: int, api_key: str) -> dict:
    """D-011 primary transport: Tavily's hosted MCP server (JSON-RPC)."""
    resp = httpx.post(
        TAVILY_MCP_URL,
        params={"tavilyApiKey": api_key},
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "tavily_search",
                "arguments": {"query": query, "max_results": max_results},
            },
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    payload = _parse_sse_json(resp.text)
    if "error" in payload:
        raise _MCPTransportError(str(payload["error"])[:120])
    result = payload.get("result") or {}
    if result.get("isError"):
        raise _MCPTransportError("tool returned isError")
    content = result.get("content") or []
    if not content or content[0].get("type") != "text":
        raise _MCPTransportError("unexpected MCP content shape")
    inner = json.loads(content[0]["text"])
    if inner.get("error"):
        raise _MCPTransportError(str(inner["error"])[:120])
    return inner


def web_search(query: str, max_results: int = 5) -> dict:
    """Tavily web search. Degrades cleanly when TAVILY_API_KEY is unset."""
    query = (query or "").strip()
    if not query:
        return {"error": "A search query is required."}
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"error": "Web search is unavailable (no API key configured)."}
    max_results = max(1, min(int(max_results), 10))
    try:
        data = _search_via_mcp(query, max_results, api_key)
    except Exception:
        # MCP endpoint unreachable/blocked/misbehaving -> classic REST.
        try:
            data = _search_via_rest(query, max_results, api_key)
        except httpx.HTTPStatusError as exc:
            return {"error": f"Web search failed (HTTP {exc.response.status_code})."}
        except Exception as exc:
            return {"error": f"Web search failed: {type(exc).__name__}."}
    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("content") or "")[:300],
        }
        for r in data.get("results", [])
    ]
    return {"results": results, "answer": data.get("answer") or ""}


def _weather_via_weathergov(lat: float, lon: float, days: int) -> dict | None:
    """Weather.gov-primary path. Returns None (never raises) so the caller
    falls back to Open-Meteo — the same "return None, let the caller
    fall through" discipline weathergov_current itself uses."""
    try:
        wg_current = _wg_current(lat, lon, _weathergov_fetch)
    except Exception:
        wg_current = None
    if wg_current is None:
        return None

    temp_f = wg_current.get("temp_f")
    current = {
        "temperature_f": temp_f,
        "temperature_c": _f_to_c(temp_f),
        # Weather.gov's observation payload (shared via weathergov_current)
        # does not surface humidity/wind — those keys stay present but
        # None rather than silently disappearing (W2: shape never varies).
        "humidity_percent": None,
        "wind_kph": None,
        "condition": wg_current.get("summary") or "",
    }

    daily_out: list[dict] = []
    try:
        fc = _wg_daily_forecast(lat, lon, _weathergov_fetch, days=days)
    except Exception:
        fc = None
    for d in (fc or {}).get("days", []):
        max_f, min_f = d.get("high_f"), d.get("low_f")
        daily_out.append({
            "date": d.get("label", ""),
            "max_f": max_f,
            "min_f": min_f,
            "max_c": _f_to_c(max_f),
            "min_c": _f_to_c(min_f),
            # Weather.gov's /forecast periods don't carry a precipitation
            # probability in the shape daily_forecast reads — left None
            # rather than fabricated; Open-Meteo's fallback path below
            # does populate it.
            "precip_probability": None,
            "condition": d.get("condition", ""),
        })

    return {
        "city": wg_current.get("location") or "",
        "source": wg_current.get("source", "weather.gov"),
        "current": current,
        "daily": daily_out,
    }


def get_weather(city: str, days: int = 1) -> dict:
    """Current conditions + forecast for a city. W1: Weather.gov-primary
    (via the shared jarvis.weathergov client), Open-Meteo as fallback for
    outside the US or any Weather.gov failure. W2: the payload always
    carries both °F and °C fields; W3: `units` names which is primary,
    read from JARVIS_UNITS. W4: `source` always says which upstream
    actually answered."""
    city = (city or "").strip()
    if not city:
        return {"error": "A city name is required."}
    days = max(1, min(int(days), 3))
    units = _configured_units()

    try:
        geo = httpx.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=TIMEOUT)
        geo.raise_for_status()
        geo_results = geo.json().get("results") or []
    except Exception as exc:
        return {"error": f"Weather lookup failed: {type(exc).__name__}."}
    if not geo_results:
        return {"error": f"I couldn't find a place called '{city}'."}

    place = geo_results[0]
    label = place["name"]
    if place.get("country"):
        label = f"{label}, {place['country']}"
    lat, lon = float(place["latitude"]), float(place["longitude"])

    wg_result = _weather_via_weathergov(lat, lon, days)

    if wg_result is not None:
        source = wg_result["source"]
        current = wg_result["current"]
        daily_out = wg_result["daily"]
        city_label = wg_result["city"] or label
    else:
        # --- fallback: Open-Meteo (non-US, or Weather.gov unavailable) ---
        try:
            fc = httpx.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max,weather_code",
                    "timezone": "auto",
                    "forecast_days": days,
                },
                timeout=TIMEOUT,
            )
            fc.raise_for_status()
            data = fc.json()
        except Exception as exc:
            return {"error": f"Weather forecast failed: {type(exc).__name__}."}

        cur = data.get("current", {})
        daily = data.get("daily", {})
        temp_c = cur.get("temperature_2m")
        current = {
            "temperature_c": temp_c,
            "temperature_f": _c_to_f(temp_c),
            "humidity_percent": cur.get("relative_humidity_2m"),
            "wind_kph": cur.get("wind_speed_10m"),
            "condition": _condition(cur.get("weather_code")),
        }
        daily_out = []
        for i, date in enumerate(daily.get("time", [])):
            precip = (daily.get("precipitation_probability_max") or [None])[i]
            max_c = (daily.get("temperature_2m_max") or [None])[i]
            min_c = (daily.get("temperature_2m_min") or [None])[i]
            daily_out.append({
                "date": date,
                "max_c": max_c,
                "min_c": min_c,
                "max_f": _c_to_f(max_c),
                "min_f": _c_to_f(min_c),
                "precip_probability": precip,
                "condition": _condition((daily.get("weather_code") or [None])[i]),
            })
        source = "open-meteo"
        city_label = label

    first = daily_out[0] if daily_out else {}
    if units == "metric":
        cur_temp = current["temperature_c"]
        cur_unit = "°C"
        first_max, first_min = first.get("max_c"), first.get("min_c")
    else:
        cur_temp = current["temperature_f"]
        cur_unit = "°F"
        first_max, first_min = first.get("max_f"), first.get("min_f")

    human = f"In {city_label} it's currently {cur_temp}{cur_unit} and {current['condition']}"
    if current.get("wind_kph") is not None:
        human += f" with {current['wind_kph']} km/h winds"
    if first and first_max is not None and first_min is not None:
        human += (
            f"; {'today' if days == 1 else first.get('date', '')} expect a "
            f"high of {first_max}{cur_unit} and a low of {first_min}{cur_unit}"
        )
        if first.get("precip_probability") is not None:
            human += f" with a {first['precip_probability']}% chance of precipitation"
        human += "."
    else:
        human += "."

    return {
        "city": city_label,
        "source": source,
        "units": units,
        "current": current,
        "daily": daily_out,
        "human": human,
    }


# --------------------------------------------------------------- radar

RADAR_ZOOM = 6


def radar_tile_grid(lat: float, lon: float, zoom: int = RADAR_ZOOM) -> list[tuple[int, int]]:
    """3×3 slippy-map tile coords (row-major) around (lat, lon).

    Standard Web-Mercator math: fractional tile position -> floor to the
    containing tile, then the surrounding ring. x wraps at the antimeridian;
    out-of-range y rows (near the poles) are dropped.
    """
    n = 2 ** zoom
    xf = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    yf = (
        (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi)
        / 2.0
        * n
    )
    x0, y0 = int(math.floor(xf)), int(math.floor(yf))
    tiles = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y = y0 + dy
            if 0 <= y < n:
                tiles.append(((x0 + dx) % n, y))
    return tiles


def get_weather_radar(city: str) -> dict:
    """Latest precipitation radar tiles for a city, via keyless RainViewer.

    Returns {"city", "lat", "lon", "ts", "tiles": [9 tile URLs],
    "basemap_tiles": [9 tile URLs]} — the UI stitches the 3×3 grid into
    one map. No API key, no binary transport.

    W6 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md): RainViewer's tiles
    are TRANSPARENT precipitation overlays meant to sit on a basemap — with
    nothing underneath, a clear-sky radar is nine blank images and a
    stormy one is colour with no geography to place it against.
    `basemap_tiles` is a keyless CARTO dark_all layer at the EXACT SAME
    z/x/y coordinates `radar_tile_grid` already computed for `tiles` — the
    same coordinate list is reused, never recomputed, so the two grids
    cannot desync if the zoom level ever changes. `dark_all` was chosen to
    suit the console's `--bg: #15191d` graphite theme rather than glaring
    against it like standard OSM tiles would.
    """
    city = (city or "").strip()
    if not city:
        return {"error": "A city name is required."}

    try:
        geo = httpx.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=TIMEOUT)
        geo.raise_for_status()
        geo_results = geo.json().get("results") or []
    except Exception as exc:
        return {"error": f"Radar lookup failed: {type(exc).__name__}."}
    if not geo_results:
        return {"error": f"I couldn't find a place called '{city}'."}

    place = geo_results[0]
    label = place["name"]
    if place.get("country"):
        label = f"{label}, {place['country']}"
    lat, lon = float(place["latitude"]), float(place["longitude"])

    try:
        rv = httpx.get(RAINVIEWER_URL, timeout=TIMEOUT)
        rv.raise_for_status()
        data = rv.json()
        host = data["host"]
        past = data["radar"]["past"]
        ts = past[-1]["time"]
    except Exception as exc:
        return {"error": f"Radar data failed: {type(exc).__name__}."}

    coords = radar_tile_grid(lat, lon)
    tiles = [
        f"{host}/v2/radar/{ts}/512/{RADAR_ZOOM}/{x}/{y}/2/1_1.png"
        for x, y in coords
    ]
    # W6: SAME coords as `tiles`, reused rather than recomputed — the
    # basemap and the precipitation overlay can never desync.
    basemap_tiles = [
        CARTO_BASEMAP_URL.format(z=RADAR_ZOOM, x=x, y=y) for x, y in coords
    ]
    return {
        "city": label, "lat": lat, "lon": lon, "ts": ts,
        "tiles": tiles, "basemap_tiles": basemap_tiles,
    }
