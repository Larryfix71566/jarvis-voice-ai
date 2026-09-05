# Mortimer native-audio transport — retire WebRTC on the local path

**Status:** DRAFT for Larry's approval, 2026-09-05. Implement **after** the
current gap-closure list is resolved (Larry's sequencing). Supersedes the
`AudioInputCoordinator` band-aid (2026-09-05, JarvisKit) — that stopgap is
deleted in this plan's Step 8. Written for a Sonnet-class implementer after a
frontier planner: every design decision is made here; the implementer builds,
it does not choose. Branch: cut from the gap-closure result, name TBD by Larry.
The implementer never runs git (same rule as every Mortimer plan).

---

## §0 Why this exists

The client moved from a browser to the native Swift app (MortimerHost /
JarvisKit). WebRTC was the right transport when the client was a browser —
browsers do real-time audio only over WebRTC. It is the **wrong** transport
now, for one specific reason: the client and the bot run on the **same Mac**
(`127.0.0.1:7860`). Everything WebRTC is built for — NAT traversal, ICE, DTLS,
SRTP, congestion control, Opus over a lossy internet — is dead weight on
loopback. What WebRTC *does* impose is Google's libwebrtc audio device module
(ADM), and that ADM is the direct, root cause of every audio-device problem
hit in this app:

- **2026-09-05, the AirPods slow-voice incident.** AirPods Pro 3 present a
  48 kHz output and a **separate 24 kHz microphone**. WebRTC runs ONE duplex
  audio unit (mic + speaker together, for echo cancellation), so 48 kHz playout
  got dragged through the 24 kHz capture clock: half speed, an octave low. The
  bot's audio measured normal throughout; the stretch was purely the ADM's
  duplex-rate handling. Worked around only by forcing the system default input
  to the built-in 48 kHz mic (the band-aid this plan removes).
- **The output device never follows.** The ADM opens the default output at
  playout init and never moves; when AirPods connect mid-session the voice
  stays on the old device. Worked around with a reconnect (a whole new bot
  session) — see `AudioOutputMonitor` / the Reconnect chip.
- **No device selection at all.** This WebRTC build (`stasel/WebRTC` 120.0.0)
  exposes no input- or output-device API (that lives only in the LiveKit
  `webrtc-sdk` fork). So every fix has to go through the *system* default
  device, which is invasive and fragile.

A native audio path removes the ADM entirely and gives the app full control of
capture, playout, device selection, rate handling, and echo cancellation —
which is exactly what a native app should own.

**This is not "drop WebRTC."** The platform roadmap's **T2 (remote access,
iOS over a VPN tunnel)** is a genuinely remote client over the internet, and
that is precisely what WebRTC is for. So the decision is: **native audio for
the same-machine path; keep WebRTC (`DirectWebRTCTransport`) for the remote
path; pick the transport by where the client is.** The `RTVITransport`
protocol already makes this a clean swap — `DirectWebRTCTransport` is one
conformer; this plan adds a second.

---

## §1 Scope

**In scope.** A `NativeAudioTransport` (JarvisKit) that conforms to the
existing `RTVITransport` protocol and, for a loopback bot, replaces WebRTC
with: (a) capture + playout through `AVAudioEngine` with Apple's Voice
Processing I/O for echo cancellation, and (b) a WebSocket carrying PCM audio
both ways plus the RTVI/app message frames. A pipecat server-side WebSocket
transport option selected for local connections. Transport selection in
`JarvisClient` by whether `botURL` is loopback.

**Out of scope (this plan).** The remote/T2 path keeps `DirectWebRTCTransport`
unchanged. No change to the wake-word listener (separate socket to `:7862`).
No change to the sidecar admin API, the display/agent message *shapes*, or any
UI. No new audio features (barge-in behavior, VAD tuning) beyond parity with
today.

---

## §2 What exists today (verified 2026-09-05)

