"""Retained weather copies, including interrupted/late replies, not transcripts."""
import asyncio
import copy
from types import SimpleNamespace

from pipecat.processors.aggregators.llm_context import LLMContext
from jarvis.bot.pipeline import (
    WeatherContextMinimizer, _WEATHER_CONTEXT_NOTE,
    _mark_weather_context, _weather_context_call, adapt_to_pipecat,
)


def user(text):
    return {"role": "user", "content": text}


def assistant(text):
    return {"role": "assistant", "content": text}


def tool(identity, text):
    return {"role": "tool", "tool_call_id": identity, "content": text}


async def invoke(owner, identity, handler, sink):
    async def callback(value):
        sink.append(value)
    await adapt_to_pipecat("delegate_task", handler, weather_context=owner)(
        SimpleNamespace(arguments={}, tool_call_id=identity, result_callback=callback))


async def test_real_adapter_returns_full_result_and_minimizes_only_after_next_user():
    owner = WeatherContextMinimizer()
    spoken = []
    async def weather(_):
        _mark_weather_context()
        return "Folly Beach: 81 degrees and sunny"
    await invoke(owner, "weather-1", weather, spoken)
    assert _weather_context_call.get() is None
    messages = [user("weather in Folly Beach"), tool("weather-1", spoken[0]), assistant(spoken[0])]
    persisted_transcript = copy.deepcopy(messages)
    context = LLMContext(messages=messages)
    owner.minimize(context)
    owner.begin_relay(); owner.finish_relay()
    assert context.get_messages() == persisted_transcript
    context.add_message(user("weather again"))
    owner.minimize(context)
    assert context.get_messages()[1]["content"] == _WEATHER_CONTEXT_NOTE
    assert context.get_messages()[2]["content"] == _WEATHER_CONTEXT_NOTE
    assert spoken == ["Folly Beach: 81 degrees and sunny"]
    assert persisted_transcript[2]["content"] == spoken[0]
    assert context.get_messages()[-1] == user("weather again")
    assert not owner.weather_calls


async def test_unrelated_delegation_and_user_weather_words_do_not_trigger_minimization():
    owner = WeatherContextMinimizer()
    async def unrelated(_):
        return "The weather code review found a bug"
    sink = []
    await invoke(owner, "code-review", unrelated, sink)
    messages = [user("review weather code"), tool("code-review", sink[0]), assistant(sink[0]), user("continue")]
    expected = copy.deepcopy(messages)
    owner.minimize(LLMContext(messages=messages))
    assert messages == expected


async def test_mixed_turn_retains_other_tool_results_and_subsequent_turns():
    owner = WeatherContextMinimizer(); owner.weather_calls.add("w"); owner.ready_calls.add("w")
    messages = [user("weather and appointment"), tool("w", "81F"),
        tool("calendar", "Appointment Tuesday 3pm"), assistant("81F; Tuesday 3pm"),
        user("thanks"), assistant("You are welcome"), user("again")]
    owner.minimize(LLMContext(messages=messages))
    assert messages[1]["content"] == messages[3]["content"] == _WEATHER_CONTEXT_NOTE
    assert messages[2]["content"] == "Appointment Tuesday 3pm"
    assert messages[5]["content"] == "You are welcome"


async def test_interrupted_result_arriving_after_new_user_remains_for_first_relay():
    owner = WeatherContextMinimizer(); owner.weather_calls.add("w"); owner.ready_calls.add("w")
    messages = [user("weather"), user("wait"), tool("w", "81F"), assistant("81F")]
    context = LLMContext(messages=messages)
    owner.minimize(context)
    assert messages[2]["content"] == "81F"
    context.add_message(user("weather again"))
    owner.minimize(context)
    assert messages[2]["content"] == messages[3]["content"] == _WEATHER_CONTEXT_NOTE


