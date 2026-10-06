from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from jarvis import subscription_tools as T
from jarvis.model_execution import ModelExecutionRequest, ModelToolReference
from jarvis.privacy_policy import DataPolicy
from jarvis.subscription import SubscriptionCapabilityError


def request(parent="parent", task="task:0"):
    return ModelExecutionRequest("developer", task, parent, "public fixture",
        tools=(ModelToolReference("fixture", {"type": "object", "properties": {},
                                              "additionalProperties": False}),),
        data_policy=DataPolicy("approved_external", "public-fixture"))


def route():
    return SimpleNamespace(model="claude-sonnet-5", route=SimpleNamespace(adapter="subscription_runtime"))


def session():
    return T._ClaudeNativeSession(request(), route(), {"messages": [{"role":"user", "content":"fixture"}]}, "fake")


def final_response():
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))])


async def test_flag_without_native_receipt_cannot_launch(monkeypatch):
    monkeypatch.setenv(T.TOOLS_ENABLED_ENV, "1")
    monkeypatch.delenv(T.TOOL_CAPABILITY_RECEIPT_ENV, raising=False)
    monkeypatch.setattr(T.asyncio, "create_subprocess_exec", lambda *_a, **_k: pytest.fail("provider started"))
    with pytest.raises(SubscriptionCapabilityError, match="receipt is required"):
        await T.ClaudeSubscriptionToolClient("claude-sonnet-5").execute_request(request(), route(), {"messages": []})


@pytest.mark.parametrize("field,value", [("native_tool_call_observed", "true"),
    ("customization_canaries_absent", 1), ("system_constraints_observed", "true"),
    ("unadvertised_host_tool_rejected", "true"), ("api_credentials_absent", "true"),
    ("schema_version", True), ("tool_schema_sha256", "changed"),
    ("protocol_source", {"version": "other"}), ("isolation_env_sha256", "changed")])
def test_native_receipt_requires_exact_proof_and_typed_booleans(monkeypatch, tmp_path, field, value):
    req = request()
    identity = {"path": "/fixture/claude", "version": "2.1.290 (Claude Code)", "sha256": "b" * 64}
    monkeypatch.setattr(T, "claude_tool_runtime_identity", lambda: identity)
    proof = {"schema_version": 1, "provider": "claude", "model": route().model,
        "executable": identity, "protocol": T.PROTOCOL, "tool_names": ["fixture"],
        "invocation_sha256": T._json_digest(T._claude_tool_argv(identity["path"], route().model,
            "<mcp-config>", "<system-prompt>", ["fixture"])),
        "tool_schema_sha256": T._json_digest([{"name": tool.name, "description": tool.description,
            "parameters": dict(tool.parameters)} for tool in req.tools]),
        "control_protocol_sha256": T._json_digest(T.NATIVE_CONTROL_CONTRACT),
        "protocol_source": T.NATIVE_PROTOCOL_SOURCE,
        "isolation_env_sha256": T._json_digest(T.NATIVE_ISOLATION_ENV),
        **{name: True for name in ("native_tool_call_observed", "unknown_tool_rejected",
            "unadvertised_host_tool_rejected", "unadvertised_host_tool_side_effect_absent",
            "builtins_disabled", "customization_canaries_absent", "system_constraints_observed",
            "api_credentials_absent", "terminal_success_without_error_items")}}
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(proof))
    monkeypatch.setenv(T.TOOLS_ENABLED_ENV, "1")
    monkeypatch.setenv(T.TOOL_CAPABILITY_RECEIPT_ENV, str(path))
    assert T._validate_native_receipt(route().model, ["fixture"], req.tools) == identity
    proof[field] = value
    path.write_text(json.dumps(proof))
    with pytest.raises(SubscriptionCapabilityError):
        T._validate_native_receipt(route().model, ["fixture"], req.tools)


@pytest.mark.parametrize("parent,call_id", [("other-parent", "call"), ("parent", "wrong-call")])
async def test_native_continuation_cannot_resume_other_parent_or_call(parent, call_id):
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    s.suspended = True
    context = s.messages + [{"role":"assistant","content":None,"tool_calls":[{
        "id":call_id,"type":"function","function":{"name":"fixture","arguments":"{}"},
        "mortimer_parent_id":parent,"mortimer_task_id":"task:0"}]},
        {"role":"tool","tool_call_id":call_id,"name":"fixture","content":"result"}]
    try:
        with pytest.raises(SubscriptionCapabilityError):
            await s.next_completion(request(parent=parent,task="task:1"), {"messages": context})
        assert not pending.result.done()
    finally:
        await s.close()


