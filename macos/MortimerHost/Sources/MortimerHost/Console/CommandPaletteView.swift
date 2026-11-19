import SwiftUI

/// Interface cleanup Phase 2: the Command-K menu. Everything the console no
/// longer keeps on screen is one keystroke and a few letters away. The command
/// list and the filter are pure so they can be tested without a view.
enum CommandPalette {
    enum Action: Equatable {
        case view(String)          // ConsoleAction.viewSet target
        case toggleInspect
        case openLog
        case openDisplay
        case connect
        case disconnect
        case toggleWakeWord
        case toggleSounds
        case toggleExpandVoice
    }

    struct Command: Identifiable, Equatable {
        let id: String
        let title: String
        let icon: String
        let keywords: [String]
        let action: Action
    }

    /// Fixed order: navigation first, then inspection, then connection and
    /// preferences. Wake word is offered only when the listener exists, and
    /// Connect only while not connected (the palette is not "the screen").
    static func commands(connected: Bool, connecting: Bool, wakeWordAvailable: Bool,
                         wakeWordOn: Bool, soundsOn: Bool, inspectOpen: Bool,
                         compactConversation: Bool) -> [Command] {
        var list: [Command] = [
            Command(id: "conversation", title: "Conversation", icon: "bubble.left.and.bubble.right",
                    keywords: ["chat", "talk", "thread"], action: .view("conversation")),
            Command(id: "results", title: "Results", icon: "doc.text.magnifyingglass",
                    keywords: ["answers", "recents", "display"], action: .view("results")),
            Command(id: "atlas", title: "Knowledge Atlas", icon: "map",
                    keywords: ["knowledge", "know"], action: .view("atlas")),
            Command(id: "memory", title: "Memory graph", icon: "circle.hexagongrid",
                    keywords: ["knowledge", "remember"], action: .view("memory")),
            Command(id: "skills", title: "Skills", icon: "wand.and.stars",
                    keywords: ["tools", "abilities"], action: .view("skills")),
            Command(id: "workflows", title: "Workflows", icon: "arrow.triangle.branch",
                    keywords: ["tools", "automation"], action: .view("workflows")),
            Command(id: "inspect", title: inspectOpen ? "Close Inspect" : "Inspect", icon: "sidebar.right",
                    keywords: ["drawer", "agents", "runs", "panels"], action: .toggleInspect),
            Command(id: "log", title: "Open Log", icon: "text.alignleft",
                    keywords: ["transcript", "inspect"], action: .openLog),
            Command(id: "display", title: "Open display", icon: "rectangle.on.rectangle",
                    keywords: ["window", "monitor", "screen"], action: .openDisplay)
        ]
        if connected {
            list.append(Command(id: "disconnect", title: "Disconnect", icon: "bolt.slash",
                                keywords: ["hang up", "stop"], action: .disconnect))
        } else if !connecting {
            list.append(Command(id: "connect", title: "Connect", icon: "bolt",
                                keywords: ["start", "reconnect", "retry"], action: .connect))
        }
        if wakeWordAvailable {
            list.append(Command(id: "wake", title: wakeWordOn ? "Wake word off" : "Wake word on",
                                icon: "ear", keywords: ["hey", "listen"], action: .toggleWakeWord))
        }
        list.append(Command(id: "sounds", title: soundsOn ? "Sounds off" : "Sounds on",
                            icon: soundsOn ? "speaker.slash" : "speaker.wave.2",
                            keywords: ["audio", "mute", "chime"], action: .toggleSounds))
        list.append(Command(id: "expand", title: compactConversation ? "Expand voice" : "Keep voice compact",
                            icon: "waveform", keywords: ["orb", "compact", "conversation"],
                            action: .toggleExpandVoice))
        return list
    }

    /// Empty query keeps the order. Otherwise: title prefix, word prefix,
    /// title substring, keyword substring; ties keep the list order.
    static func filter(_ commands: [Command], query: String) -> [Command] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if q.isEmpty { return commands }
        var scored: [(rank: Int, index: Int, command: Command)] = []
        for (index, command) in commands.enumerated() {
            let title = command.title.lowercased()
            var rank: Int?
            if title.hasPrefix(q) {
                rank = 0
            } else if title.split(separator: " ").contains(where: { $0.hasPrefix(q) }) {
                rank = 1
            } else if title.contains(q) {
                rank = 2
            } else if command.keywords.contains(where: { $0.lowercased().contains(q) }) {
                rank = 3
            }
            if let rank { scored.append((rank, index, command)) }
        }
        scored.sort { lhs, rhs in
            lhs.rank != rhs.rank ? lhs.rank < rhs.rank : lhs.index < rhs.index
        }
        return scored.map { $0.command }
    }
}

struct CommandPaletteView: View {
    let commands: [CommandPalette.Command]
    let onRun: (CommandPalette.Command) -> Void
    let onClose: () -> Void
    @State private var query = ""
    @FocusState private var searchFocused: Bool

    private var matches: [CommandPalette.Command] {
        CommandPalette.filter(commands, query: query)
    }

    var body: some View {
        VStack(spacing: 0) {
            TextField("Search commands", text: $query)
                .textFieldStyle(.plain)
                .font(.title3)
                .padding(14)
                .focused($searchFocused)
                .onSubmit { if let first = matches.first { onRun(first) } }
                .accessibilityLabel("Search commands")
                .accessibilityIdentifier("console.palette.search")
            Divider()
            resultList
        }
        .frame(width: 420, height: 360)
        .background(AppTheme.panel)
        .onAppear { searchFocused = true }
        .onExitCommand { onClose() }
        .accessibilityIdentifier("console.palette")
    }

    @ViewBuilder
    private var resultList: some View {
        if matches.isEmpty {
            Text("No matching command")
                .foregroundStyle(AppTheme.textDim)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(matches) { command in
                        row(command)
                    }
                }
                .padding(8)
            }
        }
    }

    private func row(_ command: CommandPalette.Command) -> some View {
        let isFirst = command.id == matches.first?.id
        return Button { onRun(command) } label: {
            HStack(spacing: 10) {
                Image(systemName: command.icon)
                    .frame(width: 18)
                    .foregroundStyle(AppTheme.accent)
                Text(command.title)
                    .foregroundStyle(AppTheme.text)
                Spacer()
                if isFirst {
                    Text("↩︎")
                        .font(.caption)
                        .foregroundStyle(AppTheme.textDim)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isFirst ? AppTheme.accentFaint : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(command.title)
        .accessibilityIdentifier("console.palette.\(command.id)")
    }
}
