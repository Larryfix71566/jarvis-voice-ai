"""Typed turns and the spoken bare-yes gate against REAL pipecat pieces
(WS-34 C7-py).  No model, audio or network: a real user aggregator, a real
ForegroundRequests, a real TranscriptLogger and a real PipelineWorker carry
the frames; only inference is absent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMContextFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.turns.user_start import ExternalUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

import jarvis.bot.pipeline as pipeline_module
from jarvis.bot.pipeline import (
    _FOREGROUND_FRAME_KEY,
    BareYesGate,
    ForegroundRequests,
    FramePusher,
    InterruptionPassed,
    _foreground_request,
    approvals_flag_enabled,
    make_agent_event_handler,
    start_typed_turn,
    typed_request_flag_enabled,
)
from jarvis.bot.sensitive_turn import (
    SensitiveTurn,
    current_sensitive_turn,
    is_sensitive,
)
from jarvis.bot.transcript_log import TranscriptLogger
from jarvis.bot.typed_request import ApprovalBook
from jarvis.voice_sources import VoiceSources

SID = "00000000-0000-4000-8000-000000000001"
GEN = "00000000-0000-4000-8000-000000000002"


class Transport:
    def __init__(self):
        self.messages = []

    def output(self):
        return self

    async def send_message(self, frame):
        self.messages.append(frame.message["data"])


class Source(FrameProcessor):
    def __init__(self, ready: asyncio.Event):
        super().__init__()
        self._ready = ready

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self._ready.set()


class Sink(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.frames: list[Frame] = []
        self.armed_when_context_arrived: list[bool] = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        self.frames.append(frame)
        if isinstance(frame, LLMContextFrame):
            self.armed_when_context_arrived.append(is_sensitive())
        await self.push_frame(frame, direction)


@pytest.fixture
def holder(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "t.db"))
    from jarvis.db import run_migrations
    run_migrations()
    h = SensitiveTurn()
    token = current_sensitive_turn.set(h)
    yield h
    current_sensitive_turn.reset(token)


def rows():
    from jarvis.db import get_conn
    with get_conn() as conn:
        return [tuple(r) for r in conn.execute("SELECT role, content FROM conversations").fetchall()]


class Rig:
    """Source -> [gate] -> real user aggregator -> [TranscriptLogger] -> Sink."""

    def __init__(self, *, with_logger=True, gate=None):
        self.transport = Transport()
        self.owner = ForegroundRequests(self.transport, SID, GEN)
        self.ready = asyncio.Event()
        self.source = Source(self.ready)
        self.sink = Sink()
        self.context = LLMContext([])
        self.pair = LLMContextAggregatorPair(self.context, user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(start=[ExternalUserTurnStartStrategy()],
                                                   stop=[ExternalUserTurnStopStrategy()])))
        self.logger = TranscriptLogger(session_id="s1") if with_logger else None
        self.gate = gate
        steps = [self.source] + ([gate] if gate else []) + [self.pair.user()]
        steps += ([self.logger] if self.logger else []) + [self.sink]
        self.passed = InterruptionPassed()
        self.passed.source = self.logger
        self.worker = PipelineWorker(Pipeline(steps), params=PipelineParams(),
                                     observers=[self.passed])
        self.pusher = FramePusher()
        self.pusher.bind(self.worker)
        self.owner.install(gate or self.source, self.pair.user(), self.pair.assistant())
        self.runtime = SimpleNamespace(
            alive=True, interruption_passed=self.passed, sensitive_turn=None,
            foreground_requests=self.owner, voice_sources=VoiceSources(), session_id="s1")
        self._running = None

    async def __aenter__(self):
        runner = WorkerRunner(handle_sigint=False, handle_sigterm=False)
        self._running = asyncio.create_task(runner.run(self.worker))
        await asyncio.wait_for(self.ready.wait(), timeout=5)
        return self

    async def __aexit__(self, *exc):
        await self.worker.cancel()
        try:
            await asyncio.wait_for(self._running, timeout=5)
        except Exception:
            logging.getLogger(__name__).debug("worker did not stop cleanly", exc_info=True)

    async def typed(self, text, tag="typed:t1"):
        return await start_typed_turn(self.runtime, self.pusher, self.pair, text, tag)

    async def settle(self, predicate, timeout=3.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("condition not reached")
            await asyncio.sleep(0.01)


def context_frames(sink):
    return [f for f in sink.frames if isinstance(f, LLMContextFrame)]


# ------------------------------------------------------------ 23 / 24 / 25

async def test_typed_turn_is_one_user_context_message_with_a_foreground_request(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        assert await rig.typed("Will it rain tomorrow?", "typed:abc")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        frames = context_frames(rig.sink)
        assert len(frames) == 1
        assert rig.context.get_messages()[-1] == {"role": "user", "content": "Will it rain tomorrow?"}
        started = [m for m in rig.transport.messages if m.get("type") == "console/turn"]
        assert [m["state"] for m in started] == ["started"]
        assert started[0]["input_user_id"] == "typed:abc"
        request = frames[0].metadata[_FOREGROUND_FRAME_KEY]
        assert request is not None and request.request_id == started[0]["request_id"]
        assert request.request_id != "abc"  # server-minted, not client-chosen


async def test_results_for_a_typed_turn_carry_a_non_null_origin(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        assert await rig.typed("search for something", "approval:z")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        request = rig.owner.current
        assert request is not None
        sent = []
        book = ApprovalBook(session_id=SID, generation=GEN, emit=sent.append)
        token = _foreground_request.set(request)
        try:
            handler = make_agent_event_handler(rig.transport, None, book)
            handler({"type": "agent_tool_result", "agent": "analyst", "display_name": "Analyst",
                     "run_id": "r1", "tool": "web_search", "ok": True,
                     "arguments": {"query": "x"},
                     "result": '{"results":[{"title":"T","url":"https://example.test","snippet":"s"}]}'})
            handler({"type": "agent_tool_result", "agent": "developer", "display_name": "Developer",
                     "run_id": "r2", "tool": "plan_start", "ok": True,
                     "arguments": {"goal": "g"},
                     "result": json.dumps({"needs_confirmation": True, "summary": "Ready.",
                                           "staging_id": "stg_9"})})
        finally:
            _foreground_request.reset(token)
        await asyncio.sleep(0.05)
        displays = [m["display"] for m in rig.transport.messages if m.get("type") == "display"]
        assert displays and displays[0]["origin_request_id"] == request.request_id
        assert sent[0]["type"] == "approval/pending"
        assert sent[0]["origin_request_id"] == request.request_id


async def test_no_transcription_frame_and_no_user_transcription_echo(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        assert await rig.typed("hello there")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        assert not [f for f in rig.sink.frames
                    if isinstance(f, (TranscriptionFrame, InterimTranscriptionFrame))]
        assert not [m for m in rig.transport.messages if m.get("type") == "user-transcription"]


# ---------------------------------------------------------------------- 26

async def test_sensitive_text_is_armed_before_the_context_frame_and_never_stored(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        assert await rig.typed("my routing number is 021000021")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        # Armed when the model-bound frame arrived: the interruption's flag
        # clearing happened BEFORE arming, not after.
        assert rig.sink.armed_when_context_arrived == [True]
        assert is_sensitive()
        assert rows() == []


async def test_ordinary_text_is_stored_once_as_a_user_row(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        assert await rig.typed("what is the capital of France")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        assert rig.sink.armed_when_context_arrived == [False]
        assert rows() == [("user", "what is the capital of France")]


async def test_previous_turns_flag_is_cleared_by_a_new_typed_turn(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        holder.arm("financial")
        assert await rig.typed("an ordinary follow up")
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        assert rig.sink.armed_when_context_arrived == [False]
        assert rows() == [("user", "an ordinary follow up")]


async def test_control_arming_before_the_interruption_would_lose_the_flag(holder):
    """Why start_typed_turn waits: TranscriptLogger clears the flag on every
    InterruptionFrame, so arming first and interrupting after is undone."""
    async with Rig() as rig:
        holder.arm("financial")
        seen = asyncio.Event()
        original = rig.logger.process_frame

        async def watching(frame, direction):
            await original(frame, direction)
            if isinstance(frame, InterruptionFrame):
                seen.set()

        rig.logger.process_frame = watching
        await rig.worker.queue_frame(InterruptionFrame())
        await asyncio.wait_for(seen.wait(), timeout=3)
        assert not holder.is_armed()


# ---------------------------------------------------------------------- 27

async def test_interruption_that_never_passes_means_not_ready_and_no_side_effects(holder, monkeypatch):
    monkeypatch.setattr(pipeline_module, "TYPED_INTERRUPT_WAIT_S", 0.2)
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        rig.passed.source = object()  # the observer will never see "its" logger push it
        assert await rig.typed("hello") is False
        await asyncio.sleep(0.05)
        assert rig.context.get_messages() == []
        assert context_frames(rig.sink) == []
        assert rows() == []
        assert rig.transport.messages == []
        assert rig.owner.input_identity is None and rig.owner.parts == []


def approval_session(rig, book, replies, emitted=None):
    """A TypedRequestSession bound to the rig's REAL start_typed_turn and a
    silent note on the rig's real user aggregator (as run_session wires it)."""
    from jarvis.bot.typed_request import TypedRequestSession

    async def send(m):
        replies.append(m)

    async def start(text, tag):
        return await start_typed_turn(rig.runtime, rig.pusher, rig.pair, text, tag)

    async def speak(text):
        raise AssertionError("a decision never speaks")

    async def note(text):
        rig.runtime.voice_sources.append(rig.pair.user(), text)

    return TypedRequestSession(
        session_id=SID, generation=GEN, send=send, start_turn=start, speak=speak, note=note,
        is_alive=lambda: rig.runtime.alive, is_sensitive=is_sensitive, book=book)


