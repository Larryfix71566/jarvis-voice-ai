import SwiftUI
import JarvisKit

/// Interface cleanup Phase 2. The quiet home for the clock, next reminder,
/// weather and battery/vitals warning that Phase 1 took off the stage.
/// Resting: the time, plus an amber dot only when something needs attention.
/// Click: a popover with the detail. Never shows the last-session summary
/// (Fable change C: no raw memory-note text), and being down adds no error
/// surface: hidden content simply stays hidden.

/// What the popover shows. Pure value so tests need no client or view.
struct GlanceContent: Equatable {
    var time: String
    var date: String
    var reminder: String?
    var weather: String?
    var warning: String?
    var needsAttention: Bool
}

enum Glance {
    /// SystemVitals' flag threshold (the sidecar flags at the same 85%).
    static let metricThresholdPercent = 85.0

    static func timeText(_ date: Date) -> String {
        date.formatted(.dateTime.hour(.defaultDigits(amPM: .omitted)).minute())
    }

    static func dateText(_ date: Date) -> String {
        date.formatted(.dateTime.weekday(.wide).month(.wide).day())
    }

    /// Battery at or under the existing low-battery rule, or any metric over
    /// 85%, or the sidecar's own flags.
    static func needsAttention(system: AmbientSystem?) -> Bool {
        guard let system else { return false }
        if !system.flags.isEmpty { return true }
        if let battery = system.battery, battery <= AppTuning.lowBatteryPercent { return true }
        let metrics: [Double?] = [system.cpu, system.memory, system.disk]
        return metrics.contains { ($0 ?? 0) > metricThresholdPercent }
    }

    /// Reminder expiry, as AmbientStripView: gone 60 s past due; an
    /// unparseable due_at is never treated as expired.
    static func reminderExpired(_ reminder: AmbientReminder, now: Date) -> Bool {
        guard let due = parseISO(reminder.dueAt) else { return false }
        return now > due.addingTimeInterval(AppTuning.reminderExpiryGraceSeconds)
    }

    static func lines(now: Date, ambient: AmbientResponse?, connected: Bool) -> GlanceContent {
        var content = GlanceContent(time: timeText(now), date: dateText(now), reminder: nil,
                                    weather: nil, warning: nil, needsAttention: false)
        guard connected, let ambient, ambient.ok else { return content }

        if let reminder = ambient.reminder, !reminder.text.isEmpty, !reminderExpired(reminder, now: now) {
            if let due = parseISO(reminder.dueAt) {
                let dueText = due.formatted(.dateTime.hour().minute())
                content.reminder = "\(reminder.text) · \(dueText)"
            } else {
                content.reminder = reminder.text
            }
        }
        if let weather = ambient.weather, !weather.summary.isEmpty {
            let temp = "\(Int(weather.tempF.rounded()))°"
            content.weather = weather.location.isEmpty
                ? "\(weather.summary) \(temp)" : "\(weather.summary) \(temp) · \(weather.location)"
        }
        content.warning = warningText(ambient.system)
        content.needsAttention = needsAttention(system: ambient.system)
        return content
    }

    static func warningText(_ system: AmbientSystem?) -> String? {
        guard let system, needsAttention(system: system) else { return nil }
        var parts: [String] = []
        if let battery = system.battery, battery <= AppTuning.lowBatteryPercent {
            parts.append("Battery \(Int(battery.rounded()))%")
        }
        let named: [(String, Double?)] = [("CPU", system.cpu), ("Memory", system.memory), ("Disk", system.disk)]
        for (label, value) in named {
            if let value, value > metricThresholdPercent {
                parts.append("\(label) \(Int(value.rounded()))%")
            }
        }
        if parts.isEmpty { parts.append("System under load") }
        return parts.joined(separator: " · ")
    }
}

struct GlanceButton: View {
    @EnvironmentObject private var client: JarvisClient
    @State private var model = AmbientModel()
    @State private var open = false

    private var connected: Bool { client.state == .connected }

    var body: some View {
        TimelineView(.periodic(from: .now, by: 10)) { context in
            glanceButton(now: context.date)
        }
        .onAppear { if connected { model.start(api: client.admin) } }
        .onChange(of: connected) { _, isConnected in
            if isConnected { model.start(api: client.admin) } else { model.stop() }
        }
        .onDisappear { model.stop() }
    }

    private func glanceButton(now: Date) -> some View {
        let content = Glance.lines(now: now, ambient: model.data, connected: connected)
        return Button {
            open.toggle()
        } label: {
            HStack(spacing: 5) {
                Text(content.time)
                    .font(.system(size: 12, design: .monospaced))
                    .monospacedDigit()
                    .foregroundStyle(AppTheme.textDim)
                if content.needsAttention {
                    Circle().fill(AppTheme.amber).frame(width: 6, height: 6)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Glance: \(content.time)")
        .accessibilityIdentifier("console.glance")
        .popover(isPresented: $open, arrowEdge: .bottom) {
            popoverBody(content)
        }
    }

    private func popoverBody(_ content: GlanceContent) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(content.time)
                    .font(.system(size: 26, weight: .light, design: .monospaced))
                    .foregroundStyle(AppTheme.text)
                Text(content.date)
                    .font(.system(size: 12))
                    .foregroundStyle(AppTheme.textDim)
            }
            if let reminder = content.reminder { row("Next reminder", reminder, AppTheme.text) }
            if let weather = content.weather { row("Weather", weather, AppTheme.text) }
            if let warning = content.warning { row("Warning", warning, AppTheme.amber) }
        }
        .padding(14)
        .frame(minWidth: 220, alignment: .leading)
    }

    private func row(_ title: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title).font(.system(size: 10)).foregroundStyle(AppTheme.textDim)
            Text(value).font(.system(size: 12)).foregroundStyle(color)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}
