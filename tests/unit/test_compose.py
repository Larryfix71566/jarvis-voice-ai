"""AnswerComposer, kill switch and pipeline wiring (C3 plan tests 13 to 34)."""
from __future__ import annotations

import asyncio
import copy
import json
import logging

import pytest

from jarvis.bot import compose as compose_mod
from jarvis.bot.compose import MAX_ANSWERS, AnswerComposer, composed_answers_enabled
from jarvis.bot.compose_schema import validate_envelope
from jarvis.bot.display import build_display_payload, layout_hints
from jarvis.bot.pipeline import make_agent_event_handler
from jarvis.bot.research_watcher import ResearchWatcher


def search(title="A", url="https://a.example/x", run_id="r1", **extra):
    payload = {"kind": "markdown", "title": title, "body": f"body {title}", "images": [],
               "basemap_images": [], "links": [{"label": title, "url": url}], "agent": "Analyst",
               "run_id": run_id, "ts": 100.0, "surface": "window", "tool": "web_search"}
    payload.update(extra)
    return payload


def make(sensitive=False):
    counter = iter(range(1, 1000))
    return AnswerComposer(is_sensitive=lambda: sensitive, now=lambda: 50.0,
                          new_id=lambda: f"00000000-0000-4000-8000-{next(counter):012d}")


def test_two_results_one_answer_stable_block_ids():
    c = make()
    first = c.compose(search("A"), request_id="q1")[-1]
    second = c.compose(search("B", url="https://b.example/"), request_id="q1")[-1]
    assert first["answer_id"] == second["answer_id"]
    assert (first["layout"]["revision"], second["layout"]["revision"]) == (1, 2)
    assert (first["answer_revision"], second["answer_revision"]) == (1, 2)
    assert first["layout"]["template"] == "research" and second["layout"]["template"] == "joined"
    ids1 = [b["id"] for b in first["layout"]["blocks"]]
    ids2 = [b["id"] for b in second["layout"]["blocks"]]
    assert set(ids1) - {"sources"} <= set(ids2)
    assert validate_envelope(first) == [] and validate_envelope(second) == []


def test_requests_do_not_mix_and_no_request_is_standalone():
    c = make()
    a = c.compose(search("A"), request_id="q1")[-1]
    b = c.compose(search("B"), request_id="q2")[-1]
    s1 = c.compose(search("S"), request_id=None)[-1]
    s2 = c.compose(search("S"), request_id=None)[-1]
    assert len({a["answer_id"], b["answer_id"], s1["answer_id"], s2["answer_id"]}) == 4
    assert s1["layout"]["complete"] is True and s1["layout"]["revision"] == 1


def test_delegated_result_then_completion():
    c = make()
    c.delegation_started("q1", "run1")
    first = c.compose(search(), request_id="q1")[-1]
    assert first["layout"]["complete"] is False
    c.delegation_finished("q1", "run1")
    done = c.take_completion("q1")
    assert done["answer_id"] == first["answer_id"]
    assert done["layout"]["revision"] == 2 and done["layout"]["complete"] is True
    assert c.take_completion("q1") is None


def test_no_delegation_is_complete_at_once():
    c = make()
    out = c.compose(search(), request_id="q1")[-1]
    assert out["layout"]["complete"] is True
    assert c.take_completion("q1") is None


def test_completion_waits_for_every_delegation():
    c = make()
    c.delegation_started("q1", "a")
    c.delegation_started("q1", "b")
    c.compose(search(), request_id="q1")
    c.delegation_finished("q1", "a")
    assert c.take_completion("q1") is None
    c.delegation_finished("q1", "b")
    assert c.take_completion("q1")["layout"]["complete"] is True


def test_sensitive_turn_passes_through_and_stores_nothing():
    c = make(sensitive=True)
    payload = search()
    out = c.compose(payload, request_id="q1")
    assert out == [payload] and out[0] is payload
    assert "layout" not in payload and "answer_id" not in payload
    assert not c._answers


def test_unset_context_var_is_sensitive_by_default():
    from jarvis.bot.sensitive_turn import current_sensitive_turn

    assert current_sensitive_turn.get() is None
    c = AnswerComposer()  # real fail-closed is_sensitive
    payload = search()
    assert c.compose(payload, request_id="q1")[0] is payload
    assert "layout" not in payload


