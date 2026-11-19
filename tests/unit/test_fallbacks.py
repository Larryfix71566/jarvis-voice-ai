"""WS-38 1A: second-path rules (jarvis/fallbacks.py)."""

import json

import httpx
import pytest

from jarvis import fallbacks as fb
from jarvis.toolresult import REASON_CLASSES


@pytest.mark.parametrize("reason,cls", sorted(REASON_CLASSES.items()))
def test_may_fall_back_follows_the_class_table(reason, cls):
    expected = cls in ("transient", "approach") and reason not in fb.NO_BACKUP_REASONS
    assert fb.may_fall_back(reason) is expected


def test_policy_and_unlisted_never_fall_back():
    assert not any(fb.may_fall_back(r) for r, c in REASON_CLASSES.items() if c == "policy")
    for r in (None, "", "made_up_reason", "tavily exploded"):
        assert fb.may_fall_back(r) is False


def test_no_backup_reasons_are_all_listed_and_refused():
    for r in fb.NO_BACKUP_REASONS:
        assert r in REASON_CLASSES
        assert fb.may_fall_back(r) is False


def _status(code):
    req = httpx.Request("POST", "https://x")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError("e", request=req, response=resp)


@pytest.mark.parametrize("exc,reason", [
    (httpx.ReadTimeout("t"), "upstream_timeout"),
    (httpx.ConnectError("c"), "upstream_unreachable"),
    (httpx.RemoteProtocolError("p"), "upstream_unreachable"),
    (_status(401), "upstream_auth_rejected"),
    (_status(403), "upstream_blocked"),
    (_status(429), "upstream_rate_limited"),
    (_status(432), "upstream_quota_exhausted"),
    (_status(433), "upstream_quota_exhausted"),
    (_status(400), "upstream_rejected_request"),
    (_status(404), "upstream_rejected_request"),
    (_status(500), "upstream_error"),
    (_status(503), "upstream_error"),
    (json.JSONDecodeError("m", "d", 0), "upstream_protocol_error"),
    (ValueError("v"), "upstream_protocol_error"),
    (RuntimeError("r"), "upstream_protocol_error"),
])
def test_http_failure_reason(exc, reason):
    got = fb.http_failure_reason(exc)
    assert got == reason
    assert got in REASON_CLASSES


def test_served_validates_codes():
    assert fb.served("web_search", "tavily_rest", "upstream_error").after == "upstream_error"
    with pytest.raises(ValueError):
        fb.served("web_search", "nope")
    with pytest.raises(ValueError):
        fb.served("unknown_tool", "tavily_mcp")
    with pytest.raises(ValueError):
        fb.served("web_search", "tavily_rest", "free text")


def test_mark_and_read_served_round_trip():
    ps = fb.served("web_search", "tavily_rest", "upstream_unreachable")
    body = fb.mark({"results": []}, ps)
    assert body["served_by"] == "tavily_rest"
    assert fb.read_served("web_search", json.dumps(body)) == ps
    primary = fb.mark({}, fb.served("web_search", "tavily_mcp"))
    assert "fallback_after" not in primary
    assert fb.read_served("web_search", json.dumps(primary)).after is None


def test_read_served_rejects_unknown_or_malformed():
    assert fb.read_served("web_search", json.dumps({"served_by": "other"})) is None
    assert fb.read_served("get_weather", json.dumps({"served_by": "tavily_mcp"})) is None
    assert fb.read_served("web_search", "not json") is None
    assert fb.read_served("web_search", "[1]") is None
    ps = fb.read_served("web_search", json.dumps(
        {"served_by": "tavily_rest", "fallback_after": "free text"}))
    assert ps is not None and ps.after is None


def test_log_served_emits_closed_codes():
    class L:
        def info(self, *a):
            self.a = a
    l = L()
    fb.log_served(l, fb.served("web_search", "tavily_mcp"))
    assert l.a[1:] == ("web_search", "tavily_mcp", None)
