"""Where the user is right now — MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 2 D4
(Larry's decision D-L6, 2026-09-25).

The order is fixed:
  1. a fresh fix from the device Larry is talking through, asked for on
     demand over this session's own app-message channel;
  2. IP geolocation, spoken as approximate;
  3. "not available", with the reason.
There is no memory fallback and no last-known fix. On a protected turn step 2
is skipped, because the IP lookup leaves the machine.

Why per request rather than the sidecar's stored device location: the fix
must come from the client in THIS conversation. Today the server and client
are the same MacBook Air; after the Mac mini move (with an iPhone client over
Tailscale), the server's own location would be the wrong answer.

Protocol (client support is announced, never assumed):
  client -> bot  {"type": "location/hello", "version": 1, "authorization": "..."}
  bot -> client  {"type": "location/request", "version": 1, "request_id": "...",
                  "accuracy_m": 100}
  client -> bot  {"type": "location/result", "version": 1, "request_id": "...",
                  "ok": true, "lat": .., "lon": .., "accuracy_m": .., "age_s": ..,
                  "label": "Alpharetta, GA"}
              or {"type": "location/result", ..., "ok": false,
                  "error": "denied" | "unavailable"}
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

HELLO_TYPE = "location/hello"
REQUEST_TYPE = "location/request"
RESULT_TYPE = "location/result"
PROTOCOL_VERSION = 1

REQUEST_TIMEOUT_S = 8.0
DESIRED_ACCURACY_M = 100
# A fix older than this is not "where you are right now" (D-L6: no
# last-known fix). CoreLocation can hand back a cached fix; ten minutes
# keeps a parked Mac answering and a stale one out.
DEVICE_FIX_MAX_AGE_S = 600
# Above this the fix is spoken as approximate, the same word IP gets.
APPROXIMATE_ACCURACY_M = 1000

REASONS = {
    "no_device": "the app you're talking through hasn't shared a location",
    "denied": "Location Services is off for Mortimer",
    "unavailable": "the Mac couldn't get a location fix",
    "timeout": "the Mac didn't answer in time",
    "stale": "the Mac only had an old fix",
    "invalid": "the Mac sent a location that didn't make sense",
    "offline": "there's no internet connection",
    "lookup_failed": "the internet location lookup failed",
}
CLIENT_ERRORS = frozenset({"denied", "unavailable"})


class DeviceLocation:
    """Per-session state: whether the client can answer, and the pending
    requests. `send` is an async callable taking one app message."""

    def __init__(self, send: Callable[[dict], Awaitable[None]]) -> None:
        self._send = send
        self._waiters: dict[str, asyncio.Future] = {}
        self.client: dict | None = None

    @property
    def supported(self) -> bool:
        return self.client is not None

    def handle_message(self, msg: Any) -> bool:
        """Consume a location/* message. True when it was one."""
        if not isinstance(msg, dict):
            return False
        kind = msg.get("type")
        if kind == HELLO_TYPE:
            self.client = {"authorization": str(msg.get("authorization") or "unknown")}
            logger.info("device_location_hello authorization=%s",
                        self.client["authorization"])
            return True
        if kind != RESULT_TYPE:
            return False
        request_id = msg.get("request_id")
        future = self._waiters.get(request_id) if isinstance(request_id, str) else None
        if future is not None and not future.done():
            future.set_result(dict(msg))
        return True

    async def request_fix(self, timeout: float = REQUEST_TIMEOUT_S) -> dict:
        """{"ok": True, lat, lon, accuracy_m, age_s, label} or
        {"ok": False, "reason": <REASONS key>}."""
        if not self.supported:
            return {"ok": False, "reason": "no_device"}
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters[request_id] = future
        try:
            await self._send({"type": REQUEST_TYPE, "version": PROTOCOL_VERSION,
                              "request_id": request_id,
                              "accuracy_m": DESIRED_ACCURACY_M})
            raw = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"ok": False, "reason": "timeout"}
        except Exception:  # noqa: BLE001 — a send failure is "no answer"
            logger.exception("device_location_request_failed")
            return {"ok": False, "reason": "timeout"}
        finally:
            self._waiters.pop(request_id, None)
        return parse_result(raw)


def parse_result(raw: dict) -> dict:
    if not raw.get("ok"):
        error = str(raw.get("error") or "unavailable")
        return {"ok": False, "reason": error if error in CLIENT_ERRORS else "unavailable"}
    try:
        lat = float(raw["lat"])
        lon = float(raw["lon"])
        accuracy = float(raw.get("accuracy_m") or 0.0)
        age = max(0.0, float(raw.get("age_s") or 0.0))
    except (KeyError, TypeError, ValueError):
        return {"ok": False, "reason": "invalid"}
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or accuracy < 0:
        return {"ok": False, "reason": "invalid"}
    if age > DEVICE_FIX_MAX_AGE_S:
        return {"ok": False, "reason": "stale"}
    return {"ok": True, "lat": lat, "lon": lon, "accuracy_m": accuracy,
            "age_s": age, "label": str(raw.get("label") or "").strip()}


async def resolve_location(
    device: DeviceLocation | None,
    *,
    protected: bool,
    ip_lookup: Callable[[], Awaitable[dict]],
) -> dict:
    """D-L6 order. Returns {"ok": True, "source": "device"|"ip", ...} or
    {"ok": False, "reason": ..., "device_reason": ...}."""
    fix = await device.request_fix() if device is not None else {
        "ok": False, "reason": "no_device"}
    if fix.get("ok"):
        return {"source": "device", **fix}
    device_reason = fix["reason"]
    if protected:
        logger.info("location_resolved source=none reason=%s ip=skipped_protected",
                    device_reason)
        return {"ok": False, "reason": device_reason, "device_reason": device_reason,
                "ip_skipped": True}
    from jarvis.ambient_weather import LocationLookupError

    try:
        ip = await ip_lookup()
    except LocationLookupError as exc:
        logger.info("location_resolved source=none device=%s ip=%s",
                    device_reason, exc.reason)
        return {"ok": False, "reason": exc.reason, "device_reason": device_reason}
    except Exception:  # noqa: BLE001
        logger.exception("location_ip_lookup_crashed")
        return {"ok": False, "reason": "lookup_failed", "device_reason": device_reason}
    logger.info("location_resolved source=ip device=%s", device_reason)
    return {"ok": True, "device_reason": device_reason, **ip, "source": "ip"}


def _place(result: dict) -> str:
    label = str(result.get("label") or "").strip()
    return label or f"coordinates {float(result['lat']):.4f}, {float(result['lon']):.4f}"


def summarize_location(result: dict) -> str:
    """The text the Supervisor relays, built in code (never by a model)."""
    if result.get("ok") and result.get("source") == "device":
        accuracy = float(result.get("accuracy_m") or 0.0)
        approx = accuracy > APPROXIMATE_ACCURACY_M
        detail = "from this device's own location"
        if accuracy:
            detail += f", accurate to about {int(round(accuracy, -1)) or int(accuracy)} m"
        age = float(result.get("age_s") or 0.0)
        if age >= 60:
            detail += f", fixed {int(age // 60)} minute(s) ago"
        where = ("approximately " if approx else "") + _place(result)
        return f"Location: {where} ({detail})."
    if result.get("ok") and result.get("source") == "ip":
        because = REASONS.get(str(result.get("device_reason")), "the device gave no location")
        return (f"Location: approximately {_place(result)} (from the internet "
                f"connection, city-level; {because}). Say it is approximate.")
    reason = str(result.get("reason") or "lookup_failed")
    if reason == "offline":
        return "Location isn't available: there's no internet connection."
    text = f"Location isn't available: {REASONS.get(reason, REASONS['lookup_failed'])}"
    device_reason = result.get("device_reason")
    if device_reason and device_reason != reason:
        text += f", and {REASONS.get(str(device_reason), 'the device gave no location')}"
    if result.get("ip_skipped"):
        text += " (the internet lookup is not used on a private turn)"
    return text + ". Do not guess a place."
