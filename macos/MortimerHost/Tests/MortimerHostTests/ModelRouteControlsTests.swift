import Foundation
import XCTest
import JarvisKit
@testable import MortimerHost

/// WS-05 MAR-H: exercise the real view model through delayed sidecar requests.
/// No provider inference or application defaults are touched.
@MainActor
final class ModelRouteControlsTests: XCTestCase {
    private static func exactDraft(_ choice: ModelRoutePreferenceStage) -> JSONValue {
        let digest = String(repeating: "a", count: 64)
        return .object(["ok": .bool(true), "draft_id": .string("v1:fixture:" + digest),
            "proposal_digest": .string(digest), "proposal": .object([
                "workload": .string(choice.workload),
                "current": .object(["model": .string("synthetic-current-v1"), "route": .string("subscription"), "privacy": .string("approved_external")]),
                "candidate": .object(["model": .string("synthetic-proposed-v1"), "profile": .string(choice.profile), "route": .string(choice.route), "privacy": .string(choice.privacy ?? "approved_external")])
            ])])
    }

    private func catalog(preferences: [JSONValue] = []) -> JSONValue {
        .object([
            "ok": .bool(true), "routing_enabled": .bool(false),
            "workloads": .object([
                "developer": .object(["profile": .string("claude-opus"), "route": .string("direct_api"), "privacy": .string("approved_external")]),
                "voice_supervisor": .object(["profile": .string("claude-haiku-4-5"), "route": .string("direct_api"), "privacy": .string("approved_external")]),
            ]),
            "routes": .object(["direct_api": .object(["billing": .string("api"), "capabilities": .array([.string("text"), .string("tools")])]), "subscription": .object([:])]),
            "profiles": .array([
                .object(["name": .string("claude-opus"), "routes": .array([.string("direct_api"), .string("subscription")])]),
                .object(["name": .string("claude-haiku-4-5"), "routes": .array([.string("direct_api")]), "supported_workloads": .array([.string("voice_supervisor")])]),
            ]), "preferences": .array(preferences),
        ])
    }

    private func preference(profile: String = "claude-opus", route: String = "subscription") -> JSONValue {
        .object(["workload": .string("developer"), "profile": .string(profile), "route": .string(route), "privacy": .string("approved_external")])
    }

