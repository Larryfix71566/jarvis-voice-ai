import XCTest
import AppKit
@testable import MortimerHost

/// Closure plan C4.3 (gap G18): the AppKit adapter behind the pure policy,
/// driven through its injected seams — synthetic screens, real borderless
/// NSWindows found by kind, a hand-fired scheduler, a fake clock and a
/// private UserDefaults suite. No live desktop topology is touched.
@MainActor
final class ScreenPlacementTests: XCTestCase {
    private let primary = PlacementScreen(id: "primary", visibleFrame: CGRect(x: 0, y: 0, width: 1440, height: 900), isMain: true)
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

    // MARK: live display topology

    /// This is an opt-in hardware receipt: a single-display Mac skips it, while
    /// a connected non-mirrored display must be visible through the same
    /// normalized topology used by the placement owner. The test deliberately
    /// checks only topology facts; panel movement and unplug/reconnect remain
    /// manual acceptance gates because XCTest cannot reproduce those events.
    func testConnectedExternalDisplayIsExposedToPlacementTopology() throws {
        let screens = ScreenPlacement.liveScreens()
        guard screens.count >= 2 else {
            throw XCTSkip("requires at least two non-mirrored displays")
        }
        XCTAssertEqual(Set(screens.map(\.id)).count, screens.count, "each display must have a stable identity")
        XCTAssertTrue(screens.allSatisfy { $0.visibleFrame.width > 0 && $0.visibleFrame.height > 0 })
        XCTAssertTrue(screens.contains { $0.visibleFrame.minX != 0 || $0.visibleFrame.minY != 0 },
                      "an external display should contribute a distinct virtual-screen origin")
        XCTAssertEqual(screens.filter(\.isMain).count, 1, "exactly one display should be the macOS main display")
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

    func testLostSupportingScreenRequestsDisplaySceneClosureBeforeFrameRecovery() throws {
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        var closed = 0
        let placement = makePlacement(seams)
        placement.setDisplayLostHandler { closed += 1 }
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: seams)
        _ = makeWindow(.display, frame: CGRect(x: 1500, y: 100, width: 600, height: 400), in: seams)
        placement.reposition()
        XCTAssertEqual(placement.records[.display]?.screenID, "external")

        seams.screens = [primary]
        placement.reposition(topologyChanged: true)
        XCTAssertEqual(closed, 1, "losing the assigned monitor closes the supporting scene before fallback")

        // AppKit may order the auxiliary window out before delivering the
        // screen-parameter notification; the logical scene must still close.
        let hiddenSeams = try Seams(screens: [primary, external]); defer { hiddenSeams.tearDown() }
        var hiddenClosed = 0
        let hiddenPlacement = makePlacement(hiddenSeams)
        hiddenPlacement.setDisplayLostHandler { hiddenClosed += 1 }
        _ = makeWindow(.console, frame: CGRect(x: 100, y: 100, width: 900, height: 600), in: hiddenSeams)
        let hiddenDisplay = makeWindow(.display, frame: CGRect(x: 1500, y: 100, width: 600, height: 400), in: hiddenSeams)
        hiddenPlacement.reposition()
        hiddenDisplay.orderOut(nil)
        hiddenSeams.screens = [primary]
        hiddenPlacement.reposition(topologyChanged: true)
        XCTAssertEqual(hiddenClosed, 1, "hidden supporting scene still closes on monitor loss")
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
        // AppKit's borderless test window can retain a three-point shadow
        // offset on the virtual-screen edge; the placement contract is the
        // display origin/size within that frame tolerance.
        XCTAssertEqual(display.frame.minX, external.visibleFrame.minX, accuracy: 3)
        XCTAssertEqual(display.frame.minY, external.visibleFrame.minY, accuracy: 3)
        XCTAssertEqual(display.frame.width, external.visibleFrame.width, accuracy: 0.01)
        XCTAssertEqual(display.frame.height, external.visibleFrame.height, accuracy: 0.01,
                       "automatic placement fills the external screen")
        let stored = ScreenPlacement.decodeRecords(seams.defaults.data(forKey: ScreenPlacement.preferenceKey))
        XCTAssertEqual(stored[.display]?.manual, false)
        XCTAssertEqual(seams.defaults.double(forKey: "mortimer.interface.sidecarTabTextSize"), 11.0, "drawer text size untouched")
        XCTAssertEqual(seams.defaults.integer(forKey: "mortimer.interface.layoutVersion"), 1, "layout version untouched")
        XCTAssertEqual(seams.defaults.data(forKey: "mortimer.memoryGraph.view"), Data("synthetic".utf8), "graph view untouched")
    }

    func testDetachedPanelPlacementClampsToRequestedVirtualScreen() throws {
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        let placement = makePlacement(seams)
        let panel = NSWindow(contentRect: CGRect(x: 0, y: 0, width: 600, height: 400),
                             styleMask: [.borderless], backing: .buffered, defer: false)
        panel.isReleasedWhenClosed = false
        panel.orderFrontRegardless()
        defer { panel.close() }

        placement.placeDetachedPanel(panel, on: "external")
        XCTAssertTrue(external.visibleFrame.contains(panel.frame))
        XCTAssertEqual(panel.frame.size, CGSize(width: 600, height: 400))
        XCTAssertEqual(panel.frame.origin, CGPoint(x: external.visibleFrame.minX,
                                                   y: external.visibleFrame.minY))
    }

    func testDetachedPanelRecoversAcrossVirtualScreenDisconnectAndReconnect() throws {
        let seams = try Seams(screens: [primary, external]); defer { seams.tearDown() }
        let placement = makePlacement(seams)
        let panel = NSWindow(contentRect: CGRect(x: 1600, y: 120, width: 700, height: 500),
                             styleMask: [.borderless], backing: .buffered, defer: false)
        panel.isReleasedWhenClosed = false
        panel.orderFrontRegardless()
        defer { panel.close() }

        placement.registerDetachedPanel(panel, id: "panel-memory", screenID: "external")
        placement.reposition(topologyChanged: true)
        let saved = panel.frame
        XCTAssertEqual(saved.origin, CGPoint(x: 1600, y: 120))

        seams.screens = [primary]
        placement.topologyChanged(); placement.reposition(topologyChanged: true)
        XCTAssertTrue(DisplayPlacementPolicy.reachable(panel.frame, screens: [primary]))
        XCTAssertNotEqual(panel.frame, saved)

        seams.screens = [primary, external]
        placement.topologyChanged(); placement.reposition(topologyChanged: true)
        XCTAssertEqual(panel.frame, saved, "reconnect restores the value-addressed panel frame")
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
