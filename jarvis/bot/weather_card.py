"""The weather card's structured view (WS-15 PR 2, plan S1/S4/S6).

`weather_view(data)` turns one `weather_report` pseudo-tool result
({"weather": <weather_at/get_weather dict>, "radar": <radar dict or None>,
"place": <optional place dict>}) into the display-ready object the native
card renders (JarvisKit `WeatherCard`, schema 1): strings already in the
user's units, a symbol name per condition, and the radar layers for the
map. Pure: no network. The same view serves both paths — local_weather
(this device's location) and the analyst's named-place calls merged by
WeatherReportMerger — so "what's the weather" and "weather in Alpharetta"
render the same card.

Radar (plan G-1/G-3, verified from the Mac on 2026-09-29): inside the lower
48 states, the NOAA NEXRAD composite via Iowa Environmental Mesonet
(`/cache/` tiles, current plus 5-50 minute frames, real data to zoom 8).
Elsewhere, the RainViewer frame the radar tool already fetched (zoom 7
since RainViewer's 2026 limits). The app enlarges the last native zoom
rather than showing nothing past it.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

IEM_TEMPLATE = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/{layer}/{{z}}/{{x}}/{{y}}.png"
IEM_ATTRIBUTION = "Radar: NOAA NEXRAD via Iowa Environmental Mesonet"
RAINVIEWER_ATTRIBUTION = "Radar: RainViewer"
IEM_MAX_ZOOM = 8
RAINVIEWER_MAX_ZOOM = 7
# The lower 48 states, where the IEM NEXRAD composite has coverage.
CONUS = (24.0, 50.0, -125.0, -66.0)

SYMBOLS = (
    (("thunder", "t-storm", "tstorm"), "cloud.bolt.rain.fill"),
    (("snow", "sleet", "flurr", "ice"), "cloud.snow.fill"),
    (("rain", "shower", "drizzle"), "cloud.rain.fill"),
    (("fog", "haze", "smoke", "mist"), "cloud.fog.fill"),
    (("partly", "mostly sunny", "mostly clear", "few clouds"), "cloud.sun.fill"),
    (("cloud", "overcast"), "cloud.fill"),
    (("wind", "breez"), "wind"),
    (("sun", "clear", "fair"), "sun.max.fill"),
)


def symbol_for(condition: str) -> str:
    text = (condition or "").lower()
    for words, symbol in SYMBOLS:
        if any(word in text for word in words):
            return symbol
    return "cloud.sun.fill"


def in_conus(lat: float, lon: float) -> bool:
    south, north, west, east = CONUS
    return south <= lat <= north and west <= lon <= east


def radar_layers(lat: float | None, lon: float | None, radar: dict | None) -> dict | None:
    """IEM inside the lower 48; otherwise RainViewer from the radar tool's
    own tile URLs; None when neither is available."""
    if lat is not None and lon is not None and in_conus(lat, lon):
        layers = [f"nexrad-n0q-m{minutes:02d}m-900913" for minutes in range(50, 0, -5)]
        labels = [f"{minutes} min ago" for minutes in range(50, 0, -5)]
        layers.append("nexrad-n0q-900913")
        labels.append("now")
        return {
            "provider": "iem",
            "max_native_zoom": IEM_MAX_ZOOM,
            "frames": [{"label": label, "template": IEM_TEMPLATE.format(layer=layer)}
                       for layer, label in zip(layers, labels)],
            "attribution": IEM_ATTRIBUTION,
        }
    tiles = (radar or {}).get("tiles") or []
    first = tiles[0] if tiles and isinstance(tiles[0], str) else ""
    match = re.match(r"^(https://[^?#]+?)/512/\d+/\d+/\d+/(.+)$", first)
    if not match:
        return None
    template = f"{match.group(1)}/256/{{z}}/{{x}}/{{y}}/{match.group(2)}"
    return {
        "provider": "rainviewer",
        "max_native_zoom": RAINVIEWER_MAX_ZOOM,
        "frames": [{"label": "latest", "template": template}],
        "attribution": RAINVIEWER_ATTRIBUTION,
    }


def _deg(value: Any) -> str | None:
    return f"{round(value)}°" if isinstance(value, (int, float)) else None


def _pct(value: Any) -> str | None:
    return f"{round(value)}%" if isinstance(value, (int, float)) else None


def _day_name(label: str) -> str:
    text = (label or "").strip()
    try:
        return datetime.fromisoformat(text[:10]).strftime("%a")
    except ValueError:
        pass
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        if text == day:
            return day[:3]
    return text or "Today"


def _hour_label(start: str) -> str:
    try:
        stamp = datetime.fromisoformat(str(start))
    except ValueError:
        return ""
    hour = stamp.hour % 12 or 12
    return f"{hour} {'AM' if stamp.hour < 12 else 'PM'}"


def weather_view(data: dict) -> dict | None:
    weather = data.get("weather") if isinstance(data.get("weather"), dict) else None
    if not weather:
        return None
    radar = data.get("radar") if isinstance(data.get("radar"), dict) else None
    place_in = data.get("place") if isinstance(data.get("place"), dict) else {}
    metric = weather.get("units") == "metric"
    s = "c" if metric else "f"

    lat = weather.get("lat", (radar or {}).get("lat"))
    lon = weather.get("lon", (radar or {}).get("lon"))
    lat = float(lat) if isinstance(lat, (int, float)) else None
    lon = float(lon) if isinstance(lon, (int, float)) else None
    place = {
        "label": str(place_in.get("label") or weather.get("city") or ""),
        "lat": lat, "lon": lon,
        "source": str(place_in.get("source") or "named"),
        "approximate": bool(place_in.get("approximate", False)),
    }

    current = weather.get("current") or {}
    now = {
        "temp": _deg(current.get(f"temperature_{s}")),
        "condition": str(current.get("condition") or ""),
        "humidity": _pct(current.get("humidity_percent")),
        "wind": current.get("wind") or (
            f"{current['wind_kph']} km/h" if current.get("wind_kph") is not None else None),
        "symbol": symbol_for(str(current.get("condition") or "")),
    }
    days = []
    for d in weather.get("daily") or []:
        if not isinstance(d, dict):
            continue
        days.append({
            "name": _day_name(str(d.get("date") or "")),
            "high": _deg(d.get(f"max_{s}")),
            "low": _deg(d.get(f"min_{s}")),
            "pop": _pct(d.get("precip_probability")),
            "condition": str(d.get("condition") or ""),
            "symbol": symbol_for(str(d.get("condition") or "")),
        })
    hourly = []
    for h in (weather.get("hourly") or [])[:12]:
        if not isinstance(h, dict):
            continue
        hourly.append({
            "label": _hour_label(str(h.get("start") or "")),
            "temp": _deg(h.get(f"temp_{s}")),
            "pop": _pct(h.get("pop")),
            "symbol": symbol_for(str(h.get("condition") or "")),
        })
    alerts = [
        {"event": str(a.get("event")), "headline": str(a.get("headline") or "")}
        for a in (weather.get("alerts") or []) if isinstance(a, dict) and a.get("event")
    ]
    source = str(weather.get("source") or "")
    return {
        "schema": 1,
        "place": place,
        "units": "metric" if metric else "imperial",
        "now": now,
        "days": days,
        "hourly": hourly,
        "alerts": alerts,
        "radar": radar_layers(lat, lon, radar),
        "summary": str(weather.get("human") or ""),
        "attribution": ("Forecast: Open-Meteo" if source == "open-meteo"
                        else "Forecast: National Weather Service"),
    }
