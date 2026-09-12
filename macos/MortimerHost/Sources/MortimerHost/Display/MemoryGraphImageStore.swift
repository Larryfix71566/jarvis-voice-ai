import AppKit
import ImageIO
import Observation
import JarvisKit

/// One session-only fallback per graph owner. Reparenting does not refetch;
/// changed focus cancels stale work and clears the previous focus's bitmap.
@MainActor
@Observable
final class MemoryGraphImageStore {
    private(set) var image: NSImage?
    private(set) var loading = false
    private(set) var error: String?
    @ObservationIgnored private var query: MemoryGraphQuery?
    @ObservationIgnored private var generation = 0
    @ObservationIgnored private var request: Task<Void, Never>?

    func load(api: AdminAPI, query: MemoryGraphQuery, force: Bool = false) {
        load(query: query, force: force) { try await api.memoryGraphImage($0) }
    }

    func load(query next: MemoryGraphQuery, force: Bool = false,
              fetch: @escaping @Sendable (MemoryGraphQuery) async throws -> Data) {
        guard force || query != next else { return }
        cancel()
        query = next; image = nil; error = nil; loading = true
        let current = generation
        request = Task { [weak self] in
            do {
                let data = try await fetch(next)
                guard !Task.isCancelled, let self, self.generation == current else { return }
                guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                      let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
                      let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
                      let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
                      width.intValue > 0, height.intValue > 0,
                      width.intValue <= 3000, height.intValue <= 3000,
                      let bitmap = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                    throw MemoryGraphError.unavailable("The graph image could not be displayed.")
                }
                self.image = NSImage(cgImage: bitmap, size: .zero)
                self.loading = false; self.request = nil
            } catch {
                guard !Task.isCancelled, let self, self.generation == current else { return }
                self.error = error is JarvisError ? TabStateMapper.fromError(error).0 : error.localizedDescription
                self.loading = false; self.request = nil
            }
        }
    }

    func cancel() {
        if loading { error = "Image request cancelled. Choose Reload image to try again." }
        generation += 1; request?.cancel(); request = nil; loading = false
    }
}
