import Foundation

/// Session-local in-flight sharing only. Completed images are not cached here.
/// Each view owns a waiter; the final departing waiter cancels network work.
actor GraphImageRequests {
    private struct Entry {
        let id: UUID
        let task: Task<Data, Error>
        var waiters: Set<UUID>
    }
    private var entries: [URL: Entry] = [:]

    func data(at url: URL, fetch: @escaping @Sendable () async throws -> Data) async throws -> Data {
        try Task.checkCancellation()
        let waiter = UUID()
        var entry = entries[url] ?? Entry(id: UUID(), task: Task { try await fetch() }, waiters: [])
        entry.waiters.insert(waiter)
        entries[url] = entry
        let id = entry.id
        let task = entry.task
        defer { release(url: url, id: id, waiter: waiter) }
        return try await withTaskCancellationHandler {
            let data = try await task.value
            try Task.checkCancellation()
            return data
        } onCancel: {
            Task { await self.release(url: url, id: id, waiter: waiter) }
        }
    }

    private func release(url: URL, id: UUID, waiter: UUID) {
        guard var entry = entries[url], entry.id == id else { return }
        entry.waiters.remove(waiter)
        if entry.waiters.isEmpty {
            entries.removeValue(forKey: url)
            entry.task.cancel()
        } else {
            entries[url] = entry
        }
    }
}
