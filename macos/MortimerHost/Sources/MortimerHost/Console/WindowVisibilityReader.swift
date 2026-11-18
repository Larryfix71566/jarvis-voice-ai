import SwiftUI
import AppKit

/// Observes the existing window only; never activates, moves or creates one.
struct WindowVisibilityReader: NSViewRepresentable {
    let changed: (Bool) -> Void
    func makeNSView(context: Context) -> WindowVisibilityView {
        let view = WindowVisibilityView()
        view.changed = changed
        return view
    }
    func updateNSView(_ view: WindowVisibilityView, context: Context) {
        view.changed = changed
        view.refresh()
    }
    static func dismantleNSView(_ view: WindowVisibilityView, coordinator: ()) {
        view.stop()
    }
}

final class WindowVisibilityView: NSView {
    var changed: ((Bool) -> Void)?
    private var tokens: [NSObjectProtocol] = []
    private var revision = 0
    private var lastReported: Bool?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        stop()
        if let window {
            for name in [NSWindow.didChangeOcclusionStateNotification,
                         NSWindow.didUpdateNotification,
                         NSWindow.didMiniaturizeNotification, NSWindow.didDeminiaturizeNotification,
                         NSWindow.willCloseNotification] {
                tokens.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] notification in
                    if notification.name == NSWindow.willCloseNotification { self?.publish(false) }
                    else { self?.refresh() }
                })
            }
            for name in [NSApplication.didHideNotification, NSApplication.didUnhideNotification] {
                tokens.append(NotificationCenter.default.addObserver(forName: name, object: NSApp, queue: .main) { [weak self] _ in
                    self?.refresh()
                })
            }
        }
        refresh()
    }

    func refresh() {
        publish(nil)
    }

    /// A delivery is already queued for this revision; later requests only
    /// update `pendingForced` instead of cancelling it.
    private var deliveryQueued = false
    private var pendingForced: Bool?

    private func publish(_ forcedValue: Bool?) {
        // The latest request decides the forced value, as before.
        pendingForced = forcedValue
        // Coalesce rather than cancel. didUpdate fires on every
        // NSApp.updateWindows; when each refresh cancelled the queued
        // delivery, a run loop that refreshed again before draining the main
        // queue could starve delivery indefinitely, and the observer never
        // reported a window it could see. The queued delivery reads the
        // window when it runs, so it is never stale.
        guard !deliveryQueued else { return }
        deliveryQueued = true
        let expected = revision
        // SwiftUI must not receive state mutations during representable updates.
        DispatchQueue.main.async { [weak self] in
            guard let self, self.revision == expected else { return }
            self.deliveryQueued = false
            let forced = self.pendingForced
            self.pendingForced = nil
            // Initial window updates can precede the final occlusion state.
            // Read at delivery time and also observe completed window updates,
            // rather than retaining a pre-show state until the next transition.
            let value = forced ?? self.window.map {
                $0.isVisible && !$0.isMiniaturized && $0.occlusionState.contains(.visible) && !NSApp.isHidden
            } ?? false
            guard self.lastReported != value else { return }
            self.lastReported = value
            self.changed?(value)
        }
    }

    func stop() {
        // Bumping the revision drops any queued delivery.
        revision += 1
        deliveryQueued = false
        pendingForced = nil
        tokens.forEach(NotificationCenter.default.removeObserver)
        tokens.removeAll()
        lastReported = nil
    }

    deinit { tokens.forEach(NotificationCenter.default.removeObserver) }
}
