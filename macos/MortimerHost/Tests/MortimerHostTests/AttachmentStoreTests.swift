import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class AttachmentStoreTests: XCTestCase {
    private func item(_ text: String) -> SharedContentTransfer {
        SharedContentTransfer(kind: .text, mimeType: "text/plain",
                              digest: String(repeating: "a", count: 64),
                              payload: Data(text.utf8))
    }

    func testStagingApprovalRemovalAndClearAreBoundedAndEphemeral() {
        let store = AttachmentStore()
        let values = (0..<5).map { item("item-\($0)") }
        values.prefix(4).forEach { store.stage($0) }
        store.stage(values[4])
        XCTAssertEqual(store.staged.count, 4)
        XCTAssertNotNil(store.error)

        let first = values[0].contentID
        store.approve(first)
        XCTAssertTrue(store.approvedIDs.contains(first))
        store.remove(first)
        XCTAssertFalse(store.approvedIDs.contains(first))
        XCTAssertEqual(store.staged.count, 3)

        store.setQuestion(String(repeating: "q", count: 2_100))
        XCTAssertEqual(store.question.count, 2_000)
        store.clear()
        XCTAssertTrue(store.staged.isEmpty)
        XCTAssertTrue(store.approvedIDs.isEmpty)
        XCTAssertEqual(store.question, "")
        XCTAssertNil(store.error)
    }

    func testClearInvalidatesLateProviderCompletions() {
        let store = AttachmentStore()
        let candidate = item("late")
        let generation = store.stagingGeneration
        store.clear()
        XCTAssertFalse(store.stage(candidate, expectedGeneration: generation))
        XCTAssertTrue(store.staged.isEmpty)
        XCTAssertFalse(store.stageError("late failure", expectedGeneration: generation))
        XCTAssertNil(store.error)
    }

    func testVoiceOfferIsVisibleUntilExplicitApprovalOrCancellation() {
        let store = AttachmentStore()
        let offer = InputOffer(
            sessionID: UUID(), generation: UUID(), requestID: UUID(), batchID: UUID(),
            attachmentIDs: [UUID()], question: "Explain this.",
            profile: ConsoleInputProfile(id: "vision", label: "Configured vision"))
        store.presentOffer(offer)
        XCTAssertEqual(store.pendingOffer, offer)
        store.clearOffer()
        XCTAssertNil(store.pendingOffer)
    }

    func testSpokenConsentIsAcceptedOnlyForTheVisibleOffer() {
        let store = AttachmentStore()
        let batch = UUID(), session = UUID(), generation = UUID()
        let offer = InputOffer(sessionID: session, generation: generation,
            requestID: UUID(), batchID: batch, attachmentIDs: [UUID()],
            question: "Explain", profile: ConsoleInputProfile(id: "vision", label: "Vision"))
        store.presentOffer(offer)
        store.presentConsent(InputConsent(sessionID: session, generation: generation,
            batchID: UUID(), approved: true))
        XCTAssertNil(store.pendingConsent)
        store.presentConsent(InputConsent(sessionID: session, generation: generation,
            batchID: batch, approved: true))
        XCTAssertTrue(store.pendingConsent?.approved == true)
    }
}
