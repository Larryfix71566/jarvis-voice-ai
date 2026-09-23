import Foundation
import os

private let clientLog = Logger(subsystem: "com.mortimer.jarviskit", category: "client")

/// N5/N6/N11. Owned by the app, not a view (self-audit item 2) — state
/// survives a view being torn down.
@MainActor
public final class JarvisClient: ObservableObject {
    public enum ConnectionState: Equatable, Sendable {
        case offline, connecting, connected
        case failed(String)
    }

    @Published public private(set) var state: ConnectionState = .offline
    @Published public private(set) var botIsSpeaking: Bool = false
    /// E1 thinking shimmer (OrbField.tsx:171-172) — LLM inference in
    /// flight, from the bot's own `bot-llm-started`/`bot-llm-stopped`
    /// RTVI observer frames (same live-verified channel botIsSpeaking
    /// rides). Views show "Thinking" only while NOT speaking — speech
    /// outranks the shimmer (OrbField.tsx:324-334).
    @Published public private(set) var botIsThinking: Bool = false
    /// Wake-detection pulse (wakeWord.ts subscribeWake) — increments on
    /// every wake-word detection so views can replay one-shot effects
    /// (stage ripple, wave flash). This is the "public wake event" the
    /// T1.3 wave port's deviation note was waiting on.
    @Published public private(set) var wakePulse: Int = 0
    // internal(set), not private(set): §7.5's UICommandOwnershipTests set
    // up preconditions (e.g. "wakeWordAvailable = false") by direct field
    // assignment via @testable import, which sees `internal` but not
    // `private` across files.
    /// Closure C7: measured input and playout levels for the wave, at
    /// ≤30 Hz, from the native path's own capture and mixer taps. Nil on
    /// the WebRTC path and while the meter is disabled — the presentation
    /// says "unavailable" rather than drawing silence.
    @Published public private(set) var audioActivity: AudioActivitySnapshot?
    /// The generation the presentation must match; a new session
    /// invalidates the last one's observations (gap G24: this used to be
    /// view `@State`).
    public var audioActivityGeneration: UUID { audioMeter.generation }
    /// C7.5: the meter's reading for the session that just ended, captured
    /// before the observer clears its window. The app writes the acceptance
    /// report from this, so the gate's evidence does not depend on anyone
    /// remembering a menu item mid-call. Non-nil with zero observations is
    /// a real answer: a session happened and measured nothing.
    @Published public private(set) var lastSessionAudioLatency: AudioMeterLatency?
    @Published public internal(set) var micEnabled: Bool = true
    @Published public internal(set) var wakeWordOn: Bool = false
    @Published public internal(set) var wakeWordAvailable: Bool = false
    /// Spoken conversation, aggregated client-side from the live RTVI
    /// observer frames (user-transcription finals + the bot-llm-text
    /// token stream) — see the transcript-aggregation section below.
    /// CORE correction 6 said this bot emits neither; the 2026-08-30
    /// live session disproved that, so this now lights up with no
    /// backend change.
    @Published public private(set) var transcript: [ConversationEntry] = []
    @Published public private(set) var voices: [Voice] = []
    @Published public private(set) var currentVoice: String = ""
    /// The negotiated console identity used to bind approved content
    /// transfers to the current bot session. Nil until the handshake arrives.
    @Published public private(set) var consoleSessionID: UUID?
    @Published public private(set) var consoleGeneration: UUID?
    @Published public private(set) var consoleInputProfile: ConsoleInputProfile?

    /// §5 step 9 — the barge-in conformance harness. sentPacketsLastSecond
    /// is a coarse proxy computed from the transport's running byte
    /// counter; it exists so §8 V6 has something to watch, not as a
    /// precise metric.
    public struct DebugAudioStats: Equatable, Sendable {
        public var sentBytes: Int = 0
        public var sentPacketsLastSecond: Int = 0
        public var micTrackEnabled: Bool = true
        public var lastKeepAliveAt: Date? = nil
    }
    @Published public private(set) var debugAudioStats = DebugAudioStats()

