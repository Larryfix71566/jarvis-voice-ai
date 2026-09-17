import Foundation
import os

private let configLog = Logger(subsystem: "com.mortimer.jarviskit", category: "config")

/// K5: one base URL per service, resolved in ONE place. Also the home for
/// K1's client-side bearer token.
public struct JarvisConfig: Sendable, Equatable {
    public var botURL: URL        // default http://127.0.0.1:7860   (JARVIS_BOT_URL)
    public var adminURL: URL      // default http://127.0.0.1:7861   (JARVIS_ADMIN_URL)
    public var wakeWordURL: URL   // default ws://127.0.0.1:7862/ws  (JARVIS_WAKEWORD_URL)
    // MORTIMER_OPTIMIZATION_PLAN.md Phase 0 step 9 — the costs service
    // (jarvis/costs_api.py, its own Procfile entry, NOT under the admin
    // sidecar's /api/* prefix). Same one-base-URL-per-service rule as
    // the three above.
    public var costsURL: URL      // default http://127.0.0.1:8487   (JARVIS_COSTS_URL)
    public var token: String?     // nil until T2 mints one

    // costsURL defaults so every existing direct-construction call site
    // (tests, previews) keeps compiling without an update — Phase 0 step
    // 9 added this field; only .default() needs to actually vary it.
    public init(botURL: URL, adminURL: URL, wakeWordURL: URL,
                costsURL: URL = URL(string: "http://127.0.0.1:8487")!,
                token: String?) {
        self.botURL = botURL
        self.adminURL = adminURL
        self.wakeWordURL = wakeWordURL
        self.costsURL = costsURL
        self.token = token
    }

