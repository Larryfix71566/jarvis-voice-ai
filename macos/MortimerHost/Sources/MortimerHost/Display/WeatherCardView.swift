import SwiftUI
import JarvisKit

/// WS-15 PR 2 (MORTIMER_WEATHER_LOCATION_AND_RADAR_PLAN.md S6): the whole
/// weather answer as ONE card: where, now, alerts, the next hours, the
/// week, and Apple's map with the radar loop. Larry, 2026-09-29: "they
/// should be on one window" — AppMessageRouter keeps this card in the main
/// window and brings it to the front.
struct WeatherCardView: View {
    let card: WeatherCard
    @State private var hybrid = false
    @State private var playing = true
    @State private var frame = 0
    @State private var radarReady = false
    /// WS-15 voice map control; the serial seen when this card appeared, so
    /// an old command is not replayed onto a new card.
    @State private var zoomCommand: WeatherMapCommand? = nil
    @State private var seenSerial = WeatherMapCommands.shared.serial

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            ForEach(Array(card.alerts.enumerated()), id: \.offset) { _, alert in
                alertBanner(alert)
            }
            if !card.hourly.isEmpty { hourlyStrip }
            if !card.days.isEmpty { week }
            map
            Text(footer)
                .font(.caption)
                .foregroundStyle(AppTheme.textDim)
        }
        .padding(4)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Weather for \(card.place.label)")
        .onChange(of: WeatherMapCommands.shared.serial) { _, serial in
            guard serial != seenSerial, let action = WeatherMapCommands.shared.latest else { return }
            seenSerial = serial
            switch action {
            case "radar_pause": playing = false
            case "radar_play": playing = true
            case "map_satellite": hybrid = true
            case "map_standard": hybrid = false
            default: zoomCommand = WeatherMapCommands.shared.latestCommand
            }
        }
    }

    // MARK: sections

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            Image(systemName: card.now.symbol)
                .symbolRenderingMode(.multicolor)
                .font(.system(size: 40))
            VStack(alignment: .leading, spacing: 2) {
                Text(card.place.label).font(.title3.weight(.semibold))
                Text(WeatherCardText.placeNote(card.place))
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let temp = card.now.temp {
                        Text(temp).font(.system(size: 34, weight: .semibold))
                    }
                    Text(card.now.condition).font(.title3)
                }
                Text(WeatherCardText.details(card.now))
                    .font(.callout).foregroundStyle(AppTheme.textDim)
            }
            Spacer(minLength: 0)
        }
    }

    private func alertBanner(_ alert: WeatherCard.Alert) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(AppTheme.amber)
            VStack(alignment: .leading, spacing: 2) {
                Text(alert.event).font(.callout.weight(.semibold))
                if !alert.headline.isEmpty {
                    Text(alert.headline).font(.caption).foregroundStyle(AppTheme.textDim)
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.attnDim.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
    }

    private var hourlyStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 16) {
                ForEach(Array(card.hourly.enumerated()), id: \.offset) { _, hour in
                    VStack(spacing: 4) {
                        Text(hour.label).font(.caption).foregroundStyle(AppTheme.textDim)
                        Image(systemName: hour.symbol).symbolRenderingMode(.multicolor)
                        Text(hour.temp ?? "–").font(.callout)
                        Text(hour.pop ?? " ").font(.caption2).foregroundStyle(AppTheme.accent)
                    }
                    .frame(minWidth: 40)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var week: some View {
        VStack(spacing: 0) {
            ForEach(Array(card.days.enumerated()), id: \.offset) { index, day in
                HStack(spacing: 10) {
                    Text(day.name).frame(width: 110, alignment: .leading).lineLimit(1)
                    Image(systemName: day.symbol).symbolRenderingMode(.multicolor)
                        .frame(width: 24)
                    Text(day.pop ?? "").font(.caption).foregroundStyle(AppTheme.accent)
                        .frame(width: 40, alignment: .leading)
                    Text(day.condition).font(.callout).foregroundStyle(AppTheme.textDim)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    Text(WeatherCardText.range(day)).monospacedDigit()
                }
                .padding(.vertical, 6)
                if index < card.days.count - 1 { Divider() }
            }
        }
    }

    @ViewBuilder
    private var map: some View {
        if let radar = card.radar, let lat = card.place.lat, let lon = card.place.lon {
            VStack(alignment: .leading, spacing: 6) {
                RadarMapView(radar: radar, latitude: lat, longitude: lon,
                             placeLabel: card.place.label, hybrid: hybrid, playing: playing,
                             zoomCommand: zoomCommand,
                             onFrame: { frame = $0 }, onReady: { radarReady = $0 })
                    .frame(height: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .accessibilityLabel("Radar map around \(card.place.label)")
                HStack(spacing: 12) {
                    if radar.frames.count > 1 {
                        Button {
                            playing.toggle()
                        } label: {
                            Image(systemName: playing ? "pause.fill" : "play.fill")
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(playing ? "Pause radar loop" : "Play radar loop")
                    }
                    Text(WeatherCardText.radarStatus(radar, index: frame, ready: radarReady))
                        .font(.caption).monospacedDigit()
                    Spacer()
                    Picker("Map", selection: $hybrid) {
                        Text("Map").tag(false)
                        Text("Satellite").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                }
            }
        } else if card.place.lat != nil {
            Text("Radar isn't available for this place right now.")
                .font(.callout).foregroundStyle(AppTheme.textDim)
        }
    }

    private var footer: String {
        [card.attribution, card.radar?.attribution].compactMap { $0 }.filter { !$0.isEmpty }
            .joined(separator: " · ")
    }
}

/// Pure text helpers for the card, unit-tested (WeatherCardTextTests).
enum WeatherCardText {
    static func placeNote(_ place: WeatherCard.Place) -> String {
        switch place.source {
        case "device": return place.approximate ? "Approximate — this Mac's location" : "This Mac's location"
        case "ip": return "Approximate — from the internet connection"
        default: return "As requested"
        }
    }

    static func details(_ now: WeatherCard.Now) -> String {
        [now.humidity.map { "Humidity \($0)" }, now.wind.map { "Wind \($0)" }]
            .compactMap { $0 }.joined(separator: " · ")
    }

    static func range(_ day: WeatherCard.Day) -> String {
        switch (day.high, day.low) {
        case let (high?, low?): return "\(high) / \(low)"
        case let (high?, nil): return high
        case let (nil, low?): return "low \(low)"
        default: return "–"
        }
    }

    /// "Loading radar…" until the shown frame's tiles are in, then the frame.
    static func radarStatus(_ radar: WeatherCard.Radar, index: Int, ready: Bool) -> String {
        ready ? frameLabel(radar, index: index) : "Loading radar…"
    }

    static func frameLabel(_ radar: WeatherCard.Radar, index: Int) -> String {
        guard radar.frames.indices.contains(index) else { return "Radar" }
        return "Radar · \(radar.frames[index].label)"
    }
}
