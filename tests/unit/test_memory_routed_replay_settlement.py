"""Policy/usage/cancellation tests for replay and automatic-review model calls.

These target extract_candidates used by scripts/replay_extraction.py, not the
normal durable extractor, which has separate route-proof tests.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from jarvis import memory_extraction, memory_sweep, model_execution, usage_ledger
from jarvis.db import get_conn, run_migrations
from jarvis.model_execution import ModelAdmissionController
from jarvis.model_routing import AccessRoute, ModelRouteError, ResolvedModelRoute
from tests.unit.test_memory_settle import _pair, _status

CANARY = "PRIVATE_REPLAY_REVIEW_CANARY"


def route(privacy="confidential"):
    return ResolvedModelRoute(
        "memory", "fixture", "fixture-model", "local", "local://fixture",
        AccessRoute("local", "openai_compatible", "local", None, privacy, capabilities=("text",)),
        None, "local/fixture", "background",
    )


class Client:
    def __init__(self, text, *, block=False, error=None):
        self.text, self.block, self.error = text, block, error
        self.sent = []
        self.started, self.cancelled = asyncio.Event(), False
        self.base_url = "local://fixture"
        self.chat = self.completions = self

    async def create(self, **kwargs):
        self.sent.append(kwargs)
        self.started.set()
        if self.error:
            raise self.error
        if self.block:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return SimpleNamespace(
            id="fixture-response", choices=[SimpleNamespace(message=SimpleNamespace(content=self.text, tool_calls=[]))],
            usage=SimpleNamespace(prompt_tokens=16, completion_tokens=4, total_tokens=20, private_field=CANARY),
        )


@pytest.fixture
def setup_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("JARVIS_MEMORY_AUTO_SETTLE", "1")
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "costs.db")
    monkeypatch.setattr(usage_ledger, "_price_map_cache", {"models": {}})
    controller = ModelAdmissionController()
    monkeypatch.setattr(model_execution, "_PROCESS_ADMISSION", controller)
    with get_conn() as conn:
        run_migrations(conn)
        yield conn, controller


def install(monkeypatch, client, resolved):
    factory = lambda _settings: (client, SimpleNamespace(model=resolved.model, resolved=resolved))
    monkeypatch.setattr(memory_extraction, "make_memory_async_client", factory)
    monkeypatch.setattr(memory_sweep, "make_memory_async_client", factory)


async def call(kind, conn, text):
    settings = SimpleNamespace(openai_model="legacy-fixture", jarvis_model_routing_enabled=True)
    if kind == "replay":
        return await memory_extraction.extract_candidates(settings, "fixture-session", text, "fixture reply")
    return await memory_sweep.settle_open_reviews(conn, settings)


@pytest.mark.parametrize("kind", ["replay", "settlement"])
async def test_enabled_calls_use_policy_boundary_and_one_normalized_usage_row(kind, setup_calls, monkeypatch):
    conn, _controller = setup_calls
    review = _pair(conn)
    conn.execute("UPDATE memories SET content=?", (CANARY,))
    conn.commit()
    text = ('{"facts":[],"observations":[]}' if kind == "replay" else
            json.dumps({"reviews": [{"id": review, "a_stated": True, "b_stated": True, "both_hold": True}]}))
    client, resolved = Client(text), route()
    install(monkeypatch, client, resolved)
    policies = []
    real_execute = model_execution.execute_chat
    async def execute(request, selected, **kwargs):
        policies.append((request.data_policy.level, request.context[0].data_policy.level))
        assert selected is resolved
        return await real_execute(request, selected, **kwargs)
    monkeypatch.setattr(memory_extraction, "execute_chat", execute)
    monkeypatch.setattr(memory_sweep, "execute_chat", execute)
    def forbidden(*args, **kwargs):
        pytest.fail("enabled call also entered legacy usage accounting")
    monkeypatch.setattr(memory_extraction, "record_completion", forbidden)
    monkeypatch.setattr(memory_sweep, "record_completion", forbidden)
    result = await call(kind, conn, CANARY)
    assert len(client.sent) == 1 and policies == [("confidential", "confidential")]
    assert CANARY in client.sent[0]["messages"][1]["content"]
    assert client.sent[0]["model"] == "fixture-model"
    if kind == "replay":
        assert result == {"facts": [], "observations": []}
    else:
        assert result["kept_both"] == 1 and _status(conn, review) == "dismissed"
    with usage_ledger._conn() as db:
        rows = db.execute("SELECT rung, route_name, billing_source, input_tokens, output_tokens, "
                          "usage_known, duration_ms FROM llm_calls").fetchall()
    assert len(rows) == 1
    assert rows[0][:6] == ("memory_extraction" if kind == "replay" else "memory_settle",
                           "local", "local", 16, 4, 1)
    assert rows[0][6] >= 0 and CANARY not in repr(rows)


@pytest.mark.parametrize("kind", ["replay", "settlement"])
async def test_confidential_sources_refuse_external_route_before_provider(kind, setup_calls, monkeypatch, caplog):
    conn, _controller = setup_calls
    review = _pair(conn)
    client = Client("{}")
    install(monkeypatch, client, route("approved_external"))
    if kind == "replay":
        with pytest.raises(ModelRouteError, match="requires 'confidential'"):
            await call(kind, conn, CANARY)
    else:
        result = await call(kind, conn, CANARY)
        assert result["left_open"] == 1 and _status(conn, review) == "open"
    assert client.sent == [] and CANARY not in caplog.text


@pytest.mark.parametrize("kind", ["replay", "settlement"])
async def test_cancellation_releases_background_admission_without_writing_review(kind, setup_calls, monkeypatch):
    conn, controller = setup_calls
    review = _pair(conn)
    client = Client("{}", block=True)
    install(monkeypatch, client, route())
    task = asyncio.create_task(call(kind, conn, CANARY))
    await asyncio.wait_for(client.started.wait(), timeout=1)
    assert controller.active_counts == (0, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.cancelled is True and controller.active_counts == (0, 0)
    assert _status(conn, review) == "open"


async def test_settlement_provider_error_leaves_review_open_and_logs_no_payload(setup_calls, monkeypatch, caplog):
    conn, controller = setup_calls
    review = _pair(conn)
    client = Client("{}", error=RuntimeError(CANARY))
    install(monkeypatch, client, route())
    result = await call("settlement", conn, CANARY)
    assert result["left_open"] == 1 and _status(conn, review) == "open"
    assert "error_type=RuntimeError" in caplog.text
    assert CANARY not in caplog.text and "Traceback" not in caplog.text
    assert controller.active_counts == (0, 0)


async def test_replay_provider_error_is_safe_for_replay_script_exception_output(setup_calls, monkeypatch):
    conn, controller = setup_calls
    client = Client("{}", error=RuntimeError("provider rejected request " + CANARY))
    install(monkeypatch, client, route())
    with pytest.raises(RuntimeError) as caught:
        await call("replay", conn, CANARY)
    assert "error_type=RuntimeError" in str(caught.value)
    assert CANARY not in str(caught.value)
    assert caught.value.__suppress_context__ is True
    assert controller.active_counts == (0, 0)


@pytest.mark.parametrize("kind", ["replay", "settlement"])
async def test_usage_sink_failure_preserves_result_and_logs_no_payload(kind, setup_calls, monkeypatch, caplog):
    conn, _controller = setup_calls
    review = _pair(conn)
    text = ('{"facts":[],"observations":[]}' if kind == "replay" else
            json.dumps({"reviews": [{"id": review, "a_stated": True, "b_stated": True, "both_hold": True}]}))
    client = Client(text)
    install(monkeypatch, client, route())
    def fail(*args, **kwargs):
        raise RuntimeError("usage sink diagnostic " + CANARY)
    monkeypatch.setattr(memory_extraction, "record_execution_result", fail)
    monkeypatch.setattr(memory_sweep, "record_execution_result", fail)
    result = await call(kind, conn, CANARY)
    if kind == "replay":
        assert result == {"facts": [], "observations": []}
    else:
        assert result["kept_both"] == 1
    assert "error_type=RuntimeError" in caplog.text
    assert CANARY not in caplog.text and "Traceback" not in caplog.text


async def test_settlement_success_log_contains_count_without_private_memory_key(setup_calls, monkeypatch, caplog):
    conn, _controller = setup_calls
    review = _pair(conn)
    key = "PRIVATE_ARCHIVED_MEMORY_KEY_CANARY"
    conn.execute("UPDATE memories SET key=? WHERE key='user.style.no_lookups'", (key,))
    conn.execute("UPDATE memory_reviews SET keys_json=? WHERE id=?",
                 (json.dumps(["user.style.do_it", key]), review))
    conn.commit()
    client = Client(json.dumps({"reviews": [{"id": review, "a_stated": True,
                                             "b_stated": False, "both_hold": False}]}))
    install(monkeypatch, client, route())
    with caplog.at_level("INFO", logger="jarvis.memory_sweep"):
        result = await call("settlement", conn, CANARY)
    assert result["settled"] == 1
    assert result["archived"][0][0] == key
    assert "archived_count=1" in caplog.text and key not in caplog.text


@pytest.mark.parametrize("kind", ["replay", "settlement"])
async def test_routing_off_retains_direct_client_request_and_accounting(kind, setup_calls, monkeypatch):
    conn, _controller = setup_calls
    _pair(conn)
    client = Client('{"facts":[],"observations":[],"reviews":[]}')
    legacy = SimpleNamespace(model="legacy-fixture", resolved=None)
    monkeypatch.setattr(memory_extraction, "make_memory_async_client", lambda _: (client, legacy))
    monkeypatch.setattr(memory_sweep, "make_memory_async_client", lambda _: (client, legacy))
    recorded = []
    monkeypatch.setattr(memory_extraction, "record_completion", lambda **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(memory_sweep, "record_completion", lambda **kwargs: recorded.append(kwargs))
    async def forbidden(*args, **kwargs):
        pytest.fail("routing-off request entered shared execution")
    monkeypatch.setattr(memory_extraction, "execute_chat", forbidden)
    monkeypatch.setattr(memory_sweep, "execute_chat", forbidden)
    await call(kind, conn, CANARY)
    assert len(client.sent) == len(recorded) == 1
    assert client.sent[0]["model"] == "legacy-fixture"
    assert [message["role"] for message in client.sent[0]["messages"]] == ["system", "user"]
