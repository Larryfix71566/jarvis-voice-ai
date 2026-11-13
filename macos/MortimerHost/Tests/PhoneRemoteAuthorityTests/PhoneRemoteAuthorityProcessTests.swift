import XCTest
import Darwin
@testable import PhoneRemoteAuthority

final class PhoneRemoteAuthorityProcessTests: XCTestCase {
    func testOrdinaryReaperOnlyExactPIDCanReleaseAndNeverSignalsUncertainOwnership() {
        for error in [ECHILD, EINVAL] {
            var signals: [Int32] = []
            let result = PhoneRemoteAuthorityOwner.ordinaryChildCleanup(pid: 123, healthy: false,
                started: 10, now: { 10 }, wait: { (-1, 0, error) },
                signal: { signals.append($0); return 0 }, pause: {})
            XCTAssertFalse(result.reaped)
            XCTAssertTrue(signals.isEmpty)
        }
        let foreign = PhoneRemoteAuthorityOwner.ordinaryChildCleanup(pid: 123, healthy: false,
            started: 10, now: { 10 }, wait: { (124, 0, 0) }, signal: { _ in XCTFail("foreign PID"); return 0 }, pause: {})
        XCTAssertFalse(foreign.reaped)
    }

    func testOrdinaryReaperGraceEscalationAndInterruptedWaitKeepAbsoluteBudget() {
        for mode in ["healthy", "term", "kill", "interrupted", "exhausted"] {
            var clock = 10.0
            var signals: [Int32] = []
            var waits = 0
            let result = PhoneRemoteAuthorityOwner.ordinaryChildCleanup(pid: 123, healthy: mode == "healthy",
                started: 10, now: { clock }, wait: {
                    waits += 1
                    if mode == "healthy" || (mode == "term" && signals.last == SIGTERM)
                        || (mode == "kill" && signals.last == SIGKILL) { return (123, 0, 0) }
                    if mode == "interrupted" { return (-1, 0, EINTR) }
                    return (0, 0, 0)
                }, signal: { signals.append($0); return 0 }, pause: { clock += 0.005 })
            XCTAssertEqual(result.reaped, ["healthy", "term", "kill"].contains(mode))
            XCTAssertLessThanOrEqual(clock, 12.506)
            XCTAssertGreaterThan(waits, 0)
            if mode == "healthy" { XCTAssertTrue(signals.isEmpty) }
            if mode == "term" { XCTAssertEqual(signals, [SIGTERM]) }
            if mode == "kill" || mode == "exhausted" { XCTAssertEqual(signals, [SIGTERM, SIGKILL]) }
            if mode == "interrupted" { XCTAssertTrue(signals.isEmpty) }
        }
    }

    private func waitForCompleteReceipt(deadline: TimeInterval, read: () -> Data?,
                                        isRunning: () -> Bool,
                                        now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
                                        pause: () -> Void = { usleep(5_000) }) -> [String: Any]? {
        while now() < deadline {
            if let data = read(), let value = try? JSONSerialization.jsonObject(with: data),
               let receipt = value as? [String: Any] { return receipt }
            if !isRunning() { return nil }
            pause()
        }
        return nil
    }

    func testTerminalReceiptWaitIgnoresEmptyPartialDataAndKeepsAbsoluteDeadline() throws {
        var clock = 10.0
        var reads = 0
        let fragments: [Data?] = [nil, Data(), Data("{\"confirmed_reap\":".utf8),
            Data("{\"confirmed_reap\":false,\"pid\":123}".utf8)]
        let receipt = try XCTUnwrap(waitForCompleteReceipt(deadline: 11, read: {
            defer { reads += 1 }; return fragments[min(reads, fragments.count - 1)]
        }, isRunning: { true }, now: { clock }, pause: { clock += 0.1 }))
        XCTAssertEqual(reads, 4)
        XCTAssertEqual(receipt["pid"] as? Int, 123)
        XCTAssertEqual(receipt["confirmed_reap"] as? Bool, false)
        XCTAssertNil(waitForCompleteReceipt(deadline: 11, read: { Data("{".utf8) },
            isRunning: { true }, now: { clock }, pause: { clock += 0.1 }))
        XCTAssertLessThanOrEqual(clock, 11.1)
        XCTAssertNil(waitForCompleteReceipt(deadline: 12, read: { Data() },
            isRunning: { false }, now: { clock }, pause: { XCTFail("exited owner must not wait") }))
    }

