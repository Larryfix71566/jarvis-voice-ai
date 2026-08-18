// ShellBridge.swift
// B2 — the native side of window.mortimerShell's message channel.
// popoutWindow.ts posts {cmd:"openWindow", name:"display"|"drawer"}
// through webkit.messageHandlers.mortimer; this class receives it and
// asks ShellController to open/focus the matching native window.

import Foundation
import SwiftUI
import WebKit
import os

private let logger = Logger(subsystem: "com.mortimer.shell", category: "bridge")

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
        // S3 — log every bridge message, including malformed ones. This
        // handler used to fail every unrecognized shape completely
        // silently; S1's name-contract bug went undiagnosed for a full
        // session because of exactly that.
        guard message.name == "mortimer" else {
            logger.error("didReceive: unexpected handler name '\(message.name, privacy: .public)'")
            return
        }
        guard let body = message.body as? [String: Any] else {
            logger.error("didReceive: body is not a dictionary: \(String(describing: message.body), privacy: .public)")
            return
        }
        guard let cmd = body["cmd"] as? String else {
            logger.error("didReceive: body missing string 'cmd': \(String(describing: body), privacy: .public)")
            return
        }

        switch cmd {
        case "openWindow":
            guard let name = body["name"] as? String else {
                logger.error("didReceive openWindow: missing string 'name'")
                return
            }
            logger.debug("didReceive openWindow name='\(name, privacy: .public)'")
            Task { @MainActor in
                self.controller.openWindow(named: name, environment: self.openWindow)
            }
        case "closeWindow":
            // Close-path mirror of openWindow (2026-08-18): inside the
            // shell, web-side window.close() can't close a native
            // window, so pop-in asks us to do it. Same bare-role name
            // contract as openWindow (S1).
            guard let name = body["name"] as? String else {
                logger.error("didReceive closeWindow: missing string 'name'")
                return
            }
            logger.debug("didReceive closeWindow name='\(name, privacy: .public)'")
            Task { @MainActor in
                self.controller.closeWindow(named: name)
            }
        default:
            logger.error("didReceive: unrecognized cmd '\(cmd, privacy: .public)' — ignored, never crashes the bridge")
        }
    }
}
