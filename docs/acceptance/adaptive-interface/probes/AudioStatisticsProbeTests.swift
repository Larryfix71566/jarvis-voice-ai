import XCTest
import WebRTC
@testable import JarvisKit

// Disposable feasibility probe: no server, credentials, or enabled microphone.
final class AudioStatisticsProbeTests: XCTestCase {
    func testMutedLocalSourceStatisticsSchema() async throws {
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
        for index in 0..<12 {
            let report: RTCStatisticsReport = await withCheckedContinuation { continuation in
                pc.statistics { continuation.resume(returning: $0) }
            }
            let audio = report.statistics.values.filter {
                ($0.values["kind"] as? String) == "audio" || ($0.values["mediaType"] as? String) == "audio"
            }
            for stat in audio.sorted(by: { $0.type < $1.type }) {
                let allowed = ["audioLevel", "totalAudioEnergy", "totalSamplesDuration", "totalSamplesReceived", "jitterBufferDelay", "jitterBufferEmittedCount"]
                let levels = allowed.compactMap { key -> String? in
                    guard let value = stat.values[key] as? NSNumber else { return nil }
                    return "\(key)=\(value)"
                }.joined(separator: ",")
                print("AUDIO_PROBE sample=\(index) timestamp_us=\(stat.timestamp_us) type=\(stat.type) keys=\(stat.values.keys.sorted()) values=\(levels)")
            }
            print("AUDIO_PROBE sample=\(index) report_timestamp_us=\(report.timestamp_us) audio_records=\(audio.count)")
            try await Task.sleep(nanoseconds: 33_333_333)
        }
    }
}
