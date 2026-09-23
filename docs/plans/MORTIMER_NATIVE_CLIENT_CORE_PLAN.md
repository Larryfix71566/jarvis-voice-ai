# Mortimer native client core — visual-ceiling spike and JarvisKit

**Status:** IMPLEMENTED (code), verified through §8's build-and-unit gate as of 2026-09-15. Implements roadmap track T1, sub-items **T1.1** (visual-ceiling spike) and **T1.2** (`JarvisKit` shared Swift package), plus the minimum macOS host app needed to pass gate **G1(b)**.

**§8 status.** V1–V4 (build and unit gate) pass: `macos/JarvisKit` builds and runs **170 tests** green, `macos/MortimerHost` **154** green, `macos/VPIOBench` builds. G1(b)'s live-session items (V5 session, V6 audio never stops, V7a–c interruption scenarios) have been exercised repeatedly during the C6 native-audio work — full conversations with barge-in, on both transports — but were **not recorded case by case against V5/V6/V7**, so G1(b) is not claimed as formally passed. Doing so needs one session walked against that table.

**Reconciled 2026-09-22 against main `88b206f`.** The 170 / 154 counts above are stale. Current **static** counts of `func test…` declarations, not test-run results: `macos/JarvisKit/Tests` **195**, `macos/MortimerHost/Tests` **250**. No Swift toolchain was available for this reconciliation, so no pass count is claimed for `88b206f`. The latest recorded run (`docs/acceptance/command-console/receipts/full-verification-2026-09-18.md`, on a pre-merge release-review worktree) has JarvisKit 190 passed and MortimerHost 244 executed with 0 failures and 3 display-dependent skips. G1(b) remains not formally passed.

**Author / origin (Larry's words, quoted from the roadmap's origin section):**
- *"The plan is to migrate away from the web part since it is holding us back from what we want to do related to multiscreen and transparent windows."*
- *"the usefulness of the web interface has been lost since the integration of the swift wrapper — we have to rebuild the app with any changes anyway. I propose that we move away from the web portion of the interface and use swift for the UI."*
- Larry 2026-08-18, quoted in `macos/MortimerShell/Sources/MortimerShell/WindowVibrancy.swift:2-3`: *"the display window/panel is not like liquid glass, I would like it see through like liquid glass."*

**Roadmap constraints this plan is bound by:**

| C | How this plan honours it |
|---|---|
| **C1** — backend contract does not change | Not one file under `jarvis/`, `mcp_servers/`, or `config/` is created, modified, or deleted by this plan (see §4: the manifest contains no Python file). Barge-in parity is achieved by the client obeying the *existing* server semantics (§3 N9, §5 step 9), not by adding a signal. The one place where C1 bites (no RTVI transcription messages exist) is stated as a gap in §1, not worked around. |
| **C2** — localhost is the trust boundary until G2 | `JarvisConfig` defaults are `http://127.0.0.1:7860` and `http://127.0.0.1:7861`; nothing in this plan opens a port or contacts a non-loopback host by default. `JarvisConfig.validate()` (§5 step 3) **refuses** a non-loopback `botURL`/`adminURL` when `token == nil` — thrown from `JarvisClient.connect()` before the transport is built (`JarvisError.insecureHost`), tested by `testNonLoopbackWithoutTokenRefuses`. This is a client-side belt-and-braces; the *server-side* fail-closed bind is K1/T2's (`JARVIS_AUTH_ENABLED`), which no route exposes today, so the client cannot key off it — the refusal keys off `token == nil` instead. |
| **C3** — sensitive tier waits for G3 | This plan stores exactly one secret (the K1 bearer token) and stores it in the macOS/iOS Keychain. No financial data, no `facts`, no second store. |
| **C4** — every mutation stays draft → confirm | `AdminAPI` (§3 N14) exposes the sidecar's draft routes and their confirm routes as *separate* methods with distinct types; there is no combined "commit and push" convenience method. |
| **C5** — Supervisor owns interface chrome | `JarvisClient` publishes `ui` app-messages to subscribers; JarvisKit itself applies **only** the three commands it owns state for (`mic_mute`, `wake_on`, `wake_off` — §3 N10). Everything else is forwarded to the host app unchanged. JarvisKit never originates a `ui` message. |
| **C6** — untrusted content never shares an agent with an outbound channel | No agent, no MCP server, no `config/agents.yaml` change in this plan. |
| **C7** — routing eval ≥ 90 % | No Supervisor model, prompt, or agent change. G1(d) still requires one live run; §8 item V9 records it. |
| **C8** — self-edit allow/deny changes are human commits | `macos/**` is on the deny list (`config/self_edit_allowlist.json`, roadmap §1). This plan does **not** change it — every file here is written by the implementing model in a normal working tree and committed by Larry (§5 step 0). |
| **C9** — secrets in the vault | The client's bearer token is a *client-side* secret; it lives in the macOS/iOS Keychain (`KeychainStore`, §5 step 3), never in `.env`, never in `config/`, never in a plist, never in `UserDefaults`. The server-side half is the vault's business and belongs to `MORTIMER_REMOTE_ACCESS_PLAN.md`. |
| **C10** — degradation-proof | Every open question in this plan is a decision tree with a mechanical check (§3 N3/N4, §5 step 2, §5 step 10). The two places the roadmap said "investigate" — the Swift RTVI SDK and the wake word — are decided by a probe whose command line is written out, with both branches implemented in full. |

**Contracts this plan INTRODUCES (consumed by later plans):**
- **K8 — JarvisKit public surface.** Specified member-by-member in §3 N5–N8 and N12–N14, with the literal Swift declarations in §5. Consumed by the T1.3 macOS-app plan, the T1.5 iOS-app plan, and `MORTIMER_LOCAL_VOICE_AND_MINI_PLAN.md` (which changes what the bot *speaks*, not what it *sends*).

