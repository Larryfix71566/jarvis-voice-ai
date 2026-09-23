import Foundation
import Observation
import JarvisKit

@MainActor
@Observable
final class AttachmentStore {
    private(set) var staged: [SharedContentTransfer] = []
    private(set) var approvedIDs: Set<UUID> = []
    private(set) var error: String?
    /// Increments when staged content is cleared. Async file-provider
    /// callbacks must present the generation they started with, otherwise a
    /// late completion could repopulate content the user explicitly removed.
    private(set) var stagingGeneration: UInt64 = 0
    var question = ""
    var previewVisible = false
    private(set) var cancelRequest = 0
    private(set) var pendingOffer: InputOffer?
    private(set) var pendingConsent: InputConsent?
    private var offerExpiryTask: Task<Void, Never>?

    @discardableResult
    func stage(_ content: SharedContentTransfer, expectedGeneration: UInt64? = nil) -> Bool {
        guard expectedGeneration == nil || expectedGeneration == stagingGeneration else { return false }
        guard staged.count < 4 else { error = "Up to four items can be staged."; return false }
        guard !staged.contains(where: { $0.contentID == content.contentID }) else { return false }
        staged.append(content); error = nil; return true
    }
    func approve(_ id: UUID) { guard staged.contains(where: { $0.contentID == id }) else { return }; approvedIDs.insert(id) }
    func remove(_ id: UUID) { staged.removeAll { $0.contentID == id }; approvedIDs.remove(id); error = nil }
    func clear() {
        stagingGeneration &+= 1
        staged.removeAll(); approvedIDs.removeAll(); question = ""; error = nil; previewVisible = false; clearOffer()
    }
    func setQuestion(_ value: String) { question = String(value.prefix(2000)) }
    @discardableResult
    func stageError(_ message: String, expectedGeneration: UInt64? = nil) -> Bool {
        guard expectedGeneration == nil || expectedGeneration == stagingGeneration else { return false }
        error = String(message.prefix(200)); return true
    }
    func requestCancel() { cancelRequest &+= 1 }

    func presentOffer(_ offer: InputOffer) {
        guard (1...4).contains(offer.attachmentIDs.count) else {
            stageError("The approval offer is not valid.")
            return
        }
        offerExpiryTask?.cancel()
        pendingOffer = offer
        error = nil
        let batchID = offer.batchID
        offerExpiryTask = Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 120_000_000_000)
            guard !Task.isCancelled, let self,
                  self.pendingOffer?.batchID == batchID else { return }
            self.pendingOffer = nil
            self.error = "The content approval expired; ask again to review it."
            self.offerExpiryTask = nil
        }
    }

    func clearOffer() {
        offerExpiryTask?.cancel()
        offerExpiryTask = nil
        pendingOffer = nil
        pendingConsent = nil
    }

    func presentConsent(_ consent: InputConsent) {
        guard pendingOffer?.batchID == consent.batchID else { return }
        pendingConsent = consent
    }

    func clearConsent() {
        pendingConsent = nil
    }

    /// Privacy-safe inventory entries for voice target resolution. Payload
    /// bytes, digests and question text stay local to the staged tray.
    var consoleInventoryEntries: [JSONValue] {
        staged.map { item in
            .object([
                "id": .string(item.contentID.uuidString),
                "label": .string("\(item.kind) attachment"),
                "mime": .string(item.mimeType),
                "state": .string(approvedIDs.contains(item.contentID) ? "approved" : "staged"),
            ])
        }
    }
}
