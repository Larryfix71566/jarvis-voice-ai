# C7 — P2 measured audio on the native path (in progress)

Date: 2026-09-13. Branch `feat/native-audio-transport`, on top of C6 (`5391db3`). Plan: closure plan C7 (§ "P2 measured audio on the native path"), which this record follows item by item. Unblocked by C6's live session — the level slots it reads are filled by the same taps that carried the first native conversation (`C6-native-audio.md`).

## What is built

| Item | Where | Evidence |
|---|---|---|
| C7.1 observer, app-scoped generation (gap G24), ≤30 Hz (gap G25) | `JarvisKit/AudioActivityObserver.swift`: samples `AudioLevelSource` (the transport's `latestInputLevel` / `latestPlayoutLevel`) on its own serial queue at `sampleHz` 30, feeds `AudioActivityAccumulator`, publishes an `AudioActivitySnapshot`. Owned by `JarvisClient`, which begins a session on connect, ends it on disconnect and on a dropped transport, and reports mute as an eligibility change. The generation now lives here; `AdaptiveStageView`'s `@State private var observationGeneration` is gone. | `AudioActivityObserverTests` (9): the cap is 30 Hz; measured levels reach the presentation while eligible; muting drops input but not playout; a new session is a new generation; `endSession` stops publishing; input measured before eligibility began is refused; latency percentiles; the meter's off switch. `kit-c7a.raw`: JarvisKit **158/0**, MortimerHost **148/0**. |
| C7.2 eligibility | Input is published only when the microphone is enabled **and** the transport provides measured levels (`NativeAudioTransport: AudioLevelSource`; the WebRTC transport does not conform). Nothing is published at all without a source, so the presentation's existing "audio level unavailable" path stays truthful rather than drawing a flat line. | `testWithoutAMeasuredSourceNothingIsPublished`, `testMutingDropsTheInputChannelButNotPlayout`, `testInputMeasuredBeforeEligibilityBeganIsRefused`. |
| C7.3 wire | `AdaptiveStageView.voicePresentation()` passes `client.audioActivity` and `client.audioActivityGeneration` to `VoicePresentationState.derive`. Nothing else in the presentation changed — the wave, orb, colours, envelope and overlap label are as they were. | MortimerHost 148/0 unchanged. |
| C7.4 runtime disable | `JarvisFlags.audioMeterEnabled`: `JARVIS_AUDIO_METER=off` in the environment or `defaults write com.mortimer.host JARVIS_AUDIO_METER -bool false`. The observer publishes nothing and logs that it is disabled. | `testTheMeterCanBeDisabledAtRuntime`. |
| C7.5 latency | Every accepted observation records buffer-host-time → snapshot-published, kept for 60 s; `JarvisClient.audioMeterLatency()` returns p50/p95/worst. Gate: p95 ≤ 150 ms on the deployment Mac. | `testLatencyReportsPercentilesOfBufferToPresentationDelay` proves the arithmetic; **the hardware number is open** — it needs a live session and the debug menu item that writes `P2-latency.json`. |

Deviation from the plan's file list: the observer is owned by `JarvisClient` and published as `audioActivity` rather than being a separate app-scoped object injected through `MortimerHostApp`. The requirement it exists for — one sampler, app-scoped generation, no view `@State`, no second tap — is met, with less wiring; `MortimerHostApp` is untouched.

## C7.5 — latency, and the 100 ms that was hiding in the tap (2026-09-13)

The first reading failed the gate: displayed p95 204 ms (input) and 171 ms (playout) against 150. Splitting the measurement into **arrival** (how old a level is the first time the sampler sees it — the audio path's own cost) and **displayed** (the age of the level the snapshot carries, counted every tick — what a viewer sees) showed the sampler was not the problem: levels were already 137 ms old on arrival, with a spread under 2 ms. A fixed offset, not jitter.

Instrumenting the taps found it. `installTap(bufferSize: 1024)` is a hint the engine may ignore, and here it did:

```
input tap:  4800 frames at 48000 Hz = 100.0 ms of audio, 10.0/s, age at callback 108.3 ms
input device 71: buffer 512 frames, range 15…4096      ← the hardware was never the limit
```

4800 frames is larger than the device's own maximum. The engine was accumulating twenty render quanta before each callback — and that buffer sat in front of **everything**, not just the wave: 100 ms before the bot heard a word, 100 ms before a barge-in could register. WebRTC's device module delivered 10 ms frames, so the tap had quietly broken the native-audio plan's D6 ("no behaviour change vs today").

**D10, capture:** `AVAudioSinkNode` receives the render quantum instead. Its block runs on the audio thread and allocates nothing — channel 0 is copied into one of eight preallocated mono buffers; the level, resample and send happen on the engine queue as before. `JARVIS_AUDIO_CAPTURE=tap` restores the old path.

**D10, playout:** the same remedy does not work — a sink node is driven by the input hardware, so hung off the mixer nothing pulls it and it delivered exactly zero buffers. But playout needs no tap at all: this client schedules every buffer, so each is sliced into ~20 ms levels positioned in the player's own sample clock, and the meter asks the player where it is (`playerTime`) when it reads. Three bugs were measured out of that on the way: slices anchored to a running total of scheduled frames (the player's clock runs on through silence, so after the first gap every slice read as already played and the channel went dark); a stamp at the render time (the engine renders 12–20 ms ahead, and the accumulator refuses a measurement time in the reader's future — a timeline with 60 hits per 2 s recorded zero observations); and a clamp to the getter's own `now`, which was still later than the `now` the meter had already captured. The stamp that works is when the playing slice *started*.

### Result — the C7.5 gate

| | before (tap) | after (D10) |
|---|---|---|
| input, arrival p95 | 139.1 ms | **25.2 ms** |
| input, displayed p95 | 204.3 ms | **25.2 ms** |
| playout, arrival p95 | 105.6 ms | **1.7 ms** |
| playout, displayed p95 | 171.1 ms | **67.6 ms** |
| capture age at callback | 108.3 ms | **14.7 ms** |
| tap cadence | 4800 frames, 10.0/s | **512 frames, 93.8/s** |
| **gate (p95 ≤ 150 ms)** | FAIL | **pass, 67.6 ms** |

`P2-latency.json`, 2026-09-13T23:01:07Z, 2,466 observations over 60 s on the deployment MacBook Air, built-in mic and speakers, both channels in one session. Playout's displayed figure exceeds its arrival figure because a level lingers in the snapshot between scheduled buffers; the 272 ms worst case is an utterance's tail decaying against the accumulator's 300 ms staleness window, not a delivery delay.

The report also learned to refuse a false pass: a session where one channel produced no observations now reads `incomplete`, because input passing at 25 ms while playout recorded nothing is not a passed gate.

## Open

- **§3.3 must be re-run on the D10 graph.** The sink node is a connection on the input node, and whether that changes Voice Processing's echo cancellation is exactly the question the C6 record lists as untested. The bench drives the real `AudioEngineIO`, so this is one run on built-in mic in a quiet room, same gate: zero Silero user turns on the bot's own playback. Until it passes, D10 is not signed off.
- **§3.4 is not answered by this.** The plan's method is mouth-to-ear round trip against the C0.4 WebRTC baseline, which still does not exist. What is now known is the buffering term (100 ms, removed) — not parity.
- §9.3's real-audio matrix, which C8 runs.
- Commit hygiene: the C7 **source** landed inside `5391db3`, whose message describes only the C6 §8 watchdog fix — the commit launcher's `git add -A macos docs` swept the working tree. The tests and this record are the commit that follows. Nothing was lost; the history is just less tidy than it reads.
