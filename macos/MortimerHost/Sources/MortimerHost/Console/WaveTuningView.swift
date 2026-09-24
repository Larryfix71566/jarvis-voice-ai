import SwiftUI

/// Item 10 (2026-09-16). Four dB values decide how measured RMS becomes
/// visible travel, and the right values are a matter of perception rather
/// than of measurement -- so they are tuned here, live, against a real
/// voice, instead of being argued about. The measured starting points come
/// from P2-latency.json, 2026-09-17T00:06Z.
///
/// Deliberately a Debug window and not a preference: once a set of values
/// reads well they become the defaults in `AudioPresentationTuning` and
/// this window goes back to being a diagnostic.
struct WaveTuningView: View {
    @AppStorage(AudioPresentationTuning.inputFloorKey) private var inputFloor =
        AudioPresentationTuning.inputFloorDefault
    @AppStorage(AudioPresentationTuning.inputCeilingKey) private var inputCeiling =
        AudioPresentationTuning.inputCeilingDefault
    @AppStorage(AudioPresentationTuning.outputFloorKey) private var outputFloor =
        AudioPresentationTuning.outputFloorDefault
    @AppStorage(AudioPresentationTuning.outputCeilingKey) private var outputCeiling =
        AudioPresentationTuning.outputCeilingDefault

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Voice level windows")
                    .font(.headline)
                Text("Talk while you drag. The floor sets how much the atom responds "
                     + "between syllables; the ceiling sets where it stops growing.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            channel(
                title: "Your voice",
                tint: AudioPresentationTuning.userColor,
                measured: "median −58.4 dBFS · p95 −15.9 · peak −10.6",
                floor: $inputFloor, ceiling: $inputCeiling,
                floorRange: -80 ... -30, ceilingRange: -40 ... 0
            )

            channel(
                title: "Mortimer",
                tint: AudioPresentationTuning.assistantColor,
                measured: "median −18.6 dBFS · p95 −8.4 · peak −5.3",
                floor: $outputFloor, ceiling: $outputCeiling,
                floorRange: -60 ... -10, ceilingRange: -25 ... 0
            )

            HStack {
                Button("Reset to measured") {
                    inputFloor = AudioPresentationTuning.inputFloorDefault
                    inputCeiling = AudioPresentationTuning.inputCeilingDefault
                    outputFloor = AudioPresentationTuning.outputFloorDefault
                    outputCeiling = AudioPresentationTuning.outputCeilingDefault
                }
                Spacer()
                Text(summary)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
        .padding(20)
        .frame(minWidth: 380)
    }

    /// Copyable, so a set of values that reads well can be pasted back
    /// rather than read off four sliders by eye.
    private var summary: String {
        String(format: "in %.0f…%.0f · out %.0f…%.0f",
               inputFloor, inputCeiling, outputFloor, outputCeiling)
    }

    @ViewBuilder
    private func channel(title: String, tint: Color, measured: String,
                         floor: Binding<Double>, ceiling: Binding<Double>,
                         floorRange: ClosedRange<Double>,
                         ceilingRange: ClosedRange<Double>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 7) {
                Circle().fill(tint).frame(width: 8, height: 8)
                Text(title).font(.subheadline.weight(.medium))
            }
            Text(measured)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.tertiary)
            row("floor", value: Binding(
                get: { floor.wrappedValue },
                set: { newValue in
                    floor.wrappedValue = newValue
                    if ceiling.wrappedValue <= newValue { ceiling.wrappedValue = newValue + 1 }
                }), range: floorRange, tint: tint)
            row("ceiling", value: Binding(
                get: { ceiling.wrappedValue },
                set: { newValue in
                    ceiling.wrappedValue = newValue
                    if floor.wrappedValue >= newValue { floor.wrappedValue = newValue - 1 }
                }), range: ceilingRange, tint: tint)
        }
    }

    @ViewBuilder
    private func row(_ label: String, value: Binding<Double>,
                     range: ClosedRange<Double>, tint: Color) -> some View {
        HStack(spacing: 10) {
            Text(label)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 52, alignment: .leading)
            Slider(value: value, in: range, step: 1)
                .tint(tint)
            Text(String(format: "%.0f dB", value.wrappedValue))
                .font(.system(.caption, design: .monospaced))
                .monospacedDigit()
                .frame(width: 58, alignment: .trailing)
        }
    }
}
