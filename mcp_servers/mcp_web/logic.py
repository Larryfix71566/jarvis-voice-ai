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

from mcp_servers.mcp_selfedit.logic import AdminClient, OFFLINE_ERROR
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

    G1 (MORTIMER_SESSION_GAPS_AND_SELFEDIT_CONVERGENCE_PLAN.md): RainViewer
    moved from timestamp-based tile paths (`/v2/radar/{time}/...`) to a
    hashed `path` field per frame (`/v2/radar/{hash}/...`); URLs built from
    `time` now 410. Tile URLs are built from `frame["path"]` when present —
    `time` is kept ONLY as the payload's `ts` display timestamp, never used
    to construct a URL again. If `path` is missing from the frame (an older
    or unexpected API shape), fall back to the old ts-constructed form
    rather than erroring — a possibly-stale tile beats no radar at all.
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
        frame = past[-1]
        ts = frame["time"]
        path = frame.get("path")
    except Exception as exc:
        return {"error": f"Radar data failed: {type(exc).__name__}."}

    coords = radar_tile_grid(lat, lon)
    if path:
        # G1: RainViewer's current API — hashed path, not a constructed ts.
        tiles = [
            f"{host}{path}/512/{RADAR_ZOOM}/{x}/{y}/2/1_1.png"
            for x, y in coords
        ]
    else:
        # Fallback: old constructed form, only if the frame lacks `path`.
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


# ------------------------------------------------- site research & comparison
# MORTIMER_SITE_RESEARCH_AND_COMPARISON_PLAN.md R1. Thin HTTP-client tools,
# same two-phase-confirmation convention as mcp_selfedit.logic's
# selfedit_start/plan_start (this module reuses AdminClient rather than a
# second sidecar-client implementation) — all crawl/model logic lives in
# the admin sidecar's /api/research/* endpoints and jarvis/research/crawl.py;
# nothing here duplicates it.


def _call(fn):
    try:
        return fn()
    except Exception:
        return {"ok": False, "error": OFFLINE_ERROR}


def research_compare_start(
    client, urls: list, focus: str = "", confirm: bool = False,
) -> dict:
    """Two-phase start of a site comparison. URLS must name exactly two
    sites; FOCUS steers the crawl (e.g. "pricing and support") and, when
    given, is what the review compares on — leave empty for a general
    comparison. Crawling costs Tavily credits and runs in the background
    for a few minutes; the confirm=false preview names the approximate
    cost so the user is deciding with that in view."""
    urls = [u.strip() for u in (urls or []) if isinstance(u, str) and u.strip()]
    if len(urls) != 2:
        return {"ok": False, "error": "I need exactly two URLs to compare."}
    if not confirm:
        focus_note = f" — focus: {focus}" if (focus or "").strip() else ""
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to crawl and compare {urls[0]} and {urls[1]}{focus_note}. "
                f"This costs Tavily credits (roughly 40 for a full comparison) and "
                f"runs in the background for a few minutes. Say yes to start."
            ),
            "urls": urls, "focus": focus,
        }
    resp = _call(lambda: client.post(
        "/api/research/start", json={"urls": urls, "focus": focus}))
    if not resp.get("ok"):
        return resp
    return {
        "ok": True, "started": True,
        "summary": (
            f"Started comparing {urls[0]} and {urls[1]}. This can take a few "
            f"minutes — ask me for status anytime."
        ),
    }


def research_status(client) -> dict:
    """Report progress of the current site comparison: still crawling,
    failed (naming which site and why), or ready to view/save."""
    resp = _call(lambda: client.get("/api/research/job"))
    if not resp.get("ok"):
        return resp
    job = resp.get("job", {}) or {}
    state = job.get("state")
    if state in (None, "idle"):
        return {"ok": True, "summary": "No comparison is active.", "job": job}
    if state == "running":
        urls = job.get("urls") or []
        return {
            "ok": True,
            "summary": f"Still crawling and comparing {', '.join(urls)}. I'll keep at it.",
            "job": job,
        }
    if state == "error":
        return {
            "ok": True,
            "summary": f"The comparison failed: {job.get('error') or 'unknown error'}",
            "job": job,
        }
    if state == "done":
        credits = job.get("credits_used")
        credit_note = f" ({credits} credits used)" if credits is not None else ""
        return {
            "ok": True,
            "summary": (
                f"The comparison is ready{credit_note} — it's on your display. "
                f"Say the word and I'll save it as a document."
            ),
            "job": job,
        }
    return {"ok": True, "summary": "Comparison status unknown.", "job": job}


