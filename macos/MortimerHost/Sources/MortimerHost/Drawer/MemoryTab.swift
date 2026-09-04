import SwiftUI
import Observation
import JarvisKit

/// APP plan §3 P4, §5 step 8 — the Memory tab: fact cards, the review
/// queue with resolve actions, per-fact delete (with confirm), and the
/// knowledge readout with notReachingPrompt as the LOUD line (the number
/// /api/knowledge exists to make visible — silent truncation must not be
/// archaeology). Polls every memoryPollSeconds (15 s, F5).
@MainActor
@Observable
final class MemoryViewModel {
    struct Loaded {
        var overview: MemoryOverview
        var reviews: [MemoryReview]
        var knowledge: KnowledgeOverview?
    }

    let api: AdminAPI
    var state: TabState<Loaded> = .loading
    var actionError: String?
    var confirmingDeleteKey: String?
    private var pollTask: Task<Void, Never>?
    private var stopped = false

    init(api: AdminAPI) { self.api = api }

    func startPolling() {
        guard pollTask == nil, !stopped else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                if self?.stopped == true { return }
                try? await Task.sleep(nanoseconds: UInt64(AppTuning.memoryPollSeconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        do {
            let overview = try await api.memoryOverview()
            let reviews = try? await api.memoryReviewsTyped()
            let knowledge = try? await api.knowledgeTyped()
            if !overview.ok {
                state = .error("request failed")
            } else if overview.facts.isEmpty && (reviews?.reviews?.isEmpty ?? true) {
                state = .empty
            } else {
                state = .loaded(Loaded(
                    overview: overview,
                    reviews: reviews?.reviews ?? [],
                    knowledge: knowledge
                ))
            }
        } catch {
            let (message, unauthorized) = TabStateMapper.fromError(error)
            state = .error(message)
            if unauthorized { stopped = true; stopPolling() }
        }
    }

    func deleteFact(key: String) {
        Task {
            actionError = nil
            do {
                let result = try await api.deleteFact(key: key)
                if result["ok"]?.boolValue == false {
                    actionError = result["error"]?.stringValue ?? "delete failed"
                }
                confirmingDeleteKey = nil
                await refresh()
            } catch { actionError = TabStateMapper.fromError(error).state }
        }
    }

    func resolve(id: Int, action: String) {
        Task {
            actionError = nil
            do {
                let result = try await api.resolveReview(id: id, action: action, rewriteContent: nil)
                if result["ok"]?.boolValue == false {
                    actionError = result["error"]?.stringValue ?? "resolve failed"
                }
                await refresh()
            } catch { actionError = TabStateMapper.fromError(error).state }
        }
    }
}

struct MemoryTab: View {
    @Bindable var model: MemoryViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                switch model.state {
                case .loading:
                    ProgressView("Memory").frame(maxWidth: .infinity)
                case .empty:
                    Text("No facts stored yet.").foregroundStyle(AppTheme.textDim)
                case .error(let message):
                    Text(message).foregroundStyle(AppTheme.red)
                case .loaded(let loaded):
                    loadedView(loaded)
                }
                if let actionError = model.actionError {
                    Text(actionError).foregroundStyle(AppTheme.red).font(.callout)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task { model.startPolling() }
        .onDisappear { model.stopPolling() }
    }

    @ViewBuilder
    private func loadedView(_ loaded: MemoryViewModel.Loaded) -> some View {
        // The knowledge readout — notReachingPrompt is the loud element (P4).
        if let knowledgeMemory = loaded.knowledge?.memory {
            VStack(alignment: .leading, spacing: 4) {
                if knowledgeMemory.notReachingPrompt > 0 {
                    Label("\(knowledgeMemory.notReachingPrompt) facts NOT reaching the prompt",
                          systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(AppTheme.amber)
                        .font(.callout.weight(.semibold))
                }
                Text("\(knowledgeMemory.live) live · \(knowledgeMemory.archived) archived · \(knowledgeMemory.reachingPrompt) in prompt · \(knowledgeMemory.contextChars) chars")
                    .font(.caption)
                    .foregroundStyle(AppTheme.textDim)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .mortimerGlass(.card)
        }

        if loaded.overview.usage.overCapacity {
            Text("Memory over capacity (\(loaded.overview.usage.factCount) facts)")
                .foregroundStyle(AppTheme.amber).font(.callout)
        }

        // The review queue.
        if !loaded.reviews.isEmpty {
            Text("Reviews").font(.headline)
            ForEach(loaded.reviews, id: \.id) { review in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(review.kind).font(.caption.weight(.semibold)).foregroundStyle(AppTheme.attn)
                        Spacer()
                        Text(review.createdAt).font(.caption2).foregroundStyle(AppTheme.textDim)
                    }
                    Text(review.detail).font(.callout)
                    if !review.keys.isEmpty {
                        Text(review.keys.joined(separator: " · "))
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(AppTheme.textDim)
                    }
                    HStack {
                        Button("Approve") { model.resolve(id: review.id, action: "approve") }
                        Button("Reject") { model.resolve(id: review.id, action: "reject") }
                    }
                    .controlSize(.small)
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .mortimerGlass(.card)
            }
        }

        // Fact cards.
        Text("Facts (\(loaded.overview.facts.count))").font(.headline)
        ForEach(loaded.overview.facts, id: \.key) { fact in
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(fact.key).font(.system(.caption, design: .monospaced)).foregroundStyle(AppTheme.accent)
                    Spacer()
                    Text("\(fact.tier) · \(fact.audience)").font(.caption2).foregroundStyle(AppTheme.textDim)
                    if model.confirmingDeleteKey == fact.key {
                        Button("Really delete") { model.deleteFact(key: fact.key) }
                            .controlSize(.small).tint(AppTheme.red)
                        Button("Keep") { model.confirmingDeleteKey = nil }.controlSize(.small)
                    } else {
                        Button { model.confirmingDeleteKey = fact.key } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(AppTheme.textDim)
                    }
                }
                Text(fact.content).font(.callout)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .mortimerGlass(.card)
        }
    }
}
