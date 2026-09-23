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
}
