"""Runner-compatible bot entry point (plan Phase 4 step 4.1, Phase 5 step 5.1).

Run:  python -m jarvis.bot.bot   (or ./scripts/run_bot.sh)
Then open http://localhost:7860/client and click Connect.

D-004 (pipecat 1.4.0): TransportParams has no vad_analyzer or
allow_interruptions fields. VAD runs as VADProcessor inside the pipeline
and interruptions come from the aggregator's user-turn-start strategy
(speaker-verified min-words; Flux's own should_interrupt is False since
2026-08-22) — both in pipeline.py. The entry shape (SmallWebRTC only,
run_session) is unchanged.
"""

from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from jarvis.audio import build_audio_filter
from jarvis.bot.pipeline import run_session
from jarvis.config import load_settings


async def bot(runner_args: RunnerArguments):
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
        case _:
            raise RuntimeError("Jarvis supports SmallWebRTC only")
    await run_session(
        transport,
        webrtc_connection=getattr(runner_args, "webrtc_connection", None),
    )


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
