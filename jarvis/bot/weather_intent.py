"""Bounded weather target from accepted input, never from generated tool arguments.

This is request-scoped dispatch validation, not a location resolver or cache.
Unclear named targets refuse rather than turning into device-local weather.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import re
import unicodedata


def canonical_place(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()) or None


@dataclass(frozen=True)
class WeatherIntent:
    kind: str
    place: str | None = None

    def permits(self, subject_key: str, tool: str) -> bool:
        if not isinstance(subject_key, str) or not isinstance(tool, str):
            return False
        if self.kind == "local":
            return tool == "local_weather" and subject_key.startswith("weather:local:")
        if self.kind != "named" or not self.place or tool == "local_weather":
            return False
        actual = subject_key.removeprefix("weather:named:").rstrip(" .?!")
        # A caller may qualify an unqualified city, never change a supplied
        # qualifier (Portland, Maine must not become Portland, Oregon).
        return subject_key.startswith("weather:named:") and (
            actual == self.place or ("," not in self.place and actual.startswith(self.place + ",")))


current_weather_intent: ContextVar[WeatherIntent | None] = ContextVar("weather_intent", default=None)

_WEATHER = re.compile(r"\b(?:weather|forecast|rain|umbrella)\b", re.I)
_PREFIX = re.compile(r"^(?:(?:please|can you|could you|would you|show me|show|give me|tell me|"
    r"pull up|check|get|what is|what's|what’s|how is|how's|how’s|the)\s+)+", re.I)
# Words that follow "weather" in plain phrasing and name no place:
# "what's the weather like", "weather looking like this week" (2026-11-19).
_NONPLACE_WORDS = (r"(?:is going to be|going to be|gonna be|will be|looking like|looks like|look like|"
                   r"looking|looks|like|doing|outside|out there)")
_NONPLACE_LEAD = re.compile(r"^(?:" + _NONPLACE_WORDS + r"(?:[\s,]+|$))+", re.I)
_AFTER = re.compile(r"\b(?:weather|forecast|rain|umbrella)(?:\s+(?:forecast|conditions))?(?:\s+" + _NONPLACE_WORDS + r")*(?:\s+(?:today|tonight|tomorrow|right now|now))*\s+(?:in|for|at)\s+([^?!;]+)", re.I)
_TAIL = re.compile(r"\s+(?:weather|forecast)\b.*$", re.I)
_TIME = re.compile(r"(?:\s+(?:again|now|please|today|tonight|tomorrow|this week|this weekend|"
    r"for (?:today|tonight|tomorrow|the week)|right now))+$", re.I)
_LOCAL = frozenset({"", "me", "us", "here", "local", "current", "my", "my location", "my area",
    "where i am", "where we are", "right here", "right now", "today", "tonight", "tomorrow", "this week", "this weekend", "the week"})
_FOLLOWUP = re.compile(r"^(?:and|what about|how about)\s+(.+?)[?.!]*$", re.I)
# Leading acknowledgements and the assistant's name are not part of a place:
# "Okay. Show me the weather." once parsed as a place called "okay. show me the"
# and refused device-local weather (Larry, 2026-11-17).
_FILLER = re.compile(r"^(?:(?:okay|ok|o\.k\.|alright|all right|hey|hi|hello|so|um+|uh+|er|erm|hmm+|"
    r"yes|yeah|yep|yup|sure|well|right|thanks|thank you|mortimer|jarvis|"
    # A leading decline of the previous offer is not part of the request (2026-11-19).
    r"no thanks|no thank you|not right now|not now|not yet|maybe later|later|nope|nah|no|but)"
    r"(?:[\s,.!?;:…—–-]+|$))+", re.I)
_SENTENCE_BREAK = re.compile(r"[.!?;]\s")
# A bare answer to "which location?": letters, spaces and light punctuation,
# at most one comma qualifier, a few words. Questions are not answers.
_BARE_PLACE = re.compile(r"(?:(?:in|for|at)\s+)?([^\W\d_][\w'’.\- ]*(?:,\s*[^\W\d_][\w'’.\- ]*)?)", re.I)
_NOT_A_PLACE = frozenset({"no", "nope", "nah", "never mind", "nevermind", "cancel", "stop", "nothing",
    "forget it", "skip it", "not now", "wait", "hold on", "what", "huh", "pardon", "sorry"})
_LOCATION_QUESTION = re.compile(r"\b(?:which|what)\s+(?:location|place|city|town|area)\b|"
    r"\bwhere\b[^.!]*\?|\bcity name\b|\bwhich one\b", re.I)


def strip_filler(text: str) -> str:
    """Drop leading acknowledgements ("Okay.", "Hey Mortimer,") before parsing."""
    return _FILLER.sub("", text).strip()


def asked_for_location(messages: object, boundary: object) -> bool:
    """True when the assistant's last words before `boundary`, since the
    previous user turn, asked which place. Gates bare-place answers only; the
    place itself always comes from the user's accepted input."""
    if not isinstance(messages, list):
        return False
    try:
        end = next(i for i, m in enumerate(messages) if m is boundary)
    except StopIteration:
        return False
    for message in reversed(messages[:end]):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user":
            content = message.get("content")
            if isinstance(content, str) and content.lstrip().startswith("[system]"):
                continue
            return False
        if role != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(part.get("text", "") for part in content
                               if isinstance(part, dict) and isinstance(part.get("text"), str))
        if isinstance(content, str) and content.strip():
            return bool(_LOCATION_QUESTION.search(content[-600:]))
    return False


