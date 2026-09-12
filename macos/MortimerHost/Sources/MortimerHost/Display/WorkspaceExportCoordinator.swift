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
    @ObservationIgnored private var panel: NSSavePanel?

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
