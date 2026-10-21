"""Host-only voice provenance. Serialized labels never authorize model egress.

Restrictions are monotonic for one context/session. Rewriting or dropping a
message cannot erase its source floor. New sessions get independent stores.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from jarvis.privacy_policy import DataPolicy, strictest


UNKNOWN = DataPolicy("confidential", "unclassified-voice-source")


class ClassifiedText(str):
    """An in-process result; JSON/string conversion deliberately loses proof."""

    def __new__(cls, text, policy):
        if not isinstance(text, str) or type(policy) is not DataPolicy:
            raise TypeError("host source policy required")
        if type(text) is ClassifiedText:
            policy = strictest(text.policy, policy)
        value = super().__new__(cls, text)
        object.__setattr__(value, "_policy", policy)
        return value

    def __setattr__(self, *_args):
        raise AttributeError("immutable source result")

    @property
    def policy(self):
        return self._policy


def text_policy(value):
    return value.policy if type(value) is ClassifiedText else UNKNOWN


@dataclass
class SourceAccumulator:
    policy: DataPolicy | None = None
    observations: int = 0

    def observe(self, policy):
        if type(policy) is not DataPolicy:
            policy = UNKNOWN
        self.policy = strictest(self.policy, policy) if self.policy else policy
        self.observations += 1


_source_scope = ContextVar("voice_source_scope", default=None)


def source_tracking_active():
    return _source_scope.get() is not None


def observe_source(policy):
    owner = _source_scope.get()
    if owner is not None:
        owner.observe(policy)


@contextmanager
def source_scope(policy=None):
    parent = _source_scope.get()
    inherited = parent.policy if parent else None
    selected = strictest(inherited, policy) if inherited and policy else (inherited or policy)
    owner = SourceAccumulator(selected)
    token = _source_scope.set(owner)
    try:
        yield owner
    finally:
        _source_scope.reset(token)
        if parent is not None:
            parent.observe(owner.policy or UNKNOWN)


def _digest(message):
    try:
        return hashlib.sha256(json.dumps(message, sort_keys=True, ensure_ascii=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError, RecursionError):
        return None


class VoiceSources:
    def __init__(self):
        self.context = None
        self.floor = None
        self.bindings = {}
        self.calls = {}
        self.texts = []

    def for_new_context(self):
        """Rebuilding a pipeline gets new identities but retains its floor."""
        child = VoiceSources()
        child.floor = self.floor
        return child

    def _observe(self, policy):
        level = strictest(self.floor, policy).level if self.floor else policy.level
        self.floor = DataPolicy(level, "voice-context-history")
        return self.floor

    def bind(self, message, policy):
        if type(message) is not dict or type(policy) is not DataPolicy:
            self._observe(UNKNOWN)
            return
        digest = _digest(message)
        if digest is None:
            policy = strictest(policy, UNKNOWN)
        old = self.bindings.get(id(message))
        if old and old[0] is message:
            policy = DataPolicy(strictest(old[2], policy).level, "retained-voice-source")
        self.bindings[id(message)] = (message, digest, policy)
        self._observe(policy)

    def append(self, aggregator, text, *, policy=None):
        if type(text) is ClassifiedText:
            policy = strictest(text.policy, policy) if policy else text.policy
        else:
            policy = policy or UNKNOWN
        message = {"role": "user", "content": str(text)}
        self.bind(message, policy)
        aggregator.add_messages([message])
        return message

    def rewrite(self, message, transform):
        policy = self.message_policy(message)
        transform(message)
        self.bind(message, policy)

    def model_output(self, context, result, policy):
        if context is not self.context:
            raise ValueError("foreign voice context")
        if result.text:
            self.texts.append((result.text, policy))
            self.texts = self.texts[-128:]
        for call in result.tool_calls:
            if call.tool_call_id in self.calls:
                raise ValueError("reused voice tool identity")
            self.calls[call.tool_call_id] = {
                "name": call.name, "arguments": dict(call.arguments), "policy": policy,
                "assistant": None, "placeholder": None, "result": None,
            }

    def tool_result(self, call_id, result, policy):
        call = self.calls.get(call_id)
        if call is None:
            self._observe(strictest(policy, UNKNOWN) if type(policy) is DataPolicy else UNKNOWN)
            return
        policy = strictest(call["policy"], policy)
        # Match Pipecat's completed result materialization exactly, including
        # quoted string results and its empty-result sentinel.
        content = json.dumps(result, ensure_ascii=False) if result else "COMPLETED"
        call["result"] = (str(content), policy)
        self._observe(policy)

    def added(self, message):
        old = self.bindings.get(id(message))
        if old and old[0] is message and old[1] == _digest(message):
            return
        policy = UNKNOWN
        if type(message) is dict and message.get("role") == "assistant":
            calls = message.get("tool_calls")
            if calls and len(calls) == 1:
                raw = calls[0]
                call = self.calls.get(raw.get("id"))
                try:
                    valid = (set(message) <= {"role", "content", "tool_calls"}
                        and set(raw) <= {"id", "type", "function"}
                        and set(raw["function"]) == {"name", "arguments"}
                        and raw.get("type", "function") == "function"
                        and call is not None and call["assistant"] is None
                        and raw["function"]["name"] == call["name"]
                        and json.loads(raw["function"]["arguments"]) == call["arguments"]
                        and not message.get("content"))
                except (KeyError, TypeError, ValueError):
                    valid = False
                if valid:
                    call["assistant"] = message
                    policy = call["policy"]
            elif not calls:
                for index, (text, issued) in enumerate(self.texts):
                    # Interrupted speech may retain only a spoken prefix.
                    value = message.get("content")
                    if (set(message) == {"role", "content"}
                            and type(value) is str and value and text.startswith(value)):
                        policy = issued
                        self.texts.pop(index)
                        break
        elif type(message) is dict and message.get("role") == "tool":
            call = self.calls.get(message.get("tool_call_id"))
            if (call and call["assistant"] is not None and call["placeholder"] is None
                    and set(message) == {"role", "content", "tool_call_id"}
                    and message.get("content") == "IN_PROGRESS"):
                call["placeholder"] = message
                policy = call["policy"]
        self.bind(message, policy)

    def message_policy(self, message):
        old = self.bindings.get(id(message))
        if old and old[0] is message:
            if old[1] == _digest(message):
                return old[2]
            call = self.calls.get(message.get("tool_call_id")) if type(message) is dict else None
            if (call and call["placeholder"] is message and call["result"]
                    and message == {"role": "tool", "tool_call_id": message["tool_call_id"],
                                    "content": call["result"][0]}):
                self.bind(message, call["result"][1])
                call["result"] = None
                return self.bindings[id(message)][2]
            return self._observe(strictest(old[2], UNKNOWN))
        return self._observe(UNKNOWN)

    def policy_for_context(self, context):
        if context is not self.context:
            return self._observe(UNKNOWN)
        policies = [self.message_policy(message) for message in context.get_messages()]
        active = {id(message) for message in context.get_messages()}
        self.bindings = {key: value for key, value in self.bindings.items() if key in active}
        self.calls = {key: value for key, value in self.calls.items()
                      if value["assistant"] is None or id(value["assistant"]) in active
                      or id(value["placeholder"]) in active}
        return DataPolicy(strictest(self.floor or UNKNOWN, *policies).level, "complete-voice-context")


def bound_context_type():
    # Keep provenance primitives usable without importing the voice SDK.
    from pipecat.processors.aggregators.llm_context import LLMContext

    class PolicyBoundContext(LLMContext):
        def __init__(self, *, sources, **kwargs):
            self.sources = sources
            super().__init__(**kwargs)
            if sources.context is not None:
                raise ValueError("source store already has a context")
            sources.context = self
            for message in self.get_messages():
                sources.added(message)

        def add_message(self, message):
            self.sources.added(message)
            super().add_message(message)

        def add_messages(self, messages):
            for message in messages:
                self.add_message(message)

        def set_messages(self, messages):
            for message in messages:
                self.sources.added(message)
            super().set_messages(messages)

    return PolicyBoundContext
