import SwiftUI
import AppKit
import JarvisKit

/// Interface cleanup Phase 2: the bottom mic bar is gone (the orb is the mic,
/// OrbMuteButton is the visible control). This file keeps the Space
/// push-to-talk monitor, now a modifier on the console root.
///
/// Semantics are the web's (MicControls.tsx): SPACE keydown unmutes and keyup
/// ALWAYS mutes (ownership guard so a keyup from ordinary typing never
/// mutes); there is deliberately no mic_unmute voice action (U7). Ownership
/// is shared with the orb's hold through PushToTalkOwnership.
extension View {
    func pushToTalkKeys() -> some View { modifier(PushToTalkKeysModifier()) }
}

struct PushToTalkKeysModifier: ViewModifier {
    @EnvironmentObject private var client: JarvisClient
    @State private var keyMonitor: Any?

    func body(content: Content) -> some View {
        content
            .onAppear(perform: installKeyMonitor)
            .onDisappear(perform: removeKeyMonitor)
    }

    // SPACE push-to-talk (MicControls.tsx:37-60): keydown → unmute;
    // keyup → mute (always — muted is PTT's resting state). NSEvent
    // local monitor; a first responder that accepts text (a TextField)
    // keeps its space bar (isTypingTarget guard). C7a: so does a focused
    // control (an approval button, or any AppKit control holding focus),
    // so Space reaches it; SpaceKeyRoute is the whole rule.
    private func installKeyMonitor() {
        guard keyMonitor == nil else { return }
        // Capture the client OBJECT (not the view struct's env wrapper) —
        // the monitor closure outlives any one render.
        let client = self.client
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp]) { event in
            guard event.keyCode == 49 else { return event }   // space
            let connected: Bool
            if case .connected = client.state { connected = true } else { connected = false }
            switch SpaceKeyRoute.route(isKeyDown: event.type == .keyDown, isRepeat: event.isARepeat,
                                       typingTarget: isTypingTarget(),
                                       focusedControl: SpaceKeyClaims.isClaimed || isFocusedControl(),
                                       connected: connected, owned: PushToTalkOwnership.spaceOwned) {
            case .passThrough:
                return event
            case .swallow:
                return nil
            case .startTalking:
                // The orb may already own push-to-talk: refuse, key swallowed.
                if PushToTalkOwnership.begin(.space) { client.setMicEnabled(true) }
                return nil
            case .stopTalking:
                PushToTalkOwnership.release(.space)
                client.setMicEnabled(false)
                return nil
            }
        }
    }

    private func removeKeyMonitor() {
        if let keyMonitor { NSEvent.removeMonitor(keyMonitor) }
        keyMonitor = nil
        // A held Space must not leave the mic stuck on if the window goes away.
        if PushToTalkOwnership.release(.space) { client.setMicEnabled(false) }
    }
}

/// The web's isTypingTarget (MicControls.tsx:13-17), native form: the
/// key window's first responder is editing text.
@MainActor
func isTypingTarget() -> Bool {
    guard let responder = NSApp.keyWindow?.firstResponder else { return false }
    return responder is NSTextView || responder is NSTextField
}

/// C7a: a non-text AppKit control holds keyboard focus (Full Keyboard
/// Access), so Space belongs to it, as everywhere else on the Mac.
@MainActor
func isFocusedControl() -> Bool {
    guard let control = NSApp.keyWindow?.firstResponder as? NSControl else { return false }
    return !(control is NSTextField) && control.isEnabled
}

/// C7a: SwiftUI controls that want Space while they hold focus. SwiftUI
/// focus is not visible as an AppKit first responder, so a focused
/// approval button claims Space here (`.onChange(of:)` its @FocusState)
/// and releases it when focus leaves or the button goes away.
@MainActor
enum SpaceKeyClaims {
    private(set) static var claims: Set<UUID> = []
    static var isClaimed: Bool { !claims.isEmpty }
    static func claim(_ id: UUID) { claims.insert(id) }
    static func release(_ id: UUID) { claims.remove(id) }
    static func releaseAll() { claims = [] }
}

/// C7a: who gets one Space key event. Pure, so the rule is unit-tested.
///
/// - Text editing keeps Space, always.
/// - A push-to-talk press that started keeps its key up (and swallows its
///   repeats), wherever focus moved meanwhile, so the mic never sticks on.
/// - Otherwise a focused control gets Space: it presses that control.
/// - Otherwise Space is push-to-talk, as before (MicControls.tsx).
enum SpaceKeyRoute: Equatable {
    case passThrough, swallow, startTalking, stopTalking

    static func route(isKeyDown: Bool, isRepeat: Bool, typingTarget: Bool,
                      focusedControl: Bool, connected: Bool, owned: Bool) -> SpaceKeyRoute {
        if typingTarget { return .passThrough }
        if isKeyDown {
            if owned { return .swallow }
            if focusedControl { return .passThrough }
            guard connected, !isRepeat else { return .swallow }
            return .startTalking
        }
        return owned ? .stopTalking : .passThrough
    }
}
