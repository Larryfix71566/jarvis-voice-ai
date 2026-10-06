"""Spawn-free source authority, exact host scope, and pre-result sink tests."""
from contextlib import AsyncExitStack, asynccontextmanager
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn, is_sensitive
from jarvis.privacy_policy import (
    DataPolicy, ToolResultBindingError, make_tool_execution_scope, validate_tool_result,
)
from jarvis.model_execution import (
    ModelContextMessage, ModelExecutionRequest, ModelToolReference, execute_chat,
)
from jarvis.model_routing import AccessRoute, ModelRouteError, ResolvedModelRoute
from jarvis.runlog.context import run_logger_scope
from jarvis.runlog.store import RunLogger
from jarvis.skills import registry as registry_module
from jarvis.skills.registry import SkillRegistry, _ServerHandle, _ToolSourceContract
from mcp_servers.mcp_repo import logic as repo_logic


CANARY = "SYNTHETIC_PRIVATE_SOURCE_CANARY"


@pytest.fixture(autouse=True)
def initialized_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def response(body=None, *, error=False, text=""):
    return SimpleNamespace(isError=error, structuredContent=body,
                           content=[SimpleNamespace(text=text)])


class Session:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        return self.value


def registry_for(tool, server, session, *, pinned=False, root=None):
    registry = SkillRegistry("unused.yaml")
    entry = {"name": server, "command": "python",
             "args": ["-m", f"mcp_servers.{server.replace('-', '_')}.server"], "env": {}}
    schema = SimpleNamespace(name=tool, description="Synthetic test tool",
                             inputSchema={"type": "object", "properties": {}})
    registry._tools[tool] = (server, schema)
    registry._sessions[server] = session
    registry._handles[server] = _ServerHandle(server, entry, state="up", session=session)
    if pinned:
        registry._source_contracts[server] = _ToolSourceContract(
            server, entry["args"][1], session, root,
        )
    return registry


def execution(tool, arguments, privacy="approved_external", parent="source-parent"):
    return make_tool_execution_scope(parent, "subagent:source-parent:0", "source-call", tool,
                                     arguments, DataPolicy(privacy, "input"))


def memory_logger():
    logger = RunLogger("source-parent", "developer", "Developer", "synthetic task",
                       enabled=True, sensitive=False)
    logger._execute = lambda *_args: None
    original = logger._safe
    logger._safe = lambda operation, callback: (
        None if operation == "skill_trace_redaction" else original(operation, callback)
    )
    return logger


@pytest.mark.parametrize("value", [
    response({"ok": True, "document": CANARY, "policy": {"level": "approved_external"}}),
    response({"ok": False, "error": CANARY}),
    response(error=True, text=CANARY),
])
async def test_unknown_private_sources_protect_before_early_mcp_log(value):
    session = Session(value)
    registry = registry_for("get_note", "mcp-notes", session)
    scope = execution("get_note", {"note_id": 1})
    logger = memory_logger()
    logger.mcp_call("prior_tool", "prior-server", False, 3, error=CANARY)
    with run_logger_scope(logger):
        envelope = await registry.call_classified("get_note", {"note_id": 1}, execution_scope=scope)

    policy, content = validate_tool_result(scope, envelope)
    assert policy.level == "confidential"
    assert CANARY in content  # Retained privately; no untested release transformation.
    assert is_sensitive()
    assert logger._sensitive
    assert CANARY not in repr(logger._buffer)
    assert all(record["error"] in {None, "<sensitive>"} for record in logger._buffer)


@pytest.mark.parametrize("field", ["arguments", "tool", "parent"])
async def test_scope_mismatch_refuses_before_child_invocation(field):
    session = Session(response({"ok": True}))
    registry = registry_for("get_note", "mcp-notes", session)
    scope = execution("get_note", {"note_id": 1}, parent="wrong-parent" if field == "parent" else "source-parent")
    logger = memory_logger()
    with run_logger_scope(logger), pytest.raises(ToolResultBindingError, match="^tool_result_binding_invalid$"):
        await registry.call_classified(
            "other_tool" if field == "tool" else "get_note",
            {"note_id": 2 if field == "arguments" else 1}, execution_scope=scope,
        )
    assert session.calls == []


