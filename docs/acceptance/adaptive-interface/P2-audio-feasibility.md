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
