import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
final class WindowVisibilityTests: XCTestCase {
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

    func testActualWindowHideShowAndDetachUpdateVisibility() throws {
        _ = NSApplication.shared
        let originalPolicy = NSApp.activationPolicy()
        XCTAssertTrue(NSApp.setActivationPolicy(.regular))
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        NSApp.finishLaunching()
        NSApp.activate(ignoringOtherApps: true)
        let view = WindowVisibilityView(frame: NSRect(x: 0, y: 0, width: 300, height: 160))
        var reports: [Bool] = []
        view.changed = { reports.append($0) }
        let window = NSWindow(contentRect: view.frame, styleMask: [.titled, .miniaturizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.close() }
        window.contentView = view
        window.makeKeyAndOrderFront(nil)
        pumpEvents(until: { reports.last == true })
        print("VISIBILITY_FIXTURE active=\(NSApp.isActive) screens=\(NSScreen.screens.count) onSpace=\(window.isOnActiveSpace) frame=\(window.frame) occlusion=\(window.occlusionState.rawValue)")
        XCTAssertTrue(window.isVisible)
        XCTAssertTrue(window.occlusionState.contains(.visible), "Fixture must have a visibly unoccluded window; policy=\(NSApp.activationPolicy()) hidden=\(NSApp.isHidden)")
        XCTAssertEqual(reports.last, true, "A visible window must resume animation")
        window.orderOut(nil)
        pumpEvents(until: { reports.last == false })
        XCTAssertEqual(reports.last, false, "Ordering the window out must suspend animation")
        window.makeKeyAndOrderFront(nil)
        pumpEvents(until: { reports.last == true })
        XCTAssertEqual(reports.last, true)
        window.miniaturize(nil)
        pumpEvents(until: { window.isMiniaturized && reports.last == false })
        XCTAssertTrue(window.isMiniaturized, "The fixture must actually minimize the window")
        XCTAssertEqual(reports.last, false)
        window.deminiaturize(nil)
        window.makeKeyAndOrderFront(nil)
        pumpEvents(until: { !window.isMiniaturized && reports.last == true })
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

    func testWaveStopsSamplingWhileWindowHiddenAndResumes() {
        _ = NSApplication.shared
        let originalPolicy = NSApp.activationPolicy()
        XCTAssertTrue(NSApp.setActivationPolicy(.regular))
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        NSApp.finishLaunching()
        NSApp.activate(ignoringOtherApps: true)
        var samples = 0
        let view = NSHostingView(rootView: VoiceWaveView(voiceState: .speaking, presentation: {
            samples += 1
            return VoicePresentationState(activity: .assistant, userLevel: nil, outputLevel: 0.7,
                microphoneMuted: false, assistantSpeaking: true)
        }))
        let window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 400, height: 180),
            styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.close() }
        window.contentView = view
        window.makeKeyAndOrderFront(nil)
        pumpEvents(for: 0.3)
        let started = samples
        pumpEvents(for: 0.2)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertGreaterThan(samples, started, "A visible active wave must sample new measured activity")
        window.orderOut(nil)
        pumpEvents(for: 0.3)
        let suspended = samples
        pumpEvents(for: 0.2)
        XCTAssertEqual(samples, suspended, "A hidden wave must stop requesting animation samples")
        window.makeKeyAndOrderFront(nil)
        pumpEvents(for: 0.3)
        let resumed = samples
        pumpEvents(for: 0.2)
        XCTAssertGreaterThan(samples, resumed, "Restoring the window must restart the active wave")
    }

    func testReducedMotionKeepsVisibleWaveStatic() {
        _ = NSApplication.shared
        let originalPolicy = NSApp.activationPolicy()
        XCTAssertTrue(NSApp.setActivationPolicy(.regular))
        defer { _ = NSApp.setActivationPolicy(originalPolicy) }
        NSApp.finishLaunching()
        NSApp.activate(ignoringOtherApps: true)
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
        window.makeKeyAndOrderFront(nil)
        pumpEvents(for: 0.3)
        XCTAssertTrue(window.occlusionState.contains(.visible))
        XCTAssertGreaterThan(samples, 0, "The reduced-motion view must still present its initial state")
        let settled = samples
        pumpEvents(for: 0.2)
        XCTAssertEqual(samples, settled, "Reduce Motion must pause the visible wave's animation samples")
    }
}
