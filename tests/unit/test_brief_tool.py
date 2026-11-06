"""WS-13 P3m: the daily_brief direct tool (jarvis/bot/brief_tool.py). Offline fakes only."""

from __future__ import annotations

import asyncio
import contextvars
import gc
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from jarvis.bot import brief_tool
from jarvis.bot.brief_tool import (
    ACK_TEXT, BAD_SCOPE_TEXT, DAILY_BRIEF_SCHEMA, REFUSAL_TEXT, brief_enabled,
    build_daily_brief_tool,
)
from jarvis.bot.pipeline import BRIEF_LOOPBACK_PEERS
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.bot.tool_schemas import supervisor_tool_schemas
from jarvis.privacy_policy import DataPolicy, issue_tool_result
from jarvis.prompts import BRIEF_ADDENDUM, MAIL_UNAVAILABLE_ADDENDUM, build_supervisor_prompt
from jarvis.runlog.context import current_run_logger

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
TZ = ZoneInfo("America/New_York")
CANARY_S, CANARY_T = "CANARY_SENDER_7f3a", "CANARY_SUBJECT_91bc"


def mail(sender=CANARY_S, subject=CANARY_T):
    return {
        "ok": True,
        "accounts": [
            {"key": "gmail", "label": "Gmail", "status": "ok", "count": {"state": "exact", "value": 2},
             "headlines_complete": True, "returned_count": 1, "error": None},
            {"key": "att", "label": "bellsouth.net", "status": "failed",
             "count": {"state": "unknown", "value": None}, "headlines_complete": False,
             "returned_count": 0, "error": "login_rejected"},
        ],
        "messages": [{"id": "m1", "account": "gmail", "received_at": "2026-11-03T14:00:00+00:00",
                      "header_date": None, "sender": sender, "subject": subject,
                      "fields_unavailable": False}],
    }


class FakeRegistry:
    def __init__(self, content=None, *, raises=None, delay=0.0, arm=True):
        self.content, self.raises, self.delay, self.arm = content, raises, delay, arm
        self.calls: list[tuple[str, dict, object]] = []
        self.holder_seen = None
        self.runlog_seen = "unset"

    async def call_classified(self, name, arguments, *, execution_scope):
        self.calls.append((name, dict(arguments), execution_scope))
        self.holder_seen = current_sensitive_turn.get()
        self.runlog_seen = current_run_logger.get()
        if self.arm and self.holder_seen is not None:
            self.holder_seen.arm("tool_source_policy", execution_scope.parent_request_id)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises is not None:
            raise self.raises
        return issue_tool_result(execution_scope, json.dumps(self.content),
                                 DataPolicy("confidential", "verified-host-confidential-source"),
                                 "mail:att/gmail", ())


class Harness:
    def __init__(self, registry, *, eligible=True, connected=True, send_raises=None):
        self.registry, self.sent = registry, []
        self.connected_value, self.send_raises = connected, send_raises

        async def send(payload):
            if send_raises is not None:
                raise send_raises
            self.sent.append(payload)

        self.schema, self.handler = build_daily_brief_tool(
            registry=registry, send_display=send, eligible=lambda: eligible,
            connected=lambda: self.connected_value, now=lambda: NOW, tz=TZ)

    async def run(self, arguments=None):
        result = await self.handler(arguments if arguments is not None else {"scope": "mail"})
        await settle()
        return result


async def settle():
    pending = asyncio.all_tasks() - {asyncio.current_task()}
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.fixture
def clean_contextvars():
    t1 = current_sensitive_turn.set(None)
    t2 = current_run_logger.set(None)
    yield
    current_run_logger.reset(t2)
    current_sensitive_turn.reset(t1)


# --- schema, switch, menu, prompt -------------------------------------------------