**Contracts this plan CONSUMES (by doc + section):**
- **K1 — client bearer tokens.** See `MORTIMER_REMOTE_ACCESS_PLAN.md` (T2). This plan uses only: the header form `Authorization: Bearer <token>`, the fact that it applies to *both* the sidecar `/api/*` routes and the bot's signalling routes, and the kill switch `JARVIS_AUTH_ENABLED`. Not restated here.
  - **Keychain convention (reconciled per `CROSS_PLAN_RESOLUTION.md` §C F15).** The K1 bearer token is stored under **one** convention shared with REMOTE's `ShellAuth`: service `"com.mortimer.jarviskit"`, account `"<scheme>://<host>:<port>"` derived from the **bot** URL. `KeychainStore` (§3 N12) already uses exactly this; REMOTE's `ShellAuth` and its §8 V6 command change to match. **A token-mint step must run before §8 V5** (added there) — without a stored token against a T2 bot, `connect()` correctly ends in `state = .failed("Token required")`, which is correct behaviour, not a defect.
  - **`JARVIS_CLIENT_AUTH_ENABLED` is a declared K1 extension (review F19), not a second contract.** K1 defines one server switch (`JARVIS_AUTH_ENABLED`, fail-closed). This plan adds a *client-side* debug lever under the same convention (§3 N16): when `false` it suppresses the `Authorization` header **and** (fail-closed, matching K1's discipline) refuses any non-loopback `botURL`/`adminURL`. Listed here so the "one narrowing" claim in §11/§12 stays true.
- **K5 — host/URL configuration.** See `MORTIMER_REMOTE_ACCESS_PLAN.md` (T2). This plan uses only: one base URL per service, `JARVIS_ADMIN_URL` and `JARVIS_BOT_URL`, and that no code names a host. Not restated here.

**Ordering note.** `MORTIMER_REMOTE_ACCESS_PLAN.md` is being written in parallel and lands in the same wave (roadmap §5, W1). This plan is written so that it is correct *before and after* T2: `JarvisConfig.token` is `String?`, and every request attaches the header only when the token is non-nil (§5 step 3). A JarvisKit built today talks to today's unauthenticated bot; the same binary talks to a T2 bot once a token is stored. There is no flag day.

---

## Revision table — review findings closed (2026-08-27)

Maps each closed finding to the section changed. BLOCKER/MAJOR from the plan's own review, plus the cross-plan edits `CROSS_PLAN_RESOLUTION.md` §C assigns to NATIVE (prefixed `XP-`).

| Finding | Sev | Section(s) | What changed |
|---|---|---|---|
| F1 | BLOCKER | correction 2, §8 V7, §10 R-N6 | G1(b) redefined as **client-observable** barge-in (bot stops speaking on interrupt; follow-up-turn proxy) instead of reading a `bot.log` notice line that is never written; server-side notice's un-observability carried to R-N6 |
| F2 | BLOCKER | §3 N10, §5 step 10, §8 V8, §11 | wake-word probe rewritten with `--max-time 3` + `echo`, so it terminates and yields `WAKE_PROBE=<code>`; both W1/W2 Swift paths written regardless of probe |
| F3 | BLOCKER | §5 step 5, step 7, §7.5 | explicit per-session object lifetime added; `pc`/data-channel/mic/ICE/`storedPCID` created in `connect()`, released in `disconnect()`; step 14 clears `storedPCID`; `testReconnectAfterDisconnectBuildsNewPeerConnection` added |
| F4 | BLOCKER | §1.1, §3 N9.5, §5 step 5.11, §6, §10 R-N5, §7.5 | consequence corrected (a stalled ping silences the **bot's audio**, not just app messages); client keep-alive **watchdog** with `keepAliveStallSeconds` + state transition + `DispatchSourceTimer`; ping sent unconditionally; `testKeepAliveStallFailsTheSession` added |
| F5 | BLOCKER | §5 step 1, step 5, step 7 | dropped `.swiftLanguageMode(.v6)`; package builds in Swift 5 language mode (implementer cannot compile); `JarvisSubscription`, transports, and protocols restated accordingly |
| F6 | BLOCKER | header C2 row, §5 step 3, §7.4 | C2 row rewritten to the honest minimum **and** a `JarvisConfig.validate()` non-loopback-without-token refusal added with tests, so the row matches the code |
| F7 | MAJOR | §5 step 5.12, §7.1, §7.5 | signalling `peerLeft` intercepted before `AppMessage.decode` → graceful disconnect; `renegotiate` logged-and-ignored (unreachable, audio-only); `testPeerLeftDisconnects` added |
| F8 | MAJOR | §5 step 4, §7.1 | stated `decodeIfPresent`+default rule for every non-optional scalar; `AgentDone.init(from:)` given verbatim (`ok`→`true`) |
| F9 | MAJOR | §3 N6, §5 step 7, §6, §7.5 | `messages` replaced by `messageStream()` func with fan-out registry + `.bufferingNewest(messageStreamBuffer)`; two-stream and drop-oldest tests added |
| F10 | MAJOR | §3 N14, §5 step 4, §7.7, §12 | two request bodies typed from `GoalIn`/`MemoryReviewResolveIn`; `resolveReview(id: Int…)`; "fourteen tab groupings, seventeen routes" reconciled; per-tab **response** structs cited to `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` |
| F11 | MAJOR | §8 preconditions, V5, V7 | precondition changed to `./scripts/mortimer.sh start` (which creates `logs/bot.log`); `run_bot.sh` alone writes only stdout |
| F12 | MAJOR | §5 step 8, §6, §5 step 7 | deleted iOS-only `RTCAudioSession` clause; `botIsSpeaking` now derived by one cross-platform `RTCAudioRenderer` RMS mechanism; three magic constants kept with a §7 hold-off test |
| F13 | MAJOR | §3 N10, §5 step 8, step 10 | mic-contention rule stated: wake listener runs only while `.connected && !micEnabled`; macOS coexists, **iOS wake is out of scope in T1.2** (`AVAudioSession .voiceChat`); wake tap is un-echo-cancelled and paused during `botIsSpeaking` |
| F14 | MAJOR | §6, §5 step 3, §9 | Override column deleted for the nine compile-time tuning constants; only 3 flags + 3 URLs are `UserDefaults`-overridable; `dataChannelOpenDeadline` given a real consumer (step 5.11) |
| F15 | MAJOR | §4, §7 preamble, §5 step 14, §9 | added `WakeWordFramingTests.swift` + `AdminAPITests.swift` to §4; fixtures clarified (11 happy-path files, variants inline); host **Debug menu** "Clear stored token" added |
| F16 | MINOR | correction 2, §8 V7 | "six frame scenarios" → the **five** live-reachable of eight; kill-switch/upstream-direction tests stay unit-only; duplicate V7 row 7d repurposed |
| F17 | MINOR | correction 1, §1.1–1.3, N8, N9 | stale `pipeline.py`/`ui_control.py` citations re-anchored **by quoted code text** (sibling plans edit `pipeline.py`) |
| F18 | MINOR | §5 step 8 | `googHighpassFilter` no longer claimed as web parity; described as the native-only extra |
| F19 | MINOR | header CONSUMES, §3 N16, §12 | `JARVIS_CLIENT_AUTH_ENABLED` declared as an explicit K1 extension with fail-closed shape |
| F20 | MINOR | §5 step 7, §7.4 | `connect()` re-reads the token from the Keychain, so a token minted while running attaches on next connect; `testConnectRereadsTokenFromKeychain` added |
| XP-F15 | cross | header CONSUMES, §8 (token-mint step) | Keychain convention reconciled to REMOTE's (`service com.mortimer.jarviskit`, account `<scheme>://<host>:<port>` from bot URL — already used); **token-mint step added before V5** so V5 does not fail with "Token required" |
| XP-F13 | cross | §2, §10 | note added: `KeychainStore` holds the **K1 bearer token only**; the T4b sensitive-tier key is a different item with `SecAccessControl` user-presence, introduced by the (unwritten) T4b plan |
| XP-F12 | cross | §3 N14, §10 R-N10 | per-tab `AdminAPI` response structs cited by name to `MORTIMER_NATIVE_CLIENT_APP_PLAN.md` (T1.3) |

**AppMessage completeness (independently re-verified for this revision):** `grep -rn '"type":'  jarvis/bot/*.py` for every `send_app_message` payload yields exactly eight wire types — `agent`, `agent_activity`, `agent_tool`, `display`, `speaker_gate`, `ui`, `voice/catalog`, `voice/current` (the `array`/`object`/`string`/… hits are JSON-Schema tool definitions, not pushes) — i.e. nine cases split on `agent.state`, plus `capability` (no emitter). No case is missing; the §3 N7 enumeration of ten stands.

---

## Corrections to the roadmap

1. **Roadmap §2.1 lists "barge-in signalling" as client-side work in T1.2. There is no client→server barge-in signal in this system, and adding one would violate C1.** Verified: the bot derives interruption entirely server-side from continuously-arriving inbound audio — anchor `jarvis/bot/pipeline.py` line `VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5)))` (was cited as `:653`; the actual line is 678 — a Sonnet implementer must `grep -n "VADProcessor(vad_analyzer" jarvis/bot/pipeline.py`, since sibling plans LOCAL/MAIL edit this file and shift its lines), the user aggregator's turn-start strategy (`SpeakerVerifiedMinWordsTurnStartStrategy`, anchor `jarvis/bot/speaker_gate.py` line `class SpeakerVerifiedMinWordsTurnStartStrategy`), and the `InterruptionNotifier` task observer (`jarvis/bot/interruption.py`, the `class InterruptionNotifier` observer). Nothing in `jarvis/bot/` reads an inbound app message about interruption: the only two inbound handlers registered are `handle_voice_set` and `handle_ui_noop` (anchor `jarvis/bot/pipeline.py` line `@webrtc_connection.event_handler("app-message")`, the single connection-level registration). The client's barge-in obligation is therefore **negative and behavioural** — never stop, gate, mute, or locally VAD the outbound audio track while the bot is speaking — and is specified as such in §3 N9.

2. **Roadmap §4 G1(b) says barge-in is "verified by the existing interruption test transcript replayed through the native client". There is no transcript to replay, and the interruption notice is not observable from outside the process.** Verified two facts, both load-bearing:
   - `tests/unit/test_interruption.py` constructs `InterruptionNotifier` directly and pushes synthetic Pipecat frames at it (`LLMFullResponseStartFrame`, `BotStartedSpeakingFrame`, `InterruptionFrame`, …) asserting which of `INTERRUPTION_NOTICE_MID_SPEECH` / `INTERRUPTION_NOTICE_WHILE_THINKING` was injected. It contains no audio, no transcript fixture, and no client. `grep -n "    async def test_" tests/unit/test_interruption.py` returns **eight** tests, not six.
   - **`InterruptionNotifier` emits no log output of any kind** — `grep -c "logger\|logging\|print(" jarvis/bot/interruption.py` → `0`. Its only side effect is `await self._inject(note)`, and `inject_silent` (anchor `jarvis/bot/pipeline.py` line `aggregators.user().add_messages`) only appends the notice text to the LLM context object. **There is no notice line in `logs/bot.log`, ever.** An earlier draft's "confirm from `bot.log`" gate was therefore vacuous — it could not fail when barge-in was broken (review F1). It is replaced.

   **G1(b) is redefined as a client-observable proposition** (§8 V6–V7): barge-in works iff, when the user speaks while the bot is talking, the bot **stops speaking promptly** (`botIsSpeaking` transitions `true → false` within ≈`stop_secs` of the user's onset) *while the client is still sending audio* (`debugAudioStats.sentPacketsLastSecond > 0` throughout), and the bot then responds to the new utterance. This CAN fail — a client that withholds audio during bot speech (the R-N4/N9 regression) leaves the bot talking to completion, an observable, decidable FAIL. Of `test_interruption.py`'s eight scenarios, **five are reachable through a live client**; the kill-switch test (`test_disabled_flag_suppresses_injection`) and the frame-direction test (`test_upstream_direction_ignored`) are process-internal and stay unit-only. The server-side *notice text* itself (mid-speech vs while-thinking) is not observable without a backend change (C1); its closest live proxy is the follow-up-turn check in V7 row 7b, and its full observability is carried to R-N6 alongside `RTVIObserver`.

3. **Roadmap §1 says the Mac shell has "11 Swift files". It has 10.** `ls macos/MortimerShell/Sources/MortimerShell | wc -l` → 10 (`MortimerShellApp`, `RetryView`, `ScreenPlacement`, `ShellBridge`, `ShellController`, `ShellLocation`, `ShellRootView`, `ShellWebView`, `WindowLookup`, `WindowVibrancy`). Cosmetic, but the file list matters because §4 names which two are ported.

4. **Brief/roadmap both point at `web/src/components/AgentStatusPanel.tsx` as the RTVI listener. That file is an empty stub.** `web/src/components/AgentStatusPanel.tsx:1-8` reads `// DELETED — pending git rm …` and ends `export {};`. The single RTVI `ServerMessage` registrant that feeds `agentRuns.ts` is `web/src/components/AgentRunFeeder.tsx:23`. The app-message enumeration in §3 N7 is taken from `AgentRunFeeder`, `App.tsx:217`, `VoicePicker.tsx:18`, `CapabilityChip.tsx:24`, `OrbField.tsx:118` and the emitting Python, not from the stub.

5. **K5 says `JARVIS_ADMIN_URL` "exists today". It exists as an env var read in exactly one place, and the web console does not use it.** Verified: `mcp_servers/mcp_selfedit/logic.py:20` (`ADMIN_URL_ENV = "JARVIS_ADMIN_URL"`) is the only reader; documented at `README.md:379`. The web console hardcodes `const API = "http://localhost:7861"` separately in each panel — `web/src/components/RunsPanel.tsx:9`, `EditModePanel.tsx:3`, `SystemVitals.tsx:3`, `GitPanel.tsx:3`, `MemoryPanel.tsx:3` — and `web/vite.config.ts` defines no proxy. JarvisKit therefore introduces the *first* client-side single-source-of-truth for that URL (`JarvisConfig.adminURL`), which is exactly what K5 asks for. No correction to K5 is needed; the roadmap's implication that clients already read it is what is wrong.

6. **No RTVI transcription messages are emitted by this bot, so a native Log tab cannot be fed over the data channel without a backend change.** Verified: `grep -n "RTVI" jarvis/bot/pipeline.py` matches only the `_wrap_rtvi` envelope helper (line 700) and comments; no `RTVIProcessor` and no `RTVIObserver` is constructed anywhere under `jarvis/`, the observers list is `[TranscriptObserver(...)]` plus an optional debug probe (`jarvis/bot/pipeline.py:852-886`), and neither `pipecat/runner/run.py` nor `pipecat/transports/smallwebrtc/transport.py` adds one. The web Log tab is fed by `usePipecatConversation()` (`web/src/App.tsx:95`) — client-js **session** state built from `user-transcription`/`bot-transcription` RTVI messages (`pipecat/processors/frameworks/rtvi/models.py:444,511`) that this pipeline never sends. Consequence, recorded here rather than hidden: `ConversationEntry` is in K8's surface and its decoder is unit-tested, but against today's bot the stream is silent. Adding `RTVIObserver` is a backend change and is therefore **forbidden to this plan by C1**; it is written up as risk R-N6 (§10) for the T1.3 plan to schedule.

---

## §0 Binding constraints for the implementing model

0.1 **You may not edit anything outside `macos/`.** The complete allowed write set is in §4. If a step seems to require a change under `jarvis/`, `mcp_servers/`, `config/`, or `web/`, **stop and report** — that is C1 being violated, and the plan is wrong, not the code.

0.2 **You may not run `git`.** The sandbox leaves an `index.lock`. Larry commits. Branch name: `native-client-core`.

0.3 **You cannot build Swift in this sandbox** (no Xcode, no Swift toolchain, no Mac). Every Swift file you write is written *without compiling it*. That is expected. Therefore: (a) write nothing that depends on an API you have not seen quoted in this plan or in an existing file under `macos/`; (b) every symbol this plan names is either declared verbatim here or exists in `macos/MortimerShell/Sources/MortimerShell/`; (c) §8 is the compile gate and Larry runs it.

0.4 **Do not delete `web/` or `macos/MortimerShell/`.** Deletion is roadmap item **T1.4** and is gated on G1(e) — five daily-driver days. This plan's §4 manifest has a `delete` section and it is deliberately empty.

0.5 **Every number lives in exactly one place**, listed in §6. If you find yourself typing a literal number a second time, import the constant instead.

0.6 **Decision trees are executed, not judged.** §3 N3 and N4 and §5 step 10 each give a command to run and a branch per outcome. Run the command, take the branch. If a command's outcome matches neither branch, **report and stop**.

0.7 **When this plan gives literal code, use it verbatim.** Do not "improve" the ICE handling, the keep-alive interval, or the JSON key names. Every one of them was read out of Pipecat 1.4.0's source and is cited.

---

## §1 What exists today (verified, `path:line`) and the gap

### 1.1 The wire the web client speaks

**Transport.** `web/src/jarvisClient.ts:10-17` constructs `new PipecatClient({transport: new SmallWebRTCTransport(), enableMic: true})` and connects with `webrtcRequestParams: { endpoint: "http://localhost:7860/api/offer" }`. Deps: `@pipecat-ai/client-js ^1.13.0`, `@pipecat-ai/small-webrtc-transport ^1.10.6` (`web/package.json`).

**Signalling, server side** (Pipecat 1.4.0, installed at `/usr/local/lib/python3.11/dist-packages/pipecat`):
- `POST /api/offer` — `pipecat/runner/run.py:795-825`. Body is `SmallWebRTCRequest` (`pipecat/transports/smallwebrtc/request_handler.py:26-47`): `sdp: str`, `type: str`, `pc_id: str | None`, `restart_pc: bool | None`, `request_data: Any | None` (also accepted as `requestData`). Response is `SmallWebRTCConnection.get_answer()` (`pipecat/transports/smallwebrtc/connection.py:548-562`): `{"sdp": ..., "type": ..., "pc_id": ...}`.
- `PATCH /api/offer` — `pipecat/runner/run.py:827-832`. Body is `SmallWebRTCPatchRequest` (`request_handler.py:67-75`): `pc_id: str`, `candidates: [IceCandidate]`, where `IceCandidate` (`request_handler.py:52-63`) is `{candidate: str, sdp_mid: str, sdp_mline_index: int}`. Response `{"status": "success"}`.
- Reuse: a POST carrying a known `pc_id` renegotiates the existing connection (`request_handler.py:196-206`); a POST with no `pc_id` while a connection exists is **rejected** (`request_handler.py:147-150`).

**Data channel.** The *client* creates it; the server only listens: `@self._pc.on("datachannel")` at `connection.py:330`, with **no label check** — any label works. Two rules follow, both load-bearing:
- **Keep-alive is mandatory, and a stalled ping silences the bot's *audio*.** `connection.py:344-346`: a text frame beginning `ping` sets `_last_received_time`. `connection.py:656-672`: `is_connected()` returns `self._pc.connectionState == "connected"` *only while `_last_received_time is None`*; once the client has ever sent a ping, it returns `(time.time() - _last_received_time) < 3`. That boolean gates far more than app messages: `SmallWebRTCClient._can_send()` is `self.is_connected and not self.is_closing` (`transport.py`, anchor line `def _can_send(self)`), and it gates **`write_audio_frame`** (anchor `async def write_audio_frame`, guarded `if self._can_send() and self._audio_output_track`), `write_video_frame`, **and** `send_message`. So a client that pings once and stops does not degrade to "voice works, controls don't" — **the bot goes completely mute while the pipeline keeps running and logs nothing on either side** (the exact signature Larry would misattribute to ElevenLabs or the transport). This is why the client keep-alive is sent *unconditionally* once the channel opens and is backed by a watchdog (§5 step 5.11): a bare 1 Hz `Task.sleep` loop that app-nap suspends in a background window would produce a permanently silent, apparently-connected session with no recovery path.
- **Data-channel open deadline is 10 s** after the peer connection reaches `connected` (`connection.py:77` `DATA_CHANNEL_TIMEOUT_SECS = 10`, used at line 610); past it, queued server→client messages are discarded and future ones are dropped silently (`connection.py:745-760`).

**Server → client envelope.** `jarvis/bot/pipeline.py` (anchor `def _wrap_rtvi`, ~line 697): every payload is wrapped as `{"id": <uuid4 str>, "label": "rtvi-ai", "type": "server-message", "data": <payload>}` and sent via `OutputTransportMessageUrgentFrame` (anchor `async def send_app_message`, ~line 731). client-js unwraps `data` before handing it to `RTVIEvent.ServerMessage`, which is why every web listener switches on `msg.type` of the *inner* payload.

**Client → server.** `jarvis/bot/pipeline.py` (anchor `def _unwrap_client_message`, ~line 709) accepts **two** shapes: the client-js envelope `{"type": "client-message", "data": {"t": <type>, "d": {...}}}`, and the raw payload `{"type": "voice/set", ...}` verbatim. Only two handlers are registered, on the **connection-level** `app-message` event, not the transport-level one (anchor `@webrtc_connection.event_handler("app-message")`, ~line 1113; the transport-level handler was verified dead and removed — see the D-005/D19 comment just above it).

**Bot transport params** — `jarvis/bot/bot.py:34-40`: `SmallWebRTCTransport(params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_in_filter=<optional>))`. No `vad_analyzer`, no `allow_interruptions` (D-004 note, `bot.py:6-11`).

### 1.2 Barge-in, as it actually works

`jarvis/bot/interruption.py:49-120` is a `BaseObserver` on the `PipelineTask`. Its state machine: `LLMFullResponseStartFrame` → `active=True` (deliberately *not* `UserStoppedSpeakingFrame` — see the 2026-08-22 defect note at `interruption.py:56-64`); `LLMFullResponseEndFrame` → text done; `BotStartedSpeakingFrame` → `audio_played=True`; `BotStoppedSpeakingFrame` + text done → `active=False`; `InterruptionFrame` while `active` → inject `INTERRUPTION_NOTICE_MID_SPEECH` if audio had started, else `INTERRUPTION_NOTICE_WHILE_THINKING`.

The `InterruptionFrame` itself is broadcast by the user aggregator when its turn-start strategy fires (`interruption.py:9-14`). That strategy is `SpeakerVerifiedMinWordsTurnStartStrategy` (anchor `jarvis/bot/speaker_gate.py` line `class SpeakerVerifiedMinWordsTurnStartStrategy`). Upstream of it: `VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5)))` (anchor that literal in `jarvis/bot/pipeline.py`; 2.5 s, not the 0.2 s default — deliberate, DEVIATIONS.md D-010), then the optional `SpeakerTap` (`speaker_gate.py:173`, assumes 16 kHz int16 mono, `speaker_gate.py:189`), then STT, then the optional `TranscriptGate` (`speaker_gate.py:275`).

**Every input to that chain is the raw inbound audio track.** There is no inbound control message. This is the whole of the client's barge-in contract.

### 1.3 Wake word

`jarvis/wakeword/server.py` is a **localhost websocket server**, default port 7862 (`server.py:113`), bound to `127.0.0.1` (`server.py:120`). Protocol: the client streams **binary** 16 kHz 16-bit mono PCM; text frames are ignored (`server.py:84-85`); the server buffers to exactly 1280-sample / 2560-byte chunks (`server.py:37-38`, `86-89`), scores each with openWakeWord, and on a `WakeGate.check` pass sends **text JSON** `{"type": "wake", "model": <str>, "score": <float, 3dp>}` (`server.py:92-101`). Knobs: `JARVIS_WAKEWORD_PORT` (7862), `JARVIS_WAKEWORD_THRESHOLD` (0.5), `JARVIS_WAKEWORD_COOLDOWN` (2.0) — `server.py:113-115`. A custom `mortimer.onnx` is **required**; `JARVIS_WAKEWORD_MODEL` defaults to `models/mortimer.onnx` and the process exits with a training hint if it is missing (`server.py:40`, `63-69`).

Client side today: `web/src/wakeWord.ts` opens `ws://localhost:7862/ws` (line 14), captures at `new AudioContext({sampleRate: 16000})` (line 131), converts float32→PCM16 in an `AudioWorklet` (lines 20-36), and on `{"type":"wake"}` plays a two-tone chime (880 Hz then 1320 Hz at +0.12 s, 0.25 s exponential decay — lines 57-82) and unmutes the mic (`MicControls.tsx:77-80`).

### 1.4 The Mac shell that exists

`macos/MortimerShell/` — SPM **executable** target, `swift-tools-version: 5.9`, `platforms: [.macOS(.v14)]`, one target, no dependencies (`Package.swift:22-31`). Ten Swift files. Two matter to this plan:
- `ScreenPlacement.swift` — DP8 semantics, already native: observes `NSApplication.didChangeScreenParametersNotification` (lines 35-46); `extendedScreens()` = every `NSScreen` that is not the console's, in `NSScreen.screens` order, falling back to `dropFirst()` when the console window is unknown (lines 51-54); one auxiliary window fills `visibleFrame` (line 68); two auxiliaries on one extended screen split 60 % left / 40 % right (lines 71-76); two auxiliaries on two-or-more extended screens each fill one (lines 101-104); no extended screen → do nothing (lines 82-85).
- `WindowVibrancy.swift` — the transparent-window recipe, **explicitly marked UNVERIFIED** (line 24: *"UNVERIFIED. Written without a Mac to run it on."*). Three required steps (lines 13-22): `isOpaque = false` + `backgroundColor = .clear`; an `NSVisualEffectView` with `blendingMode = .behindWindow` and `state = .active`; and `webView.setValue(false, forKey: "drawsBackground")`. The one hard-won placement fact (lines 153-164, fixed 2026-08-21 from a Larry screenshot): the effect view must be added to `contentView.superview` (the window frame view), **not** to `contentView` — a subview always draws over its parent's own content, so the earlier placement produced a frosted pane *over* the webview that uniformly dimmed everything and made three rounds of CSS fixes invisible.

### 1.5 The sidecar

FastAPI, `uvicorn.run(app, host="127.0.0.1", port=7861)` (`jarvis/admin/server.py:1771-1779`), CORS allow-list `["http://localhost:5173", "http://127.0.0.1:5173"]` (line 109), **no authentication** (K1 fixes this in T2). 46 `/api/*` routes; the ones the drawer tabs actually call are enumerated in §3 N14.

### 1.6 The gap

| Wanted | Today | Gap this plan closes |
|---|---|---|
| Transparent windows + Liquid Glass | An UNVERIFIED `NSVisualEffectView` recipe, and no `.glassEffect()` anywhere | T1.1 spike (§5 steps 11-13) answers it with screenshots Larry signs |
| Two windows on two displays natively | `ScreenPlacement.swift` exists but only ever ran under the WKWebView shell | Ported to `MortimerHost` and exercised by the spike |
| A voice session without a browser | Only `web/` can hold one | `JarvisKit` (§5 steps 2-9) |
| One base URL per service on the client | Hardcoded five times in `web/src/components/*.tsx` | `JarvisConfig` (K5) |
| A place iOS can share | Nothing | `macos/JarvisKit`, platforms macOS 26 + iOS 26, zero AppKit/UIKit imports |

---

## §2 Non-goals

- **T1.3 — the full macOS view port is OUT OF SCOPE of this plan.** The console/display/drawer views, the seven drawer tabs, the SwiftUI chrome, the Liquid Glass treatment of real content: none of it is designed or built here. It waits on **Larry's Liquid Glass design review (roadmap R3 / T1.0)**, which has not happened; building views before that review inverts Larry's standing options-first preference and would have to be redone. What this plan ships instead is `MortimerHost` — a deliberately ugly single-window macOS app (§3 N2) whose entire job is to prove G1(b): connect, talk, be interrupted, disconnect. It has one window, no glass, no tabs, and a debug list view.
- **T1.0 design exploration** — not this plan; it is W0 work and it is Larry's to review.
- **T1.4 deletion of `web/` and `macos/MortimerShell/`** — not this plan (§0.4). Both trees survive this plan untouched. The deletion trigger is G1(e).
- **T1.5 iOS app** — not this plan. `JarvisKit` declares `iOS 26` and imports no UIKit so that T1.5 is a UI-only exercise, but no iOS target is created here.
- **T2 auth** — not this plan. K1 is consumed, not implemented: no token minting, no `jarvis/auth.py`, no DB migration.
- **The T4b sensitive-tier key** — not this plan (`CROSS_PLAN_RESOLUTION.md` §C F13). `KeychainStore` here holds **only** the K1 bearer token, stored with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` and **no** user-presence gate (a background reconnect must work without a Touch ID prompt). The T4b tier needs a *different* Keychain item, gated with `SecAccessControl` user-presence and unreadable by the bot; it is introduced by the (unwritten) T4b plan, not extended out of `KeychainStore`. See §10.
- **Local models (T3), mail/calendar (T5), Xcode rebuilds (T6)** — not this plan.
- **Any backend change**, including the one this plan would most like to make (adding `RTVIObserver` so a transcript exists). C1 forbids it; §10 R-N6 carries it forward.
- **Server-side wake word.** The wake word stays client-side (roadmap §1). §3 N10 decides *how*, without moving it.

---

## §3 Decisions

### N1 — Three deliverables, one PR, in this order: spike, package, host.
`macos/GlassSpike/` (throwaway), `macos/JarvisKit/` (the product), `macos/MortimerHost/` (the G1(b) harness). **Why:** the roadmap sequences T1.1 → T1.2 → T1.3 and R-T1 makes `JarvisKit` the go/no-go before any view work. The spike is first because its answer (does `.glassEffect()` over a transparent `NSWindow` actually read as glass, and is text on it legible over a busy desktop?) is an input to Larry's T1.0 review, and a negative answer changes the design brief before anyone draws a view.

### N2 — `MortimerHost` is a harness, not the app.
One `WindowGroup`, one `VStack`: a connect/disconnect button, a connection-state label, a mic-muted toggle, a wake-word toggle, and a scrolling `List` of every decoded `AppMessage`'s `debugDescription`. Default system materials. **Why:** G1(b) is *"`JarvisKit` holds a live voice session against the unchanged bot with barge-in working"* — a proposition about the package, and a view layer would only add ways for the test to fail for unrelated reasons. Naming it `MortimerHost` (not `Mortimer`) also keeps it from colliding with the T1.3 app, which will own the product name.

### N3 — Swift RTVI client: decided by a **compile probe**, not by judgement.

The Pipecat project publishes an iOS/macOS client SDK. Its packages are:
- `https://github.com/pipecat-ai/pipecat-client-ios` — the transport-agnostic core (`PipecatClientIOS`): client lifecycle, RTVI message envelopes, callbacks.
- `https://github.com/pipecat-ai/pipecat-client-ios-small-webrtc` — the `SmallWebRTCTransport` counterpart to the JS package this repo uses (`PipecatClientIOSSmallWebrtc`).

I could not resolve either from this sandbox (no network to GitHub). Therefore the choice is made by a probe the implementer runs on Larry's Mac, and **both outcomes are fully written out**.

**The probe** (exact commands in §5 step 2, run in a scratch directory, output captured to `macos/JarvisKit/PROBE.md`):
1. `swift package resolve` a scratch package depending on `pipecat-client-ios-small-webrtc` at `from: "0.1.0"`.
2. If resolve succeeds, `swift build` the scratch package containing the **five-line probe file given verbatim in §5 step 2**, which uses exactly the symbols Branch A's wrapper needs.

**Branch A — taken only if step 1 AND step 2 both exit 0, AND the resolved `Package.swift` declares a macOS platform of `.v26` or lower.** JarvisKit depends on `PipecatClientIOSSmallWebrtc` and `RTVITransport` (§5 step 6) is a thin adapter over it.

**Branch B — taken in every other case**, including: resolve fails, the probe does not compile, the package declares a macOS minimum above 26, or the network is unavailable. JarvisKit implements signalling and WebRTC directly over `https://github.com/stasel/WebRTC` (SPM binary distribution of Google's `WebRTC.xcframework`, product `WebRTC`). The complete implementation is §5 step 5.

**If Branch B's own dependency also fails to resolve, report and stop.** Do not vendor a framework by hand; do not fall back to `WKWebView`. (A `WKWebView`-hosted `RTCPeerConnection` was the MortimerShell architecture and is what R1 rejected.)

**Why a probe and not a preference:** the plan cannot verify a third-party package's API from this sandbox, and a wrapper written against a guessed API is worse than no wrapper. A probe that compiles is proof; anything else takes the branch this plan wrote out in full. Branch B is the *expected* branch and is specified first in §5 for that reason.

### N4 — `JarvisKit` is a library-only SPM package at `macos/JarvisKit`, platforms `.macOS(.v26)` and `.iOS(.v26)`.
Products: one library, `JarvisKit`. Targets: `JarvisKit` and `JarvisKitTests`. **Why:** K8 fixes the path and platforms. `swift-tools-version: 6.0` (not 5.9 like MortimerShell) because macOS 26 / iOS 26 platform literals and strict concurrency both require it, and because `MortimerShell`'s `5.9` is a fossil of a package that is being deleted in T1.4. Keeping the SPM-not-`.xcodeproj` decision is the roadmap's explicit "surviving piece" (§2.1).

### N5 — `JarvisClient` is a `@MainActor` `ObservableObject` with one published state enum and one message stream.
`ConnectionState` is `offline | connecting | connected | failed(String)` — deliberately **not** the web's `VoiceState` (`offline | connecting | listening | speaking`, `web/src/voiceState.ts:9`), because `listening`/`speaking` are *derived* from bot-speaking events and belong to the view layer, and merging them into one enum means a reconnect during speech has two truths. `JarvisClient` publishes `botIsSpeaking: Bool` separately. **Why (self-audit item 2 — lifecycle):** state survives a view being torn down because the client is owned by the app, not by a view; `disconnect()` sets `.offline`, clears `botIsSpeaking`, and does **not** clear `lastMessages`.

### N6 — Message delivery is a fan-out `messageStream()` **plus** a synchronous multicast subscribe that returns an unsubscribe token.
`messageStream() -> AsyncStream<AppMessage>` — **a func, not a var** (review F9), returning a *new* stream per call; every stream is registered in a fan-out table and receives **every** message (an `AsyncStream` is single-consumer, so one shared `var` would let a second `for await` steal the first's — the func + fan-out is what makes "both paths receive every message" true). Each stream is bounded `.bufferingNewest(JarvisTuning.messageStreamBuffer)` so an undrained stream drops its oldest instead of leaking, and its continuation is removed `onTermination`. Alongside it, `subscribe(_ handler: @escaping @MainActor (AppMessage) -> Void) -> JarvisSubscription`, where `JarvisSubscription` unsubscribes on `cancel()` **and** on `deinit` via the token + `@Sendable` removal-closure form (review F5 — a non-isolated `deinit` cannot call the `@MainActor` handler table directly; the closure hops to the main actor). **Why (self-audit item 1):** `agentRuns.ts:206`, `displayResults.ts:78`, `conversationFeed.ts:53`, and `uiCommands.ts:44` every one of them returns an unsubscribe function, and the T1.3 views will have exactly the same unmount-on-tab-switch problem that forced those stores to exist (`agentRuns.ts:9-11`). Both paths receive every message; neither filters.

### N7 — `AppMessage` is a `public enum` with one case per emitted payload type, plus `.unknown`.

Enumerated from the emitting Python and cross-checked against every web consumer. **Ten cases.** Field types are Swift; optionality mirrors the JSON exactly (`?` = the emitter can omit it or send `null`).

**Citation note (sibling plans LOCAL/MAIL edit `jarvis/bot/pipeline.py` in the same/earlier wave, shifting its line numbers).** The `pipeline.py:NNN` values in the "Emitted at" column were line-exact at review time but are **not** load-bearing — locate each emitter by its `"type": "<literal>"` string, not the line. The wire `type` in column 3 is the stable anchor.

| # | `case` | JSON `type` | Emitted at | Members |
|---|---|---|---|---|
| 1 | `.agentWorking(AgentWorking)` | `"agent"` + `state=="working"` | `pipeline.py:252-263` | `name: String?`, `displayName: String?` (`display_name`), `runId: String?` (`run_id`), `task: String` (server truncates to 200), `model: String?`, `modelFallback: Bool` (`model_fallback`), `modelUnusable: Bool` (`model_unusable`), `modelUnusableDetail: String` (`model_unusable_detail`, ≤200) |
| 2 | `.agentDone(AgentDone)` | `"agent"` + `state=="done"` | `pipeline.py:279-286` | `name: String?`, `displayName: String?`, `ok: Bool`, `detail: String` (≤300). **No `run_id`, no model fields** — verified absent from the done branch. |
| 3 | `.agentTool(AgentTool)` | `"agent_tool"` | `pipeline.py:288-293` | `name: String?`, `displayName: String?`, `tool: String?` |
| 4 | `.agentActivity(AgentActivity)` | `"agent_activity"` | `pipeline.py:188-212` | `name: String?`, `runId: String?`, `tool: String`, `ok: Bool`, `latencyMs: Int` (`latency_ms`), `plannerModel: String?` (`planner_model` — present **only** when `tool` is `selfedit_start` or `selfedit_status`, `pipeline.py:206-211`) |
| 5 | `.display(DisplayEnvelope)` | `"display"` | `pipeline.py:250`, `:276`, `:393`, `:1003`, `:1026`; `handoff_tools.py:158`, `:227` | `payload: DisplayPayload` (decoded from the nested `display` object; see below) |
| 6 | `.ui(UICommand)` | `"ui"` | `ui_control.py:126` | `action: String`, `tab: String?` |
| 7 | `.voiceCatalog(VoiceCatalog)` | `"voice/catalog"` | anchor `"type": "voice/catalog"` in `pipeline.py` | `voices: [Voice]`, `current: String?`. `Voice` = `id: String`, `elevenlabsVoiceID: String?` (`elevenlabs_voice_id` — present in the payload because it comes straight out of `config/voices.yaml`; the web client ignores it), `label: String` |
| 8 | `.voiceCurrent(String)` | `"voice/current"` | `pipeline.py:1070-1071` | the `voice` id |
| 9 | `.speakerGate(SpeakerGate)` | `"speaker_gate"` | `speaker_gate.py:337-340` | `verdict: String` (always `"dropped"` today), `score: Double?`, `nearThreshold: Bool` (`near_threshold`) |
| 10 | `.capability([CapabilityAgent])` | `"capability"` | **no emitter exists** — see below | `name: String`, `displayName: String`, `profile: String?`, `resolvedModel: String?` (`resolved_model`), `fallback: Bool` |
| — | `.unknown(type: String, raw: [String: JSONValue])` | anything else | — | preserves the raw object so an older client never loses a newer bot's message |

**Case 10, stated honestly.** `web/src/components/CapabilityChip.tsx:24-29` listens for `{"type":"capability", "agents":[…]}`, but `grep -rn "capability" --include=*.py .` finds **no emitter** anywhere in the repo (only unrelated uses in `jarvis/agents/base.py:516,812` and `jarvis/selfedit/service.py:77,83,348`). The case is included because the field shape is fully determined by the existing consumer and because omitting it would make a future emitter a JarvisKit change; its decode is covered by a unit test only (§7 `testDecodeCapability`), and §8 does **not** ask Larry to observe one.

**`DisplayPayload`** — every member, from `web/src/displayResults.ts:15-48` (the authoritative consumer-side shape) cross-checked against `jarvis/bot/display.py:6-13` and the two direct-tool emitters in `jarvis/bot/handoff_tools.py`:

| Swift | JSON | Type | Source |
|---|---|---|---|
| `kind` | `kind` | `String?` — `"markdown"` \| `"image"` \| `"links"` | `display.py:10` |
| `title` | `title` | `String?` | `display.py:11` |
| `body` | `body` | `String?` (markdown) | `display.py:11` |
| `images` | `images` | `[String]?` | `display.py:12` |
| `basemapImages` | `basemap_images` | `[String]?` — radar payloads only, stacked *under* `images` | `displayResults.ts:20-25` |
| `links` | `links` | `[DisplayLink]?` where `DisplayLink = (label: String?, url: String)` | `display.py:12` |
| `agent` | `agent` | `String?` | `display.py:13` |
| `ts` | `ts` | `Double?` — **epoch SECONDS**, not ms | `displayResults.ts:28` |
| `surface` | `surface` | `String?` — `"drawer"` \| `"window"`; **absent/unrecognised ⇒ `"drawer"`** | `display.py:60-92`, `App.tsx:238-240` |
| `tool` | `tool` | `String?` | `displayResults.ts:30` |
| `commands` | `commands` | `[String]?` | `handoff_tools.py:162` |
| `note` | `note` | `String?` | `handoff_tools.py:163` |
| `expectOutput` | `expect_output` | `Bool?` | `handoff_tools.py:168` |
| `content` | `content` | `String?` — clipboard text, **must never be persisted** (`displayResults.ts:42-45`) | `handoff_tools.py:233` |
| `chars` | `chars` | `Int?` | `handoff_tools.py:234` |
| `truncated` | `truncated` | `Bool?` | `handoff_tools.py:235` |

Two decoder rules, both from verified emitter behaviour:
- The nested payload from `handoff_tools.py:159` and `:228` contains its **own** `"type": "display"` key inside the `display` object. The decoder ignores unrecognised keys; do not add a `type` member to `DisplayPayload`.
- `surface` defaulting happens in `DisplayPayload.surface`'s decoder, returning `.drawer` for nil or unrecognised — one place, matching `App.tsx:238-240`'s "an older bot talking to a newer console degrades to the non-intrusive outcome".

**Not an app message:** `ConversationEntry` (`conversationFeed.ts:28-33`: `id`, `role`, `createdAt`, `text`). It is client-js *session* state, and per correction 6 this bot emits nothing that feeds it. `JarvisKit` declares the type and an `RTVITranscription` decoder for `user-transcription`/`bot-transcription` (so T1.3 or a later backend plan can light it up with no JarvisKit change), and publishes `transcript: [ConversationEntry]`, bounded at `MAX_CONVERSATION_ENTRIES = 200` (`conversationFeed.ts:36`). Against today's bot the array stays empty. §7 tests the decoder; §8 does not test the stream.

### N8 — Outbound messages use the **raw** payload shape, not the client-js envelope.
`JarvisClient.send(_ msg: ClientMessage)` serialises `{"type": "voice/set", "voice": "<id>"}` and `{"type": "ui/noop", "reason": "<sentence>"}` directly. **Why:** `_unwrap_client_message` (anchor `def _unwrap_client_message` in `jarvis/bot/pipeline.py`) returns a non-`client-message` dict verbatim, and `connection.py:349` routes anything whose `type` is not `"signalling"` to the `app-message` event. The raw shape is therefore accepted and is one layer less to get wrong. `ClientMessage` is a closed enum — `.voiceSet(String)`, `.uiNoop(reason: String)` — so no caller can invent a type the bot does not handle. Server-side `ui/noop` is ignored when `reason` is empty or longer than 200 characters (anchor `if not reason or len(reason) > 200:` in `pipeline.py`); `ClientMessage.uiNoop` therefore refuses to construct outside `1...200` (`init?`).

### N9 — Barge-in parity is a set of **negative** client obligations (C1).
The client must, for the entire life of the session:
1. Send a continuous audio track from the moment the peer connection is established. Never `stop()` it, never `enabled = false` it, never replace it with silence, **including while the bot is speaking**.
   **Outbound audio format (verified against the bot's `TransportParams`, so the spike cannot hide a voice mismatch):** the client sends a *standard WebRTC* audio track — Opus, negotiated in SDP at **48 kHz**, **mono**. The client does NOT hand-set a sample rate on the RTP; libwebrtc's default audio track already produces 48 kHz Opus and the codec is negotiated in the offer/answer. Mono is what the bot expects: `bot.py`'s `TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_in_filter=…)` leaves `audio_in_channels` at its default **1** and `audio_in_sample_rate` **None** (anchor `params=TransportParams(` in `jarvis/bot/bot.py`). Server-side, pipecat resolves the input rate as `_params.audio_in_sample_rate or frame.audio_in_sample_rate` and **resamples** every inbound frame to `AudioResampler("s16", "mono", …)` before STT (anchor `self._audio_in_resampler = AudioResampler("s16", "mono"` in `pipecat/transports/smallwebrtc/transport.py`). So the only client obligation is: one mono libwebrtc audio track, added via `pc.add(track, streamIds:)`; the transport handles rate conversion. (The wake-word path is the one place the client MUST match an exact PCM format — 16 kHz int16 mono, 2560-byte frames — and that is specified in N10 and §6, not here.)
2. Never run client-side VAD, noise-gating, or push-to-talk suppression on the outbound track. Server-side `SileroVADAnalyzer` with `stop_secs=2.5` (anchor `VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=2.5))` in `pipeline.py`) is the only turn detector, and a client that withholds audio during a pause is exactly the regression R6 warns about.
3. Play the inbound track through an audio session configured with hardware echo cancellation (§5 step 8). Without it the bot's own voice re-enters the mic and interrupts the bot, continuously.
4. Implement "mute" as **`RTCAudioTrack.isEnabled = false`** — which keeps the track and the RTP stream alive with silence — and treat it as a user-facing state only. This is the same shape as `client.enableMic(false)` in `MicControls.tsx:105`.
5. Send `"ping"` over the data channel **unconditionally** every **1.0 s** (§6 `keepAliveInterval`) from the moment the channel opens until close — never gated on any client-side "is the bot idle?" heuristic. Because a stalled ping silences the bot's audio (see §1.1, F4), the send is driven by a `DispatchSourceTimer` (not a bare `Task.sleep` loop, which app-nap suspends) and is paired with a watchdog that fails the session if a send does not land inside the server's 3 s window (§5 step 5.11).

**Why:** every one of the six `test_interruption.py` scenarios is reachable *only* if inbound audio keeps arriving while `LLMFullResponseStartFrame`…`BotStoppedSpeakingFrame` is in flight. Obligation 5 is not about barge-in but is in the same list because violating it silently converts the session into one where inbound app messages queue instead of dispatching (`connection.py:353-357`, `656-672`) — `voice/set` and `ui/noop` stop working with no error anywhere.

### N10 — Wake word: **Branch W1 (stream to the existing sidecar) is the decision.** Branch W2 is specified and is taken only on a mechanical failure.

**Check (§5 step 10) — a probe that TERMINATES (review F2).** The earlier `curl` had no `--max-time`; after a `101 Switching Protocols` the socket stays open (`jarvis/wakeword/server.py`'s `async for message in ws:` parks forever), so curl never printed `%{http_code}` and the terminal hung — undecidable. Use, on Larry's Mac with `./scripts/run_wakeword.sh` running:
```bash
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 --http1.1 \
  -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  http://127.0.0.1:7862/ws 2>/dev/null); echo "WAKE_PROBE=$code"
```
`--max-time 3` bounds it; the `101` is emitted before the timeout kills the read; connection-refused yields `000`. Branch rule: **`WAKE_PROBE=101` → W1; anything else (including `000`, a 4xx, or a sidecar that exited because `models/mortimer.onnx` is missing) → W2.** This probe is a *runtime* determination recorded in `PROBE.md` and V8 — it does **not** decide which Swift file to write: the implementing model has no Mac (§0.3) and **both** W1 and W2 code paths are written unconditionally.
- **W1:** `WakeWordListener` captures mic audio, resamples to 16 kHz int16 mono, sends 2560-byte binary frames, decodes `{"type":"wake", …}` text frames. Zero server change; the sidecar's model, threshold, and cooldown stay where they are.
- **W2:** `WakeWordListener` reports `.unavailable(reason:)`, `JarvisClient.wakeWordAvailable` is `false`, and the `wake_on` command answers with the exact existing copy `"The wake word listener isn't available on this machine."` (`MicControls.tsx:111`). **W2 is a degraded state, not a reimplementation**: this plan does *not* port openWakeWord to Swift, does *not* add a CoreML model, and does *not* substitute `SFSpeechRecognizer`. Doing any of those would move a working local component for no gate reason and would be a second wake-word implementation to keep in sync.

**Mic-contention rule (review F13) — when the wake listener owns the input, and on which platform.** The WebRTC session (step 5.6) and the wake listener (step 10) are two capture graphs on one input device, so the rule is stated, not left to the implementer:
1. **The wake listener runs only while `state == .connected` AND `micEnabled == false`** — the sole state in which a wake event has an effect (its whole job, per `MicControls.tsx:77-80`, is to *unmute* a muted mic). Starting it stops nothing; stopping the session stops it.
2. **macOS: both graphs coexist** — CoreAudio permits multiple input clients, so the `AVAudioEngine` tap and libwebrtc's ADM run side by side.
3. **iOS: the wake listener is unavailable in T1.2** (`#if os(iOS)` ⇒ W2 with reason `"wake word is macOS-only in this release"`), because the `AVAudioSession` `.voiceChat` mode this plan sets (step 8) routes input through VPIO and does not permit a second `AVAudioEngine` input tap. T1.5 owns the iOS wake path.
4. **The wake tap is NOT echo-cancelled** — it reads the raw input node, not libwebrtc's processed stream (the web client got EC on the wake path only by accident, via its global `getUserMedia` wrap — `micConstraints.ts`, comment "The wrap also covers the wake-word engine's mic acquisition"; the native port loses that). So while the bot is speaking, the sidecar would otherwise score Mortimer's own TTS. Therefore **the listener is paused for the duration of `botIsSpeaking`** and resumes when the bot falls silent.

**Why W1 is the decision rather than a coin flip:** the roadmap's own constraint is "wake word stays client-side", and the sidecar *is* client-side — it runs on whatever machine the user is at, exactly as it does today; a native client streaming to `127.0.0.1:7862` is the identical topology the browser uses (`wakeWord.ts:14`). Porting openWakeWord into Swift would additionally strand the custom `mortimer.onnx` and the `python -m jarvis.wakeword.train` pipeline. After T3 relocates the *bot* to the mini, the wake sidecar stays on the client machine — it is not part of the Python stack that moves, and `JarvisConfig.wakeWordURL` (defaulting to `ws://127.0.0.1:7862/ws`) is the knob that keeps that true.

**Chime parity:** JarvisKit reproduces `wakeWord.ts:57-82` exactly — 880 Hz at t+0, 1320 Hz at t+0.12 s, each gain 0.18 decaying exponentially to 0.001 over 0.25 s, whole thing torn down at 0.8 s — synthesised with `AVAudioEngine` + two `AVAudioPlayerNode`s, no asset file. **Why exact:** it is the sound Larry already associates with "it heard me"; changing it is a design change and T1.0 owns design changes.

### N11 — JarvisKit owns exactly three `ui` actions; everything else is forwarded.
`mic_mute`, `wake_on`, `wake_off` — the three `MicControls.tsx:99-129` owns, because JarvisKit owns the mic and the wake listener. Their no-op replies use the **verbatim existing copy**:

| Action | Condition | JarvisKit does |
|---|---|---|
| `mic_mute` | already muted, or not connected | nothing, sends nothing (`MicControls.tsx:100-104` — a stale command is harmless) |
| `mic_mute` | live | `micEnabled = false` |
| `wake_on` | `wakeWordAvailable == false` | send `ui/noop` `"The wake word listener isn't available on this machine."` |
| `wake_on` | already on | send `ui/noop` `"The wake word is already on."` |
| `wake_on` | off and available | start the listener |
| `wake_off` | already off | send `ui/noop` `"The wake word is already off."` |
| `wake_off` | on | stop the listener |

There is deliberately **no `mic_unmute`** — `UI_ACTIONS` (`ui_control.py:25-31`) does not contain one, for the reason the tool description gives (`ui_control.py:75-78`: while muted the user cannot be heard, so the command could never arrive). All other actions (`drawer_*`, `transcript_*`, `display_*`, `overlay_dismiss`) are published to subscribers as `.ui(UICommand)` and are **T1.3's** to apply; their no-op copy lives in T1.3, not here (self-audit item 5: the copy JarvisKit owns is the three strings above and nothing else). Valid `tab` values, for the T1.3 plan's benefit: `repo, edit, memory, runs, agents, output, transcript` (`ui_control.py:33-35`). Aliases (`developer`/`dev`/`agent` → `agents`) are resolved **server-side before validation** (`ui_control.py:43`), so the client never sees one.

### N12 — Configuration and secrets: `JarvisConfig` + `KeychainStore` (K5, K1, C9).
```
public struct JarvisConfig: Sendable, Equatable {
    public var botURL: URL        // default http://127.0.0.1:7860   (JARVIS_BOT_URL)
    public var adminURL: URL      // default http://127.0.0.1:7861   (JARVIS_ADMIN_URL)
    public var wakeWordURL: URL   // default ws://127.0.0.1:7862/ws
    public var token: String?     // nil until T2 mints one
}
```
Resolution order for each URL, applied once at `JarvisConfig.default()`: `ProcessInfo.processInfo.environment[<VAR>]` → `UserDefaults.standard.string(forKey: <same name>)` → the compiled default. **Why that order and not the reverse:** it matches how MortimerShell already lets Larry re-try a value without a rebuild (`WindowVibrancy.swift:72-85` documents exactly that pattern with `defaults write`), and env wins so a launch script can override a stale default. No JarvisKit code contains a host name outside `JarvisConfig.default()` (roadmap §6 invariant 1).

`KeychainStore.token(for: URL) -> String?` and `KeychainStore.setToken(_ String?, for: URL)`, K8's named accessor. Service string `"com.mortimer.jarviskit"`, account string `"<scheme>://<host>:<port>"` derived from the **bot** URL, `kSecAttrAccessible = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (survives reboot for a background reconnect; never syncs to iCloud; never leaves the device). Keying on the bot URL means moving to the mini (T3) is a new keychain entry, not a silently reused one.

### N13 — Every HTTP request in JarvisKit goes through one function.
`JarvisHTTP.send(_ request: URLRequest, config: JarvisConfig) async throws -> (Data, HTTPURLResponse)` attaches `Authorization: Bearer <token>` iff `config.token != nil`, sets `Accept: application/json`, applies `timeoutIntervalForRequest = 15` (§6), and maps `401` to `JarvisError.unauthorized`, `403` to `.forbidden`, other non-2xx to `.http(status:body:)`. **Why (self-audit item 1):** K1 says the header goes on *every* sidecar `/api/*` route **and** the bot's signalling routes; two code paths for that is how one of them gets missed. Signalling (`POST`/`PATCH /api/offer`) and `AdminAPI` both call this function.

`JarvisError.unauthorized` is surfaced once and never retried — the same discipline K1 gives the web console ("a 401 anywhere shows a single toast … and does not retry"). `JarvisClient` transitions to `.failed("Token required")` and stops.

### N14 — `AdminAPI` is a typed wrapper over exactly the routes the drawer tabs call today.
Enumerated by grepping `web/src/components/*.tsx` for `${API}` paths and confirmed against `jarvis/admin/server.py`'s route decorators. **Fourteen tab groupings, seventeen routes** (review F10 — the earlier "fourteen routes" miscounted; the table has always listed seventeen), grouped by the tab that uses them:

| Tab | Method | Route | `server.py` |
|---|---|---|---|
| Repo | `GET` | `/api/git/status` | `:712` |
| Edit | `GET` | `/api/selfedit/models` | `:755` |
| Edit | `GET` | `/api/selfedit/status` | `:760` |
| Edit | `POST` | `/api/selfedit/run` | `:795` |
| Memory | `GET` | `/api/memory` | `:1214` |
| Memory | `DELETE` | `/api/memory/fact/{key}` | `:1445` |
| Memory | `GET` | `/api/memory/reviews` | `:1461` |
| Memory | `POST` | `/api/memory/reviews/{id}/resolve` | `:1473` |
| Memory | `GET` | `/api/knowledge` | `:1226` |
| Runs | `GET` | `/api/runs` | `:1501` |
| Runs | `GET` | `/api/runs/{run_id}` | `:1518` |
| (ambient) | `GET` | `/api/ambient` | `:1324` |
| (council) | `GET` | `/api/council/job`, `/api/council/rounds`, `/api/council/round/{id}` | `:1576`, `:1595`, `:1586` |
| (plan) | `GET` | `/api/plan/job` | `:1679` |
| (health) | `GET` | `/api/health` | `:707` |

**Decoding rule, chosen so this plan cannot drift from the sidecar:** `AdminAPI`'s methods return `JSONValue` for **response** bodies (a `Codable` recursive enum defined in §5 step 4) plus **one** strongly-typed response, `health() async throws -> AdminHealth`, used by the connection preflight. **Why (responses only):** the sidecar's *response* bodies are FastAPI dicts assembled inline, several of them shaped by whatever `jarvis/runlog/store.py` or `jarvis/memory.py` returns; typing all seventeen responses from a plan that cannot run them would put seventeen guesses into a contract that two later plans consume. `JSONValue` is exact, is decodable without guessing.

**Request bodies ARE typed (review F10).** The two `POST` routes with a body take Pydantic models that live in the same file this plan already read, so they are derivable and are typed here — passing `JSONValue` for them would defer no risk and *create* one (a wrong key is a silent 422, not a compile error):
- `selfeditRun(goal: String?, profile: String?, plan: String?, stagingId: String?) -> JSONValue` from `class GoalIn` (anchor `class GoalIn(BaseModel):` in `jarvis/admin/server.py`: `goal: str = ""`, `profile: str | None`, `plan: str | None`, `plan_path: str | None`, `staging_id: str | None`; the wrapper exposes the four the Edit tab sends and lets the sidecar's staging path own `plan_path`).
- `resolveReview(id: Int, action: String, rewriteContent: String?) -> JSONValue` from `class MemoryReviewResolveIn` (anchor `class MemoryReviewResolveIn(BaseModel):`: `action: str`, `rewrite_content: str | None`). **`id` is `Int`**, not `String` — the route is `@app.post("/api/memory/reviews/{review_id}/resolve")` with `review_id: int` (anchor that decorator), so a non-numeric id must fail to compile, not 422 at runtime.

Each method's URL, HTTP method, path parameters, and (for the two POSTs) request body are fully typed — that is the part that must not drift. The **response**-body `JSONValue` is a deliberate, stated narrowing of K8's *"typed wrappers"* and is the only place this plan narrows a contract; §12's checkbox scopes it to *response bodies only*.

**Per-tab response structs are owned by T1.3, not this plan.** The concrete `Codable` struct per tab (`RunsResponse`, `MemoryResponse`, …) is added *inside* `AdminAPI` at the point T1.3 renders that tab and can see the real payload. Those structs are the property of **`MORTIMER_NATIVE_CLIENT_APP_PLAN.md`** (the T1.3 plan named in `CROSS_PLAN_RESOLUTION.md` §C F12), which is `AdminAPI`'s sole per-tab-struct consumer; this plan neither defines nor guesses them.

### N15 — Ported from `MortimerShell`: `ScreenPlacement` (semantics) and the vibrancy recipe (as a fallback). Nothing is deleted.
- `ScreenPlacement.swift` → `macos/MortimerHost/Sources/MortimerHost/ScreenPlacement.swift`, DP8 semantics **unchanged** (§1.4 lists all five rules), with two mechanical edits: `ShellWindowKind` → `HostWindowKind` (`.console`, `.display`, `.drawer`) and `findShellWindow` → a local `findHostWindow` matching on `NSWindow.identifier?.rawValue`. **Why port and not rewrite:** the roadmap names it a surviving piece; the 60/40 split, the `visibleFrame` (not `frame`) choice, and the "no extended screen → do nothing" rule are each a decision someone already made and Larry already lives with.
- `WindowVibrancy.swift`'s recipe → `macos/GlassSpike` as the **fallback arm** of the spike (§5 step 12), minus step 3 (`drawsBackground`), which exists only because of WKWebView and is irrelevant to a pure SwiftUI window. The 2026-08-21 `contentView.superview` placement fix is carried over verbatim, because it is the single non-obvious fact in that file.
- **Deleted in this plan: nothing.** T1.4 owns deletion (§0.4, §4).

### N16 — Kill switches are `UserDefaults` booleans read in one place each, named to match the repo's `JARVIS_<FEATURE>_ENABLED` convention.
There is no `.env` on a Mac app bundle, so the client analogue of an env kill switch is `UserDefaults` (`defaults write <bundle-id> JARVIS_WAKEWORD_ENABLED -bool false`), read through one accessor, `JarvisFlags` (§6). Three flags, all defaulting to enabled: `JARVIS_WAKEWORD_ENABLED`, `JARVIS_CLIENT_AUTH_ENABLED`, `JARVIS_GLASS_ENABLED` (spike/host: false ⇒ opaque windows, the rollback in §9).

`JARVIS_CLIENT_AUTH_ENABLED` is a declared **K1 extension** (review F19), not a silent second contract — it is listed in the header's "Contracts this plan CONSUMES" and in §12. To keep K1's fail-closed discipline rather than invert it, `false` does two things, not one: (a) no `Authorization` header is attached, and (b) `JarvisConfig.validate()` **additionally refuses any non-loopback `botURL`/`adminURL`** (a client with auth deliberately off must not then reach a remote host in the clear). So the switch is the client-side counterpart of `JARVIS_AUTH_ENABLED`, mismatched pairs are debuggable from either end, and turning client auth off never fails *open*.

---

## §4 Files — complete manifest

Every file touched in §5 appears here; nothing here is absent from §5.

### Create — `macos/JarvisKit/` (T1.2, the product)

| Path | Purpose | Step |
|---|---|---|
| `macos/JarvisKit/Package.swift` | SPM manifest, tools 6.0, macOS 26 / iOS 26, library `JarvisKit` | 1 |
| `macos/JarvisKit/README.md` | what the package is, the two branch outcomes, how to run its tests | 1 |
| `macos/JarvisKit/PROBE.md` | **written by the implementer** with the verbatim output of §5 step 2 and the branch taken | 2 |
| `macos/JarvisKit/Sources/JarvisKit/JarvisConfig.swift` | `JarvisConfig`, `JarvisFlags`, env/`UserDefaults`/default resolution | 3 |
| `macos/JarvisKit/Sources/JarvisKit/KeychainStore.swift` | `KeychainStore.token(for:)` / `setToken(_:for:)` | 3 |
| `macos/JarvisKit/Sources/JarvisKit/JarvisHTTP.swift` | the single request function, bearer attach, error mapping | 3 |
| `macos/JarvisKit/Sources/JarvisKit/JSONValue.swift` | recursive `Codable` JSON value | 4 |
| `macos/JarvisKit/Sources/JarvisKit/AppMessage.swift` | the ten cases, `DisplayPayload`, `ConversationEntry`, decoders | 4 |
| `macos/JarvisKit/Sources/JarvisKit/ClientMessage.swift` | `.voiceSet`, `.uiNoop`, encoders | 4 |
| `macos/JarvisKit/Sources/JarvisKit/Signalling.swift` | `OfferRequest`/`OfferAnswer`/`PatchRequest`, `postOffer`, `patchCandidates` | 5 |
| `macos/JarvisKit/Sources/JarvisKit/RTVITransport.swift` | `RTVITransport` protocol + `RTVITransportDelegate` | 5 |
| `macos/JarvisKit/Sources/JarvisKit/DirectWebRTCTransport.swift` | **Branch B** implementation (`WebRTC` xcframework) | 5 |
| `macos/JarvisKit/Sources/JarvisKit/PipecatSDKTransport.swift` | **Branch A** implementation; created only on Branch A | 6 |
| `macos/JarvisKit/Sources/JarvisKit/JarvisClient.swift` | `ConnectionState`, publishes, `connect`/`disconnect`/`send`/`subscribe` | 7 |
| `macos/JarvisKit/Sources/JarvisKit/AudioSession.swift` | echo cancellation, capture format, mute-as-`isEnabled` | 8 |
| `macos/JarvisKit/Sources/JarvisKit/WakeWordListener.swift` | Branch W1 stream + W2 unavailable state + the chime | 10 |
| `macos/JarvisKit/Sources/JarvisKit/AdminAPI.swift` | the seventeen typed route wrappers (fourteen tab groupings) + typed request bodies + `AdminHealth` | 4 |
| `macos/JarvisKit/Tests/JarvisKitTests/AppMessageTests.swift` | §7.1 | 4 |
| `macos/JarvisKit/Tests/JarvisKitTests/ClientMessageTests.swift` | §7.2 | 4 |
| `macos/JarvisKit/Tests/JarvisKitTests/SignallingTests.swift` | §7.3 | 5 |
| `macos/JarvisKit/Tests/JarvisKitTests/ConfigAndAuthTests.swift` | §7.4 | 3 |
| `macos/JarvisKit/Tests/JarvisKitTests/UICommandOwnershipTests.swift` | §7.5 | 7 |
| `macos/JarvisKit/Tests/JarvisKitTests/WakeWordFramingTests.swift` | §7.6 — PCM framing arithmetic + wake decode | 10 |
| `macos/JarvisKit/Tests/JarvisKitTests/AdminAPITests.swift` | §7.7 — `testAdminRoutesBuildExpectedURLs` over all seventeen routes | 4 |
| `macos/JarvisKit/Tests/JarvisKitTests/Fixtures/` (11 `.json` files) | one per `AppMessage` case (+ one unknown) for the eleven happy-path decode tests; variant tests build JSON inline (§7 preamble) | 4 |

### Create — `macos/GlassSpike/` (T1.1, throwaway)

| Path | Purpose | Step |
|---|---|---|
| `macos/GlassSpike/Package.swift` | executable `GlassSpike`, macOS 26 | 11 |
| `macos/GlassSpike/README.md` | the screenshot checklist Larry signs (§8 S1–S6) | 13 |
| `macos/GlassSpike/Sources/GlassSpike/GlassSpikeApp.swift` | `@main`, two `WindowGroup`s + `openWindow` | 11 |
| `macos/GlassSpike/Sources/GlassSpike/GlassPanelView.swift` | `.glassEffect()` panel, legibility text block, contrast slider | 12 |
| `macos/GlassSpike/Sources/GlassSpike/TransparentWindow.swift` | `isOpaque=false` / `.clear` accessor + the `NSVisualEffectView` fallback arm | 12 |
| `macos/GlassSpike/Sources/GlassSpike/SpikeScreenPlacement.swift` | the two-display placement the spike exercises | 11 |

### Create — `macos/MortimerHost/` (G1(b) harness)

| Path | Purpose | Step |
|---|---|---|
| `macos/MortimerHost/Package.swift` | executable `MortimerHost`, macOS 26, depends on `../JarvisKit` | 14 |
| `macos/MortimerHost/README.md` | the two Xcode settings, and the G1(b) run procedure | 14 |
| `macos/MortimerHost/Sources/MortimerHost/MortimerHostApp.swift` | `@main`, one window, owns the `JarvisClient` | 14 |
| `macos/MortimerHost/Sources/MortimerHost/HostView.swift` | connect button, state label, mute/wake toggles, message list | 14 |
| `macos/MortimerHost/Sources/MortimerHost/ScreenPlacement.swift` | **ported** from `MortimerShell` (N15) | 14 |
| `macos/MortimerHost/Sources/MortimerHost/WindowLookup.swift` | **ported** identifier-based window lookup | 14 |
| `macos/MortimerHost/templates/Info.plist.template` | `NSMicrophoneUsageDescription` | 14 |
| `macos/MortimerHost/templates/MortimerHost.entitlements.template` | `com.apple.security.device.audio-input`, `…network.client` | 14 |

### Modify

| Path | Change | Step |
|---|---|---|
| `macos/README.md` | if absent, create; add a three-line index of the four packages now under `macos/` and which is which | 15 |

### Delete

**Nothing.** `web/` and `macos/MortimerShell/` are untouched by this plan; their removal is roadmap **T1.4**, gated on **G1(e)** (five consecutive daily-driver days). See §0.4.

---

## §5 Implementation steps, in order

Each step: files, exact change, and the test that proves it.

### Step 0 — Working tree and branch
No `git` commands (§0.2). Create every file in the working tree. Larry commits on branch `native-client-core`. `macos/**` is on the self-edit deny list (`config/self_edit_allowlist.json`), so this work is **never** eligible for the self-edit path — it is a human PR. Do not propose changing that list (C8).

### Step 1 — `macos/JarvisKit/Package.swift`

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JarvisKit",
    platforms: [.macOS(.v26), .iOS(.v26)],
    products: [
        .library(name: "JarvisKit", targets: ["JarvisKit"]),
    ],
    dependencies: [
        // BRANCH B (default). Replace this block per §5 step 6 only if the
        // probe in step 2 passed. Do not have both.
        .package(url: "https://github.com/stasel/WebRTC.git", from: "120.0.0"),
    ],
    targets: [
        .target(
            name: "JarvisKit",
            dependencies: [.product(name: "WebRTC", package: "WebRTC")]
            // Swift 5 language mode (tools 6.0 default). NOT .swiftLanguageMode(.v6):
            // review F5 — the implementer cannot compile here (§0.3), and strict
            // concurrency under .v6 would force design decisions this plan does not
            // contain (a non-isolated deinit calling a @MainActor method; Sendable
            // on protocols whose conformers hold RTCPeerConnection). The package
            // builds with concurrency *warnings*, not errors. A later plan that can
            // compile may adopt .v6 and resolve them; that is not this plan's risk.
        ),
        .testTarget(
            name: "JarvisKitTests",
            dependencies: ["JarvisKit"],
            resources: [.copy("Fixtures")]
        ),
    ]
)
```
**Test:** none yet (no toolchain here). §8 V1 is the gate.

**Why Swift 5 language mode and not `.v6` (review F5):** three strict-concurrency violations would otherwise be errors the implementer must design around blind — `JarvisSubscription.deinit` mutating a `@MainActor` handler table; `RTVITransport: Sendable` with a mutable `var delegate` requirement while `DirectWebRTCTransport` holds non-`Sendable` `RTCPeerConnection`/`RTCDataChannel`; and unstated actor isolation on `AdminAPI`/the transports. Swift 5 mode reduces all three to warnings, so the quoted declarations in steps 5 and 7 compile as written. The declarations are still written defensively (transports are reference types with a stated internal serial queue; `JarvisSubscription` uses the token+closure form, step 7) so that a future `.v6` adoption is mechanical, not a redesign.

### Step 2 — The probe that picks the transport branch (N3)

Run on Larry's Mac, capture **all** output verbatim into `macos/JarvisKit/PROBE.md`:

```bash
set -x
mkdir -p /tmp/pcprobe && cd /tmp/pcprobe
cat > Package.swift <<'EOF'
// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "pcprobe",
    platforms: [.macOS(.v26)],
    dependencies: [
        .package(url: "https://github.com/pipecat-ai/pipecat-client-ios-small-webrtc.git", from: "0.1.0"),
    ],
    targets: [.target(name: "pcprobe", dependencies: [
        .product(name: "PipecatClientIOSSmallWebrtc", package: "pipecat-client-ios-small-webrtc"),
    ])]
)
EOF
mkdir -p Sources/pcprobe
cat > Sources/pcprobe/Probe.swift <<'EOF'
import PipecatClientIOS
import PipecatClientIOSSmallWebrtc
@MainActor func probe(url: String) throws {
    let transport = SmallWebRTCTransport(options: RTVIClientOptions(params: RTVIClientParams(baseUrl: url)))
    _ = transport
}
EOF
swift package resolve ; echo "RESOLVE_EXIT=$?"
swift build            ; echo "BUILD_EXIT=$?"
grep -n "platforms" .build/checkouts/pipecat-client-ios-small-webrtc/Package.swift
```

**Branch selection — apply mechanically:**
- `RESOLVE_EXIT=0` **and** `BUILD_EXIT=0` **and** the grepped `platforms:` line names `.macOS(` with a version **≤ 26** → **Branch A**. Go to step 6 (and delete `DirectWebRTCTransport.swift` before writing anything else, so only one transport exists).
- Any other combination, including no network → **Branch B**. Continue to step 5. Do not retry, do not adjust the probe, do not substitute a different version requirement.
- If Branch B is selected and `swift package resolve` of `https://github.com/stasel/WebRTC.git` **also** fails: **report and stop** (§0.6).

**Test:** `macos/JarvisKit/PROBE.md` exists, contains both exit codes, and names the branch in its first line.

### Step 3 — Config, Keychain, HTTP (N12, N13)

`JarvisConfig.swift`:
```swift
import Foundation

public struct JarvisConfig: Sendable, Equatable {
    public var botURL: URL
    public var adminURL: URL
    public var wakeWordURL: URL
    public var token: String?

    public init(botURL: URL, adminURL: URL, wakeWordURL: URL, token: String?) { … }

    /// K5: one base URL per service, resolved in ONE place.
    /// Order: process environment -> UserDefaults -> compiled default.
    public static func `default`() -> JarvisConfig {
        func url(_ name: String, _ fallback: String) -> URL {
            if let s = ProcessInfo.processInfo.environment[name], let u = URL(string: s) { return u }
            if let s = UserDefaults.standard.string(forKey: name), let u = URL(string: s) { return u }
            return URL(string: fallback)!
        }
        let bot = url("JARVIS_BOT_URL", "http://127.0.0.1:7860")
        return JarvisConfig(
            botURL: bot,
            adminURL: url("JARVIS_ADMIN_URL", "http://127.0.0.1:7861"),
            wakeWordURL: url("JARVIS_WAKEWORD_URL", "ws://127.0.0.1:7862/ws"),
            token: JarvisFlags.authEnabled ? KeychainStore.token(for: bot) : nil
        )
    }

    /// C2 / review F6 / F19. Called by JarvisClient.connect() BEFORE the
    /// transport is built. Refuses a non-loopback host reached without a
    /// bearer token — the client-side belt to K1's server-side braces.
    /// Also refuses non-loopback when client auth is deliberately off (F19,
    /// fail-closed). The server-side JARVIS_AUTH_ENABLED signal is exposed by
    /// no route today, so the refusal keys off token/flag state, not a probe.
    static let loopbackHosts: Set<String> = ["127.0.0.1", "::1", "localhost"]
    public func validate() throws {
        func loopback(_ u: URL) -> Bool { (u.host).map(JarvisConfig.loopbackHosts.contains) ?? false }
        for u in [botURL, adminURL] where !loopback(u) {
            if token == nil { throw JarvisError.insecureHost(u.absoluteString) }
            if !JarvisFlags.authEnabled { throw JarvisError.insecureHost(u.absoluteString) }
        }
    }
}

public enum JarvisFlags {
    /// Client-side counterparts of the repo's JARVIS_<FEATURE>_ENABLED
    /// convention. `defaults write <bundle-id> <NAME> -bool false`.
    /// Absent key == enabled (matches the repo's "unset means on" rule).
    static func on(_ key: String) -> Bool {
        UserDefaults.standard.object(forKey: key) == nil
            ? true : UserDefaults.standard.bool(forKey: key)
    }
    public static var wakeWordEnabled: Bool { on("JARVIS_WAKEWORD_ENABLED") }
    public static var authEnabled: Bool     { on("JARVIS_CLIENT_AUTH_ENABLED") }
    public static var glassEnabled: Bool    { on("JARVIS_GLASS_ENABLED") }
}
```

`KeychainStore.swift` — `SecItemCopyMatching` / `SecItemAdd` / `SecItemUpdate` / `SecItemDelete` against `kSecClassGenericPassword`, `kSecAttrService = "com.mortimer.jarviskit"`, `kSecAttrAccount = account(for:)` where `account(for: URL) -> String` is `"\(scheme)://\(host):\(port)"` with port defaulting to 7860 when absent, and `kSecAttrAccessible = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`. `setToken(nil, for:)` deletes. Never logs the value; the only log line is `keychain_token_present=<Bool>`.

`JarvisHTTP.swift`:
```swift
public enum JarvisError: Error, Equatable {
    case unauthorized, forbidden
    case http(status: Int, body: String)
    case transport(String)
    case decoding(String)
    case insecureHost(String)   // C2/F6: non-loopback reached without a token
}

public enum JarvisHTTP {
    public static let timeoutSeconds: TimeInterval = 15   // §6

    public static func send(_ req: URLRequest, config: JarvisConfig)
        async throws -> (Data, HTTPURLResponse)
    {
        var r = req
        r.timeoutInterval = timeoutSeconds
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        // K1 — Authorization on EVERY sidecar /api/* route AND on the bot's
        // signalling routes. One attach point; there is no other sender.
        if let t = config.token { r.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
        let (data, resp) = try await URLSession.shared.data(for: r)
        guard let http = resp as? HTTPURLResponse else { throw JarvisError.transport("non-HTTP response") }
        switch http.statusCode {
        case 200...299: return (data, http)
        case 401:       throw JarvisError.unauthorized
        case 403:       throw JarvisError.forbidden
        default:        throw JarvisError.http(status: http.statusCode,
                                               body: String(data: data, encoding: .utf8) ?? "")
        }
    }
}
```

**Test:** `ConfigAndAuthTests.swift` — §7.4.

### Step 4 — `JSONValue`, `AppMessage`, `ClientMessage`, `AdminAPI` (N7, N8, N14)

`JSONValue.swift`: `public enum JSONValue: Codable, Sendable, Equatable { case null, bool(Bool), number(Double), string(String), array([JSONValue]), object([String: JSONValue]) }` with `init(from:)` trying each in that order and `encode(to:)` the inverse. Subscript helpers `subscript(_ key: String) -> JSONValue?` and `var stringValue/doubleValue/intValue/boolValue`.

`AppMessage.swift` — the shape (members exactly as §3 N7's tables; `CodingKeys` map every snake_case name):

```swift
public enum AppMessage: Sendable, Equatable {
    case agentWorking(AgentWorking)
    case agentDone(AgentDone)
    case agentTool(AgentTool)
    case agentActivity(AgentActivity)
    case display(DisplayPayload)
    case ui(UICommand)
    case voiceCatalog(VoiceCatalog)
    case voiceCurrent(String)
    case speakerGate(SpeakerGate)
    case capability([CapabilityAgent])
    case unknown(type: String, raw: [String: JSONValue])
}
```

Decoding entry point — this is the only place the envelope is understood:

```swift
public extension AppMessage {
    /// Decode ONE data-channel text frame.
    /// Accepts the server envelope written by _wrap_rtvi (jarvis/bot/pipeline.py)
    ///   {"id":…, "label":"rtvi-ai", "type":"server-message", "data": <payload>}
    /// and, defensively, a bare payload (the envelope is a client-js
    /// workaround, D-005 — a future bot may drop it).
    /// Returns nil for a signalling frame or a frame with no "type".
    static func decode(frame data: Data) throws -> AppMessage? {
        let root = try JSONDecoder().decode(JSONValue.self, from: data)
        guard case .object(let obj) = root, let t = obj["type"]?.stringValue else { return nil }
        if t == "signalling" { return nil }                 // connection.py:349
        let payloadValue: JSONValue
        if t == "server-message", let d = obj["data"] { payloadValue = d } else { payloadValue = root }
        guard case .object(let p) = payloadValue, let kind = p["type"]?.stringValue else { return nil }
        let payload = try JSONEncoder().encode(payloadValue)
        let dec = JSONDecoder()
        switch kind {
        case "agent":
            switch p["state"]?.stringValue {
            case "working": return .agentWorking(try dec.decode(AgentWorking.self, from: payload))
            case "done":    return .agentDone(try dec.decode(AgentDone.self, from: payload))
            default:        return .unknown(type: kind, raw: p)
            }
        case "agent_tool":     return .agentTool(try dec.decode(AgentTool.self, from: payload))
        case "agent_activity": return .agentActivity(try dec.decode(AgentActivity.self, from: payload))
        case "display":
            guard let d = p["display"] else { return .unknown(type: kind, raw: p) }
            return .display(try dec.decode(DisplayPayload.self, from: JSONEncoder().encode(d)))
        case "ui":             return .ui(try dec.decode(UICommand.self, from: payload))
        case "voice/catalog":  return .voiceCatalog(try dec.decode(VoiceCatalog.self, from: payload))
        case "voice/current":  return .voiceCurrent(p["voice"]?.stringValue ?? "")
        case "speaker_gate":   return .speakerGate(try dec.decode(SpeakerGate.self, from: payload))
        case "capability":
            guard let a = p["agents"] else { return .capability([]) }
            return .capability(try dec.decode([CapabilityAgent].self, from: JSONEncoder().encode(a)))
        default:               return .unknown(type: kind, raw: p)
        }
    }
}
```

**Non-optional scalars decode with a default, not `keyNotFound` (review F8).** §3 N7's optionality mirrors *today's* emitter, but §7 tests *older* emitters that omit fields. The rule, stated once and applied in every payload struct's `init(from:)`: **every non-optional scalar decodes with `decodeIfPresent` and a stated default — `ok` → `true`, every other `Bool` → `false`, every `String` → `""`, every `Int` → `0`.** Optionals (`?`) stay `decodeIfPresent` with `nil`. `AgentDone` is the worked example (it is the one §7 tests both ways — with and without `ok`):
```swift
public struct AgentDone: Sendable, Equatable {
    public let name: String?
    public let displayName: String?
    public let ok: Bool
    public let detail: String
    enum CodingKeys: String, CodingKey { case name, displayName = "display_name", ok, detail }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        name       = try c.decodeIfPresent(String.self, forKey: .name)
        displayName = try c.decodeIfPresent(String.self, forKey: .displayName)
        ok         = try c.decodeIfPresent(Bool.self, forKey: .ok) ?? true       // agentRuns.ts:362
        detail     = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""   // clamp is server-side
    }
}
```
Every other payload struct (`AgentWorking`, `AgentTool`, `AgentActivity`, `VoiceCatalog`, `SpeakerGate`, `CapabilityAgent`, `UICommand`) follows the identical pattern for its non-optional members.

`DisplayPayload.surface` is `public var surface: DisplaySurface` where `public enum DisplaySurface: String { case drawer, window }` and the custom `init(from:)` decodes `String?` and maps nil/unrecognised → `.drawer` (`App.tsx:238-240`, `display.py:92`). All other members are optional exactly as §3 N7's table says.

`ClientMessage.swift`:
```swift
public enum ClientMessage: Sendable, Equatable {
    case voiceSet(voice: String)
    case uiNoop(reason: String)

    /// `if not reason or len(reason) > 200` in pipeline.py drops empty/over-200 reasons.
    public static func noop(_ reason: String) -> ClientMessage? {
        let r = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (1...200).contains(r.count) else { return nil }
        return .uiNoop(reason: r)
    }

    /// The RAW shape (N8): pipeline.py:728 returns a non-"client-message"
    /// dict verbatim, so no envelope is needed or wanted.
    func jsonData() throws -> Data {
        switch self {
        case .voiceSet(let v):  return try JSONEncoder().encode(["type": "voice/set", "voice": v])
        case .uiNoop(let r):    return try JSONEncoder().encode(["type": "ui/noop", "reason": r])
        }
    }
}
```

`AdminAPI.swift` — a struct holding a `JarvisConfig`; one method per route in §3 N14's table, each building the `URLRequest` and calling `JarvisHTTP.send`. Signatures (all `async throws`):
`gitStatus() -> JSONValue`, `selfeditModels() -> JSONValue`, `selfeditStatus() -> JSONValue`, `selfeditRun(goal: String?, profile: String?, plan: String?, stagingId: String?) -> JSONValue` (typed request body from `GoalIn`, N14/F10), `memory() -> JSONValue`, `deleteFact(key: String) -> JSONValue`, `memoryReviews() -> JSONValue`, `resolveReview(id: Int, action: String, rewriteContent: String?) -> JSONValue` (typed request body from `MemoryReviewResolveIn`; **`id: Int`**, N14/F10), `knowledge() -> JSONValue`, `runs() -> JSONValue`, `run(id: String) -> JSONValue`, `ambient() -> JSONValue`, `councilJob() -> JSONValue`, `councilRounds() -> JSONValue`, `councilRound(id: String) -> JSONValue`, `planJob() -> JSONValue`, `health() -> AdminHealth`. Seventeen methods for the seventeen routes.
`AdminHealth` is `struct AdminHealth: Codable, Sendable { public let ok: Bool }` decoded leniently (any 2xx with a JSON object ⇒ `ok = true`). Path parameters go through `addingPercentEncoding(withAllowedCharacters: .urlPathAllowed)`; the fact key and review id are the only interpolated segments.

**Test:** `AppMessageTests.swift` + `ClientMessageTests.swift` — §7.1, §7.2, against the eleven fixtures.

### Step 5 — **Branch B**: signalling + direct WebRTC

`Signalling.swift`:
```swift
struct OfferRequest: Encodable {
    let sdp: String
    let type: String          // "offer"
    var pc_id: String?        // request_handler.py:39
    var restart_pc: Bool?     // request_handler.py:40
}
struct OfferAnswer: Decodable {
    let sdp: String
    let type: String
    let pc_id: String         // connection.py:558-561
}
struct WireIceCandidate: Encodable {
    let candidate: String
    let sdp_mid: String       // request_handler.py:62
    let sdp_mline_index: Int  // request_handler.py:63
}
struct PatchRequest: Encodable {
    let pc_id: String
    let candidates: [WireIceCandidate]
}

enum Signalling {
    /// POST <botURL>/api/offer  (pipecat/runner/run.py:795)
    static func postOffer(_ body: OfferRequest, config: JarvisConfig) async throws -> OfferAnswer
    /// PATCH <botURL>/api/offer (pipecat/runner/run.py:827)
    static func patch(_ body: PatchRequest, config: JarvisConfig) async throws
}
```
Both build `config.botURL.appending(path: "api/offer")`, set `Content-Type: application/json`, encode with a `JSONEncoder` whose `keyEncodingStrategy` is left **default** (the keys above are already the wire names — do not use `.convertToSnakeCase`, it would turn `pc_id` into `pc_id` correctly but `sdp_mline_index` handling would depend on the property name, and explicit names cannot drift).

`RTVITransport.swift` — the seam both branches implement. **No `Sendable` on either protocol (review F5):** the conformer `DirectWebRTCTransport` holds `RTCPeerConnection`, `RTCDataChannel`, the ICE buffer, the outbound queue and `storedPCID` — none `Sendable` — and a `var delegate { get set }` requirement is not Sendable-safe. It is a reference type that serialises its own mutable state on a single internal serial `DispatchQueue` (stated in `DirectWebRTCTransport` below); delegate callbacks hop to `@MainActor` at the `JarvisClient` boundary.
```swift
protocol RTVITransport: AnyObject {
    var delegate: RTVITransportDelegate? { get set }
    func connect(config: JarvisConfig) async throws
    func disconnect() async
    func send(_ data: Data) throws          // one data-channel text frame
    func setMicEnabled(_ enabled: Bool)
}
protocol RTVITransportDelegate: AnyObject {
    func transportDidConnect()
    func transportDidDisconnect(error: Error?)
    func transport(didReceiveFrame data: Data)
    func transport(botIsSpeaking: Bool)     // inbound audio RMS crossing, step 8
}
```

`DirectWebRTCTransport.swift` — the ordered algorithm, written out because it is the part a weaker model would get wrong.

**Object lifetime (review F3) — this is not optional, and it is the difference between a client that reconnects and one whose second Connect click silently does nothing.** A closed `RTCPeerConnection` cannot be reopened; neither can a closed `RTCDataChannel`. Therefore:
- **Process-lifetime statics:** `RTCInitializeSSL()` (step 1) and the `RTCPeerConnectionFactory` (step 2). Built once, never torn down.
- **Per-session, created fresh inside `connect()` every time and released in `disconnect()`:** the `RTCPeerConnection`, the `RTCDataChannel`, the mic `RTCAudioTrack`, the ICE candidate buffer, `storedPCID`, the keep-alive timer and the watchdog. **Steps 2* through 14 below run inside `connect()`** (step 2 reads the shared factory; it does not rebuild it). `connect()` called while `pc != nil` calls `disconnect()` first. This is exercised by `testReconnectAfterDisconnectBuildsNewPeerConnection` (§7.5).

1. `RTCInitializeSSL()` once (a `static let bootstrap`).
2. Build `RTCPeerConnectionFactory(encoderFactory: RTCDefaultVideoEncoderFactory(), decoderFactory: RTCDefaultVideoDecoderFactory())`.
3. `RTCConfiguration`: `iceServers = []` (loopback and, later, a Tailscale interface — R5's rationale is that host candidates suffice and no TURN is needed), `sdpSemantics = .unifiedPlan`, `continualGatheringPolicy = .gatherContinually`.
4. `let pc = factory.peerConnection(with: config, constraints: RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil), delegate: self)`.
5. **Create the data channel before the offer** — the server only ever listens (`connection.py:330`), so if the client does not create one there is none:
   `let cfg = RTCDataChannelConfiguration(); cfg.isOrdered = true; dataChannel = pc.dataChannel(forLabel: "pipecat", configuration: cfg)` — the label is arbitrary and unread by the server; `"pipecat"` is chosen for log legibility.
6. Add the mic track: `let source = factory.audioSource(with: AudioSession.captureConstraints)` (step 8), `let track = factory.audioTrack(with: source, trackId: "jarvis-mic")`, `pc.add(track, streamIds: ["jarvis"])`.
7. `let offer = try await pc.offer(for: RTCMediaConstraints(mandatoryConstraints: ["OfferToReceiveAudio": "true"], optionalConstraints: nil))`; `try await pc.setLocalDescription(offer)`.
8. `let answer = try await Signalling.postOffer(OfferRequest(sdp: offer.sdp, type: "offer", pc_id: nil, restart_pc: nil), config: config)`. Store `answer.pc_id` in `storedPCID`. **`storedPCID` is needed for the ICE `PATCH` (step 10), not for reconnects** — there is no automatic reconnect in this plan (step 7), and because `disconnect()` clears `storedPCID` (step 15) and a network drop clears it too (step 14), every `connect()` sends `pc_id: nil`, which is the correct shape for a *new* connection (`request_handler.py`: a POST with no `pc_id` while a connection is already active is refused, but by then this client has always disconnected first, so no stale connection exists server-side).
9. `try await pc.setRemoteDescription(RTCSessionDescription(type: .answer, sdp: answer.sdp))`.
10. ICE: buffer every `didGenerate candidate` until `storedPCID` is non-nil, then `PATCH` them in batches. Batch rule: flush when the buffer reaches **5** candidates or **250 ms** after the first buffered candidate, whichever comes first (§6). `sdp_mid` uses `candidate.sdpMid ?? "0"`; `sdp_mline_index` uses `Int(candidate.sdpMLineIndex)`.
11. `RTCDataChannelDelegate.dataChannel(_:didChangeState:)`:
    - **Data-channel open deadline (review F14):** when `.connected` is reached (step 14), arm a one-shot timer for `JarvisTuning.dataChannelOpenDeadline` (10 s, mirroring the server's `DATA_CHANNEL_TIMEOUT_SECS`). If the channel has not reached `.open` by then, cancel it and `transportDidDisconnect(error: JarvisError.transport("data channel never opened"))` — the client fails loudly at the same moment the server discards queued messages, instead of appearing connected but deaf.
    - **On `.open`:** start the keep-alive and cancel the open-deadline timer. The keep-alive sends the text frame `"ping"` **unconditionally** every `JarvisTuning.keepAliveInterval` (1.0 s) — never gated on client-side "is the bot idle?" logic. **This is not optional** (§3 N9.5, `connection.py:656-672`); a stalled ping silences the bot's audio (§1.1, F4).
    - **Mechanism, stated so §0.7 does not let it be "improved":** the ping is driven by a `DispatchSourceTimer` on a dedicated serial queue (**not** a bare `Task { while true { try await Task.sleep… } }`, which macOS app-nap suspends in a background window, producing a silent-but-connected session). Each successful `sendData` records `lastKeepAliveSentAt`.
    - **Watchdog (review F4):** a second 1 Hz `DispatchSourceTimer` checks `Date().timeIntervalSince(lastKeepAliveSentAt)`; if it exceeds `JarvisTuning.keepAliveStallSeconds` (2.5 s — inside the server's 3 s window), it transitions `state = .failed("keep-alive stalled")` and tears the transport down (`transportDidDisconnect(error:)`). Tested by `testKeepAliveStallFailsTheSession` (§7.5).
12. `dataChannel(_:didReceiveMessageWith buffer:)` → if `buffer.isBinary` ignore. Otherwise **intercept signalling before handing the frame to the app-message decoder (review F7)** — for Branch B, JarvisKit *is* the transport, so the server's signalling frames are ours to act on, not to discard:
    - Parse `{"type":"signalling","message":{"type": …}}`. On `"peerLeft"` — the server sends this over the data channel *before* closing the peer connection, and it is the only graceful end-of-session signal (`connection.py`, anchor `PeerLeftMessage`, sent from `async def disconnect`) — cancel the keep-alive and watchdog and call `delegate?.transportDidDisconnect(error: nil)`. Without this, a clean bot-side shutdown produces no client state change until libwebrtc's ICE/DTLS teardown eventually flips `RTCPeerConnectionState`, which pipecat's own source warns is unreliable.
    - On `"renegotiate"` — log `signalling_renegotiate_ignored`; it is genuinely unreachable for this audio-only bot (`connection.py` gates `RenegotiateMessage` on a video/screen track, which `bot.py` never enables) but must not crash.
    - Any other signalling message: log and ignore.
    - A **non-signalling** frame → `delegate?.transport(didReceiveFrame: buffer.data)`, where `AppMessage.decode` runs (it returns `nil` for a signalling `type`, which stays correct — the interception above is what acts on it).
13. `send(_:)` → `dataChannel.sendData(RTCDataBuffer(data: data, isBinary: false))`; if the channel is not `.open`, buffer up to `JarvisTuning.outboundQueueMax` (32) frames and flush on open, dropping oldest past the cap (same bounded-history discipline the web stores use).
14. `peerConnection(_:didChange newState: RTCPeerConnectionState)` → `.connected` ⇒ arm the data-channel open-deadline timer (step 11) and `transportDidConnect()`; `.failed`/`.closed`/`.disconnected` ⇒ cancel the keep-alive timer **and the watchdog**, **clear `storedPCID`** (a network drop must not leave a stale id for the next `connect()` — review F3), and `transportDidDisconnect(error:)`.
15. `disconnect()` → cancel keep-alive **and watchdog and open-deadline** timers, `dataChannel?.close()`, `pc.close()`, then set `dataChannel = nil`, `pc = nil`, `micTrack = nil`, empty the ICE buffer, and clear `storedPCID` (a fresh session must not reuse a dead `pc_id`; a nil `pc` is how `connect()` knows it may build a new one — step 5 lifetime).
16. `setMicEnabled(_:)` → `micTrack.isEnabled = enabled`. **Never** `pc.removeTrack` (N9.4).

**Test:** `SignallingTests.swift` — §7.3 (pure encode/decode; no network).

### Step 6 — **Branch A only**: `PipecatSDKTransport.swift`
Taken only when step 2 selected Branch A. Then, and only then:
1. In `Package.swift`, replace the `stasel/WebRTC` dependency with `.package(url: "https://github.com/pipecat-ai/pipecat-client-ios-small-webrtc.git", from: "0.1.0")` and the target dependency with `.product(name: "PipecatClientIOSSmallWebrtc", package: "pipecat-client-ios-small-webrtc")`.
2. **Delete** `Sources/JarvisKit/DirectWebRTCTransport.swift`. Exactly one `RTVITransport` implementation exists in the built package (self-audit item 9 — no "two ways to connect").
3. `PipecatSDKTransport` conforms to `RTVITransport` by holding the SDK's `SmallWebRTCTransport` configured with `baseUrl: config.botURL.appending(path: "api/offer").absoluteString`, mapping the SDK's connect/disconnect callbacks onto `transportDidConnect` / `transportDidDisconnect`, and its server-message callback onto `transport(didReceiveFrame:)` **after re-encoding the delivered object to `Data`** — `AppMessage.decode(frame:)` stays the single decoder in both branches (self-audit item 4).
4. Keep-alive: if the SDK does not document a keep-alive, add the same 1.0 s `"ping"` loop over its message-send API. If it provides one, do **not** add a second.
5. Bearer header: the SDK must be given a way to set `Authorization` on its signalling request. If it exposes request headers, set them from `config.token`. **If it does not, Branch A is void** — revert to Branch B (restore `DirectWebRTCTransport.swift`, restore the `stasel/WebRTC` dependency) and record that in `PROBE.md`. K1 is not optional.

### Step 7 — `JarvisClient` (N5, N6, N11)

```swift
@MainActor
public final class JarvisClient: ObservableObject {
    public enum ConnectionState: Equatable, Sendable {
        case offline, connecting, connected
        case failed(String)
    }

    @Published public private(set) var state: ConnectionState = .offline
    @Published public private(set) var botIsSpeaking: Bool = false
    @Published public private(set) var micEnabled: Bool = true
    @Published public private(set) var wakeWordOn: Bool = false
    @Published public private(set) var wakeWordAvailable: Bool = false
    @Published public private(set) var transcript: [ConversationEntry] = []   // see correction 6
    @Published public private(set) var voices: [Voice] = []
    @Published public private(set) var currentVoice: String = ""

    public private(set) var config: JarvisConfig   // re-read on connect(), F20
    // AdminAPI is a struct holding a JarvisConfig (N14, §5 step 4). The F20
    // token re-read in connect() ALSO reassigns `admin = AdminAPI(config: config)`
    // so an admin request made after a token is stored carries that token —
    // otherwise the lazy snapshot would keep the pre-mint (nil) token.
    public private(set) lazy var admin = AdminAPI(config: config)

    /// F9: a NEW stream per call (a `func`, not a `var`, so that is visible at
    /// the call site). Every stream receives every message from the moment it is
    /// created until the client deinits or the process ends. Bounded:
    /// `.bufferingNewest(JarvisTuning.messageStreamBuffer)` — a stream nobody
    /// drains drops its oldest, it does not leak. Each continuation is registered
    /// in the SAME fan-out table `subscribe(_:)` uses and removed `onTermination`.
    public func messageStream() -> AsyncStream<AppMessage>

    public init(config: JarvisConfig = .default())
    public func connect() async
    public func disconnect() async
    public func send(_ message: ClientMessage)
    public func setMicEnabled(_ on: Bool)
    public func setWakeWord(_ on: Bool) async
    @discardableResult
    public func subscribe(_ handler: @escaping @MainActor (AppMessage) -> Void) -> JarvisSubscription
}

/// F5: token + @Sendable removal closure, so a non-isolated deinit can
/// unsubscribe from a @MainActor handler table without calling a @MainActor
/// method directly. `remove` hops to the main actor internally.
public final class JarvisSubscription {
    private let token: UUID
    private let remove: @Sendable (UUID) -> Void
    init(token: UUID, remove: @escaping @Sendable (UUID) -> Void) { self.token = token; self.remove = remove }
    public func cancel() { remove(token) }
    deinit { remove(token) }
}
// subscribe(_:) builds it as:
//   let token = UUID(); handlers[token] = handler
//   return JarvisSubscription(token: token,
//       remove: { [weak self] t in Task { @MainActor in self?.handlers.removeValue(forKey: t) } })
```

Both the fan-out `handlers` table (keyed by `UUID`) and the `messageStream()` continuation registry are `@MainActor`-isolated; every decoded message is delivered to all handlers and all live stream continuations in one main-actor pass.

Behaviour, fixed:
- `connect()` — in order: (1) **re-read the token from the Keychain into `config`** so a token stored while the app is running attaches on the next connect without a relaunch (review F20; `config.token = JarvisFlags.authEnabled ? KeychainStore.token(for: config.botURL) : nil`, then reassign `admin = AdminAPI(config: config)` so admin calls carry the fresh token), (2) `try config.validate()` and on `JarvisError.insecureHost` set `state = .failed(...)` and stop *before any network* (review F6/C2), (3) `state = .connecting`, (4) resolve the transport (whichever branch exists), (5) `try await transport.connect(config:)`. On success `state = .connected`; on `JarvisError.unauthorized` `state = .failed("Token required")` and **no retry** (N13); on any other error `state = .failed(<localizedDescription>)`. There is no automatic reconnect in this plan — reconnect policy is a T1.3 decision and inventing one here would be a second unowned behaviour. (The transport itself calls `disconnect()` first if it already holds a live `pc` — step 5 lifetime, F3.)
- `disconnect()` — stops the wake listener, `await transport.disconnect()`, `state = .offline`, `botIsSpeaking = false`. **`transcript`, `voices`, and `currentVoice` are NOT cleared** (self-audit item 2: a disconnect must not erase what the user was reading; a fresh `voice/catalog` on the next connect replaces `voices` wholesale, matching `VoicePicker.tsx:20-22`).
- Every decoded `AppMessage` is (a) yielded to `messages`, (b) delivered to every `subscribe` handler in registration order, and (c) applied to `JarvisClient`'s own state for exactly three cases and no others: `.voiceCatalog` → `voices`/`currentVoice`; `.voiceCurrent` → `currentVoice`; `.ui` → the three owned actions in N11. Nothing else mutates client state (C5: JarvisKit is not the interface owner).
- `.ui` handling is the literal table in N11, with the three verbatim strings, sending through `ClientMessage.noop(_:)`.
- `botIsSpeaking` comes from the transport delegate (step 8), never from an app message — no app message reports it.

**Test:** `UICommandOwnershipTests.swift` — §7.5.

### Step 8 — `AudioSession.swift` (N9)
- `AudioSession.captureConstraints`: `RTCMediaConstraints(mandatoryConstraints: ["googEchoCancellation": "true", "googAutoGainControl": "true", "googNoiseSuppression": "true", "googHighpassFilter": "true"], optionalConstraints: nil)`. The first **three** are the A1 protections `web/src/micConstraints.ts` forces on every `getUserMedia` call (anchor `echoCancellation: true,` — the three keys `echoCancellation`/`noiseSuppression`/`autoGainControl`, no highpass). `googHighpassFilter` is a **native-only extra** the browser applies by default and the native stack does not (review F18) — it is not web parity, it restores a default the browser gave for free.
- **Outbound track format:** the mic track added in step 5.6 is a standard libwebrtc audio track (Opus, 48 kHz, mono negotiated in SDP); no manual sample rate is set (see N9.1 — the bot resamples). `captureConstraints` is applied to the WebRTC source **only**; the wake-word `AVAudioEngine` path (step 10) is a separate, unprocessed capture with its own format (16 kHz int16 mono), stated in N10.
- On iOS (`#if os(iOS)`): `AVAudioSession` category `.playAndRecord`, mode `.voiceChat`, options `[.defaultToSpeaker, .allowBluetooth]`, activated on connect and deactivated on disconnect. `.voiceChat` routes input through VPIO, which is why the iOS wake listener is out of scope in T1.2 (N10 rule 3). On macOS: no `AVAudioSession`; echo cancellation comes from the constraints above plus the system's default input processing.
- `botIsSpeaking` — **one mechanism for both platforms (review F12).** The earlier draft's `RTCAudioSession` clause is deleted: `RTCAudioSession` is iOS-only (it wraps `AVAudioSession`), so on macOS — this plan's *primary* platform — it is never available and its fallback was the only real spec. Instead: register an `RTCAudioRenderer` on the remote `RTCAudioTrack` (`remoteTrack.add(renderer)`) and compute RMS over each delivered `RTCAudioBuffer`. Report `true` when RMS exceeds `JarvisTuning.speakingLevelThreshold` (0.01, above the noise floor of a silent Opus stream) and `false` after it has stayed below for `JarvisTuning.speakingReleaseMS` (400 ms — a hold-off longer than inter-word gaps, so a view bound to the flag does not strobe). `RTCAudioRenderer`/`RTCAudioBuffer` are the only WebRTC symbols this uses and both are quoted here per §0.3(a). `speakingPollInterval` is unused by this mechanism and is dropped from §6. **`botIsSpeaking` has one consumer in T1.2 — the host debug label and the wake-listener pause (N10 rule 4) — and is not required by G1(b); if the renderer API proves unavailable on macOS 26, it degrades to always-`false` with a logged `botIsSpeaking_unavailable`, and the wake-pause falls back to "listener runs only while muted" (N10 rule 1), which is already true.** Tested by `testSpeakingHoldOffSuppressesInterWordGaps` (§7.5) over synthetic buffers.
- **Prohibited, spelled out so it is not "improved" back in:** no client-side VAD, no `isEnabled = false` while the bot speaks, no track removal on mute, no half-duplex.

### Step 9 — Barge-in conformance harness
Add `JarvisClient.debugAudioStats` (`sentBytes`, `sentPacketsLastSecond`, `micTrackEnabled`, `lastKeepAliveAt`) published at 1 Hz, and have `MortimerHost` show it. **Why it exists:** G1(b) fails silently if audio stops flowing during bot speech; a counter that keeps climbing while the bot talks is the proof, and §8 V6 reads it.

**Test:** §8 V5–V7 (hardware).

### Step 10 — `WakeWordListener.swift` (N10)
Check exactly as N10 specifies, then:
- **W1:** `URLSessionWebSocketTask` to `config.wakeWordURL`. Capture with `AVAudioEngine`'s input node, install a tap, convert to 16 kHz mono `Int16` with `AVAudioConverter`, accumulate into a `Data` buffer, and send **exactly** `2560`-byte binary messages (`server.py:37-38`) — never a partial frame, never a text frame (`server.py:84-85` ignores text). Decode inbound **text** frames as `{"type":"wake","model":…,"score":…}`; on `type == "wake"`, play the chime (N10) and set `micEnabled = true` (matching `MicControls.tsx:77-80`), then notify subscribers.
- **W2:** `available = false`, `unavailableReason` set from the failure, `wakeWordAvailable = false` on the client, no capture started, no socket retried. A `wake_on` command answers with the verbatim string in N11.
- Either way, `JarvisFlags.wakeWordEnabled == false` short-circuits to W2 with reason `"disabled by JARVIS_WAKEWORD_ENABLED"`.
- Stopping releases the tap, stops the engine, and cancels the socket — the exact resource set `wakeWord.ts:84-96` releases.

**Test:** the frame-size arithmetic is unit-tested (`testWakePCMFramesAreExactly2560Bytes`, §7.6); the socket is hardware (§8 V8).

### Step 11 — `GlassSpike` skeleton (T1.1)
`Package.swift`: executable `GlassSpike`, `platforms: [.macOS(.v26)]`, no dependencies.
`GlassSpikeApp.swift`:
- `@main struct GlassSpikeApp: App` with **two** scenes: `WindowGroup(id: "panelA")` and `WindowGroup(id: "panelB")`, each hosting `GlassPanelView(label:)`.
- On appear of A, `@Environment(\.openWindow) private var openWindow` → `openWindow(id: "panelB")`, then `SpikeScreenPlacement.shared.reposition()`.
- Both windows: `.windowStyle(.hiddenTitleBar)`, `.windowResizability(.contentSize)`, and `.background(TransparentWindowAccessor())` (step 12).
`SpikeScreenPlacement.swift`: the DP8 algorithm from N15, with the two windows treated as (display, drawer) so the 60/40 and one-per-screen rules are both exercised.

### Step 12 — The glass panel and the transparency arms (T1.1)
`TransparentWindow.swift`:
```swift
/// Arm 1 (primary): make the hosting NSWindow non-opaque so a SwiftUI
/// .glassEffect() panel has the desktop behind it, not a white page.
/// Ported from MortimerShell's WindowVibrancy.swift steps 1-2; step 3
/// (WKWebView drawsBackground) is dropped — there is no webview here.
struct TransparentWindowAccessor: NSViewRepresentable {
    var useVisualEffectFallback: Bool          // Arm 2
    func makeNSView(context: Context) -> NSView {
        let probe = NSView()
        DispatchQueue.main.async { apply(to: probe.window) }   // WindowVibrancy.swift:126-128
        return probe
    }
    func updateNSView(_ v: NSView, context: Context) {}
    private func apply(to window: NSWindow?) {
        guard let window, let content = window.contentView else { return }
        window.isOpaque = false
        window.backgroundColor = .clear
        window.titlebarAppearsTransparent = true
        guard useVisualEffectFallback, let frameView = content.superview else { return }
        // The 2026-08-21 fix, carried verbatim (WindowVibrancy.swift:153-164):
        // the effect view MUST be a sibling of contentView, not a subview,
        // or it renders OVER the content and uniformly dims every pixel.
        for stray in content.subviews.compactMap({ $0 as? NSVisualEffectView }) { stray.removeFromSuperview() }
        if frameView.subviews.contains(where: { $0 is NSVisualEffectView }) { return }
        let effect = NSVisualEffectView()
        effect.material = .sidebar               // WindowVibrancy.swift:66 default
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.autoresizingMask = [.width, .height]
        effect.frame = content.frame
        frameView.addSubview(effect, positioned: .below, relativeTo: content)
    }
}
```
`GlassPanelView.swift` — exactly what the spike must show, so the screenshots are comparable:
- A rounded rect panel, 520 × 360, `.glassEffect(.regular, in: .rect(cornerRadius: 28))` in `GlassEffectContainer`.
- A second panel beside it using `.glassEffect(.clear, in: .rect(cornerRadius: 28))`, so `.regular` vs `.clear` appear in **one** screenshot (roadmap T1.0 wants both seen).
- Inside each: a `Text` block containing three lines at 13 pt, 15 pt, and 22 pt — the smallest is deliberately the size a run-card's activity ticker uses, because that is the text most at risk.
- A toggle bound to `JarvisFlags.glassEnabled` that swaps the panels for `.background(.regularMaterial)` (the rollback look, §9).
- A segmented control switching Arm 1 (`.glassEffect` over a transparent window) and Arm 2 (`NSVisualEffectView` fallback), so a failing Arm 1 has an immediate comparison shot rather than a re-build.

### Step 13 — The screenshot checklist (T1.1 acceptance)
Write `macos/GlassSpike/README.md` containing **exactly** the six shots in §8 S1–S6, each with its pass/fail criterion, and a sign-off line Larry dates.

### Step 14 — `MortimerHost` (G1(b) harness)
`Package.swift`: executable, `platforms: [.macOS(.v26)]`, `dependencies: [.package(path: "../JarvisKit")]`.
`MortimerHostApp.swift`: `@main`, one `WindowGroup`, `@StateObject private var client = JarvisClient()` — owned by the app so `disconnect` does not depend on a view's lifetime (N5).
`HostView.swift`: connect/disconnect button; `Text(String(describing: client.state))`; `Toggle("Mic", isOn:)` bound through `setMicEnabled`; `Toggle("Wake word", isOn:)` bound through `setWakeWord`, disabled when `!client.wakeWordAvailable`; `Text` of `debugAudioStats`; a `List` of the last 200 `AppMessage` descriptions fed by `client.subscribe`; and a **`Menu("Debug")` with one item, "Clear stored token"**, calling `KeychainStore.setToken(nil, for: client.config.botURL)` (review F15 — §9's rollback row names this control, so it exists).
`ScreenPlacement.swift` + `WindowLookup.swift`: ported per N15. `MortimerHost` opens only one window, so placement is exercised by the spike; the port lives here because this is the tree T1.3 grows from and porting it twice is how the two copies diverge.
`templates/Info.plist.template`: `NSMicrophoneUsageDescription` = `"Mortimer listens for your voice and for the wake word."`.
`templates/MortimerHost.entitlements.template`: `com.apple.security.device.audio-input` = true, `com.apple.security.network.client` = true. Both are set by hand in Xcode's Signing & Capabilities / Info tabs — SPM executables have no automatic Info.plist mechanism (`macos/MortimerShell/Package.swift:14-21` documents the same constraint for the existing shell).

### Step 15 — `macos/README.md`
Three lines: `JarvisKit/` is the shared client package (this plan); `GlassSpike/` is a throwaway T1.1 target, delete after G1(a); `MortimerHost/` is the G1(b) harness that T1.3 grows into; `MortimerShell/` is the outgoing WKWebView shell, deleted by T1.4 after G1(e). State that `macos/**` is on the self-edit deny list.

---

## §6 Tuning knobs — one home each

All numeric constants live in `macos/JarvisKit/Sources/JarvisKit/JarvisConfig.swift`, in one `public enum JarvisTuning`. Nothing else in the package may contain a bare number that means a duration, a size, or a threshold.

**All `JarvisTuning` constants are compile-time (review F14).** The earlier draft advertised a `UserDefaults` "Override" per constant that no step read — nine phantom rollback levers. Removed. The **only** `UserDefaults`-overridable client state is the three flags and three URLs read in `JarvisConfig`/`JarvisFlags` (§5 step 3). Tuning constants change with a rebuild.

| Constant | Default | Why this value |
|---|---|---|
| `JarvisTuning.keepAliveInterval` | `1.0` s | Must be well under the server's 3 s staleness window (`connection.py:672`); 1 s gives two missed pings of slack |
| `JarvisTuning.keepAliveStallSeconds` | `2.5` s | Watchdog threshold (§5 step 5.11, review F4) — inside the server's 3 s window, so the client fails the session *before* the server silences the bot's audio |
| `JarvisTuning.dataChannelOpenDeadline` | `10.0` s | Mirrors `DATA_CHANNEL_TIMEOUT_SECS` (`connection.py:77`); consumed by step 5.11 — if `.open` is not reached by then the client disconnects loudly at the same moment the server discards queued messages |
| `JarvisTuning.iceBatchSize` | `5` | Batches the PATCH without delaying the first candidates |
| `JarvisTuning.iceBatchDelay` | `0.25` s | Upper bound on how long a candidate waits for company |
| `JarvisTuning.outboundQueueMax` | `32` frames | Bounded, oldest dropped — same discipline as `MAX_AGENT_RUNS`/`MAX_DISPLAY_RESULTS` |
| `JarvisTuning.messageStreamBuffer` | `200` | `messageStream()` buffering (`.bufferingNewest`, review F9) — a stream nobody drains drops oldest, not leaks |
| `JarvisTuning.speakingLevelThreshold` | `0.01` | Above the noise floor of a silent Opus stream (RMS over `RTCAudioBuffer`, step 8) |
| `JarvisTuning.speakingReleaseMS` | `400` ms | Longer than inter-word gaps, shorter than a turn boundary |
| `JarvisTuning.wakeFrameBytes` | `2560` | **Not tunable in effect** — `server.py:37-38` fixes 1280 samples × 2 bytes. Declared as a constant so the arithmetic has one home; changing it breaks the sidecar |
| `JarvisTuning.wakeSampleRate` | `16000` | `server.py:5`, `wakeWord.ts:131` |
| `JarvisTuning.chimeTones` | `[(880, 0.0), (1320, 0.12)]`, gain `0.18`, decay to `0.001` over `0.25` s, teardown `0.8` s | Exact parity with `wakeWord.ts:57-82` |
| `JarvisTuning.maxConversationEntries` | `200` | `conversationFeed.ts:36` |
| `JarvisTuning.maxHostMessages` | `200` | Host debug list; same bounded rule |
| `JarvisHTTP.timeoutSeconds` | `15` s | Long enough for `/api/runs` on a cold DB, short enough that a dead sidecar is obvious |

(`speakingPollInterval` was dropped — the `RTCAudioRenderer` mechanism in step 8, review F12, is event-driven, not polled.)

Kill switches (N16), read only in `JarvisFlags`: `JARVIS_WAKEWORD_ENABLED`, `JARVIS_CLIENT_AUTH_ENABLED`, `JARVIS_GLASS_ENABLED` — all default `true` when the key is absent. **Total `UserDefaults` keys: six** (three URLs + three flags).

**Server-side knobs this plan reads but must never duplicate:** `JARVIS_WAKEWORD_PORT` / `_THRESHOLD` / `_COOLDOWN` / `_MODEL` (`jarvis/wakeword/server.py:113-115`, `:63`) stay server-side; the client only learns the port through `JarvisConfig.wakeWordURL`.

---

## §7 Tests — by file and function

All in `macos/JarvisKit/Tests/JarvisKitTests/`, run by `swift test`. **Fixtures are eleven JSON files** under `Tests/JarvisKitTests/Fixtures/`, one per `AppMessage` case plus one unknown, each the **complete server frame** (envelope included) as `_wrap_rtvi` (`jarvis/bot/pipeline.py`) would send it — used by the eleven happy-path decode tests. **The variant tests build their JSON inline in the test body**, not from a fixture file (review F15): the eleven happy-path decode tests each load one fixture (one per `AppMessage` case + one unknown); every other §7.1 row — the missing/extra/malformed/`null`-field variants, the bare-payload, the signalling frame, the no-`type` frame — constructs its JSON as a string literal in the test. Eleven fixtures, ~24 inputs, no ambiguity about which is which.

### 7.1 `AppMessageTests.swift`

| Function | Input | Expected |
|---|---|---|
| `testDecodeAgentWorking` | `agent_working.json`: `data` = `{"type":"agent","name":"analyst","display_name":"Analyst","state":"working","run_id":"r-1","task":"compare hosts","model":"moonshotai/kimi-k2.5-instruct","model_fallback":false,"model_unusable":false,"model_unusable_detail":""}` | `.agentWorking` with `runId == "r-1"`, `model == "moonshotai/kimi-k2.5-instruct"`, `modelFallback == false` |
| `testDecodeAgentDone` | `agent_done.json`: `{"type":"agent","name":"analyst","display_name":"Analyst","state":"done","ok":false,"detail":"tool failed"}` | `.agentDone(ok: false, detail: "tool failed")` |
| `testDecodeAgentDoneMissingOkDefaultsTrue` | same minus `ok` | `ok == true` (`agentRuns.ts:362` — "bots predating ok/detail send neither — assume success") |
| `testDecodeAgentTool` | `{"type":"agent_tool","name":"developer","display_name":"Developer","tool":"selfedit_start"}` | `.agentTool(tool: "selfedit_start")` |
| `testDecodeAgentActivityWithPlannerModel` | `{"type":"agent_activity","name":"developer","run_id":"r-2","tool":"selfedit_status","ok":true,"latency_ms":812,"planner_model":"claude-opus-4"}` | `.agentActivity` with `latencyMs == 812`, `plannerModel == "claude-opus-4"` |
| `testDecodeAgentActivityWithoutPlannerModel` | same, `tool` = `"web_search"`, no `planner_model` | `plannerModel == nil` |
| `testDecodeDisplayWindowSurface` | `{"type":"display","display":{"kind":"markdown","title":"Weather","body":"…","surface":"window","tool":"weather_report","agent":"analyst","ts":1756200000}}` | `.display`, `surface == .window`, `ts == 1_756_200_000` |
| `testDecodeDisplayMissingSurfaceDefaultsToDrawer` | same minus `surface` | `surface == .drawer` (`App.tsx:238-240`) |
| `testDecodeDisplayUnknownSurfaceDefaultsToDrawer` | `surface = "hologram"` | `surface == .drawer` |
| `testDecodeDisplayHandoffPayloadIgnoresInnerType` | `display` = `{"type":"display","surface":"window","tool":"show_commands","title":"Run this","commands":["ls -la"],"note":"then copy","expect_output":true}` (the literal shape of `handoff_tools.py:158-169`) | decodes; `commands == ["ls -la"]`, `expectOutput == true`; the inner `"type"` is ignored, not an error |
| `testDecodeDisplayClipboardPayload` | `{"type":"display","surface":"window","tool":"read_clipboard","title":"Read from your clipboard","content":"secret text","chars":11,"truncated":false}` | `content == "secret text"`, `chars == 11` |
| `testDecodeDisplayRadarBasemap` | payload with both `images` and `basemap_images` | both arrays present, `basemapImages.count == images.count` |
| `testDecodeUICommandWithTab` | `{"type":"ui","action":"drawer_tab","tab":"agents"}` | `.ui(action: "drawer_tab", tab: "agents")` |
| `testDecodeUICommandWithoutTab` | `{"type":"ui","action":"display_popout"}` | `tab == nil` |
| `testDecodeVoiceCatalog` | `{"type":"voice/catalog","voices":[{"id":"jarvis","elevenlabs_voice_id":"abc","label":"Jarvis"}],"current":"jarvis"}` | one `Voice`, `elevenlabsVoiceID == "abc"`, `current == "jarvis"` |
| `testDecodeVoiceCurrent` | `{"type":"voice/current","voice":"bella"}` | `.voiceCurrent("bella")` |
| `testDecodeSpeakerGateNearThreshold` | `{"type":"speaker_gate","verdict":"dropped","score":0.42,"near_threshold":true}` | `score == 0.42`, `nearThreshold == true` |
| `testDecodeSpeakerGateNullScore` | same with `"score": null` | `score == nil`, no throw (`speaker_gate.py:339` sends `None` when no score) |
| `testDecodeCapability` | `{"type":"capability","agents":[{"name":"analyst","display_name":"Analyst","profile":"deep","resolved_model":null,"fallback":true}]}` | one agent, `resolvedModel == nil`, `fallback == true` |
| `testDecodeUnknownTypePreservesRaw` | `{"type":"weather_alert","severity":"high"}` | `.unknown(type: "weather_alert", raw:)` whose `raw["severity"]?.stringValue == "high"` |
| `testDecodeSignallingFrameReturnsNil` | `{"type":"signalling","message":{…}}` | `nil` (`connection.py:349` — signalling is the transport's, not ours) |
| `testDecodeBarePayloadWithoutEnvelope` | `{"type":"ui","action":"drawer_close"}` with no `label`/`server-message` wrapper | `.ui(action: "drawer_close")` |
| `testDecodeMalformedJSONThrows` | `"{"` | throws; does not crash |
| `testDecodeFrameWithoutTypeReturnsNil` | `{"hello":"world"}` | `nil` |

### 7.2 `ClientMessageTests.swift`
| Function | Input | Expected |
|---|---|---|
| `testVoiceSetEncodesRawShape` | `.voiceSet(voice: "bella")` | JSON object exactly `{"type":"voice/set","voice":"bella"}` — no `label`, no `client-message` wrapper (N8) |
| `testUiNoopEncodesRawShape` | `.uiNoop(reason: "The drawer is already open.")` | `{"type":"ui/noop","reason":"The drawer is already open."}` |
| `testNoopRejectsEmpty` | `ClientMessage.noop("   ")` | `nil` (`pipeline.py:1086`) |
| `testNoopRejectsOver200Chars` | 201-character string | `nil` |
| `testNoopAcceptsExactly200Chars` | 200-character string | non-nil |

### 7.3 `SignallingTests.swift`
| Function | Input | Expected |
|---|---|---|
| `testOfferRequestKeys` | `OfferRequest(sdp: "v=0…", type: "offer", pc_id: nil, restart_pc: nil)` | encodes to exactly the keys `sdp`, `type` (nils omitted); no `pcId`, no camelCase |
| `testOfferRequestWithPCID` | `pc_id: "pc-7"` | key is literally `pc_id` (`request_handler.py:39`) |
| `testOfferAnswerDecodes` | `{"sdp":"v=0…","type":"answer","pc_id":"pc-7"}` | all three fields |
| `testPatchRequestCandidateKeys` | one candidate | keys are `candidate`, `sdp_mid`, `sdp_mline_index` (`request_handler.py:57-63`) |
| `testPatchRequestBatching` | 12 candidates through the batcher with `iceBatchSize = 5` | 3 PATCH bodies of sizes 5, 5, 2 |

### 7.4 `ConfigAndAuthTests.swift`
| Function | Input | Expected |
|---|---|---|
| `testDefaultURLsAreLoopback` | clean env + clean defaults | `botURL == http://127.0.0.1:7860`, `adminURL == http://127.0.0.1:7861`, `wakeWordURL == ws://127.0.0.1:7862/ws` (C2) |
| `testEnvironmentBeatsUserDefaults` | both set to different values | env wins (N12) |
| `testUserDefaultsBeatsCompiledDefault` | only defaults set | defaults value used |
| `testBearerAttachedWhenTokenPresent` | `config.token = "jvt_abc"` | request carries `Authorization: Bearer jvt_abc` |
| `testNoAuthorizationHeaderWhenTokenNil` | `token = nil` | header absent (works against a pre-T2 bot) |
| `testAuthDisabledFlagSuppressesToken` | `JARVIS_CLIENT_AUTH_ENABLED=false` with a token in the Keychain | `config.token == nil`, header absent |
| `test401MapsToUnauthorized` | stub `URLProtocol` returning 401 | `JarvisError.unauthorized`, and the stub records **exactly one** request (no retry, K1) |
| `test403MapsToForbidden` | 403 | `.forbidden` |
| `test500MapsToHTTP` | 500 with body `"boom"` | `.http(status: 500, body: "boom")` |
| `testKeychainAccountDerivedFromBotURL` | `http://192.168.1.9:7860` and `http://127.0.0.1:7860` | different account strings, so relocating to the mini (T3) does not reuse a token |
| `testNonLoopbackWithoutTokenRefuses` | `botURL = http://203.0.113.4:7860`, `token == nil` | `validate()` throws `JarvisError.insecureHost` (C2/F6) |
| `testNonLoopbackWithTokenConnects` | same host, `token != nil`, flag on | `validate()` does not throw |
| `testNonLoopbackWithAuthFlagOffRefuses` | non-loopback host, token present, `JARVIS_CLIENT_AUTH_ENABLED=false` | `validate()` throws `insecureHost` (F19 fail-closed) |
| `testConnectRereadsTokenFromKeychain` | store a token via `KeychainStore.setToken` on a live client, then `connect()` (stub transport) | the transport receives a `config` whose `token` is the just-stored value — no relaunch needed (F20) |

### 7.5 `UICommandOwnershipTests.swift`
Driven by injecting `AppMessage.ui(...)` into a `JarvisClient` with a stub transport that records outbound frames.
| Function | Input | Expected |
|---|---|---|
| `testMicMuteWhenLiveMutes` | `action: "mic_mute"`, `micEnabled = true` | `micEnabled == false`; **no** outbound frame |
| `testMicMuteWhenAlreadyMutedSendsNothing` | same with `micEnabled = false` | no state change, no outbound frame (`MicControls.tsx:100-104`) |
| `testWakeOnWhenUnavailableSendsExactNoop` | `wakeWordAvailable = false` | one outbound frame `{"type":"ui/noop","reason":"The wake word listener isn't available on this machine."}` |
| `testWakeOnWhenAlreadyOnSendsExactNoop` | `wakeWordOn = true` | reason `"The wake word is already on."` |
| `testWakeOffWhenAlreadyOffSendsExactNoop` | `wakeWordOn = false` | reason `"The wake word is already off."` |
| `testUnownedUIActionIsForwardedNotApplied` | `action: "drawer_popout"` | subscriber receives `.ui(action: "drawer_popout")`; client state unchanged; no outbound frame (C5) |
| `testSubscribeReturnsWorkingUnsubscribe` | subscribe, deliver, `cancel()`, deliver again | handler called exactly once |
| `testSubscriptionDeinitUnsubscribes` | subscribe inside a scope, exit scope, deliver | handler not called |
| `testDisconnectPreservesVoicesAndTranscript` | populate, then `disconnect()` | `voices` and `transcript` unchanged, `state == .offline`, `botIsSpeaking == false` (self-audit item 2) |
| `testUnauthorizedConnectDoesNotRetry` | transport throws `.unauthorized` | `state == .failed("Token required")`; transport's `connect` called once |
| `testReconnectAfterDisconnectBuildsNewPeerConnection` | connect, disconnect, connect (stub transport records) | second `connect()` builds a fresh transport session; no "second click does nothing" (F3) |
| `testKeepAliveStallFailsTheSession` | stub transport signals a keep-alive stall past `keepAliveStallSeconds` | `state == .failed("keep-alive stalled")`; transport torn down (F4) |
| `testPeerLeftDisconnects` | stub transport delivers a `{"type":"signalling","message":{"type":"peerLeft"}}` frame | `transportDidDisconnect(error: nil)` fired; `state == .offline` (F7) |
| `testTwoStreamsBothReceiveEveryMessage` | two `messageStream()` iterators, deliver 3 messages | each stream yields all 3 (F9 fan-out; not single-consumer) |
| `testStreamBufferDropsOldest` | one undrained `messageStream()`, deliver `messageStreamBuffer + 5` | oldest 5 dropped, newest `messageStreamBuffer` retained (F9) |
| `testSpeakingHoldOffSuppressesInterWordGaps` | synthetic `RTCAudioBuffer` RMS sequence with a 0.3 s sub-threshold gap | `botIsSpeaking` does **not** transition to `false` during the gap (hold-off, F12) |

### 7.6 `WakeWordFramingTests.swift`
| Function | Input | Expected |
|---|---|---|
| `testWakePCMFramesAreExactly2560Bytes` | 7000 bytes fed through the framer | two 2560-byte frames emitted, 1880 bytes retained (`server.py:86-89`) |
| `testWakeFramerNeverEmitsPartial` | 100 bytes | zero frames emitted |
| `testWakeMessageDecodes` | `{"type":"wake","model":"mortimer","score":0.83}` | `WakeEvent(model: "mortimer", score: 0.83)` |
| `testNonWakeTextFrameIgnored` | `{"type":"hello"}` | `nil`, no throw (`wakeWord.ts:118` ignores everything else) |

### 7.7 `AdminAPITests.swift`
Against a stub `URLProtocol` recording the outgoing request — asserts **URL, method, header, and (for the two POSTs) request-body key names**, not response shape (responses are `JSONValue`, N14).
| Function | Input | Expected |
|---|---|---|
| `testAdminRoutesBuildExpectedURLs` | each of the seventeen methods | the exact path + HTTP verb in N14's table; **seventeen** requests observed (this is the test that would have caught the 14-vs-17 miscount, F10) |
| `testSelfeditRunEncodesGoalInKeys` | `selfeditRun(goal:"x", profile:nil, plan:nil, stagingId:"s1")` | body keys are `goal`, `staging_id` (nils omitted); no camelCase (`GoalIn`) |
| `testResolveReviewUsesIntIdAndBodyKeys` | `resolveReview(id: 7, action:"approve", rewriteContent:nil)` | path `…/reviews/7/resolve`; body key `action` (`MemoryReviewResolveIn`); `id` is `Int` so a non-numeric id cannot be constructed |
| `testBearerHeaderOnAdminRoute` | `config.token = "jvt"` | every admin request carries `Authorization: Bearer jvt` (one attach point, N13) |

### 7.8 Not tested here, and why
- The `ConversationEntry` / RTVI-transcription decoder is unit-tested for shape (`testDecodeUserTranscription`, `testDecodeBotTranscription` against `pipecat/processors/frameworks/rtvi/models.py:444,511`, in `AppMessageTests.swift`) but has no end-to-end test, because **this bot emits neither** (correction 6). Do not write an integration test that will silently pass by never running.

---

## §8 Verification Larry runs on his hardware

The sandbox has no Xcode, no Swift toolchain, no Keychain, no microphone, no second display, and no network to GitHub. Everything below is Larry's.

### Build and unit gate
- **V1.** `cd macos/JarvisKit && swift build` → exit 0. *(If Branch B, this is also the proof that `stasel/WebRTC` resolves.)*
- **V2.** `cd macos/JarvisKit && swift test` → all of §7 pass; record the count.
- **V3.** `cd macos/GlassSpike && swift build` → exit 0.
- **V4.** `cd macos/MortimerHost && swift build` → exit 0. Open `Package.swift` in Xcode, set `NSMicrophoneUsageDescription` and the two entitlements from `templates/`, run.

### G1(b) — live voice session with barge-in
Preconditions: **`./scripts/mortimer.sh start`** (not `run_bot.sh` — the latter execs the bot on stdout and never creates `logs/bot.log`; `mortimer.sh` rotates and creates `logs/bot.log`, `logs/admin.log`, `logs/web.log`, review F11; tail with `./scripts/mortimer.sh logs`). `MortimerHost` running; no browser tab open on the console (so only one client exists).

- **V4b — mint a token (only if the bot has T2/K1 auth enabled; `CROSS_PLAN_RESOLUTION.md` §C F15).** If `JARVIS_AUTH_ENABLED=true`, mint a client token per `MORTIMER_REMOTE_ACCESS_PLAN.md` and store it via the host's Debug menu → (or) `KeychainStore.setToken(_:for:)` keyed on the bot URL. **Without this, V5 correctly ends in `state = .failed("Token required")` — that is correct behaviour, not a defect.** If the bot is still pre-T2 (unauthenticated), skip this step; `token == nil` and no header is sent.
- **V5 — session.** Click Connect. **Pass:** `state` shows `connected` within 5 s; the greeting is *heard*; `logs/bot.log` contains `[session] client connected`.
- **V6 — audio never stops.** While Mortimer is mid-sentence, watch `debugAudioStats`. **Pass:** `sentPacketsLastSecond > 0` continuously through the bot's entire reply, and `micTrackEnabled == true` throughout. **Fail:** any second at zero — that is N9 violated and barge-in cannot work.
- **V7 — the interruption scenarios, judged by CLIENT-OBSERVABLE behaviour (review F1/F16).** The interruption *notice* is injected into LLM context only and is never logged (`interruption.py` has zero logging), so there is nothing to read in `bot.log`. Instead each row's pass/fail is what the host and your ears can see. Of `test_interruption.py`'s eight scenarios, these are the five reachable live; the kill-switch and upstream-direction tests stay unit-only.

| # | Do this | Pass (observable) — Fail |
|---|---|---|
| 7a | Ask a question; let the reply finish completely; say nothing | **Pass:** bot completes; `botIsSpeaking` goes `false` at the end; no early stop. **Fail:** bot cuts itself off (a spurious self-interruption) |
| 7b | Ask a question; interrupt **after** Mortimer starts speaking | **Pass:** `botIsSpeaking` → `false` within ≈2.5 s of your onset **while `sentPacketsLastSecond` stayed > 0 throughout** (V6), the bot then answers your new utterance, and a follow-up "what were you saying?" gets a reply that acknowledges being cut off (the closest live proxy for the mid-speech notice). **Fail:** bot talks to completion ignoring you — audio was withheld (re-check V6) or client-side VAD is on (N9.2) |
| 7c | Ask a question; interrupt **while it is thinking**, before any audio | **Pass:** the in-flight reply is abandoned and the bot answers the new utterance. **Fail:** the original answer arrives anyway |
| 7d | Two consecutive clean turns (repurposed from the old duplicate 7a) | **Pass:** both complete normally — `_assistant_active` reset after the first, no stuck state. **Fail:** the second turn behaves as if still mid-interruption |
| 7e | With the TV on (or a second voice), stay silent through a full reply | **Pass:** bot completes uninterrupted; if the speaker gate is enabled, `speaker_gate_dropped` lines appear in `bot.log` and the bot does **not** stop. **Fail:** the second voice interrupts the bot |
| 7f | Interrupt twice inside one reply | **Pass:** the bot stops on the first interrupt and handles the sequence without crashing or double-processing. **Fail:** a crash, or the second interrupt is mishandled |

**Pass:** all five match. **This gate CAN fail** — a client that withholds audio during bot speech leaves 7b/7c showing the bot talking to completion. Do not change anything under `jarvis/`. (The server-side mid-speech-vs-while-thinking *notice text* is not observable without a backend change — R-N6.)

- **V8 — wake word.** Start `./scripts/run_wakeword.sh`. Run the N10 probe (the `--max-time 3` `curl`); record `WAKE_PROBE=<code>` in `PROBE.md`. Connect a session, then **mute the mic** (the listener runs only while `.connected && !micEnabled`, N10 rule 1). If `WAKE_PROBE=101`: enable the wake toggle, say "Mortimer". **Pass:** two-tone chime, mic unmutes, `jarvis.wakeword` logs `console connected`. If anything else (incl. `000`): **Pass** is the toggle being disabled and a spoken *"The wake word listener isn't available on this machine."* when you say "open the wake word". On iOS this release, the toggle is disabled regardless (N10 rule 3).
- **V9 — routing eval (C7 / G1(d)).** `RUN_LIVE=1 python -m tests.evals.routing_eval`. Expected: unchanged from the last recorded score, ≥ 90 %. No backend changed, so a change here means something else moved. **Record the number in the PR.**

### T1.1 — the six screenshots Larry signs (G1(a))
Taken on Larry's hardware, two displays connected, over a **deliberately busy desktop**: a full-screen photo with both light and dark regions, plus a terminal with white-on-black text visible behind the panel.

| Shot | Setup | Pass | Fail |
|---|---|---|---|
| **S1 — transparency exists** | Arm 1, one window, `.regular` panel over the photo | The photo is *recognisable* through the panel; the window is not a grey rectangle | Uniform grey/white → Arm 1 failed; take S1b with Arm 2 and note it |
| **S2 — `.regular` vs `.clear` side by side** | Both panels in one window | Both visibly different from each other and both showing the desktop | Indistinguishable → record it; the T1.0 review needs to know the two treatments do not differ meaningfully here |
| **S3 — legibility over the worst case** | Panel positioned over the boundary between the photo's brightest and darkest region | All three text sizes readable **without leaning in**, including the 13 pt line | The 13 pt line unreadable → record the smallest size that *is* readable; T1.3's type floor is that number |
| **S4 — two windows, two displays** | Both windows open, two displays attached | One window fully on each display, each filling `visibleFrame` | Both on one display → `SpikeScreenPlacement` / `openWindow` did not take effect; capture `Console.app` output for `screen-placement` |
| **S5 — one display, both windows** | Unplug the second display with both open | Left window 60 % width, right 40 %, both full height (DP8) | Any other split |
| **S6 — hot-plug** | With both windows open on one display, plug the second display back in | Windows relocate **without a relaunch** (`didChangeScreenParametersNotification`) | Requires relaunch → the observer is not registered |

`macos/GlassSpike/README.md` carries this table with a `Signed: ______  Date: ______` line. **G1(a) passes only when Larry signs it.** A failing S1 does not block G1(b) — it blocks T1.0's design brief, which is exactly what the spike is for.

### What could not be verified here
`swift build`, `swift test`, `.glassEffect()` rendering, `NSVisualEffectView` behaviour on macOS 26, Keychain access, WebRTC negotiation, microphone capture, the wake-word socket, and whether `pipecat-client-ios-small-webrtc` resolves at all. Every one of them is above.

---

## §9 Rollback

Nothing in this plan changes runtime behaviour of anything that exists today, so rollback is mostly "stop launching the new app".

| To undo | How |
|---|---|
| The whole plan | `git revert` the `native-client-core` merge. `web/`, `macos/MortimerShell/`, and every Python file are untouched by it, so the running system is unaffected either way — the web console and the WKWebView shell keep working throughout (that is C1 and §0.4 doing their job). |
| Glass, without a rebuild | `defaults write <MortimerHost bundle-id> JARVIS_GLASS_ENABLED -bool false` and relaunch → opaque windows, `.regularMaterial` panels. |
| Wake word, without a rebuild | `defaults write <bundle-id> JARVIS_WAKEWORD_ENABLED -bool false` → the listener never starts; the wake toggle is disabled; the existing "not available" copy is spoken. |
| Token auth, without a rebuild | `defaults write <bundle-id> JARVIS_CLIENT_AUTH_ENABLED -bool false` → no `Authorization` header. Use this to isolate a T2 401 to the client half. |
| Point at a different bot/sidecar | `defaults write <bundle-id> JARVIS_BOT_URL -string http://…` (same for `JARVIS_ADMIN_URL`, `JARVIS_WAKEWORD_URL`), or export the env var before launch. |
| A stored token | `KeychainStore.setToken(nil, for:)` from the host's debug menu, or Keychain Access → delete the `com.mortimer.jarviskit` item. |
| Branch A turned out wrong | Restore `DirectWebRTCTransport.swift` and the `stasel/WebRTC` dependency (both are in git history), delete `PipecatSDKTransport.swift`, update `PROBE.md`. §5 step 6.5 already names this path. |

**Data changes to revert: none.** This plan writes no rows, no files under `data/`, and no vault entries. The only persistent state it creates is one Keychain item and **six** `UserDefaults` keys (three URLs + three flags — §6; the tuning constants are compile-time, review F14), all listed above.

---

## §10 Risks

| Id | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| **R-N1** | `.glassEffect()` over a transparent `NSWindow` does not composite the desktop (the API may only sample in-app content) | medium | T1.0's design brief is built on a false premise | That is precisely what S1/S1b measure; Arm 2 (`NSVisualEffectView`, the verified-by-Larry MortimerShell recipe) is in the same binary behind a segmented control, so the answer costs one click, not one rebuild |
| **R-N2** | `pipecat-client-ios-small-webrtc` does not exist, does not support macOS 26, or cannot set an `Authorization` header | **likely** | Branch A unavailable | Branch B is the default and is written out in full (§5 step 5); the probe (§5 step 2) decides mechanically and the outcome is recorded in `PROBE.md` |
| **R-N3** | `stasel/WebRTC` also fails to resolve, or its API has drifted from `RTCPeerConnectionFactory`/`RTCDataChannel` | low | No transport at all | §0.6: report and stop. Do **not** vendor a framework by hand and do **not** fall back to a `WKWebView` peer connection (R1 rejected that architecture) |
| **R-N4** | The client stops sending audio while the bot speaks (a "sensible" half-duplex optimisation) and barge-in silently dies | medium | G1(b) fails, and it fails in a way that looks like a server bug | N9 states it as a prohibition; V6 measures it with a live packet counter; §5 step 8 names the four prohibited techniques explicitly |
| **R-N5** | The keep-alive is omitted, sent once, or its `Task.sleep` loop is app-nap-suspended, so `is_connected()` goes false | medium | **The bot's audio output stops entirely, along with every server→client app message — no error on either side** (F4: `_can_send()` gates `write_audio_frame`, not just `send_message`) | Ping is a `DispatchSourceTimer` (not `Task.sleep`), sent unconditionally; a watchdog (`keepAliveStallSeconds`, step 5.11) transitions to `.failed("keep-alive stalled")` inside the server's 3 s window; `testKeepAliveStallFailsTheSession` proves it |
| **R-N6** | No transcript exists over the wire (correction 6), so a native Log tab has nothing to render | **certain** | T1.3 ships a dead tab, or T1.3 needs a backend change it is not scoped for | Recorded here, in §1.6, and in correction 6. `ConversationEntry` and the RTVI-transcription decoder ship *ready*; adding `RTVIObserver` to `jarvis/bot/pipeline.py` is one line but is a backend change (C1) and belongs to the T1.3 plan or its own |
| **R-N7** | macOS 26 / iOS 26 as the platform floor excludes a machine Larry actually uses | low | Cannot run the app | K8 fixes these platforms; if a machine is older, that is a K8 amendment, not a local workaround. Report and stop |
| **R-N8** | Two clients connected at once (browser console + `MortimerHost`) | medium during migration | The second POST is refused (`request_handler.py:147-150`) and looks like a client bug | V5's precondition says one client; the refusal maps to `JarvisError.http(status:)` and the host shows the body verbatim |
| **R-N9** | The wake sidecar's model is missing so the process exits at startup (`server.py:63-69`) and the probe reports connection-refused | medium | Wake word degraded | Branch W2 is a first-class state, not an error path; the existing copy is spoken; nothing else degrades |
| **R-N10** | `AdminAPI` returning `JSONValue` **responses** is read as "untyped" and T1.3 re-invents its own client | medium | Two admin clients | N14 states the narrowing (response bodies only — request bodies ARE typed, F10) and why; **`MORTIMER_NATIVE_CLIENT_APP_PLAN.md` (T1.3) is the sole owner of the per-tab response structs** (`CROSS_PLAN_RESOLUTION.md` §C F12), added **inside** `AdminAPI`, not beside it |
| **R-N11** | `KeychainStore` (K1 token, no user-presence gate) is mistaken for the T4b sensitive-tier key holder | low | A later plan stores a sensitive-tier key without the presence gate, or the bot can read it | Stated in §2 and here (`CROSS_PLAN_RESOLUTION.md` §C F13): **`KeychainStore` holds the K1 bearer token only**, `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, no `SecAccessControl`. The T4b tier key is a **different Keychain item**, gated with `SecAccessControl` user-presence and unreadable by the bot, introduced by the (unwritten) T4b plan — not extended out of `KeychainStore`. Roadmap §5 W4 carries the same clause |

---

## §11 Self-audit — the nine-item taxonomy, walked

1. **Multi-consumer contracts named but not typed.** K8 is introduced here and every member is specified: `AppMessage`'s ten cases with each member's Swift type, JSON key, optionality, and source line (§3 N7 tables); `DisplayPayload`'s sixteen members in a table; `ClientMessage`'s two cases with their exact serialised JSON; `JarvisConfig`'s four fields and their resolution order; `KeychainStore`'s two functions with service/account/accessibility; `JarvisClient`'s full declaration including which publishes exist; `AdminAPI`'s seventeen methods for seventeen routes (fourteen tab groupings) with `server.py` anchors, its two POST request bodies typed from `GoalIn`/`MemoryReviewResolveIn` (F10); `RTVITransport` and its delegate as literal protocol declarations (no `Sendable`, F5). **Message delivery is specified:** `messageStream() -> AsyncStream<AppMessage>` (a fan-out, one stream per call, bounded `.bufferingNewest`, F9) plus `subscribe(_:) -> JarvisSubscription`, which unsubscribes on `cancel()` *and* on `deinit` via the token+closure form (F5), tested by `testSubscribeReturnsWorkingUnsubscribe`, `testSubscriptionDeinitUnsubscribes`, `testTwoStreamsBothReceiveEveryMessage`. The one narrowing (`AdminAPI` **response** bodies as `JSONValue`; request bodies are typed) is stated in N14 with its reason and flagged again in R-N10.
2. **Lifecycle left implicit.** Stated: `JarvisClient` is owned by the app, not a view (§5 step 7, N5); `disconnect()` clears `state` and `botIsSpeaking` but **preserves** `voices`, `currentVoice`, and `transcript`, with a test; `connect()` does **not** auto-retry and reconnect policy is explicitly deferred to T1.3; `JarvisSubscription` dies with its owner; the wake listener stops on `disconnect()` and releases the exact resource set `wakeWord.ts:84-96` releases; **the per-session object graph (`pc`, data channel, mic track, ICE buffer, `storedPCID`, keep-alive timer, watchdog) is built fresh inside every `connect()` and released in every `disconnect()`** (§5 step 5 lifetime, F3), so connect→disconnect→connect works (`testReconnectAfterDisconnectBuildsNewPeerConnection`); the keep-alive is watchdogged so an app-nap stall fails the session rather than silently muting the bot (F4).
3. **How a value is applied.** Named property by property: `micEnabled` → `RTCAudioTrack.isEnabled` (never `removeTrack`); glass → `.glassEffect(.regular/.clear, in: .rect(cornerRadius: 28))` inside `GlassEffectContainer`; transparency → `NSWindow.isOpaque = false` + `backgroundColor = .clear` + `titlebarAppearsTransparent = true`; the fallback material → `NSVisualEffectView.material = .sidebar`, `blendingMode = .behindWindow`, `state = .active`, added to `contentView.superview` **below** `contentView`; placement → `NSWindow.setFrame(screen.visibleFrame, display: true)` and the 60/40 `NSRect` arithmetic ported verbatim; the bearer token → `URLRequest.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")` in one function.
4. **Two sections describing the same behaviour differently.** Checked pairwise: the `surface` default is stated once as a rule (N7) and once as a decoder location (§5 step 4) — same rule, `.drawer`, one implementation. The keep-alive appears in §1.1 (why), N9.5 (obligation), §5 step 5.11 (code), §6 (the number) and R-N5 (risk) — one value, one owner, `JarvisTuning.keepAliveInterval`. The wake chime is specified once numerically (§6) and referenced elsewhere. The three `ui/noop` strings appear once (N11) and are referenced by §7.5. `AppMessage` decoding exists in exactly one function in both transport branches (§5 step 6.3 says so explicitly).
5. **Copy and visual states named but unspecified.** The only user-visible copy JarvisKit owns is the three wake/mic no-op sentences, quoted verbatim from `MicControls.tsx:111,115,123`, plus `NSMicrophoneUsageDescription`'s exact string (§5 step 14) and `state = .failed("Token required")`. All other `ui` copy belongs to T1.3 and N11 says so. Visual states in scope: the spike's two glass treatments, the three text sizes, the rollback look, and the host's five controls — each enumerated in §5 steps 12 and 14. The host is deliberately unstyled and §3 N2 says why.
6. **Initialization timing.** Fixed: `RTCInitializeSSL()` once via a `static let`; the data channel is created **before** the offer (§5 step 5.5 — the server only listens, `connection.py:330`); the keep-alive starts on `didChangeState → .open`, not on connect; ICE candidates buffer until `pc_id` exists and only then PATCH; `TransparentWindowAccessor` defers to the next runloop turn because `probe.window` is nil at `makeNSView` time (the reason is quoted from `WindowVibrancy.swift:126-128`); `JarvisConfig.default()` reads the Keychain at construction **and `connect()` re-reads it** so a token minted while the app runs attaches on the next connect without a relaunch (F20); `openWindow(id: "panelB")` fires on A's appear, then placement runs.
7. **Signatures agree; every schema column is populated; every value is derivable.** Every `AppMessage` member is produced by a cited emitter line or a cited consumer field, and every fixture in §7.1 populates the members its case declares. `AgentDone` deliberately lacks `runId`/`model` because the emitter's done branch (`pipeline.py:279-286`) does not send them — a column that no step could populate would be the defect this item names. `plannerModel` is optional precisely because `pipeline.py:206-211` only sets it for two tool names, and §7.1 tests both ways. `pc_id` is derivable (it comes back in the answer) before it is ever needed (the PATCH). `JarvisConfig.token` is derivable before `connect()` (Keychain at construction). `debugAudioStats` is derivable from the peer connection's own statistics.
8. **Judgment left to the implementer.** Searched for the three shapes. The two genuine unknowns are decision trees with executable checks and both branches written: the Swift SDK (§3 N3 / §5 step 2, with the probe file given verbatim and Branch B implemented in full) and the wake word (§3 N10 / §5 step 10, with a `curl` that **terminates** — `--max-time 3` — and yields `WAKE_PROBE=101` for W1 or anything else for W2, F2; both Swift paths written regardless). The "be careful" area — the bearer token — is literal code (§5 step 3) plus the adversarial cases as tests (401 with no retry, 403, token suppressed by the flag, per-host Keychain accounts, non-loopback-without-token refusal F6, connect-time re-read F20). Three places say "report and stop" rather than leaving a gap: no WebRTC dependency at all, a probe outcome matching neither branch, and a platform floor Larry's hardware cannot meet.
9. **Plan drift.** Every file in §5 appears in §4 and vice versa — including `PROBE.md` (written in step 2), the eleven fixtures (step 4), the two `templates/` files (step 14), and **all seven test files** (`AppMessageTests`, `ClientMessageTests`, `SignallingTests`, `ConfigAndAuthTests`, `UICommandOwnershipTests`, `WakeWordFramingTests` §7.6, `AdminAPITests` §7.7 — the last two added in this revision, review F15, so §7.6/§7.7 now each have a manifest row). §4's **delete** section is empty and §0.4 says why, so no section says "delete `web/`" while another says it survives. The two branch-conditional files are handled explicitly: `DirectWebRTCTransport.swift` is created in step 5 and **deleted** in step 6 if and only if Branch A is taken, and step 6.2 states the invariant ("exactly one `RTVITransport` implementation exists in the built package"). `ScreenPlacement.swift` is described consistently as a **port into `MortimerHost`** with the original left in place. Nothing in this plan claims a file under `jarvis/` exists that does not, and correction 4 fixes the one place the brief itself pointed at a stub.

**Roadmap §6 cross-track invariants:** (1) no host is named in code — every URL comes from `JarvisConfig.default()`, and "the mini" appears nowhere; (2) no new table, so no `user_id` obligation; (3) no new MCP server; (4) no new agent-facing capability, so `TOTAL_TOOLS` and the routing fixture are untouched; (5) this plan ends with the routing-eval requirement (V9), the test counts (V2), and the hardware-only list (end of §8).

---

## §12 Approval checklist

- [ ] Larry accepts the scope: T1.1 spike + T1.2 `JarvisKit` + a harness app, with **T1.3's view port explicitly deferred to his Liquid Glass design review (R3)**.
- [ ] Larry accepts the six roadmap corrections at the top, in particular that there is **no client-side barge-in signal** and **no transcript over the wire**.
- [ ] Larry accepts K8 as specified in §3, including the one narrowing: `AdminAPI` returns `JSONValue` **response** bodies (request bodies and routes are fully typed — N14, R-N10, review F10).
- [ ] Larry accepts `JARVIS_CLIENT_AUTH_ENABLED` as a declared K1 extension with fail-closed shape (§3 N16, review F19).
- [ ] Larry accepts that `web/` and `macos/MortimerShell/` are **not** deleted here (T1.4, gated on G1(e)).
- [ ] Larry accepts macOS 26 / iOS 26 as `JarvisKit`'s platform floor.
- [ ] Larry accepts the wake-word decision: stream to the existing `127.0.0.1:7862` sidecar; no Swift port of openWakeWord; degraded-but-honest when it is not running.
- [ ] Larry runs V1–V4 (build + unit tests) and records the test count.
- [ ] Larry runs the S1–S6 screenshot checklist and **signs** `macos/GlassSpike/README.md` → **G1(a)**.
- [ ] Larry runs V5–V8 and records the five interruption outcomes → **G1(b)**.
- [ ] Larry runs V9 (`RUN_LIVE=1 python -m tests.evals.routing_eval`) and records the score → **G1(d)**, C7.
- [ ] Larry commits on branch `native-client-core` (the implementer runs no `git`, §0.2).
- [ ] Open item carried to the T1.3 plan: whether to add `RTVIObserver` to the bot so a native Log tab has content (R-N6).
