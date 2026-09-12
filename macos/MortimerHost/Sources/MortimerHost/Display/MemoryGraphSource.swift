import Foundation
import JarvisKit

enum MemoryGraphSource {
    static func imageURL(_ payload: DisplayPayload) -> URL? {
        (payload.images ?? []).compactMap(URL.init(string:)).first {
            $0.path == "/api/graph/memory/image.png" || $0.path == "/api/graph/memory/image.svg"
        }
    }

    /// The image supplies query metadata only. JSON always goes to the
    /// configured authenticated AdminAPI, never to an image's arbitrary host.
    static func query(_ url: URL) -> MemoryGraphQuery {
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }
        return MemoryGraphQuery(focus: value("focus") ?? "", depth: Int(value("depth") ?? ""),
                                edgeTypes: (value("edge_types") ?? "").split(separator: ",").map(String.init),
                                since: value("since"))
    }
}
