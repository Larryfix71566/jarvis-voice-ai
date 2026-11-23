import SwiftUI

public enum OrbActivity: Equatable, Sendable {
    case offline, connecting, listening, user, assistant, thinking, muted
}

/// Semantic inputs, not app-specific colors or dependencies.
public struct OrbPalette {
    let approval, panel, text, user, textDim, mortimer: Color

    public init(approval: Color, panel: Color, text: Color, user: Color,
                textDim: Color, mortimer: Color) {
        self.approval = approval
        self.panel = panel
        self.text = text
        self.user = user
        self.textDim = textDim
        self.mortimer = mortimer
    }

    public static let standard = OrbPalette(
        approval: rgb(255, 216, 74), panel: rgb(17, 21, 26), text: rgb(226, 241, 249),
        user: rgb(45, 212, 191), textDim: rgb(143, 168, 184), mortimer: rgb(224, 112, 32)
    )

    private static func rgb(_ r: Double, _ g: Double, _ b: Double) -> Color {
        Color(red: r / 255, green: g / 255, blue: b / 255)
    }
}
