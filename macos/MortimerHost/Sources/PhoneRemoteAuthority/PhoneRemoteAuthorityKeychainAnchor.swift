import CoreFoundation
import Foundation
import LocalAuthentication
import Security

enum PhoneRemoteAuthorityAnchorError: Error, Equatable {
    case unavailable
    case interactionUnavailable
    case denied
    case notVisible
    case corrupt
    case busy

    var protocolErrorCode: String {
        switch self {
        case .denied: return "anchor_denied"
        case .corrupt: return "anchor_corrupt"
        case .busy: return "owner_busy"
        case .unavailable, .interactionUnavailable, .notVisible: return "authority_unavailable"
        }
    }
}

protocol PhoneRemoteAuthorityAnchorBackend {
    func read() throws -> Anchor
    func write(_ anchor: Anchor, expecting previous: Anchor) throws
}

/// Serializes owner-side anchor calls and makes any reentrant, concurrent, or
/// backend failure terminal even if an outer injected call later returns.
final class PhoneRemoteAuthorityAnchorSession {
    private let backend: PhoneRemoteAuthorityAnchorBackend
    private let operationLock = NSLock()
    private let stateLock = NSLock()
    private var failed = false

    init(backend: PhoneRemoteAuthorityAnchorBackend) { self.backend = backend }

    func read() throws -> Anchor { try perform { try backend.read() } }

    func write(_ anchor: Anchor, expecting previous: Anchor) throws {
        try perform {
            try backend.write(anchor, expecting: previous)
            return ()
        }
    }

    private func perform<T>(_ body: () throws -> T) throws -> T {
        guard operationLock.try() else {
            latchFailure()
            throw PhoneRemoteAuthorityAnchorError.busy
        }
        defer { operationLock.unlock() }
        try requireActive()
        do {
            let result = try body()
            try requireActive()
            return result
        } catch let error as PhoneRemoteAuthorityAnchorError {
            latchFailure()
            throw error
        } catch {
            latchFailure()
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
    }

    private func requireActive() throws {
        stateLock.lock(); defer { stateLock.unlock() }
        guard !failed else { throw PhoneRemoteAuthorityAnchorError.unavailable }
    }

    private func latchFailure() {
        stateLock.lock(); failed = true; stateLock.unlock()
    }
}

/// Test-only file implementation selected only by the existing --test-owner CLI.
final class FilePhoneRemoteAuthorityAnchor: PhoneRemoteAuthorityAnchorBackend {
    private let path: String

    init(path: String) { self.path = path }

    func read() throws -> Anchor {
        do {
            return try decodeAnchorFile(Data(contentsOf: URL(fileURLWithPath: path)))
        } catch let error as PhoneRemoteAuthorityAnchorError {
            throw error
        } catch {
            throw PhoneRemoteAuthorityAnchorError.corrupt
        }
    }

    func write(_ anchor: Anchor, expecting previous: Anchor) throws {
        do {
            guard try read() == previous else { throw PhoneRemoteAuthorityAnchorError.corrupt }
            var data = try JSONSerialization.data(withJSONObject: anchor.wire, options: [.sortedKeys])
            if ProcessInfo.processInfo.environment["PHONE_REMOTE_AUTHORITY_TEST_DUPLICATE_READBACK"] == "host_generation" {
                let text = String(decoding: data, as: UTF8.self)
                let original = "\"host_generation\":\(anchor.generation)"
                guard text.contains(original) else { throw PhoneRemoteAuthorityAnchorError.corrupt }
                data = Data(text.replacingOccurrences(of: original,
                    with: original + ",\"host_generation\":0").utf8)
            }
            try data.write(to: URL(fileURLWithPath: path), options: .atomic)
            guard try read() == anchor else { throw PhoneRemoteAuthorityAnchorError.corrupt }
        } catch let error as PhoneRemoteAuthorityAnchorError {
            throw error
        } catch {
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
    }
}

struct SecurityItemCopyResult {
    let status: OSStatus
    let value: Any?
}

protocol SecurityItemClient {
    func copyMatching(_ query: [String: Any]) -> SecurityItemCopyResult
    func update(_ query: [String: Any], attributes: [String: Any]) -> OSStatus
}

protocol NoninteractiveAuthenticationContextProviding {
    func makeContext() throws -> LAContext
}

struct LAContextNoninteractiveProvider: NoninteractiveAuthenticationContextProviding {
    func makeContext() throws -> LAContext {
        let context = LAContext()
        context.interactionNotAllowed = true
        guard context.interactionNotAllowed else {
            throw PhoneRemoteAuthorityAnchorError.interactionUnavailable
        }
        return context
    }
}

/// Injected Data Protection Keychain adapter. Callers must supply the signed
/// access group explicitly; this type never provisions, repairs, or falls back.
final class PhoneRemoteAuthorityKeychainAnchor: PhoneRemoteAuthorityAnchorBackend {
    static let service = "com.mortimer.phone-authority"
    static let account = "host-generation-v1"
    static let maxAnchorBytes = 65_536

