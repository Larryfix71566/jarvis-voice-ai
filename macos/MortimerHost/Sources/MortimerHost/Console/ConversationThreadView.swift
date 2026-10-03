import SwiftUI
import JarvisKit

/// WS-17 / Command Console plan §7.2, increment CC7a.1: the conversation
/// thread. Layout 2's stage shows both speakers' full text as transcript rows
/// (approved design A2, Larry 2026-09-30) instead of the last two captions
/// truncated to 160 characters, and spoken answers stop becoming workspace
/// results. Structured display payloads (weather, research, images, graph)
/// keep their own route unchanged.
///
/// On by default. `defaults write com.mortimer.host
/// mortimer.interface.conversationThread -bool false` restores the previous
/// stage and per-answer results until CC7a.4 removes the switch.
enum ConversationThread {
    static let flagKey = "mortimer.interface.conversationThread"

    static func isEnabled(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: flagKey) as? Bool ?? true
    }

    /// Codex boundary 1 (CX-15): spoken answers become results only in the
    /// pre-CC7a layout-2 stage. Other layouts never routed them.
    static func routesSpokenAnswersToResults(layoutVersion: Int, threadEnabled: Bool) -> Bool {
        InterfaceLayoutVersion.resolve(layoutVersion) == 2 && !threadEnabled
    }

    static func showsThread(layoutVersion: Int, threadEnabled: Bool) -> Bool {
        InterfaceLayoutVersion.resolve(layoutVersion) == 2 && threadEnabled
    }

    struct Row: Identifiable, Equatable {
        let id: String
        let isUser: Bool
        let time: Date
        /// Full text, trimmed at the ends only. Never truncated.
        let text: String
        var speaker: String { isUser ? "YOU" : "MORTIMER" }
    }

    /// One row per transcript entry, in transcript order. Empty entries
    /// (a stream that has not produced text yet) are skipped.
    static func rows(_ entries: [ConversationEntry]) -> [Row] {
        entries.compactMap { entry in
            let text = entry.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { return nil }
            return Row(id: entry.id, isUser: entry.role == "user",
                       time: Date(timeIntervalSince1970: entry.createdAt), text: text)
        }
    }

    // MARK: CC7a.2 inline result cards

    /// A result's compact card in the thread (approved design B1, Larry
    /// 2026-09-30): kind icon, "Kind · subject", one summary line, Open.
    /// The card never draws the result itself, so at most one radar map is
    /// live (the opened one).
    struct Card: Identifiable, Equatable {
        let id: UUID
        let time: Date
        let kind: String
        let icon: String
        let subject: String
        let summary: String
        let isPrivate: Bool
        var title: String { "\(kind) · \(subject)" }
    }

    /// Protected (local-only) results show this instead of a body excerpt
    /// (approved design: "Private turn · shown on this Mac only").
    static let privateSummary = "Private · shown on this Mac only"

    static func card(_ result: WorkspaceResult) -> Card {
        let payload = result.payload
        let title = nonEmpty(payload.title) ?? "Result"
        let kind: String
        let icon: String
        var subject = title
        var summary: String
        if let weather = payload.weather {
            kind = "Weather"; icon = "cloud.sun"
            subject = nonEmpty(weather.place.label) ?? title
            var parts = [weather.now.temp, weather.now.condition].compactMap(nonEmpty)
            if !weather.alerts.isEmpty {
                parts.append(weather.alerts.count == 1 ? "1 alert" : "\(weather.alerts.count) alerts")
            }
            summary = parts.joined(separator: " · ")
        } else if MemoryGraphSource.imageURL(payload) != nil {
            kind = "Memory graph"; icon = "point.3.connected.trianglepath.dotted"
            summary = oneLine(payload.body)
        } else if let images = payload.images, !images.isEmpty {
            kind = "Image"; icon = "photo"
            summary = images.count == 1 ? "1 image" : "\(images.count) images"
        } else if let links = payload.links, !links.isEmpty {
            kind = "Research"; icon = "magnifyingglass"
            summary = links.count == 1 ? "1 source" : "\(links.count) sources"
        } else if payload.kind == "text" {
            kind = "Response"; icon = "text.bubble"
            summary = oneLine(payload.body)
        } else {
            kind = "Result"; icon = "doc.text"
            summary = oneLine(payload.body ?? payload.note)
        }
        if payload.isProtectedLocal { summary = privateSummary }
        return Card(id: result.id, time: result.receivedAt, kind: kind, icon: icon,
                    subject: subject, summary: summary, isPrivate: payload.isProtectedLocal)
    }

    /// The first line of text, without Markdown heading, list or quote
    /// marks, at most `limit` characters.
    static func oneLine(_ text: String?, limit: Int = 140) -> String {
        guard let text else { return "" }
        let first = text.split(whereSeparator: \.isNewline).lazy
            .map { $0.trimmingCharacters(in: .whitespaces)
                .trimmingCharacters(in: CharacterSet(charactersIn: "#*>-_` ")) }
            .first { !$0.isEmpty } ?? ""
        let line = first.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        return line.count > limit ? String(line.prefix(limit - 1)) + "…" : line
    }

    private static func nonEmpty(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else { return nil }
        return trimmed
    }

    enum Item: Identifiable, Equatable {
        case row(Row)
        case card(Card)
        var id: String {
            switch self {
            case .row(let row): return row.id
            case .card(let card): return "card-" + card.id.uuidString
            }
        }
    }

    /// Cards sit at the end of the turn they arrived in (plan §7.2,
    /// "compact cards in the thread where they arrived"): after Mortimer's
    /// reply to that question and before the next question, even when the
    /// tool's result arrived before the spoken reply. A card that arrived
    /// before any retained question leads the thread; one from the current
    /// turn ends it. Cards in one turn keep their arrival order.
    static func items(rows: [Row], cards: [Card]) -> [Item] {
        let ordered = cards.enumerated()
            .sorted { ($0.element.time, $0.offset) < ($1.element.time, $1.offset) }
            .map(\.element)
        var slots = Array(repeating: [Card](), count: rows.count + 1)
        for card in ordered {
            let slot = rows.firstIndex { $0.isUser && $0.time > card.time } ?? rows.count
            slots[slot].append(card)
        }
        var items: [Item] = []
        for (index, row) in rows.enumerated() {
            items += slots[index].map(Item.card)
            items.append(.row(row))
        }
        items += slots[rows.count].map(Item.card)
        return items
    }

    /// New items between two snapshots of the thread: the identities in
    /// `current` that were not in `previous`, wherever they sit. Not by count
    /// (at the retention bound, AppTuning.maxConversationEntries, a new turn
    /// replaces the oldest; Codex review of PR #140) and not by position
    /// (a reply is inserted before its turn's tool-first card, and closing
    /// the last card moves no row; Codex review of PR #164). A replaced
    /// transcript, such as a new session, counts as all new.
    static func newTurns(from previous: [String], to current: [String]) -> Int {
        let seen = Set(previous)
        return current.reduce(0) { $0 + (seen.contains($1) ? 0 : 1) }
    }

    /// Within this many points of the end counts as reading the newest turn.
    static let bottomTolerance = 24.0

    static func isAtBottom(contentHeight: Double, visibleMaxY: Double) -> Bool {
        contentHeight - visibleMaxY <= bottomTolerance
    }

    /// The thread follows new turns only while Larry is at the bottom. When
    /// he has scrolled up to read, new turns are counted for a "New" button
    /// instead of moving the text under him.
    struct Follow: Equatable {
        private(set) var following = true
        private(set) var unseen = 0

        mutating func scrolled(atBottom: Bool) {
            following = atBottom
            if atBottom { unseen = 0 }
        }

        /// Returns whether the view should scroll to the newest row.
        mutating func rowsChanged(added: Int) -> Bool {
            if following { return true }
            unseen += max(0, added)
            return false
        }

        mutating func jumpedToEnd() {
            following = true
            unseen = 0
        }
    }
}

