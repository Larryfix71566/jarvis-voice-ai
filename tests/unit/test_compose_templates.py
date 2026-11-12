"""Templates for composed answers (C3 plan tests 1 to 12)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from jarvis.bot import compose_templates as ct
from jarvis.bot.compose_schema import MAX_TEXT_CHARS, validate_layout
from jarvis.bot.display import build_display_payload


def built(tool, data, args=None, hints=True):
    return build_display_payload("analyst", "Analyst", tool, args or {}, json.dumps(data),
                                 "run1", layout_hints=hints)


def layout_of(payload, hints=None):
    hints = payload.get("layout_hints") if hints is None else hints
    part = ct.part_for(payload, hints)
    assert part is not None
    layout = ct.build_layout([part], revision=1, complete=True)
    return part, layout


RADAR = {"tiles": [f"https://tile.example/{i}.png" for i in range(12)],
         "basemap_tiles": [f"https://base.example/{i}.png" for i in range(12)],
         "city": "Alpharetta", "ts": 1000}

PAYLOADS = [
    ("web_search", {"answer": "A", "results": [{"url": "https://a.example/x", "title": "A", "snippet": "s"}]}, {"query": "q"}),
    ("get_weather", {"city": "X", "human": "Sunny", "daily": []}, {}),
    ("get_weather_radar", RADAR, {}),
    ("app_create", {"name": "n", "summary": "S", "files": ["a.py"], "repo_url": "https://github.com/x/y"}, {}),
    ("app_write_file", {"app": "a", "path": "p", "summary": "done"}, {}),
    ("git_diff_summary", {"stat": ["a.py | 2 +-"]}, {}),
    ("repo_read_file", {"path": "docs/a.md", "content": "hello"}, {}),
    ("plan_ready", {"plan": "the plan", "goal": "g", "saved_path": "docs/plans/p.md"}, {}),
    ("research_report", {"comparison": "cmp", "urls": ["https://a.example", "https://b.example"],
                         "sites": [{"url": "https://b.example", "ok": False, "error": "boom", "error_kind": "rate"}],
                         "credits_used": 3}, {}),
    ("graph_view", {"image_url": "http://127.0.0.1:7861/api/graph/x.png", "graph": "memory", "summary": "s"}, {}),
]


@pytest.mark.parametrize("tool,data,args", PAYLOADS, ids=[p[0] for p in PAYLOADS])
def test_every_template_builds_a_valid_layout(tool, data, args):
    payload = built(tool, data, args)
    assert payload is not None
    _, layout = layout_of(payload)
    assert validate_layout(layout) == []
    assert layout["blocks"][0]["type"] == "header"


def test_hand_built_payloads_validate():
    for payload in (
        {"tool": "show_commands", "title": "Run", "commands": ["ls"], "note": "n", "expect_output": True,
         "surface": "window"},
        {"tool": "shared_content", "title": "Shared", "text": "answer", "kind": "text", "surface": "drawer"},
        {"tool": "weather_report", "title": "W", "weather": {"a": 1}, "body": "b", "images": [], "links": []},
        {"tool": "repo_read_file", "title": "Project roadmap", "body": "b",
         "roadmap": {"schema": "x"}, "roadmap_timezone": "UTC"},
        {"tool": "repo_read_file", "title": "Roadmap unavailable", "body": "No partial roadmap."},
    ):
        _, layout = layout_of(payload)
        assert validate_layout(layout) == []


def test_plan_ready_keeps_saved_to_in_text_and_has_no_media():
    payload = built("plan_ready", {"plan": "the plan", "saved_path": "docs/plans/p.md"})
    assert payload["images"] == ["saved to docs/plans/p.md"]
    _, layout = layout_of(payload)
    assert not any(b["type"] == "media" for b in layout["blocks"])
    text = next(b for b in layout["blocks"] if b["type"] == "text")
    assert text["text"].endswith("_saved to docs/plans/p.md_")


def test_long_document_is_clipped_to_text_limit():
    payload = built("repo_read_file", {"path": "a.md", "content": "x" * 40_000})
    _, layout = layout_of(payload)
    text = next(b for b in layout["blocks"] if b["type"] == "text")
    assert len(text["text"]) == MAX_TEXT_CHARS
    assert validate_layout(layout) == []


def test_research_report_crawl_issues_list():
    failed = built("research_report", PAYLOADS[8][1])
    _, layout = layout_of(failed)
    lists = [b for b in layout["blocks"] if b["type"] == "list"]
    assert lists[0]["title"] == "Crawl issues"
    assert lists[0]["items"][0] == {"title": "https://b.example", "detail": "boom", "meta": "rate"}
    clean = built("research_report", {"comparison": "cmp", "urls": [], "sites": [{"url": "u", "ok": True}]})
    _, layout = layout_of(clean)
    assert not any(b["type"] == "list" for b in layout["blocks"])


def test_app_create_fifteen_files_caps_list():
    payload = built("app_create", {"name": "n", "summary": "S", "files": [f"f{i}.py" for i in range(15)]})
    _, layout = layout_of(payload)
    block = next(b for b in layout["blocks"] if b["type"] == "list")
    assert block["title"] == "Files"
    assert len(block["items"]) == 12 and block["more_count"] == 3
    text = next(b for b in layout["blocks"] if b["type"] == "text")
    assert text["text"] == "S"


def test_weather_report_wrapper_or_text_plus_media():
    wrapped = {"tool": "weather_report", "title": "W", "weather": {"a": 1}, "body": "b"}
    _, layout = layout_of(wrapped)
    assert [b["type"] for b in layout["blocks"]] == ["header", "weather"]
    plain = {"tool": "weather_report", "title": "W", "body": "b", "images": ["https://t.example/1.png"],
             "basemap_images": [], "links": []}
    _, layout = layout_of(plain)
    assert [b["type"] for b in layout["blocks"]] == ["header", "text", "media"]


def test_radar_nine_images_and_file_urls_give_no_media():
    _, layout = layout_of(built("get_weather_radar", RADAR))
    media = next(b for b in layout["blocks"] if b["type"] == "media")
    assert len(media["images"]) == 9 and len(media["basemap_images"]) == 9
    local = built("get_weather_radar", {"tiles": ["file:///tmp/a.png"], "city": "X"})
    _, layout = layout_of(local)
    assert not any(b["type"] == "media" for b in layout["blocks"])


def test_bad_links_lose_url_keep_label():
    payload = built("web_search", {"results": [
        {"url": "https://u:p@evil.example/x", "title": "Evil"},
        {"url": "javascript:alert(1)", "title": "JS"},
        {"url": "https://ok.example/", "title": "Ok"}]})
    part = ct.part_for(payload)
    layout = ct.build_layout([part], revision=1, complete=True)
    from jarvis.bot.compose_schema import sanitize_layout_urls
    layout = sanitize_layout_urls(layout)
    items = next(b for b in layout["blocks"] if b["type"] == "sources")["items"]
    assert items[0] == {"label": "Evil"} and items[1] == {"label": "JS"}
    assert items[2]["url"] == "https://ok.example/"
    assert validate_layout(layout) == []


def test_show_commands_wrapper_and_legacy_fields():
    payload = {"type": "display", "surface": "window", "tool": "show_commands", "title": "Run",
               "commands": ["ls", "pwd"], "note": "hi", "expect_output": True}
    part, layout = layout_of(payload)
    wrapper = layout["blocks"][1]
    assert wrapper["type"] == "commands" and wrapper["commands"] == ["ls", "pwd"]
    legacy = ct.legacy_fields([part], layout["title"], now=5.0)
    assert legacy["kind"] == "markdown" and legacy["title"] == "Run" and legacy["body"] == ""
    assert legacy["commands"] == ["ls", "pwd"]


def test_shared_content_text_in_block_and_body():
    payload = {"surface": "drawer", "kind": "text", "title": "Shared", "text": "the answer", "tool": "shared_content"}
    part, layout = layout_of(payload)
    block = layout["blocks"][1]
    assert block["type"] == "text" and block["format"] == "plain" and block["text"] == "the answer"
    assert ct.legacy_fields([part], "Shared", now=1.0)["body"] == "the answer"


def test_roadmap_wrapper_and_unavailable_notice():
    _, layout = layout_of({"tool": "repo_read_file", "title": "Project roadmap", "body": "b",
                          "roadmap": {"schema": "x"}, "roadmap_timezone": "America/New_York"})
    assert layout["template"] == "roadmap"
    wrapper = layout["blocks"][1]
    assert wrapper["type"] == "roadmap" and wrapper["roadmap"] == {"schema": "x"}
    assert wrapper["roadmap_timezone"] == "America/New_York"
    _, layout = layout_of({"tool": "repo_read_file", "title": "Roadmap unavailable", "body": "No partial."})
    assert layout["template"] == "notice" and layout["blocks"][1]["type"] == "text"


def test_modules_are_pure():
    root = Path(__file__).resolve().parents[2] / "jarvis" / "bot"
    for name in ("compose.py", "compose_templates.py"):
        src = (root / name).read_text()
        for banned in ("pipecat", "httpx", "requests", "sqlite3", "subprocess"):
            assert not re.search(rf"^\s*(import|from)\s+{banned}\b", src, re.MULTILINE), (name, banned)
    assert "os.environ" not in (root / "compose_templates.py").read_text()
    compose_src = (root / "compose.py").read_text()
    outside = compose_src.replace(
        compose_src.split("def composed_answers_enabled")[1].split("class _Answer")[0], "")
    assert "os.environ" not in outside
