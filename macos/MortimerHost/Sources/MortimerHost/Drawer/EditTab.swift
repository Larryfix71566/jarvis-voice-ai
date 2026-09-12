import SwiftUI
import Observation
import JarvisKit

/// APP plan §3 P3, §5 step 7 — the Edit tab: the self-edit run lifecycle
/// (models, status/proposals, run/validate/submit/revert). The council &
/// plan-authoring panels are DEFERRED (§2) — voice still reaches them
/// via the bot. Polls every editRunPollSeconds (3 s — the one tab whose
/// cadence is real web parity, F5).
@MainActor
@Observable
final class EditViewModel {
    private(set) var api: AdminAPI
    var state: TabState<SelfEditStatus> = .loading
    var models: [SelfEditModel] = []
    var selectedModel = ""
    var goal = ""
    var actionError: String?
    var actionBusy = false
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI) { self.api = api }

    func updateAPI(_ api: AdminAPI) {
        stopPolling()
        self.api = api
        stopped = false
    }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            await self?.loadModels()
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.editRunPollSeconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func loadModels() async {
        guard let response = try? await api.selfeditModelsTyped(), response.ok else { return }
        guard !Task.isCancelled else { return }
        models = response.models
        if selectedModel.isEmpty {
            selectedModel = response.models.first(where: \.isDefault)?.name
                ?? response.models.first?.name ?? ""
        }
    }

    func refresh() async {
        do {
            let status = try await api.selfeditStatusTyped()
            guard !Task.isCancelled else { return }
            // Two shapes (P3): busy → error != nil; idle real status with
            // nothing active → empty; else loaded.
            if let error = status.error {
                state = .error(error)
            } else if status.active != true && (status.proposals?.isEmpty ?? true) {
                state = .empty
            } else {
                state = .loaded(status)
            }
        } catch {
            guard !Task.isCancelled else { return }
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }
        }
    }

    private func act(_ label: String, _ operation: @escaping () async throws -> JSONValue) {
        Task {
            actionBusy = true
            actionError = nil
            defer { actionBusy = false }
            do {
                let result = try await operation()
                if result["ok"]?.boolValue == false {
                    actionError = result["error"]?.stringValue ?? "\(label) failed"
                }
                await refresh()
            } catch {
                actionError = TabStateMapper.fromError(error).state
            }
        }
    }

    func run() {
        let goalText = goal
        let profile = selectedModel.isEmpty ? nil : selectedModel
        act("run") { [api] in
            try await api.selfeditRun(goal: goalText, profile: profile, plan: nil, stagingId: nil)
        }
    }
    func validate() { act("validate") { [api] in try await api.selfeditValidate() } }
    func submit() { act("submit") { [api] in try await api.selfeditSubmit() } }
    func revert() { act("revert") { [api] in try await api.selfeditRevert() } }
}

struct EditTab: View {
    @Bindable var model: EditViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                controls

                switch model.state {
                case .loading:
                    ProgressView("Edit").frame(maxWidth: .infinity)
                case .empty:
                    Text("No self-edit session. Say \"start a self-edit\" or pick a model and a goal.")
                        .foregroundStyle(AppTheme.textDim)
                case .error(let message):
                    Text(message).foregroundStyle(AppTheme.red)
                case .loaded(let status):
                    statusView(status)
                }

                if let actionError = model.actionError {
                    Text(actionError).foregroundStyle(AppTheme.red).font(.callout)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .preserveDrawerScroll("edit")
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !model.models.isEmpty {
                Picker("Model", selection: $model.selectedModel) {
                    ForEach(model.models, id: \.name) { m in
                        Text("\(m.label)\(m.keyPresent ? "" : " (no key)")").tag(m.name)
                    }
                }
                .pickerStyle(.menu)
            }
            TextField("Goal", text: $model.goal)
                .textFieldStyle(.roundedBorder)
            HStack {
                Button("Run") { model.run() }
                    .disabled(model.goal.isEmpty || model.actionBusy)
                Button("Validate") { model.validate() }.disabled(model.actionBusy)
                Button("Submit") { model.submit() }.disabled(model.actionBusy)
                Button("Revert") { model.revert() }.disabled(model.actionBusy)
                if model.actionBusy { ProgressView().controlSize(.small) }
            }
        }
    }

    @ViewBuilder
    private func statusView(_ status: SelfEditStatus) -> some View {
        HStack(spacing: 10) {
            if status.active == true {
                Label("active", systemImage: "gearshape.2").foregroundStyle(AppTheme.accent)
            }
            if let branch = status.branch {
                Text(branch).font(.system(.caption, design: .monospaced)).foregroundStyle(AppTheme.textDim)
            }
            if let validated = status.validatedOk {
                Text(validated ? "validated ✓" : "validation failed")
                    .foregroundStyle(validated ? AppTheme.green : AppTheme.red)
                    .font(.caption)
            }
        }

        if let goal = status.goal, !goal.isEmpty {
            Text(goal).font(.callout).foregroundStyle(AppTheme.textDim)
        }

        if let proposals = status.proposals, !proposals.isEmpty {
            ForEach(Array(proposals.enumerated()), id: \.offset) { _, proposal in
                DisclosureGroup {
                    Text(proposal.diff)
                        .font(.system(.caption2, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(proposal.path).font(.system(.caption, design: .monospaced))
                        if !proposal.rationale.isEmpty {
                            Text(proposal.rationale).font(.caption2).foregroundStyle(AppTheme.textDim)
                        }
                    }
                }
                .padding(8)
                .mortimerGlass(.card)
            }
        }
    }
}
