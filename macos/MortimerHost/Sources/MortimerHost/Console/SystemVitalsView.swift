import SwiftUI
import JarvisKit

/// SystemVitals — bottom-right machine readout, ported from
/// web/src/components/SystemVitals.tsx (parity sweep 2026-08-30).
///
/// Deliberately NOT a live gauge cluster: no animation, no fast timer,
/// and nothing rendered at all when every metric is healthy — silent
/// when healthy, amber (--attn) when a metric crosses the SAME 85%
/// threshold the systems agent warns aloud at, and the full cluster on
/// demand (click to expand). Battery is the exception to silence
/// (BATTERY_ALWAYS): the one metric a person acts on. Data rides its own
/// 60s /api/ambient poll (`system` field); the sidecar being down is not
/// this component's story to tell — the capability chip covers that.
@MainActor
@Observable
final class VitalsModel {
    private(set) var data: AmbientSystem?
    var expanded = false
    private var pollTask: Task<Void, Never>?

    func start(api: AdminAPI) {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                let response = try? await api.ambientTyped()
                self?.data = response?.system
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.vitalsPollSeconds * 1_000_000_000))
            }
        }
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
    }
}

struct SystemVitalsView: View {
    let connected: Bool
    @EnvironmentObject private var client: JarvisClient
    @State private var model = VitalsModel()

    private static let labels: [String: String] = ["cpu": "CPU", "memory": "MEM", "disk": "DISK"]

    var body: some View {
        Group {
            if connected, let data = model.data {
                content(data)
            }
        }
        .onAppear { model.start(api: client.admin) }
        .onDisappear { model.stop() }
    }

    @ViewBuilder
    private func content(_ data: AmbientSystem) -> some View {
        let batteryLow = data.battery.map { $0 <= AppTuning.lowBatteryPercent } ?? false
        let showBattery = data.battery != nil && (AppTuning.batteryAlways || batteryLow)

        if model.expanded {
            expandedView(data, batteryLow: batteryLow)
        } else if !data.flags.isEmpty || showBattery {
            collapsedView(data, batteryLow: batteryLow, showBattery: showBattery)
        }
        // else: silent when there is nothing to say (SystemVitals.tsx:105).
    }

    private func collapsedView(_ data: AmbientSystem, batteryLow: Bool, showBattery: Bool) -> some View {
        Button {
            model.expanded = true
        } label: {
            HStack(spacing: 8) {
                ForEach(data.flags, id: \.self) { flag in
                    Text("\(Self.labels[flag] ?? flag.uppercased()) \(pct(metric(data, flag)))")
                        .foregroundStyle(AppTheme.attn)
                }
                if showBattery {
                    Text(pct(data.battery))
                        .foregroundStyle(batteryLow ? AppTheme.attn : AppTheme.textDim)
                }
            }
            .font(.system(size: 11, design: .monospaced))
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .mortimerGlass(.chip)
        }
        .buttonStyle(.plain)
        .help("System vitals")
    }

    private func expandedView(_ data: AmbientSystem, batteryLow: Bool) -> some View {
        VStack(alignment: .trailing, spacing: 7) {
            HStack {
                Spacer()
                Button {
                    model.expanded = false
                } label: {
                    Text("×").foregroundStyle(AppTheme.textDim)
                }
                .buttonStyle(.plain)
            }
            row("CPU", value: data.cpu, flagged: data.flags.contains("cpu"))
            row("MEM", value: data.memory, flagged: data.flags.contains("memory"))
            row("DISK", value: data.disk, flagged: data.flags.contains("disk"))
            if data.battery != nil {
                row("BATT", value: data.battery, flagged: batteryLow)
            }
            Text("up \(uptime(data.uptimeHours))")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(AppTheme.textDim)
                .padding(.top, 4)
                .overlay(Rectangle().fill(AppTheme.hairline).frame(height: 1), alignment: .top)
        }
        .padding(12)
        .frame(minWidth: 190)
        .mortimerGlass(.chip)
    }

    private func row(_ label: String, value: Double?, flagged: Bool) -> some View {
        HStack(spacing: 8) {
            Text(label)
                .frame(width: 34, alignment: .leading)
                .foregroundStyle(AppTheme.textDim)
            // Static bar, no transition — a bar that animates on every
            // 60s poll is the motion this component exists to avoid.
            GeometryReader { geo in
                Rectangle()
                    .fill(flagged ? AppTheme.attn : AppTheme.accent)
                    .frame(width: geo.size.width * min(1, (value ?? 0) / 100))
            }
            .frame(width: 90, height: 4)
            .background(Color.white.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 2))
            Text(pct(value))
                .frame(width: 38, alignment: .trailing)
                .foregroundStyle(flagged ? AppTheme.attn : AppTheme.text)
        }
        .font(.system(size: 11, design: .monospaced))
    }

    private func metric(_ data: AmbientSystem, _ key: String) -> Double? {
        switch key {
        case "cpu": return data.cpu
        case "memory": return data.memory
        case "disk": return data.disk
        default: return nil
        }
    }

    private func pct(_ v: Double?) -> String {
        v.map { "\(Int($0.rounded()))%" } ?? "—"
    }

    /// SystemVitals.tsx formatUptime — the largest sensible unit.
    private func uptime(_ hours: Double?) -> String {
        guard let hours else { return "—" }
        if hours < 1 { return "\(Int((hours * 60).rounded()))m" }
        if hours < 48 { return "\(Int(hours.rounded()))h" }
        return "\(Int((hours / 24).rounded()))d" }
}