def test_schema_shape():
    fn = DAILY_BRIEF_SCHEMA["function"]
    assert fn["name"] == "daily_brief"
    assert fn["parameters"]["properties"]["scope"]["enum"] == ["mail"]
    assert fn["parameters"]["required"] == ["scope"]
    for phrase in ("Gmail", "AT&T", "read-only", "send", "reply", "delete", "body"):
        assert phrase in fn["description"]


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("true", True), ("1", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("FALSE", False), (" no ", False), ("off", False), ("Off", False),
])
def test_kill_switch_parsing(value, expected):
    env = {} if value is None else {"JARVIS_BRIEF_ENABLED": value}
    assert brief_enabled(env) is expected


def test_kill_switch_reads_process_env_by_default(monkeypatch):
    monkeypatch.setenv("JARVIS_BRIEF_ENABLED", "off")
    assert brief_enabled() is False
    monkeypatch.delenv("JARVIS_BRIEF_ENABLED")
    assert brief_enabled() is True


DELEGATE = {"type": "function", "function": {"name": "delegate_task"}}


def test_menu_has_daily_brief_only_when_flag_is_on():
    off = [s["function"]["name"] for s in supervisor_tool_schemas(DELEGATE)]
    on = supervisor_tool_schemas(DELEGATE, brief=True)
    assert "daily_brief" not in off
    assert on[-1] is DAILY_BRIEF_SCHEMA and on[:-1] == supervisor_tool_schemas(DELEGATE)
    assert supervisor_tool_schemas(DELEGATE, brief=False) == supervisor_tool_schemas(DELEGATE)


_FMT = dict(jarvis_name="Mortimer", user_name="Larry", timezone="America/New_York",
            units="imperial", agent_catalog="- x", model_catalog="- y", voice_catalog="- z",
            memory_context="(none)")


def test_prompt_addendum_follows_the_flag():
    on = build_supervisor_prompt(**_FMT, brief=True)
    off = build_supervisor_prompt(**_FMT, brief=False)
    none = build_supervisor_prompt(**_FMT)
    assert BRIEF_ADDENDUM in on and MAIL_UNAVAILABLE_ADDENDUM not in on
    assert MAIL_UNAVAILABLE_ADDENDUM in off and BRIEF_ADDENDUM not in off
    assert BRIEF_ADDENDUM not in none and MAIL_UNAVAILABLE_ADDENDUM not in none
    assert on.startswith(none) and off.startswith(none)
    assert 'scope "mail"' in BRIEF_ADDENDUM and "never delegate" in BRIEF_ADDENDUM
    assert "that isn't something I have a tool for yet" in BRIEF_ADDENDUM
    assert "Mail isn't connected to me yet." in MAIL_UNAVAILABLE_ADDENDUM


def test_loopback_peer_allowlist():
    assert BRIEF_LOOPBACK_PEERS == {"127.0.0.1", "::1", "localhost"}


# --- the handler ------------------------------------------------------------------

async def test_unknown_or_missing_scope_is_a_fixed_error_with_no_calls(clean_contextvars):
    h = Harness(FakeRegistry(mail()))
    for args in ({}, {"scope": "calendar"}, {"scope": None}):
        assert await h.run(args) == BAD_SCOPE_TEXT
    assert h.registry.calls == [] and h.sent == []


async def test_ineligible_session_gets_exact_refusal_and_zero_registry_calls(clean_contextvars):
    h = Harness(FakeRegistry(mail()), eligible=False)
    assert await h.run() == "The brief needs the Mortimer app." == REFUSAL_TEXT
    assert h.registry.calls == [] and h.sent == []


async def test_eligible_raising_counts_as_ineligible(clean_contextvars):
    reg = FakeRegistry(mail())

    def boom():
        raise RuntimeError("no peer")

    _, handler = build_daily_brief_tool(registry=reg, send_display=lambda p: None,
                                        eligible=boom, connected=lambda: True)
    assert await handler({"scope": "mail"}) == REFUSAL_TEXT and reg.calls == []


async def test_ack_is_fixed_and_returned_before_the_registry_finishes(clean_contextvars):
    reg = FakeRegistry(mail(), delay=0.2)
    h = Harness(reg)
    result = await h.handler({"scope": "mail"})
    assert result == "Putting your mail together." == ACK_TEXT
    assert h.sent == []                       # job still running
    await settle()
    assert len(h.sent) == 1


