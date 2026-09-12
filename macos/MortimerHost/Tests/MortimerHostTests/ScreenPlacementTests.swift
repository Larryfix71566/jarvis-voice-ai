import XCTest
import AppKit
@testable import MortimerHost

/// Closure plan C4.3 (gap G18): the AppKit adapter behind the pure policy,
/// driven through its injected seams — synthetic screens, real borderless
/// NSWindows found by kind, a hand-fired scheduler, a fake clock and a
/// private UserDefaults suite. No live desktop topology is touched.
@MainActor
final class ScreenPlacementTests: XCTestCase {
    private let primary = PlacementScreen(id: "primary", visibleFrame: CGRect(x: 0, y: 0, width: 1440, height: 900))
    private let external = PlacementScreen(id: "external", visibleFrame: CGRect(x: 1440, y: 0, width: 1920, height: 1080))

    @MainActor
    private final class Seams {
        var screens: [PlacementScreen]
        var windows: [HostWindowKind: NSWindow] = [:]
        var scheduled: [(delay: TimeInterval, work: DispatchWorkItem)] = []
        var clock: TimeInterval = 100
        let suite: String
        let defaults: UserDefaults
        init(screens: [PlacementScreen]) throws {
            _ = NSApplication.shared
            self.screens = screens
            suite = "placement-\(UUID().uuidString)"
            defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        }
        func tearDown() {
            windows.values.forEach { $0.close() }
            defaults.removePersistentDomain(forName: suite)
        }
        /// Runs the most recently scheduled work item, the way the main
        /// queue would after the debounce delay.
        func fireLast() { scheduled.last?.work.perform() }
    }

    private func makePlacement(_ seams: Seams) -> ScreenPlacement {
        ScreenPlacement(defaults: seams.defaults,
                        screens: { seams.screens },
                        windows: { seams.windows[$0] },
                        schedule: { delay, work in seams.scheduled.append((delay, work)) },
                        now: { seams.clock })
    }

    private func makeWindow(_ kind: HostWindowKind, frame: CGRect, in seams: Seams) -> NSWindow {
        let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.identifier = NSUserInterfaceItemIdentifier(kind.rawValue)
        window.orderFrontRegardless()
        seams.windows[kind] = window
        return window
    }

    // MARK: debounce