async def test_detached_task_inherits_call_identity_and_late_note_is_minimized_once_relayed():
    owner = WeatherContextMinimizer()
    released = asyncio.Event(); started = asyncio.Event()
    tasks = []
    note = {"role": "user", "content": "[system] Weather: 81F; relay once"}
    async def delegated(_):
        async def child():
            started.set(); await released.wait()
            _mark_weather_context()
            owner.arm_late_note(note)
        tasks.append(asyncio.create_task(child()))
        await asyncio.shield(tasks[0])
        return "81F"
    wrapper = asyncio.create_task(invoke(owner, "w", delegated, []))
    await started.wait(); wrapper.cancel()
    try:
        await wrapper
    except asyncio.CancelledError:
        pass
    released.set(); await tasks[0]
    messages = [user("weather"), user("wait"), note, assistant("81F")]
    context = LLMContext(messages=messages)
    owner.minimize(context)
    assert note["content"].endswith("relay once")
    owner.begin_relay(); owner.finish_relay()
    context.add_message(user("again")); owner.minimize(context)
    assert note["content"] == messages[3]["content"] == _WEATHER_CONTEXT_NOTE
    assert not owner.late_notes


async def test_current_tool_continuation_and_system_notes_do_not_erase_forecast():
    owner = WeatherContextMinimizer(); owner.weather_calls.add("w"); owner.ready_calls.add("w")
    messages = [user("weather"), tool("w", "81F"), assistant("81F"), user("[system] correction")]
    expected = copy.deepcopy(messages)
    owner.minimize(LLMContext(messages=messages))
    assert messages == expected


async def test_parallel_tool_arguments_keep_other_task_but_remove_forecast_copy():
    import json
    owner = WeatherContextMinimizer(); owner.weather_calls.add("w"); owner.ready_calls.add("w")
    parallel = {"role": "assistant", "content": "Earlier it was 81F", "tool_calls": [
        {"id": "w", "function": {"name": "delegate_task", "arguments": json.dumps({"agent": "analyst", "task": "Was 81F; refresh"})}},
        {"id": "other", "function": {"name": "delegate_task", "arguments": '{"agent":"scheduler","task":"tomorrow"}'}}]}
    messages = [user("weather and schedule"), parallel, tool("w", "81F"), user("again")]
    owner.minimize(LLMContext(messages=messages))
    assert "81F" not in json.dumps(messages)
    assert parallel["tool_calls"][0]["id"] == "w"
    assert json.loads(parallel["tool_calls"][1]["function"]["arguments"])["task"] == "tomorrow"


async def test_local_cached_weather_marks_even_without_display_emission():
    owner = WeatherContextMinimizer(); spoken = []
    async def cached(_):
        return "Weather: 81F. Reused retained weather card."
    async def callback(value):
        spoken.append(value)
    await adapt_to_pipecat("local_weather", cached, weather_context=owner)(
        SimpleNamespace(arguments={}, tool_call_id="local", result_callback=callback))
    owner.ready_calls.add("local")
    context = LLMContext(messages=[user("weather here"), tool("local", spoken[0]), user("again")])
    owner.minimize(context)
    assert context.get_messages()[1]["content"] == _WEATHER_CONTEXT_NOTE
    assert spoken[0].startswith("Weather: 81F")


async def test_actual_response_observer_ignores_stale_end_and_forwarded_frames():
    from jarvis.bot.pipeline import WeatherContextRelayObserver
    from pipecat.frames.frames import LLMFullResponseStartFrame, LLMFullResponseEndFrame
    from pipecat.processors.frame_processor import FrameDirection
    owner = WeatherContextMinimizer(); llm = object()
    observer = WeatherContextRelayObserver(owner, llm)
    context = LLMContext(messages=[user("weather")])
    owner.minimize(context)
    async def emit(frame, source=llm):
        await observer.on_push_frame(SimpleNamespace(source=source, direction=FrameDirection.DOWNSTREAM, frame=frame))
    await emit(LLMFullResponseStartFrame())
    owner.weather_calls.add("w")
    context.add_message(tool("w", "81F"))
    await emit(LLMFullResponseStartFrame(), source=object())  # forwarded, not a new response
    await emit(LLMFullResponseEndFrame())
    context.add_message(user("wait")); owner.minimize(context)
    assert context.get_messages()[1]["content"] == "81F"  # not relayed yet
    await emit(LLMFullResponseStartFrame())
    context.add_message(assistant("81 degrees"))
    await emit(LLMFullResponseEndFrame())
    context.add_message(user("again")); owner.minimize(context)
    assert context.get_messages()[1]["content"] == _WEATHER_CONTEXT_NOTE
    assert context.get_messages()[3]["content"] == _WEATHER_CONTEXT_NOTE  # echo in relay turn
