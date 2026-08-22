// WindowVibrancy.swift
// Larry 2026-08-18: "the display window/panel is not like liquid glass, I
// would like it see through like liquid glass."
//
// WHY THIS CANNOT BE DONE IN CSS
//
// `backdrop-filter` blurs what is behind an element WITHIN its own page.
// The popped-out display is a separate window, so there is nothing behind
// it but that window's own background — CSS can lighten the pane, but it
// can never show the desktop through it. Real see-through needs three
// things on the native side, and all three are required together:
//
//   1. NSWindow.isOpaque = false and backgroundColor = .clear, so the
//      window itself stops painting a solid rectangle.
//   2. An NSVisualEffectView behind the WKWebView, which is what actually
//      samples and blurs the desktop (the same material Finder sidebars
//      and Notification Center use).
//   3. WKWebView.setValue(false, forKey: "drawsBackground") — the webview
//      paints an opaque white base by default, and it will happily cover
//      the vibrancy view underneath if this is skipped. This is the step
//      that is easiest to miss, because the other two look correct in
//      isolation and the result is still a white rectangle.
//
// UNVERIFIED. Written without a Mac to run it on. `drawsBackground` is a
// private-ish KVC key on WKWebView — long-standing and widely used, but
// not public API, so it could warn or no-op on a future macOS. If the
// window comes up opaque white, that key is the first suspect; if it comes
// up transparent but unreadable, the CSS wash in displaywindow.css is the
// thing to restore. Record the verdict in the shell README either way.

import AppKit
import SwiftUI
import WebKit
import os

private let vibrancyLog = Logger(subsystem: "com.mortimer.shell", category: "vibrancy")

// ── TRANSPARENCY KNOBS (Larry 2026-08-18: "could it be more
// transparent?") ─────────────────────────────────────────────────────
//
// With `html.shell-vibrancy` set, the page paints NOTHING — so what is on
// screen is this material, unmodified. These two values are the only
// levers, and they do different jobs:
//
//   vibrancyMaterial  WHICH recipe macOS uses. Each is a fixed blend of
//                     blur radius and tint; they are not a linear scale,
//                     so this is a taste choice, not a dial.
//   vibrancyAlpha     HOW MUCH of that recipe is applied. Below ~0.6 the
//                     blur weakens along with the tint, so the desktop
//                     shows through sharply rather than softly — that
//                     reads as a transparent hole, not as glass.
//
// Materials from most to least see-through in a dark theme:
//
//   .sidebar              lightest, most desktop visible  ← now default
//   .popover              light, slight warm tint
//   .menu                 light, tighter blur
//   .hudWindow            was the default; dark and quite solid
//   .underWindowBackground  darkest, nearly opaque
//
// If .sidebar reads too light against the graphite palette, .popover is
// the next step back. If it is still not see-through enough, lower
// vibrancyAlpha to 0.85 before reaching for a different material — and
// stop at 0.6, past which the HIG's post-blur contrast rule starts
// costing legibility on the text this window exists to show.
private let defaultVibrancyMaterial: NSVisualEffectView.Material = .sidebar

/// 1.0 = the material as macOS designed it. See the note above before
/// going below 0.6.
private let defaultVibrancyAlpha: CGFloat = 1.0

// Both knobs are overridable from UserDefaults, because otherwise trying
// a value costs an Xcode rebuild — and picking a material is a taste
// judgement that wants several quick attempts, not one considered guess.
// Set and relaunch (no rebuild, no Xcode):
//
//   defaults write Documents-jarvis-voice-ai-clean-macos-.Mortimer \\
//       MortimerVibrancyMaterial -string popover
//   defaults write Documents-jarvis-voice-ai-clean-macos-.Mortimer \\
//       MortimerVibrancyAlpha -float 0.85
//
// Remove an override with `defaults delete <bundle-id> <key>`; anything
// unrecognised falls back to the compiled default and says so in the log,
// so a typo shows up as a log line rather than a mysteriously unchanged
// window.
private let materialsByName: [String: NSVisualEffectView.Material] = [
    "sidebar": .sidebar,
    "popover": .popover,
    "menu": .menu,
    "hudwindow": .hudWindow,
    "underwindowbackground": .underWindowBackground,
    "windowbackground": .windowBackground,
    "contentbackground": .contentBackground,
    "fullscreenui": .fullScreenUI,
]

private var vibrancyMaterial: NSVisualEffectView.Material {
    guard let raw = UserDefaults.standard.string(forKey: "MortimerVibrancyMaterial") else {
        return defaultVibrancyMaterial
    }
    guard let match = materialsByName[raw.lowercased()] else {
        vibrancyLog.error(
            "unknown MortimerVibrancyMaterial '\(raw, privacy: .public)' — using the default. Known: \(materialsByName.keys.sorted().joined(separator: ", "), privacy: .public)")
        return defaultVibrancyMaterial
    }
    return match
}

