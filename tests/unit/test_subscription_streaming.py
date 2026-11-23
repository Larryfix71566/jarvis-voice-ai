"""WS-43: streamed voice text and pre-started native sessions (all behind flags)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis import subscription_tools as T
from jarvis.model_execution import (
    ModelExecutionRequest, ModelToolReference, _collect_chat_stream, _validated_tool_calls,
)
from jarvis.privacy_policy import DataPolicy
from jarvis.subscription import SubscriptionCapabilityError

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
TOOLS = (ModelToolReference("fixture", SCHEMA),)
MODEL = "claude-sonnet-5"


def request(parent="parent", task="task:0", workload="voice_supervisor", timeout=30.0):
    return ModelExecutionRequest(workload, task, parent, "public fixture", tools=TOOLS,
        data_policy=DataPolicy("approved_external", "public-fixture"), timeout_s=timeout)


def route():
    return SimpleNamespace(model=MODEL, route=SimpleNamespace(adapter="subscription_runtime"))


def args(*, system="system rules", user=None, stream=True):
    messages = [{"role": "system", "content": system}]
    if user is not None:
        messages.append({"role": "user", "content": user})
    return {"model": MODEL, "messages": messages, **({"stream": True} if stream else {})}


def make_session(*, stream, effort=None, parent="parent"):
    return T._ClaudeNativeSession(request(parent=parent), route(),
                                  {"messages": [{"role": "user", "content": "hi"}]}, "fake",
                                  stream=stream, effort=effort)


# --- A1: argv, menu, receipt ------------------------------------------------

DEFAULT_ARGV = ["claude", "--print", "--input-format", "stream-json", "--output-format",
                "stream-json", "--verbose", "--no-session-persistence", "--restricted",
                "--setting-sources", "", "--disable-slash-commands", "--no-chrome",
                "--strict-mcp-config", "--mcp-config", "/m.json", "--tools", "",
                "--allowed-tools", "mcp__mortimer__a,mcp__mortimer__b",
                "--permission-mode", "dontAsk", "--permission-prompts", "none",
                "--system-prompt-file", "/s.txt", "--model", MODEL]


def argv(**options):
    return T._claude_tool_argv("claude", MODEL, "/m.json", "/s.txt", ["a", "b"], **options)


def test_default_argv_is_the_literal_pre_ws43_list():
    assert argv() == DEFAULT_ARGV
    assert argv(stream=False, effort=None) == DEFAULT_ARGV


def test_stream_and_effort_append_exactly_their_flags_at_the_end():
    assert argv(stream=True) == DEFAULT_ARGV + ["--include-partial-messages"]
    assert argv(effort="low") == DEFAULT_ARGV + ["--effort", "low"]
    assert argv(stream=True, effort="high") == DEFAULT_ARGV + ["--include-partial-messages", "--effort", "high"]


def test_default_menu_record_and_path_match_the_old_formula(tmp_path):
    record = T.tool_menu_record("voice_supervisor", MODEL, TOOLS)
    assert set(record) == {"record_kind", "schema_version", "workload", "model", "tools"}
    old = T._json_digest([record["model"], record["tools"]])[:12]
    assert T.tool_menu_path(tmp_path, record) == tmp_path / f"voice_supervisor-{old}.json"


def test_streamed_and_buffered_menus_get_different_files(tmp_path):
    buffered = T.tool_menu_record("voice_supervisor", MODEL, TOOLS)
    streamed = T.tool_menu_record("voice_supervisor", MODEL, TOOLS, stream=True)
    effort = T.tool_menu_record("voice_supervisor", MODEL, TOOLS, effort="low")
    assert streamed["stream_text"] is True and "effort" not in streamed
    assert effort["effort"] == "low" and "stream_text" not in effort
    paths = {T.tool_menu_path(tmp_path, record) for record in (buffered, streamed, effort)}
    assert len(paths) == 3


def test_record_tool_menu_passes_the_options_through(tmp_path, monkeypatch):
    monkeypatch.setenv(T.TOOL_MENU_DIR_ENV, str(tmp_path))
    plain = T.record_tool_menu("voice_supervisor", MODEL, TOOLS)
    both = T.record_tool_menu("voice_supervisor", MODEL, TOOLS, stream=True, effort="medium")
    assert plain != both
    assert "stream_text" not in json.loads(plain.read_text())
    saved = json.loads(both.read_text())
    assert saved["stream_text"] is True and saved["effort"] == "medium"


IDENTITY = {"path": "/fixture/claude", "version": "2.1.291 (Claude Code)", "sha256": "b" * 64}


def receipt_for(**options):
    return {"schema_version": 1, "provider": "claude", "model": MODEL, "executable": IDENTITY,
        "protocol": T.PROTOCOL, "tool_names": ["fixture"],
        "invocation_sha256": T._json_digest(T._claude_tool_argv(
            IDENTITY["path"], MODEL, "<mcp-config>", "<system-prompt>", ["fixture"], **options)),
        "tool_schema_sha256": T._json_digest([{"name": t.name, "description": t.description,
            "parameters": dict(t.parameters)} for t in TOOLS]),
        "control_protocol_sha256": T._json_digest(T.NATIVE_CONTROL_CONTRACT),
        "protocol_source": T.NATIVE_PROTOCOL_SOURCE,
        "isolation_env_sha256": T._json_digest(T.NATIVE_ISOLATION_ENV),
        **{name: True for name in ("native_tool_call_observed", "unknown_tool_rejected",
            "unadvertised_host_tool_rejected", "unadvertised_host_tool_side_effect_absent",
            "builtins_disabled", "customization_canaries_absent", "system_constraints_observed",
            "api_credentials_absent", "terminal_success_without_error_items")}}


@pytest.mark.parametrize("proved", [{}, {"stream": True}, {"effort": "low"},
                                    {"stream": True, "effort": "low"}])
@pytest.mark.parametrize("asked", [{}, {"stream": True}, {"effort": "low"}, {"effort": "high"},
                                   {"stream": True, "effort": "low"}])
def test_receipt_matches_only_the_exact_stream_and_effort(monkeypatch, tmp_path, proved, asked):
    monkeypatch.setattr(T, "claude_tool_runtime_identity", lambda: IDENTITY)
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt_for(**proved)))
    monkeypatch.setenv(T.TOOLS_ENABLED_ENV, "1")
    monkeypatch.setenv(T.TOOL_CAPABILITY_RECEIPT_ENV, str(path))
    if proved == asked:
        assert T._validate_native_receipt(MODEL, ["fixture"], TOOLS, **asked) == IDENTITY
    else:
        with pytest.raises(SubscriptionCapabilityError):
            T._validate_native_receipt(MODEL, ["fixture"], TOOLS, **asked)


def test_voice_flag_helpers_default_off_and_refuse_bad_effort():
    assert not T.voice_streaming_enabled({}) and not T.voice_prestart_enabled({})
    assert T.voice_streaming_enabled({T.VOICE_STREAMING_ENV: "1"})
    assert not T.voice_streaming_enabled({T.VOICE_STREAMING_ENV: "true"})
    on = {T.VOICE_STREAMING_ENV: "1"}
    assert T.voice_prestart_enabled(on)
    assert not T.voice_prestart_enabled({**on, T.VOICE_PRESTART_ENV: "0"})
    assert not T.voice_prestart_enabled({T.VOICE_PRESTART_ENV: "1"})
    assert T.voice_effort({}) is None and T.voice_effort({T.VOICE_EFFORT_ENV: ""}) is None
    assert T.voice_effort({T.VOICE_EFFORT_ENV: "medium"}) == "medium"
    with pytest.raises(ValueError):
        T.voice_effort({T.VOICE_EFFORT_ENV: "max"})
    with pytest.raises(SubscriptionCapabilityError):
        T.ClaudeSubscriptionToolClient(MODEL, effort="max")


def test_receipt_script_menu_carries_stream_and_effort(tmp_path):
    from scripts.verify_claude_tool_receipts import Menu, load_menu, menu_options
    from scripts.verify_claude_developer_capability import CapabilityUnavailable
    plain = Menu(Path("x"), "voice_supervisor", MODEL, TOOLS, "fixture")
    assert (plain.stream, plain.effort, menu_options(plain)) == (False, None, {})

    def write(**extra):
        record = {**T.tool_menu_record("voice_supervisor", MODEL, TOOLS), **extra}
        target = tmp_path / "menu.json"
        target.write_text(json.dumps(record))
        return target
    loaded = load_menu(write(stream_text=True, effort="low"))
    assert menu_options(loaded) == {"stream": True, "effort": "low"}
    assert menu_options(load_menu(write())) == {}
    for bad in ({"stream_text": False}, {"stream_text": "yes"}, {"effort": "max"}, {"effort": 3}):
        with pytest.raises(CapabilityUnavailable, match="tool_menu_invalid"):
            load_menu(write(**bad))


# --- A2: session streaming --------------------------------------------------

def line(packet):
    return (json.dumps(packet) + "\n").encode()


def delta(text, parent=None, kind="text_delta"):
    inner = {"type": kind, "text": text} if kind == "text_delta" else {"type": kind, "partial_json": text}
    return line({"type": "stream_event", "parent_tool_use_id": parent,
                 "event": {"type": "content_block_delta", "index": 0, "delta": inner}})


def assistant(message_id, *blocks):
    return line({"type": "assistant", "message": {"id": message_id, "content": list(blocks)}})


TOOL_USE = {"type": "tool_use", "id": "call", "name": "mcp__mortimer__fixture", "input": {}}


async def run_stdout(s, *events):
    stream = asyncio.StreamReader()
    for event in events:
        stream.feed_data(event)
    stream.feed_eof()
    s.process = SimpleNamespace(stdout=stream)
    try:
        await s._stdout()
    finally:
        s.process = None


async def collect(s):
    events = []

    async def seen(fragment):
        events.append(fragment)
    return await _collect_chat_stream(s.stream_round(), seen, allowed_tools=("fixture",)), events


async def test_streamed_tool_round_rebuilds_the_same_content_and_call():
    s = make_session(stream=True)
    try:
        await run_stdout(s, delta("One moment. "), delta("sub-agent", parent="toolu_x"),
                         delta("{}", kind="input_json_delta"), delta("Checking."),
                         assistant("msg_1", {"type": "text", "text": "One moment. Checking."}),
                         assistant("msg_1", TOOL_USE))
        response, events = await collect(s)
        assert events == ["One moment. ", "Checking."]
        assert s.published_assistant["content"] == "One moment. Checking."
        message = response.choices[0].message
        assert message.content == "One moment. Checking."
        assert response.choices[0].finish_reason == "tool_calls"
        assert s.suspended is True
        validators = {"fixture": __import__("jsonschema").Draft202012Validator(SCHEMA)}
        calls = _validated_tool_calls(message, validators)
        assert [call.name for call in calls] == ["fixture"]
        assert calls[0].provider_extras == {"mortimer_parent_id": "parent", "mortimer_task_id": "task:0"}
        assert s.published_assistant["tool_calls"][0]["mortimer_parent_id"] == "parent"
        assert s.round_text == []
    finally:
        await s.close()


async def test_streamed_final_round_yields_deltas_then_stop_chunk():
    s = make_session(stream=True)
    try:
        await run_stdout(s, delta("Hello. "), delta("Done."),
                         line({"type": "result", "subtype": "success", "is_error": False,
                               "result": "Hello. Done.", "usage": {"input_tokens": 3, "output_tokens": 2,
                                                                  "cache_read_input_tokens": 0,
                                                                  "cache_creation_input_tokens": 0}}))
        response, events = await collect(s)
        assert events == ["Hello. ", "Done."]
        assert response.choices[0].message.content == "Hello. Done."
        assert response.choices[0].message.tool_calls == []
        assert response.choices[0].finish_reason == "stop"
        assert response.usage["completion_tokens"] == 2
        assert s.suspended is False
    finally:
        await s.close()


async def test_stream_mode_without_stream_events_falls_back_to_one_delta():
    s = make_session(stream=True)
    try:
        await run_stdout(s, assistant("msg_1", {"type": "text", "text": "One moment."}),
                         assistant("msg_1", TOOL_USE))
        response, events = await collect(s)
        assert events == ["One moment."]
        assert response.choices[0].message.content == "One moment."
    finally:
        await s.close()
    s = make_session(stream=True)
    try:
        await run_stdout(s, line({"type": "result", "subtype": "success", "is_error": False,
                                  "result": "All done."}))
        response, events = await collect(s)
        assert events == ["All done."] and response.choices[0].message.content == "All done."
    finally:
        await s.close()


async def test_stream_events_are_ignored_when_not_streaming():
    s = make_session(stream=False)
    try:
        await run_stdout(s, delta("ignored"), assistant("msg_1", {"type": "text", "text": "One moment."}),
                         assistant("msg_1", TOOL_USE))
        item = await s.queue.get()
        assert not isinstance(item, T._TextDelta)
        assert item.choices[0].message.content == "One moment."
        assert s.round_text == [] and s.published_assistant["content"] == "One moment."
    finally:
        await s.close()


async def test_next_completion_skips_text_deltas_for_buffered_consumers():
    s = make_session(stream=True)
    try:
        await run_stdout(s, delta("Hi."), line({"type": "result", "subtype": "success",
                                                "is_error": False, "result": "Hi."}))
        response = await s.next_completion(request(), {"messages": s.messages})
        assert response.choices[0].message.content == "Hi."
    finally:
        await s.close()


# --- A3/A4: client with a fake CLI -----------------------------------------

class FakeStdin:
    def __init__(self, proc):
        self.proc = proc

    def write(self, frame):
        packet = json.loads(frame)
        self.proc.written.append(packet)
        if packet.get("type") == "control_request":
            self.proc.stdout.feed_data(line({"type": "control_response", "response": {
                "subtype": "success", "request_id": packet["request_id"]}}))
        elif packet.get("type") == "user":
            for item in self.proc.script:
                self.proc.stdout.feed_data(item)

    async def drain(self):
        pass


class FakeProc:
    def __init__(self, script):
        self.stdout, self.stderr = asyncio.StreamReader(), asyncio.StreamReader()
        self.returncode, self.pid, self.written, self.script = None, 4242, [], script
        self.stdin = FakeStdin(self)


@pytest.fixture
def cli(monkeypatch, tmp_path):
    state = SimpleNamespace(procs=[], argvs=[], terminated=[], menus=[], validated=[], fail_spawns=0,
                            script=[delta("Hello. "), delta("There."),
                                    line({"type": "result", "subtype": "success", "is_error": False,
                                          "result": "Hello. There."})])

    async def spawn(*argv, **_kw):
        if state.fail_spawns:
            state.fail_spawns -= 1
            raise OSError("fixture spawn failure")
        proc = FakeProc(state.script)
        state.procs.append(proc)
        state.argvs.append(list(argv))
        return proc

    async def terminate(process):
        process.returncode = -15
        state.terminated.append(process)

    def validate(model, names, tools=(), **options):
        state.validated.append(options)
        return {"path": "fake"}

    def record(workload, model, tools, **options):
        state.menus.append(options)

    monkeypatch.setattr(T.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(T, "_terminate_async", terminate)
    monkeypatch.setattr(T, "_validate_native_receipt", validate)
    monkeypatch.setattr(T, "record_tool_menu", record)
    return state


async def drain_stream(generator):
    events = []

    async def seen(fragment):
        events.append(fragment)
    return await _collect_chat_stream(generator, seen, allowed_tools=("fixture",)), events


async def test_spare_is_used_with_no_second_launch_and_deadline_starts_at_bind(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL, effort="low")
    req = request(timeout=30.0)
    client.prestart(req, route(), args())
    assert client.has_spare()
    spare = await client.spares["parent"]
    assert len(cli.procs) == 1 and [p["type"] for p in cli.procs[0].written] == ["control_request"]
    assert spare.bound is False and spare.stream is True
    assert "--include-partial-messages" in cli.argvs[0] and cli.argvs[0][-2:] == ["--effort", "low"]
    launched_deadline = spare.deadline
    await asyncio.sleep(0.05)
    generator = await client.execute_request(req, route(), args(user="what time is it"))
    assert not client.has_spare() and len(cli.procs) == 1
    assert spare.deadline >= launched_deadline + 0.04
    assert spare.deadline == pytest.approx(spare.start_time + 30.0)
    assert [p["type"] for p in cli.procs[0].written] == ["control_request", "user"]
    assert "what time is it" in json.dumps(cli.procs[0].written[1])
    response, events = await drain_stream(generator)
    assert events == ["Hello. ", "There."] and response.choices[0].message.content == "Hello. There."
    assert client.sessions == {} and client.streaming == set()
    assert cli.menus == [{"stream": True, "effort": "low"}]


@pytest.mark.parametrize("change", ["system", "task"])
async def test_mismatched_spare_is_closed_and_a_cold_session_serves(cli, change):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    client.prestart(request(), route(), args())
    spare = await client.spares["parent"]
    real = request(task="task:other") if change == "task" else request()
    real_args = args(system="different rules" if change == "system" else "system rules", user="hi")
    generator = await client.execute_request(real, route(), real_args)
    assert len(cli.procs) == 2 and cli.terminated == [cli.procs[0]] and spare.closed
    response, _ = await drain_stream(generator)
    assert response.choices[0].message.content == "Hello. There."
    assert client.sessions == {} and not client.cleanup_unverified


async def test_flag_mismatch_between_spare_and_request_is_a_miss(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    client.prestart(request(), route(), args())
    await client.spares["parent"]
    response = await client.execute_request(request(), route(), args(user="hi", stream=False))
    assert response.choices[0].message.content == "Hello. There."
    assert len(cli.procs) == 2 and "--include-partial-messages" not in cli.argvs[1]
    assert cli.menus[-1] == {} and cli.validated[-1] == {}


async def test_discard_spares_closes_a_pending_spare(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    client.prestart(request(), route(), args())
    spare = await client.spares["parent"]
    with pytest.raises(SubscriptionCapabilityError, match="already pending"):
        client.prestart(request(parent="other"), route(), args())
    await client.discard_spares()
    assert spare.closed and cli.terminated == [cli.procs[0]] and not client.has_spare()
    await client.discard_spares()


async def test_discard_spares_cancels_a_spare_still_launching(cli, monkeypatch):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    gate = asyncio.Event()
    original = T._ClaudeNativeSession.launch

    async def slow_launch(self):
        await gate.wait()
        await original(self)
    monkeypatch.setattr(T._ClaudeNativeSession, "launch", slow_launch)
    client.prestart(request(), route(), args())
    await asyncio.sleep(0.02)
    await client.discard_spares()
    assert not client.has_spare() and cli.procs == [] and not client.cleanup_unverified


async def test_failed_spare_falls_back_to_a_cold_launch(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    cli.fail_spawns = 1
    client.prestart(request(), route(), args())
    with pytest.raises(OSError):
        await client.spares["parent"]
    generator = await client.execute_request(request(), route(), args(user="hi"))
    response, _ = await drain_stream(generator)
    assert len(cli.procs) == 1 and response.choices[0].message.content == "Hello. There."
    assert not client.cleanup_unverified


@pytest.mark.parametrize("messages", [[{"role": "user", "content": "hi"}]])
async def test_prestart_refuses_conversation_and_duplicate_parents(cli, messages):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    with pytest.raises(SubscriptionCapabilityError, match="system context only"):
        client.prestart(request(), route(), {"messages": messages, "stream": True})
    client.prestart(request(), route(), args())
    with pytest.raises(SubscriptionCapabilityError):
        client.prestart(request(), route(), args())
    await client.discard_spares()


async def test_second_request_for_an_unfinished_stream_is_refused(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    generator = await client.execute_request(request(), route(), args(user="hi"))
    assert client.streaming == {"parent"}
    with pytest.raises(SubscriptionCapabilityError, match="stream is still active"):
        await client.execute_request(request(task="task:1"), route(), args(user="again"))
    assert "parent" in client.sessions
    await _collect_chat_stream(generator, lambda _t: None, allowed_tools=("fixture",))
    assert client.streaming == set() and client.sessions == {}


async def test_streamed_tool_round_keeps_the_session_suspended(cli):
    cli.script = [delta("One moment."), assistant("msg_1", {"type": "text", "text": "One moment."}),
                  assistant("msg_1", TOOL_USE)]
    client = T.ClaudeSubscriptionToolClient(MODEL)
    generator = await client.execute_request(request(), route(), args(user="hi"))
    response, events = await drain_stream(generator)
    assert events == ["One moment."] and response.choices[0].finish_reason == "tool_calls"
    session = client.sessions["parent"]
    assert session.suspended and client.streaming == set()
    await client.close_request("parent")


async def test_non_true_stream_values_are_still_refused(cli):
    client = T.ClaudeSubscriptionToolClient(MODEL)
    with pytest.raises(SubscriptionCapabilityError, match="unsupported capability"):
        await client.execute_request(request(), route(), {**args(user="hi"), "stream": "yes"})
    assert cli.procs == []
