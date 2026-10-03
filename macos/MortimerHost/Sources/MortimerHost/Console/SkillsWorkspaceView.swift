import SwiftUI
import AppKit
import JarvisKit

struct SkillsWorkspaceActivityState {
    var skillID: String?
    var runs: [SkillRunSummary] = []
    var selectedRunID: String?
    var page: SkillActivityPage?
    var events: [SkillActivityEvent] = []
    var hasMore = false
    var loadedRunID: String?
    var error: String?
    var retryNonce = 0
    var retryLoadsMore = false
    /// Invalidates in-flight responses whenever the selected skill or run
    /// changes, including an A → B → A selection that run-ID checks alone miss.
    private(set) var selectionGeneration: UInt64 = 0

    mutating func selectSkill(_ id: String?) {
        guard skillID != id else { return }
        skillID = id
        runs = []
        selectedRunID = nil
        clearTrace()
    }

    mutating func selectRun(_ id: String?) {
        guard selectedRunID != id else { return }
        selectedRunID = id
        clearTrace()
    }

    mutating func clearTrace() {
        selectionGeneration &+= 1
        page = nil
        events = []
        hasMore = false
        loadedRunID = nil
        error = nil
        retryLoadsMore = false
    }
}

private struct SkillsCatalogCard: Identifiable, Equatable {
    let id: String
    let name: String
    let description: String
    let category: String
    let installation: String
    let revision: String?
    let enabled: Bool
    let readiness: String
    let readinessReasons: [String]
    let verification: String
    let exampleIDs: [String]

    init?(_ value: JSONValue) {
        guard let id = value["skill_id"]?.stringValue,
              let name = value["display_name"]?.stringValue,
              let description = value["description"]?.stringValue else { return nil }
        self.id = id
        self.name = name
        self.description = description
        self.category = value["category"]?.stringValue ?? "general"
        self.installation = value["installation"]?.stringValue ?? "installed"
        self.revision = value["revision"]?.stringValue
        self.enabled = value["enabled"]?.boolValue ?? false
        self.readiness = value["readiness"]?.stringValue ?? "unknown"
        self.readinessReasons = value["readiness_reasons"]?.arrayValue?.compactMap(\.stringValue) ?? []
        self.verification = value["verification"]?.stringValue ?? "not_tested"
        self.exampleIDs = Array((value["example_ids"]?.arrayValue ?? [])
            .compactMap(\.stringValue).prefix(32))
    }
}

/// Keeps unchanged catalog rows from rebuilding their text and status layout
/// when selecting a different skill. The list's 100-row fixture measured this
/// as the wide-layout selection hot path.
private struct SkillsCatalogCardRowContent: View, Equatable {
    let card: SkillsCatalogCard
    let isSelected: Bool
    let differentiateWithoutColor: Bool
    let reduceTransparency: Bool

    static func == (lhs: Self, rhs: Self) -> Bool {
        // Selection updates compare every visible row. Catalog cards also
        // carry revision, verification and example metadata that this compact
        // row never renders; comparing those arrays on each click adds work
        // without affecting the row's pixels or accessibility output.
        lhs.card.id == rhs.card.id
            && lhs.card.name == rhs.card.name
            && lhs.card.description == rhs.card.description
            && lhs.card.category == rhs.card.category
            && lhs.card.installation == rhs.card.installation
            && lhs.card.readiness == rhs.card.readiness
            && lhs.card.readinessReasons.first == rhs.card.readinessReasons.first
            && lhs.card.enabled == rhs.card.enabled
            && lhs.isSelected == rhs.isSelected
            && lhs.differentiateWithoutColor == rhs.differentiateWithoutColor
            && lhs.reduceTransparency == rhs.reduceTransparency
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(card.name).font(.headline).lineLimit(2)
                Spacer(minLength: 4)
                if isSelected && differentiateWithoutColor {
                    Label("Selected", systemImage: "checkmark.circle.fill")
                        .font(.caption.weight(.semibold))
                }
                if card.enabled {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(AppTheme.green)
                        .accessibilityLabel("Enabled")
                }
            }
            Text(card.description)
                .font(.caption).foregroundStyle(AppTheme.textDim)
                .lineLimit(3)
            HStack(spacing: 8) {
                Text(card.category.capitalized)
                Text(card.installation.capitalized)
                Text(card.readiness.replacingOccurrences(of: "_", with: " ").capitalized)
            }
            .font(.caption2).foregroundStyle(AppTheme.textDim)
            if let reason = card.readinessReasons.first {
                Text(readinessMessage(reason))
                    .font(.caption2).foregroundStyle(AppTheme.textDim)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .padding(10)
        .background(
            reduceTransparency ? AppTheme.panelOpaque
                : (isSelected ? AppTheme.accent.opacity(0.14) : AppTheme.panel.opacity(0.65)),
            in: RoundedRectangle(cornerRadius: 11)
        )
        .overlay(RoundedRectangle(cornerRadius: 11)
            .stroke(isSelected ? AppTheme.accent.opacity(reduceTransparency ? 1 : 0.65) : .clear,
                    lineWidth: isSelected && differentiateWithoutColor ? 2 : 1))
    }
}

/// Keep the button and its accessibility modifiers stable as well as its
/// label. Actions read the current shared store/coordinator, so equality never
/// retains a closure with an obsolete catalog or navigation snapshot.
private struct SkillsCatalogCardButton: View, Equatable {
    let card: SkillsCatalogCard
    let isSelected: Bool
    let differentiateWithoutColor: Bool
    let reduceTransparency: Bool
    let store: SkillsStore
    let coordinator: ConsoleActionCoordinator?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.card == rhs.card && lhs.isSelected == rhs.isSelected
            && lhs.differentiateWithoutColor == rhs.differentiateWithoutColor
            && lhs.reduceTransparency == rhs.reduceTransparency
            && lhs.store === rhs.store && lhs.coordinator === rhs.coordinator
    }

    var body: some View {
        Button {
            if let coordinator { _ = coordinator.executePointer(.skillSelect, target: card.id) }
            else { _ = store.selectSkill(card.id) }
        } label: {
            SkillsCatalogCardRowContent(card: card, isSelected: isSelected,
                differentiateWithoutColor: differentiateWithoutColor,
                reduceTransparency: reduceTransparency)
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityValue(card.enabled ? "Enabled" : "Disabled")
        .accessibilityHint("Opens the skill overview and intended process")
    }
}

enum SkillsWorkspacePresentationPolicy {
    static func needsAttention(
        installation: String,
        readiness: String,
        verification: String,
        enabled: Bool = true,
        readinessReasons: [String] = []
    ) -> Bool {
        if verification == "failed" || verification == "stale" { return true }

        // A deliberately inert package should not create a dashboard alert
        // just because readiness reports `skill_disabled` alongside unknown
        // runtime evidence. Keep every other explicit blocker visible, and
        // fail closed for reason codes this UI has not classified yet.
        if !enabled, readinessReasons.contains("skill_disabled") {
            let expectedWhileInert: Set<String> = [
                "skill_disabled",
                "revision_enforcement_disabled",
                "revision_pin_unverified",
                "tool_runtime_unverified",
                "tool_inventory_unavailable",
                "tool_inventory_incomplete",
                "credential_presence_unverified",
                "credential_authentication_unverified",
                "model_route_compatibility_unverified",
                "sandbox_availability_unverified",
            ]
            return readinessReasons.contains { !expectedWhileInert.contains($0) }
        }

        return readiness == "blocked"
            || (installation != "proposed" && readiness != "ready")
    }

    static func showsEdgeChoices(processKind: String?) -> Bool {
        processKind == "branching" || processKind == "guidance"
    }

    static func showsLinearNext(processKind: String?) -> Bool {
        processKind == "linear"
    }

    static func usesSplitLayout(width: CGFloat, dynamicTypeSize: DynamicTypeSize) -> Bool {
        width >= 960 && !dynamicTypeSize.isAccessibilitySize
    }

    static func canTransferToSupportingDisplay(screenCount: Int) -> Bool {
        screenCount > 1
    }

    static func activityRefreshInterval(
        skillID: String, runStatus: String?, sceneIsActive: Bool
    ) -> Double? {
        if runStatus == "running" { return sceneIsActive ? 1 : 5 }
        // Validation can begin after the originating Developer has finished,
        // including while this view already shows its terminal run. The view's
        // task lifetime still cancels polling on tab/selection/window changes.
        if skillID == "skill-creator" { return sceneIsActive ? 5 : 15 }
        return nil
    }

