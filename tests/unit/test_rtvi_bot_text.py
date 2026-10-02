"""Mortimer's lines in the conversation thread were doubled (Larry,
2026-09-30): "You're in Folly Beach ... location. Getting theYou're in Folly
Beach ...". The LLM context held the reply once; the client builds the
thread from bot-llm-text messages.

Cause: pipecat's RTVIObserver sends one bot-llm-text per LLMTextFrame id it
sees. The LLM pushes its token frames; ReplyGuard (any mode but "off")
consumes them and pushes NEW sentence frames, so the observer sent both
streams, interleaved.

Fix: the observer ignores frames pushed by the LLM itself
(`rtvi_observer_params`). Every LLM frame still reaches the client when
ReplyGuard passes it on, so the client gets exactly what goes to TTS, once.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    DataFrame,
    FunctionCallFromLLM,
    FunctionCallsStartedFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIObserverParams
from pipecat.tests.utils import run_test

from jarvis.bot.voice_guidance import ReplyGuard, VoiceTurnState, rtvi_observer_params

# The reply from the 2026-09-30 thread, in LLM-sized chunks.
REPLY_TOKENS = ["You're", " in", " Folly", " Beach,", " South", " Carolina,", " from", " your",
                " device's", " location.", " Getting", " the", " weather", " now."]
REPLY = "".join(REPLY_TOKENS)


class _Ask(DataFrame):
    pass


class _StubLLM(FrameProcessor):
    """Stands in for the LLM service: answers an _Ask with its own frames."""

    def __init__(self, tokens, *, function_call=False):
        super().__init__()
        self._tokens = tokens
        self._function_call = function_call

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if not isinstance(frame, _Ask):
            await self.push_frame(frame, direction)
            return
        await self.push_frame(LLMFullResponseStartFrame())
        for token in self._tokens:
            await self.push_frame(LLMTextFrame(text=token))
        if self._function_call:
            call = FunctionCallFromLLM(function_name="system_status", tool_call_id="t1",
                                       arguments={}, context=None)
            # As the real LLM service does: one copy each way.
            await self.broadcast_frame(FunctionCallsStartedFrame, function_calls=[call])
        await self.push_frame(LLMFullResponseEndFrame())


class _CapturingObserver(RTVIObserver):
    def __init__(self, params):
        super().__init__(None, params=params)
        self.messages = []

    async def send_rtvi_message(self, model, exclude_none=True):
        self.messages.append(model)


async def _run(tokens, *, mode, params_for, user_text="where am I", function_call=False):
    llm = _StubLLM(tokens, function_call=function_call)
    state = VoiceTurnState()
    state.user_text = user_text

    async def on_correct(_note):
        pass

    guard = ReplyGuard(state, mode=mode, on_correct=on_correct, schedule=lambda coro: coro.close())
    observer = _CapturingObserver(params_for(llm))
    down, _ = await run_test(Pipeline([llm, guard]), frames_to_send=[_Ask()], observers=[observer])
    sent = "".join(m.data.text for m in observer.messages if m.type == "bot-llm-text")
    spoken = "".join(f.text for f in down if isinstance(f, LLMTextFrame))
    types = [m.type for m in observer.messages]
    return sent, spoken, types


async def test_default_observer_doubles_the_guarded_reply():
    # The defect, reproduced: why rtvi_observer_params exists.
    sent, spoken, _ = await _run(REPLY_TOKENS, mode="log", params_for=lambda _llm: RTVIObserverParams())
    assert spoken == REPLY
    assert sent != REPLY
    assert sent.count("You're in Folly Beach") == 2


async def test_each_guard_mode_sends_the_reply_once():
    for mode in ("log", "correct", "off"):
        sent, spoken, _ = await _run(REPLY_TOKENS, mode=mode, params_for=rtvi_observer_params)
        assert sent == REPLY, mode
        assert spoken == REPLY, mode


async def test_the_thread_gets_what_is_spoken_not_what_the_guard_cut():
    tokens = ["Radar is loading. ", "I don't have a tool to pull ", "live radar. Anything else?"]
    sent, spoken, _ = await _run(tokens, mode="correct", params_for=rtvi_observer_params,
                                 user_text="show me the radar")
    assert spoken == "Radar is loading. "
    assert sent == spoken


async def test_reply_before_a_tool_call_is_sent_once():
    sent, spoken, types = await _run(["One moment, checking that now"], mode="log",
                                     params_for=rtvi_observer_params, function_call=True)
    assert sent == spoken == "One moment, checking that now"
    assert types.count("llm-function-call-started") == 1


async def test_turn_boundaries_are_still_sent_once():
    _, _, types = await _run(REPLY_TOKENS, mode="log", params_for=rtvi_observer_params)
    assert types.count("bot-llm-started") == 1
    assert types.count("bot-llm-stopped") == 1
    assert types.index("bot-llm-started") < types.index("bot-llm-text") < types.index("bot-llm-stopped")


def test_the_session_task_ignores_the_llm_as_an_rtvi_source(monkeypatch):
    from jarvis.bot import pipeline as bot_pipeline

    captured = {}

    class _Task:
        def __init__(self, pipeline, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(bot_pipeline, "PipelineTask", _Task)
    llm = _StubLLM(REPLY_TOKENS)
    bot_pipeline.build_task(Pipeline([llm]), llm, observers=[])
    assert captured["rtvi_observer_params"].ignored_sources == [llm]
    assert captured["params"].enable_metrics and captured["params"].enable_usage_metrics
