import SwiftUI
import JarvisKit

/// AmbientStrip — the idle screen's signs of life, ported from
/// web/src/components/AmbientStrip.tsx (E4, parity sweep 2026-08-30).
///
/// Top-left of the stage: clock (always, client-side — large thin time
/// over a small uppercase date, the minute as a one-pixel hairline) +
/// next reminder / live weather / last-session summary from
/// GET /api/ambient, polled every 60s. Chips hide when null or when the
/// sidecar is down — being down must never add an error surface. Renders
/// nothing while disconnected.
///
/// The informational chips (not the clock) are dismissible via a hover ×;
/// a dismissal hides that chip until its CONTENT changes, persisted in
/// UserDefaults keyed by the dismissed content (the web's localStorage
/// scheme carried over). The reminder chip self-expires 60s past due_at.
///
/// Deviation on the record: the web's legacy localStorage weather-cache
/// fallback (for a sidecar predating the `weather` field) is not ported —
/// Larry's sidecar serves `weather`, and the cache's only writer was the
/// web console itself.
@MainActor
@Observable
final class AmbientModel {
    private(set) var data: AmbientResponse?
    private(set) var now = Date()
    private(set) var dismissed: [String: String] = [:]   // chip type -> content key

    private var pollTask: Task<Void, Never>?
    private var clockTask: Task<Void, Never>?
    private static let dismissedKey = "mortimer.ambient.dismissed"

    init() {
        if let stored = UserDefaults.standard.dictionary(forKey: Self.dismissedKey) as? [String: String] {
            dismissed = stored
        }
    }

    func start(api: AdminAPI) {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                // Failure hides the sidecar-backed chips, silently
                // (AmbientStrip.tsx:111-130).
                let response = try? await api.ambientTyped()
                self?.data = (response?.ok == true) ? response : nil
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.ambientPollSeconds * 1_000_000_000))
            }
        }
        // 10s clock tick — six minute-hairline steps per minute; also
        // what re-evaluates reminder expiry (AmbientStrip.tsx:94-109).
        clockTask = Task { [weak self] in
            while !Task.isCancelled {
                self?.now = Date()
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.ambientClockTickSeconds * 1_000_000_000))
            }
        }
    }

    func stop() {
        pollTask?.cancel(); pollTask = nil
        clockTask?.cancel(); clockTask = nil
    }

    func dismiss(_ type: String, contentKey: String) {
        dismissed[type] = contentKey
        UserDefaults.standard.set(dismissed, forKey: Self.dismissedKey)
    }
}

struct AmbientStripView: View {
    let connected: Bool
    @EnvironmentObject private var client: JarvisClient
    @State private var model = AmbientModel()

    var body: some View {
        Group {
            if connected {
                VStack(alignment: .leading, spacing: 6) {
                    clockBlock
                    if let reminder = model.data?.reminder, !reminderExpired(reminder),
                       model.dismissed["reminder"] != reminderKey(reminder) {
                        chip("⏰ \(truncate(reminder.text, 60)) · \(relTime(iso: reminder.dueAt))",
                             type: "reminder", contentKey: reminderKey(reminder))
                    }
                    if let weather = model.data?.weather,
                       model.dismissed["weather"] != weatherKey(weather) {
                        chip(weatherText(weather), type: "weather", contentKey: weatherKey(weather))
                    }
                    if let summary = model.data?.summary, !summary.isEmpty,
                       model.dismissed["summary"] != summary {
                        chip(truncate(summary, 90), type: "summary", contentKey: summary, wraps: true)
                    }
                }
                .frame(maxWidth: 340, alignment: .leading)
            }
        }
        .onAppear { model.start(api: client.admin) }
        .onDisappear { model.stop() }
    }

