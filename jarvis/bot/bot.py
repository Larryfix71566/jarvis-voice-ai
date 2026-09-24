"""Runner-compatible bot entry point (plan Phase 4 step 4.1, Phase 5 step 5.1).

Run:  python -m jarvis.bot.bot   (or ./scripts/run_bot.sh)
Then open http://localhost:7860/client and click Connect.

D-004 (pipecat 1.4.0): TransportParams has no vad_analyzer or
allow_interruptions fields. VAD runs as VADProcessor inside the pipeline
and interruptions come from the aggregator's user-turn-start strategy
(speaker-verified min-words; Flux's own should_interrupt is False since
2026-08-22) — both in pipeline.py. The entry shape (run_session per
connection) is unchanged; since the native-audio transport plan there are
two transport cases: SmallWebRTC (/api/offer) and the plain WebSocket
(/ws-client, the same-Mac native client).
"""

from pipecat.runner.types import (
    RunnerArguments,
    SmallWebRTCRunnerArguments,
    WebSocketRunnerArguments,
)
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from jarvis.audio import build_audio_filter
from jarvis.bot.pipeline import run_session
from jarvis.bot.ws_transport import ClientMessageProcessor, build_websocket_transport
from jarvis.config import load_settings


async def bot(runner_args: RunnerArguments):
    client_messages = None
    match runner_args:
        case SmallWebRTCRunnerArguments():
            # Voice isolation plan, Workstream A: server-side neural noise
            # suppression on the mic stream. OFF unless JARVIS_NS_ENABLED=true;
            # build_audio_filter() returns None and TransportParams then
            # behaves exactly as before. The deferred Workstream-V voice gate
            # will attach behind this same audio_in_filter seam when its
            # activation triggers fire (plan §5.0).
            settings = load_settings()
            audio_filter = build_audio_filter(settings)
            transport = SmallWebRTCTransport(
                webrtc_connection=runner_args.webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,  # Phase 5: TTS
                    audio_in_filter=audio_filter,
                ),
            )
        case WebSocketRunnerArguments():
            # MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md D7: the loopback
            # client (MortimerHost on the same Mac) arrives on the runner's
            # /ws-client route with PCM both ways and the app messages on
            # one socket. Same audio_in_filter seam; the pipeline below the
            # transport is untouched. SmallWebRTC stays for /api/offer (the
            # remote/T2 path and JARVIS_FORCE_WEBRTC rollback).
            settings = load_settings()
            transport = build_websocket_transport(
                runner_args.websocket, build_audio_filter(settings))
            # No connection object on this transport: client app messages
            # reach the session through this pipeline processor instead.
            client_messages = ClientMessageProcessor()
        case _:
            raise RuntimeError("Jarvis supports SmallWebRTC and the plain WebSocket transport only")
    await run_session(
        transport,
        webrtc_connection=getattr(runner_args, "webrtc_connection", None),
        client_messages=client_messages,
    )


def _runner_main_preserving_env(importer=None):
    """Import pipecat's runner without letting its .env override the shell.

    ``pipecat.runner.run`` calls ``load_dotenv(override=True)`` at import
    time, finding a .env by walking up from site-packages. That silently
    replaced an exported JARVIS_DB_PATH on 2026-09-13..16 and three days of
    conversations went to another checkout's database (C6 item 12). The rule
    everywhere else is that the exported environment wins over .env
    (jarvis/config.py), so restore any variable the import changed and say so.
    Variables the import merely adds are kept.
    """
    import importlib
    import logging
    import os

    before = dict(os.environ)
    module = (importer or (lambda: importlib.import_module("pipecat.runner.run")))()
    reverted = sorted(k for k, v in before.items() if os.environ.get(k) != v)
    for key in reverted:
        os.environ[key] = before[key]
    if reverted:
        logging.getLogger(__name__).warning(
            "pipecat_dotenv_override_reverted keys=%s", ",".join(reverted))
    return module.main


if __name__ == "__main__":
    _runner_main_preserving_env()()
