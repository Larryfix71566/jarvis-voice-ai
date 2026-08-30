import XCTest
import JarvisKit
@testable import MortimerHost

/// APP plan §7.4 — the deterministic four-state mapping (P7/C10).
@MainActor
final class TabStateTests: XCTestCase {
    func testThrowMapsToError() {
        let (message, unauthorized) = TabStateMapper.fromError(JarvisError.http(status: 500, body: "x"))
        XCTAssertEqual(message, "HTTP 500: x")
        XCTAssertFalse(unauthorized)
    }

    func testOkFalseMapsToError() {
        let state: TabState<[Int]> = TabStateMapper.map(ok: false, error: "nope", isEmpty: false, value: [1])
        guard case .error(let message) = state else { return XCTFail("expected .error") }
        XCTAssertEqual(message, "nope")
    }

    func testOkFalseWithNoErrorGetsDefaultCopy() {
        let state: TabState<[Int]> = TabStateMapper.map(ok: false, error: nil, isEmpty: false, value: [])
        guard case .error(let message) = state else { return XCTFail("expected .error") }
        XCTAssertEqual(message, "request failed")
    }

    func testEmptyListMapsToEmpty() {
        let state: TabState<[Int]> = TabStateMapper.map(ok: true, error: nil, isEmpty: true, value: [])
        guard case .empty = state else { return XCTFail("expected .empty") }
    }

    func testLoadedOtherwise() {
        let state: TabState<[Int]> = TabStateMapper.map(ok: true, error: nil, isEmpty: false, value: [1, 2])
        guard case .loaded(let value) = state else { return XCTFail("expected .loaded") }
        XCTAssertEqual(value, [1, 2])
    }

    /// The 401 rule (N13 discipline): the specified copy, and the caller
    /// must stop its poll — RepoViewModel is the representative caller.
    func testUnauthorizedNoRetry() async {
        let (message, unauthorized) = TabStateMapper.fromError(JarvisError.unauthorized)
        XCTAssertEqual(message, "Token required — set it in the Debug menu")
        XCTAssertTrue(unauthorized)
    }
}
