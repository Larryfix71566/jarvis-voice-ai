import Foundation

/// The seam both branches implement. No Sendable on either protocol
/// (review F5): the conformer DirectWebRTCTransport holds
/// RTCPeerConnection, RTCDataChannel, the ICE buffer, the outbound queue
/// and storedPCID — none Sendable — and a `var delegate { get set }`
/// requirement is not Sendable-safe. It is a reference type that
/// serialises its own mutable state on a single internal serial
/// DispatchQueue; delegate callbacks hop to @MainActor at the
/// JarvisClient boundary.
protocol RTVITransport: AnyObject {
    var delegate: RTVITransportDelegate? { get set }
    func connect(config: JarvisConfig) async throws
    func disconnect() async
    func send(_ data: Data) throws          // one data-channel text frame
    func setMicEnabled(_ enabled: Bool)
}

protocol RTVITransportDelegate: AnyObject {
    func transportDidConnect()
    func transportDidDisconnect(error: Error?)
    func transport(didReceiveFrame data: Data)
    func transport(botIsSpeaking: Bool)     // inbound audio RMS crossing, step 8
}