async def test_tool_result_is_byte_identical_for_different_mail(clean_contextvars):
    a = await Harness(FakeRegistry(mail("Alice", "Hello"))).run()
    b = await Harness(FakeRegistry(mail("Bob", "Totally different"))).run()
    c = await Harness(FakeRegistry({"ok": False, "error": "mail_disabled"})).run()
    d = await Harness(FakeRegistry(raises=RuntimeError("x"))).run()
    assert a.encode() == b.encode() == c.encode() == d.encode() == ACK_TEXT.encode()


async def test_canaries_never_leave_the_card_payload(clean_contextvars, caplog):
    caplog.set_level(logging.DEBUG)
    h = Harness(FakeRegistry(mail()))
    result = await h.run()
    (payload,) = h.sent
    assert CANARY_S not in result and CANARY_T not in result
    for field in ("body", "title"):
        assert CANARY_S not in payload[field] and CANARY_T not in payload[field]
    outside = json.dumps({k: v for k, v in payload.items() if k != "brief"})
    assert CANARY_S not in outside and CANARY_T not in outside
    inside = json.dumps(payload["brief"])
    assert CANARY_S in inside and CANARY_T in inside
    logged = "\n".join(r.getMessage() + " " + str(r.args) for r in caplog.records)
    assert CANARY_S not in logged and CANARY_T not in logged
    assert "brief_job_sent" in logged
    assert "bellsouth" not in logged


async def test_card_payload_reports_each_account_with_real_status(clean_contextvars):
    h = Harness(FakeRegistry(mail()))
    await h.run()
    (payload,) = h.sent
    assert payload["kind"] == "brief" and payload["data_policy"] == "confidential"
    assert payload["arrival"] == "requested" and payload["outcome"] == "partial"
    accounts = {a["key"]: a for a in payload["brief"]["sections"][0]["accounts"]}
    assert accounts["gmail"]["status"] == "ok" and accounts["gmail"]["count_text"] == "2"
    assert accounts["att"]["status"] == "failed" and accounts["att"]["reason"] == "login rejected"
    assert accounts["att"]["label"] == "AT&T" and accounts["att"]["count_text"] == "unknown"


async def test_one_classified_call_with_a_host_owned_confidential_scope(clean_contextvars):
    reg = FakeRegistry(mail())
    h = Harness(reg)
    await h.run()
    ((name, args, scope),) = reg.calls
    assert name == "mail_headlines" and args == {"window_hours": 24, "account": "all"}
    assert scope.tool_name == "mail_headlines"
    assert scope.input_policy.level == "confidential"
    assert scope.parent_request_id == scope.task_id == scope.tool_call_id


async def test_job_runs_under_a_fresh_sensitive_turn_and_no_runlog(clean_contextvars):
    foreground = SensitiveTurn()
    current_sensitive_turn.set(foreground)
    sentinel = object()
    current_run_logger.set(sentinel)          # a foreground RunLogger stand-in
    reg = FakeRegistry(mail())                # arms whatever holder it sees
    h = Harness(reg)
    await h.run()
    assert reg.holder_seen is not None and reg.holder_seen is not foreground
    assert reg.holder_seen.is_armed()         # the job's own holder was armed
    assert foreground.is_armed() is False     # the session holder is untouched
    assert (foreground.armed, foreground.turn_id, foreground.kind) == (False, None, None)
    assert reg.runlog_seen is None            # no foreground RunLogger inside the job
    assert current_sensitive_turn.get() is foreground    # foreground context unchanged
    assert current_run_logger.get() is sentinel


async def test_a_new_turn_clearing_the_session_holder_does_not_clear_the_job(clean_contextvars):
    foreground = SensitiveTurn()
    current_sensitive_turn.set(foreground)
    reg = FakeRegistry(mail(), delay=0.1)
    h = Harness(reg)
    await h.handler({"scope": "mail"})
    await asyncio.sleep(0.02)
    foreground.clear()
    await settle()
    assert reg.holder_seen is not foreground and reg.holder_seen.is_armed()


