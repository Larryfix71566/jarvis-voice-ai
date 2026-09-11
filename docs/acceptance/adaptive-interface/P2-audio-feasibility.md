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
