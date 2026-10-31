import CoreFoundation
import Foundation
import LocalAuthentication
import Security
import XCTest
import Darwin
@testable import PhoneRemoteAuthority

final class PhoneRemoteAuthorityKeychainAnchorTests: XCTestCase {
    private let accessGroup = "TESTTEAM.com.example.phone-authority"

    private final class TestLAContext: LAContext {
        private var noninteractive: Bool
        override var interactionNotAllowed: Bool {
            get { noninteractive }
            set { noninteractive = newValue }
        }

        init(noninteractive: Bool) {
            self.noninteractive = noninteractive
            super.init()
        }
    }

    private final class FakeSecurityClient: SecurityItemClient {
        private let lock = NSLock()
        var copies: [SecurityItemCopyResult]
        var updateStatus: OSStatus = errSecSuccess
        private(set) var queries: [[String: Any]] = []
        private(set) var updates: [([String: Any], [String: Any])] = []
        var afterFirstCopy: (() -> Void)?

        init(copies: [SecurityItemCopyResult] = []) { self.copies = copies }

        func copyMatching(_ query: [String: Any]) -> SecurityItemCopyResult {
            lock.lock()
            queries.append(query)
            let result = copies.isEmpty
                ? SecurityItemCopyResult(status: errSecItemNotFound, value: nil)
                : copies.removeFirst()
            let callback = afterFirstCopy
            afterFirstCopy = nil
            lock.unlock()
            callback?()
            return result
        }

        func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus {
            lock.lock(); defer { lock.unlock() }
            updates.append((query, attributes))
            return updateStatus
        }
    }

    private final class FakeContextProvider: NoninteractiveAuthenticationContextProviding {
        private(set) var contexts: [LAContext] = []
        var fail = false
        var noninteractive = true

        func makeContext() throws -> LAContext {
            guard !fail else { throw PhoneRemoteAuthorityAnchorError.interactionUnavailable }
            let context = TestLAContext(noninteractive: noninteractive)
            contexts.append(context)
            return context
        }
    }

    private final class ReentrantAnchorBackend: PhoneRemoteAuthorityAnchorBackend {
        let value: Anchor
        var session: PhoneRemoteAuthorityAnchorSession?
        var onRead: (() -> Void)?
        var onWrite: (() -> Void)?
        private(set) var reads = 0
        private(set) var writes = 0

        init(_ value: Anchor) { self.value = value }
        func read() throws -> Anchor { reads += 1; onRead?(); return value }
        func write(_ anchor: Anchor, expecting previous: Anchor) throws { writes += 1; onWrite?() }
    }

    private final class DenyingAnchorBackend: PhoneRemoteAuthorityAnchorBackend {
        func read() throws -> Anchor { throw PhoneRemoteAuthorityAnchorError.denied }
        func write(_ anchor: Anchor, expecting previous: Anchor) throws { throw PhoneRemoteAuthorityAnchorError.denied }
    }

    private func makeAnchor(host: String = "host-test", generation: UInt64 = 1,
                            transitionID: String? = nil, transition: String = "stable",
                            login: UInt64 = 0) throws -> Anchor {
        try Anchor([
            "anchor_version": NSNumber(value: UInt64(1)),
            "host_id": host,
            "host_generation": NSNumber(value: generation),
            "transition_id": transitionID as Any? ?? NSNull(),
            "transition_state": transition,
            "login_counter": NSNumber(value: login),
        ])
    }

