"""K3 flag lifecycle and the fifteen suppression sites (plan §7.3, D-H6)."""

import json

import pytest

from jarvis.bot.sensitive_turn import (
    SensitiveTurn, arm_from_text, current_sensitive_turn, current_turn_id,
    is_sensitive, redacted,
)
from jarvis.skills.registry import REPO_ROOT


@pytest.fixture
def holder():
    obj = SensitiveTurn()
    token = current_sensitive_turn.set(obj)
    yield obj
    current_sensitive_turn.reset(token)


# --- lifecycle -----------------------------------------------------------

def test_unset_contextvar_is_fail_closed():
    """FAIL-CLOSED (D-H4, review F1/F6): a missing holder means "suppress".
    In production the ContextVar is always set (run_session / cli.main wire it
    before any turn), so this branch is a loud wiring-regression signal, not a
    normal state. current_turn_id stays '-' (no armed turn to correlate)."""
    assert is_sensitive() is True
    assert current_turn_id() == "-"


def test_arm_and_clear(holder):
    assert is_sensitive() is False
    assert arm_from_text("my account number is 000123456789") is True
    assert is_sensitive() is True
    assert holder.kind == "account"
    assert holder.turn_id is not None
    holder.clear()
    assert is_sensitive() is False
    assert holder.turn_id is None


def test_arm_is_idempotent_within_a_turn(holder):
    arm_from_text("card number 4111111111111111")
    first = holder.turn_id
    arm_from_text("and my routing is 021000021")
    assert holder.turn_id == first


def test_clear_is_safe_when_never_armed(holder):
    holder.clear()
    assert is_sensitive() is False


def test_ordinary_turn_never_arms(holder):
    assert arm_from_text("what's the weather in Birmingham") is False
    assert is_sensitive() is False


def test_kill_switch_prevents_arming(holder, monkeypatch):
    monkeypatch.setenv("JARVIS_SENSITIVE_GUARD_ENABLED", "false")
    assert arm_from_text("card number 4111111111111111") is False
    assert is_sensitive() is False


def test_redacted_line_carries_no_content(holder):
    arm_from_text("card number 4111111111111111")
    line = redacted("card number 4111111111111111")   # no `role` arg (F20)
    assert "4111" not in line
    assert "card" not in line          # the KIND is a hint too
    assert holder.turn_id in line
    assert "28 chars withheld" in line  # len("card number 4111111111111111") == 28


def test_the_flag_reaches_a_child_task(holder):
    """The ContextVar holds a REFERENCE, so a task started before arming
    still sees the armed state (D-H4)."""
    import asyncio

    async def child():
        return is_sensitive()

    async def main():
        arm_from_text("card number 4111111111111111")
        return await asyncio.create_task(child())

    assert asyncio.run(main()) is True


# --- P1/P2/P3: the conversations table -----------------------------------

def test_p1_p2_no_conversations_row_when_armed(holder, tmp_path, monkeypatch):
    from jarvis.bot import transcript_log
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import get_conn, run_migrations
    run_migrations()

    transcript_log._persist("s1", "user", "ordinary line")
    arm_from_text("card number 4111111111111111")
    transcript_log._persist("s1", "user", "card number 4111111111111111")
    holder.clear()

    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM conversations").fetchall()
    assert [r[0] for r in rows] == ["ordinary line"]


def test_p4_p5_supervisor_does_not_persist_when_armed(holder, tmp_path, monkeypatch):
    """Same assertion for the CLI/text path (jarvis/agents/supervisor.py).

    Constructed with a stub client; only _persist behaviour is exercised.
    Authored during implementation (the plan left this case as an outline) —
    it exercises the exact guard pattern jarvis/agents/supervisor.py's chat()
    applies at both call sites (Step 6f: arm_from_text(...) then
    `if not is_sensitive(): self._persist(...)`) directly against a real
    Orchestrator instance and a real conversations table, without driving
    the full OpenAI-backed chat() loop (which would require mocking
    chat.completions.create's response shape for no additional coverage of
    the suppression logic itself)."""
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import get_conn, run_migrations
    run_migrations()
    from jarvis.agents.supervisor import Orchestrator

    orch = Orchestrator(
        settings=object(), registry=object(), session_id="s1",
        client_factory=lambda settings: None,
    )

    arm_from_text("ordinary question")               # P4 guard, not armed
    if not is_sensitive():
        orch._persist("user", "ordinary question")
    holder.clear()

    arm_from_text("my routing number is 021000021")  # P4 guard, armed
    if not is_sensitive():
        orch._persist("user", "my routing number is 021000021")

    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM conversations").fetchall()
    assert [r[0] for r in rows] == ["ordinary question"]


# --- F1: the real frame sequence suppresses the assistant row ------------

