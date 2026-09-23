import XCTest
@testable import JarvisKit

final class MessagePrivacyTests: XCTestCase {
    func testApprovalIsSessionScopedAndRevocable() {
        let id = UUID(); var privacy = MessagePrivacy(sessionID: UUID())
        XCTAssertFalse(privacy.canTransfer(id))
        privacy.approve(id); XCTAssertTrue(privacy.canTransfer(id))
        privacy.revoke(id); XCTAssertFalse(privacy.canTransfer(id))
    }
}
