import XCTest
import AppKit
import SwiftUI
@testable import MortimerHost

@MainActor
final class KnowledgeAtlasTests: XCTestCase {
    func testAtlasSearchAndSelectionPreserveStableCardIdentity() {
        let store = AtlasStore()
        let first = AtlasCard(id: UUID(), title: "Weather", summary: "Forecast", source: "tool", group: nil)
        let second = AtlasCard(id: UUID(), title: "Repository", summary: "Changes", source: nil, group: nil)
        store.replace([first, second]); store.setQuery("weather")
        XCTAssertEqual(store.visibleCards.map(\.id), [first.id])
        store.select(first.id); XCTAssertEqual(store.selectedID, first.id)
        store.assign(first.id, to: "Research"); XCTAssertTrue(store.groups["Research"]?.contains(first.id) == true)
    }

    func testAtlasCardAccessibilityExposesSummaryAndSource() {
        let result = AtlasCard(id: UUID(), title: "Weather", summary: "Rain after 4 PM",
                               source: "National Weather Service", group: nil)
        XCTAssertEqual(result.accessibilityLabel, "Result: Weather")
        XCTAssertEqual(result.accessibilityValue,
                       "Rain after 4 PM. Source: National Weather Service")

        let context = AtlasCard(id: UUID(), title: "Architecture", summary: "Local-first design",
                                source: nil, group: nil, kind: .architecture)
        XCTAssertEqual(context.accessibilityLabel, "Architecture: Architecture")
        XCTAssertEqual(context.accessibilityValue, "Local-first design")
    }