    func testOrdinaryUnknownWaitRetainsActualSingletonAfterPartialEOF() throws {
        let environment = ProcessInfo.processInfo.environment
        // Like the other actual-process tests, this requires an explicitly built
        // offline owner. Plain `swift test` still runs the injected reaper tests.
        guard let owner = environment["PHONE_REMOTE_AUTHORITY_OWNER_BIN"],
              FileManager.default.isExecutableFile(atPath: owner) else {
            throw XCTSkip("focused process test requires the built offline owner executable")
        }
        guard let python = environment["PHONE_REMOTE_AUTHORITY_PYTHON"] ?? findPython() else {
            XCTFail("Python 3.12 or python3 must be available on PATH for the process test")
            return
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("broker-held-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        XCTAssertEqual(chmod(root.path, S_IRWXU), 0)
        defer { try? FileManager.default.removeItem(at: root) }
        let lock = root.appendingPathComponent("owner.lock").path
        let fd = open(lock, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        XCTAssertGreaterThanOrEqual(fd, 0)
        defer { close(fd) }
        let anchor = root.appendingPathComponent("anchor.json")
        try Data("{\"anchor_version\":1,\"host_id\":\"host-test\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8).write(to: anchor)
        let launcher = root.appendingPathComponent("child")
        try Data("#!\(python)\nimport os,time\nos.close(3)\ntime.sleep(10)\n".utf8).write(to: launcher)
        XCTAssertEqual(chmod(launcher.path, S_IRWXU), 0)
        let ready = root.appendingPathComponent("ready").path
        let process = Process()
        process.executableURL = URL(fileURLWithPath: owner)
        process.arguments = ["--test-owner", lock, launcher.path, root.appendingPathComponent("unused.sqlite").path,
            root.path, "v4-test-reap-echild", "1", "0", "1", "0", anchor.path]
        process.environment = environment.merging(["PHONE_REMOTE_AUTHORITY_READY_FILE": ready]) { _, new in new }
        try process.run()
        defer { if process.isRunning { process.terminate(); process.waitUntilExit() } }
        let deadline = ProcessInfo.processInfo.systemUptime + 4
        let receipt = try XCTUnwrap(waitForCompleteReceipt(deadline: deadline,
            read: { try? Data(contentsOf: URL(fileURLWithPath: ready + ".terminal")) },
            isRunning: { process.isRunning }), "complete terminal receipt did not arrive within four seconds")
        XCTAssertEqual(receipt["confirmed_reap"] as? Bool, false)
        XCTAssertEqual(receipt["singleton_held"] as? Bool, true)
        XCTAssertTrue(process.isRunning, "uncertain owner must remain fenced-held")
        XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), -1)
        XCTAssertEqual(errno, EWOULDBLOCK)
        let child = try XCTUnwrap(receipt["pid"] as? Int32)
        XCTAssertEqual(kill(child, 0), -1)
        XCTAssertEqual(errno, ESRCH, "the test seam first reaps its real child, then loses the receipt")
        XCTAssertFalse((receipt["stages"] as? [String] ?? []).contains("KILL"), "no signal after ECHILD")
        process.terminate(); process.waitUntilExit()
        XCTAssertEqual(flock(fd, LOCK_EX | LOCK_NB), 0, "test teardown, not normal cleanup, releases held owner")
        XCTAssertEqual(flock(fd, LOCK_UN), 0)
    }

    func testV4RejectsCrossVersionStoreWithoutChangingProtectedTombstone() throws {
        guard let ownerPath = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_OWNER_BIN"],
              FileManager.default.isExecutableFile(atPath: ownerPath) else {
            throw XCTSkip("focused process test requires the built offline owner executable")
        }
        let repository = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_ROOT"] ?? repositoryRoot()
        guard let python = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PYTHON"] ?? findPython() else {
            XCTFail("Python 3.12 or python3 must be available on PATH for the process test")
            return
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("authority-v4-normal-\(UUID().uuidString)").path
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        XCTAssertEqual(chmod(root, S_IRWXU), 0)
        defer { try? FileManager.default.removeItem(atPath: root) }
        let lockPath = root + "/owner.lock", anchorPath = root + "/anchor.json", readyPath = root + "/ready"
        let resultPath = root + "/result"
        let tombstone = "\"operation_id\":\"123e4567-e89b-12d3-a456-426614174000\",\"target_generation\":1,\"manifest_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"checkpoint_sha256\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"database_sha256\":\"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\""
        let protectedV2 = "{\"anchor_version\":2,\"host_id\":\"host-test\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0,\"pending_restore\":null,\"last_completed_restore\":{\(tombstone)}}"
        try Data(protectedV2.utf8)
            .write(to: URL(fileURLWithPath: anchorPath))
        let lockFD = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        XCTAssertGreaterThanOrEqual(lockFD, 0)
        if lockFD >= 0 { close(lockFD) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ownerPath)
        process.arguments = ["--test-owner", lockPath, python, root + "/authority.sqlite", repository,
                             "v4-normal", "7", "25", "1", "0", anchorPath]
        process.environment = ProcessInfo.processInfo.environment.merging([
            "PHONE_REMOTE_AUTHORITY_READY_FILE": readyPath,
            "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT": resultPath,
            "PYTHONPATH": repository + ":" + (ProcessInfo.processInfo.environment["PYTHONPATH"] ?? "")
        ]) { _, new in new }
        let provision = Process()
        provision.executableURL = URL(fileURLWithPath: python)
        provision.arguments = ["-c", "import sqlite3; from jarvis.bot.phone_admission_store import FakeProtectedAnchor, PhoneAdmissionStore; c=sqlite3.connect(r'\(root)/authority.sqlite', isolation_level=None); s=PhoneAdmissionStore(c, FakeProtectedAnchor('host-test')); c.execute('INSERT INTO phone_remote_devices VALUES(?,?,?,?,NULL)', ('d-v4','alice',b'synthetic-key','test')); c.execute('INSERT INTO phone_remote_grants VALUES(?,?,?,?,1,NULL)', ('g-v4','d-v4','alice','[\"read\"]')); c.commit(); c.close()"]
        provision.environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONPATH": repository + ":" + (ProcessInfo.processInfo.environment["PYTHONPATH"] ?? ""),
            "PYTHONNOUSERSITE": "1"
        ]) { _, new in new }
        try provision.run(); provision.waitUntilExit()
        XCTAssertEqual(provision.terminationStatus, 0, "preprovisioned disposable store fixture must be valid")
        try process.run()
        process.waitUntilExit()
        let result = (try? String(contentsOfFile: resultPath, encoding: .utf8)) ?? "no child result"
        XCTAssertNotEqual(process.terminationStatus, 0, "protected-v2/store-v1 must fail before service activation: \(result)")
        XCTAssertTrue(FileManager.default.fileExists(atPath: readyPath))
        let persisted = try Data(contentsOf: URL(fileURLWithPath: anchorPath))
        let anchor = try XCTUnwrap(JSONSerialization.jsonObject(with: persisted) as? [String: Any])
        let expectedTombstone = try XCTUnwrap(JSONSerialization.jsonObject(with: Data("{\(tombstone)}".utf8)) as? [String: Any])
        XCTAssertEqual(anchor["anchor_version"] as? Int, 2)
        XCTAssertEqual(anchor["pending_restore"] as? NSNull, NSNull())
        XCTAssertEqual(anchor["last_completed_restore"] as? NSDictionary, expectedTombstone as NSDictionary,
                       "failed startup must preserve the protected v2 completion tombstone")
        XCTAssertEqual(anchor["login_counter"] as? Int, 0)
    }

