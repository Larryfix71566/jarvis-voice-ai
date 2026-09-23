import Foundation

/// A display as placement sees it: a persistent identity and its work area
/// in AppKit points. Backing scale is deliberately not part of it — frames
/// are points on every display, so mixed-scale setups need no pixel clamp
/// (closure C4.2, gap G17).
struct PlacementScreen: Equatable {
    let id: String
    let visibleFrame: CGRect
    /// The display macOS currently designates as the main display. This is
    /// the default console role; an explicit user move can still override it
    /// through a persisted manual placement record.
    let isMain: Bool

    init(id: String, visibleFrame: CGRect, isMain: Bool = false) {
        self.id = id
        self.visibleFrame = visibleFrame
        self.isMain = isMain
    }
}

struct PlacementRecovery: Codable, Equatable {
    let screenID: String
    let frame: CGRect
    let manualRevision: Int
}

struct PlacementRecord: Codable, Equatable {
    var screenID: String
    var frame: CGRect
    var manual: Bool
    var manualRevision = 0
    var recovery: PlacementRecovery?
}

/// Pure topology and user-intent policy. Only existing windows are inputs;
/// this layer cannot create windows, subscribe to results or restart audio.
struct DisplayPlacementPolicy {
    var records: [HostWindowKind: PlacementRecord] = [:]
    private var workAreas: [String: CGRect] = [:]

    static func valid(_ rect: CGRect) -> Bool {
        rect.minX.isFinite && rect.minY.isFinite && rect.width.isFinite && rect.height.isFinite
            && rect.width > 0 && rect.height > 0 && rect.width < 100_000 && rect.height < 100_000
            && abs(rect.minX) < 1_000_000 && abs(rect.minY) < 1_000_000
    }

    /// Require a reachable title bar, not merely a sliver of the window body.
    static func reachable(_ frame: CGRect, screens: [PlacementScreen]) -> Bool {
        guard valid(frame) else { return false }
        let title = CGRect(x: frame.minX, y: frame.maxY - 28, width: frame.width, height: 28)
        return screens.contains { screen in
            let intersection = title.intersection(screen.visibleFrame)
            return intersection.width >= min(160, frame.width) && intersection.height >= 24
        }
    }

    static func clamp(_ frame: CGRect, to area: CGRect) -> CGRect {
        let width = min(area.width, max(300, valid(frame) ? frame.width : 900))
        let height = min(area.height, max(200, valid(frame) ? frame.height : 600))
        return CGRect(x: min(area.maxX - width, max(area.minX, frame.minX.isFinite ? frame.minX : area.minX)),
                      y: min(area.maxY - height, max(area.minY, frame.minY.isFinite ? frame.minY : area.minY)),
                      width: width, height: height)
    }

    static func screen(for frame: CGRect, in screens: [PlacementScreen]) -> PlacementScreen? {
        let best = screens.max {
            let a = frame.intersection($0.visibleFrame), b = frame.intersection($1.visibleFrame)
            return max(0, a.width) * max(0, a.height) < max(0, b.width) * max(0, b.height)
        }
        guard let best, !frame.intersection(best.visibleFrame).isEmpty else { return nil }
        return best
    }

    mutating func noteManual(_ kind: HostWindowKind, frame: CGRect, screens: [PlacementScreen]) {
        guard Self.valid(frame), let screen = Self.screen(for: frame, in: screens) else { return }
        records[kind] = PlacementRecord(screenID: screen.id, frame: frame, manual: true,
                                        manualRevision: (records[kind]?.manualRevision ?? 0) + 1)
    }

    /// Docking or closing is newer intent than an earlier unplug recovery.
    mutating func noteClosed(_ kind: HostWindowKind) {
        guard var record = records[kind] else { return }
        record.recovery = nil; record.manualRevision += 1
        records[kind] = record
    }

