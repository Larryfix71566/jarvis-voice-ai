import Foundation
import XCTest
import JarvisKit
@testable import MortimerHost

/// WS-05 MAR-H: exercise the real view model through delayed sidecar requests.
/// No provider inference or application defaults are touched.
@MainActor
final class ModelRouteControlsTests: XCTestCase {
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

    private func model(load: @escaping () async throws -> JSONValue,
                       stage: @escaping (ModelRoutePreferenceStage) async throws -> JSONValue = { _ in .object(["ok": .bool(true), "draft_id": .string("draft")]) },
                       confirm: @escaping (String) async throws -> JSONValue = { _ in .object(["ok": .bool(true)]) }) -> RepoViewModel {
        let config = JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!,
                                  adminURL: URL(string: "http://127.0.0.1:7861")!,
                                  wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil)
        return RepoViewModel(api: AdminAPI(config: config),
                             modelRouteRequests: ModelRouteRequests(load: load, stage: stage, confirm: confirm))
    }

    func testSavedPreferenceSurvivesConfirmAndRefresh() async {
        var saved = false
        let vm = model(load: { self.catalog(preferences: saved ? [self.preference()] : []) }, confirm: { _ in
            saved = true
            return .object(["ok": .bool(true)])
        })
        await vm.refreshModelRoutes()
        vm.selectedModelRoute = "subscription"
        await vm.stageModelRoute()
        await vm.confirmModelRoute()
        XCTAssertTrue(saved)
        XCTAssertEqual(vm.selectedModelRoute, "subscription")
        XCTAssertNil(vm.modelRouteDraftID)
        XCTAssertEqual(vm.modelRouteNote, "Model route saved.")
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
            return .object(["ok": .bool(true)])
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
        continuation?.resume(returning: .object(["ok": .bool(true)]))
        await task.value
        XCTAssertFalse(vm.modelRouteConfirming)
    }
}