def _bare_place(text: str) -> str | None:
    if "?" in text or len(text) > 80:
        return None
    match = _BARE_PLACE.fullmatch(text.strip(" .!"))
    if not match:
        return None
    target = _place(match.group(1))
    if not target or target in _NOT_A_PLACE or len(target.replace(",", " ").split()) > 6:
        return None
    return target


def _place(value: str) -> str | None:
    unqualified = canonical_place(value.strip(" ,?!."))
    if unqualified in _LOCAL:
        return unqualified
    # Leading space so a bare tail ("weather please") is trimmed like "weather today please".
    value = _TIME.sub("", " " + value.strip(" ,?!.")).strip(" ,?!.")
    result = canonical_place(value)
    if result is None and unqualified:
        return ""  # only a time word or "please": no place named
    if not result or len(result) > 120 or any(c.isdigit() for c in result):
        return None
    if re.search(r"\b(?:and|or|versus|vs)\b", result):
        return None
    return result


def accepted_weather_intent(text: str, previous: WeatherIntent | None = None, *,
                            location_asked: bool = False) -> WeatherIntent:
    """`location_asked`: the assistant's last turn asked which place. Only then,
    and only after a weather request, does a bare place ("Alpharetta.") count
    as a named weather target."""
    text = " ".join(unicodedata.normalize("NFKC", text).split()).strip()
    if len(text) > 4096:
        return WeatherIntent("unclear")
    text = strip_filler(text)
    local_question = canonical_place(_TIME.sub("", text.strip(" ?.！!")))
    if local_question in {"is it going to rain", "will it rain", "do i need an umbrella",
                          "should i bring an umbrella", "what's the week look like",
                          "what’s the week look like", "what does the week look like weather-wise"}:
        return WeatherIntent("local")
    if not _WEATHER.search(text):
        follow = _FOLLOWUP.fullmatch(text)
        if follow and previous and previous.kind in {"local", "named"}:
            target = _place(follow.group(1))
            if target in {"there", "that city", "the same place"}:
                return previous
            if target and target not in _LOCAL:
                return WeatherIntent("named", target)
        if location_asked and previous and previous.kind in {"local", "named", "unclear"}:
            target = _bare_place(text)
            if target in {"there", "that city", "the same place"}:
                return previous if previous.kind == "named" else WeatherIntent("unclear")
            if target in _LOCAL:
                return WeatherIntent("local")
            if target:
                return WeatherIntent("named", target)
        return WeatherIntent("not_weather")
    places = _AFTER.findall(text)
    if len(places) > 1:
        return WeatherIntent("unclear")
    if places:
        target = _place(places[0])
    else:
        prefix = _PREFIX.sub("", text)
        if _WEATHER.match(prefix):
            tail = _NONPLACE_LEAD.sub("", _WEATHER.sub("", prefix, count=1).strip(" ,?!.")).strip(" ,?!.")
            if canonical_place(tail) == "again":
                return previous if previous and previous.kind in {"local", "named"} else WeatherIntent("unclear")
            target = _place(tail) if tail else ""
        else:
            before = _TAIL.sub("", prefix)
            # Words from an earlier sentence are not a place ("I'm off to
            # Denver. Show me the weather." must not name "…denver. show me the").
            target = None if _SENTENCE_BREAK.search(before) else _place(before)
    if target in {"there", "that city", "the same place"}:
        return previous if previous and previous.kind == "named" else WeatherIntent("unclear")
    if target is None:
        return WeatherIntent("unclear")
    if target in _LOCAL:
        return WeatherIntent("local")
    return WeatherIntent("named", target)
