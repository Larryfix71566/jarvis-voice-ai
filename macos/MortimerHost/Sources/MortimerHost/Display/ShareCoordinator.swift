import AppKit
import Foundation
import Observation

/// Immutable snapshot shown in the share preview. A later result arrival can
/// never retarget an already-open preview.
struct SharePreview: Identifiable, Equatable {
    let id: UUID
    let resultID: UUID
    let text: String
    let format: String
    let data: Data?
}

@MainActor
@Observable
final class ShareCoordinator {
    private(set) var preview: SharePreview?
    private(set) var status = "idle"
    private(set) var message: String?
    private var picker: NSSharingServicePicker?

    @discardableResult
    func beginPreview(_ result: WorkspaceResult, text: String? = nil) -> SharePreview {
        let value = SharePreview(id: UUID(), resultID: result.id,
                                 text: text ?? WorkspaceResultExport.text(result),
                                 format: "text", data: nil)
        preview = value; status = "preview"; message = nil
        return value
    }

    /// Freeze a rendered PNG for the share transaction. The caller supplies
    /// the already-loaded bitmap; this coordinator never downloads an
    /// arbitrary URL or captures adjacent private UI.
    @discardableResult
    func beginImagePreview(resultID: UUID, pngData: Data) -> Bool {
        guard !pngData.isEmpty, pngData.count <= 8 * 1024 * 1024 else {
            message = "The image is unavailable or exceeds the share limit."
            status = "error"
            return false
        }
        preview = SharePreview(id: UUID(), resultID: resultID, text: "Rendered image preview",
                               format: "png", data: pngData)
        status = "preview"; message = nil
        return true
    }

    /// Compatibility helper for existing callers that need the frozen text.
    @discardableResult
    func preview(_ result: WorkspaceResult) -> String { beginPreview(result).text }

    func cancel() {
        picker = nil; preview = nil; status = "idle"; message = nil
    }

    @discardableResult
    func copy() -> Bool {
        guard let preview else { message = "Nothing is ready to share."; return false }
        if preview.format == "png", let data = preview.data {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            let ok = pasteboard.setData(data, forType: .png)
            status = ok ? "copied" : "error"
            message = ok ? "Copied rendered image." : "Copy failed."
            return ok
        }
        return copy(preview.text)
    }

    @discardableResult
    func copy(_ text: String) -> Bool {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        let ok = pasteboard.setString(text, forType: .string)
        status = ok ? "copied" : "error"
        message = ok ? "Copied selected result." : "Copy failed."
        return ok
    }

    /// Opening a picker is a user boundary. This reports pending_user and
    /// never claims that a recipient accepted the item.
    @discardableResult
    func presentPicker(from view: NSView) -> Bool {
        guard let preview else { message = "Nothing is ready to share."; return false }
        let item: Any = (preview.format == "png" ? (preview.data ?? Data()) : preview.text)
        picker = NSSharingServicePicker(items: [item])
        picker?.show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
        status = "pending_user"
        message = "Share sheet opened; choose a destination."
        return true
    }

    /// Convenience adapter for the share sheet. The sheet itself owns the
    /// visible window, so no view or provider is invented when the caller is
    /// a voice action; an unavailable key window is reported honestly.
    @discardableResult
    func presentPicker() -> Bool {
        guard let view = NSApp.keyWindow?.contentView else {
            message = "The share sheet is unavailable until the window is active."
            status = "error"
            return false
        }
        return presentPicker(from: view)
    }

    /// Open the native save dialog for the frozen preview. The dialog is a
    /// user boundary; the write status is updated only after the writer
    /// completes.
    func chooseSave() {
        guard preview != nil else { message = "Nothing is ready to share."; return }
        let panel = NSSavePanel()
        let isImage = preview?.format == "png"
        panel.allowedContentTypes = isImage ? [.png] : [.plainText]
        panel.nameFieldStringValue = isImage ? "Mortimer result.png" : "Mortimer result.txt"
        panel.canCreateDirectories = true
        panel.begin { [weak self] response in
            guard let self else { return }
            guard response == .OK, let url = panel.url else {
                self.message = "Save cancelled."; self.status = "idle"; return
            }
            Task { _ = await self.save(to: url) }
        }
    }

    /// Save only the immutable preview. The writer seam is used by tests and
    /// lets the caller report actual completion rather than dialog opening.
    func save(to url: URL,
              writer: @escaping @Sendable (Data, URL) async throws -> Void = { data, destination in
                  try await Task.detached(priority: .utility) {
                      let scoped = destination.startAccessingSecurityScopedResource()
                      defer { if scoped { destination.stopAccessingSecurityScopedResource() } }
                      try data.write(to: destination, options: .atomic)
                  }.value
              }) async -> Bool {
        guard let preview else { message = "Nothing is ready to share."; return false }
        status = "saving"; message = nil
        do {
            try await writer(preview.data ?? Data(preview.text.utf8), url)
            status = "saved"; message = "Saved \(url.lastPathComponent)."
            return true
        } catch {
            status = "error"; message = "Save failed: \(error.localizedDescription)"
            return false
        }
    }
}

extension NSImage {
    func pngData() -> Data? {
        guard let tiff = tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff) else { return nil }
        return bitmap.representation(using: .png, properties: [:])
    }
}
