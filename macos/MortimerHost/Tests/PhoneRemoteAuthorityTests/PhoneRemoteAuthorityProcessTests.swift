import XCTest
import Darwin
import PhoneRemoteAuthority

final class PhoneRemoteAuthorityProcessTests: XCTestCase {
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
