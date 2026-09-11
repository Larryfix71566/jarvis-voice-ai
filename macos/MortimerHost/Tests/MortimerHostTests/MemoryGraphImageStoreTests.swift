import XCTest
import JarvisKit
@testable import MortimerHost

private actor ImageReadProbe {
    var calls = 0
    let png = Data(base64Encoded: "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1cAAAAASUVORK5CYII=")!
    func fetch(_ query: MemoryGraphQuery) async throws -> Data {
        calls += 1
        if query.focus == "slow" {
            // Deliberately ignore cancellation to prove stale replies are rejected.
            try? await Task.sleep(nanoseconds: 80_000_000)
            return Data("obsolete invalid image".utf8)
        }
        return png
    }
}

@MainActor
final class MemoryGraphImageStoreTests: XCTestCase {
    func testReparentingReusesImageAndStaleFocusCannotOverwriteIt() async throws {
        let store = MemoryGraphImageStore(), probe = ImageReadProbe()
        store.load(query: MemoryGraphQuery(focus: "slow")) { try await probe.fetch($0) }
        try await Task.sleep(nanoseconds: 10_000_000)
        store.load(query: MemoryGraphQuery(focus: "current")) { try await probe.fetch($0) }
        for _ in 0..<100 {
            if !store.loading { break }
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertNotNil(store.image)
        let image = store.image
        store.load(query: MemoryGraphQuery(focus: "current")) { try await probe.fetch($0) }
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertTrue(store.image === image)
        XCTAssertNil(store.error)
        let calls = await probe.calls
        XCTAssertEqual(calls, 2)
    }

    func testCancelledImageStaysStoppedUntilExplicitReload() async throws {
        let store = MemoryGraphImageStore(), probe = ImageReadProbe()
        let query = MemoryGraphQuery(focus: "slow")
        store.load(query: query) { try await probe.fetch($0) }
        try await Task.sleep(nanoseconds: 10_000_000)
        store.cancel()
        XCTAssertFalse(store.loading)
        XCTAssertNil(store.image)
        XCTAssertEqual(store.error, "Image request cancelled. Choose Reload image to try again.")
        // Rebuilding a view must not restart an explicitly cancelled read.
        store.load(query: query) { try await probe.fetch($0) }
        try await Task.sleep(nanoseconds: 100_000_000)
        let calls = await probe.calls
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(store.error, "Image request cancelled. Choose Reload image to try again.")
        store.load(query: query, force: true) { _ in try await probe.fetch(MemoryGraphQuery()) }
        for _ in 0..<100 where store.loading { try await Task.sleep(nanoseconds: 5_000_000) }
        XCTAssertNotNil(store.image)
        XCTAssertNil(store.error)
    }

    func testInvalidImageHasExplicitErrorAndCanRetry() async throws {
        let store = MemoryGraphImageStore(), probe = ImageReadProbe()
        store.load(query: MemoryGraphQuery()) { _ in Data("invalid".utf8) }
        for _ in 0..<100 {
            if !store.loading { break }
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertNil(store.image); XCTAssertNotNil(store.error)
        store.load(query: MemoryGraphQuery(), force: true) { try await probe.fetch($0) }
        for _ in 0..<100 {
            if !store.loading { break }
            try await Task.sleep(nanoseconds: 5_000_000)
        }
        XCTAssertNotNil(store.image); XCTAssertNil(store.error)
    }
}
