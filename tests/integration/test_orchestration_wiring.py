"""WS-42: pipeline wiring of the flag. Reuses the fixtures of test_bot_wiring."""

import pytest

from jarvis.bot.pipeline import build_pipeline

from tests.integration import test_bot_wiring as _bot_wiring
from tests.integration.test_bot_wiring import FakeTransport, _system_prompt_of

# Reuse test_bot_wiring's fixtures. Bound by assignment rather than imported by
# name, so pyflakes does not read each test's fixture argument as a redefinition.
fakes = _bot_wiring.fakes
runtime = _bot_wiring.runtime


def _tool_names(aggregators) -> list[str]:
    ctx = getattr(aggregators.user(), "context", None) or getattr(aggregators, "_context", None)
    return [t.name for t in ctx.tools.standard_tools]


def test_flag_off_keeps_delegate_task_first_in_the_menu(runtime, fakes, monkeypatch):
    monkeypatch.delenv("JARVIS_ORCHESTRATOR_ENABLED", raising=False)
    _, llm, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert "delegate_task" in llm.functions and "hand_off" not in llm.functions
    names = _tool_names(aggregators)
    assert names[0] == "delegate_task" and "hand_off" not in names
    prompt = _system_prompt_of(aggregators)
    assert "delegate_task" in prompt and "hand_off" not in prompt


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_flag_on_swaps_delegate_task_for_hand_off(runtime, fakes, monkeypatch, value):
    monkeypatch.setenv("JARVIS_ORCHESTRATOR_ENABLED", value)
    _, llm, aggregators, _ = build_pipeline(FakeTransport(), runtime)
    assert "hand_off" in llm.functions and "delegate_task" not in llm.functions
    names = _tool_names(aggregators)
    assert names[0] == "hand_off" and "delegate_task" not in names
    assert names[1:] == [n for n in names[1:] if n != "hand_off"]
    prompt = _system_prompt_of(aggregators)
    assert "delegate_task" not in prompt
    assert "All specialist work is handed off with the hand_off tool." in prompt


def test_flag_on_registers_the_same_other_tools(runtime, fakes, monkeypatch):
    monkeypatch.delenv("JARVIS_ORCHESTRATOR_ENABLED", raising=False)
    _, off_llm, _, _ = build_pipeline(FakeTransport(), runtime)
    monkeypatch.setenv("JARVIS_ORCHESTRATOR_ENABLED", "1")
    _, on_llm, _, _ = build_pipeline(FakeTransport(), runtime)
    assert sorted(set(off_llm.functions) - {"delegate_task"}) == sorted(set(on_llm.functions) - {"hand_off"})


async def test_flag_on_hand_off_runs_a_step_through_the_registered_handler(
        runtime, fakes, monkeypatch):
    """The registered hand_off decides (stubbed model call), then the step runs
    through the real delegate handler built by the pipeline."""
    from types import SimpleNamespace

    from jarvis.agents import orchestration as orch

    seen = {}

    async def fake_execute_chat(request, resolved, **kwargs):
        seen["workload"] = request.workload
        seen["policy"] = request.data_policy
        return SimpleNamespace(
            text='{"steps": [{"agent_name": "scheduler", "task": "Set an alarm."}], "ask_user": null}',
            model="claude-fable-5-2")

    monkeypatch.setattr(orch, "execute_chat", fake_execute_chat)
    monkeypatch.setenv("JARVIS_ORCHESTRATOR_ENABLED", "1")
    _, llm, _, _ = build_pipeline(FakeTransport(), runtime)
    runtime.voice_state.user_text = "set an alarm for six"
    delivered = []

    class FakeParams:
        arguments = {"note": "alarm"}

        async def result_callback(self, result):
            delivered.append(result)

    await llm.functions["hand_off"](FakeParams())
    assert seen["workload"] == "orchestration"
    assert len(delivered) == 1
    assert str(delivered[0]).startswith("done\n[routed by claude-fable-5-2: scheduler]")