async def test_not_connected_at_the_end_sends_nothing(clean_contextvars, caplog):
    caplog.set_level(logging.INFO)
    h = Harness(FakeRegistry(mail()), connected=False)
    assert await h.run() == ACK_TEXT
    assert h.sent == []
    assert "brief_job_dropped" in caplog.text and CANARY_S not in caplog.text


async def test_connection_lost_while_reading_sends_nothing(clean_contextvars):
    reg = FakeRegistry(mail(), delay=0.1)
    h = Harness(reg)
    await h.handler({"scope": "mail"})
    h.connected_value = False
    await settle()
    assert h.sent == []


@pytest.mark.parametrize("make", [
    lambda: FakeRegistry(raises=RuntimeError(f"boom {CANARY_S}")),
    lambda: FakeRegistry(raises=ValueError("tool_result_binding_invalid")),
    lambda: FakeRegistry({"ok": False, "error": "unknown_account"}),
    lambda: FakeRegistry(["not", "a", "dict"]),
])
async def test_registry_failure_still_produces_an_honest_all_failed_card(clean_contextvars, caplog, make):
    caplog.set_level(logging.DEBUG)
    h = Harness(make())
    assert await h.run() == ACK_TEXT
    (payload,) = h.sent
    section = payload["brief"]["sections"][0]
    assert {a["status"] for a in section["accounts"]} == {"failed"}
    assert payload["outcome"] == "all_failed" and section["headlines"] == []
    assert CANARY_S not in caplog.text and CANARY_S not in json.dumps(payload)


async def test_a_slow_source_times_out_into_an_all_failed_card(clean_contextvars, monkeypatch):
    monkeypatch.setattr(brief_tool, "JOB_TIMEOUT_S", 0.05)
    h = Harness(FakeRegistry(mail(), delay=1.0))
    await h.run()
    (payload,) = h.sent
    assert payload["outcome"] == "all_failed"


async def test_a_failing_send_is_logged_content_free_and_dropped(clean_contextvars, caplog):
    caplog.set_level(logging.DEBUG)
    h = Harness(FakeRegistry(mail()), send_raises=RuntimeError(f"socket {CANARY_T}"))
    assert await h.run() == ACK_TEXT
    assert "brief_job_send_failed" in caplog.text and CANARY_T not in caplog.text


async def test_tasks_are_strongly_referenced_until_done(clean_contextvars):
    reg = FakeRegistry(mail(), delay=0.05)
    h = Harness(reg)
    await h.handler({"scope": "mail"})
    gc.collect()
    await settle()
    assert len(h.sent) == 1


# --- session-owned cancellation, bounded send, teardown ----------------------------

class BlockingRegistry:
    """call_classified blocks on an event; records start, cancellation, contexts."""

    def __init__(self, content=None):
        self.content = content
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.completed = False
        self.holder_seen = None
        self.runlog_seen = "unset"

    async def call_classified(self, name, arguments, *, execution_scope):
        self.holder_seen = current_sensitive_turn.get()
        self.runlog_seen = current_run_logger.get()
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        self.completed = True
        return issue_tool_result(execution_scope, json.dumps(self.content),
                                 DataPolicy("confidential", "verified-host-confidential-source"),
                                 "mail:att/gmail", ())


class JobHarness:
    def __init__(self, registry, send=None):
        self.registry, self.sent, self.jobs = registry, [], brief_tool.BriefJobs()
        self.send_started = asyncio.Event()
        self.send_cancelled = False

        async def default_send(payload):
            self.sent.append(payload)

        self._send = send or default_send

        async def send(payload):
            self.send_started.set()
            try:
                await self._send(payload)
            except asyncio.CancelledError:
                self.send_cancelled = True
                raise

        self.schema, self.handler = build_daily_brief_tool(
            registry=registry, send_display=send, eligible=lambda: True,
            connected=lambda: True, now=lambda: NOW, tz=TZ, jobs=self.jobs)