- **`RTVITransport` protocol** (`JarvisKit/Sources/JarvisKit/RTVITransport.swift`):
  `connect(config:) async throws`, `disconnect() async`, `send(_ data: Data)`
  (one data-channel text frame), `setMicEnabled(_:)`, and a `delegate`
  (`transportDidConnect`, `transportDidDisconnect(error:)`,
  `transport(didReceiveFrame:)`, `transport(botIsSpeaking:)`).
  `DirectWebRTCTransport` is the sole conformer; `JarvisClient` builds it
  lazily and is otherwise transport-agnostic.
- **`DirectWebRTCTransport`** does: HTTP signalling → RTCPeerConnection → one
  audio track each way + one data channel for the RTVI text frames. `av`/
  `aiortc` on the server, `stasel/WebRTC` on the client.
- **`AudioSession`** (JarvisKit): on macOS both `activate()`/`deactivate()`
  are no-ops; echo cancellation today comes from WebRTC capture constraints
  (`googEchoCancellation` etc.). **`botIsSpeaking` is DEGRADED** — the plan's
  renderer-RMS mechanism does not exist in `stasel/WebRTC` M120, so it stays
  `false` all session (documented in `AudioSession.swift`). The native path
  fixes this for free (the client owns the player node — see §4).
- **Server** (`jarvis/bot/bot.py`): `SmallWebRTCTransport` only, built in the
  `SmallWebRTCRunnerArguments` case of `bot()`. `TransportParams(audio_in_
  enabled, audio_out_enabled, audio_in_filter)`. The pipeline
  (`jarvis/bot/pipeline.py`) is transport-agnostic below the transport: VAD →
  Deepgram Flux STT → Anthropic LLM → ElevenLabs TTS → output transport.
- **pipecat 1.4.0**, elevenlabs 2.61.0, aiortc 1.15.0, av 16.1.0 (the lock).

---

## §3 VERIFY FIRST — resolve these in Step 1 before building anything

I was wrong twice diagnosing the AirPods issue by theorizing ahead of
evidence; this plan will not repeat that. The following are **assumptions that
must be confirmed against the installed stack before a line of transport code
is written.** If any fails, stop and bring the finding to Larry — do not
improvise around it.

1. **pipecat has a WebSocket transport that carries bidirectional audio in
   this version.** Confirm the exact class and its serializer in the installed
   pipecat 1.4.0 (candidates: `WebsocketServerTransport`,
   `FastAPIWebsocketTransport`, `WebsocketServerParams` + a serializer such as
   `ProtobufFrameSerializer`). Confirm it streams `InputAudioRawFrame` /
   `OutputAudioRawFrame` and that a custom or raw-PCM serializer is available
   if Protobuf is unwanted on loopback. **If pipecat 1.4.0 has no suitable
   WebSocket audio transport, this plan changes shape (a custom pipecat
   transport, or a small WebSocket audio bridge) — decide with Larry.**
2. **The RTVI/app text frames can ride the same channel.** Today they are
   data-channel text frames (`transport.send`, `transport(didReceiveFrame:)`).
   Confirm how pipecat's WebSocket transport carries app/RTVI messages
   alongside audio (same socket, framed by the serializer, vs a second
   socket). The `AppMessage` decode on the client must be unchanged.
3. **Apple Voice Processing I/O echo cancellation is acceptable.** Confirm
   `AVAudioInputNode.setVoiceProcessingEnabled(true)` (macOS 14+) gives AEC/AGC
   good enough that the bot does not hear its own TTS through the mic, at the
   AirPods-output + built-in-mic and AirPods-both configurations. This is the
   one quality risk; measure it before committing (a bench test, §7).
4. **Latency parity.** Measure round-trip mouth-to-ear on the native path vs
   WebRTC on loopback. Expectation: equal or better (no Opus, no jitter
   buffer), but confirm — the AVAudioEngine buffer sizes must be tuned.
5. **Wake word unaffected.** Confirm the wake listener's separate `:7862`
   socket path is independent of the transport swap.

---

## §4 Design decisions (made — the implementer does not choose)