    func testV3OwnerAndControlledChildCompleteVersionedHandshakeAndShutdown() throws {
        guard let ownerPath = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_OWNER_BIN"],
              FileManager.default.isExecutableFile(atPath: ownerPath) else {
            throw XCTSkip("focused process test requires the built offline owner executable")
        }
        let repository = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_ROOT"] ?? repositoryRoot()
        guard let python = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PYTHON"] ?? findPython() else {
            XCTFail("Python 3.12 or python3 must be available on PATH for the process test")
            return
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("authority-v3-\(UUID().uuidString)").path
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        XCTAssertEqual(chmod(root, S_IRWXU), 0)
        defer { try? FileManager.default.removeItem(atPath: root) }
        let lockPath = root + "/owner.lock"
        let anchorPath = root + "/anchor.json"
        let readyPath = root + "/ready"
        try Data("{\"anchor_version\":1,\"host_id\":\"host-test\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8)
            .write(to: URL(fileURLWithPath: anchorPath))
        let lockFD = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        XCTAssertGreaterThanOrEqual(lockFD, 0)
        if lockFD >= 0 { close(lockFD) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ownerPath)
        process.arguments = ["--test-owner", lockPath, python, root + "/unused.sqlite", repository,
                             "v3-hold", "0", "25", "1", "0", anchorPath]
        process.environment = ProcessInfo.processInfo.environment.merging([
            "PHONE_REMOTE_AUTHORITY_READY_FILE": readyPath,
            "PYTHONPATH": repository + ":" + (ProcessInfo.processInfo.environment["PYTHONPATH"] ?? "")
        ]) { _, new in new }
        try process.run()
        process.waitUntilExit()
        XCTAssertEqual(process.terminationStatus, 0, "v3 owner/child handshake must finish cleanly")
        XCTAssertTrue(FileManager.default.fileExists(atPath: readyPath))
    }

    func testOwnerAndChildHoldTheSamePreprovisionedLockAcrossHandshake() throws {
        guard let ownerPath = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_OWNER_BIN"],
              FileManager.default.isExecutableFile(atPath: ownerPath) else {
            throw XCTSkip("focused process test requires the built offline owner executable")
        }
        let repository = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_ROOT"] ?? repositoryRoot()
        guard let python = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PYTHON"] ?? findPython() else {
            XCTFail("Python 3.12 or python3 must be available on PATH for the process test")
            return
        }
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("authority-owner-\(UUID().uuidString)").path
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        XCTAssertEqual(chmod(root, S_IRWXU), 0, "test lock directory must have the adopted private mode")
        defer { try? FileManager.default.removeItem(atPath: root) }
        let lockPath = root + "/owner.lock"
        let readyPath = root + "/ready"
        let anchorPath = root + "/anchor.json"
        try Data("{\"anchor_version\":1,\"host_id\":\"host-test\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8).write(to: URL(fileURLWithPath: anchorPath))
        let initialLockFD = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        XCTAssertGreaterThanOrEqual(initialLockFD, 0)
        if initialLockFD >= 0 { close(initialLockFD) }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ownerPath)
        process.arguments = ["--test-owner", lockPath, python, root + "/unused.sqlite", repository,
                             "hold", "0", "1000", "1", "0", anchorPath]
        process.environment = ProcessInfo.processInfo.environment.merging([
            "PHONE_REMOTE_AUTHORITY_READY_FILE": readyPath,
            "PYTHONPATH": repository + ":" + (ProcessInfo.processInfo.environment["PYTHONPATH"] ?? "")
        ]) { _, new in new }
        try process.run()
        defer { if process.isRunning { process.terminate() } }
        let deadline = Date().addingTimeInterval(5)
        while !FileManager.default.fileExists(atPath: readyPath), Date() < deadline { usleep(10_000) }
        XCTAssertTrue(FileManager.default.fileExists(atPath: readyPath), "child did not complete the actual process handshake")
        let contender = open(lockPath, O_RDWR)
        XCTAssertGreaterThanOrEqual(contender, 0)
        if contender >= 0 {
            XCTAssertNotEqual(flock(contender, LOCK_EX | LOCK_NB), 0, "second owner must not acquire the held inode")
            close(contender)
        }
        process.waitUntilExit()
        XCTAssertEqual(process.terminationStatus, 0)
    }

