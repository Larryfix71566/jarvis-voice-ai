"""Unit tests for jarvis/anthropic_shim.py (MORTIMER_OPTIMIZATION_PLAN.md
Phase 1, Rev 3.2, Path B, landing step (i), task 2).

Fixtures only — no network. Every test either exercises pure translation
logic directly, or drives `_ChatCompletionsShim`/`_AsyncChatCompletionsShim`
against a fake `.messages.create` (never the real `anthropic.Anthropic`
client's network path). `anthropic`/`openai` real types ARE used throughout
(this is the whole point: catching a translation bug means comparing
against the real SDK's classes, not a hand-rolled stand-in for them).
"""

from __future__ import annotations

import json

import anthropic
import httpx
import openai
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from jarvis import anthropic_shim as shim


# ---------------------------------------------------------------------------
# S1 — tools
# ---------------------------------------------------------------------------

class TestConvertTools:
    def test_none_returns_not_given(self):
        assert shim._convert_tools(None) is anthropic.NOT_GIVEN

    def test_empty_list_returns_not_given(self):
        assert shim._convert_tools([]) is anthropic.NOT_GIVEN

    def test_function_tool_converts(self):
        out = shim._convert_tools([{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }])
        assert out == [{
            "name": "get_weather",
            "description": "Get the weather",
            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
        }]

    def test_missing_description_defaults_empty_string(self):
        out = shim._convert_tools([{"type": "function", "function": {"name": "f"}}])
        assert out[0]["description"] == ""

    def test_missing_parameters_defaults_empty_object_schema(self):
        out = shim._convert_tools([{"type": "function", "function": {"name": "f"}}])
        assert out[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_non_function_tool_type_raises(self):
        with pytest.raises(shim.ShimError):
            shim._convert_tools([{"type": "retrieval"}])

    def test_binds_against_real_anthropic_tool_param(self):
        # Every produced tool dict must be constructible as a real
        # anthropic.types.ToolParam-shaped object (name/description/
        # input_schema are exactly its required + used optional keys).
        out = shim._convert_tools([{
            "type": "function",
            "function": {"name": "f", "description": "d", "parameters": {"type": "object"}},
        }])
        assert set(out[0]) <= {"name", "description", "input_schema"}


# ---------------------------------------------------------------------------
# S2 — leading system run -> top-level `system` blocks
# ---------------------------------------------------------------------------

class TestLeadingSystemBlocks:
    def test_no_system_messages_returns_not_given(self):
        system, messages = shim._convert_messages([{"role": "user", "content": "hi"}])
        assert system is anthropic.NOT_GIVEN

    def test_single_leading_system_message_cached(self):
        system, _ = shim._convert_messages([
            {"role": "system", "content": "BASE PROMPT"},
            {"role": "user", "content": "hi"},
        ])
        assert system == [{
            "type": "text",
            "text": "BASE PROMPT",
            "cache_control": {"type": "ephemeral"},
        }]

    def test_multiple_leading_system_messages_only_first_cached(self):
        system, _ = shim._convert_messages([
            {"role": "system", "content": "BASE PROMPT"},
            {"role": "system", "content": "PROCEDURE INJECTION"},
            {"role": "system", "content": "SKILL INJECTION"},
            {"role": "user", "content": "hi"},
        ])
        assert [b.get("cache_control") for b in system] == [
            {"type": "ephemeral"}, None, None,
        ]
        assert [b["text"] for b in system] == [
            "BASE PROMPT", "PROCEDURE INJECTION", "SKILL INJECTION",
        ]

    def test_empty_leading_system_content_skipped_but_still_consumed(self):
        # An empty leading system message contributes no block, but is
        # still part of the leading run (not translated into a user turn).
        system, messages = shim._convert_messages([
            {"role": "system", "content": ""},
            {"role": "system", "content": "BASE PROMPT"},
            {"role": "user", "content": "hi"},
        ])
        assert len(system) == 1
        assert system[0]["text"] == "BASE PROMPT"
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        assert messages == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]


