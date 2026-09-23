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
    /// A monotonic request from the shared DrawerState. It lets voice and
    /// pointer adapters scroll the header while keeping selection unchanged.
    var scrollRequest: Int = 0
    var scrollDirection: Int = 0
    private var labelSize: CGFloat { CGFloat(min(22, max(11, textSize.isFinite ? textSize : 11))) }
    private var tabHeight: CGFloat { max(32, labelSize + 20) }
    @State private var tabViewport = TabStripViewport()
    @State private var tabFrames: [String: CGRect] = [:]
    @State private var fallbackOffset: CGFloat = 0
    @FocusState private var stripFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Some AppKit/SwiftUI hosting fixtures do not publish ScrollView's
    /// contentSize, even though child frames are available. Derive a safe
    /// fallback from those frames so overflow controls remain reachable in
    /// the same way on a real window and in acceptance rendering.
    private var estimatedFrames: [String: CGRect] {
        var x: CGFloat = 0
        var result: [String: CGRect] = [:]
        for key in DrawerState.tabKeys {
            let label = DrawerState.tabLabels[key] ?? key
            // Monospaced labels are stable enough for an overflow fallback;
            // real child geometry replaces these values as soon as AppKit
            // publishes it.
            let width = CGFloat(label.count) * labelSize * 0.62 + 18
            result[key] = CGRect(x: x, y: 0, width: width, height: tabHeight)
            x += width + 2
        }
        return result
    }

    private var effectiveFrames: [String: CGRect] {
        var result = estimatedFrames
        for (key, frame) in tabFrames { result[key] = frame }
        return result
    }

    private var effectiveViewport: TabStripViewport {
        let measured = effectiveFrames.values.map { $0.maxX }.max() ?? 0
        // Keep a bounded visual offset under the shared state owner. This is
        // also reliable in AppKit accessibility fixtures where ScrollViewReader
        // reports content geometry but does not move its accessibility frames.
        return TabStripViewport(offset: fallbackOffset,
                                width: tabViewport.width,
                                contentWidth: max(tabViewport.contentWidth, measured))
    }

    var body: some View {
            ScrollViewReader { proxy in
                HStack(spacing: 2) {
                    if effectiveViewport.overflows {
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
                        .offset(x: -fallbackOffset)
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
                        fallbackOffset = 0
                        proxy.scrollTo(tab)
                    }
                    .onChange(of: tabViewport.contentWidth) { _, _ in
                        proxy.scrollTo(selectedTab)
                    }
                    .onChange(of: tabViewport.width) { _, _ in
                        proxy.scrollTo(selectedTab)
                    }
                    .onChange(of: scrollRequest) { _, _ in
                        scrollTabs(proxy: proxy)
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
                    if effectiveViewport.overflows {
                        tabScrollButton(forward: true, proxy: proxy)
                    }
                }
            }
    }

    private func scrollTabs(proxy: ScrollViewProxy) {
        let forward = scrollDirection >= 0
        let viewport = effectiveViewport
        let target = nextScrollTarget(forward: forward, viewport: viewport)
        guard let frame = estimatedFrames[target], viewport.width > 0 else { return }
        let desired = forward ? frame.maxX - viewport.width : frame.minX
        let maximum = max(0, viewport.contentWidth - viewport.width)
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
            fallbackOffset = min(maximum, max(0, desired))
        }
        _ = proxy
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
            let frames = estimatedFrames
            let target = nextScrollTarget(forward: forward, viewport: effectiveViewport)
            // Use the same bounded offset for native and accessibility-hosted
            // windows; ScrollViewReader remains responsible for selected-tab
            // reveal, while these buttons do not change selection.
            if let frame = frames[target], effectiveViewport.width > 0 {
                let desired = forward ? frame.maxX - effectiveViewport.width : frame.minX
                let maximum = max(0, effectiveViewport.contentWidth - effectiveViewport.width)
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                    fallbackOffset = target == (forward ? DrawerState.tabKeys.last : DrawerState.tabKeys.first)
                        ? (forward ? maximum : 0)
                        : min(maximum, max(0, desired))
                }
            }
            _ = proxy
        } label: {
            Image(systemName: forward ? "chevron.right" : "chevron.left")
                .frame(width: 24, height: tabHeight)
        }
        .buttonStyle(.plain)
        .disabled(forward ? !effectiveViewport.canScrollForward : !effectiveViewport.canScrollBack)
        .accessibilityLabel(forward ? "Scroll tabs right" : "Scroll tabs left")
        .help(forward ? "Show more tabs to the right" : "Show more tabs to the left")
    }

    private func nextScrollTarget(forward: Bool, viewport: TabStripViewport) -> String {
        let frames = estimatedFrames
        if forward {
            return DrawerState.tabKeys.first(where: {
                guard let frame = frames[$0] else { return false }
                return frame.maxX > viewport.offset + viewport.width + 1
            }) ?? DrawerState.tabKeys.last!
        }
        return DrawerState.tabKeys.reversed().first(where: {
            guard let frame = frames[$0] else { return false }
            return frame.minX < viewport.offset - 1
        }) ?? DrawerState.tabKeys.first!
    }

}
