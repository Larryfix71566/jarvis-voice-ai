import SwiftUI
import Observation
import JarvisKit

/// APP plan §3 P2/P6/P7, §5 step 6 — the Repo tab. Poll gitStatusTyped
/// every repoPollSeconds (15 s — F5, NOT the Edit tab's 3 s); commits
/// and pushes are draft→confirm TWO-step user actions (C4), the pending
/// actionId held here across tab switches.
@MainActor
@Observable
final class RepoViewModel {
    private(set) var api: AdminAPI
    var state: TabState<GitStatus> = .loading
    var architectureState: TabState<ArchitectureReference> = .loading
    var modelRoutesState: TabState<JSONValue> = .loading
    var selectedModelWorkload = "developer"
    var selectedModelProfile = "claude-opus"
    var selectedModelRoute = "direct_api"
    var selectedModelPrivacy = "approved_external"
    var modelRouteDraftID: String?
    var modelRouteNote: String?
    var commitMessage = ""
    var pendingCommit: GitDraft?
    var pendingPush: GitDraft?
    var actionError: String?
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI) { self.api = api }

    func updateAPI(_ api: AdminAPI) {
        stopPolling()
        self.api = api
        stopped = false
        architectureState = .loading
        modelRoutesState = .loading
        modelRouteDraftID = nil
    }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.repoPollSeconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    /// GitPanel.tsx `note` — "Committed." / "Pushed." / an error string.
    var note: String?

    func refresh() async {
        do {
            let status = try await api.gitStatusTyped()
            guard !Task.isCancelled else { return }
            // git_status() is returned VERBATIM (no ok wrapper, P2). A
            // clean tree still renders the full panel (branch line +
            // disabled input + Push), exactly the web's GitPanel — never
            // an empty state that hides the controls (parity sweep).
            state = .loaded(status)
        } catch {
            guard !Task.isCancelled else { return }
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }   // N13: no retry on 401
        }
        // Keep this read-only reference independent of Git status rendering;
        // the user can still inspect the contract when a Git action is
        // temporarily unavailable.
        if case .loading = architectureState {
            await refreshArchitecture()
        }
        if case .loading = modelRoutesState {
            await refreshModelRoutes()
        }
    }

    /// Read the checked-in architecture contract for the user-facing Repo
    /// sidecar. It is intentionally independent of Git status failures: a
    /// stale Git endpoint must not hide the reference, and a missing document
    /// must not make repository actions look unavailable.
    func refreshArchitecture() async {
        do {
            let reference = try await api.architectureReference()
            guard !Task.isCancelled else { return }
            if reference.ok && !reference.content.isEmpty {
                architectureState = .loaded(reference)
            } else {
                architectureState = .error(reference.error ?? "Architecture reference unavailable")
            }
        } catch {
            guard !Task.isCancelled else { return }
            architectureState = .error(TabStateMapper.fromError(error).state)
        }
    }

    func refreshModelRoutes() async {
        do {
            let routes = try await api.modelRoutes()
            guard !Task.isCancelled else { return }
            modelRoutesState = .loaded(routes)
            applyModelWorkloadDefaults()
        } catch {
            guard !Task.isCancelled else { return }
            modelRoutesState = .error(TabStateMapper.fromError(error).state)
        }
    }

    func applyModelWorkloadDefaults() {
        guard case .loaded(let routes) = modelRoutesState,
              let workload = routes["workloads"]?[selectedModelWorkload] else { return }
        if let profile = workload["profile"]?.stringValue { selectedModelProfile = profile }
        if let route = workload["route"]?.stringValue { selectedModelRoute = route }
        if let privacy = workload["privacy"]?.stringValue { selectedModelPrivacy = privacy }
    }

    func stageModelRoute() async {
        modelRouteNote = nil
        do {
            let result = try await api.stageModelRoute(.init(
                workload: selectedModelWorkload,
                profile: selectedModelProfile,
                route: selectedModelRoute,
                privacy: selectedModelPrivacy
            ))
            if result["ok"]?.boolValue == true {
                modelRouteDraftID = result["draft_id"]?.stringValue
                modelRouteNote = "Draft ready — confirm to save."
            } else {
                modelRouteNote = result["error"]?.stringValue ?? "Route draft was rejected."
            }
        } catch { modelRouteNote = TabStateMapper.fromError(error).state }
    }

    func confirmModelRoute() async {
        guard let draftID = modelRouteDraftID else { return }
        do {
            let result = try await api.confirmModelRoute(draftId: draftID)
            if result["ok"]?.boolValue == true {
                modelRouteNote = "Model route saved."
                modelRouteDraftID = nil
                await refreshModelRoutes()
            } else {
                modelRouteNote = result["error"]?.stringValue ?? "Route confirmation failed."
            }
        } catch { modelRouteNote = TabStateMapper.fromError(error).state }
    }

    var modelRouteWorkloads: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let object = value["workloads"]?.objectValue else { return [] }
        return object.keys.sorted()
    }

    var modelRouteProfiles: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let profiles = value["profiles"]?.arrayValue else { return [] }
        return profiles.compactMap { $0["name"]?.stringValue }.sorted()
    }

    var modelRouteNames: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let routes = value["routes"]?.objectValue else { return [] }
        return routes.keys.sorted()
    }

    var selectedModelRouteSummary: String? {
        guard case .loaded(let value) = modelRoutesState,
              let route = value["routes"]?[selectedModelRoute]?.objectValue else { return nil }
        let capabilities = route["capabilities"]?.arrayValue?.compactMap { $0.stringValue }
            .joined(separator: ", ")
        let privacy = route["privacy"]?.stringValue
        let billing = route["billing"]?.stringValue
        let parts = [
            capabilities.map { "capabilities: \($0)" },
            privacy.map { "privacy: \($0)" },
            billing.map { "billing: \($0)" },
        ].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    func prepareCommit() async {
        note = nil
        actionError = nil
        do { pendingCommit = try await api.prepareCommit(message: commitMessage) }
        catch { actionError = TabStateMapper.fromError(error).state }
    }

    func confirmCommit() async {
        guard let actionId = pendingCommit?.actionId else { return }
        actionError = nil
        do {
            let result = try await api.commit(actionId: actionId)
            note = result.ok ? "Committed." : (result.error ?? "commit failed")
            pendingCommit = nil
            commitMessage = ""
            await refresh()
        } catch { actionError = TabStateMapper.fromError(error).state }
    }

    func preparePush() async {
        note = nil
        actionError = nil
        do { pendingPush = try await api.preparePush() }
        catch { actionError = TabStateMapper.fromError(error).state }
    }

    func confirmPush() async {
        guard let actionId = pendingPush?.actionId else { return }
        actionError = nil
        do {
            let result = try await api.push(actionId: actionId)
            note = result.ok ? "Pushed." : (result.error ?? "push failed")
            pendingPush = nil
            await refresh()
        } catch { actionError = TabStateMapper.fromError(error).state }
    }
}

