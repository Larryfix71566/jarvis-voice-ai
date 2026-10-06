"""Provider-neutral, policy-checked boundary for one model request.

This module preserves ordered context and approved, normalized attachments.
Provider differences remain inside route adapters; Mortimer's agent/tool loops
remain their owners' responsibility.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import math
import re
import threading
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any, Literal

from jarvis.bot.shared_content import (
    MAX_ATTACHMENTS,
    SharedContent,
    normalize_shared_content,
)
from jarvis.model_routing import (
    AccessRoute,
    ModelRouteError,
    ResolvedModelRoute,
    WorkloadLimits,
    make_route_client,
)
from jarvis.model_budget import (
    ModelBudgetUnavailable, TaskBudget, begin_model_task_budget,
    remaining_seconds, reserve_model_call_budget,
)
from jarvis.privacy_policy import (
    DataPolicy,
    assert_route_allowed,
    inherit_result_policy,
    strictest,
    tool_argument_limit,
    tool_result_limit,
    bounded_tool_arguments,
)

logger = logging.getLogger(__name__)


class ModelExecutionInputError(ValueError):
    """The request contains unsupported or malformed model input."""


class ModelExecutionOutputError(RuntimeError):
    """The provider returned output outside the caller's declared contract."""


ExecutionEventType = Literal[
    "queued", "started", "progress", "text_delta", "tool_request",
    "tool_result", "artifact", "completed", "cancelled", "failed",
]
ExecutionProgressStage = Literal["provider_request", "response_received"]


@dataclass(frozen=True)
class ModelExecutionEvent:
    """Policy-labeled event correlated to the originating request.

    Most events contain no payload. Text deltas are delivered only through the
    caller-owned in-process sink after the selected provider route has passed
    the same effective-policy check as the request; they are not usage-log or
    provider telemetry fields. Consumers must retain and enforce this policy.
    """

    task_id: str
    parent_request_id: str
    sequence: int
    event_type: ExecutionEventType
    data_policy: DataPolicy
    error_code: str | None = None
    progress_stage: ExecutionProgressStage | None = None
    text_delta: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class ModelToolReference:
    """Model-visible schema copied from Mortimer's trusted tool registry.

    This is a reference, not execution permission. The caller must still use
    Mortimer's existing permission and sandbox executor for every invocation.
    """

    name: str
    parameters: Mapping[str, Any]
    description: str = ""


@dataclass(frozen=True)
class ModelToolCall:
    """Validated provider request for a caller-owned registered tool."""

    tool_call_id: str
    name: str
    arguments: Mapping[str, Any]
    raw_arguments: str | None = None
    provider_extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelOutputRequirements:
    max_tokens: int | None = None
    require_nonempty_text: bool = False


class ModelAdmissionController:
    """One-process limit for non-voice execution, shared across event loops.

    At most two requests execute at once and at most one is background. This
    leaves one slot available to interactive work even while background work
    is queued. Waiting interactive requests are admitted ahead of background
    waiters as soon as capacity becomes available. A condition variable owns
    the counters so synchronous workers and multiple async loops cannot each
    create a separate effective capacity pool.
    """

    def __init__(self, *, max_active: int = 2, max_background: int = 1):
        if max_active < 1 or max_background < 0 or max_background >= max_active:
            raise ValueError("admission limits must reserve an interactive slot")
        self._max_active = max_active
        self._max_background = max_background
        self._condition = threading.Condition()
        self._active_interactive = 0
        self._active_background = 0
        self._waiters: list[tuple[int, str, object]] = []
        self._next_ticket = 0

    @property
    def active_counts(self) -> tuple[int, int]:
        """Return (interactive, background) counts for diagnostics/tests."""
        with self._condition:
            return self._active_interactive, self._active_background

    @property
    def waiting_interactive(self) -> int:
        with self._condition:
            return sum(priority == "interactive" for _, priority, _ in self._waiters)

    def _can_start(self, priority: str, token: object) -> bool:
        active = self._active_interactive + self._active_background
        if active >= self._max_active:
            return False

        earlier = [
            (ticket, queued_priority)
            for ticket, queued_priority, queued_token in self._waiters
            if queued_token is not token
        ]
        interactive_waiters = [
            ticket for ticket, queued_priority in earlier
            if queued_priority == "interactive"
        ]
        if priority == "interactive":
            own_ticket = next(
                ticket for ticket, queued_priority, queued_token in self._waiters
                if queued_token is token
            )
            return not any(ticket < own_ticket for ticket in interactive_waiters)
        if priority == "background":
            earlier_background = [
                ticket for ticket, queued_priority in earlier
                if queued_priority == "background"
            ]
            own_ticket = next(
                ticket for ticket, queued_priority, queued_token in self._waiters
                if queued_token is token
            )
            return (
                self._active_background < self._max_background
                and not interactive_waiters
                and not any(ticket < own_ticket for ticket in earlier_background)
            )
        return False

    def _acquire(self, priority: str, cancelled: threading.Event) -> bool:
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            token = object()
            waiter = (ticket, priority, token)
            self._waiters.append(waiter)
            while True:
                if cancelled.is_set():
                    self._waiters.remove(waiter)
                    self._condition.notify_all()
                    return False
                if self._can_start(priority, token):
                    self._waiters.remove(waiter)
                    if priority == "interactive":
                        self._active_interactive += 1
                    else:
                        self._active_background += 1
                    self._condition.notify_all()
                    return True
                self._condition.wait(timeout=0.05)

    def _release(self, priority: str) -> None:
        with self._condition:
            if priority == "interactive":
                self._active_interactive -= 1
            else:
                self._active_background -= 1
            self._condition.notify_all()

    @asynccontextmanager
    async def slot(self, priority: str) -> AsyncIterator[None]:
        if priority not in {"interactive", "background"}:
            raise ModelExecutionInputError("priority must be interactive or background")
        cancelled = threading.Event()
        acquisition = asyncio.create_task(asyncio.to_thread(
            self._acquire, priority, cancelled,
        ))
        try:
            acquired = await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            cancelled.set()
            with self._condition:
                self._condition.notify_all()
            try:
                acquired = await asyncio.shield(acquisition)
            except asyncio.CancelledError:
                acquired = False
            if acquired:
                self._release(priority)
            raise
        if not acquired:
            raise asyncio.CancelledError
        try:
            yield
        finally:
            self._release(priority)


