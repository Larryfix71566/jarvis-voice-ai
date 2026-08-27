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
    // internal(set), not private(set): §7.5's UICommandOwnershipTests set
    // up preconditions (e.g. "wakeWordAvailable = false") by direct field
    // assignment via @testable import, which sees `internal` but not
    // `private` across files.
    @Published public internal(set) var micEnabled: Bool = true
    @Published public internal(set) var wakeWordOn: Bool = false
    @Published public internal(set) var wakeWordAvailable: Bool = false
    @Published public private(set) var transcript: [ConversationEntry] = []   // see correction 6
    @Published public private(set) var voices: [Voice] = []
    @Published public private(set) var currentVoice: String = ""

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

    public private(set) var config: JarvisConfig   // re-read on connect(), F20
    // AdminAPI is a struct holding a JarvisConfig (N14, §5 step 4). The F20
    // token re-read in connect() ALSO reassigns `admin = AdminAPI(config: config)`
    // so an admin request made after a token is stored carries that token —
    // otherwise the lazy snapshot would keep the pre-mint (nil) token.
    public private(set) lazy var admin: AdminAPI = AdminAPI(config: config)

    // internal (not private): §7.5's UICommandOwnershipTests and §7.4's
    // testConnectRereadsTokenFromKeychain inject a stub transport via the
    // test-only initializer at the bottom of this file. @testable import
    // exposes `internal`, never `private`, across files — hence internal.
    lazy var transport: RTVITransport = {
        let t = DirectWebRTCTransport()
        t.delegate = self
        return t
    }()
    private lazy var wakeListener: WakeWordListener = {
        let l = WakeWordListener(config: config)
        l.onWake = { [weak self] in self?.handleWakeEvent() }
        l.onAvailabilityChange = { [weak self] a in self?.handleWakeAvailabilityChange(a) }
        return l
    }()

    private var handlers: [UUID: @MainActor (AppMessage) -> Void] = [:]
    private var streamContinuations: [UUID: AsyncStream<AppMessage>.Continuation] = [:]
    private var statsTimer: Timer?

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

    @discardableResult
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

        // (4)/(5) — the transport itself calls disconnect() first if it
        // already holds a live pc (step 5 lifetime, F3).
        do {
            try await transport.connect(config: config)
            state = .connected
            startStatsTimer()
            updateWakeListenerRunState()
        } catch JarvisError.unauthorized {
            state = .failed("Token required")   // N13 — no retry
        } catch let error as JarvisError {
            state = .failed(Self.describe(error))
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    public func disconnect() async {
        await wakeListener.stop()
        await transport.disconnect()
        state = .offline
        botIsSpeaking = false
        stopStatsTimer()
        // transcript, voices, currentVoice are NOT cleared (self-audit
        // item 2) — a fresh voice/catalog on the next connect replaces
        // `voices` wholesale, matching VoicePicker.tsx:20-22.
    }

    // MARK: - Outbound

    public func send(_ message: ClientMessage) {
        guard let data = try? message.jsonData() else { return }
        try? transport.send(data)
    }

    public func setMicEnabled(_ on: Bool) {
        micEnabled = on
        transport.setMicEnabled(on)
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
        if shouldRun {
            Task { await wakeListener.start() }
        } else {
            Task { await wakeListener.stop() }
        }
    }

    private func handleWakeEvent() {
        // wakeWord.ts:118 / MicControls.tsx:77-80 — a wake event unmutes.
        setMicEnabled(true)
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
        case .voiceCatalog(let catalog):
            voices = catalog.voices
            if let current = catalog.current { currentVoice = current }
        case .voiceCurrent(let voice):
            currentVoice = voice
        case .ui(let cmd):
            handleUICommand(cmd)
        default:
            break
        }

        deliver(message)
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

    private func tickStats() {
        guard let direct = transport as? DirectWebRTCTransport else { return }
        let total = direct.sentBytesTotal
        debugAudioStats.sentPacketsLastSecond = max(0, total - debugAudioStats.sentBytes)
        debugAudioStats.sentBytes = total
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
            await self.wakeListener.stop()
        }
    }

    nonisolated func transport(didReceiveFrame data: Data) {
        Task { @MainActor in self.handleReceivedFrame(data) }
    }

    nonisolated func transport(botIsSpeaking: Bool) {
        Task { @MainActor in
            self.botIsSpeaking = botIsSpeaking
            self.wakeListener.setPaused(botIsSpeaking)   // N10 rule 4
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