    private let client: SecurityItemClient
    private let contextProvider: NoninteractiveAuthenticationContextProviding
    private let accessGroup: String
    private let callLock = NSLock()
    private let stateLock = NSLock()
    private var terminal = false

    init(client: SecurityItemClient, accessGroup: String,
         contextProvider: NoninteractiveAuthenticationContextProviding = LAContextNoninteractiveProvider()) throws {
        guard !accessGroup.isEmpty, accessGroup.utf8.count <= 255 else {
            throw PhoneRemoteAuthorityAnchorError.denied
        }
        self.client = client
        self.accessGroup = accessGroup
        self.contextProvider = contextProvider
    }

    func read() throws -> Anchor {
        try withExclusiveCall { try readUnlocked() }
    }

    func write(_ anchor: Anchor, expecting previous: Anchor) throws {
        try withExclusiveCall {
            guard try readUnlocked() == previous else {
                throw PhoneRemoteAuthorityAnchorError.corrupt
            }
            let query = selector(context: try newNoninteractiveContext())
            try requireActive()
            let status = client.update(query, attributes: [kSecValueData as String: Self.encodeCanonical(anchor)])
            try requireActive()
            guard status == errSecSuccess else { throw map(status) }
            let observed = try readUnlocked()
            guard observed == anchor,
                  Self.encodeCanonical(observed) == Self.encodeCanonical(anchor) else {
                throw PhoneRemoteAuthorityAnchorError.corrupt
            }
        }
    }

    private func withExclusiveCall<T>(_ body: () throws -> T) throws -> T {
        guard callLock.try() else {
            latchFailure()
            throw PhoneRemoteAuthorityAnchorError.busy
        }
        defer { callLock.unlock() }
        try requireActive()
        do {
            let result = try body()
            try requireActive()
            return result
        } catch let error as PhoneRemoteAuthorityAnchorError {
            latchFailure()
            throw error
        } catch {
            latchFailure()
            throw PhoneRemoteAuthorityAnchorError.unavailable
        }
    }

    private func requireActive() throws {
        stateLock.lock(); defer { stateLock.unlock() }
        guard !terminal else { throw PhoneRemoteAuthorityAnchorError.unavailable }
    }

    private func latchFailure() {
        stateLock.lock(); terminal = true; stateLock.unlock()
    }

    private func readUnlocked() throws -> Anchor {
        var allQuery = selector(context: try newNoninteractiveContext())
        allQuery[kSecMatchLimit as String] = kSecMatchLimitAll
        allQuery[kSecReturnAttributes as String] = true
        guard allQuery[kSecReturnData as String] == nil else { throw PhoneRemoteAuthorityAnchorError.corrupt }

        try requireActive()
        let first = client.copyMatching(allQuery)
        try requireActive()
        guard first.status == errSecSuccess else { throw map(first.status) }
        guard let rows = first.value as? [[String: Any]], rows.count == 1,
              validAttributes(rows[0], allowsData: false) else {
            throw PhoneRemoteAuthorityAnchorError.corrupt
        }

        var exactQuery = selector(context: try newNoninteractiveContext())
        exactQuery[kSecMatchLimit as String] = kSecMatchLimitOne
        exactQuery[kSecReturnAttributes as String] = true
        exactQuery[kSecReturnData as String] = true
        try requireActive()
        let second = client.copyMatching(exactQuery)
        try requireActive()
        guard second.status == errSecSuccess else { throw map(second.status) }
        guard let result = second.value as? [String: Any],
              validAttributes(result, allowsData: true),
              let data = result[kSecValueData as String] as? Data,
              !data.isEmpty, data.count <= Self.maxAnchorBytes else {
            throw PhoneRemoteAuthorityAnchorError.corrupt
        }
        let anchor: Anchor
        do { anchor = try Self.decodeProtected(data) }
        catch { throw PhoneRemoteAuthorityAnchorError.corrupt }
        return anchor
    }

