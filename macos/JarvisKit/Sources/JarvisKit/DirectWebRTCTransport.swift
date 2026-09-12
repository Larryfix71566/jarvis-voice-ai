import Foundation
import WebRTC
import os

private let transportLog = Logger(subsystem: "com.mortimer.jarviskit", category: "transport")

/// BRANCH B (§5 step 5) — signalling + direct WebRTC over stasel/WebRTC.
/// Written out in full because it is the part a weaker model would get
/// wrong (§0's own words). Every numbered step below corresponds 1:1 to
/// the plan's §5 step 5 list.
///
/// Object lifetime (review F3) is the load-bearing rule: a closed
/// RTCPeerConnection cannot be reopened, neither can a closed
/// RTCDataChannel. So:
///   - process-lifetime statics: RTCInitializeSSL() and the
///     RTCPeerConnectionFactory. Built once, never torn down.
///   - per-session state (pc, dataChannel, micTrack, the ICE buffer,
///     storedPCID, the keep-alive timer, the watchdog, the open-deadline
///     timer): built fresh inside every connect() and released in every
///     disconnect(). connect() called while pc != nil calls disconnect()
///     first.
///
/// All mutable per-session state is confined to `queue`, a dedicated
/// serial DispatchQueue — this type is a reference type that serialises
/// its own state rather than being Sendable (review F5); delegate
/// callbacks that must reach @MainActor hop there explicitly at the
/// JarvisClient boundary (the delegate protocol itself declares
/// @MainActor-agnostic methods; JarvisClient's conformance is what hops).
final class DirectWebRTCTransport: NSObject, RTVITransport {
    weak var delegate: RTVITransportDelegate?

    // Process-lifetime statics.
    private static let sslBootstrap: Bool = {
        RTCInitializeSSL()
        return true
    }()
    private static let factory: RTCPeerConnectionFactory = {
        _ = DirectWebRTCTransport.sslBootstrap
        return RTCPeerConnectionFactory(
            encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory()
        )
    }()

    // Per-session state. Confined to `queue`.
    private let queue = DispatchQueue(label: "com.mortimer.jarviskit.webrtc")
    private var pc: RTCPeerConnection?
    private var dataChannel: RTCDataChannel?
    private var micTrack: RTCAudioTrack?
    private var audioSource: RTCAudioSource?
    private var storedPCID: String?
    private var config: JarvisConfig?

    // ICE batching (step 10).
    private var iceBuffer: [RTCIceCandidate] = []
    private var iceBatchWorkItem: DispatchWorkItem?

    // Data-channel open deadline (step 11).
    private var openDeadlineTimer: DispatchSourceTimer?

    // Keep-alive + watchdog (step 11).
    private var keepAliveTimer: DispatchSourceTimer?
    private var watchdogTimer: DispatchSourceTimer?
    private var lastKeepAliveSentAt: Date = .distantPast

    // Outbound queue while the channel is not yet open (step 13).
    private var outboundQueue: [Data] = []

    // botIsSpeaking (step 8): unavailable on this dependency — see the
    // extension at the bottom of this file. One log line per session.
    private var loggedSpeakingUnavailable = false

    // debugAudioStats (§5 step 9): real numbers come from the peer
    // connection's v2 statistics API — see fetchOutboundAudioStats at
    // the bottom of this file. (An earlier draft counted data-channel
    // bytes here, which reads 0 forever during a voice session and
    // proves nothing about V6.)

    // MARK: - RTVITransport

    func connect(config: JarvisConfig) async throws {
        // A live session must be torn down before a new one is built —
        // this is what makes a second Connect click work (review F3).
        if pc != nil { await disconnect() }

        self.config = config

        // 1. RTCInitializeSSL() — via the static above.
        _ = DirectWebRTCTransport.sslBootstrap

        // 3. RTCConfiguration.
        let rtcConfig = RTCConfiguration()
        rtcConfig.iceServers = []   // loopback (and, later, Tailscale) — host candidates suffice, no TURN
        rtcConfig.sdpSemantics = .unifiedPlan
        rtcConfig.continualGatheringPolicy = .gatherContinually

        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)

        // 4. Build the peer connection against the shared factory.
        guard let newPC = DirectWebRTCTransport.factory.peerConnection(
            with: rtcConfig, constraints: constraints, delegate: self
        ) else {
            throw JarvisError.transport("RTCPeerConnectionFactory could not create a peer connection")
        }
        pc = newPC

