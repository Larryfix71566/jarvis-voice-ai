"""Unit tests for jarvis/usage_ledger.py's record_completion() adapter
(MORTIMER_OPTIMIZATION_PLAN.md Phase 1, Rev 3.2, landing step (i), task 3).

Scope: the two bugs that go live once caching is on — record_completion()
previously subtracted cache READS but not cache WRITES from input_tokens
(double-billing writes at both the 1.25x/2.0x cache-write multiplier and
the full 1.0x input rate), and _CACHE_WRITE_ALIASES did not know about the
`prompt_tokens_details.cache_write_tokens` shape (OpenRouter, and now
jarvis/anthropic_shim.py's own _convert_response()).

record_call() (the actual SQLite write) is monkeypatched out in every
test — this file never touches data/costs.db or config/model_prices.yaml.
Usage objects are exercised as both plain dicts and attribute objects
(SimpleNamespace) since _get() supports both and real call sites see both
(a dict from a raw JSON response, a pydantic/attrs object from an SDK).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from jarvis import usage_ledger


@pytest.fixture
def captured_calls(monkeypatch):
    calls = []

    def _fake_record_call(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(usage_ledger, "record_call", _fake_record_call)
    return calls


def _response(usage):
    return SimpleNamespace(id="resp_1", usage=usage)


class TestRecordCompletionInputTokensFormula:
    def test_no_cache_activity_unchanged(self, captured_calls):
        # Pre-caching baseline (today's compat-layer behaviour): no cache
        # fields present at all -> input_tokens == prompt_tokens, exactly
        # as before this fix.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({"prompt_tokens": 500, "completion_tokens": 40}),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 500
        assert call["cache_read_tokens"] == 0
        assert call["cache_write_tokens"] == 0

    def test_cache_read_only_regression(self, captured_calls):
        # Today's only live case (OpenAI/OpenRouter cached_tokens, no
        # writes reported) -- must be unchanged by this fix.
        usage_ledger.record_completion(
            rung="supervisor", provider="openai", model="gpt-x",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 300},
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 300
        assert call["cache_write_tokens"] == 0
        assert call["input_tokens"] == 1000 - 300

    def test_cache_write_subtracted_dict_top_level_alias(self, captured_calls):
        # Native anthropic-shim / pipecat shape: cache_creation_input_tokens
        # at the top level of usage, alongside prompt_tokens_details.cached_tokens.
        usage_ledger.record_completion(
            rung="developer", provider="anthropic", model="claude-sonnet-5",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 40,
                "prompt_tokens_details": {"cached_tokens": 300},
                "cache_creation_input_tokens": 150,
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 300
        assert call["cache_write_tokens"] == 150
        # Before the fix this would have been 1000 - 300 = 700, double
        # billing the 150 write tokens at both 1.0x and the write multiplier.
        assert call["input_tokens"] == 1000 - 300 - 150

    def test_cache_write_subtracted_openrouter_nested_alias(self, captured_calls):
        # OpenRouter / jarvis/anthropic_shim.py's own shape: BOTH cache
        # fields live inside prompt_tokens_details, no top-level
        # cache_creation_input_tokens at all.
        usage_ledger.record_completion(
            rung="council", provider="openrouter", model="anthropic/claude-sonnet-5",
            response=_response({
                "prompt_tokens": 2000, "completion_tokens": 80,
                "prompt_tokens_details": {"cached_tokens": 500, "cache_write_tokens": 200},
            }),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 500
        assert call["cache_write_tokens"] == 200
        assert call["input_tokens"] == 2000 - 500 - 200

    def test_cache_write_and_read_via_attribute_object(self, captured_calls):
        # SimpleNamespace stand-in for a pydantic CompletionUsage /
        # PromptTokensDetails object (what a real openai.types.chat.
        # ChatCompletion.usage actually is, including the object returned
        # by jarvis/anthropic_shim.py's _convert_response()).
        usage = SimpleNamespace(
            prompt_tokens=1500, completion_tokens=60,
            prompt_tokens_details=SimpleNamespace(cached_tokens=400, cache_write_tokens=100),
        )
        usage_ledger.record_completion(
            rung="selfedit_executor", provider="anthropic", model="claude-sonnet-5",
            response=_response(usage),
        )
        call = captured_calls[0]
        assert call["cache_read_tokens"] == 400
        assert call["cache_write_tokens"] == 100
        assert call["input_tokens"] == 1500 - 400 - 100

    def test_input_tokens_never_negative(self, captured_calls):
        # Defensive: if a provider ever reports cache tokens that sum to
        # more than prompt_tokens (has happened with rounding on other
        # providers per the existing max(...,0) guard), clamp to zero
        # rather than recording a negative token count.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({
                "prompt_tokens": 100, "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": 80},
                "cache_creation_input_tokens": 50,
            }),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 0

    def test_top_level_alias_takes_priority_over_nested_when_both_present(self, captured_calls):
        # _find_first walks _CACHE_WRITE_ALIASES in order; the top-level
        # cache_creation_input_tokens alias is checked before the nested
        # prompt_tokens_details.cache_write_tokens one. Real responses
        # only ever populate one or the other, but the priority itself
        # should stay stable and documented by a test.
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({
                "prompt_tokens": 1000, "completion_tokens": 10,
                "cache_creation_input_tokens": 111,
                "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 222},
            }),
        )
        call = captured_calls[0]
        assert call["cache_write_tokens"] == 111

    def test_missing_usage_does_not_raise(self, captured_calls):
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=SimpleNamespace(id="resp_1"),
        )
        call = captured_calls[0]
        assert call["input_tokens"] == 0
        assert call["cache_write_tokens"] == 0
        assert call["cache_read_tokens"] == 0

    def test_gen_id_falls_back_to_response_id(self, captured_calls):
        usage_ledger.record_completion(
            rung="supervisor", provider="anthropic", model="claude-haiku-4-5",
            response=_response({"prompt_tokens": 10, "completion_tokens": 1}),
        )
        assert captured_calls[0]["gen_id"] == "resp_1"


class TestCacheWriteAliases:
    def test_alias_tuple_has_both_shapes(self):
        assert (None, "cache_creation_input_tokens") in usage_ledger._CACHE_WRITE_ALIASES
        assert ("prompt_tokens_details", "cache_write_tokens") in usage_ledger._CACHE_WRITE_ALIASES
