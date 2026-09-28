"""Status spec P7: the session_disconnect log line (no behaviour change).

The handler wiring (run_session's on_client_disconnected emits this line)
is asserted in tests/integration/test_bot_wiring.py's disconnect test.
"""
import re

from jarvis.bot.pipeline import session_disconnect_line

LINE = re.compile(
    r"^session_disconnect session=\S+ duration_s=\d+\.\d "
    r"transport=(ws|webrtc) close_code=(\d+|unknown)$")


class FakeStarletteWebSocket:
    """What the FastAPI WebSocket transport hands the handler: no close code."""
    client_state = "DISCONNECTED"


class FakeClientWithCode:
    close_code = 1006


def test_websocket_without_a_close_code_logs_unknown():
    line = session_disconnect_line("abc-123", 42.26, "ws", FakeStarletteWebSocket())
    assert line == ("session_disconnect session=abc-123 duration_s=42.3 "
                    "transport=ws close_code=unknown")
    assert LINE.match(line)


def test_close_code_is_used_when_the_client_exposes_one():
    line = session_disconnect_line("s1", 5, "webrtc", FakeClientWithCode())
    assert line == ("session_disconnect session=s1 duration_s=5.0 "
                    "transport=webrtc close_code=1006")
    assert LINE.match(line)


def test_no_client_and_non_int_codes_are_unknown():
    for client in (None, type("C", (), {"close_code": True})(),
                   type("C", (), {"close_code": "1000"})()):
        assert session_disconnect_line("s", 1.0, "ws", client).endswith(
            "close_code=unknown")
