import SwiftUI
import Charts
import JarvisKit

/// APP plan §3 P14 — the ONE shared renderer for display payloads
/// (DisplayContent.tsx's native form), used by the Output tab, the
/// console overlay, and the display window. Renders markdown / images
/// (with radar basemap stacked UNDER, W6) / links / handoff commands /
/// clipboard content. Clipboard `content` is display-only, never
/// persisted (P9 / C3 — the stores have no disk backing at all).
struct DisplayContentView: View {
    let payload: DisplayPayload
    /// True while the containing panel is mid-resize (SingleDisplayPanel);
    /// a graph image keeps its current bitmap until the size settles.
    var isResizing: Bool = false
    var restoredScrollOffset: Double? = nil
    var onScrollOffset: ((Double) -> Void)? = nil
    @State private var scrollPosition = ScrollPosition(y: 0)
    @State private var restoredScroll = false
    /// The scroll viewport, in points — a graph image is requested from the
    /// sidecar at THIS size (× the screen's backing scale) rather than the
    /// server's fixed 1400×900 default, so labels stay crisp at any panel
    /// size (2026-09-05; the endpoint's `w`/`h` were never sent before).
    @State private var viewport: CGSize = .zero

    var body: some View {
        // WS-13 P3m: the mail brief is protected by design and renders as
        // literal text, so unlike weather it is shown even when protected.
        if let layout = payload.layout, !payload.isProtectedLocal {
            composedBody(layout)
        } else if payload.kind == "brief", let card = payload.brief {
            ScrollView {
                BriefCardView(card: card).padding(12)
            }
        // WS-15 PR 2: a weather card renders as ONE card (summary, hours,
        // week, map with radar); anything else keeps the standard layout.
        } else if payload.kind == "weather", let card = payload.weather, !payload.isProtectedLocal {
            ScrollView {
                WeatherCardView(card: card).padding(12)
            }
        } else {
            standardBody
        }
    }

    private var standardBody: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let body = payload.body, !body.isEmpty {
                    if payload.isProtectedLocal {
                        Text(verbatim: body)
                            .textSelection(.disabled)
                            .accessibilityLabel(body)
                    } else {
                        Text(markdown: body).textSelection(.enabled)
                    }
                }

