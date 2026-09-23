import XCTest
@testable import JarvisKit

/// APP plan §7.1 — one test per response struct, decoding a fixture
/// CAPTURED from the running sidecar (§8 V0's curl list), never
/// hand-authored: a hand-authored fixture cannot catch a shape drift,
/// which is the whole point of typing the structs. Until V0 captures a
/// route's fixture the test SKIPS with the capture command — so V1 is
/// green pre-capture and the tests become real the moment the fixtures
/// are committed. The two deliberately hand-made inputs (the busy-status
/// shape, the older-sidecar missing-field case) are inline.
final class AdminResponseDecodeTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "admin-fixtures")
            ?? Bundle.module.url(forResource: name, withExtension: "json")
        guard let url, let data = try? Data(contentsOf: url) else {
            throw XCTSkip("fixture \(name).json not captured yet — run APP plan §8 V0 (curl the route into Tests/JarvisKitTests/admin-fixtures/)")
        }
        return data
    }

    func testDecodeGitStatus() throws {
        let status = try JSONDecoder().decode(GitStatus.self, from: fixture("git_status"))
        XCTAssertNotNil(status.changedFiles)     // decoded, defaulting allowed
        XCTAssertGreaterThanOrEqual(status.ahead, 0)
        XCTAssertGreaterThanOrEqual(status.behind, 0)
        XCTAssertFalse(status.branch.isEmpty)
    }

    func testDecodeSelfEditModels() throws {
        let models = try JSONDecoder().decode(SelfEditModels.self, from: fixture("selfedit_models"))
        XCTAssertTrue(models.ok)
        let first = try XCTUnwrap(models.models.first)
        XCTAssertFalse(first.name.isEmpty)
        // keyPresent is Bool, isDefault decoded from "default", tier optional.
        _ = first.keyPresent
        _ = first.isDefault
        _ = first.tier
    }

    func testDecodeArchitectureReference() throws {
        let json = """
        {"ok":true,"path":"docs/ARCHITECTURE.md","content":"# Runtime shape\\n","sha256":"abc","truncated":false}
        """
        let reference = try JSONDecoder().decode(ArchitectureReference.self, from: Data(json.utf8))
        XCTAssertTrue(reference.ok)
        XCTAssertEqual(reference.path, "docs/ARCHITECTURE.md")
        XCTAssertTrue(reference.content.contains("Runtime shape"))
        XCTAssertEqual(reference.sha256, "abc")
        XCTAssertFalse(reference.truncated)
    }

    func testDecodeSelfEditStatusReal() throws {
        let status = try JSONDecoder().decode(SelfEditStatus.self, from: fixture("selfedit_status"))
        // A real (idle) status has NO ok key.
        XCTAssertNil(status.ok)
    }

    func testDecodeSelfEditStatusBusy() throws {
        let json = """
        {"ok": false, "error": "an upgrade run is in progress"}
        """
        let status = try JSONDecoder().decode(SelfEditStatus.self, from: Data(json.utf8))
        XCTAssertEqual(status.ok, false)
        XCTAssertNotNil(status.error)
    }

    func testDecodeMemoryOverview() throws {
        let overview = try JSONDecoder().decode(MemoryOverview.self, from: fixture("memory"))
        XCTAssertTrue(overview.ok)
        if let fact = overview.facts.first {
            _ = fact.sourceSessionId          // String? — nullable column
            XCTAssertFalse(fact.key.isEmpty)
        }
        _ = overview.usage.tiers              // [String: Int]
        _ = overview.usage.overCapacity       // Bool
    }

    func testDecodeMemoryFactMetadata() throws {
        let json = """
        {"ok":true,"facts":[{"id":7,"key":"user.name","content":"Larry",
          "subject":"user","scope":"global","memory_type":"explicit_preference",
          "provenance":"user","evidence_status":"explicit","confidence":0.97,
          "content_revision":2,"classifier_version":"b1","used_for_count":3,
          "supersedes_id":4}],"summary":"","observations":[],
          "usage":{"fact_count":1,"tiers":{},"caps":{},"max_context_chars":100,"over_capacity":false}}
        """
        let overview = try JSONDecoder().decode(MemoryOverview.self, from: Data(json.utf8))
        let fact = try XCTUnwrap(overview.facts.first)
        XCTAssertEqual(fact.id, 7)
        XCTAssertEqual(fact.subject, "user")
        XCTAssertEqual(fact.scope, "global")
        XCTAssertEqual(fact.memoryType, "explicit_preference")
        XCTAssertEqual(fact.evidenceStatus, "explicit")
        XCTAssertEqual(fact.confidence, 0.97, accuracy: 0.0001)
        XCTAssertEqual(fact.contentRevision, 2)
        XCTAssertEqual(fact.classifierVersion, "b1")
        XCTAssertEqual(fact.usedForCount, 3)
        XCTAssertEqual(fact.supersedesId, 4)
    }

    func testDecodeMemoryReviews() throws {
        let reviews = try JSONDecoder().decode(MemoryReviews.self, from: fixture("memory_reviews"))
        XCTAssertTrue(reviews.ok)
        if let review = reviews.reviews?.first {
            XCTAssertGreaterThan(review.id, 0)   // Int, not String
            _ = review.keys                      // [String]
        }
    }

    func testDecodeKnowledge() throws {
        let knowledge = try JSONDecoder().decode(KnowledgeOverview.self, from: fixture("knowledge"))
        XCTAssertTrue(knowledge.ok)
        if let memory = knowledge.memory {
            XCTAssertGreaterThanOrEqual(memory.notReachingPrompt, 0)   // Int — the loud number
        }
        if let skill = knowledge.skills?.enabled.first {
            _ = skill.hasScripts                 // Bool
        }
    }

    func testDecodeRunsList() throws {
        let list = try JSONDecoder().decode(RunsList.self, from: fixture("runs"))
        XCTAssertTrue(list.ok)
        if let run = list.runs.first {
            _ = run.latencyMs                    // Int? — nullable
            XCTAssertGreaterThanOrEqual(run.toolCount, 0)   // non-optional
            _ = run.model                        // String? (F3)
            _ = run.toolsOk                      // Int? (F3)
            _ = run.toolsFailed                  // Int? (F3)
        }
    }

    func testDecodeRunDetail() throws {
        let detail = try JSONDecoder().decode(RunDetail.self, from: fixture("run_detail"))
        XCTAssertTrue(detail.ok)
        if let event = detail.events?.first {
            // THE load-bearing assertion: agent_events.ok is Int?
            // (1|0|NULL), NOT Bool (db.py:151 `ok INTEGER`).
            if let ok = event.ok {
                XCTAssertTrue(ok == 0 || ok == 1)
            }
        }
        _ = detail.payload                       // [JSONValue]?
    }

    func testDecodeOlderSidecarMissingField() throws {
        // A run row with tool_count REMOVED — the decodeIfPresent+default
        // rule (F8): defaults, no throw.
        let json = """
        {"run_id":"r-1","agent":"analyst","display_name":"Analyst","task":"t",
         "status":"ok","started_at":"2026-08-30T15:00:00"}
        """
        let run = try JSONDecoder().decode(RunSummary.self, from: Data(json.utf8))
        XCTAssertEqual(run.toolCount, 0)
        XCTAssertNil(run.latencyMs)
        XCTAssertNil(run.model)
    }

    // MARK: Council roster (Interface Task)

    func testDecodeCouncilRoster() throws {
        let list = try JSONDecoder().decode(
            CouncilRosterList.self, from: fixture("council_roster")
        )
        XCTAssertTrue(list.ok)
        guard let round = list.rounds.first else { return }  // an empty DB is legal
        XCTAssertFalse(round.roundId.isEmpty)
        XCTAssertEqual(round.tokens.total, round.tokens.prompt + round.tokens.completion)
        // A degraded round must carry the reason text, never a bare flag —
        // the reason IS the feature (a dead judge's error string).
        if round.degraded { XCTAssertFalse(round.degradedReasons.isEmpty) }
        XCTAssertLessThanOrEqual(round.proposers.filter(\.isWinner).count, 1)
        for judge in round.judges where judge.allAbstained {
            XCTAssertEqual(judge.scored, 0)
        }
    }

    func testDecodeCouncilRosterOlderRoundMissingFields() throws {
        // A round recorded before migration 0018 (no retry_outcome) and
        // before it had any scores — the shape most of the real history
        // is in. decodeIfPresent+default: no throw, no fabricated data.
        let json = """
        {"ok": true, "rounds": [
          {"round_id":"r-old","workflow":"selfedit","placement":"planner",
           "status":"too_small","started_at":"2026-08-17T17:22:27+00:00",
           "degraded":true,"degraded_reasons":["round status: too_small"]}
        ]}
        """
        let list = try JSONDecoder().decode(CouncilRosterList.self, from: Data(json.utf8))
        let round = try XCTUnwrap(list.rounds.first)
        XCTAssertNil(round.retryOutcome)
        XCTAssertNil(round.winnerProfile)
        XCTAssertEqual(round.proposers, [])
        XCTAssertEqual(round.judges, [])
        XCTAssertEqual(round.shadowJudges, [])
        XCTAssertEqual(round.tokens.total, 0)
        XCTAssertEqual(round.degradedReasons, ["round status: too_small"])
    }
}
