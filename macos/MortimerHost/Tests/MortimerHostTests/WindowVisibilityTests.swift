import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
final class WindowVisibilityTests: XCTestCase {
    private func prepareVisibleWindowServer() throws -> NSApplication.ActivationPolicy {
        let app = NSApplication.shared
        guard !NSScreen.screens.isEmpty else {
            throw XCTSkip("requires an interactive WindowServer with at least one screen; this test process has none")
        }
        let originalPolicy = app.activationPolicy()
        guard app.setActivationPolicy(.regular) else {
            throw XCTSkip("the test process cannot activate as a regular app in this session")
        }
        app.finishLaunching()
        // A frontmost-app request before a fixture window exists is not a
        // visibility prerequisite. Establish the real window state below.
        return originalPolicy
    }

    private func pumpEvents(for seconds: TimeInterval) {
        _ = NSApplication.shared
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline {
            if let event = NSApp.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01), inMode: .default, dequeue: true) {
                NSApp.sendEvent(event)
            }
            NSApp.updateWindows()
            RunLoop.main.run(until: Date().addingTimeInterval(0.005))
        }
    }

    /// Pumps events until `condition` holds or `timeout` elapses. The
    /// visibility observer reports through window-server occlusion events,
    /// whose latency is not fixed: 0.3 s was enough on the deployment Mac and
    /// once not enough in the sandbox guest (verification attempt
    /// 7ef13e35…, closure C5 record). The assertion that follows is unchanged;
    /// only the wait is bounded instead of fixed.
    private func pumpEvents(until condition: () -> Bool, timeout: TimeInterval = 3) {
        let deadline = Date().addingTimeInterval(timeout)
        repeat { pumpEvents(for: 0.05) } while !condition() && Date() < deadline
    }

    /// Puts a fixture window in front of every other app's windows. These
    /// tests read visibility from the window server, so any other window over
    /// the fixture (the Terminal running `swift test`, the Mortimer app) makes
    /// them fail for a reason that is not the code under test. On 24 Sep main
    /// failed 2 of 4 isolated runs (a restored wave did not resume within
    /// 0.5 s; a deminiaturized window was not reported visible within 3 s),
    /// and a full-suite run saw the fixture itself report not visible 0.3 s
    /// after appearing. The assertions are unchanged; only the fixture is
    /// raised above other apps' windows.
    private func show(_ window: NSWindow) {
        window.level = .floating
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
    }

    private func waitForVisibleFixture(_ window: NSWindow, until condition: () -> Bool) {
        // Activation-policy transitions can leave the owned test app hidden
        // after its initial show request. Restore only this visible fixture;
        // hide/minimize/close checks keep using the unmodified event pump.
        // The original three-second bound and real OS/observer assertions stay.
        pumpEvents(until: {
            if NSApp.isHidden { NSApp.unhideWithoutActivation() }
            if !window.isVisible { window.orderFrontRegardless() }
            return !NSApp.isHidden && window.isVisible
                && window.occlusionState.contains(.visible) && condition()
        })
    }

    func testVisibleFixtureRecoversFromAnApplicationHideAfterShowing() throws {
        let app = NSApplication.shared
        guard !NSScreen.screens.isEmpty else {
            throw XCTSkip("requires a real WindowServer screen for the synthetic hidden-owner fixture")
        }
        let originalPolicy = app.activationPolicy()
        guard app.setActivationPolicy(.regular) else {
            throw XCTSkip("the test process cannot use a regular application policy")
        }
        app.finishLaunching()
        let view = WindowVisibilityView(frame: NSRect(x: 0, y: 0, width: 300, height: 160))
        var reports: [Bool] = []
        view.changed = { reports.append($0) }
        let window = NSWindow(contentRect: view.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        defer {
            window.close()
            app.unhideWithoutActivation()
            _ = app.setActivationPolicy(originalPolicy)
        }
        // Independently prove this WindowServer can display the owned fixture.
        app.unhideWithoutActivation()
        show(window)
        pumpEvents(until: { reports.last == true })
        XCTAssertTrue(window.isVisible)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertEqual(reports.last, true)

        // Reproduce a late hidden-owner state after the initial show request.
        app.hide(nil)
        pumpEvents(until: { app.isHidden && reports.last == false })
        XCTAssertTrue(app.isHidden)
        XCTAssertEqual(reports.last, false)
        waitForVisibleFixture(window, until: { reports.last == true })
        XCTAssertFalse(app.isHidden, "Visible fixture preparation must restore its own hidden application")
        XCTAssertTrue(window.isVisible)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertEqual(reports.last, true, "Read the real observer after the owned window is restored")
    }

    func testVisibleFixtureRecoversFromADeferredApplicationHide() throws {
        let originalPolicy = try prepareVisibleWindowServer()
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 400, height: 180),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer {
            NSApp.unhideWithoutActivation()
            window.close()
        }
        NSApp.unhideWithoutActivation()
        show(window)
        pumpEvents(until: { window.occlusionState.contains(.visible) })
        XCTAssertTrue(window.occlusionState.contains(.visible), "Establish a real visible fixture first")

        var deliveredHiddenState = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            NSApp.hide(nil)
            self.pumpEvents(until: { NSApp.isHidden })
            deliveredHiddenState = NSApp.isHidden
        }
        waitForVisibleFixture(window, until: { window.occlusionState.contains(.visible) })
        pumpEvents(for: 0.3)
        XCTAssertTrue(deliveredHiddenState, "The real late-hide event must have occurred")
        XCTAssertFalse(NSApp.isHidden, "A first visible sample must not miss a pending application hide")
        XCTAssertTrue(window.isVisible)
        XCTAssertTrue(window.occlusionState.contains(.visible))
    }

    func testActualWindowHideShowAndDetachUpdateVisibility() throws {
        let originalPolicy = try prepareVisibleWindowServer()
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        let view = WindowVisibilityView(frame: NSRect(x: 0, y: 0, width: 300, height: 160))
        var reports: [Bool] = []
        view.changed = { reports.append($0) }
        let window = NSWindow(contentRect: view.frame, styleMask: [.titled, .miniaturizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.close() }
        window.contentView = view
        show(window)
        waitForVisibleFixture(window, until: { reports.last == true })
        print("VISIBILITY_FIXTURE active=\(NSApp.isActive) screens=\(NSScreen.screens.count) onSpace=\(window.isOnActiveSpace) frame=\(window.frame) occlusion=\(window.occlusionState.rawValue)")
        XCTAssertTrue(window.isVisible)
        XCTAssertTrue(window.occlusionState.contains(.visible), "Fixture must have a visibly unoccluded window; policy=\(NSApp.activationPolicy()) hidden=\(NSApp.isHidden)")
        XCTAssertEqual(reports.last, true, "A visible window must resume animation")
        window.orderOut(nil)
        pumpEvents(until: { reports.last == false })
        XCTAssertEqual(reports.last, false, "Ordering the window out must suspend animation")
        show(window)
        waitForVisibleFixture(window, until: { reports.last == true })
        XCTAssertEqual(reports.last, true)
        window.miniaturize(nil)
        pumpEvents(until: { window.isMiniaturized && reports.last == false })
        XCTAssertTrue(window.isMiniaturized, "The fixture must actually minimize the window")
        XCTAssertEqual(reports.last, false)
        window.deminiaturize(nil)
        show(window)
        waitForVisibleFixture(window, until: { !window.isMiniaturized && reports.last == true })
        XCTAssertFalse(window.isMiniaturized)
        XCTAssertEqual(reports.last, true)
        window.contentView = nil
        pumpEvents(until: { reports.last == false })
        XCTAssertEqual(reports.last, false)
    }

    func testStoppedObserverCannotDeliverQueuedState() {
        let view = WindowVisibilityView()
        var reports: [Bool] = []
        view.changed = { reports.append($0) }
        view.refresh()
        view.stop()
        pumpEvents(for: 0.1)
        XCTAssertTrue(reports.isEmpty)
    }

    func testWaveStopsSamplingWhileWindowHiddenAndResumes() throws {
        let originalPolicy = try prepareVisibleWindowServer()
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        var samples = 0
        let view = NSHostingView(rootView: VoiceWaveView(voiceState: .speaking, presentation: {
            samples += 1
            return VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: 0.7,
                microphoneMuted: false, assistantSpeaking: true)
        }))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 400, height: 180),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { if window.isVisible { window.close() } }
        window.contentView = view
        show(window)
        waitForVisibleFixture(window, until: { window.occlusionState.contains(.visible) })
        pumpEvents(for: 0.3)
        let started = samples
        pumpEvents(for: 0.2)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertGreaterThan(samples, started, "A visible active wave must sample new measured activity")
        window.orderOut(nil)
        pumpEvents(until: { !window.occlusionState.contains(.visible) })
        pumpEvents(for: 0.3)
        let suspended = samples
        pumpEvents(for: 0.2)
        XCTAssertEqual(samples, suspended, "A hidden wave must stop requesting animation samples")
        show(window)
        waitForVisibleFixture(window, until: { window.occlusionState.contains(.visible) })
        pumpEvents(for: 0.3)
        let resumed = samples
        pumpEvents(for: 0.2)
        XCTAssertGreaterThan(samples, resumed, "Restoring the window must restart the active wave")
        window.close()
        pumpEvents(for: 0.3)
        let closed = samples
        pumpEvents(for: 0.2)
        XCTAssertEqual(samples, closed, "Closing the host window must stop requesting animation samples")
    }

    func testReducedMotionKeepsVisibleWaveStatic() throws {
        let originalPolicy = try prepareVisibleWindowServer()
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        var samples = 0
        let view = NSHostingView(rootView: VoiceWaveAnimation(voiceState: .speaking, presentation: {
            samples += 1
            return VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: 0.7,
                microphoneMuted: false, assistantSpeaking: true)
        }, reduceMotion: true))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 400, height: 180),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.close() }
        window.contentView = view
        show(window)
        waitForVisibleFixture(window, until: { window.occlusionState.contains(.visible) })
        pumpEvents(for: 0.3)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertGreaterThan(samples, 0, "The reduced-motion view must still present its initial state")
        let settled = samples
        pumpEvents(for: 0.2)
        XCTAssertEqual(samples, settled, "Reduce Motion must pause the visible wave's animation samples")
    }
}
