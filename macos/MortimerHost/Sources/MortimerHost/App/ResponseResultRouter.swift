import Foundation
import JarvisKit

/// One in-memory result for the current user request, including assistant
/// subturns around tool calls. No backend replay or model work is involved.
@MainActor
final class ResponseResultRouter {
    private var requestKey: String?
    private var resultID = UUID()
    private var receivedAt = Date()
    private var hasPresented = false
    private var previousResponseID: UUID?
    private var lastBody = ""

    func receive(_ entries: [ConversationEntry], workspace: WorkspaceStore,
                 display: DisplayWindowStore) {
        guard !entries.isEmpty else {
            requestKey = nil; hasPresented = false; lastBody = ""
            previousResponseID = nil
            return
        }
        let userIndex = entries.lastIndex { $0.role == "user" }
        let answerEntries = entries.dropFirst(userIndex.map { $0 + 1 } ?? 0)
            .filter { $0.role == "assistant" }
        // If transcript retention drops the user anchor during a long turn,
        // continue the current response instead of making a duplicate card.
        let key = userIndex.map { entries[$0].id }
            ?? requestKey ?? answerEntries.first?.id
        guard let key else { return }
        if key != requestKey {
            requestKey = key; resultID = UUID(); hasPresented = false
            receivedAt = Date(timeIntervalSince1970: answerEntries.first?.createdAt
                              ?? entries.last!.createdAt)
            lastBody = ""
        }
        let body = answerEntries.map(\.text)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: "\n\n")
        guard !body.isEmpty, body != lastBody else { return }
        lastBody = body
        let result = WorkspaceResult(
            payload: DisplayPayload(responseText: body, timestamp: receivedAt.timeIntervalSince1970),
            id: resultID, receivedAt: receivedAt)
        if hasPresented {
            // Closing the result is an explicit dismissal for this request.
            guard workspace.containsResult(resultID) else { return }
            workspace.updateResponse(result)
            display.presentResponse(result, isNew: false)
            return
        }
        let followsResponses = workspace.showsConversation || (
            previousResponseID != nil && workspace.activeID == previousResponseID
            && !workspace.showsMemoryGraph && !workspace.showsAtlas && !workspace.showsWorkflows
            && workspace.comparisonID == nil
            && !workspace.pinnedIDs.contains(previousResponseID!))
        workspace.receive(result)
        if followsResponses { workspace.select(result.id) }
        display.presentResponse(result, isNew: true)
        previousResponseID = result.id
        hasPresented = true
    }
}
