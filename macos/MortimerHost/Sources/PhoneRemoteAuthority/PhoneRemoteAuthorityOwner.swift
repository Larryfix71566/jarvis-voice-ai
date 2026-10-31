import CoreFoundation
import Foundation
import Darwin

public enum PhoneRemoteAuthorityError: Error { case invalidFrame, unavailable }

private let protocolName = "mortimer.phone-authority-channel.v1"
private let maxFrame = 65_536
private let maxSequence: UInt64 = UInt64.max

private func exactInt(_ value: Any?, min: UInt64 = 0) -> UInt64? {
    guard let n = value as? NSNumber,
          CFGetTypeID(n) != CFBooleanGetTypeID(),
          String(cString: n.objCType) != "d", String(cString: n.objCType) != "f" else { return nil }
    let raw = n.stringValue
    guard let i = UInt64(raw), i >= min else { return nil }
    return i
}

private func readExact(_ fd: Int32, _ count: Int) throws -> Data {
    var data = Data(count: count)
    try data.withUnsafeMutableBytes { raw in
        guard let base = raw.baseAddress else { throw PhoneRemoteAuthorityError.invalidFrame }
        var offset = 0
        while offset < count {
            let n = recv(fd, base.advanced(by: offset), count - offset, 0)
            if n == 0 { throw PhoneRemoteAuthorityError.unavailable }
            if n < 0 { if errno == EINTR { continue }; throw PhoneRemoteAuthorityError.unavailable }
            offset += n
        }
    }
    return data
}

private func writeAll(_ fd: Int32, _ data: Data) throws {
    try data.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { throw PhoneRemoteAuthorityError.invalidFrame }
        var offset = 0
        while offset < data.count {
            let n = send(fd, base.advanced(by: offset), data.count - offset, 0)
            if n < 0 { if errno == EINTR { continue }; throw PhoneRemoteAuthorityError.unavailable }
            if n == 0 { throw PhoneRemoteAuthorityError.unavailable }
            offset += n
        }
    }
}

private struct DuplicateKeyScanner {
    let bytes: [UInt8]
    var index = 0
    mutating func skipSpace() { while index < bytes.count && [0x20, 0x09, 0x0a, 0x0d].contains(bytes[index]) { index += 1 } }
    mutating func stringToken() -> String? {
        guard index < bytes.count, bytes[index] == 0x22 else { return nil }
        let start = index; index += 1
        while index < bytes.count {
            let byte = bytes[index]; index += 1
            if byte == 0x5c { guard index < bytes.count else { return nil }; index += 1 }
            else if byte == 0x22 {
                let token = Data(bytes[start..<index])
                return (try? JSONSerialization.jsonObject(with: token, options: [.fragmentsAllowed])) as? String
            }
        }
        return nil
    }
    mutating func value(_ depth: Int = 0) -> Bool {
        guard depth <= 64 else { return false }
        skipSpace(); guard index < bytes.count else { return false }
        switch bytes[index] {
        case 0x7b:
            index += 1; skipSpace(); if index < bytes.count && bytes[index] == 0x7d { index += 1; return true }
            var keys = Set<String>()
            while true {
                skipSpace(); guard let key = stringToken(), keys.insert(key).inserted else { return false }
                skipSpace(); guard index < bytes.count, bytes[index] == 0x3a else { return false }; index += 1
                guard value(depth + 1) else { return false }; skipSpace(); guard index < bytes.count else { return false }
                if bytes[index] == 0x7d { index += 1; return true }
                guard bytes[index] == 0x2c else { return false }; index += 1
            }
        case 0x5b:
            index += 1; skipSpace(); if index < bytes.count && bytes[index] == 0x5d { index += 1; return true }
            while true {
                guard value(depth + 1) else { return false }; skipSpace(); guard index < bytes.count else { return false }
                if bytes[index] == 0x5d { index += 1; return true }
                guard bytes[index] == 0x2c else { return false }; index += 1
            }
        case 0x22: return stringToken() != nil
        default:
            while index < bytes.count && ![0x2c, 0x5d, 0x7d, 0x20, 0x09, 0x0a, 0x0d].contains(bytes[index]) { index += 1 }
            return index > 0
        }
    }
    mutating func hasNoDuplicateKeys() -> Bool {
        let valid = value(); skipSpace(); return valid && index == bytes.count
    }
}

