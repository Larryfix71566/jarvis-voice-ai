# Dual-speaker audio feasibility — unresolved

Inspected 2026-09-11 at application commit `ca38c1f`. P2 is not implemented
or accepted. The existing voice wave still uses simulated speaking amplitude.

## Current authoritative evidence

The resolved dependency is stasel/WebRTC 120.0.0, revision
`3edaa8f0ddae889ad8ea236023de88672f6a16ec`. Read the installed framework headers
inside the same prepared offline VM used for native tests, task `66fed310bde6`.
Check `p0-current-audio-headers` read 431 header paths (including framework copies)
and returned successfully. This is a read-only inspection, not an audio trial.
Log SHA-256: `91e0cb123874afec749dd62ef977192b5683b9fc38c65633a4016cb88b5c9e17`.

- RTCAudioTrack exposes its source; no public audio-renderer callback was found.
  Header SHA-256: `934b31905b84994158abc0d0b870f02d41179a6ac1d0b3a675fd199bb4c961e8`.
- RTCAudioSource.volume is documented as gain in [0,10], not measured amplitude.
  Header SHA-256: `42a42cbb7bed995c0f0b3b8034ea6f545b1c9bf8a80690c659b42e2e57099e71`.
- Peer-connection statistics and sender/receiver statistics callbacks exist.
  Reports expose timestamped dictionaries. The header does not promise particular
  audio keys, update frequency, processed-input eligibility or playback alignment.
  RTCStatisticsReport header SHA-256:
  `23701a593d8ecc07554532d9b7a2983d2153762853578de80e2e76e44becf218`.
- A scan for RTCAudioRenderer, RTCAudioBuffer, audioLevel and
  audioProcessingModule found none in the exported headers. This does not prove
  dynamic statistics lack an audioLevel field; that remains a runtime question.
- DirectWebRTCTransport currently reads outbound packet/byte counters. Those are
  transport diagnostics, not speech amplitude. JarvisClient uses existing RTVI
  observer frames for bot speaking state; historical always-false comments are
  not authoritative about today's client behavior.

## What remains to prove

An isolated runtime probe must identify eligible microphone and actual-playout
observations for the active tracks, show their timestamps/freshness under silence,
speech and overlap, and measure the plan's latency targets. A field being present
is insufficient: received/decoded audio can precede audible output, and server
speech events cannot substitute for local microphone amplitude. The probe must
not record raw private audio or change capture devices, gain, sample rates,
echo cancellation, wake/mute/PTT or interruption behavior.

If statistics cannot satisfy these requirements, prepare a separately reviewed
additive observation design at the existing capture/playout path. The current
plan does not authorize a transport upgrade/rewrite or a second microphone engine
as a workaround. Do not enable an invented envelope or call a gain value a meter.

Real-device feasibility and paired quality/latency acceptance remain open. This
finding blocks claiming P2 complete; it does not block independent implementation
or verification of the other phases. No candidate audio code or live app was
changed during this inspection.

## Muted runtime schema probe (2026-09-11)

