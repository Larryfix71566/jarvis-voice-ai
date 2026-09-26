"""Phase 2 W14 (MORTIMER_VOICE_WORKFLOWS_PLAN.md): a UI change is done when
it can be seen. The tasks are the developer's own, from agent_runs on
2026-09-09 00:38-00:59, the zoom-and-pan self-edit that was reported as
confirmed and never reached the screen (turn 2694)."""

from __future__ import annotations

import pytest

from jarvis.workflows import load_workflows, match_workflow

LOGGED_TASKS = [
    "Check the status of the current self-edit. What stage is it at — still validating, "
    "validation done, PR opened, or something else?",
    "Investigate why zoom and pan are not working on the graph window. Review "
    "GraphImageView.swift for the recent changes to mouse wheel zoom (0.5x–5x range) and "
    "+/− key pan functionality. Check the implementation",
    "You just confirmed a zoom and pan implementation for the memory graph window (staging "
    "c77256b29bd6). Check what happened: was it committed and pushed? Is the code actually "
    "in the working tree now? Why",
    "Check the status of the current self-edit. Report whether validation passed, if the PR "
    "opened, and what state the build is in.",
]


@pytest.fixture(scope="module")
def workflows():
    return load_workflows()


@pytest.mark.parametrize("task", LOGGED_TASKS)
def test_logged_ui_self_edit_checks_get_the_workflow(workflows, task):
    wf = match_workflow("developer", task, workflows)
    assert wf is not None and wf.name == "verify-ui-change-on-screen"


def test_developer_only(workflows):
    assert match_workflow("analyst", LOGGED_TASKS[2], workflows) is None


@pytest.mark.parametrize("task", [
    "Get the current weather for Alpharetta, Georgia.",
    "Show the rotary graph. Retrieve the graph_view of runs, tools, models, and council rounds "
    "from the current development session, and display it in the output window.",
])
def test_unrelated_tasks_do_not_get_it(workflows, task):
    wf = match_workflow("developer", task, workflows)
    assert wf is None or wf.name != "verify-ui-change-on-screen"


def test_steps_require_looking_and_honest_status(workflows):
    wf = next(w for w in workflows if w.name == "verify-ui-change-on-screen")
    text = wf.as_prompt()
    assert "screen_view" in text
    assert "unverified" in text
    assert "instead of calling it done" in text
    assert wf.done_when
