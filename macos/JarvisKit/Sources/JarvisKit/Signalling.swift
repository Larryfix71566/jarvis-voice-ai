import Foundation

struct OfferRequest: Encodable {
    let sdp: String
    let type: String          // "offer"
    var pc_id: String?        // request_handler.py:39
    var restart_pc: Bool?     // request_handler.py:40
}
struct OfferAnswer: Decodable {
    let sdp: String
    let type: String
    let pc_id: String         // connection.py:558-561
}
struct WireIceCandidate: Encodable {
    let candidate: String
    let sdp_mid: String       // request_handler.py:62
    let sdp_mline_index: Int  // request_handler.py:63
}
struct PatchRequest: Encodable {
    let pc_id: String
    let candidates: [WireIceCandidate]
}

/// Both build config.botURL.appending(path: "api/offer"), set
/// Content-Type: application/json, encode with a JSONEncoder whose
/// keyEncodingStrategy is left DEFAULT — the keys above are already the
/// wire names; do not use .convertToSnakeCase (explicit names cannot
/// drift, a strategy could).
enum Signalling {
    /// POST <botURL>/api/offer  (pipecat/runner/run.py:795)
    static func postOffer(_ body: OfferRequest, config: JarvisConfig) async throws -> OfferAnswer {
        var req = URLRequest(url: config.botURL.appending(path: "api/offer"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, _) = try await JarvisHTTP.send(req, config: config)
        return try JSONDecoder().decode(OfferAnswer.self, from: data)
    }

    /// PATCH <botURL>/api/offer (pipecat/runner/run.py:827)
    static func patch(_ body: PatchRequest, config: JarvisConfig) async throws {
        var req = URLRequest(url: config.botURL.appending(path: "api/offer"))
        req.httpMethod = "PATCH"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        _ = try await JarvisHTTP.send(req, config: config)
    }
}
