# Review — MORTIMER_NATIVE_CLIENT_CORE_PLAN.md (T1.1/T1.2)

Reviewed against `/home/claude/repo` (jarvis-voice-ai-clean snapshot),
Pipecat 1.4.0 at `/usr/local/lib/python3.11/dist-packages/pipecat`,
`/home/claude/plans/BRIEF.md` (K1–K8).

**Counts: 6 BLOCKER, 9 MAJOR, 5 MINOR.**

The plan's *research* is unusually good — the `AppMessage` enumeration is
complete and its emitter citations are line-exact, and the copy strings are
verbatim. Its *execution surface* is where it fails: the two gates it defines
(G1(b) and the wake-word branch) cannot be run as written, and Branch B — the
default transport, and the largest single piece of work — is missing the
connection lifecycle a Sonnet implementer would have to invent.

---

## Findings

### F1 — G1(b)'s entire pass/fail procedure reads a log line that is never written [BLOCKER]

**Where:** plan §8 V7 (the six-scenario table), and "Corrections to the roadmap" item 2.
Repo: `jarvis/bot/interruption.py:1-121`, `jarvis/bot/pipeline.py:834-840`.

**What the plan says:** correction 2 — *"G1(b) is redefined mechanically in §8 (V5–V7) as: the same six frame scenarios, reproduced live through the native client, each confirmed from `logs/bot.log`."* §8 V7's right-hand column is headed **"Expected in `bot.log`"**, with rows *"one notice, `INTERRUPTION_NOTICE_MID_SPEECH`"*, *"**No** interruption notice line for that turn"*, *"exactly **one** notice"*.

**Why it's wrong:** `InterruptionNotifier` emits no log output of any kind. It has no `logger`, no `logging` import, and no `print`. Its only side effect is `await self._inject(note)`, and the injected callback (`pipeline.py:834-840 inject_silent`) does nothing but `aggregators.user().add_messages(...)` — it does not log either. The notice text exists only inside the LLM context object. There is therefore **no notice line in `bot.log`, ever**, and every V7 row's pass criterion is unobservable. Worse, the criterion is *asymmetrically* broken: rows 7a/7d/7e ("no notice") pass vacuously and rows 7b/7c/7f ("one notice") fail unconditionally — so a client with barge-in completely broken and a client with barge-in perfect produce the identical, unreadable result. This is precisely the "verification that doesn't verify" shape, and it is the gate the whole T1.2 deliverable is measured by.

**Evidence:**
```
$ wc -l jarvis/bot/interruption.py
121 jarvis/bot/interruption.py
$ grep -c "logger\|logging\|print(" jarvis/bot/interruption.py
0
```
The full `InterruptionFrame` branch, `interruption.py:112-121`:
```python
if isinstance(frame, InterruptionFrame):
    if self._assistant_active:
        if self._enabled:
            note = (INTERRUPTION_NOTICE_MID_SPEECH if self._audio_played
                    else INTERRUPTION_NOTICE_WHILE_THINKING)
            await self._inject(note)
        self._assistant_active = False
    return
```
And `pipeline.py:834-840`:
```python
async def inject_silent(text: str) -> None:
    aggregators.user().add_messages([{"role": "user", "content": text}])
```

**Fix:** the plan must not require a backend change (C1), so V7 needs an observable substitute. Two options, both executable today — pick one and write it into §8:
1. Change the criterion to **the next spoken turn**: after 7b, ask a follow-up ("what were you saying?"); pass = Mortimer's reply acknowledges being cut off. Weak but real, and it is what the notice is *for*.
2. Add `JARVIS_DEBUG_OBSERVER`-style observation on the **client** side instead: `MortimerHost` already gets `debugAudioStats`; extend V7's criteria to what the client can see — `botIsSpeaking` transitions and `sentPacketsLastSecond` across the interruption — and state plainly that the server-side notice is not observable without a backend change, carrying that to R-N6 alongside `RTVIObserver`.
Do **not** leave "read `bot.log`" in the plan; Larry will run it, see nothing, and have no basis to sign or reject.

---

### F2 — the wake-word branch probe command never terminates, so W1/W2 is undecidable [BLOCKER]

**Where:** plan §3 N10 ("Check (§5 step 10)"), §5 step 10, §8 V8, §11 item 8 (which cites this command as proof no judgment is left).

**What the plan says:**
> `curl -sS -o /dev/null -w '%{http_code}' --http1.1 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' http://127.0.0.1:7862/ws`
> - **`101` → Branch W1.** … **Anything else … → Branch W2.**

**Why it's wrong:** after a `101 Switching Protocols`, the connection is a live websocket. `jarvis/wakeword/server.py:79-90` then parks in `async for message in ws:` forever. curl has no `--max-time` and does not treat 101 as a completed transfer — it blocks reading the tunnel indefinitely and **never prints anything**, so `%{http_code}` is never emitted. The implementer/Larry gets a hung terminal, not `101` and not a failure code. Under the plan's own §0.6 rule ("If a command's outcome matches neither branch, **report and stop**"), the correct action is to stop — which means the wake word never gets implemented on the happy path.

**Evidence:** reproduced against a `websockets`-served endpoint on 7862 (same library and handler shape as `jarvis/wakeword/server.py`):
```
$ time timeout 8 curl -sS -o /dev/null -w '%{http_code}\n' --http1.1 \
    -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
    -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
    http://127.0.0.1:7862/ws
                       <-- no output at all
real    0m8.004s
EXIT=124                <-- killed by timeout
```
With `--max-time 3` added it does print the code, but exits non-zero and writes an error to stderr (which `-sS` shows):
```
$ curl -sS -o /dev/null -w 'CODE=%{http_code}\n' --max-time 3 --http1.1 -H ... http://127.0.0.1:7862/ws
curl: (28) Operation timed out after 3002 milliseconds with 0 bytes received
CODE=101
EXIT=28
```
Refused-connection case (the W2 trigger) also does not produce "anything else than 101" cleanly — it produces `CODE=000` and exit 7.

**Fix:** replace the check with one that terminates and yields a single token. Concretely:
```bash
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 --http1.1 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  http://127.0.0.1:7862/ws 2>/dev/null); echo "WAKE_PROBE=$code"
```
and state the branch rule as `WAKE_PROBE=101 → W1; anything else (including 000) → W2`. Also state explicitly that **both** W1 and W2 code paths are written regardless of the probe outcome (the implementing model has no Mac and cannot run the probe — §0.3 — so a build-time branch here is not executable at all); the probe result belongs in `PROBE.md` and in V8, not in a decision about which Swift file to write.

---

### F3 — Branch B never says the peer connection is rebuilt per `connect()`; connect → disconnect → connect is undefined [BLOCKER]

**Where:** plan §5 step 5 (steps 1-16), §5 step 7 (`connect()`/`disconnect()` behaviour).

**What the plan says:** step 5 is a flat ordered list beginning *"1. `RTCInitializeSSL()` once (a `static let bootstrap`). 2. Build `RTCPeerConnectionFactory(...)`. … 4. `let pc = factory.peerConnection(with: …)`"*, and step 15: *"`disconnect()` → cancel keep-alive, `dataChannel?.close()`, `pc.close()`, clear `storedPCID`."* Step 7: *"`connect()` — `state = .connecting`; resolve the transport (whichever branch exists); `try await transport.connect(config:)`."*

