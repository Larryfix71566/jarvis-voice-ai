import SwiftUI
import JarvisKit

/// A is the quiet results area beside the transcript. B is an explicitly
/// summoned sheet with the identical canonical set, not a second history.
struct ResultCarouselView: View {
    let coordinator: ConsoleActionCoordinator?
    var showsActions = true
    /// Voice activity colour source for the front card's follow glow.
    var glowActivity: VoicePresentationState.Activity = .assistant
    /// Test-only override; normal composition follows the system setting.
    var reduceTransparencyOverride: Bool? = nil
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @FocusState private var hasKeyboardFocus: Bool
    @State private var dragOffset: CGFloat = 0

    static func usesFlatPresentation(reduceMotion: Bool, reduceTransparency: Bool,
                                     increasedContrast: Bool = false) -> Bool {
        reduceMotion || reduceTransparency || increasedContrast
    }

    private var flat: Bool {
        Self.usesFlatPresentation(reduceMotion: reduceMotion, reduceTransparency: reduceTransparencyOverride ?? reduceTransparency,
                                 increasedContrast: contrast == .increased)
    }
    private var index: Int {
        guard let front = workspace.carouselFrontResult else { return 0 }
        return workspace.carouselResults.firstIndex(where: { $0.id == front.id }) ?? 0
    }

    var body: some View {
        VStack(spacing: 10) {
            ArrivalNoticeView(coordinator: coordinator)
            HStack {
                Spacer()
                Button("Show all results") { setMode(all: true) }
                    .disabled(workspace.carouselResults.isEmpty)
                    .accessibilityIdentifier("result-show-all")
            }
            if let front = workspace.carouselFrontResult {
                HStack {
                    Button { step(-1) } label: { Label("Previous", systemImage: "chevron.left") }
                        .disabled(index == 0)
                        .keyboardShortcut(.leftArrow, modifiers: [.command, .option])
                        .accessibilityLabel("Previous result")
                    Spacer()
                    Text("\(index + 1) of \(workspace.carouselResults.count)").font(.caption.monospacedDigit())
                    Spacer()
                    Button { step(1) } label: { Label("Next", systemImage: "chevron.right") }
                        .disabled(index + 1 == workspace.carouselResults.count)
                        .keyboardShortcut(.rightArrow, modifiers: [.command, .option])
                        .accessibilityLabel("Next result")
                }
                if workspace.showsAllResults {
                    // B owns the live renderer while its sheet is visible.
                    Color.clear.frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    GeometryReader { geometry in
                        let depth = !flat && geometry.size.width >= 720
                        let frontWidth = depth ? min(620, geometry.size.width - 160) : geometry.size.width
                        let neighbourWidth = min(180, (geometry.size.width - frontWidth) / 2 - 12)
                        let width = geometry.size.width
                        ZStack {
                            if depth && index > 0 {
                                neighbour(workspace.carouselResults[index - 1], leading: true)
                                    .frame(width: neighbourWidth, height: max(160, geometry.size.height * 0.72))
                                    .position(x: geometry.size.width / 2 - frontWidth / 2 - neighbourWidth / 2 - 8, y: geometry.size.height / 2)
                                    .offset(x: dragOffset)
                            }
                            if depth && index + 1 < workspace.carouselResults.count {
                                neighbour(workspace.carouselResults[index + 1], leading: false)
                                    .frame(width: neighbourWidth, height: max(160, geometry.size.height * 0.72))
                                    .position(x: geometry.size.width / 2 + frontWidth / 2 + neighbourWidth / 2 + 8, y: geometry.size.height / 2)
                                    .offset(x: dragOffset)
                            }
                            ResultCarouselFrontView(result: front, coordinator: coordinator, flat: flat, showsActions: showsActions,
                                                    glowColor: CometOrbRenderer.stateColor(glowActivity),
                                                    glowSuppressed: dragOffset != 0)
                                .frame(width: frontWidth, height: geometry.size.height)
                                .position(x: geometry.size.width / 2, y: geometry.size.height / 2)
                                .offset(x: dragOffset)
                                .accessibilityElement(children: .contain)
                                .accessibilityLabel("Results, \(index + 1) of \(workspace.carouselResults.count), \(Self.title(front))")
                                .accessibilityIdentifier("carousel-front")
                                .accessibilityAdjustableAction { direction in
                                    switch direction {
                                    case .increment: step(1)
                                    case .decrement: step(-1)
                                    @unknown default: break
                                    }
                                }
                        }.frame(width: geometry.size.width, height: geometry.size.height)
                            .background(ScrollSwipeCatcher(index: index, count: workspace.carouselResults.count,
                                onChange: { translation in followDrag(translation, width: width) },
                                onEnd: { amount in finishSwipe(amount) }))
                            .contentShape(Rectangle())
                            .simultaneousGesture(DragGesture(minimumDistance: 8)
                                .onChanged { value in
                                    guard abs(value.translation.width) > abs(value.translation.height) || dragOffset != 0 else { return }
                                    followDrag(value.translation.width, width: width)
                                }
                                .onEnded { value in
                                    let amount = CarouselSwipeModel.decision(
                                        translation: value.translation.width,
                                        predictedEnd: value.predictedEndTranslation.width,
                                        velocity: value.velocity.width,
                                        index: index, count: workspace.carouselResults.count, width: width)
                                    finishSwipe(amount)
                                })
                            .clipped()
                    }

                }
            } else {
                ContentUnavailableView("No results", systemImage: "rectangle.stack",
                                       description: Text("Display-worthy answers appear here."))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .buttonStyle(ResultControlButtonStyle())
        .accessibilityIdentifier("result-carousel")
        .focusable()
        .focused($hasKeyboardFocus)
        .onMoveCommand { direction in
            guard hasKeyboardFocus else { return }
            if direction == .left { step(-1) }
            if direction == .right { step(1) }
        }
        .animation(flat ? nil : .easeInOut(duration: 0.36), value: workspace.carouselFrontResult?.id)
        .sheet(isPresented: Binding(get: { workspace.showsAllResults }, set: { workspace.setShowsAllResults($0) })) {
            ResultAllResultsView(coordinator: coordinator)
        }
    }

    static func title(_ result: WorkspaceResult) -> String {
        result.payload.layout?.title ?? result.payload.title ?? "Result"
    }

    private func neighbour(_ result: WorkspaceResult, leading: Bool) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(Self.title(result)).font(.caption.weight(.semibold)).lineLimit(1)
            Text(ConversationThread.card(result).summary).font(.caption2).lineLimit(1).blur(radius: 3).drawingGroup()
        }
        .padding(12).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .orbGlassCard(lit: false, glowColor: AppTheme.mortimer, glowSuppressed: true)
        .scaleEffect(0.94)
        .rotation3DEffect(.degrees(leading ? 9 : -9), axis: (x: 0, y: 1, z: 0))
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// Flat presentation keeps the card still; only the commit decision applies.
    private func followDrag(_ translation: CGFloat, width: CGFloat) {
        guard !flat else { return }
        dragOffset = CarouselSwipeModel.offset(translation: translation, index: index,
                                               count: workspace.carouselResults.count, width: width)
    }

    private func finishSwipe(_ amount: Int) {
        if amount != 0 { step(amount) }
        if flat { dragOffset = 0 }
        else { withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) { dragOffset = 0 } }
    }