    /// Stable activity-task identity for transport changes. Do not include a
    /// failure's diagnostic string: it may contain transport details and does
    /// not represent a distinct connection lifecycle state for trace refresh.
    static func activityConnectionKey(_ state: JarvisClient.ConnectionState) -> String {
        switch state {
        case .offline: "offline"
        case .connecting: "connecting"
        case .connected: "connected"
        case .failed: "failed"
        }
    }

    static func canOpenCreator(authoringAvailable: Bool, catalogRevision: String) -> Bool {
        authoringAvailable && catalogRevision.count == 64
    }

    static func isCurrentDetailResponse(
        requestID: UUID,
        currentRequestID: UUID,
        requestedSkillID: String,
        selectedSkillID: String?
    ) -> Bool {
        requestID == currentRequestID && requestedSkillID == selectedSkillID
    }
}

/// Read-only first Skills surface. Backend package metadata is authoritative;
/// this view owns only query results and the user's current selection.
struct SkillsWorkspaceView: View {
    var detailOnly = false
    var coordinator: ConsoleActionCoordinator?
    @EnvironmentObject private var client: JarvisClient
    @Environment(SkillsStore.self) private var skillsStore
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(DisplayWindowStore.self) private var display
    @Environment(DrawerState.self) private var drawer
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var cards: [SkillsCatalogCard] = []
    @State private var appliedNavigationSkillID: String?
    @State private var detailLoadRequestID = UUID()
    @State private var detail: JSONValue?
    @State private var search = ""
    @State private var errorMessage: String?
    @State private var loading = false
    @State private var activeTab = "overview"
    @State private var selectedStepID: String?
    @State private var inventoryFilter = "all"
    @State private var categoryFilter = "all"
    @State private var activityState = SkillsWorkspaceActivityState(skillID: nil)
    @State private var compactShowsDetail = false
    @State private var authoringAvailable = false
    @State private var catalogRevision = ""
    @State private var enabledSkillCount = 0
    @State private var attentionSkillCount = 0
    @State private var categoryOptions = ["finance", "home", "surveillance"]
    @State private var showingCreator = false
    @State private var voiceDraft: SkillsStore.VoiceDraftRequest?
    @State private var examplePreview: JSONValue?
    @State private var exampleLoadingID: String?
    @State private var examplePreviewError: String?
    @State private var versionEvidence: JSONValue?
    @State private var versionEvidenceError: String?
    @State private var versionsLoading = false
    @State private var accessibilityStatus = SkillsWorkspaceAccessibilityStatus()
    @State private var refreshActionSignal = 0
    @State private var backActionSignal = 0
    @State private var retryActionSignal = 0
    @State private var loadMoreActionSignal = 0
    @State private var actionHandlerOwner = UUID()

    init(detailOnly: Bool = false, coordinator: ConsoleActionCoordinator? = nil) {
        self.detailOnly = detailOnly
        self.coordinator = coordinator
    }

    private var activityTaskKey: String {
        // Selection only changes the activity/version task identity while one
        // of those tabs is visible. Restarting an otherwise idle task on every
        // overview selection adds scheduling and cancellation work to the
        // catalog's wide-layout selection path.
        let selectedSkill = activeTab == "activity" || activeTab == "versions"
            ? selectedID ?? ""
            : ""
        let selectedRun = activeTab == "activity" ? activityState.selectedRunID ?? "" : ""
        let retryNonce = activeTab == "activity" ? activityState.retryNonce : 0
        return "\(activeTab)|\(selectedSkill)|\(selectedRun)|\(scenePhase)|\(SkillsWorkspacePresentationPolicy.activityConnectionKey(client.state))|\(retryNonce)"
    }