        // 5. Create the data channel BEFORE the offer — the server only
        // ever listens (connection.py:330); if the client does not
        // create one there is none.
        let dcConfig = RTCDataChannelConfiguration()
        dcConfig.isOrdered = true
        let dc = newPC.dataChannel(forLabel: "pipecat", configuration: dcConfig)
        dc?.delegate = self
        dataChannel = dc

        // 6. Add the mic track.
        let source = DirectWebRTCTransport.factory.audioSource(with: AudioSession.captureConstraints)
        audioSource = source
        let track = DirectWebRTCTransport.factory.audioTrack(with: source, trackId: "jarvis-mic")
        micTrack = track
        newPC.add(track, streamIds: ["jarvis"])

        // 7. Offer.
        let offerConstraints = RTCMediaConstraints(
            mandatoryConstraints: ["OfferToReceiveAudio": "true"], optionalConstraints: nil
        )
        let offer = try await newPC.offer(for: offerConstraints)
        try await newPC.setLocalDescription(offer)

        // 8. POST the offer. storedPCID is needed for the ICE PATCH
        // (step 10), not for reconnects — every connect() sends pc_id:
        // nil, which is correct for a NEW connection (a prior session,
        // if any, was already disconnect()-ed above).
        let answer = try await Signalling.postOffer(
            OfferRequest(sdp: offer.sdp, type: "offer", pc_id: nil, restart_pc: nil),
            config: config
        )
        storedPCID = answer.pc_id

        // 9. Remote description.
        let remoteDesc = RTCSessionDescription(type: .answer, sdp: answer.sdp)
        try await newPC.setRemoteDescription(remoteDesc)

