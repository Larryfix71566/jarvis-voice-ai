"""Integration test: a procedure learned from real SubAgent runs gets
injected as a hint once promoted (MORTIMER_MEMORY_PROCEDURES_PLAN.md Part B,
§7 verification — "run the same kind of task through a stubbed SubAgent
three times; assert no hint is injected on runs 1-2 (still a candidate),
assert a hint message appears in the messages sent to the fake LLM on a
subsequent matching task once promoted; assert the hint text equals the
stored procedure's description").

Drives a real SubAgent (jarvis/agents/base.py) with a scripted FakeLLM and
FakeRegistry — no network — and calls jarvis.procedures.learn_from_run
directly and synchronously after each run, the same call
jarvis/agents/delegate.py spawns fire-and-forget in production. Awaiting it
directly here keeps the test deterministic instead of racing a background
task.
"""

import json
from types import SimpleNamespace

import pytest

from jarvis.agents.base import SubAgent
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.db import get_conn, run_migrations
from jarvis.procedures import PROCEDURE_PROMOTE_AFTER, learn_from_run

from tests.unit.test_memory import _factory
from tests.unit.test_subagent import FakeCompletions, FakeLLM, FakeRegistry

TASK = "look up the current weather conditions in tokyo japan"
LABEL = "weather lookup"
DESCRIPTION = "used get_weather to check current weather conditions for a city"


def make_settings():
    return SimpleNamespace(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_timezone="America/New_York",
        jarvis_runlog_enabled=True,   # learn_from_run must find a real row
        jarvis_procedures_enabled=True,
    )


def make_agent():
    fake = FakeLLM([("text", "It is sunny in Tokyo.")])
    agent = SubAgent(
        name="analyst",
        display_name="Analyst",
        description="d",
        mcp_servers=["mcp-web"],
        settings=make_settings(),
        registry=FakeRegistry(),
        client_factory=lambda settings: fake,
    )
    return agent, fake.chat.completions


def _hint_present(messages: list[dict]) -> bool:
    return any(
        m["role"] == "system" and "A similar task has succeeded before" in m["content"]
        for m in messages
    )


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "e2e.db"))
    run_migrations()
    conn = get_conn(tmp_path / "e2e.db")
    yield conn
    conn.close()


@pytest.fixture()
def stub_settings_for_learning(monkeypatch):
    """learn_from_run loads its own Settings (D20) — point it at a fake
    with jarvis_procedures_enabled=True, matching the SubAgent's own
    settings above."""
    import jarvis.config as config_module

    monkeypatch.setattr(
        config_module, "load_settings", lambda: make_settings(), raising=True
    )


@pytest.fixture()
def unarmed_turn():
    """T4a K3 (gap-closure plan GC1): jarvis.bot.sensitive_turn.is_sensitive()
    is FAIL-CLOSED when the ContextVar is unset (jarvis/bot/sensitive_turn.py)
    — production wires it in run_session/cli.main before any turn. Without
    this, SubAgent.run's RunLogger snapshots sensitive=True (base.py:467) and
    stores runlog.store.SENSITIVE_SENTINEL ("<sensitive>") as the run's task
    instead of the real text, so every run here tokenized to the single word
    "sensitive" and learn_from_run's FTS candidate lookup (over label and
    description, never task_tokens) could never find the weather-labeled
    candidate it just created — three runs produced three separate
    never-promoted candidates instead of one reinforced three times. Reset
    via token so the ambient context doesn't leak into whatever test runs
    next in this process."""
    token = current_sensitive_turn.set(SensitiveTurn())
    yield
    current_sensitive_turn.reset(token)


async def test_procedure_promoted_after_three_successes_then_injected_as_hint(
    db, stub_settings_for_learning, unarmed_turn,
):
    describe_payload = json.dumps({"label": LABEL, "description": DESCRIPTION})

    for i in range(1, PROCEDURE_PROMOTE_AFTER + 1):
        agent, completions = make_agent()
        run_id = f"run-{i}"
        await agent.run(TASK, run_id=run_id)

        # No hint yet — the procedure isn't active until after this run's
        # learning step (runs 1..PROCEDURE_PROMOTE_AFTER are all "still a
        # candidate" at the moment their own request was sent).
        assert not _hint_present(completions.requests[0]["messages"]), (
            f"run {i} must not see a hint before promotion"
        )

        await learn_from_run(
            run_id, "analyst", client_factory=_factory(describe_payload),
        )

    row = db.execute("SELECT * FROM procedures").fetchone()
    assert row["status"] == "active"
    assert row["success_count"] == PROCEDURE_PROMOTE_AFTER

    # A subsequent matching task now gets the hint.
    agent, completions = make_agent()
    await agent.run(TASK, run_id="run-final")
    messages = completions.requests[0]["messages"]
    assert _hint_present(messages)
    hint = next(m for m in messages if m["role"] == "system" and m is not messages[0])
    assert hint["content"] == f"A similar task has succeeded before: {DESCRIPTION}"


async def test_unrelated_task_never_gets_a_hint(db, stub_settings_for_learning, unarmed_turn):
    describe_payload = json.dumps({"label": LABEL, "description": DESCRIPTION})
    for i in range(1, PROCEDURE_PROMOTE_AFTER + 1):
        agent, _ = make_agent()
        run_id = f"run-{i}"
        await agent.run(TASK, run_id=run_id)
        await learn_from_run(
            run_id, "analyst", client_factory=_factory(describe_payload),
        )

    # Procedure is now active for the weather task, but a genuinely
    # different task must be completely unaffected — no hint, no error.
    agent, completions = make_agent()
    await agent.run("commit and push the repository changes", run_id="run-other")
    assert not _hint_present(completions.requests[0]["messages"])
