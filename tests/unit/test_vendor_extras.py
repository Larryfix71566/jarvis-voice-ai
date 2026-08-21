"""MORTIMER_VOICE_MODEL_BENCH_PLAN.md V3 — thought-signature round-trip.

Google's Gemini 3 direct endpoint attaches an encrypted `thought_signature`
to tool calls and REQUIRES it echoed back when conversation history is
replayed. The first parity run (2026-08-20) failed EVERY tool-calling case
with HTTP 400 because `_assistant_message` rebuilt history dicts keeping
only the standard OpenAI fields: role, content, id, function name/args.

The fix is generic, not Google-specific: the openai SDK's response models
are pydantic with extra="allow", so any field a provider adds lands in
`model_extra` — `_merge_vendor_extras` copies those into the replayed dict.
These tests pin both halves: extras survive when present, and NOTHING
changes when they are absent (Anthropic/Moonshot/OpenRouter responses must
be byte-identical to the pre-fix shape).
"""

from __future__ import annotations

from openai.types.chat.chat_completion_message import ChatCompletionMessage

from jarvis.agents.base import _assistant_message
from jarvis.agents.supervisor import Orchestrator


def _message(payload: dict) -> ChatCompletionMessage:
    return ChatCompletionMessage.model_validate(payload)


GOOGLE_STYLE = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "delegate_task", "arguments": "{}"},
            "extra_content": {"google": {"thought_signature": "SIG-TC"}},
        }
    ],
    "extra_content": {"google": {"thought_signature": "SIG-MSG"}},
}

PLAIN_STYLE = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "delegate_task", "arguments": "{}"},
        }
    ],
}


class TestVendorExtrasRoundTrip:
    def test_tool_call_level_extras_survive(self):
        """THE test — the signature lives on the functionCall part, which is
        exactly what Google's 400 named."""
        result = _assistant_message(_message(GOOGLE_STYLE))
        assert result["tool_calls"][0]["extra_content"] == {
            "google": {"thought_signature": "SIG-TC"}
        }

    def test_message_level_extras_survive(self):
        """Gemini can also attach the signature to the last part of the
        message rather than the function call."""
        result = _assistant_message(_message(GOOGLE_STYLE))
        assert result["extra_content"] == {
            "google": {"thought_signature": "SIG-MSG"}
        }

    def test_the_standard_fields_are_unchanged(self):
        result = _assistant_message(_message(GOOGLE_STYLE))
        assert result["role"] == "assistant"
        call = result["tool_calls"][0]
        assert call["id"] == "call_1"
        assert call["type"] == "function"
        assert call["function"] == {"name": "delegate_task", "arguments": "{}"}

    def test_a_plain_response_adds_nothing(self):
        """Anthropic/Moonshot/OpenRouter responses carry no extras, and the
        replayed dict must be byte-identical to the pre-fix shape — a new
        key sent to a provider that never produced it is exactly the kind
        of drift this generic approach must not introduce."""
        result = _assistant_message(_message(PLAIN_STYLE))
        assert set(result.keys()) == {"role", "content", "tool_calls"}
        assert set(result["tool_calls"][0].keys()) == {"id", "type", "function"}

    def test_supervisor_and_subagent_share_one_implementation(self):
        """The two loops replay history the same way; a fix applied to one
        and not the other is how this bug survives in a different surface."""
        ours = _assistant_message(_message(GOOGLE_STYLE))
        theirs = Orchestrator._assistant_message(_message(GOOGLE_STYLE))
        assert ours == theirs