    #if os(macOS)
    /// 2026-09-05 — set when macOS's default output device changes while
    /// a session is live (AirPods connecting): this WebRTC build's playout
    /// stays on the device it opened, so the app surfaces a Reconnect
    /// (see AudioOutputMonitor). Cleared on the next successful connect.
    /// With JarvisFlags.followAudioOutput the client reconnects itself.
    @Published public private(set) var audioOutputChange: AudioOutputChange?
    private lazy var audioOutputMonitor = AudioOutputMonitor { [weak self] previous, next in
        self?.handleAudioOutputChange(from: previous, to: next)
    }
    /// 2026-09-05 — set when connect() repointed the default INPUT to a
    /// rate-matching mic so the AirPods 24 kHz mic can't slow playout
    /// (see AudioInputCoordinator). Informational — the fix already
    /// happened. Cleared on the next connect.
    @Published public private(set) var audioInputChange: AudioInputChange?
    private let audioInputCoordinator = AudioInputCoordinator()
    #endif

    public private(set) var config: JarvisConfig   // re-read on connect(), F20
    // AdminAPI is a struct holding a JarvisConfig (N14, §5 step 4). The F20
    // token re-read in connect() ALSO reassigns `admin = AdminAPI(config: config)`
    // so an admin request made after a token is stored carries that token —
    // otherwise the lazy snapshot would keep the pre-mint (nil) token.
    public private(set) lazy var admin: AdminAPI = AdminAPI(config: config)
    // Same pattern, same reason — Phase 0 step 9's costs service.
    public private(set) lazy var costs: CostsAPI = CostsAPI(config: config)

    // internal (not private): §7.5's UICommandOwnershipTests and §7.4's
    // testConnectRereadsTokenFromKeychain inject a stub transport via the
    // test-only initializer at the bottom of this file. @testable import
    // exposes `internal`, never `private`, across files — hence internal.
    lazy var transport: RTVITransport = {
        let t = Self.makeTransport(for: config)
        t.delegate = self
        return t
    }()

    /// MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md D1: a loopback bot gets the
    /// native path (AVAudioEngine + one WebSocket); anything else — the
    /// remote/T2 path — keeps WebRTC. `JarvisFlags.forceWebRTC` is the
    /// rollback lever (§9): on, loopback uses WebRTC exactly as before.
    static func usesNativeAudio(for config: JarvisConfig) -> Bool {
        guard let host = config.botURL.host, JarvisConfig.loopbackHosts.contains(host) else { return false }
        return !JarvisFlags.forceWebRTC
    }

    static func makeTransport(for config: JarvisConfig) -> RTVITransport {
        usesNativeAudio(for: config) ? NativeAudioTransport() : DirectWebRTCTransport()
    }

    /// True while the live transport is the native path — the app uses it
    /// to hide the WebRTC-only device notices.
    public var isNativeAudio: Bool { transport is NativeAudioTransport }
    private lazy var audioMeter: AudioActivityObserver = {
        AudioActivityObserver(publish: { [weak self] snapshot in
            Task { @MainActor in self?.audioActivity = snapshot }
        })
    }()

    private lazy var wakeListener: WakeWordListener = {
        let l = WakeWordListener(config: config)
        l.onWake = { [weak self] in self?.handleWakeEvent() }
        l.onAvailabilityChange = { [weak self] a in self?.handleWakeAvailabilityChange(a) }
        return l
    }()

    private var handlers: [UUID: @MainActor (AppMessage) -> Void] = [:]
    private var streamContinuations: [UUID: AsyncStream<AppMessage>.Continuation] = [:]
    private var inputAcceptWaiters: [UUID: CheckedContinuation<InputAccept?, Never>] = [:]
    private var inputAckWaiters: [String: CheckedContinuation<Bool, Never>] = [:]
    private var statsTimer: Timer?
    /// Cumulative outbound-rtp packetsSent at the last 1 Hz tick, so the
    /// per-second delta V6 watches can be computed.
    private var lastAudioPacketsSent: Int = 0