def test_armed_at_completion_forgets_answer():
    flag = {"s": False}
    c = AnswerComposer(is_sensitive=lambda: flag["s"])
    c.delegation_started("q1", "r")
    c.compose(search(), request_id="q1")
    c.delegation_finished("q1", "r")
    flag["s"] = True
    assert c.take_completion("q1") is None
    assert "q1" not in c._answers


@pytest.mark.parametrize("payload", [
    {"tool": "protected_result", "title": "P", "body": "b", "data_policy": "protected_local"},
    {"tool": "read_clipboard", "title": "C", "content": "secret", "chars": 6},
    {"tool": "daily_brief", "kind": "brief", "title": "Brief", "body": "b", "data_policy": "confidential"},
    {"tool": "commit", "title": "x", "body": "b"},
    {"tool": "repo_write_file", "title": "x", "body": "b"},
    {"tool": "never_heard_of_it", "title": "x", "body": "b"},
    {"tool": "web_search", "title": "x", "body": "b", "answer_id": "x"},
])
def test_pass_through_returns_same_object_unchanged(payload):
    c = make()
    before = copy.deepcopy(payload)
    out = c.compose(payload, request_id="q1")
    assert out == [payload] and out[0] is payload and payload == before


def test_layout_hints_never_leak():
    c = make()
    cases = [(search(layout_hints={"x": 1}), "q1"), (search(layout_hints={"x": 1}), None),
             ({"tool": "read_clipboard", "content": "c", "layout_hints": {}}, "q1"),
             ({"tool": "nope", "layout_hints": {}}, "q1")]
    for payload, rid in cases:
        for out in c.compose(payload, request_id=rid):
            assert "layout_hints" not in out
    sens = make(sensitive=True)
    assert "layout_hints" not in sens.compose(search(layout_hints={}), request_id="q")[0]


def test_ninth_answer_completes_the_oldest():
    c = make()
    c.delegation_started("q0", "r")  # first answer stays open
    first = c.compose(search("0"), request_id="q0")[-1]
    for i in range(1, MAX_ANSWERS):
        c.compose(search(str(i)), request_id=f"q{i}")
    out = c.compose(search("9"), request_id="q9")
    assert len(out) == 2
    assert out[0]["answer_id"] == first["answer_id"] and out[0]["layout"]["complete"] is True
    assert out[1]["layout"]["revision"] == 1


def test_ninth_with_complete_oldest_returns_one_item():
    c = make()
    for i in range(MAX_ANSWERS):
        c.compose(search(str(i)), request_id=f"q{i}")
    assert len(c.compose(search("9"), request_id="q9")) == 1


def test_eighth_result_rolls_over_to_new_answer():
    c = make()
    c.delegation_started("q1", "r")
    outs = [c.compose(search(str(i), url=f"https://x.example/{i}"), request_id="q1")[-1] for i in range(7)]
    assert len({o["answer_id"] for o in outs}) == 1
    assert validate_envelope(outs[-1]) == []
    eighth = c.compose(search("8", url="https://x.example/8"), request_id="q1")
    assert len(eighth) == 2
    assert eighth[0]["answer_id"] == outs[0]["answer_id"] and eighth[0]["layout"]["complete"] is True
    assert eighth[1]["answer_id"] != outs[0]["answer_id"]


def test_oversized_layout_falls_back_to_legacy_fields_with_identity():
    c = make()
    huge = {"tool": "show_commands", "title": "Run", "surface": "window",
            "commands": ["x" * 90_000] * 8, "note": "n", "expect_output": False}
    out = c.compose(huge, request_id="q1")
    assert len(out) == 1 and out[0] is not huge
    assert "layout" not in out[0] and "layout" not in huge
    assert out[0]["answer_id"] and out[0]["answer_revision"] == 1
    assert out[0]["commands"] == huge["commands"]
    assert validate_envelope(out[0]) == []
    assert "q1" in c._answers  # the answer is held, so a later result joins it


def test_over_the_display_ceiling_in_both_forms_is_sent_unchanged():
    c = make()
    huge = {"tool": "show_commands", "title": "Run", "surface": "window",
            "commands": ["x" * 200_000] * 8, "note": "n", "expect_output": False}
    out = c.compose(huge, request_id="q1")
    assert out == [huge] and out[0] is huge
    assert "layout" not in huge and "answer_id" not in huge and "answer_revision" not in huge
    assert not c._answers


