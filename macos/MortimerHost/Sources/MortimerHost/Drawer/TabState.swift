import Foundation
import JarvisKit

/// APP plan §3 P7 — every HTTP tab renders exactly one of four states
/// (C10). The mapping is a deterministic rule, applied by every
/// view-model through these helpers and pinned by TabStateTests (§7.4).
enum TabState<T> {
    case loading
    case loaded(T)
    case empty
    case error(String)
}

enum TabStateMapper {
    /// A thrown JarvisError → .error(message). 401 gets the specified
    /// copy and the caller must stop its poll (testUnauthorizedNoRetry).
    static func fromError(_ error: Error) -> (state: String, isUnauthorized: Bool) {
        if let jarvisError = error as? JarvisError {
            switch jarvisError {
            case .unauthorized:
                return ("Token required — set it in the Debug menu", true)
            case .forbidden:
                return ("Forbidden", false)
            case .http(let status, let body):
                return ("HTTP \(status): \(body)", false)
            case .transport(let message):
                return (message, false)
            case .decoding(let message):
                return ("Decode failed: \(message)", false)
            case .insecureHost(let host):
                return ("Refusing insecure host: \(host)", false)
            }
        }
        return (error.localizedDescription, false)
    }

    /// A decoded body: ok == false → .error(body.error ?? "request
    /// failed"); an empty list payload → .empty; else .loaded.
    static func map<T>(ok: Bool, error: String?, isEmpty: Bool, value: T) -> TabState<T> {
        if !ok { return .error(error ?? "request failed") }
        if isEmpty { return .empty }
        return .loaded(value)
    }
}
