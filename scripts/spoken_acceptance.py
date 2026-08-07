"""Spoken-acceptance harness (Phase 4 "Spoken Dozen" tooling).

Plays pre-recorded WAV files into a running Jarvis bot over the same
/api/offer WebRTC path the browser client uses, so the Phase 4 checklist can
be exercised without a human at the mic. Uses only locked dependencies
(aiortc + PyAV ship with pipecat's webrtc extra).

This is test tooling only — it changes no server behavior.

Prereqs:
  - bot running:  JARVIS_DB_PATH=<db> ./scripts/run_bot.sh  (log to a file)
  - utterances as 48 kHz mono s16 WAV (convert with:
      ffmpeg -y -i in.mp3 -ar 48000 -ac 1 -c:a pcm_s16le out.wav)

Usage:
  python3 scripts/spoken_acceptance.py \
      --manifest tests/acceptance/spoken-dozen-manifest.txt \
      --bot-log /tmp/bot.log --url http://localhost:7860/api/offer \
      --quiet 8 --turn-timeout 150

Manifest format: one WAV path per line, in checklist order. Lines starting
with '#' are comments. Between files the track keeps sending silence so the
session stays connected for the whole run.

For each file the harness behaves like a patient user: after the audio ends
it waits for the turn's full delegation cycle before playing the next file
(max --turn-timeout), then --quiet seconds of log inactivity. Speaking while
a sub-agent is mid-call is a barge-in: Flux should_interrupt=True makes
pipecat CANCEL the in-flight function call (cancel_on_interruption default),
which would forfeit the turn's result — the wait avoids that artifact.

Terminal-signal detection uses the rtvi-ai data channel, which the harness
receives directly (no log scraping):
  - {"tool_call_id": "..."}                 -> a function call started
  - {"tool_call_id": "...", "cancelled": X}  -> that call's result arrived
  - {"type": "agent", "state": "working"|"done"} -> sub-agent lifecycle
The result message fires for BOTH completion and the plan-locked 45s
sub-agent timeout (verified live: on timeout there is no agent "done"
message, but the result message still arrives), so counting results is the
one terminal signal that works on every path.
  1. Delegated turn: terminal when results received >= delegations started,
     then a long quiet (covers the supervisor's LLM re-run between hops of a
     multi-hop turn so we never barge-in on hop 2).
  2. Non-delegated turn: first JARVIS log line, or 25s with no delegation,
     then --quiet seconds of inactivity.

Progress goes to stdout; the bot log carries the USER:/JARVIS:/[AGENT]/TURN
lines used as checklist evidence.

Manifest directives (Phase 5/7 extensions — same tooling, no server changes):
  @APP {"type":"voice/set","voice":"eric"}
      Send a raw client app-message over the data channel (the server accepts
      the locked raw shape verbatim) and wait up to 10s for the matching
      {"type":"voice/current"} echo.
  @BARGE <long.wav> <interrupt.wav> <speak_secs>
      Play long.wav, wait for the bot to START speaking, let it speak for
      speak_secs, then play interrupt.wav without waiting for the turn —
      a barge-in. Measures seconds from interruption start until the bot's
      remote audio stops (acceptance: ~1 s), then waits for the interrupt
      turn to complete normally.
  @AWAIT_TURN <timeout>
      Speak nothing; wait for a NEW server-side turn (e.g. a due reminder
      injected by the RemindersWatcher while connected) within timeout.
"""

from __future__ import annotations

import argparse
import asyncio
import fractions
import json
import logging
import re
import sys
import time
import wave
from pathlib import Path

import httpx
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack
from av import AudioFrame

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("spoken_acceptance")
logger.setLevel(logging.INFO)

SAMPLE_RATE = 48000
SAMPLES_PER_FRAME = 960  # 20 ms
TURN_MARKER = "TURN user_end->llm_done"


ACTIVITY_RMS = 800  # int16 RMS above this counts as bot speech