def test_oversized_answer_drops_trailing_blocks_with_notice(caplog):
    c = make()
    c.delegation_started("q1", "r")
    caplog.set_level(logging.WARNING)
    for i in range(7):  # 2-byte characters: 7 x 60 KB exceeds the 256 KiB layout limit
        out = c.compose(search(str(i), url=f"https://x.example/{i}", body="\u00e9" * 30_000),
                        request_id="q1")[-1]
    blocks = out["layout"]["blocks"]
    assert blocks[-1] == {"id": "truncated", "type": "text", "format": "plain",
                          "text": "More results were left out to fit."}
    assert len(blocks) < 9
    assert validate_envelope(out) == []
    assert "compose_truncated" in caplog.text


def test_one_result_is_input_plus_answer_id_and_layout():
    c = make()
    payload = search()
    original = copy.deepcopy(payload)
    out = c.compose(payload, request_id="q1")[-1]
    assert {k: v for k, v in out.items() if k not in ("answer_id", "answer_revision", "layout")} == original
    assert out["answer_revision"] == out["layout"]["revision"] == 1
    assert validate_envelope(out) == []


def test_joined_legacy_fields():
    c = make()
    c.compose(search("A", surface="drawer"), request_id="q1")
    out = c.compose(search("B", url="https://b.example/"), request_id="q1")[-1]
    assert out["kind"] == "markdown" and out["tool"] == "composed_answer"
    assert out["title"] == out["layout"]["title"] == "A"
    assert out["body"].index("## A") < out["body"].index("body A") < out["body"].index("## B")
    assert "subject_key" not in out and out["surface"] == "window"
    assert out["links"] == [{"label": "A", "url": "https://a.example/x"},
                            {"label": "B", "url": "https://b.example/"}]


