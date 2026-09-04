import XCTest
@testable import JarvisKit

final class ConfigAndAuthTests: XCTestCase {
    override func setUp() {
        super.setUp()
        StubURLProtocol.reset()
        URLProtocol.registerClass(StubURLProtocol.self)
        // Clean env for the resolution-order tests below.
        UserDefaults.standard.removeObject(forKey: "JARVIS_BOT_URL")
        UserDefaults.standard.removeObject(forKey: "JARVIS_ADMIN_URL")
        UserDefaults.standard.removeObject(forKey: "JARVIS_WAKEWORD_URL")
    }

    override func tearDown() {
        URLProtocol.unregisterClass(StubURLProtocol.self)
        super.tearDown()
    }

    func testDefaultURLsAreLoopback() {
        let config = JarvisConfig.default()
        XCTAssertEqual(config.botURL, URL(string: "http://127.0.0.1:7860"))       // C2
        XCTAssertEqual(config.adminURL, URL(string: "http://127.0.0.1:7861"))
        XCTAssertEqual(config.wakeWordURL, URL(string: "ws://127.0.0.1:7862/ws"))
    }

    func testEnvironmentBeatsUserDefaults() {
        // ProcessInfo.processInfo.environment re-reads via getenv, so
        // setenv() in-process is a faithful way to exercise N12's
        // documented precedence (env beats UserDefaults) without a
        // subprocess.
        UserDefaults.standard.set("http://10.0.0.9:9999", forKey: "JARVIS_BOT_URL")
        setenv("JARVIS_BOT_URL", "http://172.16.0.1:8888", 1)
        defer {
            UserDefaults.standard.removeObject(forKey: "JARVIS_BOT_URL")
            unsetenv("JARVIS_BOT_URL")
        }
        let config = JarvisConfig.default()
        XCTAssertEqual(config.botURL, URL(string: "http://172.16.0.1:8888"))   // env wins (N12)
    }

    func testUserDefaultsBeatsCompiledDefault() {
        UserDefaults.standard.set("http://192.168.1.50:7860", forKey: "JARVIS_BOT_URL")
        defer { UserDefaults.standard.removeObject(forKey: "JARVIS_BOT_URL") }
        let config = JarvisConfig.default()
        XCTAssertEqual(config.botURL, URL(string: "http://192.168.1.50:7860"))
    }

    func testBearerAttachedWhenTokenPresent() async throws {
        StubURLProtocol.statusCode = 200
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "jvt_abc"
        )
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        _ = try await JarvisHTTP.send(req, config: config)
        XCTAssertEqual(StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization"), "Bearer jvt_abc")
    }

    func testNoAuthorizationHeaderWhenTokenNil() async throws {
        StubURLProtocol.statusCode = 200
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        _ = try await JarvisHTTP.send(req, config: config)
        XCTAssertNil(StubURLProtocol.lastRequest?.value(forHTTPHeaderField: "Authorization"))
    }

    func testAuthDisabledFlagSuppressesToken() {
        UserDefaults.standard.set(false, forKey: "JARVIS_CLIENT_AUTH_ENABLED")
        defer { UserDefaults.standard.removeObject(forKey: "JARVIS_CLIENT_AUTH_ENABLED") }
        let botURL = URL(string: "http://127.0.0.1:7860")!
        KeychainStore.setToken("jvt_stored", for: botURL)
        defer { KeychainStore.setToken(nil, for: botURL) }
        let config = JarvisConfig.default()
        XCTAssertNil(config.token)
    }

    func test401MapsToUnauthorized() async {
        StubURLProtocol.statusCode = 401
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "jvt"
        )
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        do {
            _ = try await JarvisHTTP.send(req, config: config)
            XCTFail("expected unauthorized")
        } catch {
            XCTAssertEqual(error as? JarvisError, .unauthorized)
        }
        XCTAssertEqual(StubURLProtocol.requestCount, 1)   // no retry, K1
    }

    func test403MapsToForbidden() async {
        StubURLProtocol.statusCode = 403
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "jvt"
        )
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        do {
            _ = try await JarvisHTTP.send(req, config: config)
            XCTFail("expected forbidden")
        } catch {
            XCTAssertEqual(error as? JarvisError, .forbidden)
        }
    }

    func test500MapsToHTTP() async {
        StubURLProtocol.statusCode = 500
        StubURLProtocol.responseBody = Data("boom".utf8)
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        var req = URLRequest(url: config.adminURL.appending(path: "api/health"))
        req.httpMethod = "GET"
        do {
            _ = try await JarvisHTTP.send(req, config: config)
            XCTFail("expected .http")
        } catch {
            XCTAssertEqual(error as? JarvisError, .http(status: 500, body: "boom"))
        }
    }

    func testKeychainAccountDerivedFromBotURL() {
        let a = URL(string: "http://192.168.1.9:7860")!
        let b = URL(string: "http://127.0.0.1:7860")!
        KeychainStore.setToken("token-a", for: a)
        KeychainStore.setToken("token-b", for: b)
        defer { KeychainStore.setToken(nil, for: a); KeychainStore.setToken(nil, for: b) }
        XCTAssertEqual(KeychainStore.token(for: a), "token-a")
        XCTAssertEqual(KeychainStore.token(for: b), "token-b")
        // Relocating to the mini (T3) is a new keychain entry, not a
        // silently reused one.
        XCTAssertNotEqual(KeychainStore.token(for: a), KeychainStore.token(for: b))
    }

    func testNonLoopbackWithoutTokenRefuses() {
        let config = JarvisConfig(
            botURL: URL(string: "http://203.0.113.4:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        XCTAssertThrowsError(try config.validate()) { error in
            XCTAssertEqual(error as? JarvisError, .insecureHost("http://203.0.113.4:7860"))
        }
    }

    func testNonLoopbackWithTokenConnects() throws {
        let config = JarvisConfig(
            botURL: URL(string: "http://203.0.113.4:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "jvt"
        )
        XCTAssertNoThrow(try config.validate())
    }

    func testNonLoopbackWithAuthFlagOffRefuses() {
        UserDefaults.standard.set(false, forKey: "JARVIS_CLIENT_AUTH_ENABLED")
        defer { UserDefaults.standard.removeObject(forKey: "JARVIS_CLIENT_AUTH_ENABLED") }
        let config = JarvisConfig(
            botURL: URL(string: "http://203.0.113.4:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: "jvt"
        )
        XCTAssertThrowsError(try config.validate())   // fail-closed, review F19
    }

    @MainActor
    func testConnectRereadsTokenFromKeychain() async throws {
        let botURL = URL(string: "http://127.0.0.1:7860")!
        KeychainStore.setToken(nil, for: botURL)
        let stub = StubTransport()
        let client = JarvisClient(
            config: JarvisConfig(botURL: botURL, adminURL: URL(string: "http://127.0.0.1:7861")!,
                                  wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: nil),
            stubTransport: stub
        )
        KeychainStore.setToken("just-minted", for: botURL)
        defer { KeychainStore.setToken(nil, for: botURL) }

        await client.connect()

        XCTAssertEqual(stub.lastConfigSeenOnConnect?.token, "just-minted")   // F20 — no relaunch needed
    }
}
