"""WS-13 P3m: pure mail-brief assembly (jarvis/brief.py). Offline, no I/O."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from jarvis.brief import (
    BODY_TEXT, HEADER_UNAVAILABLE, MAX_HEADLINES, assemble_mail_brief, build_brief_payload,
)

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)   # 10:00 local (EST)


def acct(key, status="ok", state="exact", value=3, error=None, label=None):
    return {"key": key, "label": label or key, "status": status,
            "count": {"state": state, "value": value}, "headlines_complete": True,
            "returned_count": 0, "error": error}


def msg(i, account="gmail", received=None, sender="S", subject="T", unavailable=False):
    received = received or (NOW - timedelta(minutes=i)).isoformat()
    return {"id": f"id{i}", "account": account, "received_at": received, "header_date": None,
            "sender": sender, "subject": subject, "fields_unavailable": unavailable}


def content(accounts, messages=()):
    return {"ok": True, "accounts": accounts, "messages": list(messages)}


def build(c=None, error=None):
    return assemble_mail_brief(c, error=error, now=NOW, tz=TZ)


def by_key(section):
    return {a["key"]: a for a in section["accounts"]}


def test_ok_account_shows_signed_in_and_exact_count():
    s = build(content([acct("gmail"), acct("att", value=0)]))
    a = by_key(s)
    assert a["gmail"]["status"] == "ok" and a["gmail"]["status_text"] == "Signed in"
    assert a["gmail"]["count_text"] == "3"
    assert a["att"]["count_text"] == "0" and a["att"]["count_state"] == "exact"
    assert a["att"]["label"] == "AT&T" and a["gmail"]["label"] == "Gmail"
    assert s["outcome"] == "full"


@pytest.mark.parametrize("status,text", [
    ("ok", "Signed in"), ("partial", "Partly read"), ("timeout", "Timed out"),
    ("not_configured", "Not set up"), ("failed", "Couldn't read"),
])
def test_every_status_has_its_fixed_phrase(status, text):
    s = build(content([acct("gmail", status=status, state="unknown", value=None, error="deadline"),
                       acct("att")]))
    assert by_key(s)["gmail"]["status"] == status
    assert by_key(s)["gmail"]["status_text"] == text


def test_mail_disabled_marks_every_account_disabled():
    s = build({"ok": False, "error": "mail_disabled"})
    assert {a["status"] for a in s["accounts"]} == {"disabled"}
    assert {a["status_text"] for a in s["accounts"]} == {"Mail is turned off"}
    assert s["outcome"] == "all_failed"


@pytest.mark.parametrize("raw,label", [
    ("login_rejected", "login rejected"),
    ("tls", "couldn't connect"), ("network", "couldn't connect"),
    ("server_abort", "couldn't connect"), ("connection_closed", "couldn't connect"),
    ("protocol", "couldn't read"), ("internal", "couldn't read"),
    ("SECRET server text: password=hunter2", "couldn't read"), (None, "couldn't read"),
])
def test_failed_reason_comes_from_a_closed_allowlist(raw, label):
    s = build(content([acct("gmail", status="failed", state="unknown", value=None, error=raw),
                       acct("att")]))
    assert by_key(s)["gmail"]["reason"] == label
    assert "hunter2" not in json.dumps(s)


def test_non_failed_status_has_no_reason():
    s = build(content([acct("gmail", status="timeout", state="unknown", value=None, error="deadline"),
                       acct("att")]))
    assert by_key(s)["gmail"]["reason"] is None


def test_lower_bound_and_unknown_never_render_as_zero():
    s = build(content([acct("gmail", status="partial", state="lower_bound", value=7),
                       acct("att", status="failed", state="unknown", value=None, error="tls")]))
    a = by_key(s)
    assert a["gmail"]["count_text"] == "at least 7" and a["gmail"]["count_state"] == "lower_bound"
    assert a["att"]["count_text"] == "unknown" and a["att"]["count_value"] is None
    assert "0" not in a["att"]["count_text"]


@pytest.mark.parametrize("count", [None, {}, {"state": "exact", "value": None},
                                   {"state": "exact", "value": -1}, {"state": "exact", "value": True},
                                   {"state": "weird", "value": 4}, "3"])
def test_malformed_count_is_unknown_not_zero(count):
    raw = acct("gmail")
    raw["count"] = count
    s = build(content([raw, acct("att")]))
    assert by_key(s)["gmail"]["count_text"] == "unknown"


def test_headlines_newest_first_cap_ten_and_more():
    msgs = [msg(i, subject=f"subj{i}") for i in range(14)]
    s = build(content([acct("gmail"), acct("att")], list(reversed(msgs))))
    assert len(s["headlines"]) == MAX_HEADLINES == 10
    assert [h["subject"] for h in s["headlines"]] == [f"subj{i}" for i in range(10)]
    assert s["more"] == 4


def test_no_more_when_within_cap():
    s = build(content([acct("gmail"), acct("att")], [msg(1), msg(2)]))
    assert s["more"] == 0 and len(s["headlines"]) == 2


def test_headline_fields_and_local_times():
    today = msg(1, account="att", received="2026-11-03T14:30:00+00:00", sender="A", subject="B")
    earlier = msg(2, account="gmail", received="2026-11-01T15:00:00+00:00")
    s = build(content([acct("gmail"), acct("att")], [today, earlier]))
    h = s["headlines"]
    assert h[0] == {"account_label": "AT&T", "sender": "A", "subject": "B", "received_local": "09:30"}
    assert h[1]["received_local"] == "Sun 10:00" and h[1]["account_label"] == "Gmail"


def test_unparseable_time_is_blank_not_invented():
    s = build(content([acct("gmail"), acct("att")], [msg(1, received="garbage")]))
    assert s["headlines"][0]["received_local"] == ""


def test_fields_unavailable_uses_fixed_text():
    s = build(content([acct("gmail"), acct("att")],
                      [msg(1, sender="LEAK", subject="LEAK", unavailable=True)]))
    h = s["headlines"][0]
    assert h["sender"] == h["subject"] == HEADER_UNAVAILABLE == "(header unavailable)"
    assert "LEAK" not in json.dumps(s)


def test_control_characters_stripped_and_length_capped():
    nasty = "a\x00b\x07c\x1b[31m‮d e\nf\tg" + "x" * 500
    s = build(content([acct("gmail"), acct("att")], [msg(1, sender=nasty, subject=nasty)]))
    h = s["headlines"][0]
    for field in (h["sender"], h["subject"]):
        assert len(field) <= 200
        assert all(ord(ch) >= 32 and ord(ch) != 127 for ch in field)
        assert "‮" not in field and " " not in field
    assert h["sender"].startswith("abc[31mde f g")


def test_markdown_is_left_literal():
    raw = "**bold** [link](http://x.test) `code` # h"
    s = build(content([acct("gmail"), acct("att")], [msg(1, subject=raw)]))
    assert s["headlines"][0]["subject"] == raw


@pytest.mark.parametrize("c,error", [
    (None, "failed"), (None, "timeout"), ("not a dict", None), ([], None),
    ({"ok": False, "error": "something_else"}, None), ({"ok": True}, None),
    ({"ok": True, "accounts": "x"}, None), ({"ok": True, "accounts": []}, None),
    ({"ok": False, "error": "unknown_account"}, None),
    (content([acct("gmail"), acct("att")]), "failed"),   # error wins over content
])
def test_registry_or_content_failure_is_an_all_failed_card(c, error):
    s = build(c, error=error)
    assert [a["key"] for a in s["accounts"]] == ["gmail", "att"]
    assert {a["status"] for a in s["accounts"]} == {"failed"}
    assert {a["reason"] for a in s["accounts"]} == {"couldn't read"}
    assert {a["count_text"] for a in s["accounts"]} == {"unknown"}
    assert s["headlines"] == [] and s["outcome"] == "all_failed"
    build_brief_payload(s, result_id="r", ts=1.0)   # still a valid card


def test_outcome_values():
    full = build(content([acct("gmail"), acct("att")]))
    part_one_ok = build(content([acct("gmail"), acct("att", status="failed", state="unknown",
                                                     value=None, error="tls")]))
    part_partial = build(content([acct("gmail", status="partial", state="lower_bound", value=2),
                                  acct("att", status="not_configured", state="unknown", value=None)]))
    none_ok = build(content([acct("gmail", status="timeout", state="unknown", value=None),
                             acct("att", status="not_configured", state="unknown", value=None)]))
    assert (full["outcome"], part_one_ok["outcome"], part_partial["outcome"], none_ok["outcome"]) \
        == ("full", "partial", "partial", "all_failed")


def test_payload_shape_and_fixed_body():
    s = build(content([acct("gmail"), acct("att")], [msg(1, sender="CANARY_S", subject="CANARY_T")]))
    p = build_brief_payload(s, result_id="rid-1", ts=123.5)
    assert p["kind"] == "brief" and p["title"] == "Mail" and p["body"] == BODY_TEXT
    assert p["data_policy"] == "confidential" and p["arrival"] == "requested"
    assert p["result_id"] == "rid-1" and p["revision"] == 1 and p["outcome"] == "full"
    assert p["images"] == [] and p["basemap_images"] == [] and p["links"] == []
    assert (p["agent"], p["run_id"], p["ts"], p["surface"], p["tool"]) == \
        ("Mortimer", "", 123.5, "window", "daily_brief")
    brief = p["brief"]
    assert brief["version"] == 1 and brief["generated_at_local"] == "2026-11-03 10:00"
    (section,) = brief["sections"]
    assert section["source"] == "mail" and "outcome" not in section
    assert set(section) == {"source", "accounts", "headlines", "more"}
    # Canaries live only inside payload["brief"].
    outside = json.dumps({k: v for k, v in p.items() if k != "brief"})
    assert "CANARY" not in outside and "CANARY" in json.dumps(p["brief"])
    json.dumps(p, allow_nan=False)


def test_assembly_is_deterministic():
    c = content([acct("gmail"), acct("att")], [msg(1), msg(2)])
    assert build(c) == build(c)
