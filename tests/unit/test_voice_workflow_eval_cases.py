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
    assert len(CASES) == 31  # 29 prior cases + 2 WS-17 prior-history regressions
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



def test_the_ws15_cases_require_local_weather():
    # WS-15: current weather with no place named must be answered by
    # local_weather (this device's location), never delegated with a
    # remembered place. A named place stays with the analyst.
    weather = [c for c in CASES if c.get("require_tool") == "local_weather"]
    assert [c["input"] for c in weather] == [
        "What's the weather?", "Do I need an umbrella today?",
        "What does the week look like weather-wise?"]
    for case in weather:
        assert ev.grade(case, "It's 75 and clear at Folly Beach.", [], ["local_weather"])[0]
        assert not ev.grade(case, "It's 75 and clear in Spartanburg.", ["analyst"], [])[0]
    control = next(c for c in CASES if c["input"] == "What's the weather in Alpharetta?")
    assert control["expect_any"] == ["analyst"]


def test_numbered_result_requires_inventory_then_selection_not_just_view_change():
    case = next(c for c in CASES if c.get("id") == "ws17-numbered-result")
    assert not ev.grade(case, "Opened.", [], ["console_action"], ["view_set"])[0]
    assert not ev.grade(case, "Opened.", [], ["console_action"], ["result_select", "inventory"])[0]
    assert ev.grade(case, "Opened.", [], ["console_action"], ["inventory", "result_select"])[0]


def test_repeat_weather_requires_actual_delegation_even_for_a_plausible_answer():
    case = next(c for c in CASES if c.get("id") == "ws17-repeat-weather")
    assert not ev.grade(case, "Sunny and 75 degrees.", [], [])[0]
    assert not ev.grade(case, "Sunny and 75 degrees.", [], ["delegate_task"])[0]
    assert ev.grade(case, "Sunny and 75 degrees.", ["analyst"], ["delegate_task"])[0]


def test_ws17_routing_only_harness_never_dispatches_real_tools(monkeypatch, tmp_path):
    import asyncio
    from tests.unit.test_orchestrator import FakeLLM, make_settings
    from jarvis.db import run_migrations
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "routing.db"))
    run_migrations()
    from jarvis.skills.registry import SkillRegistry
    from jarvis.agents.base import SubAgent
    async def forbidden(*args, **kwargs):
        raise AssertionError("synthetic routing probe attempted a real skill/specialist")
    monkeypatch.setattr(SkillRegistry, "start", forbidden)
    monkeypatch.setattr(SkillRegistry, "call", forbidden)
    monkeypatch.setattr(SubAgent, "run", forbidden)
    clients = [
        FakeLLM([("tool", "console_action", {"action": "inventory"}),
                 ("tool", "console_action", {"action": "result_select", "target": "1", "inventory_revision": 1}),
                 ("text", "Opened.")]),
        FakeLLM([("tool", "delegate_task", {"agent_name": "analyst", "task": "Get weather in Folly Beach"}),
                 ("text", "Sunny and 75 degrees.")]),
    ]
    assert asyncio.run(ev.run_ws17_routing_probe(make_settings(), client_factory=lambda _: clients.pop(0))) == (2, 2)
    assert clients == []
