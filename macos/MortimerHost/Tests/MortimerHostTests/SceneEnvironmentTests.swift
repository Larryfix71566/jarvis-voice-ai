import XCTest
@testable import MortimerHost

/// 2026-09-30 crash: "display_popout" opened the Mortimer Display window,
/// whose DisplayWindowView reads SkillsStore from the environment, but that
/// scene never injected it, so SwiftUI trapped in EnvironmentValues. Every
/// content window must carry the same app stores as the console.
final class SceneEnvironmentTests: XCTestCase {
    func testEveryContentWindowInjectsTheConsolesStores() throws {
        let root = GraphFixture.repositoryRoot()
        let source = try String(contentsOf: root.appendingPathComponent(
            "macos/MortimerHost/Sources/MortimerHost/App/MortimerHostApp.swift"), encoding: .utf8)
        let body = try XCTUnwrap(source.range(of: "var body: some Scene")).lowerBound
        let text = String(source[body...])
        let scene = try NSRegularExpression(pattern: #"\n\s*(Window|WindowGroup)\("([^"]+)""#)
        let env = try NSRegularExpression(pattern: #"\.environment\((\w+)\)"#)
        let ns = text as NSString
        let matches = scene.matches(in: text, range: NSRange(location: 0, length: ns.length))
        var stores: [String: Set<String>] = [:]
        for (i, m) in matches.enumerated() {
            let end = i + 1 < matches.count ? matches[i + 1].range.location : ns.length
            let block = ns.substring(with: NSRange(location: m.range.location, length: end - m.range.location))
            let title = ns.substring(with: m.range(at: 2))
            let b = block as NSString
            stores[title] = Set(env.matches(in: block, range: NSRange(location: 0, length: b.length))
                .map { b.substring(with: $0.range(at: 1)) })
        }
        let console = try XCTUnwrap(stores["Mortimer"], "console scene not found: \(stores.keys.sorted())")
        XCTAssertTrue(console.contains("skills"))
        for title in ["Mortimer Display", "Mortimer Drawer", "Mortimer Panel", "Mortimer Content"] {
            let have = try XCTUnwrap(stores[title], "scene \(title) not found")
            XCTAssertEqual(console.subtracting(have).sorted(), [], "\(title) lacks console stores")
        }
    }
}