        // Flush any ICE candidates gathered before storedPCID existed.
        flushIceBufferIfPossible()
    }

    func disconnect() async {
        cancelAllTimers()
        dataChannel?.close()
        pc?.close()
        dataChannel = nil
        pc = nil
        micTrack = nil
        audioSource = nil
        iceBuffer.removeAll()
        iceBatchWorkItem?.cancel()
        iceBatchWorkItem = nil
        storedPCID = nil
        outboundQueue.removeAll()
        loggedSpeakingUnavailable = false
        config = nil
    }

    func send(_ data: Data) throws {
        guard let dc = dataChannel, dc.readyState == .open else {
            // Buffer up to outboundQueueMax, dropping oldest past the cap
            // — same bounded-history discipline the web stores use.
            outboundQueue.append(data)
            if outboundQueue.count > JarvisTuning.outboundQueueMax {
                outboundQueue.removeFirst(outboundQueue.count - JarvisTuning.outboundQueueMax)
            }
            return
        }
        let buffer = RTCDataBuffer(data: data, isBinary: false)
        dc.sendData(buffer)
    }

    func setMicEnabled(_ enabled: Bool) {
        // Never pc.removeTrack (N9.4) — just flip isEnabled.
        micTrack?.isEnabled = enabled
    }

    // MARK: - ICE batching (step 10)

    /// Batch rule: flush when the buffer reaches 5 candidates or 250 ms
    /// after the first buffered candidate, whichever comes first (§6).
    private func bufferIce(_ candidate: RTCIceCandidate) {
        iceBuffer.append(candidate)
        if iceBatchWorkItem == nil {
            let work = DispatchWorkItem { [weak self] in self?.flushIceBufferIfPossible() }
            iceBatchWorkItem = work
            queue.asyncAfter(deadline: .now() + JarvisTuning.iceBatchDelay, execute: work)
        }
        if iceBuffer.count >= JarvisTuning.iceBatchSize {
            iceBatchWorkItem?.cancel()
            iceBatchWorkItem = nil
            flushIceBufferIfPossible()
        }
    }

    private func flushIceBufferIfPossible() {
        guard let pcID = storedPCID, !iceBuffer.isEmpty else { return }
        let batch = iceBuffer
        iceBuffer.removeAll()
        iceBatchWorkItem?.cancel()
        iceBatchWorkItem = nil
        let wireCandidates = batch.map {
            WireIceCandidate(
                candidate: $0.sdp,
                sdp_mid: $0.sdpMid ?? "0",
                sdp_mline_index: Int($0.sdpMLineIndex)
            )
        }
        guard let cfg = config else { return }
        let request = PatchRequest(pc_id: pcID, candidates: wireCandidates)
        Task {
            do { try await Signalling.patch(request, config: cfg) }
            catch { transportLog.error("ICE PATCH failed: \(String(describing: error), privacy: .public)") }
        }
    }

    // MARK: - Data-channel open deadline / keep-alive / watchdog (step 11)

    private func armOpenDeadlineTimer() {
        openDeadlineTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + JarvisTuning.dataChannelOpenDeadline)
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            self.openDeadlineTimer = nil
            transportLog.error("data channel did not reach .open within deadline")
            self.teardownAfterFailure(error: JarvisError.transport("data channel never opened"))
        }
        openDeadlineTimer = timer
        timer.resume()
    }

    private func startKeepAliveAndWatchdog() {
        openDeadlineTimer?.cancel()
        openDeadlineTimer = nil

        lastKeepAliveSentAt = Date()

        // The ping is driven by a DispatchSourceTimer (NOT a bare
        // Task.sleep loop, which app-nap suspends in a background
        // window) and is sent UNCONDITIONALLY every keepAliveInterval —
        // never gated on client-side "is the bot idle?" logic.
        let keepAlive = DispatchSource.makeTimerSource(queue: queue)
        keepAlive.schedule(deadline: .now() + JarvisTuning.keepAliveInterval,
                            repeating: JarvisTuning.keepAliveInterval)
        keepAlive.setEventHandler { [weak self] in
            guard let self, let dc = self.dataChannel, dc.readyState == .open else { return }
            let ping = "ping".data(using: .utf8)!
            dc.sendData(RTCDataBuffer(data: ping, isBinary: false))
            self.lastKeepAliveSentAt = Date()
        }
        keepAliveTimer = keepAlive
        keepAlive.resume()

        // Watchdog: a stalled ping silences the bot's audio (F4) — fail
        // the session inside the server's 3 s window.
        let watchdog = DispatchSource.makeTimerSource(queue: queue)
        watchdog.schedule(deadline: .now() + 1.0, repeating: 1.0)
        watchdog.setEventHandler { [weak self] in
            guard let self else { return }
            if Date().timeIntervalSince(self.lastKeepAliveSentAt) > JarvisTuning.keepAliveStallSeconds {
                transportLog.error("keep-alive stalled past \(JarvisTuning.keepAliveStallSeconds, privacy: .public)s")
                self.teardownAfterFailure(error: JarvisError.transport("keep-alive stalled"))
            }
        }
        watchdogTimer = watchdog
        watchdog.resume()
    }

    private func cancelAllTimers() {
        openDeadlineTimer?.cancel(); openDeadlineTimer = nil
        keepAliveTimer?.cancel(); keepAliveTimer = nil
        watchdogTimer?.cancel(); watchdogTimer = nil
    }

    private func teardownAfterFailure(error: Error) {
        cancelAllTimers()
        // A network drop / forced failure must not leave a stale pc_id
        // for the next connect() (review F3).
        storedPCID = nil
        delegate?.transportDidDisconnect(error: error)
    }

    // MARK: - Signalling-frame interception (step 12)

    private func handleDataChannelMessage(_ data: Data) {
        // Intercept signalling before handing the frame to the app-message
        // decoder (review F7) — for Branch B, JarvisKit IS the transport,
        // so the server's signalling frames are ours to act on.
        if let root = try? JSONDecoder().decode(JSONValue.self, from: data),
           case .object(let obj) = root,
           obj["type"]?.stringValue == "signalling",
           let message = obj["message"],
           case .object(let msgObj) = message,
           let innerType = msgObj["type"]?.stringValue {
            switch innerType {
            case "peerLeft":
                // The server sends this over the data channel BEFORE
                // closing the peer connection — the only graceful
                // end-of-session signal.
                cancelAllTimers()
                delegate?.transportDidDisconnect(error: nil)
            case "renegotiate":
                // Genuinely unreachable for this audio-only bot
                // (connection.py gates it on a video/screen track, which
                // bot.py never enables) but must not crash.
                transportLog.debug("signalling_renegotiate_ignored")
            default:
                transportLog.debug("signalling frame ignored: \(innerType, privacy: .public)")
            }
            return
        }
        // Not signalling — hand to AppMessage.decode (it returns nil for
        // a signalling "type", which stays correct; the interception
        // above is what acts on it).
        delegate?.transport(didReceiveFrame: data)
    }
}

// MARK: - RTCPeerConnectionDelegate

extension DirectWebRTCTransport: RTCPeerConnectionDelegate {
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {
        // Where the plan attached the botIsSpeaking renderer. Unavailable
        // on this dependency — see noteSpeakingDetectionUnavailable().
        guard !stream.audioTracks.isEmpty else { return }
        queue.async { [weak self] in self?.noteSpeakingDetectionUnavailable() }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}

