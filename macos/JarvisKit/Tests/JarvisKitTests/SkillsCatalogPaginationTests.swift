import Foundation
import XCTest
@testable import JarvisKit

final class SkillsCatalogPaginationTests: XCTestCase {
    override func setUp() {
        super.setUp()
        CatalogPagesProtocol.reset()
        URLProtocol.registerClass(CatalogPagesProtocol.self)
    }

    override func tearDown() {
        URLProtocol.unregisterClass(CatalogPagesProtocol.self)
        super.tearDown()
    }

    func testAllSkillsCatalogLoadsEveryPageAndRetainsFirstPageMetadata() async throws {
        let api = AdminAPI(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "test"
        ))

        let catalog = try await api.allSkillsCatalog(pageSize: 25)

        XCTAssertEqual(catalog["catalog_revision"]?.stringValue, String(repeating: "a", count: 64))
        XCTAssertEqual(catalog["capabilities"]?["authoring"]?.boolValue, true)
        XCTAssertEqual(catalog["items"]?.arrayValue?.count, 61)
        XCTAssertEqual(catalog["items"]?.arrayValue?.last?["skill_id"]?.stringValue, "skill-60")
        XCTAssertEqual(catalog["next_cursor"], .null)
        XCTAssertEqual(CatalogPagesProtocol.requestedCursors, [nil, "25", "50"])
    }

    func testAllSkillsCatalogRejectsRepeatedCursorInsteadOfReturningPartialCatalog() async throws {
        CatalogPagesProtocol.repeatCursor = true
        let api = AdminAPI(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "test"
        ))

        do {
            _ = try await api.allSkillsCatalog(pageSize: 25)
            XCTFail("a repeated cursor must be surfaced as an error")
        } catch {
            XCTAssertEqual(CatalogPagesProtocol.requestedCursors.count, 2)
        }
    }

    func testAllSkillsCatalogRejectsRevisionChangeBetweenPages() async throws {
        CatalogPagesProtocol.changeRevisionAfterFirstPage = true
        let api = AdminAPI(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "test"
        ))

        do {
            _ = try await api.allSkillsCatalog(pageSize: 25)
            XCTFail("catalog mutation during pagination must be explicit")
        } catch {
            XCTAssertEqual(CatalogPagesProtocol.requestedCursors.count, 2)
        }
    }

    func testAllSkillsCatalogRejectsOverlappingSkillIDs() async throws {
        CatalogPagesProtocol.overlapPageIDs = true
        let api = AdminAPI(config: JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!, token: "test"
        ))

        do {
            _ = try await api.allSkillsCatalog(pageSize: 25)
            XCTFail("overlapping pages must not render duplicate skill cards")
        } catch {
            XCTAssertEqual(CatalogPagesProtocol.requestedCursors.count, 2)
        }
    }
}

private final class CatalogPagesProtocol: URLProtocol {
    nonisolated(unsafe) static var requestedCursors: [String?] = []
    nonisolated(unsafe) static var repeatCursor = false
    nonisolated(unsafe) static var changeRevisionAfterFirstPage = false
    nonisolated(unsafe) static var overlapPageIDs = false

    static func reset() {
        requestedCursors = []
        repeatCursor = false
        changeRevisionAfterFirstPage = false
        overlapPageIDs = false
    }

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.path == "/api/skills"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
        let cursor = components?.queryItems?.first(where: { $0.name == "cursor" })?.value
        Self.requestedCursors.append(cursor)
        let offset = Int(cursor ?? "0") ?? 0
        let nextOffset = Self.repeatCursor ? 25 : min(offset + 25, 61)
        let itemStart = Self.overlapPageIDs && offset > 0 ? offset - 1 : offset
        let items = (itemStart..<nextOffset).map { index in
            ["skill_id": "skill-\(index)", "display_name": "Skill \(index)",
             "description": "Catalog fixture \(index)"]
        }
        let body: [String: Any] = [
            "schema_version": 1,
            "catalog_revision": String(repeating: Self.changeRevisionAfterFirstPage && offset > 0 ? "b" : "a", count: 64),
            "capabilities": ["authoring": true],
            "items": items,
            "next_cursor": nextOffset < 61 ? String(nextOffset) : NSNull(),
        ]
        let data = try! JSONSerialization.data(withJSONObject: body)
        let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                       httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