private func frameRead(_ fd: Int32, expectedSequence: UInt64,
                       owner: String, child: String) throws -> [String: Any] {
    let prefix = try readExact(fd, 4)
    let size = prefix.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
    guard size > 0, size <= maxFrame else { throw PhoneRemoteAuthorityError.invalidFrame }
    let bytes = try readExact(fd, Int(size))
    var duplicateScanner = DuplicateKeyScanner(bytes: Array(bytes))
    guard duplicateScanner.hasNoDuplicateKeys() else { throw PhoneRemoteAuthorityError.invalidFrame }
    guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
          Set(object.keys) == Set(["protocol", "version", "kind", "owner_incarnation", "child_incarnation", "sequence", "correlation_id", "payload"]),
          object["protocol"] as? String == protocolName,
          exactInt(object["version"], min: 1) == 1,
          let kind = object["kind"] as? String, !kind.isEmpty,
          object["owner_incarnation"] as? String == owner,
          object["child_incarnation"] as? String == child,
          exactInt(object["sequence"], min: 1) == expectedSequence,
          let correlation = object["correlation_id"] as? String,
          UUID(uuidString: correlation)?.uuidString.lowercased() == correlation,
          let payload = object["payload"] as? [String: Any] else { throw PhoneRemoteAuthorityError.invalidFrame }
    return ["kind": kind, "correlation_id": correlation, "payload": payload]
}

private func frameWrite(_ fd: Int32, sequence: UInt64, owner: String, child: String,
                        kind: String, correlation: String, payload: [String: Any]) throws {
    let object: [String: Any] = ["protocol": protocolName, "version": 1, "kind": kind,
        "owner_incarnation": owner, "child_incarnation": child, "sequence": sequence,
        "correlation_id": correlation, "payload": payload]
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .fragmentsAllowed])
    guard !data.isEmpty, data.count <= maxFrame else { throw PhoneRemoteAuthorityError.invalidFrame }
    var n = UInt32(data.count).bigEndian
    var packet = Data(bytes: &n, count: 4); packet.append(data)
    try writeAll(fd, packet)
}

private struct Anchor: Equatable {
    var version: UInt64
    var host: String
    var generation: UInt64
    var transitionID: String?
    var transition: String
    var login: UInt64
    init(_ value: [String: Any]) throws {
        guard Set(value.keys) == Set(["anchor_version", "host_id", "host_generation", "transition_id", "transition_state", "login_counter"]),
              let version = exactInt(value["anchor_version"], min: 1), version <= UInt32.max,
              let host = value["host_id"] as? String, !host.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let generation = exactInt(value["host_generation"]),
              let login = exactInt(value["login_counter"]),
              let transition = value["transition_state"] as? String,
              transition == "stable" || transition == "pending" else { throw PhoneRemoteAuthorityError.invalidFrame }
        let rawID = value["transition_id"]
        let id: String?
        if transition == "stable" {
            guard rawID is NSNull else { throw PhoneRemoteAuthorityError.invalidFrame }
            id = nil
        } else {
            guard let pendingID = rawID as? String, !pendingID.isEmpty else { throw PhoneRemoteAuthorityError.invalidFrame }
            id = pendingID
        }
        self.version = version; self.host = host; self.generation = generation
        self.transitionID = id; self.transition = transition; self.login = login
    }
    static func == (lhs: Anchor, rhs: Anchor) -> Bool {
        lhs.version == rhs.version
            && lhs.host.utf8.elementsEqual(rhs.host.utf8)
            && lhs.generation == rhs.generation
            && optionalBytesEqual(lhs.transitionID, rhs.transitionID)
            && lhs.transition == rhs.transition
            && lhs.login == rhs.login
    }

    private static func optionalBytesEqual(_ lhs: String?, _ rhs: String?) -> Bool {
        switch (lhs, rhs) {
        case (nil, nil): return true
        case let (left?, right?): return left.utf8.elementsEqual(right.utf8)
        default: return false
        }
    }
    var wire: [String: Any] { ["anchor_version": version, "host_id": host, "host_generation": generation,
        "transition_id": transitionID as Any? ?? NSNull(), "transition_state": transition, "login_counter": login] }
}

