import Foundation
import JarvisKit

/// Test-only text fixture. Production accepts display payloads through the
/// decoder; there is no transcript-to-result payload constructor.
func decodedResponsePayload(text: String, timestamp: Double) -> DisplayPayload {
    let fields: [String: Any] = ["kind": "text", "title": "Mortimer response", "body": text,
        "agent": "Mortimer", "ts": timestamp, "surface": "window"]
    return try! JSONDecoder().decode(DisplayPayload.self,
        from: JSONSerialization.data(withJSONObject: fields))
}
