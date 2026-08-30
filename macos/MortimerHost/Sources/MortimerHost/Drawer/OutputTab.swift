import SwiftUI
import JarvisKit

/// The Output tab, matched to web/src/components/OutputTab.tsx (parity
/// sweep 2026-08-30): "Output" panel title + Clear; one row per result
/// (title · agent · relative time · ×); exactly ONE expanded at a time,
/// auto-expanding only a genuinely NEW newest item (D32 — never
/// re-expanding what the user collapsed); the web's exact empty copy.
struct OutputTab: View {
    @Environment(DisplayResultStore.self) private var store
    @State private var expandedId: Int?
    @State private var lastNewestId: Int?
    /// 30s heartbeat so the relative times don't freeze.
    @State private var now = Date()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text("OUTPUT")
                        .font(.system(size: 10, design: .monospaced))
                        .kerning(2.0)
                        .foregroundStyle(AppTheme.textDim)
                    Spacer()
                    if !store.results.isEmpty {
                        Button("Clear") { store.clear() }
                            .font(.system(size: 10, design: .monospaced))
                            .buttonStyle(.plain)
                            .foregroundStyle(AppTheme.textDim)
                    }
                }
                if store.results.isEmpty {
                    Text("Work products — diffs, commits, scaffolds — land here. Try \"show the repo status\".")
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textDim)
                } else {
                    ForEach(store.results) { result in
                        item(result)
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear {
            // First mount: newest starts expanded (OutputTab.tsx:23-26).
            if expandedId == nil && lastNewestId == nil {
                expandedId = store.results.first?.id
            }
            lastNewestId = store.results.first?.id
        }
        .onChange(of: store.results.first?.id) { _, newest in
            // Auto-expand only a genuinely NEW newest item (D32).
            if let newest, newest != lastNewestId {
                expandedId = newest
            }
            lastNewestId = newest
        }
        .task {
            while !Task.isCancelled {
                now = Date()
                try? await Task.sleep(nanoseconds: 30_000_000_000)
            }
        }
    }

    private func item(_ result: DisplayResult) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(result.payload.title ?? "Result")
                    .font(.system(size: 12))
                    .foregroundStyle(AppTheme.text)
                    .lineLimit(1)
                Spacer()
                if let agent = result.payload.agent, !agent.isEmpty {
                    Text(agent.uppercased())
                        .font(.system(size: 10, design: .monospaced))
                        .kerning(0.8)
                        .foregroundStyle(AppTheme.textDim)
                }
                Text(timeText(result.receivedAt))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
                Button {
                    store.remove(id: result.id)
                } label: {
                    Text("×")
                }
                .buttonStyle(.plain)
                .foregroundStyle(AppTheme.textDim)
                .help("Dismiss")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
            .onTapGesture {
                expandedId = (expandedId == result.id) ? nil : result.id
            }

            if expandedId == result.id {
                Divider().overlay(AppTheme.hairline)
                DisplayContentView(payload: result.payload)
                    .padding(8)
            }
        }
        .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(AppTheme.hairline, lineWidth: 1))
    }

    private func timeText(_ date: Date) -> String {
        _ = now   // re-render dependency for the 30s heartbeat
        return relTime(from: date)
    }
}
