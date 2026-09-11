import SwiftUI

private struct DrawerScrollRestoration: ViewModifier {
    let tab: String
    @Environment(DrawerModels.self) private var models
    @State private var position = ScrollPosition(y: 0)
    @State private var restored = false

    func body(content: Content) -> some View {
        content
            .scrollPosition($position)
            .onScrollGeometryChange(for: Double.self) { geometry in
                Double(geometry.contentOffset.y + geometry.contentInsets.top)
            } action: { _, offset in
                guard restored, offset.isFinite else { return }
                models.scrollOffsets[tab] = max(0, offset)
            }
            .onAppear {
                if let offset = models.scrollOffsets[tab] { position.scrollTo(y: offset) }
                restored = true
            }
    }
}

extension View {
    func preserveDrawerScroll(_ tab: String) -> some View { modifier(DrawerScrollRestoration(tab: tab)) }
}
