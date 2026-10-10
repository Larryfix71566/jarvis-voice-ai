"""Request-scoped native weather reuse, with no Python weather cache.

The native WorkspaceStore alone decides freshness and owns retained source
data. This bridge validates its bounded reply and carries one-use dispatch
provenance to the existing display merger; it never stores reusable weather.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import math
import time
from typing import Any, Callable, Iterator
import unicodedata

from jarvis.bot.sensitive_turn import is_sensitive
from jarvis.runlog.context import get_run_id

MAX_WEATHER_SOURCE = 16 * 1024
MAX_SUBJECT_KEY = 200
MAX_DISPATCH_METADATA = 128
WEATHER_TOOLS = frozenset({"local_weather", "get_weather", "get_weather_radar"})


def canonical_weather_subject(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    return value or None


def named_weather_subject_key(city: Any) -> str | None:
    subject = canonical_weather_subject(city)
    key = f"weather:named:{subject}" if subject is not None else None
    return key if key is not None and len(key) <= MAX_SUBJECT_KEY else None


def local_weather_subject_key(found: dict) -> str | None:
    """Bind local reuse to a new device-first fix, never its remembered label."""
    try:
        lat, lon = float(found["lat"]), float(found["lon"])
        accuracy = float(found.get("accuracy_m") or 0)
    except (TypeError, ValueError, KeyError, OverflowError):
        return None
    if (not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180
            or not math.isfinite(accuracy) or accuracy < 0):
        return None
    source = found.get("source")
    if not isinstance(source, str) or source not in {"device", "ip"}:
        return None
    from jarvis.bot.device_location import APPROXIMATE_ACCURACY_M
    approximate = source != "device" or accuracy > APPROXIMATE_ACCURACY_M
    # Existing weather.gov requests format coordinates with this precision.
    # Moving within one place label therefore cannot reuse another grid fix.
    return f"weather:local:{source}:{int(approximate)}:{lat:.4f}:{lon:.4f}"


def valid_weather_source(source: Any) -> dict | None:
    if not isinstance(source, dict) or set(source) - {"weather", "radar", "place", "subject_aliases"}:
        return None
    if any(source.get(key) is not None and not isinstance(source[key], dict)
           for key in ("weather", "radar", "place")):
        return None
    if not any(isinstance(source.get(key), dict) for key in ("weather", "radar")):
        return None
    aliases = source.get("subject_aliases", [])
    if (not isinstance(aliases, list) or len(aliases) > 8
            or any(not isinstance(alias, str) or len(alias) > 120
                   or canonical_weather_subject(alias) != alias for alias in aliases)):
        return None
    try:
        encoded = json.dumps(source, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_WEATHER_SOURCE:
            return None
        return json.loads(encoded)
    except (TypeError, ValueError, OverflowError):
        return None


def valid_weather_timing(ts: Any, fresh_until: Any) -> tuple[float, float] | None:
    if (isinstance(ts, bool) or isinstance(fresh_until, bool)
            or not isinstance(ts, (int, float)) or not isinstance(fresh_until, (int, float))):
        return None
    try:
        if not math.isfinite(ts) or not math.isfinite(fresh_until) or not ts <= fresh_until <= ts + 900:
            return None
    except OverflowError:
        return None
    return float(ts), float(fresh_until)


def weather_display_metadata(subject_key: Any, source: Any, ts: Any,
                             fresh_until: Any = None) -> dict:
    """Invalid cache fields cannot lose a safe key or proven original fetch time."""
    if not isinstance(subject_key, str) or not subject_key or len(subject_key) > MAX_SUBJECT_KEY:
        return {}
    metadata = {"subject_key": subject_key}
    if fresh_until is None and not isinstance(ts, bool) and isinstance(ts, (int, float)):
        fresh_until = ts + 900
    valid_source = valid_weather_source(source)
    timing = valid_weather_timing(ts, fresh_until)
    if timing is not None:
        metadata["ts"] = timing[0]
    if valid_source is not None and timing is not None:
        metadata.update(weather_source=valid_source, fresh_until=timing[1])
    return metadata


@dataclass(frozen=True)
class WeatherReuseOutcome:
    status: str
    code: str
    source: dict | None = None
    ts: float | None = None
    fresh_until: float | None = None


_MISS_CODES = frozenset({"no_matching_result", "cache_missing", "cache_expired", "cache_incomplete"})
_REFUSAL_CODES = frozenset({
    "ambiguous_result", "stale_selection", "result_unavailable", "protected_result",
    "protected_turn", "not_ready", "disconnected", "not_confirmed", "timeout",
    "invalid_request", "invalid_reply", "query_failed", "unsupported",
})


class WeatherReuseBridge:
    def __init__(self, query: Callable[..., Any], *, is_protected: Callable[[], bool] | None = None) -> None:
        self._query = query
        self._protected = is_protected or is_sensitive
        # Only timing/key provenance, consumed once. Never weather bodies/TTL
        # candidates; run cancellation cannot leave an unbounded result cache.
        self._dispatch: OrderedDict[tuple[str, str, str], dict] = OrderedDict()

    def is_protected(self) -> bool:
        """Read current eligibility before even requesting a device/IP fix."""
        try:
            return self._protected() is not False
        except Exception:  # noqa: BLE001 — broken policy wiring fails closed
            return True

    async def lookup(self, *, subject_key: str, tool: str, days: int, units: str,
                     run_id: str | None = None) -> WeatherReuseOutcome:
        if self.is_protected():
            return WeatherReuseOutcome("refused", "protected_turn")
        if (not isinstance(subject_key, str) or not subject_key or len(subject_key) > MAX_SUBJECT_KEY
                or not isinstance(tool, str) or tool not in WEATHER_TOOLS
                or type(days) is not int or not 1 <= days <= 7
                or not isinstance(units, str) or units not in {"metric", "imperial"}
                or (run_id is not None and (not isinstance(run_id, str) or len(run_id) > 120))):
            return WeatherReuseOutcome("refused", "invalid_request")
        try:
            reply = await asyncio.wait_for(self._query(subject_key=subject_key, tool=tool,
                days=days, units=units, run_id=run_id), timeout=5.0)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            return WeatherReuseOutcome("refused", "timeout")
        except Exception:  # noqa: BLE001 — no native error body in model/log output
            return WeatherReuseOutcome("refused", "query_failed")
        if self.is_protected():
            return WeatherReuseOutcome("refused", "protected_turn")
        if isinstance(reply, WeatherReuseOutcome):
            reply = {"status": reply.status, "code": reply.code, "weather_source": reply.source,
                     "ts": reply.ts, "fresh_until": reply.fresh_until}
        if not isinstance(reply, dict) or set(reply) - {"status", "code", "weather_source", "ts", "fresh_until"}:
            return WeatherReuseOutcome("refused", "invalid_reply")
        status, code = reply.get("status"), reply.get("code")
        if status in ("miss", "refused") and any(reply.get(key) is not None
                for key in ("weather_source", "ts", "fresh_until")):
            return WeatherReuseOutcome("refused", "invalid_reply")
        if status == "miss" and isinstance(code, str) and code in _MISS_CODES:
            return WeatherReuseOutcome("miss", code)
        if status == "refused" and isinstance(code, str) and code in _REFUSAL_CODES:
            return WeatherReuseOutcome("refused", code)
        if status != "hit" or code != "cache_hit":
            return WeatherReuseOutcome("refused", "invalid_reply")
        source = valid_weather_source(reply.get("weather_source"))
        timing = valid_weather_timing(reply.get("ts"), reply.get("fresh_until"))
        if source is None or timing is None or not self._complete(source, tool=tool, days=days, units=units):
            return WeatherReuseOutcome("refused", "invalid_reply")
        if tool != "local_weather":
            self.record_dispatch(tool=tool, subject_key=subject_key, run_id=run_id,
                                 ts=timing[0], fresh_until=timing[1], reused=True)
        return WeatherReuseOutcome("hit", "cache_hit", source, *timing)

    @staticmethod
    def _complete(source: dict, *, tool: str, days: int, units: str) -> bool:
        if tool == "get_weather_radar":
            radar = source.get("radar")
            return (isinstance(radar, dict) and not radar.get("error") and radar.get("ok") is not False
                    and isinstance(radar.get("tiles"), list) and bool(radar["tiles"])
                    and all(isinstance(url, str) and url for url in radar["tiles"]))
        weather = source.get("weather")
        return (isinstance(weather, dict) and not weather.get("error") and weather.get("ok") is not False
                and weather.get("units") == units
                and isinstance(weather.get("current"), dict) and bool(weather["current"])
                and isinstance(weather.get("daily"), list) and len(weather["daily"]) >= days
                and all(isinstance(day, dict) for day in weather["daily"][:days]))

    def record_dispatch(self, *, tool: str, subject_key: str, run_id: str | None = None,
                        ts: Any = None, fresh_until: Any = None, reused: bool = False) -> None:
        run_id = run_id if run_id is not None else get_run_id() or ""
        ts = time.time() if ts is None else ts
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            return
        timing = valid_weather_timing(ts, ts + 900 if fresh_until is None else fresh_until)
        if (timing is None or not isinstance(run_id, str) or len(run_id) > 120
                or not isinstance(tool, str) or tool not in WEATHER_TOOLS
                or not isinstance(subject_key, str) or not subject_key or len(subject_key) > MAX_SUBJECT_KEY):
            return
        key = (run_id, tool, subject_key)
        self._dispatch[key] = {"subject_key": subject_key, "ts": timing[0], "fresh_until": timing[1],
                               "reused": reused is True}
        self._dispatch.move_to_end(key)
        while len(self._dispatch) > MAX_DISPATCH_METADATA:
            self._dispatch.popitem(last=False)

    def take_dispatch_metadata(self, *, tool: str, arguments: dict, run_id: str = "") -> dict | None:
        key = named_weather_subject_key(arguments.get("city"))
        return self._dispatch.pop((run_id, tool, key), None) if key is not None else None

    def clear(self) -> None:
        self._dispatch.clear()


current_weather_reuse: ContextVar[WeatherReuseBridge | None] = ContextVar("current_weather_reuse", default=None)


@contextmanager
def weather_reuse_scope(bridge: WeatherReuseBridge | None) -> Iterator[None]:
    token = current_weather_reuse.set(bridge)
    try:
        yield
    finally:
        current_weather_reuse.reset(token)