    private func model(refreshBrief: @escaping () async throws -> JSONValue = { .object(["ok": .bool(false)]) },
                       load: @escaping () async throws -> JSONValue,
                       stage: @escaping (ModelRoutePreferenceStage) async throws -> JSONValue = { ModelRouteControlsTests.exactDraft($0) },
                       confirm: @escaping (String) async throws -> JSONValue = { _ in .object(["ok": .bool(true), "state": .string("saved"), "configured_model": .string("synthetic-proposed-v1"), "runtime_adoption": .string("unverified")]) }) -> RepoViewModel {
        let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
                                  adminURL: URL(string: "http://127.0.0.1:7861")!,
                                  wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)
        return RepoViewModel(api: AdminAPI(config: config),
                             modelRouteRequests: ModelRouteRequests(load: load, stage: stage, confirm: confirm, refreshBrief: refreshBrief))
    }

    func testSavedPreferenceSurvivesConfirmAndRefresh() async {
        var saved = false
        let vm = model(load: { self.catalog(preferences: saved ? [self.preference()] : []) }, confirm: { _ in
            saved = true
            return .object(["ok": .bool(true), "state": .string("saved"), "configured_model": .string("synthetic-proposed-v1"), "runtime_adoption": .string("unverified")])
        })
        await vm.refreshModelRoutes()
        vm.selectedModelRoute = "subscription"
        await vm.stageModelRoute()
        await vm.confirmModelRoute()
        XCTAssertTrue(saved)
        XCTAssertEqual(vm.selectedModelRoute, "subscription")
        XCTAssertNil(vm.modelRouteDraftID)
        XCTAssertEqual(vm.modelRouteNote, "Model route saved; active runtime adoption is unverified.")
        XCTAssertTrue(vm.modelRouteActivationSummary.contains("does not change the activation flag"))
        XCTAssertTrue(vm.modelRouteActivationSummary.contains("bot status has not been verified"))
    }

    func testUnavailableSavedChoiceIsKeptVisibleWithoutSubstitution() async {
        let vm = model(load: { self.catalog(preferences: [self.preference(profile: "removed-profile", route: "unavailable-route")]) })
        await vm.refreshModelRoutes()
        XCTAssertEqual(vm.selectedModelProfile, "removed-profile")
        XCTAssertEqual(vm.selectedModelRoute, "unavailable-route")
        XCTAssertTrue(vm.modelRouteProfiles.contains("removed-profile"))
        XCTAssertTrue(vm.modelRouteNames.contains("unavailable-route"))
        XCTAssertTrue(vm.selectedModelRouteSummary?.contains("unavailable") == true)
    }

    func testVoiceOnlyProfileIsShownOnlyForVoiceAndDirectAPIIsPresent() async {
        let vm = model(load: { self.catalog() })
        await vm.refreshModelRoutes()
        XCTAssertTrue(vm.modelRouteNames.contains("direct_api"))
        XCTAssertFalse(vm.modelRouteProfiles.contains("claude-haiku-4-5"))
        vm.selectedModelWorkload = "voice_supervisor"
        XCTAssertEqual(vm.selectedModelProfile, "claude-haiku-4-5")
        XCTAssertTrue(vm.modelRouteProfiles.contains("claude-haiku-4-5"))
        XCTAssertEqual(vm.modelRouteNames, ["direct_api"])
    }

    func testMissingProfileDoesNotBorrowGlobalRouteCapabilities() async {
        var object = catalog(preferences: [preference(profile: "removed-profile")]).objectValue!
        object["choices"] = .object(["developer": .object([:])])
        let payload = JSONValue.object(object)
        let vm = model(load: { payload })
        await vm.refreshModelRoutes()
        XCTAssertEqual(vm.selectedModelRoute, "subscription")
        XCTAssertTrue(vm.selectedModelRouteSummary?.contains("unavailable") == true)
    }

    func testEverySelectionChangeInvalidatesDraftBeforeConfirmation() async {
        var confirms = 0
        let vm = model(load: { self.catalog() }, confirm: { _ in
            confirms += 1
            return .object(["ok": .bool(true), "state": .string("saved"), "configured_model": .string("synthetic-proposed-v1"), "runtime_adoption": .string("unverified")])
        })
        await vm.refreshModelRoutes()
        let changes: [() -> Void] = [
            { vm.selectedModelProfile = "other" },
            { vm.selectedModelRoute = "subscription" },
            { vm.selectedModelPrivacy = "confidential" },
            { vm.selectedModelWorkload = "voice_supervisor" },
        ]
        for change in changes {
            await vm.stageModelRoute()
            XCTAssertNotNil(vm.modelRouteDraftID)
            change()
            XCTAssertNil(vm.modelRouteDraftID)
            await vm.confirmModelRoute()
        }
        XCTAssertEqual(confirms, 0)
    }

    func testLateDraftCannotAttachAfterSelectionChangesAndChangesBack() async {
        var continuation: CheckedContinuation<JSONValue, Never>?
        let entered = expectation(description: "stage entered")
        let vm = model(load: { self.catalog() }, stage: { _ in
            await withCheckedContinuation { continuation = $0; entered.fulfill() }
        })
        await vm.refreshModelRoutes()
        let task = Task { await vm.stageModelRoute() }
        await fulfillment(of: [entered], timeout: 2)
        vm.selectedModelRoute = "subscription"
        vm.selectedModelRoute = "direct_api"
        continuation?.resume(returning: .object(["ok": .bool(true), "draft_id": .string("obsolete")]))
        await task.value
        XCTAssertNil(vm.modelRouteDraftID)
        XCTAssertFalse(vm.modelRouteStaging)
    }

    func testDiscardInvalidatesAStillPendingDraftResponse() async {
        var continuation: CheckedContinuation<JSONValue, Never>?
        let entered = expectation(description: "stage entered")
        let vm = model(load: { self.catalog() }, stage: { _ in
            await withCheckedContinuation { continuation = $0; entered.fulfill() }
        })
        let task = Task { await vm.stageModelRoute() }
        await fulfillment(of: [entered], timeout: 2)
        vm.discardModelRouteDraft()
        continuation?.resume(returning: .object(["ok": .bool(true), "draft_id": .string("obsolete")]))
        await task.value
        XCTAssertNil(vm.modelRouteDraftID)
    }

    func testLateCatalogDoesNotReplaceEditMadeWhileLoading() async {
        var continuation: CheckedContinuation<JSONValue, Never>?
        let entered = expectation(description: "catalog entered")
        let vm = model(load: {
            await withCheckedContinuation { continuation = $0; entered.fulfill() }
        })
        let task = Task { await vm.refreshModelRoutes() }
        await fulfillment(of: [entered], timeout: 2)
        vm.selectedModelRoute = "subscription"
        continuation?.resume(returning: catalog())
        await task.value
        XCTAssertEqual(vm.selectedModelRoute, "subscription")
    }

    func testUnsuccessfulCatalogIsAnErrorAndClearsDraft() async {
        let vm = model(load: { .object(["ok": .bool(false), "error": .string("catalog unavailable")]) })
        await vm.stageModelRoute()
        XCTAssertNotNil(vm.modelRouteDraftID)
        await vm.refreshModelRoutes()
        guard case .error(let message) = vm.modelRoutesState else { return XCTFail("expected error") }
        XCTAssertEqual(message, "catalog unavailable")
        XCTAssertNil(vm.modelRouteDraftID)
    }

    func testConcurrentConfirmDoesNotSendTwice() async {
        var continuation: CheckedContinuation<JSONValue, Never>?
        var confirms = 0
        let entered = expectation(description: "confirm entered")
        let vm = model(load: { self.catalog() }, confirm: { _ in
            confirms += 1
            return await withCheckedContinuation { continuation = $0; entered.fulfill() }
        })
        await vm.refreshModelRoutes()
        await vm.stageModelRoute()
        let task = Task { await vm.confirmModelRoute() }
        await fulfillment(of: [entered], timeout: 2)
        await vm.confirmModelRoute()
        XCTAssertEqual(confirms, 1)
        continuation?.resume(returning: .object(["ok": .bool(true), "state": .string("saved"), "configured_model": .string("synthetic-proposed-v1"), "runtime_adoption": .string("unverified")]))
        await task.value
        XCTAssertFalse(vm.modelRouteConfirming)
    }
    func testLegacyDraftWithoutExactModelsCannotBeConfirmed() async {
        var calls = 0
        let vm = model(load: { self.catalog() }, stage: { _ in
            .object(["ok": .bool(true), "draft_id": .string("legacy")])
        }, confirm: { _ in calls += 1; return .object(["ok": .bool(true)]) })
        await vm.stageModelRoute()
        XCTAssertNil(vm.modelRouteDraftID)
        await vm.confirmModelRoute()
        XCTAssertEqual(calls, 0)
        XCTAssertTrue(vm.modelRouteNote?.contains("exact model preview") == true)
    }

    func testExactProposalDisplaysBothModelsAndUnverifiedEvidence() async {
        let vm = model(load: { self.catalog() })
        await vm.stageModelRoute()
        XCTAssertTrue(vm.modelRouteProposalSummary?.contains("synthetic-current-v1") == true)
        XCTAssertTrue(vm.modelRouteProposalSummary?.contains("synthetic-proposed-v1") == true)
        XCTAssertTrue(vm.modelRouteProposalSummary?.contains("unverified") == true)
    }

    func testSuccessWithoutSavedModelReadbackDoesNotClaimApplied() async {
        let vm = model(load: { self.catalog() }, confirm: { _ in .object(["ok": .bool(true)]) })
        await vm.stageModelRoute()
        await vm.confirmModelRoute()
        XCTAssertTrue(vm.modelRouteNote?.contains("readback is unavailable") == true)
    }

    func testMissingBriefDoesNotInventModelAvailability() async {
        let vm = model(load: { self.catalog() })
        await vm.refreshModelRoutes()
        XCTAssertTrue(vm.harnessBriefSummary.contains("unavailable"))
    }

    func testHarnessSwitchCannotStageOrConfirm() async {
        var stages = 0
        var confirms = 0
        let vm = model(load: { self.catalog() }, stage: { choice in
            stages += 1
            return Self.exactDraft(choice)
        }, confirm: { _ in
            confirms += 1
            return .object(["ok": .bool(true)])
        })
        await vm.refreshModelRoutes()
        vm.selectedModelWorkload = "voice_supervisor"
        await vm.stageModelRoute()
        await vm.confirmModelRoute()
        XCTAssertEqual(stages, 0)
        XCTAssertEqual(confirms, 0)
        XCTAssertNil(vm.modelRouteDraftID)
    }

    func testExplicitEvidenceRefreshShowsStalenessWithoutModelWrites() async {
        var refreshes = 0
        let vm = model(refreshBrief: {
            refreshes += 1
            return .object(["ok": .bool(true), "freshness": .string("stale"), "report": .object([
                "summary": .string("Historical evidence; active controller unknown."),
                "evidence_generated_at": .string("2000-01-01"),
                "candidates": .array([])
            ])])
        }, load: { self.catalog() }, stage: { _ in
            XCTFail("Evidence refresh must not stage a model")
            return .null
        }, confirm: { _ in
            XCTFail("Evidence refresh must not confirm a model")
            return .null
        })
        await vm.refreshModelRoutes()
        XCTAssertEqual(refreshes, 0)
        await vm.refreshHarnessBrief()
        XCTAssertEqual(refreshes, 1)
        XCTAssertTrue(vm.harnessBriefSummary.contains("Freshness: stale"))
        XCTAssertTrue(vm.harnessBriefSummary.contains("2000-01-01"))
        XCTAssertNil(vm.modelRouteDraftID)
    }

    func testUnresolvedCurrentSelectionCanPreviewAndConfirmRepair() async {
        var confirms = 0
        let vm = model(load: { self.catalog() }, stage: { choice in
            var result = Self.exactDraft(choice).objectValue!
            var proposal = result["proposal"]!.objectValue!
            proposal["current"] = .object(["model": .null, "profile": .string("removed-profile"),
                "route": .string("direct_api"), "privacy": .string("approved_external"),
                "resolution_state": .string("unresolved")])
            result["proposal"] = .object(proposal)
            return .object(result)
        }, confirm: { _ in
            confirms += 1
            return .object(["ok": .bool(true), "state": .string("saved"),
                "configured_model": .string("synthetic-proposed-v1"), "runtime_adoption": .string("unverified")])
        })
        await vm.stageModelRoute()
        XCTAssertNotNil(vm.modelRouteDraftID)
        XCTAssertTrue(vm.modelRouteProposalSummary?.contains("Configured selection: unresolved") == true)
        await vm.confirmModelRoute()
        XCTAssertEqual(confirms, 1)
        XCTAssertTrue(vm.modelRouteNote?.contains("active runtime adoption is unverified") == true)
    }

    func testMissingCurrentIdentityWithoutExplicitUnresolvedStateIsRejected() async {
        let vm = model(load: { self.catalog() }, stage: { choice in
            var result = Self.exactDraft(choice).objectValue!
            var proposal = result["proposal"]!.objectValue!
            proposal["current"] = .object(["model": .null])
            result["proposal"] = .object(proposal)
            return .object(result)
        })
        await vm.stageModelRoute()
        XCTAssertNil(vm.modelRouteDraftID)
    }

}
