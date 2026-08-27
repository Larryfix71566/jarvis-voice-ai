import Foundation
import Security
import os

private let keychainLog = Logger(subsystem: "com.mortimer.jarviskit", category: "keychain")

/// K1's token store. Service `"com.mortimer.jarviskit"`, one account per
/// bot URL (scheme://host:port) so relocating to a different host (e.g.
/// T3's mini) is a new Keychain entry, not a silently reused one.
/// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` — survives a reboot
/// for a background reconnect, never syncs to iCloud, never leaves the
/// device. This is the K1 bearer-token store ONLY (§3 N12, R-N11) — a
/// later T4b sensitive-tier key is a different Keychain item, gated with
/// SecAccessControl user-presence, and is never added here.
public enum KeychainStore {
    private static let service = "com.mortimer.jarviskit"

    /// "<scheme>://<host>:<port>" derived from the bot URL, port
    /// defaulting to 7860 when absent.
    static func account(for botURL: URL) -> String {
        let scheme = botURL.scheme ?? "http"
        let host = botURL.host ?? "127.0.0.1"
        let port = botURL.port ?? 7860
        return "\(scheme)://\(host):\(port)"
    }

    public static func token(for botURL: URL) -> String? {
        let acct = account(for: botURL)
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: acct,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        query.removeValue(forKey: kSecReturnData as String)
        guard status == errSecSuccess, let data = item as? Data,
              let value = String(data: data, encoding: .utf8) else {
            keychainLog.debug("keychain_token_present=false")
            return nil
        }
        keychainLog.debug("keychain_token_present=true")
        return value
    }

    public static func setToken(_ token: String?, for botURL: URL) {
        let acct = account(for: botURL)
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: acct,
        ]

        guard let token else {
            let status = SecItemDelete(baseQuery as CFDictionary)
            keychainLog.debug("keychain_token_present=false (deleted, status=\(status))")
            return
        }

        guard let data = token.data(using: .utf8) else {
            keychainLog.error("setToken: token is not valid UTF-8, not stored")
            return
        }

        // Try update first; if nothing exists yet, add.
        let updateAttributes: [String: Any] = [kSecValueData as String: data]
        let updateStatus = SecItemUpdate(baseQuery as CFDictionary, updateAttributes as CFDictionary)
        if updateStatus == errSecItemNotFound {
            var addQuery = baseQuery
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
            keychainLog.debug("keychain_token_present=true (added, status=\(addStatus))")
        } else {
            keychainLog.debug("keychain_token_present=true (updated, status=\(updateStatus))")
        }
    }
}
