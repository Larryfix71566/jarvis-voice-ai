"""MORTIMER_WORKFLOW_VIEWER_PLAN.md (Larry 2026-09-25): the Python half of the
read-only workflow viewer — `GET /api/workflows`, the `draft` flag (D-V1 A:
listed, never matched) and the view modes voice is told about."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis import workflows as W
from jarvis.voice_workflows import voice_workflows

REPO = Path(__file__).resolve().parents[2]
DRAFTS = {"research-before-modifying", "user-interface-analyst-visibility",
          "user-style-display-output", "user-style-ui-requirement",
          "user-task-website-comparison"}


@pytest.fixture(autouse=True)
def _workflows_on(monkeypatch):
    monkeypatch.delenv("JARVIS_WORKFLOWS_ENABLED", raising=False)


# ---- D-V1: drafts are listed, never matched ---------------------------------


def test_draft_is_read_strictly():
    base = {"name": "x", "when": "compare websites"}
    assert W.parse_workflow({**base, "draft": True}).draft is True
    for not_draft in (None, False, "true", "yes", 1):
        assert W.parse_workflow({**base, "draft": not_draft}).draft is False


def test_exactly_the_five_review_me_files_are_drafts():
    loaded = W.load_workflows()
    assert {w.name for w in loaded if w.draft} == DRAFTS
    for w in loaded:
        text = (REPO / "config" / "workflows" / w.source).read_text(encoding="utf-8")
        assert ("REVIEW ME" in text) == w.draft, w.name


def test_a_draft_never_matches_even_word_for_word():
    loaded = W.load_workflows()
    draft = next(w for w in loaded if w.name == "user-task-website-comparison")
    assert W.match_workflow("analyst", draft.when, loaded) is None
    undrafted = [W.Workflow(**{**draft.__dict__, "draft": False})]
    assert W.match_workflow("analyst", draft.when, undrafted) is not None
    voice_draft = W.Workflow(name="v", when="w", agents=["supervisor"], draft=True)
    assert voice_workflows([voice_draft]) == []


# ---- piece 1: GET /api/workflows -----------------------------------------------


def test_the_endpoint_lists_every_workflow_in_full():
    from jarvis.status.overview import workflows_detail

    body = workflows_detail()
    assert body["ok"] is True and body["enabled"] is True
    assert body["match_threshold"] == W.MATCH_THRESHOLD == 0.35
    items = {w["name"]: w for w in body["workflows"]}
    assert len(items) == len(W.load_workflows()) == 23
    assert sum(w["kind"] == "voice" for w in items.values()) == 7
    assert {n for n, w in items.items() if w["draft"]} == DRAFTS
    voice = items["voice-model-availability"]
    assert voice["kind"] == "voice" and voice["agents"] == ["supervisor"]
    assert voice["priority"] == 14 and voice["triggers"] == ["user"]
    assert max(len(s) for s in voice["steps"]) == 325
    # Hook names only: the regexes never leave the server.
    for w in items.values():
        assert set(w["triggers"]) <= {"user", "result", "reply"}
    rule = items["verify-ui-change-on-screen"]
    assert rule["kind"] == "rule" and rule["agents"] == ["developer"] and len(rule["steps"]) == 4


def test_the_endpoint_says_when_workflows_are_off(monkeypatch):
    from jarvis.status.overview import workflows_detail

    monkeypatch.setenv("JARVIS_WORKFLOWS_ENABLED", "false")
    assert workflows_detail() == {"ok": True, "enabled": False, "match_threshold": 0.35,
                                  "workflows": []}


def test_a_bad_file_is_skipped_not_fatal(tmp_path, monkeypatch):
    from jarvis.status.overview import workflows_detail

    (tmp_path / "good.yaml").write_text("name: good\nwhen: a thing\nsteps: [do it]\n")
    (tmp_path / "bad.yaml").write_text("name: [unclosed\n")
    (tmp_path / "nameless.yaml").write_text("when: no name\n")
    monkeypatch.setattr(W, "WORKFLOWS_DIR", tmp_path)
    body = workflows_detail()
    assert [w["name"] for w in body["workflows"]] == ["good"]


def test_the_sidecar_route_serves_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import jarvis.admin.server as srv
    from jarvis.status.overview import workflows_detail

    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "w.db"))
    assert TestClient(srv.app).get("/api/workflows").json() == workflows_detail()


def test_the_jarviskit_fixture_has_the_endpoints_shape():
    from jarvis.status.overview import workflows_detail

    fixture = json.loads((REPO / "macos/JarvisKit/Tests/JarvisKitTests/admin-fixtures/workflows.json")
                         .read_text(encoding="utf-8"))
    live = workflows_detail()
    assert set(fixture) == set(live)
    assert {frozenset(w) for w in fixture["workflows"]} == {frozenset(w) for w in live["workflows"]}


# ---- piece 3: voice can name the mode ------------------------------------------


def test_console_action_names_the_view_modes_from_the_shared_file():
    from jarvis.bot.console_actions import CONSOLE_ACTION_SCHEMA, VIEW_SET_MODES

    modes = json.loads((REPO / "config/console_view_modes.json").read_text())["view_set"]
    assert tuple(modes) == VIEW_SET_MODES
    assert modes == ["conversation", "results", "atlas", "memory", "workflows"]
    description = CONSOLE_ACTION_SCHEMA["function"]["description"]
    assert "args.mode is one of conversation, results, atlas, memory, workflows" in description
