"""MORTIMER_VOICE_WORKFLOWS_PLAN.md §7 T1 — VoiceWorkflowInjector and
ReplyGuard driven frame by frame (push_frame seam as in test_speaker_gate.py)."""

from __future__ import annotations

import json

import pytest
from pipecat.frames.frames import (
    FunctionCallsStartedFrame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection

from jarvis import voice_workflows as vw
from jarvis.bot.voice_guidance import (
    ReplyGuard,
    VoiceTurnState,
    VoiceWorkflowInjector,
    normalize_guard_mode,
)

DOWN = FrameDirection.DOWNSTREAM


def _capture(processor):
    pushed = []

    async def fake_push_frame(frame, direction=DOWN):
        pushed.append(frame)

    processor.push_frame = fake_push_frame
    return pushed


def _texts(pushed):
    return "".join(f.text for f in pushed if isinstance(f, LLMTextFrame))


# --------------------------------------------------------------- injector

class TestInjector:
    async def test_new_turn_gets_matching_guidance(self):
        state = VoiceTurnState()
        inj = VoiceWorkflowInjector(state)
        pushed = _capture(inj)
        ctx = LLMContext(messages=[{"role": "system", "content": "sys"}])
        ctx.add_message({"role": "user", "content": "Can you not check my Internet connection for a location?"})
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        msgs = ctx.get_messages()
        assert msgs[-1]["content"].startswith("[system] Larry's standing instruction")
        assert "voice-check-before-cant" in msgs[-1]["content"]
        assert state.user_text.startswith("Can you not check")
        assert len(state.notes) == 1 and len(pushed) == 1

    async def test_tool_rerun_in_same_turn_does_not_inject_again(self):
        state = VoiceTurnState()
        inj = VoiceWorkflowInjector(state)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "Can you see my location?"}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        ctx.add_message({"role": "tool", "tool_call_id": "t1", "content": "ok"})
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert sum(1 for m in ctx.get_messages() if str(m.get("content", "")).startswith("[system] Larry's")) == 1

    async def test_next_turn_tombstones_previous_guidance(self):
        state = VoiceTurnState()
        inj = VoiceWorkflowInjector(state)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "Can you see my location?"}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        first_note = state.notes[0]
        ctx.add_message({"role": "assistant", "content": "You're in Spartanburg."})
        ctx.add_message({"role": "user", "content": "Thanks."})
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert first_note["content"] == vw.TOMBSTONE
        assert state.user_text == "Thanks." and state.notes == []

    async def test_system_note_is_not_a_user_turn(self):
        state = VoiceTurnState()
        inj = VoiceWorkflowInjector(state)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "[system] The user just connected."}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert state.last_user_message is None and len(ctx.get_messages()) == 1

    async def test_explicit_ask_stamps_the_gate(self):
        # D-L5 — even with injection disabled, the ask opens show_commands.
        gate: dict = {}
        state = VoiceTurnState()
        inj = VoiceWorkflowInjector(state, inject_enabled=False, gate=gate)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "Give me the command to do that."}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert isinstance(gate.get("explicit_ask_at"), float)

    async def test_pushback_does_not_stamp_the_gate(self):
        gate: dict = {}
        inj = VoiceWorkflowInjector(VoiceTurnState(), gate=gate)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "Are you unable to run that command yourself?"}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert "explicit_ask_at" not in gate

    async def test_disabled_tracks_turn_but_adds_nothing(self):
        state = VoiceTurnState()
        state.corrected = True
        inj = VoiceWorkflowInjector(state, inject_enabled=False)
        _capture(inj)
        ctx = LLMContext(messages=[{"role": "user", "content": "Can you see my location?"}])
        await inj.process_frame(LLMContextFrame(context=ctx), DOWN)
        assert len(ctx.get_messages()) == 1
        assert state.user_text == "Can you see my location?" and state.corrected is False


# ------------------------------------------------------------------ guard

def _guard(mode="correct", user_text="show me the radar"):
    state = VoiceTurnState()
    state.user_text = user_text
    scheduled = []
    notes = []

    async def on_correct(note):
        notes.append(note)

    guard = ReplyGuard(state, mode=mode, on_correct=on_correct,
                       schedule=lambda coro: scheduled.append(coro))
    pushed = _capture(guard)
    return guard, state, pushed, scheduled, notes


async def _respond(guard, chunks, *, function_call=False):
    await guard.process_frame(LLMFullResponseStartFrame(), DOWN)
    for c in chunks:
        await guard.process_frame(LLMTextFrame(text=c), DOWN)
    if function_call:
        await guard.process_frame(FunctionCallsStartedFrame(function_calls=[]), DOWN)
    await guard.process_frame(LLMFullResponseEndFrame(), DOWN)


