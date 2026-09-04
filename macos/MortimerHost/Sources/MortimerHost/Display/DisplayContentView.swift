import SwiftUI
import JarvisKit

/// APP plan §3 P14 — the ONE shared renderer for display payloads
/// (DisplayContent.tsx's native form), used by the Output tab, the
/// console overlay, and the display window. Renders markdown / images
/// (with radar basemap stacked UNDER, W6) / links / handoff commands /
/// clipboard content. Clipboard `content` is display-only, never
/// persisted (P9 / C3 — the stores have no disk backing at all).
struct DisplayContentView: View {
    let payload: DisplayPayload

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if let body = payload.body, !body.isEmpty {
                    Text(markdown: body)
                        .textSelection(.enabled)
                }

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
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// W6: radar tiles are transparent precipitation overlays — the
    /// keyless basemap at the same z/x/y stacks UNDER them.
    private func imagesStack(images: [String], basemaps: [String]?) -> some View {
        ForEach(Array(images.enumerated()), id: \.offset) { index, urlString in
            ZStack {
                if let basemaps, index < basemaps.count, let base = URL(string: basemaps[index]) {
                    AsyncImage(url: base) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                }
                if let url = URL(string: urlString) {
                    AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: {
                        ProgressView()
                    }
                }
            }
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    /// H3 — commands the USER runs themselves; H6.1 — the return-path
    /// footer renders from the expect_output FLAG, not model prose.
    private func commandsBlock(_ commands: [String], note: String?, expectOutput: Bool) -> some View {
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