    private func selector(context: LAContext) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecUseDataProtectionKeychain as String: true,
            kSecAttrService as String: Self.service,
            kSecAttrAccount as String: Self.account,
            kSecAttrAccessGroup as String: accessGroup,
            kSecAttrSynchronizable as String: false,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecUseAuthenticationContext as String: context,
        ]
    }

    private func newNoninteractiveContext() throws -> LAContext {
        let context = try contextProvider.makeContext()
        guard context.interactionNotAllowed else {
            throw PhoneRemoteAuthorityAnchorError.interactionUnavailable
        }
        return context
    }

    private func validAttributes(_ attributes: [String: Any], allowsData: Bool) -> Bool {
        let required: Set<String> = [
            kSecClass as String, kSecAttrService as String, kSecAttrAccount as String,
            kSecAttrAccessGroup as String, kSecAttrSynchronizable as String,
            kSecAttrAccessible as String,
        ]
        var allowed = required.union([
            kSecAttrCreationDate as String, kSecAttrModificationDate as String,
        ])
        if allowsData { allowed.insert(kSecValueData as String) }
        guard required.isSubset(of: Set(attributes.keys)), Set(attributes.keys).isSubset(of: allowed),
              attributes[kSecClass as String] as? String == kSecClassGenericPassword as String,
              attributes[kSecAttrService as String] as? String == Self.service,
              attributes[kSecAttrAccount as String] as? String == Self.account,
              attributes[kSecAttrAccessGroup as String] as? String == accessGroup,
              let sync = attributes[kSecAttrSynchronizable as String] as? NSNumber,
              CFGetTypeID(sync) == CFBooleanGetTypeID(), !sync.boolValue,
              attributes[kSecAttrAccessible as String] as? String == kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String else {
            return false
        }
        if let created = attributes[kSecAttrCreationDate as String], !(created is Date) { return false }
        if let modified = attributes[kSecAttrModificationDate as String], !(modified is Date) { return false }
        if allowsData, !(attributes[kSecValueData as String] is Data) { return false }
        return true
    }

    private func map(_ status: OSStatus) -> PhoneRemoteAuthorityAnchorError {
        switch status {
        case errSecItemNotFound: return .notVisible
        case errSecInteractionNotAllowed: return .interactionUnavailable
        case errSecMissingEntitlement, errSecAuthFailed, errSecNoAccessForItem: return .denied
        default: return .unavailable
        }
    }

    static func decodeProtected(_ data: Data) throws -> Anchor {
        guard !data.isEmpty, data.count <= maxAnchorBytes else { throw PhoneRemoteAuthorityAnchorError.corrupt }
        let anchor = try decodeAnchorFile(data)
        guard encodeCanonical(anchor).elementsEqual(data) else { throw PhoneRemoteAuthorityAnchorError.corrupt }
        return anchor
    }

    static func encodeCanonical(_ anchor: Anchor) -> Data {
        func quote(_ value: String) -> String {
            var output = "\""
            for scalar in value.unicodeScalars {
                switch scalar.value {
                case 0x22: output += "\\\""
                case 0x5c: output += "\\\\"
                case 0...0x1f: output += String(format: "\\u%04x", Int(scalar.value))
                default: output.unicodeScalars.append(scalar)
                }
            }
            output += "\""
            return output
        }
        let transitionID = anchor.transitionID.map(quote) ?? "null"
        let text = "{\"anchor_version\":\(anchor.version),\"host_id\":\(quote(anchor.host))," +
            "\"host_generation\":\(anchor.generation),\"transition_id\":\(transitionID)," +
            "\"transition_state\":\(quote(anchor.transition)),\"login_counter\":\(anchor.login)}"
        return Data(text.utf8)
    }
}