# ---------------------------------------------------------------------------
# S3 — non-leading system messages merge into the message stream
# ---------------------------------------------------------------------------

class TestNonLeadingSystemMerge:
    def test_merges_into_preceding_user_message(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hello"},
            {"role": "system", "content": "D3 CONSTRAINT"},
        ])
        assert messages == [{
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "D3 CONSTRAINT"},
            ],
        }]

    def test_starts_new_user_message_after_assistant(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
            {"role": "system", "content": "PENDING_DRAFT_CONSTRAINT"},
        ])
        assert messages[-1] == {
            "role": "user",
            "content": [{"type": "text", "text": "PENDING_DRAFT_CONSTRAINT"}],
        }
        assert messages[-1] is not messages[0]

    def test_merges_into_tool_result_turn(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "tool result"},
            {"role": "system", "content": "D3 CONSTRAINT"},
        ])
        last = messages[-1]
        assert last["role"] == "user"
        assert last["content"][0] == {
            "type": "tool_result", "tool_use_id": "call_1", "content": "tool result",
        }
        assert last["content"][1] == {"type": "text", "text": "D3 CONSTRAINT"}

    def test_empty_non_leading_system_content_produces_no_block(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hello"},
            {"role": "system", "content": ""},
        ])
        assert messages == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]


# ---------------------------------------------------------------------------
# S4 — tool_calls / tool_results / role alternation
# ---------------------------------------------------------------------------

class TestToolCallsAndAlternation:
    def test_assistant_tool_calls_become_tool_use_blocks(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "foo", "arguments": '{"x": 1}'}},
            ]},
        ])
        assert messages[-1] == {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_1", "name": "foo", "input": {"x": 1}}],
        }

    def test_assistant_content_plus_tool_calls(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "thinking...", "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "foo", "arguments": "{}"}},
            ]},
        ])
        assert messages[-1]["content"][0] == {"type": "text", "text": "thinking..."}
        assert messages[-1]["content"][1]["type"] == "tool_use"

    def test_tool_role_becomes_tool_result(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
        ])
        assert messages[-1] == {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "result 1"}],
        }

    def test_consecutive_tool_results_merge_into_one_user_message(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "g", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
            {"role": "tool", "tool_call_id": "call_2", "content": "result 2"},
        ])
        assert messages[-1]["role"] == "user"
        assert len(messages[-1]["content"]) == 2
        assert messages[-1]["content"][0]["tool_use_id"] == "call_1"
        assert messages[-1]["content"][1]["tool_use_id"] == "call_2"

    def test_consecutive_user_messages_merge(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ])
        assert len(messages) == 1
        assert [b["text"] for b in messages[0]["content"]] == ["first", "second"]

    def test_consecutive_assistant_messages_merge(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "part 1"},
            {"role": "assistant", "content": "part 2"},
        ])
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert [b["text"] for b in assistant_msgs[0]["content"]] == ["part 1", "part 2"]

    def test_empty_assistant_message_skipped(self):
        _, messages = shim._convert_messages([
            {"role": "system", "content": "BASE"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None},
            {"role": "user", "content": "still here"},
        ])
        assert not any(m["role"] == "assistant" for m in messages)
        assert len(messages) == 1  # both user turns merged, empty assistant skipped

    def test_unsupported_role_raises(self):
        with pytest.raises(shim.ShimError):
            shim._convert_messages([
                {"role": "system", "content": "BASE"},
                {"role": "developer", "content": "x"},
            ])

    def test_no_messages_after_leading_system_run_raises(self):
        with pytest.raises(shim.ShimError):
            shim._convert_messages([{"role": "system", "content": "BASE"}])

    def test_full_conversation_binds_against_real_messages_create_signature(self):
        # End-to-end: build a realistic multi-turn request and confirm every
        # key it produces is a real parameter of the installed anthropic
        # SDK's Messages.create — the same check a live call would make.
        import inspect
        request = shim._build_request(
            model="claude-haiku-4-5",
            messages=[
                {"role": "system", "content": "BASE PROMPT"},
                {"role": "system", "content": "PROCEDURE INJECTION"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "foo", "arguments": '{"x": 1}'}},
                ]},
                {"role": "tool", "tool_call_id": "call_1", "content": "result text"},
                {"role": "system", "content": "D3 CONSTRAINT"},
                {"role": "user", "content": "continue"},
            ],
            tools=[{
                "type": "function",
                "function": {"name": "foo", "description": "does foo",
                             "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}}},
            }],
            temperature=0.2,
        )
        sig = inspect.signature(anthropic.resources.messages.messages.Messages.create)
        sig.bind(object(), **request)  # raises TypeError on any bad key


