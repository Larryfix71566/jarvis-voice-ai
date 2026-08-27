// GlassPanelView.swift
// T1.1 — exactly what the spike must show, so the six screenshots (§8
// S1-S6) are comparable across arms and across runs.
//
// GlassSpike has NO dependency on JarvisKit (§5 step 11 — "no
// dependencies"), so the rollback flag here reads the SAME UserDefaults
// key JarvisFlags.glassEnabled reads (JARVIS_GLASS_ENABLED) directly,
// rather than sharing JarvisKit's JarvisFlags type. `defaults write
// <bundle-id> JARVIS_GLASS_ENABLED -bool false` (§9) therefore has the
// identical effect here as it will on the real app.

import SwiftUI

private func glassEnabledFromDefaults() -> Bool {
    UserDefaults.standard.object(forKey: "JARVIS_GLASS_ENABLED") == nil
        ? true : UserDefaults.standard.bool(forKey: "JARVIS_GLASS_ENABLED")
}

enum SpikeArm: String, CaseIterable, Identifiable {
    case arm1 = "Arm 1 — transparent window"
    case arm2 = "Arm 2 — NSVisualEffectView fallback"
    var id: String { rawValue }
}

struct GlassPanelView: View {
    let label: String

    @State private var glassEnabled = glassEnabledFromDefaults()
    @State private var arm: SpikeArm = .arm1

    var body: some View {
        VStack(spacing: 16) {
            Picker("Arm", selection: $arm) {
                ForEach(SpikeArm.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)

            Toggle("Glass enabled (JARVIS_GLASS_ENABLED)", isOn: $glassEnabled)
                .padding(.horizontal)

            if glassEnabled {
                GlassEffectContainer {
                    HStack(spacing: 24) {
                        legibilityPanel(title: "\(label) — .regular")
                            .glassEffect(.regular, in: .rect(cornerRadius: 28))
                        legibilityPanel(title: "\(label) — .clear")
                            .glassEffect(.clear, in: .rect(cornerRadius: 28))
                    }
                }
            } else {
                // The rollback look (§9): opaque windows, .regularMaterial panels.
                HStack(spacing: 24) {
                    legibilityPanel(title: "\(label) — rollback")
                        .background(.regularMaterial, in: .rect(cornerRadius: 28))
                }
            }
        }
        .padding(24)
        .background(TransparentWindowAccessor(useVisualEffectFallback: arm == .arm2))
        .navigationTitle(label)   // gives SpikeScreenPlacement's title-fallback lookup something to match
    }

    /// The legibility test block: three text sizes over the panel, the
    /// smallest matching a run-card's activity ticker (13pt) — the size
    /// most at risk against a busy desktop (§8 S3).
    private func legibilityPanel(title: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            Text("22pt — section heading").font(.system(size: 22))
            Text("15pt — body copy, run status").font(.system(size: 15))
            Text("13pt — activity ticker line").font(.system(size: 13))
        }
        .padding(24)
        .frame(width: 520, height: 360, alignment: .topLeading)
    }
}
