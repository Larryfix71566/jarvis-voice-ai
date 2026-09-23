import SwiftUI
import JarvisKit

/// Command Console v2 composition. It is additive: WorkspaceView remains the
/// owner of result history while this view provides the Atlas working surface.
struct CommandConsoleView: View {
    let voiceState: VoiceState
    let wideWindow: Bool
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(AttachmentStore.self) private var attachments
    @EnvironmentObject private var client: JarvisClient
    @Environment(ConsoleNoticeState.self) private var notices
    @State private var transferTask: Task<Void, Never>?
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Label("Command Console", systemImage: "command")
                    .font(.headline)
                Button("Conversation") {
                    if let coordinator { _ = coordinator.executePointer(.viewSet, target: "conversation") }
                    else { workspace.returnToConversation() }
                }
                Button("Knowledge Atlas") {
                    if let coordinator { _ = coordinator.executePointer(.viewSet, target: "atlas") }
                    else { workspace.openAtlas() }
                }
                Button("Memory graph") {
                    if let coordinator { _ = coordinator.executePointer(.viewSet, target: "memory") }
                    else { workspace.openMemoryGraph() }
                }
                Spacer()
                if let result = notices.consoleResult {
                    Text(result.summary)
                        .font(.caption)
                        .lineLimit(1)
                        .foregroundStyle(result.status == "error" ? AppTheme.red : AppTheme.text.opacity(0.7))
                }
            }
            .padding(16)
            .background(AppTheme.panel.opacity(0.55))
            AdaptiveStageView(voiceState: voiceState, wideWindow: wideWindow,
                              coordinator: coordinator)
            // Keep the first inbound-content affordance visible. Previously
            // the tray appeared only after staging had already happened,
            // leaving paste/choose/drop with no discoverable entry point.
            AttachmentTrayView(onAsk: sendSharedContent,
                                onApproveOffer: approveOffer,
                                onDeclineOffer: declineOffer)
        }
        .background(AppTheme.bg)
        .onChange(of: attachments.cancelRequest) { _, _ in
            transferTask?.cancel()
            transferTask = nil
            attachments.stageError("Content transfer cancelled.")
        }
        .onChange(of: attachments.pendingConsent) { _, consent in
            guard let consent else { return }
            attachments.clearConsent()
            guard let offer = attachments.pendingOffer,
                  offer.batchID == consent.batchID else { return }
            if consent.approved { sendSharedContent(offer: offer) }
            else { declineOffer() }
        }
    }

    /// Send only explicitly approved, locally normalized items. The sequence
    /// is deterministic and bounded: manifest, ordered chunks, commit for
    /// each item, then one analysis request. The bot owns provider execution;
    /// this view never sends a path or silently approves content.
    private func sendSharedContent() {
        sendSharedContent(offer: nil)
    }

    private func approveOffer() {
        guard let offer = attachments.pendingOffer else { return }
        sendSharedContent(offer: offer)
    }

    private func declineOffer() {
        attachments.clearOffer()
        attachments.stageError("Shared content request cancelled.")
    }

    private func sendSharedContent(offer: InputOffer?) {
        guard let sessionID = client.consoleSessionID,
              let generation = client.consoleGeneration else {
            attachments.stageError("Connect to Mortimer before sending content.")
            return
        }
        let selected: [SharedContentTransfer]
        let question: String
        if let offer {
            let offered = Set(offer.attachmentIDs)
            selected = attachments.staged.filter { offered.contains($0.contentID) }
            question = offer.question.trimmingCharacters(in: .whitespacesAndNewlines)
        } else {
            selected = attachments.staged.filter { attachments.approvedIDs.contains($0.contentID) }
            question = attachments.question.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        guard !selected.isEmpty, !question.isEmpty else {
            attachments.stageError("Approve at least one item and enter a question.")
            return
        }
        let batchID = offer?.batchID ?? UUID()
        let approvalID = UUID()
        let manifest = InputManifest(
            sessionID: sessionID, generation: generation, batchID: batchID,
            approvalID: approvalID, question: question,
            attachments: selected.map(InputManifestAttachment.init))
        attachments.clearOffer()
        transferTask?.cancel()
        transferTask = Task { @MainActor in
            // Register the accept waiter before sending the manifest so a
            // fast local transport cannot race the continuation.
            let acceptTask = Task { @MainActor in
                await waitForAccept(batchID: batchID)
            }
            client.send(.inputManifest(manifest))
            guard let accept = await acceptTask.value else {
                attachments.stageError("Mortimer did not accept the content transfer.")
                return
            }
            let transferID = accept.transferID
            let chunkSize = min(16 * 1024, max(1, accept.maxChunkBytes))
            for content in selected {
                let bytes = content.payload
                var offset = 0
                var sequence = 0
                while offset < bytes.count {
                    if Task.isCancelled { return }
                    let end = min(offset + chunkSize, bytes.count)
                    let chunk = bytes.subdata(in: offset..<end)
                    let currentSequence = sequence
                    let ackTask = Task { @MainActor in
                        await waitForAck(transferID: transferID,
                                         attachmentID: content.contentID,
                                         sequence: currentSequence)
                    }
                    client.send(.inputChunk(InputChunk(
                        sessionID: sessionID, generation: generation,
                        transferID: transferID, attachmentID: content.contentID,
                        sequence: currentSequence, base64: chunk.base64EncodedString())))
                    guard await ackTask.value else {
                        client.send(.inputCancel(InputCancel(
                            sessionID: sessionID, generation: generation,
                            batchID: batchID, transferID: transferID)))
                        attachments.stageError("The content transfer timed out; nothing was analyzed.")
                        return
                    }
                    offset = end; sequence += 1
                    // Keep byte transfer off the audio callback cadence while
                    // respecting the protocol's minimum inter-chunk spacing.
                    try? await Task.sleep(nanoseconds: 10_000_000)
                }
                client.send(.inputCommit(InputCommit(
                    sessionID: sessionID, generation: generation,
                    transferID: transferID, attachmentID: content.contentID,
                    totalChunks: sequence, totalBytes: bytes.count,
                    sha256: content.digest)))
            }
            client.send(.inputAnalyze(InputAnalyze(
                sessionID: sessionID, generation: generation, batchID: batchID,
                attachmentIDs: selected.map(\.contentID), question: question)))
        }
    }

    private func waitForAccept(batchID: UUID) async -> InputAccept? {
        await withTaskGroup(of: InputAccept?.self) { group in
            group.addTask { await client.waitForInputAccept(batchID: batchID) }
            group.addTask {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                return nil
            }
            let value = await group.next() ?? nil
            group.cancelAll()
            return value
        }
    }

    private func waitForAck(transferID: UUID, attachmentID: UUID,
                            sequence: Int) async -> Bool {
        await withTaskGroup(of: Bool.self) { group in
            group.addTask {
                await client.waitForInputAck(transferID: transferID,
                                             attachmentID: attachmentID,
                                             sequence: sequence)
            }
            group.addTask {
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                return false
            }
            let value = await group.next() ?? false
            group.cancelAll()
            return value
        }
    }
}