class BotAudioRecorder:
    """Records the bot's remote audio track to per-turn 48 kHz mono s16 WAVs.

    With TTS working, this captures what Jarvis actually spoke, so the
    audible checklist items get machine-verifiable evidence (the WAVs can
    also be transcribed back for content checks).

    Doubles as the remote-activity monitor for @BARGE: every resampled
    frame's RMS updates ``last_active``, so the barge logic can detect the
    bot starting/stopping speech. Recording to WAV only happens when an
    output dir is set; monitoring is always on."""

    def __init__(self, out_dir: Path | None) -> None:
        self._out_dir = out_dir
        self._wf: wave.Wave_write | None = None
        self.last_active = 0.0

    def attach(self, track) -> None:
        asyncio.ensure_future(self._pump(track))

    async def _pump(self, track) -> None:
        import numpy as np
        from av.audio.resampler import AudioResampler

        resampler = AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        while True:
            try:
                frame = await track.recv()
            except Exception:
                return
            for f in resampler.resample(frame):
                data = bytes(f.planes[0])
                if self._wf is not None:
                    self._wf.writeframesraw(data)
                arr = np.frombuffer(data, dtype=np.int16)
                if arr.size:
                    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
                    if rms > ACTIVITY_RMS:
                        self.last_active = time.perf_counter()

    def recently_active(self, within: float = 1.0) -> bool:
        return (time.perf_counter() - self.last_active) <= within

    def start_turn(self, name: str) -> None:
        self.end_turn()
        if self._out_dir is None:
            return
        self._wf = wave.open(str(self._out_dir / f"{name}-bot.wav"), "wb")
        self._wf.setnchannels(1)
        self._wf.setsampwidth(2)
        self._wf.setframerate(SAMPLE_RATE)

    def end_turn(self) -> None:
        if self._wf is not None:
            self._wf.close()
            self._wf = None


class PlaylistTrack(AudioStreamTrack):
    """Streams 48 kHz mono s16 WAV files at real-time pace; silence elsewhere."""

    def __init__(self) -> None:
        super().__init__()
        self._queue: asyncio.Queue[Path] = asyncio.Queue()
        self._wf: wave.Wave_read | None = None
        self._wf_name: str | None = None
        self._pts = 0
        self._start: float | None = None
        self._silence = b"\x00" * (SAMPLES_PER_FRAME * 2)

    def enqueue(self, path: Path) -> None:
        self._queue.put_nowait(path)

    def current_file_done(self) -> bool:
        return self._wf is None and self._queue.empty()

    def current_name(self) -> str | None:
        return self._wf_name

    async def recv(self) -> AudioFrame:
        if self._start is None:
            self._start = time.perf_counter()
        if self._wf is None and not self._queue.empty():
            path = self._queue.get_nowait()
            self._wf = wave.open(str(path), "rb")
            self._wf_name = path.name
            assert (
                self._wf.getframerate() == SAMPLE_RATE
                and self._wf.getnchannels() == 1
                and self._wf.getsampwidth() == 2
            ), f"{path} must be 48kHz mono s16 WAV"
            logger.info("playing %s", path.name)
        data = self._silence
        if self._wf is not None:
            data = self._wf.readframes(SAMPLES_PER_FRAME)
            if len(data) < SAMPLES_PER_FRAME * 2:
                # pad tail with silence, close file
                data = data + self._silence[: SAMPLES_PER_FRAME * 2 - len(data)]
                self._wf.close()
                self._wf = None
                self._wf_name = None
                logger.info("file finished, sending silence")
        frame = AudioFrame(format="s16", layout="mono", samples=SAMPLES_PER_FRAME)
        frame.planes[0].update(data)
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, SAMPLE_RATE)
        self._pts += SAMPLES_PER_FRAME
        # pace to real time
        target = self._start + self._pts / SAMPLE_RATE
        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        return frame


def count_turns(log_path: Path) -> int:
    try:
        return log_path.read_text(errors="replace").count(TURN_MARKER)
    except FileNotFoundError:
        return 0


async def wait_for_turn(log_path: Path, before: int, timeout: float) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if count_turns(log_path) > before:
            return True
        await asyncio.sleep(0.5)
    return False


DONE_RE = re.compile(r"\[AGENT\] \w+ done")
WORKING_RE = re.compile(r"\[AGENT\] \w+ working")

DELEGATED_QUIET = 40.0  # covers the supervisor's LLM re-run between hops


class DCState:
    """rtvi-ai data-channel counters (module docstring: terminal signals)."""

    def __init__(self) -> None:
        self.started = 0  # {"tool_call_id": ...} without "cancelled"
        self.results = 0  # {"tool_call_id": ..., "cancelled": ...}
        self.working = 0  # {"type": "agent", "state": "working"}
        self.done = 0     # {"type": "agent", "state": "done"}

    def snapshot(self) -> tuple:
        return (self.started, self.results, self.working)

    def feed(self, inner: dict) -> None:
        if "tool_call_id" in inner:
            if "cancelled" in inner:
                self.results += 1
            else:
                self.started += 1
        elif inner.get("type") == "agent":
            if inner.get("state") == "working":
                self.working += 1
            elif inner.get("state") == "done":
                self.done += 1


dc = DCState()

voice_messages: list[dict] = []  # {"type":"voice/current", ...} echoes


def parse_manifest(path: Path) -> list[tuple]:
    """WAV paths plus @-directives (module docstring). Returns typed items:
    ("wav", Path) | ("app", dict) | ("barge", Path, Path, float) |
    ("await_turn", float)."""
    items: list[tuple] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@APP "):
            items.append(("app", json.loads(line[len("@APP "):])))
        elif line.startswith("@BARGE "):
            parts = line.split()
            items.append(("barge", Path(parts[1]), Path(parts[2]), float(parts[3])))
        elif line.startswith("@AWAIT_TURN "):
            items.append(("await_turn", float(line.split()[1])))
        else:
            items.append(("wav", Path(line)))
    return items


