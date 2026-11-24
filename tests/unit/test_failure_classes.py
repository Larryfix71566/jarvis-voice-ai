"""WS-38 2A: failure classes and closed reason codes.

docs/reviews/2026-11-19-request-resolution-design-note.md §6. The 9:51 PM
run on 2026-11-18 is the regression case: an analyst repeated an identical
refused weather call because nothing said the refusal was deterministic.
"""

from __future__ import annotations

import json

import pytest

from jarvis.agents.base import ITERATIONS_EXHAUSTED_MESSAGE, TIMEOUT_MESSAGE
from jarvis.agents.delegate import _tag_run_failure
from jarvis.bot import weather_reuse
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.db import get_conn, run_migrations
from jarvis.runlog.store import SENSITIVE_SENTINEL, RunLogger
from jarvis.toolresult import (
    FAILURE_CLASSES,
    FAILURE_TAG_RE,
    REASON_CLASSES,
    UNLISTED_REASON,
    classify_tool_result,
    failure_class_note,
    failure_tag,
)
from jarvis.voice_workflows import RESULT_KINDS, result_kinds
from tests.unit.test_subagent import FakeRegistry, make_agent


# ---------------------------------------------------------------- classifier

@pytest.mark.parametrize("tool,result,category,expected", [
    ("x", "x failed: timed out after 30s.", None, ("transient", "tool_timeout")),
    ("x", "x failed: mcp-web stopped and could not be restarted (EOFError).", None,
     ("transient", "tool_transport_error")),
    ("x", "x failed: ValueError.", None, ("approach", "tool_exception")),
    ("x", "Unknown tool x", None, ("approach", "unknown_tool")),
    ("x", "Tool 'x' is not available in this context", None, ("approach", "tool_not_available")),
    ("get_weather", '{"ok":false,"error":"weather_reuse_invalid_request"}', None,
     ("approach", "weather_reuse_invalid_request")),
    ("get_weather", '{"ok":false,"error":"weather_reuse_not_requested"}', None,
     ("policy", "weather_reuse_not_requested")),
    ("get_weather", '{"ok":false,"error":"weather_reuse_protected_turn"}', None,
     ("policy", "weather_reuse_protected_turn")),
    ("local_weather", "local_weather failed: weather_reuse_timeout. Say so.", None,
     ("transient", "weather_reuse_timeout")),
    ("local_weather", "local_weather failed: protected turn cannot call external tool server.", None,
     ("policy", "protected_turn")),
    ("local_weather", "local_weather failed: named or unclear weather target; device location "
     "is not the requested place.", None, ("policy", "weather_place_not_requested")),
    ("local_weather", "local_weather failed: the request did not clearly name a place or ask for "
     "weather here. Ask the user which place.", None, ("policy", "weather_place_not_requested")),
    # The registry's own category wins over whatever the text says.
    ("x", '{"ok":false,"error":"tool_reported_failure"}', "tool_timeout", ("transient", "tool_timeout")),
])
def test_failures_carry_a_class_and_closed_reason(tool, result, category, expected):
    outcome = classify_tool_result(tool, result, failure_category=category)
    assert not outcome.ok
    assert (outcome.failure_class, outcome.reason) == expected


@pytest.mark.parametrize("result", [
    '{"ok": false, "error": "HTTP 401: Bad credentials"}',
    '{"ok": false, "error": "alpharetta"}',
    '{"ok": false}',
    "x failed: something nobody listed",
])
def test_unlisted_failures_default_to_approach_and_never_echo_text(result):
    outcome = classify_tool_result("x", result)
    assert (outcome.failure_class, outcome.reason) == ("approach", UNLISTED_REASON)


def test_success_has_no_class_or_reason():
    outcome = classify_tool_result("x", '{"stat": [1]}')
    assert outcome.ok and outcome.failure_class is None and outcome.reason is None


def test_every_listed_reason_has_a_known_class():
    assert set(REASON_CLASSES.values()) <= set(FAILURE_CLASSES)


def test_every_weather_reuse_refusal_code_is_listed():
    # The registry reports these as weather_reuse_<code>. A new code with no
    # entry would quietly default to approach.
    missing = {f"weather_reuse_{code}" for code in weather_reuse._REFUSAL_CODES} - set(REASON_CLASSES)
    assert missing == set()


def test_tag_round_trips_and_closes_unknown_reasons():
    tag = failure_tag("policy", "weather_reuse_protected_turn")
    assert FAILURE_TAG_RE.search(tag).groups() == ("policy", "weather_reuse_protected_turn")
    assert FAILURE_TAG_RE.search(failure_tag("approach", "free text")).group(2) == UNLISTED_REASON


def test_policy_note_forbids_routing_around_the_guard():
    note = failure_class_note("policy", "weather_reuse_not_requested")
    assert "on purpose" in note and "another tool" in note and "code change" in note


# ------------------------------------------------------------ sub-agent loop

@pytest.fixture
def ordinary_turn():
    # Same explicit non-sensitive turn holder test_subagent.py uses.
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


class RefusingRegistry(FakeRegistry):
    async def call(self, name, arguments, server_names=None):
        self.calls.append((name, arguments, server_names))
        return '{"ok": false, "error": "weather_reuse_invalid_request"}'