    func testFailedPreChildValidationReleasesTheSingletonDescriptor() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("authority-lock-cleanup-\(UUID().uuidString)").path
        try FileManager.default.createDirectory(atPath: root, withIntermediateDirectories: true)
        XCTAssertEqual(chmod(root, S_IRWXU), 0)
        defer { try? FileManager.default.removeItem(atPath: root) }
        let lockPath = root + "/owner.lock"
        let lockFD = open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        XCTAssertGreaterThanOrEqual(lockFD, 0)
        if lockFD >= 0 { close(lockFD) }
        let anchorPath = root + "/anchor.json"
        try Data("{invalid".utf8).write(to: URL(fileURLWithPath: anchorPath))
        XCTAssertThrowsError(try PhoneRemoteAuthorityOwner.runOfflineTestOwner(
            lockPath: lockPath, python: "/unused", database: root + "/unused.sqlite",
            workingDirectory: root, scenario: "hold", expectedGrants: 0,
            holdMilliseconds: 0, readyPath: "", testHostGeneration: 1,
            testLoginCounter: 0, testAnchorPath: anchorPath))
        var probeFD = open(lockPath, O_RDWR)
        XCTAssertGreaterThanOrEqual(probeFD, 0)
        if probeFD >= 0 {
            XCTAssertEqual(flock(probeFD, LOCK_EX | LOCK_NB), 0,
                           "malformed anchor startup must release the acquired lock")
            close(probeFD)
        }

