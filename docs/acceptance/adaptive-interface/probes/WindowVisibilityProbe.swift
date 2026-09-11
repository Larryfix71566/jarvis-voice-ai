import AppKit
import Foundation

@MainActor
final class ProbeDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var view: WindowVisibilityView!
    var reported: Bool?
    var checks: [[String: Any]] = []
    func applicationDidFinishLaunching(_ notification: Notification) {
        view = WindowVisibilityView(frame: NSRect(x: 0, y: 0, width: 400, height: 240))
        view.changed = { [weak self] in self?.reported = $0 }
        window = NSWindow(contentRect: view.frame, styleMask: [.titled, .miniaturizable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        later { self.check("shown", expected: true); self.window.orderOut(nil)
            self.later { self.check("hidden", expected: false); self.window.makeKeyAndOrderFront(nil)
                self.later { self.check("reshown", expected: true); self.window.miniaturize(nil)
                    self.later { self.check("minimized", expected: false, condition: self.window.isMiniaturized)
                        self.window.deminiaturize(nil); self.window.makeKeyAndOrderFront(nil)
                        self.later { self.check("restored", expected: true, condition: !self.window.isMiniaturized)
                            self.window.contentView = nil
                            self.later { self.check("detached", expected: false); self.finish() }
                        }
                    }
                }
            }
        }
    }
    func later(_ operation: @escaping () -> Void) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8, execute: operation)
    }
    func check(_ name: String, expected: Bool, condition: Bool = true) {
        checks.append(["name": name, "passed": condition && reported == expected,
                       "reported": reported as Any? ?? "missing", "expected": expected,
                       "active": NSApp.isActive, "windowVisible": window.isVisible,
                       "occlusion": window.occlusionState.rawValue])
    }
    func finish() {
        let passed = checks.allSatisfy { $0["passed"] as? Bool == true }
        do {
            let data = try JSONSerialization.data(withJSONObject: ["passed": passed, "checks": checks], options: [.prettyPrinted, .sortedKeys])
            try data.write(to: URL(fileURLWithPath: "/Users/mortimer-dev/visibility-probe-result.json"), options: .atomic)
        } catch { }
        NSApp.terminate(nil)
    }
}

@main struct VisibilityProbe {
    static func main() {
        let application = NSApplication.shared
        let delegate = ProbeDelegate()
        application.delegate = delegate
        withExtendedLifetime(delegate) { application.run() }
    }
}
