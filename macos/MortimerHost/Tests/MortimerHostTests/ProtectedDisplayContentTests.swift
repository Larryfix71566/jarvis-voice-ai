import XCTest
import AppKit
import SwiftUI
import ScreenCaptureKit
import JarvisKit
@testable import MortimerHost

@MainActor
final class ProtectedDisplayContentTests: XCTestCase {
    private var window: NSWindow?

    override func tearDown() {
        window?.close()
        window = nil
        super.tearDown()
    }

    func testProtectedPayloadRendersOnlyItsNonSelectableLocalBody() throws {
        _ = NSApplication.shared
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","body":"Protected body canary","surface":"window","data_policy":"local_only","images":["https://private.example.invalid/image.png"],"basemap_images":["https://private.example.invalid/basemap-canary.png"],"links":[{"label":"Private source canary","url":"https://private.example.invalid/source?token=secret"}],"commands":["private command canary"],"content":"private clipboard canary"}"#.utf8))
        let view = host(payload)
        let labels = accessibilityLabels(in: view)
        let protectedPixels = try pixels(of: view)
        window?.close(); window = nil

        let bodyOnly = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","body":"Protected body canary","surface":"window","data_policy":"local_only"}"#.utf8))
        let bodyOnlyView = host(bodyOnly)
        let bodyOnlyPixels = try pixels(of: bodyOnlyView)
        XCTAssertEqual(protectedPixels, bodyOnlyPixels,
                       "protected rendering must ignore links, images, commands, and clipboard fields")
        XCTAssertFalse(labels.contains("Copy command"), "protected rendering exposed command copy: \(labels)")
        window?.close(); window = nil

        let emptyProtected = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected","surface":"window","data_policy":"local_only"}"#.utf8))
        let emptyView = host(emptyProtected)
        XCTAssertNotEqual(bodyOnlyPixels, try pixels(of: emptyView),
                          "the protected body should still render locally")
    }

    func testProtectedAutomatedPNGContainsOnlyTheLocalBody() throws {
        _ = NSApplication.shared
        let protectedPayload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected screenshot title canary","body":"Visible protected body","surface":"window","data_policy":"local_only","images":["https://protected-image-canary.invalid/image.png"],"basemap_images":["https://protected-basemap-canary.invalid/map.png"],"links":[{"label":"Protected link canary","url":"https://protected-link-canary.invalid/?token=secret"}],"commands":["protected command canary"],"content":"protected clipboard canary"}"#.utf8))
        let bodyOnlyPayload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected screenshot title canary","body":"Visible protected body","surface":"window","data_policy":"local_only"}"#.utf8))

        let protectedPNG = FileManager.default.temporaryDirectory
            .appendingPathComponent("mortimer-protected-\(UUID().uuidString).png")
        let bodyOnlyPNG = FileManager.default.temporaryDirectory
            .appendingPathComponent("mortimer-protected-reference-\(UUID().uuidString).png")
        defer {
            try? FileManager.default.removeItem(at: protectedPNG)
            try? FileManager.default.removeItem(at: bodyOnlyPNG)
            window?.close()
            window = nil
        }

        try writePNG(of: host(protectedPayload), to: protectedPNG)
        window?.close(); window = nil
        try writePNG(of: host(bodyOnlyPayload), to: bodyOnlyPNG)

        let protectedBytes = try Data(contentsOf: protectedPNG)
        let bodyOnlyBytes = try Data(contentsOf: bodyOnlyPNG)
        let protectedImage = try XCTUnwrap(NSBitmapImageRep(data: protectedBytes))
        let bodyOnlyImage = try XCTUnwrap(NSBitmapImageRep(data: bodyOnlyBytes))
        XCTAssertEqual(protectedImage.pixelsWide, bodyOnlyImage.pixelsWide)
        XCTAssertEqual(protectedImage.pixelsHigh, bodyOnlyImage.pixelsHigh)
        XCTAssertEqual(rgbaPixels(protectedImage), rgbaPixels(bodyOnlyImage),
                       "an automated PNG sink must contain the same pixels as the protected body-only view")

        let protectedMarkers = [
            "Protected screenshot title canary", "protected-image-canary.invalid",
            "protected-basemap-canary.invalid", "protected-link-canary.invalid", "protected command canary",
            "protected clipboard canary",
        ]
        for marker in protectedMarkers {
            XCTAssertFalse(protectedBytes.range(of: Data(marker.utf8)) != nil,
                           "PNG bytes contain protected plaintext marker: \(marker)")
        }
    }

