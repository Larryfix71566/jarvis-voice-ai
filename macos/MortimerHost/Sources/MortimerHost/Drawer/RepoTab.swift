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
    let api: AdminAPI
    var state: TabState<GitStatus> = .loading
    var commitMessage = ""
    var pendingCommit: GitDraft?
    var pendingPush: GitDraft?
    var actionError: String?
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI) { self.api = api }

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
            // git_status() is returned VERBATIM (no ok wrapper, P2). A
            // clean tree still renders the full panel (branch line +
            // disabled input + Push), exactly the web's GitPanel — never
            // an empty state that hides the controls (parity sweep).
            state = .loaded(status)
        } catch {
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }   // N13: no retry on 401
        }
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
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task { model.startPolling() }
        .onDisappear { model.stopPolling() }
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
