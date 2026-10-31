import XCTest
import Darwin
import PhoneRemoteAuthority

final class PhoneRemoteAuthorityProcessTests: XCTestCase {
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