    public init(config: JarvisConfig = .default()) {
        self.config = config
    }

    /// Test-only constructor (internal — @testable import exposes this to
    /// JarvisKitTests, never to a production caller outside the package):
    /// injects a stub transport so §7.5's UICommandOwnershipTests and
    /// §7.4's testConnectRereadsTokenFromKeychain can drive JarvisClient
    /// end-to-end (connect/disconnect/inbound frames/outbound sends)
    /// without a real WebRTC session.
    init(config: JarvisConfig = .default(), stubTransport: RTVITransport) {
        self.config = config
        self.transport = stubTransport
        stubTransport.delegate = self
    }

    deinit {
        statsTimer?.invalidate()
    }

    // MARK: - Message delivery (N6, review F5/F9)

    /// A NEW stream per call (a func, not a var, review F9). Every stream
    /// receives every message from the moment it is created until the
    /// client deinits or the process ends. Bounded
    /// .bufferingNewest(JarvisTuning.messageStreamBuffer).
    public func messageStream() -> AsyncStream<AppMessage> {
        AsyncStream(bufferingPolicy: .bufferingNewest(JarvisTuning.messageStreamBuffer)) { continuation in
            let id = UUID()
            streamContinuations[id] = continuation
            continuation.onTermination = { [weak self] _ in
                Task { @MainActor in self?.streamContinuations.removeValue(forKey: id) }
            }
        }
    }

    /// Deliberately NOT @discardableResult, deviating from plan §5 step
    /// 7's quoted declaration. The returned JarvisSubscription
    /// unsubscribes on deinit (review F5), so a caller that ignores the
    /// result gets a handler that unsubscribes before it ever fires — a
    /// silent no-op that compiled cleanly and shipped as a bug in this
    /// package's own test suite until the first real `swift test` run.
    /// Without the annotation the compiler flags every discarded token
    /// at the call site; no correct caller is affected (a correct caller
    /// must store the token for the handler to live at all).
    public func subscribe(_ handler: @escaping @MainActor (AppMessage) -> Void) -> JarvisSubscription {
        let token = UUID()
        handlers[token] = handler
        return JarvisSubscription(token: token, remove: { [weak self] t in
            Task { @MainActor in self?.handlers.removeValue(forKey: t) }
        })
    }

    private func deliver(_ message: AppMessage) {
        for (_, handler) in handlers { handler(message) }
        for (_, continuation) in streamContinuations { continuation.yield(message) }
    }

    // MARK: - Connect / disconnect

