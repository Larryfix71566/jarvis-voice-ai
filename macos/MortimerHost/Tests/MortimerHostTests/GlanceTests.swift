import XCTest
import JarvisKit
@testable import MortimerHost

/// Interface cleanup Phase 2, slice E: the status line's failed state and
/// the glance popover's "what to show" rules.
@MainActor
final class GlanceTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func ambient(reminderDue: Date? = nil, weather: Bool = false,
                         battery: Double? = nil, cpu: Double? = nil,
                         flags: [String] = [], summary: String? = nil) throws -> AmbientResponse {
        var json: [String: Any] = ["ok": true]
        if let reminderDue {
            let iso = ISO8601DateFormatter().string(from: reminderDue)
            json["reminder"] = ["text": "Call the plumber", "due_at": iso]
        }
        if weather { json["weather"] = ["summary": "Clear", "temp_f": 71.4, "location": "Alpharetta"] }
        if let summary { json["summary"] = summary }
        var system: [String: Any] = ["flags": flags]
        if let battery { system["battery"] = battery }
        if let cpu { system["cpu"] = cpu }
        json["system"] = system
        let data = try JSONSerialization.data(withJSONObject: json)
        return try JSONDecoder().decode(AmbientResponse.self, from: data)
    }

    private func derive(_ connection: JarvisClient.ConnectionState) -> OrbStatus {
        let presentation = VoicePresentationState(activity: .listening, userLevel: nil, outputLevel: nil,
                                                  microphoneMuted: false, assistantSpeaking: false)
        return OrbStatus.derive(connection: connection, presentation: presentation, needsYou: false,
                                audioOutputNotice: nil, speakerGateNotice: nil, audioInputNotice: nil)
    }

    // MARK: Status line

    func testFailedOffersRetryWithReasonAsDetail() {
        let status = derive(.failed("sidecar refused"))
        XCTAssertEqual(status.text, "Couldn't connect")
        XCTAssertEqual(status.tone, .attention)
        XCTAssertEqual(status.action, .retry)
        XCTAssertEqual(status.detail, "sidecar refused")
        XCTAssertNil(derive(.failed("  ")).detail)
    }

    func testOfflineIsUnchanged() {
        let status = derive(.offline)
        XCTAssertEqual(status, OrbStatus(text: "Not connected", tone: .quiet, action: .connect))
        XCTAssertNil(status.detail)
    }

    // MARK: Glance content

    func testDisconnectedShowsTimeAndDateOnly() throws {
        let busy = try ambient(reminderDue: now.addingTimeInterval(600), weather: true, battery: 5)
        let content = Glance.lines(now: now, ambient: busy, connected: false)
        XCTAssertEqual(content.time, Glance.timeText(now))
        XCTAssertFalse(content.date.isEmpty)
        XCTAssertNil(content.reminder)
        XCTAssertNil(content.weather)
        XCTAssertNil(content.warning)
        XCTAssertFalse(content.needsAttention)
    }

    func testNoDataShowsTimeOnly() {
        let content = Glance.lines(now: now, ambient: nil, connected: true)
        XCTAssertNil(content.reminder)
        XCTAssertNil(content.weather)
        XCTAssertNil(content.warning)
        XCTAssertFalse(content.needsAttention)
    }

    func testReminderWeatherAndBatteryAppearWhenPresent() throws {
        let busy = try ambient(reminderDue: now.addingTimeInterval(600), weather: true, battery: 12)
        let content = Glance.lines(now: now, ambient: busy, connected: true)
        XCTAssertTrue(content.reminder?.contains("Call the plumber") ?? false)
        XCTAssertEqual(content.weather, "Clear 71° · Alpharetta")
        XCTAssertEqual(content.warning, "Battery 12%")
        XCTAssertTrue(content.needsAttention)
    }

    func testHealthyBatteryAndNoReminderStaySilent() throws {
        let calm = try ambient(battery: 80, cpu: 30)
        let content = Glance.lines(now: now, ambient: calm, connected: true)
        XCTAssertNil(content.reminder)
        XCTAssertNil(content.weather)
        XCTAssertNil(content.warning)
        XCTAssertFalse(content.needsAttention)
    }

    func testExpiredReminderIsHiddenAfterTheGraceWindow() throws {
        let justDue = try ambient(reminderDue: now.addingTimeInterval(-30))
        XCTAssertNotNil(Glance.lines(now: now, ambient: justDue, connected: true).reminder)
        let stale = try ambient(reminderDue: now.addingTimeInterval(-AppTuning.reminderExpiryGraceSeconds - 5))
        XCTAssertNil(Glance.lines(now: now, ambient: stale, connected: true).reminder)
    }

    func testLastSessionSummaryIsNeverShown() throws {
        let secret = "MEMORY-NOTE-SECRET raw note text"
        let withSummary = try ambient(reminderDue: now.addingTimeInterval(600), weather: true, battery: 10, summary: secret)
        let content = Glance.lines(now: now, ambient: withSummary, connected: true)
        let all = [content.time, content.date, content.reminder, content.weather, content.warning]
            .compactMap { $0 }.joined(separator: "|")
        XCTAssertFalse(all.contains("MEMORY-NOTE-SECRET"))
    }

    // MARK: Attention rules

    func testNeedsAttentionThresholds() throws {
        func system(cpu: Double? = nil, battery: Double? = nil, flags: [String] = []) throws -> AmbientSystem {
            try XCTUnwrap(try ambient(battery: battery, cpu: cpu, flags: flags).system)
        }
        XCTAssertFalse(Glance.needsAttention(system: nil))
        XCTAssertFalse(Glance.needsAttention(system: try system(cpu: 84)))
        XCTAssertTrue(Glance.needsAttention(system: try system(cpu: 86)))
        XCTAssertTrue(Glance.needsAttention(system: try system(battery: AppTuning.lowBatteryPercent)))
        XCTAssertFalse(Glance.needsAttention(system: try system(battery: AppTuning.lowBatteryPercent + 1)))
        XCTAssertTrue(Glance.needsAttention(system: try system(flags: ["disk"])))
    }
}
