import XCTest
@testable import MortimerHost

final class SkillsWorkspaceAccessibilityStatusTests: XCTestCase {
    func testStatusTransitionsAnnounceEachNewStateOnce() {
        var status = SkillsWorkspaceAccessibilityStatus()

        XCTAssertEqual(status.transition(resource: .catalog, to: .loading), "Skills library loading.")
        XCTAssertNil(status.transition(resource: .catalog, to: .loading))
        XCTAssertEqual(status.transition(resource: .catalog, to: .loaded), "Skills library loaded.")
        XCTAssertNil(status.transition(resource: .catalog, to: .loaded))

        // A later refresh is a new transition and can announce its outcome.
        XCTAssertEqual(status.transition(resource: .catalog, to: .loading), "Skills library loading.")
        XCTAssertEqual(
            status.transition(resource: .catalog, to: .failed),
            "Skills library could not be loaded. Retry when ready."
        )
        XCTAssertNil(status.transition(resource: .catalog, to: .failed))
        XCTAssertEqual(status.transition(resource: .catalog, to: .loaded), "Skills library loaded.")
    }

    func testResourcesHaveIndependentDuplicateSuppressionAndGenericMessages() {
        var status = SkillsWorkspaceAccessibilityStatus()

        XCTAssertEqual(status.transition(resource: .detail, to: .loading), "Skill details loading.")
        XCTAssertEqual(status.transition(resource: .activity, to: .loading), "Skill activity loading.")
        XCTAssertEqual(status.transition(resource: .versions, to: .failed),
                       "Skill version evidence could not be loaded. Retry when ready.")
        XCTAssertEqual(status.transition(resource: .example, to: .loaded), "Example preview loaded.")
        XCTAssertNil(status.transition(resource: .detail, to: .loading))
    }

    func testProcessStepNavigationAnnouncesSelectionAndCollapseWithoutSpeakingStepIDs() {
        var status = SkillsWorkspaceAccessibilityStatus()

        XCTAssertEqual(status.processStepSelectionChanged(to: "inspect"), "Process step selected.")
        XCTAssertNil(status.processStepSelectionChanged(to: "inspect"),
                     "Repeated state updates must not repeat the announcement")
        XCTAssertEqual(status.processStepSelectionChanged(to: "draft"), "Process step selected.",
                       "Moving to another step through a shared voice action needs confirmation")
        XCTAssertEqual(status.processStepSelectionChanged(to: nil), "Process step collapsed.")
        XCTAssertNil(status.processStepSelectionChanged(to: nil))
    }
}