def one_preview_book(emitted):
    book = ApprovalBook(session_id=SID, generation=GEN, emit=emitted.append)
    book.observe({"type": "agent_tool_result", "agent": "developer", "display_name": "Developer",
                  "tool": "plan_start", "ok": True, "run_id": "r1", "arguments": {"goal": "g"},
                  "result": json.dumps({"needs_confirmation": True, "staging_id": "stg_1"})},
                 origin_id=None, sensitive=False)
    return book, emitted[0]["approval_id"]


def decide_message(aid, decision, rid="00000000-0000-4000-8000-000000000030"):
    return {"type": "approval/decide", "version": 1, "session_id": SID, "generation": GEN,
            "request_id": rid, "approval_id": aid, "decision": decision}


async def test_approve_whose_interruption_never_passes_is_not_ready_with_no_side_effects(holder, monkeypatch):
    monkeypatch.setattr(pipeline_module, "TYPED_INTERRUPT_WAIT_S", 0.2)
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        rig.passed.source = object()  # the observer will never see "its" logger push it
        emitted, replies = [], []
        book, aid = one_preview_book(emitted)
        session = approval_session(rig, book, replies)
        await session.handle_decide(decide_message(aid, "approve"))
        await asyncio.sleep(0.05)
        assert [r["code"] for r in replies] == ["not_ready"]
        assert [m for m in emitted if m["type"] == "approval/settled"] == []
        assert [e.approval_id for e in book.open_items()] == [aid]
        assert rig.context.get_messages() == [] and context_frames(rig.sink) == []
        assert rows() == [] and rig.transport.messages == []
        assert rig.owner.input_identity is None and rig.owner.parts == []


