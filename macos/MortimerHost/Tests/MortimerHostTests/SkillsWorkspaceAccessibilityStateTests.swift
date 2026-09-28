import AppKit
import SwiftUI
import XCTest
import JarvisKit
@testable import MortimerHost

/// Exercises the screen-reader state of a process step at the largest supported
/// text size. This complements the normal-size expanded-state check in the
/// rendering suite, without claiming a live VoiceOver acceptance run.
@MainActor
final class SkillsWorkspaceAccessibilityStateTests: XCTestCase {
    private final class SkillsAccessibilityFixtureURLProtocol: URLProtocol {
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasPrefix("/api/skills") == true
        }

        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url, let data = Self.response(for: url.path) else {
                client?.urlProtocol(self, didFailWithError: URLError(.resourceUnavailable))
                return
            }
            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}

        private static func response(for path: String) -> Data? {
            let revision = String(repeating: "a", count: 64)
            let value: [String: Any]
            if path == "/api/skills" {
                value = [
                    "schema_version": 1,
                    "catalog_revision": revision,
                    "capabilities": ["process_view": true, "activity_trace": false, "authoring": false],
                    "items": [[
                        "skill_id": "accessibility-demo", "display_name": "Accessibility demo",
                        "description": "A fixture for large-text process accessibility.",
                        "category": "development", "installation": "installed",
                        "revision": revision, "enabled": true, "readiness": "unknown",
                        "readiness_reasons": [], "verification": "not_tested",
                        "example_ids": [],
                    ]],
                    "next_cursor": NSNull(),
                ]
            } else if path == "/api/skills/accessibility-demo" {
                value = [
                    "schema_version": 1, "skill_id": "accessibility-demo",
                    "display_name": "Accessibility demo",
                    "description": "A fixture for large-text process accessibility.",
                    "category": "development", "version": "1.0.0", "revision": revision,
                    "installation": "installed", "enabled": true, "readiness": "unknown",
                    "readiness_reasons": [], "verification": "not_tested",
                    "capabilities": [], "required_tools": [], "required_credentials": [],
                    "reference_paths": [], "example_ids": [], "related_workflow_ids": [],
                    "compatible_with": [], "source": ["kind": "local", "reference": "fixture"],
                    "process_kind": "linear", "process_nodes": [[
                        "step_id": "inspect", "title": "Inspect the request",
                        "description": "Read the request and identify its constraints.",
                        "inputs": ["Request"], "outputs": ["Scoped task"], "tools": [],
                        "approval": NSNull(), "success_criteria": ["Constraints are clear"],
                        "edges": [],
                    ]],
                ]
            } else {
                return nil
            }
            return try? JSONSerialization.data(withJSONObject: value)
        }
    }

    func testLargeTextProcessStepExposesExpandedStateToAccessibilityClients() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(
            true, forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface")
        )
        URLProtocol.registerClass(SkillsAccessibilityFixtureURLProtocol.self)
        defer { URLProtocol.unregisterClass(SkillsAccessibilityFixtureURLProtocol.self) }

        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"
        ))
        let skills = SkillsStore()
        let workspace = WorkspaceStore()
        let display = DisplayWindowStore()
        let drawer = DrawerState()
        let host = NSHostingView(rootView: SkillsWorkspaceView()
            .environmentObject(client).environment(skills).environment(workspace)
            .environment(display).environment(drawer)
            .dynamicTypeSize(.accessibility5)
            .preferredColorScheme(.dark))
        host.frame = NSRect(x: 0, y: 0, width: 720, height: 900)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = host
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }

        let loaded = expectation(description: "large-text Skills fixture loads")
        Task { @MainActor in
            let deadline = Date().addingTimeInterval(4)
            while skills.catalogInventory.isEmpty && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            guard skills.selectSkill("accessibility-demo") else {
                loaded.fulfill()
                return
            }
            while (skills.processInventoryBySkill["accessibility-demo"]?.count ?? 0) != 1
                    && Date() < deadline {
                try? await Task.sleep(for: .milliseconds(20))
            }
            skills.selectTab("process")
            skills.selectStep("inspect")
            loaded.fulfill()
        }
        wait(for: [loaded], timeout: 5)
        XCTAssertEqual(skills.selectedStepID, "inspect")
        XCTAssertEqual(skills.processInventoryBySkill["accessibility-demo"]?.count, 1)

        let layoutDeadline = Date().addingTimeInterval(0.3)
        while Date() < layoutDeadline {
            host.layoutSubtreeIfNeeded()
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        }

        var state: String?
        func findExpandedStep(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            let valueSelector = NSSelectorFromString("accessibilityValue")
            let label = element.responds(to: labelSelector)
                ? element.perform(labelSelector)?.takeUnretainedValue() as? String
                : nil
            if label?.contains("Inspect the request") == true,
               element.responds(to: valueSelector) {
                state = element.perform(valueSelector)?.takeUnretainedValue() as? String
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                for child in children { findExpandedStep(child) }
            }
        }
        findExpandedStep(host)
        XCTAssertEqual(state, "Expanded",
                       "Large accessibility text must retain the process step's expanded/collapsed state")
    }
}
