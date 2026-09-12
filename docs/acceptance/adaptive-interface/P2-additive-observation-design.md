# Additive audio observation proposal

**RETIRED 2026-09-11** by `docs/plans/MORTIMER_ADAPTIVE_INTERFACE_CLOSURE_PLAN.md` locked decision L1: measured levels come from the native-audio transport's own `AVAudioEngine` taps (closure C6/C7), not from taps inside the pinned WebRTC build. Kept as a record; not implemented.

Status: design for separate review; not implemented, approved or accepted.
Scope: remove the exact pinned framework's measurement-timestamp and held-level
limitations without changing the captured or rendered audio. P2 remains open.

## Decision and alternatives

Do not connect existing getStats levels to the production meter as though report
time were measurement time. The pinned source evidence in P2-audio-feasibility.md
shows why polling faster and differentiating energy do not fix that problem.
Continue active-audio feasibility to determine whether existing statistics can
meet the target with independently established timing. If they cannot, the
preferred additive approach is a narrow observation bridge on the same pinned
source, not a WebRTC version upgrade or replacement audio engine.

A framework source patch needs its own review and reproducible build before it
can enter this application. Do not change the package URL, checksum, framework,
transport, audio constraints or gate thresholds merely to make a prototype run.

## Observation locations

Input candidate: the existing native processed-frame path immediately before
AudioSendStream sends the frame onward for encoding. Verify its route from the
active microphone track, including asynchronous processing, mute, wake and PTT.
The observer must not alter samples, buffer ownership, gain or audio scheduling.
Eligibility still requires the existing processed-speech evidence and a measured
noise floor. A post-processing level alone does not authenticate or recognize speech.

Output candidate: the existing device-render callback's final buffer after mixer
and resampling, before it returns to the audio device. Compare this with the
per-receiver mixer-pull point to measure the remaining delay. Verify which native
callback the shipped macOS audio device uses; do not assume NeedMorePlayData is
active solely because it exists in upstream source. Associate the observation
with the active app session, account for device changes, and prove it cannot
include an unrelated peer or app's audio. System output mute and unreachable
output devices must retain their truthful notices.

## Real-time and ownership contract

The observation records only a bounded normalized level, channel, original
monotonic measurement time, and source/session identity. Compute the level from
the buffer already present; never retain, record or transmit PCM. Define RMS and
peak explicitly and validate normalization for every supported format/channel count.

Audio callbacks must not call SwiftUI, allocate an event queue, log, perform I/O,
wait on another thread, or hold a new contended lock. Publish into a preallocated
latest-value slot using an implementation whose atomic behavior is verified on
the target architecture. The reader must receive a coherent record; do not assume
that a multi-field struct assignment is atomic. Overwrite/drop observations under
load instead of blocking audio. A disabled observer must have negligible measured
overhead and must not change buffer contents or callback results.

One non-audio owner samples those slots at no more than 30Hz, rejects wrong-session
and stale source records, and supplies AudioActivityAccumulator using measurement
time. Preserve per-channel times through VoicePresentationState. Do not open a
second microphone or reconnect the transport for layout changes. Disconnect,
track replacement, mute and device change invalidate affected observations before
old callbacks can revive them. Teardown must outlive any in-flight callback safely.

## Build and review evidence required

Record exact upstream source commit, unmodified build recipe/toolchain/flags,
original archive checksum, patch, rebuilt archive checksum and exported API diff.
First build the unmodified pinned source as a control. If that build cannot be
reproduced, report the missing input instead of silently updating dependencies.
Review the patch for audio-path changes beyond observation; keep the old framework
available for rollback. Add source and artifact provenance to the sandbox profile
without weakening its network, allowlist or independent verification rules.

## Acceptance before production integration

1. In the offline disposable environment, compare original/observed paths with
   generated silence, steps, speech-like bursts, overlapping streams, format
   changes and teardown races. Verify unchanged audio buffers and bounded cost.
2. Demonstrate actual measurement-time freshness and no stale replay through
   callback stalls, duplicate reads, disconnect/reconnect and mute/PTT transitions.
3. On the deployment Mac, use the required built-in microphone/speakers and
   headphones/AirPods. Measure echo-only, background sound and quiet/loud speech;
   establish eligible input and device-specific noise behavior without changing
   voice processing to improve the display.
4. Measure eligible input-to-displayed-frame and output-to-playout alignment,
   retaining the plan's p95 150ms target. Include device buffering and display
   scheduling; neither a callback timestamp nor a synthetic screenshot is proof.
5. Run at least 20 paired baseline/candidate voice trials and the full frozen
   verification profile. Preserve the plan's quality and latency gates. Record
   inconclusive results as inconclusive, never as acceptance.
6. Only then replace the adaptive provider's explicit missing snapshot with the
   verified observer. Recheck colors, overlap priority, captions, all notices,
   hidden-window suspension, reduced motion, and layout changes during speech.

This proposal does not authorize deployment or a dependency replacement. Existing
header, workspace, graph and monitor work can continue while P2 is unresolved.