async def test_extra_context_refusal_happens_before_gateway_result_release():
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    s.suspended = True
    messages = s.messages + [{"role":"tool","tool_call_id":"call","name":"fixture","content":"secret-result"},
                             {"role":"user","content":"new instructions"}]
    try:
        with pytest.raises(SubscriptionCapabilityError, match="additional context"):
            await s.next_completion(request(task="task:1"), {"messages": messages})
        assert not pending.result.done()
    finally:
        await s.close()


async def test_earlier_context_mutation_cannot_resume_native_provider():
    s = session()
    s.suspended = True
    try:
        with pytest.raises(SubscriptionCapabilityError, match="earlier context"):
            await s.next_completion(request(task="task:1"), {"messages":[{"role":"user","content":"changed"}]})
    finally:
        await s.close()


@pytest.mark.parametrize("name,budget", [("Bash", 32), ("mcp__mortimer__fixture", 0)])
async def test_runtime_tool_names_and_request_budget_fail_closed(name, budget):
    s = session()
    s.max_tool_calls = budget
    stream = asyncio.StreamReader()
    stream.feed_data((json.dumps({"type":"assistant","message":{"content":[{
        "type":"tool_use","id":"call","name":name,"input":{}}]}})+"\n").encode())
    stream.feed_eof()
    s.process = SimpleNamespace(stdout=stream)
    try:
        await s._stdout()
        result = await s.queue.get()
        assert isinstance(result, SubscriptionCapabilityError)
        assert s.pending == {}
    finally:
        s.process = None
        await s.close()


async def test_cancellation_closes_only_the_parent_native_session(monkeypatch):
    closed = []
    started = asyncio.Event()
    class FakeSession:
        def __init__(self, req, *_a):
            self.parent = req.parent_request_id
        async def start(self):
            pass
        async def next_completion(self, *_a):
            started.set()
            await asyncio.Event().wait()
        async def close(self):
            closed.append(self.parent)
    monkeypatch.setattr(T, "_validate_native_receipt", lambda *_a: {"path":"fake"})
    monkeypatch.setattr(T, "_ClaudeNativeSession", FakeSession)
    client = T.ClaudeSubscriptionToolClient("claude-sonnet-5")
    untouched = FakeSession(request(parent="other-parent"))
    client.sessions["other-parent"] = untouched
    task = asyncio.create_task(client.execute_request(request(), route(), {"messages": []}))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == ["parent"]
    assert client.sessions == {"other-parent": untouched}


def test_native_argv_denies_builtins_and_has_explicit_mcp_and_stdin_stream():
    argv = T._claude_tool_argv("claude", "claude-sonnet-5", "/private/mcp.json", "/private/system.txt", ["fixture"])
    assert argv[argv.index("--tools")+1] == ""
    assert argv[argv.index("--setting-sources")+1] == ""
    assert argv[argv.index("--input-format")+1] == "stream-json"
    assert "--restricted" in argv and "--strict-mcp-config" in argv
    assert "--no-session-persistence" in argv
    assert "mcp__mortimer__fixture" in argv
    assert "--safe-mode" not in argv  # This flag disables the explicit MCP transport too.
    assert "--system-prompt-file" in argv


def continuation(s, *, arguments="{}", extra=()):
    return s.messages + [{"role": "assistant", "content": None, "tool_calls": [{
        "id": "call", "type": "function", "function": {"name": "fixture", "arguments": arguments},
        "mortimer_parent_id": "parent", "mortimer_task_id": "task:0"}]}] + [
        {"role": "tool", "tool_call_id": "call", "name": "fixture", "content": "result"}] + list(extra)


@pytest.mark.parametrize("extra", [({"role": "assistant", "content": "new context"},),
                                   ({"role": "user", "content": "new instructions"},)])
