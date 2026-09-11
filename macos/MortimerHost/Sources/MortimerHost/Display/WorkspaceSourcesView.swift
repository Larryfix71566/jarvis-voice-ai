import SwiftUI
import JarvisKit

struct WorkspaceSourcesView: View {
    let result: WorkspaceResult
    @Bindable var presentation: WorkspaceResultPresentation
    @State private var scroll = ScrollPosition(y: 0)
    @State private var restored = false
    private var sources: [DisplayLink] { result.payload.links ?? [] }

    var body: some View {
        GeometryReader { geometry in
            HStack(alignment: .top, spacing: 12) {
                sourceList
                if geometry.size.width >= 820 && presentation.showsInspector {
                    Divider()
                    inspector.frame(width: 300)
                }
            }
            .sheet(isPresented: Binding(get: { geometry.size.width < 820 && presentation.showsInspector },
                                       set: { presentation.showsInspector = $0 })) {
                inspector.padding(20).frame(minWidth: 320, idealWidth: 420, minHeight: 300)
            }
        }
    }

    private var sourceList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Links supplied with this result. Opening a source is your choice.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                if sources.isEmpty {
                    ContentUnavailableView("No source links supplied", systemImage: "link",
                        description: Text("The original result remains available in Summary."))
                }
                ForEach(Array(sources.enumerated()), id: \.offset) { index, source in
                    Button {
                        presentation.selectedSource = index
                        presentation.showsInspector = true
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(source.label ?? source.url).font(.headline)
                            Text(source.url).font(.caption).foregroundStyle(AppTheme.textDim)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(10)
                            .background(presentation.selectedSource == index ? AppTheme.accent.opacity(0.15) : AppTheme.panel.opacity(0.5),
                                        in: RoundedRectangle(cornerRadius: 8))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Inspect source \(index + 1): \(source.label ?? source.url)")
                    .accessibilityAddTraits(presentation.selectedSource == index ? [.isSelected] : [])
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollPosition($scroll)
        .onScrollGeometryChange(for: Double.self) { Double($0.contentOffset.y + $0.contentInsets.top) } action: { _, offset in
            if restored && offset.isFinite { presentation.sourceScrollOffset = max(0, offset) }
        }
        .onAppear { scroll.scrollTo(y: presentation.sourceScrollOffset); restored = true }
    }

    private var inspector: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Source details").font(.headline)
                Spacer()
                Button("Done") { presentation.showsInspector = false }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
            if let index = presentation.selectedSource, sources.indices.contains(index) {
                let source = sources[index]
                Text(source.label ?? "Untitled source").font(.title3).textSelection(.enabled)
                Text(source.url).textSelection(.enabled)
                Text("Supplied with \(result.payload.title ?? "this result"). Publication date and excerpt were not supplied.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                if let url = WorkspaceResultExport.sourceURL(source.url) {
                    Link("Open source", destination: url)
                } else {
                    Text("This address cannot be opened as a web source. You can select and copy it.")
                        .font(.caption).foregroundStyle(AppTheme.attn)
                }
            }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}
