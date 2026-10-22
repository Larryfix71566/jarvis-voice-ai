import SwiftUI
import Observation
import JarvisKit

/// Model-route and evidence AdminAPI requests, injectable only for deterministic
/// delayed-response tests. Production retains the sidecar's single owner.
@MainActor
struct ModelRouteRequests {
    var load: () async throws -> JSONValue
    var stage: (ModelRoutePreferenceStage) async throws -> JSONValue
    var confirm: (String) async throws -> JSONValue
    var refreshBrief: () async throws -> JSONValue

    init(api: AdminAPI) {
        load = { try await api.modelRoutes() }
        stage = { try await api.stageModelRoute($0) }
        confirm = { try await api.confirmModelRoute(draftId: $0) }
        refreshBrief = { try await api.refreshHarnessModelEvidence() }
    }

    init(load: @escaping () async throws -> JSONValue,
         stage: @escaping (ModelRoutePreferenceStage) async throws -> JSONValue,
         confirm: @escaping (String) async throws -> JSONValue,
         refreshBrief: @escaping () async throws -> JSONValue = { .object(["ok": .bool(false)]) }) {
        self.load = load
        self.stage = stage
        self.confirm = confirm
        self.refreshBrief = refreshBrief
    }
}

private struct ModelRouteChoice: Equatable {
    let workload: String
    let profile: String
    let route: String
    let privacy: String
}

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
    var selectedModelWorkload = "developer" {
        didSet {
            guard oldValue != selectedModelWorkload else { return }
            modelRouteSelectionChanged()
            applyModelWorkloadDefaults()
        }
    }
    var selectedModelProfile = "claude-opus" {
        didSet { if oldValue != selectedModelProfile { modelRouteSelectionChanged() } }
    }
    var selectedModelRoute = "direct_api" {
        didSet { if oldValue != selectedModelRoute { modelRouteSelectionChanged() } }
    }
    var selectedModelPrivacy = "approved_external" {
        didSet { if oldValue != selectedModelPrivacy { modelRouteSelectionChanged() } }
    }
    private(set) var modelRouteDraftID: String?
    private(set) var modelRouteProposal: JSONValue?
    var modelRouteNote: String?
    private(set) var harnessBriefRefreshing = false
    private(set) var modelRouteStaging = false
    private(set) var modelRouteConfirming = false
    private var modelRouteRequests: ModelRouteRequests
    private var modelRouteDraftChoice: ModelRouteChoice?
    private var modelRouteSelectionRevision = 0
    private var modelRouteServiceRevision = 0
    private var modelRouteLoadRevision = 0
    var commitMessage = ""
    var pendingCommit: GitDraft?
    var pendingPush: GitDraft?
    var actionError: String?
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI, modelRouteRequests: ModelRouteRequests? = nil) {
        self.api = api
        self.modelRouteRequests = modelRouteRequests ?? ModelRouteRequests(api: api)
    }

    func updateAPI(_ api: AdminAPI) {
        stopPolling()
        self.api = api
        stopped = false
        architectureState = .loading
        modelRoutesState = .loading
        modelRouteServiceRevision += 1
        modelRouteLoadRevision += 1
        modelRouteRequests = ModelRouteRequests(api: api)
        modelRouteStaging = false
        modelRouteConfirming = false
        harnessBriefRefreshing = false
        discardModelRouteDraft()
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
        modelRouteLoadRevision += 1
        let loadRevision = modelRouteLoadRevision
        let selectionRevision = modelRouteSelectionRevision
        do {
            let routes = try await modelRouteRequests.load()
            guard !Task.isCancelled, loadRevision == modelRouteLoadRevision else { return }
            guard routes["ok"]?.boolValue == true else {
                modelRoutesState = .error(routes["error"]?.stringValue ?? "Model route catalog unavailable")
                discardModelRouteDraft()
                return
            }
            modelRoutesState = .loaded(routes)
            // A refresh must not replace an edit made while the request ran.
            if selectionRevision == modelRouteSelectionRevision { applyModelWorkloadDefaults() }
        } catch {
            guard !Task.isCancelled, loadRevision == modelRouteLoadRevision else { return }
            modelRoutesState = .error(TabStateMapper.fromError(error).state)
            discardModelRouteDraft()
        }
    }

    func applyModelWorkloadDefaults() {
        guard case .loaded(let routes) = modelRoutesState,
              let workload = routes["workloads"]?[selectedModelWorkload] else { return }
        let saved = routes["preferences"]?.arrayValue?.first {
            $0["workload"]?.stringValue == selectedModelWorkload
        }
        if let profile = (saved?["profile"] ?? workload["profile"])?.stringValue { selectedModelProfile = profile }
        if let route = (saved?["route"] ?? workload["route"])?.stringValue { selectedModelRoute = route }
        if let privacy = (saved?["privacy"] ?? workload["privacy"])?.stringValue { selectedModelPrivacy = privacy }
    }

    private var modelRouteChoice: ModelRouteChoice {
        ModelRouteChoice(workload: selectedModelWorkload, profile: selectedModelProfile,
                         route: selectedModelRoute, privacy: selectedModelPrivacy)
    }

    private func modelRouteSelectionChanged() {
        discardModelRouteDraft()
    }

    func discardModelRouteDraft() {
        modelRouteSelectionRevision += 1
        modelRouteDraftID = nil
        modelRouteProposal = nil
        modelRouteDraftChoice = nil
        modelRouteNote = nil
    }

    func stageModelRoute() async {
        guard selectedModelWorkload != "voice_supervisor" else {
            discardModelRouteDraft()
            modelRouteNote = "Harness switching is unavailable until all configuration writers and runtime share exact approval."
            return
        }
        guard !modelRouteStaging, !modelRouteConfirming else { return }
        discardModelRouteDraft()
        let choice = modelRouteChoice
        let selectionRevision = modelRouteSelectionRevision
        let serviceRevision = modelRouteServiceRevision
        modelRouteStaging = true
        defer { if serviceRevision == modelRouteServiceRevision { modelRouteStaging = false } }
        do {
            let result = try await modelRouteRequests.stage(.init(
                workload: choice.workload, profile: choice.profile,
                route: choice.route, privacy: choice.privacy
            ))
            guard !Task.isCancelled, serviceRevision == modelRouteServiceRevision,
                  selectionRevision == modelRouteSelectionRevision,
                  choice == modelRouteChoice else { return }
            if result["ok"]?.boolValue == true,
               let draftID = result["draft_id"]?.stringValue, !draftID.isEmpty,
               let digest = result["proposal_digest"]?.stringValue, digest.count == 64,
               draftID.hasSuffix(":" + digest),
               let proposal = result["proposal"],
               proposal["workload"]?.stringValue == choice.workload,
               proposal["candidate"]?["profile"]?.stringValue == choice.profile,
               proposal["candidate"]?["route"]?.stringValue == choice.route,
               proposal["candidate"]?["privacy"]?.stringValue == choice.privacy,
               let current = proposal["current"],
               (!(current["model"]?.stringValue ?? "").isEmpty ||
                (current["model"] == .null && current["resolution_state"]?.stringValue == "unresolved")),
               let candidateModel = proposal["candidate"]?["model"]?.stringValue, !candidateModel.isEmpty {
                modelRouteDraftID = draftID
                modelRouteDraftChoice = choice
                modelRouteProposal = proposal
                modelRouteNote = "Exact proposal ready — review before confirming."
            } else {
                modelRouteNote = result["error"]?.stringValue ?? "Route draft was rejected: exact model preview is required."
            }
        } catch {
            guard serviceRevision == modelRouteServiceRevision,
                  selectionRevision == modelRouteSelectionRevision else { return }
            modelRouteNote = TabStateMapper.fromError(error).state
        }
    }

    func confirmModelRoute() async {
        guard !modelRouteStaging, !modelRouteConfirming,
              let draftID = modelRouteDraftID, modelRouteProposal != nil, modelRouteDraftChoice == modelRouteChoice else { return }
        let serviceRevision = modelRouteServiceRevision
        let choice = modelRouteChoice
        modelRouteConfirming = true
        defer { if serviceRevision == modelRouteServiceRevision { modelRouteConfirming = false } }
        do {
            let result = try await modelRouteRequests.confirm(draftID)
            guard !Task.isCancelled, serviceRevision == modelRouteServiceRevision else { return }
            if result["ok"]?.boolValue == true,
               result["state"]?.stringValue == "saved",
               result["configured_model"]?.stringValue == modelRouteProposal?["candidate"]?["model"]?.stringValue {
                discardModelRouteDraft()
                // Do not replace a different selection made programmatically
                // during confirmation; the UI disables editing until settled.
                if choice == modelRouteChoice {
                    await refreshModelRoutes()
                    modelRouteNote = "Model route saved; active runtime adoption is unverified."
                }
            } else {
                guard choice == modelRouteChoice else { return }
                modelRouteNote = result["error"]?.stringValue ?? "Route confirmation failed or saved readback is unavailable; refresh before retrying."
            }
        } catch {
            guard serviceRevision == modelRouteServiceRevision, choice == modelRouteChoice else { return }
            modelRouteNote = TabStateMapper.fromError(error).state
        }
    }

    var modelRouteProposalSummary: String? {
        guard let proposal = modelRouteProposal,
              let current = proposal["current"], let candidate = proposal["candidate"] else { return nil }
        func value(_ item: JSONValue, _ key: String) -> String { item[key]?.stringValue ?? "unknown" }
        let currentModel = current["resolution_state"]?.stringValue == "unresolved"
            ? "unresolved (configured profile or route unavailable)" : value(current, "model")
        return "Configured selection: \(currentModel) via \(value(current, "route"))\n"
            + "Proposed selection: \(value(candidate, "model")) via \(value(candidate, "route"))\n"
            + "Privacy: \(value(current, "privacy")) → \(value(candidate, "privacy"))\n"
            + "Eligibility and active runtime: unverified. Quality, latency and quota: unmeasured.\n"
            + "Confirmation saves this selection snapshot. Future registry edits can change resolution; active runtime is unverified."
    }

    var harnessBriefSummary: String {
        guard case .loaded(let routes) = modelRoutesState,
              let report = routes["harness_brief"]?["report"] else {
            return "Harness model brief unavailable. No model availability or improvement is inferred."
        }
        let summary = report["summary"]?.stringValue ?? "No recommendation available."
        let date = report["evidence_generated_at"]?.stringValue ?? report["generated_at"]?.stringValue ?? "unknown date"
        let freshness = routes["harness_brief"]?["freshness"]?.stringValue ?? "unknown"
        let sources = report["sources"]?.arrayValue?.map {
            "\($0["url"]?.stringValue ?? "unknown source") — \($0["status"]?.stringValue ?? "unknown")"
        }.joined(separator: "\n") ?? "Sources unavailable."
        let candidates = report["candidates"]?.arrayValue?.compactMap { $0["model"]?.stringValue }.joined(separator: ", ") ?? "none"
        let gaps = report["gaps"]?.arrayValue?.compactMap { $0.stringValue }.joined(separator: "\n") ?? ""
        return "Freshness: \(freshness)\n\(summary)\nEvidence recorded: \(date)\nDocumented candidates: \(candidates)\n\(sources)\n\(gaps)"
    }

    func refreshHarnessBrief() async {
        guard !harnessBriefRefreshing else { return }
        let revision = modelRouteServiceRevision
        harnessBriefRefreshing = true
        defer { if revision == modelRouteServiceRevision { harnessBriefRefreshing = false } }
        do {
            let result = try await modelRouteRequests.refreshBrief()
            guard !Task.isCancelled, revision == modelRouteServiceRevision,
                  case .loaded(let routes) = modelRoutesState,
                  var object = routes.objectValue else { return }
            object["harness_brief"] = result
            modelRoutesState = .loaded(.object(object))
        } catch {
            guard revision == modelRouteServiceRevision else { return }
            modelRouteNote = "Official model evidence refresh failed; no model was changed."
        }
    }

    var modelRouteWorkloads: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let object = value["workloads"]?.objectValue else { return [] }
        return Set(Array(object.keys) + [selectedModelWorkload]).sorted()
    }

    var modelRouteProfiles: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let profiles = value["profiles"]?.arrayValue else { return [] }
        let names = profiles.filter {
            guard let workloads = $0["supported_workloads"]?.arrayValue else { return true }
            return workloads.contains(.string(selectedModelWorkload))
        }.compactMap { $0["name"]?.stringValue }
        return Set(names + [selectedModelProfile]).sorted()
    }

    var modelRouteNames: [String] {
        guard case .loaded(let value) = modelRoutesState,
              let routes = value["routes"]?.objectValue else { return [] }
        let profile = value["profiles"]?.arrayValue?.first { $0["name"]?.stringValue == selectedModelProfile }
        let names = profile?["routes"]?.arrayValue?.compactMap { $0.stringValue } ?? Array(routes.keys)
        // Keep an unavailable saved choice visible; never substitute a route.
        return Set(names + [selectedModelRoute]).sorted()
    }

    var modelRouteActivationSummary: String {
        guard case .loaded(let value) = modelRoutesState,
              let enabled = value["routing_enabled"]?.boolValue else { return "Runtime routing status unavailable." }
        return enabled ? "Configured routing is enabled in the admin process; bot status must also be verified."
            : "Routing is disabled in the admin process; bot status has not been verified. Saving a choice does not change the activation flag."
    }

    var selectedModelRouteSummary: String? {
        guard case .loaded(let value) = modelRoutesState else { return nil }
        let descriptor: JSONValue?
        if value["choices"]?.objectValue != nil {
            descriptor = value["choices"]?[selectedModelWorkload]?[selectedModelProfile]?[selectedModelRoute]
        } else {
            descriptor = value["routes"]?[selectedModelRoute]
        }
        guard let route = descriptor?.objectValue else {
            return "Saved or selected route is unavailable in the current catalog."
        }
        let capabilities = route["capabilities"]?.arrayValue?.compactMap { $0.stringValue }
            .joined(separator: ", ")
        let privacy = route["privacy"]?.stringValue
        let billing = route["billing"]?.stringValue
        let parts = [
            capabilities.map { "capabilities: \($0)" },
            privacy.map { "privacy: \($0)" },
            billing.map { "billing: \($0)" },
            route["reason"]?.stringValue,
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
                    DisclosureGroup("Harness model daily brief") {
                        Button("Refresh official model evidence") { Task { await model.refreshHarnessBrief() } }
                            .disabled(model.harnessBriefRefreshing)
                        Text(model.harnessBriefSummary)
                            .font(.system(size: 11))
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let proposal = model.modelRouteProposalSummary {
                        Text(proposal)
                            .font(.system(size: 11))
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if model.selectedModelWorkload == "voice_supervisor" {
                        Text("Harness switching is unavailable. Runtime identity and approval across all configuration writers are not yet enforced.")
                            .foregroundStyle(AppTheme.textDim)
                    }
                    HStack {
                        Button("Draft route") { Task { await model.stageModelRoute() } }
                            .tint(AppTheme.accent)
                            .disabled(model.selectedModelWorkload == "voice_supervisor" || model.modelRouteStaging || model.modelRouteConfirming)
                        if model.modelRouteDraftID != nil {
                            Button("Confirm selection snapshot") { Task { await model.confirmModelRoute() } }
                                .tint(AppTheme.green)
                            Button("Discard", action: model.discardModelRouteDraft)
                        }
                        Button("Refresh") { Task { await model.refreshModelRoutes() } }
                            .buttonStyle(.borderless)
                    }
                    .disabled(model.modelRouteConfirming)
                    Text(model.modelRouteActivationSummary)
                        .font(.system(size: 10))
                        .foregroundStyle(AppTheme.textDim)
                    if let note = model.modelRouteNote {
                        Text(note)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(note.contains("failed") || note.contains("rejected") ? AppTheme.red : AppTheme.textDim)
                    }
                    Text("Changes are staged and require explicit confirmation. Unavailable routes fail closed.")
                        .font(.system(size: 10))
                        .foregroundStyle(AppTheme.textDim)
                }
                .disabled(model.modelRouteConfirming)
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
