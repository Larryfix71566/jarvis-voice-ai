import XCTest
import AppKit
import SwiftUI
import JarvisKit
@testable import MortimerHost

private final class SkillsExampleRequestProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var storedPath: String?

    func reset() {
        lock.lock()
        storedPath = nil
        lock.unlock()
    }

    func record(_ path: String) {
        lock.lock()
        storedPath = path
        lock.unlock()
    }

    var path: String? {
        lock.lock()
        defer { lock.unlock() }
        return storedPath
    }
}

private final class SkillsWorkspaceStubURLProtocol: URLProtocol {
    static let exampleRequest = SkillsExampleRequestProbe()
    static let versionsRequest = SkillsExampleRequestProbe()

    override class func canInit(with request: URLRequest) -> Bool { request.url?.path.hasPrefix("/api/skills") == true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url, let body = Self.body(path: url.path) else {
            client?.urlProtocol(self, didFailWithError: URLError(.resourceUnavailable))
            return
        }
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    private static func body(path: String) -> Data? {
        let catalog: [String: Any] = [
            "schema_version": 1,
            "catalog_revision": String(repeating: "a", count: 64),
            "capabilities": ["process_view": true, "activity_trace": true, "authoring": false],
            "items": [[
                "skill_id": "demo-skill", "display_name": "Demo skill",
                "description": "A reviewed skill for rendering the Skills workspace",
                "category": "development", "installation": "installed",
                "revision": String(repeating: "b", count: 64), "enabled": true,
                "readiness": "unknown", "readiness_reasons": ["model_route_compatibility_unverified"],
                "verification": "not_tested",
                "example_ids": ["example-positive"],
            ], [
                "skill_id": "disabled-skill", "display_name": "Disabled skill",
                "description": "A disabled skill for accessibility-state rendering",
                "category": "development", "installation": "installed",
                "revision": String(repeating: "d", count: 64), "enabled": false,
                "readiness": "unknown", "readiness_reasons": ["skill_disabled"],
                "verification": "not_tested", "example_ids": [],
            ]], "next_cursor": NSNull(),
        ]
        let detail: [String: Any] = [
            "schema_version": 1, "skill_id": "demo-skill", "display_name": "Demo skill",
            "description": "A reviewed skill for rendering the Skills workspace",
            "category": "development", "version": "1.0.0",
            "revision": String(repeating: "b", count: 64), "installation": "installed",
            "enabled": true, "readiness": "unknown",
            "readiness_reasons": ["model_route_compatibility_unverified"],
            "verification": "not_tested", "capabilities": [], "required_tools": [],
            "required_credentials": [], "reference_paths": [],
            "example_ids": ["example-positive"],
            "related_workflow_ids": [], "compatible_with": [],
            "source": ["kind": "local", "reference": "synthetic fixture"],
            "process_kind": "linear", "process_nodes": [
                ["step_id": "inspect-request", "title": "Inspect the request",
                 "description": "Identify the goal and constraints.", "inputs": ["User request"],
                 "outputs": ["Scoped task"], "tools": [], "approval": NSNull(),
                 "success_criteria": ["Goal and constraints are clear"],
                 "edges": [["to": "check-result"]]],
                ["step_id": "check-result", "title": "Check the result",
                 "description": "Verify the completed work against the request.",
                 "inputs": ["Scoped task"], "outputs": ["Verified result"], "tools": [],
                 "approval": NSNull(), "success_criteria": ["Checks pass"], "edges": []],
            ],
        ]
        let value: [String: Any]
        if path == "/api/skills" { value = catalog }
        else if path == "/api/skills/demo-skill" { value = detail }
        else if path == "/api/skills/demo-skill/examples/example-positive" {
            Self.exampleRequest.record(path)
            value = [
                "schema_version": 1, "skill_id": "demo-skill",
                "example_id": "example-positive", "synthetic": true,
                "request": "Review the sample repository status.",
                "expect_selected": true,
            ]
        }
        else if path == "/api/skills/demo-skill/versions" {
            Self.versionsRequest.record(path)
            value = [
                "schema_version": 1,
                "skill_id": "demo-skill",
                "installed": [
                    "declared_version": "1.0.0",
                    "package_revision": String(repeating: "b", count: 64),
                    "enabled": true,
                ],
                "registry": [
                    "schema_version": 2,
                    "active_pin": String(repeating: "b", count: 64),
                    "pin_state": "matches_installed",
                ],
                "candidates": [[
                    "request_id": "request-candidate-1",
                    "operation": "request_activation",
                    "state": "awaiting_review",
                    "candidate_revision": String(repeating: "c", count: 64),
                    "review_artifact_operation": "request_activation",
                ]],
            ]
        }
        else { return nil }
        return try? JSONSerialization.data(withJSONObject: value)
    }
}

@MainActor
final class SkillsWorkspaceRenderingTests: XCTestCase {
    func testSkillDetailTransferRequiresAnotherDisplayAndKeepsSingleScreenInline() {
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.canTransferToSupportingDisplay(screenCount: 1))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.canTransferToSupportingDisplay(screenCount: 2))
    }

    func testActivityRefreshKeyTracksReconnectWithoutIncludingFailureDetails() {
        XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityConnectionKey(.offline), "offline")
        XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityConnectionKey(.connecting), "connecting")
        XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityConnectionKey(.connected), "connected")
        XCTAssertNotEqual(
            SkillsWorkspacePresentationPolicy.activityConnectionKey(.offline),
            SkillsWorkspacePresentationPolicy.activityConnectionKey(.connected),
            "a reconnect must change the activity task identity so it retries the trace fetch",
        )
        XCTAssertEqual(
            SkillsWorkspacePresentationPolicy.activityConnectionKey(.failed("token=private")),
            "failed",
            "connection diagnostics must not be copied into the activity task identity",
        )
    }

    private func activityEvent(_ id: String, runID: String, sequence: Int) throws -> SkillActivityEvent {
        let data = try JSONSerialization.data(withJSONObject: [
            "event_id": id, "run_id": runID, "request_id": "request-1",
            "seq": sequence, "schema_version": 1, "occurred_at": "now",
            "type": "skill_step_started", "status": "unknown", "evidence_refs": [],
        ])
        return try JSONDecoder().decode(SkillActivityEvent.self, from: data)
    }

    private func recordedActivityPage(runID: String) throws -> SkillActivityPage {
        let data = try JSONSerialization.data(withJSONObject: [
            "schema_version": 1, "trace_status": "recorded",
            "events": [[
                "event_id": "event-1", "run_id": runID, "request_id": "request-1",
                "seq": 1, "schema_version": 1, "occurred_at": "now",
                "type": "skill_step_started", "status": "unknown", "evidence_refs": [],
            ]],
            "after_seq": 0, "next_after_seq": 1, "has_more": true,
            "truncated": false,
        ])
        return try JSONDecoder().decode(SkillActivityPage.self, from: data)
    }

    func testSharedSkillSwitchClearsPreviousActivityInspection() throws {
        var state = SkillsWorkspaceActivityState(skillID: "skill-old")
        let event = try activityEvent("event-1", runID: "run-old", sequence: 1)
        state.runs = try JSONDecoder().decode([SkillRunSummary].self, from: JSONSerialization.data(withJSONObject: [[
            "run_id": "run-old", "agent": "test", "display_name": "Test run",
            "status": "completed", "started_at": "now",
        ]]))
        state.selectedRunID = "run-old"
        state.page = try recordedActivityPage(runID: "run-old")
        state.events = [event]
        state.hasMore = true
        state.loadedRunID = "run-old"
        state.error = "stale retry error"
        state.retryLoadsMore = true

        // Shared navigation uses this same transition when the selected skill
        // changes, so no prior skill's run or trace can remain visible.
        state.selectSkill("skill-new")

        XCTAssertEqual(state.skillID, "skill-new")
        XCTAssertTrue(state.runs.isEmpty)
        XCTAssertNil(state.selectedRunID)
        XCTAssertNil(state.page)
        XCTAssertTrue(state.events.isEmpty)
        XCTAssertFalse(state.hasMore)
        XCTAssertNil(state.loadedRunID)
        XCTAssertNil(state.error)
        XCTAssertFalse(state.retryLoadsMore)
    }

    func testSelectingSameSkillPreservesActivityInspection() throws {
        var state = SkillsWorkspaceActivityState(skillID: "skill-same")
        state.selectedRunID = "run-same"
        state.events = [try activityEvent("event-same", runID: "run-same", sequence: 1)]
        state.loadedRunID = "run-same"

        state.selectSkill("skill-same")

        XCTAssertEqual(state.selectedRunID, "run-same")
        XCTAssertEqual(state.events.map(\.eventID), ["event-same"])
        XCTAssertEqual(state.loadedRunID, "run-same")
    }

    func testActivityMergeDeduplicatesEventIDsAndKeepsExistingEvidence() throws {
        let existing = try activityEvent("e1", runID: "run-1", sequence: 1)
        let duplicate = try activityEvent("e1", runID: "run-1", sequence: 3)
        let next = try activityEvent("e2", runID: "run-1", sequence: 2)

        let merged = SkillsWorkspaceView.mergeActivityEvents(
            [existing], with: [duplicate, next], selectedRunID: "run-1",
        )

        XCTAssertEqual(merged.map(\.eventID), ["e1", "e2"])
        XCTAssertEqual(merged.map(\.sequence), [1, 2])
    }

    func testActivityMergeExcludesEventsFromOtherRuns() throws {
        let selected = try activityEvent("selected", runID: "run-1", sequence: 1)
        let other = try activityEvent("other", runID: "run-2", sequence: 2)

        let merged = SkillsWorkspaceView.mergeActivityEvents(
            [other], with: [selected], selectedRunID: "run-1",
        )

        XCTAssertEqual(merged.map(\.eventID), ["selected"])
    }

    func testActivityMergeSortsOutOfOrderPagesIntoStrictSequenceOrder() throws {
        let existing = try activityEvent("e2", runID: "run-1", sequence: 2)
        let unseenEarlier = try activityEvent("e1", runID: "run-1", sequence: 1)
        let later = try activityEvent("e3", runID: "run-1", sequence: 3)

        let merged = SkillsWorkspaceView.mergeActivityEvents(
            [existing], with: [later, unseenEarlier], selectedRunID: "run-1",
        )

        XCTAssertEqual(merged.map(\.eventID), ["e1", "e2", "e3"])
        XCTAssertEqual(merged.map(\.sequence), [1, 2, 3])
        XCTAssertTrue(zip(merged, merged.dropFirst()).allSatisfy { $0.sequence < $1.sequence })
    }

    func testActivityEmptyStateDoesNotInventCompletionForMissingTrace() {
        XCTAssertEqual(
            SkillsWorkspaceView.activityEmptyTitle(traceStatus: "unavailable"),
            "No skill trace recorded",
        )
        XCTAssertTrue(
            SkillsWorkspaceView.activityEmptyDescription(traceStatus: "unavailable")
                .contains("unknown, not completed"),
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEmptyTitle(traceStatus: "recorded"),
            "No events on this page",
        )
    }

    func testActivityResponseFromAStaleOrCancelledRunCannotReplaceSelection() {
        XCTAssertTrue(SkillsWorkspaceView.activityResponseIsCurrent(
            requestedRunID: "run-2", selectedRunID: "run-2",
            requestedGeneration: 4, selectedGeneration: 4, taskCancelled: false,
        ))
        XCTAssertFalse(SkillsWorkspaceView.activityResponseIsCurrent(
            requestedRunID: "run-1", selectedRunID: "run-2",
            requestedGeneration: 4, selectedGeneration: 4, taskCancelled: false,
        ))
        XCTAssertFalse(SkillsWorkspaceView.activityResponseIsCurrent(
            requestedRunID: "run-2", selectedRunID: nil,
            requestedGeneration: 4, selectedGeneration: 4, taskCancelled: false,
        ))
        XCTAssertFalse(SkillsWorkspaceView.activityResponseIsCurrent(
            requestedRunID: "run-2", selectedRunID: "run-2",
            requestedGeneration: 4, selectedGeneration: 4, taskCancelled: true,
        ))
    }

    func testActivityResponseFromEarlierSameRunSelectionIsRejectedAfterAtoBtoA() {
        var state = SkillsWorkspaceActivityState(skillID: "skill-a")
        state.selectRun("run-a")
        let requestedGeneration = state.selectionGeneration

        state.selectRun("run-b")
        state.selectRun("run-a")

        XCTAssertEqual(state.selectedRunID, "run-a")
        XCTAssertFalse(SkillsWorkspaceView.activityResponseIsCurrent(
            requestedRunID: "run-a", selectedRunID: state.selectedRunID,
            requestedGeneration: requestedGeneration,
            selectedGeneration: state.selectionGeneration,
            taskCancelled: false,
        ))
    }

    func testActivityExplainsToolObservationWithoutClaimingStepCompletion() {
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: true,
                stepTitle: "Retrieve conditions",
            ),
            "Tool call started for: Retrieve conditions",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_finished", hasToolCallEvidence: true,
                stepTitle: "Retrieve conditions", status: "unknown",
            ),
            "Tool call returned for: Retrieve conditions",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventStatus(
                eventType: "skill_step_finished", status: "unknown",
                hasToolCallEvidence: true,
            ),
            "Step outcome not validated",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_finished", hasToolCallEvidence: false,
                stepTitle: "Review result", status: "unknown",
            ),
            "Outcome unknown for: Review result",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_finished", hasToolCallEvidence: true,
                stepTitle: "Retrieve conditions", status: "failed",
            ),
            "Tool call failed for: Retrieve conditions",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_finished", hasToolCallEvidence: false,
                stepTitle: "Review result", status: "failed",
            ),
            "Failed: Review result",
        )
    }

    func testActivityHistoricalStepUsesIDInsteadOfCurrentRevisionTitle() {
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: false,
                stepTitle: nil, stepID: "retrieve-conditions",
            ),
            "Process step started: retrieve-conditions",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: "0123456789abcdef", detailRevision: "fedcba9876543210",
                hasStep: true,
            ),
            " · Historical package 01234567",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: "0123456789abcdef", detailRevision: "0123456789abcdef",
                hasStep: true,
            ),
            "",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: nil, detailRevision: "0123456789abcdef", hasStep: true,
            ),
            " · Package revision unavailable",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: "0123456789abcdef", detailRevision: nil, hasStep: false,
            ),
            "",
        )
    }

    func testActivityHistoricalStepUsesOpaqueIDAndRevisionInsteadOfCurrentTitle() {
        let historicalRevision = String(repeating: "a", count: 64)
        let currentRevision = String(repeating: "b", count: 64)

        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: false,
                stepTitle: nil, stepID: "inspect-request",
            ),
            "Process step started: inspect-request",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: historicalRevision, detailRevision: currentRevision,
                hasStep: true,
            ),
            " · Historical package aaaaaaaa",
        )
    }

    func testActivityFallbackDoesNotRenderUntrustedStepIDText() {
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: false,
                stepTitle: nil, stepID: "private task text: token=secret",
            ),
            "Process step started",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: false,
                stepTitle: nil, stepID: String(repeating: "a", count: 65),
            ),
            "Process step started",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityEventTitle(
                eventType: "skill_step_started", hasToolCallEvidence: false,
                stepTitle: nil, stepID: "retrieve-conditions",
            ),
            "Process step started: retrieve-conditions",
        )
    }

    func testActivityCurrentStepAndNonStepEventsAvoidUnnecessaryRevisionLabel() {
        let revision = String(repeating: "c", count: 64)

        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: revision, detailRevision: revision, hasStep: true,
            ),
            "",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: nil, detailRevision: revision, hasStep: false,
            ),
            "",
        )
        XCTAssertEqual(
            SkillsWorkspaceView.activityRevisionLabel(
                eventRevision: nil, detailRevision: revision, hasStep: true,
            ),
            " · Package revision unavailable",
        )
    }

    override func setUp() {
        super.setUp()
        SkillsWorkspaceStubURLProtocol.exampleRequest.reset()
        SkillsWorkspaceStubURLProtocol.versionsRequest.reset()
        URLProtocol.registerClass(SkillsWorkspaceStubURLProtocol.self)
    }

    override func tearDown() {
        URLProtocol.unregisterClass(SkillsWorkspaceStubURLProtocol.self)
        super.tearDown()
    }

    func testLibraryAndSelectedProcessStepRenderAtWideAndNarrowWidths() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        for (width, height) in [(1280, 800), (720, 800)] {
            let skills = SkillsStore()
            let workspace = WorkspaceStore()
            let display = DisplayWindowStore()
            let drawer = DrawerState()
            let view = NSHostingView(rootView: SkillsWorkspaceView()
                .environmentObject(client).environment(skills).environment(workspace)
                .environment(display).environment(drawer)
                .preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: width, height: height)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                                  backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.orderFrontRegardless()
            defer { closeRenderingFixtureWindow(window) }
            let loaded = expectation(description: "catalog loads with no implicit skill selection")
            Task { @MainActor in
                let deadline = Date().addingTimeInterval(4)
                while skills.catalogInventory.isEmpty && Date() < deadline {
                    try? await Task.sleep(for: .milliseconds(20))
                }
                loaded.fulfill()
            }
            wait(for: [loaded], timeout: 5)
            XCTAssertEqual(skills.catalogInventory.count, 2)
            XCTAssertNil(skills.selectedSkillID, "opening Skills must land on the library, not auto-open the first card")
            view.layoutSubtreeIfNeeded()
            var cardAccessibilityValues: [String] = []
            var enabledCardControl: NSObject?
            var controlAccessibilityLabels: [String] = []
            var visitedAXElements = Set<ObjectIdentifier>()
            func collectCardValues(_ value: Any) {
                guard let element = value as? NSObject,
                      visitedAXElements.insert(ObjectIdentifier(element)).inserted else { return }
                let labelSelector = NSSelectorFromString("accessibilityLabel")
                if element.responds(to: labelSelector),
                   let label = element.perform(labelSelector)?.takeUnretainedValue() as? String {
                    controlAccessibilityLabels.append(label)
                }
                let valueSelector = NSSelectorFromString("accessibilityValue")
                if element.responds(to: valueSelector),
                   let accessibilityValue = element.perform(valueSelector)?.takeUnretainedValue() as? String {
                    cardAccessibilityValues.append(accessibilityValue)
                    if accessibilityValue == "Enabled",
                       element.responds(to: NSSelectorFromString("accessibilityPerformPress")) {
                        enabledCardControl = element
                    }
                }
                let childrenSelector = NSSelectorFromString("accessibilityChildren")
                if element.responds(to: childrenSelector),
                   let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                    for child in children { collectCardValues(child) }
                }
            }
            func inspectNativeAccessibility(_ current: NSView) {
                collectCardValues(current)
                for subview in current.subviews { inspectNativeAccessibility(subview) }
            }
            inspectNativeAccessibility(view)
            XCTAssertTrue(cardAccessibilityValues.contains("Enabled"),
                          "enabled catalog cards must expose their state to accessibility clients")
            XCTAssertTrue(cardAccessibilityValues.contains("Disabled"),
                          "disabled catalog cards must expose their state to accessibility clients")
            XCTAssertTrue(controlAccessibilityLabels.contains("Search skills by name, purpose, or category"),
                          "the skill search field must have a purpose-specific accessibility name")
            XCTAssertTrue(controlAccessibilityLabels.contains(where: { $0.contains("Filter skills by state") }),
                          "the installation-state picker must expose its purpose in the native accessibility name")
            XCTAssertTrue(controlAccessibilityLabels.contains(where: { $0.contains("Filter skills by category") }),
                          "the category picker must expose its purpose in the native accessibility name")
            let libraryBitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: libraryBitmap)
            let libraryOutput = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(".build/interface-fixtures/skills-library-\(width).png")
            try FileManager.default.createDirectory(at: libraryOutput.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try XCTUnwrap(libraryBitmap.representation(using: .png, properties: [:])).write(to: libraryOutput)
            // Exercise the actual catalog button, not a direct store mutation:
            // the stable row must retain its action as well as its pixels.
            let button = try XCTUnwrap(enabledCardControl)
            let press = NSSelectorFromString("accessibilityPerformPress")
            typealias Press = @convention(c) (AnyObject, Selector) -> Bool
            XCTAssertTrue(unsafeBitCast(button.method(for: press), to: Press.self)(button, press))
            XCTAssertEqual(skills.selectedSkillID, "demo-skill")
            let detailLoaded = expectation(description: "selected skill detail loads")
            Task { @MainActor in
                let deadline = Date().addingTimeInterval(4)
                while (skills.processInventoryBySkill["demo-skill"]?.count ?? 0) != 2 && Date() < deadline {
                    try? await Task.sleep(for: .milliseconds(20))
                }
                detailLoaded.fulfill()
            }
            wait(for: [detailLoaded], timeout: 5)
            XCTAssertEqual(skills.selectedSkillID, "demo-skill")
            XCTAssertEqual(skills.processInventoryBySkill["demo-skill"]?.count, 2)

            skills.selectTab("process")
            skills.selectStep("inspect-request")
            let deadline = Date().addingTimeInterval(1)
            while Date() < deadline {
                view.layoutSubtreeIfNeeded()
                RunLoop.main.run(until: Date().addingTimeInterval(0.02))
            }
            XCTAssertEqual(skills.selectedStepID, "inspect-request")
            XCTAssertEqual(skills.selectedTab, "process")
            var selectedStepAXValues: [String] = []
            func collectSelectedStep(_ value: Any) {
                guard let element = value as? NSObject else { return }
                let labelSelector = NSSelectorFromString("accessibilityLabel")
                let label = element.responds(to: labelSelector)
                    ? element.perform(labelSelector)?.takeUnretainedValue() as? String
                    : nil
                if label?.contains("Inspect the request") == true,
                   element.responds(to: NSSelectorFromString("accessibilityValue")),
                   let state = element.perform(NSSelectorFromString("accessibilityValue"))?.takeUnretainedValue() as? String {
                    selectedStepAXValues.append(state)
                }
                let childrenSelector = NSSelectorFromString("accessibilityChildren")
                if element.responds(to: childrenSelector),
                   let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                    for child in children { collectSelectedStep(child) }
                }
            }
            collectSelectedStep(view)
            XCTAssertTrue(selectedStepAXValues.contains("Expanded"),
                          "The selected process step must expose its expanded state to accessibility clients")
            let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let output = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(".build/interface-fixtures/skills-\(width).png")
            try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: output)
        }
    }

    func testAccessibilitySizeEnvironmentKeepsProcessDetailsExposedInCompactLayout() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let skills = SkillsStore()
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let drawer = DrawerState()
        let view = NSHostingView(rootView: SkillsWorkspaceView()
            .environmentObject(client).environment(skills).environment(workspace)
            .environment(display).environment(drawer)
            .dynamicTypeSize(.accessibility5)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 720, height: 900)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }

        let loaded = expectation(description: "large-text catalog loads")
        Task { @MainActor in
            let deadline = Date().addingTimeInterval(4)
            while skills.catalogInventory.isEmpty && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            loaded.fulfill()
        }
        wait(for: [loaded], timeout: 5)
        XCTAssertTrue(skills.selectSkill("demo-skill"))
        let detailLoaded = expectation(description: "large-text skill detail loads")
        Task { @MainActor in
            let deadline = Date().addingTimeInterval(4)
            while (skills.processInventoryBySkill["demo-skill"]?.count ?? 0) != 2
                && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            detailLoaded.fulfill()
        }
        wait(for: [detailLoaded], timeout: 5)
        skills.selectTab("process")
        skills.selectStep("inspect-request")
        view.layoutSubtreeIfNeeded()

        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let output = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures/skills-accessibility-large.png")
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: output)

        var labels: [String] = []
        func collectLabels(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String {
                labels.append(label)
            }
            let valueSelector = NSSelectorFromString("accessibilityValue")
            if element.responds(to: valueSelector),
               let value = element.perform(valueSelector)?.takeUnretainedValue() as? String {
                labels.append(value)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                for child in children { collectLabels(child) }
            }
        }
        collectLabels(view)
        XCTAssertTrue(labels.contains(where: { $0.contains("Inspect the request") }))
        XCTAssertTrue(labels.contains(where: { $0.contains("Check the result") }))
        XCTAssertTrue(labels.contains(where: { $0.contains("Process") }),
                      "The active skill detail tab must be exposed to accessibility clients")
    }

    func testCreatorSheetRendersItsShortLivedBriefForm() throws {
        _ = NSApplication.shared
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let view = NSHostingView(rootView: SkillCreatorSheet(
            client: client, catalogRevision: String(repeating: "a", count: 64)
        ).preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 560, height: 540)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let output = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures/skills-creator-form.png")
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: output)
        XCTAssertGreaterThan(try Data(contentsOf: output).count, 10_000)
    }

    func testDeclaredSyntheticExampleFetchesAndRendersInSelectedSkillOverview() throws {
        _ = NSApplication.shared
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let skills = SkillsStore()
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let drawer = DrawerState()
        let view = NSHostingView(rootView: SkillsWorkspaceView()
            .environmentObject(client).environment(skills).environment(workspace)
            .environment(display).environment(drawer)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 1280, height: 800)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }

        let loaded = expectation(description: "synthetic catalog and detail load")
        Task { @MainActor in
            let deadline = Date().addingTimeInterval(5)
            while skills.catalogInventory.isEmpty && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            guard skills.selectSkill("demo-skill") else {
                loaded.fulfill()
                return
            }
            while skills.processInventoryBySkill["demo-skill"] == nil && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            skills.selectTab("overview")
            _ = skills.selectExample("example-positive")
            while SkillsWorkspaceStubURLProtocol.exampleRequest.path == nil && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            loaded.fulfill()
        }
        wait(for: [loaded], timeout: 6)
        XCTAssertEqual(SkillsWorkspaceStubURLProtocol.exampleRequest.path,
                       "/api/skills/demo-skill/examples/example-positive")

        let renderDeadline = Date().addingTimeInterval(0.5)
        while Date() < renderDeadline {
            view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        }
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let output = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures/skills-example-preview.png")
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: output)
        XCTAssertGreaterThan(try Data(contentsOf: output).count, 10_000)
    }

    func testVersionsViewSeparatesInstalledPinFromCandidateAndDisclaimsHistory() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
        let skills = SkillsStore()
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let drawer = DrawerState()
        let view = NSHostingView(rootView: SkillsWorkspaceView()
            .environmentObject(client).environment(skills).environment(workspace)
            .environment(display).environment(drawer)
            .preferredColorScheme(.dark))
        view.frame = NSRect(x: 0, y: 0, width: 1280, height: 800)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }

        let loaded = expectation(description: "catalog, detail and version evidence load")
        Task { @MainActor in
            let deadline = Date().addingTimeInterval(5)
            while skills.catalogInventory.isEmpty && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            guard skills.selectSkill("demo-skill") else {
                loaded.fulfill()
                return
            }
            while skills.processInventoryBySkill["demo-skill"] == nil && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            skills.selectTab("versions")
            while SkillsWorkspaceStubURLProtocol.versionsRequest.path == nil && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            loaded.fulfill()
        }
        wait(for: [loaded], timeout: 6)
        XCTAssertEqual(SkillsWorkspaceStubURLProtocol.versionsRequest.path,
                       "/api/skills/demo-skill/versions")

        let renderDeadline = Date().addingTimeInterval(0.5)
        while Date() < renderDeadline {
            view.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        }
        var labels: [String] = []
        func collectLabels(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            if element.responds(to: labelSelector),
               let label = element.perform(labelSelector)?.takeUnretainedValue() as? String {
                labels.append(label)
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                for child in children { collectLabels(child) }
            }
        }
        collectLabels(view)
        let accessibleText = labels.joined(separator: " ")
        XCTAssertTrue(accessibleText.contains("Manifest version"))
        XCTAssertTrue(accessibleText.contains("1.0.0"))
        XCTAssertTrue(accessibleText.contains("matches_installed"))
        XCTAssertTrue(accessibleText.contains("Candidate request evidence"))
        XCTAssertTrue(accessibleText.contains("request-candidate-1"))

        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let output = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent(".build/interface-fixtures/skills-versions.png")
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        try XCTUnwrap(bitmap.representation(using: .png, properties: [:])).write(to: output)
        XCTAssertGreaterThan(try Data(contentsOf: output).count, 10_000)
    }

}