    private func step(_ amount: Int) {
        if let coordinator { _ = coordinator.executePointer(amount > 0 ? .resultNext : .resultPrevious) }
        else { _ = workspace.selectAdjacentResult(step: amount) }
    }

    private func setMode(all: Bool) {
        guard let front = workspace.carouselFrontResult else { return }
        if let coordinator {
            _ = coordinator.executePointer(.resultMode, target: front.id.uuidString,
                                           args: ["mode": .string(all ? "all" : "carousel")])
        } else { workspace.setShowsAllResults(all) }
    }
}

/// The front card alone owns pin/close and a full renderer. Neighbours never
/// fetch images or instantiate graphs, and approval controls do not live here.
private struct ResultCarouselFrontView: View {
    let result: WorkspaceResult
    let coordinator: ConsoleActionCoordinator?
    let flat: Bool
    var showsActions = true
    /// The orb's current colour and whether a drag is in progress.
    var glowColor: Color = AppTheme.mortimer
    var glowSuppressed = false
    @Environment(WorkspaceStore.self) private var workspace
    @State private var pinLimitNotice = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                if workspace.pinnedIDs.contains(result.id) { Label("Pinned", systemImage: "pin.fill").font(.caption) }
                if workspace.unreadIDs.contains(result.id) {
                    Label("Unread", systemImage: "circle.fill").font(.caption).foregroundStyle(AppTheme.listening)
                }
                if workspace.updatedIDs.contains(result.id) {
                    Label("Updated", systemImage: "arrow.clockwise").font(.caption).foregroundStyle(AppTheme.mortimer)
                }
                Spacer()
                if showsActions {
                Button(workspace.pinnedIDs.contains(result.id) ? "Unpin" : "Pin") { togglePin() }
                Button("Close") {
                    if let coordinator { _ = coordinator.executePointer(.resultClose, target: result.id.uuidString) }
                    else { workspace.close(result.id) }
                }
                }
            }
            if result.payload.isProtectedLocal && (workspace.showsConversation || workspace.unreadIDs.contains(result.id)) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(ResultCarouselView.title(result)).font(.headline)
                    Label(ConversationThread.privateSummary, systemImage: "lock.shield")
                    Button("Open private result") {
                        if let coordinator { _ = coordinator.executePointer(.resultSelect, target: result.id.uuidString) }
                        else { workspace.select(result.id) }
                    }.accessibilityLabel("Open \(ResultCarouselView.title(result))")
                }.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            } else { WorkspaceResultPane(result: result, coordinator: coordinator, showsActions: showsActions) }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .modifier(CarouselSurface(flat: flat, glowColor: glowColor, glowSuppressed: glowSuppressed))
        .id(result.id)
        .alert("Pin limit reached", isPresented: $pinLimitNotice) { Button("OK", role: .cancel) {} }
        message: { Text("Unpin a result before pinning another. Your existing pins are preserved.") }
    }

    private func togglePin() {
        let pinned = workspace.pinnedIDs.contains(result.id)
        if let coordinator {
            let outcome = coordinator.executePointer(pinned ? .resultUnpin : .resultPin, target: result.id.uuidString)
            if !pinned && outcome == .noop { pinLimitNotice = true }
        } else if pinned { workspace.unpin(result.id) }
        else { pinLimitNotice = !workspace.pin(result.id) }
    }
}

