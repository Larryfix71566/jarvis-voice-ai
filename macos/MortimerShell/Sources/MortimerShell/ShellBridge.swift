// ShellBridge.swift
// B2 — the native side of window.mortimerShell's message channel.
// popoutWindow.ts posts {cmd:"openWindow", name:"display"|"drawer"}
// through webkit.messageHandlers.mortimer; this class receives it and
// asks ShellController to open/focus the matching native window.

import Foundation
import SwiftUI
import WebKit

final class ShellBridge: NSObject, WKScriptMessageHandler {
    private let controller: ShellController
    private let openWindow: OpenWindowAction

    init(controller: ShellController, openWindow: OpenWindowAction) {
        self.controller = controller
        self.openWindow = openWindow
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard message.name == "mortimer",
              let body = message.body as? [String: Any],
              let cmd = body["cmd"] as? String
        else { return }

        switch cmd {
        case "openWindow":
            guard let name = body["name"] as? String else { return }
            Task { @MainActor in
                self.controller.openWindow(named: name, environment: self.openWindow)
            }
        default:
            break // unknown command — ignored, never crashes the bridge
        }
    }
}