    public func connect() async {
        // (1) re-read the token from the Keychain so a token stored while
        // the app is running attaches on the next connect without a
        // relaunch (review F20).
        config.token = JarvisFlags.authEnabled ? KeychainStore.token(for: config.botURL) : nil
        admin = AdminAPI(config: config)
        costs = CostsAPI(config: config)

        // (2) validate BEFORE any network (review F6/C2).
        do {
            try config.validate()
        } catch let error as JarvisError {
            state = .failed(Self.describe(error))
            return
        } catch {
            state = .failed(error.localizedDescription)
            return
        }

        // (3)
        state = .connecting

        #if os(macOS)
        // BEFORE the transport connects: WebRTC's ADM reads the system
        // default input device at init, so this is the one moment we can
        // steer it. If that mic's rate doesn't match the output's (the
        // AirPods 24 kHz-mic / 48 kHz-speaker split), repoint the default
        // input at the built-in 48 kHz mic so the duplex unit is clean.
        // Restored in disconnect(). AirPods stay the output device.
        // Native-audio plan D8: the band-aid serves the WebRTC path only —
        // the native converter takes any input rate, so the system default
        // input is never touched there.
        audioInputChange = nil
        // 2026-09-17, item 01 / D8 amendment: unconditional on this
        // transport. The kill switch (JARVIS_MATCH_INPUT_RATE) is gone —
        // a mismatch produces unusable audio, so there was never a case for
        // turning the correction off, and a lever that disables a
        // load-bearing fix is the class of thing that silently did nothing
        // until this week's provenance logging caught its sibling.
        if transport is DirectWebRTCTransport {
            audioInputChange = audioInputCoordinator.matchInputToOutputIfNeeded()
        }
        #endif

        // (4)/(5) — the transport itself calls disconnect() first if it
        // already holds a live pc (step 5 lifetime, F3).
        clientLog.notice("""
            connect: transport \(String(describing: type(of: self.transport)), privacy: .public),             bot \(self.config.botURL.absoluteString, privacy: .public),             native \(self.isNativeAudio, privacy: .public),             forceWebRTC \(JarvisFlags.forceWebRTC, privacy: .public),             token \(self.config.token == nil ? "absent" : "present", privacy: .public)
            """)
        do {
            try await transport.connect(config: config)
            clientLog.notice("connect: transport reported connected")
            state = .connected
            audioMeter.beginSession(source: transport as? AudioLevelSource,
                                    microphoneEnabled: micEnabled)
            startStatsTimer()
            updateWakeListenerRunState()
            #if os(macOS)
            // Playout was just initialised against the CURRENT default
            // output device — a fresh baseline for the monitor. WebRTC
            // only (native-audio plan D3/D8): AVAudioEngine follows the
            // default output itself, so the native path needs no notice
            // and no reconnect.
            audioOutputChange = nil
            if transport is DirectWebRTCTransport { audioOutputMonitor.start() }
            #endif
            // N10 runtime availability probe — enables the wake toggle
            // when the sidecar is reachable. Gated to the real transports:
            // under a stub transport (tests) the probe's real socket to
            // 127.0.0.1:7862 would race the tests' manual
            // wakeWordAvailable setup.
            if transport is DirectWebRTCTransport || transport is NativeAudioTransport {
                Task { await wakeListener.probeAvailability() }
            }
        } catch JarvisError.unauthorized {
            state = .failed("Token required")   // N13 — no retry
        } catch let error as JarvisError {
            clientLog.error("connect failed (JarvisError): \(Self.describe(error), privacy: .public)")
            state = .failed(Self.describe(error))
        } catch {
            clientLog.error("""
                connect failed: \(String(describing: error), privacy: .public)                 — \(error.localizedDescription, privacy: .public)
                """)
            state = .failed(error.localizedDescription)
        }
    }

    public func disconnect() async {
        lastSessionAudioLatency = audioMeter.latency()
        audioMeter.endSession()
        audioActivity = nil
        #if os(macOS)
        audioOutputMonitor.stop()
        // Give the user's original mic back — the rate-match is only for the
        // duration of a session (AudioInputCoordinator).
        audioInputCoordinator.restore()
        #endif
        await wakeListener.stop()
        await transport.disconnect()
        state = .offline
        botIsSpeaking = false
        consoleSessionID = nil
        consoleGeneration = nil
        consoleInputProfile = nil
        resolveInputWaiters()
        stopStatsTimer()
        lastAudioPacketsSent = 0   // fresh session, fresh cumulative counters
        // transcript, voices, currentVoice are NOT cleared (self-audit
        // item 2) — a fresh voice/catalog on the next connect replaces
        // `voices` wholesale, matching VoicePicker.tsx:20-22.
    }

    /// disconnect() then connect() — the ONE way this build can move the
    /// bot's voice to a new default output device (AudioOutputMonitor),
    /// and what the app's "Reconnect" notice action calls. A new peer
    /// connection is a new bot session; callers own that trade.
    public func reconnect() async {
        await disconnect()
        await connect()
    }

