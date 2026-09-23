"""Provider-neutral execution contract for model calls.

Adapters remain responsible for SDK details. This boundary validates the data
policy before a client is created or a request is transmitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from jarvis.model_routing import ResolvedModelRoute, make_route_client
from jarvis.privacy_policy import DataPolicy, assert_route_allowed, inherit_result_policy


@dataclass(frozen=True)
class ModelExecutionRequest:
    workload: str
    task_id: str
    parent_request_id: str
    instructions: str
    context: tuple[Any, ...] = ()
    attachments: tuple[Any, ...] = ()
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


async def execute_chat(request: ModelExecutionRequest,
                       resolved: ResolvedModelRoute,
                       *,
                       client_factory: Callable[..., Any] | None = None) -> ModelExecutionResult:
    """Execute one text request after policy validation.

    The injected factory is the test seam; production uses the validated route
    adapter. Tool loops remain owned by their existing agent boundary.
    """
    assert_route_allowed(resolved.route, request.data_policy)
    client = (client_factory(resolved) if client_factory is not None
              else make_route_client(resolved, timeout=request.timeout_s))
    response = await client.chat.completions.create(
        model=resolved.model,
        messages=[{"role": "user", "content": request.instructions}],
    )
    text = response.choices[0].message.content or ""
    return ModelExecutionResult(
        task_id=request.task_id,
        parent_request_id=request.parent_request_id,
        model=resolved.model,
        route=resolved.route.name,
        billing=resolved.route.billing,
        text=text,
        data_policy=inherit_result_policy(request.data_policy),
    )