    // Clock block (Larry 2026-08-18: a display, not a label): large thin
    // tabular time, spoken-style uppercase date, the minute as a hairline.
    private var clockBlock: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(model.now, format: .dateTime.hour(.defaultDigits(amPM: .omitted)).minute())
                .font(.system(size: 30, weight: .ultraLight, design: .monospaced))
                .monospacedDigit()
                .foregroundStyle(AppTheme.text)
            Text(model.now.formatted(.dateTime.weekday(.wide).day().month(.wide)))
                .font(.system(size: 11))
                .kerning(1.0)
                .textCase(.uppercase)
                .foregroundStyle(AppTheme.textDim)
            // The minute hairline: one pixel of slow travel, stepping on
            // the 10s tick — honest steps, no animation.
            GeometryReader { geo in
                Rectangle()
                    .fill(AppTheme.accent.opacity(0.55))
                    .frame(width: geo.size.width * secondsFraction, height: 1)
            }
            .frame(width: 84, height: 1)
            .background(Color.white.opacity(0.10))
        }
        .padding(.leading, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Current time")
        .accessibilityValue(model.now.formatted(.dateTime.hour(.defaultDigits(amPM: .omitted)).minute()))
    }

    private var secondsFraction: Double {
        Double(Calendar.current.component(.second, from: model.now)) / 60.0
    }

    private func chip(_ text: String, type: String, contentKey: String, wraps: Bool = false) -> some View {
        HStack(spacing: 4) {
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(AppTheme.textDim)
                .lineLimit(wraps ? 3 : 1)
            Button {
                model.dismiss(type, contentKey: contentKey)
            } label: {
                Text("×").foregroundStyle(AppTheme.textDim)
            }
            .buttonStyle(.plain)
            .help("Dismiss")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .mortimerGlass(.chip)
    }

    private func reminderKey(_ r: AmbientReminder) -> String { "\(r.text)|\(r.dueAt)" }
    private func weatherKey(_ w: AmbientWeather) -> String { "\(w.summary)|\(w.tempF)|\(w.location)" }

    private func weatherText(_ w: AmbientWeather) -> String {
        let temp = "\(Int(w.tempF.rounded()))°"
        return w.location.isEmpty ? "\(w.summary) \(temp)" : "\(w.summary) \(temp) · \(w.location)"
    }

    /// Reminder expiry (AmbientStrip.tsx:146-152): hide once due_at +
    /// 60s grace is behind now; an unparseable due_at is NEVER treated as
    /// expired (wrong-but-visible beats silently eating a reminder).
    private func reminderExpired(_ r: AmbientReminder) -> Bool {
        guard let due = parseISO(r.dueAt) else { return false }
        return model.now > due.addingTimeInterval(AppTuning.reminderExpiryGraceSeconds)
    }

    private func truncate(_ s: String, _ max: Int) -> String {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.count > max ? String(t.prefix(max - 1)) + "…" : t
    }
}

/// timeFormat.ts relTime — "12s ago" / "5m ago" / "3h ago" / "2d ago";
/// negative deltas (a future reminder) render as "in Xm" the way the
/// web's relTime clamps to 0s… actually the web clamps to "0s ago" — a
/// due-in-the-future reminder still reads sanely there because relTime
/// is only ever handed near-past stamps; for the reminder chip a future
/// due_at is the common case, so this renders "in …" honestly rather
/// than the web's degenerate "0s ago". Deviation on the record.
func relTime(iso: String) -> String {
    guard let date = parseISO(iso) else { return "" }
    let delta = Date().timeIntervalSince(date)
    let future = delta < 0
    let s = Int(abs(delta))
    let text: String
    if s < 60 { text = "\(s)s" }
    else if s < 3600 { text = "\(s / 60)m" }
    else if s < 86400 { text = "\(s / 3600)h" }
    else { text = "\(s / 86400)d" }
    return future ? "in \(text)" : "\(text) ago"
}

func relTime(from date: Date) -> String {
    let s = max(0, Int(Date().timeIntervalSince(date)))
    if s < 60 { return "\(s)s ago" }
    if s < 3600 { return "\(s / 60)m ago" }
    if s < 86400 { return "\(s / 3600)h ago" }
    return "\(s / 86400)d ago"
}

func parseISO(_ iso: String) -> Date? {
    let withFractional = ISO8601DateFormatter()
    withFractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = withFractional.date(from: iso) { return d }
    let plain = ISO8601DateFormatter()
    return plain.date(from: iso)
}
