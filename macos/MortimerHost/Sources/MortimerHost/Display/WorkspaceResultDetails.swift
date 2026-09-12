import Foundation
import Observation
import JarvisKit

enum WorkspaceResultMode: String, CaseIterable {
    case summary = "Summary", sources = "Sources", connections = "Connections"
}

@MainActor
@Observable
final class WorkspaceResultPresentation {
    var mode: WorkspaceResultMode
    var selectedSource: Int?
    var showsInspector = false
    var sourceScrollOffset = 0.0
    init(hasConnections: Bool) { mode = hasConnections ? .connections : .summary }
}

/// Formats supplied evidence only. Clipboard content is never part of an export.
enum WorkspaceResultExport {
    static func text(_ result: WorkspaceResult) -> String {
        let p = result.payload
        var parts = [p.title ?? "Mortimer result"]
        if let body = p.body, !body.isEmpty { parts.append(body) }
        if let links = p.links, !links.isEmpty {
            parts.append("Sources\n" + links.map { "\($0.label ?? $0.url)\n\($0.url)" }.joined(separator: "\n\n"))
        }
        if let images = p.images, !images.isEmpty { parts.append("Image references\n" + images.joined(separator: "\n")) }
        if let basemaps = p.basemapImages, !basemaps.isEmpty { parts.append("Basemap references\n" + basemaps.joined(separator: "\n")) }
        if let commands = p.commands, !commands.isEmpty {
            parts.append("Commands supplied for manual use\n" + commands.joined(separator: "\n"))
        }
        if let note = p.note, !note.isEmpty { parts.append(note) }
        if p.expectOutput == true { parts.append("The supplied command requests output to be returned.") }
        if p.truncated == true { parts.append("The supplied result is truncated.") }
        if p.content != nil { parts.append("Clipboard content omitted from this export.") }
        return parts.joined(separator: "\n\n") + "\n"
    }

    static func sourceURL(_ text: String) -> URL? {
        guard let url = URL(string: text), let scheme = url.scheme?.lowercased(),
              ["https", "http"].contains(scheme), let host = url.host, !host.isEmpty else { return nil }
        return url
    }
}