_PROCESS_ADMISSION = ModelAdmissionController()


@dataclass(frozen=True)
class ModelContextMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    data_policy: DataPolicy = field(default_factory=DataPolicy)
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    provider_extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelAttachment:
    """Normalized content, its source policy and exact external approval."""

    content: SharedContent
    data_policy: DataPolicy = field(default_factory=DataPolicy)
    approved_route: str | None = None
    approved_model_identity: str | None = None


@dataclass(frozen=True)
class ModelExecutionRequest:
    workload: str
    task_id: str
    parent_request_id: str
    instructions: str
    context: tuple[ModelContextMessage | str, ...] = ()
    attachments: tuple[ModelAttachment, ...] = ()
    tools: tuple[ModelToolReference, ...] = ()
    output: ModelOutputRequirements = field(default_factory=ModelOutputRequirements)
    data_policy: DataPolicy = field(default_factory=DataPolicy)
    timeout_s: float = 60.0
    stream_text: bool = False
    extra_body: Mapping[str, Any] | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class ModelExecutionResult:
    task_id: str
    parent_request_id: str
    model: str
    provider: str
    route: str
    billing: str
    text: str
    data_policy: DataPolicy
    tool_calls: tuple[ModelToolCall, ...] = ()
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    duration_ms: float = 0.0
    response_id: str | None = None
    provider_extras: Mapping[str, Any] = field(default_factory=dict)