def research_save(client, path: str | None = None, confirm: bool = False) -> dict:
    """Preview, then save the generated comparison in an open VM session."""
    status = _call(lambda: client.get("/api/research/job"))
    if not status.get("ok"):
        return status
    job = status.get("job", {}) or {}
    if job.get("state") != "done":
        return {"ok": False, "error": "there's no finished comparison to save yet."}
    if not confirm:
        target = path or "a docs/research/ file named after the sites"
        return {
            "ok": True,
            "needs_confirmation": True,
            "summary": (
                f"Ready to save the comparison as a draft at {target}. Say yes "
                f"to save it in an open self-edit sandbox session. Verification and draft PR preparation follow with selfedit_finish."
            ),
            "path": path,
        }
    resp = _call(lambda: client.post("/api/research/save", json={"path": path}))
    if not resp.get("ok"):
        return resp
    if resp.get("saved_to_sandbox") is not True:
        return {"ok": False, "error": "The server did not confirm a sandbox save. Inspect self-edit status before retrying; no saved document is being reported."}
    return {**resp, "summary": (
        f"Saved the comparison at {resp.get('path')} in the sandbox. "
        "Use selfedit_finish to verify it and prepare a draft PR; it is not published yet."
    )}


# ------------------------------------------------------------- sports scores
# Status spec P6 (L7). Two UNOFFICIAL, undocumented public endpoints, accepted
# by Larry 2026-09-23 and verified that day from his browser (Step 0; the
# captured, trimmed responses are tests/fixtures/sports/*.json):
#   MLB: statsapi.mlb.com schedule -> dates[].games[]; state field
#        status.abstractGameState (Preview | Live | Final); a scheduled game
#        has no teams.*.score key; gameDate is UTC ("...Z").
#   NFL: ESPN site/v2 scoreboard -> events[]; state field status.type.state
#        (pre | in | post); competitor score is a STRING and a scheduled game
#        carries "0", which is reported as None, never as a 0-0 score.
#        "in" was NOT observed live (no game in progress at capture time).
# A state this code does not recognise is reported with the source's own
# description, never mapped to a guess: "final" in particular is claimed only
# when the source says the game is over AND gives a score (ESPN: completed).

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
ESPN_NFL_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)
SPORTS_LEAGUES = ("nfl", "mlb")

MLB_STATE_MAP = {"Preview": "scheduled", "Live": "in_progress", "Final": "final"}
ESPN_STATE_MAP = {"pre": "scheduled", "in": "in_progress", "post": "final"}


def _sports_get_json(url: str, params: dict):
    resp = httpx.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _sports_tz():
    """JARVIS_TIMEZONE (a BASE_ENV_KEYS variable, so it reaches this child),
    or UTC when it is unset, an unresolved "${...}" literal, or not a zone —
    the same defence mcp_reminders' _tz() applies. Never raises."""
    from zoneinfo import ZoneInfo

    value = os.environ.get("JARVIS_TIMEZONE", "").strip()
    if value and "${" not in value:
        try:
            return ZoneInfo(value)
        except Exception:  # noqa: BLE001 — a bad zone must not kill the tool
            pass
    return ZoneInfo("UTC")


def _start_local(utc_text, tz) -> str | None:
    """ISO start time in the configured zone, minute precision. Accepts both
    MLB's "2026-09-20T17:10:00Z" and ESPN's "2026-09-20T17:00Z"."""
    from datetime import datetime, timezone

    if not isinstance(utc_text, str) or not utc_text.strip():
        return None
    text = utc_text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).isoformat(timespec="minutes")


