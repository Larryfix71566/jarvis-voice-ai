"""Weather requests with leading fillers, and bare-place answers to "which location?".

Both transcripts are from Larry's Mac on 2026-11-17: "Okay. Show me the weather."
parsed as a place called "okay. show me the", refusing device weather, and the
answer "Alpharetta." to Mortimer's location question parsed as not-weather, so
every analyst weather call was refused as weather_reuse_invalid_request.
"""
import pytest
from pipecat.frames.frames import LLMContextFrame, TranscriptionFrame, UserStartedSpeakingFrame
from pipecat.processors.aggregators.llm_context import LLMContext

from jarvis.bot.pipeline import ForegroundRequests
from jarvis.bot.weather_intent import WeatherIntent, accepted_weather_intent, asked_for_location

ASKED = "Which location do you want — Alpharetta, Spartanburg, or somewhere else?"


@pytest.mark.parametrize("text", ["Okay. Show me the weather.", "Okay, show me the weather.",
    "OK what's the weather?", "Alright, the weather.", "Hey Mortimer, what's the weather?",
    "Mortimer, weather please.", "Um, is it going to rain?", "So, do I need an umbrella?",
    "Yeah. Weather.", "Thanks. Show me the weather."])
def test_leading_fillers_keep_device_local_weather(text):
    intent = accepted_weather_intent(text)
    assert intent == WeatherIntent("local")
    assert intent.permits("weather:local:device:synthetic", "local_weather")


@pytest.mark.parametrize("text,place", [("Okay, weather in Portland, Maine", "portland, maine"),
    ("Okay. Show me Spartanburg weather.", "spartanburg"), ("Hey, forecast for St. Louis", "st. louis")])
def test_leading_fillers_keep_named_places(text, place):
    assert accepted_weather_intent(text) == WeatherIntent("named", place)


def test_qualifier_rule_is_unchanged_after_a_filler():
    intent = accepted_weather_intent("Okay. Weather in Portland, Maine")
    assert intent.permits("weather:named:portland, maine", "get_weather")
    assert not intent.permits("weather:named:portland, oregon", "get_weather")


@pytest.mark.parametrize("text", ["I'm going to Denver. Show me the weather.",
    "Not here. Show me the weather."])
def test_an_earlier_sentence_never_becomes_the_place(text):
    intent = accepted_weather_intent(text)
    assert intent.kind == "unclear"
    assert not intent.permits("weather:local:device:synthetic", "local_weather")


@pytest.mark.parametrize("previous", [WeatherIntent("named", "okay. show me the"),
    WeatherIntent("local"), WeatherIntent("unclear")])
@pytest.mark.parametrize("text,place", [("Alpharetta.", "alpharetta"),
    ("Alpharetta, Georgia", "alpharetta, georgia"), ("Spartanburg", "spartanburg"),
    ("In Spartanburg.", "spartanburg"), ("Okay, Alpharetta.", "alpharetta")])
def test_bare_place_answers_a_pending_location_question(previous, text, place):
    intent = accepted_weather_intent(text, previous, location_asked=True)
    assert intent == WeatherIntent("named", place)
    assert intent.permits(f"weather:named:{place}", "get_weather")
    assert intent.permits(f"weather:named:{place}", "get_weather_radar")
    assert not intent.permits("weather:local:device:synthetic", "local_weather")


def test_tonights_alpharetta_answer_qualified_by_the_analyst_is_permitted():
    intent = accepted_weather_intent("Alpharetta.", WeatherIntent("unclear"), location_asked=True)
    assert intent.permits("weather:named:alpharetta, ga", "get_weather")
    assert intent.permits("weather:named:alpharetta, georgia", "get_weather_radar")


def test_here_answers_a_location_question_with_device_weather():
    assert accepted_weather_intent("Here.", WeatherIntent("unclear"), location_asked=True) == WeatherIntent("local")


@pytest.mark.parametrize("text", ["Alpharetta.", "Open my notes.", "Okay.", "Thanks."])
def test_no_pending_location_question_means_no_weather(text):
    assert accepted_weather_intent(text, WeatherIntent("local")).kind == "not_weather"
    assert accepted_weather_intent(text, WeatherIntent("named", "alpharetta")).kind == "not_weather"


@pytest.mark.parametrize("previous", [None, WeatherIntent("not_weather")])
def test_location_question_after_a_non_weather_turn_grants_nothing(previous):
    assert accepted_weather_intent("Alpharetta.", previous, location_asked=True).kind == "not_weather"


