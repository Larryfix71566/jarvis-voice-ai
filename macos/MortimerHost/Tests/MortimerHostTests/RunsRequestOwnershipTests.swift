import XCTest
import JarvisKit
@testable import MortimerHost

private actor RunsReadCounter {
    var calls = 0
    func record() { calls += 1 }
}

@MainActor
final class RunsRequestOwnershipTests: XCTestCase {
    private var api: AdminAPI {
        AdminAPI(config: JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!, wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "synthetic"))
    }

    func testOldFilterErrorCannotReplaceNewResults() async throws {
        let current = try JSONDecoder().decode(RunsList.self, from: Data(#"{"ok":true,"runs":[{"run_id":"current"}]}"#.utf8))
        let model = RunsViewModel(api: api, fetchList: { _, agent, _ in
            if agent == "old" {
                try? await Task.sleep(nanoseconds: 80_000_000)
                throw JarvisError.unauthorized
            }
            return current
        })
        model.agentFilter = "old"
        try await Task.sleep(nanoseconds: 10_000_000)
        model.agentFilter = "current"
        try await Task.sleep(nanoseconds: 120_000_000)
        guard case .loaded(let rows) = model.state else { return XCTFail("Old authorization failure replaced the newer result") }
        XCTAssertEqual(rows.map(\.runId), ["current"])
        model.startPolling()
        defer { model.stopPolling() }
        await model.refresh()
        guard case .loaded = model.state else { return XCTFail("Current request must still succeed") }
    }

    func testOldDetailCannotReplaceNewSelectionOrReopenClosedDetail() async throws {
        let old = try JSONDecoder().decode(RunDetail.self, from: Data(#"{"ok":true,"run":{"run_id":"old"}}"#.utf8))
        let new = try JSONDecoder().decode(RunDetail.self, from: Data(#"{"ok":true,"run":{"run_id":"new"}}"#.utf8))
        let model = RunsViewModel(api: api, fetchDetail: { _, id in
            if id == "old" { try? await Task.sleep(nanoseconds: 80_000_000); return old }
            return new
        })
        model.loadDetail(runId: "old")
        try await Task.sleep(nanoseconds: 10_000_000)
        model.loadDetail(runId: "new")
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(model.detailRunId, "new")
        XCTAssertEqual(model.detail?.run?.runId, "new")
        model.loadDetail(runId: "old")
        try await Task.sleep(nanoseconds: 10_000_000)
        model.loadDetail(runId: "old")
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertNil(model.detailRunId)
        XCTAssertNil(model.detail)
    }

    func testCancelledQueuedRefreshDoesNotStartAnotherRequest() async throws {
        let counter = RunsReadCounter()
        let empty = try JSONDecoder().decode(RunsList.self, from: Data(#"{"ok":true,"runs":[]}"#.utf8))
        let model = RunsViewModel(api: api, fetchList: { _, _, _ in
            await counter.record(); return empty
        })
        let cancelled = Task { await model.refresh() }
        cancelled.cancel()
        await cancelled.value
        await model.refresh()
        let calls = await counter.calls
        XCTAssertEqual(calls, 1)
    }

    func testDetailFailureIsVisibleInsteadOfAnEndlessSpinner() async throws {
        let model = RunsViewModel(api: api, fetchDetail: { _, _ in throw JarvisError.forbidden })
        model.loadDetail(runId: "denied")
        for _ in 0..<100 where model.detailError == nil { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertEqual(model.detailError, "Forbidden")
        XCTAssertNil(model.detail)
        model.loadDetail(runId: "denied")
        XCTAssertNil(model.detailRunId)
        XCTAssertNil(model.detailError)
    }
}
