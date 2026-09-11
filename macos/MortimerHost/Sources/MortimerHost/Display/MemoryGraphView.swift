import SwiftUI
import JarvisKit

struct MemoryGraphView: View {
    @Bindable var store: MemoryGraphStore
    let api: AdminAPI
    @State private var serverFocus = ""
    @State private var viewport = CGSize.zero
    @State private var showBrowser = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack { navigation; presentationControls }
                VStack(alignment: .leading) { navigation; presentationControls }
            }
            HStack {
                TextField("Focus in memory (key or topic)", text: $serverFocus)
                    .onSubmit { focusServer() }
                Button("Focus") { focusServer() }
                Picker("Depth", selection: Binding(get: { store.metadata.query.depth }, set: { depth in
                    var query = store.metadata.query; query.depth = depth
                    store.load(api: api, query: query, remember: true)
                })) { ForEach(1...4, id: \.self) { Text("\($0)").tag($0) } }
                .frame(width: 95)
            }
            if store.loading {
                HStack { ProgressView().controlSize(.small); Text("Loading graph… Previous view retained.").font(.caption)
                    Button("Cancel") { store.cancel() }
                }
            }
            if let error = store.error {
                HStack(alignment: .top) {
                    Text(error).foregroundStyle(AppTheme.attn).textSelection(.enabled)
                    Button("Retry") { store.load(api: api) }
                }
            }
            if let graph = store.graph {
                Text("\(store.visibleNodes.count) visible of \(graph.nodes.count) loaded nodes · \(store.visibleEdges.count) visible relationships")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                if graph.truncated {
                    Text("Partial graph · \(graph.truncatedReason)").font(.caption).foregroundStyle(AppTheme.attn)
                }
            }
            if store.pathStart != nil {
                HStack {
                    if let path = store.tracedPath {
                        Text("Path: \(path.count - 1) connections in this loaded view").font(.caption)
                    } else if store.pathEnd != nil {
                        Text("No path in this loaded view with the current filters.").font(.caption)
                    } else { Text("Select a second node, then choose Trace to selected.").font(.caption) }
                    Button("Clear path") { store.clearPath() }
                }
            }
            GeometryReader { geometry in
                HStack(spacing: 12) {
                    if geometry.size.width >= 1000 { nodeBrowser.frame(width: 220) }
                    graphSurface
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    if geometry.size.width >= 1000 && store.showsInspector && (store.selectedNode != nil || store.selectedEdge != nil) {
                        inspector.frame(width: 280)
                    }
                }
                .sheet(isPresented: Binding(get: { store.showsInspector && geometry.size.width < 1000 && (store.selectedNode != nil || store.selectedEdge != nil) },
                                           set: { store.showsInspector = $0 })) {
                    VStack { HStack { Text("Graph details").font(.headline); Spacer(); Button("Done") { store.showsInspector = false } }; inspector }
                        .padding(20).frame(minWidth: 340, idealWidth: 460, minHeight: 400)
                }
            }
        }
        .sheet(isPresented: $showBrowser) {
            VStack { HStack { Text("Browse loaded graph").font(.headline); Spacer(); Button("Done") { showBrowser = false } }; nodeBrowser }
                .padding(20).frame(minWidth: 350, idealWidth: 500, minHeight: 450)
        }
        .task { store.loadIfNeeded(api: api) }
        .onDisappear { store.saveView() }
    }

    private var navigation: some View {
        HStack {
            Button("Back") { store.back() }.disabled(!store.canGoBack)
            Button("Refresh") { store.load(api: api) }.disabled(store.loading)
            Button("Browse / filter") { showBrowser = true }
            Spacer(minLength: 0)
        }
    }

    private var presentationControls: some View {
        HStack {
            Button("−") { var camera = store.metadata.camera; camera.zoom(0.8); store.setCamera(camera) }.accessibilityLabel("Zoom out")
            Button("+") { var camera = store.metadata.camera; camera.zoom(1.25); store.setCamera(camera) }.accessibilityLabel("Zoom in")
            Button("Fit") { store.fit(size: viewport) }
            Button("Reset layout") { store.resetLayout() }
            Toggle("Image fallback", isOn: $store.usesImageFallback).toggleStyle(.button)
        }
    }

    @ViewBuilder
    private var graphSurface: some View {
        if store.usesImageFallback {
            VStack {
                Text("Image fallback · pan, node selection and inspection are unavailable in this view.")
                    .font(.caption).foregroundStyle(AppTheme.attn)
                Text("Server image for the current focus and depth; local filters and node placement do not apply.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                if store.imageFallback.loading { ProgressView("Loading graph image…") }
                if let error = store.imageFallback.error {
                    Text(error).foregroundStyle(AppTheme.attn).textSelection(.enabled)
                }
                if let image = store.imageFallback.image {
                    Image(nsImage: image).resizable().scaledToFit()
                        .accessibilityLabel("Memory graph image. Use the interactive view for accessible node details.")
                }
                Button("Reload image") { store.imageFallback.load(api: api, query: store.metadata.query, force: true) }
            }
            .onAppear { store.imageFallback.load(api: api, query: store.metadata.query) }
            .onChange(of: store.metadata.query) { _, query in
                store.imageFallback.load(api: api, query: query)
            }
        } else if store.graph?.nodes.isEmpty == true {
            ContentUnavailableView("No memories in this view", systemImage: "point.3.connected.trianglepath.dotted",
                                   description: Text("Change the focus or return to the previous view."))
        } else if store.graph != nil {
            VStack(spacing: 6) {
                if !store.metadata.collapsedTypes.isEmpty {
                    ScrollView(.horizontal) {
                        HStack {
                            ForEach(store.metadata.collapsedTypes.sorted(), id: \.self) { type in
                                let count = store.filteredNodes.filter { $0.type == type }.count
                                Button("Expand \(type) (\(count) loaded)") { store.toggleGroup(type) }
                            }
                        }
                    }
                }
                MemoryGraphCanvas(store: store)
                    .onGeometryChange(for: CGSize.self) { $0.size } action: { size in
                        viewport = size
                        if store.needsFit { store.fit(size: size) }
                    }
                    .onChange(of: store.metadata.positions) { _, _ in
                        if store.needsFit { store.fit(size: viewport) }
                    }
            }
        } else {
            ContentUnavailableView("Memory graph", systemImage: "point.3.connected.trianglepath.dotted",
                                   description: Text(store.loading ? "Loading your graph…" : "Use Retry or Refresh to load the graph."))
        }
    }

    private var nodeBrowser: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("Search this view", text: $store.search)
            Text("Searches loaded node names and IDs. Use Focus for broader memory exploration.")
                .font(.caption).foregroundStyle(AppTheme.textDim)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Node types / display groups").font(.headline)
                    ForEach(store.nodeTypes, id: \.self) { type in
                        HStack {
                            Circle().fill(graphColor(store.graph?.legend.nodeTypes[type])).frame(width: 9, height: 9)
                            Toggle(type, isOn: Binding(get: { !store.metadata.hiddenNodeTypes.contains(type) }, set: { store.setNodeType(type, visible: $0) }))
                            Button(store.metadata.collapsedTypes.contains(type) ? "Expand" : "Group") { store.toggleGroup(type) }
                        }
                    }
                    Text("Relationship types").font(.headline)
                    ForEach(store.edgeTypes, id: \.self) { type in
                        Toggle("\(type) · \(store.graph?.legend.edgeTypes[type] ?? "solid")",
                               isOn: Binding(get: { !store.metadata.hiddenEdgeTypes.contains(type) }, set: { store.setEdgeType(type, visible: $0) }))
                    }
                    Divider()
                    Text("\(store.matchingNodes.count) matching loaded nodes").font(.caption)
                    ForEach(store.matchingNodes) { node in
                        Button {
                            store.select(node.id); store.centerSelection(); showBrowser = false
                        } label: {
                            VStack(alignment: .leading) { Text(node.label); Text(node.id).font(.caption).foregroundStyle(AppTheme.textDim) }
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .accessibilityLabel("\(node.label), \(node.type), \(node.id)")
                        .accessibilityAddTraits(store.metadata.selectedID == node.id ? [.isSelected] : [])
                    }
                }.textSelection(.enabled)
            }
        }
    }

    private var inspector: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let edge = store.selectedEdge {
                    Text(edge.type).font(.headline)
                    Text("From: \(edge.from)\nTo: \(edge.to)")
                    Text("Relationship supplied by the memory graph. Path search traverses it in either direction.").font(.caption)
                    attributes(edge.attrs)
                } else if let node = store.selectedNode {
                    Text(node.label).font(.headline)
                    Text(node.id).font(.caption)
                    Text("Type: \(node.type)").font(.caption)
                    if store.metadata.hiddenNodeTypes.contains(node.type) || store.metadata.collapsedTypes.contains(node.type) {
                        Text("Selected node is hidden by the current display filters.").foregroundStyle(AppTheme.attn)
                    }
                    Button("Focus / expand neighbors") {
                        var query = store.metadata.query; query.focus = node.id
                        store.load(api: api, query: query, remember: true)
                    }
                    HStack {
                        Button("Start path") { store.traceFromSelection() }
                        Button("Trace to selected") { store.traceToSelection() }.disabled(store.pathStart == nil)
                    }
                    attributes(node.attrs)
                    if node.attrs["provenance"] == nil || node.attrs["provenance"] == .null {
                        Text("Provenance was not supplied for this node.").font(.caption)
                    }
                    if let detail = store.fullDetail { Text(detail) }
                    else {
                        Text("Graph labels and content previews may be abbreviated.").font(.caption)
                        if let error = store.detailError { Text(error).foregroundStyle(AppTheme.attn) }
                        Button(store.detailError == nil ? "Read full detail" : "Retry full detail") {
                            store.loadFullDetail(api: api)
                        }.disabled(store.detailLoading)
                    }
                    if store.detailLoading { ProgressView() }
                    Divider()
                    Text("Loaded connections").font(.headline)
                    ForEach(Array((store.graph?.edges ?? []).filter { $0.from == node.id || $0.to == node.id }.enumerated()), id: \.offset) { _, edge in
                        Button("\(edge.type): \(edge.from) → \(edge.to)") { store.select(edge: edge) }
                    }
                } else {
                    Text("Select a node or relationship to inspect its supplied details.")
                }
            }.frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
        }
    }

    private func attributes(_ attrs: [String: JSONValue]) -> some View {
        ForEach(attrs.keys.sorted(), id: \.self) { key in
            VStack(alignment: .leading, spacing: 3) {
                Text(key).font(.caption).foregroundStyle(AppTheme.textDim)
                Text(graphAttributeText(attrs[key]!))
            }
        }
    }

    private func focusServer() {
        var query = store.metadata.query; query.focus = serverFocus.trimmingCharacters(in: .whitespacesAndNewlines)
        store.load(api: api, query: query, remember: true)
    }
}

func graphColor(_ hex: String?) -> Color {
    guard let hex, hex.count == 7, hex.first == "#", let value = UInt32(hex.dropFirst(), radix: 16) else { return .gray }
    return Color(red: Double((value >> 16) & 255) / 255, green: Double((value >> 8) & 255) / 255, blue: Double(value & 255) / 255)
}

func graphAttributeText(_ value: JSONValue) -> String {
    switch value {
    case .null: return "Not supplied"
    case .string(let text): return text
    case .bool(let value): return value ? "Yes" : "No"
    case .number(let value): return String(value)
    default:
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
        return (try? encoder.encode(value)).flatMap { String(data: $0, encoding: .utf8) } ?? "Unavailable"
    }
}