- **D1 — One new conformer, zero churn to the WebRTC path.**
  `NativeAudioTransport: RTVITransport` is added beside `DirectWebRTCTransport`.
  `JarvisClient` selects: `botURL` loopback (127.0.0.1 / ::1 / localhost) →
  `NativeAudioTransport`; otherwise → `DirectWebRTCTransport`. A
  `JarvisFlags.forceWebRTC` (default off) forces the old path for A/B and
  rollback.
- **D2 — Capture.** `AVAudioEngine.inputNode` with
  `setVoiceProcessingEnabled(true)` for native AEC/AGC/NS. Capture at the
  input node's format; resample to the wire rate (48 kHz mono PCM Int16 or
  Float32 — pick to match the pipecat serializer, §3.1) with
  `AVAudioConverter`. Any input device at any rate works — the converter
  handles it, which is the entire point (the AirPods 24 kHz mic just resamples,
  no duplex-clock trap).
- **D3 — Playout.** Received PCM → `AVAudioPlayerNode` → main mixer → output
  node. `AVAudioEngine` follows the system default output device and re-routes
  on device change (`.AVAudioEngineConfigurationChange`), so AirPods-follow
  and hot-plug are automatic — no reconnect, no `AudioOutputMonitor` hack on
  this path.
- **D4 — botIsSpeaking for free.** The client owns the player node, so it
  knows exactly when TTS audio is playing. `transport(botIsSpeaking:)` becomes
  accurate on the native path (it was permanently `false` under WebRTC),
  fixing the speaking label and the N10 wake-pause-while-speaking rule with no
  server change.
- **D5 — Wire.** One WebSocket to the bot: PCM audio frames both ways +
  the RTVI/app text frames, framed by pipecat's serializer (exact form per
  §3.1/§3.2). Raw PCM on loopback (no Opus) — bandwidth is a non-issue on the
  same machine and it removes codec latency and a failure surface.
- **D6 — `setMicEnabled` / barge-in / mute** keep their current semantics
  (stop feeding capture frames when muted; the aggregator's user-turn-start
  strategy still drives interruptions). No behavior change vs today.
- **D7 — Server selects the transport by connection kind**, mirroring D1:
  `bot()` builds `WebsocketServerTransport` (local) or `SmallWebRTCTransport`
  (remote). The runner/route decides; the pipeline below the transport is
  untouched (it is already transport-agnostic).
- **D8 — The `AudioInputCoordinator` band-aid is removed** once the native
  path is the default for local, along with its `JARVIS_MATCH_INPUT_RATE`
  flag and the input-notice UI — the native converter makes the whole
  mic-rate problem disappear. `AudioOutputMonitor` + the Reconnect chip stay
  (they still serve the WebRTC/remote path).

---

## §5 Files

**Client (JarvisKit / MortimerHost):**
- NEW `JarvisKit/Sources/JarvisKit/NativeAudioTransport.swift` — the
  `RTVITransport` conformer: WebSocket + `AVAudioEngine` capture/playout + VPIO.
- NEW `JarvisKit/Sources/JarvisKit/AudioEngineIO.swift` — the AVAudioEngine
  wrapper (capture tap, converter, player node, device-change handling),
  factored so it is unit-testable without a live socket.
- EDIT `JarvisKit/Sources/JarvisKit/JarvisClient.swift` — transport selection
  (D1); drop the macOS `audioInputCoordinator` wiring (D8).
- EDIT `JarvisKit/Sources/JarvisKit/JarvisConfig.swift` — `forceWebRTC` flag;
  remove `matchInputRate` (D8).
- DELETE `JarvisKit/Sources/JarvisKit/AudioInputCoordinator.swift` and its
  tests (D8).
- EDIT MortimerHost `AppMessageRouter` / `UICommandRouter` / `OrbFieldView` —
  remove the input-notice plumbing (D8). Output notice/Reconnect stay.

**Server (jarvis):**
- EDIT `jarvis/bot/bot.py` — add the `WebsocketServerTransport` case, selected
  for local connections; `SmallWebRTC` stays for remote.
- EDIT `jarvis/bot/pipeline.py` — only if the transport swap needs a different
  `TransportParams`/serializer wiring; the pipeline body is unchanged.