async def test_extra_assistant_or_user_context_is_not_silently_dropped(extra):
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    s.suspended = True
    try:
        with pytest.raises(SubscriptionCapabilityError, match="additional context"):
            await s.next_completion(request(task="task:1"), {"messages": continuation(s, extra=extra)})
        assert not pending.result.done()
    finally:
        await s.close()


@pytest.mark.parametrize("mutation", ["name", "arguments", "content"])
async def test_native_assistant_publication_cannot_be_changed_before_results(mutation):
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    s.suspended = True
    messages = continuation(s)
    if mutation == "content":
        messages[1][mutation] = "fabricated assistant text"
    else:
        messages[1]["tool_calls"][0]["function"][mutation] = "other" if mutation == "name" else '{"changed": true}'
    try:
        with pytest.raises(SubscriptionCapabilityError):
            await s.next_completion(request(task="task:1"), {"messages": messages})
        assert not pending.result.done()
    finally:
        await s.close()


async def test_duplicate_identical_native_calls_rejected_before_any_publication():
    s = session()
    stream = asyncio.StreamReader()
    stream.feed_data((json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": "mcp__mortimer__fixture", "input": {}}
        for call_id in ("call1", "call2")]}}) + "\n").encode())
    stream.feed_eof()
    s.process = SimpleNamespace(stdout=stream)
    try:
        await s._stdout()
        assert isinstance(await s.queue.get(), SubscriptionCapabilityError)
        assert s.pending == {}
        assert s.call_count == 0
    finally:
        s.process = None
        await s.close()


async def test_outer_system_constraints_use_exact_native_post_tool_hook():
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0", claimed=True)
    s.pending["call"] = pending
    s.suspended = True
    constraint = "The public fixture failed; do not report success."
    await s.queue.put(final_response())
    written = []
    async def write(packet):
        written.append(packet)
    s._write_native = write
    try:
        await s.next_completion(request(task="task:1"), {"messages": continuation(s, extra=(
            {"role": "system", "content": constraint},))})
        assert pending.result.result() == "result"
        s.pending.pop("call")
        s.completed["call"] = pending
        event = {"type": "control_request", "request_id": "hook1", "request": {
            "subtype": "hook_callback", "callback_id": T._POST_TOOL_CALLBACK, "tool_use_id": "call",
            "input": {"hook_event_name": "PostToolUse", "tool_use_id": "call",
                      "tool_name": "mcp__mortimer__fixture", "tool_input": {}}}}
        await s._post_tool_hook(event)
        assert written[0]["response"]["response"] == {"hookSpecificOutput": {
            "hookEventName": "PostToolUse", "additionalContext": constraint}}
        assert pending.hook_done
        with pytest.raises(SubscriptionCapabilityError, match="hook binding"):
            await s._post_tool_hook(event)
    finally:
        await s.close()


@pytest.mark.parametrize("mutation", ["call", "name", "arguments", "callback"])
async def test_native_hook_rejects_unrelated_calls_and_altered_arguments(mutation):
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0", claimed=True)
    pending.result.set_result("result")
    s.completed["call"] = pending
    source = {"hook_event_name": "PostToolUse", "tool_use_id": "call",
              "tool_name": "mcp__mortimer__fixture", "tool_input": {}}
    request_data = {"subtype": "hook_callback", "callback_id": T._POST_TOOL_CALLBACK,
                    "tool_use_id": "call", "input": source}
    if mutation == "call":
        request_data["tool_use_id"] = "other"
    elif mutation == "name":
        source["tool_name"] = "Bash"
    elif mutation == "arguments":
        source["tool_input"] = {"different": True}
    else:
        request_data["callback_id"] = "other"
    s._write_native = lambda _packet: pytest.fail("unbound native hook was released")
    try:
        with pytest.raises(SubscriptionCapabilityError, match="hook binding"):
            await s._post_tool_hook({"request_id": "hook", "request": request_data})
    finally:
        await s.close()


@pytest.mark.parametrize("change", [{"parent_id":"other"}, {"task_id":"other"},
                                  {"nonce":"wrong"}, {"name":"Bash"}])