    func testBurstOfSignalsCollapsesIntoOneRepositionThatRemembersTopology() throws {
        let seams = try Seams(screens: [primary]); defer { seams.tearDown() }
        let placement = makePlacement(seams)
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: seams)
        placement.scheduleReposition()
        placement.scheduleReposition(topologyChanged: true)
        placement.scheduleReposition()
        XCTAssertEqual(seams.scheduled.count, 3)
        XCTAssertTrue(seams.scheduled.allSatisfy { $0.delay == ScreenPlacement.debounceSeconds })
        XCTAssertTrue(seams.scheduled.dropLast().allSatisfy { $0.work.isCancelled }, "earlier items are cancelled")
        XCTAssertFalse(seams.scheduled.last!.work.isCancelled)
        XCTAssertEqual(placement.repositionCount, 0, "nothing runs before the delay")
        seams.scheduled.filter { !$0.work.isCancelled }.forEach { $0.work.perform() }
        XCTAssertEqual(placement.repositionCount, 1)
        // A topology change inside the burst is not lost, and the clock
        // measures from the first signal to the reconciliation.
        seams.clock = 100
        placement.topologyChanged()
        seams.clock = 100.1
        placement.scheduleReposition()
        seams.clock = 100.3
        seams.fireLast()
        XCTAssertEqual(placement.repositionCount, 2)
        XCTAssertEqual(try XCTUnwrap(placement.lastTopologyRecoverySeconds), 0.3, accuracy: 0.0001)
        XCTAssertEqual(placement.lastTopologyRecoveryMoves, 0, "a reachable console on its screen is not moved")
    }

    // MARK: self-notification suppression and manual evidence

    func testAppliedMovesAreNotRecordedAsManualButLiveResizeIs() throws {
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        let placement = makePlacement(seams)
        placement.startObserving()
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: seams)
        // Off-screen display window: reposition must move it (a setFrame that
        // posts didMove/didResize synchronously) without recording a manual move.
        let display = makeWindow(.display, frame: CGRect(x: 9000, y: 9000, width: 600, height: 400), in: seams)
        placement.reposition(topologyChanged: true)
        XCTAssertTrue(DisplayPlacementPolicy.reachable(display.frame, screens: [primary, external]), "recovered on screen: \(display.frame)")
        XCTAssertEqual(placement.records[.display]?.manual, false, "an applied recovery is automatic, not manual")
        XCTAssertFalse(placement.isApplying)
        // A programmatic move with no pointer or live-resize evidence is not manual either.
        display.setFrameOrigin(NSPoint(x: 1500, y: 100))
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        XCTAssertEqual(placement.records[.display]?.manual, false)
        XCTAssertEqual(placement.records[.display]?.manualRevision, 0)
        // The end of a live resize is explicit evidence.
        NotificationCenter.default.post(name: NSWindow.didEndLiveResizeNotification, object: display)
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        XCTAssertEqual(placement.records[.display]?.manual, true)
        XCTAssertEqual(placement.records[.display]?.manualRevision, 1)
        XCTAssertEqual(placement.records[.display]?.screenID, "external")
        XCTAssertEqual(placement.records[.display]?.frame, display.frame)
        // The manual record survived to the store.
        let stored = ScreenPlacement.decodeRecords(seams.defaults.data(forKey: ScreenPlacement.preferenceKey))
        XCTAssertEqual(stored[.display]?.manual, true)
        // A console live-resize also asks for a reposition (auxiliaries follow it).
        let before = seams.scheduled.count
        NotificationCenter.default.post(name: NSWindow.didEndLiveResizeNotification, object: seams.windows[.console]!)
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        XCTAssertEqual(seams.scheduled.count, before + 1)
    }

    // MARK: persistence

    func testPersistedRecordsDecodeOrAreRejectedFieldByField() throws {
        let good = PlacementRecord(screenID: "external", frame: CGRect(x: 1500, y: 100, width: 600, height: 400), manual: true, manualRevision: 3)
        var displaced = good
        displaced.recovery = PlacementRecovery(screenID: "primary", frame: CGRect(x: 10, y: 10, width: 500, height: 300), manualRevision: 3)
        let badFrame = PlacementRecord(screenID: "primary", frame: CGRect(x: 0, y: 0, width: 0, height: 300), manual: false)
        let badRevision = PlacementRecord(screenID: "primary", frame: CGRect(x: 0, y: 0, width: 500, height: 300), manual: false, manualRevision: -1)
        let longID = PlacementRecord(screenID: String(repeating: "x", count: 256), frame: CGRect(x: 0, y: 0, width: 500, height: 300), manual: false)
        let badRecovery = PlacementRecord(screenID: "primary", frame: CGRect(x: 0, y: 0, width: 500, height: 300), manual: true,
                                          recovery: PlacementRecovery(screenID: "external", frame: CGRect(x: 0, y: 0, width: 0, height: 1), manualRevision: 0))
        func encode(_ records: [String: PlacementRecord], version: Int = 1) throws -> Data {
            var saved = ScreenPlacement.Saved(records: records); saved.version = version
            return try JSONEncoder().encode(saved)
        }
        let decoded = ScreenPlacement.decodeRecords(try encode([
            "display": displaced, "console": badFrame, "drawer": badRevision, "unknown-kind": good]))
        XCTAssertEqual(decoded, [.display: displaced], "only the sane record survives, recovery included; unknown kinds are dropped")
        XCTAssertEqual(ScreenPlacement.decodeRecords(try encode(["console": longID])), [:])
        XCTAssertEqual(ScreenPlacement.decodeRecords(try encode(["console": badRecovery])), [:])
        XCTAssertEqual(ScreenPlacement.decodeRecords(try encode(["display": good], version: 2)), [:], "a foreign version discards the store")
        XCTAssertEqual(ScreenPlacement.decodeRecords(Data("not json".utf8)), [:])
        XCTAssertEqual(ScreenPlacement.decodeRecords(nil), [:])
        XCTAssertEqual(ScreenPlacement.decodeRecords(Data(repeating: 0x20, count: 50_000)), [:], "oversized stores are ignored")
        // A fresh adapter reads its records from the injected store.
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        seams.defaults.set(try encode(["display": good]), forKey: ScreenPlacement.preferenceKey)
        let placement = makePlacement(seams)
        XCTAssertEqual(placement.records, [.display: good])
        // …and a reopened manual window is restored to its saved frame.
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: seams)
        let display = makeWindow(.display, frame: CGRect(x: 1600, y: 300, width: 400, height: 300), in: seams)
        placement.reposition()
        XCTAssertEqual(display.frame, good.frame)
    }

    // MARK: Reset Layout

    func testResetLayoutClearsOnlyPlacementState() throws {
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        seams.defaults.set(11.0, forKey: "mortimer.interface.sidecarTabTextSize")
        seams.defaults.set(1, forKey: "mortimer.interface.layoutVersion")
        seams.defaults.set(Data("synthetic".utf8), forKey: "mortimer.memoryGraph.view")
        let placement = makePlacement(seams)
        placement.startObserving()
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: seams)
        let display = makeWindow(.display, frame: CGRect(x: 1500, y: 100, width: 600, height: 400), in: seams)
        placement.reposition()
        NotificationCenter.default.post(name: NSWindow.didEndLiveResizeNotification, object: display)
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        XCTAssertEqual(placement.records[.display]?.manual, true)
        XCTAssertNotNil(placement.placed[.display])
        placement.resetLayout()
        XCTAssertEqual(placement.records[.display]?.manual, false, "after reset the display is placed automatically again")
        XCTAssertEqual(placement.records[.display]?.manualRevision, 0)
        XCTAssertEqual(placement.records[.console]?.manual, false)
        XCTAssertEqual(display.frame, external.visibleFrame, "automatic placement fills the external screen")
        let stored = ScreenPlacement.decodeRecords(seams.defaults.data(forKey: ScreenPlacement.preferenceKey))
        XCTAssertEqual(stored[.display]?.manual, false)
        XCTAssertEqual(seams.defaults.double(forKey: "mortimer.interface.sidecarTabTextSize"), 11.0, "drawer text size untouched")
        XCTAssertEqual(seams.defaults.integer(forKey: "mortimer.interface.layoutVersion"), 1, "layout version untouched")
        XCTAssertEqual(seams.defaults.data(forKey: "mortimer.memoryGraph.view"), Data("synthetic".utf8), "graph view untouched")
    }

    // MARK: unlock / wake signals

    func testWakeSessionScreensAndUnlockSignalsAllScheduleATopologyReposition() throws {
        let seams = try Seams(screens: [primary]); defer { seams.tearDown() }
        let placement = makePlacement(seams)
        placement.startObserving()
        let initial = seams.scheduled.count
        XCTAssertEqual(initial, 1, "startObserving schedules the first reconciliation")
        let center = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.didWakeNotification, NSWorkspace.sessionDidBecomeActiveNotification, NSWorkspace.screensDidWakeNotification] {
            let before = seams.scheduled.count
            center.post(name: name, object: NSWorkspace.shared)
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
            XCTAssertEqual(seams.scheduled.count, before + 1, "\(name.rawValue) must schedule a reposition")
        }
        let before = seams.scheduled.count
        DistributedNotificationCenter.default().postNotificationName(ScreenPlacement.screenUnlockedNotification, object: nil,
                                                                     userInfo: nil, deliverImmediately: true)
        let deadline = Date(timeIntervalSinceNow: 2)
        while seams.scheduled.count == before, Date() < deadline { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.02)) }
        XCTAssertEqual(seams.scheduled.count, before + 1, "com.apple.screenIsUnlocked must schedule a reposition")
        XCTAssertEqual(ScreenPlacement.screenUnlockedNotification.rawValue, "com.apple.screenIsUnlocked")
        // Every one of them is a topology-class signal: the pending work carries it.
        seams.fireLast()
        XCTAssertNotNil(placement.lastTopologyRecoverySeconds)
    }
}
