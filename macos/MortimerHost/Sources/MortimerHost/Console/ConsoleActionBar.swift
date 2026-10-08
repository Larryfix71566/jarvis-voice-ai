import SwiftUI
import JarvisKit

/// WS-17 (Larry, 2026-09-30): the Command Console has ONE row of controls.
/// "All buttons on the console line, none below." This bar replaces the
/// console header's view buttons, the stage's own row (Expand voice, the
/// view buttons, Return to workspace), the results view's row (the view
/// buttons, Display, Pin, Compare), its tab strip, and the result's own row
/// (Summary/Sources, Copy, Share, Export). Layout 2 only; the older layouts,
/// detached panels and the supporting display keep their controls.
///
/// Approved order (Larry, 2026-09-30): Conversation · Results ▾ (click opens
/// the results view, the arrow lists the open results) · Knowledge ▾
/// (Knowledge Atlas, Memory graph: what Mortimer knows) · Tools ▾ (Skills,
/// Workflows: what Mortimer can do) · Actions ▾ (only while a result is
/// shown) · Expand voice (only on the conversation). Sending content to the
/// supporting display stays available with no result open: each menu offers
/// it for its own content (Codex review of #147, 10-02). The row never wraps: when it does
/// not fit it drops the "Command Console" title, then shows icons, keeping
/// every control's accessibility label and tooltip.
struct ConsoleActionBar: View {
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer
    @Environment(ShareCoordinator.self) private var sharing
    @AppStorage("mortimer.interface.compactConversation") private var compactConversation = true
    @State private var pinLimitNotice = false
    @State private var showingSharePreview = false

    init(coordinator: ConsoleActionCoordinator?) {
        self.coordinator = coordinator
    }

