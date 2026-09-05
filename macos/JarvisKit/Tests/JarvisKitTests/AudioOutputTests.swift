#if os(macOS)
import XCTest
@testable import JarvisKit

/// 2026-09-05 — the testable halves of the default-output-device follow
/// (AudioOutputMonitor). The CoreAudio listener itself needs real
/// hardware events; what a test can pin down is the notice copy, the
/// opt-in default, and that the monitor reads a device on this machine
/// without throwing.
final class AudioOutputTests: XCTestCase {
    func testNoticeTextNamesBothDevices() {
        let change = AudioOutputChange(from: "MacBook Air Speakers", to: "AirPods Pro")
        XCTAssertEqual(change.noticeText,
                       "Audio output moved to AirPods Pro — Mortimer's voice is still on MacBook Air Speakers")
    }

    func testNoticeTextWithoutAPreviousDevice() {
        let change = AudioOutputChange(from: nil, to: "AirPods Pro")
        XCTAssertEqual(change.noticeText, "Audio output moved to AirPods Pro — Mortimer's voice did not follow")
    }

    /// Unlike the other three flags, absent == OFF: a follow is a
    /// reconnect, and a reconnect is a new bot session.
    func testFollowAudioOutputIsOptIn() {
        let key = "JARVIS_FOLLOW_AUDIO_OUTPUT"
        let saved = UserDefaults.standard.object(forKey: key)
        defer {
            if let saved { UserDefaults.standard.set(saved, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        UserDefaults.standard.removeObject(forKey: key)
        XCTAssertFalse(JarvisFlags.followAudioOutput)
        UserDefaults.standard.set(true, forKey: key)
        XCTAssertTrue(JarvisFlags.followAudioOutput)
    }

    func testDefaultOutputDeviceReadsWithoutThrowing() {
        // A CI box may have no audio hardware (nil); a Mac has one. Either
        // way the call must not crash, and a device must carry a name.
        if let device = AudioOutputMonitor.defaultOutputDevice() {
            XCTAssertFalse(device.name.isEmpty)
        }
    }

    func testStartAndStopAreIdempotent() {
        let monitor = AudioOutputMonitor { _, _ in }
        monitor.start()
        monitor.start()
        monitor.stop()
        monitor.stop()
    }

    // MARK: - AudioInputCoordinator (the AirPods mic-rate fix)

    func testRateMismatchIsTrueOnlyWhenBothKnownAndDiffer() {
        // AirPods: 24 kHz mic vs 48 kHz speaker → mismatch.
        XCTAssertTrue(AudioInputCoordinator.rateMismatch(input: 24000, output: 48000))
        XCTAssertTrue(AudioInputCoordinator.rateMismatch(input: 48000, output: 24000))
        // Both 48 kHz (built-in) → no mismatch.
        XCTAssertFalse(AudioInputCoordinator.rateMismatch(input: 48000, output: 48000))
        // A point of rounding is not a mismatch.
        XCTAssertFalse(AudioInputCoordinator.rateMismatch(input: 48000, output: 47999.5))
        // Unknown (0) rates never count as a mismatch to act on.
        XCTAssertFalse(AudioInputCoordinator.rateMismatch(input: 0, output: 48000))
        XCTAssertFalse(AudioInputCoordinator.rateMismatch(input: 48000, output: 0))
    }

    func testMatchInputRateIsOnByDefault() {
        let key = "JARVIS_MATCH_INPUT_RATE"
        let saved = UserDefaults.standard.object(forKey: key)
        defer {
            if let saved { UserDefaults.standard.set(saved, forKey: key) }
            else { UserDefaults.standard.removeObject(forKey: key) }
        }
        UserDefaults.standard.removeObject(forKey: key)
        XCTAssertTrue(JarvisFlags.matchInputRate)   // absent == on (unusable audio otherwise)
        UserDefaults.standard.set(false, forKey: key)
        XCTAssertFalse(JarvisFlags.matchInputRate)
    }

    func testInputNoticeTextNamesTheRates() {
        let change = AudioInputChange(from: "Larry's AirPods Pro 3", to: "MacBook Air Microphone",
                                      fromRate: 24000, toRate: 48000)
        XCTAssertEqual(change.noticeText,
                       "Mic set to MacBook Air Microphone — Larry's AirPods Pro 3 runs at 24 kHz, which would slow Mortimer's voice")
    }

    func testRestoreWithoutAReassignmentIsANoOp() {
        // No connect happened, so nothing to restore — must not crash or
        // change any device.
        AudioInputCoordinator().restore()
    }
}
#endif