@pytest.mark.parametrize("pinned,tool,server,body", [
    (True, "get_current_time", "mcp-time", {"iso": "2026-10-06T12:00:00Z", "human": "synthetic time", "timezone": "UTC", "unix": 0}),
    (True, "date_diff", "mcp-time", {"days": 1, "hours": 24.0}),
    (True, "web_search", "mcp-web", {"results": [{"url": "https://public.example/", "snippet": "public synthetic fact"}]}),
    (True, "get_weather", "mcp-web", {"temperature_f": 70, "source": "weather.gov"}),
    (True, "status_build", "mcp-status", {"revision": "synthetic-revision"}),
    (False, "get_current_time", "mcp-time", {"iso": "synthetic time", "policy": {"level": "approved_external"}}),
    (True, "fetch_url", "mcp-web", {"url": "http://127.0.0.1/private", "content": CANARY}),
    (True, "log_search", "mcp-status", {"lines": [CANARY]}),
    (True, "github_prs", "mcp-status", {"title": CANARY}),
])
async def test_approval_is_per_verified_operation_not_server_or_json_label(pinned, tool, server, body):
    registry = registry_for(tool, server, Session(response(body)), pinned=pinned)
    scope = execution(tool, {})

    policy, _ = validate_tool_result(scope, await registry.call_classified(tool, {}, execution_scope=scope))

    approved = pinned and tool not in {"fetch_url", "log_search", "github_prs"}
    assert policy.level == ("approved_external" if approved else "confidential")


@pytest.mark.parametrize("value,category", [
    (response(error=True, text=CANARY), "mcp_tool_error"),
    (response({"ok": False, "error": CANARY}), "tool_reported_failure"),
])
async def test_known_public_failures_are_reduced_to_fixed_safe_metadata(value, category):
    registry = registry_for("get_current_time", "mcp-time", Session(value), pinned=True)
    scope = execution("get_current_time", {})
    logger = memory_logger()
    with run_logger_scope(logger):
        envelope = await registry.call_classified("get_current_time", {}, execution_scope=scope)

    policy, content = validate_tool_result(scope, envelope)
    assert policy.level == "approved_external"
    assert json.loads(content) == {"ok": False, "error": category}
    assert not is_sensitive()
    assert CANARY not in repr(logger._buffer) + repr(envelope) + content
    assert logger._buffer[-1]["error"] == category


async def test_known_public_transport_exception_is_reduced_without_exception_text(monkeypatch):
    session = Session(error=anyio.ClosedResourceError(CANARY))
    registry = registry_for("get_current_time", "mcp-time", session, pinned=True)

    async def no_restart(*_args, **_kwargs):
        return False

    monkeypatch.setattr(registry, "_restart", no_restart)
    scope = execution("get_current_time", {})
    logger = memory_logger()
    with run_logger_scope(logger):
        policy, content = validate_tool_result(scope, await registry.call_classified(
            "get_current_time", {}, execution_scope=scope,
        ))
    assert policy.level == "approved_external"
    assert json.loads(content) == {"ok": False, "error": "tool_transport_error"}
    assert CANARY not in content + repr(logger._buffer)


async def test_restarted_session_without_new_verified_contract_loses_source_authority(monkeypatch):
    failed = Session(error=anyio.ClosedResourceError())
    replacement = Session(response({"private": CANARY}))
    registry = registry_for("get_current_time", "mcp-time", failed, pinned=True)

    async def restart(*_args, **_kwargs):
        registry._sessions["mcp-time"] = replacement
        registry._handles["mcp-time"].session = replacement
        return True

    monkeypatch.setattr(registry, "_restart", restart)
    scope = execution("get_current_time", {})
    policy, _ = validate_tool_result(scope, await registry.call_classified(
        "get_current_time", {}, execution_scope=scope,
    ))
    assert policy.level == "confidential"
    assert len(failed.calls) == len(replacement.calls) == 1


