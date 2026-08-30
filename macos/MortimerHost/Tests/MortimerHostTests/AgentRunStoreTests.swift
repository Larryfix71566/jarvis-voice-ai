import XCTest
import JarvisKit
@testable import MortimerHost

/// APP plan §7.2 — pins the agentRuns.ts reducer behaviour the port
/// carries (no equivalent web test exists, but the behaviour is
/// load-bearing). Messages are built by decoding the wire JSON through
/// AppMessage.decode, so the test exercises the same path production does.
@MainActor
final class AgentRunStoreTests: XCTestCase {
    private func message(_ json: String) throws -> AppMessage {
        try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
    }

    private func working(name: String = "analyst", runId: String = "r1",
                         task: String = "compare hosts", model: String = "kimi-k2.5") throws -> AppMessage {
        try message("""
        {"type":"agent","name":"\(name)","display_name":"\(name.capitalized)","state":"working",
         "run_id":"\(runId)","task":"\(task)","model":"\(model)","model_fallback":false}
        """)
    }

    func testWorkingInsertsRun() throws {
        let store = AgentRunStore()
        store.apply(try working())
        XCTAssertEqual(store.runs.count, 1)
        let run = try XCTUnwrap(store.runs.first)
        XCTAssertNil(run.doneAt)
        XCTAssertEqual(run.model, "kimi-k2.5")
        XCTAssertFalse(run.modelFallback)
    }

    func testActivityMatchedByRunId() throws {
        let store = AgentRunStore()
        store.apply(try working(name: "analyst", runId: "r1"))
        store.apply(try working(name: "systems", runId: "r2"))
        store.apply(try message("""
        {"type":"agent_activity","name":"analyst","run_id":"r1","tool":"web_search","ok":true,"latency_ms":300}
        """))
        XCTAssertEqual(store.runs.first(where: { $0.runId == "r1" })?.activity.count, 1)
        XCTAssertEqual(store.runs.first(where: { $0.runId == "r2" })?.activity.count, 0)
    }

    func testActivityFallsBackToLiveRun() throws {
        let store = AgentRunStore()
        store.apply(try message("""
        {"type":"agent","name":"analyst","state":"working","task":"t"}
        """))   // no run_id — "" on both sides
        store.apply(try message("""
        {"type":"agent_activity","name":"analyst","tool":"web_search","ok":true,"latency_ms":100}
        """))
        XCTAssertEqual(store.runs.first?.activity.count, 1)
    }

    func testPlannerModelSticks() throws {
        let store = AgentRunStore()
        store.apply(try working(name: "developer", runId: "d1"))
        store.apply(try message("""
        {"type":"agent_activity","name":"developer","run_id":"d1","tool":"selfedit_status",
         "ok":true,"latency_ms":500,"planner_model":"claude-opus-4"}
        """))
        store.apply(try message("""
        {"type":"agent_activity","name":"developer","run_id":"d1","tool":"web_search","ok":true,"latency_ms":100}
        """))
        // agentRuns.ts:327-341 — once seen, never cleared by a later
        // line that didn't report one.
        XCTAssertEqual(store.runs.first?.plannerModel, "claude-opus-4")
    }

    func testSelfEditRunsAppendAndCap() throws {
        let store = AgentRunStore()
        for i in 0..<(AppTuning.maxAgentRuns + 1) {
            store.apply(try working(name: "developer", runId: "d\(i)"))
            if i < AppTuning.maxAgentRuns {
                // settle every run but the newest so eviction has victims
                store.apply(try message("""
                {"type":"agent","name":"developer","state":"done","ok":true,"detail":""}
                """))
            }
        }
        let developerRuns = store.runs.filter { $0.name == "developer" }
        XCTAssertEqual(developerRuns.count, AppTuning.maxAgentRuns)
        // The newest (live) run survived the cap.
        XCTAssertTrue(developerRuns.contains { $0.runId == "d\(AppTuning.maxAgentRuns)" })
    }

    func testNonSelfEditReplaces() throws {
        let store = AgentRunStore()
        store.apply(try working(name: "analyst", runId: "a1"))
        store.apply(try working(name: "analyst", runId: "a2"))
        // agentRuns.ts:258 — one card, replaced.
        XCTAssertEqual(store.runs.filter { $0.name == "analyst" }.count, 1)
        XCTAssertEqual(store.runs.first?.runId, "a2")
    }

    func testDoneSetsOkAndDetail() throws {
        let store = AgentRunStore()
        store.apply(try working(name: "analyst", runId: "a1"))
        store.apply(try message("""
        {"type":"agent","name":"analyst","state":"done","ok":false,"detail":"tool failed"}
        """))
        let run = try XCTUnwrap(store.runs.first)
        XCTAssertNotNil(run.doneAt)
        XCTAssertFalse(run.ok)
        XCTAssertEqual(run.detail, "tool failed")
    }
}
