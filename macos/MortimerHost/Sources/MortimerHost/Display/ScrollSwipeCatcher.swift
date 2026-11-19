import AppKit
import SwiftUI

/// Background view that watches trackpad/mouse scroll events over its bounds
/// and reports horizontal swipes. Events are consumed only for claimed
/// horizontal gestures; vertical scrolling passes through untouched.
struct ScrollSwipeCatcher: NSViewRepresentable {
    var index: Int
    var count: Int
    /// Raw drag translation while a trackpad swipe is in progress.
    var onChange: (CGFloat) -> Void
    /// Gesture finished; `step` is -1, 0 or +1.
    var onEnd: (Int) -> Void

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        context.coordinator.view = view
        context.coordinator.install()
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        let c = context.coordinator
        c.index = index
        c.count = count
        c.onChange = onChange
        c.onEnd = onEnd
    }

    static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
        coordinator.remove()
    }

    /// Local monitors run on the main thread. The package builds in Swift 5
    /// language mode and the repo's other monitors (ConsoleView) use plain
    /// closures, so this follows the same pattern.
    final class Coordinator {
        weak var view: NSView?
        var index = 0
        var count = 0
        var onChange: (CGFloat) -> Void = { _ in }
        var onEnd: (Int) -> Void = { _ in }
        private var accumulator = ScrollSwipeAccumulator()
        private var monitor: Any?

        func install() {
            guard monitor == nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] event in
                guard let self, self.handle(event) else { return event }
                return nil
            }
        }

        func remove() {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }

        deinit { remove() }

        /// Returns true when the event is consumed.
        private func handle(_ event: NSEvent) -> Bool {
            guard let view, let window = view.window, event.window === window else { return false }
            let point = view.convert(event.locationInWindow, from: nil)
            guard view.bounds.contains(point) else { return false }
            let momentum = !event.momentumPhase.isEmpty
            let phase: ScrollSwipePhase
            let raw = momentum ? event.momentumPhase : event.phase
            if raw.contains(.cancelled) { phase = .cancelled }
            else if raw.contains(.ended) { phase = .ended }
            else if raw.contains(.began) || raw.contains(.mayBegin) { phase = .began }
            else { phase = .changed }
            // Make the card follow the fingers whatever the natural-scrolling setting.
            let sign: CGFloat = event.hasPreciseScrollingDeltas && !event.isDirectionInvertedFromDevice ? -1 : 1
            let out = accumulator.feed(deltaX: event.scrollingDeltaX * sign, deltaY: event.scrollingDeltaY * sign,
                                       phase: phase, momentum: momentum,
                                       precise: event.hasPreciseScrollingDeltas,
                                       timestamp: event.timestamp,
                                       index: index, count: count, width: view.bounds.width)
            if out.finished { onEnd(out.commit) }
            else if out.claimed && out.translation != 0 { onChange(out.translation) }
            return out.claimed
        }
    }
}
