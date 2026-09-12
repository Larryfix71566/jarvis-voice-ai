import SwiftUI
import JarvisKit

struct MemoryGraphCanvas: View {
    @Bindable var store: MemoryGraphStore
    @State private var dragCamera: GraphCamera?
    @State private var draggedNode: String?
    @State private var zoomStart: GraphCamera?

    var body: some View {
        GeometryReader { geometry in
            let nodes = store.visibleNodes
            let edges = store.visibleEdges
            let camera = store.metadata.camera
            let positions = store.metadata.positions
            let route = store.tracedPath ?? []
            let pathNodes = Set(route)
            let selected = store.metadata.selectedID
            let neighbors = Set(edges.filter { $0.from == selected || $0.to == selected }.flatMap { [$0.from, $0.to] })
            Canvas { context, size in
                // Closure C3.1 (gap G11): one stroke per (style, emphasis)
                // group and one fill per (colour, opacity) group instead of
                // one drawing call per edge/node, with every segment clipped
                // to the viewport before it is dashed. Same picture, bounded
                // per-frame cost on the 500-node / 2,000-edge fixture.
                let viewport = CGRect(origin: .zero, size: size).insetBy(dx: -12, dy: -12)
                var edgePaths: [EdgeStrokeKey: Path] = [:]
                var arrowPaths: [EdgeStrokeKey: Path] = [:]
                var edgeLabels: [(String, CGPoint)] = []
                let directional = store.directionalEdgeTypes
                let legendStyles = store.graph?.legend.edgeTypes ?? [:]
                var pathSteps: Set<String> = []
                for (from, to) in zip(route, route.dropFirst()) {
                    pathSteps.insert(from + "\u{0}" + to); pathSteps.insert(to + "\u{0}" + from)
                }
                for edge in edges {
                    guard let a = positions[edge.from], let b = positions[edge.to] else { continue }
                    let start = camera.screenPoint(a, size: size), end = camera.screenPoint(b, size: size)
                    guard let clipped = MemoryGraphCanvas.clip(start, end, to: viewport) else { continue }
                    let (from, to) = clipped
                    let onPath = !pathSteps.isEmpty && pathSteps.contains(edge.from + "\u{0}" + edge.to)
                    let highlighted = onPath || edge == store.selectedEdge
                    let related = selected == nil || edge.from == selected || edge.to == selected
                    let style = legendStyles[edge.type]
                    let key = EdgeStrokeKey(dash: style == "dashed" ? .dashed : style == "dotted" ? .dotted : .solid,
                                            emphasis: highlighted ? .highlighted : related ? .related : .unrelated)
                    edgePaths[key, default: Path()].move(to: from)
                    edgePaths[key, default: Path()].addLine(to: to)
                    // Directions come from the server's legend vocabulary (every
                    // memory-graph edge is built src → dst by memory_graph.py);
                    // an edge type the server does not declare gets no arrow.
                    if directional.contains(edge.type), viewport.contains(end) {
                        let angle = atan2(end.y - start.y, end.x - start.x)
                        let tip = CGPoint(x: end.x - cos(angle) * 9, y: end.y - sin(angle) * 9)
                        let solidKey = EdgeStrokeKey(dash: .solid, emphasis: key.emphasis)
                        arrowPaths[solidKey, default: Path()].move(to: CGPoint(x: tip.x - cos(angle - 0.45) * 7, y: tip.y - sin(angle - 0.45) * 7))
                        arrowPaths[solidKey, default: Path()].addLine(to: tip)
                        arrowPaths[solidKey, default: Path()].addLine(to: CGPoint(x: tip.x - cos(angle + 0.45) * 7, y: tip.y - sin(angle + 0.45) * 7))
                    }
                    if highlighted {
                        edgeLabels.append((edge.type, CGPoint(x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 - 8)))
                    }
                }
                // Unrelated first, highlighted last, so emphasis stays on top.
                for key in edgePaths.keys.sorted() {
                    guard let path = edgePaths[key] else { continue }
                    context.stroke(path, with: .color(key.color), style: StrokeStyle(lineWidth: key.emphasis == .highlighted ? 2 : 0.8, dash: key.dash.pattern))
                }
                for key in arrowPaths.keys.sorted() {
                    guard let path = arrowPaths[key] else { continue }
                    context.stroke(path, with: .color(key.color), lineWidth: key.emphasis == .highlighted ? 2 : 1)
                }
                for (type, at) in edgeLabels {
                    context.draw(Text(type).font(.caption2).foregroundColor(AppTheme.text), at: at)
                }
                var nodeFills: [NodeFillKey: Path] = [:]
                var rings = Path()
                for node in nodes {
                    guard let point = positions[node.id] else { continue }
                    let at = camera.screenPoint(point, size: size)
                    guard at.x > -100, at.x < size.width + 100, at.y > -50, at.y < size.height + 50 else { continue }
                    let highlighted = node.id == selected || pathNodes.contains(node.id)
                    let radius: CGFloat = node.type == "prefix" ? 8 : 5
                    let opacity = selected == nil || neighbors.contains(node.id) || highlighted ? 1.0 : 0.3
                    let key = NodeFillKey(hex: store.graph?.legend.nodeTypes[node.type], opacity: opacity)
                    nodeFills[key, default: Path()].addEllipse(in: CGRect(x: at.x - radius, y: at.y - radius, width: radius * 2, height: radius * 2))
                    if highlighted {
                        rings.addEllipse(in: CGRect(x: at.x - radius - 4, y: at.y - radius - 4, width: radius * 2 + 8, height: radius * 2 + 8))
                    }
                }
                for key in nodeFills.keys.sorted() {
                    guard let path = nodeFills[key] else { continue }
                    context.fill(path, with: .color(graphColor(key.hex).opacity(key.opacity)))
                }
                if !rings.isEmpty { context.stroke(rings, with: .color(AppTheme.accent), lineWidth: 2) }
                // Place labels only where their measured rectangles fit.
                // Selection/path labels have priority; omitted labels remain
                // searchable and available in the keyboard node browser.
                var occupied: [CGRect] = []
                let labelNodes = nodes.sorted {
                    let a = $0.id == selected || pathNodes.contains($0.id)
                    let b = $1.id == selected || pathNodes.contains($1.id)
                    return a == b ? $0.id < $1.id : a
                }
                for node in labelNodes {
                    let highlighted = node.id == selected || pathNodes.contains(node.id)
                    guard highlighted || nodes.count <= 50 || (camera.scale >= 1.6 && node.type == "prefix"),
                          let point = positions[node.id] else { continue }
                    let at = camera.screenPoint(point, size: size)
                    let text = context.resolve(Text(node.label).font(.caption2).foregroundColor(AppTheme.text))
                    let measured = text.measure(in: CGSize(width: 190, height: 44))
                    let width = measured.width + 8, height = measured.height + 4
                    let candidates = [
                        CGRect(x: at.x - width / 2, y: at.y + 12, width: width, height: height),
                        CGRect(x: at.x - width / 2, y: at.y - height - 12, width: width, height: height),
                        CGRect(x: at.x + 12, y: at.y - height / 2, width: width, height: height),
                        CGRect(x: at.x - width - 12, y: at.y - height / 2, width: width, height: height)
                    ]
                    let bounds = CGRect(origin: .zero, size: size).insetBy(dx: 4, dy: 4)
                    guard let rect = candidates.first(where: { candidate in
                        bounds.contains(candidate) && !occupied.contains { $0.intersects(candidate) }
                    }) else { continue }
                    occupied.append(rect.insetBy(dx: -3, dy: -2))
                    context.fill(Path(roundedRect: rect, cornerRadius: 3), with: .color(AppTheme.bg.opacity(0.88)))
                    context.draw(text, in: rect.insetBy(dx: 4, dy: 2))
                }
            }
            .background(AppTheme.bg)
            .contentShape(Rectangle())
            .gesture(SpatialTapGesture().onEnded { event in
                if let node = nearestNode(event.location, nodes: nodes, positions: positions, camera: camera, size: geometry.size) {
                    store.select(node.id)
                } else if let edge = edges.first(where: { edge in
                    guard let a = positions[edge.from], let b = positions[edge.to] else { return false }
                    return segmentDistance(event.location, camera.screenPoint(a, size: geometry.size), camera.screenPoint(b, size: geometry.size)) < 6
                }) { store.select(edge: edge) }
            })
            .simultaneousGesture(DragGesture(minimumDistance: 4).onChanged { value in
                if dragCamera == nil {
                    dragCamera = store.metadata.camera
                    draggedNode = nearestNode(value.startLocation, nodes: nodes, positions: positions, camera: camera, size: geometry.size)?.id
                }
                guard var start = dragCamera else { return }
                if let node = draggedNode {
                    store.moveNode(node, to: start.worldPoint(value.location, size: geometry.size), save: false)
                } else {
                    start.offset.x += value.translation.width; start.offset.y += value.translation.height
                    store.setCamera(start, save: false)
                }
            }.onEnded { _ in dragCamera = nil; draggedNode = nil; store.saveView() })
            .simultaneousGesture(MagnifyGesture().onChanged { value in
                if zoomStart == nil { zoomStart = store.metadata.camera }
                guard var camera = zoomStart else { return }
                camera.zoom(value.magnification)
                store.setCamera(camera, save: false)
            }.onEnded { _ in zoomStart = nil; store.saveView() })
            .accessibilityLabel("Memory graph canvas. Use Browse and filter for keyboard-accessible nodes and relationships.")
        }
    }

