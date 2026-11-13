import SwiftUI

/// APP plan §3 P10 / §0.6 — colour tokens ported from web/src/App.css's
/// :root block ("arc-reactor HUD theme", graphite base). No view hardcodes
/// a colour; everything comes from here. Alpha-carrying tokens keep the
/// CSS's exact rgba values.
enum AppTheme {
    // --bg / --panel / --hairline
    static let bg = Color(red: 0x15 / 255.0, green: 0x19 / 255.0, blue: 0x1D / 255.0)
    static let panel = Color(red: 0x11 / 255.0, green: 0x15 / 255.0, blue: 0x1A / 255.0)
    static let hairline = Color(red: 0x2A / 255.0, green: 0x34 / 255.0, blue: 0x3D / 255.0)

    // --accent family (#2cc9ff)
    static let accent = Color(red: 0x2C / 255.0, green: 0xC9 / 255.0, blue: 0xFF / 255.0)
    static let accentDim = accent.opacity(0.35)
    static let accentFaint = accent.opacity(0.12)

    // --text / --text-dim
    static let text = Color(red: 0xE2 / 255.0, green: 0xF1 / 255.0, blue: 0xF9 / 255.0)
    static let textDim = Color(red: 0x8F / 255.0, green: 0xA8 / 255.0, blue: 0xB8 / 255.0)

    // Semantic state tokens (E1): cyan = alive/ok, amber = attention, red = error.
    static let amber = Color(red: 0xFF / 255.0, green: 0xB4 / 255.0, blue: 0x54 / 255.0)
    static let green = Color(red: 0x3D / 255.0, green: 0xDC / 255.0, blue: 0x97 / 255.0)
    static let red = Color(red: 0xFF / 255.0, green: 0x5F / 255.0, blue: 0x56 / 255.0)
    static let attn = amber
    static let attnDim = amber.opacity(0.35)

    // C0b approved palette. Keep these distinct from the general semantic
    // warning/success/failure tokens above; call sites migrate in C5/C7a.
    static let listening = Color(red: 0x66 / 255.0, green: 0x73 / 255.0, blue: 0xFF / 255.0)
    static let user = AudioPresentationTuning.userColor
    static let mortimer = AudioPresentationTuning.assistantColor
    static let ok = Color(red: 0xA6 / 255.0, green: 0xFF / 255.0, blue: 0xC1 / 255.0)
    static let approval = Color(red: 0xFF / 255.0, green: 0xD8 / 255.0, blue: 0x4A / 255.0)
    static let error = Color(red: 0xFF / 255.0, green: 0x59 / 255.0, blue: 0x8B / 255.0)

    // --glass-* (the CSS material recipe; used by Glass.swift's fallback
    // tinting — the primary glass-on arm is .glassEffect(), P10/T1.0).
    static let glassBg = Color(red: 43 / 255.0, green: 50 / 255.0, blue: 58 / 255.0).opacity(0.35)
    static let glassBgHeavy = Color(red: 30 / 255.0, green: 36 / 255.0, blue: 43 / 255.0).opacity(0.58)
    /// --glass-bg-opaque — the glass-OFF (rollback) fill, §9.
    static let panelOpaque = Color(red: 30 / 255.0, green: 36 / 255.0, blue: 43 / 255.0).opacity(0.94)
    /// Fully opaque accessibility surface when Reduce Transparency is on.
    static let panelSolid = Color(red: 30 / 255.0, green: 36 / 255.0, blue: 43 / 255.0)
    static let glassBorder = Color.white.opacity(0.14)
    static let glassEdge = Color.white.opacity(0.18)
    static let highContrastBorder = Color.white.opacity(0.55)
}