def turn_signature(text: str) -> tuple:
    return (
        text.count(TURN_MARKER),
        len(WORKING_RE.findall(text)),
        len(DONE_RE.findall(text)),
        text.count("JARVIS:"),
        dc.started,
        dc.results,
        dc.working,
        dc.done,
    )


async def wait_for_turn_complete(
    log_path: Path, before: int, snap: tuple, quiet: float, timeout: float
) -> bool:
    """Wait for the turn cycle (see module docstring for the terminal-signal
    strategy). snap is a DCState.snapshot() taken before the utterance."""
    deadline = time.perf_counter() + timeout
    if not await wait_for_turn(log_path, before, timeout):
        return False
    started0, results0, working0 = snap
    try:
        jarvis0 = log_path.read_text(errors="replace").count("JARVIS:")
    except FileNotFoundError:
        jarvis0 = 0
    turn_seen_at = time.perf_counter()
    last_sig: tuple | None = None
    last_change = turn_seen_at
    while time.perf_counter() < deadline:
        await asyncio.sleep(0.5)
        try:
            text = log_path.read_text(errors="replace")
        except FileNotFoundError:
            continue
        sig = turn_signature(text)
        if sig != last_sig:
            last_sig = sig
            last_change = time.perf_counter()
            continue
        now = time.perf_counter()
        n_deleg = max(dc.started - started0, dc.working - working0)
        if n_deleg > 0:
            # delegated: one data-channel result message per delegation,
            # on BOTH the success and the locked-45s-timeout path; then a
            # long quiet so a multi-hop turn's next hop can start first.
            terminal = (dc.results - results0) >= n_deleg
            need_quiet = max(quiet, DELEGATED_QUIET)
        else:
            terminal = sig[3] > jarvis0 or (now - turn_seen_at) > 25
            need_quiet = quiet
        if not terminal:
            continue
        # NOTE: we do NOT wait for the final post-result JARVIS line. While
        # the ElevenLabs account is blocked, the TTS service parks downstream
        # FunctionCall* frames (verified with a frame-level probe: the hop
        # ElevenLabsTTSService->SmallWebRTCOutputTransport never happens until
        # the next interruption flushes it), so the follow-up completion is
        # suppressed in this degraded mode. With a working TTS the frames
        # flow and the final reply lands; waiting for it here would just
        # time out every delegated turn and cause barge-in cancellations.
        if now - last_change >= need_quiet:
            return True
    return False


