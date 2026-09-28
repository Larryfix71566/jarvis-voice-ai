import XCTest
import JarvisKit
@testable import MortimerHost

final class ConsoleActionRegistryTests: XCTestCase {
    func testRegistryEnumeratesEverySharedActionAndTargetRules() {
        let registry = ConsoleActionRegistry()
        XCTAssertEqual(registry.enabledActions, Set(ConsoleAction.allCases))
        XCTAssertTrue(registry.descriptor(for: .resultSelect)?.requiresTarget == true)
        XCTAssertTrue(registry.descriptor(for: .resultMode)?.requiresTarget == true)
        XCTAssertTrue(registry.descriptor(for: .panelDetach)?.requiresTarget == true)
        XCTAssertFalse(registry.descriptor(for: .viewSet)?.requiresTarget == true)
        XCTAssertFalse(registry.descriptor(for: .sharedContent)?.requiresTarget == true)
        XCTAssertFalse(registry.descriptor(for: .inventory)?.requiresTarget == true)
    }

    func testIdentityDependentActionsRequireTheSameSecondaryTargetAsPython() {
        let registry = ConsoleActionRegistry()
        let base = { (action: ConsoleAction, target: String, secondary: String?) in
            ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                           revision: 0, action: action, target: target,
                           secondaryTarget: secondary)
        }
        XCTAssertFalse(registry.validate(base(.compareSet, "result-a", nil)))
        XCTAssertTrue(registry.validate(base(.compareSet, "result-a", "result-b")))
        XCTAssertFalse(registry.validate(base(.atlasMove, "card-a", nil)))
        XCTAssertTrue(registry.validate(ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                                       revision: 0, action: .atlasMove, target: "card-a",
                                                       args: ["row": .number(2), "column": .number(1)])))
        XCTAssertTrue(registry.validate(ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                                       revision: 0, action: .atlasMove, target: "card-a",
                                                       secondaryTarget: "card-b",
                                                       args: ["relation": .string("left")])))
        XCTAssertFalse(registry.validate(base(.graphPath, "node-a", nil)))
        XCTAssertTrue(registry.validate(base(.graphPath, "node-a", "node-b")))
    }

    func testDisabledActionCannotValidate() {
        let registry = ConsoleActionRegistry(enabled: [.inventory])
        let request = ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                     revision: 0, action: .help)
        XCTAssertFalse(registry.validate(request))
    }

    func testCatalogScalarTypesAreValidatedBeforeMutation() {
        let registry = ConsoleActionRegistry()
        let base = { (action: ConsoleAction, args: [String: JSONValue]) in
            ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                           revision: 0, action: action, args: args)
        }
        XCTAssertTrue(registry.validate(base(.inputQuestion, ["question": .string("show this")])))
        XCTAssertFalse(registry.validate(base(.inputQuestion, ["question": .number(1)])))
        XCTAssertTrue(registry.validate(base(.appearanceSet, ["layout": .number(2)])))
        XCTAssertFalse(registry.validate(base(.appearanceSet, ["layout": .string("2")])))
        XCTAssertTrue(registry.validate(base(.sidecarText, ["size": .number(22)])))
        XCTAssertTrue(registry.validate(ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                                       revision: 0, action: .graphFocus, target: "node-a",
                                                       args: ["depth": .number(3)])))
        XCTAssertFalse(registry.validate(ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                                                        revision: 0, action: .graphFocus, target: "node-a",
                                                        args: ["depth": .number(5)])))
    }

    func testSkillsNavigationActionsUseClosedArgumentsAndTargets() {
        let registry = ConsoleActionRegistry()
        func request(_ action: ConsoleAction, target: String? = nil,
                     args: [String: JSONValue] = [:]) -> ConsoleRequest {
            ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                           revision: 0, action: action, target: target, args: args)
        }
        XCTAssertTrue(registry.validate(request(.skillsSearch, args: ["query": .string("creator")])))
        XCTAssertFalse(registry.validate(request(.skillsSearch, args: ["query": .string(String(repeating: "x", count: 257))])))
        let decomposedSearch = String(repeating: "e\u{301}", count: 129)
        XCTAssertEqual(decomposedSearch.count, 129)
        XCTAssertEqual(decomposedSearch.unicodeScalars.count, 258)
        XCTAssertFalse(registry.validate(request(.skillsSearch, args: ["query": .string(decomposedSearch)])),
                       "native validation must use the same Unicode code-point limit as Python")
        XCTAssertFalse(registry.validate(request(.skillsSearch)))
        XCTAssertTrue(registry.validate(request(.skillsFilter, args: ["state": .string("installed"), "category": .string("development")])))
        XCTAssertFalse(registry.validate(request(.skillsFilter, args: ["state": .string("everything"), "category": .string("development")])))
        XCTAssertTrue(registry.validate(request(.skillTab, args: ["tab": .string("process")])))
        XCTAssertFalse(registry.validate(request(.skillTab, args: ["tab": .string("execute")])))
        XCTAssertFalse(registry.validate(request(.skillSelect)))
        XCTAssertTrue(registry.validate(request(.skillSelect, target: "valid-skill-id")))
        let oversizedBrief = String(repeating: "e\u{301}", count: 4_001)
        XCTAssertEqual(oversizedBrief.count, 4_001)
        XCTAssertFalse(registry.validate(request(.skillRequestPreview, args: [
            "operation": .string("draft"), "skill_id": .string("draft-skill"),
            "task_brief": .string(oversizedBrief),
        ])), "draft brief limits must match Python's Unicode code-point counting")
    }

    func testSkillWorkspaceControlsHaveTypedSharedActions() {
        let registry = ConsoleActionRegistry()
        func request(_ action: ConsoleAction, target: String? = nil,
                     args: [String: JSONValue] = [:]) -> ConsoleRequest {
            ConsoleRequest(sessionID: UUID(), generation: UUID(), requestID: UUID(),
                           revision: 0, action: action, target: target, args: args)
        }
        for action: ConsoleAction in [.skillsRefresh, .skillBack, .skillActivityRetry, .skillActivityMore,
                                      .skillCreatorOpen] {
            XCTAssertTrue(registry.validate(request(action)), "\(action) should not need an inventory target")
            XCTAssertFalse(registry.descriptor(for: action)?.requiresTarget ?? true)
        }
        XCTAssertTrue(registry.validate(request(.skillDisplayTransfer, target: "technical-plan-document")))
        XCTAssertFalse(registry.validate(request(.skillDisplayTransfer)))
        XCTAssertTrue(registry.validate(request(.skillStepSelect, target: "draft",
            args: ["expanded": .bool(false)])))
        XCTAssertFalse(registry.validate(request(.skillStepSelect, target: "draft",
            args: ["expanded": .string("false")])))
    }
}