    func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}

    // 10. Buffer every candidate until storedPCID exists, then PATCH in batches.
    func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        queue.async { [weak self] in self?.bufferIce(candidate) }
    }

    func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}

    func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}

    // 14. Overall connection-state transitions.
    func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCPeerConnectionState) {
        queue.async { [weak self] in
            guard let self else { return }
            switch newState {
            case .connected:
                // Arm the data-channel open-deadline timer; the actual
                // transportDidConnect() fires when the data channel
                // reaches .open (see RTCDataChannelDelegate below), which
                // is the point at which this client can actually talk.
                self.armOpenDeadlineTimer()
            case .failed, .closed, .disconnected:
                self.storedPCID = nil
                self.teardownAfterFailure(error: JarvisError.transport("peer connection \(newState)"))
            default:
                break
            }
        }
    }

    // Unified-plan remote-track notification — where the bot's audio
    // track arrives. This is the hook a future botIsSpeaking mechanism
    // attaches to; nothing to attach on this dependency (step 8).
    func peerConnection(_ peerConnection: RTCPeerConnection, didStartReceivingOn transceiver: RTCRtpTransceiver) {
        guard transceiver.receiver.track is RTCAudioTrack else { return }
        queue.async { [weak self] in self?.noteSpeakingDetectionUnavailable() }
    }
}

// MARK: - RTCDataChannelDelegate

extension DirectWebRTCTransport: RTCDataChannelDelegate {
    // 11. Data-channel lifecycle.
    func dataChannelDidChangeState(_ dataChannel: RTCDataChannel) {
        queue.async { [weak self] in
            guard let self else { return }
            switch dataChannel.readyState {
            case .open:
                self.startKeepAliveAndWatchdog()
                self.delegate?.transportDidConnect()
                // Flush anything queued while the channel was not yet open.
                let queued = self.outboundQueue
                self.outboundQueue.removeAll()
                for frame in queued {
                    dataChannel.sendData(RTCDataBuffer(data: frame, isBinary: false))
                }
            case .closed:
                self.cancelAllTimers()
            default:
                break
            }
        }
    }

    // 12. Inbound frame.
    func dataChannel(_ dataChannel: RTCDataChannel, didReceiveMessageWith buffer: RTCDataBuffer) {
        if buffer.isBinary { return }
        let data = buffer.data
        queue.async { [weak self] in self?.handleDataChannelMessage(data) }
    }
}

// MARK: - Outbound audio statistics (§5 step 9 / §8 V6)

/// Cumulative counters for the outbound audio RTP stream, from the peer
/// connection's v2 statistics API (RTCStatisticsReport — verified
/// present in M120's headers). V6's whole point is a counter that keeps
/// climbing while the bot talks; these are the real packets, not a
/// proxy.
struct OutboundAudioStats: Equatable {
    let packetsSent: Int
    let bytesSent: Int
}

extension DirectWebRTCTransport {
    /// Completion fires on an arbitrary WebRTC thread with nil when no
    /// session is live or no outbound audio stream exists yet.
    func fetchOutboundAudioStats(_ completion: @escaping (OutboundAudioStats?) -> Void) {
        queue.async { [weak self] in
            guard let self, let pc = self.pc else { completion(nil); return }
            pc.statistics { report in
                var packets = 0
                var bytes = 0
                var found = false
                for stat in report.statistics.values where stat.type == "outbound-rtp" {
                    let kind = (stat.values["kind"] as? String)
                        ?? (stat.values["mediaType"] as? String)
                    guard kind == "audio" else { continue }
                    found = true
                    packets += (stat.values["packetsSent"] as? NSNumber)?.intValue ?? 0
                    bytes += (stat.values["bytesSent"] as? NSNumber)?.intValue ?? 0
                }
                completion(found ? OutboundAudioStats(packetsSent: packets, bytesSent: bytes) : nil)
            }
        }
    }

    /// The last successful keep-alive send, for the debug readout; nil
    /// before the channel first opens.
    var lastKeepAliveDate: Date? {
        lastKeepAliveSentAt == .distantPast ? nil : lastKeepAliveSentAt
    }
}

// MARK: - botIsSpeaking (step 8) — DEGRADED on this dependency

extension DirectWebRTCTransport {
    /// The plan's mechanism (review F12) needed an audio-renderer API
    /// that stasel/WebRTC 120.0.0 does not have — see the long note in
    /// AudioSession.swift for the header evidence and what it costs.
    /// This is the plan's own written degradation, not a substitute
    /// mechanism: nothing is attached, `botIsSpeaking` stays false, and
    /// we say so once per session rather than failing silently.
    func noteSpeakingDetectionUnavailable() {
        guard !loggedSpeakingUnavailable else { return }
        loggedSpeakingUnavailable = true
        transportLog.notice("botIsSpeaking_unavailable: no audio renderer API in this WebRTC build; botIsSpeaking stays false for this session")
    }
}
