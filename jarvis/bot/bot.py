"""Runner-compatible bot entry point (plan Phase 4, step 4.1 — locked shape).

Run:  python -m jarvis.bot.bot   (or ./scripts/run_bot.sh)
Then open http://localhost:7860/client and click Connect.
"""

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from jarvis.bot.pipeline import run_session


async def bot(runner_args: RunnerArguments):
    match runner_args:
        case SmallWebRTCRunnerArguments():
            transport = SmallWebRTCTransport(
                webrtc_connection=runner_args.webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=False,  # Phase 4: no TTS yet
                    vad_analyzer=SileroVADAnalyzer(),
                ),
            )
        case _:
            raise RuntimeError("Phase 4 supports SmallWebRTC only")
    await run_session(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
