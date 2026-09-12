import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class DrawerModelsTests: XCTestCase {
    private func configuration(token: String = "fixture") -> JarvisConfig {
        JarvisConfig(botURL: URL(string: "http://127.0.0.1:7860")!, adminURL: URL(string: "http://127.0.0.1:7861")!,
                     wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: token)
    }

    func testDraftsAndModelIdentitySurviveSecondPresentationAndTokenRefresh() throws {
        let models = DrawerModels()
        models.configure(configuration())
        let edit = try XCTUnwrap(models.edit), repo = try XCTUnwrap(models.repo)
        edit.goal = "Unsaved synthetic development request"
        edit.selectedModel = "fixture-model"
        repo.commitMessage = "Unsubmitted synthetic commit message"
        models.scrollOffsets["edit"] = 220
        models.configure(configuration())
        XCTAssertTrue(models.edit === edit)
        models.configure(configuration(token: "refreshed-fixture"))
        XCTAssertTrue(models.edit === edit)
        XCTAssertTrue(models.repo === repo)
        XCTAssertEqual(models.edit?.goal, "Unsaved synthetic development request")
        XCTAssertEqual(models.edit?.selectedModel, "fixture-model")
        XCTAssertEqual(models.repo?.commitMessage, "Unsubmitted synthetic commit message")
        XCTAssertEqual(models.scrollOffsets["edit"], 220)
    }

    func testOutgoingPresentationCannotReleaseIncomingLease() {
        let models = DrawerModels(), docked = UUID(), detached = UUID()
        // Without configured clients these exercise ownership, not network I/O.
        models.acquire(docked, tab: "edit")
        models.acquire(detached, tab: "edit")
        models.release(docked)
        XCTAssertEqual(models.visibleCount(for: "edit"), 1)
        models.acquire(detached, tab: "repo")
        XCTAssertEqual(models.visibleCount(for: "edit"), 0)
        XCTAssertEqual(models.visibleCount(for: "repo"), 1)
        models.release(detached)
        XCTAssertEqual(models.visibleCount(for: "repo"), 0)
    }
}
