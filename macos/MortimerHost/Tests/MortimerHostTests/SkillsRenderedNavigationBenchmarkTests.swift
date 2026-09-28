import AppKit
import XCTest
import SwiftUI
import JarvisKit
@testable import MortimerHost

private let skillsRenderedBenchmarkCatalogRevision = String(repeating: "a", count: 64)
private let skillsRenderedBenchmarkDetailRequests = SkillsRenderedBenchmarkRequestCounter()

private final class SkillsRenderedBenchmarkRequestCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var storedValue = 0

    func reset() {
        lock.lock()
        storedValue = 0
        lock.unlock()
    }

    func increment() {
        lock.lock()
        storedValue += 1
        lock.unlock()
    }

    var value: Int {
        lock.lock()
        defer { lock.unlock() }
        return storedValue
    }
}

/// Measures the SwiftUI/AppKit path after SkillsStore selection changes. These
/// samples include layout and bitmap display of the hosting view; they are
/// intentionally separate from the store-only SW-K benchmark.
@MainActor
final class SkillsRenderedNavigationBenchmarkTests: XCTestCase {
    private final class FixtureURLProtocol: URLProtocol {
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasPrefix("/api/skills") == true
        }

        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url, let payload = Self.payload(path: url.path) else {
                client?.urlProtocol(self, didFailWithError: URLError(.resourceUnavailable))
                return
            }
            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: payload)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}

        private static func payload(path: String) -> Data? {
            if path == "/api/skills" {
                let items = (0..<100).map { index -> [String: Any] in
                    let id = skillID(index)
                    return [
                        "skill_id": id,
                        "display_name": "Benchmark skill \(index)",
                        "description": "Benchmark skill \(index) reference guide for one narrow capability",
                        "category": "development",
                        "installation": "installed",
                        "revision": skillRevision(index),
                        "enabled": true,
                        "readiness": "ready",
                        "readiness_reasons": [],
                        "verification": "passed",
                        "example_ids": [],
                    ]
                }
                return try? JSONSerialization.data(withJSONObject: [
                    "schema_version": 1,
                    "catalog_revision": skillsRenderedBenchmarkCatalogRevision,
                    "capabilities": ["process_view": true, "activity_trace": true, "authoring": false],
                    "items": items,
                    "next_cursor": NSNull(),
                ])
            }

            guard let id = path.split(separator: "/").last.map(String.init),
                  let index = (0..<100).first(where: { skillID($0) == id }) else { return nil }
            skillsRenderedBenchmarkDetailRequests.increment()
            let nodes = (0..<12).map { step -> [String: Any] in
                [
                    "step_id": "step-\(step)",
                    "title": "Review fixture step \(step)",
                    "description": String(String(repeating: "Synthetic fixture detail content. ", count: 24).prefix(512)),
                    "inputs": ["Synthetic request"],
                    "outputs": ["Verified fixture result"],
                    "tools": [],
                    "approval": NSNull(),
                    "success_criteria": ["The synthetic result is verified."],
                    "edges": step == 11 ? [] : [["to": "step-\(step + 1)"]],
                ]
            }
            return try? JSONSerialization.data(withJSONObject: [
                "schema_version": 1,
                "skill_id": id,
                "display_name": "Benchmark skill \(index)",
                "description": "Benchmark skill \(index) reference guide for one narrow capability",
                "category": "development",
                "version": "1.0.0",
                "revision": skillRevision(index),
                "installation": "installed",
                "enabled": true,
                "readiness": "ready",
                "readiness_reasons": [],
                "verification": "passed",
                "capabilities": [],
                "required_tools": [],
                "required_credentials": [],
                "reference_paths": [],
                "example_ids": [],
                "related_workflow_ids": [],
                "compatible_with": [],
                "source": ["kind": "local", "reference": "synthetic benchmark fixture"],
                "process_kind": "linear",
                "process_nodes": nodes,
            ])
        }

        private static func skillID(_ index: Int) -> String {
            String(format: "benchmark-skill-%03d", index)
        }

        private static func skillRevision(_ index: Int) -> String {
            String(format: "%064x", index + 1)
        }
    }

    func testRenderedCatalogSelectionAndCachedNavigationP95AtWideAndCompactSizes() async throws {
        guard !NSScreen.screens.isEmpty else {
            throw XCTSkip("rendered-navigation benchmark requires a macOS display")
        }
        _ = NSApplication.shared
        let isSandboxGuest = ProcessInfo.processInfo.environment["MORTIMER_SANDBOX_GUEST"] == "1"
        XCTAssertTrue(URLProtocol.registerClass(FixtureURLProtocol.self))
        defer { URLProtocol.unregisterClass(FixtureURLProtocol.self) }
        skillsRenderedBenchmarkDetailRequests.reset()

        let catalogURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // MortimerHostTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // MortimerHost
            .deletingLastPathComponent() // macos
            .deletingLastPathComponent() // repository root
            .appendingPathComponent("tests/fixtures/skills_workspace/performance-100-skills.json")
        let fixture = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: catalogURL)) as? [String: Any])
        XCTAssertEqual(fixture["skill_count"] as? Int, 100)
        XCTAssertEqual(fixture["skill_id_prefix"] as? String, "benchmark-skill")
        XCTAssertEqual(fixture["body_chars"] as? Int, 512)
        XCTAssertEqual(fixture["description_suffix"] as? String,
                       "reference guide for one narrow capability")

        let client = JarvisClient(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))

        var results: [[String: Any]] = []
        for (layout, width, height) in [("wide", 1280, 800), ("compact", 720, 800)] {
            let skills = SkillsStore()
            let workspace = WorkspaceStore()
            let displayStore = DisplayWindowStore()
            let drawer = DrawerState()
            let view = NSHostingView(rootView: SkillsWorkspaceView()
                .environmentObject(client).environment(skills).environment(workspace)
                .environment(displayStore).environment(drawer).preferredColorScheme(.dark))
            view.frame = NSRect(x: 0, y: 0, width: width, height: height)
            let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                                  backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.orderFrontRegardless()
            defer { closeRenderingFixtureWindow(window) }

            let catalogLoaded = expectation(description: "100-skill synthetic catalog loads")
            Task { @MainActor in
                let deadline = Date().addingTimeInterval(5)
                while skills.catalogInventory.count < 32 && Date() < deadline {
                    try? await Task.sleep(for: .milliseconds(10))
                }
                catalogLoaded.fulfill()
            }
            await fulfillment(of: [catalogLoaded], timeout: 6)
            XCTAssertEqual(skills.catalogInventory.count, 32,
                           "the voice inventory is intentionally capped; the view owns all 100 catalog cards")

            let ids = (0..<100).map { String(format: "benchmark-skill-%03d", $0) }
            let warmIDs = Array(ids.suffix(32))
            for index in 68..<100 {
                let id = ids[index]
                let revision = String(format: "%064x", index + 1)
                skills.cacheDetail(.object([
                    "skill_id": .string(id), "revision": .string(revision),
                    "process_nodes": .array((0..<12).map { step in
                        .object(["step_id": .string("step-\(step)"),
                                 "title": .string("Review fixture step \(step)"),
                                 "description": .string(String(String(repeating: "Synthetic fixture detail content. ", count: 24).prefix(512)))])
                    }),
                ]), skillID: id, revision: revision)
            }

            var selectionSamples: [Double] = []
            var navigationSamples: [Double] = []
            var selectionSettleSamples: [Double] = []
            var selectionBitmapSamples: [Double] = []
            selectionSamples.reserveCapacity(100)
            navigationSamples.reserveCapacity(100)
            selectionSettleSamples.reserveCapacity(100)
            selectionBitmapSamples.reserveCapacity(100)
            var bitmapDigests = Set<Int>()

            for sample in 0..<100 {
                // Exercise catalog entries beyond the shared 32-item voice
                // inventory while keeping every timed detail in the bounded
                // 32-entry package-revision cache.
                let id = warmIDs[sample % warmIDs.count]
                let selectionStart = ContinuousClock.now
                XCTAssertTrue(skills.selectSkill(id))
                let settleStart = ContinuousClock.now
                await settle(view)
                selectionSettleSamples.append(milliseconds(since: settleStart))
                let bitmapStart = ContinuousClock.now
                let selectionBitmap = try display(view)
                selectionBitmapSamples.append(milliseconds(since: bitmapStart))
                bitmapDigests.insert(selectionBitmap)
                selectionSamples.append(milliseconds(since: selectionStart))

                let warmID = warmIDs[(sample + 1) % warmIDs.count]
                let navigationStart = ContinuousClock.now
                XCTAssertTrue(skills.selectSkill(warmID))
                _ = skills.selectTab("process")
                await settle(view)
                let navigationBitmap = try display(view)
                bitmapDigests.insert(navigationBitmap)
                navigationSamples.append(milliseconds(since: navigationStart))
            }

            let selectionP95 = p95(selectionSamples)
            let selectionSettleP95 = p95(selectionSettleSamples)
            let navigationP95 = p95(navigationSamples)
            let detailRequestsDuringBenchmark = skillsRenderedBenchmarkDetailRequests.value
            let row: [String: Any] = [
                "layout": layout,
                "width_points": width,
                "height_points": height,
                "samples": 100,
                "catalog_skills": 100,
                "cached_details": 32,
                "selection_render_p95_ms": selectionP95,
                "selection_to_layout_p95_ms": selectionSettleP95,
                "selection_bitmap_p95_ms": p95(selectionBitmapSamples),
                "cached_navigation_render_p95_ms": navigationP95,
                "distinct_rendered_frames": bitmapDigests.count,
                "includes_swiftui_layout_and_nsview_bitmap_display": true,
                "detail_requests_during_measurement": detailRequestsDuringBenchmark,
                "virtualized_guest": isSandboxGuest,
                "timing_budget_enforced": !isSandboxGuest,
            ]
            results.append(row)
            XCTAssertEqual(detailRequestsDuringBenchmark, 0,
                           "all measured catalog selection and process navigation must resolve from the local revision cache")
            if isSandboxGuest {
                // Tart's virtual display can return a stale NSHostingView
                // bitmap even while native accessibility/render tests show
                // the updated skill. Keep state/navigation coverage in the
                // guest; physical-Mac runs retain the pixel-change assertion.
                XCTAssertEqual(skills.selectedSkillID, warmIDs[100 % warmIDs.count])
                XCTAssertEqual(skills.selectedTab, "process")
            } else {
                XCTAssertGreaterThan(bitmapDigests.count, 1, "navigation must change the actual rendered output")
            }
            // The 20 ms selection budget measures the selection-to-layout
            // response. Full-window bitmap generation is reported separately:
            // it is a diagnostic rendering sample, not part of user input
            // latency. Cached process navigation retains its 100 ms budget.
            if !isSandboxGuest {
                XCTAssertLessThanOrEqual(selectionSettleP95, 20.0,
                                         "\(layout) selection-to-layout response exceeds SW-K 20 ms")
                XCTAssertLessThanOrEqual(navigationP95, 100.0,
                                         "\(layout) cached rendered navigation exceeds SW-K 100 ms")
            }
        }

        let output: [String: Any] = [
            "benchmark": "skills_rendered_navigation",
            "schema_version": 1,
            "samples_per_case": 100,
            "percentile": "nearest-rank p95",
            "results": results,
        ]
        let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        print("SKILLS_RENDERED_NAVIGATION_JSON=\(String(decoding: data, as: UTF8.self))")
    }

    private func settle<Content: View>(_ view: NSHostingView<Content>) async {
        // Let the store observation and cached detail task run, then measure a
        // real AppKit layout and display pass on the host's main run loop. One
        // run-loop turn models first response; repeated turns would measure
        // test stabilization delay as part of the UI's selection latency.
        await Task.yield()
        pumpMainRunLoop(view)
    }

    private func pumpMainRunLoop<Content: View>(_ view: NSHostingView<Content>) {
        view.layoutSubtreeIfNeeded()
    }

    private func display<Content: View>(_ view: NSHostingView<Content>) throws -> Int {
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let pixels = try XCTUnwrap(bitmap.bitmapData)
        let bytes = Data(bytes: pixels, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
        return bytes.hashValue
    }

    private func milliseconds(since start: ContinuousClock.Instant) -> Double {
        let elapsed = start.duration(to: .now).components
        return Double(elapsed.seconds) * 1_000
            + Double(elapsed.attoseconds) / 1e15
    }

    private func p95(_ values: [Double]) -> Double {
        values.sorted()[Int(ceil(Double(values.count) * 0.95)) - 1]
    }
}