    private func nearestNode(_ point: CGPoint, nodes: [MemoryGraphNode], positions: [String: CGPoint],
                             camera: GraphCamera, size: CGSize) -> MemoryGraphNode? {
        nodes.compactMap { node -> (MemoryGraphNode, Double)? in
            guard let world = positions[node.id] else { return nil }
            let screen = camera.screenPoint(world, size: size)
            let distance = hypot(point.x - screen.x, point.y - screen.y)
            return distance <= 15 ? (node, Double(distance)) : nil
        }.min { $0.1 < $1.1 }?.0
    }

    enum EdgeDash: Int, Comparable { case solid, dashed, dotted
        static func < (a: EdgeDash, b: EdgeDash) -> Bool { a.rawValue < b.rawValue }
        var pattern: [CGFloat] { switch self { case .solid: return []; case .dashed: return [6, 4]; case .dotted: return [2, 4] } }
    }
    enum EdgeEmphasis: Int, Comparable { case unrelated, related, highlighted
        static func < (a: EdgeEmphasis, b: EdgeEmphasis) -> Bool { a.rawValue < b.rawValue }
    }
    struct EdgeStrokeKey: Hashable, Comparable {
        let dash: EdgeDash
        let emphasis: EdgeEmphasis
        static func < (a: EdgeStrokeKey, b: EdgeStrokeKey) -> Bool {
            a.emphasis == b.emphasis ? a.dash < b.dash : a.emphasis < b.emphasis
        }
        var color: Color {
            switch emphasis {
            case .highlighted: return AppTheme.accent
            case .related: return Color.gray.opacity(0.5)
            case .unrelated: return Color.gray.opacity(0.12)
            }
        }
    }
    struct NodeFillKey: Hashable, Comparable {
        let hex: String?
        let opacity: Double
        static func < (a: NodeFillKey, b: NodeFillKey) -> Bool {
            a.opacity == b.opacity ? (a.hex ?? "") < (b.hex ?? "") : a.opacity < b.opacity
        }
    }

