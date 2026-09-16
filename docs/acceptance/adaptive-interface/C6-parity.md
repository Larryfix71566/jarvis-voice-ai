# C6 step 6 — parity pass, native transport vs WebRTC

Native-audio plan §6 step 6: "Full parity pass against today's behavior:
transcripts, tool events, display payloads, UI commands, mute, barge-in,
wake word."

Method: both paths read end to end, client and server, and every claim below
cites the line that supports it. Where a claim needs a running system to
settle, it is listed under **Open** rather than asserted.

Read at `3027078` (branch `fix/audio-device-resilience`), 2026-09-13.

---

## Parity holds

### Transcripts, tool events, display payloads (server → client)

One sender for both transports. `send_app_message` (pipeline.py:867) calls
`transport.output().send_message(OutputTransportMessageUrgentFrame(...))`
with the payload wrapped by `_wrap_rtvi` (pipeline.py:833) — the same
`{"label":"rtvi-ai","type":"server-message","data":…}` envelope on either
transport. Nothing in that path branches on transport type.

On the client both conformers hand the same bytes to the same delegate
method: `DirectWebRTCTransport` at :322, `NativeAudioTransport` at the
`.message(json)` case of `received(_:session:)`. `AppMessage.decode` then
runs identically. Transcripts, tool events and display payloads are all
carried inside that envelope, so they cannot diverge without the envelope
diverging.

### UI commands (client → server)

Different mechanism, same two handlers. WebRTC registers
`@webrtc_connection.event_handler("app-message")` (pipeline.py:1342);
the WebSocket path has no connection object, so `ClientMessageProcessor`
picks the messages off the pipeline as `InputTransportMessageFrame` and
`client_messages.bind(handle_voice_set, handle_ui_noop)` (pipeline.py:1350)
binds *the same two functions*. Neither path handles anything the other
does not.

### The pipeline itself

`bot()` builds a different transport per `match` case and then calls the
same `run_session(transport, …)` (bot.py:64). The only transport-conditional
code inside is the `client_messages` plumbing above and its
`build_pipeline(…, client_messages=…)` variant (pipeline.py:986). The
pipeline body is unchanged, which is what step 4's parity check asserted and
this confirms still holds.

### Barge-in

WebRTC needed nothing client-side: the server stopping TTS stops the media
track. The native path carries an explicit `interruption` frame, handled at
the `.interruption` case of `received(_:session:)` → `audio?.flushPlayout()`.
Both end with the queued TTS gone.

### Wake word

Same trigger condition on both: `wakeWordOn && state == .connected &&
!micEnabled` (`updateWakeListenerRunState`, JarvisClient.swift:~370). Only
the audio source differs — WebRTC opens the listener's own engine, native
feeds it from the transport's monitor tap (§3.5 measured that a second
engine costs VPIO its cancellation: 38.4 dB → 0.7 dB). The native source is
echo-cancelled, so this is strictly better input to the detector.

---

## Intentional divergences (improvements, recorded so they are not read as drift)

- **`botIsSpeaking` is real on the native path** and permanently `false` on
  WebRTC (DirectWebRTCTransport.swift:459-471 — no audio renderer API in
  this build). D4.
- **No output-device notice or Reconnect chip on the native path**
  (JarvisClient.swift:259-262): `AVAudioEngine` follows the default output
  itself, so the monitor is started only for `DirectWebRTCTransport`.
- **WebRTC intercepts signalling frames** (`renegotiate`, `peer-left`) before
  the delegate; the native path has no signalling to intercept.

---

## Divergences that are NOT improvements

### 1. `connect()` returns before the bot exists — the UI says connected ~5.4 s early

`JarvisClient` sets `state = .connected` immediately after
`await transport.connect(config:)` returns (JarvisClient.swift:251). What
that await means is not the same on the two paths:

- **WebRTC**: `connect` performs the `/api/offer` HTTP round trip, and the
  server answers it only after the session is built. Returning means the bot
  is ready.
- **Native**: `connect` ends at `socket.open()`, which only resumes the
  URLSession task. It returns before the WebSocket handshake completes, let
  alone before the server has built the session — measured at **5.4 s** on
  this Mac (socket accepted 13:08:36.941, pipeline started 13:08:42.351, §8
  finding).

So for roughly five seconds the app shows a connected session, starts the
audio meter, starts the stats timer and arms the wake listener against a bot
that cannot answer. Anyone who speaks in that window is talking to a server
whose pipeline is not running yet.

The machinery to fix this already exists: `establish(session:)` fires on the
server's first pong or first inbound frame and is exactly the "the bot is
alive" signal, with `nativeReadyDeadline` (30 s) already bounding the wait.
Making `connect` await establishment would give `state = .connected` the same
meaning on both paths. It is a deliberate change to the connect timeline —
a spinner for ~5 s instead of an instant, and slightly wrong, "connected" —
so it is written here as a finding, not silently applied.

### 2. Muting sends nothing, where WebRTC sent silence

- **WebRTC**: `micTrack?.isEnabled = false`. The track stays in the peer
  connection and the server keeps receiving an audio stream.
- **Native**: `captured(_:session:)` returns early on `micEnabled`, so the
  client stops sending audio frames entirely.

Whether the server minds a stream that simply stops is **Open** below.

---

## Open — not settleable by reading

- **Does the server tolerate a socket that sends no audio while muted?**
  Needs the installed pipecat's `FastAPIWebsocketTransport` (session timeout,
  receive-loop expectations). §8's "wake word while muted" check exercises
  exactly this.
- **Are capture frames sent between socket-open and pipeline-start buffered
  or dropped?** Same source needed. Only matters if divergence 1 is left
  as it is.
- **Output device switch mid-session** (§8) — also the measurement that
  should replace the guessed retry budget in the D3 amendment.
- **§3.3 echo on the two AirPods configurations** on the D10 graph.
- **§3.4 latency parity** — still blocked on a C0.4 WebRTC baseline that has
  never been captured.
