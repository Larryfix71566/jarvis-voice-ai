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
_AFTER = re.compile(r"\b(?:weather|forecast|rain|umbrella)(?:\s+(?:forecast|conditions))?(?:\s+(?:today|tonight|tomorrow|right now|now))*\s+(?:in|for|at)\s+([^?!;]+)", re.I)
_TAIL = re.compile(r"\s+(?:weather|forecast)\b.*$", re.I)
_TIME = re.compile(r"(?:\s+(?:again|now|please|today|tonight|tomorrow|this week|this weekend|"
    r"for (?:today|tonight|tomorrow|the week)|right now))+$", re.I)
_LOCAL = frozenset({"", "here", "local", "current", "my", "my location", "my area",
    "where i am", "where we are", "right here", "right now", "today", "tonight", "tomorrow", "this week", "this weekend", "the week"})
_FOLLOWUP = re.compile(r"^(?:and|what about|how about)\s+(.+?)[?.!]*$", re.I)


def _place(value: str) -> str | None:
    unqualified = canonical_place(value.strip(" ,?!."))
    if unqualified in _LOCAL:
        return unqualified
    value = _TIME.sub("", value.strip(" ,?!.")).strip(" ,?!.")
    result = canonical_place(value)
    if not result or len(result) > 120 or any(c.isdigit() for c in result):
        return None
    if re.search(r"\b(?:and|or|versus|vs)\b", result):
        return None
    return result


def accepted_weather_intent(text: str, previous: WeatherIntent | None = None) -> WeatherIntent:
    text = " ".join(unicodedata.normalize("NFKC", text).split()).strip()
    if len(text) > 4096:
        return WeatherIntent("unclear")
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
        return WeatherIntent("not_weather")
    places = _AFTER.findall(text)
    if len(places) > 1:
        return WeatherIntent("unclear")
    if places:
        target = _place(places[0])
    else:
        prefix = _PREFIX.sub("", text)
        if _WEATHER.match(prefix):
            tail = _WEATHER.sub("", prefix, count=1).strip(" ,?!.")
            if canonical_place(tail) == "again":
                return previous if previous and previous.kind in {"local", "named"} else WeatherIntent("unclear")
            target = _place(tail) if tail else ""
        else:
            target = _place(_TAIL.sub("", prefix))
    if target in {"there", "that city", "the same place"}:
        return previous if previous and previous.kind == "named" else WeatherIntent("unclear")
    if target is None:
        return WeatherIntent("unclear")
    if target in _LOCAL:
        return WeatherIntent("local")
    return WeatherIntent("named", target)
