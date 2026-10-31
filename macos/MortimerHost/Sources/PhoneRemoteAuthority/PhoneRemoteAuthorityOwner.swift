import CoreFoundation
import Foundation
import Darwin
import SQLite3
import CryptoKit

public enum PhoneRemoteAuthorityError: Error { case invalidFrame, unavailable }

private let protocolNameV1 = "mortimer.phone-authority-channel.v1"
private let protocolNameV2 = "mortimer.phone-authority-channel.v2"
private let protocolNameV3 = "mortimer.phone-authority-channel.v3"
private let protocolNameV4 = "mortimer.phone-authority-channel.v4"
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

private func waitReadable(_ fd: Int32, until deadline: Double) throws {
    while true {
        let remaining = deadline - ProcessInfo.processInfo.systemUptime
        guard remaining > 0 else { throw PhoneRemoteAuthorityError.unavailable }
        let timeout = Int32(max(1, min(Double(Int32.max), ceil(remaining * 1_000))))
        var descriptor = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
        let result = poll(&descriptor, nfds_t(1), timeout)
        if result > 0 { return }
        if result == 0 { throw PhoneRemoteAuthorityError.unavailable }
        if errno != EINTR { throw PhoneRemoteAuthorityError.unavailable }
    }
}

private func readExact(_ fd: Int32, _ count: Int, deadline: Double? = nil) throws -> Data {
    var data = Data(count: count)
    try data.withUnsafeMutableBytes { raw in
        guard let base = raw.baseAddress else { throw PhoneRemoteAuthorityError.invalidFrame }
        var offset = 0
        while offset < count {
            if let deadline { try waitReadable(fd, until: deadline) }
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

private func waitForChild(_ pid: pid_t, status: inout Int32, milliseconds: Int) -> pid_t {
    let deadline = ProcessInfo.processInfo.systemUptime + Double(milliseconds) / 1_000
    while ProcessInfo.processInfo.systemUptime < deadline {
        let result = waitpid(pid, &status, WNOHANG)
        if result < 0 && errno == EINTR { continue }
        if result < 0 { return -2 }
        if result != 0 { return result }
        usleep(5_000)
    }
    while true {
        let result = waitpid(pid, &status, WNOHANG)
        if result < 0 && errno == EINTR { continue }
        return result < 0 ? -2 : result
    }
}

struct DuplicateKeyScanner {
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

func frameRead(_ fd: Int32, expectedSequence: UInt64,
                       owner: String, child: String, protocolName: String, version: UInt64,
                       deadline: Double? = nil) throws -> [String: Any] {
    let prefix = try readExact(fd, 4, deadline: deadline)
    let size = prefix.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
    guard size > 0, size <= maxFrame else { throw PhoneRemoteAuthorityError.invalidFrame }
    let bytes = try readExact(fd, Int(size), deadline: deadline)
    var duplicateScanner = DuplicateKeyScanner(bytes: Array(bytes))
    guard duplicateScanner.hasNoDuplicateKeys() else { throw PhoneRemoteAuthorityError.invalidFrame }
    guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
          Set(object.keys) == Set(["protocol", "version", "kind", "owner_incarnation", "child_incarnation", "sequence", "correlation_id", "payload"]),
          object["protocol"] as? String == protocolName,
          exactInt(object["version"], min: version) == version,
          let kind = object["kind"] as? String, !kind.isEmpty,
          object["owner_incarnation"] as? String == owner,
          object["child_incarnation"] as? String == child,
          exactInt(object["sequence"], min: 1) == expectedSequence,
          let correlation = object["correlation_id"] as? String,
          UUID(uuidString: correlation)?.uuidString.lowercased() == correlation,
          let payload = object["payload"] as? [String: Any] else { throw PhoneRemoteAuthorityError.invalidFrame }
    return ["kind": kind, "correlation_id": correlation, "payload": payload]
}

func frameWrite(_ fd: Int32, sequence: UInt64, owner: String, child: String,
                        kind: String, correlation: String, payload: [String: Any],
                        protocolName: String, version: UInt64) throws {
    let object: [String: Any] = ["protocol": protocolName, "version": version, "kind": kind,
        "owner_incarnation": owner, "child_incarnation": child, "sequence": sequence,
        "correlation_id": correlation, "payload": payload]
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .fragmentsAllowed])
    guard !data.isEmpty, data.count <= maxFrame else { throw PhoneRemoteAuthorityError.invalidFrame }
    var n = UInt32(data.count).bigEndian
    var packet = Data(bytes: &n, count: 4); packet.append(data)
    try writeAll(fd, packet)
}

struct Anchor: Equatable {
    let version: UInt64
    let host: String
    let generation: UInt64
    let transitionID: String?
    let transition: String
    let login: UInt64
    let pendingRestore: [String: Any]?
    let lastCompletedRestore: [String: Any]?
    init(_ value: [String: Any]) throws {
        let baseKeys: Set<String> = ["anchor_version", "host_id", "host_generation", "transition_id", "transition_state", "login_counter"]
        guard let rawVersion = exactInt(value["anchor_version"], min: 1), rawVersion <= 2,
              Set(value.keys) == (rawVersion == 1 ? baseKeys : baseKeys.union(["pending_restore", "last_completed_restore"])),
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
        let pending: [String: Any]?
        let tombstone: [String: Any]?
        if version == 1 {
            pending = nil; tombstone = nil
        } else {
            guard let rawPending = value["pending_restore"], let rawTombstone = value["last_completed_restore"] else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            pending = try Self.validatePending(rawPending, transitionID: id, generation: generation,
                                               transition: transition)
            tombstone = try Self.validateTombstone(rawTombstone, transition: transition)
            if transition == "stable" && tombstone == nil { throw PhoneRemoteAuthorityError.invalidFrame }
        }
        self.version = version; self.host = host; self.generation = generation
        self.transitionID = id; self.transition = transition; self.login = login
        self.pendingRestore = pending; self.lastCompletedRestore = tombstone
    }
    static func == (lhs: Anchor, rhs: Anchor) -> Bool {
        lhs.version == rhs.version
            && lhs.host.utf8.elementsEqual(rhs.host.utf8)
            && lhs.generation == rhs.generation
            && optionalBytesEqual(lhs.transitionID, rhs.transitionID)
            && lhs.transition == rhs.transition
            && lhs.login == rhs.login
            && Self.jsonEqual(lhs.pendingRestore, rhs.pendingRestore)
            && Self.jsonEqual(lhs.lastCompletedRestore, rhs.lastCompletedRestore)
    }

    private static func validDigest(_ value: Any?) -> Bool {
        guard let value = value as? String, value.utf8.count == 64 else { return false }
        return value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    private static func canonicalUUID(_ value: Any?) -> String? {
        guard let text = value as? String, text.count == 36,
              let uuid = UUID(uuidString: text), uuid.uuidString.lowercased() == text else { return nil }
        return text
    }
    private static func validatePending(_ raw: Any, transitionID: String?, generation: UInt64,
                                        transition: String) throws -> [String: Any]? {
        if raw is NSNull { return nil }
        guard transition == "pending", let object = raw as? [String: Any],
              Set(object.keys) == ["operation_id", "target_generation", "manifest_sha256", "checkpoint_sha256"],
              canonicalUUID(object["operation_id"]) == transitionID,
              let target = exactInt(object["target_generation"], min: 1), target == generation,
              validDigest(object["manifest_sha256"]), validDigest(object["checkpoint_sha256"]) else {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        return object
    }
    private static func validateTombstone(_ raw: Any, transition: String) throws -> [String: Any]? {
        if raw is NSNull {
            if transition == "stable" { throw PhoneRemoteAuthorityError.invalidFrame }
            return nil
        }
        guard let object = raw as? [String: Any],
              Set(object.keys) == ["operation_id", "target_generation", "manifest_sha256", "checkpoint_sha256", "database_sha256"],
              canonicalUUID(object["operation_id"]) != nil,
              exactInt(object["target_generation"], min: 1) != nil,
              validDigest(object["manifest_sha256"]), validDigest(object["checkpoint_sha256"]),
              validDigest(object["database_sha256"]) else { throw PhoneRemoteAuthorityError.invalidFrame }
        return object
    }
    private static func jsonEqual(_ lhs: [String: Any]?, _ rhs: [String: Any]?) -> Bool {
        switch (lhs, rhs) {
        case (nil, nil): return true
        case let (left?, right?):
            guard let a = try? JSONSerialization.data(withJSONObject: left, options: [.sortedKeys]),
                  let b = try? JSONSerialization.data(withJSONObject: right, options: [.sortedKeys]) else { return false }
            return a == b
        default: return false
        }
    }

    func preservesRestoreMetadata(from previous: Anchor) -> Bool {
        Self.jsonEqual(pendingRestore, previous.pendingRestore)
            && Self.jsonEqual(lastCompletedRestore, previous.lastCompletedRestore)
    }

    private static func optionalBytesEqual(_ lhs: String?, _ rhs: String?) -> Bool {
        switch (lhs, rhs) {
        case (nil, nil): return true
        case let (left?, right?): return left.utf8.elementsEqual(right.utf8)
        default: return false
        }
    }
    var wire: [String: Any] {
        var value: [String: Any] = ["anchor_version": version, "host_id": host, "host_generation": generation,
            "transition_id": transitionID as Any? ?? NSNull(), "transition_state": transition, "login_counter": login]
        if version == 2 {
            value["pending_restore"] = pendingRestore as Any? ?? NSNull()
            value["last_completed_restore"] = lastCompletedRestore as Any? ?? NSNull()
        }
        return value
    }
    var projection: [String: Any] { ["anchor_version": 1, "host_id": host, "host_generation": generation,
        "transition_id": transitionID as Any? ?? NSNull(), "transition_state": transition, "login_counter": login] }
}

func decodeAnchorFile(_ data: Data) throws -> Anchor {
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
    private var helloCorrelation = ""
    private let expectedGrants: Int
    private let holdMilliseconds: UInt32
    private let readyPath: String
    private let anchorSession: PhoneRemoteAuthorityAnchorSession
    private var terminalErrorSent = false
    private var normalDraining = false
    private var offlineQuiescencePath: String?
    private var serviceActivated = false
    private var serviceReadyCorrelation: String?
    private var completedGrants = 0
    private var terminalStatus: Int32 = 0
    private var restorePrepared = false
    private var restoreHoldRequired = false
    private var restoreCorrelations = Set<String>()
    private let version: UInt64
    private var protocolName: String { version == 4 ? protocolNameV4 : (version == 3 ? protocolNameV3 : (version == 2 ? protocolNameV2 : protocolNameV1)) }

    init(lockFD: Int32, listenerFD: Int32, childPID: pid_t, ownerID: String,
                childID: String, anchor: Anchor, expectedGrants: Int,
                holdMilliseconds: UInt32, readyPath: String,
                anchorBackend: PhoneRemoteAuthorityAnchorBackend, version: UInt64) {
        self.lockFD = lockFD; self.listenerFD = listenerFD; self.childPID = childPID
        self.ownerID = ownerID; self.childID = childID; self.anchor = anchor; self.initialAnchor = anchor
        self.expectedGrants = expectedGrants; self.holdMilliseconds = holdMilliseconds; self.readyPath = readyPath
        self.anchorSession = PhoneRemoteAuthorityAnchorSession(backend: anchorBackend)
        self.version = version
    }

    /// Runs one owner lifecycle. The lock descriptor stays open until child reaping.
    public static func runOfflineTestOwner(lockPath: String, python: String, database: String,
                           workingDirectory: String, scenario: String, expectedGrants: Int,
                           holdMilliseconds: UInt32, readyPath: String,
                           testHostGeneration: UInt64, testLoginCounter: UInt64,
                           testAnchorPath: String) throws -> Int32 {
        // Include the store.open grant plus up to 64 challenge grants in the
        // total-capacity acceptance scenario.
        guard (0...65).contains(expectedGrants), holdMilliseconds <= 60_000 else { return 64 }
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
        if scenario == "v4-recovery" {
            return try runOfflineRecovery(lockFD: lockFD, python: python, database: database,
                workingDirectory: workingDirectory, anchorPath: testAnchorPath, readyPath: readyPath)
        }
        let version: UInt64 = scenario.hasPrefix("v4-") ? 4 : (scenario.hasPrefix("v3-") ? 3 : (scenario.hasPrefix("v2-") ? 2 : 1))
        let anchorBackend = FilePhoneRemoteAuthorityAnchor(path: testAnchorPath)
        let initial = try anchorBackend.read()
        let validInitialVersion = version == 4
            ? (initial.version == 1 || (initial.version == 2 && initial.pendingRestore == nil
                && initial.lastCompletedRestore != nil))
            : initial.version == 1
        guard validInitialVersion, initial.generation == testHostGeneration,
              initial.login == testLoginCounter, initial.generation > 0,
              initial.transition == "stable", initial.transitionID == nil else { return 25 }
        var sockets: [Int32] = [0, 0]
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else { return 22 }
        var noSigPipe: Int32 = 1
        guard setsockopt(sockets[0], SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe,
                         socklen_t(MemoryLayout<Int32>.size)) == 0,
              setsockopt(sockets[1], SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe,
                         socklen_t(MemoryLayout<Int32>.size)) == 0 else {
            close(sockets[0]); close(sockets[1]); return 22
        }
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
                                              readyPath: readyPath, anchorBackend: anchorBackend,
                                              version: version)
        var status = owner.serve()
        // Always close the owner endpoint before waiting. Terminal abort/error
        // paths must deliver EOF to a child that may be waiting for it. Keep
        // the singleton descriptor until that child has actually exited.
        _ = shutdown(sockets[0], SHUT_RDWR)
        close(sockets[0])
        var childStatus: Int32 = 0
        var waited: pid_t
        var cleanupSignal = "none"
        if owner.restoreHoldRequired {
            if let marker = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RESTORE_REAP_WAIT_FILE"] {
                try? Data("waiting".utf8).write(to: URL(fileURLWithPath: marker), options: .atomic)
            }
            let grace = owner.testDuration("PHONE_REMOTE_AUTHORITY_TEST_RESTORE_REAP_GRACE_MS", fallback: 500)
            let initialWait = waitForChild(pid, status: &childStatus, milliseconds: grace)
            if initialWait == -2 {
                while true { sleep(1) }
            } else if initialWait != pid {
                cleanupSignal = "TERM"
                _ = kill(pid, SIGTERM)
                let termWait = waitForChild(pid, status: &childStatus, milliseconds: 500)
                if termWait == -2 {
                    while true { sleep(1) }
                } else if termWait != pid {
                    cleanupSignal = "KILL"
                    _ = kill(pid, SIGKILL)
                    repeat { waited = waitpid(pid, &childStatus, 0) } while waited < 0 && errno == EINTR
                } else {
                    waited = pid
                }
            } else {
                waited = pid
            }
            guard waited == pid else {
                // Never release the authority lock until the owned child is
                // confirmed reaped. Remain fenced if the kernel is uncertain.
                while true { sleep(1) }
            }
            if let marker = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RESTORE_REAP_FILE"] {
                let receipt = "reaped;signal=\(cleanupSignal);status=\(childStatus)"
                try? Data(receipt.utf8).write(to: URL(fileURLWithPath: marker), options: .atomic)
            }
        } else {
            repeat { waited = waitpid(pid, &childStatus, 0) } while waited < 0 && errno == EINTR
        }
        let childExitedNormally = (childStatus & 0x7f) == 0
        let childExitCode = (childStatus >> 8) & 0xff
        if status == 0 && (!childExitedNormally || childExitCode != 0) {
            status = 40 + (childExitedNormally ? childExitCode : 0)
        }
        if owner.restoreHoldRequired {
            if let marker = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE"] {
                try? Data("pending-or-uncertain".utf8).write(to: URL(fileURLWithPath: marker), options: .atomic)
            }
            // Once an anchor write was attempted, even a failed acknowledgment
            // leaves persistence uncertain. Never release the owner lock.
            while true { sleep(1) }
        }
        return status
    }

    private static func spawnChild(python: String, database: String, workingDirectory: String,
                                   scenario: String, socketFD: Int32, lockFD: Int32,
                                   recoveryConfig: [String: Any]? = nil, sourceFD: Int32? = nil) throws -> pid_t {
        var actions: posix_spawn_file_actions_t?; posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        let safeSocket = fcntl(socketFD, F_DUPFD, 10)
        let safeLock = fcntl(lockFD, F_DUPFD, 10)
        let safeSource = sourceFD.map { fcntl($0, F_DUPFD, 10) }
        defer { if let safeSource, safeSource >= 0 { close(safeSource) } }
        guard safeSocket >= 0, safeLock >= 0 else { throw PhoneRemoteAuthorityError.unavailable }
        defer { close(safeSocket); close(safeLock) }
        for fd: Int32 in 0...2 where fcntl(fd, F_GETFD) >= 0 {
            guard posix_spawn_file_actions_addclose(&actions, fd) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
        }
        guard posix_spawn_file_actions_adddup2(&actions, safeSocket, 3) == 0,
              posix_spawn_file_actions_adddup2(&actions, safeLock, 4) == 0 else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        if let safeSource {
            guard safeSource >= 0, posix_spawn_file_actions_adddup2(&actions, safeSource, 5) == 0 else {
                throw PhoneRemoteAuthorityError.unavailable
            }
        }
        guard let directory = opendir("/dev/fd") else { throw PhoneRemoteAuthorityError.unavailable }
        let directoryFD = dirfd(directory)
        while let entry = readdir(directory) {
            let name = withUnsafePointer(to: entry.pointee.d_name) {
                $0.withMemoryRebound(to: CChar.self, capacity: MemoryLayout.size(ofValue: entry.pointee.d_name)) {
                    String(cString: $0)
                }
            }
            if let fd = Int32(name), fd >= (sourceFD == nil ? 5 : 6), fd != directoryFD {
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
        let args: [String]
        if recoveryConfig != nil {
            args = [python, "-m", "tests.unit.test_phone_remote_recovery", "--recovery-child", database]
        } else if scenario.hasPrefix("v3-restore-") {
            args = [python, "-m", "tests.unit.test_phone_remote_authority_service",
                    "--authority-child", database, scenario]
        } else {
            args = [python, "-m", "tests.unit.test_phone_remote_authority_channel",
                    "--authority-child", database, scenario]
        }
        var argv = args.map { strdup($0) }; argv.append(nil)
        defer { argv.forEach { free($0) } }
        let parentEnvironment = ProcessInfo.processInfo.environment
        var envMap = [
            "PATH": "/usr/bin:/bin", "PYTHONPATH": workingDirectory,
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8", "PHONE_REMOTE_AUTHORITY_CHANNEL_FD": "3",
            "PHONE_REMOTE_AUTHORITY_LOCK_FD": "4"
        ]
        if let recoveryConfig {
            envMap["PHONE_REMOTE_AUTHORITY_RECOVERY_CONFIG"] = String(data: try RecoveryStorage.json(recoveryConfig), encoding: .utf8)!
        }
        if scenario.hasPrefix("v4-") { envMap["PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION"] = "4" }
        else if scenario.hasPrefix("v3-") { envMap["PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION"] = "3" }
        else if scenario.hasPrefix("v2-") { envMap["PHONE_REMOTE_AUTHORITY_PROTOCOL_VERSION"] = "2" }
        // Only deterministic offline test controls cross the process boundary.
        for key in ["PHONE_REMOTE_AUTHORITY_FAILPOINT", "PHONE_REMOTE_AUTHORITY_CRASH_AT",
                    "PHONE_REMOTE_AUTHORITY_ENTERED_FILE", "PHONE_REMOTE_AUTHORITY_RELEASE_FILE",
                    "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE",
                    "PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE",
                    "PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_ACK",
                    "PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_OCCURRENCE",
                    "PHONE_REMOTE_AUTHORITY_REJECT_ENTERED_FILE",
                    "PHONE_REMOTE_AUTHORITY_REJECT_RELEASE_FILE",
                    "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_ENTERED_FILE",
                    "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_RELEASE_FILE",
                    "PHONE_REMOTE_AUTHORITY_LOGIN_VERIFY_TIME_FILE",
                    "PHONE_REMOTE_AUTHORITY_LOGIN_MESSAGE_DIR",
                    "PHONE_REMOTE_AUTHORITY_MEDIA_ENTERED_FILE",
                    "PHONE_REMOTE_AUTHORITY_MEDIA_RELEASE_FILE",
                    "PHONE_REMOTE_AUTHORITY_TEST_SYNC_DIR",
                    "PHONE_REMOTE_AUTHORITY_SCENARIO_RESULT",
                    "PHONE_REMOTE_AUTHORITY_TEST_DUPLICATE_READBACK",
                    "PHONE_REMOTE_AUTHORITY_RESTORE_HOLD_FILE",
                    "PHONE_REMOTE_AUTHORITY_RESTORE_WIRE_FILE",
                    "PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] {
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
        let restoreOperation = operation == "restore.prepare"
        let restoreFrame = (kind == "owner.grant.acquired" && payload["operation"] as? String == "restore.prepare")
            || (restoreOperation && kind == "owner.anchor.state")
            || (restoreOperation && kind == "owner.anchor.verified"
                && (payload["state"] as? [String: Any])?["transition_id"] as? String != nil)
            || ((restoreOperation || restorePrepared)
                && (kind == "owner.restore.prepared" || kind == "owner.shutdown"))
        if restoreFrame, let path = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RESTORE_WIRE_FILE"] {
            let trace: [String: Any] = ["direction": "owner", "kind": kind,
                "correlation_id": correlation, "sequence": outSequence, "payload": payload]
            if let data = try? JSONSerialization.data(withJSONObject: trace, options: [.sortedKeys]) {
                let fd = open(path, O_WRONLY | O_CREAT | O_APPEND, S_IRUSR | S_IWUSR)
                if fd >= 0 { _ = data.withUnsafeBytes { write(fd, $0.baseAddress, data.count) }; _ = write(fd, "\n", 1); close(fd) }
            }
        }
        try frameWrite(listenerFD, sequence: outSequence, owner: ownerID, child: childID,
                       kind: kind, correlation: correlation, payload: payload,
                       protocolName: protocolName, version: version)
    }

    private func receive() throws -> (String, String, [String: Any]) {
        return try receive(timeoutMilliseconds: nil)
    }

    private func receive(timeoutMilliseconds: Int?) throws -> (String, String, [String: Any]) {
        let deadline = timeoutMilliseconds.map {
            ProcessInfo.processInfo.systemUptime + Double($0) / 1_000
        }
        let frame = try frameRead(listenerFD, expectedSequence: inSequence, owner: ownerID, child: childID,
                                  protocolName: protocolName, version: version, deadline: deadline)
        guard inSequence < maxSequence else { throw PhoneRemoteAuthorityError.invalidFrame }
        inSequence += 1
        let requestCorrelation = frame["correlation_id"] as! String
        if operation == "restore.prepare" && !restoreCorrelations.insert(requestCorrelation).inserted {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        correlation = requestCorrelation
        return (frame["kind"] as! String, requestCorrelation, frame["payload"] as! [String: Any])
    }

    private func error(_ code: String, correlation: String) {
        fputs("authority protocol stopped: \(code)\n", stderr)
        terminal = true
        terminalStatus = 30
        guard !terminalErrorSent else { return }
        terminalErrorSent = true
        try? send("owner.error", ["code": code], correlation: correlation)
    }

    func serve() -> Int32 {
        helloCorrelation = UUID().uuidString.lowercased()
        correlation = helloCorrelation
        do {
            let hello: [String: Any] = version == 4
                ? ["mode": "normal", "store_schema_version": anchor.version, "protected_anchor": anchor.wire]
                : ["max_frame_bytes": maxFrame]
            try send("owner.hello", hello, correlation: helloCorrelation)
            let ready = try receive()
            let expectedReady: [String: Any] = version == 4
                ? ["mode": "normal", "store_schema_version": anchor.version] : [:]
            guard ready.0 == "child.ready", ready.1 == helloCorrelation,
                  try JSONSerialization.data(withJSONObject: ready.2, options: [.sortedKeys])
                    == JSONSerialization.data(withJSONObject: expectedReady, options: [.sortedKeys]) else { error("phase_invalid", correlation: ready.1); return 23 }
            if !readyPath.isEmpty { try? Data("ready".utf8).write(to: URL(fileURLWithPath: readyPath), options: .atomic) }
            if holdMilliseconds > 0 { usleep(holdMilliseconds * 1000) }
            if expectedGrants == 0 { try shutdownChild(correlation: correlation) }
            while !terminal {
                let (kind, corr, p) = try receive()
                try handle(kind, corr, p)
            }
            return terminalStatus
        } catch let failure as PhoneRemoteAuthorityAnchorError {
            self.error(failure.protocolErrorCode, correlation: correlation)
            return 24
        } catch {
            // Preserve the established v1/v2/v3 behavior for malformed channel
            // frames: close with EOF rather than adding a new wire error.
            fputs("authority protocol stopped: invalid channel\n", stderr)
            terminalStatus = 31
            terminal = true
            return 24
        }
    }

    private func handle(_ kind: String, _ corr: String, _ p: [String: Any]) throws {
        switch kind {
        case "child.service.ready":
            guard version == 4, !serviceActivated, serviceReadyCorrelation == nil,
                  grant == nil, completedGrants == 1,
                  Set(p.keys) == ["host_id", "host_generation", "store_schema_version", "last_completed_restore"],
                  (p["host_id"] as? String)?.utf8.elementsEqual(anchor.host.utf8) == true,
                  exactInt(p["host_generation"]) == anchor.generation,
                  exactInt(p["store_schema_version"]) == anchor.version,
                  try readAuthorityAnchor() == anchor else { throw PhoneRemoteAuthorityError.invalidFrame }
            let expectedTombstone = anchor.lastCompletedRestore as Any? ?? NSNull()
            guard try JSONSerialization.data(withJSONObject: [p["last_completed_restore"]!], options: [.sortedKeys])
                    == JSONSerialization.data(withJSONObject: [expectedTombstone], options: [.sortedKeys]) else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            serviceReadyCorrelation = corr
            if version == 4 && ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-normal-lost-activate" {
                throw PhoneRemoteAuthorityError.unavailable
            }
            try send("owner.service.activate", activationPayload, correlation: corr)
        case "child.service.activated":
            guard version == 4, !serviceActivated, serviceReadyCorrelation == corr,
                  exactInt(p["host_generation"]) == anchor.generation,
                  exactInt(p["store_schema_version"]) == anchor.version,
                  try JSONSerialization.data(withJSONObject: p, options: [.sortedKeys])
                    == JSONSerialization.data(withJSONObject: activationPayload, options: [.sortedKeys]) else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            serviceActivated = true
            if expectedGrants == completedGrants { try shutdownChild(correlation: corr) }
        case "child.grant.acquire":
            guard Set(p.keys) == ["operation"], let op = p["operation"] as? String,
                  (["store.open", "store.read", "session.login", "session.signout", "authority.mutate", "ticket.issue", "ticket.consume"].contains(op)
                    || (version >= 2 && ["service.authorize", "service.commit"].contains(op))
                    || (version >= 3 && op == "session.challenge")
                    || (version == 3 && op == "restore.prepare"))
            else { error("phase_invalid", correlation: corr); return }
            guard version != 4 || serviceActivated || (op == "store.open" && completedGrants == 0) else {
                error("phase_invalid", correlation: corr); return
            }
            guard !normalDraining || op == "service.commit" else { error("phase_invalid", correlation: corr); return }
            if normalDraining && ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-drain-lost-commit" {
                throw PhoneRemoteAuthorityError.unavailable
            }
            guard grant == nil else { error("owner_busy", correlation: corr); return }
            guard anchor.transition == "stable", anchor == initialAnchor else { error("authority_unavailable", correlation: corr); return }
            if op == "restore.prepare" {
                guard corr != helloCorrelation, restoreCorrelations.insert(corr).inserted else {
                    error("correlation_invalid", correlation: corr); return
                }
            }
            grant = UUID().uuidString.lowercased(); operation = op; phase = "read"
            verifiedRead = false
            try send("owner.grant.acquired", ["grant_id": grant!, "operation": op], correlation: corr)
        case "child.anchor.read":
            guard Set(p.keys) == ["grant_id"], validGrant(p), phase == "read" || phase == "writeAdvance" || phase == "writeReadback" || phase == "stableReadback",
                  (anchor.transition == "stable" || phase != "read") else { error("phase_invalid", correlation: corr); return }
            guard try readAuthorityAnchor() == anchor else { error("anchor_corrupt", correlation: corr); return }
            if version >= 2 && (operation == "service.authorize" || operation == "service.commit") {
                guard phase == "read", !verifiedRead else { error("phase_invalid", correlation: corr); return }
                phase = "serviceRelease"
            }
            verifiedRead = true
            if phase == "writeReadback" {
                phase = operation == "restore.prepare" ? "restoreDatabasePending" : "writeAdvance"
            }
            if phase == "stableReadback" { phase = "release" }
            if version >= 3 && phase == "read" && operation == "session.login" { phase = "loginPreflight" }
            else if phase == "read" && (operation == "authority.mutate" || operation == "session.login") { phase = "writeAdvance" }
            if version >= 3 && phase == "read" && operation == "session.challenge" { phase = "challengeRelease" }
            if version == 3 && phase == "read" && operation == "restore.prepare" { phase = "restorePreflight" }
            try send("owner.anchor.state", ["grant_id": grant!, "state": anchor.projection], correlation: corr)
        case "child.anchor.advance":
            guard Set(p.keys) == ["grant_id", "step", "state"], validGrant(p),
                  (phase == "writeAdvance" || (version >= 3 && phase == "loginPreflight" && operation == "session.login")
                    || (version == 3 && phase == "restorePreflight" && operation == "restore.prepare")), let step = p["step"] as? String,
                  let object = p["state"] as? [String: Any], var next = try? Anchor(object) else {
                error("phase_invalid", correlation: corr); return
            }
            if version == 4 && anchor.version == 2 {
                guard next.version == 1 else { error("phase_invalid", correlation: corr); return }
                var protected = next.wire
                protected["anchor_version"] = 2
                protected["pending_restore"] = anchor.pendingRestore as Any? ?? NSNull()
                protected["last_completed_restore"] = anchor.lastCompletedRestore as Any? ?? NSNull()
                guard let merged = try? Anchor(protected) else { error("phase_invalid", correlation: corr); return }
                next = merged
            }
            guard isLegal(next, step: step) else { error("phase_invalid", correlation: corr); return }
            if phase == "loginPreflight" { phase = "writeAdvance" }
            if phase == "restorePreflight" { phase = "writeAdvance" }
            if step == "restore_pending" && operation == "restore.prepare" {
                // From this point, persistence may change even when the
                // acknowledgment fails. Retain the owner lock after reaping.
                restoreHoldRequired = true
            }
            let previousAnchor = anchor
            anchor = next
            try writeAuthorityAnchor(anchor, expecting: previousAnchor)
            if operation == "restore.prepare",
               ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] == "anchor-write-uncertain" {
                terminal = true; terminalStatus = 31
                throw PhoneRemoteAuthorityAnchorError.unavailable
            }
            guard try readAuthorityAnchor() == anchor else { error("anchor_corrupt", correlation: corr); return }
            phase = (step == "global_pending" || step == "login_pending" || step == "restore_pending")
                ? "writeReadback" : "stableReadback"
            try send("owner.anchor.verified", ["grant_id": grant!, "state": anchor.projection], correlation: corr)
        case "child.grant.release":
            guard Set(p.keys) == ["grant_id"], validGrant(p), verifiedRead,
                  ((phase == "read" && anchor.transition == "stable"
                    && ["store.open", "store.read", "session.signout", "ticket.issue", "ticket.consume"].contains(operation!))
                    || (version == 3 && phase == "restorePreflight" && operation == "restore.prepare"
                        && anchor.transition == "stable" && anchor == initialAnchor)
                    || phase == "release"
                    || (version >= 2 && phase == "serviceRelease"
                        && ["service.authorize", "service.commit"].contains(operation!))
                    || (version >= 3 && phase == "challengeRelease" && operation == "session.challenge")) else {
                error("phase_invalid", correlation: corr); return
            }
            let id = grant!; let completedOperation = operation!
            grant = nil; operation = nil; phase = "idle"; verifiedRead = false; initialAnchor = anchor
            pauseBeforeTestReleaseAck(operation: completedOperation, occurrence: completedGrants + 1)
            if version == 4 && completedOperation == "store.open" &&
                ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-normal-lost-open-ack" {
                throw PhoneRemoteAuthorityError.unavailable
            }
            if normalDraining && ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-drain-lost-release" {
                throw PhoneRemoteAuthorityError.unavailable
            }
            try send("owner.grant.released", ["grant_id": id], correlation: corr)
            completedGrants += 1
            if expectedGrants > 0 && completedGrants == expectedGrants && (version != 4 || serviceActivated) { try shutdownChild(correlation: corr) }
        case "child.restore.database_pending":
            let operationID = p["operation_id"] as? String
            guard version == 3, Set(p.keys) == ["grant_id", "operation_id"],
                  validGrant(p), operation == "restore.prepare", phase == "restoreDatabasePending",
                  anchor.transition == "pending", operationID == anchor.transitionID,
                  let operationID, UUID(uuidString: operationID)?.uuidString.lowercased() == operationID,
                  restoreCorrelations.contains(corr) else {
                error("phase_invalid", correlation: corr); return
            }
            phase = "restoreFenced"
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] == "database-pending-received" {
                error("phase_invalid", correlation: corr); return
            }
        case "child.restore.fenced":
            let operationID = p["operation_id"] as? String
            guard version == 3, Set(p.keys) == ["grant_id", "operation_id"], validGrant(p),
                  operation == "restore.prepare", phase == "restoreFenced",
                  anchor.transition == "pending", operationID == anchor.transitionID,
                  let operationID, UUID(uuidString: operationID)?.uuidString.lowercased() == operationID,
                  restoreCorrelations.contains(corr) else {
                error("phase_invalid", correlation: corr); return
            }
            let id = grant!
            grant = nil; operation = nil; phase = "restoreShutdown"; verifiedRead = false
            restorePrepared = true
            let preparedGeneration = ProcessInfo.processInfo.environment[
                "PHONE_REMOTE_AUTHORITY_TEST_BAD_RESTORE_PREPARED_ACK"] == "1"
                ? anchor.generation + 1 : anchor.generation
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] == "grant-retirement" {
                error("phase_invalid", correlation: corr); return
            }
            try send("owner.restore.prepared", ["grant_id": id,
                "operation_id": operationID, "host_generation": preparedGeneration,
                "transition_state": "pending"], correlation: corr)
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] == "prepared-delivery" {
                error("phase_invalid", correlation: corr); return
            }
            let shutdownCorrelation = UUID().uuidString.lowercased()
            guard shutdownCorrelation != corr else { error("correlation_invalid", correlation: corr); return }
            try shutdownChild(correlation: shutdownCorrelation)
        case "child.grant.reject":
            guard version >= 3, Set(p.keys) == ["grant_id", "operation", "code"], validGrant(p),
                  p["operation"] as? String == "session.login",
                  p["code"] as? String == "not_authorized",
                  operation == "session.login", phase == "loginPreflight", verifiedRead,
                  anchor.transition == "stable" else {
                error("phase_invalid", correlation: corr); return
            }
            let id = grant!
            grant = nil; operation = nil; phase = "idle"; verifiedRead = false; initialAnchor = anchor
            completedGrants += 1
            pauseBeforeTestRejectAck(occurrence: completedGrants)
            try send("owner.grant.rejected", ["grant_id": id, "operation": "session.login",
                       "code": "not_authorized"], correlation: corr)
            if expectedGrants > 0 && completedGrants == expectedGrants && (version != 4 || serviceActivated) { try shutdownChild(correlation: corr) }
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

    private var activationPayload: [String: Any] {
        ["host_id": anchor.host, "host_generation": anchor.generation,
         "store_schema_version": anchor.version,
         "operation_id": anchor.lastCompletedRestore?["operation_id"] as Any? ?? NSNull()]
    }

    private func pauseBeforeTestReleaseAck(operation: String, occurrence: Int) {
        let target = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE"]
        guard target == operation,
              (ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE"] == nil
                || Int(ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_RELEASE_OCCURRENCE"]!) == occurrence),
              let entered = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_ENTERED_FILE"],
              let release = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RELEASE_FILE"] else { return }
        try? Data("before-ack".utf8).write(to: URL(fileURLWithPath: entered), options: .atomic)
        while !FileManager.default.fileExists(atPath: release) { usleep(5_000) }
    }

    private func pauseBeforeTestRejectAck(occurrence: Int) {
        guard ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_ACK"] == "1",
              (ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_OCCURRENCE"] == nil
                || Int(ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_PAUSE_REJECT_OCCURRENCE"]!) == occurrence),
              let entered = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_REJECT_ENTERED_FILE"],
              let release = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_REJECT_RELEASE_FILE"] else { return }
        try? Data("before-reject-ack".utf8).write(to: URL(fileURLWithPath: entered), options: .atomic)
        while !FileManager.default.fileExists(atPath: release) { usleep(5_000) }
    }

    private func shutdownChild(correlation: String) throws {
        if restorePrepared && restoreCorrelations.contains(correlation) {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        if version == 4 {
            let operation = UUID().uuidString.lowercased()
            let request = UUID().uuidString.lowercased()
            try send("owner.shutdown", ["operation_id": operation, "reason": "restore_quiesce"], correlation: request)
            let (kind, corr, payload) = try receive(timeoutMilliseconds: 5_000)
            guard kind == "child.shutdown_ack", corr == request,
                  Set(payload.keys) == ["operation_id", "drained"],
                  payload["operation_id"] as? String == operation,
                  let drained = payload["drained"] as? NSNumber,
                  CFGetTypeID(drained) == CFBooleanGetTypeID(), drained.boolValue, grant == nil else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            terminal = true
            return
        }
        try send("owner.shutdown", ["reason": "requested"], correlation: correlation)
        let timeout: Int? = restorePrepared
            ? testDuration("PHONE_REMOTE_AUTHORITY_TEST_RESTORE_SHUTDOWN_TIMEOUT_MS", fallback: 5_000)
            : nil
        let (kind, corr, payload) = try receive(timeoutMilliseconds: timeout)
        guard kind == "child.shutdown_ack", corr == correlation, payload.isEmpty, grant == nil,
              (!restorePrepared || phase == "restoreShutdown") else {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        terminal = true
    }

    private func testDuration(_ key: String, fallback: Int) -> Int {
        guard let raw = ProcessInfo.processInfo.environment[key],
              let value = Int(raw), (1...30_000).contains(value) else { return fallback }
        return value
    }

    private func validGrant(_ p: [String: Any]) -> Bool {
        p["grant_id"] as? String == grant && grant != nil
    }

    private func readAuthorityAnchor() throws -> Anchor {
        if restoreHoldRequired,
           ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_RESTORE_FAIL_PHASE"] == "anchor-readback-uncertain" {
            terminal = true
            terminalStatus = 31
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
        do { return try anchorSession.read() }
        catch {
            terminal = true
            terminalStatus = 31
            if let typed = error as? PhoneRemoteAuthorityAnchorError { throw typed }
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
    }

    private func writeAuthorityAnchor(_ value: Anchor, expecting previous: Anchor) throws {
        do { try anchorSession.write(value, expecting: previous) }
        catch {
            terminal = true
            terminalStatus = 31
            if let typed = error as? PhoneRemoteAuthorityAnchorError { throw typed }
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
    }

    private func isLegal(_ n: Anchor, step: String) -> Bool {
        guard let op = operation else { return false }
        if version == 4 && anchor.version == 2
            && (!n.preservesRestoreMetadata(from: anchor) || n.version != 2) { return false }
        if (phase == "writeAdvance" || (version >= 3 && phase == "loginPreflight" && op == "session.login")
            || (version == 3 && phase == "restorePreflight" && op == "restore.prepare"))
            && anchor.transition == "stable" {
            guard n.version == anchor.version, n.host.utf8.elementsEqual(anchor.host.utf8), n.transition == "pending", n.transitionID != nil else { return false }
            if step == "restore_pending" && op == "restore.prepare" {
                guard let operationID = n.transitionID,
                      UUID(uuidString: operationID)?.uuidString.lowercased() == operationID else { return false }
                return anchor.generation < maxSequence && n.generation == anchor.generation + 1
                    && n.login == anchor.login
            }
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

// Offline owner storage. No production path or Keychain construction is provided.
private enum RecoveryStorage {
    static func json(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    static func isDigest(_ value: Any?) -> Bool {
        guard let text = value as? String, text.utf8.count == 64 else { return false }
        return text.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    static func file(_ path: String, allowEmpty: Bool = false) throws -> Data {
        let fd = open(path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw PhoneRemoteAuthorityError.unavailable }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, st.st_mode & S_IFMT == S_IFREG, st.st_uid == geteuid(),
              st.st_nlink == 1, st.st_mode & 0o077 == 0, (st.st_size > 0 || allowEmpty && st.st_size == 0), st.st_size <= 1 << 30 else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        var data = Data(count: Int(st.st_size))
        try data.withUnsafeMutableBytes { raw in
            var offset = 0
            while offset < raw.count {
                let count = Darwin.read(fd, raw.baseAddress!.advanced(by: offset), raw.count - offset)
                if count < 0 && errno == EINTR { continue }
                guard count > 0 else { throw PhoneRemoteAuthorityError.unavailable }
                offset += count
            }
        }
        return data
    }
    static func sync(_ path: String) throws {
        let fd = open(path, O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { throw PhoneRemoteAuthorityError.unavailable }
        defer { close(fd) }
        guard fsync(fd) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
    }
    static func directory(_ path: String) throws {
        if mkdir(path, 0o700) != 0 && errno != EEXIST { throw PhoneRemoteAuthorityError.unavailable }
        var st = stat()
        guard lstat(path, &st) == 0, st.st_mode & S_IFMT == S_IFDIR,
              st.st_uid == geteuid(), st.st_mode & 0o077 == 0 else { throw PhoneRemoteAuthorityError.unavailable }
        try sync(path); try sync(URL(fileURLWithPath: path).deletingLastPathComponent().path)
    }
    static func writeNew(_ value: Any, _ path: String) throws {
        let bytes = try json(value)
        let fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw PhoneRemoteAuthorityError.unavailable }
        defer { close(fd) }
        try bytes.withUnsafeBytes { raw in
            var offset = 0
            while offset < raw.count {
                let count = Darwin.write(fd, raw.baseAddress!.advanced(by: offset), raw.count - offset)
                if count < 0 && errno == EINTR { continue }
                guard count > 0 else { throw PhoneRemoteAuthorityError.unavailable }
                offset += count
            }
        }
        guard fsync(fd) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
        try sync(URL(fileURLWithPath: path).deletingLastPathComponent().path)
    }
    static func object(_ path: String, max: Int = 65_536) throws -> [String: Any] {
        let bytes = try file(path)
        var scanner = DuplicateKeyScanner(bytes: Array(bytes))
        guard bytes.count <= max, scanner.hasNoDuplicateKeys(),
              let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              try json(object) == bytes else { throw PhoneRemoteAuthorityError.invalidFrame }
        return object
    }
    static func withDB<T>(_ path: String, writable: Bool = false, _ body: (OpaquePointer) throws -> T) throws -> T {
        // Check before SQLite can follow or modify a caller-swapped path; the
        // offline owner only opens existing private single-link regular files.
        var before = stat()
        guard lstat(path, &before) == 0, before.st_mode & S_IFMT == S_IFREG,
              before.st_uid == geteuid(), before.st_mode & 0o077 == 0,
              before.st_nlink == 1, before.st_size <= 1 << 30 else { throw PhoneRemoteAuthorityError.unavailable }
        var parent = stat()
        let parentURL = URL(fileURLWithPath: path).deletingLastPathComponent()
        guard lstat(parentURL.path, &parent) == 0, parent.st_mode & S_IFMT == S_IFDIR,
              parent.st_uid == geteuid(), parent.st_mode & 0o077 == 0 else { throw PhoneRemoteAuthorityError.unavailable }
        // macOS /var and /tmp are system aliases. Resolve the checked directory,
        // while retaining NOFOLLOW on the final database component.
        guard let physicalParent = realpath(parentURL.path, nil) else { throw PhoneRemoteAuthorityError.unavailable }
        let sqlitePath = String(cString: physicalParent) + "/" + URL(fileURLWithPath: path).lastPathComponent
        free(physicalParent)
        var db: OpaquePointer?
        let flags = (writable ? SQLITE_OPEN_READWRITE : SQLITE_OPEN_READONLY) | SQLITE_OPEN_NOFOLLOW
        guard sqlite3_open_v2(sqlitePath, &db, flags, nil) == SQLITE_OK,
              let handle = db else { if let db { sqlite3_close(db) }; throw PhoneRemoteAuthorityError.unavailable }
        defer { sqlite3_close(handle) }
        var after = stat()
        guard lstat(path, &after) == 0, before.st_dev == after.st_dev, before.st_ino == after.st_ino else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        return try body(handle)
    }
    static func rows(_ db: OpaquePointer, _ sql: String) throws -> [[Any]] {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK, let statement else {
            throw PhoneRemoteAuthorityError.unavailable
        }
        defer { sqlite3_finalize(statement) }
        var result = [[Any]]()
        while true {
            let rc = sqlite3_step(statement)
            if rc == SQLITE_DONE { return result }
            guard rc == SQLITE_ROW else { throw PhoneRemoteAuthorityError.unavailable }
            var row = [Any]()
            for i in 0..<sqlite3_column_count(statement) {
                switch sqlite3_column_type(statement, i) {
                case SQLITE_NULL: row.append(NSNull())
                case SQLITE_INTEGER: row.append(sqlite3_column_int64(statement, i))
                case SQLITE_FLOAT: row.append(sqlite3_column_double(statement, i))
                case SQLITE_BLOB:
                    let count = Int(sqlite3_column_bytes(statement, i))
                    row.append(count == 0 ? Data() : Data(bytes: sqlite3_column_blob(statement, i)!, count: count))
                default:
                    guard let bytes = sqlite3_column_text(statement, i),
                          let string = String(data: Data(bytes: bytes, count: Int(sqlite3_column_bytes(statement, i))), encoding: .utf8) else {
                        throw PhoneRemoteAuthorityError.invalidFrame
                    }
                    row.append(string)
                }
            }
            result.append(row)
        }
    }
    static func u32(_ value: Int) -> Data { var v = UInt32(value).bigEndian; return Data(bytes: &v, count: 4) }
    static func u64(_ value: UInt64) -> Data { var v = value.bigEndian; return Data(bytes: &v, count: 8) }
    static func field(_ value: Data) -> Data { u32(value.count) + value }
    static func catalog(_ path: String) throws {
        try withDB(path) { db in
            guard try rows(db, "PRAGMA quick_check").first?.first as? String == "ok",
                  try rows(db, "PRAGMA foreign_key_check").isEmpty else { throw PhoneRemoteAuthorityError.unavailable }
            let inventory = try rows(db, "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type COLLATE BINARY,name COLLATE BINARY,tbl_name COLLATE BINARY")
            var bytes = Data("MortimerSQLiteSchemaCatalog\0v1\0".utf8) + u32(inventory.count)
            for row in inventory { for item in row {
                if item is NSNull { bytes.append(0) }
                else if let text = item as? String { bytes.append(1); bytes += field(Data(text.utf8)) }
                else { throw PhoneRemoteAuthorityError.invalidFrame }
            }}
            let pins = ["8c73ec0152e72d644db5db6f4d06fda80805b654a3feb8423bcd0402bb974bc0",
                        "1cd36fb698d791412fbe298df7814812ffaa1cfa1bda9078c228c550940d165b",
                        "0977aa20b4b4e0c13d3cb70c90e3837215b421f33783aba06be6d74c06f66e27"]
            guard pins.contains(hash(bytes)) else { throw PhoneRemoteAuthorityError.invalidFrame }
            let expected = "0001_init 0002_actions 0003_memory 0004_observations 0005_conversation_search 0006_agent_runs 0007_procedures 0008_tool_outcomes 0009_council 0010_council_v2 0011_run_model 0012_memory_tiers 0013_memory_archive 0014_council_attempted 0015_memory_reviews 0016_memory_extraction_v2 0017_memory_extraction_pending 0018_council_retry_outcome 0019_memory_recall_events 0020_user_id 0021_reminders_notified 0022_memory_automation 0023_memory_classification_shadow 0024_model_route_preferences 0025_notices 0026_expire_retired_actions 0027_notice_memory_review 0028_memory_admission_jobs 0029_memory_classification_budget 0030_memory_admission_shadow 0031_agent_event_tool_call_identity 0032_execution_action_claims 0033_skill_events 0034_client_tokens 0036_skill_step_check_receipts".split(separator: " ").map(String.init)
            guard try rows(db, "SELECT id FROM migrations ORDER BY rowid").compactMap({ $0.first as? String }) == expected else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
        }
    }
    static func authority(_ path: String) throws -> String {
        try withDB(path) { db in
            let devices = try rows(db, "SELECT device_id,owner_id,public_key,key_algorithm,revoked_at FROM phone_remote_devices ORDER BY device_id COLLATE BINARY")
            let grants = try rows(db, "SELECT grant_id,device_id,owner_id,scopes_json,grant_generation,revoked_at FROM phone_remote_grants ORDER BY grant_id COLLATE BINARY")
            var bytes = Data("MortimerPhoneAuthorityCheckpoint\0v1\0".utf8) + u32(devices.count)
            func text(_ item: Any) throws -> Data {
                guard let text = item as? String else { throw PhoneRemoteAuthorityError.invalidFrame }
                return field(Data(text.utf8))
            }
            func revoked(_ item: Any) throws -> Data {
                if item is NSNull { return Data([0]) }
                guard let number = item as? NSNumber, number.doubleValue.isFinite, number.doubleValue >= 0 else {
                    throw PhoneRemoteAuthorityError.invalidFrame
                }
                return Data([1]) + u64(number.doubleValue.bitPattern)
            }
            for row in devices {
                guard let key = row[2] as? Data, !key.isEmpty else { throw PhoneRemoteAuthorityError.invalidFrame }
                bytes.append(1); bytes += try text(row[0]); bytes += try text(row[1]); bytes += field(key)
                bytes += try text(row[3]); bytes += try revoked(row[4])
            }
            bytes += u32(grants.count)
            for row in grants {
                guard let scopeJSON = row[3] as? String,
                      let scopes = try JSONSerialization.jsonObject(with: Data(scopeJSON.utf8)) as? [String],
                      Set(scopes).count == scopes.count, Set(scopes).isSubset(of: ["read", "voice", "action", "calls"]),
                      let generation = exactInt(row[4]), generation <= UInt64(Int64.max) else {
                    throw PhoneRemoteAuthorityError.invalidFrame
                }
                bytes.append(2); bytes += try text(row[0]); bytes += try text(row[1]); bytes += try text(row[2])
                bytes += field(try json(scopes.sorted())); bytes += u64(generation); bytes += try revoked(row[5])
            }
            return hash(bytes)
        }
    }
    static func stablePair(_ path: String, _ anchor: Anchor, manifestBase: String? = nil) throws {
        guard anchor.transition == "stable", anchor.pendingRestore == nil else { throw PhoneRemoteAuthorityError.unavailable }
        try withDB(path) { db in
            let meta = try rows(db, "SELECT schema_version,host_id,host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1")
            guard meta.count == 1, exactInt(meta[0][0]) == anchor.version,
                  (meta[0][1] as? String)?.utf8.elementsEqual(anchor.host.utf8) == true,
                  exactInt(meta[0][2]) == anchor.generation, meta[0][3] is NSNull,
                  meta[0][4] as? String == "stable" else { throw PhoneRemoteAuthorityError.unavailable }
            if let tombstone = anchor.lastCompletedRestore {
                let root = (manifestBase ?? URL(fileURLWithPath: path).deletingLastPathComponent().path) + "/.phone-restore/" + (tombstone["operation_id"] as! String)
                let manifest = try object(root + "/manifest.json", max: 16_384)
                guard try hash(file(root + "/manifest.json")) == tombstone["manifest_sha256"] as? String,
                      manifest["host_id"] as? String == anchor.host,
                      manifest["operation_id"] as? String == tombstone["operation_id"] as? String,
                      manifest["checkpoint_sha256"] as? String == tombstone["checkpoint_sha256"] as? String,
                      exactInt(manifest["target_generation"]) == exactInt(tombstone["target_generation"]) else {
                    throw PhoneRemoteAuthorityError.invalidFrame
                }
                let receipt = try rows(db, "SELECT operation_id,host_id,target_generation,manifest_sha256,checkpoint_sha256,authority_sha256,receipt_version FROM phone_remote_restore_receipt WHERE singleton_id=1")
                let expected: [Any] = [tombstone["operation_id"]!, anchor.host, tombstone["target_generation"]!, tombstone["manifest_sha256"]!, tombstone["checkpoint_sha256"]!, manifest["authority_sha256"]!, 1]
                guard receipt.count == 1, try json(receipt[0]) == json(expected) else { throw PhoneRemoteAuthorityError.invalidFrame }
            }
        }
    }
    static func prepare(_ path: String, source: String, operation: String, anchor: Anchor) throws -> [String: Any] {
        try catalog(source); try catalog(path); try stablePair(path, anchor)
        let baseRoot = URL(fileURLWithPath: path).deletingLastPathComponent().path
        try directory(baseRoot + "/.phone-restore")
        let root = baseRoot + "/.phone-restore/" + operation
        try directory(root)
        try withDB(path, writable: true) { db in
            let result = try rows(db, "PRAGMA wal_checkpoint(TRUNCATE)")
            guard (result.first?.first as? Int64) == 0,
                  try rows(db, "PRAGMA journal_mode=DELETE").first?.first as? String == "delete" else { throw PhoneRemoteAuthorityError.unavailable }
        }
        guard !FileManager.default.fileExists(atPath: path + "-wal"), !FileManager.default.fileExists(atPath: path + "-shm") else { throw PhoneRemoteAuthorityError.unavailable }
        try sync(path); try sync(baseRoot)
        let base = try file(path), checkpointPath = root + "/checkpoint.db"
        let cpFD = open(checkpointPath, O_CREAT | O_EXCL | O_RDWR | O_NOFOLLOW, 0o600)
        guard cpFD >= 0 else { throw PhoneRemoteAuthorityError.unavailable }; close(cpFD)
        try withDB(path) { sourceDB in
            try withDB(checkpointPath, writable: true) { targetDB in
                guard let backup = sqlite3_backup_init(targetDB, "main", sourceDB, "main") else { throw PhoneRemoteAuthorityError.unavailable }
                let rc = sqlite3_backup_step(backup, -1), finish = sqlite3_backup_finish(backup)
                guard rc == SQLITE_DONE, finish == SQLITE_OK else { throw PhoneRemoteAuthorityError.unavailable }
                _ = try rows(targetDB, "PRAGMA journal_mode=DELETE")
            }
        }
        try sync(checkpointPath); try sync(root); try stablePair(checkpointPath, anchor, manifestBase: baseRoot)
        let checkpoint = try file(checkpointPath), sourceBytes = try file(source)
        let authorityHash = try authority(checkpointPath)
        guard try authority(path) == authorityHash, anchor.generation < UInt64(Int64.max) else { throw PhoneRemoteAuthorityError.unavailable }
        let manifest: [String: Any] = ["manifest_version": 1, "operation_id": operation, "host_id": anchor.host,
            "base_generation": anchor.generation, "target_generation": anchor.generation + 1,
            "source_id": "00000000-0000-4000-8000-000000000001", "source_schema_version": 1, "source_size_bytes": sourceBytes.count,
            "source_sha256": hash(sourceBytes), "checkpoint_size_bytes": checkpoint.count,
            "checkpoint_sha256": hash(checkpoint), "authority_sha256": authorityHash, "base_database_sha256": hash(base)]
        try writeNew(manifest, root + "/manifest.json")
        let absent: [String: Any] = ["present": false, "size_bytes": 0, "sha256": NSNull()]
        var cleanup = [String: Any]()
        for name in ["checkpoint", "staged_database", "old_database", "old_wal", "old_shm"] {
            cleanup[name] = ["state": name == "checkpoint" ? "pending" : "absent", "sha256": name == "checkpoint" ? hash(checkpoint) as Any : NSNull()]
        }
        let journal: [String: Any] = ["journal_version": 1, "operation_id": operation,
            "manifest_sha256": hash(try json(manifest)), "phase": "checkpoint_bound", "rename_step": NSNull(),
            "files": ["database": ["present": true, "size_bytes": base.count, "sha256": hash(base)], "wal": absent, "shm": absent],
            "staged_database_sha256": NSNull(), "installed_database_sha256": NSNull(), "final_database_sha256": NSNull(), "cleanup_artifacts": cleanup]
        try writeNew(journal, root + "/journal.json")
        return manifest
    }
}

extension PhoneRemoteAuthorityOwner {
    /// Explicit synthetic controller capability: reachable only through --test-owner.
    /// Paths are fixed by the owned fixture, never read from a phone request.
    private static func runOfflineRecovery(lockFD: Int32, python: String, database: String,
                                          workingDirectory: String, anchorPath: String, readyPath: String) throws -> Int32 {
        let backend = FilePhoneRemoteAuthorityAnchor(path: anchorPath)
        var protected = try backend.read()
        let baseRoot = URL(fileURLWithPath: database).deletingLastPathComponent().path
        let source = baseRoot + "/source.db"
        guard URL(fileURLWithPath: database).lastPathComponent == "jarvis.db" else { throw PhoneRemoteAuthorityError.invalidFrame }
        if protected.version == 1 && protected.transition == "pending" {
            let transition = protected.wire["transition_id"] as? String ?? ""
            let canonical = UUID(uuidString: transition)?.uuidString.lowercased() == transition
            let rows = try? RecoveryStorage.withDB(database) {
                try RecoveryStorage.rows($0, "SELECT schema_version,host_id,host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1")
            }
            let expected: [Any] = [1, protected.host, protected.generation, transition, "pending"]
            let matches = rows?.count == 1 && (try? RecoveryStorage.json(rows![0])) == (try? RecoveryStorage.json(expected))
            let code = canonical && matches ? "legacy_pending_unbound" : "transaction_mismatch"
            try RecoveryStorage.writeNew(["status": "blocked", "code": code], baseRoot + "/blocked")
            while true { sleep(1) }  // no source, migration, or child may enter this hold
        }
        let priorCompletedOperation = protected.lastCompletedRestore?["operation_id"] as? String
        let sourceFD = open(source, O_RDONLY | O_NOFOLLOW)
        // Completed retries and finalization need only retained evidence, not
        // the old backup object. Missing source is checked before fresh staging.
        defer { if sourceFD >= 0 { close(sourceFD) } }
        let incarnation = UUID().uuidString.lowercased()
        var owned: PhoneRemoteAuthorityOwner?
        var recoveryHeld = protected.transition == "pending" || protected.lastCompletedRestore != nil
        func reap(_ child: PhoneRemoteAuthorityOwner, success: Bool) throws {
            _ = Darwin.shutdown(child.listenerFD, SHUT_RDWR); close(child.listenerFD)
            var status: Int32 = 0
            var signal = "none", termWait = 0.0, killWait = 0.0
            var waited = waitForChild(child.childPID, status: &status, milliseconds: success ? 250 : 0)
            // ECHILD or any unknown wait state is not authority to signal a
            // potentially reused PID. Keep the lock and never launch a peer.
            if waited == -2 { while true { sleep(1) } }
            if waited != child.childPID {
                signal = "TERM"
                _ = kill(child.childPID, SIGTERM)
                let start = ProcessInfo.processInfo.systemUptime
                waited = waitForChild(child.childPID, status: &status, milliseconds: 250)
                termWait = ProcessInfo.processInfo.systemUptime - start
            }
            if waited == -2 { while true { sleep(1) } }
            if waited != child.childPID {
                signal = "KILL"
                _ = kill(child.childPID, SIGKILL)
                let start = ProcessInfo.processInfo.systemUptime
                waited = waitForChild(child.childPID, status: &status, milliseconds: 2000)
                killWait = ProcessInfo.processInfo.systemUptime - start
            }
            guard waited == child.childPID else { while true { sleep(1) } }
            try RecoveryStorage.writeNew(["pid": child.childPID, "signal": signal, "confirmed": true,
                "term_wait_ms": termWait * 1000, "kill_wait_ms": killWait * 1000],
                baseRoot + "/reaped-" + child.childID + ".json")
            owned = nil
            if success && status != 0 { throw PhoneRemoteAuthorityError.unavailable }
        }
        func launch(_ mode: String, manifest: [String: Any]? = nil) throws -> PhoneRemoteAuthorityOwner {
            guard owned == nil else { throw PhoneRemoteAuthorityError.unavailable }
            var sockets: [Int32] = [0, 0]
            guard socketpair(AF_UNIX, SOCK_STREAM, 0, &sockets) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
            var noSigPipe: Int32 = 1
            _ = setsockopt(sockets[0], SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))
            var config: [String: Any] = ["mode": mode, "protected_anchor": protected.wire,
                "source_available": sourceFD >= 0 && mode != "normal"]
            let quiescencePath = baseRoot + "/quiesce-" + UUID().uuidString.lowercased()
            let exerciseDrain = mode == "normal" && protected.version == 1 &&
                (ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"]?.hasPrefix("r324-drain-") == true)
            let exerciseProof = mode == "normal" && protected.version == 2 &&
                ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-normal-proof"
            if mode == "normal" {
                config["exercise_proof"] = exerciseProof
                config["quiescence_path"] = quiescencePath
                config["exercise_drain"] = exerciseDrain
            }
            if let manifest { config["manifest"] = manifest }
            let pid: pid_t
            do {
                pid = try spawnChild(python: python, database: database, workingDirectory: workingDirectory,
                    scenario: "v4-recovery", socketFD: sockets[1], lockFD: lockFD,
                    recoveryConfig: config, sourceFD: mode == "normal" || sourceFD < 0 ? nil : sourceFD)
            } catch { close(sockets[0]); close(sockets[1]); throw error }
            close(sockets[1])
            let child = PhoneRemoteAuthorityOwner(lockFD: lockFD, listenerFD: sockets[0], childPID: pid,
                ownerID: incarnation, childID: UUID().uuidString.lowercased(), anchor: protected,
                expectedGrants: 0, holdMilliseconds: 0, readyPath: "", anchorBackend: backend, version: 4)
            owned = child
            if mode == "normal" {
                child.offlineQuiescencePath = quiescencePath
                try RecoveryStorage.writeNew(["pid": pid, "child_incarnation": child.childID], quiescencePath + ".pid")
            }

            let hello: [String: Any]
            var ready: [String: Any]
            if let manifest {
                hello = ["mode": mode, "operation_id": manifest["operation_id"]!, "host_id": protected.host,
                         "target_generation": manifest["target_generation"]!, "manifest_sha256": RecoveryStorage.hash(try RecoveryStorage.json(manifest))]
                ready = hello; ready["maximum_store_schema_version"] = 2
            } else {
                hello = ["mode": "normal", "store_schema_version": protected.version, "protected_anchor": protected.wire]
                ready = ["mode": "normal", "store_schema_version": protected.version]
            }
            let correlation = UUID().uuidString.lowercased()
            try child.send("owner.hello", hello, correlation: correlation)
            let response = try child.receive(timeoutMilliseconds: 5000)

            guard response.0 == "child.ready", response.1 == correlation,
                  exactInt(response.2[manifest == nil ? "store_schema_version" : "maximum_store_schema_version"]) == (manifest == nil ? protected.version : 2),
                  (manifest == nil || exactInt(response.2["target_generation"]) == exactInt(manifest?["target_generation"])),
                  try RecoveryStorage.json(response.2) == RecoveryStorage.json(ready) else { throw PhoneRemoteAuthorityError.invalidFrame }
            if mode == "normal" {
                try RecoveryStorage.stablePair(database, protected)

                while !child.serviceActivated {
                    let frame = try child.receive(timeoutMilliseconds: 5000)

                    try child.handle(frame.0, frame.1, frame.2)
                    guard !child.terminal else { throw PhoneRemoteAuthorityError.unavailable }
                }
                if exerciseDrain || exerciseProof {
                    let deadline = ProcessInfo.processInfo.systemUptime + 5
                    while !FileManager.default.fileExists(atPath: quiescencePath + ".activity") {
                        guard ProcessInfo.processInfo.systemUptime < deadline else { throw PhoneRemoteAuthorityError.unavailable }
                        var poller = pollfd(fd: child.listenerFD, events: Int16(POLLIN), revents: 0)
                        if poll(&poller, 1, 10) > 0 {
                            let frame = try child.receive(timeoutMilliseconds: max(1, Int((deadline - ProcessInfo.processInfo.systemUptime) * 1000)))
                            try child.handle(frame.0, frame.1, frame.2)
                            guard !child.terminal else { throw PhoneRemoteAuthorityError.unavailable }
                        }
                    }
                    protected = try backend.read()
                }
            }
            return child
        }
        func exchange(_ child: PhoneRemoteAuthorityOwner, _ kind: String, _ payload: [String: Any],
                      _ reply: String) throws -> [String: Any] {
            let correlation = UUID().uuidString.lowercased()
            try child.send(kind, payload, correlation: correlation)
            let response = try child.receive(timeoutMilliseconds: 5000)
            guard response.0 == reply, response.1 == correlation else { throw PhoneRemoteAuthorityError.invalidFrame }
            return response.2
        }
        func stop(_ child: PhoneRemoteAuthorityOwner, operation: String, reason: String) throws {
            var deadline: Double?
            if reason == "restore_quiesce", let path = child.offlineQuiescencePath {
                let end = ProcessInfo.processInfo.systemUptime + 5
                deadline = end
                child.normalDraining = true
                // This file is the injected local controller capability used by
                // the offline harness, never a phone or production endpoint.
                try RecoveryStorage.writeNew(["operation_id": operation, "deadline": end], path + ".request")
                while !FileManager.default.fileExists(atPath: path + ".terminal") {
                    guard ProcessInfo.processInfo.systemUptime < end else { throw PhoneRemoteAuthorityError.unavailable }
                    var poller = pollfd(fd: child.listenerFD, events: Int16(POLLIN), revents: 0)
                    if poll(&poller, 1, 10) > 0 {
                        let frame = try child.receive(timeoutMilliseconds: max(1, Int((end - ProcessInfo.processInfo.systemUptime) * 1000)))
                        try child.handle(frame.0, frame.1, frame.2)
                        guard !child.terminal else { throw PhoneRemoteAuthorityError.unavailable }
                    }
                }
                let terminal: [String: Any] = ["operation_id": operation, "terminal": true]
                guard child.grant == nil, try RecoveryStorage.json(RecoveryStorage.object(path + ".terminal")) == RecoveryStorage.json(terminal) else {
                    throw PhoneRemoteAuthorityError.invalidFrame
                }
            }
            let correlation = UUID().uuidString.lowercased()
            try child.send("owner.shutdown", ["operation_id": operation, "reason": reason], correlation: correlation)
            let timeout = deadline.map { max(1, Int(($0 - ProcessInfo.processInfo.systemUptime) * 1000)) } ?? 5000
            guard deadline == nil || ProcessInfo.processInfo.systemUptime < deadline! else { throw PhoneRemoteAuthorityError.unavailable }
            let response = try child.receive(timeoutMilliseconds: timeout)
            guard response.0 == "child.shutdown_ack", response.1 == correlation else { throw PhoneRemoteAuthorityError.invalidFrame }
            let result = response.2
            let expected: [String: Any] = reason == "restore_quiesce" ? ["operation_id": operation, "drained": true] : ["operation_id": operation]
            guard try RecoveryStorage.json(result) == RecoveryStorage.json(expected) else { throw PhoneRemoteAuthorityError.invalidFrame }
            try reap(child, success: true)
        }
        var requestedBegin = ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_RECOVERY_BEGIN"] == "1"
        recoveryAttempts: while true {
        do {
            let manifest: [String: Any]
            let operation: String
            var preparedWitnesses = [[String: Any]]()
            if protected.transition == "stable" && (protected.lastCompletedRestore == nil || requestedBegin) {
                requestedBegin = false
                // Caller/source policy preflight precedes the admission fence.
                try RecoveryStorage.catalog(source)

                _ = try RecoveryStorage.file(source)
                let normal = try launch("normal")

                operation = UUID().uuidString.lowercased()
                guard operation != protected.lastCompletedRestore?["operation_id"] as? String else {
                    throw PhoneRemoteAuthorityError.unavailable
                }
                // Close admission and drain the exact authorized continuation
                // before terminal shutdown acknowledges this fresh operation.
                recoveryHeld = true
                try stop(normal, operation: operation, reason: "restore_quiesce")
                guard try backend.read() == protected else { throw PhoneRemoteAuthorityError.unavailable }
                manifest = try RecoveryStorage.prepare(database, source: source, operation: operation, anchor: protected)
                let child = try launch("prepare", manifest: manifest)
                let digest = RecoveryStorage.hash(try RecoveryStorage.json(manifest))
                let common: [String: Any] = ["operation_id": operation, "manifest_sha256": digest]
                let preflight = try exchange(child, "owner.restore.preflight", common, "child.restore.preflight_result")
                if preflight["status"] as? String == "blocked" {
                    let codes: Set<String> = ["legacy_pending_unbound", "operation_mismatch", "manifest_invalid", "source_unavailable",
                        "source_integrity", "schema_unsupported", "checkpoint_mismatch", "authority_conflict", "transaction_mismatch",
                        "storage_uncertain", "owner_busy", "health_unavailable"]
                    guard Set(preflight.keys) == ["operation_id", "status", "code"],
                          preflight["operation_id"] as? String == operation,
                          let code = preflight["code"] as? String, codes.contains(code) else { throw PhoneRemoteAuthorityError.invalidFrame }
                    try stop(child, operation: operation, reason: "preflight_denied")
                    guard try backend.read() == protected,
                          try RecoveryStorage.hash(RecoveryStorage.file(database)) == manifest["base_database_sha256"] as? String else {
                        throw PhoneRemoteAuthorityError.unavailable
                    }
                    try RecoveryStorage.stablePair(database, protected)
                    let normal = try launch("normal")
                    guard normal.serviceActivated else { throw PhoneRemoteAuthorityError.unavailable }
                    if !readyPath.isEmpty { try RecoveryStorage.writeNew(["status": "blocked", "code": code], readyPath) }
                    try reap(normal, success: false)
                    return 0
                }
                let expected: [String: Any] = ["operation_id": operation, "status": "ok", "manifest_sha256": digest,
                    "checkpoint_sha256": manifest["checkpoint_sha256"]!, "authority_sha256": manifest["authority_sha256"]!,
                    "base_database_sha256": manifest["base_database_sha256"]!, "checkpoint_size_bytes": manifest["checkpoint_size_bytes"]!]
                guard exactInt(preflight["checkpoint_size_bytes"]) == exactInt(manifest["checkpoint_size_bytes"]),
                      try RecoveryStorage.json(preflight) == RecoveryStorage.json(expected) else { throw PhoneRemoteAuthorityError.invalidFrame }
                var pending = protected.wire
                pending["anchor_version"] = 2; pending["host_generation"] = manifest["target_generation"]
                pending["transition_id"] = operation; pending["transition_state"] = "pending"
                pending["pending_restore"] = ["operation_id": operation, "target_generation": manifest["target_generation"]!,
                    "manifest_sha256": digest, "checkpoint_sha256": manifest["checkpoint_sha256"]!]
                pending["last_completed_restore"] = protected.lastCompletedRestore as Any? ?? NSNull()
                let next = try Anchor(pending)
                try backend.write(next, expecting: protected)
                guard try backend.read() == next else { throw PhoneRemoteAuthorityError.unavailable }
                protected = next
                if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-after-pending-anchor" {
                    try RecoveryStorage.writeNew(["phase": "pending-anchor"], baseRoot + "/interrupted")
                    throw PhoneRemoteAuthorityError.unavailable
                }
                let request: [String: Any] = ["operation_id": operation, "manifest_sha256": digest,
                    "checkpoint_sha256": manifest["checkpoint_sha256"]!, "authority_sha256": manifest["authority_sha256"]!,
                    "target_generation": manifest["target_generation"]!]
                let result = try exchange(child, "owner.restore.commit_pending", request, "child.restore.pending_result")
                let pendingExpected: [String: Any] = ["operation_id": operation, "status": "ok", "host_id": protected.host,
                    "target_generation": protected.generation, "transition_state": "pending"]
                guard exactInt(result["target_generation"]) == protected.generation,
                      try RecoveryStorage.json(result) == RecoveryStorage.json(pendingExpected) else { throw PhoneRemoteAuthorityError.invalidFrame }
                try stop(child, operation: operation, reason: "prepare_complete")
                func pendingStatus(_ requested: String) throws -> [String: Any] {
                    guard requested == operation, owned == nil, try backend.read() == protected else {
                        throw PhoneRemoteAuthorityError.unavailable
                    }
                    let actual = try RecoveryStorage.withDB(database) {
                        try RecoveryStorage.rows($0, "SELECT schema_version,host_id,host_generation,transition_id,transition_state FROM phone_remote_meta WHERE singleton_id=1")
                    }
                    let exact: [Any] = [2, protected.host, protected.generation, operation, "pending"]
                    guard actual.count == 1, try RecoveryStorage.json(actual[0]) == RecoveryStorage.json(exact),
                          try RecoveryStorage.authority(database) == manifest["authority_sha256"] as? String else {
                        throw PhoneRemoteAuthorityError.unavailable
                    }
                    return ["status": "pending", "operation_id": operation, "target_generation": protected.generation,
                        "manifest_sha256": digest, "owner_incarnation": incarnation,
                        "request_correlation": UUID().uuidString.lowercased()]
                }
                let before = try RecoveryStorage.hash(RecoveryStorage.file(database))
                preparedWitnesses = [try pendingStatus(operation), try pendingStatus(operation)]
                var rejected = false
                do { _ = try pendingStatus(UUID().uuidString.lowercased()) } catch { rejected = true }
                guard rejected, try RecoveryStorage.hash(RecoveryStorage.file(database)) == before,
                      try backend.read() == protected else { throw PhoneRemoteAuthorityError.unavailable }
            } else {
                guard let binding = protected.pendingRestore ?? protected.lastCompletedRestore,
                      let op = binding["operation_id"] as? String else { throw PhoneRemoteAuthorityError.unavailable }
                operation = op
                let path = baseRoot + "/.phone-restore/" + operation + "/manifest.json"
                manifest = try RecoveryStorage.object(path, max: 16_384)
                guard try RecoveryStorage.hash(RecoveryStorage.file(path)) == binding["manifest_sha256"] as? String,
                      manifest["checkpoint_sha256"] as? String == binding["checkpoint_sha256"] as? String,
                      exactInt(manifest["target_generation"]) == exactInt(binding["target_generation"]),
                      manifest["host_id"] as? String == protected.host else { throw PhoneRemoteAuthorityError.invalidFrame }
            }
            let digest = RecoveryStorage.hash(try RecoveryStorage.json(manifest))
            let common: [String: Any] = ["operation_id": operation, "manifest_sha256": digest]
            let root = baseRoot + "/.phone-restore/" + operation
            var journal = try RecoveryStorage.object(root + "/journal.json")
            if protected.pendingRestore != nil {
                // The native supervisor verifies the immutable authority source
                // itself before trusting a replacement child's inspection.
                let checkpointPath = root + "/checkpoint.db"
                let checkpoint = try RecoveryStorage.file(checkpointPath)
                guard UInt64(checkpoint.count) == exactInt(manifest["checkpoint_size_bytes"]),
                      RecoveryStorage.hash(checkpoint) == manifest["checkpoint_sha256"] as? String,
                      try RecoveryStorage.authority(checkpointPath) == manifest["authority_sha256"] as? String else {
                    throw PhoneRemoteAuthorityError.unavailable
                }
                try RecoveryStorage.catalog(checkpointPath)
                let schema = try RecoveryStorage.withDB(checkpointPath) {
                    try RecoveryStorage.rows($0, "SELECT schema_version FROM phone_remote_meta WHERE singleton_id=1")
                }
                guard schema.count == 1, let checkpointVersion = exactInt(schema[0][0]), [1, 2].contains(checkpointVersion) else {
                    throw PhoneRemoteAuthorityError.invalidFrame
                }
                var checkpointAnchor = protected.wire
                checkpointAnchor["anchor_version"] = checkpointVersion
                checkpointAnchor["host_generation"] = manifest["base_generation"]
                checkpointAnchor["transition_id"] = NSNull(); checkpointAnchor["transition_state"] = "stable"
                if checkpointVersion == 1 {
                    checkpointAnchor.removeValue(forKey: "pending_restore"); checkpointAnchor.removeValue(forKey: "last_completed_restore")
                } else { checkpointAnchor["pending_restore"] = NSNull() }
                try RecoveryStorage.stablePair(checkpointPath, Anchor(checkpointAnchor), manifestBase: baseRoot)
                if journal["phase"] as? String == "checkpoint_bound" {
                    let resume = try launch("prepare_resume", manifest: manifest)
                    var payload = common; payload["base_database_sha256"] = manifest["base_database_sha256"]
                    let response = try exchange(resume, "owner.restore.resume_preflight", payload, "child.restore.resume_preflight_result")
                    guard Set(response.keys) == ["operation_id", "status", "database_state", "base_database_sha256"],
                          response["operation_id"] as? String == operation, response["status"] as? String == "ok",
                          response["base_database_sha256"] as? String == manifest["base_database_sha256"] as? String,
                          let state = response["database_state"] as? String, ["base", "pending"].contains(state) else { throw PhoneRemoteAuthorityError.invalidFrame }
                    if state == "base" {
                        let payload: [String: Any] = ["operation_id": operation, "manifest_sha256": digest,
                            "checkpoint_sha256": manifest["checkpoint_sha256"]!, "authority_sha256": manifest["authority_sha256"]!, "target_generation": protected.generation]
                        let result = try exchange(resume, "owner.restore.commit_pending", payload, "child.restore.pending_result")
                        let expected: [String: Any] = ["operation_id": operation, "status": "ok", "host_id": protected.host,
                            "target_generation": protected.generation, "transition_state": "pending"]
                        guard exactInt(result["target_generation"]) == protected.generation,
                              try RecoveryStorage.json(result) == RecoveryStorage.json(expected) else { throw PhoneRemoteAuthorityError.invalidFrame }
                    }
                    try stop(resume, operation: operation, reason: "prepare_resume_complete")
                }
                let recovery = try launch("recover", manifest: manifest)
                func inspect() throws -> [String: Any] {
                    let value = try exchange(recovery, "owner.restore.inspect", common, "child.restore.inspect_result")
                    let keys: Set<String> = ["operation_id", "status", "phase", "database_state", "checkpoint_sha256",
                        "authority_sha256", "base_database_sha256", "staged_database_sha256", "installed_database_sha256"]
                    let allowed = ["pending": ["checkpoint_bound", "staged", "quiesced", "installing", "installed"],
                                   "committed": ["installed", "database_committed", "database_finalized"]]
                    guard Set(value.keys) == keys, value["operation_id"] as? String == operation,
                          value["status"] as? String == "ok", let phase = value["phase"] as? String,
                          let dbState = value["database_state"] as? String, allowed[dbState]?.contains(phase) == true,
                          value["checkpoint_sha256"] as? String == manifest["checkpoint_sha256"] as? String,
                          value["authority_sha256"] as? String == manifest["authority_sha256"] as? String,
                          value["base_database_sha256"] as? String == manifest["base_database_sha256"] as? String else {
                        throw PhoneRemoteAuthorityError.invalidFrame
                    }
                    if phase == "checkpoint_bound" {
                        guard value["staged_database_sha256"] is NSNull, value["installed_database_sha256"] is NSNull else {
                            throw PhoneRemoteAuthorityError.invalidFrame
                        }
                    } else {
                        guard RecoveryStorage.isDigest(value["staged_database_sha256"]) else { throw PhoneRemoteAuthorityError.invalidFrame }
                        if ["installed", "database_committed", "database_finalized"].contains(phase) {
                            guard value["installed_database_sha256"] as? String == value["staged_database_sha256"] as? String else {
                                throw PhoneRemoteAuthorityError.invalidFrame
                            }
                        } else if !(value["installed_database_sha256"] is NSNull) {
                            guard phase == "installing", value["installed_database_sha256"] as? String == value["staged_database_sha256"] as? String else {
                                throw PhoneRemoteAuthorityError.invalidFrame
                            }
                        }
                    }
                    return value
                }
                var inspection = try inspect()
                if inspection["phase"] as? String == "checkpoint_bound" {
                    var payload = common; payload["checkpoint_sha256"] = manifest["checkpoint_sha256"]
                    let staged = try exchange(recovery, "owner.restore.stage", payload, "child.restore.stage_result")
                    guard Set(staged.keys) == ["operation_id", "status", "staged_database_sha256", "staged_size_bytes", "store_schema_version"],
                          staged["operation_id"] as? String == operation, staged["status"] as? String == "ok",
                          RecoveryStorage.isDigest(staged["staged_database_sha256"]), exactInt(staged["store_schema_version"]) == 2,
                          let size = exactInt(staged["staged_size_bytes"]), size > 0, size <= 1 << 30 else { throw PhoneRemoteAuthorityError.invalidFrame }
                    inspection = try inspect()
                    guard inspection["phase"] as? String == "staged",
                          inspection["staged_database_sha256"] as? String == staged["staged_database_sha256"] as? String else { throw PhoneRemoteAuthorityError.invalidFrame }
                }
                if ["staged", "quiesced", "installing"].contains(inspection["phase"] as? String ?? "") {
                    var payload = common; payload["checkpoint_sha256"] = manifest["checkpoint_sha256"]
                    payload["staged_database_sha256"] = inspection["staged_database_sha256"]
                    let installed = try exchange(recovery, "owner.restore.install", payload, "child.restore.install_result")
                    let expected: [String: Any] = ["operation_id": operation, "status": "ok",
                        "installed_database_sha256": inspection["staged_database_sha256"]!, "phase": "installed"]
                    guard try RecoveryStorage.json(installed) == RecoveryStorage.json(expected) else { throw PhoneRemoteAuthorityError.invalidFrame }
                    inspection = try inspect()
                    guard inspection["phase"] as? String == "installed" else { throw PhoneRemoteAuthorityError.invalidFrame }
                }
                var payload = common; payload["checkpoint_sha256"] = manifest["checkpoint_sha256"]
                payload["installed_database_sha256"] = inspection["installed_database_sha256"]
                payload["target_generation"] = protected.generation
                let committed = try exchange(recovery, "owner.restore.commit_database", payload, "child.restore.database_committed")
                guard Set(committed.keys) == ["operation_id", "status", "receipt_version", "database_sha256", "phase"],
                      committed["operation_id"] as? String == operation, committed["status"] as? String == "ok",
                      exactInt(committed["receipt_version"]) == 1, committed["phase"] as? String == "database_committed",
                      let finalDigest = committed["database_sha256"] as? String, RecoveryStorage.isDigest(finalDigest) else { throw PhoneRemoteAuthorityError.invalidFrame }
                try stop(recovery, operation: operation, reason: "recovery_complete")
                journal = try RecoveryStorage.object(root + "/journal.json")
                guard journal["phase"] as? String == "database_finalized",
                      journal["final_database_sha256"] as? String == finalDigest,
                      try RecoveryStorage.hash(RecoveryStorage.file(database)) == finalDigest else { throw PhoneRemoteAuthorityError.unavailable }
                var stable = protected.wire
                stable["transition_id"] = NSNull(); stable["transition_state"] = "stable"; stable["pending_restore"] = NSNull()
                stable["last_completed_restore"] = ["operation_id": operation, "target_generation": protected.generation,
                    "manifest_sha256": digest, "checkpoint_sha256": manifest["checkpoint_sha256"]!, "database_sha256": finalDigest]
                let next = try Anchor(stable)
                try RecoveryStorage.catalog(database)
                try RecoveryStorage.stablePair(database, next)
                try backend.write(next, expecting: protected)
                guard try backend.read() == next else { throw PhoneRemoteAuthorityError.unavailable }
                protected = next
                if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-after-stable-anchor" {
                    try RecoveryStorage.writeNew(["phase": "stable-anchor"], baseRoot + "/interrupted")
                    throw PhoneRemoteAuthorityError.unavailable
                }
            }
            try RecoveryStorage.cleanup(root, database: database, anchor: protected)
            let normal = try launch("normal")
            // Completion and same-operation retries are available only while
            // this exact activated child remains healthy under the same lock.
            guard kill(normal.childPID, 0) == 0, normal.serviceActivated else { throw PhoneRemoteAuthorityError.unavailable }
            func completion(_ requestedOperation: String) throws -> [String: Any] {
                guard requestedOperation == operation, owned === normal, normal.serviceActivated,
                      kill(normal.childPID, 0) == 0, try backend.read() == protected,
                      try RecoveryStorage.object(root + "/journal.json")["phase"] as? String == "complete" else {
                    throw PhoneRemoteAuthorityError.unavailable
                }
                try RecoveryStorage.stablePair(database, protected)
                guard let tombstone = protected.lastCompletedRestore else { throw PhoneRemoteAuthorityError.invalidFrame }
                return ["status": "completed", "operation_id": operation,
                    "target_generation": tombstone["target_generation"]!,
                    "manifest_sha256": tombstone["manifest_sha256"]!,
                    "checkpoint_sha256": tombstone["checkpoint_sha256"]!,
                    "database_sha256": tombstone["database_sha256"]!,
                    "request_correlation": UUID().uuidString.lowercased(),
                    "owner_incarnation": incarnation, "child_incarnation": normal.childID]
            }
            let first = try completion(operation), repeated = try completion(operation)
            let completedDatabase = try RecoveryStorage.hash(RecoveryStorage.file(database))
            var wrongOperationRejected = false
            do { _ = try completion(UUID().uuidString.lowercased()) } catch { wrongOperationRejected = true }
            if let prior = priorCompletedOperation, prior != operation {
                var retired = false
                do { _ = try completion(prior) } catch { retired = true }
                guard retired else { throw PhoneRemoteAuthorityError.invalidFrame }
            }
            guard wrongOperationRejected,
                  try RecoveryStorage.hash(RecoveryStorage.file(database)) == completedDatabase,
                  try backend.read() == protected else { throw PhoneRemoteAuthorityError.unavailable }
            guard first["child_incarnation"] as? String == repeated["child_incarnation"] as? String,
                  first["request_correlation"] as? String != repeated["request_correlation"] as? String else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            if !readyPath.isEmpty { try RecoveryStorage.writeNew(["first": first, "repeated": repeated, "prepared": preparedWitnesses], readyPath) }
            // Test-controller teardown ends supervision only after returning
            // both completion witnesses. It is not a new restore/quiescence.
            try reap(normal, success: false)
            return 0
        } catch {

            if let child = owned { try? reap(child, success: false) }
            // No pending write is undone. This synthetic entrypoint holds the
            // singleton after any uncertain transition until test teardown.
            let observed = try? backend.read()
            if let observed, observed.transition == "stable" {
                // Inspect the actual persisted pair after confirmed child reap;
                // this never claims rollback or grants new admission.
                try? RecoveryStorage.stablePair(database, observed)
            }
            if recoveryHeld || observed?.transition == "pending" {
                try? RecoveryStorage.writeNew(["status": "blocked"], baseRoot + "/blocked")
                // The offline controller supplies an explicit capability through
                // this fixed private test mailbox. No production caller, path,
                // source selection, or phone protocol is authenticated here.
                let requestPath = baseRoot + "/continue.request"
                while true {
                    if FileManager.default.fileExists(atPath: requestPath),
                       let request = try? RecoveryStorage.object(requestPath),
                       Set(request.keys) == ["operation_id", "request_correlation"],
                       let operation = request["operation_id"] as? String,
                       let correlation = request["request_correlation"] as? String,
                       UUID(uuidString: operation)?.uuidString.lowercased() == operation,
                       UUID(uuidString: correlation)?.uuidString.lowercased() == correlation,
                       let current = try? backend.read() {
                        let binding = current.pendingRestore ?? current.lastCompletedRestore
                        let accepted = owned == nil && binding?["operation_id"] as? String == operation
                        let response: [String: Any] = accepted
                            ? ["status": "pending", "operation_id": operation, "target_generation": binding!["target_generation"]!,
                               "manifest_sha256": binding!["manifest_sha256"]!, "owner_incarnation": incarnation,
                               "request_correlation": correlation]
                            : ["status": "blocked", "code": "operation_mismatch", "request_correlation": correlation]
                        let responsePath = baseRoot + "/continue-" + correlation + ".response"
                        // A reused correlation never dispatches another attempt.
                        if !FileManager.default.fileExists(atPath: responsePath) {
                            try? RecoveryStorage.writeNew(response, responsePath)
                            if unlink(requestPath) == 0 { try? RecoveryStorage.sync(baseRoot) }
                            if accepted {
                                protected = current
                                continue recoveryAttempts
                            }
                        }
                    }
                    usleep(10_000)
                }
            }
            throw error
        }
        }
    }
}

private extension RecoveryStorage {
    static func cleanup(_ root: String, database: String, anchor: Anchor) throws {
        try stablePair(database, anchor)
        guard let tombstone = anchor.lastCompletedRestore else { throw PhoneRemoteAuthorityError.unavailable }
        var state = try object(root + "/journal.json")
        let keys: Set<String> = ["journal_version", "operation_id", "manifest_sha256", "phase", "rename_step", "files", "staged_database_sha256", "installed_database_sha256", "final_database_sha256", "cleanup_artifacts"]
        guard Set(state.keys) == keys, exactInt(state["journal_version"]) == 1,
              state["operation_id"] as? String == tombstone["operation_id"] as? String,
              state["manifest_sha256"] as? String == tombstone["manifest_sha256"] as? String,
              state["final_database_sha256"] as? String == tombstone["database_sha256"] as? String else {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        func interrupt(_ point: String) throws {
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_FAILPOINT"] == "r324-cleanup-" + point {
                let base = URL(fileURLWithPath: database).deletingLastPathComponent().path
                try writeNew(["phase": point], base + "/interrupted")
                throw PhoneRemoteAuthorityError.unavailable
            }
        }
        func save() throws {
            let tmp = root + "/journal.next.tmp"
            if FileManager.default.fileExists(atPath: tmp) {
                guard try file(tmp, allowEmpty: true).count <= 65_536 else { throw PhoneRemoteAuthorityError.unavailable }
                guard unlink(tmp) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
                try sync(root)
            }
            try writeNew(state, tmp)
            guard rename(tmp, root + "/journal.json") == 0 else { throw PhoneRemoteAuthorityError.unavailable }
            try sync(root)
            try interrupt("after-" + (state["phase"] as? String ?? "invalid"))
        }
        if state["phase"] as? String == "database_finalized" {
            guard try hash(file(database)) == tombstone["database_sha256"] as? String else { throw PhoneRemoteAuthorityError.unavailable }
            state["phase"] = "anchor_committed"; try save()
        }
        if state["phase"] as? String == "anchor_committed" { state["phase"] = "cleaning"; try save() }
        guard ["cleaning", "complete"].contains(state["phase"] as? String ?? ""),
              var artifacts = state["cleanup_artifacts"] as? [String: [String: Any]],
              Set(artifacts.keys) == ["checkpoint", "staged_database", "old_database", "old_wal", "old_shm"] else {
            throw PhoneRemoteAuthorityError.invalidFrame
        }
        for (name, filename) in [("checkpoint", "checkpoint.db"), ("staged_database", "staged.db"),
                                 ("old_database", "old.db"), ("old_wal", "old.wal"), ("old_shm", "old.shm")] {
            guard var item = artifacts[name], Set(item.keys) == ["state", "sha256"],
                  let phase = item["state"] as? String, ["absent", "pending", "intent", "done"].contains(phase) else {
                throw PhoneRemoteAuthorityError.invalidFrame
            }
            let path = root + "/" + filename
            var st = stat()
            let exists = lstat(path, &st) == 0
            if phase == "absent" || phase == "done" {
                guard !exists else { throw PhoneRemoteAuthorityError.unavailable }; continue
            }
            guard state["phase"] as? String == "cleaning" else { throw PhoneRemoteAuthorityError.invalidFrame }
            if phase == "pending" {
                guard exists, try hash(file(path)) == item["sha256"] as? String else { throw PhoneRemoteAuthorityError.unavailable }
                item["state"] = "intent"; artifacts[name] = item; state["cleanup_artifacts"] = artifacts; try save()
            }
            if exists {
                guard try hash(file(path)) == item["sha256"] as? String,
                      unlink(path) == 0 else { throw PhoneRemoteAuthorityError.unavailable }
                try sync(root)
                try interrupt("unlinked-" + name)
            }
            item["state"] = "done"; artifacts[name] = item; state["cleanup_artifacts"] = artifacts; try save()
        }
        if state["phase"] as? String != "complete" { state["phase"] = "complete"; try save() }
    }
}
