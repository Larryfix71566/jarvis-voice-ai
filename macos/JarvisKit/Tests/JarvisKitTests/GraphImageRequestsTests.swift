import XCTest
@testable import JarvisKit

private actor GraphFetchProbe {
    private(set) var calls = 0
    private(set) var cancellations = 0
    func fetch() async throws -> Data {
        calls += 1
        do { try await Task.sleep(nanoseconds: 100_000_000) }
        catch { cancellations += 1; throw error }
        return Data([1, 2, 3])
    }
}

final class GraphImageRequestsTests: XCTestCase {
    let url = URL(string: "http://localhost/api/graph/memory/image.png?w=800")!

    func testConcurrentViewsShareOneReadAndLaterReadIsFresh() async throws {
        let requests = GraphImageRequests(), probe = GraphFetchProbe()
        async let first = requests.data(at: url) { try await probe.fetch() }
        async let second = requests.data(at: url) { try await probe.fetch() }
        let (a, b) = try await (first, second)
        XCTAssertEqual(a, b)
        let sharedCalls = await probe.calls
        XCTAssertEqual(sharedCalls, 1)
        _ = try await requests.data(at: url) { try await probe.fetch() }
        let freshCalls = await probe.calls
        XCTAssertEqual(freshCalls, 2, "completed data must not become a stale cache")
    }

    func testCancellingOneViewPreservesOtherView() async throws {
        let requests = GraphImageRequests(), probe = GraphFetchProbe()
        let first = Task { try await requests.data(at: url) { try await probe.fetch() } }
        let second = Task { try await requests.data(at: url) { try await probe.fetch() } }
        try await Task.sleep(nanoseconds: 20_000_000)
        first.cancel()
        let result = try await second.value
        XCTAssertEqual(result, Data([1, 2, 3]))
        do { _ = try await first.value; XCTFail("cancelled view must not receive an image") }
        catch is CancellationError {} catch { XCTFail("Unexpected error: \(error)") }
        let calls = await probe.calls
        let cancellations = await probe.cancellations
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(cancellations, 0)
    }

    func testLastViewCancellationStopsFetchAndAllowsRetry() async throws {
        let requests = GraphImageRequests(), probe = GraphFetchProbe()
        let first = Task { try await requests.data(at: url) { try await probe.fetch() } }
        try await Task.sleep(nanoseconds: 20_000_000)
        first.cancel()
        do { _ = try await first.value; XCTFail("cancelled read must fail") }
        catch is CancellationError {} catch { XCTFail("Unexpected error: \(error)") }
        let cancellations = await probe.cancellations
        XCTAssertEqual(cancellations, 1)
        _ = try await requests.data(at: url) { try await probe.fetch() }
        let calls = await probe.calls
        XCTAssertEqual(calls, 2)
    }

    func testDifferentSizesAndSeparateOwnersDoNotShare() async throws {
        let requests = GraphImageRequests(), other = GraphImageRequests(), probe = GraphFetchProbe()
        let resized = URL(string: "http://localhost/api/graph/memory/image.png?w=900")!
        async let first = requests.data(at: url) { try await probe.fetch() }
        async let second = requests.data(at: resized) { try await probe.fetch() }
        async let third = other.data(at: url) { try await probe.fetch() }
        _ = try await (first, second, third)
        let calls = await probe.calls
        XCTAssertEqual(calls, 3)
    }

    func testFailedReadDoesNotPoisonRetry() async throws {
        let requests = GraphImageRequests()
        do {
            _ = try await requests.data(at: url) { throw URLError(.notConnectedToInternet) }
            XCTFail("network failure must propagate")
        } catch let error as URLError { XCTAssertEqual(error.code, .notConnectedToInternet) }
        let retried = try await requests.data(at: url) { Data([4]) }
        XCTAssertEqual(retried, Data([4]))
    }
}