struct ConversationThreadView: View {
    /// Card actions go through the same dispatcher as voice and the console
    /// row. Nil (previews, tests) falls back to the store directly.
    let coordinator: ConsoleActionCoordinator?
    @Environment(ConversationStore.self) private var conversation
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @State private var follow = ConversationThread.Follow()
    @State private var pinLimitNotice = false
    private static let endID = "conversation-thread-end"

    init(coordinator: ConsoleActionCoordinator? = nil) {
        self.coordinator = coordinator
    }

    var body: some View {
        let rows = ConversationThread.rows(conversation.entries)
        let items = ConversationThread.items(rows: rows,
                                             cards: workspace.results.map(ConversationThread.card))
        ScrollViewReader { proxy in
            ZStack(alignment: .bottom) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        if items.isEmpty {
                            ContentUnavailableView("Ready", systemImage: "waveform",
                                description: Text("Use the microphone controls to start a conversation."))
                                .padding(.top, 40)
                        }
                        ForEach(items) { item in
                            switch item {
                            case .row(let row):
                                ConversationThreadRowView(row: row)
                            case .card(let card):
                                ConversationThreadCardView(card: card, coordinator: coordinator,
                                                           pinLimitNotice: $pinLimitNotice)
                            }
                        }
                        Color.clear.frame(height: 1).id(Self.endID)
                    }
                    .padding(.horizontal, AdaptiveLayoutMetrics.workspacePadding)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .defaultScrollAnchor(.bottom)
                .onScrollGeometryChange(for: Bool.self) { geometry in
                    ConversationThread.isAtBottom(contentHeight: Double(geometry.contentSize.height),
                                                  visibleMaxY: Double(geometry.visibleRect.maxY))
                } action: { _, atBottom in
                    follow.scrolled(atBottom: atBottom)
                }
                .onChange(of: items.map(\.id)) { old, new in
                    // A card that joins the end of the thread counts as a new
                    // turn: followed at the bottom, counted when scrolled up.
                    let added = ConversationThread.newTurns(from: old, to: new)
                    guard added > 0 else { return }
                    if follow.rowsChanged(added: added) { scrollToEnd(proxy) }
                }
                .onChange(of: rows.last?.text) { _, _ in
                    // A streaming answer grows in place; keep its end in view
                    // only while following.
                    if follow.following { scrollToEnd(proxy) }
                }

                if follow.unseen > 0 {
                    Button {
                        follow.jumpedToEnd()
                        scrollToEnd(proxy)
                    } label: {
                        Label(follow.unseen == 1 ? "1 new" : "\(follow.unseen) new", systemImage: "arrow.down")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(AppTheme.accent.opacity(0.85))
                    .padding(.bottom, 10)
                    .accessibilityLabel("Show \(follow.unseen) new conversation turns")
                }
            }
        }
        .accessibilityIdentifier("conversation-thread")
        .alert("Pin limit reached", isPresented: $pinLimitNotice) {
            Button("OK", role: .cancel) {}
        } message: { Text("Unpin a result before pinning another. Your existing pins are preserved.") }
    }

    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        if reduceMotion {
            proxy.scrollTo(Self.endID, anchor: .bottom)
        } else {
            withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(Self.endID, anchor: .bottom) }
        }
    }
}

