import AppKit
import CoreGraphics
import os

private let placementLog = Logger(subsystem: "com.mortimer.host", category: "placement")

/// One AppKit adapter for buttons, voice commands, restoration, display changes
/// and wake/unlock. Content/model ownership never lives in this class.
///
/// Closure C4.3 (gap G18): the screen list, the window lookup, the debounce
/// scheduler, the clock and the defaults store are injectable so the adapter
/// is testable without the live desktop; `shared` uses the real ones.
@MainActor
final class ScreenPlacement {
    static let shared = ScreenPlacement()
    nonisolated static let frameTolerance: CGFloat = 2
    nonisolated static let debounceSeconds: TimeInterval = 0.25
    static let preferenceKey = "mortimer.interface.placement.v1"

    struct Saved: Codable {
        var version = 1
        var records: [String: PlacementRecord]
    }

    typealias Scheduler = @MainActor (_ delay: TimeInterval, _ work: DispatchWorkItem) -> Void

    private let defaults: UserDefaults
    private let screenProvider: @MainActor () -> [PlacementScreen]
    private let windowProvider: @MainActor (HostWindowKind) -> NSWindow?
    private let schedule: Scheduler
    private let now: @MainActor () -> TimeInterval

    private var policy = DisplayPlacementPolicy()
    private var observing = false
    private var applying = false
    private var pending: DispatchWorkItem?
    private var topologyPending = false
    private var observers: [NSObjectProtocol] = []
    /// Called when the fixed supporting-display scene loses its requested
    /// physical screen. The app-owned WindowPlacement uses this to close the
    /// scene so its content is immediately reparented into the main console;
    /// placement itself remains the sole topology owner.
    private var displayLostHandler: (@MainActor () -> Void)?
    /// Last confirmed non-main screen for the supporting scene. AppKit can
    /// rewrite the persisted record to the main display while a monitor is
    /// disappearing; this cache preserves the identity needed to close the
    /// scene before that rewrite hides the loss.
    private var lastSupportingScreenID: String?
    private var seenWindows: [HostWindowKind: ObjectIdentifier] = [:]
    private var placedFrames: [HostWindowKind: CGRect] = [:]
    /// Dynamic Command Console panels use stable value IDs rather than the
    /// fixed HostWindowKind set. Keep their requested screen and recovery
    /// frame in this same topology owner so unplug/reconnect cannot strand a
    /// detached graph, result or Atlas window.
    private final class DetachedPanelState {
        let id: String
        weak var window: NSWindow?
        var screenID: String
        var frame: CGRect
        var manual = false
        var recovery: PlacementRecovery?

        init(id: String, window: NSWindow, screenID: String, frame: CGRect) {
            self.id = id
            self.window = window
            self.screenID = screenID
            self.frame = frame
        }
    }
    private var detachedPanels: [String: DetachedPanelState] = [:]
    /// Closure C4.4 (gap G19): when the current topology change was first
    /// observed, and how long the last recovery took from that observation
    /// to its final `setFrame`. The hardware gate is ≤ 1 s.
    private var topologyObservedAt: TimeInterval?
    private(set) var lastTopologyRecoverySeconds: TimeInterval?
    private(set) var lastTopologyRecoveryMoves = 0
    private(set) var repositionCount = 0
    private(set) var scheduledCount = 0

