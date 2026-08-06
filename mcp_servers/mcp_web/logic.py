"""mcp-web: Tavily search + Open-Meteo weather pure logic (plan Phase 1, §1.4).

Sync functions, plain dicts in/out, 10s httpx timeouts, network failures
return {"error": ...} — never raise. TAVILY_API_KEY absent -> degraded
mode error dict (plan §6.2).

D-011: the Tavily search transport is MCP-first. Tavily's AWS WAF blocks
some egress IPs on api.tavily.com (bare awselb 403 before auth), while
their hosted MCP endpoint mcp.tavily.com serves the same key/account from
the same source IP. web_search therefore tries the MCP JSON-RPC endpoint
first and falls back to the classic REST API; the locked return contract
({"results": [{title,url,snippet}], "answer": str}) is unchanged.
"""

from __future__ import annotations

import json
import os

import httpx

TAVILY_URL = "https://api.tavily.com/search"
TAVILY_MCP_URL = "https://mcp.tavily.com/mcp/"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10.0

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


def get_weather(city: str, days: int = 1) -> dict:
    """Current conditions + forecast for a city, via keyless Open-Meteo."""
    city = (city or "").strip()
    if not city:
        return {"error": "A city name is required."}
    days = max(1, min(int(days), 3))

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

    try:
        fc = httpx.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
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
    current = {
        "temperature_c": cur.get("temperature_2m"),
        "humidity_percent": cur.get("relative_humidity_2m"),
        "wind_kph": cur.get("wind_speed_10m"),
        "condition": _condition(cur.get("weather_code")),
    }
    daily_out = []
    for i, date in enumerate(daily.get("time", [])):
        precip = (daily.get("precipitation_probability_max") or [None])[i]
        daily_out.append({
            "date": date,
            "max_c": (daily.get("temperature_2m_max") or [None])[i],
            "min_c": (daily.get("temperature_2m_min") or [None])[i],
            "precip_probability": precip,
            "condition": _condition((daily.get("weather_code") or [None])[i]),
        })

    first = daily_out[0] if daily_out else {}
    human = (
        f"In {label} it's currently {current['temperature_c']}°C and "
        f"{current['condition']} with {current['wind_kph']} km/h winds"
    )
    if first:
        human += (
            f"; {'today' if days == 1 else first['date']} expect a high of "
            f"{first['max_c']}°C and a low of {first['min_c']}°C with a "
            f"{first['precip_probability']}% chance of precipitation."
        )

    return {"city": label, "current": current, "daily": daily_out, "human": human}