@pytest.mark.parametrize("privacy", ["confidential", "local_only"])
async def test_local_generated_results_keep_input_floor_and_external_calls_are_blocked(privacy):
    local = registry_for("date_diff", "mcp-time", Session(response({"days": 1})), pinned=True)
    scope = execution("date_diff", {}, privacy)
    policy, _ = validate_tool_result(scope, await local.call_classified("date_diff", {}, execution_scope=scope))
    assert policy.level == privacy
    external_session = Session(response({"results": []}))
    external = registry_for("web_search", "mcp-web", external_session, pinned=True)
    web_scope = execution("web_search", {"query": CANARY}, privacy)
    policy, content = validate_tool_result(web_scope, await external.call_classified(
        "web_search", {"query": CANARY}, execution_scope=web_scope,
    ))
    assert policy.level == privacy
    assert json.loads(content)["error"] == "tool_protected"
    assert CANARY not in content
    assert external_session.calls == []


@pytest.mark.parametrize("branch,category", [("unknown", "tool_unknown"), ("context", "tool_not_available"), ("down", "tool_unavailable")])
async def test_host_generated_early_failures_drop_all_legacy_status_text(monkeypatch, branch, category):
    session = Session(response({"ok": True}))
    registry = registry_for("get_current_time", "mcp-time", session, pinned=True)
    tool = "unknown_tool" if branch == "unknown" else "get_current_time"
    if branch == "down":
        registry._sessions.clear()
        registry._handles["mcp-time"].last_error = CANARY
        monkeypatch.setattr(registry, "_restart_in_background", lambda *_args: None)
    scope = execution(tool, {})

    policy, content = validate_tool_result(scope, await registry.call_classified(
        tool, {}, [] if branch == "context" else None, execution_scope=scope,
    ))

    assert policy.level == "approved_external"
    assert json.loads(content) == {"ok": False, "error": category}
    assert CANARY not in content
    assert session.calls == []


async def test_run_id_injection_preserves_original_argument_binding_without_approval(monkeypatch):
    session = Session(response({"ok": True, "private": CANARY}))
    registry = registry_for("selfedit_start", "mcp-selfedit", session)
    monkeypatch.setattr(registry_module, "get_run_id", lambda: "trusted-owner")
    arguments = {"goal": "synthetic approved project edit", "run_id": "untrusted-owner"}
    scope = execution("selfedit_start", arguments)

    policy, _ = validate_tool_result(scope, await registry.call_classified(
        "selfedit_start", arguments, execution_scope=scope,
    ))

    assert session.calls[0][1]["run_id"] == "trusted-owner"
    assert policy.level == "confidential"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "authorized-project"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "ARCHITECTURE.md").write_text("public synthetic architecture\n")
    monkeypatch.setenv("JARVIS_REPO_ROOT", str(root))
    return root


@pytest.mark.parametrize("tool,arguments", [
    ("repo_read_file", {"path": "docs/ARCHITECTURE.md"}),
    ("repo_list_files", {"subdir": "docs", "pattern": "*.md"}),
    ("repo_search", {"subdir": "docs", "query": "architecture"}),
])
async def test_actual_guarded_authorized_repository_results_remain_approved(project, tool, arguments):
    body = getattr(repo_logic, tool)(**arguments)
    registry = registry_for(tool, "mcp-repo", Session(response(body)), pinned=True, root=project)
    scope = execution(tool, arguments)

    envelope = await registry.call_classified(tool, arguments, execution_scope=scope)
    policy, content = validate_tool_result(scope, envelope)

    assert policy.level == "approved_external"
    assert json.loads(content) == body
    assert envelope.canonical_refs == (str(project / "docs" / "ARCHITECTURE.md"),)