/// CC7a.2 approved design B1: one compact line under Mortimer's reply, in
/// the text column. Open shows the result on the stage (Conversation in
/// the console row comes back); the menu pins, compares or closes it.
/// Closing removes the card and the result from the workspace only; the
/// Output history keeps its record (§7.2 Codex boundary 2).
struct ConversationThreadCardView: View {
    let card: ConversationThread.Card
    let coordinator: ConsoleActionCoordinator?
    @Binding var pinLimitNotice: Bool
    @Environment(WorkspaceStore.self) private var workspace

    init(card: ConversationThread.Card, coordinator: ConsoleActionCoordinator?,
         pinLimitNotice: Binding<Bool>) {
        self.card = card
        self.coordinator = coordinator
        self._pinLimitNotice = pinLimitNotice
    }

    var body: some View {
        let pinned = workspace.pinnedIDs.contains(card.id)
        let unread = workspace.unreadIDs.contains(card.id)
        HStack(spacing: 10) {
            Image(systemName: card.isPrivate ? "lock.fill" : card.icon)
                .font(.system(size: 15))
                .foregroundStyle(AppTheme.accent)
                .frame(width: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(card.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(AppTheme.text)
                    .lineLimit(1)
                if !card.summary.isEmpty {
                    Text(card.summary)
                        .font(.system(size: 12))
                        .foregroundStyle(AppTheme.textDim)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if unread {
                Circle().fill(AppTheme.accent).frame(width: 7, height: 7)
                    .help("Not opened yet")
                    .accessibilityLabel("Not opened yet")
            }
            if pinned {
                Image(systemName: "pin.fill")
                    .font(.system(size: 11))
                    .foregroundStyle(AppTheme.textDim)
                    .help("Pinned")
                    .accessibilityLabel("Pinned")
            }
            Menu {
                Button(pinned ? "Unpin" : "Pin") { togglePin(pinned: pinned) }
                Menu("Compare with") {
                    ForEach(workspace.results.filter { $0.id != card.id }) { other in
                        Button(ConversationThread.card(other).title) { compare(with: other.id) }
                    }
                }
                .disabled(workspace.results.count < 2)
                Divider()
                Button("Close") { close() }
            } label: {
                Image(systemName: "ellipsis")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pin, compare or close")
            .accessibilityLabel("More actions for \(card.title)")
            Button("Open") { open() }
                .help("Show this result; Conversation brings you back")
                .accessibilityLabel("Open \(card.title)")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(AppTheme.panel.opacity(0.8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.hairline))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        // In the text column, under the reply it belongs to (row speaker
        // column 84 + spacing 12).
        .padding(.leading, 96)
        .padding(.vertical, 6)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(card.summary.isEmpty ? card.title : "\(card.title). \(card.summary)")
        .accessibilityIdentifier("thread-card")
    }

    private var target: String { card.id.uuidString }

    private func open() {
        if let coordinator { _ = coordinator.executePointer(.resultSelect, target: target) }
        else { workspace.select(card.id) }
    }

    private func togglePin(pinned: Bool) {
        if let coordinator {
            if coordinator.executePointer(pinned ? .resultUnpin : .resultPin, target: target) == .noop,
               !pinned { pinLimitNotice = true }
        } else if pinned {
            workspace.unpin(card.id)
        } else {
            pinLimitNotice = !workspace.pin(card.id)
        }
    }

    private func compare(with other: UUID) {
        if let coordinator {
            _ = coordinator.executePointer(.compareSet, target: target, secondaryTarget: other.uuidString)
        } else {
            workspace.select(card.id)
            workspace.compare(with: other)
        }
    }

    private func close() {
        if let coordinator { _ = coordinator.executePointer(.resultClose, target: target) }
        else { workspace.close(card.id) }
    }
}

/// CC7a.2 approved design "New result while reading": while something
/// other than the conversation is on the stage, an arrival shows
/// "New: … Show / Dismiss" above it instead of taking the stage. On the
/// conversation itself the result opens (Larry, 10-03); its card stays in
/// the thread for later.
struct ArrivalNoticeView: View {
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace

    init(coordinator: ConsoleActionCoordinator?) {
        self.coordinator = coordinator
    }

    var body: some View {
        if let id = workspace.arrivalNoticeID,
           let result = workspace.results.first(where: { $0.id == id }) {
            let card = ConversationThread.card(result)
            HStack(spacing: 10) {
                Image(systemName: card.isPrivate ? "lock.fill" : card.icon)
                    .foregroundStyle(AppTheme.accent)
                    .accessibilityHidden(true)
                Text("New: \(card.title)")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(AppTheme.text)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Button("Show") {
                    if let coordinator { _ = coordinator.executePointer(.resultSelect, target: id.uuidString) }
                    else { workspace.select(id) }
                }
                Button("Dismiss") { workspace.dismissArrivalNotice() }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(AppTheme.accentFaint)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(AppTheme.accentDim))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .padding(.horizontal, AdaptiveLayoutMetrics.workspacePadding)
            .padding(.top, 8)
            .accessibilityElement(children: .contain)
            .accessibilityLabel("New result: \(card.title)")
            .accessibilityIdentifier("arrival-notice")
        }
    }
}

/// Approved design A2: a speaker column (YOU / MORTIMER and the time) and
/// the full text at full width, one hairline between turns.
struct ConversationThreadRowView: View {
    let row: ConversationThread.Row

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.speaker)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .kerning(1.2)
                    .foregroundStyle(row.isUser ? AppTheme.accent : AppTheme.textDim)
                Text(row.time.formatted(date: .omitted, time: .shortened))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(AppTheme.textDim)
            }
            .frame(width: 84, alignment: .leading)
            Text(row.text)
                .font(.system(size: 15))
                .foregroundStyle(AppTheme.text)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 9)
        .overlay(alignment: .bottom) {
            Rectangle().fill(AppTheme.hairline.opacity(0.6)).frame(height: 1)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(row.isUser ? "You" : "Mortimer"): \(row.text)")
    }
}
