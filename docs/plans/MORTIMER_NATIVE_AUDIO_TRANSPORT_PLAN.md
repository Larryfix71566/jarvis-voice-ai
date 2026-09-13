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

### §3 findings — 2026-09-12 (C6 step 1, items 1, 2 and 5)

Verified against the installed **pipecat-ai 1.4.0** (`.venv` of the `jarvis-voice-ai-clean` checkout, `requirements-lock.txt:119`), with every file read checked against the wheel's `RECORD` (all `sha256=` entries match — the files are the published 1.4.0, unmodified). SHA-256 of the files read: `transports/websocket/server.py` `b1c6e3ee…`, `transports/websocket/fastapi.py` `ccf09739…`, `serializers/protobuf.py` `a9c0a278…`, `serializers/base_serializer.py` `79f28aa0…`, `frames/frames.proto` `adcd346a…`, `runner/run.py` `8551d184…`, `runner/utils.py` `72308dd4…`, `transports/base_input.py` `8bc46109…`. Items 3 and 4 are bench measurements on hardware and are still open (Larry).

**§3.1 — confirmed, with two corrections to the plan's candidates.**

- The transport is `pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport` with `FastAPIWebsocketParams(TransportParams)` (`add_wav_header`, `serializer`, `session_timeout`, `fixed_audio_packet_size`, `allowed_origins`, `ws_close_timeout`). `WebsocketServerTransport` exists but is **deprecated since 1.4.0** (an alias of `SingleClientWebsocketServerTransport`, `transports/websocket/server.py:635`, removal in 2.0) and it binds its own `websockets` server on a separate port; the FastAPI one rides the runner's existing `:7860` app. The runner already serves it: `_setup_websocket_routes` registers `/ws-client` and `/ws-client/{token}` on the same FastAPI app as `/api/offer` whenever `fastapi` + `websockets` import (`runner/run.py:455-494`, `_configure_server_app` registers every transport family regardless of `--transport`, `run.py:530-534`; `websockets 16.1.1` and `fastapi 0.141.1` are in the lock). A connection there calls `bot()` with `WebSocketRunnerArguments(websocket=…, transport_type="websocket")` (`run.py:441-452`). So **D7 is a second `case` in `bot()`**, not a second server: `case WebSocketRunnerArguments(): FastAPIWebsocketTransport(websocket=runner_args.websocket, params=FastAPIWebsocketParams(...))`; SmallWebRTC stays for `/api/offer`. Nothing about ports or the runner changes; `scripts/run_bot.sh` is untouched. Auth: `--ws-auth` defaults to `none` (`PIPECAT_WEBSOCKET_AUTH`), so the loopback client connects to `ws://127.0.0.1:7860/ws-client` with no token; the origin check passes an absent `Origin` header when `PIPECAT_ALLOWED_ORIGINS` is unset (`is_origin_allowed` returns True for an empty list) — a native `URLSessionWebSocketTask` sends no `Origin`, so that variable must stay unset (or the client must send one).
- Audio: the input transport deserializes each socket message and pushes `InputAudioRawFrame` into the normal audio path (`fastapi.py:359-374`); the output transport sends `OutputAudioRawFrame` per chunk and **paces them to real time** (`write_audio_frame` → `_write_audio_sleep`, `_send_interval = (chunk / rate) / 2`, `fastapi.py:454,509-590`), so the client needs only a small playout queue. **The WebSocket input path does not resample** (`BaseInputTransport.push_audio_frame` queues the frame as received, `base_input.py:188-195`; only SmallWebRTC has an `_audio_in_resampler`). The pipeline's input rate is `audio_in_sample_rate` (param) or the `StartFrame` default **16000**; output is `audio_out_sample_rate` or the default **24000** (`frames.py:922-923`), and every outbound audio frame carries `sample_rate`/`num_channels` in the protobuf. Therefore **D2's wire format is 16 kHz mono Int16 PCM upstream** (the client's `AVAudioConverter` targets 16 kHz, which is what SmallWebRTC resamples to today, so VAD/Flux see identical audio) and the client plays whatever rate the frames declare (24 kHz from ElevenLabs). The plan's "48 kHz" is replaced by this.
- Serializer: `ProtobufFrameSerializer` (`serializers/protobuf.py`, schema `frames/frames.proto`: `oneof frame { text, audio, transcription, message, interruption }`; `AudioRawFrame` = `bytes audio, uint32 sample_rate, uint32 num_channels`; `protobuf 6.33.6` installed). Raw-PCM-without-protobuf would need a custom `FrameSerializer` subclass (`serialize`/`deserialize`/`setup`, `base_serializer.py:23-100`) — not needed: the protobuf envelope is a few dozen bytes per 40 ms chunk and is the only built-in serializer that carries both audio and messages, so **D5 uses `ProtobufFrameSerializer` on the wire** and the Swift side needs a protobuf encoder for exactly five message types (hand-written varint encoding is enough; no SwiftProtobuf dependency required — decide in C6 step 3).

**§3.2 — confirmed: same socket, framed by the serializer — with one setting and one server-side change.**

- Outbound: `send_app_message` → `OutputTransportMessageUrgentFrame` → `serialize` wraps `frame.message` as `MessageFrame(data=json.dumps(message))` (`protobuf.py:88-95`); the client receives the same JSON the data channel carries today, `AppMessage` decoding unchanged (`AppMessage.swift:324-333` already accepts the `server-message` envelope). **Setting — corrected 2026-09-12 (same day, by the server test):** the base `FrameSerializer.InputParams.ignore_rtvi_messages` defaults to **True** and its filter drops every outbound message whose `label == "rtvi-ai"` (`base_serializer.py:51-69`) — which is every message `_wrap_rtvi` produces — but `ProtobufFrameSerializer.__init__` forces the flag to False after `super().__init__` (`protobuf.py:74-78`), so the stock protobuf serializer already carries these messages. The first version of this finding claimed the native path would be silent without an explicit flag; `test_wrapped_app_message_survives_the_serializer` showed a bare `ProtobufFrameSerializer()` serializing the envelope, and the constructor explains why. `websocket_params()` still sets `ignore_rtvi_messages=False` explicitly so the intent does not depend on that constructor detail, and the test shows the base filter dropping the message when re-enabled.
- Inbound: a `message` protobuf is deserialized to `InputTransportMessageFrame` and **broadcast into the pipeline** (`fastapi.py:373-374`). `FastAPIWebsocketTransport` registers only `on_client_connected` / `on_client_disconnected` / `on_session_timeout` (`fastapi.py:656-658`) — there is **no `on_app_message` event and no connection object**, so `pipeline.py`'s `@webrtc_connection.event_handler("app-message")` receive path does not exist on this transport. **Server change:** `handle_voice_set` / `handle_ui_noop` are reached through a small `FrameProcessor` placed after `transport.input()` that consumes `InputTransportMessageFrame` (running `_unwrap_client_message` as today), on the WebSocket case; the WebRTC case keeps the connection-level handler. This is the "possibly NEW `jarvis/bot/ws_transport.py`" item in §5 — it is a processor, not a transport.
- Also on the wire: the output transport serializes `InterruptionFrame` (`fastapi.py:491` `process_frame` → `_write_frame`; proto `interruption`). The native client must **flush its player queue on it** (drop queued TTS buffers), otherwise queued audio keeps playing after a barge-in; WebRTC hid this because the track simply stopped. Add to D3/D6.

**§3.5 — confirmed, with one bench item added.** The wake listener opens its own `URLSession.shared.webSocketTask` to `wakeWordURL` (`ws://127.0.0.1:7862/ws`, `JarvisConfig.swift:8,41`; `WakeWordListener.swift:104,223`) and streams 16 kHz PCM from its own `AVAudioEngine` input tap (`WakeWordListener.swift:162-178`); nothing in it references the RTVI transport. Independent of the swap. What is *not* independent: the listener runs while the session is connected and the mic is muted (`JarvisClient.swift:303`), so **two `AVAudioEngine` instances share the input device in one process**, one of them (the transport's) with Voice Processing enabled. Today's equivalent is the libwebrtc ADM alongside the wake engine, so concurrent capture itself is proven; the VPIO combination is not — it joins the §3.3 bench: wake word must still fire while the transport is connected, muted, VPIO on, on the built-in mic and on AirPods.

**§3.3 and §3.5 — measured 2026-09-13 on the MacBook Air (Mac17,4, macOS 26.6.2), built-in mic + speakers, quiet room.** Full numbers, discarded runs and log hashes: `docs/acceptance/adaptive-interface/C6-native-audio.md`. Two results override the text above.

1. **Voice Processing cancels, and the gate is met on this device.** With nothing else holding the input device, `AudioEngineIO` VPIO-on leaves the bot's own playback **6.0 dB *below* the idle noise floor** (39.2 dB below the VPIO-off residual), and the pipeline's own `SileroVADAnalyzer` with `pipeline.py`'s `VADParams` scores **0 speaking chunks and 0 user turns** on it (confidence max 0.156 against a 0.7 threshold), while the VPIO-off capture of the same signal raises 7 turns. So no server-side change is needed for §3.3's fallback list, on this configuration. The two AirPods configurations still need a run on the shipped graph (§3.3 asks for three).
2. **§3.5 is refuted: the wake listener must not open its own engine on the native path.** A second `AVAudioEngine` on the same input device — exactly what `WakeWordListener.startCapture()` does today — costs the transport's engine its cancellation (39.2 dB of reduction collapses to 0.7 dB; the residual sits 32.9 dB *above* the floor and Silero raises **9 user turns** on the bot's own voice) and the second engine itself receives **silence** on the built-in mic (`wakeRMS` 0 in every VPIO-on phase; on AirPods it did receive audio, so the deafness is device-dependent and the cancellation loss is not). Both symptoms are one cause. **Design change (approved by Larry, 2026-09-13):** on the native path the wake listener is fed from the transport's own processed capture tap and opens no engine — `AudioEngineIO.onMonitorPCM` (fires whether or not capture is enabled, since wake runs precisely while the mic is muted) → `NativeAudioTransport.setCaptureMonitor(_:)` → `WakeWordListener.feed(_:)`, with `WakeAudioSource.external` suppressing `startCapture()`. Measured in that shape: the wake path receives every buffer while muted (121 of 121 in both phases) and the canceller stays intact (residual 2.7 dB below the idle floor, 0 speaking chunks, 0 user turns). The wake audio is now echo-cancelled, which is strictly better input for the detector; N10 rule 4's pause during bot speech is kept unchanged. The WebRTC path keeps `.ownEngine` — libwebrtc's ADM tolerates the second engine, which is what ships today.

**Open (hardware, Larry): §3.3 on the two AirPods configurations, and §3.4 latency parity** — §3.4 needs the C0.4 WebRTC baseline captures first.

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
- **Amendments from the §3 findings (2026-09-12)** — these override the
  text above where they differ: D2 wire format is **16 kHz mono Int16 PCM**
  upstream (the WebSocket input does not resample; 16 kHz is what SmallWebRTC
  delivers to the pipeline today), playout at the rate each frame declares
  (24 kHz). D5 wire framing is pipecat's `ProtobufFrameSerializer` (which carries the
  `rtvi-ai`-labelled envelope; the flag is set explicitly anyway). D7's server class is
  `FastAPIWebsocketTransport` on the runner's existing `/ws-client` route —
  a second `case` in `bot()`, no new server or port. Inbound app messages on
  that transport are consumed by a small `InputTransportMessageFrame`
  processor (the WebRTC case keeps its connection-level handler). D3/D6: the
  client flushes its player queue on the serializer's `interruption` frame.
  Branch: `feat/native-audio-transport`, cut from `main` `6cdf1b8`.
- **D9 (2026-09-13, from the §3.3/§3.5 measurements):** the input node is
  **tapped, never connected**. With Voice Processing on, this Mac's input bus
  reports the mic array's 9-channel 48 kHz layout (1 ch before) and the output
  bus 0 ch / 0 Hz; a `mainMixer → output` connection with `format: nil`
  inherits that nothing and fails `kAUInitialize` (-10875), so that connection
  carries the hardware output format explicitly, read *before* VPIO is
  enabled. The tap takes `format: nil` and `CaptureConverter.firstChannel(of:)`
  feeds channel 0 to the converter (the `--channels` bench measured all nine
  channels identical). And on the native path the wake listener is fed from
  that same tap instead of opening its own engine (§3.5 above).

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
