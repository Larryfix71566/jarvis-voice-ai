import XCTest
@testable import JarvisKit

@MainActor
final class TranscriptStreamingTests: XCTestCase {
    private func makeClient() -> (JarvisClient, StubTransport) {
        let config = JarvisConfig(
            botURL: URL(string: "http://127.0.0.1:7860")!,
            adminURL: URL(string: "http://127.0.0.1:7861")!,
            wakeWordURL: URL(string: "ws://127.0.0.1:7862/ws")!,
            token: nil
        )
        let transport = StubTransport()
        return (JarvisClient(config: config, stubTransport: transport), transport)
    }

    private func send(_ type: String, data: String = "") -> String {
        let payload = data.isEmpty ? "" : ",\"data\":{\"text\":\"\(data)\"}"
        return """
        {"id":"test","label":"rtvi-ai","type":"server-message","data":{"type":"\(type)"\(payload)}}
        """
    }

    func testBotLLMTextFramesAggregateIntoOneLiveAssistantEntry() async {
        let (client, transport) = makeClient()

        transport.simulateReceivedAppMessage(json: send("bot-llm-started"))
        await flushMainActor()
        XCTAssertEqual(client.transcript.count, 1)
        let entryID = client.transcript[0].id

        transport.simulateReceivedAppMessage(json: send("bot-llm-text", data: "Full "))
        await flushMainActor()
        transport.simulateReceivedAppMessage(json: send("bot-llm-text", data: "answer"))
        await flushMainActor()

        XCTAssertEqual(client.transcript.count, 1)
        XCTAssertEqual(client.transcript[0].id, entryID)
        XCTAssertEqual(client.transcript[0].role, "assistant")
        XCTAssertEqual(client.transcript[0].text, "Full answer")

        transport.simulateReceivedAppMessage(json: send("bot-llm-stopped"))
        await flushMainActor()
        XCTAssertEqual(client.transcript[0].id, entryID)
        XCTAssertEqual(client.transcript[0].text, "Full answer")
    }

    func testOnlyFinalUserTranscriptionEntersTranscript() async {
        let (client, transport) = makeClient()
        let interim = """
        {"type":"server-message","data":{"type":"user-transcription","data":{"text":"partial","final":false}}}
        """
        let final = """
        {"type":"server-message","data":{"type":"user-transcription","data":{"text":"confirmed","final":true}}}
        """

        transport.simulateReceivedAppMessage(json: interim)
        await flushMainActor()
        XCTAssertTrue(client.transcript.isEmpty)

        transport.simulateReceivedAppMessage(json: final)
        await flushMainActor()
        XCTAssertEqual(client.transcript.map(\.text), ["confirmed"])
        XCTAssertEqual(client.transcript.map(\.role), ["user"])
    }
}
