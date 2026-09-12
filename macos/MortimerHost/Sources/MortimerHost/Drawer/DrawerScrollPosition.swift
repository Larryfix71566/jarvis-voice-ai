import SwiftUI

private struct DrawerScrollRestoration: ViewModifier {
    let tab: String
    @Environment(DrawerModels.self) private var models
    @State private var position = ScrollPosition(y: 0)
    @State private var restored = false
    /// C1.4 — this presentation's identity for scroll-writer arbitration.
    @State private var presentation = UUID()

    func body(content: Content) -> some View {
        content
            .scrollPosition($position)
            .onScrollGeometryChange(for: Double.self) { geometry in
                Double(geometry.contentOffset.y + geometry.contentInsets.top)
            } action: { _, offset in
                guard restored else { return }
                models.recordScroll(offset, tab: tab, from: presentation)
            }
            .onAppear {
                // The most recently mounted presentation of a tab is the one
                // that records; an outgoing presentation cannot overwrite it.
                models.claimScrollWriter(presentation, tab: tab)
                if let offset = models.scrollOffsets[tab] { position.scrollTo(y: offset) }
                restored = true
            }
            .onDisappear {
                models.releaseScrollWriter(presentation, tab: tab)
            }
    }
}

extension View {
    func preserveDrawerScroll(_ tab: String) -> some View { modifier(DrawerScrollRestoration(tab: tab)) }
}
