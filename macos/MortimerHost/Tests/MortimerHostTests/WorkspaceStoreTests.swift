import XCTest
import JarvisKit
@testable import MortimerHost

@MainActor
final class WorkspaceStoreTests: XCTestCase {
    private func result() throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self,
            from: Data(#"{"body":"Research result","surface":"drawer"}"#.utf8))
        return WorkspaceResult(payload: payload)
    }

    private func protectedResult() throws -> WorkspaceResult {
        let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
            #"{"title":"Protected title canary","body":"Protected body canary","data_policy":"local_only"}"#.utf8))
        return WorkspaceResult(payload: payload)
    }

    func testArrivalPreservesReadingComparisonAndScroll() throws {
        let store = WorkspaceStore(historyLimit: 2)
        let a = try result(), b = try result()
        store.receive(a)
        store.receive(b)
        store.compare(with: b.id)
        store.rememberScroll(420, for: a.id)
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.activeID, a.id)
        XCTAssertEqual(store.comparisonID, b.id)
        XCTAssertEqual(store.scrollOffsets[a.id], 420)
        XCTAssertEqual(store.results.count, 4)
    }

    func testExplicitConversationChoiceSurvivesNewResults() throws {
        let store = WorkspaceStore()
        store.receive(try result())
        store.returnToConversation()
        store.receive(try result())
        XCTAssertTrue(store.showsConversation)
        XCTAssertEqual(store.unreadIDs.count, 1)
    }

    func testFirstResultDoesNotUndoReturnFromGraphToConversation() throws {
        let store = WorkspaceStore()
        store.openMemoryGraph()
        store.returnToConversation()
        let incoming = try result()
        store.receive(incoming)

        XCTAssertTrue(store.showsConversation, "A result must not undo explicit navigation.")
        XCTAssertEqual(store.activeID, incoming.id, "The result must remain reachable from conversation.")
        XCTAssertTrue(store.unreadIDs.contains(incoming.id))
    }

    func testFirstResultWhileBrowsingGraphIsUnreadAndPreservesGraph() throws {
        let store = WorkspaceStore()
        store.openMemoryGraph()
        let graph = store.memoryGraph
        let incoming = try result()
        store.receive(incoming)

        XCTAssertTrue(store.showsMemoryGraph)
        XCTAssertFalse(store.showsConversation)
        XCTAssertTrue(store.memoryGraph === graph)
        XCTAssertTrue(store.unreadIDs.contains(incoming.id), "A result hidden behind the graph has not been read.")
        store.select(incoming.id)
        XCTAssertFalse(store.showsMemoryGraph)
        XCTAssertFalse(store.unreadIDs.contains(incoming.id))
    }

    func testFirstResultStillOpensWorkspaceWithoutExplicitNavigation() throws {
        let store = WorkspaceStore()
        let incoming = try result()
        store.receive(incoming)
        XCTAssertFalse(store.showsConversation)
        XCTAssertEqual(store.activeID, incoming.id)
        XCTAssertFalse(store.unreadIDs.contains(incoming.id))
    }

    func testPinLimitRefusesWithoutEviction() throws {
        let store = WorkspaceStore(historyLimit: 1, pinLimit: 2)
        let a = try result(), b = try result(), c = try result()
        store.receive(a); XCTAssertTrue(store.pin(a.id))
        store.receive(b); XCTAssertTrue(store.pin(b.id))
        store.receive(c); XCTAssertFalse(store.pin(c.id))
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.pinnedIDs, [a.id, b.id])
        XCTAssertTrue(store.results.contains { $0.id == b.id })
    }

    func testClosingWorkspaceTabPreservesOutputHistoryAndSharedIdentity() throws {
        let workspace = WorkspaceStore(), output = DisplayResultStore()
        let received = try result()
        workspace.receive(received)
        output.apply(received.payload, workspaceID: received.id)
        XCTAssertEqual(output.results.first?.workspaceID, workspace.activeID)
        workspace.close(received.id)
        XCTAssertEqual(output.results.count, 1)
        XCTAssertNil(workspace.activeID)
        XCTAssertTrue(workspace.showsConversation)
    }

    func testIdenticalPayloadsAreDistinctButSameReceiptIsNotDuplicated() throws {
        let store = WorkspaceStore()
        let a = try result(), b = try result()
        store.receive(a); store.receive(a); store.receive(b)
        XCTAssertEqual(store.results.count, 2)
        XCTAssertNotEqual(a.id, b.id)
    }

    func testOutputExpansionBelongsToHistoryAndDoesNotReopenCollapsedItems() throws {
        let store = DisplayResultStore()
        store.apply(try result().payload)
        let first = try XCTUnwrap(store.results.first?.id)
        XCTAssertEqual(store.expandedID, first)
        store.expandedID = nil
        // A new presentation reads the same store without an on-appear reset.
        let detached = store
        XCTAssertNil(detached.expandedID)
        detached.apply(try result().payload)
        XCTAssertEqual(detached.expandedID, detached.results.first?.id)
        detached.remove(id: detached.results.first!.id)
        XCTAssertNil(detached.expandedID)
        XCTAssertEqual(detached.results.first?.id, first)
    }

    func testSupportingResultSurvivesHistoryTrimmingWithoutChangingMainSelection() throws {
        let store = WorkspaceStore(historyLimit: 1)
        let main = try result(), supporting = try result()
        store.receive(main); store.receive(supporting)
        store.rememberScroll(310, for: supporting.id)
        XCTAssertTrue(store.sendToDisplay(.result(supporting.id)))
        for _ in 0..<10 { store.receive(try result()) }
        XCTAssertEqual(store.activeID, main.id)
        XCTAssertEqual(store.supportingResult?.id, supporting.id)
        XCTAssertEqual(store.scrollOffsets[supporting.id], 310)
        XCTAssertFalse(store.sendToDisplay(.result(UUID())))
    }

    func testGraphDisplayAssignmentReusesGraphOwnerAndKeepsCompactComparisonChoice() {
        let store = WorkspaceStore()
        let graph = store.memoryGraph
        store.showComparisonOnCompact = true
        XCTAssertTrue(store.sendToDisplay(.memoryGraph))
        store.returnToConversation()
        store.returnToWorkspace()
        XCTAssertTrue(store.memoryGraph === graph)
        XCTAssertEqual(store.supportingContent, .memoryGraph)
        XCTAssertTrue(store.showComparisonOnCompact)
    }

    func testProtectedResultIsExcludedFromSupervisorInventoryAndSupportingDisplay() throws {
        let store = WorkspaceStore()
        let protected = try protectedResult()
        let publicResult = try result()
        store.receive(protected)
        store.receive(publicResult)
        XCTAssertTrue(store.compare(with: publicResult.id))

        let wireInventory = try JSONEncoder().encode(store.consoleInventoryJSON)
        let wireText = try XCTUnwrap(String(data: wireInventory, encoding: .utf8))
        XCTAssertFalse(wireText.contains(protected.id.uuidString))
        XCTAssertFalse(wireText.contains("Protected title canary"))
        XCTAssertFalse(wireText.contains("Protected body canary"))
        XCTAssertTrue(wireText.contains(publicResult.id.uuidString))

        let legacyInventory = store.consoleInventory
        let legacyCards = try XCTUnwrap(legacyInventory["results"] as? [[String: Any]])
        XCTAssertEqual(legacyCards.count, 1)
        XCTAssertEqual(legacyCards.first?["id"] as? String, publicResult.id.uuidString)
        XCTAssertFalse(String(describing: legacyInventory).contains("Protected title canary"))

        let resultCards = try XCTUnwrap(
            store.consoleInventoryJSON["results"]?.arrayValue
        )
        XCTAssertEqual(resultCards.count, 1)
        XCTAssertEqual(resultCards.first?["id"]?.stringValue, publicResult.id.uuidString)
        XCTAssertTrue(store.consoleInventoryJSON["active_result_id"] == .null)
        XCTAssertFalse(store.sendToDisplay(.result(protected.id)))
        XCTAssertNil(store.supportingContent)
        XCTAssertTrue(store.sendToDisplay(.result(publicResult.id)))
    }

    func testUnknownNonExternalPoliciesNeverEnterInventoryOrSupportingDisplay() throws {
        for policy in ["local_only", "confidential", "future_restricted_policy"] {
            let store = WorkspaceStore()
            let payload = try JSONDecoder().decode(DisplayPayload.self, from: Data(
                "{\"title\":\"Protected \(policy) title\",\"body\":\"Protected inventory canary\",\"data_policy\":\"\(policy)\"}".utf8))
            let item = WorkspaceResult(payload: payload)
            store.receive(item)

            XCTAssertFalse(store.sendToDisplay(.result(item.id)), policy)
            XCTAssertNil(store.supportingContent, policy)
            let inventory = try JSONEncoder().encode(store.consoleInventoryJSON)
            let wire = try XCTUnwrap(String(data: inventory, encoding: .utf8))
            XCTAssertFalse(wire.contains(item.id.uuidString), "protected ID leaked for \(policy)")
            XCTAssertFalse(wire.contains("Protected \(policy) title"), "protected title leaked for \(policy)")
            XCTAssertFalse(wire.contains("Protected inventory canary"), "protected body leaked for \(policy)")
        }
    }

    func testCloseActivePromotesComparisonAndRemovesOnlyItsMetadata() throws {
        let store = WorkspaceStore()
        let a = try result(), b = try result()
        store.receive(a); store.receive(b); store.compare(with: b.id)
        store.rememberScroll(70, for: b.id)
        store.close(a.id)
        XCTAssertEqual(store.activeID, b.id)
        XCTAssertNil(store.comparisonID)
        XCTAssertEqual(store.scrollOffsets[b.id], 70)
    }

    func testConsoleInventoryRevisionTracksSelectionAndModeChanges() throws {
        let store = WorkspaceStore()
        let first = try result(), second = try result()
        store.receive(first); store.receive(second)
        let before = store.consoleRevision
        store.select(second.id)
        XCTAssertGreaterThan(store.consoleRevision, before)
        let afterSelection = store.consoleRevision
        store.openMemoryGraph()
        XCTAssertGreaterThan(store.consoleRevision, afterSelection)
        let inventory = store.consoleInventory
        XCTAssertEqual(inventory["mode"] as? String, "memory")
        XCTAssertEqual((inventory["results"] as? [[String: Any]])?.count, 2)
    }

    func testConsoleInventoryJSONContainsBoundedTargetsWithoutResultBody() throws {
        let store = WorkspaceStore()
        let item = try result()
        store.receive(item)
        guard case .object(let payload) = store.consoleInventoryJSON else {
            return XCTFail("inventory must be a JSON object")
        }
        XCTAssertEqual(payload["active_result_id"]?.stringValue, item.id.uuidString)
        let resultObject = try XCTUnwrap(payload["results"]?.arrayValue?.first?.objectValue)
        XCTAssertEqual(resultObject["id"]?.stringValue, item.id.uuidString)
        XCTAssertNil(resultObject["body"])
        XCTAssertNil(payload["path"])
    }

    // MARK: CC7a.2 (WS-17): quiet arrivals while the conversation thread shows

    /// UI2-23: a result that arrives never takes the stage. On the
    /// conversation it is a card in the thread; while something else is
    /// shown it raises the "New" notice, which Show, Back to the
    /// conversation, Dismiss or closing the result clear.
    func testArrivalsOpenOnTheConversationAndRaiseTheNoticeWhileReading() throws {
        let store = WorkspaceStore()
        store.quietArrivals = true
        let first = try result()
        store.receive(first, answersCurrentRequest: true)
        // Larry, 10-03: on the conversation the answer to what he just
        // asked opens (and its card stays in the thread).
        XCTAssertFalse(store.showsConversation, "A result asked for from the conversation opens.")
        XCTAssertEqual(store.activeID, first.id)
        XCTAssertFalse(store.unreadIDs.contains(first.id), "Opened, so read.")
        XCTAssertNil(store.arrivalNoticeID)

        store.openAtlas()
        let second = try result()
        store.receive(second)
        XCTAssertTrue(store.showsAtlas, "Reading the Atlas is not interrupted.")
        XCTAssertEqual(store.activeID, first.id)
        XCTAssertEqual(store.arrivalNoticeID, second.id)
        store.select(second.id)
        XCTAssertNil(store.arrivalNoticeID, "Show opens it and clears the notice.")
        XCTAssertFalse(store.unreadIDs.contains(second.id))

        let third = try result()
        store.receive(third)
        XCTAssertEqual(store.activeID, second.id, "The open result keeps focus.")
        XCTAssertEqual(store.arrivalNoticeID, third.id)
        store.dismissArrivalNotice()
        XCTAssertNil(store.arrivalNoticeID)
        XCTAssertTrue(store.unreadIDs.contains(third.id), "Dismiss leaves it unread in the thread and Results.")

        let fourth = try result()
        store.receive(fourth)
        store.close(fourth.id)
        XCTAssertNil(store.arrivalNoticeID, "Closing the result ends its notice.")

        let fifth = try result()
        store.receive(fifth)
        store.returnToConversation()
        XCTAssertNil(store.arrivalNoticeID, "Back on the conversation the card is in the thread.")
        XCTAssertTrue(store.showsConversation)
    }

    /// Weather was brought to the front on arrival (WS-15 PR 2); with the
    /// thread on it arrives like every other result. The router's only
    /// change is to skip `select` while `quietArrivals` is on, so the store
    /// state after `receive` is the whole behaviour.
    func testQuietArrivalKeepsAnOpenResultInFocusAndOffKeepsThePreviousBehaviour() throws {
        let quiet = WorkspaceStore()
        quiet.quietArrivals = true
        let open = try result(), weather = try result()
        quiet.receive(open)
        quiet.select(open.id)
        quiet.receive(weather)
        XCTAssertEqual(quiet.activeID, open.id)
        XCTAssertEqual(quiet.arrivalNoticeID, weather.id)
        XCTAssertFalse(quiet.showsConversation)

        let previous = WorkspaceStore()
        let incoming = try result()
        previous.receive(incoming)
        XCTAssertFalse(previous.showsConversation, "Thread off: the first result still opens the workspace.")
        XCTAssertNil(previous.arrivalNoticeID, "Thread off: no notice is ever raised.")
    }

    /// Quiet arrivals keep the retention bound and never evict the open
    /// result or a pin.
    func testQuietArrivalsKeepTheRetentionBound() throws {
        let store = WorkspaceStore(historyLimit: 2)
        store.quietArrivals = true
        let open = try result()
        store.receive(open)
        store.select(open.id)
        let pinned = try result()
        store.receive(pinned)
        XCTAssertTrue(store.pin(pinned.id))
        for _ in 0..<6 { store.receive(try result()) }
        XCTAssertTrue(store.containsResult(open.id))
        XCTAssertTrue(store.containsResult(pinned.id))
        XCTAssertEqual(store.results.count, 4, "open + pinned + historyLimit (2) others")
    }

    /// Codex review of PR #164: on a layout switch the new stage appears
    /// before the old one disappears. Each stage reports for itself, so the
    /// departing stage cannot turn quiet arrivals off under its replacement.
    func testQuietArrivalsFollowTheStagesThatShowTheThread() {
        let store = WorkspaceStore()
        let layoutOne = UUID(), layoutTwo = UUID(), laterTwo = UUID()
        store.setQuietArrivals(false, owner: layoutOne)
        XCTAssertFalse(store.quietArrivals)
        store.setQuietArrivals(true, owner: layoutTwo)        // 1 -> 2: new stage appears
        store.releaseQuietArrivals(owner: layoutOne)          // then the old one leaves
        XCTAssertTrue(store.quietArrivals, "Layout 1 -> 2 keeps quiet arrivals on.")
        store.setQuietArrivals(false, owner: layoutOne)       // 2 -> 1
        store.releaseQuietArrivals(owner: layoutTwo)
        XCTAssertFalse(store.quietArrivals, "Layout 2 -> 1 turns them off.")
        store.setQuietArrivals(true, owner: laterTwo)         // 1 -> 2 again
        store.releaseQuietArrivals(owner: layoutOne)
        XCTAssertTrue(store.quietArrivals)
        store.setQuietArrivals(false, owner: laterTwo)        // thread switched off
        XCTAssertFalse(store.quietArrivals)
        store.setQuietArrivals(true, owner: laterTwo)         // and on
        XCTAssertTrue(store.quietArrivals)
        store.releaseQuietArrivals(owner: laterTwo)           // 2 -> 0: no stage at all
        XCTAssertFalse(store.quietArrivals)
    }

    /// Larry, 10-03: asking again from the conversation opens the new answer,
    /// even when an earlier result is active; asking while reading does not.
    func testEachAnswerAskedForFromTheConversationOpens() throws {
        let store = WorkspaceStore()
        store.quietArrivals = true
        let weather = try result(), research = try result()
        store.receive(weather, answersCurrentRequest: true)
        store.returnToConversation()
        store.receive(research, answersCurrentRequest: true)
        XCTAssertFalse(store.showsConversation)
        XCTAssertEqual(store.activeID, research.id, "The newer answer opens, not the earlier one.")
        XCTAssertNil(store.arrivalNoticeID)
        let whileReading = try result()
        store.receive(whileReading, answersCurrentRequest: true)
        XCTAssertEqual(store.activeID, research.id, "While reading a result, even an answer does not take over.")
        XCTAssertEqual(store.arrivalNoticeID, whileReading.id)
    }

    /// Codex review of #169: a result nobody vouched for as the current
    /// answer (a background job finishing later) stays a card on the
    /// conversation, unread, with no notice and no change of view.
    func testAResultThatIsNotTheCurrentAnswerStaysACardOnTheConversation() throws {
        let store = WorkspaceStore()
        store.quietArrivals = true
        let late = try result()
        store.receive(late)
        XCTAssertTrue(store.showsConversation)
        XCTAssertTrue(store.unreadIDs.contains(late.id))
        XCTAssertNil(store.arrivalNoticeID, "On the conversation the card itself is the notice.")
        XCTAssertEqual(store.activeID, late.id, "Active for the Results view, not shown.")
    }
}
