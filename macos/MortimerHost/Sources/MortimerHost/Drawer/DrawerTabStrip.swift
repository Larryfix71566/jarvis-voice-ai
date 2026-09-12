import SwiftUI

/// Presentation-only header. Its state cannot recreate tab models or change a draft.
///
/// Closure plan C1.1 (gap G01): the strip is a keyboard-focusable control.
/// With focus, ← / → move the selection one tab, Home / End jump to the
/// first / last tab, and the existing selection observer scrolls the
/// chosen tab into view. Selection changes go through the SAME `select`
/// setter click and voice use (interface plan §4.2), so keyboard can never
/// diverge from them. Scrolling the strip with the arrow buttons still
/// never changes selection.
struct DrawerTabStrip: View {
    let selectedTab: String
    let attention: [String: Color]
    let select: (String) -> Void

    var textSize: Double = 11
    private var labelSize: CGFloat { CGFloat(min(22, max(11, textSize.isFinite ? textSize : 11))) }
    private var tabHeight: CGFloat { max(32, labelSize + 20) }
    @State private var tabViewport = TabStripViewport()
    @State private var tabFrames: [String: CGRect] = [:]
    @FocusState private var stripFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
            ScrollViewReader { proxy in
                HStack(spacing: 2) {
                    if tabViewport.overflows {
                        tabScrollButton(forward: false, proxy: proxy)
                    }
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 2) {
                            ForEach(DrawerState.tabKeys, id: \.self) { key in
                                tabButton(key)
                                    .id(key)
                                    .onGeometryChange(for: CGRect.self) { geometry in
                                        geometry.frame(in: .named("drawer-tab-content"))
                                    } action: { frame in
                                        tabFrames[key] = frame
                                    }
                            }
                        }
                        .coordinateSpace(name: "drawer-tab-content")
                    }
                    .frame(height: tabHeight)
                    .onScrollGeometryChange(for: TabStripViewport.self) { geometry in
                        TabStripViewport(offset: geometry.contentOffset.x,
                                         width: geometry.containerSize.width,
                                         contentWidth: geometry.contentSize.width)
                    } action: { _, viewport in
                        tabViewport = viewport
                    }
                    .onChange(of: selectedTab, initial: true) { _, tab in
                        // Shared setter includes voice commands and restored preferences.
                        proxy.scrollTo(tab)
                    }
                    .onChange(of: tabViewport.contentWidth) { _, _ in
                        proxy.scrollTo(selectedTab)
                    }
                    .onChange(of: tabViewport.width) { _, _ in
                        proxy.scrollTo(selectedTab)
                    }
                    // C1.1 — keyboard navigation. The container, not each
                    // button, takes focus: one Tab stop for the whole strip,
                    // arrows move within it. A visible focus ring is kept
                    // (focusEffectDisabled is NOT applied) so the user can
                    // see where keys will land.
                    .focusable()
                    .focused($stripFocused)
                    .onKeyPress(.leftArrow) { moveSelection(by: -1) }
                    .onKeyPress(.rightArrow) { moveSelection(by: 1) }
                    .onKeyPress(.home) { jumpSelection(toFirst: true) }
                    .onKeyPress(.end) { jumpSelection(toFirst: false) }
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel("Sidecar tabs")
                    .accessibilityHint("Use the left and right arrow keys to change tab")
                    if tabViewport.overflows {
                        tabScrollButton(forward: true, proxy: proxy)
                    }
                }
            }
    }

    /// ← / →: the neighbouring tab in DrawerState.tabKeys order; the ends do
    /// not wrap, so a key press at an end is a no-op rather than a jump.
    private func moveSelection(by step: Int) -> KeyPress.Result {
        let keys = DrawerState.tabKeys
        guard let index = keys.firstIndex(of: selectedTab) else { return .ignored }
        let next = index + step
        guard keys.indices.contains(next) else { return .handled }
        select(keys[next])
        return .handled
    }

    private func jumpSelection(toFirst: Bool) -> KeyPress.Result {
        guard let target = toFirst ? DrawerState.tabKeys.first : DrawerState.tabKeys.last else { return .ignored }
        if target != selectedTab { select(target) }
        return .handled
    }

    private func tabButton(_ key: String) -> some View {
        Button {
            select(key)
        } label: {
            HStack(spacing: 6) {
                Text(DrawerState.tabLabels[key] ?? key)
                    .textCase(.uppercase)
                    .font(.system(size: labelSize, design: .monospaced))
                    .kerning(1.2)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                if let dotColor = attention[key] {
                    Circle()
                        .fill(dotColor)
                        .frame(width: 6, height: 6)
                        .shadow(color: dotColor, radius: 4)
                }
            }
            .padding(.horizontal, 9)
            .frame(minHeight: tabHeight)
            .overlay(
                RoundedRectangle(cornerRadius: 2)
                    .strokeBorder(selectedTab == key ? AppTheme.accentDim : .clear,
                                  lineWidth: 1)
            )
            .foregroundStyle(selectedTab == key ? AppTheme.accent : AppTheme.textDim)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(DrawerState.tabLabels[key] ?? key)
        .accessibilityValue(attention[key] == nil ? "" : "New activity")
        .accessibilityAddTraits(selectedTab == key ? [.isSelected] : [])
    }

    private func tabScrollButton(forward: Bool, proxy: ScrollViewProxy) -> some View {
        Button {
            guard let target = tabViewport.target(forward: forward,
                                                   keys: DrawerState.tabKeys,
                                                   frames: tabFrames) else { return }
            withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                proxy.scrollTo(target, anchor: forward ? .trailing : .leading)
            }
        } label: {
            Image(systemName: forward ? "chevron.right" : "chevron.left")
                .frame(width: 24, height: tabHeight)
        }
        .buttonStyle(.plain)
        .disabled(forward ? !tabViewport.canScrollForward : !tabViewport.canScrollBack)
        .accessibilityLabel(forward ? "Scroll tabs right" : "Scroll tabs left")
        .help(forward ? "Show more tabs to the right" : "Show more tabs to the left")
    }

}
