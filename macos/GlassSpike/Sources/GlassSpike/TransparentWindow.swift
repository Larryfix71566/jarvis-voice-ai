// TransparentWindow.swift
// Arm 1 (primary): make the hosting NSWindow non-opaque so a SwiftUI
// .glassEffect() panel has the desktop behind it, not a white page.
// Ported from MortimerShell's WindowVibrancy.swift steps 1-2; step 3
// (WKWebView drawsBackground) is dropped — there is no webview here.

import AppKit
import SwiftUI

struct TransparentWindowAccessor: NSViewRepresentable {
    var useVisualEffectFallback: Bool          // Arm 2
    func makeNSView(context: Context) -> NSView {
        let probe = NSView()
        DispatchQueue.main.async { apply(to: probe.window) }   // WindowVibrancy.swift:126-128
        return probe
    }
    func updateNSView(_ v: NSView, context: Context) {}
    private func apply(to window: NSWindow?) {
        guard let window, let content = window.contentView else { return }
        window.isOpaque = false
        window.backgroundColor = .clear
        window.titlebarAppearsTransparent = true
        guard useVisualEffectFallback, let frameView = content.superview else { return }
        // The 2026-08-21 fix, carried verbatim (WindowVibrancy.swift:153-164):
        // the effect view MUST be a sibling of contentView, not a subview,
        // or it renders OVER the content and uniformly dims every pixel.
        for stray in content.subviews.compactMap({ $0 as? NSVisualEffectView }) { stray.removeFromSuperview() }
        if frameView.subviews.contains(where: { $0 is NSVisualEffectView }) { return }
        let effect = NSVisualEffectView()
        effect.material = .sidebar               // WindowVibrancy.swift:66 default
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.autoresizingMask = [.width, .height]
        effect.frame = content.frame
        frameView.addSubview(effect, positioned: .below, relativeTo: content)
    }
}
