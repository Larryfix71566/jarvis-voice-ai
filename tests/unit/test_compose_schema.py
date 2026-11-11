"""Composed-answer layout schema (contract section 1, section 6)."""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

import jarvis.bot.compose_schema as cs
from jarvis.bot.compose_schema import (
    LayoutError,
    compact_size,
    layout_size,
    require_valid_layout,
    sanitize_layout_urls,
    sanitize_url,
    truncate_layout,
    validate_envelope,
    validate_layout,
)

ANSWER_ID = "00000000-0000-4000-8000-0000000000a1"


def sample() -> dict:
    """The layout of contract 1.3, as written (weather object abbreviated there too)."""
    return {
        "version": 1, "revision": 2, "template": "brief_and_weather",
        "title": "This morning and tomorrow",
        "summary": "Six new messages, two worth a look. Rain is likely tomorrow after 2 PM.",
        "complete": True,
        "blocks": [
            {"id": "b1", "type": "header", "title": "This morning and tomorrow",
             "summary": "Six new messages, two worth a look. Rain is likely tomorrow after 2 PM.",
             "agents": [{"name": "Librarian", "latency_ms": 600}, {"name": "Analyst", "latency_ms": 2400}]},
            {"id": "b2", "type": "stats", "items": [
                {"value": "6", "label": "new messages"},
                {"value": "2", "label": "flagged", "tone": "approval"},
                {"value": "70%", "label": "rain tomorrow, peak 2 PM"},
                {"value": "64° / 51°", "label": "high / low"}]},
            {"id": "b3", "type": "list", "title": "Inbox · since 6 PM yesterday",
             "items": [{"title": "Dana Reyes", "detail": "Contract redlines", "meta": "7:12 AM", "tone": "approval"}],
             "more_count": 1, "source": {"tool": "daily_brief", "run_id": "4f1c0a2e"}},
            {"id": "b4", "type": "chart", "title": "Rain chance tomorrow", "chart": "bar", "unit": "%",
             "points": [{"label": "12 PM", "value": 40}, {"label": "2 PM", "value": 70, "highlight": True}],
             "a11y": "Rain chance peaks at 70 percent at 2 PM."},
            {"id": "b5", "type": "weather", "weather": {"schema": "..."},
             "source": {"tool": "weather_report", "run_id": "9b7d11c3"}},
            {"id": "b6", "type": "sources", "items": [{"label": "weather.gov", "url": "https://www.weather.gov/"}]},
            {"id": "b7", "type": "actions", "items": [
                {"id": "a1", "label": "Hourly detail", "kind": "ask", "text": "Show the hourly detail for tomorrow."},
                {"id": "a2", "label": "Send to second screen", "kind": "console", "action": "display_show"}]},
        ],
    }


def block(layout, bid):
    return next(b for b in layout["blocks"] if b["id"] == bid)


def test_contract_example_validates_as_written():
    assert validate_layout(sample()) == []
    assert require_valid_layout(sample())["version"] == 1


def test_every_block_type_has_a_valid_example():
    layout = sample()
    layout["blocks"] += [
        {"id": "t", "type": "text", "format": "markdown", "text": "hello"},
        {"id": "m", "type": "media", "images": ["https://a.example/1.png"],
         "basemap_images": ["https://a.example/2.png"], "caption": "Radar", "a11y": "Radar tiles"},
        {"id": "br", "type": "brief", "brief": {"x": 1}},
        {"id": "rm", "type": "roadmap", "roadmap": {"x": 1}, "roadmap_timezone": "America/New_York"},
        {"id": "cm", "type": "commands", "commands": ["ls"], "note": "run it", "expect_output": True},
        {"id": "g", "type": "graph", "image_url": "http://127.0.0.1:7861/graph.png", "summary": "g"},
    ]
    assert validate_layout(layout) == []


# ---- one failing case per rule

def mutated(fn):
    layout = sample()
    fn(layout)
    return validate_layout(layout)


