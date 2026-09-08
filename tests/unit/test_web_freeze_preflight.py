"""Unit tests for the GC4 web-freeze preflight rule (gap-closure plan,
2026-09-04): jarvis/selfedit/service.py's SelfEditService.preflight refuses
a goal that only touches web/ -- interface work goes to macos/MortimerHost
now. Since 2026-09-07 (MORTIMER_SELFEDIT_AUTHORING_PLAN.md SE7) that is a
redirect rather than a dead end: self-edit CAN change the Swift sources,
so the message names target_paths instead of saying "human PR". The
allowlist itself is untouched (web/src/** still reads "allow"); this is a
separate gate in front of it."""
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


def test_mixed_goal_touching_web_is_also_refused():
    """WIDENED 2026-09-05. This previously asserted the opposite: a goal naming
    one web/ path plus one other path passed, because the rule used `all`. That
    made the freeze conditional on how a goal was worded, and it was the only
    reason validation still had to build web/ at all."""
    res = _service().preflight(
        "update web/src/x.ts and jarvis/prompts.py", has_plan=False
    )
    assert res["ok"] is False
    assert "frozen" in res["error"]
    assert "tiers" in res


def test_validation_no_longer_builds_the_frozen_web_client():
    """The regression guard. Reinstating the build would silently reopen the
    npm-failure path to an E1 council, so fail here with the reason instead."""
    src = (REPO_ROOT / "jarvis" / "selfedit" / "service.py").read_text()
    assert '"npm"' not in src, "validation must not build the frozen web client"
    assert "frontend_build" not in src, "the frontend_build check was reinstated"
