"""Native subscription tool sessions suspended at Mortimer's own tool loop.

Claude receives only the request's explicit MCP schemas. The gateway is a
transport, never a skill executor: pending calls become normal completion tool
calls, and only a later policy-checked Mortimer request supplies their results.
The feature and exact-version native acceptance receipt are both mandatory.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jarvis.subscription import (
    SubscriptionCapabilityError,
    SubscriptionRuntimeError,
    _file_digest,
    _json_digest,
    _prompt,
    _subscription_env,
    _terminate_async,
    normalize_claude_usage,
    provider_command,
)
from jarvis.privacy_policy import tool_argument_limit, tool_result_limit, bounded_tool_arguments

TOOLS_ENABLED_ENV = "JARVIS_SUBSCRIPTION_TOOLS_ENABLED"
TOOL_CAPABILITY_RECEIPT_ENV = "JARVIS_SUBSCRIPTION_TOOL_CAPABILITY_RECEIPT"
PROTOCOL = "claude-stream-json-mortimer-mcp-v2"
CLAUDE_NATIVE_VERSIONS = frozenset({"2.1.290 (Claude Code)"})
MAX_TOOL_CALLS = 32
MAX_RESULT_CHARACTERS = 1_000_000  # Same content limit as ModelContextMessage.
MAX_RESULT_FRAME_BYTES = 6 * MAX_RESULT_CHARACTERS + 128
MAX_NATIVE_FRAME_BYTES = MAX_RESULT_FRAME_BYTES + 65_536
_GATEWAY_NAME = "mortimer"
_POST_TOOL_CALLBACK = "mortimer_post_tool_v1"
# Matches the native wire framing in official claude-agent-sdk 0.2.163's
# _internal/query.py. The installed 2.1.290 CLI was independently probed.
NATIVE_CONTROL_CONTRACT = {
    "subtype": "initialize", "skills": [],
    "hooks": {"PostToolUse": [{"matcher": None,
                                "hookCallbackIds": [_POST_TOOL_CALLBACK], "timeout": 120}]},
}
NATIVE_ISOLATION_ENV = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                        "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
NATIVE_PROTOCOL_SOURCE = {"package": "claude-agent-sdk", "version": "0.2.163",
                          "file": "claude_agent_sdk/_internal/query.py",
                          "sha256": "0562517de949f4431177f204fe84cda3265f495d0eb0a949b9ced96cc5bd8276"}


def _encode_frame(packet: dict[str, Any], limit: int) -> bytes:
    try:
        frame = (json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SubscriptionCapabilityError("native transport content cannot be encoded") from exc
    if len(frame) > limit:
        raise SubscriptionCapabilityError("native transport frame exceeds its byte limit")
    return frame


def _result_frame(content: str, name: str | None = None) -> bytes:
    quota = tool_result_limit(name)
    if not isinstance(content, str) or len(content) > quota:
        raise SubscriptionCapabilityError("native tool result exceeds the execution content limit")
    return _encode_frame({"ok": True, "content": content}, 6 * quota + 128)


def _request_frame_limit(names):
    return max(262144, max((tool_argument_limit(name) for name in names), default=16384) + 65536)


def _native_frame_limit(names):
    return max(MAX_NATIVE_FRAME_BYTES,
               max((6 * tool_result_limit(name) + 128 for name in names), default=0) + 65536)


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except (ConnectionError, OSError):
        pass  # The failure is recorded by its owner; no private transport error escapes.


def _claude_tool_argv(command: str, model: str, mcp_path: str,
                      system_path: str, names: list[str]) -> list[str]:
    return [command, "--print", "--input-format", "stream-json", "--output-format",
            "stream-json", "--verbose", "--no-session-persistence", "--restricted",
            "--setting-sources", "", "--disable-slash-commands", "--no-chrome",
            "--strict-mcp-config", "--mcp-config", mcp_path, "--tools", "",
            "--allowed-tools", ",".join(f"mcp__{_GATEWAY_NAME}__{name}" for name in names),
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--system-prompt-file", system_path, "--model", model]


def claude_tool_runtime_identity() -> dict[str, str]:
    selected = shutil.which(provider_command("claude"))
    if not selected:
        raise SubscriptionCapabilityError("Claude native tool runtime is unavailable")
    path = Path(selected).resolve()
    try:
        with tempfile.TemporaryDirectory(prefix="mortimer-runtime-", dir="/tmp") as cwd:
            result = subprocess.run([str(path), "--version"], cwd=cwd,
                                    env=_subscription_env(cwd), capture_output=True,
                                    text=True, timeout=5, check=False)
        version = result.stdout.strip()
        if result.returncode != 0 or version not in CLAUDE_NATIVE_VERSIONS:
            raise SubscriptionCapabilityError("Claude native tool version has no verified contract")
        return {"path": str(path), "version": version, "sha256": _file_digest(path)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SubscriptionCapabilityError("Claude native tool identity could not be checked") from exc


def _validate_native_receipt(model: str, names: list[str], tools: Any = ()) -> dict[str, str]:
    if os.environ.get(TOOLS_ENABLED_ENV) != "1":
        raise SubscriptionCapabilityError("subscription native tools are disabled")
    path = os.environ.get(TOOL_CAPABILITY_RECEIPT_ENV)
    if not path:
        raise SubscriptionCapabilityError("native tool capability acceptance receipt is required")
    try:
        source = Path(path)
        if not source.is_file() or source.stat().st_size > 500_000:
            raise ValueError("receipt unavailable")
        receipt = json.loads(source.read_text(encoding="utf-8"))
        identity = claude_tool_runtime_identity()
        invocation = _claude_tool_argv(identity["path"], model, "<mcp-config>", "<system-prompt>", names)
        if (type(receipt.get("schema_version")) is not int or receipt.get("schema_version") != 1
                or receipt.get("provider") != "claude"
                or receipt.get("model") != model or receipt.get("executable") != identity
                or receipt.get("protocol") != PROTOCOL
                or receipt.get("invocation_sha256") != _json_digest(invocation)
                or receipt.get("tool_names") != names
                or receipt.get("tool_schema_sha256") != _json_digest([
                    {"name": tool.name, "description": tool.description,
                     "parameters": dict(tool.parameters)} for tool in tools])
                or receipt.get("native_tool_call_observed") is not True
                or receipt.get("unknown_tool_rejected") is not True
                or receipt.get("unadvertised_host_tool_rejected") is not True
                or receipt.get("unadvertised_host_tool_side_effect_absent") is not True
                or receipt.get("builtins_disabled") is not True
                or receipt.get("customization_canaries_absent") is not True
                or receipt.get("system_constraints_observed") is not True
                or receipt.get("control_protocol_sha256") != _json_digest(NATIVE_CONTROL_CONTRACT)
                or receipt.get("protocol_source") != NATIVE_PROTOCOL_SOURCE
                or receipt.get("isolation_env_sha256") != _json_digest(NATIVE_ISOLATION_ENV)
                or receipt.get("api_credentials_absent") is not True
                or receipt.get("terminal_success_without_error_items") is not True):
            raise ValueError("receipt mismatch")
    except SubscriptionCapabilityError:
        raise
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise SubscriptionCapabilityError("native tool acceptance does not match this request") from exc
    return identity


@dataclass
class _Pending:
    call_id: str
    name: str
    arguments: dict[str, Any]
    result: asyncio.Future[str]
    task_id: str
    claimed: bool = False
    constraints: str = ""
    hook_done: bool = False
    frame: bytes | None = None
    delivery: asyncio.Future[bool] | None = None


class _ClaudeNativeSession:
    """One ephemeral provider process and private IPC channel per parent run."""

    def __init__(self, request: Any, resolved: Any, completion_args: dict[str, Any],
                 command: str, *, max_tool_calls: int = MAX_TOOL_CALLS):
        self.parent_id = request.parent_request_id
        self.workload = request.workload
        self.model = resolved.model
        self.task_id = request.task_id
        self.origin_task_id = request.task_id
        self.names = [tool.name for tool in request.tools]
        self.schemas = {tool.name: dict(tool.parameters) for tool in request.tools}
        self.descriptions = {tool.name: tool.description for tool in request.tools}
        self.command = command
        self.max_tool_calls = max_tool_calls
        self.call_count = 0
        self.pending: dict[str, _Pending] = {}
        self.completed: dict[str, _Pending] = {}
        self.seen_ids: set[str] = set()
        self.gateway_requests: set[str] = set()
        self.control_requests: set[str] = set()
        self.initialize_id = uuid.uuid4().hex
        self.initialized: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.messages = copy.deepcopy(completion_args["messages"])
        self.published_assistant: dict[str, Any] | None = None
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.pending_ready = asyncio.Condition()
        self.closed = False
        self.failure: BaseException | None = None
        self.suspended = False
        self.temp = tempfile.TemporaryDirectory(prefix="mortimer-native-tools-", dir="/tmp")
        self.directory = Path(self.temp.name)
        self.nonce = secrets.token_hex(32)
        self.socket_path = self.directory / "gateway.sock"
        self.process: asyncio.subprocess.Process | None = None
        self.server: asyncio.AbstractServer | None = None
        self.readers: list[asyncio.Task[Any]] = []
        self.gateway_tasks: set[asyncio.Task[Any]] = set()
        self.start_time = time.monotonic()
        self.deadline = self.start_time + request.timeout_s

    async def start(self) -> None:
        if any(message.get("role") == "tool" or message.get("tool_calls") for message in self.messages):
            raise SubscriptionCapabilityError("a native session cannot start with unrelated tool history")
        self.server = await asyncio.start_unix_server(self._gateway, path=str(self.socket_path),
                                                     limit=_request_frame_limit(self.names))
        self.socket_path.chmod(0o600)
        config = {"socket": str(self.socket_path), "nonce": self.nonce,
                  "parent_id": self.parent_id, "task_id": self.task_id,
                  "tools": [{"name": name, "description": self.descriptions[name],
                             "inputSchema": self.schemas[name]} for name in self.names]}
        gateway_path = self.directory / "gateway.json"
        gateway_path.write_text(json.dumps(config), encoding="utf-8")
        gateway_path.chmod(0o600)
        mcp_path = self.directory / "mcp.json"
        mcp_path.write_text(json.dumps({"mcpServers": {_GATEWAY_NAME: {
            "command": sys.executable, "args": [str(Path(__file__).resolve()), "--gateway", str(gateway_path)]
        }}}), encoding="utf-8")
        mcp_path.chmod(0o600)
        system_path = self.directory / "system.txt"
        system_path.write_text("\n\n".join(message["content"] for message in self.messages
                                          if message.get("role") == "system"), encoding="utf-8")
        system_path.chmod(0o600)
        argv = _claude_tool_argv(self.command, self.model, str(mcp_path), str(system_path), self.names)
        self.process = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=self.temp.name,
            env=self._environment(), start_new_session=True,
            limit=_native_frame_limit(self.names),
        )
        self.readers = [asyncio.create_task(self._stdout()), asyncio.create_task(self._stderr())]
        ordinary = [message for message in self.messages if message.get("role") != "system"]
        prompt = _prompt(ordinary) if ordinary else "Follow the supplied instructions."
        await self._write_native({"type": "control_request", "request_id": self.initialize_id,
                                  "request": NATIVE_CONTROL_CONTRACT})
        async with asyncio.timeout(max(0.001, self.deadline - time.monotonic())):
            await self.initialized
        await self._write_native({"type": "user", "client_composed": True,
                                  "message": {"role": "user", "content": prompt}})

    def _environment(self) -> dict[str, str]:
        env = _subscription_env(self.temp.name)
        env.update(NATIVE_ISOLATION_ENV)
        return env

    async def _write_native(self, packet: dict[str, Any]) -> None:
        if self.closed or not self.process or not self.process.stdin:
            raise SubscriptionRuntimeError("native control transport is unavailable")
        self.process.stdin.write(_encode_frame(packet, _native_frame_limit(self.names)))
        await self.process.stdin.drain()

    async def _post_tool_hook(self, event: dict[str, Any]) -> None:
        request_id = event.get("request_id")
        request = event.get("request", {})
        source = request.get("input", {})
        call_id = request.get("tool_use_id")
        pending = self.completed.get(call_id) if isinstance(call_id, str) else None
        if (not isinstance(request_id, str) or not request_id or request_id in self.control_requests
                or request.get("subtype") != "hook_callback"
                or request.get("callback_id") != _POST_TOOL_CALLBACK
                or not isinstance(source, dict) or source.get("hook_event_name") != "PostToolUse"
                or source.get("tool_use_id") != call_id or pending is None or pending.hook_done
                or source.get("tool_name") != f"mcp__{_GATEWAY_NAME}__{pending.name}"
                or source.get("tool_input") != pending.arguments or not pending.claimed
                or not pending.result.done() or pending.result.cancelled()):
            raise SubscriptionCapabilityError("native tool hook binding is invalid")
        if pending.delivery is not None and not await pending.delivery:
            raise SubscriptionRuntimeError("native tool result delivery failed", category="transport")
        self.control_requests.add(request_id)
        output: dict[str, Any] = {}
        if pending.constraints:
            # Official PostToolUse additionalContext is emitted as a native
            # role=system reminder after the result, preserving BaseAgent's
            # failure/draft constraints without rewriting tool content.
            output = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                              "additionalContext": pending.constraints}}
        await self._write_native({"type": "control_response", "response": {
            "subtype": "success", "request_id": request_id, "response": output}})
        pending.hook_done = True

    async def _stderr(self) -> None:
        assert self.process and self.process.stderr
        # Drain without retaining provider diagnostics or prompt material.
        while await self.process.stderr.read(65536):
            pass

    async def _stdout(self) -> None:
        assert self.process and self.process.stdout
        try:
            while raw := await self.process.stdout.readline():
                event = json.loads(raw)
                if not isinstance(event, dict):
                    raise SubscriptionRuntimeError("native stream contains a malformed event")
                if event.get("type") == "control_response":
                    response = event.get("response", {})
                    if (response.get("request_id") != self.initialize_id
                            or response.get("subtype") != "success" or self.initialized.done()):
                        raise SubscriptionCapabilityError("native initialization contract is invalid")
                    self.initialized.set_result(None)
                elif event.get("type") == "control_request":
                    await self._post_tool_hook(event)
                elif event.get("type") == "assistant":
                    content = event.get("message", {}).get("content", [])
                    if not isinstance(content, list):
                        raise SubscriptionRuntimeError("native assistant content is malformed")
                    calls = []
                    text = []
                    staged: list[_Pending] = []
                    for block in content:
                        if block.get("type") == "text":
                            text.append(str(block.get("text") or ""))
                        elif block.get("type") == "tool_use":
                            call_id = block.get("id")
                            native_name = block.get("name", "")
                            prefix = f"mcp__{_GATEWAY_NAME}__"
                            name = native_name.removeprefix(prefix)
                            arguments = block.get("input")
                            if (not native_name.startswith(prefix) or name not in self.schemas
                                    or not isinstance(call_id, str) or not call_id
                                    or call_id in self.seen_ids or not isinstance(arguments, dict)
                                    or self.call_count + len(staged) >= self.max_tool_calls
                                    or self.pending
                                    or any(item.call_id == call_id or (
                                        item.name == name and item.arguments == arguments
                                    ) for item in staged)):
                                raise SubscriptionCapabilityError("native runtime requested an unapproved or excessive tool")
                            from jsonschema import Draft202012Validator
                            Draft202012Validator(self.schemas[name]).validate(arguments)
                            bounded_tool_arguments(name, arguments)
                            staged.append(_Pending(call_id, name, copy.deepcopy(arguments),
                                                   asyncio.get_running_loop().create_future(), self.task_id))
                            calls.append(SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(
                                name=name, arguments=json.dumps(arguments)), model_extra={
                                "mortimer_parent_id": self.parent_id, "mortimer_task_id": self.task_id}))
                    if calls:
                        # Stdio MCP lacks the originating tool_use_id. Refuse
                        # identical calls before publication, so Mortimer's
                        # executor never acts on an ambiguous native batch.
                        for pending in staged:
                            self.seen_ids.add(pending.call_id)
                            self.pending[pending.call_id] = pending
                        self.call_count += len(staged)
                        self.published_assistant = {
                            "role": "assistant", "content": "\n".join(text) or None,
                            "tool_calls": [{"id": call.id, "type": "function", "function": {
                                "name": call.function.name, "arguments": call.function.arguments},
                                **call.model_extra} for call in calls],
                        }
                        async with self.pending_ready:
                            self.pending_ready.notify_all()
                        await self.queue.put(SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                            content="\n".join(text), tool_calls=calls, model_extra={}))], usage=None))
                elif event.get("type") == "result":
                    if (event.get("is_error") is not False or event.get("subtype") != "success"
                            or self.pending or any(not item.hook_done for item in self.completed.values())):
                        raise SubscriptionRuntimeError("native runtime did not finish successfully")
                    result = event.get("result")
                    if not isinstance(result, str) or not result.strip():
                        raise SubscriptionRuntimeError("native completion contains no assistant text")
                    await self.queue.put(SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                        content=result, tool_calls=[], model_extra={}))], usage=normalize_claude_usage(event.get("usage"))))
                    return
                elif event.get("type") not in {"system", "user", "stream_event", "rate_limit_event"}:
                    raise SubscriptionRuntimeError("native runtime returned an unsupported event")
            raise SubscriptionRuntimeError("native stream ended without a terminal result")
        except Exception as exc:  # noqa: BLE001 — provider stream errors are normalized without payloads
            self.failure = (exc if isinstance(exc, SubscriptionRuntimeError)
                            else SubscriptionRuntimeError("native stream validation failed"))
            async with self.pending_ready:
                self.pending_ready.notify_all()
            if not self.initialized.done():
                self.initialized.set_exception(self.failure)
                self.initialized.exception()  # start() still receives this failure; avoid orphan warnings in probes.
            await self.queue.put(self.failure)

    async def _gateway(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task:
            self.gateway_tasks.add(task)
        pending = None
        try:
            async with asyncio.timeout(max(0.001, self.deadline - time.monotonic())):
                packet = json.loads(await reader.readline())
                gateway_id = packet.get("request_id")
                if (packet.get("nonce") != self.nonce or packet.get("parent_id") != self.parent_id
                        or packet.get("task_id") != self.origin_task_id or not isinstance(gateway_id, str)
                        or gateway_id in self.gateway_requests):
                    raise SubscriptionCapabilityError("native gateway request binding is invalid")
                if packet.get("name") not in self.schemas or not isinstance(packet.get("arguments"), dict):
                    raise SubscriptionCapabilityError("native gateway tool is unavailable")
                from jsonschema import Draft202012Validator
                Draft202012Validator(self.schemas[packet["name"]]).validate(packet["arguments"])
                bounded_tool_arguments(packet['name'], packet['arguments'])
                self.gateway_requests.add(gateway_id)
                async with self.pending_ready:
                    await self.pending_ready.wait_for(lambda: self.closed or self.failure or any(
                        not item.claimed and item.name == packet.get("name")
                        and item.arguments == packet.get("arguments") for item in self.pending.values()))
                    candidates = [item for item in self.pending.values() if not item.claimed
                                  and item.name == packet.get("name") and item.arguments == packet.get("arguments")]
                    if self.closed or self.failure or len(candidates) != 1:
                        raise SubscriptionCapabilityError("native gateway call is unrelated or ambiguous")
                    pending = candidates[0]
                    pending.claimed = True
                content = await pending.result
                frame = pending.frame if pending.frame is not None else _result_frame(content, pending.name)
                pending.delivery = asyncio.get_running_loop().create_future()
                self.completed[pending.call_id] = pending
                writer.write(frame)
                await writer.drain()
                self.pending.pop(pending.call_id, None)
                pending.delivery.set_result(True)
        except Exception:  # noqa: BLE001 — IPC returns only a fixed refusal, never private exception text
            if pending is not None:
                self.completed.pop(pending.call_id, None)
                if pending.delivery is not None and not pending.delivery.done():
                    pending.delivery.set_result(False)
                self.failure = SubscriptionRuntimeError("native tool result delivery failed", category="transport")
                async with self.pending_ready:
                    self.pending_ready.notify_all()
                await self.queue.put(self.failure)
            try:
                writer.write(b'{"ok":false,"error":"Mortimer refused the native tool continuation."}\n')
                await writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            await _close_writer(writer)
            if task:
                self.gateway_tasks.discard(task)

    async def next_completion(self, request: Any, completion_args: dict[str, Any]) -> Any:
        if request.parent_request_id != self.parent_id or request.workload != self.workload:
            raise SubscriptionCapabilityError("native continuation belongs to a different parent or workload")
        if self.suspended:
            messages = completion_args["messages"]
            if messages[:len(self.messages)] != self.messages:
                raise SubscriptionCapabilityError("native continuation changed its earlier context")
            additions = messages[len(self.messages):]
            if any(message.get("role") not in {"assistant", "tool", "system"} for message in additions):
                raise SubscriptionCapabilityError("native continuation has unsupported additional context")
            assistants = [message for message in additions if message.get("role") == "assistant"]
            if (len(assistants) != 1 or not additions or additions[0] is not assistants[0]
                    or len(additions) < 1 + len(self.pending)):
                raise SubscriptionCapabilityError("native continuation has unsupported additional context")
            assistant = assistants[0]
            calls = assistant.get("tool_calls", [])
            if (not isinstance(calls, list) or len(calls) != len(self.pending)
                    or {call.get("id") for call in calls} != set(self.pending)):
                raise SubscriptionCapabilityError("native assistant tool bindings do not match this task")
            for call in calls:
                pending = self.pending[call["id"]]
                function = call.get("function")
                try:
                    arguments = json.loads(function["arguments"]) if isinstance(function, dict) else None
                except (KeyError, TypeError, ValueError):
                    arguments = None
                if (call.get("type", "function") != "function" or not isinstance(function, dict)
                        or function.get("name") != pending.name or arguments != pending.arguments
                        or call.get("mortimer_parent_id") != self.parent_id
                        or call.get("mortimer_task_id") != pending.task_id):
                    raise SubscriptionCapabilityError("native assistant tool bindings do not match this task")
            if self.published_assistant is not None and assistant != self.published_assistant:
                raise SubscriptionCapabilityError("native continuation changed its published assistant message")
            if self.published_assistant is None and assistant.get("content"):
                raise SubscriptionCapabilityError("native continuation has unsupported additional context")
            replies = additions[1:1 + len(self.pending)]
            constraints = additions[1 + len(self.pending):]
            if any(message.get("role") != "system" or not isinstance(message.get("content"), str)
                   or not message["content"].strip() or set(message) != {"role", "content"}
                   for message in constraints):
                raise SubscriptionCapabilityError("native continuation has unsupported additional context")
            if (len(replies) != len(self.pending)
                    or any(message.get("role") != "tool" for message in replies)
                    or {message.get("tool_call_id") for message in replies} != set(self.pending)
                    or any(message.get("name") != self.pending[message["tool_call_id"]].name
                           or not isinstance(message.get("content"), str) for message in replies)):
                raise SubscriptionCapabilityError("native tool results do not match this task's pending calls")
            # Validate and serialize the entire batch before releasing any
            # result future. A later oversized/malformed result cannot cause
            # partial native continuation or a falsely completed call.
            frames = {message["tool_call_id"]: _result_frame(message["content"], message['name']) for message in replies}
            constraint_text = "\n\n".join(message["content"] for message in constraints)
            _encode_frame({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                            "additionalContext": constraint_text}}, MAX_RESULT_FRAME_BYTES)
            for message in replies:
                pending = self.pending[message["tool_call_id"]]
                pending.constraints = constraint_text
                pending.frame = frames[message["tool_call_id"]]
                pending.result.set_result(message["content"])
            self.suspended = False
            self.messages = copy.deepcopy(messages)
            self.published_assistant = None
        self.task_id = request.task_id
        response = await self.queue.get()
        if isinstance(response, BaseException):
            raise response
        self.suspended = bool(response.choices[0].message.tool_calls)
        return response

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if not self.initialized.done():
            self.initialized.cancel()
        async with self.pending_ready:
            self.pending_ready.notify_all()
        for item in self.pending.values():
            if not item.result.done():
                item.result.cancel()
        try:
            if self.process is not None:
                await _terminate_async(self.process)
        finally:
            # Even unverified process cleanup must close the private gateway
            # and remove its nonce/schema files. The process error propagates;
            # an unverifiable descendant tree is never accepted as success.
            if self.server is not None:
                self.server.close()
                await self.server.wait_closed()
            for task in self.readers + list(self.gateway_tasks):
                task.cancel()
            await asyncio.gather(*self.readers, *self.gateway_tasks, return_exceptions=True)
            self.temp.cleanup()


class ClaudeSubscriptionToolClient:
    def __init__(self, model: str):
        self.model = model
        self.base_url = "subscription://claude"
        self.sessions: dict[str, _ClaudeNativeSession] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.active_requests: dict[str, int] = {}
        # Keep failed ownership visible and refuse every future request on
        # this client. Recreating a session is not evidence that the prior
        # provider process tree has been terminated.
        self.failed_cleanup_sessions: dict[str, _ClaudeNativeSession] = {}
        self.cleanup_unverified = False

    async def execute_request(self, request: Any, resolved: Any, completion_args: dict[str, Any]) -> Any:
        if self.cleanup_unverified:
            raise SubscriptionRuntimeError("native provider cleanup is unverified; client cannot be reused",
                                           category="cleanup")
        if (resolved.model != self.model or resolved.route.adapter != "subscription_runtime"
                or completion_args.get("max_tokens") is not None or completion_args.get("stream")
                or completion_args.get("response_format") is not None
                or request.attachments or request.extra_body or request.temperature is not None):
            raise SubscriptionCapabilityError("native subscription request has an unsupported capability")
        parent = request.parent_request_id
        lock = self.locks.setdefault(parent, asyncio.Lock())
        self.active_requests[parent] = self.active_requests.get(parent, 0) + 1
        try:
            async with lock:
                if self.cleanup_unverified:
                    raise SubscriptionRuntimeError("native provider cleanup is unverified; client cannot be reused",
                                                   category="cleanup")
                session = self.sessions.get(parent)
                if session is None:
                    names = [tool.name for tool in request.tools]
                    identity = await asyncio.to_thread(_validate_native_receipt, self.model, names, request.tools)
                    if self.cleanup_unverified:
                        raise SubscriptionRuntimeError("native provider cleanup is unverified; launch refused",
                                                       category="cleanup")
                    session = _ClaudeNativeSession(request, resolved, completion_args, identity["path"])
                    self.sessions[parent] = session
                    await session.start()
                elif (session.model != resolved.model
                      or session.schemas != {tool.name: dict(tool.parameters) for tool in request.tools}
                      or session.descriptions != {tool.name: tool.description for tool in request.tools}):
                    raise SubscriptionCapabilityError("native continuation changed the model or tool registry")
                response = await session.next_completion(request, completion_args)
                if self.cleanup_unverified:
                    raise SubscriptionRuntimeError("native provider cleanup is unverified; completion refused",
                                                   category="cleanup")
                if not response.choices[0].message.tool_calls:
                    await self.close_request(parent)
                return response
        except BaseException as failure:
            try:
                await self.close_request(parent)
            except BaseException:
                if isinstance(failure, asyncio.CancelledError):
                    raise failure
                raise
            raise
        finally:
            remaining = self.active_requests[parent] - 1
            if remaining:
                self.active_requests[parent] = remaining
            else:
                self.active_requests.pop(parent)
                if parent not in self.sessions:
                    self.locks.pop(parent, None)

    async def close_request(self, parent_request_id: str) -> None:
        if parent_request_id in self.failed_cleanup_sessions:
            raise SubscriptionRuntimeError("native provider cleanup remains unverified",
                                           category="cleanup")
        session = self.sessions.pop(parent_request_id, None)
        try:
            if session is not None:
                try:
                    await session.close()
                except BaseException as failure:
                    self.failed_cleanup_sessions[parent_request_id] = session
                    self.cleanup_unverified = True
                    if isinstance(failure, asyncio.CancelledError):
                        raise
                    raise SubscriptionRuntimeError("native provider cleanup is unverified",
                                                   category="cleanup") from None
        finally:
            if parent_request_id not in self.active_requests:
                self.locks.pop(parent_request_id, None)


async def _gateway_worker(config_path: str) -> None:
    """Explicit MCP server forwards to its private parent; it executes no tool."""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in config["tools"]}
    server = Server(_GATEWAY_NAME)

    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in tools.values()]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]):
        if name not in tools:
            raise ValueError("Mortimer rejected an unknown tool")
        writer = None
        try:
            reader, writer = await asyncio.open_unix_connection(config["socket"], limit=6 * tool_result_limit(name) + 128)
            packet = {key: config[key] for key in ("nonce", "parent_id", "task_id")}
            packet.update(name=name, arguments=arguments, request_id=uuid.uuid4().hex)
            writer.write(_encode_frame(packet, _request_frame_limit((name,))))
            await writer.drain()
            response = json.loads(await reader.readline())
            if not response.get("ok"):
                raise ValueError("Mortimer refused the tool result")
            return [TextContent(type="text", text=response["content"])]
        except Exception:  # noqa: BLE001 — expose no private socket/config details through MCP
            raise ValueError("Mortimer refused the native tool continuation") from None
        finally:
            if writer is not None:
                await _close_writer(writer)

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--gateway":
        raise SystemExit("Only the private Mortimer gateway entry point is supported.")
    asyncio.run(_gateway_worker(sys.argv[2]))