@pytest.mark.parametrize("text", ["No.", "Never mind.", "Okay.", "Why do you ask?", "Cancel",
    "Show the roadmap and the calendar for 3 days", "12345"])
def test_non_answers_to_a_location_question_stay_not_weather(text):
    assert accepted_weather_intent(text, WeatherIntent("unclear"), location_asked=True).kind == "not_weather"


def test_and_portland_followup_still_works():
    first = accepted_weather_intent("Weather in Exampleburg")
    assert accepted_weather_intent("And Portland?", first) == WeatherIntent("named", "portland")
    assert accepted_weather_intent("And Portland?", first, location_asked=True) == WeatherIntent("named", "portland")


def _boundary(messages):
    return messages[-1]


@pytest.mark.parametrize("question", [ASKED, "That's not a place, Boss. Which location do you want the weather for?",
    "I need the full city name. Alfredo where?", "Which city?"])
def test_asked_for_location_reads_the_last_assistant_turn(question):
    messages = [{"role": "user", "content": "Okay. Show me the weather."},
                {"role": "assistant", "content": "Checking the weather now."},
                {"role": "assistant", "content": question},
                {"role": "user", "content": "Alpharetta."}]
    assert asked_for_location(messages, _boundary(messages))


def test_asked_for_location_reads_list_content_and_skips_system_notes():
    messages = [{"role": "assistant", "content": [{"type": "text", "text": ASKED}]},
                {"role": "user", "content": "[system] Prior task status superseded."},
                {"role": "user", "content": "Alpharetta."}]
    assert asked_for_location(messages, _boundary(messages))


@pytest.mark.parametrize("messages", [
    [{"role": "user", "content": "Alpharetta."}],
    [{"role": "assistant", "content": "One moment."}, {"role": "user", "content": "Alpharetta."}],
    [{"role": "assistant", "content": ASKED}, {"role": "user", "content": "Spartanburg"},
     {"role": "assistant", "content": "Here is the Spartanburg weather."}, {"role": "user", "content": "Alpharetta."}],
    [{"role": "assistant", "content": ASKED}, {"role": "user", "content": "No."}, {"role": "user", "content": "Alpharetta."}],
])
def test_asked_for_location_is_false_without_a_fresh_question(messages):
    assert not asked_for_location(messages, _boundary(messages))


def test_asked_for_location_needs_the_boundary_in_the_messages():
    messages = [{"role": "assistant", "content": ASKED}]
    assert not asked_for_location(messages, {"role": "user", "content": "Alpharetta."})
    assert not asked_for_location(None, None)


class _Transport:
    def __init__(self):
        self.messages = []

    def output(self):
        return self

    async def send_message(self, frame):
        self.messages.append(frame.message["data"])


async def _turn(owner, history, text, timestamp):
    await owner.before_push(owner.input_source, UserStartedSpeakingFrame())
    await owner.before_push(owner.input_source, TranscriptionFrame(text, "synthetic-user", timestamp, finalized=True))
    frame = LLMContextFrame(LLMContext(history + [{"role": "user", "content": text}]))
    await owner.before_push(owner.user_aggregator, frame)
    return owner.current


async def test_pipeline_carries_tonights_transcript_to_a_named_alpharetta_intent():
    owner = ForegroundRequests(_Transport(), "session", "generation")
    owner.input_source, owner.user_aggregator = object(), object()
    first = await _turn(owner, [], "Okay. Show me the weather.", "t1")
    assert first.weather_intent == WeatherIntent("local")
    history = [{"role": "user", "content": "Okay. Show me the weather."},
               {"role": "assistant", "content": "Checking the weather now."},
               {"role": "assistant", "content": ASKED}]
    second = await _turn(owner, history, "Alpharetta.", "t2")
    assert second.weather_intent == WeatherIntent("named", "alpharetta")


async def test_pipeline_bare_place_without_a_question_is_not_weather():
    owner = ForegroundRequests(_Transport(), "session", "generation")
    owner.input_source, owner.user_aggregator = object(), object()
    await _turn(owner, [], "What's the weather?", "t1")
    history = [{"role": "user", "content": "What's the weather?"},
               {"role": "assistant", "content": "It's 46 degrees and clear."}]
    second = await _turn(owner, history, "Alpharetta.", "t2")
    assert second.weather_intent.kind == "not_weather"