async def test_identical_repeat_after_listed_refusal_is_not_dispatched(ordinary_turn):
    # The 9:51 shape: the same refused call, sent again unchanged.
    registry = RefusingRegistry()
    agent, completions = make_agent(
        [("tool", "fake_tool", {"city": "Alpharetta, Georgia"}),
         ("tool", "fake_tool", {"city": "Alpharetta, Georgia"}),
         ("text", "could not get the weather")],
        registry=registry,
    )
    reply = await agent.run("weather for Alpharetta")
    assert len(registry.calls) == 1
    third = completions.requests[2]["messages"]
    blocked = [m for m in third if m["role"] == "tool"][-1]
    assert json.loads(blocked["content"]) == {
        "ok": False, "error": "weather_reuse_invalid_request", "repeat_blocked": True,
    }
    second = completions.requests[1]["messages"]
    tool_idx = next(i for i, m in enumerate(second) if m["role"] == "tool")
    constraint = second[tool_idx + 1]
    assert constraint["role"] == "system"
    assert "Failure class: approach (reason `weather_reuse_invalid_request`)" in constraint["content"]
    assert "MUST NOT" in constraint["content"]
    assert reply.startswith("FAILED: every tool call in this run failed (2/2)")
    assert FAILURE_TAG_RE.search(reply).groups() == ("approach", "weather_reuse_invalid_request")


async def test_changed_arguments_are_still_dispatched(ordinary_turn):
    registry = RefusingRegistry()
    agent, _ = make_agent(
        [("tool", "fake_tool", {"city": "Alpharetta, Georgia"}),
         ("tool", "fake_tool", {"city": "Alpharetta, GA"}),
         ("text", "done")],
        registry=registry,
    )
    await agent.run("weather")
    assert len(registry.calls) == 2


async def test_unlisted_failure_may_be_repeated(ordinary_turn):
    class Flaky(FakeRegistry):
        async def call(self, name, arguments, server_names=None):
            self.calls.append((name, arguments, server_names))
            return '{"ok": false, "error": "HTTP 503"}'

    registry = Flaky()
    agent, _ = make_agent(
        [("tool", "fake_tool", {}), ("tool", "fake_tool", {}), ("text", "done")],
        registry=registry,
    )
    await agent.run("task")
    assert len(registry.calls) == 2


# ------------------------------------------------------------------ run log

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "runlog.db"
    conn = get_conn(path)
    run_migrations(conn)
    conn.close()
    return path


def test_private_run_keeps_the_closed_reason_but_not_the_result(db_path, tmp_path):
    root = tmp_path / "payload_root"
    rl = RunLogger("r1", "supervisor", "Supervisor", "weather", session_id="s",
                   db_path=db_path, root=root, sensitive=True)
    rl.start()
    rl.tool_result("local_weather", "local_weather failed: PRIVATE_CANARY", 2, False,
                   reason="weather_place_not_requested")
    rl.tool_result("other", "PRIVATE_CANARY_TWO", 2, False, reason="PRIVATE_CANARY_THREE")
    rl.finish("FAILED: weather unavailable")
    payload = next(root.rglob("*.jsonl")).read_text()
    assert "PRIVATE_CANARY" not in payload
    records = [json.loads(line) for line in payload.splitlines() if line.strip()]
    results = [r for r in records if r.get("type") == "tool_result"]
    assert [(r["result"], r["reason"], r["failure_class"]) for r in results] == [
        (SENSITIVE_SENTINEL, "weather_place_not_requested", "policy"),
        (SENSITIVE_SENTINEL, UNLISTED_REASON, "approach"),
    ]


def test_successful_result_records_no_reason(db_path, tmp_path):
    root = tmp_path / "payload_root"
    rl = RunLogger("r2", "developer", "Developer", "t", session_id="s", db_path=db_path, root=root)
    rl.start()
    rl.tool_result("git_status", "clean", 1, True, reason="tool_timeout")
    rl.finish("done")
    records = [json.loads(line) for line in next(root.rglob("*.jsonl")).read_text().splitlines()
               if line.strip()]
    result = next(r for r in records if r.get("type") == "tool_result")
    assert "reason" not in result


# ------------------------------------------------- delegate and voice layer

@pytest.mark.parametrize("result,expected", [
    (ITERATIONS_EXHAUSTED_MESSAGE.format(used=5), ("approach", "iterations_exhausted")),
    (TIMEOUT_MESSAGE, ("transient", "agent_timeout")),
    ("FAILED: this tool source requires a more private route; no protected content was shared.",
     ("policy", "private_route_required")),
])
def test_whole_run_failures_are_tagged(result, expected):
    tagged = _tag_run_failure(result)
    assert tagged.startswith(result)
    assert FAILURE_TAG_RE.search(tagged).groups() == expected


def test_existing_tags_and_unknown_failures_are_left_alone():
    already = "FAILED: every tool call in this run failed (1/1). Last error: x\n" + failure_tag(
        "policy", "protected_turn")
    assert _tag_run_failure(already) == already
    assert _tag_run_failure("FAILED: specialist error (KeyError).") == "FAILED: specialist error (KeyError)."


def test_result_kinds_marks_a_reasoned_failure():
    assert "reasoned" in RESULT_KINDS
    reasoned = "FAILED: x\n" + failure_tag("policy", "weather_reuse_not_requested")
    assert result_kinds(reasoned) == ["failed", "reasoned"]
    unlisted = "FAILED: x\n" + failure_tag("approach", UNLISTED_REASON)
    assert result_kinds(unlisted) == ["failed"]
    assert result_kinds("FAILED: the task could not be completed.") == ["failed"]