    mutating func reconcile(windows: [HostWindowKind: CGRect], screens rawScreens: [PlacementScreen],
                            primaryID: String?, restoring: Set<HostWindowKind> = []) -> [HostWindowKind: CGRect] {
        // Mirrored work areas count once. IDs remain the persistent identity.
        var screens: [PlacementScreen] = []
        for screen in rawScreens.sorted(by: { $0.id < $1.id }) where Self.valid(screen.visibleFrame) {
            if !screens.contains(where: { $0.id == screen.id || $0.visibleFrame == screen.visibleFrame }) { screens.append(screen) }
        }
        let consoleRecovery = records[.console]?.recovery
        let restoringConsole = consoleRecovery.flatMap { recovery in
            screens.first { $0.id == recovery.screenID && recovery.manualRevision == records[.console]?.manualRevision
                && (recovery.screenID != records[.console]?.screenID || $0.visibleFrame.contains(recovery.frame)) }
        }
        guard let primary = restoringConsole ?? screens.first(where: { $0.id == primaryID }) ?? screens.first else { return [:] }
        let changedAreas = Set(screens.filter { workAreas[$0.id] != nil && workAreas[$0.id] != $0.visibleFrame }.map(\.id))
        defer { workAreas = Dictionary(uniqueKeysWithValues: screens.map { ($0.id, $0.visibleFrame) }) }
        let external = screens.filter { $0.id != primary.id }
        let ids = Set(screens.map(\.id))
        let auxiliaries = [HostWindowKind.display, .drawer].filter { windows[$0] != nil }
        var assigned: [HostWindowKind: PlacementScreen] = [:]
        for kind in auxiliaries {
            if let preferred = records[kind]?.screenID,
               let screen = external.first(where: { $0.id == preferred }),
               !assigned.values.contains(where: { $0.id == screen.id }) { assigned[kind] = screen }
        }
        for kind in auxiliaries where assigned[kind] == nil {
            assigned[kind] = external.first(where: { screen in !assigned.values.contains { $0.id == screen.id } }) ?? external.first
        }
        var moves: [HostWindowKind: CGRect] = [:]
        for kind in HostWindowKind.allCases {
            guard let live = windows[kind] else { continue }
            var record = records[kind]
            if let recovery = record?.recovery, recovery.manualRevision == record?.manualRevision,
               let destination = screens.first(where: { $0.id == recovery.screenID }),
               recovery.screenID != record?.screenID || destination.visibleFrame.contains(recovery.frame) {
                let restored = Self.clamp(recovery.frame, to: destination.visibleFrame)
                record?.frame = restored; record?.screenID = destination.id; record?.recovery = nil
                records[kind] = record; moves[kind] = restored
                continue
            }
            if restoring.contains(kind), let existing = record, existing.manual,
               let destination = screens.first(where: { $0.id == existing.screenID }) {
                let restored = Self.clamp(existing.frame, to: destination.visibleFrame)
                record?.frame = restored; records[kind] = record; moves[kind] = restored
                continue
            }
            if let existing = record, changedAreas.contains(existing.screenID),
               let destination = screens.first(where: { $0.id == existing.screenID }),
               existing.manual && !destination.visibleFrame.contains(live) {
                let safe = Self.clamp(live, to: destination.visibleFrame)
                record?.recovery = PlacementRecovery(screenID: existing.screenID, frame: existing.frame, manualRevision: existing.manualRevision)
                record?.frame = safe; records[kind] = record; moves[kind] = safe
                continue
            }
            if let existing = record, !ids.contains(existing.screenID) {
                let safe = Self.clamp(live, to: primary.visibleFrame)
                if record?.recovery == nil {
                    record?.recovery = PlacementRecovery(screenID: existing.screenID, frame: existing.frame, manualRevision: existing.manualRevision)
                }
                record?.frame = safe; record?.screenID = primary.id
                records[kind] = record; moves[kind] = safe
                continue
            }
            if !Self.reachable(live, screens: screens) {
                let destination = screens.first(where: { $0.id == record?.screenID }) ?? primary
                let safe = Self.clamp(live, to: destination.visibleFrame)
                if record == nil { record = PlacementRecord(screenID: destination.id, frame: safe, manual: false) }
                record?.frame = safe; record?.screenID = destination.id
                records[kind] = record; moves[kind] = safe
                continue
            }
            // Recovered content stays put until its original display returns
            // or a genuine manual move supersedes the recovery record.
            if record?.manual == true || record?.recovery != nil {
                continue
            }
            if kind == .console || external.isEmpty {
                if record == nil {
                    // A new or reset layout always puts the console on the
                    // selected primary display. This prevents a stale
                    // AppKit-restored frame on an auxiliary screen from
                    // inverting the console/display roles. Once the user
                    // drags the console, noteManual persists that intent and
                    // the manual branch above preserves it.
                    let destination = primary
                    let safe = Self.clamp(live, to: destination.visibleFrame)
                    records[kind] = PlacementRecord(screenID: destination.id,
                                                    frame: safe,
                                                    manual: false)
                    if live != safe {
                        moves[kind] = safe
                    }
                }
                continue
            }
            guard let destination = assigned[kind] else { continue }
            var frame = destination.visibleFrame
            // Legacy split is only for the two explicitly opened auxiliaries
            // sharing one external screen; it never creates either window.
            if external.count == 1 && auxiliaries.count == 2 {
                let left = kind == .display
                frame.origin.x += left ? 0 : frame.width * 0.6
                frame.size.width *= left ? 0.6 : 0.4
            }
            records[kind] = PlacementRecord(screenID: destination.id, frame: frame, manual: false,
                                            manualRevision: record?.manualRevision ?? 0)
            moves[kind] = frame
        }
        return moves
    }
}
