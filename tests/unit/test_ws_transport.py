"""Native-audio transport plan §7 (server): the WebSocket transport carries
the app messages the pipeline sends, and client messages reach the
handlers through the pipeline rather than a connection event.

Every assertion here runs against the installed pipecat serializer and
frame classes — the RTVI-label filter and the absence of ``on_app_message``
on ``FastAPIWebsocketTransport`` are exercised, not described.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from pipecat.audio.filters.base_audio_filter import BaseAudioFilter
from pipecat.frames.frames import (
    InputAudioRawFrame,
    InputTransportMessageFrame,
    OutputTransportMessageUrgentFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

import jarvis.bot.bot as bot_module
from jarvis.bot.pipeline import _wrap_rtvi
from jarvis.bot.ws_transport import (
    ClientMessageProcessor,
    build_websocket_transport,
    websocket_params,
)


class _Filter(BaseAudioFilter):
    """The narrowest concrete BaseAudioFilter (TransportParams validates
    the field's type, so a bare string cannot stand in)."""

    async def start(self, sample_rate: int) -> None: ...
    async def stop(self) -> None: ...
    async def process_frame(self, frame): ...
    async def filter(self, audio: bytes) -> bytes:
        return audio


def test_params_enable_audio_both_ways_and_keep_the_filter_seam():
    audio_filter = _Filter()
    params = websocket_params(audio_filter=audio_filter)
    assert params.audio_in_enabled is True
    assert params.audio_out_enabled is True
    assert params.audio_in_filter is audio_filter
    assert isinstance(params.serializer, ProtobufFrameSerializer)
    assert params.serializer._params.ignore_rtvi_messages is False
    # The pipeline's input rate is not overridden: 16 kHz from the
    # StartFrame default, which is what the native client sends.
    assert params.audio_in_sample_rate is None


def test_wrapped_app_message_survives_the_serializer():
    """Correction to the §3.2 finding as first written: the base
    FrameSerializer's ignore_rtvi_messages defaults to True, but
    ProtobufFrameSerializer.__init__ forces it to False (protobuf.py:74-78),
    so a bare ProtobufFrameSerializer() already carries the rtvi-ai envelope.
    websocket_params() sets the flag explicitly so the intent survives a
    pipecat upgrade that changes the constructor; the base filter is shown
    dropping the message when re-enabled, which is the trap the flag guards."""
    message = _wrap_rtvi({"type": "display", "display": {"k": 1}})
    frame = OutputTransportMessageUrgentFrame(message=message)
    plain = ProtobufFrameSerializer()
    assert plain._params.ignore_rtvi_messages is False
    assert asyncio.run(plain.serialize(frame)), "the stock protobuf serializer carries it"
    filtered = ProtobufFrameSerializer()
    filtered._params.ignore_rtvi_messages = True
    assert filtered.should_ignore_frame(frame) is True
    assert asyncio.run(filtered.serialize(frame)) is None, "the base-class filter would drop it"
    ours = asyncio.run(websocket_params().serializer.serialize(frame))
    assert isinstance(ours, bytes) and ours
    # …and the client gets the envelope back byte-for-byte as JSON.
    decoded = asyncio.run(websocket_params().serializer.deserialize(ours))
    assert isinstance(decoded, InputTransportMessageFrame)
    assert decoded.message == message


def test_client_audio_and_message_frames_deserialize_as_documented():
    serializer = websocket_params().serializer
    audio = asyncio.run(serializer.deserialize(bytes.fromhex("120b1a040102030420807d2801")))
    assert isinstance(audio, InputAudioRawFrame)
    assert (audio.sample_rate, audio.num_channels, audio.audio) == (16000, 1, b"\x01\x02\x03\x04")
    message = asyncio.run(serializer.deserialize(bytes.fromhex(
        "22250a237b2274797065223a2022766f6963652f736574222c2022766f696365223a202278227d")))
    assert isinstance(message, InputTransportMessageFrame)
    assert message.message == {"type": "voice/set", "voice": "x"}


def test_transport_has_no_app_message_event_so_the_processor_is_the_receive_path():
    events = FastAPIWebsocketTransport.__init__.__code__.co_consts
    registered = {c for c in events if isinstance(c, str) and c.startswith("on_")}
    assert "on_client_connected" in registered
    assert "on_app_message" not in registered


def test_client_message_processor_runs_bound_handlers_and_passes_frames_through():
    seen: list = []
    pushed: list = []

    async def voice(message):
        seen.append(("voice", message))

    async def noop(message):
        seen.append(("noop", message))

    processor = ClientMessageProcessor()
    processor.bind(voice, noop)
    assert processor.handlers == (voice, noop)

    async def record_push(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    processor.push_frame = record_push  # type: ignore[method-assign]

    async def run():
        message = InputTransportMessageFrame(message={"type": "voice/set", "voice": "x"})
        await processor.process_frame(message, FrameDirection.DOWNSTREAM)
        await processor.process_frame(TextFrame(text="ignored"), FrameDirection.DOWNSTREAM)

    asyncio.run(run())
    assert seen == [("voice", {"type": "voice/set", "voice": "x"}),
                    ("noop", {"type": "voice/set", "voice": "x"})]
    assert [type(f).__name__ for f, _ in pushed] == ["InputTransportMessageFrame", "TextFrame"]


def test_bot_builds_the_websocket_transport_for_websocket_runner_arguments(monkeypatch):
    from pipecat.runner.types import WebSocketRunnerArguments

    built = {}

    def fake_build(websocket, audio_filter):
        built["websocket"] = websocket
        built["filter"] = audio_filter
        return "WS_TRANSPORT"

    async def fake_run_session(transport, webrtc_connection=None, client_messages=None):
        built["transport"] = transport
        built["webrtc_connection"] = webrtc_connection
        built["client_messages"] = type(client_messages).__name__

    monkeypatch.setattr(bot_module, "build_websocket_transport", fake_build)
    monkeypatch.setattr(bot_module, "run_session", fake_run_session)
    monkeypatch.setattr(bot_module, "load_settings", lambda: "SETTINGS")
    monkeypatch.setattr(bot_module, "build_audio_filter", lambda settings: f"FILTER({settings})")

    args = WebSocketRunnerArguments(websocket="SOCKET", transport_type="websocket")
    asyncio.run(bot_module.bot(args))
    assert built == {
        "websocket": "SOCKET", "filter": "FILTER(SETTINGS)",
        "transport": "WS_TRANSPORT", "webrtc_connection": None,
        "client_messages": "ClientMessageProcessor",
    }


def test_bot_still_refuses_unknown_runner_arguments():
    from pipecat.runner.types import RunnerArguments

    with pytest.raises(RuntimeError):
        asyncio.run(bot_module.bot(RunnerArguments()))


def test_build_websocket_transport_wraps_the_fastapi_transport():
    class Socket:
        headers = {}

    transport = build_websocket_transport(Socket(), audio_filter=None)
    assert isinstance(transport, FastAPIWebsocketTransport)
    assert json.dumps(_wrap_rtvi({"type": "x"}))  # the envelope is plain JSON