private struct CarouselSurface: ViewModifier {
    let flat: Bool
    let glowColor: Color
    let glowSuppressed: Bool
    func body(content: Content) -> some View {
        if flat {
            content.background(AppTheme.panelSolid, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(AppTheme.hairline))
        } else { content.orbGlassCard(lit: true, glowColor: glowColor, glowSuppressed: glowSuppressed) }
    }
}

/// B exposes the same numbered inventory; only its selected card is expanded.
struct ResultAllResultsView: View {
    let coordinator: ConsoleActionCoordinator?
    @Environment(WorkspaceStore.self) private var workspace
    @Environment(\.mortimerReduceMotion) private var reduceMotion
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("All results").font(.title2)
                Spacer()
                Button("Return to carousel") { close() }.keyboardShortcut(.cancelAction)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(workspace.carouselResults) { result in
                        Button { select(result.id) } label: {
                            HStack {
                                let number = workspace.recents.entries.first(where: { $0.id == result.id })?.number
                                Text(number.map { "\($0)." } ?? (result.payload.isProtectedLocal ? "Private" : "Older"))
                                    .font(.caption.monospacedDigit())
                                Text(ResultCarouselView.title(result)).lineLimit(1)
                                Spacer()
                                if workspace.pinnedIDs.contains(result.id) { Label("Pinned", systemImage: "pin.fill").font(.caption) }
                                if workspace.unreadIDs.contains(result.id) { Label("Unread", systemImage: "circle.fill").font(.caption) }
                                if workspace.updatedIDs.contains(result.id) { Label("Updated", systemImage: "arrow.clockwise").font(.caption) }
                            }.padding(8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(workspace.carouselFrontResult?.id == result.id ? AppTheme.listening.opacity(0.12) : Color.clear)
                        }.buttonStyle(.plain)
                            .accessibilityAddTraits(workspace.carouselFrontResult?.id == result.id ? [.isSelected] : [])
                    }
                }
            }.frame(maxHeight: 180)
            if let front = workspace.carouselFrontResult {
                ResultCarouselFrontView(result: front, coordinator: coordinator,
                    flat: ResultCarouselView.usesFlatPresentation(reduceMotion: reduceMotion,
                        reduceTransparency: reduceTransparency, increasedContrast: contrast == .increased))
            }
        }.padding(16)
            .frame(minWidth: 480, idealWidth: 760, maxWidth: .infinity, minHeight: 520, idealHeight: 720, maxHeight: .infinity)
            .buttonStyle(ResultControlButtonStyle())
            .accessibilityIdentifier("all-results")
    }
    private func select(_ id: UUID) {
        if let coordinator { _ = coordinator.executePointer(.resultSelect, target: id.uuidString) }
        else { workspace.select(id) }
    }
    private func close() {
        guard let front = workspace.carouselFrontResult else { workspace.setShowsAllResults(false); return }
        if let coordinator {
            _ = coordinator.executePointer(.resultMode, target: front.id.uuidString, args: ["mode": .string("carousel")])
        } else { workspace.setShowsAllResults(false) }
    }
}

/// Explicit token contrast avoids inherited white labels on AppKit white bezels.
struct ResultControlButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.callout)
            .foregroundStyle(isEnabled ? AppTheme.text : AppTheme.textDim)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(AppTheme.panelSolid.opacity(configuration.isPressed ? 0.7 : 1),
                        in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(AppTheme.hairline))
            .opacity(isEnabled ? 1 : 0.55)
    }
}
