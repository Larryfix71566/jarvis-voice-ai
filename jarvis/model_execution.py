"""Provider-neutral, policy-checked boundary for one model request.

This module preserves ordered context and approved, normalized attachments.
Provider differences remain inside route adapters; Mortimer's agent/tool loops
remain their owners' responsibility.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import math
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Literal

from jarvis.bot.shared_content import (
    MAX_ATTACHMENTS,
    SharedContent,
    normalize_shared_content,
)
from jarvis.model_routing import ModelRouteError, ResolvedModelRoute, make_route_client
from jarvis.privacy_policy import (
    DataPolicy,
    assert_route_allowed,
    inherit_result_policy,
    strictest,
)


class ModelExecutionInputError(ValueError):
    """The request contains unsupported or malformed model input."""


ExecutionEventType = Literal[
    "queued", "started", "progress", "text_delta", "tool_request",
    "tool_result", "artifact", "completed", "cancelled", "failed",
]


@dataclass(frozen=True)
class ModelExecutionEvent:
    """Non-payload lifecycle event correlated to the originating request.

    The event carries the effective policy even when it has no content. A
    content-bearing future event must additionally pass its content through
    the same policy checks before the event is emitted.
    """

    task_id: str
    parent_request_id: str
    sequence: int
    event_type: ExecutionEventType
    data_policy: DataPolicy
    error_code: str | None = None


class ModelAdmissionController:
    """One-process, event-loop-local limit for non-voice model execution.

    At most two requests execute at once and at most one is background. This
    leaves one slot available to interactive work even while background work
    is queued. Waiting interactive requests are admitted ahead of background
    waiters as soon as capacity becomes available.
    """

    def __init__(self, *, max_active: int = 2, max_background: int = 1):
        if max_active < 1 or max_background < 0 or max_background >= max_active:
            raise ValueError("admission limits must reserve an interactive slot")
        self._max_active = max_active
        self._max_background = max_background
        self._condition = asyncio.Condition()
        self._active_interactive = 0
        self._active_background = 0
        self._waiting_interactive = 0

    @property
    def active_counts(self) -> tuple[int, int]:
        """Return (interactive, background) counts for diagnostics/tests."""
        return self._active_interactive, self._active_background

    @property
    def waiting_interactive(self) -> int:
        return self._waiting_interactive

    def _can_start(self, priority: str) -> bool:
        active = self._active_interactive + self._active_background
        if active >= self._max_active:
            return False
        if priority == "interactive":
            return True
        return (
            priority == "background"
            and self._active_background < self._max_background
            and self._waiting_interactive == 0
        )

    @asynccontextmanager
    async def slot(self, priority: str) -> AsyncIterator[None]:
        if priority not in {"interactive", "background"}:
            raise ModelExecutionInputError("priority must be interactive or background")
        acquired = False
        async with self._condition:
            if priority == "interactive":
                self._waiting_interactive += 1
            try:
                while not self._can_start(priority):
                    await self._condition.wait()
                if priority == "interactive":
                    self._waiting_interactive -= 1
                    self._active_interactive += 1
                else:
                    self._active_background += 1
                acquired = True
                self._condition.notify_all()
            finally:
                if not acquired and priority == "interactive":
                    self._waiting_interactive -= 1
                    self._condition.notify_all()
        try:
            yield
        finally:
            async with self._condition:
                if priority == "interactive":
                    self._active_interactive -= 1
                else:
                    self._active_background -= 1
                self._condition.notify_all()


_PROCESS_ADMISSION = ModelAdmissionController()


@dataclass(frozen=True)
class ModelContextMessage:
    role: Literal["system", "user", "assistant"]
    content: str
    data_policy: DataPolicy = field(default_factory=DataPolicy)


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
    data_policy: DataPolicy = field(default_factory=DataPolicy)
    timeout_s: float = 60.0


@dataclass(frozen=True)
class ModelExecutionResult:
    task_id: str
    parent_request_id: str
    model: str
    route: str
    billing: str
    text: str
    data_policy: DataPolicy


def _validated_inputs(request: ModelExecutionRequest,
                      resolved: ResolvedModelRoute
                      ) -> tuple[list[dict[str, Any]], DataPolicy]:
    if (not isinstance(request.workload, str) or not request.workload
            or request.workload != resolved.workload):
        raise ModelExecutionInputError("request workload does not match resolved route")
    if (not isinstance(request.task_id, str) or not request.task_id.strip()
            or not isinstance(request.parent_request_id, str)
            or not request.parent_request_id.strip()):
        raise ModelExecutionInputError("task and parent request IDs are required")
    if not isinstance(request.instructions, str) or not request.instructions.strip():
        raise ModelExecutionInputError("instructions must be non-empty text")
    if (isinstance(request.timeout_s, bool) or not isinstance(request.timeout_s, (int, float))
            or not math.isfinite(request.timeout_s) or request.timeout_s <= 0):
        raise ModelExecutionInputError("timeout must be a positive finite number")
    if not isinstance(request.data_policy, DataPolicy):
        raise ModelExecutionInputError("request data policy is invalid")
    if not isinstance(request.context, tuple):
        raise ModelExecutionInputError("context must be an immutable tuple")

    messages: list[dict[str, Any]] = []
    policies = [request.data_policy]
    for item in request.context:
        # Strings were the only practical context shape in the original
        # uncalled foundation. Keep them as ordinary user context; reject all
        # other untyped objects rather than silently coercing or dropping them.
        if isinstance(item, str):
            item = ModelContextMessage("user", item)
        if not isinstance(item, ModelContextMessage):
            raise ModelExecutionInputError("context items must be text messages")
        if not isinstance(item.role, str) or item.role not in {"system", "user", "assistant"}:
            raise ModelExecutionInputError("unsupported context message role")
        if not isinstance(item.content, str) or not item.content.strip():
            raise ModelExecutionInputError("context message content must be non-empty text")
        if not isinstance(item.data_policy, DataPolicy):
            raise ModelExecutionInputError("context data policy is invalid")
        messages.append({"role": item.role, "content": item.content})
        policies.append(item.data_policy)

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

    messages.append({"role": "user", "content": user_content})
    effective_policy = strictest(*policies)
    assert_route_allowed(resolved.route, effective_policy)
    return messages, effective_policy


async def execute_chat(request: ModelExecutionRequest,
                       resolved: ResolvedModelRoute,
                       *,
                       client_factory: Callable[..., Any] | None = None,
                       event_sink: Callable[[ModelExecutionEvent], Any] | None = None,
                       admission: ModelAdmissionController | None = None) -> ModelExecutionResult:
    """Execute one validated request, preserving context and attachments.

    Cancellation propagates to the provider client, and the outer deadline
    prevents late results from being returned to callers. Tool loops remain
    owned by their existing agent boundary.
    """
    messages, effective_policy = _validated_inputs(request, resolved)
    controller = admission or _PROCESS_ADMISSION
    sequence = 0

    async def emit(event_type: ExecutionEventType, *, error_code: str | None = None) -> None:
        nonlocal sequence
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
        )
        try:
            observed = event_sink(event)
            if inspect.isawaitable(observed):
                await observed
        except Exception:
            # Lifecycle observers must not turn a successful provider result
            # into a failure or obscure the original provider exception.
            return

    await emit("queued")
    try:
        # The deadline includes time spent queued for capacity; a saturated
        # worker must not make a request live longer than its caller allowed.
        async with asyncio.timeout(request.timeout_s):
            async with controller.slot(resolved.priority):
                await emit("started")
                client = (client_factory(resolved) if client_factory is not None
                          else make_route_client(resolved, timeout=request.timeout_s))
                response = await client.chat.completions.create(
                    model=resolved.model,
                    messages=messages,
                )
                text = response.choices[0].message.content or ""
                result = ModelExecutionResult(
                    task_id=request.task_id,
                    parent_request_id=request.parent_request_id,
                    model=resolved.model,
                    route=resolved.route.name,
                    billing=resolved.route.billing,
                    text=text,
                    data_policy=inherit_result_policy(effective_policy),
                )
                await emit("completed")
                return result
    except asyncio.CancelledError:
        await emit("cancelled")
        raise
    except TimeoutError:
        await emit("failed", error_code="timeout")
        raise
    except Exception as exc:
        # Only a stable category is published. Provider exception text may
        # include input, credentials, endpoints or account details.
        await emit("failed", error_code=type(exc).__name__)
        raise