async def test_disconnect_before_acquisition_cancels_the_job(clean_contextvars):
    reg = BlockingRegistry(mail())
    h = JobHarness(reg)
    result = await h.handler({"scope": "mail"})
    (task,) = list(h.jobs._tasks)
    assert h.jobs.cancel_all() == 1          # before the loop ever ran the job
    await asyncio.gather(task, return_exceptions=True)
    assert result == ACK_TEXT
    assert task.cancelled()
    assert not reg.started.is_set() and not reg.completed
    assert h.sent == [] and not h.send_started.is_set()
    assert len(h.jobs) == 0


async def test_disconnect_during_acquisition_cancels_the_registry_call(clean_contextvars, caplog):
    caplog.set_level(logging.INFO)
    reg = BlockingRegistry(mail())
    h = JobHarness(reg)
    await h.handler({"scope": "mail"})
    (task,) = list(h.jobs._tasks)
    await reg.started.wait()
    assert h.jobs.cancel_all() == 1
    await asyncio.gather(task, return_exceptions=True)
    assert reg.cancelled and not reg.completed
    assert h.sent == [] and not h.send_started.is_set()
    assert "brief_job_cancelled" in caplog.text and "brief_job_sent" not in caplog.text
    assert CANARY_S not in caplog.text


async def test_disconnect_during_sending_cancels_the_send(clean_contextvars, caplog):
    caplog.set_level(logging.INFO)
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    reg = BlockingRegistry(mail())
    reg.release.set()
    h = JobHarness(reg, send=blocked)
    await h.handler({"scope": "mail"})
    (task,) = list(h.jobs._tasks)
    await h.send_started.wait()
    assert h.jobs.cancel_all() == 1
    await asyncio.gather(task, return_exceptions=True)
    assert h.send_cancelled and task.cancelled()
    assert "brief_job_cancelled" in caplog.text and "brief_job_sent" not in caplog.text


async def test_a_send_that_never_returns_is_bounded(clean_contextvars, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(brief_tool, "SEND_TIMEOUT_S", 0.05)

    async def never(payload):
        await asyncio.Event().wait()

    reg = BlockingRegistry(mail())
    reg.release.set()
    h = JobHarness(reg, send=never)
    await h.handler({"scope": "mail"})
    await settle()
    assert "brief_job_send_failed type=TimeoutError" in caplog.text
    assert "brief_job_sent" not in caplog.text
    assert len(h.jobs) == 0


async def test_teardown_without_disconnect_closes_the_jobs(clean_contextvars):
    reg = BlockingRegistry(mail())
    h = JobHarness(reg)
    await h.handler({"scope": "mail"})
    (task,) = list(h.jobs._tasks)
    await reg.started.wait()
    await h.jobs.aclose()
    assert task.done() and reg.cancelled
    assert len(h.jobs) == 0 and h.jobs.closed
    assert await h.handler({"scope": "mail"}) == REFUSAL_TEXT
    assert len(h.jobs) == 0 and h.sent == []
    with pytest.raises(RuntimeError):
        h.jobs.start(asyncio.sleep(0), context=contextvars.copy_context())
    await h.jobs.aclose()                    # idempotent, never raises


async def test_job_has_its_own_holder_and_no_runlog_and_ack_comes_first(clean_contextvars):
    foreground = SensitiveTurn()
    current_sensitive_turn.set(foreground)
    current_run_logger.set(object())
    reg = BlockingRegistry(mail())
    h = JobHarness(reg)
    result = await h.handler({"scope": "mail"})
    assert result == ACK_TEXT and h.sent == []       # returned before the job finished
    await reg.started.wait()
    assert reg.holder_seen is not None and reg.holder_seen is not foreground
    assert reg.runlog_seen is None
    reg.release.set()
    await settle()
    assert len(h.sent) == 1