    enum Density { case full, untitled, icons }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            row(.full)
            row(.untitled)
            row(.icons)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .alert("Pin limit reached", isPresented: $pinLimitNotice) {
            Button("OK", role: .cancel) {}
        } message: { Text("Unpin a result before pinning another. Your existing pins are preserved.") }
        .sheet(isPresented: $showingSharePreview) {
            SharePreviewSheet(coordinator: coordinator, isPresented: $showingSharePreview)
        }
    }

    // MARK: Rules (pure, tested)

    enum ViewMode: Equatable { case conversation, results, atlas, memory, skills, workflows }

    /// Same precedence as `WorkspaceStore.consoleInventory`'s mode.
    static func mode(conversation: Bool, skills: Bool, memory: Bool, atlas: Bool, workflows: Bool) -> ViewMode {
        if conversation { return .conversation }
        if skills { return .skills }
        if memory { return .memory }
        if atlas { return .atlas }
        if workflows { return .workflows }
        return .results
    }

    /// The result the Actions menu acts on: in a comparison, the side chosen
    /// with "Acting on" (`WorkspaceStore.comparisonSide`, B = the comparison
    /// result); otherwise the active result.
    static func actionTarget(active: WorkspaceResult?, comparison: WorkspaceResult?,
                             side: WorkspaceComparisonSide) -> WorkspaceResult? {
        if let comparison, side == .b { return comparison }
        return active
    }

    /// Actions only while a result is on screen.
    static func showsActions(mode: ViewMode, hasActiveResult: Bool) -> Bool {
        mode == .results && hasActiveResult
    }

    private var mode: ViewMode {
        Self.mode(conversation: workspace.showsConversation, skills: workspace.showsSkills,
                  memory: workspace.showsMemoryGraph, atlas: workspace.showsAtlas,
                  workflows: workspace.showsWorkflows)
    }

    private var target: WorkspaceResult? {
        Self.actionTarget(active: workspace.activeResult, comparison: workspace.comparisonResult,
                          side: workspace.comparisonSide)
    }

    // MARK: Row

    @ViewBuilder
    private func row(_ density: Density) -> some View {
        let icons = density == .icons
        HStack(spacing: 8) {
            if density == .full {
                Label("Command Console", systemImage: "command").font(.headline)
            } else {
                Image(systemName: "command").font(.headline)
                    .accessibilityLabel("Command Console")
            }
            viewButton("Conversation", icon: "bubble.left.and.bubble.right", target: "conversation",
                       active: mode == .conversation, icons: icons)
            resultsMenu(icons: icons)
            knowledgeMenu(icons: icons)
            toolsMenu(icons: icons)
            if Self.showsActions(mode: mode, hasActiveResult: workspace.activeResult != nil) {
                Divider().frame(height: 18)
                actionsMenu(icons: icons)
            }
            Spacer(minLength: 8)
            if mode == .conversation {
                expandVoiceButton(icons: icons)
            }
        }
    }

    private func go(_ target: String) {
        if let coordinator { _ = coordinator.executePointer(.viewSet, target: target); return }
        switch target {
        case "conversation": workspace.returnToConversation()
        case "results": workspace.returnToWorkspace()
        case "atlas": workspace.openAtlas()
        case "memory": workspace.openMemoryGraph()
        case "skills": workspace.openSkills()
        case "workflows": workspace.openWorkflows()
        default: break
        }
    }

    @ViewBuilder
    private func barLabel(_ title: String, icon: String, icons: Bool) -> some View {
        if icons { Image(systemName: icon) } else { Text(title) }
    }

    private func viewButton(_ title: String, icon: String, target: String, active: Bool, icons: Bool) -> some View {
        Button { go(target) } label: { barLabel(title, icon: icon, icons: icons) }
            .padding(.horizontal, 2)
            .background(active ? AppTheme.accentFaint : Color.clear)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(active ? AppTheme.accentDim : Color.clear))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .help(title)
            .accessibilityLabel(title)
            .accessibilityIdentifier("console.\(target)")
            .accessibilityAddTraits(active ? [.isSelected] : [])
    }

    // MARK: Results ▾

    /// CC7a.3 Recents (plan §7.2, approved design): PINNED, then RECENT
    /// (about 10), each row numbered to match voice ("open number 3") with
    /// its age; selected, pinned and unread marks as before. Pin / Close /
    /// Compare act on any entry. Results past the bound stay reachable
    /// under Older; the bound never removes a result.
    private func resultsMenu(icons: Bool) -> some View {
        let count = workspace.results.count
        let title = count == 0 ? "Results" : "Results · \(count)"
        let listing = workspace.recents
        let now = Date()
        return Menu {
            if workspace.results.isEmpty {
                Text("No results yet")
            }
            if !listing.pinned.isEmpty {
                Section("Pinned") { recentsRows(listing.pinned, now: now) }
            }
            if !listing.recent.isEmpty {
                Section("Recent") { recentsRows(listing.recent, now: now) }
            }
            if !listing.older.isEmpty {
                Menu("Older · \(listing.older.count)") {
                    recentsRows(listing.olderEntries, now: now)
                }
            }
            if !listing.actionableEntries.isEmpty {
                Divider()
                Menu("Pin or unpin") {
                    ForEach(listing.actionableEntries) { entry in
                        Button(Self.pinCommandTitle(entry, pinned: workspace.pinnedIDs.contains(entry.id))) {
                            togglePin(entry.id)
                        }
                    }
                }
                Menu("Close") {
                    ForEach(listing.actionableEntries) { entry in
                        Button(entry.label) {
                            if let coordinator { _ = coordinator.executePointer(.resultClose, target: entry.id.uuidString) }
                            else { workspace.close(entry.id) }
                        }
                    }
                }
                if let shown = workspace.activeResult, mode == .results {
                    Menu("Compare with shown") {
                        ForEach(listing.actionableEntries.filter { $0.id != shown.id }) { entry in
                            Button(entry.label) {
                                if let coordinator {
                                    _ = coordinator.executePointer(.compareSet, target: shown.id.uuidString,
                                                                   secondaryTarget: entry.id.uuidString)
                                } else {
                                    workspace.compare(with: entry.id)
                                }
                            }
                        }
                    }
                }
                let pinned = Self.pinnedDisplayCommands(results: workspace.results,
                                                        isPinned: { workspace.pinnedIDs.contains($0) })
                if !pinned.isEmpty {
                    Menu("Show pinned on display") { displayButtons(pinned) }
                }
            }
        } label: {
            barLabel(title, icon: "doc.text.magnifyingglass", icons: icons)
        } primaryAction: {
            go("results")
        }
        .fixedSize()
        .padding(.horizontal, 2)
        .background(mode == .results ? AppTheme.accentFaint : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help("Show results; the arrow lists Recents")
        .accessibilityLabel(title)
        .accessibilityIdentifier("console.results")
    }

    @ViewBuilder
    private func recentsRows(_ entries: [WorkspaceRecents.Entry], now: Date) -> some View {
        ForEach(entries) { entry in
            Button { select(entry.id) } label: {
                let text = Self.recentsRowTitle(entry, now: now)
                if let icon = Self.recentsIcon(entry) {
                    Label(text, systemImage: icon)
                } else {
                    Text(text)
                }
            }
            .accessibilityLabel(Self.recentsAccessibilityLabel(entry, now: now))
        }
    }

    private func select(_ id: UUID) {
        if let coordinator { _ = coordinator.executePointer(.resultSelect, target: id.uuidString) }
        else { workspace.select(id) }
    }

    private func togglePin(_ id: UUID) {
        let pinned = workspace.pinnedIDs.contains(id)
        if let coordinator {
            if coordinator.executePointer(pinned ? .resultUnpin : .resultPin, target: id.uuidString) == .noop,
               !pinned { pinLimitNotice = true }
        } else if pinned { workspace.unpin(id) }
        else { pinLimitNotice = !workspace.pin(id) }
    }

    /// "3  Weather · Folly Beach · 5m".
    static func recentsRowTitle(_ entry: WorkspaceRecents.Entry, now: Date = Date()) -> String {
        "\(entry.label) · \(WorkspaceRecents.age(of: entry.freshnessDate, now: now))"
    }

    /// Spoken by VoiceOver: number, title, age, then state.
    static func recentsAccessibilityLabel(_ entry: WorkspaceRecents.Entry, now: Date = Date()) -> String {
        var parts = [entry.number.map { "Number \($0)" }, entry.card.title,
                     WorkspaceRecents.age(of: entry.freshnessDate, now: now)].compactMap { $0 }
        if entry.isActive { parts.append("shown") }
        if entry.isUnread { parts.append("unread") }
        if entry.section == .pinned { parts.append("pinned") }
        if entry.isPrivate { parts.append("private") }
        return parts.joined(separator: ", ")
    }

    static func pinCommandTitle(_ entry: WorkspaceRecents.Entry, pinned: Bool) -> String {
        "\(pinned ? "Unpin" : "Pin") \(entry.label)"
    }

    /// Selected first, then unread, then pinned (pinned rows already sit
    /// under their own heading).
    static func recentsIcon(_ entry: WorkspaceRecents.Entry) -> String? {
        if entry.isActive { return "checkmark" }
        if entry.isUnread { return "circle.fill" }
        if entry.section == .pinned { return "pin.fill" }
        return nil
    }

    // MARK: Knowledge ▾ and Tools ▾ (Larry 2026-09-30)

    private func knowledgeMenu(icons: Bool) -> some View {
        Menu {
            Button("Knowledge Atlas") { go("atlas") }
            Button("Memory graph") { go("memory") }
            Divider()
            displayButtons(Self.knowledgeDisplayCommands(windowOpen: display.isWindowOpen))
        } label: {
            barLabel("Knowledge", icon: "books.vertical", icons: icons)
        }
        .fixedSize()
        .padding(.horizontal, 2)
        .background(mode == .atlas || mode == .memory ? AppTheme.accentFaint : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help("Knowledge Atlas and Memory graph")
        .accessibilityLabel("Knowledge")
        .accessibilityIdentifier("console.knowledge")
    }

    private func toolsMenu(icons: Bool) -> some View {
        Menu {
            Button("Skills") { go("skills") }
            Button("Workflows") { go("workflows") }
            Divider()
            displayButtons(Self.toolsDisplayCommands(windowOpen: display.isWindowOpen))
        } label: {
            barLabel("Tools", icon: "wrench.and.screwdriver", icons: icons)
        }
        .fixedSize()
        .padding(.horizontal, 2)
        .background(mode == .skills || mode == .workflows ? AppTheme.accentFaint : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help("Skills and Workflows")
        .accessibilityLabel("Tools")
        .accessibilityIdentifier("console.tools")
    }

    // MARK: Actions ▾

    private func actionsMenu(icons: Bool) -> some View {
        Menu {
            if let comparison = workspace.comparisonResult, let active = workspace.activeResult {
                Picker("Acting on", selection: Binding(
                    get: { workspace.comparisonSide },
                    set: { side in
                        if let coordinator { _ = coordinator.executePointer(.compareSide, target: side.rawValue) }
                        else { _ = workspace.setComparisonSide(side) }
                    })) {
                    Text("A: \(active.payload.title ?? "Result")").tag(WorkspaceComparisonSide.a)
                    Text("B: \(comparison.payload.title ?? "Result")").tag(WorkspaceComparisonSide.b)
                }
                .pickerStyle(.inline)
                Divider()
            }
            if let target {
                targetActions(target)
            }
        } label: {
            barLabel("Actions", icon: "ellipsis.circle", icons: icons)
        }
        .fixedSize()
        .help("Actions on the result shown")
        .accessibilityLabel("Actions")
        .accessibilityIdentifier("console.actions")
    }

    @ViewBuilder
    private func targetActions(_ result: WorkspaceResult) -> some View {
        let isProtected = result.payload.isProtectedLocal
        if !isProtected {
            let presentation = workspace.presentation(for: result)
            Picker("View", selection: Binding(get: { presentation.mode }, set: { mode in
                if let coordinator {
                    _ = coordinator.executePointer(.resultMode, target: result.id.uuidString,
                                                    args: ["mode": .string(mode.rawValue)])
                } else {
                    presentation.mode = mode
                }
            })) {
                Text("Summary").tag(WorkspaceResultMode.summary)
                Text("Sources").tag(WorkspaceResultMode.sources)
                if MemoryGraphSource.imageURL(result.payload) != nil {
                    Text("Connections").tag(WorkspaceResultMode.connections)
                }
            }
            .pickerStyle(.inline)
            Divider()
        }
        Button(workspace.pinnedIDs.contains(result.id) ? "Unpin" : "Pin") {
            let pinned = workspace.pinnedIDs.contains(result.id)
            if let coordinator {
                if coordinator.executePointer(pinned ? .resultUnpin : .resultPin, target: result.id.uuidString) == .noop,
                   !pinned { pinLimitNotice = true }
            } else if pinned { workspace.unpin(result.id) }
            else { pinLimitNotice = !workspace.pin(result.id) }
        }
        compareMenu(for: result)
        displayMenu
        Divider()
        Button("Copy") {
            if let coordinator {
                _ = coordinator.executePointer(.sharePreview, target: result.id.uuidString)
                _ = coordinator.executePointer(.shareCopy)
            } else {
                workspace.exporter.copy(result: result)
            }
        }
        .disabled(isProtected)
        Button("Share…") {
            if let coordinator {
                if coordinator.executePointer(.sharePreview, target: result.id.uuidString) == .applied {
                    showingSharePreview = true
                }
            } else if sharing.beginPreview(result) != nil {
                showingSharePreview = true
            }
        }
        .disabled(isProtected)
        Button("Export…") { workspace.exporter.chooseDestination(for: result) }
            .disabled(workspace.exporter.busy || isProtected)
    }

    private func compareMenu(for result: WorkspaceResult) -> some View {
        Menu("Compare with") {
            ForEach(workspace.results.filter { $0.id != result.id }) { other in
                Button(other.payload.title ?? "Result") {
                    if let coordinator {
                        _ = coordinator.executePointer(.compareSet, target: result.id.uuidString,
                                                       secondaryTarget: other.id.uuidString)
                    } else {
                        workspace.select(result.id)
                        workspace.compare(with: other.id)
                    }
                }
            }
            if workspace.comparisonID != nil {
                Divider()
                Button("End comparison") {
                    if let coordinator { _ = coordinator.executePointer(.compareEnd) }
                    else { workspace.compare(with: nil) }
                }
            }
        }
    }

    /// The results view's former Display menu, unchanged in content.
    private var displayMenu: some View {
        Menu("Show on display") {
            Button("Show memory graph") { sendToDisplay(.memoryGraph) }
            Button("Show Skills") { sendToDisplay(.skills) }
            Button("Show workflows") { sendToDisplay(.workflows) }
            if let active = workspace.activeResult, !active.payload.isProtectedLocal {
                Button("Show active result") { sendToDisplay(.result(active.id)) }
            }
            if let comparison = workspace.comparisonResult, !comparison.payload.isProtectedLocal {
                Button("Show comparison result") { sendToDisplay(.result(comparison.id)) }
            }
            ForEach(workspace.results.filter {
                workspace.pinnedIDs.contains($0.id) && !$0.payload.isProtectedLocal
            }) { result in
                Button(result.payload.title ?? "Pinned result") { sendToDisplay(.result(result.id)) }
            }
            if display.isWindowOpen {
                Button("Return display content here") { drawer.placementRef?.closeDisplay() }
            }
        }
    }

    private func sendToDisplay(_ content: SupportingDisplayContent) {
        // WS-21 D1: the same validated, confirmed route voice uses.
        if let supportingDisplay = drawer.supportingDisplayRef {
            supportingDisplay.show(content); return
        }
        guard workspace.sendToDisplay(content) else { return }
        drawer.placementRef?.openDisplay()
    }

    // MARK: Show on the supporting display (Codex review of #147, 10-02)

    /// One "show on the supporting display" command. Layout 2 hides the
    /// results view's Display menu, so each command sits in the menu that
    /// owns its content and stays reachable with no result open: Knowledge
    /// (memory graph), Tools (Skills, Workflows), Results (pinned results),
    /// Actions (the result shown). `content == nil` returns the display
    /// content to this window.
    struct DisplayCommand: Equatable, Identifiable {
        let title: String
        let content: SupportingDisplayContent?
        var id: String {
            if case .result(let id) = content { return id.uuidString }
            return title
        }
    }

    private static func returnHere(_ windowOpen: Bool) -> [DisplayCommand] {
        windowOpen ? [DisplayCommand(title: "Return display content here", content: nil)] : []
    }

    static func knowledgeDisplayCommands(windowOpen: Bool) -> [DisplayCommand] {
        [DisplayCommand(title: "Show memory graph on display", content: .memoryGraph)] + returnHere(windowOpen)
    }

    static func toolsDisplayCommands(windowOpen: Bool) -> [DisplayCommand] {
        [DisplayCommand(title: "Show Skills on display", content: .skills),
         DisplayCommand(title: "Show workflows on display", content: .workflows)] + returnHere(windowOpen)
    }

    /// Pinned results that may leave this window (protected-local ones never do).
    static func pinnedDisplayCommands(results: [WorkspaceResult], isPinned: (UUID) -> Bool) -> [DisplayCommand] {
        results.filter { isPinned($0.id) && !$0.payload.isProtectedLocal }
            .map { DisplayCommand(title: $0.payload.title ?? "Pinned result", content: .result($0.id)) }
    }

    /// Puts the command's content on the supporting display; false when the
    /// store refuses it (a protected or closed result) or for "return here".
    @discardableResult
    static func apply(_ command: DisplayCommand, to workspace: WorkspaceStore) -> Bool {
        guard let content = command.content else { return false }
        return workspace.sendToDisplay(content)
    }

    @ViewBuilder
    private func displayButtons(_ commands: [DisplayCommand]) -> some View {
        ForEach(commands) { command in
            Button(command.title) { run(command) }
        }
    }

    private func run(_ command: DisplayCommand) {
        guard let content = command.content else { drawer.placementRef?.closeDisplay(); return }
        sendToDisplay(content)
    }

    // MARK: Expand voice

    private func expandVoiceButton(icons: Bool) -> some View {
        let title = compactConversation ? "Expand voice" : "Keep voice compact"
        return Button { compactConversation.toggle() } label: {
            barLabel(title, icon: compactConversation ? "waveform" : "rectangle.compress.vertical", icons: icons)
        }
        .help(title)
        .accessibilityLabel(title)
        .accessibilityIdentifier("console.expandVoice")
    }
}
