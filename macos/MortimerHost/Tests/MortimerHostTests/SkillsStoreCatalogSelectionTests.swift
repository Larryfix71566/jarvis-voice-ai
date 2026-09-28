import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class SkillsStoreCatalogSelectionTests: XCTestCase {
    func testSelectionIncludesCatalogEntriesBeyondVoiceInventoryAndFirstPage() {
        let store = SkillsStore()
        let entries: [JSONValue] = (0..<61).map { index in
            .object([
                "skill_id": .string("skill-\(index)"),
                "display_name": .string("Skill \(index)"),
                "description": .string("Fixture"),
                "category": .string("general"),
                "installation": .string("installed"),
                "enabled": .bool(true),
                "readiness": .string("ready"),
                "example_ids": .array([]),
            ])
        }

        store.updateCatalog(entries)

        XCTAssertEqual(store.catalogInventory.count, 32,
                       "console voice/action inventory remains deliberately bounded")
        XCTAssertTrue(store.selectSkill("skill-60"),
                      "pointer selection must work for a catalog card beyond both prior caps")
        XCTAssertEqual(store.selectedSkillID, "skill-60")
    }

    func testRepeatedAcceptedNavigationRequestsRemainObservableWithoutStateChanges() {
        let store = SkillsStore()
        store.updateCatalog([.object([
            "skill_id": .string("sample"),
            "display_name": .string("Sample"),
            "description": .string("Fixture"),
        ])])

        XCTAssertTrue(store.selectSkill("sample"))
        let afterFirstSelect = store.navigationRequestRevision
        XCTAssertTrue(store.selectSkill("sample"))
        XCTAssertEqual(store.navigationRequestRevision, afterFirstSelect + 1,
                       "reselecting the active skill after compact Back must still notify the view")

        XCTAssertTrue(store.selectTab("overview"))
        let afterFirstTab = store.navigationRequestRevision
        XCTAssertTrue(store.selectTab("overview"))
        XCTAssertEqual(store.navigationRequestRevision, afterFirstTab + 1)

        let beforeInvalidRequest = store.navigationRequestRevision
        XCTAssertFalse(store.selectTab("unknown"))
        XCTAssertEqual(store.navigationRequestRevision, beforeInvalidRequest,
                       "invalid navigation targets must not publish a navigation request")
    }

    func testCachedDetailIsRevisionBoundAndRejectsMismatchedIdentity() {
        let store = SkillsStore()
        let revision = String(repeating: "a", count: 64)
        let otherRevision = String(repeating: "b", count: 64)
        let detail: JSONValue = .object([
            "skill_id": .string("sample"),
            "revision": .string(revision),
            "process_nodes": .array([]),
        ])
        store.updateCatalog([
            .object(["skill_id": .string("sample"), "display_name": .string("Sample"),
                     "revision": .string(revision)]),
            .object(["skill_id": .string("another-skill"), "display_name": .string("Other"),
                     "revision": .string(revision)]),
        ])

        store.cacheDetail(detail, skillID: "sample", revision: revision)

        XCTAssertEqual(store.cachedDetail(skillID: "sample", revision: revision), detail)
        XCTAssertNil(store.cachedDetail(skillID: "sample", revision: otherRevision))
        store.cacheDetail(detail, skillID: "another-skill", revision: revision)
        store.cacheDetail(detail, skillID: "sample", revision: "invalid")
        XCTAssertNil(store.cachedDetail(skillID: "another-skill", revision: revision))
        XCTAssertEqual(store.cachedDetail(skillID: "sample", revision: revision), detail)
    }

    func testNewRevisionReplacesOlderDetailAndCacheIsBounded() {
        let store = SkillsStore()
        let firstRevision = String(repeating: "a", count: 64)
        let nextRevision = String(repeating: "b", count: 64)
        func detail(_ id: String, _ revision: String) -> JSONValue {
            .object(["skill_id": .string(id), "revision": .string(revision)])
        }
        store.updateCatalog([.object(["skill_id": .string("replace"),
                                      "display_name": .string("Replace"),
                                      "revision": .string(firstRevision)])])
        store.cacheDetail(detail("replace", firstRevision), skillID: "replace", revision: firstRevision)
        store.updateCatalog([.object(["skill_id": .string("replace"),
                                      "display_name": .string("Replace"),
                                      "revision": .string(nextRevision)])])
        store.cacheDetail(detail("replace", nextRevision), skillID: "replace", revision: nextRevision)
        XCTAssertNil(store.cachedDetail(skillID: "replace", revision: firstRevision))
        XCTAssertNotNil(store.cachedDetail(skillID: "replace", revision: nextRevision))

        let entries: [JSONValue] = (0..<33).map { index in
            .object(["skill_id": .string("skill-\(index)"),
                     "display_name": .string("Skill \(index)"),
                     "revision": .string(String(format: "%064x", index + 1))])
        }
        store.updateCatalog(entries)
        for index in 0..<33 {
            let id = "skill-\(index)"
            let revision = String(format: "%064x", index + 1)
            store.cacheDetail(detail(id, revision), skillID: id, revision: revision)
        }
        XCTAssertNil(store.cachedDetail(skillID: "skill-0", revision: String(format: "%064x", 1)))
        XCTAssertNotNil(store.cachedDetail(skillID: "skill-32", revision: String(format: "%064x", 33)))
    }

    func testRevisitingDetailUsesCacheAndChangedCatalogRevisionReloads() async throws {
        let store = SkillsStore()
        let firstRevision = String(repeating: "a", count: 64)
        let nextRevision = String(repeating: "b", count: 64)
        func catalog(_ revision: String) -> JSONValue {
            .object([
                "skill_id": .string("sample"),
                "display_name": .string("Sample"),
                "revision": .string(revision),
            ])
        }
        func detail(_ revision: String) -> JSONValue {
            .object([
                "skill_id": .string("sample"),
                "revision": .string(revision),
                "process_nodes": .array([]),
            ])
        }
        store.updateCatalog([catalog(firstRevision)])
        var networkLoads = 0
        let first = try await store.resolveDetail(skillID: "sample", revision: firstRevision) {
            networkLoads += 1
            return detail(firstRevision)
        }
        let revisit = try await store.resolveDetail(skillID: "sample", revision: firstRevision) {
            networkLoads += 1
            return detail(firstRevision)
        }
        XCTAssertEqual(first, revisit)
        XCTAssertEqual(networkLoads, 1, "list → detail → back → same detail should reuse the package-revision cache")

        store.updateCatalog([catalog(nextRevision)])
        let refreshed = try await store.resolveDetail(skillID: "sample", revision: nextRevision) {
            networkLoads += 1
            return detail(nextRevision)
        }
        XCTAssertEqual(refreshed["revision"]?.stringValue, nextRevision)
        XCTAssertEqual(networkLoads, 2, "catalog revision changes must fetch the new package detail")
        XCTAssertNil(store.cachedDetail(skillID: "sample", revision: firstRevision))
    }

    func testFailedDetailLoadDoesNotCreateCacheEntry() async {
        let store = SkillsStore()
        let revision = String(repeating: "c", count: 64)
        do {
            _ = try await store.resolveDetail(skillID: "sample", revision: revision) {
                throw NSError(domain: "fixture", code: 1)
            }
            XCTFail("expected loader error")
        } catch {
            XCTAssertNil(store.cachedDetail(skillID: "sample", revision: revision))
        }
    }

    func testDetailResolverRejectsWrongSkillOrPackageRevision() async {
        let store = SkillsStore()
        let revision = String(repeating: "d", count: 64)
        store.updateCatalog([.object(["skill_id": .string("sample"),
                                      "display_name": .string("Sample"),
                                      "revision": .string(revision)])])
        let mismatches: [JSONValue] = [
            .object(["skill_id": .string("other"), "revision": .string(revision)]),
            .object(["skill_id": .string("sample"),
                     "revision": .string(String(repeating: "e", count: 64))]),
        ]
        for result in mismatches {
            do {
                _ = try await store.resolveDetail(skillID: "sample", revision: revision) { result }
                XCTFail("mismatched detail identity must not be returned to the view")
            } catch {
                XCTAssertNil(store.cachedDetail(skillID: "sample", revision: revision))
            }
        }
    }

    func testCachedDetailResolutionP95OverOneHundredSamples() async throws {
        let store = SkillsStore()
        let revision = String(repeating: "f", count: 64)
        store.updateCatalog([.object(["skill_id": .string("bench"),
                                      "display_name": .string("Bench"),
                                      "revision": .string(revision)])])
        let detail: JSONValue = .object([
            "skill_id": .string("bench"), "revision": .string(revision),
            "process_nodes": .array((0..<12).map { index in
                .object(["step_id": .string("step-\(index)"),
                         "description": .string(String(repeating: "fixture ", count: 24))])
            }),
        ])
        _ = try await store.resolveDetail(skillID: "bench", revision: revision) { detail }

        let clock = ContinuousClock()
        var samplesMilliseconds: [Double] = []
        samplesMilliseconds.reserveCapacity(100)
        for _ in 0..<100 {
            let start = clock.now
            let resolved = try await store.resolveDetail(skillID: "bench", revision: revision) {
                XCTFail("warm cached resolver should not invoke its loader")
                return detail
            }
            XCTAssertEqual(resolved, detail)
            let elapsed = start.duration(to: clock.now).components
            samplesMilliseconds.append(
                Double(elapsed.seconds) * 1_000 + Double(elapsed.attoseconds) / 1e15
            )
        }
        samplesMilliseconds.sort()
        let p95 = samplesMilliseconds[Int(ceil(Double(samplesMilliseconds.count) * 0.95)) - 1]
        print("SKILLS_DETAIL_CACHE_RESOLVE_P95_MS=\(String(format: "%.4f", p95)) samples=100; resolver-only, no SwiftUI rendering/network")
    }

    func testCachedStoreNavigationP95WithHundredSkillCatalog() async throws {
        let store = SkillsStore()
        let revision = String(repeating: "a", count: 64)
        let repositoryRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // MortimerHostTests
            .deletingLastPathComponent() // Tests
            .deletingLastPathComponent() // MortimerHost
            .deletingLastPathComponent() // macos
            .deletingLastPathComponent() // repository root
        let fixtureURL = repositoryRoot.appendingPathComponent(
            "tests/fixtures/skills_workspace/performance-100-skills.json")
        let fixture = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any])
        let count = try XCTUnwrap(fixture["skill_count"] as? Int)
        let prefix = try XCTUnwrap(fixture["skill_id_prefix"] as? String)
        XCTAssertEqual(count, 100)
        let ids = (0..<count).map { String(format: "%@-%03d", prefix, $0) }
        store.updateCatalog(ids.map { id in
            .object(["skill_id": .string(id), "display_name": .string(id),
                     "revision": .string(revision)])
        })

        // Prewarm the most recent 32 details to match the store's documented
        // LRU bound, then revisit only those entries while keeping all 100
        // catalog IDs loaded. This is deterministic and requires no service.
        let warmIDs = Array(ids.suffix(32))
        for id in warmIDs {
            store.cacheDetail(.object([
                "skill_id": .string(id), "revision": .string(revision),
                "process_nodes": .array((0..<12).map { index in
                    .object(["step_id": .string("step-\(index)"),
                             "title": .string("Step \(index)")])
                }),
            ]), skillID: id, revision: revision)
        }

        let clock = ContinuousClock()
        var selectionMilliseconds: [Double] = []
        var navigationMilliseconds: [Double] = []
        selectionMilliseconds.reserveCapacity(100)
        navigationMilliseconds.reserveCapacity(100)
        for sample in 0..<100 {
            let id = warmIDs[sample % warmIDs.count]
            let selectionStart = clock.now
            XCTAssertTrue(store.selectSkill(id))
            let selectionElapsed = selectionStart.duration(to: clock.now).components
            selectionMilliseconds.append(
                Double(selectionElapsed.seconds) * 1_000 + Double(selectionElapsed.attoseconds) / 1e15
            )

            let navigationStart = clock.now
            XCTAssertTrue(store.selectTab("process"))
            let detail = try await store.resolveDetail(skillID: id, revision: revision) {
                XCTFail("cached navigation must not invoke the detail loader")
                return .null
            }
            XCTAssertEqual(detail["skill_id"]?.stringValue, id)
            let navigationElapsed = navigationStart.duration(to: clock.now).components
            navigationMilliseconds.append(
                Double(navigationElapsed.seconds) * 1_000 + Double(navigationElapsed.attoseconds) / 1e15
            )
        }

        func p95(_ samples: [Double]) -> Double {
            samples.sorted()[Int(ceil(Double(samples.count) * 0.95)) - 1]
        }
        let selectionP95 = p95(selectionMilliseconds)
        let navigationP95 = p95(navigationMilliseconds)
        print("SKILLS_STORE_SELECTION_P95_MS=\(String(format: "%.4f", selectionP95)); CACHED_STORE_NAVIGATION_P95_MS=\(String(format: "%.4f", navigationP95)); samples=100; catalog=100; cached details=32; excludes SwiftUI rendering/network")
        XCTAssertLessThanOrEqual(selectionP95, 20.0)
        XCTAssertLessThanOrEqual(navigationP95, 100.0)
    }
}