def _int_or_none(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def mlb_status(status: dict, has_scores: bool) -> str:
    """Map an MLB game's status block. Unknown abstract states, and a "Final"
    with no score (e.g. a postponement, not observed in Step 0), keep the
    source's own words rather than being guessed."""
    status = status or {}
    abstract = status.get("abstractGameState")
    mapped = MLB_STATE_MAP.get(abstract)
    described = status.get("detailedState") or abstract or "unknown"
    if mapped is None or (mapped == "final" and not has_scores):
        return described
    return mapped


def espn_status(status_type: dict) -> str:
    """Map an ESPN event's status.type. "post" counts as final only when the
    source also says completed; anything unrecognised keeps its description."""
    status_type = status_type or {}
    mapped = ESPN_STATE_MAP.get(status_type.get("state"))
    described = (status_type.get("description") or status_type.get("name")
                 or status_type.get("state") or "unknown")
    if mapped is None or (mapped == "final" and status_type.get("completed") is not True):
        return described
    return mapped


def parse_mlb_schedule(payload: dict, tz) -> list[dict]:
    games = []
    for day in (payload or {}).get("dates") or []:
        for game in day.get("games") or []:
            teams = game.get("teams") or {}
            away, home = teams.get("away") or {}, teams.get("home") or {}
            away_score = _int_or_none(away.get("score"))
            home_score = _int_or_none(home.get("score"))
            status = mlb_status(game.get("status") or {},
                                away_score is not None and home_score is not None)
            if status == "scheduled":
                away_score = home_score = None
            games.append({
                "away": (away.get("team") or {}).get("name") or "",
                "home": (home.get("team") or {}).get("name") or "",
                "away_score": away_score,
                "home_score": home_score,
                "status": status,
                "start_local": _start_local(game.get("gameDate"), tz),
            })
    return games


def parse_espn_scoreboard(payload: dict, tz) -> list[dict]:
    games = []
    for event in (payload or {}).get("events") or []:
        comps = event.get("competitions") or [{}]
        sides = {c.get("homeAway"): c for c in (comps[0].get("competitors") or [])}
        away, home = sides.get("away") or {}, sides.get("home") or {}
        status = espn_status((event.get("status") or {}).get("type") or {})
        if status == "scheduled":
            # A scheduled ESPN game carries score "0": no score, not 0-0.
            away_score = home_score = None
        else:
            away_score = _int_or_none(away.get("score"))
            home_score = _int_or_none(home.get("score"))
        games.append({
            "away": (away.get("team") or {}).get("displayName") or "",
            "home": (home.get("team") or {}).get("displayName") or "",
            "away_score": away_score,
            "home_score": home_score,
            "status": status,
            "start_local": _start_local(event.get("date") or comps[0].get("date"), tz),
        })
    return games


def sports_scores(league: str, date: str = "", fetch=None, now=None) -> dict:
    """Scores or schedule for one league on one day (spec P6).

    LEAGUE is "nfl" or "mlb"; DATE is YYYY-MM-DD in JARVIS_TIMEZONE, empty
    for today. FETCH(url, params) -> parsed JSON is the injected HTTP getter
    (tests pass fixtures; the server uses httpx); NOW is an injectable
    aware datetime for "today". Never raises."""
    from datetime import datetime, timezone

    league = (league or "").strip().lower()
    if league not in SPORTS_LEAGUES:
        return {"ok": False, "error": f"no structured source for {league or '(none)'}"}
    tz = _sports_tz()
    date = (date or "").strip()
    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"ok": False, "error": "date must be YYYY-MM-DD"}
    else:
        day = (now or datetime.now(timezone.utc)).astimezone(tz).date()
    fetch = fetch or _sports_get_json

    if league == "mlb":
        source, url = "statsapi.mlb.com", MLB_SCHEDULE_URL
        params = {"sportId": 1, "date": day.isoformat(), "hydrate": "linescore"}
        parse = parse_mlb_schedule
    else:
        source, url = "site.api.espn.com", ESPN_NFL_SCOREBOARD_URL
        params = {"dates": day.strftime("%Y%m%d")}
        parse = parse_espn_scoreboard

    try:
        payload = fetch(url, params)
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"{source} failed (HTTP {exc.response.status_code})."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{source} failed: {type(exc).__name__}."}
    try:
        games = parse(payload, tz)
    except Exception as exc:  # noqa: BLE001 — shape drift on an unofficial API
        return {"ok": False,
                "error": f"{source} returned an unexpected shape ({type(exc).__name__})."}
    return {
        "ok": True,
        "league": league,
        "date": day.isoformat(),
        "source": source,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "games": games,
    }