def _validated_inputs(request: ModelExecutionRequest,
                      resolved: ResolvedModelRoute
                      ) -> tuple[
                          list[dict[str, Any]], DataPolicy, list[dict[str, Any]],
                          dict[str, Any], set[str]
                      ]:
    if (not isinstance(request.workload, str) or not request.workload
            or request.workload != resolved.workload):
        raise ModelExecutionInputError("request workload does not match resolved route")
    if (not isinstance(request.task_id, str) or not request.task_id.strip()
            or not isinstance(request.parent_request_id, str)
            or not request.parent_request_id.strip()):
        raise ModelExecutionInputError("task and parent request IDs are required")
    if not isinstance(request.instructions, str):
        raise ModelExecutionInputError("instructions must be text")
    if (isinstance(request.timeout_s, bool) or not isinstance(request.timeout_s, (int, float))
            or not math.isfinite(request.timeout_s) or request.timeout_s <= 0):
        raise ModelExecutionInputError("timeout must be a positive finite number")
    if not isinstance(request.data_policy, DataPolicy):
        raise ModelExecutionInputError("request data policy is invalid")
    if not isinstance(request.output, ModelOutputRequirements):
        raise ModelExecutionInputError("output requirements are invalid")
    max_tokens = request.output.max_tokens
    if max_tokens is not None and (
            isinstance(max_tokens, bool) or not isinstance(max_tokens, int)
            or not 1 <= max_tokens <= 32_000):
        raise ModelExecutionInputError("max_tokens must be an integer from 1 to 32000")
    if not isinstance(request.output.require_nonempty_text, bool):
        raise ModelExecutionInputError("require_nonempty_text must be boolean")
    if not isinstance(request.stream_text, bool):
        raise ModelExecutionInputError("stream_text must be boolean")
    if request.stream_text and "streaming" not in resolved.route.capabilities:
        raise ModelRouteError(
            f"route {resolved.route.name!r} lacks required capability: streaming"
        )
    if request.temperature is not None and (
            isinstance(request.temperature, bool)
            or not isinstance(request.temperature, (int, float))
            or not math.isfinite(request.temperature)):
        raise ModelExecutionInputError("temperature must be a finite number or None")
    if (request.extra_body is not None
            and (resolved.provider != "anthropic"
                 or not isinstance(request.extra_body, Mapping)
                 or set(request.extra_body) != {"output_config"}
                 or not isinstance(request.extra_body.get("output_config"), Mapping)
                 or set(request.extra_body["output_config"]) != {"effort"}
                 or request.extra_body["output_config"].get("effort")
                 not in {"low", "medium", "high", "xhigh", "max"})):
        raise ModelExecutionInputError(
            "only a supported Anthropic output-effort parameter is allowed"
        )
    if max_tokens is not None and resolved.route.adapter not in {
            "openai_compatible", "saygm_gateway"}:
        raise ModelRouteError(
            f"route {resolved.route.name!r} cannot enforce max_tokens")
    if not isinstance(request.context, tuple):
        raise ModelExecutionInputError("context must be an immutable tuple")

    messages: list[dict[str, Any]] = []
    policies = [request.data_policy]
    pending_tool_results: dict[str, str] = {}
    seen_tool_call_ids: set[str] = set()
    history_tool_names: set[str] = set()
    for item in request.context:
        # Strings were the only practical context shape in the original
        # uncalled foundation. Keep them as ordinary user context; reject all
        # other untyped objects rather than silently coercing or dropping them.
        if isinstance(item, str):
            item = ModelContextMessage("user", item)
        if not isinstance(item, ModelContextMessage):
            raise ModelExecutionInputError("context items must be text messages")
        if not isinstance(item.role, str) or item.role not in {
                "system", "user", "assistant", "tool"}:
            raise ModelExecutionInputError("unsupported context message role")
        if not isinstance(item.data_policy, DataPolicy):
            raise ModelExecutionInputError("context data policy is invalid")
        quota = tool_result_limit(item.name) if item.role == 'tool' else 1_000_000
        if not isinstance(item.content, str) or len(item.content) > quota:
            raise ModelExecutionInputError("context message content must be bounded text")
        if not isinstance(item.tool_calls, tuple):
            raise ModelExecutionInputError("context tool calls must be an immutable tuple")
        if item.role == "tool":
            if (not item.content.strip() or not isinstance(item.name, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", item.name)
                    or not isinstance(item.tool_call_id, str)
                    or pending_tool_results.get(item.tool_call_id) != item.name
                    or item.tool_calls):
                raise ModelExecutionInputError("tool result does not match a pending tool call")
            pending_tool_results.pop(item.tool_call_id)
            messages.append({
                "role": "tool", "tool_call_id": item.tool_call_id,
                "name": item.name, "content": item.content,
            })
        elif item.role == "assistant" and item.tool_calls:
            if pending_tool_results or item.name is not None or item.tool_call_id is not None:
                raise ModelExecutionInputError("assistant tool-call message is out of order")
            if len(item.tool_calls) > 16:
                raise ModelExecutionInputError("context has too many tool calls")
            message_extras = _validated_provider_extras(
                item.provider_extras,
                reserved={"role", "content", "tool_calls"},
                label="assistant message",
            )
            wire_calls = []
            for call in item.tool_calls:
                if (not isinstance(call, ModelToolCall)
                        or not isinstance(call.tool_call_id, str)
                        or not call.tool_call_id.strip() or len(call.tool_call_id) > 256
                        or call.tool_call_id in seen_tool_call_ids
                        or not isinstance(call.name, str)
                        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", call.name)
                        or not isinstance(call.arguments, Mapping)):
                    raise ModelExecutionInputError("assistant tool-call context is malformed")
                raw_arguments = call.raw_arguments
                if raw_arguments is None:
                    raw_arguments = json.dumps(call.arguments, separators=(",", ":"))
                if not isinstance(raw_arguments, str) or len(raw_arguments) > tool_argument_limit(call.name):
                    raise ModelExecutionInputError("assistant tool arguments exceed the limit")
                try:
                    parsed_arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise ModelExecutionInputError("assistant tool arguments are malformed") from exc
                if not isinstance(parsed_arguments, dict) or dict(call.arguments) != parsed_arguments:
                    raise ModelExecutionInputError("assistant tool arguments do not match their JSON")
                try:
                    bounded_tool_arguments(call.name, parsed_arguments)
                except ValueError as exc:
                    raise ModelExecutionInputError('assistant tool arguments exceed the canonical limit') from exc
                call_extras = _validated_provider_extras(
                    call.provider_extras,
                    reserved={"id", "type", "function"},
                    label="tool call",
                )
                pending_tool_results[call.tool_call_id] = call.name
                seen_tool_call_ids.add(call.tool_call_id)
                history_tool_names.add(call.name)
                wire_call = {
                    "id": call.tool_call_id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": raw_arguments},
                }
                wire_call.update(call_extras)
                wire_calls.append(wire_call)
            if item.content and not item.content.strip():
                raise ModelExecutionInputError("assistant tool-call content is invalid")
            wire_message = {
                "role": "assistant", "content": item.content or None,
                "tool_calls": wire_calls,
            }
            wire_message.update(message_extras)
            messages.append(wire_message)
        else:
            if (not item.content.strip() or item.name is not None
                    or item.tool_call_id is not None or item.tool_calls
                    or item.provider_extras):
                raise ModelExecutionInputError("context message has invalid role-specific fields")
            messages.append({"role": item.role, "content": item.content})
        policies.append(item.data_policy)

    if pending_tool_results:
        raise ModelExecutionInputError("context ends before every tool call has a result")

    attachments = request.attachments
    if not isinstance(attachments, tuple):
        raise ModelExecutionInputError("attachments must be an immutable tuple")
    if len(attachments) > MAX_ATTACHMENTS:
        raise ModelExecutionInputError(
            f"at most {MAX_ATTACHMENTS} attachments are supported"
        )

    user_content: str | list[dict[str, Any]] = request.instructions.strip()
    seen_content_ids: set[str] = set()
    for attachment in attachments:
        if (not isinstance(attachment, ModelAttachment)
                or not isinstance(attachment.content, SharedContent)
                or not attachment.content.ephemeral):
            raise ModelExecutionInputError("attachments must be normalized ephemeral content")
        if not isinstance(attachment.data_policy, DataPolicy):
            raise ModelExecutionInputError("attachment data policy is invalid")
        if attachment.data_policy.level == "approved_external" and (
                attachment.approved_route != resolved.route.name
                or attachment.approved_model_identity != resolved.identity):
            raise ModelExecutionInputError(
                "external attachment approval does not match the selected route and model"
            )
        item = attachment.content
        if not isinstance(item.content_id, str) or not item.content_id.strip():
            raise ModelExecutionInputError("attachment identity is required")
        if item.content_id in seen_content_ids:
            raise ModelExecutionInputError("duplicate attachment identity")
        seen_content_ids.add(item.content_id)
        try:
            if item.kind == "text":
                normalized = normalize_shared_content(kind="text", text=item.text)
            elif item.kind == "image":
                normalized = normalize_shared_content(
                    kind="image", data=item.data, mime_type=item.mime_type
                )
            else:
                raise ModelExecutionInputError("unsupported attachment kind")
        except ValueError as exc:
            raise ModelExecutionInputError(str(exc)) from exc

        policies.append(attachment.data_policy)
        if normalized.kind == "text":
            block = f"[Attached text]\n{normalized.text}"
            if isinstance(user_content, list):
                user_content.append({"type": "text", "text": block})
            else:
                user_content += f"\n\n{block}"
            continue
        if "images" not in resolved.route.capabilities:
            raise ModelRouteError(f"route {resolved.route.name!r} lacks required capability: images")
        encoded = base64.b64encode(normalized.data or b"").decode("ascii")
        if not isinstance(user_content, list):
            user_content = [{"type": "text", "text": user_content}]
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{normalized.mime_type};base64,{encoded}",
                "detail": "auto",
            },
        })

    if request.instructions.strip() or attachments:
        messages.append({"role": "user", "content": user_content})
    elif not messages:
        raise ModelExecutionInputError("request requires instructions or context")

    if not isinstance(request.tools, tuple):
        raise ModelExecutionInputError("tools must be an immutable tuple")
    if len(request.tools) > 32:
        raise ModelExecutionInputError("at most 32 registered tool references are supported")
    tool_schemas: list[dict[str, Any]] = []
    tool_names: set[str] = set()
    tool_validators: dict[str, Any] = {}
    if request.tools and "tools" not in resolved.route.capabilities:
        raise ModelRouteError(f"route {resolved.route.name!r} lacks required capability: tools")
    for tool in request.tools:
        if not isinstance(tool, ModelToolReference):
            raise ModelExecutionInputError("tools must be trusted registered references")
        if (not isinstance(tool.name, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tool.name)):
            raise ModelExecutionInputError("tool reference name is invalid")
        if tool.name in tool_names:
            raise ModelExecutionInputError("duplicate tool reference name")
        if not isinstance(tool.parameters, Mapping):
            raise ModelExecutionInputError("tool parameters must be a JSON schema mapping")
        try:
            encoded_schema = json.dumps(
                dict(tool.parameters), ensure_ascii=False, allow_nan=False,
                separators=(",", ":"),
            )
            schema = json.loads(encoded_schema)
        except (TypeError, ValueError) as exc:
            raise ModelExecutionInputError("tool schema must contain JSON values") from exc
        if len(encoded_schema) > 32_768 or schema.get("type") != "object":
            raise ModelExecutionInputError("tool schema must be a bounded object schema")
        if not isinstance(tool.description, str) or len(tool.description) > 2_000:
            raise ModelExecutionInputError("tool description is invalid or exceeds quota")
        if _contains_schema_ref(schema):
            raise ModelExecutionInputError("external tool-schema references are not supported")
        try:
            from jsonschema import Draft202012Validator
            Draft202012Validator.check_schema(schema)
            tool_validators[tool.name] = Draft202012Validator(schema)
        except ImportError as exc:
            raise ModelExecutionInputError(
                "JSON Schema validation is unavailable; refusing tool references"
            ) from exc
        except Exception as exc:
            raise ModelExecutionInputError("tool parameters contain an invalid JSON schema") from exc
        tool_names.add(tool.name)
        tool_schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            },
        })
    if history_tool_names - tool_names:
        raise ModelExecutionInputError(
            "tool history references a tool outside the caller's current allowlist"
        )
    # Historical calls are sent to the provider again. Apply the same current
    # registered schemas as new calls, after the trusted validators exist.
    for item in request.context:
        if isinstance(item, ModelContextMessage):
            for call in item.tool_calls:
                try:
                    tool_validators[call.name].validate(dict(call.arguments))
                except Exception as exc:
                    raise ModelExecutionInputError(
                        'historical tool arguments do not match the registered schema') from exc

    effective_policy = strictest(*policies)
    assert_route_allowed(resolved.route, effective_policy)
    return messages, effective_policy, tool_schemas, tool_validators, seen_tool_call_ids


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _contains_schema_ref(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(key == "$ref" or _contains_schema_ref(item)
                   for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_schema_ref(item) for item in value)
    return False


def _validated_provider_extras(value: Any, *, reserved: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or len(value) > 32:
        raise ModelExecutionInputError(f"{label} provider metadata is malformed")
    if any(not isinstance(key, str) or not key or key in reserved for key in value):
        raise ModelExecutionInputError(f"{label} provider metadata has a reserved key")
    try:
        encoded = json.dumps(
            dict(value), ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        copied = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ModelExecutionInputError(f"{label} provider metadata is not JSON data") from exc
    if len(encoded.encode("utf-8")) > 16_384:
        raise ModelExecutionInputError(f"{label} provider metadata exceeds its quota")
    return copied


def _usage_count(usage: Any, *names: str) -> int | None:
    for name in names:
        value = usage
        for component in name.split("."):
            value = _field(value, component)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _validated_tool_calls(message: Any,
                          validators: Mapping[str, Any], *,
                          seen_ids: set[str] | None = None) -> tuple[ModelToolCall, ...]:
    raw_calls = _field(message, "tool_calls") or ()
    if not isinstance(raw_calls, (list, tuple)):
        raise ModelExecutionOutputError("provider tool-call output is malformed")
    if len(raw_calls) > 16:
        raise ModelExecutionOutputError("provider returned too many tool calls")
    calls: list[ModelToolCall] = []
    call_ids: set[str] = set(seen_ids or ())
    for raw in raw_calls:
        call_id = _field(raw, "id")
        function = _field(raw, "function")
        name = _field(function, "name")
        arguments = _field(function, "arguments")
        if (not isinstance(call_id, str) or not call_id.strip()
                or len(call_id) > 256 or call_id in call_ids):
            raise ModelExecutionOutputError("provider returned an invalid tool-call identity")
        if not isinstance(name, str) or name not in validators:
            raise ModelExecutionOutputError("provider requested a tool outside the allowlist")
        if not isinstance(arguments, str) or len(arguments) > tool_argument_limit(name):
            raise ModelExecutionOutputError("provider returned invalid or oversized tool arguments")
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ModelExecutionOutputError("provider returned malformed tool arguments") from exc
        if not isinstance(parsed, dict):
            raise ModelExecutionOutputError("tool arguments must be a JSON object")
        try:
            bounded_tool_arguments(name, parsed)
        except ValueError as exc:
            raise ModelExecutionOutputError('provider tool arguments exceed the canonical limit') from exc
        try:
            validators[name].validate(parsed)
        except Exception as exc:
            raise ModelExecutionOutputError(
                "provider tool arguments do not match the registered schema"
            ) from exc
        call_ids.add(call_id)
        raw_extras = _field(raw, "model_extra") or {}
        call_extras = _validated_provider_extras(
            raw_extras, reserved={"id", "type", "function"}, label="provider tool call"
        )
        calls.append(ModelToolCall(call_id, name, parsed, arguments, call_extras))
    if calls and not validators:
        raise ModelExecutionOutputError("provider requested tools when none were permitted")
    return tuple(calls)


async def _collect_chat_stream(stream: Any,
                              on_text_delta: Callable[[str], Any], *,
                              allowed_tools: tuple[str, ...] = ()) -> Any:
    """Collect OpenAI-shaped chunks without exposing partial tool arguments.

    Text deltas are policy-bearing events; tool requests are reconstructed and
    validated only after a provider finish marker arrives. The stream is
    always closed on completion, error, deadline or caller cancellation.
    """
    text_parts: list[str] = []
    tool_parts: dict[int, dict[str, Any]] = {}
    response_id: str | None = None
    usage: Any = None
    finish_reason: str | None = None
    try:
        async for chunk in stream:
            candidate_id = _field(chunk, "id")
            if isinstance(candidate_id, str) and candidate_id:
                if response_id is not None and response_id != candidate_id:
                    raise ModelExecutionOutputError("provider changed the stream response identity")
                response_id = candidate_id
            candidate_usage = _field(chunk, "usage")
            if candidate_usage is not None:
                usage = candidate_usage
            choices = _field(chunk, "choices") or ()
            if not choices:
                continue
            if not isinstance(choices, (list, tuple)) or len(choices) > 1:
                raise ModelExecutionOutputError("provider stream choice shape is unsupported")
            choice = choices[0]
            delta = _field(choice, "delta")
            content = _field(delta, "content")
            if content is not None:
                if not isinstance(content, str):
                    raise ModelExecutionOutputError("provider streamed non-text content")
                if content:
                    text_parts.append(content)
                    observed = on_text_delta(content)
                    if inspect.isawaitable(observed):
                        await observed
            calls = _field(delta, "tool_calls") or ()
            if not isinstance(calls, (list, tuple)) or len(calls) > 16:
                raise ModelExecutionOutputError("provider streamed malformed tool calls")
            for part in calls:
                index = _field(part, "index")
                if (isinstance(index, bool) or not isinstance(index, int)
                        or not 0 <= index < 16):
                    raise ModelExecutionOutputError("provider streamed an invalid tool index")
                state = tool_parts.setdefault(index, {
                    "id": None, "name": "", "arguments": "", "extras": {},
                })
                call_id = _field(part, "id")
                if call_id is not None:
                    if not isinstance(call_id, str) or not call_id.strip():
                        raise ModelExecutionOutputError("provider streamed an invalid tool identity")
                    if state["id"] not in (None, call_id):
                        raise ModelExecutionOutputError("provider changed a streamed tool identity")
                    state["id"] = call_id
                function = _field(part, "function")
                for key in ("name", "arguments"):
                    fragment = _field(function, key)
                    if fragment is not None:
                        if not isinstance(fragment, str):
                            raise ModelExecutionOutputError("provider streamed malformed tool data")
                        state[key] += fragment
                        if len(state['name']) > 64:
                            raise ModelExecutionOutputError("provider streamed oversized tool data")
                        # A provider may send arguments before completing the
                        # name. Bound that buffer by the permitted name prefixes;
                        # the final exact name/schema is still checked before a
                        # tool_request event or operation can be published.
                        quota = max((tool_argument_limit(name) for name in allowed_tools
                                     if name.startswith(state['name'])), default=16_384)
                        if len(state['arguments']) > quota:
                            raise ModelExecutionOutputError("provider streamed oversized tool data")
                raw_extras = _field(part, "model_extra") or {}
                extras = _validated_provider_extras(
                    raw_extras, reserved={"index", "id", "type", "function"},
                    label="streamed tool call",
                )
                for key, value in extras.items():
                    previous = state["extras"].get(key)
                    if previous is not None and previous != value:
                        raise ModelExecutionOutputError("provider changed streamed tool metadata")
                    state["extras"][key] = value
            candidate_finish = _field(choice, "finish_reason")
            if candidate_finish is not None:
                if (not isinstance(candidate_finish, str)
                        or candidate_finish not in {
                            "stop", "length", "tool_calls", "function_call", "content_filter",
                        }):
                    raise ModelExecutionOutputError("provider returned an unknown stream finish reason")
                if finish_reason is not None and finish_reason != candidate_finish:
                    raise ModelExecutionOutputError("provider changed stream finish reason")
                finish_reason = candidate_finish
    finally:
        close = getattr(stream, "aclose", None) or getattr(stream, "close", None)
        if callable(close):
            try:
                closed = close()
                if inspect.isawaitable(closed):
                    await closed
            except Exception as exc:  # noqa: BLE001 — cleanup cannot mask task outcome
                logger.warning("model_stream_cleanup_failed: %s", type(exc).__name__)

    if finish_reason is None:
        raise ModelExecutionOutputError("provider stream ended without a finish marker")
    calls = []
    for index in sorted(tool_parts):
        state = tool_parts[index]
        if not state["id"]:
            raise ModelExecutionOutputError("provider streamed a tool call without an identity")
        calls.append(SimpleNamespace(
            id=state["id"], type="function",
            function=SimpleNamespace(name=state["name"], arguments=state["arguments"]),
            model_extra=state["extras"],
        ))
    message = SimpleNamespace(
        content="".join(text_parts) or None,
        tool_calls=calls,
        model_extra={},
    )
    return SimpleNamespace(
        id=response_id,
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=usage,
    )


async def execute_chat(request: ModelExecutionRequest,
                       resolved: ResolvedModelRoute,
                       *,
                       client_factory: Callable[..., Any] | None = None,
                       event_sink: Callable[[ModelExecutionEvent], Any] | None = None,
                       event_sink_policy: DataPolicy | None = None,
                       admission: ModelAdmissionController | None = None,
                       task_budget: TaskBudget | None = None) -> ModelExecutionResult:
    """Execute one validated request, preserving context and attachments.

    Cancellation propagates to the provider client, and the outer deadline
    prevents late results from being returned to callers. Tool loops remain
    owned by their existing agent boundary.
    """
    entry_loop_time = asyncio.get_running_loop().time()
    started_at = time.monotonic()
    budget_started_at = time.time()
    request = _limited_output_request(request, resolved.limits.max_output_tokens_per_call)
    messages, effective_policy, tools, tool_validators, seen_tool_call_ids = _validated_inputs(
        request, resolved
    )
    if request.stream_text and event_sink is not None:
        if not isinstance(event_sink_policy, DataPolicy):
            raise ModelExecutionInputError(
                "streamed text events require an explicitly classified event sink"
            )
        assert_route_allowed(
            AccessRoute(
                name="execution_event_sink", adapter="in_process_sink", billing="none",
                credential_env=None, privacy=event_sink_policy.level,
                capabilities=("text",),
            ),
            inherit_result_policy(effective_policy),
        )
    controller = admission or _PROCESS_ADMISSION
    sequence = 0
    deadline: asyncio.Timeout | None = None

    def require_active() -> None:
        # Awaited adapters and observers can swallow CancelledError. The
        # timeout object's state and monotonic deadline still own admission
        # and publication, even after such an await returns a late value.
        current = asyncio.current_task()
        timed_out = deadline is not None and (
            deadline.expired() or (deadline.when() is not None
                                   and asyncio.get_running_loop().time() >= deadline.when())
        )
        if timed_out:
            raise TimeoutError
        if current is not None and current.cancelling():
            raise asyncio.CancelledError

    async def observe(event: ModelExecutionEvent, *, terminal: bool = False) -> None:
        if not terminal:
            require_active()
        try:
            observed = event_sink(event)
            if inspect.isawaitable(observed):
                await observed
        except Exception:  # noqa: BLE001 — telemetry observers never own request outcome
            pass
        if not terminal:
            require_active()

    async def emit(event_type: ExecutionEventType, *, error_code: str | None = None,
                   progress_stage: ExecutionProgressStage | None = None,
                   text_delta: str | None = None) -> None:
        nonlocal sequence
        terminal = event_type in {"cancelled", "failed"}
        if not terminal:
            require_active()
        sequence += 1
        if event_sink is None:
            return
        event = ModelExecutionEvent(
            task_id=request.task_id,
            parent_request_id=request.parent_request_id,
            sequence=sequence,
            event_type=event_type,
            data_policy=effective_policy,
            error_code=error_code,
            progress_stage=progress_stage,
            text_delta=text_delta,
        )
        await observe(event, terminal=terminal)

    async def emit_tool_request(call: ModelToolCall) -> None:
        nonlocal sequence
        require_active()
        sequence += 1
        if event_sink is None:
            return
        event = ModelExecutionEvent(
            task_id=request.task_id,
            parent_request_id=request.parent_request_id,
            sequence=sequence,
            event_type="tool_request",
            data_policy=effective_policy,
            tool_call_id=call.tool_call_id,
            tool_name=call.name,
        )
        await observe(event)

    async def emit_tool_result(call_id: str, name: str) -> None:
        nonlocal sequence
        require_active()
        sequence += 1
        if event_sink is None:
            return
        event = ModelExecutionEvent(
            task_id=request.task_id,
            parent_request_id=request.parent_request_id,
            sequence=sequence,
            event_type="tool_result",
            data_policy=effective_policy,
            tool_call_id=call_id,
            tool_name=name,
        )
        await observe(event)

    client = None
    try:
        # The deadline includes lifecycle admission and time spent queued for
        # capacity; cancellation at either point must still emit one terminal
        # event rather than escaping before the lifecycle guard is active.
        setup_limit = request.timeout_s
        if resolved.limits.deadline_seconds is not None:
            setup_limit = min(setup_limit, resolved.limits.deadline_seconds)
        if (isinstance(task_budget, TaskBudget) and type(task_budget.limits) is WorkloadLimits
                and task_budget.limits.deadline_seconds is not None):
            setup_limit = min(setup_limit, task_budget.limits.deadline_seconds)
        async with asyncio.timeout_at(entry_loop_time + setup_limit) as deadline:
            require_active()
            limits = resolved.limits
            if task_budget is not None:
                if (not isinstance(task_budget, TaskBudget) or task_budget.workload != request.workload
                        or task_budget.parent_request_id != request.parent_request_id):
                    raise ModelBudgetUnavailable("budget_scope_mismatch")
                # Validate the host handle and retain its earlier output-only
                # cap. Durable state is reopened below, never accepted from
                # caller-provided policy fields as the spending authority.
                await asyncio.to_thread(remaining_seconds, task_budget)
                require_active()
                limits = WorkloadLimits(*(
                    min(first, second) if first is not None and second is not None
                    else first if first is not None else second
                    for first, second in zip(
                        (limits.max_output_tokens_per_call, limits.deadline_seconds,
                         limits.max_estimated_spend_usd_per_task),
                        (task_budget.limits.max_output_tokens_per_call,
                         task_budget.limits.deadline_seconds,
                         task_budget.limits.max_estimated_spend_usd_per_task),
                    )
                ))
            budget = await asyncio.to_thread(
                begin_model_task_budget, request.workload,
                request.parent_request_id, limits, started_at=budget_started_at,
            )
            require_active()
            # The durable parent's bounds can be stricter than a new route
            # snapshot (including after configuration is cleared/restarted).
            request = _limited_output_request(request, budget.limits.max_output_tokens_per_call)
            messages, effective_policy, tools, tool_validators, seen_tool_call_ids = _validated_inputs(
                request, resolved,
            )
            remaining = await asyncio.to_thread(remaining_seconds, budget)
            require_active()
            if remaining <= 0:
                raise ModelBudgetUnavailable("budget_deadline_exhausted")
            tightened_deadline = asyncio.get_running_loop().time() + min(
                remaining, max(0, request.timeout_s - (time.monotonic() - started_at)),
            )
            deadline.reschedule(min(deadline.when(), tightened_deadline))
            spend_capped = budget.limits.max_estimated_spend_usd_per_task is not None
            if spend_capped:
                if resolved.route.adapter not in {"openai_compatible", "saygm_gateway"}:
                    raise ModelBudgetUnavailable("budget_unsupported_route")
                if request.output.max_tokens is None:
                    raise ModelBudgetUnavailable("budget_output_limit")
                if request.attachments or any(not isinstance(m.get("content"), str) for m in messages):
                    raise ModelBudgetUnavailable("budget_input_invalid")
            await emit("queued")
            async with controller.slot(resolved.priority):
                require_active()
                await emit("started")
                # Tool execution belongs to the caller, so this boundary
                # receives results as validated conversation context on the
                # next model round. Publish lifecycle metadata for those
                # results without exposing their content to the event sink.
                for item in request.context:
                    if isinstance(item, ModelContextMessage) and item.role == "tool":
                        await emit_tool_result(item.tool_call_id, item.name)
                client = (client_factory(resolved) if client_factory is not None
                          else make_route_client(resolved, timeout=request.timeout_s))
                require_active()
                completion_args: dict[str, Any] = {
                    "model": resolved.model,
                    "messages": messages,
                }
                if request.temperature is not None:
                    completion_args["temperature"] = request.temperature
                if tools:
                    completion_args["tools"] = tools
                if request.output.max_tokens is not None:
                    completion_args["max_tokens"] = request.output.max_tokens
                if request.extra_body is not None:
                    completion_args["extra_body"] = {
                        "output_config": dict(request.extra_body["output_config"])
                    }
                if request.stream_text:
                    completion_args["stream"] = True
                if spend_capped and not _api_adapter_has_no_retries(client):
                    raise ModelBudgetUnavailable("budget_unsupported_route")
                if budget.scope_id is not None:
                    estimate = _estimated_text_input_tokens(messages, tools) if spend_capped else 1
                    await asyncio.to_thread(
                        reserve_model_call_budget, budget, request.task_id,
                        resolved.provider, resolved.model, resolved.route.name,
                        resolved.route.billing, estimate, request.output.max_tokens or 1,
                    )
                    # A cancellation suppressed by a custom adapter must not
                    # publish or start a provider operation after reservation.
                    require_active()
                await emit("progress", progress_stage="provider_request")
                native_execute = getattr(client, "execute_request", None)
                if native_execute is not None:
                    response = await native_execute(request, resolved, completion_args)
                else:
                    response = await client.chat.completions.create(**completion_args)
                require_active()
                if request.stream_text:
                    response = await _collect_chat_stream(
                        response,
                        lambda fragment: emit("text_delta", text_delta=fragment),
                        allowed_tools=tuple(tool_validators),
                    )
                    require_active()
                await emit("progress", progress_stage="response_received")
                message = response.choices[0].message
                text = message.content
                if text is None:
                    text = ""
                elif not isinstance(text, str):
                    raise ModelExecutionOutputError("provider returned non-text message content")
                if request.output.require_nonempty_text and not text.strip():
                    raise ModelExecutionOutputError("provider returned empty text")
                tool_calls = _validated_tool_calls(
                    message, tool_validators, seen_ids=seen_tool_call_ids
                )
                provider_extras = _validated_provider_extras(
                    _field(message, "model_extra") or {},
                    reserved={"role", "content", "tool_calls"},
                    label="provider assistant message",
                )
                for call in tool_calls:
                    await emit_tool_request(call)
                usage = _field(response, "usage")
                response_id = _field(response, "id")
                if not isinstance(response_id, str) or len(response_id) > 256:
                    response_id = None
                result = ModelExecutionResult(
                    task_id=request.task_id,
                    parent_request_id=request.parent_request_id,
                    model=resolved.model,
                    provider=resolved.provider,
                    route=resolved.route.name,
                    billing=resolved.route.billing,
                    text=text,
                    data_policy=inherit_result_policy(effective_policy),
                    tool_calls=tool_calls,
                    prompt_tokens=_usage_count(usage, "prompt_tokens", "input_tokens"),
                    completion_tokens=_usage_count(usage, "completion_tokens", "output_tokens"),
                    total_tokens=_usage_count(usage, "total_tokens"),
                    cache_read_tokens=_usage_count(
                        usage, "prompt_tokens_details.cached_tokens",
                        "cache_read_input_tokens", "cached_tokens",
                    ),
                    cache_write_tokens=_usage_count(
                        usage, "cache_creation_input_tokens",
                        "prompt_tokens_details.cache_write_tokens",
                    ),
                    duration_ms=(time.monotonic() - started_at) * 1000.0,
                    response_id=response_id,
                    provider_extras=provider_extras,
                )
                await emit("completed")
                require_active()
                return result
    except asyncio.CancelledError:
        await close_model_request(client, request.parent_request_id)
        await emit("cancelled")
        raise
    except TimeoutError:
        await close_model_request(client, request.parent_request_id)
        await emit("failed", error_code="timeout")
        raise
    except Exception as exc:
        await close_model_request(client, request.parent_request_id)
        # Only a stable category is published. Provider exception text may
        # include input, credentials, endpoints or account details.
        await emit("failed", error_code=(exc.code if isinstance(exc, ModelBudgetUnavailable)
                                         else type(exc).__name__))
        raise


def _limited_output_request(request: ModelExecutionRequest, cap: int | None) -> ModelExecutionRequest:
    if cap is None:
        return request
    if not isinstance(request.output, ModelOutputRequirements):
        raise ModelExecutionInputError("output requirements are invalid")
    existing = request.output.max_tokens
    if existing is not None and (type(existing) is not int or not 1 <= existing <= 32_000):
        raise ModelExecutionInputError("max_tokens must be an integer from 1 to 32000")
    return replace(request, output=replace(request.output, max_tokens=min(existing, cap)
                                          if existing is not None else cap))


def _estimated_text_input_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> int:
    # Explicit conservative local estimate, not a provider token or invoice
    # measurement. Include every UTF-8 byte plus framing/schema overhead.
    return 1024 + len(json.dumps({"messages": messages, "tools": tools},
                                ensure_ascii=False, separators=(",", ":"),
                                allow_nan=False).encode("utf-8"))


def _api_adapter_has_no_retries(client: Any) -> bool:
    """Prove retry configuration from supported SDKs, never a foreign flag."""
    import openai
    import anthropic
    from jarvis.anthropic_shim import AsyncAnthropicChatShim
    from jarvis.llm_client import _OpenRouterCachingClient

    if type(client) is _OpenRouterCachingClient:
        client = client._client
    if type(client) is AsyncAnthropicChatShim:
        client = client._anthropic
    return (type(client) in {openai.AsyncOpenAI, anthropic.AsyncAnthropic}
            and type(client.max_retries) is int and client.max_retries == 0)


async def close_model_request(client: Any, parent_request_id: str) -> None:
    """Close only this parent's native session after failure or agent cleanup."""
    close = getattr(client, "close_request", None)
    if close is None:
        return
    try:
        cleanup = close(parent_request_id)
        if inspect.isawaitable(cleanup):
            task = asyncio.ensure_future(cleanup)
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await asyncio.shield(task)
    except Exception as exc:  # noqa: BLE001 — cleanup diagnostics contain no provider payload
        logger.warning("model_request_cleanup_failed: %s", type(exc).__name__)