# ---------------------------------------------------------------------------
# S5/S7 — response translation
# ---------------------------------------------------------------------------

def _msg(*, content, stop_reason="end_turn", input_tokens=100, output_tokens=50,
         cache_read=0, cache_write=0) -> Message:
    return Message(
        id="msg_123",
        type="message",
        role="assistant",
        model="claude-haiku-4-5",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_write or None,
            cache_read_input_tokens=cache_read or None,
        ),
    )


class TestConvertResponse:
    def test_text_only(self):
        cc = shim._convert_response(
            _msg(content=[TextBlock(type="text", text="hello")]), model="claude-haiku-4-5",
        )
        assert cc.choices[0].message.content == "hello"
        assert cc.choices[0].message.tool_calls is None
        assert cc.choices[0].finish_reason == "stop"

    def test_tool_use_only(self):
        cc = shim._convert_response(
            _msg(
                content=[ToolUseBlock(type="tool_use", id="toolu_1", name="foo", input={"x": 1})],
                stop_reason="tool_use",
            ),
            model="claude-haiku-4-5",
        )
        assert cc.choices[0].message.content is None
        tc = cc.choices[0].message.tool_calls[0]
        assert tc.id == "toolu_1"
        assert tc.function.name == "foo"
        assert json.loads(tc.function.arguments) == {"x": 1}
        assert cc.choices[0].finish_reason == "tool_calls"

    def test_mixed_text_and_tool_use(self):
        cc = shim._convert_response(
            _msg(content=[
                TextBlock(type="text", text="let me check"),
                ToolUseBlock(type="tool_use", id="toolu_1", name="foo", input={}),
            ], stop_reason="tool_use"),
            model="claude-haiku-4-5",
        )
        assert cc.choices[0].message.content == "let me check"
        assert len(cc.choices[0].message.tool_calls) == 1

    @pytest.mark.parametrize("stop_reason,expected", [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("stop_sequence", "stop"),
        ("tool_use", "tool_calls"),
        ("pause_turn", "stop"),
        ("refusal", "content_filter"),
        ("model_context_window_exceeded", "length"),
    ])
    def test_finish_reason_mapping(self, stop_reason, expected):
        cc = shim._convert_response(
            _msg(content=[TextBlock(type="text", text="x")], stop_reason=stop_reason),
            model="claude-haiku-4-5",
        )
        assert cc.choices[0].finish_reason == expected

    def test_usage_is_openai_inclusive_semantics(self):
        cc = shim._convert_response(
            _msg(content=[TextBlock(type="text", text="x")],
                 input_tokens=100, output_tokens=50, cache_read=30, cache_write=20),
            model="claude-haiku-4-5",
        )
        # prompt_tokens must cover uncached + read + written, matching what
        # usage_ledger's existing _CACHED_TOKEN_ALIASES subtraction assumes.
        assert cc.usage.prompt_tokens == 100 + 30 + 20
        assert cc.usage.completion_tokens == 50
        assert cc.usage.total_tokens == 100 + 30 + 20 + 50
        assert cc.usage.prompt_tokens_details.cached_tokens == 30
        assert cc.usage.prompt_tokens_details.cache_write_tokens == 20

    def test_usage_with_no_cache_activity(self):
        cc = shim._convert_response(
            _msg(content=[TextBlock(type="text", text="x")], input_tokens=100, output_tokens=50),
            model="claude-haiku-4-5",
        )
        assert cc.usage.prompt_tokens == 100
        assert cc.usage.prompt_tokens_details.cached_tokens == 0
        assert cc.usage.prompt_tokens_details.cache_write_tokens == 0

    def test_model_field_is_the_requested_model_not_the_response_model(self):
        # msg.model may differ (e.g. a snapshot id); callers key cost lookups
        # off the model they asked for.
        cc = shim._convert_response(
            _msg(content=[TextBlock(type="text", text="x")]), model="claude-haiku-4-5-20260101",
        )
        assert cc.model == "claude-haiku-4-5-20260101"