    #if os(macOS)
    private func handleAudioOutputChange(from previous: AudioOutputMonitor.Device?,
                                         to next: AudioOutputMonitor.Device?) {
        guard case .connected = state else { return }
        let change = AudioOutputChange(from: previous?.name, to: next?.name ?? "no output device")
        audioOutputChange = change
        clientLog.notice("audio_output_changed from=\(previous?.name ?? "none", privacy: .public) to=\(next?.name ?? "none", privacy: .public) follow=\(JarvisFlags.followAudioOutput)")
        if JarvisFlags.followAudioOutput {
            Task { await self.reconnect() }
        }
    }
    #endif

    // MARK: - Outbound

    /// C7.5: p50/p95 of buffer-host-time to presentation over the last
    /// 60 s. The debug menu writes it to the acceptance record.
    public func audioMeterLatency() -> AudioMeterLatency { audioMeter.latency() }

    public func send(_ message: ClientMessage) {
        guard let data = try? message.jsonData() else { return }
        try? transport.send(data)
    }

    /// Wait for the server's input/accept before sending any content bytes.
    /// The continuation is session-scoped and is resolved on disconnect so a
    /// failed transport cannot strand a task or retain staged data forever.
    public func waitForInputAccept(batchID: UUID) async -> InputAccept? {
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: nil) }
                else { inputAcceptWaiters[batchID] = continuation }
            }
        }, onCancel: { [weak self] in
            Task { @MainActor in self?.cancelInputAcceptWaiter(batchID: batchID) }
        })
    }

    /// Wait for the single outstanding chunk acknowledgement required by the
    /// transfer contract. The caller owns the timeout and cancellation policy.
    public func waitForInputAck(transferID: UUID, attachmentID: UUID,
                                sequence: Int) async -> Bool {
        let key = inputAckKey(transferID: transferID, attachmentID: attachmentID,
                              sequence: sequence)
        return await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                if Task.isCancelled { continuation.resume(returning: false) }
                else { inputAckWaiters[key] = continuation }
            }
        }, onCancel: { [weak self] in
            Task { @MainActor in self?.cancelInputAckWaiter(key: key) }
        })
    }

    private func inputAckKey(transferID: UUID, attachmentID: UUID, sequence: Int) -> String {
        "\(transferID.uuidString.lowercased()):\(attachmentID.uuidString.lowercased()):\(sequence)"
    }

    private func resolveInputWaiters() {
        inputAcceptWaiters.values.forEach { $0.resume(returning: nil) }
        inputAcceptWaiters.removeAll()
        inputAckWaiters.values.forEach { $0.resume(returning: false) }
        inputAckWaiters.removeAll()
    }

    private func cancelInputAcceptWaiter(batchID: UUID) {
        inputAcceptWaiters.removeValue(forKey: batchID)?.resume(returning: nil)
    }

    private func cancelInputAckWaiter(key: String) {
        inputAckWaiters.removeValue(forKey: key)?.resume(returning: false)
    }

    /// AppMessageRouter records the server's bounded console identity here;
    /// views use it only to construct versioned input messages.
    public func setConsoleIdentity(sessionID: UUID, generation: UUID,
                                   inputProfile: ConsoleInputProfile? = nil) {
        consoleSessionID = sessionID
        consoleGeneration = generation
        consoleInputProfile = inputProfile
    }

    public func setMicEnabled(_ on: Bool) {
        micEnabled = on
        transport.setMicEnabled(on)
        audioMeter.setMicrophoneEnabled(on)
        debugAudioStats.micTrackEnabled = on
        updateWakeListenerRunState()
    }

    public func setWakeWord(_ on: Bool) async {
        wakeWordOn = on
        if on {
            await wakeListener.start()
        } else {
            await wakeListener.stop()
        }
        updateWakeListenerRunState()
    }

    // MARK: - Mic-contention rule (review F13)

    /// The wake listener runs only while state == .connected AND
    /// micEnabled == false (N10 rule 1) — starting it stops nothing;
    /// stopping the session stops it. Called on every state change that
    /// could flip that condition.
    private func updateWakeListenerRunState() {
        let shouldRun = wakeWordOn && state == .connected && !micEnabled
        #if os(macOS)
        // Native path (§3.5, measured 2026-09-13): the listener must NOT
        // open its own AVAudioEngine on top of the transport's. A second
        // engine on the same input device receives silence on the
        // built-in mic and costs the transport's engine its echo
        // cancellation (38.4 dB of reduction becomes 0.7 dB). Wake audio
        // comes from the transport's processed tap instead — which is
        // also strictly better input for the detector, since it is
        // echo-cancelled (N10 rule 4's pause during bot speech stays as
        // it is; it is no longer the only thing keeping the bot's own
        // voice out of the detector).
        if let native = transport as? NativeAudioTransport {
            if shouldRun {
                native.setCaptureMonitor { [weak self] pcm in self?.feedWakeAudio(pcm) }
                Task { await wakeListener.start(source: .external) }
            } else {
                native.setCaptureMonitor(nil)
                Task { await wakeListener.stop() }
            }
            return
        }
        #endif
        if shouldRun {
            Task { await wakeListener.start() }
        } else {
            Task { await wakeListener.stop() }
        }
    }

    #if os(macOS)
    /// The transport's capture monitor fires on the audio engine's thread;
    /// this is the hop onto the main actor, the same boundary shape as the
    /// RTVITransportDelegate callbacks at the bottom of this file.
    nonisolated func feedWakeAudio(_ pcm: Data) {
        Task { @MainActor in self.wakeListener.feed(pcm) }
    }
    #endif

    private func handleWakeEvent() {
        // wakeWord.ts:118 / MicControls.tsx:77-80 — a wake event unmutes.
        setMicEnabled(true)
        wakePulse += 1
    }

    private func handleWakeAvailabilityChange(_ a: WakeAvailability) {
        switch a {
        case .available: wakeWordAvailable = true
        case .unavailable, .unknown: wakeWordAvailable = false
        }
    }

    // MARK: - .ui handling (N11 — the three JarvisKit-owned actions)

    private func handleUICommand(_ cmd: UICommand) {
        switch cmd.action {
        case "mic_mute":
            if micEnabled {
                setMicEnabled(false)
            }
            // already muted or not connected: nothing, sends nothing
            // (MicControls.tsx:100-104 — a stale command is harmless).
        case "wake_on":
            if !wakeWordAvailable {
                send(ClientMessage.noop("The wake word listener isn't available on this machine.") ?? .uiNoop(reason: ""))
            } else if wakeWordOn {
                send(ClientMessage.noop("The wake word is already on.") ?? .uiNoop(reason: ""))
            } else {
                Task { await setWakeWord(true) }
            }
        case "wake_off":
            if !wakeWordOn {
                send(ClientMessage.noop("The wake word is already off.") ?? .uiNoop(reason: ""))
            } else {
                Task { await setWakeWord(false) }
            }
        default:
            break   // forwarded via deliver(_:) — everything else is T1.3's (C5)
        }
    }

    // MARK: - Inbound frame handling

    private func handleReceivedFrame(_ data: Data) {
        // try? flattens Optional<AppMessage?> from a throwing function
        // that already returns AppMessage? (SE-0230) — a decode failure
        // and a signalling/type-less frame (decode() returning nil) are
        // both correctly ignored here.
        guard let message = try? AppMessage.decode(frame: data) else { return }

        switch message {
        case .inputAccept(let accept):
            if let batchID = accept.batchID,
               let waiter = inputAcceptWaiters.removeValue(forKey: batchID) {
                waiter.resume(returning: accept)
            }
        case .inputAck(let ack):
            let key = inputAckKey(transferID: ack.transferID,
                                  attachmentID: ack.attachmentID,
                                  sequence: ack.sequence)
            if let waiter = inputAckWaiters.removeValue(forKey: key) {
                waiter.resume(returning: true)
            }
        case .inputReady:
            // Readiness is delivered to the normal message stream for the
            // host/router; byte senders have already completed their commit.
            break
        case .voiceCatalog(let catalog):
            voices = catalog.voices
            if let current = catalog.current { currentVoice = current }
        case .voiceCurrent(let voice):
            currentVoice = voice
        case .ui(let cmd):
            handleUICommand(cmd)
        case .unknown(let type, let raw):
            // botIsSpeaking from RTVI observer frames — VERIFIED live
            // 2026-08-30: this bot emits standard RTVI observer messages
            // (user-started-speaking, bot-llm-started, bot-interrupted, …
            // seen in MortimerHost's message log), contradicting CORE
            // correction 6. The plan's audio-renderer mechanism (F12)
            // does not exist in stasel/WebRTC M120 (see AudioSession.swift),
            // so these frames are the ONE available speaking signal — and
            // a better one: the server's own TTS lifecycle, not an RMS
            // guess. Falls through harmlessly on a bot that stops
            // emitting them (botIsSpeaking then stays false, the
            // documented degradation).
            switch type {
            case "bot-started-speaking":
                setBotSpeaking(true)
            case "bot-stopped-speaking", "bot-interrupted":
                setBotSpeaking(false)
                if type == "bot-interrupted" { finalizePendingAssistantEntry() }
            // The transcript, fed from the SAME live-verified RTVI
            // observer stream (2026-08-30's discovery superseding CORE
            // correction 6): user-transcription final frames and the
            // bot-llm-text token stream are what client-js's
            // usePipecatConversation aggregates in the web console, so
            // aggregating them here gives the Log tab its spoken bubbles
            // and the stage its live captions with NO backend change
            // (R-A1 stays untouched — this is a client-side consumer of
            // frames the bot already emits).
            case "user-transcription":
                if let d = raw["data"]?.objectValue,
                   d["final"]?.boolValue == true,
                   let text = d["text"]?.stringValue,
                   !text.trimmingCharacters(in: .whitespaces).isEmpty {
                    appendTranscript(role: "user", text: text)
                }
            case "bot-llm-started":
                botIsThinking = true
                beginAssistantEntry()
            case "bot-llm-text":
                if let d = raw["data"]?.objectValue,
                   let chunk = d["text"]?.stringValue {
                    appendToAssistantEntry(chunk)
                }
            case "bot-llm-stopped":
                botIsThinking = false
                finalizePendingAssistantEntry()
            default:
                break
            }
        default:
            break
        }

        deliver(message)
    }

    private func setBotSpeaking(_ speaking: Bool) {
        guard botIsSpeaking != speaking else { return }
        botIsSpeaking = speaking
        wakeListener.setPaused(speaking)   // N10 rule 4, re-enabled by this signal
    }

    // MARK: - Transcript aggregation (client-side, from RTVI observer frames)

    /// Index into `transcript` of the assistant entry currently being
    /// streamed token-by-token (bot-llm-text), nil when none is open.
    private var pendingAssistantEntryId: String?

    private func appendTranscript(role: String, text: String) {
        transcript.append(ConversationEntry(
            id: UUID().uuidString, role: role,
            createdAt: Date().timeIntervalSince1970, text: text
        ))
        capTranscript()
    }

    private func beginAssistantEntry() {
        // A new inference turn — close out any orphaned pending entry
        // (an interruption whose bot-llm-stopped never arrived).
        finalizePendingAssistantEntry()
        let entry = ConversationEntry(
            id: UUID().uuidString, role: "assistant",
            createdAt: Date().timeIntervalSince1970, text: ""
        )
        pendingAssistantEntryId = entry.id
        transcript.append(entry)
        capTranscript()
    }

    private func appendToAssistantEntry(_ chunk: String) {
        guard let id = pendingAssistantEntryId,
              let index = transcript.lastIndex(where: { $0.id == id }) else { return }
        let old = transcript[index]
        transcript[index] = ConversationEntry(
            id: old.id, role: old.role, createdAt: old.createdAt,
            text: old.text + chunk
        )
    }

    private func finalizePendingAssistantEntry() {
        // An entry that never received a token is removed — an empty
        // bubble tells the user nothing.
        if let id = pendingAssistantEntryId,
           let index = transcript.lastIndex(where: { $0.id == id }),
           transcript[index].text.trimmingCharacters(in: .whitespaces).isEmpty {
            transcript.remove(at: index)
        }
        pendingAssistantEntryId = nil
    }

    private func capTranscript() {
        if transcript.count > JarvisTuning.maxConversationEntries {
            transcript.removeFirst(transcript.count - JarvisTuning.maxConversationEntries)
        }
    }

    // MARK: - Stats (§5 step 9)

    private func startStatsTimer() {
        stopStatsTimer()
        let timer = Timer(timeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tickStats() }
        }
        RunLoop.main.add(timer, forMode: .common)
        statsTimer = timer
    }

    private func stopStatsTimer() {
        statsTimer?.invalidate()
        statsTimer = nil
    }

    /// §5 step 9 / §8 V6: the counters come from the peer connection's
    /// own outbound-rtp audio statistics — sentPacketsLastSecond > 0
    /// continuously through the bot's entire reply is the proof that
    /// N9's never-withhold-audio obligation holds.
    private func tickStats() {
        if let direct = transport as? DirectWebRTCTransport {
            direct.fetchOutboundAudioStats { [weak self] stats in
                Task { @MainActor in
                    guard let self, let stats else { return }
                    self.applyAudioStats(stats, lastKeepAlive: direct.lastKeepAliveDate)
                }
            }
        } else if let native = transport as? NativeAudioTransport {
            // Native path: the frames this client put on the socket, and
            // the last answered keep-alive ping.
            applyAudioStats(native.outboundAudioStats, lastKeepAlive: native.lastKeepAliveDate)
        }
    }

    private func applyAudioStats(_ stats: OutboundAudioStats, lastKeepAlive: Date?) {
        debugAudioStats.sentPacketsLastSecond = max(0, stats.packetsSent - lastAudioPacketsSent)
        lastAudioPacketsSent = stats.packetsSent
        debugAudioStats.sentBytes = stats.bytesSent
        debugAudioStats.lastKeepAliveAt = lastKeepAlive
    }

    private static func describe(_ error: JarvisError) -> String {
        switch error {
        case .unauthorized: return "Token required"
        case .forbidden: return "Forbidden"
        case .http(let status, let body): return "HTTP \(status): \(body)"
        case .transport(let message): return message
        case .decoding(let message): return "Decoding error: \(message)"
        case .insecureHost(let host): return "Refusing insecure host: \(host)"
        }
    }
}

// MARK: - RTVITransportDelegate (hop to @MainActor at this boundary, review F5)

extension JarvisClient: RTVITransportDelegate {
    nonisolated func transportDidConnect() {
        Task { @MainActor in
            self.debugAudioStats.lastKeepAliveAt = Date()
        }
    }

    nonisolated func transportDidDisconnect(error: Error?) {
        Task { @MainActor in
            if let error {
                self.state = .failed((error as? JarvisError).map(Self.describe) ?? error.localizedDescription)
            } else {
                self.state = .offline
            }
            self.botIsSpeaking = false
            self.stopStatsTimer()
            self.lastSessionAudioLatency = self.audioMeter.latency()
            self.audioMeter.endSession()
            self.audioActivity = nil
            self.resolveInputWaiters()
            await self.wakeListener.stop()
        }
    }

    nonisolated func transport(didReceiveFrame data: Data) {
        Task { @MainActor in self.handleReceivedFrame(data) }
    }

    nonisolated func transport(botIsSpeaking: Bool) {
        Task { @MainActor in
            self.setBotSpeaking(botIsSpeaking)   // N10 rule 4 via one setter
        }
    }
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