    /// Liang–Barsky: the part of segment a→b inside `rect`, or nil when the
    /// segment misses it entirely. Dash patterns are then computed only over
    /// the visible length, which is what bounds the zoomed-in frame cost.
    static func clip(_ a: CGPoint, _ b: CGPoint, to rect: CGRect) -> (CGPoint, CGPoint)? {
        let dx = b.x - a.x, dy = b.y - a.y
        var t0 = 0.0, t1 = 1.0
        for (p, q) in [(-dx, a.x - rect.minX), (dx, rect.maxX - a.x), (-dy, a.y - rect.minY), (dy, rect.maxY - a.y)] {
            if p == 0 { if q < 0 { return nil } ; continue }
            let r = q / p
            if p < 0 { if r > t1 { return nil }; t0 = max(t0, r) }
            else { if r < t0 { return nil }; t1 = min(t1, r) }
        }
        return (CGPoint(x: a.x + dx * t0, y: a.y + dy * t0), CGPoint(x: a.x + dx * t1, y: a.y + dy * t1))
    }

    private func segmentDistance(_ point: CGPoint, _ a: CGPoint, _ b: CGPoint) -> Double {
        let dx = b.x - a.x, dy = b.y - a.y
        let length = dx * dx + dy * dy
        guard length > 0 else { return hypot(point.x - a.x, point.y - a.y) }
        let t = min(1, max(0, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length))
        return hypot(point.x - a.x - t * dx, point.y - a.y - t * dy)
    }
}
