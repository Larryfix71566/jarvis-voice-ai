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

## Open

- The hardware p95 (C7.5) and the debug menu item that dumps `P2-latency.json`.
- §9.3's real-audio matrix, which C8 runs.
- Commit hygiene: the C7 **source** landed inside `5391db3`, whose message describes only the C6 §8 watchdog fix — the commit launcher's `git add -A macos docs` swept the working tree. The tests and this record are the commit that follows. Nothing was lost; the history is just less tidy than it reads.
