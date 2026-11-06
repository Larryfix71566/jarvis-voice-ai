"""Checked, content-free transport send for the brief (jarvis/bot/ws_transport.py).

Runs against the REAL pipecat FastAPIWebsocketTransport adapter, with only the
Starlette websocket and the serializer faked."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from loguru import logger as loguru_logger
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from starlette.websockets import WebSocketState

from jarvis.bot.brief_tool import BriefJobs, build_daily_brief_tool
from jarvis.bot.pipeline import send_app_message, send_app_message_checked
from jarvis.bot.ws_transport import CheckedSendError, send_frame_checked
from jarvis.privacy_policy import DataPolicy, issue_tool_result

CANARY = "SYNTHETIC_PRIVATE_CANARY"
NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
MESSAGE = {"type": "display", "display": {"kind": "brief", "title": "Mail"}}


class FakeSerializer(FrameSerializer):
    async def setup(self, frame):
        pass

    async def serialize(self, frame):
        return b"x"

    async def deserialize(self, data):
        return None


class FakeWebSocket:
    def __init__(self, *, fail=True):
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.fail = fail
        self.attempts = 0
        self.bytes_sent: list[bytes] = []
        self.headers = {}

    async def send_bytes(self, data):
        self.attempts += 1
        if self.fail:
            raise RuntimeError(CANARY)
        self.bytes_sent.append(data)

    async def send_text(self, data):
        self.attempts += 1
        if self.fail:
            raise RuntimeError(CANARY)


def make_transport(ws):
    return FastAPIWebsocketTransport(
        websocket=ws, params=FastAPIWebsocketParams(serializer=FakeSerializer()))


@pytest.fixture
def loguru_sink():
    lines: list[str] = []
    sink_id = loguru_logger.add(lambda m: lines.append(str(m)), level="TRACE")
    yield lines
    loguru_logger.remove(sink_id)


def test_pinned_pipecat_private_attributes():
    t = make_transport(FakeWebSocket())
    out = t.output()
    assert out._client._websocket is not None and out._params.serializer is not None
    for name in ("is_closing", "is_connected"):
        assert hasattr(out._client, name)


async def test_checked_send_raises_without_leaking_the_exception_text(caplog, loguru_sink):
    caplog.set_level(logging.DEBUG)
    ws = FakeWebSocket()
    with pytest.raises(CheckedSendError) as info:
        await send_app_message_checked(make_transport(ws), MESSAGE)
    assert str(info.value) == "send_failed" and info.value.__cause__ is None
    assert ws.attempts == 1
    assert CANARY not in caplog.text and CANARY not in "\n".join(loguru_sink)


async def test_unchecked_send_cannot_report_failure():
    # Why the checked variant exists: pipecat swallows the error.
    ws = FakeWebSocket()
    await send_app_message(make_transport(ws), MESSAGE)     # does not raise
    assert ws.attempts == 1


async def test_not_connected_raises_and_attempts_nothing():
    ws = FakeWebSocket()
    ws.client_state = WebSocketState.DISCONNECTED
    with pytest.raises(CheckedSendError, match="not_connected"):
        await send_app_message_checked(make_transport(ws), MESSAGE)
    assert ws.attempts == 0


async def test_application_state_disconnected_is_not_connected():
    ws = FakeWebSocket()
    ws.application_state = WebSocketState.DISCONNECTED
    with pytest.raises(CheckedSendError, match="not_connected"):
        await send_app_message_checked(make_transport(ws), MESSAGE)
    assert ws.attempts == 0


async def test_unsupported_transport():
    with pytest.raises(CheckedSendError, match="unsupported_transport"):
        await send_frame_checked(object(), object())


async def test_success_path_writes_the_payload():
    ws = FakeWebSocket(fail=False)
    await send_app_message_checked(make_transport(ws), MESSAGE)
    assert ws.bytes_sent == [b"x"]


async def test_end_to_end_brief_logs_a_failed_send_and_no_canary(caplog, loguru_sink):
    caplog.set_level(logging.DEBUG)
    ws = FakeWebSocket()
    transport = make_transport(ws)

    async def send(payload):
        await send_app_message_checked(transport, {"type": "display", "display": payload})

    content = {
        "ok": True,
        "accounts": [{"key": "gmail", "label": "Gmail", "status": "ok",
                      "count": {"state": "exact", "value": 1}, "headlines_complete": True,
                      "returned_count": 0, "error": None},
                     {"key": "att", "label": "x", "status": "ok",
                      "count": {"state": "exact", "value": 0}, "headlines_complete": True,
                      "returned_count": 0, "error": None}],
        "messages": [],
    }

    class Registry:
        async def call_classified(self, name, arguments, *, execution_scope):
            return issue_tool_result(execution_scope, json.dumps(content),
                                     DataPolicy("confidential", "verified-host-confidential-source"),
                                     "mail:att/gmail", ())

    jobs = BriefJobs()
    _, handler = build_daily_brief_tool(
        registry=Registry(), send_display=send, eligible=lambda: True,
        connected=lambda: True, now=lambda: NOW, tz=ZoneInfo("UTC"), jobs=jobs)
    await handler({"scope": "mail"})
    await asyncio.gather(*list(jobs._tasks), return_exceptions=True)
    assert "brief_job_send_failed type=CheckedSendError" in caplog.text
    assert "brief_job_sent" not in caplog.text
    assert ws.attempts == 1
    assert CANARY not in caplog.text and CANARY not in "\n".join(loguru_sink)
