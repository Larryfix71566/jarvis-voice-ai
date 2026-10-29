import XCTest
@testable import MortimerPhoneCore

final class PhoneSessionStateTests: XCTestCase {
    func testRequestResponseMappingAndEnd() {
        let mappings: [(PhoneRemoteStatus, PhoneSessionState)] = [
            (.ok, .ready(requestID: "r")),
            (.denied, .denied),
            (.unavailable, .unavailable),
            (.incompatible, .incompatible),
        ]
        for (status, expected) in mappings {
            var machine = PhoneSessionStateMachine()
            machine.apply(.beginRequest(requestID: "r"))
            machine.apply(.response(requestID: "r", status: status))
            XCTAssertEqual(machine.state, expected)
            machine.apply(.end)
            XCTAssertEqual(machine.state, .ended)
        }
    }

    func testReconnectRequiresExplicitActionAndStaleResponsesAreIgnored() {
        var machine = PhoneSessionStateMachine()
        machine.apply(.beginRequest(requestID: "first"))
        machine.apply(.transportInterrupted)
        XCTAssertEqual(machine.state, .reconnecting)

        machine.apply(.response(requestID: "first", status: .ok))
        XCTAssertEqual(machine.state, .reconnecting, "late response cannot silently resume")
        machine.apply(.response(requestID: "next", status: .ok))
        XCTAssertEqual(machine.state, .reconnecting, "out-of-order response cannot silently resume")

        machine.apply(.reconnectRequested(requestID: "next"))
        XCTAssertEqual(machine.state, .requesting(requestID: "next"))
        machine.apply(.response(requestID: "first", status: .ok))
        XCTAssertEqual(machine.state, .requesting(requestID: "next"))
        machine.apply(.response(requestID: "next", status: .ok))
        XCTAssertEqual(machine.state, .ready(requestID: "next"))
    }

    func testEndIsTerminalAndNonReadyResponsesStayFailClosed() {
        var machine = PhoneSessionStateMachine()
        machine.apply(.end)
        machine.apply(.beginRequest(requestID: "r"))
        XCTAssertEqual(machine.state, .ended)

        for status in [PhoneRemoteStatus.denied, .unavailable, .incompatible] {
            var state = PhoneSessionStateMachine()
            state.apply(.beginRequest(requestID: "r"))
            state.apply(.response(requestID: "r", status: status))
            XCTAssertNotEqual(state.state, .ready(requestID: "r"))
        }
    }

    func testRepeatedAndOutOfOrderLifecycleActionsRemainDeterministic() {
        var machine = PhoneSessionStateMachine()
        machine.apply(.transportInterrupted)
        XCTAssertEqual(machine.state, .idle)
        machine.apply(.beginRequest(requestID: "a"))
        machine.apply(.beginRequest(requestID: "b"))
        XCTAssertEqual(machine.state, .requesting(requestID: "b"))
        machine.apply(.response(requestID: "a", status: .denied))
        XCTAssertEqual(machine.state, .requesting(requestID: "b"))
        machine.apply(.transportInterrupted)
        machine.apply(.transportInterrupted)
        XCTAssertEqual(machine.state, .reconnecting)
        machine.apply(.reconnectRequested(requestID: "c"))
        machine.apply(.reconnectRequested(requestID: "d"))
        XCTAssertEqual(machine.state, .requesting(requestID: "c"))
    }
}