    func testProtectedContentInActualWindowCaptureMatchesBodyOnlyReference() async throws {
        guard CGPreflightScreenCaptureAccess() else {
            throw XCTSkip("Grant Screen Recording to the test runner to exercise real window capture")
        }
        let app = NSApplication.shared
        guard !NSScreen.screens.isEmpty else {
            throw XCTSkip("requires an interactive WindowServer with at least one screen; real window capture is unavailable")
        }
        let originalPolicy = app.activationPolicy()
        guard app.setActivationPolicy(.regular) else {
            throw XCTSkip("the test process cannot activate as a regular app in this WindowServer session")
        }
        defer { _ = app.setActivationPolicy(originalPolicy) }
        app.finishLaunching()
        app.activate(ignoringOtherApps: true)
        do {
            try waitUntil("the test host app becomes active") { app.isActive }
        } catch let error as NSError
            where error.domain == "ProtectedDisplayContentTests.WindowCapturePrerequisite" {
            throw XCTSkip("the test host cannot become active in this WindowServer session; real window capture is unavailable")
        }

        let protected = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Captured title canary","body":"Visible captured body","surface":"window","data_policy":"local_only","links":[{"label":"captured-link-canary","url":"https://private.invalid/?token=secret"}],"images":["https://private.invalid/image.png"],"basemap_images":["https://private.invalid/basemap-canary.png"],"commands":["captured command canary"],"content":"captured clipboard canary"}"#.utf8))
        let bodyOnly = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Captured title canary","body":"Visible captured body","surface":"window","data_policy":"local_only"}"#.utf8))

        let capturedView = host(protected)
        let capturedWindow = try XCTUnwrap(window)
        showForCapture(capturedWindow)
        try waitUntil("the protected fixture window is visible and unoccluded") {
            capturedWindow.isVisible && capturedWindow.occlusionState.contains(.visible)
        }
        let protectedCapture = try await captureWindowPNG(capturedWindow)

        // Use the same live window for both payloads. Closing and recreating it changes
        // the WindowServer edge/compositing pixels independently of the SwiftUI content.
        capturedView.rootView = displayView(bodyOnly)
        capturedView.layoutSubtreeIfNeeded()
        capturedWindow.displayIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))
        try waitUntil("the body-only reference window is visible and unoccluded") {
            capturedWindow.isVisible && capturedWindow.occlusionState.contains(.visible)
        }
        let referenceCapture = try await captureWindowPNG(capturedWindow)

        let protectedImage = try XCTUnwrap(NSBitmapImageRep(data: protectedCapture))
        let referenceImage = try XCTUnwrap(NSBitmapImageRep(data: referenceCapture))
        XCTAssertEqual(protectedImage.pixelsWide, referenceImage.pixelsWide)
        XCTAssertEqual(protectedImage.pixelsHigh, referenceImage.pixelsHigh)
        let protectedPixels = rgbaPixels(protectedImage)
        let referencePixels = rgbaPixels(referenceImage)
        if protectedPixels != referencePixels {
            XCTFail("OS window-capture PNG differs from the protected body-only rendering: "
                    + pixelDifferenceSummary(protectedPixels, referencePixels,
                                             width: protectedImage.pixelsWide))
        }
    }

    func testOrdinaryPayloadKeepsCommandCopyAffordance() throws {
        _ = NSApplication.shared
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Ordinary","body":"Ordinary body","commands":["echo ordinary"]}"#.utf8))
        let labels = accessibilityLabels(in: host(payload))
        XCTAssertTrue(labels.contains("Copy command"), "ordinary command copy affordance regressed: \(labels)")
    }

    private func host(_ payload: DisplayPayload) -> NSHostingView<AnyView> {
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let view = NSHostingView(rootView: displayView(payload))
        view.frame = NSRect(x: 0, y: 0, width: 620, height: 420)
        let hostWindow = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        hostWindow.isReleasedWhenClosed = false
        hostWindow.contentView = view
        hostWindow.orderFrontRegardless()
        window = hostWindow
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.15))
        return view
    }

    private func displayView(_ payload: DisplayPayload) -> AnyView {
        AnyView(DisplayContentView(payload: payload)
            .padding(12).background(AppTheme.bg).foregroundStyle(AppTheme.text)
            .preferredColorScheme(.dark))
    }

    private func showForCapture(_ window: NSWindow) {
        window.level = .floating
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
    }

    private func waitUntil(_ description: String, timeout: TimeInterval = 3,
                           condition: () -> Bool) throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() && Date() < deadline {
            if let event = NSApp.nextEvent(matching: .any, until: Date().addingTimeInterval(0.01),
                                           inMode: .default, dequeue: true) {
                NSApp.sendEvent(event)
            }
            NSApp.updateWindows()
            RunLoop.main.run(until: Date().addingTimeInterval(0.005))
        }
        guard condition() else {
            throw NSError(domain: "ProtectedDisplayContentTests.WindowCapturePrerequisite",
                          code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Timed out waiting for \(description)"])
        }
    }

    private func accessibilityLabels(in view: NSView) -> [String] {
        var labels: [String] = []
        func visit(_ value: Any) {
            if let element = value as? NSAccessibilityProtocol {
                if let label = element.accessibilityLabel(), !label.isEmpty { labels.append(label) }
                for child in element.accessibilityChildren() ?? [] { visit(child) }
            } else if let element = value as? NSObject {
                let labelSelector = NSSelectorFromString("accessibilityLabel")
                if element.responds(to: labelSelector),
                   let label = element.perform(labelSelector)?.takeUnretainedValue() as? String,
                   !label.isEmpty { labels.append(label) }
                let childrenSelector = NSSelectorFromString("accessibilityChildren")
                if element.responds(to: childrenSelector),
                   let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                    children.forEach(visit)
                }
            }
        }
        visit(view)
        return labels
    }

    private func pixels(of view: NSView) throws -> [UInt8] {
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let count = bitmap.bytesPerRow * bitmap.pixelsHigh
        return Array(UnsafeBufferPointer(start: bitmap.bitmapData, count: count))
    }

    private func writePNG(of view: NSView, to url: URL) throws {
        let bitmap = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        try png.write(to: url, options: .atomic)
    }

    private func captureWindowPNG(_ window: NSWindow) async throws -> Data {
        let shareable = try await SCShareableContent.excludingDesktopWindows(false,
                                                                               onScreenWindowsOnly: true)
        let windowID = CGWindowID(window.windowNumber)
        let captureWindow = try XCTUnwrap(shareable.windows.first { $0.windowID == windowID },
                                          "the live test window should appear in ScreenCaptureKit's inventory")
        let filter = SCContentFilter(desktopIndependentWindow: captureWindow)
        let configuration = SCStreamConfiguration()
        configuration.width = max(1, Int(window.frame.width * window.backingScaleFactor))
        configuration.height = max(1, Int(window.frame.height * window.backingScaleFactor))
        let image = try await SCScreenshotManager.captureImage(contentFilter: filter,
                                                               configuration: configuration)
        return try XCTUnwrap(NSBitmapImageRep(cgImage: image)
            .representation(using: .png, properties: [:]))
    }

    private func rgbaPixels(_ bitmap: NSBitmapImageRep) -> [UInt8] {
        var pixels: [UInt8] = []
        pixels.reserveCapacity(bitmap.pixelsWide * bitmap.pixelsHigh * 4)
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB)
                pixels.append(UInt8(((color?.redComponent ?? 0) * 255).rounded()))
                pixels.append(UInt8(((color?.greenComponent ?? 0) * 255).rounded()))
                pixels.append(UInt8(((color?.blueComponent ?? 0) * 255).rounded()))
                pixels.append(UInt8(((color?.alphaComponent ?? 0) * 255).rounded()))
            }
        }
        return pixels
    }

    private func pixelDifferenceSummary(_ actual: [UInt8], _ expected: [UInt8],
                                        width: Int) -> String {
        guard actual.count == expected.count, width > 0 else {
            return "RGBA lengths \(actual.count) and \(expected.count) differ"
        }
        var count = 0
        var minX = width
        var minY = Int.max
        var maxX = 0
        var maxY = 0
        for pixel in 0..<(actual.count / 4) {
            let offset = pixel * 4
            guard actual[offset] != expected[offset]
                || actual[offset + 1] != expected[offset + 1]
                || actual[offset + 2] != expected[offset + 2]
                || actual[offset + 3] != expected[offset + 3] else { continue }
            count += 1
            let x = pixel % width
            let y = pixel / width
            minX = min(minX, x)
            minY = min(minY, y)
            maxX = max(maxX, x)
            maxY = max(maxY, y)
        }
        return "\(count) differing pixels; bounds x=\(minX)...\(maxX), "
            + "y=\(minY)...\(maxY) across the full window"
    }
}