        try Data("{\"anchor_version\":1,\"host_id\":\"host\",\"host_generation\":1,\"transition_id\":null,\"transition_state\":\"stable\",\"login_counter\":0}".utf8)
            .write(to: URL(fileURLWithPath: anchorPath))
        let status = try PhoneRemoteAuthorityOwner.runOfflineTestOwner(
            lockPath: lockPath, python: "/unused", database: root + "/unused.sqlite",
            workingDirectory: root, scenario: "hold", expectedGrants: 0,
            holdMilliseconds: 0, readyPath: "", testHostGeneration: 2,
            testLoginCounter: 0, testAnchorPath: anchorPath)
        XCTAssertEqual(status, 25, "anchor/caller mismatch must fail before child launch")
        probeFD = open(lockPath, O_RDWR)
        XCTAssertGreaterThanOrEqual(probeFD, 0)
        if probeFD >= 0 {
            XCTAssertEqual(flock(probeFD, LOCK_EX | LOCK_NB), 0,
                           "early validation return must release the acquired lock")
            close(probeFD)
        }

        try Data("{\"anchor_version\":1,\"host_id\":\"host\",\"host_generation\":2,\"transition_id\":\"restore_prepare:test\",\"transition_state\":\"pending\",\"login_counter\":0}".utf8)
            .write(to: URL(fileURLWithPath: anchorPath))
        let pendingStatus = try PhoneRemoteAuthorityOwner.runOfflineTestOwner(
            lockPath: lockPath, python: "/unused", database: root + "/unused.sqlite",
            workingDirectory: root, scenario: "v3-hold", expectedGrants: 0,
            holdMilliseconds: 0, readyPath: "", testHostGeneration: 2,
            testLoginCounter: 0, testAnchorPath: anchorPath)
        XCTAssertEqual(pendingStatus, 25, "a verified pending restore must not start another child")
        probeFD = open(lockPath, O_RDWR)
        XCTAssertGreaterThanOrEqual(probeFD, 0)
        if probeFD >= 0 {
            XCTAssertEqual(flock(probeFD, LOCK_EX | LOCK_NB), 0,
                           "pending-state startup refusal must release the test acquisition")
            close(probeFD)
        }
    }

    private func repositoryRoot() -> String {
        var url = URL(fileURLWithPath: #filePath).standardizedFileURL
        for _ in 0..<5 { url.deleteLastPathComponent() }
        return url.path
    }

    private func findPython() -> String? {
        let path = ProcessInfo.processInfo.environment["PATH"] ?? "/usr/bin:/bin"
        for name in ["python3.12", "python3"] {
            for directory in path.split(separator: ":") {
                let candidate = URL(fileURLWithPath: String(directory)).appendingPathComponent(name).path
                if FileManager.default.isExecutableFile(atPath: candidate) { return candidate }
            }
        }
        return nil
    }
}
