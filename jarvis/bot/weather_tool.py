"""local_weather — the Supervisor's direct tool for weather where the user is
right now (WS-15, MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md S3).

Why a direct tool (Larry chose Option A, 2026-09-29): "current" weather used
to be a delegation whose task text the voice model wrote, and it wrote the
place from memory — "typically in Spartanburg, SC" on 09-29 while Larry was
at Folly Beach, and "Folly Beach, SC area based on recent sessions" later
the same day (right by luck, still not a live fix). Here the place is
resolved in code, in the same order as "where am I" (D-L6): this session's
device fix, then the internet connection (said as approximate), then "not
available". The tool takes no place argument at all, so no model can supply
one.

It fetches conditions, 7 days, the next hours and NWS alerts for those
coordinates (mcp_web.logic.weather_at) plus radar (radar_at), pushes one
weather card through the existing display path, and returns a summary
built in code (never by a model) for the Supervisor to relay.

Protected turns: weather leaves the machine (weather.gov, radar tiles), so
it is refused on a protected turn — the same rule system_status applies to
its external topics (I3).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from typing import Any, Awaitable, Callable

from jarvis.bot.device_location import APPROXIMATE_ACCURACY_M, REASONS
from jarvis.bot.display import build_display_payload
from jarvis.bot.status_tool import _turn_is_protected
from jarvis.bot.weather_reuse import (
    WeatherReuseBridge, current_weather_reuse, local_weather_subject_key, weather_display_metadata,
)

LOCAL_WEATHER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "local_weather",
        "description": (
            "Weather where the user is right now: current conditions, today, the rest of the "
            "week, and any NWS alerts, for this device's own location (then the internet "
            "connection, approximate). Also puts a weather card with radar on screen. Takes "
            "no place: never pass or guess one. For a place the user names, delegate to the "
            "analyst instead."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

PROTECTED_TURN_REFUSAL = (
    "local_weather failed: protected turn cannot call external tool server. "
    "Say weather isn't available on a private turn."
)
WET_WORDS = ("rain", "shower", "storm", "thunder", "snow", "sleet", "drizzle")
WET_POP = 40


def _unavailable(result: dict) -> str:
    reason = str(result.get("reason") or "lookup_failed")
    text = "local_weather: location isn't available"
    if reason in REASONS:
        text += f" ({REASONS[reason]})"
    if result.get("ip_skipped"):
        text += " and the internet lookup is not used on a private turn"
    return text + ". Ask the user which place to check. Do not guess a place."


def _short_day(label: str) -> str:
    """'Wednesday' -> 'Wed'; '2026-10-01' -> 'Thu'; other NWS labels kept."""
    text = (label or "").strip()
    try:
        return date.fromisoformat(text[:10]).strftime("%a")
    except ValueError:
        pass
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        if text == day:
            return day[:3]
    return text


def _is_wet(day: dict) -> bool:
    pop = day.get("precip_probability")
    if isinstance(pop, (int, float)) and pop >= WET_POP:
        return True
    condition = str(day.get("condition") or "").lower()
    return any(word in condition for word in WET_WORDS)


def summarize_local_weather(
    weather: dict, *, place: str, source: str, approximate: bool,
    card_sent: bool, radar_ok: bool,
) -> str:
    """The text the Supervisor relays, built in code. Pure."""
    metric = weather.get("units") == "metric"
    unit = "°C" if metric else "°F"
    suffix = "c" if metric else "f"
    if source == "device" and not approximate:
        where = f"{place} (this device's location)"
    elif source == "device":
        where = f"approximately {place} (this device's location, low accuracy)"
    else:
        where = f"approximately {place} (from the internet connection; say it is approximate)"
    parts = [f"Weather for {where}."]

    for alert in (weather.get("alerts") or [])[:2]:
        if isinstance(alert, dict) and alert.get("event"):
            parts.append(f"Active alert: {alert['event']}.")

    current = weather.get("current") or {}
    temp = current.get(f"temperature_{suffix}")
    now = f"Now {temp}{unit}" if temp is not None else "Now"
    if current.get("condition"):
        now += f", {current['condition']}"
    if current.get("humidity_percent") is not None:
        now += f", humidity {current['humidity_percent']}%"
    if current.get("wind"):
        now += f", wind {current['wind']}"
    parts.append(now + ".")

    daily = [d for d in (weather.get("daily") or []) if isinstance(d, dict)]
    if daily:
        today = daily[0]
        hi, lo = today.get(f"max_{suffix}"), today.get(f"min_{suffix}")
        bits = [f"{_short_day(str(today.get('date') or 'Today'))}:"]
        if today.get("condition"):
            bits.append(str(today["condition"]).lower() + ",")
        if hi is not None:
            bits.append(f"high {hi}{unit}")
        if lo is not None:
            bits.append(f"low {lo}{unit}")
        if today.get("precip_probability") is not None:
            bits.append(f"{today['precip_probability']}% chance of rain")
        parts.append(" ".join(bits).rstrip(",") + ".")
        rest = daily[1:]
        if rest:
            highs = [d.get(f"max_{suffix}") for d in rest if d.get(f"max_{suffix}") is not None]
            wet = [_short_day(str(d.get("date") or "")) for d in rest if _is_wet(d)]
            week = f"Next {len(rest)} days:"
            if highs:
                week += (f" highs {min(highs)} to {max(highs)}{unit};" if min(highs) != max(highs)
                         else f" highs near {highs[0]}{unit};")
            week += (f" rain or storms possible {', '.join(wet)}." if wet
                     else " no rain expected.")
            parts.append(week)

    if card_sent:
        parts.append("A weather card " + ("with radar " if radar_ok else "without radar ")
                     + "was sent to the screen; if asked about radar, it is on that card.")
    parts.append("Relay this in under 40 words; do not add any place or detail not stated here.")
    return " ".join(parts)


def build_local_weather_tool(
    *,
    locate: Callable[[bool], Awaitable[dict]],
    push_display: Callable[[dict], Awaitable[Any]] | None = None,
    fetch_weather: Callable[..., dict] | None = None,
    fetch_radar: Callable[..., dict] | None = None,
    is_protected: Callable[[], bool] | None = None,
    reuse: WeatherReuseBridge | None = None,
) -> tuple[dict, Callable[[dict], Any]]:
    """Return (openai_tool_schema, async_handler) for local_weather.
    `locate(protected)` is the session's device-first resolver
    (device_location.resolve_location); `push_display(payload)` sends a
    display payload to the app. The fetchers default to mcp_web's logic and
    are the test seams."""
    if fetch_weather is None or fetch_radar is None:
        from mcp_servers.mcp_web.logic import radar_at, weather_at
        fetch_weather = fetch_weather or weather_at
        fetch_radar = fetch_radar or radar_at
    protected_now = is_protected or _turn_is_protected

    async def handler(arguments: dict) -> str:
        bridge = reuse if reuse is not None else current_weather_reuse.get()

        def blocked() -> bool:
            return protected_now() or (bridge is not None and bridge.is_protected())

        if blocked():
            return PROTECTED_TURN_REFUSAL
        try:
            found = await locate(False)
        except Exception:  # noqa: BLE001 — never raised into the turn
            found = {"ok": False, "reason": "lookup_failed"}
        if not isinstance(found, dict) or not found.get("ok"):
            return _unavailable(found if isinstance(found, dict) else {})
        try:
            lat, lon = float(found["lat"]), float(found["lon"])
        except (KeyError, TypeError, ValueError):
            return _unavailable({"reason": "lookup_failed"})
        label = str(found.get("label") or "").strip() or f"{lat:.3f}, {lon:.3f}"
        source = str(found.get("source") or "")
        accuracy = float(found.get("accuracy_m") or 0.0)
        approximate = source != "device" or accuracy > APPROXIMATE_ACCURACY_M
        subject_key = local_weather_subject_key(found)
        if blocked():
            return PROTECTED_TURN_REFUSAL
        if bridge is not None and subject_key is not None:
            from mcp_servers.mcp_web.logic import _configured_units

            cached = await bridge.lookup(subject_key=subject_key, tool="local_weather", days=7,
                                         units=_configured_units())
            if blocked():
                return PROTECTED_TURN_REFUSAL
            if cached.status == "refused":
                return (f"local_weather failed: weather_reuse_{cached.code}. "
                        "The cached result could not be confirmed; say so, do not claim a new lookup.")
            if cached.status == "hit":
                # The native query already applies requested-result arrival
                # and adds a reference. A replay would duplicate that direct
                # tool reference, especially outside an originating agent run.
                weather = {**cached.source["weather"], "city": label}
                radar = cached.source.get("radar")
                radar_ok = isinstance(radar, dict) and not radar.get("error") and bool(radar.get("tiles"))
                from jarvis.bot.weather_card import weather_view
                view = weather_view({**cached.source, "weather": weather})
                if view is not None:
                    radar_ok = view.get("radar") is not None
                return summarize_local_weather(
                    weather, place=label, source=source, approximate=approximate,
                    card_sent=True, radar_ok=radar_ok,
                ) + " Reused the retained weather card; no new weather lookup was made."

        try:
            def fetched(call: Callable[..., dict], *args: Any) -> tuple[dict, float]:
                result = call(*args)
                return result, time.time()

            (weather, weather_ts), (radar, radar_ts) = await asyncio.gather(
                asyncio.to_thread(fetched, fetch_weather, lat, lon, label, 7),
                asyncio.to_thread(fetched, fetch_radar, lat, lon, label),
            )
        except Exception:  # noqa: BLE001
            return "local_weather failed: the weather lookup failed. Say so; do not guess."
        if blocked():
            return PROTECTED_TURN_REFUSAL
        if not isinstance(weather, dict) or weather.get("error"):
            why = weather.get("error") if isinstance(weather, dict) else ""
            return f"local_weather failed: {why or 'no weather data'} Say so; do not guess."
        # The card and the speech name the place the DEVICE reported
        # (e.g. "Folly Beach, SC"), not weather.gov's nearest-city label.
        weather = {**weather, "city": label}
        radar_ok = isinstance(radar, dict) and not radar.get("error") and bool(radar.get("tiles"))

        card_sent = False
        if push_display is not None:
            original_source = {
                "weather": weather,
                "radar": {**radar, "city": label} if radar_ok else None,
                "place": {"label": label, "source": source, "approximate": approximate},
            }
            payload = build_display_payload(
                agent="mortimer", display_name="Mortimer", tool="weather_report",
                arguments={},
                result_str=json.dumps(original_source),
            )
            if payload is not None:
                # A paired fetch cannot renew its older half. Neither a
                # provider observation nor a radar frame is fetch timing.
                fetch_ts = min(weather_ts, radar_ts) if radar_ok else weather_ts
                payload.update(weather_display_metadata(subject_key, original_source, fetch_ts))
                if bridge is not None:
                    payload["data_policy"] = "approved_external"
                # PR 2: inside the lower 48 the card's map uses NOAA radar
                # tiles directly, so it has radar even if RainViewer failed.
                if isinstance(payload.get("weather"), dict):
                    radar_ok = payload["weather"].get("radar") is not None
                try:
                    await push_display(payload)
                    card_sent = True
                except Exception:  # noqa: BLE001 — the spoken answer still stands
                    card_sent = False
        return summarize_local_weather(
            weather, place=label, source=source, approximate=approximate,
            card_sent=card_sent, radar_ok=radar_ok,
        )

    return LOCAL_WEATHER_SCHEMA, handler
