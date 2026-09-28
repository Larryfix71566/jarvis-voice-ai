import Foundation

/// MORTIMER_VOICE_WORKFLOWS_PLAN.md Phase 2 D4 (Larry's decision D-L6,
/// 2026-09-25): "where am I" asks the device Larry is talking through, on
/// this session's own data channel, before any IP lookup. The wire shapes
/// mirror jarvis/bot/device_location.py; the bot only asks after this
/// client has sent `location/hello`.
public struct LocationRequest: Codable, Sendable, Equatable {
    public let type: String
    public let version: Int
    public let requestID: String
    public let accuracyM: Double

    enum CodingKeys: String, CodingKey {
        case type, version, requestID = "request_id", accuracyM = "accuracy_m"
    }

    public init(requestID: String, accuracyM: Double = 100) {
        self.type = "location/request"
        self.version = 1
        self.requestID = requestID
        self.accuracyM = accuracyM
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? "location/request"
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? 1
        requestID = String(try c.decode(String.self, forKey: .requestID).prefix(64))
        accuracyM = try c.decodeIfPresent(Double.self, forKey: .accuracyM) ?? 100
    }
}

/// What Location Services currently allows this app, as the bot logs it.
public enum LocationAuthorization: String, Codable, Sendable {
    case authorized, denied, restricted
    case notDetermined = "not_determined"
    case unknown
}

public struct LocationHello: Encodable, Sendable, Equatable {
    public let type = "location/hello"
    public let version = 1
    public let authorization: LocationAuthorization

    public init(authorization: LocationAuthorization) {
        self.authorization = authorization
    }
}

/// Why no fix: `denied` when Location Services is off for the app,
/// `unavailable` for anything else CoreLocation reports.
public enum LocationFailure: String, Sendable {
    case denied, unavailable
}

public struct LocationResult: Encodable, Sendable, Equatable {
    public let type = "location/result"
    public let version = 1
    public let requestID: String
    public let ok: Bool
    public let lat: Double?
    public let lon: Double?
    public let accuracyM: Double?
    public let ageS: Double?
    public let label: String?
    public let error: String?

    enum CodingKeys: String, CodingKey {
        case type, version, requestID = "request_id", ok, lat, lon
        case accuracyM = "accuracy_m", ageS = "age_s", label, error
    }

    public static func fix(requestID: String, lat: Double, lon: Double,
                           accuracyM: Double, ageS: Double, label: String?) -> LocationResult {
        LocationResult(requestID: requestID, ok: true, lat: lat, lon: lon,
                       accuracyM: max(0, accuracyM), ageS: max(0, ageS),
                       label: label, error: nil)
    }

    public static func failure(requestID: String, _ failure: LocationFailure) -> LocationResult {
        LocationResult(requestID: requestID, ok: false, lat: nil, lon: nil,
                       accuracyM: nil, ageS: nil, label: nil, error: failure.rawValue)
    }

    private init(requestID: String, ok: Bool, lat: Double?, lon: Double?, accuracyM: Double?,
                 ageS: Double?, label: String?, error: String?) {
        self.requestID = requestID
        self.ok = ok
        self.lat = lat
        self.lon = lon
        self.accuracyM = accuracyM
        self.ageS = ageS
        self.label = label
        self.error = error
    }
}