async def test_private_gateway_rejects_other_tasks_and_unknown_tools(change):
    s = session()
    packet = {"nonce":s.nonce,"parent_id":s.parent_id,"task_id":s.origin_task_id,
              "request_id":"request","name":"fixture","arguments":{}}
    packet.update(change)
    reader = asyncio.StreamReader()
    reader.feed_data((json.dumps(packet)+"\n").encode())
    reader.feed_eof()
    class Writer:
        content = b""
        def write(self, value):
            self.content += value
        async def drain(self):
            pass
        def close(self):
            pass
        async def wait_closed(self):
            pass
    writer = Writer()
    try:
        await s._gateway(reader, writer)
        assert json.loads(writer.content)["ok"] is False
        assert s.pending == {}
    finally:
        await s.close()


async def test_failed_process_verification_still_removes_private_ipc(monkeypatch):
    s = session()
    directory = s.directory
    (directory / "gateway.json").write_text("private IPC canary")
    s.process = SimpleNamespace(pid=123)
    async def cannot_verify(_process):
        raise PermissionError("process-group verification unavailable")
    monkeypatch.setattr(T, "_terminate_async", cannot_verify)
    with pytest.raises(PermissionError):
        await s.close()
    assert s.closed is True
    assert not directory.exists()


@pytest.mark.parametrize("content", ["中" * 200000, "😀" * 1000000, "\x00" * 1000000])
async def test_actual_unix_gateway_preserves_large_unicode_and_control_content(content):
    s = session()
    errors = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    writer = None
    try:
        s.server = await asyncio.start_unix_server(s._gateway, path=str(s.socket_path), limit=262144)
        pending = T._Pending("call", "fixture", {}, loop.create_future(), "task:0")
        s.pending["call"] = pending
        pending.result.set_result(content)
        reader, writer = await asyncio.open_unix_connection(str(s.socket_path), limit=T.MAX_RESULT_FRAME_BYTES)
        packet = {"nonce": s.nonce, "parent_id": s.parent_id, "task_id": s.origin_task_id,
                  "request_id": "gateway", "name": "fixture", "arguments": {}}
        writer.write(T._encode_frame(packet, 262144))
        await writer.drain()
        response = json.loads(await asyncio.wait_for(reader.readline(), 3))
        assert response == {"ok": True, "content": content}
        assert len(T._result_frame(content)) <= T.MAX_RESULT_FRAME_BYTES
        assert pending.delivery is not None and await pending.delivery is True
        assert "call" in s.completed and "call" not in s.pending
        assert errors == []
    finally:
        if writer is not None:
            await T._close_writer(writer)
        await s.close()
        loop.set_exception_handler(previous_handler)


@pytest.mark.parametrize("content", ["x" * 1000001, "\ud800"])
async def test_oversize_or_unencodable_result_refuses_before_native_release(content):
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    s.suspended = True
    messages = continuation(s)
    messages[-1]["content"] = content
    try:
        with pytest.raises(SubscriptionCapabilityError):
            await s.next_completion(request(task="task:1"), {"messages": messages})
        assert not pending.result.done()
        assert s.completed == {}
        assert s.messages == [{"role": "user", "content": "fixture"}]
    finally:
        await s.close()


async def test_failed_result_write_never_commits_a_completed_native_call():
    s = session()
    pending = T._Pending("call", "fixture", {}, asyncio.get_running_loop().create_future(), "task:0")
    s.pending["call"] = pending
    pending.result.set_result("public fixture")
    packet = {"nonce": s.nonce, "parent_id": s.parent_id, "task_id": s.origin_task_id,
              "request_id": "gateway", "name": "fixture", "arguments": {}}
    reader = asyncio.StreamReader()
    reader.feed_data(T._encode_frame(packet, 262144))
    reader.feed_eof()
    class BrokenWriter:
        def write(self, _frame):
            raise BrokenPipeError("private socket detail must not escape")
        async def drain(self):
            raise BrokenPipeError("private socket detail must not escape")
        def close(self):
            pass
        async def wait_closed(self):
            raise BrokenPipeError("private socket detail must not escape")
    try:
        await s._gateway(reader, BrokenWriter())
        assert s.completed == {}
        assert s.pending == {"call": pending}
        assert pending.delivery is not None and await pending.delivery is False
        assert s.failure.category == "transport"
        assert str(await s.queue.get()) == "native tool result delivery failed"
    finally:
        await s.close()