private var vibrancyAlpha: CGFloat {
    guard UserDefaults.standard.object(forKey: "MortimerVibrancyAlpha") != nil else {
        return defaultVibrancyAlpha
    }
    let value = CGFloat(UserDefaults.standard.double(forKey: "MortimerVibrancyAlpha"))
    // Clamp rather than trust: 0 would make the window invisible and look
    // like the feature broke.
    return min(1.0, max(0.3, value))
}

/// SwiftUI hook: attach to a window's root view to make THAT window
/// non-opaque and install the vibrancy layer. Deliberately opt-in per
/// window — the console is a full-bleed app window with nothing useful
/// behind it, so only display and drawer use this.
struct VibrantWindow: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let probe = NSView()
        // The view is not in a window yet at make time; defer one runloop
        // turn so `probe.window` resolves.
        DispatchQueue.main.async { applyVibrancy(to: probe.window) }
        return probe
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}

/// Make `window` non-opaque and slide an NSVisualEffectView beneath its
/// content. Idempotent: calling twice does not stack effect views.
func applyVibrancy(to window: NSWindow?) {
    guard let window else {
        vibrancyLog.error("applyVibrancy: no window yet — vibrancy not applied")
        return
    }
    guard let contentView = window.contentView else {
        vibrancyLog.error("applyVibrancy: window has no contentView")
        return
    }

    window.isOpaque = false
    window.backgroundColor = .clear
    // Keep the titlebar out of the material's way so the blur runs edge
    // to edge rather than stopping under a solid bar.
    window.titlebarAppearsTransparent = true

    // PLACEMENT (fixed 2026-08-21, from Larry's screenshot of a uniformly
    // dimmed drawer window): the effect view must NOT be a subview of the
    // window's contentView. In a SwiftUI window the contentView IS the
    // NSHostingView, and a view's SUBVIEWS always render on top of the
    // view's OWN drawn content — `positioned: .below` only orders among
    // sibling subviews, so the "background" material was actually a
    // frosted pane OVER the webview, dimming every pixel of web content
    // uniformly (and making every CSS change invisible, which is what
    // kept this bug alive through three CSS-side attempts). The correct
    // host is the contentView's SUPERVIEW (the window frame view), where
    // the effect view is a true sibling of the contentView and sibling
    // ordering genuinely puts it behind.
    guard let frameView = contentView.superview else {
        vibrancyLog.error("applyVibrancy: contentView has no superview — vibrancy not applied")
        return
    }

    // Clean up any effect view a previous (buggy) placement left INSIDE
    // the contentView — it would sit over the content and re-dim it.
    for stray in contentView.subviews.compactMap({ $0 as? NSVisualEffectView }) {
        stray.removeFromSuperview()
        vibrancyLog.info("applyVibrancy: removed stray effect view from contentView")
    }

    if let existing = frameView.subviews.compactMap({ $0 as? NSVisualEffectView }).first {
        // Re-apply rather than skip: tweaking the knobs above and
        // reloading should show the change without an app restart.
        existing.material = vibrancyMaterial
        existing.alphaValue = vibrancyAlpha
        vibrancyLog.debug("applyVibrancy: refreshed existing effect view")
    } else {
        let effect = NSVisualEffectView()
        effect.material = vibrancyMaterial
        effect.blendingMode = .behindWindow      // sample the DESKTOP, not this window
        effect.state = .active                   // stay lit even when unfocused
        effect.autoresizingMask = [.width, .height]
        effect.frame = contentView.frame
        effect.alphaValue = vibrancyAlpha
        frameView.addSubview(effect, positioned: .below, relativeTo: contentView)
        vibrancyLog.info("applyVibrancy: installed \(String(describing: vibrancyMaterial)) alpha=\(vibrancyAlpha) behind contentView")
    }

    // Step 3 — without this the webview paints an opaque base over the
    // effect view and everything above looks correct while being solid.
    var cleared = 0
    for webView in contentView.descendantWebViews() {
        webView.setValue(false, forKey: "drawsBackground")
        cleared += 1
    }
    vibrancyLog.info("applyVibrancy: cleared background on \(cleared) webview(s)")
    if cleared == 0 {
        // Not fatal: the webview may not be mounted yet. The retry in
        // ShellRootView covers that; this line is here so a permanently
        // empty result is visible in the log rather than silent.
        vibrancyLog.error("applyVibrancy: no WKWebView found under the content view")
    }
}

extension NSView {
    /// Every WKWebView beneath this view, at any depth. SwiftUI wraps
    /// NSViewRepresentable content in hosting views whose depth is not
    /// contractual, so this walks rather than assuming a level.
    func descendantWebViews() -> [WKWebView] {
        var found: [WKWebView] = []
        for sub in subviews {
            if let web = sub as? WKWebView { found.append(web) }
            found.append(contentsOf: sub.descendantWebViews())
        }
        return found
    }
}
