import MortimerPhoneCore
import SwiftUI

private enum PreviewSection: String, CaseIterable, Identifiable {
    case preview = "Preview"
    case about = "About"
    var id: String { rawValue }
}

struct PhonePreviewRootView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var model: PhoneAppPreviewModel
    @State private var displayedState: PhoneAppPreviewState = .disconnected
    @State private var selection: PreviewSection? = .preview
    @State private var demoTask: Task<Void, Never>?

    init(model: PhoneAppPreviewModel) {
        _model = State(initialValue: model)
    }

    var body: some View {
        NavigationSplitView {
            List(PreviewSection.allCases, selection: $selection) { section in
                Text(section.rawValue).tag(section as PreviewSection?)
            }
            .navigationTitle("Mortimer Preview")
            .accessibilityIdentifier("preview.sidebar")
        } detail: {
            NavigationStack {
                Group {
                    switch selection ?? .preview {
                    case .preview: previewContent
                    case .about: aboutContent
                    }
                }
                .navigationTitle(selection?.rawValue ?? PreviewSection.preview.rawValue)
                .navigationBarTitleDisplayMode(.inline)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            disconnectedBanner
        }
        .task {
            for await nextState in model.states() {
                displayedState = nextState
            }
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase != .active else { return }
            demoTask?.cancel()
            demoTask = nil
            model.applicationDidLoseForeground()
            displayedState = .disconnected
        }
        .onDisappear {
            demoTask?.cancel()
            model.cancelDemo()
        }
    }

    private var previewContent: some View {
        VStack(alignment: .leading, spacing: 20) {
            stateDescription
                .font(.title3)
                .accessibilityIdentifier("preview.state")

            Button(action: startDemo) {
                Label("Run synthetic status preview", systemImage: "play.fill")
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier("preview.run")
            .disabled(demoTask != nil)

            Button(action: startResults) {
                Label("Show synthetic results", systemImage: "doc.text.magnifyingglass")
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("preview.results")
            .disabled(demoTask != nil)

            if case .syntheticResults(let items, _, _) = displayedState {
                if items.isEmpty {
                    Text("No synthetic results.").accessibilityIdentifier("preview.results.empty")
                }
                ForEach(items, id: \.resultID) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.title).font(.headline)
                        Text(item.body).font(.body)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("preview.result.\(item.resultID)")
                }
                Button("Check for synthetic updates", action: resumeResults)
                    .accessibilityIdentifier("preview.results.resume")
                    .disabled(demoTask != nil)
            }

            if case .syntheticCardResults(let items, let view, let ready, let notice) = displayedState {
                if let notice { Text(notice).accessibilityIdentifier("preview.cards.notice") }
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        cardSection("Open cards", open: true, items: items, view: view, ready: ready)
                        cardSection("Closed cards", open: false, items: items, view: view, ready: ready)
                    }
                }
                Button("Refresh result controls", action: startResults)
                    .accessibilityIdentifier("preview.cards.refresh").disabled(demoTask != nil)
            }
            if demoTask != nil {
                Button(role: .cancel, action: cancelDemo) {
                    Label("Cancel preview", systemImage: "xmark")
                }
                .accessibilityIdentifier("preview.cancel")
            }

            Spacer(minLength: 0)
        }
        .padding(24)
        .frame(maxWidth: 720, alignment: .leading)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private var disconnectedBanner: some View {
        Label(PhoneAppPreviewModel.disconnectedNotice, systemImage: "iphone.slash")
            .font(.callout.weight(.semibold))
            .foregroundStyle(.orange)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.thinMaterial)
            .accessibilityIdentifier("preview.disconnected-notice")
    }

    @ViewBuilder
    private var stateDescription: some View {
        switch displayedState {
        case .disconnected:
            Text("No synthetic check is running.")
        case .demoInProgress:
            ProgressView("Running an in-process synthetic check…")
        case .syntheticResult(let readiness):
            Label("Synthetic readiness: \(readiness)", systemImage: "checkmark.circle")
                .foregroundStyle(.green)
        case .syntheticResults(let items, _, _):
            Label("\(items.count) synthetic result(s)", systemImage: "doc.text")
                .foregroundStyle(.green)
        case .syntheticCardResults(let items, _, let ready, _):
            Label("\(items.count) synthetic result(s) — \(ready ? "controls ready" : "controls disabled")", systemImage: "doc.text")
        case .syntheticError(let message):
            Label(message, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.orange)
        }
    }

    private var aboutContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Preview only")
                .font(.title2.weight(.semibold))
            Text("This unsigned scaffold uses a deterministic in-process fixture. It does not authenticate, contact a service, access audio, or represent Mortimer readiness.")
            Text("Any displayed readiness is synthetic and does not describe Mortimer.")
        }
        .padding(24)
        .frame(maxWidth: 720, alignment: .leading)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder private func cardSection(_ title: String, open: Bool, items: [PhoneRemoteResultItem], view: PhoneResultCardView?, ready: Bool) -> some View {
        Text(title).font(.headline)
        ForEach(items.filter { item in (view?.cards.first(where: { $0.resultID == item.resultID })?.open ?? true) == open }, id: \.resultID) { item in
            let card = view?.cards.first(where: { $0.resultID == item.resultID })
            VStack(alignment: .leading, spacing: 6) {
                Text(item.title).font(.headline)
                Text(item.body)
                if view?.selectedResultID == item.resultID { Text("Selected on phone") }
                if card?.pinned == true { Text("Pinned on phone") }
                HStack {
                    if open {
                        cardButton("Select", action: .select, item: item, view: view, ready: ready)
                        cardButton(card?.pinned == true ? "Unpin" : "Pin", action: card?.pinned == true ? .unpin : .pin, item: item, view: view, ready: ready)
                        cardButton("Close on phone", action: .close, item: item, view: view, ready: ready)
                    } else {
                        cardButton("Reopen on phone", action: .reopen, item: item, view: view, ready: ready)
                    }
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("preview.result.\(item.resultID)")
        }
    }

    private func cardButton(_ label: String, action: PhoneResultCardAction, item: PhoneRemoteResultItem, view: PhoneResultCardView?, ready: Bool) -> some View {
        Button(label) {
            guard demoTask == nil else { return }
            demoTask = Task { await model.performCardAction(action, resultID: item.resultID); demoTask = nil }
        }
        .disabled(!ready || demoTask != nil || view?.allowedOperations.contains(action) != true)
        .accessibilityLabel("\(label): \(item.title)")
        .accessibilityIdentifier("preview.card.\(action.rawValue).\(item.resultID)")
    }

    private func startDemo() {
        guard demoTask == nil else { return }
        demoTask = Task {
            await model.runSyntheticDemo()
            demoTask = nil
        }
    }

    private func cancelDemo() {
        model.cancelDemo()
        demoTask?.cancel()
    }

    private func startResults() {
        guard demoTask == nil else { return }
        demoTask = Task {
            await model.refreshSyntheticCards()
            demoTask = nil
        }
    }

    private func resumeResults() {
        guard demoTask == nil else { return }
        demoTask = Task {
            await model.resumeSyntheticResults()
            demoTask = nil
        }
    }
}