@pytest.mark.parametrize("name,fn", [
    ("version", lambda l: l.update(version=2)),
    ("version bool", lambda l: l.update(version=True)),
    ("revision 0", lambda l: l.update(revision=0)),
    ("revision str", lambda l: l.update(revision="1")),
    ("template empty", lambda l: l.update(template="")),
    ("template 41", lambda l: l.update(template="t" * 41)),
    ("title 121", lambda l: l.update(title="t" * 121)),
    ("summary 601", lambda l: l.update(summary="s" * 601)),
    ("complete not bool", lambda l: l.update(complete=1)),
    ("blocks empty", lambda l: l.update(blocks=[])),
    ("blocks not list", lambda l: l.update(blocks={})),
    ("extra layout key", lambda l: l.update(extra=1)),
    ("missing summary", lambda l: l.pop("summary")),
    ("block extra key", lambda l: block(l, "b2").update(zzz=1)),
    ("block id dup", lambda l: block(l, "b2").update(id="b1")),
    ("block id 41", lambda l: block(l, "b2").update(id="i" * 41)),
    ("block id empty", lambda l: block(l, "b2").update(id="")),
    ("unknown type", lambda l: block(l, "b2").update(type="carousel")),
    ("a11y 301", lambda l: block(l, "b2").update(a11y="a" * 301)),
    ("source extra", lambda l: block(l, "b3")["source"].update(url="x")),
    ("source run_id 121", lambda l: block(l, "b3")["source"].update(run_id="r" * 121)),
    ("source tool 81", lambda l: block(l, "b3")["source"].update(tool="t" * 81)),
    ("header not first", lambda l: l["blocks"].append({"id": "h2", "type": "header", "title": "t", "summary": ""})),
    ("header title 121", lambda l: block(l, "b1").update(title="t" * 121)),
    ("header agents 7", lambda l: block(l, "b1").update(agents=[{"name": "a"}] * 7)),
    ("agent latency neg", lambda l: block(l, "b1")["agents"][0].update(latency_ms=-1)),
    ("stats 0 items", lambda l: block(l, "b2").update(items=[])),
    ("stats 5 items", lambda l: block(l, "b2").update(items=[{"value": "1", "label": "l"}] * 5)),
    ("stats value 17", lambda l: block(l, "b2")["items"][0].update(value="v" * 17)),
    ("stats label 61", lambda l: block(l, "b2")["items"][0].update(label="l" * 61)),
    ("stats tone", lambda l: block(l, "b2")["items"][0].update(tone="loud")),
    ("list 13 items", lambda l: block(l, "b3").update(items=[{"title": "t"}] * 13)),
    ("list detail 241", lambda l: block(l, "b3")["items"][0].update(detail="d" * 241)),
    ("list meta 41", lambda l: block(l, "b3")["items"][0].update(meta="m" * 41)),
    ("list more_count neg", lambda l: block(l, "b3").update(more_count=-1)),
    ("list more_count bool", lambda l: block(l, "b3").update(more_count=True)),
    ("chart missing a11y", lambda l: block(l, "b4").pop("a11y")),
    ("chart type", lambda l: block(l, "b4").update(chart="line")),
    ("chart 1 point", lambda l: block(l, "b4").update(points=[{"label": "a", "value": 1}])),
    ("chart 49 points", lambda l: block(l, "b4").update(points=[{"label": "a", "value": 1}] * 49)),
    ("chart label 17", lambda l: block(l, "b4")["points"][0].update(label="l" * 17)),
    ("chart value nan", lambda l: block(l, "b4")["points"][0].update(value=math.nan)),
    ("chart value inf", lambda l: block(l, "b4")["points"][0].update(value=math.inf)),
    ("chart value bool", lambda l: block(l, "b4")["points"][0].update(value=True)),
    ("chart value str", lambda l: block(l, "b4")["points"][0].update(value="1")),
    ("sources 13", lambda l: block(l, "b6").update(items=[{"label": "x"}] * 13)),
    ("sources label 121", lambda l: block(l, "b6")["items"][0].update(label="l" * 121)),
    ("actions 5", lambda l: block(l, "b7").update(items=[{"id": "a", "label": "l", "kind": "ask", "text": "t"}] * 5)),
    ("action label 41", lambda l: block(l, "b7")["items"][0].update(label="l" * 41)),
    ("action ask text 401", lambda l: block(l, "b7")["items"][0].update(text="t" * 401)),
    ("action ask no text", lambda l: block(l, "b7")["items"][0].pop("text")),
    ("action kind", lambda l: block(l, "b7")["items"][0].update(kind="approve")),
    ("action console unknown", lambda l: block(l, "b7")["items"][1].update(action="approve")),
    ("action console extra key", lambda l: block(l, "b7")["items"][1].update(text="t")),
    ("action ask with action", lambda l: block(l, "b7")["items"][0].update(action="help")),
    ("wrapper not object", lambda l: block(l, "b5").update(weather=[])),
    ("wrapper missing", lambda l: block(l, "b5").pop("weather")),
])
def test_one_failing_case_per_rule(name, fn):
    assert mutated(fn), name