class TestReplyGuard:
    async def test_clean_reply_passes_unchanged_in_order(self):
        guard, _, pushed, scheduled, _ = _guard()
        await _respond(guard, ["It's seventy", "-two degrees. Clear ", "skies tonight."])
        assert _texts(pushed) == "It's seventy-two degrees. Clear skies tonight."
        assert isinstance(pushed[0], LLMFullResponseStartFrame)
        assert isinstance(pushed[-1], LLMFullResponseEndFrame)
        assert scheduled == []

    async def test_refusal_is_cut_and_one_correction_requested(self):
        guard, state, pushed, scheduled, notes = _guard()
        await _respond(guard, ["Radar is loading. ", "I don't have a tool to pull ", "live radar. Anything else?"])
        assert _texts(pushed) == "Radar is loading. "
        assert isinstance(pushed[-1], LLMFullResponseEndFrame)
        assert len(scheduled) == 1 and state.corrected is True
        await scheduled[0]
        assert notes[0].startswith("[system] Your last reply was cut off")
        assert "I don't have a tool to pull live radar." in notes[0]
        assert "voice-check-before-cant" in notes[0]

    async def test_handoff_gets_the_handoff_workflow(self):
        guard, _, _, scheduled, notes = _guard()
        await _respond(guard, ["Run that command locally and copy the output back."])
        await scheduled[0]
        assert "voice-do-it-dont-hand-off" in notes[0]

    async def test_refusal_followed_by_delegation_is_not_corrected(self):
        guard, state, pushed, scheduled, _ = _guard()
        await _respond(guard, ["I can't see that directly. ", "One moment."], function_call=True)
        assert scheduled == [] and state.corrected is False
        assert _texts(pushed) == ""

    async def test_acknowledgment_before_delegation_is_flushed(self):
        guard, _, pushed, scheduled, _ = _guard()
        await _respond(guard, ["One moment, checking that now"], function_call=True)
        assert _texts(pushed) == "One moment, checking that now" and scheduled == []

    async def test_second_violation_in_same_turn_is_spoken_and_logged(self, tmp_path, monkeypatch):
        gaps = tmp_path / "gaps.jsonl"
        monkeypatch.setattr(vw, "GAP_LOG_PATH", gaps)
        guard, state, pushed, scheduled, _ = _guard()
        state.corrected = True
        await _respond(guard, ["That isn't possible. I can't read your location."])
        assert _texts(pushed) == "That isn't possible. I can't read your location."
        assert scheduled == []
        assert json.loads(gaps.read_text().strip())["kind"] == "refusal"

    async def test_unterminated_last_sentence_is_checked_at_end(self):
        guard, _, pushed, scheduled, _ = _guard()
        await _respond(guard, ["Sure. ", "You'll need to run bundle.sh"])
        assert _texts(pushed) == "Sure. " and len(scheduled) == 1
        await scheduled[0]

    async def test_interruption_resets(self):
        guard, _, pushed, scheduled, _ = _guard()
        await guard.process_frame(LLMFullResponseStartFrame(), DOWN)
        await guard.process_frame(LLMTextFrame(text="I can't do"), DOWN)
        await guard.process_frame(InterruptionFrame(), DOWN)
        await guard.process_frame(LLMFullResponseEndFrame(), DOWN)
        assert _texts(pushed) == "" and scheduled == []

    async def test_capability_question_is_exempt(self):
        guard, _, pushed, scheduled, _ = _guard(user_text="Give me a rundown of your capabilities.")
        await _respond(guard, ["I handle weather. I can't make phone calls."])
        assert _texts(pushed) == "I handle weather. I can't make phone calls." and scheduled == []

    async def test_handoff_is_exempt_when_he_asked_for_the_command(self):
        guard, _, pushed, scheduled, _ = _guard(user_text="Give me the command to do that.")
        await _respond(guard, ["It's on screen. Run that command in your terminal."])
        assert _texts(pushed) == "It's on screen. Run that command in your terminal." and scheduled == []

    async def test_refusal_still_corrected_when_he_asked_for_the_command(self):
        guard, _, pushed, scheduled, _ = _guard(user_text="Give me the command to do that.")
        await _respond(guard, ["I can't do that."])
        assert _texts(pushed) == "" and len(scheduled) == 1

    async def test_log_mode_speaks_everything(self):
        guard, _, pushed, scheduled, _ = _guard(mode="log")
        await _respond(guard, ["I can't do that."])
        assert _texts(pushed) == "I can't do that." and scheduled == []

    async def test_off_mode_passes_the_same_frame_objects(self):
        guard, _, pushed, scheduled, _ = _guard(mode="off")
        frames = [LLMFullResponseStartFrame(), LLMTextFrame(text="I can't. "), LLMFullResponseEndFrame()]
        for f in frames:
            await guard.process_frame(f, DOWN)
        assert pushed == frames and scheduled == []

    async def test_upstream_frames_pass_through(self):
        guard, _, pushed, _, _ = _guard()
        f = LLMTextFrame(text="I can't.")
        await guard.process_frame(f, FrameDirection.UPSTREAM)
        assert pushed == [f]

    async def test_skip_tts_is_preserved(self):
        guard, _, pushed, _, _ = _guard()
        await guard.process_frame(LLMFullResponseStartFrame(), DOWN)
        f = LLMTextFrame(text="Hello there. ")
        f.skip_tts = True
        await guard.process_frame(f, DOWN)
        out = [p for p in pushed if isinstance(p, LLMTextFrame)]
        assert out[0].skip_tts is True


@pytest.mark.parametrize("raw,expected", [
    ("off", "off"), ("LOG", "log"), (" correct ", "correct"), ("", "log"), (None, "log"), ("on", "log"),
])
def test_normalize_guard_mode(raw, expected):
    assert normalize_guard_mode(raw) == expected


def test_reply_guard_ships_in_log_mode():
    """Larry, 2026-09-25 (plan rev 1.2, F1): the guard ships speaking
    everything and recording what it would have stopped. Switching to
    correct is a deliberate .env change, never a silent default."""
    from jarvis.config import Settings
    assert Settings.model_fields["jarvis_reply_guard_mode"].default == "log"
    import inspect
    import jarvis.bot.pipeline as bp
    assert 'getattr(settings, "jarvis_reply_guard_mode", "log")' in inspect.getsource(bp.build_pipeline)
