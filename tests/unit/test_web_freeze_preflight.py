"""Unit tests for the GC4 web-freeze preflight rule (gap-closure plan,
2026-09-04): jarvis/selfedit/service.py's SelfEditService.preflight refuses
a goal that only touches web/ -- interface work goes to macos/MortimerHost
now, which is a human PR. The allowlist itself is untouched (web/src/**
still reads "allow"); this is a separate gate in front of it."""
from __future__ import annotations

from pathlib import Path

from jarvis.selfedit.service import SelfEditService

REPO_ROOT = Path(__file__).resolve().parents[2]


def _service() -> SelfEditService:
    return SelfEditService(repo_root=REPO_ROOT)


def test_goal_touching_only_web_is_refused():
    res = _service().preflight("change web/src/App.tsx colours", has_plan=False)
    assert res["ok"] is False
    assert "frozen" in res["error"]
    # jarvis/admin/server.py:795 reads flight["tiers"] on refusal -- must survive.
    assert "tiers" in res


def test_mixed_goal_is_not_refused_by_this_rule():
    res = _service().preflight(
        "update web/src/x.ts and jarvis/prompts.py", has_plan=False
    )
    # Not every named path is under web/, so this rule doesn't fire; both
    # paths are allow-listed routine paths, so the ordinary tier logic
    # passes it through too.
    assert res["ok"] is True
    assert res["tiers"]["core"] == []
    assert res["tiers"]["denied"] == []
