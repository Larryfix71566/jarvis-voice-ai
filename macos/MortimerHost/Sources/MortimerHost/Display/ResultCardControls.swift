import SwiftUI
import JarvisKit

// C5: result-specific views live outside the transcript.
/// Legacy compact result controls, retained for standalone callers outside
/// the transcript. Open shows the result; the menu pins, compares or closes it.
/// Closing removes the card and the result from the workspace only; the
/// Output history keeps its record (§7.2 Codex boundary 2).
struct ConversationThreadCardView: View {
    let card: ConversationThread.Card
    let coordinator: ConsoleActionCoordinator?
    @Binding var pinLimitNotice: Bool
    @Environment(WorkspaceStore.self) private var workspace

    init(card: ConversationThread.Card, coordinator: ConsoleActionCoordinator?,
         pinLimitNotice: Binding<Bool>) {
        self.card = card
        self.coordinator = coordinator
        self._pinLimitNotice = pinLimitNotice
    }

    var body: some View {
        let pinned = workspace.pinnedIDs.contains(card.id)
        let unread = workspace.unreadIDs.contains(card.id)
        HStack(spacing: 10) {
            Image(systemName: card.isPrivate ? "lock.fill" : card.icon)
                .font(.system(size: 15))
                .foregroundStyle(AppTheme.listening)
                .frame(width: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(card.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.text)
                    .lineLimit(1)
                if !card.summary.isEmpty {
                    Text(card.summary)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textDim)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if unread { Label("Unread", systemImage: "circle.fill").font(.caption).foregroundStyle(AppTheme.listening) }
            if workspace.updatedIDs.contains(card.id) { Label("Updated", systemImage: "arrow.clockwise").font(.caption).foregroundStyle(AppTheme.mortimer) }
            if pinned {
                Image(systemName: "pin.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(AppTheme.textDim)
                    .help("Pinned")
                    .accessibilityLabel("Pinned")
            }
            Menu {
                Button(pinned ? "Unpin" : "Pin") { togglePin(pinned: pinned) }
                Menu("Compare with") {
                    ForEach(workspace.results.filter { $0.id != card.id }) { other in
                        Button(ConversationThread.card(other).title) { compare(with: other.id) }
                    }
                }
                .disabled(workspace.results.count < 2)
                Divider()
                Button("Close") { close() }
            } label: {
                Image(systemName: "ellipsis")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pin, compare or close")
            .accessibilityLabel("More actions for \(card.title)")
            Button("Open") { open() }
                .help("Show this result; Conversation brings you back")
                .accessibilityLabel("Open \(card.title)")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(AppTheme.panel.opacity(0.8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.hairline))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .padding(.vertical, 6)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(card.summary.isEmpty ? card.title : "\(card.title). \(card.summary)")
        .accessibilityIdentifier("thread-card")
    }

    private var target: String { card.id.uuidString }

    private func open() {
        if let coordinator { _ = coordinator.executePointer(.resultSelect, target: target) }
        else { workspace.select(card.id) }
    }

    private func togglePin(pinned: Bool) {
        if let coordinator {
            if coordinator.executePointer(pinned ? .resultUnpin : .resultPin, target: target) == .noop,
               !pinned { pinLimitNotice = true }
        } else if pinned {
            workspace.unpin(card.id)
        } else {
            pinLimitNotice = !workspace.pin(card.id)
        }
    }

    private func compare(with other: UUID) {
        if let coordinator {
            _ = coordinator.executePointer(.compareSet, target: target, secondaryTarget: other.uuidString)
        } else {
            workspace.select(card.id)
            workspace.compare(with: other)
        }
    }

    private func close() {
        if let coordinator { _ = coordinator.executePointer(.resultClose, target: target) }
        else { workspace.close(card.id) }
    }
}

/// CC7a.2 approved design "New result while reading": while something
/// other than the conversation is on the stage, an arrival shows
/// "New: … Show / Dismiss" above it instead of taking the stage. On the
/// conversation itself the answer to what Larry just asked opens (Larry,
/// 10-03; `ArrivalIntent`); its card stays in the thread for later.
struct ArrivalNoticeView: View {
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace

    init(coordinator: ConsoleActionCoordinator?) {
        self.coordinator = coordinator
    }

    var body: some View {
        if let id = workspace.arrivalNoticeID,
           let result = workspace.results.first(where: { $0.id == id }) {
            let card = ConversationThread.card(result)
            HStack(spacing: 10) {
                Image(systemName: card.isPrivate ? "lock.fill" : card.icon)
                    .foregroundStyle(AppTheme.listening)
                    .accessibilityHidden(true)
                Text("New: \(card.title)")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.text)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Button("Show") {
                    if let coordinator { _ = coordinator.executePointer(.resultSelect, target: id.uuidString) }
                    else { workspace.select(id) }
                }
                Button("Dismiss") { workspace.dismissArrivalNotice() }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(AppTheme.listening.opacity(0.12))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.listening.opacity(0.35)))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .padding(.horizontal, AdaptiveLayoutMetrics.workspacePadding)
            .padding(.top, 8)
            .accessibilityElement(children: .contain)
            .accessibilityLabel("New result: \(card.title)")
            .accessibilityIdentifier("arrival-notice")
        }
    }
}
