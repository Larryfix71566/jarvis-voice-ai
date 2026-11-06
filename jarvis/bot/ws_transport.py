"""Native-audio transport plan (MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md) D7:
the server half of the loopback path.

The runner already serves ``/ws-client`` on :7860 beside ``/api/offer``
(pipecat ``runner/run.py`` ``_setup_websocket_routes``); a connection there
reaches ``bot()`` as ``WebSocketRunnerArguments``. This module builds the
``FastAPIWebsocketTransport`` for that case and supplies the one piece the
WebSocket transport lacks that the pipeline used on WebRTC: a receive path
for client app messages.

§3 findings (2026-09-12) that this file exists to honour:

* ``ProtobufFrameSerializer`` is the only built-in serializer carrying both
  audio and messages. The base ``FrameSerializer`` filter
  (``ignore_rtvi_messages``, default True) drops every outbound message
  whose ``label == "rtvi-ai"`` — which is every message ``_wrap_rtvi``
  produces — but ``ProtobufFrameSerializer.__init__`` forces the flag off
  (protobuf.py:74-78), so the stock serializer already carries them.
  ``websocket_params`` sets it off explicitly anyway, so the intent does not
  depend on that constructor detail; ``test_ws_transport.py`` proves a
  wrapped message survives and shows the filter dropping it when re-enabled.
* ``FastAPIWebsocketTransport`` has no ``on_app_message`` event and no
  connection object; inbound ``message`` frames are broadcast into the
  pipeline as ``InputTransportMessageFrame``. ``ClientMessageProcessor``
  consumes them after ``transport.input()``. The WebRTC case keeps its
  connection-level handler and does not get this processor (SmallWebRTC
  broadcasts the same frame, so both would fire).
* The WebSocket input does not resample: the pipeline's input rate stays
  the ``StartFrame`` default (16 kHz) and the client sends 16 kHz Int16
  mono; output frames carry their own rate (24 kHz).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from pipecat.frames.frames import Frame, InputTransportMessageFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.base_serializer import FrameSerializer
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from starlette.websockets import WebSocketState

MessageHandler = Callable[[Any], Awaitable[None]]

_logger = logging.getLogger(__name__)


class CheckedSendError(Exception):
    """A checked send did not reach the socket. The message is always a fixed
    short reason code, never exception text (which could carry payload bytes)."""


async def send_frame_checked(transport: Any, frame: Frame) -> None:
    """Send one frame on a ``FastAPIWebsocketTransport`` and raise
    ``CheckedSendError`` if it cannot be written.

    pipecat's own ``send_message`` swallows every failure and logs the
    exception text, so a caller can neither learn that a send failed nor keep
    the text out of its logs. This mirrors ``_write_frame`` / ``client.send``
    with the same guards, but reports failure with a code only."""
    if not isinstance(transport, FastAPIWebsocketTransport):
        raise CheckedSendError("unsupported_transport")
    # pipecat 1.4.0 private attributes (pinned in requirements.txt); a test in
    # tests/unit/test_brief_checked_send.py pins them.
    out = transport.output()
    client = out._client
    params = out._params
    websocket = client._websocket
    try:
        usable = (not client.is_closing and client.is_connected
                  and websocket.application_state != WebSocketState.DISCONNECTED)
    except Exception:  # noqa: BLE001
        usable = False
    if not usable:
        _logger.info("checked_send_failed reason=not_connected")
        raise CheckedSendError("not_connected")
    if not params.serializer:
        raise CheckedSendError("no_serializer")
    try:
        payload = await params.serializer.serialize(frame)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("checked_send_failed reason=serialize_failed type=%s", type(exc).__name__)
        raise CheckedSendError("serialize_failed") from None
    if not payload:
        raise CheckedSendError("empty_payload")
    try:
        if isinstance(payload, (bytes, bytearray)):
            await websocket.send_bytes(bytes(payload))
        else:
            await websocket.send_text(payload)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("checked_send_failed reason=send_failed type=%s", type(exc).__name__)
        raise CheckedSendError("send_failed") from None


def websocket_params(audio_filter: Any = None) -> FastAPIWebsocketParams:
    """The loopback transport's parameters: audio both ways, the same
    ``audio_in_filter`` seam as the SmallWebRTC case, and the protobuf
    serializer with RTVI-labelled messages let through."""
    return FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_filter=audio_filter,
        serializer=ProtobufFrameSerializer(
            params=FrameSerializer.InputParams(ignore_rtvi_messages=False)),
    )


def build_websocket_transport(websocket: Any, audio_filter: Any = None) -> FastAPIWebsocketTransport:
    """``FastAPIWebsocketTransport`` for one accepted ``/ws-client`` socket."""
    return FastAPIWebsocketTransport(websocket=websocket, params=websocket_params(audio_filter))


class ClientMessageProcessor(FrameProcessor):
    """Hands every ``InputTransportMessageFrame`` to the session's message
    handlers, then passes the frame on unchanged (parity with the WebRTC
    path, where the broadcast frame also travels the pipeline). Handlers are
    bound after construction because ``run_session`` defines them once the
    pipeline exists."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._handlers: list[MessageHandler] = []

    def bind(self, *handlers: MessageHandler) -> None:
        self._handlers.extend(handlers)

    @property
    def handlers(self) -> tuple[MessageHandler, ...]:
        return tuple(self._handlers)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputTransportMessageFrame):
            for handler in self._handlers:
                await handler(frame.message)
        await self.push_frame(frame, direction)