private func decodeAnchorFile(_ data: Data) throws -> Anchor {
    guard !data.isEmpty, data.count <= maxFrame else { throw PhoneRemoteAuthorityError.invalidFrame }
    var scanner = DuplicateKeyScanner(bytes: Array(data))
    guard scanner.hasNoDuplicateKeys(),
          let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw PhoneRemoteAuthorityError.invalidFrame
    }
    return try Anchor(object)
}

/// A deliberately narrow fake-anchor owner used by the process-boundary claim.
/// Production Keychain construction and listener/service wiring are excluded.
public final class PhoneRemoteAuthorityOwner {
    private let lockFD: Int32
    private let listenerFD: Int32
    private let childPID: pid_t
    private let ownerID: String
    private let childID: String
    private var outSequence: UInt64 = 0
    private var inSequence: UInt64 = 1
    private var anchor: Anchor
    private var initialAnchor: Anchor
    private var grant: String?
    private var operation: String?
    private var phase = "idle"
    private var verifiedRead = false
    private var terminal = false
    private var correlation = ""
    private let expectedGrants: Int
    private let holdMilliseconds: UInt32
    private let readyPath: String
    private let anchorPath: String
    private var completedGrants = 0
    private var terminalStatus: Int32 = 0

    private init(lockFD: Int32, listenerFD: Int32, childPID: pid_t, ownerID: String,
                childID: String, anchor: Anchor, expectedGrants: Int,
                holdMilliseconds: UInt32, readyPath: String, anchorPath: String) {
        self.lockFD = lockFD; self.listenerFD = listenerFD; self.childPID = childPID
        self.ownerID = ownerID; self.childID = childID; self.anchor = anchor; self.initialAnchor = anchor
        self.expectedGrants = expectedGrants; self.holdMilliseconds = holdMilliseconds; self.readyPath = readyPath
        self.anchorPath = anchorPath
    }

    /// Runs one owner lifecycle. The lock descriptor stays open until child reaping.
    public static func runOfflineTestOwner(lockPath: String, python: String, database: String,
                           workingDirectory: String, scenario: String, expectedGrants: Int,
                           holdMilliseconds: UInt32, readyPath: String,
                           testHostGeneration: UInt64, testLoginCounter: UInt64,
                           testAnchorPath: String) throws -> Int32 {
        guard (0...64).contains(expectedGrants), holdMilliseconds <= 60_000 else { return 64 }
        let lockFD = open(lockPath, O_RDWR | O_NOFOLLOW)
        guard lockFD >= 0 else { return 20 }
        // Any pre-child validation error or early return must release the
        // acquired descriptor. On the normal path this defer runs only after
        // the spawned child has been reaped below.
        defer { close(lockFD) }
        var lockStat = stat()
        guard fstat(lockFD, &lockStat) == 0, (lockStat.st_mode & S_IFMT) == S_IFREG,
              lockStat.st_uid == geteuid(), (lockStat.st_mode & 0o077) == 0,
              lockStat.st_nlink == 1 else { return 20 }
        let lockDirectory = URL(fileURLWithPath: lockPath).deletingLastPathComponent().path
        var directoryStat = stat()
        guard lstat(lockDirectory, &directoryStat) == 0,
              (directoryStat.st_mode & S_IFMT) == S_IFDIR,
              directoryStat.st_uid == geteuid(), (directoryStat.st_mode & 0o077) == 0 else {
            return 20
        }
        guard flock(lockFD, LOCK_EX | LOCK_NB) == 0 else { return 21 }
        let anchorData = try Data(contentsOf: URL(fileURLWithPath: testAnchorPath))
        let initial = try decodeAnchorFile(anchorData)
        guard initial.version == 1, initial.generation == testHostGeneration,
              initial.login == testLoginCounter, initial.generation > 0,
              initial.transition == "stable", initial.transitionID == nil else { return 25 }
        var sockets: [Int32] = [0, 0]
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else { return 22 }
        let ownerID = UUID().uuidString.lowercased(), childID = UUID().uuidString.lowercased()
        let pid: pid_t
        do {
            pid = try spawnChild(python: python, database: database, workingDirectory: workingDirectory,
                                 scenario: scenario, socketFD: sockets[1], lockFD: lockFD)
        } catch {
            close(sockets[0]); close(sockets[1]); throw error
        }
        close(sockets[1])
        let owner = PhoneRemoteAuthorityOwner(lockFD: lockFD, listenerFD: sockets[0], childPID: pid,
                                              ownerID: ownerID, childID: childID, anchor: initial,
                                              expectedGrants: expectedGrants, holdMilliseconds: holdMilliseconds,
                                              readyPath: readyPath, anchorPath: testAnchorPath)
        var status = owner.serve()
        // Always close the owner endpoint before waiting. Terminal abort/error
        // paths must deliver EOF to a child that may be waiting for it. Keep
        // the singleton descriptor until that child has actually exited.
        _ = shutdown(sockets[0], SHUT_RDWR)
        close(sockets[0])
        var childStatus: Int32 = 0
        var waited: pid_t
        repeat { waited = waitpid(pid, &childStatus, 0) } while waited < 0 && errno == EINTR
        let childExitedNormally = (childStatus & 0x7f) == 0
        let childExitCode = (childStatus >> 8) & 0xff
        if status == 0 && (!childExitedNormally || childExitCode != 0) {
            status = 40 + (childExitedNormally ? childExitCode : 0)
        }
        return status
    }