    private convenience init() {
        self.init(defaults: .standard,
                  screens: { ScreenPlacement.liveScreens() },
                  windows: { findHostWindow(kind: $0) },
                  schedule: { delay, work in DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work) },
                  now: { ProcessInfo.processInfo.systemUptime })
    }

    init(defaults: UserDefaults,
         screens: @escaping @MainActor () -> [PlacementScreen],
         windows: @escaping @MainActor (HostWindowKind) -> NSWindow?,
         schedule: @escaping Scheduler,
         now: @escaping @MainActor () -> TimeInterval) {
        self.defaults = defaults
        self.screenProvider = screens
        self.windowProvider = windows
        self.schedule = schedule
        self.now = now
        policy.records = Self.decodeRecords(defaults.data(forKey: Self.preferenceKey))
    }

    /// Persisted records are trusted only when every field is sane; a bad
    /// version discards the whole store, a bad record only itself.
    static func decodeRecords(_ data: Data?) -> [HostWindowKind: PlacementRecord] {
        guard let data, data.count < 50_000,
              let saved = try? JSONDecoder().decode(Saved.self, from: data), saved.version == 1 else { return [:] }
        var records: [HostWindowKind: PlacementRecord] = [:]
        for (key, record) in saved.records {
            guard let kind = HostWindowKind(rawValue: key), DisplayPlacementPolicy.valid(record.frame),
                  record.screenID.count < 256, record.manualRevision >= 0 else { continue }
            if let recovery = record.recovery,
               (!DisplayPlacementPolicy.valid(recovery.frame) || recovery.screenID.count >= 256) { continue }
            records[kind] = record
        }
        return records
    }

    var records: [HostWindowKind: PlacementRecord] { policy.records }
    var placed: [HostWindowKind: CGRect] { placedFrames }
    var isApplying: Bool { applying }

    func setDisplayLostHandler(_ handler: (@MainActor () -> Void)?) {
        displayLostHandler = handler
    }

    nonisolated static func isUserAdjusted(live: NSRect, placed: NSRect?, tolerance: CGFloat = frameTolerance) -> Bool {
        guard let placed else { return false }
        return abs(live.minX - placed.minX) > tolerance || abs(live.minY - placed.minY) > tolerance
            || abs(live.width - placed.width) > tolerance || abs(live.height - placed.height) > tolerance
    }

    func startObserving() {
        guard !observing else { return }
        observing = true
        observe(NSApplication.didChangeScreenParametersNotification) { [weak self] _ in self?.topologyChanged() }
        observe(NSWindow.didMoveNotification) { [weak self] note in self?.windowChanged(note) }
        observe(NSWindow.didResizeNotification) { [weak self] note in self?.windowChanged(note) }
        observe(NSWindow.didEndLiveResizeNotification) { [weak self] note in self?.windowChanged(note, explicitResize: true) }
        observe(NSWindow.willCloseNotification) { [weak self] note in
            guard let self, let window = note.object as? NSWindow, let kind = self.kind(of: window) else { return }
            self.noteClosed(kind)
        }
        // Interface plan §5 "lock/unlock and sleep/wake": system wake, session
        // activation, screens waking (closure C4.1, gap G16) …
        for name in [NSWorkspace.didWakeNotification, NSWorkspace.sessionDidBecomeActiveNotification,
                     NSWorkspace.screensDidWakeNotification] {
            observers.append(NSWorkspace.shared.notificationCenter.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.topologyChanged() }
            })
        }
        // … and the screen unlock itself, which loginwindow posts as a
        // distributed notification (there is no NSWorkspace equivalent).
        observers.append(DistributedNotificationCenter.default().addObserver(
            forName: Self.screenUnlockedNotification, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.topologyChanged() }
        })
        scheduleReposition()
    }

    nonisolated static let screenUnlockedNotification = Notification.Name("com.apple.screenIsUnlocked")

    private func observe(_ name: Notification.Name, action: @escaping @MainActor (Notification) -> Void) {
        observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { note in
            MainActor.assumeIsolated { action(note) }
        })
    }

    /// Every topology-class signal funnels here: the clock starts at the
    /// first signal of a burst and the single debounced work item does the
    /// reconciliation.
    func topologyChanged() {
        if topologyObservedAt == nil { topologyObservedAt = now() }
        scheduleReposition(topologyChanged: true)
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
        scheduledCount += 1
        schedule(Self.debounceSeconds, work)
    }

    private func kind(of window: NSWindow) -> HostWindowKind? {
        let id = window.identifier?.rawValue ?? ""
        return HostWindowKind.allCases.first { id == $0.rawValue || id.hasPrefix($0.rawValue + "-") }
    }

    private func windowChanged(_ notification: Notification, explicitResize: Bool = false) {
        guard !applying, let window = notification.object as? NSWindow, window.isVisible else { return }
        let event = NSApp.currentEvent
        let pointerDrag = NSEvent.pressedMouseButtons != 0 && event?.window === window
            && (event?.type == .leftMouseDragged || event?.type == .leftMouseDown)
        if explicitResize || window.inLiveResize || pointerDrag {
            if let panel = detachedPanels.values.first(where: { $0.window === window }) {
                guard let screen = DisplayPlacementPolicy.screen(for: window.frame, in: screenProvider()) else { return }
                panel.screenID = screen.id
                panel.frame = window.frame
                panel.manual = true
                panel.recovery = nil
                return
            }
            guard let kind = kind(of: window) else { return }
            policy.noteManual(kind, frame: window.frame, screens: screenProvider())
            placedFrames[kind] = window.frame
            persist()
            if kind == .console { scheduleReposition() }
        }
    }

    /// Frames are AppKit points on every display; no pixel clamp is needed
    /// across mixed-scale screens, so the scale is not captured (closure
    /// C4.2, gap G17 — field removed rather than used).
    static func liveScreens() -> [PlacementScreen] {
        let mainDisplay: CGDirectDisplayID? = NSScreen.main.flatMap {
            ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)
                .map { CGDirectDisplayID($0.uint32Value) }
        }
        return NSScreen.screens.compactMap { screen -> PlacementScreen? in
            guard let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { return nil }
            let display = CGDirectDisplayID(number.uint32Value)
            let mirrored = CGDisplayMirrorsDisplay(display)
            let identity = mirrored == kCGNullDirectDisplay ? display : mirrored
            let uuid = CGDisplayCreateUUIDFromDisplayID(identity)?.takeRetainedValue()
            let id = uuid.map { CFUUIDCreateString(nil, $0) as String } ?? "display-\(identity)"
            return PlacementScreen(id: id, visibleFrame: screen.visibleFrame,
                                  isMain: identity == mainDisplay)
        }
    }

    func noteClosed(_ kind: HostWindowKind) {
        policy.noteClosed(kind); seenWindows[kind] = nil; placedFrames[kind] = nil
        persist()
    }

    /// Interface plan §5: Reset Layout resets only layout — placement records,
    /// placed frames and window identity memory here; the drawer width is
    /// the menu action's own reset. Nothing else in the defaults store is touched.
    func resetLayout() {
        policy.records = [:]
        placedFrames = [:]
        seenWindows = [:]
        for panel in detachedPanels.values {
            panel.manual = false
            panel.recovery = nil
            if let window = panel.window { panel.frame = window.frame }
        }
        persist()
        reposition(topologyChanged: true)
    }

    /// Register a value-addressed panel with the same placement owner as the
    /// fixed scenes. The requested screen is retained even while absent so a
    /// later reconnect can restore the user's frame.
    func registerDetachedPanel(_ window: NSWindow, id: String, screenID: String? = nil) {
        guard !id.isEmpty else { return }
        let screens = screenProvider()
        let requested = screenID?.trimmingCharacters(in: .whitespacesAndNewlines)
        let target = requested.flatMap { $0.isEmpty ? nil : $0 }
            ?? DisplayPlacementPolicy.screen(for: window.frame, in: screens)?.id
            ?? screens.first?.id
        guard let target else { return }
        if let existing = detachedPanels[id], existing.window === window {
            if requested != nil { existing.screenID = target }
            return
        }
        detachedPanels[id] = DetachedPanelState(id: id, window: window,
                                                screenID: target, frame: window.frame)
        scheduleReposition()
    }

    func unregisterDetachedPanel(id: String) {
        detachedPanels.removeValue(forKey: id)
    }

    /// Place a value-addressed detachable panel on a requested display after
    /// its SwiftUI scene has been created. Panel windows are intentionally
    /// not added to the persisted HostWindowKind set: their content identity
    /// is owned by ContentWindowRegistry, while this method reuses the same
    /// validated screen frames and clamping rules as the fixed scenes.
    func placeDetachedPanel(_ window: NSWindow, id: String? = nil, on screenID: String) {
        let panelID = id ?? window.identifier?.rawValue ?? "detached-\(ObjectIdentifier(window))"
        registerDetachedPanel(window, id: panelID, screenID: screenID)
        guard let screen = screenProvider().first(where: { $0.id == screenID }) else { return }
        let frame = DisplayPlacementPolicy.clamp(window.frame, to: screen.visibleFrame)
        if let panel = detachedPanels[panelID] { panel.frame = frame }
        guard Self.isUserAdjusted(live: window.frame, placed: frame) else { return }
        applying = true
        applyFrame(frame, to: window)
        applying = false
        placementLog.debug("detached panel placed on screen \(screenID, privacy: .public)")
    }

    /// `topologyChanged` prevents AppKit's own automatic recovery movement from
    /// being mistaken for a newer manual placement. Explicit drags are observed
    /// independently above and always replace an unplug recovery preference.
    func reposition(topologyChanged: Bool = false) {
        repositionCount += 1
        let screens = screenProvider()
        var windows: [HostWindowKind: NSWindow] = [:]
        var restoring: Set<HostWindowKind> = []
        for kind in HostWindowKind.allCases {
            guard let window = windowProvider(kind) else { seenWindows[kind] = nil; continue }
            windows[kind] = window
            if seenWindows[kind] != ObjectIdentifier(window) {
                restoring.insert(kind); seenWindows[kind] = ObjectIdentifier(window)
            } else if !topologyChanged && !topologyPending && Self.isUserAdjusted(live: window.frame, placed: placedFrames[kind]) {
                policy.noteManual(kind, frame: window.frame, screens: screens)
            }
        }
        if screens.count > 1,
           let display = windows[.display],
           let displayScreen = DisplayPlacementPolicy.screen(for: display.frame, in: screens),
           !displayScreen.isMain {
            lastSupportingScreenID = displayScreen.id
        }
        // A display scene is content, not a durable second owner. When its
        // assigned monitor disappears, close the scene before policy moves
        // the window frame to the primary screen. This makes the unplug path
        // deterministic: the main workspace immediately owns the graph and
        // response instead of leaving an off-screen supporting window open.
        if screens.count <= 1,
           windows[.display] != nil,
           let assigned = lastSupportingScreenID ?? policy.records[.display]?.screenID,
           !screens.contains(where: { $0.id == assigned }) {
            displayLostHandler?()
        }
        // macOS's main display is the default console role. A persisted
        // manual console record is the only override; using the live frame
        // here would let a stale AppKit restoration silently invert the
        // console and supporting-display roles.
        let primary = policy.records[.console].flatMap { $0.manual ? $0.screenID : nil }
            ?? screens.first(where: \.isMain)?.id
            ?? windows[.console].flatMap { DisplayPlacementPolicy.screen(for: $0.frame, in: screens)?.id }
            ?? screens.first?.id
        let frames = windows.mapValues(\.frame)
        let moves = policy.reconcile(windows: frames, screens: screens, primaryID: primary, restoring: restoring)
        var applied = 0
        applying = true
        for (kind, frame) in moves {
            guard let window = windows[kind], !window.styleMask.contains(.fullScreen) else { continue }
            if Self.isUserAdjusted(live: window.frame, placed: frame) {
                applyFrame(frame, to: window)
                applied += 1
            }
            placedFrames[kind] = window.frame
            policy.records[kind]?.frame = window.frame
        }
        applying = false
        for (kind, window) in windows where placedFrames[kind] == nil { placedFrames[kind] = window.frame }
        applied += repositionDetachedPanels(screens: screens, primaryID: primary)
        persist()
        if topologyChanged, let started = topologyObservedAt {
            let elapsed = now() - started
            topologyObservedAt = nil
            lastTopologyRecoverySeconds = elapsed
            lastTopologyRecoveryMoves = applied
            placementLog.info("topology recovery: \(applied, privacy: .public) window(s) moved, \(Int(elapsed * 1000), privacy: .public) ms after the first signal")
        }
    }

    /// Reconcile all live value-addressed panels. A missing target display is
    /// a temporary recovery: move to the primary display while retaining the
    /// original frame, then restore it when the target returns.
    private func repositionDetachedPanels(screens: [PlacementScreen], primaryID: String?) -> Int {
        var moved = 0
        let primary = screens.first(where: { $0.id == primaryID }) ?? screens.first
        for id in detachedPanels.keys.sorted() {
            guard let panel = detachedPanels[id], let window = panel.window else {
                detachedPanels.removeValue(forKey: id)
                continue
            }
            guard let target = screens.first(where: { $0.id == panel.screenID }) else {
                guard let fallback = primary else { continue }
                if panel.recovery == nil {
                    panel.recovery = PlacementRecovery(screenID: panel.screenID,
                                                       frame: panel.frame,
                                                       manualRevision: panel.manual ? 1 : 0)
                }
                let safe = DisplayPlacementPolicy.clamp(window.frame, to: fallback.visibleFrame)
                applying = true
                if Self.isUserAdjusted(live: window.frame, placed: safe) {
                    applyFrame(safe, to: window)
                    moved += 1
                }
                applying = false
                panel.frame = window.frame
                continue
            }

            let desired: CGRect
            if let recovery = panel.recovery, recovery.screenID == target.id {
                desired = recovery.frame
                panel.recovery = nil
            } else {
                desired = panel.frame
            }
            let safe = DisplayPlacementPolicy.clamp(desired, to: target.visibleFrame)
            applying = true
            if Self.isUserAdjusted(live: window.frame, placed: safe) {
                applyFrame(safe, to: window)
                moved += 1
            }
            applying = false
            panel.frame = window.frame
        }
        return moved
    }

    /// AppKit can nudge a window by a few points while it is restoring a
    /// saved frame (notably a borderless test window at the top of a display).
    /// Re-assert the origin once so the persisted placement contract matches
    /// the visible frame used by the policy and its acceptance receipts.
    private func applyFrame(_ frame: CGRect, to window: NSWindow) {
        window.setFrame(frame, display: true)
        let dx = abs(window.frame.minX - frame.minX)
        let dy = abs(window.frame.minY - frame.minY)
        if dx > Self.frameTolerance || dy > Self.frameTolerance {
            window.setFrameOrigin(frame.origin)
        }
    }

    private func persist() {
        let saved = Saved(records: Dictionary(uniqueKeysWithValues: policy.records.map { ($0.key.rawValue, $0.value) }))
        if let data = try? JSONEncoder().encode(saved) { defaults.set(data, forKey: Self.preferenceKey) }
    }
}
