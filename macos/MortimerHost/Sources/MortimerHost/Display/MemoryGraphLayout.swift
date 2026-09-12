import Foundation
import JarvisKit

enum MemoryGraphLayout {
    /// Stable, bounded layout. Existing points are fixed during expansion;
    /// new points start beside their known neighbors. No continuous simulation.
    static func positions(nodes: [MemoryGraphNode], edges: [MemoryGraphEdge],
                          preserving old: [String: CGPoint] = [:]) throws -> [String: CGPoint] {
        let ids = nodes.map(\.id).sorted()
        let index = Dictionary(uniqueKeysWithValues: ids.enumerated().map { ($1, $0) })
        var neighbors = Array(repeating: [Int](), count: ids.count)
        for edge in edges {
            if let a = index[edge.from], let b = index[edge.to], a != b {
                neighbors[a].append(b); neighbors[b].append(a)
            }
        }
        for i in neighbors.indices { neighbors[i].sort() }
        var components: [[Int]] = [], visited: Set<Int> = []
        for seed in ids.indices where !visited.contains(seed) {
            var component = [seed], cursor = 0
            visited.insert(seed)
            while cursor < component.count {
                let current = component[cursor]; cursor += 1
                for next in neighbors[current] where visited.insert(next).inserted { component.append(next) }
            }
            components.append(component.sorted())
        }
        var initial: [Int: CGPoint] = [:]
        let spacing = 60 * sqrt(Double(components.map(\.count).max() ?? 1))
        for (componentIndex, component) in components.enumerated() {
            let angle = Double(componentIndex) * 2.399963229728653
            let distance = components.count > 1 ? spacing * sqrt(Double(componentIndex)) : 0
            let center = CGPoint(x: cos(angle) * distance, y: sin(angle) * distance)
            for (localIndex, index) in component.enumerated() {
                let localAngle = Double(localIndex) * 2.399963229728653
                let radius = 24 * sqrt(Double(localIndex + 1))
                initial[index] = CGPoint(x: center.x + cos(localAngle) * radius, y: center.y + sin(localAngle) * radius)
            }
        }
        var points = ids.enumerated().map { i, id -> CGPoint in
            if let point = old[id], point.x.isFinite, point.y.isFinite { return point }
            return initial[i] ?? .zero
        }
        let fixed = ids.map { old[$0] != nil }
        for i in ids.indices where !fixed[i] {
            let anchors = neighbors[i].filter { fixed[$0] }
            if !anchors.isEmpty {
                let angle = Double(i) * 2.399963229728653
                points[i] = CGPoint(x: anchors.reduce(0) { $0 + points[$1].x } / Double(anchors.count) + cos(angle) * 45,
                                    y: anchors.reduce(0) { $0 + points[$1].y } / Double(anchors.count) + sin(angle) * 45)
            }
        }
        for step in 0..<60 {
            try Task.checkCancellation()
            var next = points
            let limit = 12 * (1 - Double(step) / 65)
            for i in ids.indices where !fixed[i] {
                var fx = -points[i].x * 0.003, fy = -points[i].y * 0.003
                for j in ids.indices where i != j {
                    let dx = points[i].x - points[j].x, dy = points[i].y - points[j].y
                    let square = max(4, dx * dx + dy * dy)
                    let force = 800 / square
                    let distance = sqrt(square)
                    fx += dx / distance * force; fy += dy / distance * force
                }
                for j in neighbors[i] {
                    let dx = points[j].x - points[i].x, dy = points[j].y - points[i].y
                    let distance = max(1, hypot(dx, dy))
                    let force = (distance - 65) * 0.015
                    fx += dx / distance * force; fy += dy / distance * force
                }
                let magnitude = max(1, hypot(fx, fy) / limit)
                next[i] = CGPoint(x: points[i].x + fx / magnitude, y: points[i].y + fy / magnitude)
            }
            points = next
        }
        return Dictionary(uniqueKeysWithValues: zip(ids, points))
    }

    /// Existing backend traversal is undirected; edge direction is retained
    /// separately for rendering and inspection. Only loaded/visible data counts.
    static func path(from start: String, to end: String, nodes: Set<String>,
                     edges: [MemoryGraphEdge]) -> [String]? {
        guard nodes.contains(start), nodes.contains(end) else { return nil }
        var adjacency: [String: Set<String>] = [:]
        for edge in edges where nodes.contains(edge.from) && nodes.contains(edge.to) {
            adjacency[edge.from, default: []].insert(edge.to)
            adjacency[edge.to, default: []].insert(edge.from)
        }
        var queue = [start], seen: Set<String> = [start], previous: [String: String] = [:], cursor = 0
        while cursor < queue.count {
            let current = queue[cursor]; cursor += 1
            if current == end {
                var route = [end]
                while let p = previous[route.last!] { route.append(p) }
                return route.reversed()
            }
            for neighbor in (adjacency[current] ?? []).sorted() where seen.insert(neighbor).inserted {
                previous[neighbor] = current; queue.append(neighbor)
            }
        }
        return nil
    }
}

struct GraphCamera: Codable, Equatable {
    var scale = 1.0
    var offset = CGPoint.zero

    func screenPoint(_ point: CGPoint, size: CGSize) -> CGPoint {
        CGPoint(x: point.x * scale + offset.x + size.width / 2,
                y: point.y * scale + offset.y + size.height / 2)
    }

    func worldPoint(_ point: CGPoint, size: CGSize) -> CGPoint {
        CGPoint(x: (point.x - offset.x - size.width / 2) / scale,
                y: (point.y - offset.y - size.height / 2) / scale)
    }

    mutating func zoom(_ factor: Double) { scale = min(5, max(0.15, scale * factor)) }

    mutating func fit(_ points: [CGPoint], size: CGSize) {
        guard !points.isEmpty, size.width > 80, size.height > 80 else { return }
        let minX = points.map(\.x).min()!, maxX = points.map(\.x).max()!
        let minY = points.map(\.y).min()!, maxY = points.map(\.y).max()!
        scale = min(3, max(0.15, min((size.width - 80) / max(80, maxX - minX),
                                    (size.height - 80) / max(80, maxY - minY))))
        offset = CGPoint(x: -(minX + maxX) / 2 * scale, y: -(minY + maxY) / 2 * scale)
    }
}
