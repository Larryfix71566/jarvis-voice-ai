import AppKit
import UniformTypeIdentifiers
import Observation

/// App-owned so a save dialog and completion survive result-view reparenting.
/// No file is written before the user accepts the native destination dialog.
@MainActor
@Observable
final class WorkspaceExportCoordinator {
    private(set) var busy = false
    private(set) var resultID: UUID?
    private(set) var message: String?
    private(set) var exportFolderURL: URL?
    @ObservationIgnored private var panel: NSSavePanel?

    init() {
        if let bookmark = UserDefaults.standard.data(forKey: "mortimer.export.folderBookmark") {
            var stale = false
            if let url = try? URL(resolvingBookmarkData: bookmark, options: [.withSecurityScope], relativeTo: nil,
                                  bookmarkDataIsStale: &stale), !stale {
                exportFolderURL = url
            }
        }
    }

    /// Choose and retain only a security-scoped bookmark for the approved
    /// export folder. No files are read, written, or deleted by this action.
    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.begin { [weak self] response in
            guard let self, response == .OK, let url = panel.url else { return }
            guard let bookmark = try? url.bookmarkData(options: .withSecurityScope,
                                                       includingResourceValuesForKeys: nil,
                                                       relativeTo: nil) else { return }
            UserDefaults.standard.set(bookmark, forKey: "mortimer.export.folderBookmark")
            self.exportFolderURL = url
            self.message = "Export folder set to \(url.lastPathComponent)."
        }
    }

    func clearFolder() {
        UserDefaults.standard.removeObject(forKey: "mortimer.export.folderBookmark")
        exportFolderURL = nil
        message = "Export folder cleared."
    }

    func copy(text: String) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        message = pasteboard.setString(text, forType: .string) ? "Copied result." : "Copy failed."
    }

    func chooseDestination(for result: WorkspaceResult) {
        guard !busy else { return }
        busy = true; resultID = result.id; message = nil
        let text = WorkspaceResultExport.text(result)
        let panel = NSSavePanel()
        self.panel = panel
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = "Mortimer result.txt"
        panel.canCreateDirectories = true
        panel.message = "Save the supplied text and reference URLs. Images are not downloaded. Clipboard content is excluded."
        panel.begin { [weak self] response in
            guard let self else { return }
            self.panel = nil
            guard response == .OK, let url = panel.url else {
                self.busy = false; self.message = "Export cancelled."; return
            }
            Task { await self.write(text: text, to: url) }
        }
    }

    /// Injectable completion seam: status reflects the actual write outcome.
    func write(text: String, to url: URL,
               writer: @escaping @Sendable (Data, URL) async throws -> Void = { data, destination in
                   try await Task.detached(priority: .utility) {
                       let scoped = destination.startAccessingSecurityScopedResource()
                       defer { if scoped { destination.stopAccessingSecurityScopedResource() } }
                       try data.write(to: destination, options: .atomic)
                   }.value
               }) async {
        busy = true; message = nil
        do {
            try await writer(Data(text.utf8), url)
            message = "Saved \(url.lastPathComponent)."
        } catch {
            message = "Export failed: \(error.localizedDescription)"
        }
        busy = false
    }
}
