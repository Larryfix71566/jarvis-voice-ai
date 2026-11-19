import SwiftUI
import AppKit
import JarvisKit
import UniformTypeIdentifiers

/// Interface cleanup Phase 2: the one implementation of "turn a drop, a paste
/// or a chosen file into staged content". The composer pill, the whole-window
/// drop and AttachmentTrayView all call it. Intake only ever STAGES; nothing
/// is sent until the user approves it and asks (AttachmentStore rules).
enum AttachmentIntake {
    static let maxItems = 4

    static let dropTypeIdentifiers = [
        UTType.fileURL.identifier, UTType.text.identifier, UTType.plainText.identifier,
        UTType.png.identifier, UTType.jpeg.identifier, UTType.heic.identifier,
        UTType.webP.identifier,
    ]

    static let importContentTypes: [UTType] = [.plainText, .utf8PlainText, .png, .jpeg, .heic, .webP]

    static func normalize(data: Data, typeIdentifier: String,
                          fileExtension: String? = nil) -> SharedContentTransfer? {
        let type = UTType(importedAs: typeIdentifier)
        if type.conforms(to: .image) {
            let ext = (fileExtension ?? type.preferredFilenameExtension ?? "png").lowercased()
            let mime = ext == "jpg" || ext == "jpeg" ? "image/jpeg" :
                (ext == "heic" ? "image/heic" : (ext == "webp" ? "image/webp" : "image/png"))
            return AttachmentNormalizer.image(data, mimeType: mime)
        }
        guard type.conforms(to: .text) || fileExtension != nil else { return nil }
        return AttachmentNormalizer.text(String(data: data, encoding: .utf8) ?? "")
    }

    /// Stage up to four dropped providers. Returns whether the drop was accepted.
    @MainActor
    static func handleDrop(_ providers: [NSItemProvider], into store: AttachmentStore) -> Bool {
        for provider in providers.prefix(maxItems) { loadDrop(provider, into: store) }
        return !providers.isEmpty
    }

    @MainActor
    static func loadDrop(_ provider: NSItemProvider, into store: AttachmentStore) {
        let generation = store.stagingGeneration
        let typeIdentifier = dropTypeIdentifiers.first {
            provider.hasItemConformingToTypeIdentifier($0)
        }
        guard let typeIdentifier else {
            store.stageError("That item type is not supported.", expectedGeneration: generation)
            return
        }
        if typeIdentifier == UTType.fileURL.identifier {
            provider.loadFileRepresentation(forTypeIdentifier: typeIdentifier) { url, _ in
                guard let url, let data = try? Data(contentsOf: url) else {
                    DispatchQueue.main.async {
                        MainActor.assumeIsolated {
                            _ = store.stageError("The dropped file could not be read.", expectedGeneration: generation)
                        }
                    }
                    return
                }
                let item = Self.normalize(data: data,
                    typeIdentifier: UTType(filenameExtension: url.pathExtension)?.identifier ?? UTType.item.identifier,
                    fileExtension: url.pathExtension)
                DispatchQueue.main.async {
                    MainActor.assumeIsolated {
                        if let item { _ = store.stage(item, expectedGeneration: generation) }
                        else { _ = store.stageError("The dropped file is not a supported text or image.", expectedGeneration: generation) }
                    }
                }
            }
            return
        }
        provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, _ in
            let item = data.flatMap { Self.normalize(data: $0, typeIdentifier: typeIdentifier) }
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    if let item { _ = store.stage(item, expectedGeneration: generation) }
                    else { _ = store.stageError("The dropped item could not be normalized.", expectedGeneration: generation) }
                }
            }
        }
    }

    @MainActor
    static func paste(into store: AttachmentStore, board: NSPasteboard = .general) {
        if let image = board.data(forType: .png), let item = AttachmentNormalizer.image(image, mimeType: "image/png") {
            store.stage(item); return
        }
        if let text = board.string(forType: .string), let item = AttachmentNormalizer.text(text) {
            store.stage(item); return
        }
        store.stageError("Clipboard has no supported text or image.")
    }

    @MainActor
    static func importFiles(_ result: Result<[URL], Error>, into store: AttachmentStore) {
        guard case .success(let urls) = result else { return }
        for url in urls.prefix(maxItems) {
            guard let data = try? Data(contentsOf: url) else { continue }
            let identifier = UTType(filenameExtension: url.pathExtension)?.identifier ?? UTType.plainText.identifier
            if let item = Self.normalize(data: data, typeIdentifier: identifier, fileExtension: url.pathExtension) {
                store.stage(item)
            }
        }
    }
}
