import Foundation
@testable import JarvisKit

/// A stub RTVITransport that records outbound frames and lets a test
/// script inbound delegate events (connect success/failure, received
/// frames, keep-alive stall, peerLeft) without a real WebRTC session.
/// Used by §7.4's testConnectRereadsTokenFromKeychain and every test in
/// §7.5 (UICommandOwnershipTests).
final class StubTransport: RTVITransport {
    weak var delegate: RTVITransportDelegate?

    private(set) var sentFrames: [Data] = []
    private(set) var connectCallCount = 0
    private(set) var lastConfigSeenOnConnect: JarvisConfig?
    private(set) var micEnabledCalls: [Bool] = []

    var connectError: Error?
    var onConnect: ((JarvisConfig) -> Void)?

    func connect(config: JarvisConfig) async throws {
        connectCallCount += 1
        lastConfigSeenOnConnect = config
        onConnect?(config)
        if let connectError { throw connectError }
    }

    func disconnect() async {}

    func send(_ data: Data) throws {
        sentFrames.append(data)
    }

    func setMicEnabled(_ enabled: Bool) {
        micEnabledCalls.append(enabled)
    }

    // MARK: - Test-driven inbound events

    func simulateConnected() {
        delegate?.transportDidConnect()
    }

    func simulateDisconnected(error: Error?) {
        delegate?.transportDidDisconnect(error: error)
    }

    func simulateReceivedFrame(_ data: Data) {
        delegate?.transport(didReceiveFrame: data)
    }

    /// Convenience: wrap a bare payload in the server-message envelope
    /// and deliver it as an inbound frame, exactly as AppMessage.decode
    /// expects (or as the bare-payload defensive path also accepts).
    func simulateReceivedAppMessage(json: String) {
        simulateReceivedFrame(Data(json.utf8))
    }

    func simulateBotSpeaking(_ speaking: Bool) {
        delegate?.transport(botIsSpeaking: speaking)
    }
}

/// A URLProtocol stub for AdminAPI / JarvisHTTP tests — records the last
/// request and returns a scripted status/body.
final class StubURLProtocol: URLProtocol {
    static var requestCount = 0
    static var lastRequest: URLRequest?
    static var statusCode = 200
    static var responseBody = Data("{}".utf8)
    static var responseHeaders: [String: String] = [:]

    static func reset() {
        requestCount = 0
        lastRequest = nil
        statusCode = 200
        responseBody = Data("{}".utf8)
        responseHeaders = [:]
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requestCount += 1
        Self.lastRequest = request
        let response = HTTPURLResponse(
            url: request.url!, statusCode: Self.statusCode,
            httpVersion: "HTTP/1.1", headerFields: Self.responseHeaders
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// JarvisClient's RTVITransportDelegate conformance is `nonisolated` and
/// hops to @MainActor via an unstructured Task (review F5's documented
/// boundary — the real DirectWebRTCTransport calls these from its own
/// background serial queue). A test driving StubTransport synchronously
/// from @MainActor code needs to give that Task a turn before asserting
/// on the state it mutates; a few Task.yield()s is the standard,
/// dependency-free way to flush a MainActor's pending work queue.
@MainActor
func flushMainActor() async {
    for _ in 0..<5 { await Task.yield() }
}

// JarvisHTTP.send(_:config:) uses URLSession.shared (N13 — one function,
// one sender). URLProtocol.registerClass(StubURLProtocol.self) in a
// test's setUp/tearDown is what makes URLSession.shared route through
// the stub above; see ConfigAndAuthTests and AdminAPITests.