    func testMountedAtlasResultControlExposesAccessibilityLabelAndValue() throws {
        _ = NSApplication.shared
        NSApplication.shared.accessibilitySetValue(true,
            forAttribute: NSAccessibility.Attribute(rawValue: "AXEnhancedUserInterface"))
        let card = AtlasCard(id: UUID(), title: "Weather", summary: "Rain after 4 PM",
                             source: "National Weather Service")
        var opened = false
        let view = NSHostingView(rootView: AtlasCardButton(card: card, selected: false) {
            opened = true
        }
            .frame(width: 320, height: 180))
        view.frame = NSRect(x: 0, y: 0, width: 320, height: 180)
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = view
        window.orderFrontRegardless()
        defer { closeRenderingFixtureWindow(window) }
        view.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.2))

        var accessiblePairs: [(String, String)] = []
        var resultControl: NSObject?
        func visit(_ value: Any) {
            guard let element = value as? NSObject else { return }
            let labelSelector = NSSelectorFromString("accessibilityLabel")
            let valueSelector = NSSelectorFromString("accessibilityValue")
            let label = element.responds(to: labelSelector)
                ? element.perform(labelSelector)?.takeUnretainedValue() as? String : nil
            let accessibleValue = element.responds(to: valueSelector)
                ? element.perform(valueSelector)?.takeUnretainedValue() as? String : nil
            if let label, let accessibleValue {
                accessiblePairs.append((label, accessibleValue))
                if label == "Result: Weather" { resultControl = element }
            }
            let childrenSelector = NSSelectorFromString("accessibilityChildren")
            if element.responds(to: childrenSelector),
               let children = element.perform(childrenSelector)?.takeUnretainedValue() as? [Any] {
                children.forEach(visit)
            }
        }
        visit(view)
        XCTAssertTrue(accessiblePairs.contains {
            $0.0 == "Result: Weather" &&
            $0.1 == "Rain after 4 PM. Source: National Weather Service"
        }, "Mounted Atlas button must expose its full accessible label/value; tree: \(accessiblePairs)")
        let press = NSSelectorFromString("accessibilityPerformPress")
        let control = try XCTUnwrap(resultControl)
        XCTAssertTrue(control.responds(to: press), "Atlas result must expose the standard press action")
        _ = control.perform(press)
        XCTAssertTrue(opened, "Pressing the accessibility control must activate result selection")
    }

    func testVoicePlacementSupportsExactGridAndCollisionSafeRelativeMoves() {
        let store = AtlasStore()
        let cards = (0..<4).map { index in
            AtlasCard(id: UUID(), title: "Card (index)", summary: "Summary", source: nil, group: nil)
        }
        store.replace(cards)
        XCTAssertEqual(store.position(of: cards[0].id), AtlasGridPosition(row: 1, column: 1))
        XCTAssertEqual(store.position(of: cards[3].id), AtlasGridPosition(row: 2, column: 1))

        XCTAssertTrue(store.move(cards[2].id, row: 2, column: 2))
        XCTAssertFalse(store.move(cards[3].id, row: 2, column: 2), "occupied exact slots are never overwritten")
        XCTAssertTrue(store.move(cards[3].id, relativeTo: cards[0].id, relation: "right"))
        XCTAssertEqual(store.position(of: cards[3].id), AtlasGridPosition(row: 3, column: 2),
                       "right moves descend until a free adjacent slot exists")
        XCTAssertTrue(store.move(cards[1].id, relativeTo: cards[0].id, relation: "left"))
        XCTAssertEqual(store.position(of: cards[1].id), AtlasGridPosition(row: 2, column: 1))
        XCTAssertTrue(store.move(cards[2].id, relativeTo: cards[0].id, relation: "left"))
        XCTAssertEqual(store.position(of: cards[2].id), AtlasGridPosition(row: 3, column: 1),
                       "left moves descend until a free adjacent slot exists")

        store.arrange()
        XCTAssertEqual(store.position(of: cards[0].id), AtlasGridPosition(row: 1, column: 1))
    }

    func testContextRefreshRetainsResultIdentityAndManualPlacement() {
        let store = AtlasStore()
        let result = AtlasCard(id: UUID(), title: "Weather", summary: "Forecast", source: "tool")
        let firstContext = AtlasCard(id: AtlasStore.stableID(namespace: "memory", key: "overview"),
                                     title: "Memory", summary: "One fact", source: "memory",
                                     kind: .memory)
        store.replace(results: [result], context: [firstContext])
        XCTAssertTrue(store.move(result.id, row: 3, column: 2))
        store.assign(result.id, to: "Research")

        let refreshed = AtlasCard(id: firstContext.id, title: "Memory", summary: "Two facts", source: "memory",
                                  kind: .memory)
        let architecture = AtlasCard(id: AtlasStore.stableID(namespace: "architecture", key: "docs/ARCHITECTURE.md"),
                                     title: "Architecture", summary: "Contract", source: "docs/ARCHITECTURE.md",
                                     kind: .architecture)
        store.replaceContext([refreshed, architecture])

        XCTAssertEqual(store.cards.first(where: { $0.id == result.id })?.title, "Weather")
        XCTAssertEqual(store.position(of: result.id), AtlasGridPosition(row: 3, column: 2))
        XCTAssertTrue(store.groups["Research"]?.contains(result.id) == true)
        XCTAssertEqual(store.cardsByKind[.architecture]?.count, 1)
        XCTAssertEqual(store.cards.first(where: { $0.id == firstContext.id })?.summary, "Two facts")
    }

    func testStableContextIdentityIsRepeatableAndNamespaced() {
        let a = AtlasStore.stableID(namespace: "memory", key: "overview")
        XCTAssertEqual(a, AtlasStore.stableID(namespace: "memory", key: "overview"))
        XCTAssertNotEqual(a, AtlasStore.stableID(namespace: "plan", key: "overview"))
    }

    func testSourceRefreshRejectsObsoleteResponsesAndPreservesLastGoodCards() {
        let store = AtlasStore()
        let result = AtlasCard(id: UUID(), title: "Research", summary: "Result", source: nil)
        store.replaceResults([result])
        let first = AtlasCard(id: AtlasStore.stableID(namespace: "architecture", key: "a"),
                              title: "Architecture", summary: "Old", source: "a",
                              kind: .architecture)

        let oldGeneration = store.beginRefresh(.architecture)
        let currentGeneration = store.beginRefresh(.architecture)
        XCTAssertFalse(store.completeRefresh(.architecture, generation: oldGeneration, cards: [first]))
        XCTAssertTrue(store.completeRefresh(.architecture, generation: currentGeneration,
                                            cards: [first], now: Date(timeIntervalSince1970: 10)))
        XCTAssertEqual(store.sourceHealth[.architecture]?.phase, .loaded)
        XCTAssertEqual(store.sourceHealth[.architecture]?.lastSuccessAt,
                       Date(timeIntervalSince1970: 10))

        let failedGeneration = store.beginRefresh(.architecture)
        XCTAssertTrue(store.failRefresh(.architecture, generation: failedGeneration,
                                        category: .unavailable))
        XCTAssertEqual(store.sourceHealth[.architecture]?.phase, .failed)
        XCTAssertTrue(store.sourceHealth[.architecture]?.stale == true)
        XCTAssertEqual(store.cards.first(where: { $0.id == first.id })?.summary, "Old")
        XCTAssertTrue(store.cards.contains(where: { $0.id == result.id }))
    }

    func testSuccessfulEmptySourceIsDistinctFromLoadFailure() {
        let store = AtlasStore()
        let generation = store.beginRefresh(.runs)
        XCTAssertTrue(store.completeRefresh(.runs, generation: generation, cards: []))
        XCTAssertEqual(store.sourceHealth[.runs]?.phase, .empty)
        XCTAssertNil(store.sourceHealth[.runs]?.failure)

        let retry = store.beginRefresh(.runs)
        XCTAssertTrue(store.failRefresh(.runs, generation: retry, category: .timedOut))
        XCTAssertEqual(store.sourceHealth[.runs]?.phase, .failed)
        XCTAssertEqual(store.sourceHealth[.runs]?.failure, .timedOut)
        XCTAssertFalse(store.sourceHealth[.runs]?.stale ?? true)
    }

    func testStoreOwnedRefreshLoadsCardsAndRecordsFailure() async throws {
        let store = AtlasStore()
        let card = AtlasCard(id: AtlasStore.stableID(namespace: "memory", key: "overview"),
                             title: "Memory", summary: "One fact", source: "memory",
                             kind: .memory)
        store.refresh(source: .memory, classifyFailure: { _ in .unavailable }) { [card] }
        try await waitForRefresh(store, source: .memory)
        XCTAssertEqual(store.sourceHealth[.memory]?.phase, .loaded)
        XCTAssertEqual(store.contextCards, [card])

        store.refresh(source: .memory, force: true, classifyFailure: { _ in .timedOut }) {
            throw URLError(.timedOut)
        }
        try await waitForRefresh(store, source: .memory)
        XCTAssertEqual(store.sourceHealth[.memory]?.phase, .failed)
        XCTAssertEqual(store.sourceHealth[.memory]?.failure, .timedOut)
        XCTAssertTrue(store.sourceHealth[.memory]?.stale == true)
        XCTAssertEqual(store.contextCards, [card], "a failed refresh retains the last good projection")
    }

    func testIndependentSourceFailurePreservesOtherSourceCardsAndHealth() async throws {
        let store = AtlasStore()
        let memory = AtlasCard(id: AtlasStore.stableID(namespace: "memory", key: "overview"),
                               title: "Memory", summary: "Available", source: "memory",
                               kind: .memory)
        let architecture = AtlasCard(
            id: AtlasStore.stableID(namespace: "architecture", key: "architecture.md"),
            title: "Architecture", summary: "Last good", source: "architecture.md",
            kind: .architecture)

        store.refresh(source: .memory, classifyFailure: { _ in .unavailable }) { [memory] }
        store.refresh(source: .architecture, classifyFailure: { _ in .unavailable }) { [architecture] }
        try await waitForRefresh(store, source: .memory)
        try await waitForRefresh(store, source: .architecture)
        XCTAssertEqual(store.sourceHealth[.memory]?.phase, .loaded)
        XCTAssertEqual(store.sourceHealth[.architecture]?.phase, .loaded)

        store.refresh(source: .architecture, force: true,
                      classifyFailure: { _ in .timedOut }) {
            throw URLError(.timedOut)
        }
        try await waitForRefresh(store, source: .architecture)

        XCTAssertEqual(store.sourceHealth[.memory]?.phase, .loaded)
        XCTAssertEqual(store.sourceHealth[.architecture]?.phase, .failed)
        XCTAssertTrue(store.sourceHealth[.architecture]?.stale == true)
        XCTAssertTrue(store.contextCards.contains(where: { $0.id == memory.id }))
        XCTAssertTrue(store.contextCards.contains(where: { $0.id == architecture.id }))
    }

    func testOverlappingRefreshesCoalescePerSource() async throws {
        let store = AtlasStore()
        let card = AtlasCard(id: AtlasStore.stableID(namespace: "runs", key: "latest"),
                             title: "Latest run", summary: "Complete", source: "runs",
                             kind: .run)
        var loads = 0
        store.refresh(source: .runs, classifyFailure: { _ in .unavailable }) {
            loads += 1
            try await Task.sleep(for: .milliseconds(10))
            return [card]
        }
        store.refresh(source: .runs, classifyFailure: { _ in .unavailable }) {
            loads += 1
            return []
        }
        try await waitForRefresh(store, source: .runs)

        XCTAssertEqual(loads, 1)
        XCTAssertEqual(store.contextCards, [card])
        XCTAssertEqual(store.sourceHealth[.runs]?.phase, .loaded)
    }

    func testExplicitRetryRecoversAfterTransientSourceFailure() async throws {
        let store = AtlasStore()
        var attempts = 0
        store.refresh(source: .plan, classifyFailure: { _ in .unavailable }) {
            attempts += 1
            throw URLError(.userAuthenticationRequired)
        }
        try await waitForRefresh(store, source: .plan)
        XCTAssertEqual(store.sourceHealth[.plan]?.phase, .failed)
        XCTAssertFalse(store.sourceHealth[.plan]?.stale ?? true)

        let recovered = AtlasCard(id: AtlasStore.stableID(namespace: "plan", key: "current"),
                                  title: "Current plan", summary: "Ready", source: "plan",
                                  kind: .plan)
        store.refresh(source: .plan, force: true,
                      classifyFailure: { _ in .unavailable }) {
            attempts += 1
            return [recovered]
        }
        try await waitForRefresh(store, source: .plan)

        XCTAssertEqual(attempts, 2)
        XCTAssertEqual(store.sourceHealth[.plan]?.phase, .loaded)
        XCTAssertFalse(store.sourceHealth[.plan]?.stale ?? true)
        XCTAssertEqual(store.contextCards, [recovered])
    }

    private func waitForRefresh(_ store: AtlasStore, source: AtlasContextSource) async throws {
        for _ in 0..<100 where store.sourceHealth[source]?.phase == .loading {
            try await Task.sleep(for: .milliseconds(1))
        }
        XCTAssertNotEqual(store.sourceHealth[source]?.phase, .loading, "refresh task should finish")
    }
}
