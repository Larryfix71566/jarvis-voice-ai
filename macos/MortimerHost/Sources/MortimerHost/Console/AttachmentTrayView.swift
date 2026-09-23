import SwiftUI
import JarvisKit
import UniformTypeIdentifiers

struct AttachmentTrayView: View {
    @Environment(AttachmentStore.self) private var attachments
    @EnvironmentObject private var client: JarvisClient
    @State private var showPicker = false
    @State private var dropTargeted = false
    var onAsk: (() -> Void)?
    var onApproveOffer: (() -> Void)?
    var onDeclineOffer: (() -> Void)?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(attachments.staged.isEmpty ? "Add content" : "Staged content").font(.headline)
                Spacer()
                Button("Paste") { paste() }
                    .accessibilityLabel("Paste content")
                Button("Choose") { showPicker = true }
                    .accessibilityLabel("Choose content")
            }
            Text(attachments.staged.isEmpty
                 ? "Paste text or an image, choose a file, or drop it here for review."
                 : "Analysis provider: \(client.consoleInputProfile?.label ?? "Configured vision")")
                .font(.caption)
                .foregroundStyle(AppTheme.textDim)
            if let offer = attachments.pendingOffer {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Approval required").font(.subheadline.weight(.semibold))
                    Text("Send these selected items to \(offer.profile.label) for analysis? Memory saving will pause until reconnect.")
                        .font(.caption)
                    HStack {
                        Button("Send these items") { onApproveOffer?() }
                            .accessibilityLabel("Send these items")
                            .disabled(onApproveOffer == nil)
                        Button("Cancel these items") { onDeclineOffer?() }
                            .accessibilityLabel("Cancel these items")
                            .disabled(onDeclineOffer == nil)
                    }
                }
                .padding(8)
                .background(AppTheme.amber.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityElement(children: .contain)
            }
            if attachments.staged.isEmpty {
                Label("Drop text or image files here", systemImage: "arrow.down.doc")
                    .font(.caption)
                    .foregroundStyle(dropTargeted ? AppTheme.accent : AppTheme.textDim)
                    .accessibilityLabel("Drop text or image files here")
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 8)
                    .background((dropTargeted ? AppTheme.accent : AppTheme.hairline).opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 8))
            }
            ForEach(attachments.staged, id: \.contentID) { item in
                HStack {
                    Text(item.kind.rawValue.capitalized)
                    Spacer()
                    Button(attachments.approvedIDs.contains(item.contentID) ? "Approved" : "Approve") { attachments.approve(item.contentID) }
                    Button("Remove") { attachments.remove(item.contentID) }
                }
            }
            if !attachments.staged.isEmpty {
                TextField("Question for Mortimer", text: Binding(
                    get: { attachments.question }, set: { attachments.setQuestion($0) }))
                    .textFieldStyle(.roundedBorder)
            }
            HStack {
                if let error = attachments.error { Text(error).foregroundStyle(AppTheme.red) }
                Spacer()
                if !attachments.staged.isEmpty {
                    Button("Clear") { attachments.clear() }
                    Button("Ask Mortimer") { onAsk?() }
                        // The tray is also used in previews and while the
                        // transport is being wired. Never present an enabled
                        // control that has no action behind it.
                        .disabled(onAsk == nil || attachments.approvedIDs.isEmpty ||
                                  attachments.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .help(onAsk == nil ? "Content analysis transport is not connected" : "Send the approved content to Mortimer")
                }
            }
        }
        .padding(12)
        .background(AppTheme.panel, in: RoundedRectangle(cornerRadius: 10))
        .onDrop(of: Self.dropTypeIdentifiers, isTargeted: $dropTargeted) { providers in
            for provider in providers.prefix(4) { loadDrop(provider) }
            return !providers.isEmpty
        }
        .fileImporter(isPresented: $showPicker, allowedContentTypes: [.plainText, .utf8PlainText, .png, .jpeg, .heic, .webP], allowsMultipleSelection: true) { result in
            guard case .success(let urls) = result else { return }
            for url in urls.prefix(4) {
                guard let data = try? Data(contentsOf: url) else { continue }
                if let item = Self.normalize(data: data, typeIdentifier: UTType(filenameExtension: url.pathExtension)?.identifier ?? UTType.plainText.identifier, fileExtension: url.pathExtension) { attachments.stage(item) }
            }
        }
    }

    private static let dropTypeIdentifiers = [
        UTType.fileURL.identifier, UTType.text.identifier, UTType.plainText.identifier,
        UTType.png.identifier, UTType.jpeg.identifier, UTType.heic.identifier,
        UTType.webP.identifier,
    ]

    private static func normalize(data: Data, typeIdentifier: String,
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

    private func loadDrop(_ provider: NSItemProvider) {
        let generation = attachments.stagingGeneration
        let typeIdentifier = Self.dropTypeIdentifiers.first {
            provider.hasItemConformingToTypeIdentifier($0)
        }
        guard let typeIdentifier else {
            attachments.stageError("That item type is not supported.", expectedGeneration: generation)
            return
        }
        if typeIdentifier == UTType.fileURL.identifier {
            provider.loadFileRepresentation(forTypeIdentifier: typeIdentifier) { url, _ in
                guard let url, let data = try? Data(contentsOf: url) else {
                    DispatchQueue.main.async { attachments.stageError("The dropped file could not be read.", expectedGeneration: generation) }
                    return
                }
                let item = Self.normalize(data: data, typeIdentifier: UTType(filenameExtension: url.pathExtension)?.identifier ?? UTType.item.identifier, fileExtension: url.pathExtension)
                DispatchQueue.main.async {
                    if let item { attachments.stage(item, expectedGeneration: generation) }
                    else { attachments.stageError("The dropped file is not a supported text or image.", expectedGeneration: generation) }
                }
            }
            return
        }
        provider.loadDataRepresentation(forTypeIdentifier: typeIdentifier) { data, _ in
            let item = data.flatMap { Self.normalize(data: $0, typeIdentifier: typeIdentifier) }
            DispatchQueue.main.async {
                if let item { attachments.stage(item, expectedGeneration: generation) }
                else { attachments.stageError("The dropped item could not be normalized.", expectedGeneration: generation) }
            }
        }
    }

    private func paste() {
        let board = NSPasteboard.general
        if let image = board.data(forType: .png), let item = AttachmentNormalizer.image(image, mimeType: "image/png") { attachments.stage(item); return }
        if let text = board.string(forType: .string), let item = AttachmentNormalizer.text(text) { attachments.stage(item); return }
        attachments.stageError("Clipboard has no supported text or image.")
    }
}
