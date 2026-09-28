"""Phase 2 D4 (MORTIMER_VOICE_WORKFLOWS_PLAN.md, Larry's decision D-L6):
where the user is right now. Device first, IP last and approximate, else
"not available" with the reason. No memory, no last-known fix."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from jarvis import ambient_weather as aw
from jarvis.bot import device_location as dl

FIX = {"type": "location/result", "version": 1, "ok": True, "lat": 34.0754,
       "lon": -84.2941, "accuracy_m": 65, "age_s": 4, "label": "Alpharetta, GA"}
IP = {"lat": 33.749, "lon": -84.388, "label": "Atlanta", "source": "ip"}


class Client:
    """A client that answers each location/request with `reply` (or never)."""

    def __init__(self, reply: dict | None, hello: bool = True):
        self.sent: list[dict] = []
        self.reply = reply
        self.device = dl.DeviceLocation(self.send)
        if hello:
            assert self.device.handle_message({"type": "location/hello", "version": 1,
                                               "authorization": "authorized"})

    async def send(self, message: dict) -> None:
        self.sent.append(message)
        if self.reply is not None:
            answer = dict(self.reply, request_id=message["request_id"])
            asyncio.get_running_loop().call_soon(self.device.handle_message, answer)


async def _ip_ok():
    return dict(IP)


def _ip_fails(reason):
    async def lookup():
        raise aw.LocationLookupError(reason)
    return lookup


async def _resolve(client, *, protected=False, ip=_ip_ok, timeout=None):
    if timeout is not None and client is not None:
        original = client.device.request_fix

        async def short():
            return await original(timeout=timeout)
        client.device.request_fix = short
    return await dl.resolve_location(client.device if client else None,
                                     protected=protected, ip_lookup=ip)


class TestOrder:
    async def test_device_fix_wins(self):
        client = Client(FIX)
        result = await _resolve(client)
        assert result["source"] == "device" and result["label"] == "Alpharetta, GA"
        sent = client.sent[0]
        assert sent["type"] == "location/request" and sent["version"] == 1
        assert sent["accuracy_m"] == 100 and isinstance(sent["request_id"], str)

    async def test_no_client_falls_to_ip(self):
        result = await _resolve(Client(FIX, hello=False))
        assert result["source"] == "ip" and result["device_reason"] == "no_device"

    async def test_location_services_off_falls_to_ip(self):
        result = await _resolve(Client({"type": "location/result", "ok": False, "error": "denied"}))
        assert result["source"] == "ip" and result["device_reason"] == "denied"

    async def test_no_answer_times_out_then_ip(self):
        result = await _resolve(Client(None), timeout=0.05)
        assert result["source"] == "ip" and result["device_reason"] == "timeout"

    async def test_old_fix_is_not_used(self):
        # D-L6: no last-known fix.
        result = await _resolve(Client(dict(FIX, age_s=dl.DEVICE_FIX_MAX_AGE_S + 1)))
        assert result["source"] == "ip" and result["device_reason"] == "stale"

    async def test_nonsense_coordinates_are_rejected(self):
        result = await _resolve(Client(dict(FIX, lat=123.0)))
        assert result["device_reason"] == "invalid"

    async def test_protected_turn_never_leaves_the_machine(self):
        called = []

        async def ip():
            called.append(True)
            return dict(IP)
        result = await _resolve(Client(FIX, hello=False), protected=True, ip=ip)
        assert result["ok"] is False and result["ip_skipped"] is True and called == []

    async def test_protected_turn_still_uses_the_device(self):
        result = await _resolve(Client(FIX), protected=True)
        assert result["source"] == "device"

    async def test_offline(self):
        result = await _resolve(Client(FIX, hello=False), ip=_ip_fails("offline"))
        assert result == {"ok": False, "reason": "offline", "device_reason": "no_device"}


class TestSpokenAnswer:
    def test_device(self):
        text = dl.summarize_location({"ok": True, "source": "device", **dl.parse_result(FIX)})
        assert text == "Location: Alpharetta, GA (from this device's own location, accurate to about 60 m)."

    def test_coarse_device_fix_is_approximate(self):
        fix = dl.parse_result(dict(FIX, accuracy_m=3000, age_s=150))
        text = dl.summarize_location({"ok": True, "source": "device", **fix})
        assert text.startswith("Location: approximately Alpharetta, GA")
        assert "fixed 2 minute(s) ago" in text

    def test_ip_is_approximate_and_says_why(self):
        text = dl.summarize_location({"ok": True, "source": "ip", "device_reason": "denied", **IP})
        assert text.startswith("Location: approximately Atlanta (from the internet connection, city-level; "
                               "Location Services is off for Mortimer)")
        assert "Say it is approximate." in text

    def test_offline_is_the_d_l6_sentence(self):
        assert dl.summarize_location({"ok": False, "reason": "offline", "device_reason": "no_device"}) \
            == "Location isn't available: there's no internet connection."

    def test_both_failed(self):
        text = dl.summarize_location({"ok": False, "reason": "lookup_failed", "device_reason": "denied"})
        assert text == ("Location isn't available: the internet location lookup failed, and "
                        "Location Services is off for Mortimer. Do not guess a place.")

    def test_private_turn(self):
        text = dl.summarize_location({"ok": False, "reason": "no_device", "device_reason": "no_device",
                                      "ip_skipped": True})
        assert "not used on a private turn" in text and text.endswith("Do not guess a place.")


class TestMessages:
    def test_unrelated_messages_are_not_consumed(self):
        device = dl.DeviceLocation(lambda m: None)
        assert device.handle_message({"type": "console/result"}) is False
        assert device.handle_message(None) is False
        assert device.supported is False

    def test_late_or_unknown_result_is_ignored(self):
        device = dl.DeviceLocation(lambda m: None)
        assert device.handle_message(dict(FIX, request_id="nobody-waiting")) is True


class TestIpLocation:
    def test_success(self):
        out = aw.ip_location(lambda url: {"status": "success", "lat": 33.7, "lon": -84.4, "city": "Atlanta"})
        assert out == {"lat": 33.7, "lon": -84.4, "label": "Atlanta", "source": "ip"}

    def test_no_connection_is_offline(self):
        def fetch(url):
            raise httpx.ConnectError("nodename nor servname provided")
        with pytest.raises(aw.LocationLookupError) as exc:
            aw.ip_location(fetch)
        assert exc.value.reason == "offline"

    @pytest.mark.parametrize("answer", [{"status": "fail"}, {"status": "success"}, None])
    def test_bad_answer_is_lookup_failed(self, answer):
        with pytest.raises(aw.LocationLookupError) as exc:
            aw.ip_location(lambda url: answer)
        assert exc.value.reason == "lookup_failed"

    def test_weather_resolver_unchanged_on_failure(self, monkeypatch):
        monkeypatch.delenv("JARVIS_WEATHER_LAT", raising=False)
        monkeypatch.delenv("JARVIS_WEATHER_LON", raising=False)
        monkeypatch.setattr(aw, "get_device_location", lambda: None)

        def fetch(url):
            raise httpx.ConnectError("offline")
        assert aw._resolve_location(fetch) is None


class TestSystemStatusTool:
    async def test_location_topic_uses_the_session_resolver(self):
        from jarvis.bot.status_tool import build_system_status_tool

        seen = []

        async def location(protected):
            seen.append(protected)
            return "Location: Alpharetta, GA (from this device's own location)."
        _, handler = build_system_status_tool(location=location)
        assert await handler({"topic": "location"}) == \
            "Location: Alpharetta, GA (from this device's own location)."
        assert seen == [False]

    async def test_resolver_crash_is_an_answer_not_an_exception(self):
        from jarvis.bot.status_tool import build_system_status_tool

        async def location(protected):
            raise RuntimeError("boom")
        _, handler = build_system_status_tool(location=location)
        assert (await handler({"topic": "location"})).startswith("Location isn't available")