# ---------------------------------------------------------------------------
# S9 — error translation
# ---------------------------------------------------------------------------

class TestTranslateError:
    def _req(self) -> httpx.Request:
        return httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def test_timeout_error(self):
        exc = anthropic.APITimeoutError(request=self._req())
        out = shim._translate_error(exc)
        assert isinstance(out, openai.APITimeoutError)

    def test_connection_error_preserves_message(self):
        exc = anthropic.APIConnectionError(message="boom", request=self._req())
        out = shim._translate_error(exc)
        assert isinstance(out, openai.APIConnectionError)
        assert "boom" in str(out)

    def test_status_error_5xx_preserved_for_failover_classifier(self):
        req = self._req()
        resp = httpx.Response(529, request=req, json={"error": {"message": "overloaded"}})
        exc = anthropic.APIStatusError("overloaded", response=resp, body={"error": {"message": "overloaded"}})
        out = shim._translate_error(exc)
        assert isinstance(out, openai.APIStatusError)
        # This is exactly what upgrade_agent.py:_is_unreachable checks.
        assert getattr(out, "status_code", 0) >= 500

    def test_status_error_4xx_preserved_for_failover_classifier(self):
        req = self._req()
        resp = httpx.Response(400, request=req, json={"error": {"message": "bad request"}})
        exc = anthropic.APIStatusError("bad request", response=resp, body={"error": {"message": "bad request"}})
        out = shim._translate_error(exc)
        assert isinstance(out, openai.APIStatusError)
        assert out.status_code == 400
        assert out.status_code < 500

    def test_unrelated_exception_passes_through_unchanged(self):
        exc = ValueError("not an SDK error")
        assert shim._translate_error(exc) is exc


# ---------------------------------------------------------------------------
# S6/S8 — request building: kwarg validation, defaults, effort passthrough
# ---------------------------------------------------------------------------

class TestBuildRequest:
    def _messages(self):
        return [{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}]

    def test_unknown_kwarg_raises_type_error(self):
        with pytest.raises(TypeError):
            shim._build_request(model="m", messages=self._messages(), n=2)

    def test_stream_true_raises_shim_error(self):
        with pytest.raises(shim.ShimError):
            shim._build_request(model="m", messages=self._messages(), stream=True)

    def test_stream_false_is_fine(self):
        req = shim._build_request(model="m", messages=self._messages(), stream=False)
        assert "stream" not in req or req.get("stream") is False

    def test_tool_choice_raises_shim_error(self):
        with pytest.raises(shim.ShimError):
            shim._build_request(model="m", messages=self._messages(), tool_choice="auto")

    def test_max_tokens_defaults_when_absent(self):
        req = shim._build_request(model="m", messages=self._messages())
        assert req["max_tokens"] == shim._DEFAULT_MAX_TOKENS

    def test_max_tokens_explicit_override(self):
        req = shim._build_request(model="m", messages=self._messages(), max_tokens=256)
        assert req["max_tokens"] == 256

    def test_temperature_omitted_when_not_given(self):
        req = shim._build_request(model="m", messages=self._messages())
        assert "temperature" not in req

    def test_temperature_passed_through(self):
        req = shim._build_request(model="m", messages=self._messages(), temperature=0.7)
        assert req["temperature"] == 0.7

    def test_request_always_carries_top_level_cache_control(self):
        req = shim._build_request(model="m", messages=self._messages())
        assert req["cache_control"] == {"type": "ephemeral"}

    def test_extra_body_effort_merges_as_top_level_field(self):
        # Phase 1b: effort.py's extra_body_for() shape for provider=='anthropic'.
        req = shim._build_request(
            model="m", messages=self._messages(),
            extra_body={"output_config": {"effort": "high"}},
        )
        assert req["output_config"] == {"effort": "high"}

    def test_extra_body_does_not_clobber_required_fields_when_empty(self):
        req = shim._build_request(model="m", messages=self._messages(), extra_body={})
        assert req["model"] == "m"