                // A protected result is a local-only body. Ancillary payload
                // fields can launch network requests, browsers, or clipboard
                // writes (commands/content/links), so never render them on this
                // path even if a producer accidentally includes them.
                if !payload.isProtectedLocal {
                    if let images = payload.images, !images.isEmpty {
                        imagesStack(images: images, basemaps: payload.basemapImages)
                    }

                    if let links = payload.links, !links.isEmpty {
                        ForEach(Array(links.enumerated()), id: \.offset) { _, link in
                            if let url = URL(string: link.url) {
                                Link(link.label ?? link.url, destination: url)
                                    .foregroundStyle(AppTheme.accent)
                            }
                        }
                    }

                    if let commands = payload.commands, !commands.isEmpty {
                        commandsBlock(commands, note: payload.note, expectOutput: payload.expectOutput ?? false)
                    }

                    if let content = payload.content, !content.isEmpty {
                        clipboardBlock(content, chars: payload.chars, truncated: payload.truncated ?? false)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollPosition($scrollPosition)
        .onScrollGeometryChange(for: Double.self) { geometry in
            Double(geometry.contentOffset.y + geometry.contentInsets.top)
        } action: { _, offset in
            if restoredScroll { onScrollOffset?(offset) }
        }
        .onAppear {
            if let offset = restoredScrollOffset { scrollPosition.scrollTo(y: offset) }
            restoredScroll = true
        }
        .onGeometryChange(for: CGSize.self) { proxy in
            proxy.size
        } action: { size in
            viewport = size
        }
    }

    /// W6: radar tiles are transparent precipitation overlays — the
    /// keyless basemap at the same z/x/y stacks UNDER them. A sidecar
    /// graph image (GL11 `/api/graph/<name>/image.png`) takes the sized
    /// path instead: it is a server-side render, so the right size is
    /// re-drawn, not a bitmap scaled.
    func imagesStack(images: [String], basemaps: [String]?) -> some View {
        ForEach(Array(images.enumerated()), id: \.offset) { index, urlString in
            ZStack {
                if let basemaps, index < basemaps.count, let base = URL(string: basemaps[index]) {
                    AsyncImage(url: base) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                }
                if let url = URL(string: urlString) {
                    if GraphImageURL.isGraphImage(url) {
                        GraphImageView(baseURL: url, viewport: viewport, isResizing: isResizing)
                    } else {
                        AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: {
                            ProgressView()
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    /// H3 — commands the USER runs themselves; H6.1 — the return-path
    /// footer renders from the expect_output FLAG, not model prose.
    func commandsBlock(_ commands: [String], note: String?, expectOutput: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(commands.enumerated()), id: \.offset) { _, command in
                HStack {
                    Text(command)
                        .font(.system(.callout, design: .monospaced))
                        .textSelection(.enabled)
                    Spacer()
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(command, forType: .string)
                    } label: {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(AppTheme.textDim)
                    .accessibilityLabel("Copy command")
                }
                .padding(8)
                .background(AppTheme.panel.opacity(0.6), in: RoundedRectangle(cornerRadius: 6))
            }
            if let note, !note.isEmpty {
                Text(note).font(.caption).foregroundStyle(AppTheme.textDim)
            }
            if expectOutput {
                Text("Copy the output and say \"read my clipboard\".")
                    .font(.caption)
                    .foregroundStyle(AppTheme.amber)
            }
        }
    }

    /// H4 — clipboard text read back from the user: ephemeral by
    /// construction; rendered, never stored.
    private func clipboardBlock(_ content: String, chars: Int?, truncated: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(content)
                .font(.system(.callout, design: .monospaced))
                .textSelection(.enabled)
                .padding(8)
                .background(AppTheme.panel.opacity(0.6), in: RoundedRectangle(cornerRadius: 6))
            HStack {
                if let chars { Text("\(chars) chars") }
                if truncated { Text("truncated").foregroundStyle(AppTheme.amber) }
            }
            .font(.caption2)
            .foregroundStyle(AppTheme.textDim)
        }
    }
}

extension Text {
    /// Multi-line markdown init — Text(markdown:) with full-string
    /// parsing so headings/lists at least render as styled inline runs.
    init(markdown: String) {
        if let attributed = try? AttributedString(
            markdown: markdown,
            options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            self.init(attributed)
        } else {
            self.init(verbatim: markdown)
        }
    }
}

// WS-35 C4: validated blocks retain server order; the legacy fields remain the
// fallback/export contract. No new action transport or carousel lives here.
extension DisplayContentView {
    func composedBody(_ layout: ComposedAnswerLayout) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if !layout.blocks.contains(where: { $0.type == .header }) {
                    Text(layout.title).font(.headline)
                    if !layout.summary.isEmpty { Text(layout.summary) }
                }
                ForEach(layout.blocks, id: \.id) { block in
                    composedBlock(block)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollPosition($scrollPosition)
        .onScrollGeometryChange(for: Double.self) { geometry in
            Double(geometry.contentOffset.y + geometry.contentInsets.top)
        } action: { _, offset in
            if restoredScroll { onScrollOffset?(offset) }
        }
        .onAppear {
            if let offset = restoredScrollOffset { scrollPosition.scrollTo(y: offset) }
            restoredScroll = true
        }
        .onGeometryChange(for: CGSize.self) { $0.size } action: { viewport = $0 }
    }

    @ViewBuilder private func composedBlock(_ block: ComposedAnswerBlock) -> some View {
        let data = block.data
        switch block.type {
        case .header:
            VStack(alignment: .leading, spacing: 4) {
                Text(data["title"]?.stringValue ?? "").font(.headline)
                if let summary = data["summary"]?.stringValue { Text(summary) }
                ForEach(Array((data["agents"]?.arrayValue ?? []).enumerated()), id: \.offset) { _, agent in
                    Text(agent["name"]?.stringValue ?? "").font(.caption)
                }
            }
        case .text:
            if data["format"]?.stringValue == "plain" {
                Text(verbatim: data["text"]?.stringValue ?? "").textSelection(.enabled)
            } else {
                Text(markdown: data["text"]?.stringValue ?? "").textSelection(.enabled)
            }
        case .stats, .list:
            VStack(alignment: .leading, spacing: 8) {
                if let title = data["title"]?.stringValue { Text(title).font(.headline) }
                ForEach(Array((data["items"]?.arrayValue ?? []).enumerated()), id: \.offset) { _, item in
                    VStack(alignment: .leading, spacing: 3) {
                        if let value = item["value"]?.stringValue { Text(value).font(.title2) }
                        Text(item["label"]?.stringValue ?? item["title"]?.stringValue ?? "")
                        if let detail = item["detail"]?.stringValue { Text(detail).font(.caption) }
                        if let meta = item["meta"]?.stringValue { Text(meta).font(.caption2) }
                        if let tone = item["tone"]?.stringValue, tone != "neutral" {
                            Label(tone.capitalized, systemImage: tone == "error" ? "exclamationmark.triangle" : tone == "approval" ? "hand.raised" : "checkmark.circle")
                                .font(.caption)
                        }
                    }
                }
                if let more = data["more_count"]?.doubleValue, more > 0 {
                    Text("\(Int(more)) more").font(.caption)
                }
            }
        case .chart:
            composedChart(data)
        case .media:
            VStack(alignment: .leading) {
                imagesStack(images: strings(data["images"]), basemaps: strings(data["basemap_images"]))
                    .accessibilityLabel(data["a11y"]?.stringValue ?? "")
                if let caption = data["caption"]?.stringValue { Text(caption).font(.caption) }
            }
        case .sources:
            VStack(alignment: .leading) {
                ForEach(Array((data["items"]?.arrayValue ?? []).enumerated()), id: \.offset) { _, item in
                    if let raw = item["url"]?.stringValue, let url = URL(string: raw) {
                        Link(item["label"]?.stringValue ?? raw, destination: url)
                    } else { Text(item["label"]?.stringValue ?? "") }
                }
            }
        case .weather:
            if let card = block.weather { WeatherCardView(card: card) }
        case .brief:
            if let card = block.brief { BriefCardView(card: card) }
        case .roadmap:
            if let snapshot = block.roadmap {
                // Read-only typed snapshot. Interactive filtering still belongs
                // to the legacy RoadmapView / console-action contract.
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(snapshot.issues, id: \.self) { Text($0).font(.caption) }
                    ForEach(snapshot.cards) { card in
                        DisclosureGroup(card.title) {
                            RoadmapCardDetails(card: card)
                        }
                    }
                }
            }
        case .commands:
            commandsBlock(strings(data["commands"]), note: data["note"]?.stringValue,
                          expectOutput: data["expect_output"]?.boolValue ?? false)
        case .graph:
            VStack(alignment: .leading) {
                if let summary = data["summary"]?.stringValue { Text(summary) }
                if let raw = data["image_url"]?.stringValue {
                    imagesStack(images: [raw], basemaps: nil)
                }
            }
        }
    }

    private func strings(_ value: JSONValue?) -> [String] {
        (value?.arrayValue ?? []).compactMap(\.stringValue)
    }

    private func composedChart(_ data: JSONValue) -> some View {
        let points = data["points"]?.arrayValue ?? []
        return VStack(alignment: .leading, spacing: 5) {
            if let title = data["title"]?.stringValue { Text(title).font(.headline) }
            Chart(Array(points.enumerated()), id: \.offset) { _, point in
                BarMark(x: .value(data["unit"]?.stringValue ?? "Value", point["value"]?.doubleValue ?? 0),
                        y: .value("Label", point["label"]?.stringValue ?? ""))
                    .foregroundStyle(AppTheme.accent)
            }.frame(height: max(100, CGFloat(points.count) * 24))
        }.accessibilityElement(children: .ignore)
            .accessibilityLabel(data["a11y"]?.stringValue ?? "")
    }
}
