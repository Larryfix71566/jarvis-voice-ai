"""Host entry deadlines and cancellation suppression, without provider calls."""
import asyncio
import sqlite3
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
import httpx
import openai

from jarvis import model_execution, usage_ledger
from jarvis.model_budget import ModelBudgetUnavailable
from jarvis.model_execution import ModelExecutionRequest, execute_chat
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits
from jarvis.privacy_policy import DataPolicy


def route(limits=WorkloadLimits()):
    return ResolvedModelRoute(
        "developer", "fixture", "fixture", "openai", "",
        AccessRoute("direct_api", "openai_compatible", "provider_api", None,
                    "approved_external", capabilities=("text", "streaming")),
        None, "openai/fixture", "interactive", limits=limits,
    )


def request(**changes):
    value = ModelExecutionRequest(
        "developer", "deadline-call", "deadline-parent", "public fixture",
        data_policy=DataPolicy("approved_external", "public-fixture"),
    )
    return replace(value, **changes)


def response():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content="late public fixture", tool_calls=None, model_extra=None,
    ))], usage=None, id="fixture")


class Client:
    def __init__(self, create):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.closed = []

    async def close_request(self, parent):
        self.closed.append(parent)


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "costs.db"
    monkeypatch.setattr(usage_ledger, "DB_PATH", path)
    monkeypatch.setenv("JARVIS_USER_ID", "local")
    return path


@pytest.fixture
def expire_at_confirmed_phase(monkeypatch):
    """Tighten the real request timeout only after the tested phase is reached.

    These cases test cancellation suppression after an observer/SDK starts.
    The separate host-entry cases retain short deadlines during bootstrap.
    No execution clock, budget, guard or provider response is replaced.
    """
    original = asyncio.timeout_at
    owned = {}

    def capture(when):
        timeout = original(when)
        owned.setdefault(asyncio.current_task(), []).append(timeout)
        return timeout

    monkeypatch.setattr(asyncio, "timeout_at", capture)

    def expire(task):
        contexts = owned[task]
        assert len(contexts) == 1
        timeout = contexts[0]
        loop = asyncio.get_running_loop()
        assert not timeout.expired() and timeout.when() > loop.time()
        timeout.reschedule(loop.time())

    return expire


async def test_worker_bootstrap_delay_expires_at_host_entry_and_survives_cleared_config(ledger, monkeypatch):
    original = model_execution.begin_model_task_budget
    finished = threading.Event()
    origins = []

    def delayed(*args, **kwargs):
        origins.append(kwargs["started_at"])
        try:
            time.sleep(.05)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(model_execution, "begin_model_task_budget", delayed)
    clients = []
    events = []
    entry = time.time()
    with pytest.raises(TimeoutError):
        await execute_chat(request(), route(WorkloadLimits(deadline_seconds=.01)),
                           client_factory=lambda _: clients.append(True), event_sink=events.append)
    assert not finished.is_set()  # timeout owns setup, while the worker still runs
    assert clients == []
    assert [(event.event_type, event.error_code) for event in events] == [("failed", "timeout")]
    assert await asyncio.to_thread(finished.wait, 1)
    monkeypatch.setattr(model_execution, "begin_model_task_budget", original)
    with sqlite3.connect(ledger) as conn:
        start, deadline = conn.execute("SELECT started_at,deadline_at FROM model_task_budgets").fetchone()
        assert conn.execute("SELECT COUNT(*) FROM model_call_budget_reservations").fetchone() == (0,)
    assert entry <= start == origins[0]
    assert deadline == pytest.approx(start + .01)
    with pytest.raises(ModelBudgetUnavailable, match="budget_deadline_exhausted"):
        await execute_chat(request(), route(), client_factory=lambda _: clients.append(True))
    assert clients == []


async def test_configured_deadline_includes_initial_input_validation(ledger, monkeypatch):
    original = model_execution._validated_inputs

    def slow_validation(*args, **kwargs):
        time.sleep(.02)
        return original(*args, **kwargs)

    monkeypatch.setattr(model_execution, "_validated_inputs", slow_validation)
    clients = []
    events = []
    with pytest.raises(TimeoutError):
        await execute_chat(request(), route(WorkloadLimits(deadline_seconds=.01)),
                           client_factory=lambda _: clients.append(True), event_sink=events.append)
    assert clients == []
    assert events[-1].error_code == "timeout"
    assert not ledger.exists()


@pytest.mark.parametrize("stage", ["queued", "started", "provider_request"])
@pytest.mark.parametrize("explicit_cancel", [False, True])
async def test_expired_lifecycle_observer_cannot_start_provider(
    ledger, stage, explicit_cancel, expire_at_confirmed_phase,
):
    calls = []
    events = []
    entered = asyncio.Event()

    async def create(**_):
        calls.append(True)
        return response()

    client = Client(create)

    async def observe(event):
        events.append(event)
        selected = event.progress_stage or event.event_type
        if selected == stage:
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                return  # hostile/buggy observer suppresses the deadline cancellation

    worker = asyncio.create_task(execute_chat(
        request(), route(WorkloadLimits() if explicit_cancel else WorkloadLimits(deadline_seconds=10)),
        client_factory=lambda _: client, event_sink=observe,
    ))
    await asyncio.wait_for(entered.wait(), 1)
    if explicit_cancel:
        worker.cancel()
    else:
        expire_at_confirmed_phase(worker)
    with pytest.raises(asyncio.CancelledError if explicit_cancel else TimeoutError):
        await worker
    assert calls == []
    assert events[-1].event_type == ("cancelled" if explicit_cancel else "failed")
    assert events[-1].error_code == (None if explicit_cancel else "timeout")
    assert not any(event.event_type == "completed" for event in events)
    assert client.closed == (["deadline-parent"] if stage == "provider_request" else [])