def test_text_block_limits():
    layout = sample()
    layout["blocks"].append({"id": "t", "type": "text", "format": "markdown", "text": "x" * 30_000})
    assert validate_layout(layout) == []
    block(layout, "t")["text"] = "x" * 30_001
    assert validate_layout(layout)
    block(layout, "t").update(text="ok", format="html")
    assert validate_layout(layout)


def test_media_limits_and_a11y_required():
    ok = {"id": "m", "type": "media", "images": [f"https://a.example/{i}.png" for i in range(9)], "a11y": "Radar"}
    layout = sample()
    layout["blocks"].append(ok)
    assert validate_layout(layout) == []
    ok["images"].append("https://a.example/10.png")
    assert validate_layout(layout)
    ok["images"] = ["https://a.example/1.png"]
    del ok["a11y"]
    assert validate_layout(layout)
    ok.update(a11y="x", caption="c" * 241)
    assert validate_layout(layout)


def test_24_blocks_pass_25_fail():
    layout = sample()
    layout["blocks"] = [layout["blocks"][0]] + [
        {"id": f"t{i}", "type": "text", "format": "plain", "text": "x"} for i in range(23)]
    assert validate_layout(layout) == []
    layout["blocks"].append({"id": "t99", "type": "text", "format": "plain", "text": "x"})
    assert any("1 to 24" in p for p in validate_layout(layout))


def test_non_dict_inputs_never_raise():
    for value in (None, [], "x", 1):
        assert validate_layout(value)
    layout = sample()
    layout["blocks"] = [1, None, "x"]
    assert validate_layout(layout)


def test_require_valid_layout_raises_with_problems():
    layout = sample()
    layout["version"] = 9
    with pytest.raises(LayoutError) as e:
        require_valid_layout(layout)
    assert e.value.problems and isinstance(e.value, ValueError)


# ---- URL rule (1.9.5)

@pytest.mark.parametrize("url,ok", [
    ("https://www.weather.gov/", True),
    ("http://example.com/a?b=c", True),
    ("http://127.0.0.1:7861/graph.png", True),
    ("https://user:pw@example.com/", False),
    ("https://user@example.com/", False),
    ("javascript:alert(1)", False),
    ("data:image/png;base64,AAAA", False),
    ("file:///etc/passwd", False),
    ("ftp://example.com/", False),
    ("//example.com/x", False),
    ("/relative/path", False),
    ("https://", False),
    ("https://exa mple.com/", False),
    ("", False),
    (None, False),
    ("https://example.com/" + "a" * 2100, False),
])
def test_sanitize_url(url, ok):
    assert (sanitize_url(url) is not None) is ok