    // Selection lives in the shared observable store. Reading it directly
    // keeps the rendered workspace synchronized without a second @State copy
    // waiting for an onChange callback after voice/console navigation.
    private var selectedID: String? { skillsStore.selectedSkillID }
    private var selectedCard: SkillsCatalogCard? { cards.first { $0.id == selectedID } }
    private var filteredCards: [SkillsCatalogCard] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        if query.isEmpty, inventoryFilter == "all", categoryFilter == "all" {
            return cards
        }
        return cards.filter { card in
            let matchesSearch = query.isEmpty
                || card.name.localizedCaseInsensitiveContains(query)
                || card.description.localizedCaseInsensitiveContains(query)
                || card.category.localizedCaseInsensitiveContains(query)
            let matchesState: Bool = switch inventoryFilter {
            case "installed": card.installation == "installed"
            case "proposed": card.installation == "proposed"
            case "needs_attention": SkillsWorkspacePresentationPolicy.needsAttention(
                installation: card.installation,
                readiness: card.readiness,
                verification: card.verification,
                enabled: card.enabled,
                readinessReasons: card.readinessReasons
            )
            default: true
            }
            let matchesCategory = categoryFilter == "all" || card.category == categoryFilter
            return matchesSearch && matchesState && matchesCategory
        }
    }

    var body: some View {
        GeometryReader { geometry in
            workspaceContent(width: geometry.size.width)
        }
        .frame(minWidth: 500, minHeight: 360)
        .sheet(isPresented: $showingCreator, onDismiss: { voiceDraft = nil }) {
            SkillCreatorSheet(client: client, catalogRevision: catalogRevision, voiceDraft: voiceDraft)
        }
        .onChange(of: skillsStore.pendingVoiceDraft) { _, _ in presentPendingVoiceDraftIfReady() }
        .onChange(of: catalogRevision) { _, _ in presentPendingVoiceDraftIfReady() }
    }

    private func workspaceContent(width: CGFloat) -> some View {
        workspacePresentation(width: width)
            .background(AppTheme.bg)
            .task { await refresh() }
            .onChange(of: skillsStore.revision) { _, _ in applySharedNavigation() }
            .onChange(of: skillsStore.navigationRequestRevision) { _, _ in
                // A repeated voice selection is still a navigation request.
                // In compact mode the user may have returned to the library
                // while the selected skill ID/tab remained unchanged, so the
                // ordinary state revision would not reveal that intent.
                if !detailOnly, skillsStore.selectedSkillID != nil {
                    compactShowsDetail = true
                }
            }
            .onChange(of: skillsStore.selectedExampleID) { _, exampleID in
                guard let exampleID else {
                    examplePreview = nil
                    exampleLoadingID = nil
                    examplePreviewError = nil
                    return
                }
                Task { await loadExamplePreview(exampleID) }
            }
            .onChange(of: selectedID) { _, _ in
                if let exampleID = skillsStore.selectedExampleID {
                    Task { await loadExamplePreview(exampleID) }
                }
            }
            .onChange(of: selectedStepID) { _, stepID in
                announceProcessStepSelection(stepID)
            }
            .onChange(of: width) { oldWidth, newWidth in
                if SkillsWorkspacePresentationPolicy.usesSplitLayout(
                    width: oldWidth, dynamicTypeSize: dynamicTypeSize
                ), !SkillsWorkspacePresentationPolicy.usesSplitLayout(
                    width: newWidth, dynamicTypeSize: dynamicTypeSize
                ), selectedID != nil {
                    compactShowsDetail = true
                }
            }
            .onAppear(perform: prepareSkillsWorkspace)
            .onDisappear(perform: unregisterSkillsWorkspaceActions)
            .onChange(of: refreshActionSignal) { _, _ in Task { await refresh() } }
            .onChange(of: backActionSignal) { _, _ in compactShowsDetail = false }
            .onChange(of: retryActionSignal) { _, _ in retryActivity() }
            .onChange(of: loadMoreActionSignal) { _, _ in Task { await loadMoreActivity() } }
            .onChange(of: search) { _, value in
                if let coordinator {
                    _ = coordinator.executePointer(.skillsSearch, args: ["query": .string(value)])
                } else { _ = skillsStore.setSearch(value) }
            }
            .onChange(of: inventoryFilter) { _, value in
                applySharedFilters(state: value, category: categoryFilter)
            }
            .onChange(of: categoryFilter) { _, value in
                applySharedFilters(state: inventoryFilter, category: value)
            }
            .onChange(of: activeTab) { _, value in
                if let coordinator {
                    _ = coordinator.executePointer(.skillTab, args: ["tab": .string(value)])
                } else { _ = skillsStore.selectTab(value) }
            }
            .task(id: activityTaskKey) {
                await loadVisibleTabData()
            }
    }

    @ViewBuilder
    private func workspacePresentation(width: CGFloat) -> some View {
        if detailOnly {
            detailPane(compact: false).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if isSelectedDetailOnSupportingDisplay {
            ContentUnavailableView {
                Label("Skill details are on the supporting display", systemImage: "display")
            } actions: {
                Button("Return skill details here") {
                    workspace.returnSkillDetailsToMain()
                    drawer.placementRef?.closeDisplay()
                }
            }
        } else if SkillsWorkspacePresentationPolicy.usesSplitLayout(
            width: width, dynamicTypeSize: dynamicTypeSize
        ) {
            HStack(spacing: 0) {
                libraryPane.frame(width: 280)
                Divider()
                detailPane(compact: false).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else if compactShowsDetail, selectedCard != nil {
            detailPane(compact: true).frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            libraryPane.frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var libraryPane: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Skills").font(.title2.weight(.semibold))
                Text("\(cards.count) skills · \(enabledSkillCount) enabled · \(attentionSkillCount) need attention")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                    .accessibilityLabel("\(cards.count) skills, \(enabledSkillCount) enabled, \(attentionSkillCount) need attention")
            }
            TextField("Search skills", text: $search)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Search skills by name, purpose, or category")
            filterControls
            if let errorMessage {
                Text(errorMessage).font(.callout).foregroundStyle(AppTheme.red)
            }
            List(filteredCards) { card in
                cardRow(card)
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            Button("Refresh skills") {
                if let coordinator { _ = coordinator.executePointer(.skillsRefresh) }
                else { Task { await refresh() } }
            }
                .disabled(loading)
            if SkillsWorkspacePresentationPolicy.canOpenCreator(
                authoringAvailable: authoringAvailable, catalogRevision: catalogRevision
            ) {
                Button {
                    if let coordinator { _ = coordinator.executePointer(.skillCreatorOpen) }
                    else { showingCreator = true }
                } label: {
                    Label("Create a skill", systemImage: "wand.and.stars")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .accessibilityHint("Draft in the configured disposable sandbox and review the exact changes before opening a pull request")
            }
        }
        .padding(16)
    }

    private var filterControls: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    filterPickers
                }
            } else {
                HStack(spacing: 8) {
                    filterPickers
                }
            }
        }
    }

    @ViewBuilder
    private var filterPickers: some View {
        Picker("Filter skills", selection: $inventoryFilter) {
            Text("All").tag("all")
            Text("Installed").tag("installed")
            Text("Proposed").tag("proposed")
            Text("Needs attention").tag("needs_attention")
        }
        .labelsHidden()
        .accessibilityLabel("Filter skills by state")
        Picker("Skill category", selection: $categoryFilter) {
            Text("All categories").tag("all")
            ForEach(categoryOptions, id: \.self) { category in
                Text(category.capitalized).tag(category)
            }
        }
        .labelsHidden()
        .accessibilityLabel("Filter skills by category")
    }

    private func loadVisibleTabData() async {
        guard selectedID != nil else { return }
        if activeTab == "activity" {
            await refreshVisibleActivity()
        } else if activeTab == "versions" {
            await loadVersionEvidence()
        }
    }

    private func prepareSkillsWorkspace() {
        if skillsStore.selectedSkillID != nil { compactShowsDetail = true }
        registerSharedActions()
    }

    private func unregisterSkillsWorkspaceActions() {
        coordinator?.unregisterSkillWorkspaceActionHandler(owner: actionHandlerOwner)
    }

    private func cardRow(_ card: SkillsCatalogCard) -> some View {
        SkillsCatalogCardButton(card: card, isSelected: selectedID == card.id,
            differentiateWithoutColor: differentiateWithoutColor,
            reduceTransparency: reduceTransparency, store: skillsStore,
            coordinator: coordinator)
        .equatable()
    }

    @ViewBuilder
    private func detailPane(compact: Bool) -> some View {
        if let errorMessage, cards.isEmpty {
            ContentUnavailableView("Skills unavailable", systemImage: "square.grid.2x2",
                                   description: Text(errorMessage))
        } else if let card = selectedCard {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top) {
                    if compact {
                        Button {
                            if let coordinator { _ = coordinator.executePointer(.skillBack) }
                            else { compactShowsDetail = false }
                        } label: {
                            Label("Skills", systemImage: "chevron.left")
                        }
                        .accessibilityLabel("Back to skills library")
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        Text(card.name).font(.title2.weight(.semibold))
                        Text(card.description).foregroundStyle(AppTheme.textDim)
                    }
                    Spacer()
                    if !detailOnly, selectedID != nil,
                       SkillsWorkspacePresentationPolicy.canTransferToSupportingDisplay(screenCount: NSScreen.screens.count) {
                        Button("Show on display") {
                            if let coordinator, let selectedID {
                                _ = coordinator.executePointer(.skillDisplayTransfer, target: selectedID)
                            } else { transferSelectedSkillToDisplay() }
                        }
                            .accessibilityLabel("Show selected skill details on the supporting display")
                            .accessibilityHint("Moves the current skill detail view to the other display")
                    }
                    if !detailOnly {
                        Button("Conversation") {
                            if let coordinator { _ = coordinator.executePointer(.viewSet, target: "conversation") }
                            else { workspace.returnToConversation() }
                        }
                            .accessibilityHint("Returns to the voice conversation view")
                    }
                }
                if let errorMessage {
                    Text(errorMessage).font(.callout).foregroundStyle(AppTheme.red)
                }
                HStack(spacing: 10) {
                    if dynamicTypeSize.isAccessibilitySize {
                        VStack(alignment: .leading, spacing: 8) {
                            statusBadge(card.enabled ? "Enabled" : "Disabled", good: card.enabled)
                            statusBadge("Readiness: \(card.readiness)", good: false)
                            statusBadge("Verification: \(card.verification)", good: false)
                        }
                    } else {
                        statusBadge(card.enabled ? "Enabled" : "Disabled", good: card.enabled)
                        statusBadge("Readiness: \(card.readiness)", good: false)
                        statusBadge("Verification: \(card.verification)", good: false)
                    }
                    if let revision = card.revision {
                        Text(String(revision.prefix(12))).font(.caption.monospaced())
                            .foregroundStyle(AppTheme.textDim)
                            .help("Full package revision \(revision)")
                    }
                }
                Group {
                    if dynamicTypeSize.isAccessibilitySize {
                        Picker("Skill detail", selection: $activeTab) {
                            detailTabOptions
                        }
                        .pickerStyle(.menu)
                        .accessibilityValue(activeTab.capitalized)
                    } else {
                        Picker("Skill detail", selection: $activeTab) {
                            detailTabOptions
                        }
                        .pickerStyle(.segmented)
                        .accessibilityValue(activeTab.capitalized)
                    }
                }
                ScrollViewReader { proxy in
                    ScrollView {
                        switch activeTab {
                        case "process": processContent
                        case "activity": activityContent
                        case "versions": versionsContent
                        default: overviewContent
                        }
                    }
                    .onChange(of: selectedStepID) { _, stepID in
                        guard let stepID else { return }
                        if reduceMotion {
                            proxy.scrollTo(stepID, anchor: .center)
                        } else {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                proxy.scrollTo(stepID, anchor: .center)
                            }
                        }
                    }
                }
                .accessibilityIdentifier("skills.detail.scroll")
            }
            .padding(18)
        } else if loading {
            ProgressView("Loading skills…").frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if !cards.isEmpty {
            ContentUnavailableView("Select a skill", systemImage: "square.grid.2x2",
                                   description: Text("Choose a skill from the library to inspect its purpose, readiness, and intended process."))
        } else {
            if ["home", "surveillance", "finance"].contains(categoryFilter),
               search.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                ContentUnavailableView("No \(categoryFilter.capitalized) skills installed",
                    systemImage: "square.grid.2x2",
                    description: Text("This roadmap area has no installed skills yet. No integration is active here."))
            } else {
                ContentUnavailableView("No skills found", systemImage: "square.grid.2x2",
                    description: Text("No skills match the current search and filters. Change the filters or refresh the library."))
            }
        }
    }

    @ViewBuilder
    private var detailTabOptions: some View {
        Text("Overview").tag("overview")
        Text("Process").tag("process")
        Text("Activity").tag("activity")
        Text("Versions").tag("versions")
    }

    private var isSelectedDetailOnSupportingDisplay: Bool {
        guard let selectedSkillID = skillsStore.selectedSkillID else { return false }
        return display.isPresented(.skillDetail(selectedSkillID), selection: workspace.supportingContent)
    }

    private func transferSelectedSkillToDisplay() {
        guard SkillsWorkspacePresentationPolicy.canTransferToSupportingDisplay(screenCount: NSScreen.screens.count),
              let skillID = skillsStore.selectedSkillID,
              workspace.sendToDisplay(.skillDetail(skillID)) else { return }
        drawer.placementRef?.openDisplay()
    }

    private var overviewContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Overview").font(.headline)
            if let detail {
                metadataRow("Category", detail["category"]?.stringValue ?? "general")
                metadataRow("Version", detail["version"]?.stringValue ?? "Unversioned")
                metadataRow("Origin", detail["source"]?["kind"]?.stringValue ?? "Unknown")
                metadataRow("Required tools", stringList(detail["required_tools"]))
                metadataRow("Required credentials", stringList(detail["required_credentials"]))
                metadataRow("Readiness details", readinessReasons(detail["readiness_reasons"]))
                relatedWorkflowsContent
                if let card = selectedCard, !card.exampleIDs.isEmpty {
                    Divider().padding(.vertical, 4)
                    Text("Synthetic matcher examples").font(.headline)
                    Text("Preview routing fixtures only. This does not run the skill or call a model.")
                        .font(.caption).foregroundStyle(AppTheme.textDim)
                    ForEach(card.exampleIDs, id: \.self) { exampleID in
                        Button {
                            if let coordinator, let selectedID {
                                _ = coordinator.executePointer(.skillExamplePreview, target: exampleID,
                                                               args: ["skill_id": .string(selectedID)])
                            } else { _ = skillsStore.selectExample(exampleID) }
                        } label: {
                            Label(exampleID, systemImage: skillsStore.selectedExampleID == exampleID
                                  ? "eye.fill" : "eye")
                        }
                        .buttonStyle(.bordered)
                        .accessibilityHint("Shows this reviewed synthetic matcher example")
                    }
                    if let exampleLoadingID {
                        ProgressView("Loading \(exampleLoadingID)…")
                    } else if let examplePreviewError {
                        Text(examplePreviewError).font(.callout).foregroundStyle(AppTheme.textDim)
                    } else if let examplePreview {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Example request").font(.subheadline.weight(.semibold))
                            Text(examplePreview["request"]?.stringValue ?? "")
                                .textSelection(.enabled)
                            Text("Expected routing: \(examplePreview["expect_selected"]?.boolValue == true ? "this skill" : "another skill")")
                                .font(.caption.weight(.medium)).foregroundStyle(AppTheme.textDim)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            reduceTransparency ? AppTheme.panelOpaque : AppTheme.panel.opacity(0.65),
                            in: RoundedRectangle(cornerRadius: 10)
                        )
                        .accessibilityElement(children: .combine)
                    }
                }
                if let note = detail["source"]?["adaptation_notes"]?.stringValue {
                    Text(note).font(.callout).foregroundStyle(AppTheme.textDim)
                }
            } else {
                Text("Loading validated skill detail…").foregroundStyle(AppTheme.textDim)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
    }

    @ViewBuilder
    private var relatedWorkflowsContent: some View {
        let workflowIDs = detail?["related_workflow_ids"]?.arrayValue?.compactMap(\.stringValue) ?? []
        if workflowIDs.isEmpty {
            metadataRow("Related workflows", "None linked")
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text("Related workflows").font(.caption).foregroundStyle(AppTheme.textDim)
                ForEach(workflowIDs, id: \.self) { workflowID in
                    Button {
                        Task {
                            guard await workspace.workflows.openRelatedWorkflow(workflowID, api: client.admin) else {
                                return
                            }
                            workspace.openWorkflows()
                        }
                    } label: {
                        Label(workspace.workflows.workflowName(for: workflowID) ?? workflowID,
                              systemImage: "arrow.up.right.square")
                    }
                    .buttonStyle(.bordered)
                    .accessibilityHint("Opens this related workflow in the separate Workflows view")
                }
            }
        }
    }

    @ViewBuilder
    private var processContent: some View {
        if let nodes = detail?["process_nodes"]?.arrayValue, !nodes.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                Text("Intended process").font(.headline).padding(.bottom, 12)
                ForEach(Array(nodes.enumerated()), id: \.offset) { index, node in
                    let stepID = node["step_id"]?.stringValue ?? "step-\(index + 1)"
                    let isSelected = selectedStepID == stepID
                    HStack(alignment: .top, spacing: 12) {
                        VStack(spacing: 4) {
                            Text(String(index + 1)).font(.caption.weight(.bold))
                                .frame(width: 26, height: 26)
                                .background(AppTheme.accent.opacity(0.2), in: Circle())
                            if index + 1 < nodes.count {
                                Rectangle().fill(AppTheme.textDim.opacity(0.45))
                                    .frame(width: 1, height: 22)
                            }
                        }
                        VStack(alignment: .leading, spacing: 6) {
                            Button {
                                setSelectedStep(isSelected ? nil : stepID)
                            } label: {
                                VStack(alignment: .leading, spacing: 5) {
                                    HStack {
                                        Text(node["title"]?.stringValue ?? "Step")
                                            .font(.headline)
                                        if isSelected && differentiateWithoutColor {
                                            Text("Selected")
                                                .font(.caption.weight(.semibold))
                                        }
                                        Spacer()
                                        Image(systemName: isSelected ? "chevron.up" : "chevron.down")
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(AppTheme.textDim)
                                    }
                                    Text(node["description"]?.stringValue ?? "")
                                        .foregroundStyle(AppTheme.textDim)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .id(stepID)
                            .accessibilityIdentifier("skills.process.step.\(stepID)")
                            .accessibilityAddTraits(isSelected ? .isSelected : [])
                            .accessibilityValue(isSelected ? "Expanded" : "Collapsed")
                            .accessibilityHint(isSelected ? "Hides step details" : "Shows inputs, outputs, tools, approvals, and success criteria")
                            if isSelected {
                                stepDetails(node, nodes: nodes)
                            }
                            if let edges = node["edges"]?.arrayValue, !edges.isEmpty,
                               SkillsWorkspacePresentationPolicy.showsEdgeChoices(
                                processKind: detail?["process_kind"]?.stringValue
                               ) {
                                VStack(alignment: .leading, spacing: 4) {
                                    ForEach(Array(edges.enumerated()), id: \.offset) { _, edge in
                                        let destination = edge["to"]?.stringValue ?? "next step"
                                        let title = nodes.first { $0["step_id"]?.stringValue == destination }?["title"]?.stringValue ?? destination
                                        Button {
                                            setSelectedStep(destination)
                                        } label: {
                                            Label("\(edge["condition"]?.stringValue ?? "Continue") → \(title)", systemImage: "arrow.turn.down.right")
                                                .font(.caption).foregroundStyle(AppTheme.accent)
                                        }
                                        .buttonStyle(.plain)
                                        .accessibilityHint("Opens the destination step")
                                    }
                                }
                                .padding(.top, 4)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(
                            reduceTransparency
                                ? AppTheme.panelOpaque
                                : (isSelected ? AppTheme.accent.opacity(0.12) : AppTheme.panel.opacity(0.55)),
                            in: RoundedRectangle(cornerRadius: 12)
                        )
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(
                            isSelected ? AppTheme.accent.opacity(reduceTransparency ? 1 : 0.75) : .clear,
                            lineWidth: isSelected && differentiateWithoutColor ? 2 : 1
                        ))
                    }
                    .padding(.bottom, 10)
                }
                Text("This is the reviewed intended process. Actual step completion appears separately in Activity and is never inferred from this map.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
                    .padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
        } else {
            unavailableContent("No reviewed step map is available for this skill.")
        }
    }

    private func stepDetails(_ node: JSONValue, nodes: [JSONValue]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            metadataRow("Inputs", stringList(node["inputs"]))
            metadataRow("Outputs", stringList(node["outputs"]))
            metadataRow("Tools", stringList(node["tools"]))
            metadataRow("Approval", node["approval"]?.stringValue ?? "None declared")
            let criteria = node["success_criteria"]?.arrayValue?.compactMap(\.stringValue) ?? []
            if !criteria.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Success criteria").font(.caption.weight(.semibold))
                    ForEach(Array(criteria.enumerated()), id: \.offset) { _, criterion in
                        Text("• \(criterion)").font(.caption).foregroundStyle(AppTheme.textDim)
                    }
                }
            }
            let edges = node["edges"]?.arrayValue ?? []
            if SkillsWorkspacePresentationPolicy.showsLinearNext(
                processKind: detail?["process_kind"]?.stringValue
            ) {
                if let destination = edges.first?["to"]?.stringValue,
                   let nextTitle = nodes.first(where: { $0["step_id"]?.stringValue == destination })?["title"]?.stringValue {
                    Button {
                        setSelectedStep(destination)
                    } label: {
                        Label("Next step: \(nextTitle)", systemImage: "arrow.down.circle")
                    }
                    .accessibilityHint("Opens and scrolls to the next intended process step")
                } else {
                    Label("End of process", systemImage: "checkmark.circle")
                        .font(.caption).foregroundStyle(AppTheme.textDim)
                        .accessibilityLabel("This is the final intended process step")
                }
            }
        }
        .padding(.top, 4)
        .accessibilityElement(children: .contain)
    }

    private var activityContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Observed activity").font(.headline)
            Text("This timeline contains recorded events only. A process step without a trusted event remains unknown.")
                .font(.caption).foregroundStyle(AppTheme.textDim)
            if let activityError = activityState.error {
                VStack(alignment: .leading, spacing: 6) {
                    Text(activityError).font(.callout).foregroundStyle(AppTheme.red)
                    Button("Retry activity") { requestActivityRetry() }
                    .accessibilityHint("Retries the recorded activity request without changing the selected run")
                }
            }
            if !activityState.runs.isEmpty {
                Picker("Skill run", selection: Binding(
                    get: { activityState.selectedRunID ?? activityState.runs.first?.runID ?? "" },
                    set: { selectActivityRun($0) }
                )) {
                    ForEach(activityState.runs) { run in
                        Text("\(run.startedAt) · \(run.status)").tag(run.runID)
                    }
                }
                .accessibilityLabel("Select a skill execution run")
            }
            if let activityPage = activityState.page, !activityState.events.isEmpty {
                if activityState.events.contains(where: { $0.type == "protected_activity" }) {
                    Label("Protected activity", systemImage: "lock.fill")
                        .font(.subheadline.weight(.semibold))
                        .accessibilityLabel("Protected activity details are hidden")
                } else {
                    ForEach(activityState.events) { event in
                        activityEventRow(event)
                    }
                }
                if activityPage.truncated {
                    Label("Activity history reached its display limit", systemImage: "ellipsis.circle")
                        .font(.caption).foregroundStyle(AppTheme.textDim)
                }
                if activityState.hasMore {
                    Button("Load more activity") { requestLoadMoreActivity() }
                        .accessibilityHint("Loads the next page of recorded skill events")
                }
                Text("Step completion is not recorded for steps without a matching trusted event.")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
            } else if activityState.runs.isEmpty && activityState.error == nil {
                ContentUnavailableView("No skill trace recorded", systemImage: "clock.arrow.circlepath",
                                       description: Text("Only runs with recorded skill traces appear in this list. Legacy and uninstrumented runs are not shown as completed."))
            } else if let activityPage = activityState.page {
                ContentUnavailableView(
                    Self.activityEmptyTitle(traceStatus: activityPage.traceStatus),
                    systemImage: "clock.arrow.circlepath",
                    description: Text(Self.activityEmptyDescription(traceStatus: activityPage.traceStatus)),
                )
            } else if activityState.page == nil && activityState.error == nil {
                ProgressView("Loading activity…")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
    }

    private func activityEventRow(_ event: SkillActivityEvent) -> some View {
        let detailRevision = detail?["revision"]?.stringValue ?? selectedCard?.revision
        let eventRevisionMatchesDetail = event.skillRevision != nil
            && event.skillRevision == detailRevision
        let stepTitle = eventRevisionMatchesDetail
            ? detail?["process_nodes"]?.arrayValue?.first {
                $0["step_id"]?.stringValue == event.stepID
            }?["title"]?.stringValue
            : nil
        let hasToolCallEvidence = event.evidenceRefs.contains { $0.kind == "tool_call_id" }
        let title = Self.activityEventTitle(
            eventType: event.type, hasToolCallEvidence: hasToolCallEvidence,
            stepTitle: stepTitle, status: event.status, stepID: event.stepID,
        )
        let status = Self.activityEventStatus(
            eventType: event.type, status: event.status,
            hasToolCallEvidence: hasToolCallEvidence,
        )
        let revisionLabel = Self.activityRevisionLabel(
            eventRevision: event.skillRevision,
            detailRevision: detailRevision,
            hasStep: event.stepID != nil,
        )
        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: event.type == "protected_activity" ? "lock.fill" : "circle.inset.filled")
                .foregroundStyle(event.status == "failed" ? AppTheme.red : AppTheme.accent)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text("\(status)\(revisionLabel) · \(event.occurredAt)")
                    .font(.caption).foregroundStyle(AppTheme.textDim)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(
            AppTheme.panel.opacity(reduceTransparency ? 1 : 0.55),
            in: RoundedRectangle(cornerRadius: 10)
        )
        .accessibilityElement(children: .combine)
    }

    static func activityEventTitle(
        eventType: String, hasToolCallEvidence: Bool, stepTitle: String?,
        status: String = "unknown", stepID: String? = nil,
    ) -> String {
        func fallback(_ title: String) -> String {
            // Historical IDs are useful when the current package no longer
            // has the step title, but this value comes from the activity API.
            // Keep arbitrary task text or transport diagnostics out of the
            // visible timeline by accepting only bounded opaque identifiers.
            guard let stepID, (1...64).contains(stepID.unicodeScalars.count),
                  stepID.unicodeScalars.allSatisfy({
                      $0.isASCII && (CharacterSet.alphanumerics.contains($0)
                          || "._:-".unicodeScalars.contains($0))
                  }) else { return title }
            return "\(title): \(stepID)"
        }
        switch eventType {
        case "skill_selected": return "Skill selected"
        case "skill_resource_read": return "Skill instructions loaded"
        case "skill_step_started":
            if hasToolCallEvidence {
                return stepTitle.map { "Tool call started for: \($0)" }
                    ?? fallback("Step tool call started")
            } else {
                return stepTitle.map { "Started: \($0)" } ?? fallback("Process step started")
            }
        case "skill_step_finished":
            if status == "failed" {
                return hasToolCallEvidence
                    ? (stepTitle.map { "Tool call failed for: \($0)" }
                        ?? fallback("Step tool call failed"))
                    : (stepTitle.map { "Failed: \($0)" } ?? fallback("Process step failed"))
            }
            if hasToolCallEvidence {
                return stepTitle.map { "Tool call returned for: \($0)" }
                    ?? fallback("Step tool call returned")
            } else {
                return stepTitle.map { "Outcome unknown for: \($0)" }
                    ?? fallback("Process step outcome unknown")
            }
        case "skill_step_skipped":
            return stepTitle.map { "Skipped: \($0)" } ?? fallback("Process step skipped")
        case "skill_selection_refused": return "Skill selection refused"
        case "truncated": return "Activity history truncated"
        default: return "Recorded skill activity"
        }
    }

    static func activityRevisionLabel(
        eventRevision: String?, detailRevision: String?, hasStep: Bool,
    ) -> String {
        guard hasStep else { return "" }
        guard let eventRevision else { return " · Package revision unavailable" }
        guard eventRevision != detailRevision else { return "" }
        return " · Historical package \(eventRevision.prefix(8))"
    }

    static func activityEventStatus(
        eventType: String, status: String, hasToolCallEvidence: Bool,
    ) -> String {
        if status == "unknown" {
            if eventType == "skill_step_finished" && hasToolCallEvidence {
                return "Step outcome not validated"
            }
            return "Outcome not recorded"
        }
        return status.capitalized
    }

    static func activityEmptyTitle(traceStatus: String) -> String {
        traceStatus == "recorded" ? "No events on this page" : "No skill trace recorded"
    }

    static func activityEmptyDescription(traceStatus: String) -> String {
        traceStatus == "recorded"
            ? "No recorded skill activity is available in this page."
            : "This run has no trusted skill trace. Its process outcome is unknown, not completed."
    }

    static func activityResponseIsCurrent(
        requestedRunID: String, selectedRunID: String?,
        requestedGeneration: UInt64, selectedGeneration: UInt64,
        taskCancelled: Bool,
    ) -> Bool {
        !taskCancelled && selectedRunID == requestedRunID
            && selectedGeneration == requestedGeneration
    }

    /// Combines activity pages without allowing another run or an overlapping
    /// / out-of-order response to corrupt the selected run's visible trace.
    /// Existing events win duplicate IDs; for duplicate sequence numbers the
    /// first event in that stable ordering is retained so output is strict.
    static func mergeActivityEvents(
        _ current: [SkillActivityEvent],
        with incoming: [SkillActivityEvent],
        selectedRunID: String,
    ) -> [SkillActivityEvent] {
        let candidates = (current + incoming).enumerated()
            .filter { $0.element.runID == selectedRunID }
            .sorted {
                if $0.element.sequence != $1.element.sequence {
                    return $0.element.sequence < $1.element.sequence
                }
                return $0.offset < $1.offset
            }

        var eventIDs = Set<String>()
        var lastSequence: Int?
        var merged: [SkillActivityEvent] = []
        for (_, event) in candidates {
            guard eventIDs.insert(event.eventID).inserted,
                  lastSequence.map({ event.sequence > $0 }) ?? true else { continue }
            merged.append(event)
            lastSequence = event.sequence
        }
        return merged
    }

    @MainActor
    private func refreshVisibleActivity() async {
        guard let skillID = selectedID else { return }
        announceAccessibilityStatus(.activity, .loading)
        repeat {
            guard !Task.isCancelled else { return }
            let selectedRunAtRequestStart = activityState.selectedRunID
            let generationAtRunListRequest = activityState.selectionGeneration
            do {
                let page = try await AdminAPI(config: client.config).skillRuns(id: skillID)
                guard !Task.isCancelled, selectedID == skillID,
                      generationAtRunListRequest == activityState.selectionGeneration else { return }
                activityState.runs = page.runs
                skillsStore.updateRuns(skillID: skillID, runs: activityState.runs)
                if let chosen = activityState.selectedRunID,
                   !activityState.runs.contains(where: { $0.runID == chosen }) {
                    activityState.selectRun(nil)
                    skillsStore.clearRun()
                }
                if activityState.selectedRunID == nil {
                    if let first = activityState.runs.first?.runID { selectActivityRun(first) }
                }
                if let runID = activityState.selectedRunID {
                    if activityState.loadedRunID != runID {
                        activityState.events = []
                        activityState.page = nil
                        activityState.hasMore = false
                        activityState.loadedRunID = runID
                    }
                    let generationAtActivityRequest = activityState.selectionGeneration
                    let afterSeq = activityState.events.last?.sequence ?? 0
                    let page = try await AdminAPI(config: client.config)
                        .skillActivity(runID: runID, afterSeq: afterSeq)
                    guard selectedID == skillID,
                          Self.activityResponseIsCurrent(
                            requestedRunID: runID, selectedRunID: activityState.selectedRunID,
                            requestedGeneration: generationAtActivityRequest,
                            selectedGeneration: activityState.selectionGeneration,
                            taskCancelled: Task.isCancelled,
                          ) else { return }
                    activityState.events = Self.mergeActivityEvents(
                        activityState.events, with: page.events, selectedRunID: runID,
                    )
                    activityState.page = page
                    activityState.hasMore = page.hasMore
                } else {
                    activityState.page = nil
                    activityState.events = []
                    activityState.hasMore = false
                    activityState.loadedRunID = nil
                }
                activityState.error = nil
                announceAccessibilityStatus(.activity, .loaded)
            } catch {
                guard !Task.isCancelled, selectedID == skillID else { return }
                guard selectedRunAtRequestStart == nil
                        || activityState.selectedRunID == selectedRunAtRequestStart,
                      generationAtRunListRequest == activityState.selectionGeneration else { return }
                activityState.error = activityState.events.isEmpty
                    ? "Could not load recorded skill activity. Retry or check Mortimer's connection."
                    : "Could not refresh recorded skill activity. The last received trace remains visible; retry when Mortimer is connected."
                activityState.retryLoadsMore = false
                announceAccessibilityStatus(.activity, .failed)
                return
            }
            let runStatus = activityState.runs.first(where: {
                $0.runID == activityState.selectedRunID
            })?.status
            guard let interval = SkillsWorkspacePresentationPolicy.activityRefreshInterval(
                skillID: skillID, runStatus: runStatus, sceneIsActive: scenePhase == .active
            ) else {
                return
            }
            do {
                try await Task.sleep(for: .seconds(interval))
            } catch {
                return
            }
        } while !Task.isCancelled
    }

    @MainActor
    private func loadMoreActivity() async {
        guard let skillID = selectedID, let runID = activityState.selectedRunID,
              let afterSeq = activityState.events.last?.sequence else { return }
        let generationAtRequest = activityState.selectionGeneration
        announceAccessibilityStatus(.activity, .loading)
        do {
            let page = try await AdminAPI(config: client.config)
                .skillActivity(runID: runID, afterSeq: afterSeq)
            guard selectedID == skillID,
                  Self.activityResponseIsCurrent(
                    requestedRunID: runID, selectedRunID: activityState.selectedRunID,
                    requestedGeneration: generationAtRequest,
                    selectedGeneration: activityState.selectionGeneration,
                    taskCancelled: Task.isCancelled,
                  ) else { return }
            activityState.events = Self.mergeActivityEvents(
                activityState.events, with: page.events, selectedRunID: runID,
            )
            activityState.page = page
            activityState.hasMore = page.hasMore
            activityState.error = nil
            announceAccessibilityStatus(.activity, .loaded)
        } catch {
            guard selectedID == skillID,
                  Self.activityResponseIsCurrent(
                    requestedRunID: runID, selectedRunID: activityState.selectedRunID,
                    requestedGeneration: generationAtRequest,
                    selectedGeneration: activityState.selectionGeneration,
                    taskCancelled: Task.isCancelled,
                  ) else { return }
            activityState.error = "Could not load the next activity page. Retry when Mortimer is connected."
            activityState.retryLoadsMore = true
            announceAccessibilityStatus(.activity, .failed)
        }
    }

    private func statusBadge(_ title: String, good: Bool) -> some View {
        Label(title, systemImage: good ? "checkmark.circle.fill" : "info.circle")
            .font(.caption)
            .foregroundStyle(good ? AppTheme.green : AppTheme.textDim)
            .padding(.horizontal, 9).padding(.vertical, 5)
            .background(
                reduceTransparency ? AppTheme.panelOpaque : AppTheme.panel.opacity(0.65),
                in: Capsule()
            )
    }

    private func metadataRow(_ title: String, _ value: String) -> some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.weight(.semibold))
                    Text(value.isEmpty ? "None declared" : value)
                        .foregroundStyle(AppTheme.textDim)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                HStack(alignment: .firstTextBaseline) {
                    Text(title).font(.subheadline.weight(.semibold))
                        .frame(width: 150, alignment: .leading)
                    Text(value.isEmpty ? "None declared" : value)
                        .foregroundStyle(AppTheme.textDim)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
    }

    private func unavailableContent(_ message: String) -> some View {
        ContentUnavailableView("Not available yet", systemImage: "clock",
                               description: Text(message))
    }

    @ViewBuilder
    private var versionsContent: some View {
        if versionsLoading, versionEvidence == nil {
            ProgressView("Loading version evidence…")
        } else if let versionEvidence {
            let installed = versionEvidence["installed"]
            let registry = versionEvidence["registry"]
            VStack(alignment: .leading, spacing: 12) {
                GroupBox("Installed package") {
                    VStack(alignment: .leading, spacing: 7) {
                        versionRow("Manifest version", value: installed?["declared_version"]?.stringValue ?? "Not declared")
                        versionRow("Package revision (SHA-256)", value: installed?["package_revision"]?.stringValue ?? "Unavailable", monospaced: true)
                        versionRow("Enabled in registry", value: installed?["enabled"]?.boolValue == true ? "Yes" : "No")
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Runtime registry pin") {
                    VStack(alignment: .leading, spacing: 7) {
                        versionRow("Pin state", value: registry?["pin_state"]?.stringValue ?? "Unknown")
                        versionRow("Pinned package revision", value: registry?["active_pin"]?.stringValue ?? "No digest pin", monospaced: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Candidate request evidence") {
                    let candidates = versionEvidence["candidates"]?.arrayValue ?? []
                    if candidates.isEmpty {
                        Text("No caller-owned candidate requests are recorded for this skill.")
                            .foregroundStyle(AppTheme.textDim)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(Array(candidates.enumerated()), id: \.offset) { entry in
                                let candidate = entry.element
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("\(candidate["operation"]?.stringValue ?? "Request") · \(candidate["state"]?.stringValue ?? "unknown state")")
                                        .font(.headline)
                                    versionRow("Request", value: candidate["request_id"]?.stringValue ?? "Unavailable", monospaced: true)
                                    if let revision = candidate["candidate_revision"]?.stringValue {
                                        versionRow("Candidate package revision", value: revision, monospaced: true)
                                    } else {
                                        Text("No validated candidate revision is recorded.")
                                            .font(.caption).foregroundStyle(AppTheme.textDim)
                                    }
                                    if let operation = candidate["review_artifact_operation"]?.stringValue {
                                        Text("Review artifact: \(operation); maintainer review state is separate from runtime activation.")
                                            .font(.caption).foregroundStyle(AppTheme.textDim)
                                    }
                                }
                                if candidate != candidates.last { Divider() }
                            }
                        }
                    }
                }
                GroupBox("Version history limits") {
                    Text("A package digest, manifest version, and active registry pin are distinct facts. Candidate requests do not prove activation; this view does not activate or roll back skills. Previous installed revisions and Git history are not available from the current runtime API.")
                        .font(.caption).foregroundStyle(AppTheme.textDim)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("A package digest, manifest version, and active registry pin are distinct facts. Candidate requests do not prove activation; this view does not activate or roll back skills. Previous installed revisions and Git history are not available from the current runtime API.")
                }
            }
        } else if let versionEvidenceError {
            ContentUnavailableView("Version evidence unavailable", systemImage: "clock.arrow.circlepath",
                                   description: Text(versionEvidenceError))
        } else {
            ContentUnavailableView("Version evidence unavailable", systemImage: "clock.arrow.circlepath",
                                   description: Text("Refresh this view to retry."))
        }
    }

    private func versionRow(_ title: String, value: String, monospaced: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(AppTheme.textDim)
            Text(value).font(monospaced ? .caption.monospaced() : .callout)
                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title): \(value)")
    }

    private func stringList(_ value: JSONValue?) -> String {
        value?.arrayValue?.compactMap(\.stringValue).joined(separator: ", ") ?? ""
    }

    private func readinessReasons(_ value: JSONValue?) -> String {
        let reasons = value?.arrayValue?.compactMap(\.stringValue) ?? []
        guard !reasons.isEmpty else { return "No readiness issues reported." }
        return reasons.map(readinessMessage).joined(separator: "; ")
    }

    @MainActor
    private func refresh() async {
        loading = true
        defer { loading = false }
        announceAccessibilityStatus(.catalog, .loading)
        do {
            let response = try await AdminAPI(config: client.config).allSkillsCatalog()
            catalogRevision = response["catalog_revision"]?.stringValue ?? ""
            authoringAvailable = response["capabilities"]?["authoring"]?.boolValue ?? false
            let items = response["items"]?.arrayValue ?? []
            skillsStore.updateCatalog(items)
            let loadedCards = items.compactMap(SkillsCatalogCard.init)
            cards = loadedCards
            enabledSkillCount = loadedCards.filter(\.enabled).count
            attentionSkillCount = loadedCards.filter {
                SkillsWorkspacePresentationPolicy.needsAttention(
                    installation: $0.installation,
                    readiness: $0.readiness,
                    verification: $0.verification,
                    enabled: $0.enabled,
                    readinessReasons: $0.readinessReasons
                )
            }.count
            categoryOptions = Array(Set(loadedCards.map(\.category))
                .union(["home", "surveillance", "finance"])).sorted()
            errorMessage = nil
            announceAccessibilityStatus(.catalog, .loaded)
            let selectedCandidate = skillsStore.selectedSkillID
            if let selectedCandidate, let card = cards.first(where: { $0.id == selectedCandidate }) {
                appliedNavigationSkillID = card.id
                activityState.selectSkill(card.id)
                activeTab = skillsStore.selectedTab
                selectedStepID = skillsStore.selectedStepID
                activityState.selectRun(skillsStore.selectedRunID)
                await loadDetail(for: card.id, revision: card.revision)
            } else {
                detail = nil
            }
        } catch {
            errorMessage = "Could not load the skills catalog. Check Mortimer's connection and retry."
            announceAccessibilityStatus(.catalog, .failed)
        }
    }

    @MainActor
    private func presentPendingVoiceDraftIfReady() {
        guard !showingCreator, authoringAvailable, catalogRevision.count == 64,
              let pending = skillsStore.takePendingVoiceDraft() else { return }
        voiceDraft = pending
        showingCreator = true
    }

    @MainActor
    private func loadDetail(for id: String, revision: String? = nil) async {
        let requestID = UUID()
        detailLoadRequestID = requestID
        announceAccessibilityStatus(.detail, .loading)
        do {
            let resolved = try await skillsStore.resolveDetail(skillID: id, revision: revision) {
                try await AdminAPI(config: client.config).skillDetail(id: id, revision: revision)
            }
            guard SkillsWorkspacePresentationPolicy.isCurrentDetailResponse(
                requestID: requestID,
                currentRequestID: detailLoadRequestID,
                requestedSkillID: id,
                selectedSkillID: selectedID
            ) else { return }
            detail = refreshedCatalogFields(in: resolved, for: id)
            let nodes = detail?["process_nodes"]?.arrayValue ?? []
            skillsStore.updateProcess(skillID: id, nodes: nodes)
            errorMessage = nil
            announceAccessibilityStatus(.detail, .loaded)
        } catch {
            guard SkillsWorkspacePresentationPolicy.isCurrentDetailResponse(
                requestID: requestID,
                currentRequestID: detailLoadRequestID,
                requestedSkillID: id,
                selectedSkillID: selectedID
            ) else { return }
            detail = nil
            errorMessage = "This skill changed or is unavailable. Refresh the library to see its current revision."
            announceAccessibilityStatus(.detail, .failed)
        }
    }

    /// Readiness and installation can change without the package digest
    /// changing. Refresh those catalog-owned fields when serving cached detail.
    private func refreshedCatalogFields(in value: JSONValue, for id: String) -> JSONValue {
        guard let card = cards.first(where: { $0.id == id }), var object = value.objectValue else {
            return value
        }
        object["installation"] = .string(card.installation)
        object["enabled"] = .bool(card.enabled)
        object["readiness"] = .string(card.readiness)
        object["readiness_reasons"] = .array(card.readinessReasons.map(JSONValue.string))
        object["verification"] = .string(card.verification)
        return .object(object)
    }

    @MainActor
    private func loadVersionEvidence() async {
        guard let id = selectedID else { return }
        versionsLoading = true
        versionEvidence = nil
        versionEvidenceError = nil
        announceAccessibilityStatus(.versions, .loading)
        defer { versionsLoading = false }
        do {
            let response = try await AdminAPI(config: client.config).skillVersions(id: id)
            guard selectedID == id, response["skill_id"]?.stringValue == id,
                  response["schema_version"]?.intValue == 1 else {
                guard selectedID == id else { return }
                versionEvidenceError = "Version evidence did not match the selected skill. Refresh this view to retry."
                announceAccessibilityStatus(.versions, .failed)
                return
            }
            versionEvidence = response
            versionEvidenceError = nil
            announceAccessibilityStatus(.versions, .loaded)
        } catch JarvisError.http(status: 503, body: let body)
            where body.contains("Skills requests require bearer authentication") {
            guard selectedID == id else { return }
            versionEvidence = nil
            versionEvidenceError = "Version and candidate history require bearer authentication, which is not enabled for this local session. The Skills library and process remain available."
            announceAccessibilityStatus(.versions, .failed)
        } catch {
            guard selectedID == id else { return }
            versionEvidence = nil
            versionEvidenceError = "Could not load caller-authorized version evidence. Check Mortimer's connection and try again."
            announceAccessibilityStatus(.versions, .failed)
        }
    }

    @MainActor
    private func loadExamplePreview(_ exampleID: String) async {
        guard exampleLoadingID != exampleID else { return }
        guard let skillID = selectedID,
              cards.first(where: { $0.id == skillID })?.exampleIDs.contains(exampleID) == true else {
            examplePreview = nil
            examplePreviewError = "That example is not declared for the selected skill."
            announceAccessibilityStatus(.example, .failed)
            return
        }
        examplePreview = nil
        examplePreviewError = nil
        exampleLoadingID = exampleID
        announceAccessibilityStatus(.example, .loading)
        defer { if exampleLoadingID == exampleID { exampleLoadingID = nil } }
        do {
            let result = try await AdminAPI(config: client.config)
                .skillExamplePreview(id: skillID, exampleID: exampleID)
            guard selectedID == skillID, skillsStore.selectedExampleID == exampleID,
                  result["skill_id"]?.stringValue == skillID,
                  result["example_id"]?.stringValue == exampleID,
                  result["synthetic"]?.boolValue == true else { return }
            examplePreview = result
            announceAccessibilityStatus(.example, .loaded)
        } catch {
            guard selectedID == skillID, skillsStore.selectedExampleID == exampleID else { return }
            examplePreviewError = "No validated synthetic preview is available for this example."
            announceAccessibilityStatus(.example, .failed)
        }
    }

    @MainActor
    private func announceAccessibilityStatus(
        _ resource: SkillsWorkspaceAccessibilityStatus.Resource,
        _ phase: SkillsWorkspaceAccessibilityStatus.Phase
    ) {
        var state = accessibilityStatus
        guard let message = state.transition(resource: resource, to: phase) else { return }
        accessibilityStatus = state
        SkillsWorkspaceAccessibilityStatus.post(message)
    }

    @MainActor
    private func announceProcessStepSelection(_ stepID: String?) {
        var state = accessibilityStatus
        guard let message = state.processStepSelectionChanged(to: stepID) else { return }
        accessibilityStatus = state
        SkillsWorkspaceAccessibilityStatus.post(message)
    }

    @MainActor
    private func applySharedNavigation() {
        if search != skillsStore.searchQuery { search = skillsStore.searchQuery }
        if inventoryFilter != skillsStore.stateFilter { inventoryFilter = skillsStore.stateFilter }
        if categoryFilter != skillsStore.categoryFilter { categoryFilter = skillsStore.categoryFilter }
        if activeTab != skillsStore.selectedTab { activeTab = skillsStore.selectedTab }
        if selectedStepID != skillsStore.selectedStepID { selectedStepID = skillsStore.selectedStepID }
        if activityState.selectedRunID != skillsStore.selectedRunID {
            activityState.selectRun(skillsStore.selectedRunID)
        }
        guard let id = skillsStore.selectedSkillID,
              let card = cards.first(where: { $0.id == id }) else {
            appliedNavigationSkillID = nil
            return
        }
        guard id != appliedNavigationSkillID else { return }
        appliedNavigationSkillID = id
        activityState.selectSkill(id)
        compactShowsDetail = true
        selectedStepID = skillsStore.selectedStepID
        activityState.selectRun(skillsStore.selectedRunID)
        if let cached = skillsStore.cachedDetail(skillID: id, revision: card.revision) {
            // A verified, revision-keyed detail is already available for this
            // selection. Install it in the same update as selectedID instead
            // of rendering a loading placeholder and scheduling a second
            // SwiftUI update after an async cache lookup.
            detail = refreshedCatalogFields(in: cached, for: id)
            errorMessage = nil
            announceAccessibilityStatus(.detail, .loaded)
        } else {
            detail = nil
            Task { await loadDetail(for: id, revision: card.revision) }
        }
    }

    @MainActor
    private func setSelectedStep(_ id: String?) {
        if let coordinator {
            if let id {
                _ = coordinator.executePointer(.skillStepSelect, target: id,
                                               args: ["expanded": .bool(true)])
            } else if let selectedStepID {
                _ = coordinator.executePointer(.skillStepSelect, target: selectedStepID,
                                               args: ["expanded": .bool(false)])
            }
            return
        }
        selectedStepID = id
        if let id { _ = skillsStore.selectStep(id) }
        else { skillsStore.clearStep() }
    }

    @MainActor
    private func selectActivityRun(_ id: String) {
        guard id != activityState.selectedRunID else { return }
        if let coordinator {
            _ = coordinator.executePointer(.skillRunSelect, target: id)
            return
        }
        activityState.selectRun(id)
        _ = skillsStore.selectRun(id)
    }

    @MainActor
    private func applySharedFilters(state: String, category: String) {
        if let coordinator {
            _ = coordinator.executePointer(.skillsFilter, args: [
                "state": .string(state), "category": .string(category),
            ])
        } else { _ = skillsStore.setFilters(state: state, category: category) }
    }

    @MainActor
    private func registerSharedActions() {
        guard !detailOnly, let coordinator else { return }
        // Avoid a coordinator/view retain cycle. SwiftUI State wrappers retain
        // their backing storage when this lightweight view value is copied.
        var actionView = self
        actionView.coordinator = nil
        coordinator.registerSkillWorkspaceActionHandler(owner: actionHandlerOwner) {
            action, request in actionView.handleSharedAction(action, request: request)
        }
    }

    @MainActor
    private func handleSharedAction(
        _ action: ConsoleAction,
        request: ConsoleRequest
    ) -> ConsoleActionCoordinator.Outcome {
        switch action {
        case .skillsRefresh:
            guard !loading else { return .noop }
            refreshActionSignal &+= 1
            return .applied
        case .skillBack:
            guard compactShowsDetail else { return .invalid }
            backActionSignal &+= 1
            return .applied
        case .skillActivityRetry:
            guard activityState.error != nil else { return .invalid }
            retryActionSignal &+= 1
            return .applied
        case .skillActivityMore:
            guard activityState.hasMore, activityState.selectedRunID != nil else { return .invalid }
            loadMoreActionSignal &+= 1
            return .applied
        case .skillCreatorOpen:
            guard SkillsWorkspacePresentationPolicy.canOpenCreator(
                authoringAvailable: authoringAvailable, catalogRevision: catalogRevision
            ) else { return .unsupported }
            guard !showingCreator else { return .noop }
            showingCreator = true
            return .applied
        default:
            return .unsupported
        }
    }

    @MainActor
    private func requestActivityRetry() {
        if let coordinator { _ = coordinator.executePointer(.skillActivityRetry) }
        else { retryActivity() }
    }

    @MainActor
    private func retryActivity() {
        if activityState.retryLoadsMore {
            Task { await loadMoreActivity() }
        } else {
            activityState.retryNonce &+= 1
        }
    }

    @MainActor
    private func requestLoadMoreActivity() {
        if let coordinator { _ = coordinator.executePointer(.skillActivityMore) }
        else { Task { await loadMoreActivity() } }
    }
}