async def test_approve_through_the_real_start_is_one_user_turn_then_settled(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        emitted, replies = [], []
        book, aid = one_preview_book(emitted)
        session = approval_session(rig, book, replies)
        await session.handle_decide(decide_message(aid, "approve"))
        await rig.settle(lambda: len(context_frames(rig.sink)) == 1)
        assert [r["code"] for r in replies] == ["accepted"]
        assert emitted[-1]["state"] == "approved"
        message = rig.context.get_messages()[-1]
        assert message["role"] == "user" and message["content"].startswith("Confirmed. Go ahead with the pending plan_start")
        started = [m for m in rig.transport.messages if m.get("type") == "console/turn"]
        assert started[0]["input_user_id"] == f"approval:{aid}"


async def test_decline_pushes_no_context_frame_and_starts_no_turn(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        emitted, replies = [], []
        book, aid = one_preview_book(emitted)
        session = approval_session(rig, book, replies)
        await session.handle_decide(decide_message(aid, "decline"))
        await asyncio.sleep(0.2)
        assert [r["code"] for r in replies] == ["accepted"] and emitted[-1]["state"] == "declined"
        assert context_frames(rig.sink) == []                    # no LLMContextFrame: no model run
        assert [m for m in rig.transport.messages if m.get("type") == "console/turn"] == []
        assert not [f for f in rig.sink.frames if isinstance(f, InterruptionFrame)]
        noted = [m for m in rig.context.get_messages() if "declined the pending plan_start" in str(m.get("content"))]
        assert len(noted) == 1                                    # the silent note is in the context
        assert rows() == []                                       # and never in the transcript


# ----------------------------------------------- origin of an entry (3.3b, S1)

def _preview_event(run_id, goal):
    return {"type": "agent_tool_result", "agent": "developer", "display_name": "Developer",
            "run_id": run_id, "tool": "plan_start", "ok": True, "arguments": {"goal": goal},
            "result": json.dumps({"needs_confirmation": True, "summary": f"Ready {goal}."})}


async def test_each_entry_carries_its_own_requests_id_with_interleaved_delegations(holder):
    sent = []
    book = ApprovalBook(session_id=SID, generation=GEN, emit=sent.append)
    handler = make_agent_event_handler(Transport(), None, book)
    req_a = SimpleNamespace(request_id="00000000-0000-4000-8000-0000000000a1", sequence=1)
    req_b = SimpleNamespace(request_id="00000000-0000-4000-8000-0000000000b2", sequence=2)

    async def run(event, delay):          # a delegation's detached run emits from its own task
        await asyncio.sleep(delay)
        handler(event)

    tasks = []
    for req, goal, delay in ((req_a, "a", 0.03), (req_b, "b", 0.0)):
        token = _foreground_request.set(req)
        try:
            tasks.append(asyncio.create_task(run(_preview_event(f"run-{goal}", goal), delay)))
        finally:
            _foreground_request.reset(token)
    await asyncio.gather(*tasks)          # b finishes first, a second: the runs interleave
    origins = {m["run_id"]: m["origin_request_id"] for m in sent if m["type"] == "approval/pending"}
    assert origins == {"run-a": req_a.request_id, "run-b": req_b.request_id}


async def test_a_run_whose_handler_was_cancelled_keeps_its_requests_id(holder):
    sent = []
    book = ApprovalBook(session_id=SID, generation=GEN, emit=sent.append)
    handler = make_agent_event_handler(Transport(), None, book)
    req = SimpleNamespace(request_id="00000000-0000-4000-8000-0000000000a1", sequence=1)
    detached = []

    async def voice_turn():               # the handler: starts the detached run, then is cancelled
        token = _foreground_request.set(req)
        try:
            async def run():
                await asyncio.sleep(0.05)
                handler(_preview_event("run-x", "x"))
            detached.append(asyncio.create_task(run()))
            await asyncio.sleep(10)
        finally:
            _foreground_request.reset(token)

    turn = asyncio.create_task(voice_turn())
    await asyncio.sleep(0.01)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    await detached[0]
    assert [m["origin_request_id"] for m in sent if m["type"] == "approval/pending"] == [req.request_id]


async def test_no_foreground_request_gives_a_null_origin(holder):
    sent = []
    book = ApprovalBook(session_id=SID, generation=GEN, emit=sent.append)
    handler = make_agent_event_handler(Transport(), None, book)
    assert _foreground_request.get() is None
    handler(_preview_event("run-n", "n"))
    assert [m["origin_request_id"] for m in sent if m["type"] == "approval/pending"] == [None]


async def test_not_alive_session_starts_nothing(holder):
    async with Rig() as rig:
        rig.runtime.sensitive_turn = holder
        rig.runtime.alive = False
        assert await rig.typed("hello") is False
        assert rig.context.get_messages() == []


async def test_observer_matches_its_own_interruption_by_id():
    passed = InterruptionPassed()
    source = object()
    passed.source = source
    mine, other = InterruptionFrame(), InterruptionFrame()
    waiter = passed.watch(mine.id)
    await passed.on_push_frame(SimpleNamespace(frame=other, source=source, direction=FrameDirection.DOWNSTREAM))
    assert not waiter.done()
    await passed.on_push_frame(SimpleNamespace(frame=mine, source=object(), direction=FrameDirection.DOWNSTREAM))
    assert not waiter.done()
    await passed.on_push_frame(SimpleNamespace(frame=mine, source=source, direction=FrameDirection.UPSTREAM))
    assert not waiter.done()
    await passed.on_push_frame(SimpleNamespace(frame=mine, source=source, direction=FrameDirection.DOWNSTREAM))
    assert waiter.done()


# ---------------------------------------------------------------------- 29

def make_gate(book, *, offer=False, sensitive=False):
    spoken = []

    async def speak(text):
        spoken.append(text)

    gate = BareYesGate(book, is_sensitive=lambda: sensitive, offer_pending=lambda: offer, speak=speak)
    return gate, spoken


def open_n(n):
    book = ApprovalBook(session_id=SID, generation=GEN, emit=lambda m: None)
    for i in range(n):
        book.observe({"type": "agent_tool_result", "agent": f"a{i}", "display_name": f"Agent{i}",
                      "tool": f"tool_{i}", "ok": True, "arguments": {"goal": f"g{i}"},
                      "result": json.dumps({"needs_confirmation": True})},
                     origin_id=None, sensitive=False)
    return book


async def say(rig, text, *, finalized=True, stamp="in-1"):
    frame_cls = TranscriptionFrame
    await rig.worker.queue_frames([
        UserStartedSpeakingFrame(),
        frame_cls(text, "u", stamp, finalized=finalized),
        UserStoppedSpeakingFrame()])
    await asyncio.sleep(0.15)


async def test_bare_yes_with_two_open_is_dropped_and_the_question_spoken():
    gate, spoken = make_gate(open_n(2))
    async with Rig(with_logger=False, gate=gate) as rig:
        await say(rig, "Yes.")
        assert len(spoken) == 1 and spoken[0].startswith("Two things are waiting")
        assert rig.context.get_messages() == []
        assert rig.owner.parts == [] and rig.owner.input_identity is None
        assert not [f for f in rig.sink.frames if isinstance(f, TranscriptionFrame)]


@pytest.mark.parametrize("n,text,offer,sensitive", [
    (1, "Yes.", False, False),            # exactly one open
    (0, "yes", False, False),             # none open
    (2, "yes", True, False),              # a file-send offer owns this yes
    (2, "yes", False, True),              # sensitive turn
    (2, "yes, the plan one", False, False),   # not a bare yes
])
async def test_other_transcripts_pass_through_untouched(n, text, offer, sensitive):
    gate, spoken = make_gate(open_n(n), offer=offer, sensitive=sensitive)
    async with Rig(with_logger=False, gate=gate) as rig:
        await say(rig, text)
        assert spoken == []
        # The transcript crossed the gate: ForegroundRequests (hooked on the
        # gate as the input source) recorded it exactly as for speech.
        assert rig.owner.parts == [text] and rig.owner.input_identity == ("in-1", "u")


async def test_interim_transcripts_pass_through():
    gate, spoken = make_gate(open_n(2))
    async with Rig(with_logger=False, gate=gate) as rig:
        await rig.worker.queue_frames([InterimTranscriptionFrame("yes", "u", "t1")])
        await asyncio.sleep(0.1)
        assert spoken == []


async def test_gate_fails_open_when_the_verdict_raises():
    class Broken:
        def yes_verdict(self, *a, **k):
            raise RuntimeError("boom")

    gate, spoken = make_gate(Broken())
    async with Rig(with_logger=False, gate=gate) as rig:
        await say(rig, "yes")
        assert spoken == []
        assert rig.owner.parts == ["yes"]


# --------------------------------------------------------- 30 / 33 wiring

PIPELINE_SOURCE = Path(pipeline_module.__file__).read_text(encoding="utf-8")


def test_gate_exists_only_when_the_book_exists():
    assert re.search(r"bare_yes_gate = None\s+if runtime\.approvals is not None:", PIPELINE_SOURCE)
    assert re.search(r"if bare_yes_gate is not None:\s+pipeline_steps\.append\(bare_yes_gate\)", PIPELINE_SOURCE)
    assert re.search(r"if approvals_flag_enabled\(\):[\s\S]{0,900}runtime\.approvals = ApprovalBook\(", PIPELINE_SOURCE)


def test_with_no_gate_install_and_observer_receive_what_they_always_did():
    assert "bare_yes_gate or speaker_transcript_gate or stt" in PIPELINE_SOURCE
    assert "runtime.transcript_source = bare_yes_gate or speaker_transcript_gate" in PIPELINE_SOURCE
    assert "only_from=runtime.transcript_source" in PIPELINE_SOURCE
    assert "runtime.speaker_gate = speaker_transcript_gate" in PIPELINE_SOURCE


def test_both_binding_lists_name_both_handlers():
    assert PIPELINE_SOURCE.count("handle_turn_typed") >= 3
    webrtc = PIPELINE_SOURCE.split('@webrtc_connection.event_handler("app-message")')[1].split("elif client_messages")[0]
    assert "await handle_turn_typed(message)" in webrtc and "await handle_approval_decide(message)" in webrtc
    ws = PIPELINE_SOURCE.split("client_messages.bind(")[1].split(")")[0]
    assert "handle_turn_typed" in ws and "handle_approval_decide" in ws


def test_handlers_do_not_run_on_the_client_message_task():
    """Detached on purpose: a blocking handler would hold the very input task
    that must carry the InterruptionFrame start_typed_turn waits for."""
    assert "_spawn_typed(typed_session.handle_turn(msg))" in PIPELINE_SOURCE
    assert "_spawn_typed(typed_session.handle_decide(msg))" in PIPELINE_SOURCE


@pytest.mark.parametrize("fn,var", [(approvals_flag_enabled, "JARVIS_APPROVALS_ENABLED"),
                                    (typed_request_flag_enabled, "JARVIS_TYPED_REQUEST_ENABLED")])
def test_kill_switches_default_on_and_read_false_forms(monkeypatch, fn, var):
    monkeypatch.delenv(var, raising=False)
    assert fn() is True
    for off in ("false", "0", "no", " FALSE ", "No"):
        monkeypatch.setenv(var, off)
        assert fn() is False
    for on in ("", "true", "1", "yes"):
        monkeypatch.setenv(var, on)
        assert fn() is True


# ------------------------------------- the WebSocket client-message task

def _ws_rig():
    """Like Rig, with the real ClientMessageProcessor right after the source,
    exactly where the WebSocket transport puts it."""
    from jarvis.bot.ws_transport import ClientMessageProcessor

    class _Rig(Rig):
        def __init__(self):
            self.client_messages = ClientMessageProcessor()
            super().__init__()
            steps = [self.source, self.client_messages, self.pair.user(), self.logger, self.sink]
            # No RTVI wrapper: it would swallow the raw client message that the
            # production runner's ClientMessageProcessor receives.
            self.worker = PipelineWorker(Pipeline(steps), params=PipelineParams(),
                                         observers=[self.passed], enable_rtvi=False)
            self.pusher.bind(self.worker)

    return _Rig()


def _typed_message(text):
    return {"type": "turn/typed", "version": 1, "session_id": SID, "generation": GEN,
            "request_id": "00000000-0000-4000-8000-000000000003", "text": text, "source": "composer"}


def _make_session(rig):
    from jarvis.bot.typed_request import TypedRequestSession
    replies = []

    async def send(message):
        replies.append(message)

    async def speak(text):
        pass

    async def start(text, tag):
        return await start_typed_turn(rig.runtime, rig.pusher, rig.pair, text, tag)

    session = TypedRequestSession(
        session_id=SID, generation=GEN, send=send, start_turn=start, speak=speak,
        is_alive=lambda: True, is_sensitive=is_sensitive, book=None)
    return session, replies


async def test_detached_handler_completes_a_typed_turn_through_the_ws_message_processor(holder):
    from pipecat.frames.frames import InputTransportMessageFrame
    rig = _ws_rig()
    async with rig:
        rig.runtime.sensitive_turn = holder
        session, replies = _make_session(rig)

        async def handler(message):
            asyncio.create_task(session.handle_turn(message))   # what run_session does

        rig.client_messages.bind(handler)
        await rig.worker.queue_frame(InputTransportMessageFrame(message=_typed_message("hello from the app")))
        await rig.settle(lambda: replies)
        assert replies[0]["code"] == "accepted"
        assert rig.context.get_messages()[-1] == {"role": "user", "content": "hello from the app"}


async def test_control_awaiting_inline_would_stall_the_ws_input_task(holder, monkeypatch):
    """Why the handlers are detached: the processor's input task awaits the
    handler, and the interruption has to travel through that same task."""
    from pipecat.frames.frames import InputTransportMessageFrame
    monkeypatch.setattr(pipeline_module, "TYPED_INTERRUPT_WAIT_S", 0.5)
    rig = _ws_rig()
    async with rig:
        rig.runtime.sensitive_turn = holder
        session, replies = _make_session(rig)

        async def inline_handler(message):
            await session.handle_turn(message)

        rig.client_messages.bind(inline_handler)
        await rig.worker.queue_frame(InputTransportMessageFrame(message=_typed_message("hello")))
        await rig.settle(lambda: replies, timeout=5)
        assert replies[0]["code"] == "not_ready"
        assert rig.context.get_messages() == []