**Why it's wrong:** the list gives no lifetime for steps 1-7. Step 1 is explicitly once ("a `static let`"), which by contrast implies 2-7 are *not* once — but nothing says they run inside `connect()`, and step 4 reads like construction. A closed `RTCPeerConnection` cannot be reopened; neither can a closed `RTCDataChannel`. A Sonnet implementer who builds `pc` in `init` (the natural reading of an unqualified "Build … / let pc = …" in a numbered setup list) produces a client where the **second** Connect click silently does nothing. Connect → Disconnect → Connect is the single most-exercised path in `MortimerHost`: §8 V5–V7 has Larry running six scenarios back to back, and V8 has him restarting to test the wake word. The plan spends 16 numbered sub-steps on ICE batching and keep-alive intervals and zero sentences on the object graph's lifetime — which §11 item 2 claims to have audited ("Lifecycle left implicit … Stated:").

Two consequences the plan also leaves open:
- Step 14 (`.failed`/`.closed`/`.disconnected` → `transportDidDisconnect`) does **not** clear `storedPCID`, but step 15 (`disconnect()`) does. So after a network drop the client holds a stale `pc_id`; step 8 then POSTs it. Server-side that hits `request_handler.py:141-145` — `"PC ID mismatch with existing connection"`, HTTP **400** — if the server-side connection has not yet been reaped, and `_pcs_map.get(pc_id)` → `None` → a brand-new connection otherwise. Two different outcomes, neither specified.
- Step 8's justification is *"Store `answer.pc_id` in `storedPCID` — **required** for reconnects"*, while step 7 says *"There is no automatic reconnect in this plan."* Both cannot be the design.

**Evidence:** `request_handler.py:141-155`:
```python
if existing_connection.pc_id != pc_id and pc_id:
    raise HTTPException(status_code=400, detail="PC ID mismatch with existing connection")
if not pc_id:
    raise HTTPException(status_code=400,
        detail="Cannot create new connection with existing connection active")
```

**Fix:** add an explicit lifetime statement to step 5, e.g.: *"Steps 2–7 execute inside `connect()`, every time. `RTCInitializeSSL()` (step 1) and the `RTCPeerConnectionFactory` are process-lifetime statics; the `RTCPeerConnection`, the `RTCDataChannel`, the mic track, the ICE buffer and `storedPCID` are per-session and are created fresh on each `connect()` and released on each `disconnect()`. `connect()` on a transport that already holds a non-nil `pc` calls `disconnect()` first."* Then make step 14 clear `storedPCID` too, and delete "required for reconnects" from step 8 (`pc_id` is needed for the ICE `PATCH` in step 10 — that is the real reason, and it is derivable). Add a §7.5 test `testReconnectAfterDisconnectBuildsNewPeerConnection` against the stub transport.

---

### F4 — a missed keep-alive silences the bot's *audio*, not just inbound app messages; the plan states the wrong consequence and specifies no detection [BLOCKER]

**Where:** plan §1.1 ("Keep-alive is mandatory"), §3 N9.5, §6 `keepAliveInterval`, §10 R-N5.
Repo: `pipecat/transports/smallwebrtc/transport.py:437, 451, 499, 551-562`; `connection.py:656-672`.

**What the plan says:** §1.1 — *"A client that pings once and stops is worse than one that never pings."* R-N5 — *"The keep-alive is omitted or sent once, so `is_connected()` goes false and inbound app messages queue silently … **Impact:** `voice/set` and `ui/noop` stop working, with **no error anywhere**."*

**Why it's wrong:** the citation at `connection.py:656-672` is correct, but the plan traced only *one* of `is_connected()`'s consumers. `SmallWebRTCClient._can_send()` is `self.is_connected and not self.is_closing`, and it gates **`write_audio_frame`** — the bot's entire TTS output path — as well as `send_message` (server→client app messages) and `write_video_frame`. So a stale ping does not degrade the session to "voice works, controls don't"; it degrades it to **Mortimer goes completely mute while the pipeline keeps running and logs nothing**. That is the exact failure signature Larry would attribute to ElevenLabs or the transport, and the plan tells him it can only affect `voice/set`.

This matters for design, not just for the risk table: the plan's mitigation is a `debugAudioStats.lastKeepAliveAt` field in a *debug harness*, and there is **no client-side detection at all** — no watchdog, no state transition, no §7 test. Combined with §5 step 7's "no automatic reconnect", an app-nap-suspended `Task.sleep` loop (which is exactly what a 1 Hz `Task` in a background window does on macOS) produces a permanently silent, apparently-connected session with no recovery path.

**Evidence:** `transport.py:435-440` and `:551-562`:
```python
async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
    if self._can_send() and self._audio_output_track:
        await self._audio_output_track.add_audio_bytes(frame.audio)
        return True
    return False
...
def _can_send(self):
    return self.is_connected and not self.is_closing

@property
def is_connected(self) -> bool:
    return self._webrtc_connection.is_connected()
```
```
$ grep -n "is_connected" transport.py
320,383,472,485,553,556,562
$ grep -n "_can_send" transport.py
437:  write_audio_frame
451:  write_video_frame
499:  send_message
```

