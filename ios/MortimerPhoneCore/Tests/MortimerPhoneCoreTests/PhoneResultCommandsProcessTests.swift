import Foundation
import XCTest
@testable import MortimerPhoneCore

/// Test-only bounded pipe bridge. Executable configuration never comes from wire bytes.
private actor CardProcessTransport: PhoneRemoteByteTransport {
    private let process: Process
    private let input: FileHandle
    private let output: FileHandle
    init() throws {
        let env = ProcessInfo.processInfo.environment
        guard let python = env["PHONE_REMOTE_AUTHORITY_PYTHON"],
              let owner = env["PHONE_REMOTE_AUTHORITY_OWNER_BIN"],
              let root = env["PHONE_REMOTE_AUTHORITY_TEST_ROOT"],
              FileManager.default.isExecutableFile(atPath: python),
              FileManager.default.isExecutableFile(atPath: owner) else {
            throw XCTSkip("Requires configured disposable Python/native-owner process fixtures")
        }
        process = Process()
        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-m", "tests.unit.test_phone_remote_authority_service", "--phone-card-bridge"]
        process.currentDirectoryURL = URL(fileURLWithPath: root)
        var environment = env; environment["PYTHONPATH"] = root; process.environment = environment
        let requestPipe = Pipe(), responsePipe = Pipe()
        process.standardInput = requestPipe; process.standardOutput = responsePipe
        process.standardError = FileHandle.standardError
        input = requestPipe.fileHandleForWriting; output = responsePipe.fileHandleForReading
        try process.run()
    }
    func exchange(_ request: Data) async throws -> Data {
        guard !request.isEmpty, request.count <= 1_048_576 else { throw CocoaError(.fileReadTooLarge) }
        let owned = process
        let timeout = DispatchWorkItem { if owned.isRunning { owned.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 20, execute: timeout)
        defer { timeout.cancel() }
        var size = UInt32(request.count).bigEndian
        try input.write(contentsOf: withUnsafeBytes(of: &size) { Data($0) } + request)
        let header = try readExactly(4)
        let count = header.reduce(UInt32(0)) { ($0 << 8) | UInt32($1) }
        guard count > 0, count <= 524_288 else { throw CocoaError(.fileReadTooLarge) }
        return try readExactly(Int(count))
    }
    private func readExactly(_ size: Int) throws -> Data {
        var data = Data()
        while data.count < size {
            guard let chunk = try output.read(upToCount: size - data.count), !chunk.isEmpty else {
                throw CocoaError(.fileReadUnknown)
            }
            data.append(chunk)
        }
        return data
    }
    func close() {
        try? input.close()
        let owned = process
        let timeout = DispatchWorkItem { if owned.isRunning { owned.terminate() } }
        DispatchQueue.global().asyncAfter(deadline: .now() + 7, execute: timeout)
        process.waitUntilExit(); timeout.cancel(); try? output.close()
    }
}

final class PhoneResultCommandsProcessTests: XCTestCase {
    @MainActor func testCheckedModelFiveActionsThroughNativeV4ProofSession() async throws {
        let transport = try CardProcessTransport()
        let model = PhoneAppPreviewModel(client: PhoneRemoteOperationsClient(transport: transport))
        await model.refreshSyntheticCards()
        guard case .syntheticCardResults(let items, let initial?, true, _) = model.state else {
            await transport.close(); return XCTFail("Native snapshot/view join failed: \(model.state)")
        }
        XCTAssertEqual(items.count, 2)
        let id = items[0].resultID
        var lastRevision = initial.viewRevision
        for action in [PhoneResultCardAction.select, .pin, .unpin, .close, .reopen] {
            await model.performCardAction(action, resultID: id)
            guard case .syntheticCardResults(let content, let view?, true, _) = model.state else {
                XCTFail("Native action did not publish: \(action): \(model.state)"); break
            }
            XCTAssertEqual(content, items)
            XCTAssertEqual(view.viewRevision, lastRevision + 1); lastRevision = view.viewRevision
            let card = try XCTUnwrap(view.cards.first { $0.resultID == id })
            XCTAssertEqual(card.open, action != .close)
            XCTAssertEqual(card.pinned, action == .pin)
            XCTAssertEqual(view.selectedResultID, action == .close ? nil : id)
        }
        await transport.close()
    }
}
