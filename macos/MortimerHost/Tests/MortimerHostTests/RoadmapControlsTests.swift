import XCTest
import SwiftUI
@testable import JarvisKit
@testable import MortimerHost


private final class RoadmapTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?
    var sent: [Data] = []
    func connect(config: JarvisConfig) async throws { throw NSError(domain: "RoadmapTransport.NoNetwork", code: 1) }
    func disconnect() async {}
    func send(_ data: Data) throws { sent.append(data) }
    func setMicEnabled(_ enabled: Bool) {}
    func emit(_ message: [String: Any]) throws {
        delegate?.transport(didReceiveFrame: try JSONSerialization.data(withJSONObject: ["id": UUID().uuidString, "label": "rtvi-ai", "type": "server-message", "data": message]))
    }
    var requests: [ConsoleRequest] { sent.compactMap { try? JSONDecoder().decode(ConsoleRequest.self, from: $0) } }
}

@MainActor
final class RoadmapControlsTests: XCTestCase {
    private let zone = "America/New_York"
    private var now: Date { ISO8601DateFormatter().date(from: "2026-10-17T18:00:00Z")! }
    // Current-roadmap wording plus distinct canaries pin ownership, landed vs
    // accepted, historic failures and prerequisite-gated acceptance separately.
    private func payload(revision: String = "a", repository: String = "d", policy: String = "approved_external", timezone: String = "America/New_York", readAt: String = "2026-10-17T18:00:00Z") throws -> DisplayPayload {
        func card(_ id: String, _ owner: String, _ status: String, _ lifecycle: String, _ author: String, _ checklist: [[String: Any]], _ next: String = "") -> [String: Any] {
            ["id": id, "title": "\(id) — Interface \(id)", "status": status, "lifecycle": lifecycle, "owner": owner,
             "fields": ["Owner": owner, "Status": status, "Implemented by": author, "Next step": next, "Scope": "interface"],
             "details": "DETAIL-\(id) " + (id == "WS-01" ? String(repeating: "padding ", count: 4500) : "source details"), "checklist": checklist]
        }
        let cards = [
            card("WS-01", "codex and claude", "landed foundation; acceptance open", "landed", "claude", [
                ["text": "Larry · after deployment, verify display", "checked": false, "section": "Acceptance to close"],
                ["text": "DONE-HIDDEN", "checked": true, "section": "Acceptance to close"]]),
            card("WS-02", "claude", "review; previous blocker resolved", "review", "codex", [
                ["text": "Larry ready now: confirm main stage", "checked": false, "section": "Acceptance"],
                ["text": "Larry general development task", "checked": false, "section": "Implementation"]]),
            card("WS-03", "codex", "in-progress; blocked on external monitor", "in-progress", "claude", [], "Awaiting monitor"),
            card("WS-04", "unassigned", "unclassified current status", "unclassified", "", []),
            card("WS-08", "codex", "accepted by Larry", "accepted", "claude", [])]
        let logs: [[String: Any]] = [("2026-10-11", "WS-01"), ("2026-10-12", "WS-02"), ("2026-10-17", "WS-03"), ("2026-10-18", "WS-08")].map { date, row in
            ["path": "docs/roadmap-log/\(row).md", "date": date, "rows": [row], "sha256": String(repeating: "c", count: 64), "title": "Dated \(row)"]
        }
        let snapshot: [String: Any] = ["schema": "mortimer.roadmap.v1", "provenance": [
            "path": "ROADMAP.md", "repository_id": String(repeating: repository, count: 64), "revision": String(repeating: revision, count: 40),
            "sha256": String(repeating: "b", count: 64), "read_at": readAt, "dirty": false, "source_kind": "local_checkout"],
            "cards": cards, "logs": logs, "issues": ["Malformed log explicitly reported"]]
        let value: [String: Any] = ["title": "Project roadmap", "body": "fallback", "tool": "repo_read_file", "surface": "window", "data_policy": policy, "roadmap_timezone": timezone, "roadmap": snapshot]
        return try JSONDecoder().decode(DisplayPayload.self, from: JSONSerialization.data(withJSONObject: value))
    }
    private func apply(_ args: [String: JSONValue], _ filter: RoadmapFilter = RoadmapFilter()) throws -> RoadmapFilter {
        try XCTUnwrap(filter.applying(args, to: XCTUnwrap(payload().roadmap), timezone: zone, now: now))
    }
    private func ids(_ filter: RoadmapFilter) throws -> [String] { filter.project(try XCTUnwrap(payload().roadmap), timezone: zone).cards.map(\.id) }
    private func coordinator(_ store: WorkspaceStore, sharing: ShareCoordinator? = nil) -> ConsoleActionCoordinator {
        let drawer = DrawerState()
        return ConsoleActionCoordinator(workspace: store, display: DisplayWindowStore(), placement: WindowPlacement(drawer: drawer, windows: WindowActions()), drawer: drawer, sharing: sharing, screens: { [] })
    }
    func testAndOrCurrentOwnersAndHistoricalAuthorsAreSeparate() throws {
        let f = try apply(["operation": .string("replace"), "owners": .array([.string("codex"), .string("claude")]), "states": .array([.string("open")]), "topics": .array([.string("INTERFACE")])])
        XCTAssertEqual(try ids(f), ["WS-01", "WS-02", "WS-03"])
        let narrow = try apply(["operation": .string("refine"), "authors": .array([.string("codex")])], f)
        XCTAssertEqual(try ids(narrow), ["WS-02"])
        XCTAssertEqual(narrow.owners, ["codex", "claude"])
        XCTAssertEqual(try ids(apply(["operation": .string("replace"), "states": .array([.string("completed")])], narrow)), ["WS-08"])
    }
    func testUnknownValuesPreserveStateFocusClearsConflictsAndClearRestoresAll() throws {
        let f = try apply(["operation": .string("replace"), "topics": .array([.string("no matches")])])
        XCTAssertTrue(try ids(f).isEmpty)
        let snapshot = try XCTUnwrap(payload().roadmap)
        for args: [String: JSONValue] in [
            ["operation": .string("focus"), "workstreams": .array([.string("WS-999")])],
            ["operation": .string("replace"), "owners": .array([.string("invented")])],
            ["operation": .string("replace"), "states": .array([.string("merged")])]
        ] { XCTAssertNil(f.applying(args, to: snapshot, timezone: zone)) }
        let focused = try apply(["operation": .string("focus"), "workstreams": .array([.string("WS-08")])], f)
        XCTAssertEqual(try ids(focused), ["WS-08"]); XCTAssertTrue(focused.topics.isEmpty)
        XCTAssertEqual(try ids(apply(["operation": .string("clear")], focused)).count, 5)
    }
    func testCurrentBlockerEvidenceExcludesResolvedHistoryAndReportsOtherMentions() throws {
        let f = try apply(["operation": .string("replace"), "blockers": .bool(true)])
        XCTAssertEqual(try ids(f), ["WS-03"])
        let view = f.project(try XCTUnwrap(payload().roadmap), timezone: zone)
        XCTAssertEqual(view.ambiguousBlockers, ["WS-02"])
        XCTAssertFalse(RoadmapFilter.blockerEvidence(view.cards[0]).isEmpty)
        XCTAssertEqual(view.unclassified, ["WS-04"])
    }
    func testLarryAcceptanceHasExplicitAssignmentAndPrerequisiteLabels() throws {
        let f = try apply(["operation": .string("replace"), "checklist": .string("larry")])
        let snapshot = try XCTUnwrap(payload().roadmap)
        XCTAssertEqual(try ids(f), ["WS-01", "WS-02"])
        XCTAssertEqual(f.visibleChecklist(snapshot.cards[1]).count, 1)
        XCTAssertTrue(RoadmapFilter.readiness(f.visibleChecklist(snapshot.cards[0])[0].text).hasPrefix("Prerequisites"))
        XCTAssertTrue(RoadmapFilter.readiness(f.visibleChecklist(snapshot.cards[1])[0].text).hasPrefix("Ready"))
        XCTAssertTrue(RoadmapFilter.readiness("Larry checks the result").hasPrefix("Readiness not specified"))
        XCTAssertTrue(RoadmapFilter.readiness("Larry: not ready now").hasPrefix("Prerequisites"))
    }
    func testMondayWeekAndRollingSevenDaysAreDistinctAndNeverGuessTimezone() throws {
        let f = try apply(["operation": .string("replace"), "period": .string("this_week")])
        XCTAssertEqual(try ids(f), ["WS-02", "WS-03"])
        let snapshot = try XCTUnwrap(payload().roadmap)
        XCTAssertTrue(f.project(snapshot, timezone: zone).dateLabel!.contains("2026-10-12"))
        let rolling = try apply(["operation": .string("replace"), "period": .string("last_seven_days")])
        XCTAssertEqual(try ids(rolling), ["WS-01", "WS-02", "WS-03"])
        XCTAssertNil(f.applying(["operation": .string("refine")], to: snapshot, timezone: "unknown"))
        XCTAssertTrue(f.project(snapshot, timezone: nil).cards.isEmpty)
        // Sunday evening UTC is still Sunday in New York; next Monday starts
        // at local midnight, not UTC midnight (including DST transition).
        let sunday = ISO8601DateFormatter().date(from: "2026-11-02T04:30:00Z")!
        let dst = try XCTUnwrap(f.applying(["operation": .string("refine")], to: snapshot, timezone: zone, now: sunday))
        XCTAssertTrue(dst.project(snapshot, timezone: zone).dateLabel!.hasPrefix("2026-10-26 – 2026-11-01"))
    }
    func testCompleteLateCardAndFrozenShareContainOnlyFilteredChecklist() throws {
        let store = WorkspaceStore(), sharing = ShareCoordinator()
        let item = WorkspaceResult(payload: try payload()); store.receive(item)
        XCTAssertGreaterThan(item.payload.roadmap!.cards[0].details.count, 30000)
        XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("replace"), "workstreams": .array([.string("WS-02")]), "checklist": .string("remaining")]))
        let preview = try XCTUnwrap(sharing.beginPreview(try XCTUnwrap(store.results.first)))
        XCTAssertTrue(preview.text.contains("Larry ready now"))
        XCTAssertFalse(preview.text.contains("DETAIL-WS-01")); XCTAssertFalse(preview.text.contains("DONE-HIDDEN"))
        XCTAssertTrue(preview.text.contains("workstreams: WS-02"))
        XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("clear")]))
        XCTAssertTrue(store.refreshRoadmap(item.id, payload: try payload(revision: "f")))
        XCTAssertEqual(sharing.preview, preview)
    }
    func testRefreshKeepsIdentityFiltersPinPlacementExpansionAndReadingTime() throws {
        let store = WorkspaceStore(); let item = WorkspaceResult(payload: try payload()); store.receive(item)
        XCTAssertTrue(store.pin(item.id))
        XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("focus"), "workstreams": .array([.string("WS-08")])]))
        XCTAssertTrue(store.sendToDisplay(.result(item.id)))
        let priorFilter = store.results[0].roadmapFilter
        XCTAssertEqual(store.receive(WorkspaceResult(payload: try payload(revision: "f"))), item.id)
        XCTAssertEqual(store.results.count, 1); XCTAssertEqual(store.results[0].receivedAt, item.receivedAt)
        XCTAssertEqual(store.results[0].roadmapFilter.workstreams, priorFilter.workstreams)
        XCTAssertEqual(store.supportingContent, .result(item.id)); XCTAssertTrue(store.pinnedIDs.contains(item.id))
        XCTAssertTrue(store.roadmapExpanded[item.id]!.contains("WS-08"))
        XCTAssertFalse(store.refreshRoadmap(item.id, payload: try payload(revision: "e", readAt: "2026-10-17T17:59:59Z")))
        XCTAssertFalse(store.refreshRoadmap(item.id, payload: try payload(repository: "e")))
        XCTAssertFalse(store.refreshRoadmap(item.id, payload: try payload(policy: "local_only")))
        XCTAssertEqual(store.results[0].payload.roadmap!.provenance.revision, String(repeating: "f", count: 40))
    }
    func testVoiceAndPointerApplySameFilterAndProtectedRoadmapRefuses() throws {
        let store = WorkspaceStore(); let item = WorkspaceResult(payload: try payload()); store.receive(item)
        let coordinator = coordinator(store)
        let args: [String: JSONValue] = ["operation": .string("replace"), "owners": .array([.string("codex")]), "checklist": .string("remaining")]
        XCTAssertEqual(coordinator.executePointer(.roadmapControl, target: item.id.uuidString, args: args), .applied)
        let expected = store.results[0].roadmapFilter
        XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("clear")]))
        XCTAssertEqual(coordinator.execute(ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(), revision: store.consoleRevision, action: .roadmapControl, target: item.id.uuidString, args: args)), .applied)
        XCTAssertEqual(store.results[0].roadmapFilter.owners, expected.owners)
        XCTAssertEqual(store.results[0].roadmapFilter.checklist, expected.checklist)
        let protected = WorkspaceResult(payload: try payload(policy: "confidential")); store.receive(protected)
        XCTAssertEqual(coordinator.executePointer(.roadmapControl, target: protected.id.uuidString, args: args), .invalid)
        XCTAssertNil(ShareCoordinator().beginPreview(protected))
    }
    private func wait(_ condition: @MainActor () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(3)
        while !condition() {
            guard Date() < deadline else { throw NSError(domain: "RoadmapControlsTests.Timeout", code: 1) }
            try await Task.sleep(for: .milliseconds(10))
        }
    }
    func testActualRouterRefreshRetainsPlacementAndRejectsWrongReplyBeforeApplyingSnapshot() async throws {
        _ = NSApplication.shared
        let transport = RoadmapTransport()
        let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:9")!, adminURL: URL(string: "http://127.0.0.1:9")!, wakeWordURL: URL(string: "ws://127.0.0.1:9/ws")!, token: nil)
        let client = JarvisClient(config: config, stubTransport: transport, tokenProvider: { _ in nil })
        let store = WorkspaceStore(), drawer = DrawerState(), display = DisplayWindowStore()
        let coordinator = ConsoleActionCoordinator(workspace: store, display: display, placement: WindowPlacement(drawer: drawer, windows: WindowActions()), drawer: drawer, client: client, screens: { [] })
        let router = AppMessageRouter()
        router.start(client: client, agentRuns: AgentRunStore(), displayResults: DisplayResultStore(), displayWindow: display, workspace: store, conversation: ConversationStore(), drawer: drawer, consoleCoordinator: coordinator)
        defer { router.stop() }
        let session = UUID(), generation = UUID()
        try transport.emit(["type": "console/hello", "version": 1, "session_id": session.uuidString, "generation": generation.uuidString, "actions": ConsoleAction.allCases.map(\.rawValue), "input_types": []])
        try await wait { client.consoleSessionID == session }
        let item = WorkspaceResult(payload: try payload()); store.receive(item)
        XCTAssertTrue(store.pin(item.id)); XCTAssertTrue(store.sendToDisplay(.result(item.id)))
        XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("focus"), "workstreams": .array([.string("WS-02")])]))
        let request = ConsoleRequest(sessionID: session, generation: generation, requestID: UUID(), revision: store.consoleRevision, action: .roadmapControl, target: item.id.uuidString, args: ["operation": .string("refresh")])
        let task = Task { await coordinator.refreshRoadmap(request) }
        try await wait { !transport.requests.isEmpty }
        let pending = try XCTUnwrap(transport.requests.last)
        let replacement = try payload(revision: "f")
        let snapshot = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(replacement.roadmap!))
        let data: JSONValue = .object(["display": .object(["title": .string("Project roadmap"), "body": .string("refreshed"), "roadmap": snapshot, "roadmap_timezone": .string(zone), "data_policy": .string("approved_external")])])
        XCTAssertTrue(coordinator.acceptRoadmapReply(ConsoleResult(sessionID: session, generation: UUID(), requestID: pending.requestID, status: "ok", code: "roadmap_snapshot", summary: "wrong generation", data: data)))
        XCTAssertEqual(store.results[0].payload, item.payload)
        let reply = ConsoleResult(sessionID: session, generation: generation, requestID: pending.requestID, status: "ok", code: "roadmap_snapshot", summary: "read", data: data)
        let wire = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(reply)) as? [String: Any])
        try transport.emit(wire)
        let outcome = await task.value
        XCTAssertEqual(outcome, .applied)
        XCTAssertEqual(store.results.count, 1)
        XCTAssertEqual(store.results[0].payload.roadmap!.provenance.revision, String(repeating: "f", count: 40))
        XCTAssertEqual(store.results[0].roadmapFilter.workstreams, ["WS-02"])
        XCTAssertEqual(store.supportingContent, .result(item.id)); XCTAssertTrue(store.pinnedIDs.contains(item.id))
        // A later ordinary repo-read arrival must also refresh in place,
        // even with a window route, rather than re-selecting the main stage.
        let second = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(snapshot)) as? [String: Any])
        try transport.emit(["type": "display", "display": ["title": "Project roadmap", "body": "ordinary read", "surface": "window", "data_policy": "approved_external", "roadmap": second, "roadmap_timezone": zone]])
        try await wait { store.results[0].payload.body == "ordinary read" }
        XCTAssertEqual(store.supportingContent, .result(item.id)); XCTAssertEqual(store.results.count, 1)
        // Explicit read failure settles without removing prior source/state.
        let failureTask = Task { await coordinator.refreshRoadmap(ConsoleRequest(sessionID: session, generation: generation, requestID: UUID(), revision: store.consoleRevision, action: .roadmapControl, target: item.id.uuidString, args: ["operation": .string("refresh")])) }
        try await wait { transport.requests.count == 2 }
        let failureRequest = try XCTUnwrap(transport.requests.last)
        XCTAssertTrue(coordinator.acceptRoadmapReply(ConsoleResult(sessionID: session, generation: generation, requestID: failureRequest.requestID, status: "error", code: "roadmap_read_failed", summary: "unavailable")))
        let failure = await failureTask.value
        XCTAssertEqual(failure, .invalid)
        XCTAssertEqual(store.results[0].payload.body, "ordinary read")
        XCTAssertTrue(store.roadmapRefreshStatus[item.id]!.contains("stale"))
    }

    func testRenderedCompactAndExpandedRoadmapExposeFilterLabelsAndLateCard() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        for width: CGFloat in [520, 1100] {
            let store = WorkspaceStore(), item = WorkspaceResult(payload: try payload())
            store.receive(item)
            XCTAssertTrue(store.applyRoadmapFilter(item.id, args: ["operation": .string("focus"), "workstreams": .array([.string("WS-08")])]))
            let host = NSHostingView(rootView: RoadmapView(result: store.results[0], coordinator: coordinator(store)).environment(store))
            host.frame = NSRect(x: 0, y: 0, width: width, height: 650)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false; window.contentView = host; window.orderFrontRegardless()
            defer { closeRenderingFixtureWindow(window) }
            window.layoutIfNeeded(); host.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.2))
            var labels: [String] = []
            func visit(_ value: Any) {
                guard let object = value as? NSObject else { return }
                for selector in ["accessibilityLabel", "accessibilityTitle", "accessibilityValue"] {
                    let sel = NSSelectorFromString(selector)
                    if object.responds(to: sel), let raw = object.perform(sel)?.takeUnretainedValue() {
                        labels.append((raw as? String) ?? (raw as? NSAttributedString)?.string ?? "")
                    }
                }
                let children = NSSelectorFromString("accessibilityChildren")
                if object.responds(to: children), let values = object.perform(children)?.takeUnretainedValue() as? [Any] { values.forEach(visit) }
            }
            visit(host)
            let text = labels.joined(separator: "\n")
            XCTAssertTrue(text.contains("Clear filters"), text)
            XCTAssertTrue(text.contains("Refresh"), text)
            XCTAssertTrue(text.contains("WS-08"), text)
            XCTAssertTrue(text.contains("1/5 workstreams"), text)
        }
    }

}