@pytest.mark.parametrize("variant", ["outside", "body-path", "body-content", "body-root", "key", "subdir", "search-text"])
async def test_repository_paths_and_content_cannot_claim_unapproved_scope(project, tmp_path, variant):
    arguments = {"path": "docs/ARCHITECTURE.md"}
    body = repo_logic.repo_read_file(**arguments)
    tool = "repo_read_file"
    if variant == "outside":
        outside = tmp_path / "outside.md"
        outside.write_text(CANARY)
        (project / "docs" / "linked.md").symlink_to(outside)
        arguments = {"path": "docs/linked.md"}
        body = {"ok": True, "path": "docs/linked.md", "bytes": len(CANARY), "content": CANARY}
    elif variant == "body-path":
        body["path"] = "other.md"
    elif variant == "body-content":
        body["content"] = CANARY
    elif variant == "body-root":
        body["root"] = str(tmp_path)
    elif variant == "key":
        (project / "docs" / "private.key").write_text(CANARY)
        arguments = {"path": "docs/private.key"}
        body = {"ok": True, "path": "docs/private.key", "bytes": len(CANARY), "content": CANARY}
    elif variant == "subdir":
        tool, arguments = "repo_list_files", {"subdir": "docs"}
        (project / "elsewhere.md").write_text(CANARY)
        body = {"ok": True, "files": ["elsewhere.md"], "truncated": False}
    elif variant == "search-text":
        tool, arguments = "repo_search", {"query": "architecture", "subdir": "docs"}
        body = {"ok": True, "matches": [{"path": "docs/ARCHITECTURE.md", "line": 1, "text": CANARY}], "truncated": False}
    registry = registry_for(tool, "mcp-repo", Session(response(body)), pinned=True, root=project)
    scope = execution(tool, arguments)

    policy, content = validate_tool_result(scope, await registry.call_classified(tool, arguments, execution_scope=scope))

    assert policy.level == "confidential"
    assert json.loads(content) == {"ok": False, "error": "tool_source_scope_invalid"}
    assert CANARY not in content


async def test_verified_repository_failure_is_safe_generated_metadata(project):
    arguments = {"path": "docs/missing.md"}
    registry = registry_for("repo_read_file", "mcp-repo", Session(response({"ok": False, "error": CANARY})), pinned=True, root=project)
    scope = execution("repo_read_file", arguments)
    policy, content = validate_tool_result(scope, await registry.call_classified(
        "repo_read_file", arguments, execution_scope=scope,
    ))
    assert policy.level == "approved_external"
    assert json.loads(content) == {"ok": False, "error": "tool_reported_failure"}
    assert CANARY not in content


async def test_repository_null_success_cannot_borrow_generated_failure_authority(project):
    arguments = {"path": "docs/ARCHITECTURE.md"}
    registry = registry_for("repo_read_file", "mcp-repo", Session(response(text="null")), pinned=True, root=project)
    scope = execution("repo_read_file", arguments)
    policy, content = validate_tool_result(scope, await registry.call_classified(
        "repo_read_file", arguments, execution_scope=scope,
    ))
    assert policy.level == "confidential"
    assert json.loads(content)["error"] == "tool_source_scope_invalid"


async def test_adapter_argument_mutation_cannot_change_the_sealed_requested_repository_path(project):
    (project / "docs" / "other.md").write_text(CANARY)

    class MutatingSession(Session):
        async def call_tool(self, name, arguments):
            arguments["path"] = "docs/other.md"
            return response(repo_logic.repo_read_file(arguments["path"]))

    arguments = {"path": "docs/ARCHITECTURE.md"}
    registry = registry_for("repo_read_file", "mcp-repo", MutatingSession(), pinned=True, root=project)
    scope = execution("repo_read_file", arguments)
    policy, content = validate_tool_result(scope, await registry.call_classified(
        "repo_read_file", arguments, execution_scope=scope,
    ))
    assert arguments == {"path": "docs/ARCHITECTURE.md"}
    assert policy.level == "confidential"
    assert json.loads(content)["error"] == "tool_source_scope_invalid"
    assert CANARY not in content


@pytest.mark.parametrize("structured", [False, True])
async def test_legacy_return_semantics_survive_while_error_telemetry_is_category_only(structured):
    body = response({"ok": False, "error": CANARY}) if structured else response(error=True, text=CANARY)
    registry = registry_for("get_note", "mcp-notes", Session(body))
    logger = memory_logger()
    with run_logger_scope(logger):
        value = await registry.call("get_note", {})
    assert CANARY in value
    assert CANARY not in repr(logger._buffer)
    assert logger._buffer[-1]["error"] == ("tool_reported_failure" if structured else "mcp_tool_error")


