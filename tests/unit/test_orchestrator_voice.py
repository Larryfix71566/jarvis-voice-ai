"""MORTIMER_VOICE_WORKFLOWS_PLAN.md D15 — the Orchestrator (routing eval,
voice-workflow eval, CLI) runs the same three hooks as pipeline.py.
Scripted FakeLLM doubles from test_orchestrator.py; no network."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from jarvis import voice_workflows as vw
from jarvis.agents.supervisor import Orchestrator
from tests.unit.test_orchestrator import FakeLLM, FakeRegistry, FakeSubAgent


def _settings(enabled: bool, mode: str):
    return SimpleNamespace(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_name="Jarvis",
        jarvis_user_name="Boss",
        jarvis_timezone="America/New_York",
        jarvis_units="imperial",
        jarvis_voice_workflows_enabled=enabled,
        jarvis_reply_guard_mode=mode,
    )


def _orch(script, *, enabled=True, mode="correct", sub_agents=None):
    fake = FakeLLM(script)
    if sub_agents is None:
        sub_agents = {n: FakeSubAgent(n)
                      for n in ("scheduler", "librarian", "analyst", "systems", "developer")}
    orch = Orchestrator(
        _settings(enabled, mode), FakeRegistry(), session_id="voice-test",
        client_factory=lambda settings: fake, mode="delegating",
        sub_agents=sub_agents,
    )
    return orch, fake.chat.completions


@pytest.fixture(autouse=True)
def gap_log(tmp_path, monkeypatch):
    path = tmp_path / "gaps.jsonl"
    monkeypatch.setenv(vw.GAP_LOG_ENV, str(path))
    return path


class TestUserHook:
    async def test_guidance_note_is_the_last_message_sent(self, fresh_db):
        orch, calls = _orch([("text", "You're in Spartanburg.")])
        await orch.chat("Can you see my location?")
        last = calls.requests[0]["messages"][-1]
        assert last["role"] == "user"
        assert last["content"].startswith("[system] Larry's standing instruction")
        assert "voice-check-before-cant" in last["content"]

    async def test_next_turn_tombstones_the_note(self, fresh_db):
        orch, calls = _orch([("text", "You're in Spartanburg."), ("text", "Sure.")])
        await orch.chat("Can you see my location?")
        await orch.chat("Thanks.")
        user_contents = [m["content"] for m in calls.requests[1]["messages"] if m["role"] == "user"]
        assert vw.TOMBSTONE in user_contents

    async def test_disabled_sends_exactly_the_pre_plan_messages(self, fresh_db):
        orch, calls = _orch([("text", "ok")], enabled=False, mode="off")
        await orch.chat("Can you see my location?")
        assert [m["role"] for m in calls.requests[0]["messages"]] == ["system", "user"]

    async def test_bare_settings_default_to_off(self, fresh_db):
        # tests/unit/test_orchestrator.py's make_settings has neither field.
        fake = FakeLLM([("text", "ok")])
        settings = _settings(True, "correct")
        del settings.jarvis_voice_workflows_enabled
        del settings.jarvis_reply_guard_mode
        orch = Orchestrator(settings, FakeRegistry(), session_id="s",
                            client_factory=lambda s: fake, mode="delegating",
                            sub_agents={"scheduler": FakeSubAgent("scheduler")})
        await orch.chat("Can you see my location?")
        assert len(fake.chat.completions.requests[0]["messages"]) == 2


class TestReplyGuard:
    async def test_refusal_gets_one_retry_and_never_enters_history(self, fresh_db):
        orch, calls = _orch([
            ("text", "I don't have a tool to read your location."),
            ("text", "That isn't something I have a tool for yet. Want me to have it added?"),
        ])
        reply = await orch.chat("where am I right now")
        assert reply.startswith("That isn't something I have a tool for yet")
        assert len(calls.requests) == 2
        assert calls.requests[1]["messages"][-1]["content"].startswith(
            "[system] Your last reply was cut off")
        assistant = [m["content"] for m in orch.history if m["role"] == "assistant"]
        assert not any("I don't have a tool to read" in (c or "") for c in assistant)

    async def test_second_violation_is_returned_and_logged(self, fresh_db, gap_log):
        orch, calls = _orch([("text", "I can't do that."), ("text", "I can't do that either.")])
        reply = await orch.chat("move my dentist appointment")
        assert reply == "I can't do that either." and len(calls.requests) == 2
        record = json.loads(gap_log.read_text().strip().splitlines()[-1])
        assert record["source"] == "reply_guard" and record["kind"] == "refusal"

    async def test_handoff_retry_carries_the_handoff_workflow(self, fresh_db):
        orch, calls = _orch([("text", "Run that command and copy the output back."), ("text", "Done.")])
        await orch.chat("check the keys")
        assert "voice-do-it-dont-hand-off" in calls.requests[1]["messages"][-1]["content"]

    async def test_log_mode_does_not_retry(self, fresh_db):
        orch, calls = _orch([("text", "I can't do that.")], mode="log")
        assert await orch.chat("move my dentist appointment") == "I can't do that."
        assert len(calls.requests) == 1

    async def test_handoff_is_exempt_when_he_asked_for_the_command(self, fresh_db):
        # D-L5 — no retry: the hand-off is what he asked for.
        orch, calls = _orch([("text", "It's on screen. Run that command in your terminal.")])
        await orch.chat("Give me the command to do that.")
        assert len(calls.requests) == 1

    async def test_refusal_still_retried_when_he_asked_for_the_command(self, fresh_db):
        orch, calls = _orch([("text", "I can't do that."), ("text", "Done.")])
        assert await orch.chat("Give me the command to do that.") == "Done."
        assert len(calls.requests) == 2

    async def test_capability_question_is_exempt(self, fresh_db):
        orch, calls = _orch([("text", "I handle weather. I can't make phone calls.")])
        await orch.chat("What are your capabilities?")
        assert len(calls.requests) == 1


class TestResultHook:
    async def test_needs_input_result_carries_guidance(self, fresh_db, gap_log):
        dev = FakeSubAgent(
            "developer",
            result="NEEDS-INPUT: I have no network tool. Run: curl -s https://example")
        orch, calls = _orch([
            ("tool", "delegate_task", {"agent_name": "developer", "task": "list models"}),
            ("text", "That isn't something I have a tool for yet."),
        ], sub_agents={"developer": dev})
        await orch.chat("which models are available")
        tool_msgs = [m for m in calls.requests[1]["messages"] if m["role"] == "tool"]
        assert "voice-do-it-dont-hand-off" in tool_msgs[-1]["content"]
        assert json.loads(gap_log.read_text().strip())["kind"] == "limitation"

    async def test_disabled_leaves_result_untouched(self, fresh_db):
        dev = FakeSubAgent("developer", result="FAILED: repo_read_file said no such file")
        orch, calls = _orch([
            ("tool", "delegate_task", {"agent_name": "developer", "task": "read x"}),
            ("text", "It failed."),
        ], enabled=False, mode="off", sub_agents={"developer": dev})
        await orch.chat("read x")
        tool_msgs = [m for m in calls.requests[1]["messages"] if m["role"] == "tool"]
        assert "[system]" not in tool_msgs[-1]["content"]