At local application commit `46da90a`, a disposable XCTest was transferred into
JarvisKitTests in the offline VM, executed alone, and removed afterward. Its
reproducible source is `probes/AudioStatisticsProbeTests.swift` beside this record;
it is deliberately outside the shipping target and ordinary test suite. To repeat,
copy it into the disposable VM's JarvisKitTests, run `swift test --package-path
macos/JarvisKit --filter AudioStatisticsProbeTests`, then remove the temporary file.
Never run this candidate probe on the production host.

The probe creates one local peer connection with the existing capture constraints,
disables its synthetic microphone track before adding it, and creates a local
offer. It has no remote peer, server connection, credentials, enabled microphone,
or raw audio recording. This is a schema observation, not a voice acceptance test.

Check `p2-muted-statistics-probe` returned exit 0 in 3.654 verifier seconds.
Log SHA-256:
`824ae7bbc615212e6dec2995e9d1cc92d7f97e51701c1d71574f588e9ca558ce`.
All 12 reports contained an audio `media-source` record with `audioLevel`,
`totalAudioEnergy`, `totalSamplesDuration`, and `trackIdentifier`. Level, energy
and sample duration were zero throughout, consistent with the disabled source.
An `outbound-rtp` record included `mediaSourceId`, supporting explicit association
rather than selecting an arbitrary audio record. No inbound/playout record was
observed in this unnegotiated connection; that does not prove its absence in a
connected session.

Reports 8 and 9 had exactly the same statistics timestamp. The probe slept at
least 33.3 ms between completed callbacks, but did not independently instrument
callback latency or scheduling. Neither its report intervals nor its zero values
establish active-source freshness, processed speech eligibility, the noise floor,
echo rejection, or the 150 ms display latency target.

This changes the next step from guessing whether an input level key exists to
measuring this specific source-linked candidate under controlled active audio.
Any observer must reject repeated/older timestamps, bind to the current session
and track, and expire stale levels independently of callback arrival. Receiver
statistics still need separate evidence of actual playout correspondence. P2
remains incomplete; no production transport, meter or wave behavior changed.

## Muted connected-peer receiver schema probe

A second disposable probe exchanges local SDP between two peer connections inside
the offline VM. Both tracks are disabled before adding them; no production
signalling, credentials, enabled microphone or private audio is used. Source:
`probes/ConnectedAudioStatisticsProbeTests.swift`. Copy it into the disposable
JarvisKitTests directory, run its named filter, then remove it; it is not part of
the ordinary test suite or application target.

Check `p2-muted-connected-probe`: exit 0, 8.499 verifier seconds; log SHA-256
`d00a4d3067ef8fe3eddbd2462de8b9cbcfc0a93dbdca3523a74d0e258933ba1a`.
The runtime reported peer connection state raw value 2 and ICE state 3. It exposed
inbound-rtp, outbound-rtp and media-source audio records. Inbound keys included
totalAudioEnergy, totalSamplesDuration, totalSamplesReceived, jitterBufferDelay
and jitterBufferEmittedCount. The inspected receiver record did not include
`audioLevel`; no media-playout record was observed. Energy/sample counters were
zero, so this is a negotiated schema probe, not proof of active audio decoding or
physical playout. It cannot establish whether extra fields appear with live media.

The result strengthens the need for active audio trials: cumulative receiver
energy may describe decoded/received audio and must not be labeled actual speaker
output without alignment measurements. Source levels remain a candidate input
signal, not proof of processed user-speech eligibility or echo rejection. P2 stays
incomplete, with no production visualization or transport changes from this probe.

## Observation validity boundary implemented

AudioActivitySnapshot and AudioActivityAccumulator now define the presentation
measurement boundary in JarvisKit. They hold normalized optional levels, a
connection generation, and monotonic measurement times; no raw audio. Missing
levels remain distinct from measured zero. Snapshots expire levels after 300ms
even if callbacks stop. Duplicate timestamps cannot renew freshness; wrong-session,
future, nonfinite and out-of-range observations are rejected. Muting immediately
clears input without suppressing output; delayed pre-unmute observations cannot
reappear after eligibility resumes. Reset clears both levels and eligibility.

Offline full JarvisKit check `p2-activity-eligibility-boundary` passed 109 tests,
including four new behavioral tests, in 1.507 verifier seconds. SHA-256:
`709c7f76cf1256fbaa2976f9f1f5347ece19a022ba9c8e33abca6b1c07c4345a`.

This boundary is not yet wired to transport or the wave. An adapter still must
prove eligible processed input and actual playout provenance, use measurement
time rather than callback arrival, and enforce the observation-rate budget.
The two channel names express required provenance; they do not establish it.
Active-audio feasibility, UI smoothing/state integration, and real-device
quality/latency acceptance remain required. P2 remains incomplete.

## Presentation state and original observation deadlines

VoicePresentationState now derives offline/connecting/listening/user/assistant/
thinking/muted states without writing to audio controls. Eligible user audio
takes visual priority during overlap while assistant activity remains available.
Muted status is orthogonal to output, silence cannot invent thinking, and missing
levels remain explicitly unavailable. VoiceEnvelope uses elapsed-time exponential
attack (40ms) and release (180ms); unavailable observations clear immediately.

Review found that a snapshot created near expiry could otherwise renew a sample's
life. AudioActivitySnapshot now carries original per-channel measurement times.
The presenter checks those times as well as the snapshot generation and time. A
regression covers a snapshot made at 290ms and rendered at 310ms: it cannot expose
the old input as current speech. Other tests cover overlap, mute/output, missing
levels, stale sessions, connection precedence and equivalent 30/60Hz smoothing.

Full offline checks passed:
- JarvisKit: `p2-measurement-deadlines-library`, 109 tests, SHA-256
  `93fdacc75e8c0b8c4c795998bb2ae395ec0ada228f4b5d8998744bd25c6024cc`.
- MortimerHost: `p2-measurement-deadlines-host`, 114 tests, SHA-256
  `7d7c8056f0a0067ae928067bdbae2a6a259df78033790a8daee7e565189c818f`.

These types are compiled but not yet connected to the actual wave or transport.
They establish presentation policy, not active metering or physical latency.
The existing wave still has its simulated envelope; removing it from the new
presentation and supplying proven observations remain required before P2 passes.

## Adaptive renderer connected; live source still missing

AdaptiveStageView now supplies VoicePresentationState to Silo and the preserved
OrbField readout. Silo retains its layered geometry and explicit wake flash.
The adaptive branch never calls simLevel: it smooths provided measured levels,
uses teal for user and violet for assistant, and renders a static trace when
measurements are missing. OrbField shows the derived status and an explicit
Audio level unavailable message while preserving existing captions and notices.
The previous layout's simulated path remains available only as the legacy
rollback presentation. This change does not enable adaptive layout by default.

Native rendered tests compare unavailable-speaking PNGs ten seconds apart
(they are identical) and inspect actual rendered pixels for distinct teal and
violet using synthetic measured inputs. `p2-wave-rendered-truth` passed the full
116-test host suite, 36.658 verifier seconds; SHA-256:
`f25de52955e453b56b25c22a75fca8d98164b80bbe29ead7c7dfe62e7787c2d2`.
A subsequent source-only edit clarifies the renderer documentation.

The adaptive production provider explicitly supplies no audio snapshot because
P0 has not proven the observation source. Consequently live user audio does not
yet drive the wave. These fixtures prove rendering behavior with supplied values,
not microphone eligibility, playout timing, capture quality, or latency.
The fallback is runtime resilience, not completion of P2. Actual observation
adapter integration and paired hardware acceptance remain mandatory. Also verify
window occlusion/minimization animation suspension and Reduce Motion on hardware;
appear/disappear pausing alone is not full visibility acceptance.

## Exact pinned upstream source traced

The [120.0.0 release](https://github.com/stasel/WebRTC/releases/tag/120.0.0)
identifies WebRTC source commit `b0cc68e61205fd11a7256a6e85307ec17ad95790`.
Eight relevant files were fetched at that exact commit and hashed in
P2-upstream-source-manifest.json. They match the corresponding inspected M120
branch files; conclusions below use the pinned commit, not current main.

- [audio_level.cc](https://webrtc.googlesource.com/src/+/b0cc68e61205fd11a7256a6e85307ec17ad95790/audio/audio_level.cc)
  holds a peak level and updates it every eleventh nominal 10ms frame, roughly
  9.09Hz. Its cumulative energy calculation uses that held value too. Taking
  energy differences therefore does not recover an independent fresh RMS signal.
- [audio_send_stream.cc](https://webrtc.googlesource.com/src/+/b0cc68e61205fd11a7256a6e85307ec17ad95790/audio/audio_send_stream.cc)
  computes these levels in SendAudioData before encoding. The inspected native
  AudioTransportImpl path invokes senders after ProcessCaptureFrame and optional
  asynchronous processing. This is stronger evidence for a processed-input seam,
  but does not by itself prove quiet-speech, noise or echo eligibility.
- [channel_receive.cc](https://webrtc.googlesource.com/src/+/b0cc68e61205fd11a7256a6e85307ec17ad95790/audio/channel_receive.cc)
  updates receiver levels inside GetAudioFrameWithInfo after channel gain. This
  is the audio mixer's pull path, not simply packet arrival. It still precedes
  final device rendering, and uses the same held-level implementation.
- [rtc_stats_collector.h](https://webrtc.googlesource.com/src/+/b0cc68e61205fd11a7256a6e85307ec17ad95790/pc/rtc_stats_collector.h)
  defaults to a 50ms report cache. A fresh report timestamp does not establish
  a fresh level measurement. The previous duplicate-timestamp probe is consistent
  with this caching but did not measure all of these intervals.

These findings rule out treating 30Hz polling or energy differences as proof
of 30Hz fresh levels. They do not constitute a measured failure of the 150ms
p95 target: that still requires active-audio trials. Before wiring these stats
into AudioActivityAccumulator, an adapter must establish actual measurement
times; using collection time would violate the current validity contract.

A concrete separately reviewed observation proposal is recorded in
P2-additive-observation-design.md. No framework was rebuilt, dependency replaced,
capture enabled or production audio changed during this source investigation.
