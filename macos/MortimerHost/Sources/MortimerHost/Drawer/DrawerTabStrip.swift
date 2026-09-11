import SwiftUI

/// Presentation-only header. Its state cannot recreate tab models or change a draft.
struct DrawerTabStrip: View {
    let selectedTab: String
    let attention: [String: Color]
    let select: (String) -> Void

    @ScaledMetric(relativeTo: .caption) private var tabHeight: CGFloat = 32
    @State private var tabViewport = TabStripViewport()
    @State private var tabFrames: [String: CGRect] = [:]
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
                    .onChange(of: tabViewport.width) { _, _ in
                        proxy.scrollTo(selectedTab)
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel("Sidecar tabs")
                    if tabViewport.overflows {
                        tabScrollButton(forward: true, proxy: proxy)
                    }
                }
            }
    }

    private func tabButton(_ key: String) -> some View {
        Button {
            select(key)
        } label: {
            HStack(spacing: 6) {
                Text(DrawerState.tabLabels[key] ?? key)
                    .textCase(.uppercase)
                    .font(.system(.caption, design: .monospaced))
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
