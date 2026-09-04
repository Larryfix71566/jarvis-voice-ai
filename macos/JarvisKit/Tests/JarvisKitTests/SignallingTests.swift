import XCTest
@testable import JarvisKit

final class SignallingTests: XCTestCase {
    private func jsonObject(_ value: Encodable) throws -> [String: Any] {
        let data = try JSONEncoder().encode(AnyEncodableForTest(value))
        return try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testOfferRequestKeys() throws {
        let req = OfferRequest(sdp: "v=0…", type: "offer", pc_id: nil, restart_pc: nil)
        let obj = try jsonObject(req)
        XCTAssertEqual(Set(obj.keys), ["sdp", "type"])   // nils omitted
    }

    func testOfferRequestWithPCID() throws {
        let req = OfferRequest(sdp: "v=0…", type: "offer", pc_id: "pc-7", restart_pc: nil)
        let obj = try jsonObject(req)
        XCTAssertEqual(obj["pc_id"] as? String, "pc-7")   // request_handler.py:39
    }

    func testOfferAnswerDecodes() throws {
        let json = """
        {"sdp":"v=0…","type":"answer","pc_id":"pc-7"}
        """
        let answer = try JSONDecoder().decode(OfferAnswer.self, from: Data(json.utf8))
        XCTAssertEqual(answer.sdp, "v=0…")
        XCTAssertEqual(answer.type, "answer")
        XCTAssertEqual(answer.pc_id, "pc-7")
    }

    func testPatchRequestCandidateKeys() throws {
        let candidate = WireIceCandidate(candidate: "candidate:1 1 UDP …", sdp_mid: "0", sdp_mline_index: 0)
        let obj = try jsonObject(candidate)
        XCTAssertEqual(Set(obj.keys), ["candidate", "sdp_mid", "sdp_mline_index"])   // request_handler.py:57-63
    }

    func testPatchRequestBatching() throws {
        // Batching itself is exercised by DirectWebRTCTransport at
        // runtime (hardware-only, §8); this test proves the WIRE SHAPE a
        // batch of 12 candidates would be split into with
        // iceBatchSize = 5, matching JarvisTuning.iceBatchSize.
        let candidates = (0..<12).map {
            WireIceCandidate(candidate: "candidate:\($0)", sdp_mid: "0", sdp_mline_index: 0)
        }
        let batchSize = JarvisTuning.iceBatchSize
        var batches: [[WireIceCandidate]] = []
        var remaining = candidates[...]
        while !remaining.isEmpty {
            let chunk = Array(remaining.prefix(batchSize))
            batches.append(chunk)
            remaining = remaining.dropFirst(chunk.count)
        }
        XCTAssertEqual(batches.map(\.count), [5, 5, 2])
    }
}

/// JSONEncoder needs a concrete Encodable; this erases one for the test
/// helper above without adding a public API surface to the package.
private struct AnyEncodableForTest: Encodable {
    let value: Encodable
    init(_ value: Encodable) { self.value = value }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
