import XCTest
import AppKit
@testable import MortimerHost

@MainActor
final class ContentWindowRegistryTests: XCTestCase {
    func testRegistrationIsValueAddressedAndLifecycleOperationsAreIdempotent() {
        let registry = ContentWindowRegistry()
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 200, height: 120),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        registry.register(window, id: "results")
        XCTAssertTrue(registry.window(id: "results") === window)
        registry.register(window, id: "results")
        XCTAssertEqual(registry.windows.count, 1)
        registry.unregister(id: "missing")
        XCTAssertTrue(registry.window(id: "results") === window)
        registry.unregister(id: "results")
        XCTAssertNil(registry.window(id: "results"))
        registry.register(window, id: "results")
        registry.closeAll()
        XCTAssertTrue(registry.windows.isEmpty)
    }
}