**Fix:** (a) correct §1.1 and R-N5 to state the real consequence — *"the bot's audio output stops, along with every server→client app message; there is no error on either side"*; (b) specify a client watchdog in §5 step 5.11: the keep-alive `Task` records `lastKeepAliveSentAt`; a separate 1 Hz check on the main actor transitions `state = .failed("keep-alive stalled")` and tears the transport down if more than `JarvisTuning.keepAliveStallSeconds` (default `2.5`, i.e. inside the server's 3 s window) has elapsed since the last successful send; (c) use a `DispatchSourceTimer` on a dedicated queue or `NSBackgroundActivityScheduler`, not a bare `Task { while true { try await Task.sleep… } }`, and say so — the plan's §0.7 forbids the implementer from "improving" the keep-alive, so the mechanism must be in the plan; (d) add `testKeepAliveStallFailsTheSession` to §7.5.

---

### F5 — the plan mandates Swift 6 language mode and then writes declarations that cannot compile under it [BLOCKER]

**Where:** plan §5 step 1 (`swiftSettings: [.swiftLanguageMode(.v6)]`), §5 step 5 (`RTVITransport` protocol), §5 step 7 (`JarvisSubscription`), §3 N6.

**What the plan says:**
```swift
.target(name: "JarvisKit", dependencies: [...], swiftSettings: [.swiftLanguageMode(.v6)])
...
protocol RTVITransport: AnyObject, Sendable {
    var delegate: RTVITransportDelegate? { get set }
    ...
}
protocol RTVITransportDelegate: AnyObject, Sendable { ... }
...
public final class JarvisSubscription { public func cancel(); deinit { cancel() } }
```
and §11 item 1: *"**Subscribe returns an unsubscribe:** yes … which unsubscribes on `cancel()` *and* on `deinit`, tested by `testSubscribeReturnsWorkingUnsubscribe` and `testSubscriptionDeinitUnsubscribes`."*

**Why it's wrong:** three separate strict-concurrency violations, each of which the implementer must resolve by *designing* something the plan does not contain — while §0.3(a) forbids it from writing anything not quoted in the plan, and §0.3 tells it it cannot compile to find out.
1. `deinit { cancel() }`: `JarvisSubscription` is not `@MainActor`, but unsubscribing mutates `JarvisClient`'s handler table, which is `@MainActor`-isolated (§5 step 7). A non-isolated `deinit` cannot call a `@MainActor` method, cannot `await`, and cannot escape `self` into a `Task`. The standard resolution — capture the subscription's *token* (a value type) plus a `@Sendable` removal closure at construction, and hop with `Task { @MainActor in remove(token) }` — is a design decision, and it is the one §11 explicitly claims is settled and tested.
2. `RTVITransport: Sendable` with a mutable stored-property requirement `var delegate: … { get set }` is not expressible as Sendable-safe; and `DirectWebRTCTransport` conforming to it holds `RTCPeerConnection`, `RTCDataChannel`, an ICE buffer, an outbound queue and `storedPCID` — none of which are `Sendable`. Under `.v6` this is an error, not a warning.
3. `JarvisConfig` is `Sendable` and holds `token: String?` — fine — but `AdminAPI` is a struct holding it and `JarvisClient` exposes it as `public lazy var admin`; `lazy` on a `@MainActor` class is fine, but the plan never says whether `AdminAPI` and the transports are actors, `@MainActor`, or `@unchecked Sendable`, and under `.v6` that choice is forced at every call site.

**Fix:** either (a) drop `.swiftLanguageMode(.v6)` from step 1 and say the package builds in Swift 5 language mode with concurrency warnings (the honest, low-risk choice for a package whose implementer cannot compile), or (b) keep `.v6` and write out the three declarations completely: make `DirectWebRTCTransport` an `actor` (or `@unchecked Sendable` with a stated internal serial queue) and drop `Sendable` from the protocols; replace `deinit { cancel() }` with the token+closure form, quoted literally:
```swift
public final class JarvisSubscription: Sendable {
    private let token: UUID
    private let remove: @Sendable (UUID) -> Void
    init(token: UUID, remove: @escaping @Sendable (UUID) -> Void) { self.token = token; self.remove = remove }
    public func cancel() { remove(token) }
    deinit { remove(token) }     // remove hops to MainActor internally
}
```
and state that `remove` is `{ t in Task { @MainActor in client?.handlers.removeValue(forKey: t) } }` built by `subscribe(_:)`. §0.7 ("use it verbatim") only works if the code is there.

---

### F6 — the C2 compliance claim describes a guard that appears nowhere in the plan [BLOCKER]

**Where:** plan header, "Roadmap constraints this plan is bound by", row **C2**.

**What the plan says:**
> **C2** — localhost is the trust boundary until G2 | … **§5 step 3 makes a non-loopback base URL a *compile-time-configurable, runtime-refused* condition until `JARVIS_AUTH_ENABLED=true` is confirmed by the health probe.**

**Why it's wrong:** §5 step 3 contains `JarvisConfig`, `JarvisFlags`, `KeychainStore` and `JarvisHTTP` in full, literal code. **None of them inspects the URL's host.** `JarvisConfig.default()` accepts whatever `JARVIS_BOT_URL` says, `JarvisHTTP.send` maps status codes and attaches a bearer, and neither refuses anything. There is no health probe in step 3, step 5 or step 7. §7.4's only related test, `testDefaultURLsAreLoopback`, asserts the *defaults* — it would pass unchanged on a build that happily connects to `http://203.0.113.4:7860` with no token.

Worse, the claimed mechanism is not derivable even if someone tried to build it: the confirmation source named is "the health probe", and the plan's own `AdminHealth` is `struct AdminHealth { public let ok: Bool }` — one boolean. The sidecar route it wraps returns exactly `{"ok": True}` (`jarvis/admin/server.py:707-709`), and there is no route anywhere that reports `JARVIS_AUTH_ENABLED`. So the C2 row asserts a safety property that is (i) unimplemented, (ii) untested, and (iii) not implementable against today's server.

This is a false premise in the highest-visibility part of the document — the table Larry reads to decide whether the plan is safe to approve. K1's threat model is that a non-loopback bind without auth is the fail-open case; a client that claims to refuse it and does not is worse than one that never claimed to.

**Evidence:**
```
$ sed -n '707,709p' jarvis/admin/server.py
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
```
§5 step 3's `JarvisHTTP.send` in full contains no host check (the plan quotes it verbatim; the only branches are on `http.statusCode`).

**Fix:** pick one and make the header row match it.
- Honest minimum: rewrite the C2 row as *"`JarvisConfig` defaults are loopback; nothing in this plan opens a port or contacts a non-loopback host by default. Enforcing a non-loopback refusal is T2's, since the confirmation signal (`JARVIS_AUTH_ENABLED`) is not exposed by any route today — carried as an open item."*
- Or implement it: add to step 3 a `JarvisConfig.validate() throws` that throws `JarvisError.insecureHost(String)` when `botURL.host` is not in `{"127.0.0.1","::1","localhost"}` **and** `token == nil`, called from `JarvisClient.connect()` before the transport is touched, plus §7.4 tests `testNonLoopbackWithoutTokenRefuses` / `testNonLoopbackWithTokenConnects`. Do not route it through a "health probe" that cannot answer the question.

---

### F7 — the decoder discards `peerLeft`, the only graceful end-of-session signal the server sends [MAJOR]

**Where:** plan §5 step 4 (`AppMessage.decode`, the `if t == "signalling" { return nil }` line), §7.1 `testDecodeSignallingFrameReturnsNil`, §5 step 5.12.
Repo: `pipecat/transports/smallwebrtc/connection.py:528-531, 785-793`.

**What the plan says:** *"`if t == "signalling" { return nil }` // connection.py:349"*, and §7.1: *"`testDecodeSignallingFrameReturnsNil` | `{"type":"signalling","message":{…}}` | `nil` (`connection.py:349` — signalling is the transport's, not ours)."*

**Why it's wrong:** the plan read `connection.py:349` (the *inbound* branch, client→server) and generalised it to the outbound direction, where the server is an active sender of signalling frames. `SmallWebRTCConnection.disconnect()` sends `{"type": "signalling", "message": {"type": "peerLeft"}}` over the data channel *before* closing the peer connection — that is how the bot tells the client "this session is over" (bot process shutting down, pipeline task ending, `run_session` returning). Step 5.12 hands every non-binary frame to `AppMessage.decode`, which returns `nil`, and nothing else in the plan looks at it. So a clean bot-side shutdown produces **no state change in `JarvisClient`**; the host keeps showing `connected` until libwebrtc's ICE/DTLS teardown eventually flips `RTCPeerConnectionState`, which Pipecat's own source comments warn is unreliable ("aiortc does not provide any way so we can be aware when we are disconnected"). And "signalling is the transport's, not ours" is precisely backwards for Branch B, where JarvisKit **is** the transport.

**Evidence:** `connection.py:528-531`:
```python
async def disconnect(self):
    """Disconnect from the WebRTC peer connection."""
    self.send_app_message({"type": SIGNALLING_TYPE, "message": PeerLeftMessage().model_dump()})
    await self._close()
```
```
$ grep -n "SIGNALLING_TYPE" connection.py
69:  SIGNALLING_TYPE = "signalling"
349: (inbound branch)
530: send_app_message({"type": SIGNALLING_TYPE, "message": PeerLeftMessage()...})
792: send_app_message({"type": SIGNALLING_TYPE, "message": RenegotiateMessage()...})
```
(`RenegotiateMessage` at 792 is reached only when a video/screen track exists — `connection.py:427-434` — so it is genuinely unreachable for this audio-only bot; that half of the plan's assumption is fine and should be stated as such rather than left to inference.)

**Fix:** in §5 step 5.12, intercept signalling before `AppMessage.decode`: parse `{"type":"signalling","message":{"type":…}}`; on `"peerLeft"` cancel the keep-alive and call `delegate?.transportDidDisconnect(error: nil)`; on `"renegotiate"` log `signalling_renegotiate_ignored` (unreachable for audio-only, per `connection.py:427-434`, but do not crash); anything else, log and ignore. Keep `AppMessage.decode` returning `nil` for signalling — that stays correct — but change §7.1's comment so the next reader does not conclude the frame is meaningless, and add `testPeerLeftDisconnects` to §7.5 against the stub transport.

---

### F8 — `AgentDone.ok` is declared non-optional but §7 requires it to default to `true` when absent [MAJOR]

**Where:** plan §3 N7 row 2, §5 step 4, §7.1 `testDecodeAgentDoneMissingOkDefaultsTrue`.

**What the plan says:** N7 row 2 — `ok: Bool`, `detail: String` (no `?`), governed by the stated rule *"optionality mirrors the JSON exactly (`?` = the emitter can omit it or send `null`)"*. §5 step 4 gives no custom `init(from:)` — only `"CodingKeys` map every snake_case name". §7.1 then requires:

| `testDecodeAgentDoneMissingOkDefaultsTrue` | same minus `ok` | `ok == true` (`agentRuns.ts:362`) |

**Why it's wrong:** with `let ok: Bool` and synthesized `Codable`, a payload missing `ok` throws `keyNotFound`. The test as written cannot pass, and the implementer must invent a decoder the plan does not contain — while §11 item 7 claims *"every fixture in §7.1 populates the members its case declares"*. The same trap sits on `detail: String` (absent in the same "older bot" payload the test describes), and on every other non-optional in N7 (`task`, `tool`, `latencyMs`, `verdict`, `label`, `action`, `modelUnusableDetail`): the plan's optionality rule is derived from *today's* emitter, but §7 tests *older* emitters, and the two rules contradict.

The consumer citation is right — `agentRuns.ts:360-363` really does say *"Bots predating ok/detail send neither — assume success"* — which makes this a specification gap, not a research gap.

**Evidence:** `web/src/agentRuns.ts:360-363`:
```ts
} else if (m.type === "agent" && m.state === "done") {
    // Bots predating ok/detail send neither — assume success.
    const ok = m.ok !== false;
    const detail = typeof m.detail === "string" ? clamp(m.detail, 300) : "";
```

**Fix:** add to §5 step 4 the literal decoder and state the rule once: *"Every non-optional scalar in `AppMessage`'s payload structs decodes with `decodeIfPresent` and a stated default: `ok` → `true`, every `String` → `""`, every `Int` → `0`, every `Bool` other than `ok` → `false`. Optionals (`?`) stay `decodeIfPresent` with `nil`."* Then give `AgentDone`'s `init(from:)` verbatim as the worked example, since it is the one §7 tests both ways.

---

### F9 — `messages: AsyncStream<AppMessage>` has no body and no semantics, on a contract two later plans consume [MAJOR]

**Where:** plan §3 N6, §5 step 7 (`public var messages: AsyncStream<AppMessage> { … }`), §11 item 1.

**What the plan says:** N6 — *"`messages: AsyncStream<AppMessage>` for structured consumers … Both paths receive **every** message; neither filters."* §5 step 7 declares it as a **computed property with an elided body**: `public var messages: AsyncStream<AppMessage> { … }`. §11 item 1 claims K8 is *"specified member-by-member"*.

**Why it's wrong:** every load-bearing decision about this member is missing, and each has a wrong-by-default answer a weaker model will pick.
- A computed property returning a fresh `AsyncStream` per access is the shape written. `AsyncStream` is **single-consumer**: two `for await` loops over `client.messages` each get a *different* stream, so the natural implementation (build a continuation in the getter, store it in a single `var continuation`) means the second consumer silently steals the first's, or gets nothing. N6's own promise ("both paths receive every message") requires a fan-out registry keyed per stream — which is exactly the multicast machinery the plan wrote out for `subscribe(_:)` and omitted here.
- Buffering policy is unstated. `AsyncStream`'s default is `.unbounded`; for a stream nobody iterates (the common case in `MortimerHost`, which uses `subscribe`), that is an unbounded leak of every `AppMessage` for the session's lifetime. Everywhere else the plan is scrupulous about bounded history (`outboundQueueMax`, `maxConversationEntries`, `maxHostMessages`) — this one is not.
- Lifetime is unstated: does `disconnect()` finish the stream? Does a stream created before `connect()` receive the post-connect messages? §11 item 2 audits `JarvisSubscription`'s lifetime and `voices`/`transcript` retention and says nothing about this.

This is self-audit item 1 verbatim ("Multi-consumer contracts named but not typed"), on the one contract this plan *introduces*.

**Fix:** replace the elided property with a literal declaration and rule in §5 step 7:
```swift
/// A NEW stream per call. Every stream receives every message from the moment
/// it is created until `deinit` or session end. Bounded: .bufferingNewest(200)
/// (JarvisTuning.messageStreamBuffer) — a stream nobody drains drops oldest.
public func messageStream() -> AsyncStream<AppMessage>
```
(make it a `func`, not a `var`, so "a new stream per call" is visible at the call site), register each continuation in the same fan-out table `subscribe(_:)` uses, and `onTermination` remove it. Add `JarvisTuning.messageStreamBuffer = 200` to §6 and `testTwoStreamsBothReceiveEveryMessage` + `testStreamBufferDropsOldest` to §7.5.

---

### F10 — `AdminAPI` untypes the *request* bodies, which are typed Pydantic models sitting in the repo; and "fourteen routes" is seventeen [MAJOR]

**Where:** plan §3 N14, §5 step 4 (`AdminAPI.swift` signatures), §7.7, §10 R-N10, §11 item 1, §12.

**What the plan says:** N14's justification is entirely about *responses* — *"the sidecar's **response bodies** are FastAPI dicts assembled inline, several of them shaped by whatever `jarvis/runlog/store.py` or `jarvis/memory.py` returns; typing all fourteen from a plan that cannot run them would put fourteen guesses into a contract."* Then §5 step 4 gives `selfeditRun(_ body: JSONValue) -> JSONValue` and `resolveReview(id: String, body: JSONValue) -> JSONValue`.

**Why it's partly wrong:** the *response* deferral is defensible and I would not block on it — `/api/runs`, `/api/memory` etc. really are assembled from store returns, and `JSONValue` is honest. But the two **request** bodies are declared Pydantic models in the same file the plan already read line-by-line, and are fully derivable. Passing `JSONValue` for them defers no risk — it *creates* one: T1.3 (or the implementer wiring the Edit tab) must guess the key names, and a wrong key is a silent 422 rather than a compile error. That is a design decision pushed downstream with no source cited, which the plan's own bar forbids. The stated rationale does not cover it, and §12's approval checkbox asks Larry to accept a narrowing described only as "response bodies".

Secondary, and countable: the plan says **"Fourteen routes"** in N14, **"the fourteen typed route wrappers"** in §4, **"all fourteen"** in §7.7, and **"seventeen method signatures and the fourteen routes"** in §11 — but N14's own table lists **seventeen** routes and §5 step 4 lists **seventeen** methods. §11 noticed the 17 and still wrote 14. An implementer told to write fourteen wrappers from a seventeen-row table has a contradiction to resolve.

Third: `/api/memory/reviews/{review_id}/resolve` takes `review_id: **int**`; the plan's `resolveReview(id: String, …)` percent-encodes a String. Non-numeric ids 422 at runtime instead of failing to compile.

**Evidence:**
```
$ grep -n "class GoalIn" -A 3 jarvis/admin/server.py
155:class GoalIn(BaseModel):
156:    goal: str = ""
157:    profile: str | None = None
161:    plan: str | None = None
$ grep -n "class MemoryReviewResolveIn" -A 7 jarvis/admin/server.py
214:class MemoryReviewResolveIn(BaseModel):
219:    action: str
220:    rewrite_content: str | None = None
```
All seventeen route citations in N14's table verify exactly (checked line by line against `jarvis/admin/server.py`; see "verified correct" below).

**Fix:** (a) type the two request bodies from the models above:
`selfeditRun(goal: String?, profile: String?, plan: String?, stagingId: String?) -> JSONValue` and `resolveReview(id: Int, action: String, rewriteContent: String?) -> JSONValue`, citing `server.py:155-161` and `:214-220`; (b) change every "fourteen" to "seventeen" (four places) or restate the table as "fourteen tab groupings, seventeen routes"; (c) narrow N14's stated deviation to *"response bodies only"* in §12's checkbox so Larry approves what is actually being deferred.

---

### F11 — V5/V7's precondition names a launcher that does not create the log file V5/V7 read [MAJOR]

**Where:** plan §8, "G1(b) — live voice session with barge-in", preconditions and V5.

**What the plan says:** *"Preconditions: `./scripts/run_bot.sh` running (`:7860`) …"* then *"**V5 — session.** … `logs/bot.log` contains `[session] client connected`"*, and V7 *"Run each and read `logs/bot.log`"*.

**Why it's wrong:** `scripts/run_bot.sh` ends with `exec python3 -m jarvis.bot.bot` — output goes to the terminal's stdout. `logs/bot.log` is created only by `scripts/mortimer.sh:85` (`nohup ./scripts/run_bot.sh >> logs/bot.log 2>&1 &`). Following the plan's preconditions literally produces no `logs/bot.log` at all (the directory does not exist in a fresh checkout — `ls logs/` → *No such file or directory*), so V5's and V7's assertions have nothing to read. Step-N-needs-what-step-N+2-produces, in the acceptance section.

**Evidence:**
```
$ tail -4 scripts/run_bot.sh
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis.bot.bot
fi
exec python3 -m jarvis.bot.bot
$ grep -n "bot.log" scripts/mortimer.sh
39:rotate_log() {  # name (e.g. "bot" -> logs/bot.log)
57:    exec tail -f logs/bot.log logs/admin.log logs/web.log
85:nohup ./scripts/run_bot.sh   >> logs/bot.log   2>&1 &
$ ls logs/
ls: cannot access 'logs/': No such file or directory
```

**Fix:** change the precondition to `./scripts/mortimer.sh start` (which rotates and creates `logs/bot.log`, `logs/admin.log`, `logs/web.log`) and note `./scripts/mortimer.sh logs` as the tail command; or keep `run_bot.sh` and change every `logs/bot.log` reference to "the bot's stdout". The first is better — V8 also wants the wake sidecar and V9 wants the sidecar up.

---

### F12 — `RTCAudioSession` is iOS-only, so the macOS `botIsSpeaking` path is an unwritten branch with invented constants [MAJOR]

**Where:** plan §5 step 8, third bullet; §6 (`speakingPollInterval`, `speakingLevelThreshold`, `speakingReleaseMS`); §5 step 7 (`botIsSpeaking` comes from the transport delegate).

**What the plan says:** *"`botIsSpeaking`: subscribe to the remote `RTCAudioTrack` via `RTCAudioSession`'s level reporting **where available**; otherwise derive from `RTCPeerConnection.statistics` polled at `JarvisTuning.speakingPollInterval` (0.2 s), reporting `true` when the inbound audio track's `audioLevel` exceeds `JarvisTuning.speakingLevelThreshold` (0.01)…"*

**Why it's wrong:** "where available" is the "similar to X" shape the brief names explicitly. `RTCAudioSession` is an iOS-only component of the WebRTC ObjC SDK (it wraps `AVAudioSession`, which does not exist on macOS), so on the plan's *primary* platform the answer is always "not available" and the fallback is always taken — meaning the plan's real specification for macOS is one sentence about polling a statistics API, with three magic numbers whose values are justified only by prose ("above the noise floor of a silent Opus stream", "longer than inter-word gaps"). The plan is otherwise rigorous about deriving numbers from source; these three are invented, untestable in §7 (they are excluded from every test file), and drive a `@Published` property that T1.3's whole speaking/listening UI will hang off.

The plan's own §0.3(a) — *"write nothing that depends on an API you have not seen quoted in this plan or in an existing file under `macos/`"* — makes this unimplementable as written: `RTCAudioSession` is quoted nowhere, `RTCPeerConnection.statistics` is quoted nowhere, and `audioLevel`'s presence on an inbound-rtp stats entry is asserted, not shown.

**Fix:** delete the `RTCAudioSession` clause. Specify one mechanism for both platforms, written out: register an `RTCAudioRenderer` on the remote `RTCAudioTrack` (`track.add(renderer)`) and compute RMS over each delivered `RTCAudioBuffer`, or — simpler and preferable here — **do not derive `botIsSpeaking` from audio at all in T1.2**. `botIsSpeaking` has exactly one consumer in this plan (`MortimerHost`'s debug label) and is not required by G1(b). Either drop it to T1.3 with the three constants, or state the renderer API literally with a §7 unit test over synthetic buffers (`testSpeakingHoldOffSuppressesInterWordGaps`, feeding a 0.3 s gap and asserting no transition).

---

### F13 — the wake listener and the WebRTC audio device fight over the microphone, with no rule stated [MAJOR]

**Where:** plan §3 N10, §5 step 8, §5 step 10, §8 V8.

**What the plan says:** step 5.6 acquires the mic through libwebrtc (`factory.audioSource(with: AudioSession.captureConstraints)` → `factory.audioTrack(...)` → `pc.add(track,…)`), and step 10 acquires it *again* through `AVAudioEngine`'s input node with an installed tap, resampled to 16 kHz Int16. Step 8 adds, on iOS, `AVAudioSession` category `.playAndRecord`, mode `.voiceChat`.

**Why it's wrong:** two capture graphs on one input device, and the plan never says whether they coexist, in what order they start, or what happens when one fails. Concretely unspecified:
- **Does the wake listener run while a session is connected?** V8's procedure has Larry connect first, then enable the toggle — so yes — but the wake word's entire purpose (`MicControls.tsx:77-80`, reproduced in step 10 as "set `micEnabled = true`") is to *unmute* a muted mic, which only makes sense while connected-and-muted. The plan states neither.
- On iOS, `.voiceChat` mode puts the input through VPIO; an `AVAudioEngine` input tap and libwebrtc's ADM cannot both own that unit. The plan declares `iOS 26` support and ships a listener that will not work there.
- The wake listener's audio is **not** echo-cancelled (it taps the raw input node, not libwebrtc's processed stream), so while Mortimer is speaking through the speakers, the sidecar scores Mortimer's own voice. The web client avoids this by accident — `micConstraints.ts` wraps `getUserMedia` globally, and its own comment says *"The wrap also covers the wake-word engine's mic acquisition"*. The native port loses that property and the plan does not notice.
- `AudioSession.captureConstraints` is applied to the WebRTC source only; there is no corresponding statement for the `AVAudioEngine` path.

**Evidence:** `web/src/micConstraints.ts:1-12` — *"client-js 1.13 / small-webrtc-transport 1.10 acquire the mic internally … so we wrap getUserMedia once at startup … The wrap also covers the wake-word engine's mic acquisition, which benefits from the same treatment."* The plan's step 8 cites this file (as "`micConstraints.ts:29-32`") but reproduces only the constraint list, not the coverage property.

**Fix:** state the rule in N10, three sentences: *"The wake listener runs only while `state == .connected` **and** `micEnabled == false` — that is the only state in which a wake event has an effect. Starting it stops nothing; on macOS both capture graphs coexist (CoreAudio permits multiple input clients). On iOS the wake listener is unavailable in T1.2 (`#if os(iOS)` → W2 with reason `\"wake word is macOS-only in this release\"`), because `AVAudioSession` `.voiceChat` mode does not permit a second input tap; T1.5 owns the iOS wake path."* Add to step 10 that the tap's audio is unprocessed and that the wake sidecar therefore hears Mortimer's TTS, and that the listener is paused for the duration of `botIsSpeaking` — or, if that is not wanted, say so and why.

---

### F14 — §6 declares nine `UserDefaults` tuning overrides that no step reads, and one knob with no consumer at all [MAJOR]

**Where:** plan §6 (the "Override" column), §5 step 3, §9.

**What the plan says:** §6's table gives each constant an "Override" entry — `JARVIS_KEEPALIVE_SECONDS`, `JARVIS_DC_DEADLINE_SECONDS`, `JARVIS_ICE_BATCH`, `JARVIS_ICE_BATCH_SECONDS`, `JARVIS_OUTBOUND_QUEUE_MAX`, `JARVIS_SPEAKING_POLL_SECONDS`, `JARVIS_SPEAKING_LEVEL`, `JARVIS_SPEAKING_RELEASE_MS`, `JARVIS_HTTP_TIMEOUT_SECONDS` — and §9 promises *"up to fourteen `UserDefaults` keys"* as revertible state.

**Why it's wrong:** §5 step 3 is the only place `UserDefaults` is read, and it reads exactly six keys: three URLs (in `JarvisConfig.default()`) and three booleans (in `JarvisFlags`). `JarvisTuning` is described in §6 as *"one `public enum JarvisTuning`"* of constants; nothing anywhere reads an override for it, and §7 tests none of them. So nine of the fourteen documented rollback levers do not exist. §9's "Point at a different bot/sidecar" row works; "tune the keep-alive without a rebuild" silently does not.

Separately, `JarvisTuning.dataChannelOpenDeadline` (10.0 s) has **no consumer at all**: no step in §5 starts a timer, fails, or logs on it. §6 justifies it as *"the client should fail loudly at the same moment"* — a behaviour that appears in no step and no test. This is self-audit item 7 ("every schema column populated by some step"), which §11 claims to have walked.

(The count is also off: 3 flags + 3 URLs + 9 tuning = 15, not fourteen.)

**Fix:** either delete the Override column for the nine tuning knobs and say plainly *"tuning constants are compile-time; only the three flags and three URLs are `UserDefaults`-overridable"* — and fix §9's count to six — or add to step 3 a literal `JarvisTuning` accessor mirroring `JarvisFlags`:
```swift
private static func num(_ key: String, _ fallback: Double) -> Double {
    UserDefaults.standard.object(forKey: key) == nil ? fallback : UserDefaults.standard.double(forKey: key)
}
```
with each constant expressed through it, plus one §7.4 test. Then give `dataChannelOpenDeadline` a consumer in step 5.11 (*"if the channel has not reached `.open` within `dataChannelOpenDeadline` after `.connected`, cancel and `transportDidDisconnect(error: JarvisError.transport(\"data channel never opened\"))`"*) or delete the knob.

---

### F15 — manifest/test drift: a test file missing from §4, a test with no file, and eleven fixtures for ~24 inputs [MAJOR]

**Where:** plan §4 (Create — `macos/JarvisKit/`), §7 preamble, §7.1, §7.6, §7.7, §9, §11 item 9.

**What the plan says:** §11 item 9 — *"Every file in §5 appears in §4 and vice versa — including `PROBE.md` (written in step 2), the eleven fixtures (step 4), and the two `templates/` files (step 14)."*

**Why it's wrong:** four distinct drifts, in the section that claims to have checked for exactly this.
1. **`WakeWordFramingTests.swift` (§7.6) is not in §4's manifest.** §4 lists five test files — `AppMessageTests`, `ClientMessageTests`, `SignallingTests`, `ConfigAndAuthTests`, `UICommandOwnershipTests` — and §5 step 10 refers to §7.6 by name. The file has no manifest row and no step that creates it.
2. **`testAdminRoutesBuildExpectedURLs` (§7.7) has no home file.** It is not in any of §7.1–7.6's tables and no `AdminAPITests.swift` exists in §4. It is also the only thing that would catch the seventeen-vs-fourteen problem in F10.
3. **Fixture count.** §7's preamble: *"Fixtures are eleven JSON files … each the **complete server frame**"*, and §4: *"(11 `.json` files) — one captured payload per `AppMessage` case + one unknown"*. §7.1 then enumerates 23 test functions requiring ~24 *distinct* inputs — `agent_done` with and without `ok`; `agent_activity` with and without `planner_model`; display with `window` / missing / `"hologram"` surface; the handoff, clipboard and radar display payloads; `ui` with and without `tab`; `speaker_gate` with `0.42` and with `null`; a bare unenveloped payload; a signalling frame; malformed JSON; a frame with no `type`. Eleven files cannot carry them, so the implementer must decide which are files and which are inline literals — while §7's preamble says all of them are fixtures.
4. **§9 references a UI that no step builds:** *"A stored token | `KeychainStore.setToken(nil, for:)` from **the host's debug menu**"*. §5 step 14's `HostView` is specified exactly — connect button, state label, two toggles, a stats `Text`, a `List` — and has no debug menu; §4 has no file for one.

**Fix:** add `macos/JarvisKit/Tests/JarvisKitTests/WakeWordFramingTests.swift` (step 10) and `.../AdminAPITests.swift` (step 4) to §4; change §7's preamble to *"Fixtures are eleven JSON files, one per `AppMessage` case plus one unknown, used by the eleven happy-path decode tests; the variant tests (missing/extra/malformed fields) build their JSON inline in the test body"* and mark which §7.1 rows are which; and either add a "Debug" `Menu` with a "Clear stored token" item to step 14's `HostView` spec, or change §9's row to "Keychain Access → delete the `com.mortimer.jarviskit` item" only.

---

### F16 — "the same six frame scenarios" is eight tests, two of which cannot be reproduced live, and V7 has a duplicate [MINOR]

**Where:** plan "Corrections to the roadmap" item 2, §8 V7.

**What the plan says:** *"the same **six frame scenarios**, reproduced live through the native client … see its assertions at lines 65, 85, 100, 118, 133, 147, 165, 181."* — six scenarios, eight line numbers.

**Why it's wrong:** `tests/unit/test_interruption.py` contains **eight** tests. Two are not reproducible through a live client at all: `test_disabled_flag_suppresses_injection` (line 147 — a `JARVIS_INTERRUPTION_NOTICE_ENABLED=false` kill-switch test) and `test_upstream_direction_ignored` (line 165 — a `FrameDirection.UPSTREAM` filter, invisible from outside the process). Of the six V7 rows, **7d ("let it finish; then speak a new turn") is the same proposition as 7a** — both are `test_completed_turn_produces_no_note`. So the mapping is: 7a≈test 1, 7b=test 4, 7c=test 5, 7e≈tests 2+3, 7f=test 8, 7d=duplicate of 7a, and tests 6+7 unrepresented. The claim that V7 is "the same six" is not true, and it is the sentence that justifies redefining a roadmap gate.

**Evidence:**
```
$ grep -n "    async def test_" tests/unit/test_interruption.py
55:  test_completed_turn_produces_no_note
67:  test_dropped_turn_with_no_reply_in_flight_produces_no_note
87:  test_repeated_dropped_turns_never_accumulate_notes
104: test_mid_speech_interruption
120: test_while_thinking_interruption
135: test_disabled_flag_suppresses_injection
149: test_upstream_direction_ignored
167: test_second_interruption_in_same_turn_not_double_counted
```

**Fix:** rewrite correction 2 as *"the five of `test_interruption.py`'s eight scenarios that are reachable through a live client; the kill-switch (line 147) and frame-direction (line 165) tests are process-internal and stay unit-only"*, and delete V7 row 7d or repurpose it as the *second* consecutive clean turn (which tests that `_assistant_active` resets — a distinct proposition worth having).

---

### F17 — `path:line` drift in several premise citations, one of them 25 lines off and repeated three times [MINOR]

**Where:** correction 1, §1.1, §1.2, §3 N8, N9.2.

**Why it's wrong:** the brief requires a `path:line` for every "today X does Y", and §0.7 tells the implementer these were "read out of Pipecat 1.4.0's source and cited". Several do not land:

| Plan says | Actually |
|---|---|
| `VADProcessor(SileroVADAnalyzer(VADParams(stop_secs=2.5)))` at `pipeline.py:653` (cited 3×: correction 1, §1.2, N9.2) | `pipeline.py:678` |
| `_wrap_rtvi` envelope at `pipeline.py:698-709` | `pipeline.py:697-706` (709 is `def _unwrap_client_message`) |
| `_unwrap_client_message` at `pipeline.py:711-729` | `pipeline.py:709-728` |
| empty/over-200 `ui/noop` reason dropped at `pipeline.py:1085-1087` | `pipeline.py:1088` |
| the two inbound handlers registered at `pipeline.py:1114-1117` | `pipeline.py:1113-1116` |
| `UI_ACTIONS` at `ui_control.py:25-31` / `UI_TABS` at `:33-35` / aliases at `:43` | `:25-32` / `:34-36` / `:44` |
| voice catalog at `pipeline.py:895-899` | `pipeline.py:896-900` |
| `micConstraints.ts:29-32` | the three constraints are `:30-32` |

None changes a conclusion, but `pipeline.py:653` is the anchor for the plan's most load-bearing negative claim (server-side VAD is the only turn detector) and is quoted three times; a Sonnet implementer told to verify it will open line 653 and find `turn_start_strategy = MinWordsUserTurnStartStrategy(min_words=2)` in a different branch.

**Fix:** re-derive the eight citations above. `grep -n "VADProcessor(vad_analyzer" jarvis/bot/pipeline.py` → 678.

---

### F18 — step 8 calls four `goog` constraints "the same three A1 protections" the web forces [MINOR]

**Where:** plan §5 step 8, first bullet.

**What the plan says:** *"`RTCMediaConstraints(mandatoryConstraints: ["googEchoCancellation": "true", "googAutoGainControl": "true", "googNoiseSuppression": "true", "googHighpassFilter": "true"], …)` — **the same three A1 protections** `web/src/micConstraints.ts:29-32` forces on every `getUserMedia` call."*

**Why it's wrong:** the web forces three (`echoCancellation`, `noiseSuppression`, `autoGainControl`, at `micConstraints.ts:30-32`). The plan lists four and adds `googHighpassFilter`, which has no web counterpart, while asserting parity. Small, but §0.7 forbids the implementer from adjusting the list, so the discrepancy is frozen in, and the sentence tells a reviewer parity was checked when a fourth item was added.

**Evidence:** `web/src/micConstraints.ts:29-33`:
```ts
audio: {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  ...audio,
},
```

**Fix:** drop `googHighpassFilter`, or keep it and say *"the three A1 protections plus `googHighpassFilter`, which the browser applies by default and the native stack does not."*

---

### F19 — `JARVIS_CLIENT_AUTH_ENABLED` is an undeclared addition to K1's switch set [MINOR]

**Where:** plan §3 N16, §5 step 3, §9; BRIEF K1.

**What the plan says:** N16 introduces `JARVIS_CLIENT_AUTH_ENABLED` — *"the client-side counterpart of K1's `JARVIS_AUTH_ENABLED`"* — and §11/§12 assert the `AdminAPI` `JSONValue` narrowing is *"the **one** place this plan narrows a contract"*.

**Why it's wrong:** K1 defines exactly one kill switch for bearer auth, `JARVIS_AUTH_ENABLED`, with fail-closed semantics (when false, the bind host is forced to loopback). The plan adds a second switch under the same naming convention with *no* fail-closed counterpart: `JarvisFlags.authEnabled == false` suppresses the token but does nothing about a non-loopback `JARVIS_BOT_URL` — the exact inverse of K1's discipline, and the same gap as F6. It may well be the right call (a client-side debug lever K1 did not anticipate), but it is a contract addition and the plan claims there is only one deviation.

**Fix:** list it in the header's "Contracts this plan CONSUMES" as an explicit K1 extension with its rationale, add it to §12's checklist, and give it K1's fail-closed shape: *"`JARVIS_CLIENT_AUTH_ENABLED=false` additionally refuses any non-loopback `botURL`/`adminURL`."*

---

### F20 — the token is snapshotted at construction, so a token minted later never attaches [MINOR]

**Where:** plan §5 step 3 (`JarvisConfig.default()`), §5 step 7 (`init(config: JarvisConfig = .default())`), §11 item 6.

**What the plan says:** `token: JarvisFlags.authEnabled ? KeychainStore.token(for: bot) : nil`, and §11 item 6 — *"`JarvisConfig.default()` reads the Keychain once at construction"* — stated as a resolved timing decision.

**Why it's wrong:** it is stated but not resolved. `JarvisConfig` is a value type held by `JarvisClient` and by `AdminAPI`; `KeychainStore.setToken(_:for:)` exists but nothing re-reads. The exact scenario T2 creates — Larry mints a token, pastes it into the host, and reconnects — produces a client still sending no `Authorization` header until the app is relaunched, and §9's "Token auth, without a rebuild" row implies otherwise. There is also no §7.4 test for it.

**Fix:** one sentence in step 7: *"`connect()` re-reads the token from the Keychain into `config` before building the transport, so a token stored while the app is running takes effect on the next connect without a relaunch."* Add `testConnectRereadsTokenFromKeychain` to §7.4.

---

## What I verified and found correct

Coverage note, so the complaints above are read in proportion — a lot of this plan holds up under a line-by-line check:

- **The `AppMessage` enumeration is complete.** I grepped the repo independently for every server→client push (`send_app_message`, `_wrap_rtvi`, `OutputTransportMessageUrgentFrame`, `RTVIServerMessageFrame`, and every `"type": "` literal under `jarvis/bot/`). The full emitted set is `agent` (working/done), `agent_tool`, `agent_activity`, `display`, `ui`, `voice/catalog`, `voice/current`, `speaker_gate` — eight wire types, nine cases split on `agent.state`. The plan's ten (those nine plus `capability`) is exactly right, and there is no eleventh. All four RTVI `ServerMessage` consumers in `web/src` (`AgentRunFeeder.tsx:23`, `App.tsx:217`, `VoicePicker.tsx:18`, `CapabilityChip.tsx:24`, `OrbField.tsx:118`) consume only those types.
- **The N7 emitter citations are line-exact**: `pipeline.py:188` (`activity_msg = {`), `:212` (`planner_model`), `:252`/`:263` (agent working block), `:279`/`:286` (agent done), `:288`/`:293` (agent_tool), `speaker_gate.py:337-340`, `ui_control.py:126`, `handoff_tools.py:159`/`:228`.
- **`AgentDone` really does lack `run_id`/`model`** — `pipeline.py:279-286` sends only `name`, `display_name`, `state`, `ok`, `detail`. **`planner_model` really is set only for `selfedit_start`/`selfedit_status`** — `pipeline.py:206-212`.
- **`DisplayPayload`'s sixteen members are exactly right.** `web/src/displayResults.ts:15-48` declares `kind, title, body, images, basemap_images, links, agent, ts, surface, tool, commands, note, expect_output, content, chars, truncated` — sixteen, matching the plan's table member for member, key for key. `display.py:147-162` populates the first ten; `handoff_tools.py:158-169` and `:227-236` populate the rest. `ts` is `time.time()` — epoch **seconds**, as the plan says.
- **The `surface` default is right**: `display.py` `DEFAULT_DISPLAY_SURFACE = "drawer"`, and `App.tsx:238-241` degrades missing/unrecognised to drawer with that exact rationale.
- **The three `ui/noop` copy strings are verbatim**: `MicControls.tsx:111, 115, 123`. **There is no `mic_unmute`** — `UI_ACTIONS` (`ui_control.py:25-32`) confirms. **`UI_TABS`** is exactly the seven the plan lists, and aliases resolve before validation.
- **All seventeen `AdminAPI` route line citations verify exactly** against `jarvis/admin/server.py` (707, 712, 755, 760, 795, 1214, 1226, 1324, 1445, 1461, 1473, 1501, 1518, 1576, 1586, 1595, 1679) — every one lands on its `@app.<verb>` decorator. `/api/health` really returns `{"ok": True}`.
- **The signalling wire format is right**: `SmallWebRTCRequest` (`request_handler.py:26-47`) and `IceCandidate`/`SmallWebRTCPatchRequest` (`:52-75`) have exactly the fields and snake_case names the plan's `OfferRequest`/`WireIceCandidate`/`PatchRequest` encode; `get_answer()` (`connection.py:548-562`) returns `{sdp, type, pc_id}`. The plan's insistence on explicit wire names over `.convertToSnakeCase` is correct.
- **The data-channel facts are right**: the client must create it (`connection.py:330`, no label check); `DATA_CHANNEL_TIMEOUT_SECS = 10` (`:77`); a text frame starting `ping` sets `_last_received_time` (`:344-346`); inbound app messages are queued when `not is_connected()` (`:352-357`); `is_connected()` behaves exactly as quoted (`:656-672`). (What the plan missed is the *breadth* of `is_connected()`'s blast radius — F4.)
- **`_unwrap_client_message` really does accept the raw shape** (`pipeline.py:709-728`), and the two handlers really are registered on the connection-level `app-message` event only (`:1113-1116`). N8 is sound.
- **Correction 6 is correct**: no `RTVIProcessor` or `RTVIObserver` is constructed under `jarvis/`, and `pipecat/runner/run.py`'s `/api/offer` path adds none (the only mention is `runner/utils.py:716`, a different helper this bot does not use). The observers list really is `[TranscriptObserver, InterruptionNotifier, SpeakingStateTracker]` (`pipeline.py:853-859`). So `ConversationEntry` really will stay empty, and saying so is right.
- **Correction 3 is correct**: `ls macos/MortimerShell/Sources/MortimerShell | wc -l` → 10, not 11.
- **Correction 5 is correct**: `JARVIS_ADMIN_URL` is read in exactly one place (`mcp_servers/mcp_selfedit/logic.py:20`), and the sidecar is `uvicorn.run(app, host="127.0.0.1", port=7861)` at `jarvis/admin/server.py:1779` with no auth.
- **The wake-word protocol facts are right**: port 7862 (`server.py:113`), bound `127.0.0.1` (`:120`), binary-only PCM (`:84-85` skips `str`), exactly 2560-byte chunks (`:37-38`, `:86-89`), text JSON `{"type","model","score"}` back (`:92-101`), `models/mortimer.onnx` required or `sys.exit` (`:63-69`), and `wakeWord.ts:14`'s URL is `ws://localhost:7862/ws`. Only the *probe command* is broken (F2).
- **`ask_to_renegotiate` is genuinely unreachable for this bot** — `connection.py:427-434` gates it on a video or screen-video input track, and `bot.py:34-40` enables audio only. The plan's silence on renegotiation is correct (its silence on `peerLeft` is not — F7).
- **The web stores really do return unsubscribe functions** (`agentRuns.ts:206-211`, `conversationFeed.ts:53-56`, `displayResults.ts`, `uiCommands.ts`), so N6's rationale is sound; `MAX_CONVERSATION_ENTRIES = 200` at `conversationFeed.ts:36`.
- **N9's core premise holds**: there is no inbound barge-in control message; the chain is `VADProcessor` → optional `SpeakerTap` → STT → optional `TranscriptGate` → `SpeakerVerifiedMinWordsTurnStartStrategy` (`speaker_gate.py:369`), all fed by raw inbound audio. Correction 1 is right and worth the space it takes.
- **C1 is honoured in fact, not just in claim**: §4's manifest contains no file outside `macos/`, and no step in §5 touches `jarvis/`, `mcp_servers/`, `config/` or `web/`.