- Possibly NEW `jarvis/bot/ws_transport.py` — only if §3.1 finds pipecat's
  built-in WebSocket transport insufficient and a thin custom one is needed.

---

## §6 Implementation steps, in order

1. **Verify §3 end to end** on the installed stack. Write the findings into
   this plan before proceeding. This is a gate, not a formality.
2. `AudioEngineIO`: capture (VPIO on) → converter → callback of 48 kHz PCM
   frames; play(pcm) → player node; device-change re-route. Unit-tested with
   synthetic buffers (no socket).
3. `NativeAudioTransport`: conform to `RTVITransport`; open the WebSocket;
   pump `AudioEngineIO` capture frames out and inbound PCM into playout; route
   text frames to/from `delegate`; wire `botIsSpeaking` from the player node
   (D4). Mirror `DirectWebRTCTransport`'s lifecycle exactly (connect calls
   disconnect first if live; bounded outbound queue; keep-alive/stall = same
   thresholds).
4. Server: `WebsocketServerTransport` case in `bot()`, selected for local.
   Parity check: the same pipeline runs unmodified behind it.
5. `JarvisClient` transport selection (D1) + `forceWebRTC` (rollback lever).
6. Full parity pass against today's behavior: transcripts, tool events,
   display payloads, UI commands, mute, barge-in, wake word.
7. Remove the band-aid (D8): delete `AudioInputCoordinator`, its flag, its UI,
   its tests.
8. Docs: CLAUDE.md audio section, REPO_MAP, and this plan's Status → IMPLEMENTED
   (Larry, after §8).

---

## §7 Tests

- `AudioEngineIO`: converter produces the target rate/format from 24 kHz,
  44.1 kHz and 48 kHz synthetic inputs (the AirPods-mic case is a unit test,
  not a live gamble); device-change handler re-routes without dropping the
  player node.
- `NativeAudioTransport`: lifecycle (connect/disconnect/reconnect) against a
  stub WebSocket; text-frame round-trip decodes to the same `AppMessage` set
  as the WebRTC path; `botIsSpeaking` flips true only while the player node
  is playing.
- Server: the WebSocket transport carries an audio frame and an app message
  in one session (a pipecat-level test or a scripted client).
- Regression: the WebRTC path still builds and passes (it is untouched).

## §8 Verification Larry runs

- Local session on the native path: normal-speed voice on **AirPods for
  output while using the AirPods** (the whole point — no input band-aid, no
  system-default-input change). Then built-in speakers, then a wired output —
  all clean, and switching output mid-session follows without a reconnect.
- Echo test: with AirPods output + built-in mic, and AirPods-both, confirm the
  bot does not transcribe its own TTS (VPIO AEC quality, §3.3).
- The speaking indicator lights (botIsSpeaking real now).
- `forceWebRTC` on → old path still works (rollback proven).

## §9 Rollback

`JARVIS_FORCE_WEBRTC=true` → the client uses `DirectWebRTCTransport` for local
too, exactly as today. The server keeps the SmallWebRTC case, so nothing on
either side is removed until Larry is satisfied. The band-aid removal (D8) is
the last commit and is itself revertible.

## §10 Risks

- **AEC quality (highest).** Apple VPIO must suppress the bot's own voice as
  well as WebRTC did. If §3.3 shows it does not, options: keep server-side NS,
  add a reference-based canceller, or (last resort) keep WebRTC for local too
  and treat the AirPods fix as permanent via the band-aid. Decide with Larry
  at the §3 gate.
- **pipecat WebSocket transport fit.** §3.1 may find it needs a custom
  transport — scope grows; not a blocker, a fork in the plan.
- **Two transports to maintain.** Accepted: they serve different networks
  (local vs remote/T2) and share the `RTVITransport` seam and the whole
  pipeline below it.

## §11 Non-goals

Not touching the remote/WebRTC path, the wake listener, the sidecar, message
shapes, or UI. Not adding audio features beyond parity. Not removing WebRTC
from the codebase — it is the T2 transport.