private func readinessMessage(_ code: String) -> String {
    let parts = code.split(separator: ":", maxSplits: 1).map(String.init)
    let detail = parts.count == 2 ? parts[1] : ""
    return switch parts[0] {
    case "package_invalid": "Skill package is invalid."
    case "skill_disabled": "Skill is disabled in the reviewed registry."
    case "required_tool_not_configured": "Required tool is not configured: \(detail)."
    case "required_tool_unavailable": "Required tool is not available at runtime: \(detail)."
    case "required_credential_missing": "Required credential is not configured: \(detail)."
    case "required_credential_authentication_failed": "Required credential authentication failed: \(detail)."
    case "invalid_credential_reference": "Skill declares an invalid credential name."
    case "model_route_incompatible": "No configured model route meets this skill's policy."
    case "sandbox_unavailable": "The required isolated sandbox is unavailable."
    case "revision_pin_unverified": "The running registry revision has not been verified."
    case "revision_enforcement_disabled": "Digest-pinned loading is disabled; the legacy skill loader is active."
    case "revision_digest_mismatch": "The package does not match its approved registry revision."
    case "revision_pin_missing": "No approved package revision is registered."
    case "tool_inventory_unavailable": "Configured tool availability could not be checked."
    case "tool_inventory_incomplete": "Tool configuration is incomplete."
    case "tool_runtime_unverified": "Configured tools have not been verified in the running session."
    case "credential_presence_unverified": "Credential presence could not be verified."
    case "credential_authentication_unverified": "Credential presence is known; authentication has not been tested."
    case "model_route_compatibility_unverified": "Model route and privacy compatibility have not been verified."
    case "sandbox_availability_unverified": "Sandbox availability has not been verified."
    default: code.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