def test_validate_rejects_bad_urls_and_sanitizer_drops_them():
    layout = sample()
    block(layout, "b6")["items"] = [
        {"label": "good", "url": "https://www.weather.gov/"},
        {"label": "creds", "url": "https://u:p@evil.example/"},
        {"label": "js", "url": "javascript:alert(1)"},
        {"label": "nolink"},
    ]
    layout["blocks"].append({"id": "m", "type": "media", "a11y": "radar", "images": [
        "https://a.example/ok.png", "data:image/png;base64,AAAA", "file:///x.png"]})
    layout["blocks"].append({"id": "m2", "type": "media", "a11y": "radar", "images": ["javascript:x"]})
    layout["blocks"].append({"id": "g", "type": "graph", "image_url": "file:///x"})
    assert len(validate_layout(layout)) >= 5
    before = copy.deepcopy(layout)
    clean = sanitize_layout_urls(layout)
    assert layout == before, "input must not be mutated"
    assert validate_layout(clean) == []
    assert [i.get("url") for i in block(clean, "b6")["items"]] == ["https://www.weather.gov/", None, None, None]
    assert block(clean, "m")["images"] == ["https://a.example/ok.png"]
    assert all(b["id"] not in ("m2", "g") for b in clean["blocks"])


# ---- envelope (1.2)

def payload(**kw):
    p = {"kind": "markdown", "title": "t", "body": "b", "answer_id": ANSWER_ID, "answer_revision": 2,
         "layout": sample()}
    p.update(kw)
    return p


def test_envelope():
    assert validate_envelope({"kind": "text", "title": "t", "body": "b"}) == []
    assert validate_envelope(payload()) == []
    assert validate_envelope(payload(answer_id="nope"))
    assert validate_envelope(payload(answer_id=ANSWER_ID.upper())) == []
    bare = payload()
    del bare["answer_id"]
    assert validate_envelope(bare)
    # answer_id and answer_revision travel together (1.2)
    no_rev = payload()
    del no_rev["answer_revision"]
    assert validate_envelope(no_rev)
    only_rev = payload()
    del only_rev["answer_id"]
    assert validate_envelope(only_rev)
    # id + revision with no layout is a legacy-fields revision that keeps identity (1.5 rule 11)
    no_layout = payload()
    del no_layout["layout"]
    assert validate_envelope(no_layout) == []
    # a layout needs both
    layout_only = payload()
    del layout_only["answer_id"], layout_only["answer_revision"]
    assert validate_envelope(layout_only)
    # layout.revision must equal answer_revision
    assert validate_envelope(payload(answer_revision=3))
    assert validate_envelope(payload(answer_revision=1))
    # revision is an int >= 1 and not a bool
    for bad_rev in (True, 0, -1, "2", 2.0, None):
        assert validate_envelope(payload(answer_revision=bad_rev)), bad_rev
    assert validate_envelope({"kind": "text", "title": "t", "body": "b", "answer_id": ANSWER_ID,
                              "answer_revision": 1}) == []
    assert validate_envelope({"kind": "text", "title": "t", "body": "b", "answer_id": ANSWER_ID,
                              "answer_revision": True})
    legacy_missing = payload()
    del legacy_missing["body"]
    assert validate_envelope(legacy_missing)
    bad_layout = payload()
    bad_layout["layout"]["version"] = 3
    assert validate_envelope(bad_layout)
    assert validate_envelope(None)


# ---- size and truncation (1.10)

def big_text_layout(n_blocks: int, chars: int = 30_000) -> dict:
    layout = sample()
    layout["blocks"] = [layout["blocks"][0]] + [
        {"id": f"t{i}", "type": "text", "format": "plain", "text": "x" * chars} for i in range(n_blocks)]
    return layout


def test_layout_that_fits_is_returned_unchanged_copy():
    layout = sample()
    out = truncate_layout(layout)
    assert out == layout and out is not layout


