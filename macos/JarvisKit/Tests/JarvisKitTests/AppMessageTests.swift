import XCTest
@testable import JarvisKit

final class AppMessageTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        guard let url = Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures") else {
            let flatURL = Bundle.module.url(forResource: name, withExtension: "json")
            return try Data(contentsOf: XCTUnwrap(flatURL))
        }
        return try Data(contentsOf: url)
    }

    func testDecodeAgentWorking() throws {
        let data = try fixture("agent_working")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .agentWorking(let w) = message else { return XCTFail("expected .agentWorking") }
        XCTAssertEqual(w.runId, "r-1")
        XCTAssertEqual(w.model, "moonshotai/kimi-k2.5-instruct")
        XCTAssertEqual(w.modelFallback, false)
        XCTAssertEqual(w.task, "compare hosts")
    }

    func testDecodeConsoleResultFromRTVIEnvelope() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"console/result","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","request_id":"00000000-0000-4000-8000-000000000003","status":"ok","code":"inventory","summary":"ready"}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .consoleResult(let result) = message else { return XCTFail("expected .consoleResult") }
        XCTAssertEqual(result.code, "inventory")
    }

    func testDecodeInputStatusKeepsTerminalCode() throws {
        let json = """
        {"type":"input/status","version":1,"status":"error","code":"cancelled","summary":"Shared content cancelled.","request_id":"00000000-0000-4000-8000-000000000003"}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .inputStatus(let status) = message else { return XCTFail("expected .inputStatus") }
        XCTAssertEqual(status.code, "cancelled")
        XCTAssertEqual(status.requestID?.uuidString, "00000000-0000-4000-8000-000000000003")
    }

    func testDecodeInputAcceptAndChunkAck() throws {
        let acceptJSON = """
        {"type":"input/accept","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","batch_id":"00000000-0000-4000-8000-000000000003","transfer_id":"00000000-0000-4000-8000-000000000004","temporary_content_mode":true,"max_chunk_bytes":16384}
        """
        let acceptMessage = try XCTUnwrap(try AppMessage.decode(frame: Data(acceptJSON.utf8)))
        guard case .inputAccept(let accept) = acceptMessage else { return XCTFail("expected .inputAccept") }
        XCTAssertTrue(accept.temporaryContentMode)
        XCTAssertEqual(accept.maxChunkBytes, 16 * 1024)

        let ackJSON = """
        {"type":"input/ack","version":1,"transfer_id":"00000000-0000-4000-8000-000000000004","attachment_id":"00000000-0000-4000-8000-000000000005","sequence":2}
        """
        let ackMessage = try XCTUnwrap(try AppMessage.decode(frame: Data(ackJSON.utf8)))
        guard case .inputAck(let ack) = ackMessage else { return XCTFail("expected .inputAck") }
        XCTAssertEqual(ack.sequence, 2)
    }

    func testDecodeInputOfferPreservesBoundedApprovalMetadata() throws {
        let json = """
        {"type":"input/offer","version":1,"session_id":"00000000-0000-4000-8000-000000000001","generation":"00000000-0000-4000-8000-000000000002","request_id":"00000000-0000-4000-8000-000000000003","batch_id":"00000000-0000-4000-8000-000000000004","attachment_ids":["00000000-0000-4000-8000-000000000005"],"question":"Explain this.","profile":{"id":"vision","label":"Configured vision"}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .inputOffer(let offer) = message else { return XCTFail("expected .inputOffer") }
        XCTAssertEqual(offer.attachmentIDs.count, 1)
        XCTAssertEqual(offer.profile.label, "Configured vision")
    }

    func testDecodeInputConsentPreservesSpokenDecisionIdentity() throws {
        let session = UUID(), generation = UUID(), batch = UUID(), turn = UUID()
        let data = try JSONEncoder().encode(InputConsent(sessionID: session,
            generation: generation, batchID: batch, approved: true, userTurnID: turn))
        let message = try XCTUnwrap(AppMessage.decode(frame: data))
        guard case .inputConsent(let consent) = message else {
            return XCTFail("expected input consent")
        }
        XCTAssertEqual(consent.batchID, batch)
        XCTAssertEqual(consent.userTurnID, turn)
        XCTAssertTrue(consent.approved)
    }

    func testDecodeAgentDone() throws {
        let data = try fixture("agent_done")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .agentDone(let d) = message else { return XCTFail("expected .agentDone") }
        XCTAssertEqual(d.ok, false)
        XCTAssertEqual(d.detail, "tool failed")
    }

    func testDecodeAgentDoneMissingOkDefaultsTrue() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"agent","name":"analyst","display_name":"Analyst","state":"done","detail":"tool failed"}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .agentDone(let d) = message else { return XCTFail("expected .agentDone") }
        XCTAssertEqual(d.ok, true)   // agentRuns.ts:362
    }

    func testDecodeAgentTool() throws {
        let data = try fixture("agent_tool")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .agentTool(let t) = message else { return XCTFail("expected .agentTool") }
        XCTAssertEqual(t.tool, "selfedit_start")
    }

    func testDecodeAgentActivityWithPlannerModel() throws {
        let data = try fixture("agent_activity")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .agentActivity(let a) = message else { return XCTFail("expected .agentActivity") }
        XCTAssertEqual(a.latencyMs, 812)
        XCTAssertEqual(a.plannerModel, "claude-opus-4")
    }

    func testDecodeAgentActivityWithoutPlannerModel() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"agent_activity","name":"developer","run_id":"r-3","tool":"web_search","ok":true,"latency_ms":300}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .agentActivity(let a) = message else { return XCTFail("expected .agentActivity") }
        XCTAssertNil(a.plannerModel)
    }

    func testDecodeDisplayWindowSurface() throws {
        let data = try fixture("display_window")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertEqual(p.surface, .window)
        XCTAssertEqual(p.ts, 1_756_200_000)
    }

    func testDecodeDisplayMissingSurfaceDefaultsToDrawer() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"display","display":{"kind":"markdown","title":"t","body":"b"}}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertEqual(p.surface, .drawer)   // App.tsx:238-240
    }

    func testDecodeDisplayUnknownSurfaceDefaultsToDrawer() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"display","display":{"kind":"markdown","surface":"hologram"}}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertEqual(p.surface, .drawer)
    }

    func testDecodeDisplayHandoffPayloadIgnoresInnerType() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"display","display":{"type":"display","surface":"window","tool":"show_commands",
           "title":"Run this","commands":["ls -la"],"note":"then copy","expect_output":true}}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertEqual(p.commands, ["ls -la"])
        XCTAssertEqual(p.expectOutput, true)
    }

    func testDecodeDisplayClipboardPayload() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"display","display":{"type":"display","surface":"window","tool":"read_clipboard",
           "title":"Read from your clipboard","content":"secret text","chars":11,"truncated":false}}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertEqual(p.content, "secret text")
        XCTAssertEqual(p.chars, 11)
    }

    func testDecodeDisplayRadarBasemap() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"display","display":{"kind":"image","images":["a.png","b.png"],
           "basemap_images":["base-a.png","base-b.png"]}}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .display(let p) = message else { return XCTFail("expected .display") }
        XCTAssertNotNil(p.images)
        XCTAssertNotNil(p.basemapImages)
        XCTAssertEqual(p.basemapImages?.count, p.images?.count)
    }

    func testDecodeUICommandWithTab() throws {
        let data = try fixture("ui_command")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .ui(let cmd) = message else { return XCTFail("expected .ui") }
        XCTAssertEqual(cmd.action, "drawer_tab")
        XCTAssertEqual(cmd.tab, "agents")
    }

    func testDecodeUICommandWithoutTab() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":{"type":"ui","action":"display_popout"}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .ui(let cmd) = message else { return XCTFail("expected .ui") }
        XCTAssertNil(cmd.tab)
    }

    func testDecodeVoiceCatalog() throws {
        let data = try fixture("voice_catalog")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .voiceCatalog(let catalog) = message else { return XCTFail("expected .voiceCatalog") }
        XCTAssertEqual(catalog.voices.count, 1)
        XCTAssertEqual(catalog.voices.first?.elevenlabsVoiceID, "abc")
        XCTAssertEqual(catalog.current, "jarvis")
    }

    func testDecodeVoiceCurrent() throws {
        let data = try fixture("voice_current")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .voiceCurrent(let v) = message else { return XCTFail("expected .voiceCurrent") }
        XCTAssertEqual(v, "bella")
    }

    func testDecodeSpeakerGateNearThreshold() throws {
        let data = try fixture("speaker_gate")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .speakerGate(let g) = message else { return XCTFail("expected .speakerGate") }
        XCTAssertEqual(g.score, 0.42)
        XCTAssertEqual(g.nearThreshold, true)
    }

    func testDecodeSpeakerGateNullScore() throws {
        let json = """
        {"id":"m","label":"rtvi-ai","type":"server-message","data":
          {"type":"speaker_gate","verdict":"dropped","score":null,"near_threshold":false}}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .speakerGate(let g) = message else { return XCTFail("expected .speakerGate") }
        XCTAssertNil(g.score)   // speaker_gate.py:339 sends None when no score
    }

    func testDecodeCapability() throws {
        let data = try fixture("capability")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .capability(let agents) = message else { return XCTFail("expected .capability") }
        XCTAssertEqual(agents.count, 1)
        XCTAssertNil(agents.first?.resolvedModel)
        XCTAssertEqual(agents.first?.fallback, true)
    }

    func testDecodeUnknownTypePreservesRaw() throws {
        let data = try fixture("unknown_type")
        let message = try XCTUnwrap(try AppMessage.decode(frame: data))
        guard case .unknown(let type, let raw) = message else { return XCTFail("expected .unknown") }
        XCTAssertEqual(type, "weather_alert")
        XCTAssertEqual(raw["severity"]?.stringValue, "high")
    }

    func testDecodeSignallingFrameReturnsNil() throws {
        let json = """
        {"type":"signalling","message":{"type":"peerLeft"}}
        """
        let message = try AppMessage.decode(frame: Data(json.utf8))
        XCTAssertNil(message)   // connection.py:349 — signalling is the transport's, not ours
    }

    func testDecodeBarePayloadWithoutEnvelope() throws {
        let json = """
        {"type":"ui","action":"drawer_close"}
        """
        let message = try XCTUnwrap(try AppMessage.decode(frame: Data(json.utf8)))
        guard case .ui(let cmd) = message else { return XCTFail("expected .ui") }
        XCTAssertEqual(cmd.action, "drawer_close")
    }

    func testDecodeMalformedJSONThrows() {
        let data = Data("{".utf8)
        XCTAssertThrowsError(try AppMessage.decode(frame: data))
    }

    func testDecodeFrameWithoutTypeReturnsNil() throws {
        let json = """
        {"hello":"world"}
        """
        let message = try AppMessage.decode(frame: Data(json.utf8))
        XCTAssertNil(message)
    }

    // §7.8 — shape-only, no end-to-end test (correction 6: this bot emits neither).
    func testDecodeUserTranscription() throws {
        let json = """
        {"text":"hello mortimer","user_id":"u1","timestamp":"2026-08-27T00:00:00Z","final":true}
        """
        let entry = try RTVITranscription.decodeUserTranscription(from: Data(json.utf8))
        XCTAssertEqual(entry.role, "user")
        XCTAssertEqual(entry.text, "hello mortimer")
    }

    func testDecodeBotTranscription() throws {
        let json = """
        {"text":"hello there","timestamp":"2026-08-27T00:00:01Z"}
        """
        let entry = try RTVITranscription.decodeBotTranscription(from: Data(json.utf8))
        XCTAssertEqual(entry.role, "assistant")
        XCTAssertEqual(entry.text, "hello there")
    }
}
