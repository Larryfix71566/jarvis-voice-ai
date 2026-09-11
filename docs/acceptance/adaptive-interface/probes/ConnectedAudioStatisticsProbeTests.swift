import XCTest
import WebRTC
@testable import JarvisKit

// Disposable feasibility probe: no server, credentials, or enabled microphone.
final class ConnectedAudioStatisticsProbeTests: XCTestCase {
    func testMutedConnectedStatisticsSchema() async throws {
        RTCInitializeSSL()
        let factory = RTCPeerConnectionFactory(encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory())
        let config = RTCConfiguration()
        config.iceServers = []
        config.sdpSemantics = .unifiedPlan
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let pc = try XCTUnwrap(factory.peerConnection(with: config, constraints: constraints, delegate: nil))
        defer { pc.close() }
        let source = factory.audioSource(with: AudioSession.captureConstraints)
        let track = factory.audioTrack(with: source, trackId: "synthetic-muted-probe")
        track.isEnabled = false
        pc.add(track, streamIds: ["synthetic"])
        let offer = try await pc.offer(for: RTCMediaConstraints(
            mandatoryConstraints: ["OfferToReceiveAudio": "true"], optionalConstraints: nil))
        try await pc.setLocalDescription(offer)
        let other = try XCTUnwrap(factory.peerConnection(with: config, constraints: constraints, delegate: nil))
        defer { other.close() }
        let otherTrack = factory.audioTrack(with: factory.audioSource(with: AudioSession.captureConstraints), trackId: "synthetic-remote-muted")
        otherTrack.isEnabled = false
        other.add(otherTrack, streamIds: ["synthetic-remote"])
        // Exchange gathered host candidates through SDP only; no signalling service.
        try await Task.sleep(nanoseconds: 1_000_000_000)
        try await other.setRemoteDescription(XCTUnwrap(pc.localDescription))
        let answer = try await other.answer(for: constraints)
        try await other.setLocalDescription(answer)
        try await Task.sleep(nanoseconds: 1_000_000_000)
        try await pc.setRemoteDescription(XCTUnwrap(other.localDescription))
        try await Task.sleep(nanoseconds: 1_000_000_000)
        print("CONNECTED_PROBE connection_state=\(pc.connectionState.rawValue) ice_state=\(pc.iceConnectionState.rawValue)")
        for index in 0..<12 {
            let report: RTCStatisticsReport = await withCheckedContinuation { continuation in
                pc.statistics { continuation.resume(returning: $0) }
            }
            let audio = report.statistics.values.filter {
                ($0.values["kind"] as? String) == "audio" || ($0.values["mediaType"] as? String) == "audio" || $0.type == "media-playout"
            }
            for stat in audio.sorted(by: { $0.type < $1.type }) {
                let allowed = ["audioLevel", "totalAudioEnergy", "totalSamplesDuration", "totalSamplesReceived", "jitterBufferDelay", "jitterBufferEmittedCount"]
                let levels = allowed.compactMap { key -> String? in
                    guard let value = stat.values[key] as? NSNumber else { return nil }
                    return "\(key)=\(value)"
                }.joined(separator: ",")
                print("CONNECTED_PROBE sample=\(index) timestamp_us=\(stat.timestamp_us) type=\(stat.type) keys=\(stat.values.keys.sorted()) values=\(levels)")
            }
            print("CONNECTED_PROBE sample=\(index) report_timestamp_us=\(report.timestamp_us) audio_records=\(audio.count)")
            try await Task.sleep(nanoseconds: 33_333_333)
        }
    }
}