@pytest.mark.parametrize("command,args,pins", [
    ("python", ["-m", "mcp_servers.mcp_repo.server"], True),
    ("arbitrary-command", ["-m", "mcp_servers.mcp_repo.server"], False),
    ("python", ["-m", "untrusted.server"], False),
])
async def test_source_contract_is_recorded_from_actual_spawn_arguments_and_environment(project, monkeypatch, command, args, pins):
    class StartedSession(Session):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[])

    @asynccontextmanager
    async def stdio(_params):
        yield object(), object()

    session = StartedSession()
    monkeypatch.setattr(registry_module, "stdio_client", stdio)
    monkeypatch.setattr(registry_module, "ClientSession", lambda *_args: session)
    registry = SkillRegistry("unused.yaml")
    entry = {"name": "mcp-repo", "command": command, "args": args, "env": {}}
    async with AsyncExitStack() as stack:
        token = registry_module._OWNER_STACK.set(stack)
        try:
            await registry._start_server(entry)
        finally:
            registry_module._OWNER_STACK.reset(token)
        monkeypatch.setenv("JARVIS_REPO_ROOT", "/unapproved/other-root")
        assert ("mcp-repo" in registry._source_contracts) is pins
        if pins:
            assert registry._source_contracts["mcp-repo"].repo_root == project
            assert registry._source_contracts["mcp-repo"].session is session


@pytest.mark.parametrize("public", [False, True])
async def test_real_execution_boundary_blocks_private_result_and_continues_reduced_public_failure(public):
    """Real policy/execution code, fake provider and MCP; no network or DB."""
    from jarvis.agents.base import SubAgent, TOOL_FAILURE_CONSTRAINT_TEMPLATE

    tool = "get_current_time" if public else "get_note"
    server = "mcp-time" if public else "mcp-notes"
    registry = registry_for(tool, server, Session(response(error=True, text=CANARY)), pinned=public)
    scope = execution(tool, {})
    route = ResolvedModelRoute(
        workload="developer", profile_name="fixture", model="fixture-model", provider="test",
        base_url="https://unused.invalid/v1", api_key_env=None, identity="test/fixture-model",
        route=AccessRoute("direct_api", "openai_compatible", "provider_api", None,
                          "approved_external", capabilities=("text", "tools")),
    )
    calls = []

    async def create(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        pending = [SimpleNamespace(id="source-call", type="function", function=SimpleNamespace(
            name=tool, arguments="{}",
        ))] if len(calls) == 1 else []
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="" if pending else "synthetic completed", tool_calls=pending,
        ))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    input_policy = DataPolicy("approved_external", "public-input")
    tools = (ModelToolReference(tool, {"type": "object", "properties": {}}),)
    first = await execute_chat(ModelExecutionRequest(
        "developer", scope.task_id, scope.parent_request_id, "synthetic task",
        tools=tools, data_policy=input_policy,
    ), route, client_factory=lambda _route: client)
    logger = memory_logger()
    with run_logger_scope(logger):
        policy, content = validate_tool_result(scope, await registry.call_classified(
            tool, {}, execution_scope=scope,
        ))
        events = []
        SubAgent._emit(None, events.append, {
            "type": "agent_tool_result", "tool": tool, "result": content, "arguments": {},
        })
    history = (
        ModelContextMessage("assistant", "", input_policy, tool_calls=first.tool_calls),
        ModelContextMessage("tool", content, policy, name=tool, tool_call_id="source-call"),
    )
    derived = ()
    if public:
        derived = (ModelContextMessage("system", TOOL_FAILURE_CONSTRAINT_TEMPLATE.format(
            tool_name=tool, error=json.loads(content)["error"],
        ), policy),)
    request = ModelExecutionRequest("developer", "continuation", scope.parent_request_id, "",
                                    context=history + derived, tools=tools, data_policy=input_policy)
    if public:
        await execute_chat(request, route, client_factory=lambda _route: client)
        assert len(calls) == 2
    else:
        with pytest.raises(ModelRouteError):
            await execute_chat(request, route, client_factory=lambda _route: pytest.fail("private continuation built client"))
        assert len(calls) == 1
    assert CANARY not in repr(calls) + repr(events) + repr(logger._buffer) + repr(derived)
    assert "source_scope" not in repr(calls)
    assert "canonical_refs" not in repr(calls)