@pytest.mark.parametrize("explicit_cancel,uncancel", [(False, False), (False, True), (True, False)])
async def test_provider_swallowing_cancellation_cannot_return_or_publish_late_result(ledger, explicit_cancel, uncancel):
    entered = asyncio.Event()
    events = []

    async def create(**_):
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            if uncancel:
                asyncio.current_task().uncancel()
            return response()

    client = Client(create)
    worker = asyncio.create_task(execute_chat(
        request(timeout_s=1 if explicit_cancel else .02), route(),
        client_factory=lambda _: client, event_sink=events.append,
    ))
    await asyncio.wait_for(entered.wait(), 1)
    if explicit_cancel:
        worker.cancel()
    with pytest.raises(asyncio.CancelledError if explicit_cancel else TimeoutError):
        await worker
    assert client.closed == ["deadline-parent"]
    assert not any(event.event_type in {"completed", "text_delta", "tool_request"}
                   or event.progress_stage == "response_received" for event in events)
    assert events[-1].event_type == ("cancelled" if explicit_cancel else "failed")
    assert events[-1].error_code == (None if explicit_cancel else "timeout")
    assert not ledger.exists()


async def test_expired_stream_cannot_publish_fragment_after_suppressed_cancellation(ledger):
    events = []
    closed = []

    async def fragments():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            yield SimpleNamespace(choices=[SimpleNamespace(index=0, delta=SimpleNamespace(
                content="late public fragment", tool_calls=None,
            ), finish_reason=None)], usage=None, id="fixture")
        finally:
            closed.append(True)

    async def create(**_):
        return fragments()

    client = Client(create)
    with pytest.raises(TimeoutError):
        await execute_chat(request(timeout_s=.02, stream_text=True), route(),
                           client_factory=lambda _: client, event_sink=events.append,
                           event_sink_policy=DataPolicy("approved_external", "public-fixture"))
    assert closed == [True]
    assert client.closed == ["deadline-parent"]
    assert not any(event.event_type in {"text_delta", "completed"} for event in events)
    assert events[-1].error_code == "timeout"


async def test_late_real_sdk_response_retains_admitted_spend_reservation(
    ledger, monkeypatch, expire_at_confirmed_phase,
):
    events = []
    entered = asyncio.Event()
    monkeypatch.setattr(usage_ledger, "load_price_map", lambda: {"models": {
        "openai/fixture": {"input_per_m": 1, "output_per_m": 1,
                           "cache_write_mult": 1, "cache_read_mult": 1},
    }})

    async def transport(_):
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            return httpx.Response(200, json={
                "id": "fixture", "object": "chat.completion", "created": 1, "model": "fixture",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": "late public fixture",
                }}],
            })

    async with openai.AsyncOpenAI(
        api_key="synthetic-unused-key", base_url="https://fixture.invalid/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    ) as client:
        worker = asyncio.create_task(execute_chat(
            request(), route(WorkloadLimits(100, 10, .01)),
            client_factory=lambda _: client, event_sink=events.append,
        ))
        await asyncio.wait_for(entered.wait(), 1)
        with sqlite3.connect(ledger) as conn:
            assert conn.execute("SELECT COUNT(*) FROM model_call_budget_reservations").fetchone() == (1,)
        expire_at_confirmed_phase(worker)
        with pytest.raises(TimeoutError):
            await worker
    assert client.is_closed()
    with sqlite3.connect(ledger) as conn:
        assert conn.execute("SELECT COUNT(*) FROM model_call_budget_reservations").fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone() == (0,)
    assert not any(event.event_type == "completed" for event in events)
    assert events[-1].error_code == "timeout"


@pytest.mark.parametrize("spend_capped", [False, True])
async def test_short_host_deadline_before_admission_never_creates_a_provider_or_reservation(
    ledger, monkeypatch, spend_capped,
):
    """The CI signatures are valid early refusal, not late-response evidence."""
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = model_execution.resolve_model_child_budget
    calls, events = [], []

    def held(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(2)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(model_execution, "resolve_model_child_budget", held)
    limits = WorkloadLimits(100, .05, .01) if spend_capped else WorkloadLimits(deadline_seconds=.05)
    worker = asyncio.create_task(execute_chat(
        request(), route(limits), client_factory=lambda _: calls.append(True), event_sink=events.append,
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(TimeoutError):
            await worker
        assert calls == []
        assert [(event.event_type, event.progress_stage, event.error_code) for event in events] == [
            ("failed", None, "timeout"),
        ]
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
    if ledger.exists():
        with sqlite3.connect(ledger) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='model_call_budget_reservations'").fetchone()
            if exists:
                assert conn.execute("SELECT COUNT(*) FROM model_call_budget_reservations").fetchone() == (0,)


async def test_synchronous_provider_delay_cannot_evade_monotonic_deadline(ledger):
    events = []

    async def create(**_):
        # The event-loop timer cannot run until this buggy adapter returns.
        time.sleep(.02)
        return response()

    client = Client(create)
    with pytest.raises(TimeoutError):
        await execute_chat(request(timeout_s=.01), route(),
                           client_factory=lambda _: client, event_sink=events.append)
    assert client.closed == ["deadline-parent"]
    assert not any(event.event_type == "completed" for event in events)
    assert events[-1].error_code == "timeout"