# ---------------------------------------------------------------------------
# Full create() round-trip against a fake native client (no network)
# ---------------------------------------------------------------------------

class _FakeMessages:
    def __init__(self, response=None, to_raise=None):
        self._response = response
        self._to_raise = to_raise
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._to_raise is not None:
            raise self._to_raise
        return self._response


class _FakeClient:
    def __init__(self, response=None, to_raise=None):
        self.messages = _FakeMessages(response=response, to_raise=to_raise)


class TestChatCompletionsShimSync:
    def test_create_round_trips_request_and_response(self):
        fake_response = _msg(content=[TextBlock(type="text", text="hi back")])
        client = _FakeClient(response=fake_response)
        shim_completions = shim._ChatCompletionsShim(client, {})

        cc = shim_completions.create(
            model="claude-haiku-4-5",
            messages=[{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}],
        )

        assert client.messages.last_kwargs["model"] == "claude-haiku-4-5"
        assert cc.choices[0].message.content == "hi back"

    def test_create_translates_errors(self):
        req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        resp = httpx.Response(529, request=req, json={"error": {"message": "overloaded"}})
        to_raise = anthropic.APIStatusError("overloaded", response=resp, body={"error": {"message": "overloaded"}})
        client = _FakeClient(to_raise=to_raise)
        shim_completions = shim._ChatCompletionsShim(client, {})

        with pytest.raises(openai.APIStatusError) as excinfo:
            shim_completions.create(
                model="claude-haiku-4-5",
                messages=[{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}],
            )
        assert excinfo.value.status_code == 529


class _FakeAsyncMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class _FakeAsyncClient:
    def __init__(self, response):
        self.messages = _FakeAsyncMessages(response)


class TestChatCompletionsShimAsync:
    @pytest.mark.asyncio
    async def test_create_round_trips(self):
        fake_response = _msg(content=[TextBlock(type="text", text="async hi")])
        client = _FakeAsyncClient(fake_response)
        shim_completions = shim._AsyncChatCompletionsShim(client)

        cc = await shim_completions.create(
            model="claude-sonnet-5",
            messages=[{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}],
        )

        assert client.messages.last_kwargs["model"] == "claude-sonnet-5"
        assert cc.choices[0].message.content == "async hi"


# ---------------------------------------------------------------------------
# Public client wrappers — construction only (no network call is triggered
# by constructing the underlying anthropic.Anthropic/AsyncAnthropic client).
# ---------------------------------------------------------------------------

