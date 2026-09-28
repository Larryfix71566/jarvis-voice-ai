import XCTest
import SwiftUI
@testable import MortimerHost

final class SkillsWorkspacePresentationPolicyTests: XCTestCase {
    func testCreatorActivityKeepsRefreshingAfterDeveloperFinishes() {
        for status in [nil, "ok", "failed", "cancelled", "orphaned"] as [String?] {
            XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityRefreshInterval(
                skillID: "skill-creator", runStatus: status, sceneIsActive: true), 5)
            XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityRefreshInterval(
                skillID: "skill-creator", runStatus: status, sceneIsActive: false), 15)
        }
    }

    func testNormalActivityPollingSettlesWhileRunningRunsStayResponsive() {
        XCTAssertNil(SkillsWorkspacePresentationPolicy.activityRefreshInterval(
            skillID: "weather", runStatus: "ok", sceneIsActive: true))
        for skill in ["weather", "skill-creator"] {
            XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityRefreshInterval(
                skillID: skill, runStatus: "running", sceneIsActive: true), 1)
            XCTAssertEqual(SkillsWorkspacePresentationPolicy.activityRefreshInterval(
                skillID: skill, runStatus: "running", sceneIsActive: false), 5)
        }
    }

    func testCreatorOpenRequiresAuthoringCapabilityAndCatalogRevision() {
        let revision = String(repeating: "a", count: 64)
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.canOpenCreator(
            authoringAvailable: true, catalogRevision: revision))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.canOpenCreator(
            authoringAvailable: false, catalogRevision: revision))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.canOpenCreator(
            authoringAvailable: true, catalogRevision: String(revision.dropLast())))
    }

    func testProposedSkillIsNotFlaggedOnlyBecauseItIsNotEnabledYet() {
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "proposed", readiness: "unknown", verification: "not_tested"))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "proposed", readiness: "blocked", verification: "not_tested"))
    }

    func testInstalledUnknownReadinessAndFailedVerificationNeedAttention() {
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed", readiness: "unknown", verification: "not_tested"))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed", readiness: "ready", verification: "stale"))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed", readiness: "ready", verification: "offline_passed"))
    }

    func testIntentionallyDisabledPackageDoesNotLookLikeAnActionableAlert() {
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed",
            readiness: "blocked",
            verification: "not_tested",
            enabled: false,
            readinessReasons: [
                "skill_disabled",
                "revision_enforcement_disabled",
                "model_route_compatibility_unverified",
            ]
        ))
    }

    func testDisabledPackageStillSurfacesUnexpectedBlockersAndFailedVerification() {
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed",
            readiness: "blocked",
            verification: "not_tested",
            enabled: false,
            readinessReasons: ["skill_disabled", "required_credential_missing:EXAMPLE_KEY"]
        ))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.needsAttention(
            installation: "installed",
            readiness: "blocked",
            verification: "failed",
            enabled: false,
            readinessReasons: ["skill_disabled"]
        ))
    }

    func testGuidanceAndBranchingProcessesExposeDeclaredEdges() {
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.showsEdgeChoices(processKind: "branching"))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.showsEdgeChoices(processKind: "guidance"))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.showsEdgeChoices(processKind: "linear"))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.showsLinearNext(processKind: "linear"))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.showsLinearNext(processKind: "guidance"))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.showsLinearNext(processKind: "branching"))
    }

    func testAccessibilityTextUsesSinglePaneEvenOnWideDisplays() {
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.usesSplitLayout(
            width: 1280, dynamicTypeSize: .accessibility5))
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.usesSplitLayout(
            width: 1280, dynamicTypeSize: .large))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.usesSplitLayout(
            width: 959, dynamicTypeSize: .large))
    }

    func testLateSkillDetailResponsesCannotReplaceTheCurrentSelection() {
        let obsoleteRequest = UUID()
        let currentRequest = UUID()

        XCTAssertFalse(SkillsWorkspacePresentationPolicy.isCurrentDetailResponse(
            requestID: obsoleteRequest,
            currentRequestID: currentRequest,
            requestedSkillID: "first-skill",
            selectedSkillID: "second-skill"
        ))
        XCTAssertFalse(SkillsWorkspacePresentationPolicy.isCurrentDetailResponse(
            requestID: obsoleteRequest,
            currentRequestID: currentRequest,
            requestedSkillID: "same-skill",
            selectedSkillID: "same-skill"
        ), "an older response for the same skill must not overwrite a newer revision")
        XCTAssertTrue(SkillsWorkspacePresentationPolicy.isCurrentDetailResponse(
            requestID: currentRequest,
            currentRequestID: currentRequest,
            requestedSkillID: "second-skill",
            selectedSkillID: "second-skill"
        ))
    }
}
