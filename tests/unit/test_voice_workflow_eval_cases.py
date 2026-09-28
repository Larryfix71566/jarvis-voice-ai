"""The voice-workflow eval's grader and case file, checked without an LLM
(MORTIMER_VOICE_WORKFLOWS_PLAN.md §7 T3b; Phase 3 cases added 2026-09-25)."""
from __future__ import annotations

from types import SimpleNamespace

import yaml

from tests.evals import voice_workflow_eval as ev

CASES = yaml.safe_load(ev.CASES_PATH.read_text(encoding="utf-8"))
ON = SimpleNamespace(jarvis_voice_workflows_enabled=True)
OFF = SimpleNamespace(jarvis_voice_workflows_enabled=False)


def test_every_case_has_input_and_well_formed_prior():
    assert len(CASES) == 26
    for case in CASES:
        assert case["input"].strip()
        for message in case.get("prior") or []:
            assert isinstance(message, dict) and message["role"] in {"user", "assistant", "tool"}, message


def test_a_replayed_proposal_result_gets_the_live_hooks_guidance():
    tool = next(m for c in CASES for m in c.get("prior") or [] if m["role"] == "tool")
    hooked = ev._hooked(tool, ON)
    assert "voice-human-only-proposal" in hooked["content"]
    assert ev._hooked(tool, OFF)["content"] == tool["content"]
    assert "voice-human-only-proposal" not in tool["content"], "the case file is not mutated"


def test_the_phase3_graders():
    ask, yes, merged = [c for c in CASES if c.get("must_say") or c.get("approve_proposal")]
    assert ev.grade(ask, "It adds httpx to requirements.txt, a human-only file. Approve?", [], [])[0]
    assert not ev.grade(ask, "Here is the command.", [], ["show_commands"])[0]
    assert not ev.grade(ask, "It is open.", [], [])[0]
    assert ev.grade(yes, "It's on screen.", [], ["show_commands"])[0]
    assert not ev.grade(yes, "Done.", [], [])[0]
    assert ev.grade(merged, "Merged; deploy with DEPLOY-MAIN when you're ready.", [], [])[0]
    assert not ev.grade(merged, "Merged. Deploy with DEPLOY-MAIN, then run bundle.sh.", [], [])[0]


def test_the_w12_cases_grade_on_the_timing_tools():
    # Phase 4 W12: the logged "there's no timer or wait capability" replies
    # fail, and so does a bare claim to wait that no tool set up.
    by_from = {c.get("from"): c for c in CASES}
    for turn, tool in ((1865, "progress_updates"), (1456, "progress_updates"), (1344, "follow_up")):
        case = by_from[turn]
        assert case["require_tool"] == tool
        assert ev.grade(case, "Done — every thirty seconds.", [], [tool])[0]
        assert not ev.grade(case, "Waiting sixty seconds, then checking.", [], [])[0]
    logged = by_from[1456]
    assert not ev.grade(logged, "I can't set automatic status updates — there's no timer or "
                                "wait capability.", [], [])[0]
