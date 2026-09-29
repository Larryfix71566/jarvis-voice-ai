import Foundation

/// WS-15 PR 2 (MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md S6): the weather
/// card's structured view, built by jarvis/bot/weather_card.py (schema 1).
/// Every string is display-ready in the user's units; the app only lays it
/// out. Decoded leniently by DisplayPayload: an unknown schema or a malformed
/// object leaves `weather` nil and the payload falls back to its markdown
/// body.
public struct WeatherCard: Sendable, Equatable, Decodable {
    public struct Place: Sendable, Equatable, Decodable {
        public let label: String
        public let lat: Double?
        public let lon: Double?
        public let source: String
        public let approximate: Bool
    }
    public struct Now: Sendable, Equatable, Decodable {
        public let temp: String?
        public let condition: String
        public let humidity: String?
        public let wind: String?
        public let symbol: String
    }
    public struct Day: Sendable, Equatable, Decodable {
        public let name: String
        public let high: String?
        public let low: String?
        public let pop: String?
        public let condition: String
        public let symbol: String
    }
    public struct Hour: Sendable, Equatable, Decodable {
        public let label: String
        public let temp: String?
        public let pop: String?
        public let symbol: String
    }
    public struct Alert: Sendable, Equatable, Decodable {
        public let event: String
        public let headline: String
    }
    public struct RadarFrame: Sendable, Equatable, Decodable {
        public let label: String
        public let template: String
    }
    public struct Radar: Sendable, Equatable, Decodable {
        public let provider: String
        public let maxNativeZoom: Int
        public let frames: [RadarFrame]
        public let attribution: String
        enum CodingKeys: String, CodingKey {
            case provider, frames, attribution
            case maxNativeZoom = "max_native_zoom"
        }
    }

    public static let supportedSchema = 1

    public let schema: Int
    public let place: Place
    public let units: String
    public let now: Now
    public let days: [Day]
    public let hourly: [Hour]
    public let alerts: [Alert]
    public let radar: Radar?
    public let summary: String
    public let attribution: String

    enum CodingKeys: String, CodingKey {
        case schema, place, units, now, days, hourly, alerts, radar, summary, attribution
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        schema = try c.decode(Int.self, forKey: .schema)
        guard schema == Self.supportedSchema else {
            throw DecodingError.dataCorruptedError(
                forKey: .schema, in: c, debugDescription: "unsupported weather card schema \(schema)")
        }
        place = try c.decode(Place.self, forKey: .place)
        units = try c.decodeIfPresent(String.self, forKey: .units) ?? "imperial"
        now = try c.decode(Now.self, forKey: .now)
        days = try c.decodeIfPresent([Day].self, forKey: .days) ?? []
        hourly = try c.decodeIfPresent([Hour].self, forKey: .hourly) ?? []
        alerts = try c.decodeIfPresent([Alert].self, forKey: .alerts) ?? []
        radar = try c.decodeIfPresent(Radar.self, forKey: .radar)
        summary = try c.decodeIfPresent(String.self, forKey: .summary) ?? ""
        attribution = try c.decodeIfPresent(String.self, forKey: .attribution) ?? ""
    }
}