    private func itemAttributes(includeData data: Data? = nil) -> [String: Any] {
        var attributes: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword as String,
            kSecAttrService as String: PhoneRemoteAuthorityKeychainAnchor.service,
            kSecAttrAccount as String: PhoneRemoteAuthorityKeychainAnchor.account,
            kSecAttrAccessGroup as String: accessGroup,
            kSecAttrSynchronizable as String: NSNumber(value: false),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String,
            kSecAttrCreationDate as String: Date(timeIntervalSince1970: 1_700_000_000),
            kSecAttrModificationDate as String: Date(timeIntervalSince1970: 1_700_000_001),
        ]
        if let data { attributes[kSecValueData as String] = data }
        return attributes
    }

    private func client(for anchor: Anchor) -> FakeSecurityClient {
        let bytes = PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(anchor)
        return FakeSecurityClient(copies: [
            SecurityItemCopyResult(status: errSecSuccess, value: [itemAttributes()]),
            SecurityItemCopyResult(status: errSecSuccess, value: itemAttributes(includeData: bytes)),
        ])
    }

    private func client(before: Anchor, after: Anchor) -> FakeSecurityClient {
        let beforeBytes = PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(before)
        let afterBytes = PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(after)
        return FakeSecurityClient(copies: [
            SecurityItemCopyResult(status: errSecSuccess, value: [itemAttributes()]),
            SecurityItemCopyResult(status: errSecSuccess, value: itemAttributes(includeData: beforeBytes)),
            SecurityItemCopyResult(status: errSecSuccess, value: [itemAttributes()]),
            SecurityItemCopyResult(status: errSecSuccess, value: itemAttributes(includeData: afterBytes)),
        ])
    }

    private func makeAdapter(_ client: SecurityItemClient) throws -> PhoneRemoteAuthorityKeychainAnchor {
        try PhoneRemoteAuthorityKeychainAnchor(client: client, accessGroup: accessGroup,
                                               contextProvider: FakeContextProvider())
    }

    func testReadUsesTwoExactNoninteractiveQueryAndResultShapes() throws {
        let expected = try makeAnchor()
        let fake = client(for: expected)
        let adapter = try makeAdapter(fake)

        XCTAssertEqual(try adapter.read(), expected)
        XCTAssertEqual(fake.queries.count, 2)
        let first = fake.queries[0]
        XCTAssertEqual(first[kSecUseDataProtectionKeychain as String] as? Bool, true)
        XCTAssertEqual(first[kSecClass as String] as? String, kSecClassGenericPassword as String)
        XCTAssertEqual(first[kSecAttrService as String] as? String, PhoneRemoteAuthorityKeychainAnchor.service)
        XCTAssertEqual(first[kSecAttrAccount as String] as? String, PhoneRemoteAuthorityKeychainAnchor.account)
        XCTAssertEqual(first[kSecAttrAccessGroup as String] as? String, accessGroup)
        XCTAssertEqual(first[kSecAttrSynchronizable as String] as? Bool, false)
        XCTAssertEqual(first[kSecAttrAccessible as String] as? String,
                       kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String)
        XCTAssertEqual(first[kSecMatchLimit as String] as? String, kSecMatchLimitAll as String)
        XCTAssertEqual(first[kSecReturnAttributes as String] as? Bool, true)
        XCTAssertNil(first[kSecReturnData as String])

        let second = fake.queries[1]
        XCTAssertEqual(second[kSecMatchLimit as String] as? String, kSecMatchLimitOne as String)
        XCTAssertEqual(second[kSecReturnAttributes as String] as? Bool, true)
        XCTAssertEqual(second[kSecReturnData as String] as? Bool, true)
        let provider = FakeContextProvider()
        let configuredFake = client(for: expected)
        let configuredAdapter = try PhoneRemoteAuthorityKeychainAnchor(client: configuredFake,
            accessGroup: accessGroup, contextProvider: provider)
        XCTAssertEqual(try configuredAdapter.read(), expected)
        for (index, query) in configuredFake.queries.enumerated() {
            let context = try XCTUnwrap(query[kSecUseAuthenticationContext as String] as? LAContext)
            XCTAssertTrue(context === provider.contexts[index], "each query must use the explicitly supplied noninteractive context")
            XCTAssertTrue(context.interactionNotAllowed)
            XCTAssertNil(query[kSecUseAuthenticationUI as String])
            XCTAssertNotNil(query[kSecUseDataProtectionKeychain as String])
        }
        XCTAssertFalse(provider.contexts[0] === provider.contexts[1])
    }

    func testUnestablishedNoninteractiveContextFailsBeforeSecurityClientCall() throws {
        let expected = try makeAnchor()
        let fake = client(for: expected)
        let provider = FakeContextProvider()
        provider.fail = true
        let adapter = try PhoneRemoteAuthorityKeychainAnchor(client: fake, accessGroup: accessGroup,
                                                              contextProvider: provider)
        XCTAssertThrowsError(try adapter.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .interactionUnavailable)
        }
        XCTAssertTrue(fake.queries.isEmpty)
        XCTAssertTrue(fake.updates.isEmpty)
        XCTAssertThrowsError(try adapter.read())
        XCTAssertTrue(fake.queries.isEmpty, "context setup failure must terminally latch")
    }

    func testReturnedInteractiveContextIsRejectedBeforeSecurityClientCall() throws {
        let expected = try makeAnchor()
        let fake = client(for: expected)
        let provider = FakeContextProvider()
        provider.noninteractive = false
        let adapter = try PhoneRemoteAuthorityKeychainAnchor(client: fake, accessGroup: accessGroup,
                                                              contextProvider: provider)
        XCTAssertThrowsError(try adapter.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .interactionUnavailable)
        }
        XCTAssertTrue(fake.queries.isEmpty)
        XCTAssertTrue(fake.updates.isEmpty)
    }

    func testDefaultContextProviderFailsClosedBeforeSecurityCallIfConfigurationIsUnverified() throws {
        let expected = try makeAnchor()
        let fake = client(for: expected)
        let adapter = try PhoneRemoteAuthorityKeychainAnchor(client: fake, accessGroup: accessGroup)
        do {
            let observed = try adapter.read()
            XCTAssertEqual(observed, expected)
        } catch let error as PhoneRemoteAuthorityAnchorError {
            XCTAssertEqual(error, .interactionUnavailable)
            XCTAssertTrue(fake.queries.isEmpty,
                          "an unverified no-UI context must fail before invoking the Security client")
        }
    }

    func testItemNotFoundMeansUnavailableNotPhysicalAbsenceAndLatches() throws {
        let fake = FakeSecurityClient(copies: [SecurityItemCopyResult(status: errSecItemNotFound, value: nil)])
        let adapter = try makeAdapter(fake)
        XCTAssertThrowsError(try adapter.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .notVisible)
        }
        XCTAssertThrowsError(try adapter.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .unavailable)
        }
        XCTAssertEqual(fake.queries.count, 1, "terminal latch must prevent every later Security call")
    }

    func testInteractionAndEntitlementFailuresRemainTypedAndContentFree() throws {
        for (status, expected) in [(errSecInteractionNotAllowed, PhoneRemoteAuthorityAnchorError.interactionUnavailable),
                                   (errSecMissingEntitlement, .denied)] {
            let fake = FakeSecurityClient(copies: [SecurityItemCopyResult(status: status, value: nil)])
            let adapter = try makeAdapter(fake)
            XCTAssertThrowsError(try adapter.read()) { error in
                XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, expected)
                XCTAssertNotNil((error as? PhoneRemoteAuthorityAnchorError)?.protocolErrorCode)
            }
            XCTAssertEqual(fake.queries.count, 1)
        }
        XCTAssertEqual(PhoneRemoteAuthorityAnchorError.interactionUnavailable.protocolErrorCode,
                       "authority_unavailable", "interaction failure is not a lock-state diagnosis")
        XCTAssertEqual(PhoneRemoteAuthorityAnchorError.denied.protocolErrorCode, "anchor_denied")
    }

    func testDuplicateOrUnexpectedAttributeResultsFailClosed() throws {
        let attrs = itemAttributes()
        let cases: [[String: Any]] = [
            attrs.merging([kSecMatchLimit as String: kSecMatchLimitAll as String]) { _, new in new },
            attrs.merging([kSecAttrService as String: "wrong.service"]) { _, new in new },
        ]
        for row in cases {
            let fake = FakeSecurityClient(copies: [SecurityItemCopyResult(status: errSecSuccess, value: [row])])
            let adapter = try makeAdapter(fake)
            XCTAssertThrowsError(try adapter.read()) { error in
                XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .corrupt)
            }
            XCTAssertEqual(fake.queries.count, 1)
        }

        let duplicate = FakeSecurityClient(copies: [
            SecurityItemCopyResult(status: errSecSuccess, value: [attrs, attrs]),
        ])
        let adapter = try makeAdapter(duplicate)
        XCTAssertThrowsError(try adapter.read())
        XCTAssertEqual(duplicate.queries.count, 1)
    }

    func testSecondQueryMustReturnExactOneDictionaryWithData() throws {
        let good = itemAttributes()
        let malformedResults: [Any] = [
            [good],
            good.merging([kSecAttrAccessGroup as String: "WRONG.group"]) { _, new in new }
                .merging([kSecValueData as String: Data("bad".utf8)]) { _, new in new },
            good.merging([kSecValueData as String: "not-data"]) { _, new in new },
        ]
        for malformed in malformedResults {
            let fake = FakeSecurityClient(copies: [
                SecurityItemCopyResult(status: errSecSuccess, value: [good]),
                SecurityItemCopyResult(status: errSecSuccess, value: malformed),
            ])
            let adapter = try makeAdapter(fake)
            XCTAssertThrowsError(try adapter.read()) { error in
                XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .corrupt)
            }
            XCTAssertEqual(fake.queries.count, 2)
        }
    }

    func testWriteUsesDataOnlyUpdateThenExactCanonicalReadback() throws {
        let initial = try makeAnchor()
        let next = try makeAnchor(generation: 2, transitionID: "transition-1", transition: "pending")
        let fake = client(before: initial, after: next)
        let adapter = try makeAdapter(fake)
        try adapter.write(next, expecting: initial)

        XCTAssertEqual(fake.updates.count, 1)
        let (query, attributes) = fake.updates[0]
        XCTAssertEqual(query[kSecAttrService as String] as? String, PhoneRemoteAuthorityKeychainAnchor.service)
        XCTAssertEqual(query[kSecAttrAccount as String] as? String, PhoneRemoteAuthorityKeychainAnchor.account)
        XCTAssertNil(query[kSecReturnAttributes as String])
        XCTAssertNil(query[kSecReturnData as String])
        XCTAssertEqual(attributes[kSecValueData as String] as? Data,
                       PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(next))
        XCTAssertEqual(fake.queries.count, 4, "write validates the prior identity and exact post-update readback")
        XCTAssertNotEqual(initial, next)
    }

    func testWriteRefusesChangedPriorAnchorBeforeCallingUpdate() throws {
        let expectedPrevious = try makeAnchor()
        let observedPrevious = try makeAnchor(host: "other-host")
        let next = try makeAnchor(generation: 2, transitionID: "transition-1", transition: "pending")
        let fake = client(for: observedPrevious)
        let adapter = try makeAdapter(fake)
        XCTAssertThrowsError(try adapter.write(next, expecting: expectedPrevious)) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .corrupt)
        }
        XCTAssertTrue(fake.updates.isEmpty, "changed anchor must be rejected before SecItemUpdate")
        XCTAssertEqual(fake.queries.count, 2)
        XCTAssertThrowsError(try adapter.read())
        XCTAssertEqual(fake.queries.count, 2, "terminal mismatch must prevent later Security calls")
    }

    func testUncertainUpdateLatchesWithoutReadbackOrRetry() throws {
        let next = try makeAnchor(generation: 2, transitionID: "transition-1", transition: "pending")
        let prior = try makeAnchor()
        let fake = client(for: prior)
        fake.updateStatus = errSecInteractionNotAllowed
        let adapter = try makeAdapter(fake)
        XCTAssertThrowsError(try adapter.write(next, expecting: prior)) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .interactionUnavailable)
        }
        XCTAssertEqual(fake.queries.count, 2, "must establish the current unique anchor before updating")
        XCTAssertEqual(fake.updates.count, 1)
        XCTAssertThrowsError(try adapter.read())
        XCTAssertEqual(fake.queries.count, 2)
        XCTAssertEqual(fake.updates.count, 1)
    }

    func testReadbackMismatchLatchesAfterSingleUpdate() throws {
        let expected = try makeAnchor(generation: 2, transitionID: "transition-1", transition: "pending")
        let wrong = try makeAnchor(generation: 3, transitionID: "transition-2", transition: "pending")
        let previous = try makeAnchor()
        let fake = client(before: previous, after: wrong)
        let adapter = try makeAdapter(fake)
        XCTAssertThrowsError(try adapter.write(expected, expecting: previous)) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .corrupt)
        }
        XCTAssertEqual(fake.updates.count, 1)
        let count = fake.queries.count
        XCTAssertThrowsError(try adapter.read())
        XCTAssertEqual(fake.queries.count, count)
    }

    func testCanonicalProtectedCodecAndExistingFileFixtureCompatibility() throws {
        let expected = try makeAnchor(host: "h\n/é")
        let bytes = PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(expected)
        XCTAssertEqual(String(decoding: bytes, as: UTF8.self),
                       "{\"anchor_version\":1,\"host_id\":\"h\\u000a/é\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}")
        XCTAssertEqual(try PhoneRemoteAuthorityKeychainAnchor.decodeProtected(bytes), expected)

        let fixture = Data("{ \"anchor_version\":1,\"host_id\":\"host-test\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0 }".utf8)
        XCTAssertNoThrow(try decodeAnchorFile(fixture), "test file decoder must preserve existing whitespace fixtures")
        XCTAssertThrowsError(try PhoneRemoteAuthorityKeychainAnchor.decodeProtected(fixture),
                             "protected backend alone requires canonical bytes")

        let composed = try makeAnchor(host: "é")
        let decomposed = try makeAnchor(host: "e\u{301}")
        XCTAssertNotEqual(composed, decomposed)
        XCTAssertNotEqual(PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(composed),
                          PhoneRemoteAuthorityKeychainAnchor.encodeCanonical(decomposed))
    }

    func testProtectedAnchorV2RequiresBoundRestoreFieldsAndPreservesCompatibilityProjection() throws {
        let operationID = UUID().uuidString.lowercased()
        let manifest = String(repeating: "a", count: 64)
        let checkpoint = String(repeating: "b", count: 64)
        let tombstone: [String: Any] = ["operation_id": UUID().uuidString.lowercased(),
            "target_generation": NSNumber(value: UInt64(4)), "manifest_sha256": manifest,
            "checkpoint_sha256": checkpoint, "database_sha256": String(repeating: "c", count: 64)]
        let stable = try Anchor(["anchor_version": NSNumber(value: UInt64(2)), "host_id": "host-test",
            "host_generation": NSNumber(value: UInt64(4)), "transition_id": NSNull(),
            "transition_state": "stable", "login_counter": NSNumber(value: UInt64(8)),
            "pending_restore": NSNull(), "last_completed_restore": tombstone])
        XCTAssertEqual(Set(stable.wire.keys), Set(["anchor_version", "host_id", "host_generation",
            "transition_id", "transition_state", "login_counter", "pending_restore", "last_completed_restore"]))
        XCTAssertEqual(Set(stable.projection.keys), Set(["anchor_version", "host_id", "host_generation",
            "transition_id", "transition_state", "login_counter"]))
        XCTAssertEqual(try Anchor(stable.wire), stable)

        let pending: [String: Any] = ["operation_id": operationID,
            "target_generation": NSNumber(value: UInt64(5)), "manifest_sha256": manifest,
            "checkpoint_sha256": checkpoint]
        let restorePending = try Anchor(["anchor_version": NSNumber(value: UInt64(2)),
            "host_id": "host-test", "host_generation": NSNumber(value: UInt64(5)),
            "transition_id": operationID, "transition_state": "pending", "login_counter": NSNumber(value: UInt64(8)),
            "pending_restore": pending, "last_completed_restore": tombstone])
        XCTAssertEqual(try Anchor(restorePending.wire), restorePending)

        var badGeneration = pending
        badGeneration["target_generation"] = NSNumber(value: UInt64(6))
        XCTAssertThrowsError(try Anchor(["anchor_version": NSNumber(value: UInt64(2)),
            "host_id": "host-test", "host_generation": NSNumber(value: UInt64(5)),
            "transition_id": operationID, "transition_state": "pending", "login_counter": NSNumber(value: UInt64(8)),
            "pending_restore": badGeneration, "last_completed_restore": tombstone]))
        XCTAssertThrowsError(try Anchor(["anchor_version": NSNumber(value: UInt64(2)),
            "host_id": "host-test", "host_generation": NSNumber(value: UInt64(4)),
            "transition_id": NSNull(), "transition_state": "stable", "login_counter": NSNumber(value: UInt64(8)),
            "pending_restore": NSNull(), "last_completed_restore": NSNull()]))
    }

    func testProtectedDecoderRejectsDuplicateKeysTypesAndUnknownFields() throws {
        let malformed = [
            Data("{\"anchor_version\":1,\"anchor_version\":1,\"host_id\":\"h\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8),
            Data("{\"anchor_version\":true,\"host_id\":\"h\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8),
            Data("{\"anchor_version\":1,\"host_id\":\"h\",\"host_generation\":1.0,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8),
            Data("{\"anchor_version\":1,\"host_id\":\"h\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0,\"extra\":0}".utf8),
        ]
        for bytes in malformed {
            XCTAssertThrowsError(try PhoneRemoteAuthorityKeychainAnchor.decodeProtected(bytes))
        }
        XCTAssertThrowsError(try PhoneRemoteAuthorityKeychainAnchor.decodeProtected(Data(repeating: 0x20, count: 65_537)))
    }

    func testConcurrentAccessIsRejectedWithoutOverlappingClientCalls() throws {
        let expected = try makeAnchor()
        let fake = client(for: expected)
        let entered = DispatchSemaphore(value: 0)
        let release = DispatchSemaphore(value: 0)
        fake.afterFirstCopy = {
            entered.signal()
            _ = release.wait(timeout: .now() + 3)
        }
        let adapter = try makeAdapter(fake)
        let finished = DispatchSemaphore(value: 0)
        var outerResult: Result<Anchor, Error>?
        DispatchQueue.global().async {
            do { outerResult = .success(try adapter.read()) }
            catch { outerResult = .failure(error) }
            finished.signal()
        }
        XCTAssertEqual(entered.wait(timeout: .now() + 2), .success)
        XCTAssertThrowsError(try adapter.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .busy)
        }
        release.signal()
        XCTAssertEqual(finished.wait(timeout: .now() + 3), .success)
        XCTAssertEqual(fake.queries.count, 1, "the rejected call must not reach the Security client")
        guard case .failure(let outerError)? = outerResult else {
            return XCTFail("the active read must not return success after a concurrent busy failure")
        }
        XCTAssertEqual(outerError as? PhoneRemoteAuthorityAnchorError, .unavailable)
        XCTAssertThrowsError(try adapter.read())
        XCTAssertEqual(fake.queries.count, 1, "failure latch must prevent subsequent client calls")
    }

    func testConcurrentFailurePoisonsOuterReadAndPreventsSubsequentBackendCalls() throws {
        let anchor = try makeAnchor()
        let backend = ReentrantAnchorBackend(anchor)
        let session = PhoneRemoteAuthorityAnchorSession(backend: backend)
        backend.session = session
        backend.onRead = { _ = try? session.read() }

        XCTAssertThrowsError(try session.read()) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .unavailable)
        }
        XCTAssertEqual(backend.reads, 1, "nested busy must poison the outer result before it is returned")
        XCTAssertThrowsError(try session.read())
        XCTAssertEqual(backend.reads, 1, "a poisoned session must not call the backend again")
    }

    func testReentrantWriteFailurePoisonsOuterWriteBeforeItCanSucceed() throws {
        let prior = try makeAnchor()
        let next = try makeAnchor(generation: 2, transitionID: "t", transition: "pending")
        let backend = ReentrantAnchorBackend(prior)
        let session = PhoneRemoteAuthorityAnchorSession(backend: backend)
        backend.session = session
        backend.onWrite = { _ = try? session.read() }

        XCTAssertThrowsError(try session.write(next, expecting: prior)) { error in
            XCTAssertEqual(error as? PhoneRemoteAuthorityAnchorError, .unavailable)
        }
        XCTAssertEqual(backend.writes, 1)
        XCTAssertEqual(backend.reads, 0, "reentrant call must be rejected before invoking the backend")
        XCTAssertThrowsError(try session.read())
        XCTAssertEqual(backend.reads, 0)
    }

    func testOwnerErrorUsesCorrelationOfFailingAnchorRead() throws {
        var sockets: [Int32] = [0, 0]
        XCTAssertEqual(socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets), 0)
        defer { close(sockets[0]); close(sockets[1]) }
        let ownerID = UUID().uuidString.lowercased()
        let childID = UUID().uuidString.lowercased()
        let owner = PhoneRemoteAuthorityOwner(lockFD: -1, listenerFD: sockets[0], childPID: getpid(),
            ownerID: ownerID, childID: childID, anchor: try makeAnchor(), expectedGrants: 1,
            holdMilliseconds: 0, readyPath: "", anchorBackend: DenyingAnchorBackend(), version: 3)
        let finished = DispatchSemaphore(value: 0)
        var serveStatus: Int32 = -1
        DispatchQueue.global().async { serveStatus = owner.serve(); finished.signal() }

        let proto = "mortimer.phone-authority-channel.v3"
        let hello = try frameRead(sockets[1], expectedSequence: 1, owner: ownerID, child: childID,
                                  protocolName: proto, version: 3)
        let helloCorrelation = hello["correlation_id"] as! String
        try frameWrite(sockets[1], sequence: 1, owner: ownerID, child: childID,
                       kind: "child.ready", correlation: helloCorrelation, payload: [:],
                       protocolName: proto, version: 3)
        let grantCorrelation = UUID().uuidString.lowercased()
        try frameWrite(sockets[1], sequence: 2, owner: ownerID, child: childID,
                       kind: "child.grant.acquire", correlation: grantCorrelation,
                       payload: ["operation": "store.read"], protocolName: proto, version: 3)
        let acquired = try frameRead(sockets[1], expectedSequence: 2, owner: ownerID, child: childID,
                                     protocolName: proto, version: 3)
        XCTAssertEqual(acquired["kind"] as? String, "owner.grant.acquired")
        XCTAssertEqual(acquired["correlation_id"] as? String, grantCorrelation)
        let acquiredPayload = try XCTUnwrap(acquired["payload"] as? [String: Any])
        let grantID = try XCTUnwrap(acquiredPayload["grant_id"] as? String)
        let readCorrelation = UUID().uuidString.lowercased()
        try frameWrite(sockets[1], sequence: 3, owner: ownerID, child: childID,
                       kind: "child.anchor.read", correlation: readCorrelation,
                       payload: ["grant_id": grantID], protocolName: proto, version: 3)
        let failure = try frameRead(sockets[1], expectedSequence: 3, owner: ownerID, child: childID,
                                    protocolName: proto, version: 3)
        XCTAssertEqual(failure["kind"] as? String, "owner.error")
        XCTAssertEqual(failure["correlation_id"] as? String, readCorrelation)
        XCTAssertEqual((failure["payload"] as? [String: String])?["code"], "anchor_denied")
        shutdown(sockets[1], SHUT_RDWR)
        XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
        XCTAssertEqual(serveStatus, 24)
    }

    func testWrongReadyCorrelationIsRejectedAgainstHelloForEveryProtocolVersion() throws {
        for version: UInt64 in 1...3 {
            var sockets: [Int32] = [0, 0]
            XCTAssertEqual(socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets), 0)
            defer { close(sockets[0]); close(sockets[1]) }
            let ownerID = UUID().uuidString.lowercased()
            let childID = UUID().uuidString.lowercased()
            let owner = PhoneRemoteAuthorityOwner(lockFD: -1, listenerFD: sockets[0], childPID: getpid(),
                ownerID: ownerID, childID: childID, anchor: try makeAnchor(), expectedGrants: 1,
                holdMilliseconds: 0, readyPath: "", anchorBackend: DenyingAnchorBackend(), version: version)
            let finished = DispatchSemaphore(value: 0)
            var serveStatus: Int32 = -1
            DispatchQueue.global().async { serveStatus = owner.serve(); finished.signal() }

            let proto = "mortimer.phone-authority-channel.v\(version)"
            let hello = try frameRead(sockets[1], expectedSequence: 1, owner: ownerID, child: childID,
                                      protocolName: proto, version: version)
            let helloCorrelation = try XCTUnwrap(hello["correlation_id"] as? String)
            let wrongCorrelation = UUID().uuidString.lowercased()
            XCTAssertNotEqual(helloCorrelation, wrongCorrelation)
            try frameWrite(sockets[1], sequence: 1, owner: ownerID, child: childID,
                           kind: "child.ready", correlation: wrongCorrelation, payload: [:],
                           protocolName: proto, version: version)
            let failure = try frameRead(sockets[1], expectedSequence: 2, owner: ownerID, child: childID,
                                        protocolName: proto, version: version)
            XCTAssertEqual(failure["kind"] as? String, "owner.error")
            XCTAssertEqual(failure["correlation_id"] as? String, wrongCorrelation)
            XCTAssertEqual((failure["payload"] as? [String: String])?["code"], "phase_invalid")
            XCTAssertEqual(finished.wait(timeout: .now() + 2), .success)
            XCTAssertEqual(serveStatus, 23)
            shutdown(sockets[1], SHUT_RDWR)
        }
    }


}
