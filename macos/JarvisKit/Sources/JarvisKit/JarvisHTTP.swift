import Foundation

public enum JarvisError: Error, Equatable {
    case unauthorized, forbidden
    case http(status: Int, body: String)
    case transport(String)
    case decoding(String)
    case insecureHost(String)   // C2/F6: non-loopback reached without a token
}

/// N13: every HTTP request in JarvisKit goes through this one function.
/// K1 says the Authorization header goes on EVERY sidecar /api/* route
/// AND on the bot's signalling routes — one attach point here is how
/// that stays true without two code paths to keep in sync.
public enum JarvisHTTP {
    public static let timeoutSeconds: TimeInterval = 15   // §6

    public static func send(_ req: URLRequest, config: JarvisConfig)
        async throws -> (Data, HTTPURLResponse)
    {
        var r = req
        r.timeoutInterval = timeoutSeconds
        if r.value(forHTTPHeaderField: "Accept") == nil {
            r.setValue("application/json", forHTTPHeaderField: "Accept")
        }
        // K1 — Authorization on EVERY sidecar /api/* route AND on the bot's
        // signalling routes. One attach point; there is no other sender.
        if let t = config.token { r.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
        let (data, resp) = try await URLSession.shared.data(for: r)
        guard let http = resp as? HTTPURLResponse else { throw JarvisError.transport("non-HTTP response") }
        switch http.statusCode {
        case 200...299: return (data, http)
        case 401:       throw JarvisError.unauthorized
        case 403:       throw JarvisError.forbidden
        default:        throw JarvisError.http(status: http.statusCode,
                                               body: String(data: data, encoding: .utf8) ?? "")
        }
    }
}