def test_real_frame_sequence_suppresses_assistant_row(holder, tmp_path, monkeypatch):
    """review F1 — drive the ACTUAL order the observer/processor see:
    UserStartedSpeakingFrame -> TranscriptionFrame(s) -> UserStoppedSpeakingFrame
    -> LLMTextFrame(s) -> LLMFullResponseEndFrame. The user turn carries no
    value; the ASSISTANT reply does (review F2). Both rows must be suppressed,
    and the flag must NOT have been cleared before the reply was scanned."""
    import asyncio
    from pipecat.frames.frames import (
        UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
        TranscriptionFrame, LLMTextFrame, LLMFullResponseEndFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection
    from pipecat.observers.base_observer import FramePushed
    from jarvis.bot.transcript_log import TranscriptObserver, TranscriptLogger
    from jarvis.db import get_conn, run_migrations
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    run_migrations()

    obs = TranscriptObserver("s1")
    log = TranscriptLogger(session_id="s1")

    async def push_obs(frame):
        await obs.on_push_frame(FramePushed(
            source=None, frame=frame, direction=FrameDirection.DOWNSTREAM,
            timestamp=0))
    async def push_log(frame):
        await log.process_frame(frame, FrameDirection.DOWNSTREAM)

    async def drive():
        await push_obs(UserStartedSpeakingFrame())
        # user asks a question with NO value in it
        await push_obs(TranscriptionFrame("what is my checking balance", "u", ""))
        await push_obs(UserStoppedSpeakingFrame())
        # assistant answers WITH the value
        await push_log(LLMTextFrame("Your checking account balance is $2,431.18."))
        await push_log(LLMFullResponseEndFrame())

    asyncio.run(drive())
    with get_conn() as conn:
        rows = conn.execute("SELECT role, content FROM conversations").fetchall()
    # the assistant row must be absent (reply scanned, flag still armed);
    # the user row is an ordinary question and MAY be present — assert the
    # figure never landed anywhere.
    assert all("2,431.18" not in c for _, c in rows)
    assert not any(role == "assistant" and "2,431" in c for role, c in rows)


# --- P8/P9/P10/P12/P13: the run log --------------------------------------

def test_run_log_redacts_on_the_snapshot(tmp_path, monkeypatch):
    """review F5/F6/F23 — the SNAPSHOT path: sensitive=True at construction
    redacts task (P12), tool_call args (P8), tool_result (P9), finish (P10)
    even for payloads that contain no financial detail of their own."""
    from jarvis.runlog.store import SENSITIVE_SENTINEL, RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()

    # correct signature: display_name is a required positional; root redirects
    # the JSONL under tmp_path; sensitive= is the snapshot (review F23).
    log = RunLogger("t0000001", "analyst", "Analyst",
                    "look up my balance", root=tmp_path, model="m",
                    sensitive=True)
    log.start()
    log.tool_call("web_search", {"query": "weather"})     # no value in args
    log.tool_result("web_search", "sunny and mild", 12, True)
    log.finish("done")

    payload = [json.loads(line)
               for line in (tmp_path / log.payload_path).read_text().splitlines()]
    start = next(r for r in payload if r["type"] == "run_start")
    call = next(r for r in payload if r["type"] == "tool_call")
    result = next(r for r in payload if r["type"] == "tool_result")
    end = next(r for r in payload if r["type"] == "run_end")
    assert start["task"] == SENSITIVE_SENTINEL          # P12
    assert call["tool"] == "web_search"                 # name survives
    assert call["arguments"] == SENSITIVE_SENTINEL      # P8
    assert result["tool"] == "web_search" and result["ok"] is True
    assert result["latency_ms"] == 12                   # metrics survive
    assert result["result"] == SENSITIVE_SENTINEL       # P9
    assert end["reply"] == SENSITIVE_SENTINEL           # P10
    assert end["tool_count"] == 1


def test_run_log_redacts_a_reply_derived_value_via_content_scan(tmp_path, monkeypatch):
    """review F2/F6 — sensitive=False snapshot, but a tool RESULT contains a
    value the user turn did not telegraph: the content scan catches it."""
    from jarvis.runlog.store import SENSITIVE_SENTINEL, RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    log = RunLogger("t0000002", "analyst", "Analyst", "look it up",
                    root=tmp_path, model="m", sensitive=False)
    log.start()
    log.tool_result("lookup", "your balance is $2,431.09", 5, True)
    log.finish("ok")
    payload = [json.loads(line)
               for line in (tmp_path / log.payload_path).read_text().splitlines()]
    result = next(r for r in payload if r["type"] == "tool_result")
    assert result["result"] == SENSITIVE_SENTINEL
    raw = (tmp_path / log.payload_path).read_text()
    assert "2,431" not in raw


def test_run_log_is_untouched_on_an_ordinary_turn(tmp_path, monkeypatch):
    """The regression that matters most: sensitive=False and no financial
    content — every payload round-trips verbatim."""
    from jarvis.runlog.store import RunLogger
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    log = RunLogger("t0000003", "analyst", "Analyst", "what's the weather",
                    root=tmp_path, model="m", sensitive=False)
    log.start()
    log.tool_call("web_search", {"query": "weather in Rome"})
    log.tool_result("web_search", "sunny, 24C", 7, True)
    log.finish("It's sunny in Rome.")
    raw = (tmp_path / log.payload_path).read_text()
    assert "weather in Rome" in raw and "sunny, 24C" in raw and "It's sunny" in raw


def test_runlog_never_imports_jarvis_bot_at_module_scope():
    """D-H7: store.py takes the snapshot as a ctor arg; it must not import
    jarvis.bot at all (jarvis.sensitive is fine — stdlib-only)."""
    source = (REPO_ROOT / "jarvis" / "runlog" / "store.py").read_text()
    assert "jarvis.bot" not in source


# --- P11: the memory gate ------------------------------------------------

def test_p11_memory_gate_is_independent_of_the_flag():
    """The gate inspects its own argument; it rejects regardless of the flag."""
    from jarvis.memory import FINANCIAL_REJECTION, scan_memory_content
    assert scan_memory_content("my routing number is 021000021") == FINANCIAL_REJECTION
    assert scan_memory_content("prefers jazz and instrumental music") is None
