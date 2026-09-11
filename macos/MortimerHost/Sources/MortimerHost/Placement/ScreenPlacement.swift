import AppKit
import CoreGraphics

/// One AppKit adapter for buttons, voice commands, restoration, display changes
/// and wake/unlock. Content/model ownership never lives in this class.
@MainActor
final class ScreenPlacement {
    static let shared = ScreenPlacement()
    nonisolated static let frameTolerance: CGFloat = 2
    private static let preferenceKey = "mortimer.interface.placement.v1"

    private struct Saved: Codable {
        var version = 1
        var records: [String: PlacementRecord]
    }

    private var policy = DisplayPlacementPolicy()
    private var observing = false
    private var applying = false
    private var pending: DispatchWorkItem?
    private var topologyPending = false
    private var observers: [NSObjectProtocol] = []
    private var seenWindows: [HostWindowKind: ObjectIdentifier] = [:]
    private var placedFrames: [HostWindowKind: CGRect] = [:]

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.preferenceKey), data.count < 50_000,
           let saved = try? JSONDecoder().decode(Saved.self, from: data), saved.version == 1 {
            for (key, record) in saved.records {
                guard let kind = HostWindowKind(rawValue: key), DisplayPlacementPolicy.valid(record.frame),
                      record.screenID.count < 256, record.manualRevision >= 0 else { continue }
                if let recovery = record.recovery,
                   (!DisplayPlacementPolicy.valid(recovery.frame) || recovery.screenID.count >= 256) { continue }
                policy.records[kind] = record
            }
        }
    }

    nonisolated static func isUserAdjusted(live: NSRect, placed: NSRect?, tolerance: CGFloat = frameTolerance) -> Bool {
        guard let placed else { return false }
        return abs(live.minX - placed.minX) > tolerance || abs(live.minY - placed.minY) > tolerance
            || abs(live.width - placed.width) > tolerance || abs(live.height - placed.height) > tolerance
    }

    func startObserving() {
        guard !observing else { return }
        observing = true
        observe(NSApplication.didChangeScreenParametersNotification) { [weak self] _ in self?.scheduleReposition(topologyChanged: true) }
        observe(NSWindow.didMoveNotification) { [weak self] note in self?.windowChanged(note) }
        observe(NSWindow.didResizeNotification) { [weak self] note in self?.windowChanged(note) }
        observe(NSWindow.didEndLiveResizeNotification) { [weak self] note in self?.windowChanged(note, explicitResize: true) }
        observe(NSWindow.willCloseNotification) { [weak self] note in
            guard let self, let window = note.object as? NSWindow, let kind = self.kind(of: window) else { return }
            self.noteClosed(kind)
        }
        for name in [NSWorkspace.didWakeNotification, NSWorkspace.sessionDidBecomeActiveNotification] {
            observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.scheduleReposition(topologyChanged: true) }
            })
        }
        scheduleReposition()
    }

    private func observe(_ name: Notification.Name, action: @escaping @MainActor (Notification) -> Void) {
        observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { note in
            MainActor.assumeIsolated { action(note) }
        })
    }

    /// A single 250 ms debounce owner, including auxiliary-window opens.
    func scheduleReposition(topologyChanged: Bool = false) {
        topologyPending = topologyPending || topologyChanged
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            let topology = self.topologyPending
            self.topologyPending = false; self.pending = nil
            self.reposition(topologyChanged: topology)
        }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
    }

    private func kind(of window: NSWindow) -> HostWindowKind? {
        let id = window.identifier?.rawValue ?? ""
        return HostWindowKind.allCases.first { id == $0.rawValue || id.hasPrefix($0.rawValue + "-") }
    }

    private func windowChanged(_ notification: Notification, explicitResize: Bool = false) {
        guard !applying, let window = notification.object as? NSWindow, let kind = kind(of: window), window.isVisible else { return }
        let event = NSApp.currentEvent
        let pointerDrag = NSEvent.pressedMouseButtons != 0 && event?.window === window
            && (event?.type == .leftMouseDragged || event?.type == .leftMouseDown)
        if explicitResize || window.inLiveResize || pointerDrag {
            policy.noteManual(kind, frame: window.frame, screens: screens())
            placedFrames[kind] = window.frame
            persist()
            if kind == .console { scheduleReposition() }
        }
    }

    private func screens() -> [PlacementScreen] {
        NSScreen.screens.compactMap { screen in
            guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { return nil }
            let display = CGDirectDisplayID(number.uint32Value)
            let mirrored = CGDisplayMirrorsDisplay(display)
            let identity = mirrored == kCGNullDirectDisplay ? display : mirrored
            let uuid = CGDisplayCreateUUIDFromDisplayID(identity)?.takeRetainedValue()
            let id = uuid.map { CFUUIDCreateString(nil, $0) as String } ?? "display-\(identity)"
            return PlacementScreen(id: id, visibleFrame: screen.visibleFrame, scale: screen.backingScaleFactor)
        }
    }

    func noteClosed(_ kind: HostWindowKind) {
        policy.noteClosed(kind); seenWindows[kind] = nil; placedFrames[kind] = nil
        persist()
    }

    func resetLayout() {
        policy.records = [:]
        placedFrames = [:]
        seenWindows = [:]
        persist()
        reposition(topologyChanged: true)
    }

    /// `topologyChanged` prevents AppKit's own automatic recovery movement from
    /// being mistaken for a newer manual placement. Explicit drags are observed
    /// independently above and always replace an unplug recovery preference.
    func reposition(topologyChanged: Bool = false) {
        let screens = screens()
        var windows: [HostWindowKind: NSWindow] = [:]
        var restoring: Set<HostWindowKind> = []
        for kind in HostWindowKind.allCases {
            guard let window = findHostWindow(kind: kind) else { seenWindows[kind] = nil; continue }
            windows[kind] = window
            if seenWindows[kind] != ObjectIdentifier(window) {
                restoring.insert(kind); seenWindows[kind] = ObjectIdentifier(window)
            } else if !topologyChanged && !topologyPending && Self.isUserAdjusted(live: window.frame, placed: placedFrames[kind]) {
                policy.noteManual(kind, frame: window.frame, screens: screens)
            }
        }
        let primary = windows[.console].flatMap { DisplayPlacementPolicy.screen(for: $0.frame, in: screens)?.id } ?? screens.first?.id
        let frames = windows.mapValues(\.frame)
        let moves = policy.reconcile(windows: frames, screens: screens, primaryID: primary, restoring: restoring)
        applying = true
        for (kind, frame) in moves {
            guard let window = windows[kind], !window.styleMask.contains(.fullScreen) else { continue }
            if Self.isUserAdjusted(live: window.frame, placed: frame) { window.setFrame(frame, display: true) }
            placedFrames[kind] = window.frame
            policy.records[kind]?.frame = window.frame
        }
        applying = false
        for (kind, window) in windows where placedFrames[kind] == nil { placedFrames[kind] = window.frame }
        persist()
    }

    private func persist() {
        let saved = Saved(records: Dictionary(uniqueKeysWithValues: policy.records.map { ($0.key.rawValue, $0.value) }))
        if let data = try? JSONEncoder().encode(saved) { UserDefaults.standard.set(data, forKey: Self.preferenceKey) }
    }
}
