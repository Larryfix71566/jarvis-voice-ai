import SwiftUI
import JarvisKit

/// Interface cleanup Phase 2: dropping anywhere in the window stages content;
/// the zone is drawn only while a drag is over the window, never at rest.
enum WindowDropOverlay {
    static func showsZone(isTargeted: Bool) -> Bool { isTargeted }
}

private struct WindowDropModifier: ViewModifier {
    @Environment(AttachmentStore.self) private var attachments
    @State private var targeted = false

    func body(content: Content) -> some View {
        content
            .onDrop(of: AttachmentIntake.dropTypeIdentifiers, isTargeted: $targeted) { providers in
                AttachmentIntake.handleDrop(providers, into: attachments)
            }
            .overlay { zone }
    }

    @ViewBuilder private var zone: some View {
        if WindowDropOverlay.showsZone(isTargeted: targeted) {
            Label("Drop to stage for Mortimer", systemImage: "arrow.down.doc")
                .font(.headline)
                .foregroundStyle(AppTheme.accent)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(AppTheme.accentFaint)
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(AppTheme.accent, style: StrokeStyle(lineWidth: 2, dash: [8, 6]))
                        .padding(8)
                )
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Drop to stage content")
                .allowsHitTesting(false)
        }
    }
}

extension View {
    func mortimerWindowDrop() -> some View {
        modifier(WindowDropModifier())
    }
}
