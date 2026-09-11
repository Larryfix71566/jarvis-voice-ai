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
                for edge in edges {
                    guard let a = positions[edge.from], let b = positions[edge.to] else { continue }
                    let start = camera.screenPoint(a, size: size), end = camera.screenPoint(b, size: size)
                    let onPath = zip(route, route.dropFirst()).contains { ($0 == edge.from && $1 == edge.to) || ($0 == edge.to && $1 == edge.from) }
                    let highlighted = onPath || edge == store.selectedEdge
                    let related = selected == nil || edge.from == selected || edge.to == selected
                    var line = Path(); line.move(to: start); line.addLine(to: end)
                    let style = store.graph?.legend.edgeTypes[edge.type]
                    let dash: [CGFloat] = style == "dashed" ? [6, 4] : style == "dotted" ? [2, 4] : []
                    let color = highlighted ? AppTheme.accent : Color.gray.opacity(related ? 0.5 : 0.12)
                    context.stroke(line, with: .color(color), style: StrokeStyle(lineWidth: highlighted ? 2 : 0.8, dash: dash))
                    // These directions are specified by memory_graph.py;
                    // unknown relationship kinds get no invented arrow meaning.
                    if ["child_of", "became", "stated_in", "restated"].contains(edge.type) {
                        let angle = atan2(end.y - start.y, end.x - start.x)
                        let tip = CGPoint(x: end.x - cos(angle) * 9, y: end.y - sin(angle) * 9)
                        var arrow = Path()
                        arrow.move(to: CGPoint(x: tip.x - cos(angle - 0.45) * 7, y: tip.y - sin(angle - 0.45) * 7))
                        arrow.addLine(to: tip)
                        arrow.addLine(to: CGPoint(x: tip.x - cos(angle + 0.45) * 7, y: tip.y - sin(angle + 0.45) * 7))
                        context.stroke(arrow, with: .color(color), lineWidth: highlighted ? 2 : 1)
                    }
                    if highlighted {
                        context.draw(Text(edge.type).font(.caption2).foregroundColor(AppTheme.text),
                                     at: CGPoint(x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 - 8))
                    }
                }
                for node in nodes {
                    guard let point = positions[node.id] else { continue }
                    let at = camera.screenPoint(point, size: size)
                    guard at.x > -100, at.x < size.width + 100, at.y > -50, at.y < size.height + 50 else { continue }
                    let highlighted = node.id == selected || pathNodes.contains(node.id)
                    let radius: CGFloat = node.type == "prefix" ? 8 : 5
                    let circle = Path(ellipseIn: CGRect(x: at.x - radius, y: at.y - radius, width: radius * 2, height: radius * 2))
                    let opacity = selected == nil || neighbors.contains(node.id) || highlighted ? 1.0 : 0.3
                    context.fill(circle, with: .color(graphColor(store.graph?.legend.nodeTypes[node.type]).opacity(opacity)))
                    if highlighted {
                        context.stroke(Path(ellipseIn: CGRect(x: at.x - radius - 4, y: at.y - radius - 4, width: radius * 2 + 8, height: radius * 2 + 8)),
                                       with: .color(AppTheme.accent), lineWidth: 2)
                    }
                }
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

    private func segmentDistance(_ point: CGPoint, _ a: CGPoint, _ b: CGPoint) -> Double {
        let dx = b.x - a.x, dy = b.y - a.y
        let length = dx * dx + dy * dy
        guard length > 0 else { return hypot(point.x - a.x, point.y - a.y) }
        let t = min(1, max(0, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length))
        return hypot(point.x - a.x - t * dx, point.y - a.y - t * dy)
    }
}