    /// K5: one base URL per service, resolved in ONE place.
    /// Order: process environment -> UserDefaults -> compiled default.
    public static func `default`() -> JarvisConfig {
        // Which source won is worth a line in the log: a URL (or a flag —
        // JarvisFlags reads UserDefaults the same way) that silently falls
        // through to the compiled default looks exactly like a bug in the
        // thing it points at. §8, 2026-09-13: an hour went into a client
        // that was dialing the fallback port.
        func url(_ name: String, _ fallback: String) -> URL {
            if let s = ProcessInfo.processInfo.environment[name], let u = URL(string: s) {
                configLog.notice("\(name, privacy: .public) from environment: \(s, privacy: .public)")
                return u
            }
            if let s = UserDefaults.standard.string(forKey: name), let u = URL(string: s) {
                configLog.notice("\(name, privacy: .public) from UserDefaults: \(s, privacy: .public)")
                return u
            }
            configLog.notice("""
                \(name, privacy: .public) unset in environment and UserDefaults                 (domain \(Bundle.main.bundleIdentifier ?? "none", privacy: .public)) —                 using the compiled default \(fallback, privacy: .public)
                """)
            return URL(string: fallback)!
        }
        let bot = url("JARVIS_BOT_URL", "http://127.0.0.1:7860")
        // The rollback lever's resolution, every time config is built. §8's
        // rollback proof failed twice over this flag -- once because the
        // code ignored the environment, and once for a reason the log could
        // not distinguish, because nothing recorded WHERE the value came
        // from. The most important flag in the app should not be the one you
        // have to infer.
        let rawForce = ProcessInfo.processInfo.environment["JARVIS_FORCE_WEBRTC"] ?? "absent"
        let defForce = UserDefaults.standard.object(forKey: "JARVIS_FORCE_WEBRTC") == nil
            ? "absent" : String(UserDefaults.standard.bool(forKey: "JARVIS_FORCE_WEBRTC"))
        configLog.notice("JARVIS_FORCE_WEBRTC: environment \(rawForce, privacy: .public), UserDefaults \(defForce, privacy: .public) -> resolved \(JarvisFlags.forceWebRTC, privacy: .public)")
        return JarvisConfig(
            botURL: bot,
            adminURL: url("JARVIS_ADMIN_URL", "http://127.0.0.1:7861"),
            wakeWordURL: url("JARVIS_WAKEWORD_URL", "ws://127.0.0.1:7862/ws"),
            costsURL: url("JARVIS_COSTS_URL", "http://127.0.0.1:8487"),
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
        for u in [botURL, adminURL, costsURL] where !loopback(u) {
            if token == nil { throw JarvisError.insecureHost(u.absoluteString) }
            if !JarvisFlags.authEnabled { throw JarvisError.insecureHost(u.absoluteString) }
        }
    }
}

/// N16: kill switches. There is no `.env` on a Mac app bundle, so the
/// client analogue of an env kill switch is UserDefaults
/// (`defaults write <bundle-id> JARVIS_WAKEWORD_ENABLED -bool false`),
/// read through this one accessor. All three default to enabled — absent
/// key == on, matching the repo's "unset means on" rule.
public enum JarvisFlags {
    static func on(_ key: String) -> Bool {
        UserDefaults.standard.object(forKey: key) == nil
            ? true : UserDefaults.standard.bool(forKey: key)
    }
    public static var wakeWordEnabled: Bool { on("JARVIS_WAKEWORD_ENABLED") }
    /// K1 extension (review F19). false does two things, not one: no
    /// Authorization header is attached, AND JarvisConfig.validate()
    /// additionally refuses any non-loopback host — turning client auth
    /// off must never fail open onto a remote host in the clear.
    public static var authEnabled: Bool { on("JARVIS_CLIENT_AUTH_ENABLED") }
    public static var glassEnabled: Bool { on("JARVIS_GLASS_ENABLED") }
    /// D10 rollback: `JARVIS_AUDIO_CAPTURE=tap` returns capture to the
    /// input tap, whose 100 ms buffers were the whole reason for the sink
    /// node. Anything else (or unset) uses the sink node.
    public static var captureUsesSinkNode: Bool {
        ProcessInfo.processInfo.environment["JARVIS_AUDIO_CAPTURE"]?.lowercased() != "tap"
            && UserDefaults.standard.string(forKey: "JARVIS_AUDIO_CAPTURE")?.lowercased() != "tap"
    }
    /// Closure C7.4 runtime disable path: `JARVIS_AUDIO_METER=off` in the
    /// environment, or `defaults write com.mortimer.host JARVIS_AUDIO_METER
    /// -bool false`, stops the observer publishing. The status stays
    /// truthful — the wave reports the level as unavailable rather than
    /// showing a flat line as if it were silence.
    public static var audioMeterEnabled: Bool {
        if let raw = ProcessInfo.processInfo.environment["JARVIS_AUDIO_METER"]?.lowercased() {
            return !["off", "false", "0", "no"].contains(raw)
        }
        return on("JARVIS_AUDIO_METER")
    }
    /// 2026-09-05 — auto-reconnect the session when the default output
    /// device changes (AirPods), so the bot's voice follows it. OPT-IN,
    /// unlike the three above (absent key == off): the plain WebRTC build
    /// can only follow a device by opening a new peer connection, and a
    /// new connection is a new bot session — the conversation context
    /// resets. Off, the app shows a notice with a Reconnect action instead
    /// (`defaults write <bundle-id> JARVIS_FOLLOW_AUDIO_OUTPUT -bool true`).
    public static var followAudioOutput: Bool {
        UserDefaults.standard.bool(forKey: "JARVIS_FOLLOW_AUDIO_OUTPUT")
    }
    /// MORTIMER_NATIVE_AUDIO_TRANSPORT_PLAN.md D1/§9 — the rollback lever.
    /// OPT-IN (absent == off): on, a loopback bot uses
    /// `DirectWebRTCTransport` exactly as before the native path existed,
    /// and the WebRTC-only device band-aids run again with it. Either
    /// `JARVIS_FORCE_WEBRTC=true` in the environment or `defaults write
    /// com.mortimer.host JARVIS_FORCE_WEBRTC -bool true`.
    ///
    /// The environment half was missing until 2026-09-15 and §8's rollback
    /// proof is what found it: this read UserDefaults only, so setting the
    /// variable §9 documents left the session on the native path and logged
    /// `forceWebRTC false` — a rollback lever that silently does nothing is
    /// worse than one that errors. Environment first, like
    /// `captureUsesSinkNode` and `audioMeterEnabled`; an explicit false in
    /// the environment is off rather than merely present.
    public static var forceWebRTC: Bool {
        if let raw = ProcessInfo.processInfo.environment["JARVIS_FORCE_WEBRTC"]?.lowercased() {
            return ["1", "true", "yes", "on"].contains(raw)
        }
        return UserDefaults.standard.bool(forKey: "JARVIS_FORCE_WEBRTC")
    }
}

/// §6 — one home for every numeric constant in the package. Nothing else
/// in JarvisKit may contain a bare number that means a duration, a size,
/// or a threshold. All compile-time (review F14) — the only
/// UserDefaults-overridable client state is the three URLs and three
/// flags above.
public enum JarvisTuning {
    /// Must be well under the server's 3 s staleness window
    /// (connection.py:672); 1 s gives two missed pings of slack.
    public static let keepAliveInterval: TimeInterval = 1.0
    /// Watchdog threshold (§5 step 5.11, review F4) — inside the server's
    /// 3 s window, so the client fails the session BEFORE the server
    /// silences the bot's audio.
    public static let keepAliveStallSeconds: TimeInterval = 2.5
    /// Native path only (§8, 2026-09-13). Two things the WebRTC constants
    /// above cannot express, because on that path `/api/offer` answers only
    /// after the server has built the session, whereas here the WebSocket
    /// handshake completes first and `run_session` then loads Smart Turn and
    /// Silero, prunes run logs, sweeps memory and connects Deepgram and
    /// ElevenLabs with the event loop blocked — measured at 5.4 s on this
    /// Mac, and longer on a cold model cache. So:
    ///
    /// - the stall watchdog is not armed until the server shows a sign of
    ///   life (a pong or any inbound frame); `nativeReadyDeadline` bounds
    ///   that wait instead, generously;
    /// - once established, `nativeKeepAliveStallSeconds` is the threshold.
    ///   It is NOT the 2.5 s above: that number exists to beat SmallWebRTC's
    ///   3 s staleness window (connection.py:672), which does not exist on
    ///   this transport, and the server's own per-turn model inference can
    ///   block its loop for longer than 2.5 s.
    public static let nativeReadyDeadline: TimeInterval = 30.0
    public static let nativeKeepAliveStallSeconds: TimeInterval = 6.0
    /// Mirrors DATA_CHANNEL_TIMEOUT_SECS (connection.py:77); if `.open` is
    /// not reached by this deadline the client disconnects loudly at the
    /// same moment the server discards queued messages.
    public static let dataChannelOpenDeadline: TimeInterval = 10.0
    /// Batches the ICE PATCH without delaying the first candidates.
    public static let iceBatchSize: Int = 5
    /// Upper bound on how long a candidate waits for company.
    public static let iceBatchDelay: TimeInterval = 0.25
    /// Bounded outbound frame queue, oldest dropped — same discipline as
    /// MAX_AGENT_RUNS / MAX_DISPLAY_RESULTS.
    public static let outboundQueueMax: Int = 32
    /// messageStream() buffering (.bufferingNewest, review F9) — a stream
    /// nobody drains drops oldest, not leaks.
    public static let messageStreamBuffer: Int = 200
    /// Above the noise floor of a silent Opus stream (RMS, §5 step 8).
    /// Consumed by SpeakingGate, which is currently undriven — see the
    /// botIsSpeaking note in AudioSession.swift.
    public static let speakingLevelThreshold: Double = 0.01
    /// Longer than inter-word gaps, shorter than a turn boundary.
    public static let speakingReleaseMS: Int = 400
    /// NOT tunable in effect — server.py:37-38 fixes 1280 samples x 2
    /// bytes. Declared as a constant so the arithmetic has one home;
    /// changing it breaks the sidecar.
    public static let wakeFrameBytes: Int = 2560
    /// server.py:5, wakeWord.ts:131
    public static let wakeSampleRate: Double = 16000
    /// Exact parity with wakeWord.ts:57-82.
    public static let chimeTones: [(frequency: Double, startOffset: TimeInterval)] = [
        (880, 0.0), (1320, 0.12),
    ]
    public static let chimeGain: Double = 0.18
    public static let chimeDecayFloor: Double = 0.001
    public static let chimeDecayDuration: TimeInterval = 0.25
    public static let chimeTeardown: TimeInterval = 0.8
    /// conversationFeed.ts:36
    public static let maxConversationEntries: Int = 200
    /// Host debug list; same bounded rule.
    public static let maxHostMessages: Int = 200
}