def _break_layouts(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr("jarvis.bot.compose.templates.build_layout", boom)


def test_build_failure_keeps_identity_with_legacy_fields(monkeypatch):
    c = make()
    _break_layouts(monkeypatch)
    payload = search()
    out = c.compose(payload, request_id="q1")
    assert len(out) == 1
    assert "layout" not in out[0] and "layout" not in payload
    assert out[0]["answer_id"] and out[0]["answer_revision"] == 1
    assert out[0]["title"] == "A" and out[0]["tool"] == "web_search"
    assert validate_envelope(out[0]) == []
    assert "q1" in c._answers


def test_standalone_build_failure_gets_new_identity_and_is_not_stored(monkeypatch):
    c = make()
    _break_layouts(monkeypatch)
    a = c.compose(search("A"), request_id=None)[-1]
    b = c.compose(search("B"), request_id=None)[-1]
    assert "layout" not in a and a["answer_revision"] == 1 and b["answer_revision"] == 1
    assert a["answer_id"] != b["answer_id"]
    assert not c._answers


def test_layout_then_fallback_then_layout_keeps_one_answer(monkeypatch):
    c = make()
    c.delegation_started("q1", "r")
    first = c.compose(search("A"), request_id="q1")[-1]
    real = compose_mod.templates.build_layout
    _break_layouts(monkeypatch)
    second = c.compose(search("B", url="https://b.example/"), request_id="q1")[-1]
    assert "layout" not in second
    assert second["answer_id"] == first["answer_id"] and second["answer_revision"] == 2
    assert "## A" in second["body"] and "## B" in second["body"]  # whole answer, both results
    monkeypatch.setattr("jarvis.bot.compose.templates.build_layout", real)
    third = c.compose(search("C", url="https://c.example/"), request_id="q1")[-1]
    assert third["answer_id"] == first["answer_id"] and third["answer_revision"] == 3
    assert third["layout"]["revision"] == 3
    body = " ".join(b.get("text", "") for b in third["layout"]["blocks"])
    assert "body A" in body and "body B" in body and "body C" in body
    assert validate_envelope(third) == []


def test_legacy_failing_too_sends_standalone_and_held_revision_does_not_move(monkeypatch):
    c = make()
    c.delegation_started("q1", "r")
    first = c.compose(search("A"), request_id="q1")[-1]
    assert first["answer_revision"] == 1
    _break_layouts(monkeypatch)
    real_legacy = compose_mod.templates.legacy_fields

    def legacy(parts, title, now=None):
        if len(parts) > 1:  # the whole-answer form fails; a single result still builds
            raise RuntimeError("y")
        return real_legacy(parts, title, now=now)

    monkeypatch.setattr("jarvis.bot.compose.templates.legacy_fields", legacy)
    alone = c.compose(search("B", url="https://b.example/"), request_id="q1")[-1]
    assert "layout" not in alone and alone["answer_revision"] == 1
    assert alone["answer_id"] != first["answer_id"]
    held = c._answers["q1"]
    assert held.answer_id == first["answer_id"] and held.revision == 1 and len(held.parts) == 1


def test_flag_values(monkeypatch):
    assert composed_answers_enabled({}) is False
    assert composed_answers_enabled({"JARVIS_COMPOSED_ANSWERS_ENABLED": "true"}) is True
    for off in ("false", "0", "no", ""):
        assert composed_answers_enabled({"JARVIS_COMPOSED_ANSWERS_ENABLED": off}) is False
    monkeypatch.delenv("JARVIS_COMPOSED_ANSWERS_ENABLED", raising=False)
    assert compose_mod.composed_answers_enabled() is False


def test_display_default_output_unchanged_and_hints_opt_in():
    cases = [("app_create", {"name": "n", "summary": "S", "files": ["a"]}),
             ("research_report", {"comparison": "c", "sites": [{"url": "u", "ok": False}]}),
             ("web_search", {"results": [{"url": "https://a.example", "title": "t"}]})]
    for tool, data in cases:
        plain = build_display_payload("a", "A", tool, {}, json.dumps(data), "r")
        hinted = build_display_payload("a", "A", tool, {}, json.dumps(data), "r", layout_hints=True)
        assert "layout_hints" not in plain
        hinted.pop("layout_hints", None)
        hinted["ts"] = plain["ts"]
        assert hinted == plain
    assert layout_hints("web_search", {}, {}) is None


# --------------------------------------------------------------- wiring

@pytest.fixture()
def sent(monkeypatch):
    messages = []

    async def fake_send(transport, message):
        messages.append(message)

    monkeypatch.setattr("jarvis.bot.pipeline.send_app_message", fake_send)
    return messages


def web_event(run_id="run1"):
    return {"type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
            "run_id": run_id, "tool": "web_search", "ok": True, "latency_ms": 5,
            "arguments": {"query": "q"},
            "result": json.dumps({"answer": "A", "results": [{"url": "https://a.example/x", "title": "T"}]})}


def lifecycle(kind, run_id="run1"):
    return {"type": kind, "agent": "analyst", "display_name": "Analyst", "run_id": run_id, "ok": True,
            "task": "t"}


async def flush():
    for _ in range(5):
        await asyncio.sleep(0)


def request_context(request_id):
    from types import SimpleNamespace

    from jarvis.bot.pipeline import _foreground_request

    return _foreground_request.set(SimpleNamespace(request_id=request_id))


async def test_handler_without_composer_sends_legacy(sent):
    handler = make_agent_event_handler(transport=object())
    handler(web_event())
    await flush()
    display = next(m for m in sent if m["type"] == "display")["display"]
    assert "layout" not in display and "answer_id" not in display and "layout_hints" not in display


async def test_handler_with_composer_orders_display_revisions_then_done(sent):
    composer = make()
    handler = make_agent_event_handler(transport=object(), composer=composer)
    token = request_context("q1")
    try:
        handler(lifecycle("delegate_start"))
        handler(web_event())
        handler(lifecycle("delegate_done"))
        await flush()
    finally:
        from jarvis.bot.pipeline import _foreground_request
        _foreground_request.reset(token)
    kinds = [(m["type"], (m.get("display") or {}).get("layout", {}).get("revision"),
              (m.get("display") or {}).get("layout", {}).get("complete")) for m in sent]
    assert [k[0] for k in kinds] == ["agent", "agent_activity", "display", "display", "agent"]
    assert [k for k in kinds if k[0] == "display"] == [("display", 1, False), ("display", 2, True)]
    assert sent[0]["state"] == "working"
    assert sent[-1]["type"] == "agent" and sent[-1]["state"] == "done"


async def test_handler_lone_weather_half_is_revision_one_complete(sent):
    composer = make()
    handler = make_agent_event_handler(transport=object(), composer=composer)
    token = request_context("q1")
    try:
        handler(lifecycle("delegate_start"))
        handler({"type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
                 "run_id": "run1", "tool": "get_weather_radar", "ok": True, "arguments": {},
                 "result": json.dumps({"tiles": ["https://t.example/1.png"], "city": "X", "ts": 1})})
        handler(lifecycle("delegate_done"))
        await flush()
    finally:
        from jarvis.bot.pipeline import _foreground_request
        _foreground_request.reset(token)
    displays = [m["display"] for m in sent if m["type"] == "display"]
    assert len(displays) == 1
    assert displays[0]["layout"]["revision"] == 1 and displays[0]["layout"]["complete"] is True


async def test_handler_protected_event_sends_no_display(sent):
    composer = make()
    handler = make_agent_event_handler(transport=object(), composer=composer)
    handler({"type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
             "run_id": "run1", "tool": "web_search", "ok": True, "latency_ms": 1})
    await flush()
    assert not [m for m in sent if m["type"] == "display"]


async def test_research_watcher_layout_hints_flag():
    pushed = []

    async def push(payload):
        pushed.append(payload)

    async def speak(_text):
        return None

    job = {"ok": True, "job": {"state": "done", "started_at": 1, "comparison": "cmp", "urls": [],
                               "sites": [], "credits_used": 1}}

    async def fetch():
        return job

    for flag in (True, False):
        watcher = ResearchWatcher(speak, push, lambda: True, fetch_job=fetch, layout_hints=flag)
        await watcher.tick_once()
    assert "layout_hints" in pushed[0] and "layout_hints" not in pushed[1]


# ------------------------------------- origin end to end (contract 1.5 rule 10)

class _Recorder:
    """A transport whose output() records the frames the real sender writes."""

    def __init__(self):
        self.frames = []

    def output(self):
        return self

    async def send_message(self, frame):
        self.frames.append(frame.message)

    def displays(self):
        return [m["data"]["display"] for m in self.frames
                if m.get("data", {}).get("type") == "display"]


def _in_request(request_id, fn):
    from types import SimpleNamespace

    from jarvis.bot.pipeline import _foreground_request

    token = _foreground_request.set(
        SimpleNamespace(request_id=request_id, sequence=1) if request_id else None)
    try:
        fn()
    finally:
        _foreground_request.reset(token)


def _check_origins(displays):
    """Every display with an answer_id is stamped with the request that answer was created under."""
    created = {}
    for d in displays:
        created.setdefault(d["answer_id"], d.get("origin_request_id"))
    for d in displays:
        assert d.get("origin_request_id") == created[d["answer_id"]], d
    return created


async def test_origin_of_every_display_is_the_request_its_answer_was_created_under():
    transport = _Recorder()
    handler = make_agent_event_handler(transport=transport, composer=make())
    for rid in ("q1", "q2"):  # two foreground requests, interleaved delegations
        _in_request(rid, lambda rid=rid: handler(lifecycle("delegate_start", f"run-{rid}")))
    for rid in ("q2", "q1"):
        _in_request(rid, lambda rid=rid: handler(web_event(f"run-{rid}")))
    for rid in ("q1", "q2"):
        _in_request(rid, lambda rid=rid: handler(lifecycle("delegate_done", f"run-{rid}")))
    await flush()
    displays = transport.displays()
    assert len(displays) == 4  # two revisions each (incomplete, then complete)
    created = _check_origins(displays)
    assert sorted(created.values()) == ["q1", "q2"]


async def test_evicted_answers_closing_revision_keeps_its_own_origin():
    transport = _Recorder()
    handler = make_agent_event_handler(transport=transport, composer=make())
    for i in range(MAX_ANSWERS + 1):  # the ninth answer pushes the oldest out
        rid = f"q{i}"
        _in_request(rid, lambda rid=rid: handler(lifecycle("delegate_start", f"run-{rid}")))
        _in_request(rid, lambda rid=rid: handler(web_event(f"run-{rid}")))
        await flush()
    displays = transport.displays()
    created = _check_origins(displays)
    assert len(created) == MAX_ANSWERS + 1
    first_answer = displays[0]["answer_id"]
    closing = [d for d in displays if d["answer_id"] == first_answer]
    assert [d["answer_revision"] for d in closing] == [1, 2]
    assert closing[1]["layout"]["complete"] is True
    assert {d["origin_request_id"] for d in closing} == {"q0"}
    # the closing revision was sent while q8 was the foreground request
    assert displays[-1]["origin_request_id"] == "q8"


async def test_standalone_answer_has_no_origin():
    transport = _Recorder()
    handler = make_agent_event_handler(transport=transport, composer=make())
    _in_request(None, lambda: handler(web_event("run-x")))
    await flush()
    displays = transport.displays()
    assert len(displays) == 1 and displays[0]["answer_id"] and "origin_request_id" not in displays[0]


def test_compose_display_helper_off_and_on():
    from jarvis.bot.pipeline import _compose_display

    payload = {"surface": "window", "tool": "plan_ready", "title": "Plan", "body": "b", "images": [],
               "links": [], "agent": "Developer", "run_id": None, "ts": 1.0, "kind": "markdown"}
    assert _compose_display(None, payload)[0] is payload
    out = _compose_display(make(), copy.deepcopy(payload))
    # watcher context: no foreground request, so a stand-alone complete answer
    assert len(out) == 1 and out[0]["layout"]["complete"] is True and out[0]["layout"]["revision"] == 1


def test_direct_tool_payloads_compose_or_pass_through():
    c = make()
    clip = {"type": "display", "surface": "window", "tool": "read_clipboard", "title": "c", "content": "s"}
    assert c.compose(clip, request_id="q")[0] is clip
    cmds = {"type": "display", "surface": "window", "tool": "show_commands", "title": "t",
            "commands": ["ls"], "note": "", "expect_output": False}
    out = c.compose(cmds, request_id="q")[-1]
    assert out["commands"] == ["ls"] and out["layout"]["blocks"][1]["type"] == "commands"
    local = {"surface": "window", "tool": "weather_report", "kind": "weather", "title": "W", "body": "",
             "weather": {"a": 1}, "images": [], "links": [], "subject_key": "k",
             "data_policy": "approved_external"}
    out = c.compose(local, request_id="q2")[-1]
    assert out["subject_key"] == "k" and out["data_policy"] == "approved_external" and out["kind"] == "weather"


# --------------------------------------------------------------- golden (plan test 30)

GOLDEN_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "fixtures" / "compose"


def _golden_cases():
    samples = json.loads((GOLDEN_DIR / "legacy_display_samples.json").read_text())
    golden = json.loads((GOLDEN_DIR / "legacy_display_golden.json").read_text())
    assert len(samples) == len(golden)
    return list(zip(samples, golden))


@pytest.mark.parametrize("sample,expected", _golden_cases(),
                         ids=lambda v: v.get("tool", "") if isinstance(v, dict) and "data" in v else "")
def test_flag_off_payload_matches_pre_c3_golden(sample, expected):
    """legacy_display_golden.json was produced by the pre-C3 display.py (the
    C0 types branch, a6784c5) from legacy_display_samples.json. With no
    composer, today's code must produce the same payload, key for key."""
    payload = build_display_payload("analyst", "Analyst", sample["tool"], sample["arguments"],
                                    json.dumps(sample["data"]), "run-golden")
    if isinstance(payload, dict):
        payload.pop("ts", None)
        payload = json.loads(json.dumps(payload, sort_keys=True))
    assert payload == expected


@pytest.mark.parametrize("sample,expected", [c for c in _golden_cases() if c[1] is not None],
                         ids=lambda v: v.get("tool", "") if isinstance(v, dict) and "data" in v else "")
async def test_handler_without_composer_sends_golden_payload(sent, sample, expected):
    handler = make_agent_event_handler(transport=object())
    handler({"type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
             "run_id": "run-golden", "tool": sample["tool"], "ok": True, "latency_ms": 1,
             "arguments": sample["arguments"], "result": json.dumps(sample["data"])})
    await flush()
    displays = [m["display"] for m in sent if m["type"] == "display"]
    if sample["tool"] in ("get_weather", "get_weather_radar"):
        # the weather merger holds a lone half until the run ends
        handler(lifecycle("delegate_done", "run-golden"))
        await flush()
        displays = [m["display"] for m in sent if m["type"] == "display"]
        assert displays and all("layout" not in d and "answer_id" not in d for d in displays)
        return
    assert len(displays) == 1
    got = dict(displays[0])
    got.pop("ts", None)
    assert json.loads(json.dumps(got, sort_keys=True)) == expected