    private static func spawnChild(python: String, database: String, workingDirectory: String,
                                   scenario: String, socketFD: Int32, lockFD: Int32) throws -> pid_t {
        var actions: posix_spawn_file_actions_t?; posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        let safeSocket = fcntl(socketFD, F_DUPFD, 10)
        let safeLock = fcntl(lockFD, F_DUPFD, 10)
        guard safeSocket >= 0, safeLock >= 0 else { throw PhoneRemoteAuthorityError.unavailable }
        defer { close(safeSocket); close(safeLock) }
        for fd: Int32 in 0...2 where fcntl(fd, F_GETFD) >= 0 {
            guard posix_spawn_file_actions_addclose(&actions, fd) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
        }
        guard posix_spawn_file_actions_adddup2(&actions, safeSocket, 3) == 0,
              posix_spawn_file_actions_adddup2(&actions, safeLock, 4) == 0 else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        guard let directory = opendir("/dev/fd") else { throw PhoneRemoteAuthorityError.unavailable }
        let directoryFD = dirfd(directory)
        while let entry = readdir(directory) {
            let name = withUnsafePointer(to: entry.pointee.d_name) {
                $0.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: entry.pointee.d_name)) {
                    String(cString: $0)
                }
            }
            if let fd = Int32(name), fd >= 5, fd != directoryFD {
                guard posix_spawn_file_actions_addclose(&actions, fd) == 0 else {
                    closedir(directory); throw PhoneRemoteAuthorityError.unavailable
                }
            }
        }
        closedir(directory)
        guard workingDirectory.withCString({ posix_spawn_file_actions_addchdir(&actions, $0) }) == 0 else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        var attr: posix_spawnattr_t?; posix_spawnattr_init(&attr)
        defer { posix_spawnattr_destroy(&attr) }
        let args = [python, "-m", "tests.unit.test_phone_remote_authority_channel", "--authority-child", database, scenario]
        var argv = args.map { strdup($0) }; argv.append(nil)
        defer { argv.forEach { free($0) } }
        let parentEnvironment = ProcessInfo.processInfo.environment
        var envMap = [
            "PATH": "/usr/bin:/bin", "PYTHONPATH": workingDirectory,
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8", "PHONE_REMOTE_AUTHORITY_CHANNEL_FD": "3",
            "PHONE_REMOTE_AUTHORITY_LOCK_FD": "4"
        ]
        // Only deterministic offline test controls cross the process boundary.
        for key in ["PHONE_REMOTE_AUTHORITY_FAILPOINT", "PHONE_REMOTE_AUTHORITY_CRASH_AT",
                    "PHONE_REMOTE_AUTHORITY_ENTERED_FILE", "PHONE_REMOTE_AUTHORITY_RELEASE_FILE",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT",
                    "PHONE_REMOTE_AUTHORITY_TEST_DUPLICATE_READBACK"] {
            if let value = parentEnvironment[key] { envMap[key] = value }
        }
        var env = envMap.map { strdup("\($0.key)=\($0.value)") }; env.append(nil)
        defer { env.forEach { free($0) } }
        var pid: pid_t = 0
        let rc = args[0].withCString { path in
            argv.withUnsafeMutableBufferPointer { av in env.withUnsafeMutableBufferPointer { ev in
                posix_spawn(&pid, path, &actions, &attr, av.baseAddress!, ev.baseAddress!)
            }}
        }
        guard rc == 0 else { fputs("child spawn failed: \(rc)\n", stderr); throw PhoneRemoteAuthorityError.unavailable }
        return pid
    }

    private func send(_ kind: String, _ payload: [String: Any], correlation: String) throws {
        guard outSequence < maxSequence else { throw PhoneRemoteAuthorityError.invalidFrame }
        outSequence += 1
        try frameWrite(listenerFD, sequence: outSequence, owner: ownerID, child: childID,
                       kind: kind, correlation: correlation, payload: payload)
    }

    private func receive() throws -> (String, String, [String: Any]) {
        let frame = try frameRead(listenerFD, expectedSequence: inSequence, owner: ownerID, child: childID)
        guard inSequence < maxSequence else { throw PhoneRemoteAuthorityError.invalidFrame }
        inSequence += 1
        return (frame["kind"] as! String, frame["correlation_id"] as! String, frame["payload"] as! [String: Any])
    }

    private func error(_ code: String, correlation: String) {
        fputs("authority protocol stopped: \(code)\n", stderr)
        if !terminal { try? send("owner.error", ["code": code], correlation: correlation) }
        terminalStatus = 30
        terminal = true
    }

    private func serve() -> Int32 {
        correlation = UUID().uuidString.lowercased()
        do {
            try send("owner.hello", ["max_frame_bytes": maxFrame], correlation: correlation)
            let ready = try receive()
            guard ready.0 == "child.ready", ready.1 == correlation, ready.2.isEmpty else { error("phase_invalid", correlation: ready.1); return 23 }
            if !readyPath.isEmpty { try? Data("ready".utf8).write(to: URL(fileURLWithPath: readyPath), options: .atomic) }
            if holdMilliseconds > 0 { usleep(holdMilliseconds * 1000) }
            if expectedGrants == 0 { try shutdownChild(correlation: correlation) }
            while !terminal {
                let (kind, corr, p) = try receive()
                try handle(kind, corr, p)
            }
            return terminalStatus
        } catch {
            fputs("authority protocol stopped: invalid channel\n", stderr)
            terminalStatus = 31
            terminal = true
            return 24
        }
    }

    private func handle(_ kind: String, _ corr: String, _ p: [String: Any]) throws {
        switch kind {
        case "child.grant.acquire":
            guard Set(p.keys) == ["operation"], let op = p["operation"] as? String,
                  ["store.open", "store.read", "session.login", "session.signout", "authority.mutate", "ticket.issue", "ticket.consume"].contains(op)
            else { error("phase_invalid", correlation: corr); return }
            guard grant == nil else { error("owner_busy", correlation: corr); return }
            guard anchor.transition == "stable", anchor == initialAnchor else { error("authority_unavailable", correlation: corr); return }
            grant = UUID().uuidString.lowercased(); operation = op; phase = "read"
            verifiedRead = false
            try send("owner.grant.acquired", ["grant_id": grant!, "operation": op], correlation: corr)
        case "child.anchor.read":
            guard Set(p.keys) == ["grant_id"], validGrant(p), phase == "read" || phase == "writeAdvance" || phase == "writeReadback" || phase == "stableReadback",
                  (anchor.transition == "stable" || phase != "read") else { error("phase_invalid", correlation: corr); return }
            guard (try? readTestAnchor()) == anchor else { error("anchor_corrupt", correlation: corr); return }
            verifiedRead = true
            if phase == "writeReadback" { phase = "writeAdvance" }
            if phase == "stableReadback" { phase = "release" }
            if phase == "read" && (operation == "authority.mutate" || operation == "session.login") { phase = "writeAdvance" }
            try send("owner.anchor.state", ["grant_id": grant!, "state": anchor.wire], correlation: corr)
        case "child.anchor.advance":
            guard Set(p.keys) == ["grant_id", "step", "state"], validGrant(p), phase == "writeAdvance", let step = p["step"] as? String,
                  let object = p["state"] as? [String: Any], let next = try? Anchor(object), isLegal(next, step: step) else {
                error("phase_invalid", correlation: corr); return
            }
            anchor = next
            let anchorBytes = try JSONSerialization.data(withJSONObject: anchor.wire, options: [.sortedKeys])
            var storedAnchorBytes = anchorBytes
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_DUPLICATE_READBACK"] == "host_generation" {
                let canonical = String(decoding: anchorBytes, as: UTF8.self)
                let original = "\"host_generation\":\(anchor.generation)"
                guard canonical.contains(original) else { throw PhoneRemoteAuthorityError.invalidFrame }
                storedAnchorBytes = Data(canonical.replacingOccurrences(of: original,
                    with: original + ",\"host_generation\":0").utf8)
            }
            try storedAnchorBytes.write(to: URL(fileURLWithPath: anchorPath), options: .atomic)
            guard try readTestAnchor() == anchor else { error("anchor_corrupt", correlation: corr); return }
            phase = (step == "global_pending" || step == "login_pending") ? "writeReadback" : "stableReadback"
            try send("owner.anchor.verified", ["grant_id": grant!, "state": anchor.wire], correlation: corr)
        case "child.grant.release":
            guard Set(p.keys) == ["grant_id"], validGrant(p), verifiedRead,
                  (phase == "read" && anchor.transition == "stable"
                    && ["store.open", "store.read", "session.signout", "ticket.issue", "ticket.consume"].contains(operation!)) || phase == "release" else {
                error("phase_invalid", correlation: corr); return
            }
            let id = grant!; let completedOperation = operation!
            grant = nil; operation = nil; phase = "idle"; verifiedRead = false; initialAnchor = anchor
            pauseBeforeTestReleaseAck(operation: completedOperation)
            try send("owner.grant.released", ["grant_id": id], correlation: corr)
            completedGrants += 1
            if expectedGrants > 0 && completedGrants == expectedGrants { try shutdownChild(correlation: corr) }
        case "child.grant.abort":
            guard Set(p.keys) == ["grant_id"], validGrant(p) else { error("grant_invalid", correlation: corr); return }
            let id = grant!; grant = nil; operation = nil
            try send("owner.grant.aborted", ["grant_id": id, "disposition": "unknown"], correlation: corr)
            terminalStatus = 32
            terminal = true
        case "child.shutdown_ack":
            error("phase_invalid", correlation: corr)
        default: error("malformed_frame", correlation: corr)
        }
    }

    private func pauseBeforeTestReleaseAck(operation: String) {
        let target = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE"]
        guard target == operation,
              let entered = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_ENTERED_FILE"],
              let release = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RELEASE_FILE"] else { return }
        try? Data("before-ack".utf8).write(to: URL(fileURLWithPath: entered), options: .atomic)
        while !FileManager.default.fileExists(atPath: release) { usleep(5_000) }
    }

    private func shutdownChild(correlation: String) throws {
        try send("owner.shutdown", ["reason": "requested"], correlation: correlation)
        let (kind, corr, payload) = try receive()
        guard kind == "child.shutdown_ack", corr == correlation, payload.isEmpty, grant == nil else {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        terminal = true
    }

    private func validGrant(_ p: [String: Any]) -> Bool {
        p["grant_id"] as? String == grant && grant != nil
    }

    private func readTestAnchor() throws -> Anchor {
        let data = try Data(contentsOf: URL(fileURLWithPath: anchorPath))
        return try decodeAnchorFile(data)
    }

    private func isLegal(_ n: Anchor, step: String) -> Bool {
        guard let op = operation else { return false }
        if phase == "writeAdvance" && anchor.transition == "stable" {
            guard n.version == anchor.version, n.host.utf8.elementsEqual(anchor.host.utf8), n.transition == "pending", n.transitionID != nil else { return false }
            if step == "global_pending" && op == "authority.mutate" {
                return anchor.generation < maxSequence && n.generation == anchor.generation + 1 && n.login == anchor.login
            }
            if step == "login_pending" && op == "session.login" {
                return anchor.login < maxSequence && n.generation == anchor.generation && n.login == anchor.login + 1
            }
            return false
        }
        if anchor.transition == "pending", n.transition == "stable", n.transitionID == nil,
           n.version == anchor.version, n.host.utf8.elementsEqual(anchor.host.utf8),
           n.generation == anchor.generation, n.login == anchor.login {
            return (step == "global_stable" && op == "authority.mutate") || (step == "login_stable" && op == "session.login")
        }
        return false
    }

    deinit { /* explicit owner lifecycle closes descriptors after waitpid */ }
}