def test_oversized_layout_drops_trailing_blocks_and_adds_notice():
    layout = big_text_layout(12)  # about 360 KB of text, over the 256 KiB layout limit
    assert layout_size(layout) > cs.MAX_LAYOUT_BYTES
    out = truncate_layout(layout)
    assert out is not None
    assert validate_layout(out) == []
    assert layout_size(out) <= cs.MAX_LAYOUT_BYTES
    assert out["blocks"][0] == layout["blocks"][0]
    assert out["blocks"][-1]["type"] == "text" and out["blocks"][-1]["text"] == cs.TRUNCATION_NOTICE
    kept = out["blocks"][:-1]
    assert kept == layout["blocks"][:len(kept)] and len(kept) < len(layout["blocks"])
    # the largest fit: one more block would not fit
    assert len(kept) >= 2


def test_over_24_blocks_is_cured_by_dropping():
    layout = sample()
    layout["blocks"] = [layout["blocks"][0]] + [
        {"id": f"t{i}", "type": "text", "format": "plain", "text": "x"} for i in range(30)]
    out = truncate_layout(layout)
    assert out is not None and len(out["blocks"]) == 24
    assert out["blocks"][-1]["text"] == cs.TRUNCATION_NOTICE


def test_falls_back_to_none_when_nothing_fits():
    layout = sample()
    layout["blocks"] = [{"id": "t", "type": "text", "format": "plain", "text": "x" * 30_000}]
    assert truncate_layout(layout, max_bytes=1000) is None
    # even the header alone plus notice does not fit a tiny ceiling
    assert truncate_layout(sample(), max_bytes=50) is None


def test_whole_message_ceiling_counts_the_envelope():
    layout = big_text_layout(2)
    size = compact_size(layout)
    assert truncate_layout(layout, envelope_bytes=0) is not None
    out = truncate_layout(layout, envelope_bytes=cs.MAX_DISPLAY_MESSAGE_BYTES - size + 1)
    assert out is None or compact_size(out) + (cs.MAX_DISPLAY_MESSAGE_BYTES - size + 1) <= cs.MAX_DISPLAY_MESSAGE_BYTES


def test_wrapper_data_is_not_cut_and_not_counted_against_layout_limit():
    layout = sample()
    block(layout, "b5")["weather"] = {"blob": "w" * (300 * 1024)}
    assert layout_size(layout) < cs.MAX_LAYOUT_BYTES < layout_size(layout, include_wrappers=True)
    assert validate_layout(layout) == []
    out = truncate_layout(layout)
    assert out == layout
    # a ceiling that excludes it drops the block rather than truncating inside it
    small = truncate_layout(layout, envelope_bytes=0, max_message_bytes=100 * 1024)
    assert small is None or all(b.get("weather", {}).get("blob", "w" * 300 * 1024) == "w" * 300 * 1024
                                for b in small["blocks"])


def test_roadmap_wrapper_over_1_mib_is_invalid():
    layout = sample()
    layout["blocks"].append({"id": "rm", "type": "roadmap", "roadmap": {"x": "y" * (1024 * 1024 + 10)}})
    assert any("roadmap" in p for p in validate_layout(layout))


def test_invalid_for_non_size_reasons_is_none():
    layout = sample()
    layout["version"] = 5
    assert truncate_layout(layout) is None
    assert truncate_layout("nope") is None  # type: ignore[arg-type]


def test_truncation_does_not_mutate_input():
    layout = big_text_layout(12)
    before = copy.deepcopy(layout)
    truncate_layout(layout)
    assert layout == before


# ---- module boundaries

def test_module_is_pure():
    source = Path(cs.__file__).read_text(encoding="utf-8")
    for forbidden in ("import pipecat", "from pipecat", "subprocess", "requests", "httpx", "sqlite3", "os.environ"):
        assert forbidden not in source, f"compose_schema grew {forbidden}"


# deferred to C3: "every v1 template validates" needs the templates of 1.6/1.7,
# which are not built here.