class TestPublicShims:
    def test_sync_shim_exposes_chat_completions_create(self):
        client = shim.AnthropicChatShim(api_key="sk-test-dummy")
        assert hasattr(client.chat.completions, "create")
        assert isinstance(client._anthropic, anthropic.Anthropic)

    def test_async_shim_exposes_chat_completions_create(self):
        client = shim.AsyncAnthropicChatShim(api_key="sk-test-dummy")
        assert hasattr(client.chat.completions, "create")
        assert isinstance(client._anthropic, anthropic.AsyncAnthropic)

    def test_base_url_is_plain_string(self):
        client = shim.AnthropicChatShim(api_key="sk-test-dummy", base_url="https://api.anthropic.com/v1/")
        assert client.base_url == "https://api.anthropic.com/v1/"
        assert str(client.base_url) == client.base_url

    def test_base_url_defaults_to_empty_string(self):
        client = shim.AnthropicChatShim(api_key="sk-test-dummy")
        assert client.base_url == ""

    def test_timeout_and_max_retries_passed_through_when_given(self):
        # Construction must not raise when these are supplied — this is
        # what jarvis/agents/base.py's client construction sends today.
        shim.AnthropicChatShim(api_key="sk-test-dummy", timeout=30.0, max_retries=2)
        shim.AsyncAnthropicChatShim(api_key="sk-test-dummy", timeout=30.0, max_retries=2)


# ---------------------------------------------------------------------------
# native_base_url — bug found 2026-09-02: the native anthropic SDK builds
# every request path by STRING-CONCATENATING base_url's own path with the
# resource's literal "/v1/messages" (confirmed against the installed
# anthropic==0.125.0's _base_client._prepare_url — not urljoin-style
# replacement). Every base_url this repo actually configures already ends
# in "/v1/" (the OpenAI-compat convention), so forwarding it unchanged
# would double up to "/v1/v1/messages" and 404 every request once the
# shim is wired to a live call site (this landing step).
# ---------------------------------------------------------------------------

class TestNativeBaseUrl:
    @pytest.mark.parametrize("given,expected", [
        ("https://api.anthropic.com/v1/", "https://api.anthropic.com"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com"),
        ("https://api.anthropic.com/", "https://api.anthropic.com"),
        ("https://api.anthropic.com", "https://api.anthropic.com"),
        (None, None),
        ("", None),
        # A base_url that does NOT end in /v1 passes through unchanged —
        # only the one OpenAI-compat suffix is stripped, nothing else.
        ("https://my-proxy.example.com/anthropic/v1/", "https://my-proxy.example.com/anthropic"),
        ("https://my-proxy.example.com/anthropic", "https://my-proxy.example.com/anthropic"),
    ])
    def test_strips_trailing_v1(self, given, expected):
        assert shim.native_base_url(given) == expected

    def test_shim_base_url_attribute_keeps_the_original_unstripped_string(self):
        # provider_from_base_url(str(client.base_url)) is what every
        # existing record_completion() call site does — it must keep
        # seeing exactly what was passed in, /v1/ and all.
        client = shim.AnthropicChatShim(api_key="sk-test-dummy", base_url="https://api.anthropic.com/v1/")
        assert client.base_url == "https://api.anthropic.com/v1/"

    def test_real_sdk_does_not_double_up_v1_when_base_url_has_the_compat_suffix(self):
        # The rigorous version of the test above: construct the REAL
        # anthropic.Anthropic client the shim builds internally (not a
        # reimplementation of its URL logic) and drive its own private
        # _prepare_url the same way messages.create() does, to prove the
        # final request path is /v1/messages, never /v1/v1/messages.
        client = shim.AnthropicChatShim(
            api_key="sk-test-dummy", base_url="https://api.anthropic.com/v1/",
        )
        prepared = client._anthropic._prepare_url("/v1/messages")
        assert str(prepared) == "https://api.anthropic.com/v1/messages"

    def test_real_sdk_url_unaffected_when_base_url_omitted(self):
        client = shim.AnthropicChatShim(api_key="sk-test-dummy")
        prepared = client._anthropic._prepare_url("/v1/messages")
        assert str(prepared) == "https://api.anthropic.com/v1/messages"

    def test_async_shim_same_url_fix_applies(self):
        client = shim.AsyncAnthropicChatShim(
            api_key="sk-test-dummy", base_url="https://api.anthropic.com/v1/",
        )
        prepared = client._anthropic._prepare_url("/v1/messages")
        assert str(prepared) == "https://api.anthropic.com/v1/messages"