async def test_unverified_cleanup_retains_owner_and_refuses_client_reuse(monkeypatch):
    client = T.ClaudeSubscriptionToolClient("claude-sonnet-5")
    class FailedOwner:
        async def close(self):
            raise T.SubscriptionRuntimeError("private cleanup diagnostic canary", category="cleanup")
    owner = FailedOwner()
    client.sessions["parent"] = owner
    with pytest.raises(T.SubscriptionRuntimeError, match="cleanup is unverified") as failure:
        await client.close_request("parent")
    assert failure.value.category == "cleanup"
    assert "canary" not in str(failure.value)
    assert client.failed_cleanup_sessions == {"parent": owner}
    assert client.cleanup_unverified
    monkeypatch.setattr(T, "_validate_native_receipt", lambda *_a: pytest.fail("new provider validation"))
    with pytest.raises(T.SubscriptionRuntimeError, match="cannot be reused"):
        await client.execute_request(request(parent="second"), route(), {"messages": []})
    with pytest.raises(T.SubscriptionRuntimeError, match="remains unverified"):
        await client.close_request("parent")


async def test_cancellation_is_preserved_when_its_native_cleanup_fails(monkeypatch):
    started = asyncio.Event()
    class FailedOwner:
        def __init__(self, *_a):
            pass
        async def start(self):
            pass
        async def next_completion(self, *_a):
            started.set()
            await asyncio.Event().wait()
        async def close(self):
            raise T.SubscriptionRuntimeError("unverified fixture cleanup", category="cleanup")
    monkeypatch.setattr(T, "_validate_native_receipt", lambda *_a: {"path":"fake"})
    monkeypatch.setattr(T, "_ClaudeNativeSession", FailedOwner)
    client = T.ClaudeSubscriptionToolClient("claude-sonnet-5")
    task = asyncio.create_task(client.execute_request(request(), route(), {"messages": []}))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.cleanup_unverified
    assert "parent" in client.failed_cleanup_sessions
    assert client.active_requests == {}


async def test_active_native_request_cannot_publish_after_another_cleanup_fails(monkeypatch):
    ready, release = asyncio.Event(), asyncio.Event()
    closed = []
    class ActiveOwner:
        def __init__(self, req, *_a):
            self.parent = req.parent_request_id
        async def start(self):
            ready.set()
        async def next_completion(self, *_a):
            await release.wait()
            return final_response()
        async def close(self):
            closed.append(self.parent)
    class FailedOwner:
        async def close(self):
            raise T.SubscriptionRuntimeError("unverified cleanup", category="cleanup")
    monkeypatch.setattr(T, "_validate_native_receipt", lambda *_a: {"path":"fake"})
    monkeypatch.setattr(T, "_ClaudeNativeSession", ActiveOwner)
    client = T.ClaudeSubscriptionToolClient("claude-sonnet-5")
    client.sessions["failed"] = FailedOwner()
    task = asyncio.create_task(client.execute_request(request(parent="active"), route(), {"messages": []}))
    await ready.wait()
    with pytest.raises(T.SubscriptionRuntimeError):
        await client.close_request("failed")
    release.set()
    with pytest.raises(T.SubscriptionRuntimeError, match="completion refused"):
        await task
    assert closed == ["active"]
    assert client.active_requests == {}
    assert client.cleanup_unverified


async def test_receipt_validation_wait_cannot_start_a_session_after_quarantine(monkeypatch):
    import threading
    entered, release = threading.Event(), threading.Event()
    class FailedOwner:
        async def close(self):
            raise T.SubscriptionRuntimeError("unverified cleanup", category="cleanup")
    def validate(*_a):
        entered.set()
        assert release.wait(timeout=2)
        return {"path":"fake"}
    monkeypatch.setattr(T, "_validate_native_receipt", validate)
    monkeypatch.setattr(T, "_ClaudeNativeSession", lambda *_a: pytest.fail("new session after quarantine"))
    client = T.ClaudeSubscriptionToolClient("claude-sonnet-5")
    client.sessions["failed"] = FailedOwner()
    task = asyncio.create_task(client.execute_request(request(parent="waiting"), route(), {"messages": []}))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        with pytest.raises(T.SubscriptionRuntimeError):
            await client.close_request("failed")
    finally:
        release.set()
    with pytest.raises(T.SubscriptionRuntimeError, match="launch refused"):
        await task
    assert client.active_requests == {}