struct RepoTab: View {
    @Bindable var model: RepoViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("REPOSITORY")
                    .font(.system(size: 10, design: .monospaced))
                    .kerning(2.0)
                    .foregroundStyle(AppTheme.textDim)
                switch model.state {
                case .loading:
                    Text("loading…").foregroundStyle(AppTheme.textDim).font(.caption)
                case .empty:
                    // Unreachable now (refresh always loads), kept for the
                    // TabState exhaustiveness.
                    EmptyView()
                case .error:
                    // GitPanel.tsx:80-87 — the sidecar being down is one
                    // quiet line, never a red banner.
                    Text("ADMIN SIDECAR OFFLINE")
                        .font(.system(size: 10, design: .monospaced))
                        .kerning(1.4)
                        .foregroundStyle(AppTheme.textDim)
                case .loaded(let status):
                    statusView(status)
                }
                if let actionError = model.actionError {
                    Text(actionError).foregroundStyle(AppTheme.red).font(.caption)
                }
                if let note = model.note {
                    Text(note)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(AppTheme.textDim)
                }
                ModelRouteControls(model: model)
                ArchitectureReferenceView(state: model.architectureState,
                                          refresh: { Task { await model.refreshArchitecture() } })
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .preserveDrawerScroll("repo")
    }

    // GitPanel.tsx:92-158, matched: ⎇ branch · clean/"N changed" ·
    // ↑ahead ↓behind; "commit message" input (disabled when clean) +
    // Draft; draft summary + Confirm commit / Discard; Push (disabled
    // when ahead == 0) + its own draft→confirm.
    @ViewBuilder
    private func statusView(_ status: GitStatus) -> some View {
        HStack(spacing: 12) {
            Text("⎇ \(status.branch)")
                .foregroundStyle(AppTheme.accent)
            Text(status.clean ? "clean" : "\(status.changedFiles.count) changed")
                .foregroundStyle(status.clean ? AppTheme.green : AppTheme.amber)
            if status.ahead > 0 { Text("↑\(status.ahead)").foregroundStyle(AppTheme.textDim) }
            if status.behind > 0 { Text("↓\(status.behind)").foregroundStyle(AppTheme.red) }
        }
        .font(.system(size: 11, design: .monospaced))

        if !status.changedFiles.isEmpty {
            VStack(alignment: .leading, spacing: 3) {
                ForEach(status.changedFiles, id: \.self) { file in
                    Text(file).font(.system(.caption, design: .monospaced))
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .mortimerGlass(.card)
        }

        // Draft → confirm commit (C4: two explicit user actions).
        if let draft = model.pendingCommit, draft.ok {
            draftBox(draft, confirmLabel: "Confirm commit",
                     confirm: { Task { await model.confirmCommit() } },
                     discard: { model.pendingCommit = nil })
        } else {
            HStack(spacing: 8) {
                TextField("commit message", text: $model.commitMessage)
                    .textFieldStyle(.roundedBorder)
                    .disabled(status.clean)
                Button("Draft") { Task { await model.prepareCommit() } }
                    .disabled(status.clean ||
                              model.commitMessage.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        if let draft = model.pendingCommit, !draft.ok, let error = draft.error {
            Text(error).font(.system(size: 10, design: .monospaced)).foregroundStyle(AppTheme.textDim)
        }

        if let draft = model.pendingPush, draft.ok {
            draftBox(draft, confirmLabel: "Confirm push",
                     confirm: { Task { await model.confirmPush() } },
                     discard: { model.pendingPush = nil })
        } else {
            Button("Push") { Task { await model.preparePush() } }
                .disabled(status.ahead == 0)
        }
        if let draft = model.pendingPush, !draft.ok, let error = draft.error {
            Text(error).font(.system(size: 10, design: .monospaced)).foregroundStyle(AppTheme.textDim)
        }
    }

    /// .git-draft — accent-bordered box: summary + Confirm/Discard.
    private func draftBox(_ draft: GitDraft, confirmLabel: String,
                          confirm: @escaping () -> Void, discard: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let summary = draft.summary {
                Text(summary).font(.system(size: 12))
            }
            HStack {
                Button(confirmLabel, action: confirm)
                    .tint(AppTheme.accent)
                Button("Discard", action: discard)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(AppTheme.accentFaint, in: RoundedRectangle(cornerRadius: 2))
        .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(AppTheme.accentDim, lineWidth: 1))
    }
}

private struct ModelRouteControls: View {
    @Bindable var model: RepoViewModel

    var body: some View {
        DisclosureGroup {
            switch model.modelRoutesState {
            case .loading:
                ProgressView("Loading model routes…").controlSize(.small)
            case .empty:
                Text("Model route catalog unavailable").foregroundStyle(AppTheme.textDim)
            case .error(let message):
                HStack(spacing: 8) {
                    Text(message).foregroundStyle(AppTheme.red)
                    Button("Retry") { Task { await model.refreshModelRoutes() } }
                        .buttonStyle(.borderless)
                }
            case .loaded:
                VStack(alignment: .leading, spacing: 8) {
                    Picker("Workload", selection: $model.selectedModelWorkload) {
                        ForEach(model.modelRouteWorkloads, id: \.self) { Text($0).tag($0) }
                    }
                    .onChange(of: model.selectedModelWorkload) { _, _ in
                        model.applyModelWorkloadDefaults()
                    }
                    Picker("Profile", selection: $model.selectedModelProfile) {
                        ForEach(model.modelRouteProfiles, id: \.self) { Text($0).tag($0) }
                    }
                    Picker("Access", selection: $model.selectedModelRoute) {
                        ForEach(model.modelRouteNames, id: \.self) { Text($0).tag($0) }
                    }
                    if let summary = model.selectedModelRouteSummary {
                        Text(summary)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(AppTheme.textDim)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Picker("Privacy", selection: $model.selectedModelPrivacy) {
                        Text("approved external").tag("approved_external")
                        Text("confidential").tag("confidential")
                        Text("local only").tag("local_only")
                    }
                    HStack {
                        Button("Draft route") { Task { await model.stageModelRoute() } }
                            .tint(AppTheme.accent)
                        if model.modelRouteDraftID != nil {
                            Button("Confirm route") { Task { await model.confirmModelRoute() } }
                                .tint(AppTheme.green)
                            Button("Discard") {
                                model.modelRouteDraftID = nil
                                model.modelRouteNote = nil
                            }
                        }
                        Button("Refresh") { Task { await model.refreshModelRoutes() } }
                            .buttonStyle(.borderless)
                    }
                    if let note = model.modelRouteNote {
                        Text(note)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(note.contains("failed") || note.contains("rejected") ? AppTheme.red : AppTheme.textDim)
                    }
                    Text("Changes are staged and require explicit confirmation. Unavailable routes fail closed.")
                        .font(.system(size: 10))
                        .foregroundStyle(AppTheme.textDim)
                }
            }
        } label: {
            Label("MODEL ACCESS", systemImage: "arrow.triangle.branch")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.2)
                .foregroundStyle(AppTheme.accent)
        }
    }
}

/// The architecture document remains in the repository as the sole source of
/// truth, but is also directly inspectable from Mortimer. This keeps model and
/// user views aligned: the displayed digest identifies the exact text shown.
private struct ArchitectureReferenceView: View {
    let state: TabState<ArchitectureReference>
    let refresh: () -> Void
    @State private var expanded = true

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            switch state {
            case .loading:
                ProgressView("Loading architecture reference…")
                    .controlSize(.small)
            case .empty:
                Text("Architecture reference unavailable")
                    .foregroundStyle(AppTheme.textDim)
            case .error(let message):
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(message).foregroundStyle(AppTheme.red)
                    Button("Retry", action: refresh)
                        .buttonStyle(.borderless)
                }
            case .loaded(let reference):
                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(reference.path)
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(AppTheme.textDim)
                        Spacer()
                        if reference.truncated {
                            Text("TRUNCATED")
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(AppTheme.amber)
                        }
                        Button("Refresh", action: refresh)
                            .buttonStyle(.borderless)
                    }
                    if let sha256 = reference.sha256 {
                        Text("sha256 \(sha256)")
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundStyle(AppTheme.textDim)
                            .textSelection(.enabled)
                    }
                    Text(reference.content)
                        .font(.system(.caption, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .lineSpacing(2)
                }
            }
        } label: {
            Label("ARCHITECTURE REFERENCE", systemImage: "building.columns")
                .font(.system(size: 10, design: .monospaced))
                .kerning(1.2)
                .foregroundStyle(AppTheme.accent)
        }
        .accessibilityLabel("Architecture reference")
        .padding(10)
        .mortimerGlass(.card)
    }
}
