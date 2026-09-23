import XCTest
import JarvisKit
@testable import MortimerHost

final class VoicePresentationStateTests: XCTestCase {
    func testOverlapPrioritizesUserWithoutInventingInterruption() {
        let id = UUID(); var meter = AudioActivityAccumulator(generation: id)
        meter.setMicrophoneEligible(true, at: 10)
        meter.observe(.processedInput, level: 0.4, measuredAt: 10, now: 10, generation: id)
        meter.observe(.actualPlayout, level: 0.6, measuredAt: 10, now: 10, generation: id)
        let state = VoicePresentationState.derive(connection: .connected, microphoneEnabled: true,
            botSpeaking: true, thinking: true, snapshot: meter.snapshot(at: 10), generation: id, now: 10)
        XCTAssertEqual(state.activity, .user)
        XCTAssertEqual(state.label, "Hearing you")
        XCTAssertTrue(state.assistantSpeaking)
        XCTAssertEqual(state.outputLevel, 0.6)
        XCTAssertFalse(state.audioLevelUnavailable)
    }

    func testMuteDoesNotHideAssistantAndMissingLevelsStayUnavailable() {
        let state = VoicePresentationState.derive(connection: .connected, microphoneEnabled: false,
            botSpeaking: true, thinking: true, snapshot: nil, generation: UUID(), now: 10)
        XCTAssertEqual(state.activity, .assistant)
        XCTAssertTrue(state.microphoneMuted)
        XCTAssertNil(state.userLevel)
        XCTAssertNil(state.outputLevel)
        XCTAssertTrue(state.audioLevelUnavailable)
    }

    func testMutedInputPreservesMeasuredMortimerSpeech() {
        let id = UUID(); var meter = AudioActivityAccumulator(generation: id)
        meter.setMicrophoneEligible(true, at: 10)
        meter.observe(.processedInput, level: 0.8, measuredAt: 10, now: 10, generation: id)
        meter.observe(.actualPlayout, level: 0.6, measuredAt: 10, now: 10, generation: id)
        let state = VoicePresentationState.derive(connection: .connected, microphoneEnabled: false,
            botSpeaking: true, thinking: false, snapshot: meter.snapshot(at: 10), generation: id, now: 10)
        XCTAssertEqual(state.activity, .assistant)
        XCTAssertEqual(state.outputLevel, 0.6)
        XCTAssertNil(state.userLevel, "Muted microphone samples must not drive the teal voice response")
        XCTAssertTrue(state.microphoneMuted)
        XCTAssertFalse(state.audioLevelUnavailable)
    }

    func testSilenceDoesNotInventThinkingAndStaleSessionCannotSpeak() {
        let id = UUID(); var meter = AudioActivityAccumulator(generation: id)
        meter.setMicrophoneEligible(true, at: 10)
        meter.observe(.processedInput, level: 0.9, measuredAt: 10, now: 10, generation: id)
        for (generation, time) in [(UUID(), 10.0), (id, 10.31)] {
            let state = VoicePresentationState.derive(connection: .connected, microphoneEnabled: true,
                botSpeaking: false, thinking: false, snapshot: meter.snapshot(at: 10), generation: generation, now: time)
            XCTAssertEqual(state.activity, .listening)
            XCTAssertNil(state.userLevel)
        }
        let thinking = VoicePresentationState.derive(connection: .connected, microphoneEnabled: true,
            botSpeaking: false, thinking: true, snapshot: nil, generation: id, now: 10)
        XCTAssertEqual(thinking.activity, .thinking)
    }

    func testLateSnapshotCannotRenewOriginalMeasurementDeadline() {
        let id = UUID(); var meter = AudioActivityAccumulator(generation: id)
        meter.setMicrophoneEligible(true, at: 10)
        meter.observe(.processedInput, level: 0.9, measuredAt: 10, now: 10, generation: id)
        let cached = meter.snapshot(at: 10.29)
        let state = VoicePresentationState.derive(connection: .connected, microphoneEnabled: true,
            botSpeaking: false, thinking: false, snapshot: cached, generation: id, now: 10.31)
        XCTAssertNil(state.userLevel)
        XCTAssertEqual(state.activity, .listening)
    }

    func testDisconnectedAndConnectingIgnoreSpeakingObservations() {
        for connection in [JarvisClient.ConnectionState.offline, .failed("synthetic"), .connecting] {
            let state = VoicePresentationState.derive(connection: connection, microphoneEnabled: true,
                botSpeaking: true, thinking: true, snapshot: nil, generation: UUID(), now: 10)
            XCTAssertFalse(state.assistantSpeaking)
            XCTAssertNil(state.outputLevel)
            XCTAssertFalse(state.audioLevelUnavailable)
        }
    }

    func testEnvelopeDependsOnElapsedTimeAndUnavailableClearsImmediately() {
        var slow = VoiceEnvelope(), fast = VoiceEnvelope()
        _ = slow.advance(target: 1, now: 0); _ = fast.advance(target: 1, now: 0)
        for tick in 1...30 { _ = slow.advance(target: 1, now: Double(tick) / 30) }
        for tick in 1...60 { _ = fast.advance(target: 1, now: Double(tick) / 60) }
        XCTAssertEqual(slow.level, fast.level, accuracy: 0.000001)
        for tick in 1...30 { _ = slow.advance(target: 0, now: 1 + Double(tick) / 30) }
        for tick in 1...60 { _ = fast.advance(target: 0, now: 1 + Double(tick) / 60) }
        XCTAssertEqual(slow.level, fast.level, accuracy: 0.000001)
        XCTAssertEqual(fast.advance(target: nil, now: 2.01), 0)
    }
}