async def run(args: argparse.Namespace) -> int:
    items = parse_manifest(Path(args.manifest))
    for item in items:
        for f in [p for p in item[1:] if isinstance(p, Path)]:
            if not f.exists():
                print(f"missing manifest file: {f}", file=sys.stderr)
                return 2

    track = PlaylistTrack()
    pc = RTCPeerConnection()
    pc.addTrack(track)
    channel = pc.createDataChannel("rtvi-ai")
    recorder = BotAudioRecorder(Path(args.audio_dir) if args.audio_dir else None)

    @pc.on("track")
    def on_track(remote):
        if remote.kind == "audio":
            recorder.attach(remote)

    @channel.on("message")
    def on_message(message):  # app messages (voice catalog, agent events)
        try:
            payload = json.loads(message)
            inner = payload.get("data", payload)
            if isinstance(inner, dict):
                dc.feed(inner)
                if inner.get("type") == "voice/current":
                    voice_messages.append(inner)
            logger.info("app-message: %s", json.dumps(inner)[:160])
        except Exception:
            logger.info("app-message(raw): %s", str(message)[:160])

    await pc.setLocalDescription(await pc.createOffer())
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.1)

    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            args.url,
            json={"sdp": pc.localDescription.sdp, "type": "offer"},
        )
        resp.raise_for_status()
        answer = resp.json()
    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
    )
    logger.info("connected (pc_id=%s)", answer.get("pc_id"))

    # Keepalive: pipecat's SmallWebRTCConnection.is_connected() requires a
    # "ping" data-channel message within the last 3 s once any message was
    # received (the browser client-js pings roughly every second). Without
    # this the server considers the client stale and QUEUES inbound app
    # messages instead of handling them — @APP voice/set would never fire.
    async def keepalive():
        while True:
            try:
                if channel.readyState == "open":
                    channel.send("ping")
            except Exception:
                pass  # retry next tick; never let the task die
            await asyncio.sleep(1.0)

    keepalive_task = asyncio.ensure_future(keepalive())

    # let the greeting turn finish before the first utterance
    log_path = Path(args.bot_log)
    greeting_turns = count_turns(log_path)
    logger.info("waiting up to %.0fs for greeting turn…", args.greeting_timeout)
    greeted = await wait_for_turn_complete(
        log_path, greeting_turns, dc.snapshot(), args.quiet, args.greeting_timeout)
    logger.info("greeting turn: %s", "seen" if greeted else "not seen (continuing)")

    results = []
    i = 0
    for item in items:
        i += 1
        kind = item[0]

        if kind == "wav":
            f = item[1]
            before = count_turns(log_path)
            snap = dc.snapshot()
            recorder.start_turn(f.stem)
            track.enqueue(f)
            while not track.current_file_done():
                await asyncio.sleep(0.2)
            ok = await wait_for_turn_complete(
                log_path, before, snap, args.quiet, args.turn_timeout)
            recorder.end_turn()
            results.append((i, f.name, ok))
            print(f"[{i:02d}] {f.name}: turn={'OK' if ok else 'TIMEOUT'}", flush=True)

        elif kind == "app":
            msg = item[1]
            voice_messages.clear()
            channel.send(json.dumps(msg))
            logger.info("sent app-message: %s", json.dumps(msg))
            deadline = time.perf_counter() + 10
            ok = False
            while time.perf_counter() < deadline:
                if any(m.get("voice") == msg.get("voice") for m in voice_messages):
                    ok = True
                    break
                await asyncio.sleep(0.2)
            got = voice_messages[-1] if voice_messages else None
            results.append((i, f"@APP {msg.get('voice')}", ok))
            print(f"[{i:02d}] @APP voice/set {msg.get('voice')}: "
                  f"echo={'OK' if ok else f'MISSING (last={got})'}", flush=True)

        elif kind == "barge":
            _, long_wav, barge_wav, speak_secs = item
            before = count_turns(log_path)
            snap = dc.snapshot()
            recorder.start_turn(long_wav.stem)
            track.enqueue(long_wav)
            while not track.current_file_done():
                await asyncio.sleep(0.2)
            # wait for the bot to START speaking (up to 45s)
            t_wait = time.perf_counter() + 45
            while time.perf_counter() < t_wait and not recorder.recently_active():
                await asyncio.sleep(0.1)
            if not recorder.recently_active():
                results.append((i, "barge", False))
                print(f"[{i:02d}] barge: bot never started speaking", flush=True)
                continue
            logger.info("bot speaking; interrupting in %.1fs", speak_secs)
            await asyncio.sleep(speak_secs)
            track.enqueue(barge_wav)
            while track.current_name() != barge_wav.name:
                await asyncio.sleep(0.05)
            t0 = time.perf_counter()
            # measure: bot audio stops after interruption start
            stop_latency = None
            deadline = t0 + 15
            while time.perf_counter() < deadline:
                if (time.perf_counter() - recorder.last_active) >= 0.5:
                    stop_latency = recorder.last_active - t0
                    break
                await asyncio.sleep(0.05)
            while not track.current_file_done():
                await asyncio.sleep(0.1)
            ok_turn = await wait_for_turn_complete(
                log_path, before, snap, args.quiet, args.turn_timeout)
            recorder.end_turn()
            ok = ok_turn and stop_latency is not None and stop_latency <= 1.5
            results.append((i, "barge", ok))
            lat = f"{stop_latency:.2f}s" if stop_latency is not None else "never stopped"
            print(f"[{i:02d}] barge: bot audio stopped {lat} after interruption; "
                  f"interrupt turn={'OK' if ok_turn else 'TIMEOUT'}", flush=True)

        elif kind == "await_turn":
            timeout = item[1]
            before = count_turns(log_path)
            snap = dc.snapshot()
            recorder.start_turn(f"await-{i:02d}")
            ok = await wait_for_turn_complete(
                log_path, before, snap, args.quiet, timeout)
            recorder.end_turn()
            results.append((i, "@AWAIT_TURN", ok))
            print(f"[{i:02d}] @AWAIT_TURN: turn={'OK' if ok else 'TIMEOUT'}", flush=True)

    keepalive_task.cancel()
    await pc.close()
    failed = [r for r in results if not r[2]]
    print(f"done: {len(results) - len(failed)}/{len(results)} turns observed")
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bot-log", required=True)
    ap.add_argument("--url", default="http://localhost:7860/api/offer")
    ap.add_argument("--turn-timeout", type=float, default=150.0)
    ap.add_argument("--greeting-timeout", type=float, default=45.0)
    ap.add_argument("--quiet", type=float, default=8.0,
                    help="seconds of log inactivity that mean 'turn finished'")
    ap.add_argument("--audio-dir", default=None,
                    help="if set, record the bot's audio to <dir>/<utterance>-bot.wav")
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()
