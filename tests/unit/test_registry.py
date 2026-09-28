"""Unit tests for jarvis/skills/registry.py — spawn-free, using fake
sessions/tools. Process-spawning coverage lives in tests/integration."""

import json
from types import SimpleNamespace

import pytest

from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.skills.registry import SkillRegistry
from jarvis.yaml_utils import DuplicateYAMLKeyError, load_unique_yaml


def test_unique_yaml_preserves_explicit_override_of_merged_defaults():
    parsed = load_unique_yaml(
        "defaults: &defaults\n"
        "  retries: 3\n"
        "  label: inherited\n"
        "job:\n"
        "  <<: *defaults\n"
        "  retries: 5\n"
    )

    assert parsed["job"] == {"retries": 5, "label": "inherited"}


def test_unique_yaml_rejects_duplicate_nested_explicit_keys():
    with pytest.raises(DuplicateYAMLKeyError):
        load_unique_yaml("settings:\n  token: first\n  token: second\n")


@pytest.mark.asyncio
async def test_registry_rejects_duplicate_config_keys_before_starting_servers(tmp_path,
                                                                              monkeypatch):
    config_path = tmp_path / "mcp_servers.yaml"
    config_path.write_text(
        "servers:\n"
        "  - name: mcp-time\n"
        "    command: python\n"
        "servers: []\n",
        encoding="utf-8",
    )
    registry = SkillRegistry(config_path)
    started = []

    async def fake_start_server(entry):
        started.append(entry)

    monkeypatch.setattr(registry, "_start_server", fake_start_server)

    with pytest.raises(DuplicateYAMLKeyError):
        await registry.start()

    assert started == []
    # Config validation happens before owner tasks or handles are created.
    assert registry._handles == {}


def make_tool(name, server, description="desc", schema=None):
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=schema or {"type": "object", "properties": {}},
    )


def make_registry() -> SkillRegistry:
    registry = SkillRegistry(config_path="unused.yaml")
    registry._tools = {
        "get_current_time": ("mcp-time", make_tool("get_current_time", "mcp-time")),
        "create_note": ("mcp-notes", make_tool("create_note", "mcp-notes")),
    }
    return registry


def make_external_registry() -> SkillRegistry:
    registry = SkillRegistry(config_path="unused.yaml")
    registry._tools = {
        "web_search": ("mcp-web", make_tool("web_search", "mcp-web")),
    }
    return registry


class TestOpenaiTools:
    def test_converts_to_function_schema(self):
        tools = make_registry().openai_tools()
        by_name = {t["function"]["name"]: t for t in tools}
        assert set(by_name) == {"get_current_time", "create_note"}
        assert by_name["get_current_time"]["type"] == "function"
        assert by_name["get_current_time"]["function"]["parameters"]["type"] == "object"

    def test_server_filter(self):
        registry = make_registry()
        tools = registry.openai_tools(["mcp-time"])
        assert [t["function"]["name"] for t in tools] == ["get_current_time"]

    def test_tools_for(self):
        registry = make_registry()
        assert registry.tools_for(["mcp-notes"]) == ["create_note"]
        assert registry.tools_for(["mcp-time", "mcp-notes"]) == [
            "get_current_time", "create_note",
        ]
        assert registry.tools_for(["mcp-system"]) == []

    def test_app_build_start_run_id_is_hidden_from_model_schema(self):
        registry = SkillRegistry(config_path="unused.yaml")
        registry._tools = {
            "app_build_start": ("mcp-apps", make_tool(
                "app_build_start", "mcp-apps", schema={
                    "type": "object",
                    "properties": {"app": {"type": "string"}, "run_id": {"type": "string"}},
                    "required": ["app", "run_id"],
                },
            )),
        }
        schema = registry.openai_tools()[0]["function"]["parameters"]
        assert "run_id" not in schema["properties"]
        assert "run_id" not in schema["required"]


class TestRegistryDiagnosticRedaction:
    def test_unreadable_skill_manifest_hides_path_and_source(self, tmp_path, monkeypatch, caplog):
        import jarvis.skills.registry as registry_module

        manifest = tmp_path / "PRIVATE_MANIFEST_PATH_CANARY" / "skill.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            "requires_env: [PRIVATE_MANIFEST_SOURCE_CANARY\n", encoding="utf-8",
        )
        monkeypatch.setattr(registry_module, "_skill_yaml_path", lambda _name: manifest)

        loaded = registry_module.load_requires_env("private-server")

        assert loaded == ([], [], [])
        assert "skill_yaml_unreadable server=private-server" in caplog.text
        assert "PRIVATE_MANIFEST_PATH_CANARY" not in caplog.text
        assert "PRIVATE_MANIFEST_SOURCE_CANARY" not in caplog.text

    def test_invalid_dynamic_source_hides_manifest_path_and_source(self, tmp_path, monkeypatch, caplog):
        import jarvis.skills.registry as registry_module

        manifest = tmp_path / "PRIVATE_DYNAMIC_PATH_CANARY" / "skill.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            "requires_env_dynamic:\n  - source: PRIVATE_DYNAMIC_SOURCE_CANARY\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("JARVIS_ENV_SCOPING_ENABLED", "true")
        monkeypatch.setattr(registry_module, "_skill_yaml_path", lambda _name: manifest)

        result = registry_module.build_child_env({"name": "private-server"})

        assert isinstance(result, dict)
        assert "mcp_requires_env_dynamic_invalid server=private-server" in caplog.text
        assert "PRIVATE_DYNAMIC_PATH_CANARY" not in caplog.text
        assert "PRIVATE_DYNAMIC_SOURCE_CANARY" not in caplog.text

    def test_unreadable_upgrade_model_manifest_hides_path_and_contents(
            self, tmp_path, monkeypatch, caplog):
        import jarvis.skills.registry as registry_module

        root = tmp_path / "PRIVATE_REPO_ROOT_CANARY"
        config = root / "config"
        config.mkdir(parents=True)
        skill = tmp_path / "skill.yaml"
        skill.write_text(
            "requires_env_dynamic:\n  - source: upgrade_models_api_keys\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("JARVIS_ENV_SCOPING_ENABLED", "true")
        monkeypatch.setattr(registry_module, "REPO_ROOT", root)
        monkeypatch.setattr(registry_module, "_skill_yaml_path", lambda _name: skill)
        import jarvis.agents.upgrade_agent as upgrade_agent

        def fail_loader():
            raise ValueError("PRIVATE_UPGRADE_SOURCE_CANARY /private/config/path")

        monkeypatch.setattr(upgrade_agent, "load_model_registry", fail_loader)
        result = registry_module.build_child_env({"name": "private-server"})

        assert isinstance(result, dict)
        assert "upgrade_models_unreadable server=private-server error_type=" in caplog.text
        assert "PRIVATE_REPO_ROOT_CANARY" not in caplog.text
        assert "PRIVATE_UPGRADE_SOURCE_CANARY" not in caplog.text


class FakeSession:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self._exc:
            raise self._exc
        return self._result


def ok_result(structured=None, text="plain text"):
    return SimpleNamespace(
        isError=False,
        structuredContent=structured,
        content=[SimpleNamespace(text=text)],
    )


class TestCall:
    async def test_unknown_tool_lists_available(self):
        result = await make_registry().call("nope", {})
        assert "Unknown tool 'nope'" in result
        assert "get_current_time" in result

    async def test_structured_content_serialized(self):
        registry = make_registry()
        session = FakeSession(result=ok_result(structured={"iso": "2026-08-04"}))
        registry._sessions = {"mcp-time": session}
        result = await registry.call("get_current_time", {})
        assert json.loads(result) == {"iso": "2026-08-04"}
        assert session.calls == [("get_current_time", {})]

    async def test_app_build_start_receives_owner_run_id(self, monkeypatch):
        import jarvis.skills.registry as registry_module

        registry = SkillRegistry(config_path="unused.yaml")
        tool = make_tool("app_build_start", "mcp-apps", schema={
            "type": "object", "properties": {"run_id": {"type": "string"}},
        })
        registry._tools = {"app_build_start": ("mcp-apps", tool)}
        session = FakeSession(result=ok_result())
        registry._sessions = {"mcp-apps": session}
        monkeypatch.setattr(registry_module, "get_run_id", lambda: "owner-run-1")
        token = current_sensitive_turn.set(SensitiveTurn())
        try:
            await registry.call("app_build_start", {"run_id": "untrusted-tool-value"})
        finally:
            current_sensitive_turn.reset(token)
        assert session.calls == [("app_build_start", {"run_id": "owner-run-1"})]

    async def test_external_tool_fails_closed_when_sensitivity_context_is_missing(self):
        registry = make_external_registry()
        session = FakeSession(result=ok_result())
        registry._sessions = {"mcp-web": session}
        token = current_sensitive_turn.set(None)
        try:
            result = await registry.call("web_search", {"query": "PRIVATE_CANARY_91"})
        finally:
            current_sensitive_turn.reset(token)
        assert "protected turn cannot call external" in result
        assert session.calls == []

    async def test_external_tool_fails_closed_for_armed_turn(self):
        registry = make_external_registry()
        session = FakeSession(result=ok_result())
        registry._sessions = {"mcp-web": session}
        holder = SensitiveTurn()
        holder.arm("financial", turn_id="canary")
        token = current_sensitive_turn.set(holder)
        try:
            result = await registry.call("web_search", {"query": "PRIVATE_CANARY_92"})
        finally:
            current_sensitive_turn.reset(token)
        assert "protected turn cannot call external" in result
        assert session.calls == []

    async def test_external_tool_allowed_only_for_explicitly_unarmed_turn(self):
        registry = make_external_registry()
        session = FakeSession(result=ok_result())
        registry._sessions = {"mcp-web": session}
        token = current_sensitive_turn.set(SensitiveTurn())
        try:
            result = await registry.call("web_search", {"query": "public query"})
        finally:
            current_sensitive_turn.reset(token)
        assert "protected turn cannot call external" not in result
        assert len(session.calls) == 1

    async def test_text_fallback_when_no_structured(self):
        registry = make_registry()
        registry._sessions = {"mcp-time": FakeSession(result=ok_result(text="hi"))}
        assert await registry.call("get_current_time", {}) == "hi"

    async def test_iserror_result_becomes_failure_string(self):
        registry = make_registry()
        result = SimpleNamespace(
            isError=True, structuredContent=None,
            content=[SimpleNamespace(text="boom")],
        )
        registry._sessions = {"mcp-time": FakeSession(result=result)}
        assert await registry.call("get_current_time", {}) == "get_current_time failed: boom"

    async def test_exception_becomes_failure_string(self):
        registry = make_registry()
        registry._sessions = {
            "mcp-time": FakeSession(exc=RuntimeError("private prompt sentinel"))
        }
        result = await registry.call("get_current_time", {})
        assert result == "get_current_time failed: RuntimeError."

    async def test_exception_message_and_run_id_are_not_written_to_logs(
            self, caplog, monkeypatch):
        import jarvis.skills.registry as registry_module

        registry = make_registry()
        registry._sessions = {
            "mcp-time": FakeSession(exc=RuntimeError("PRIVATE_CANARY_7fc19"))
        }
        monkeypatch.setattr(
            registry_module, "get_run_id", lambda: "PRIVATE_RUN_ID_CANARY")

        await registry.call("get_current_time", {})

        assert "PRIVATE_CANARY_7fc19" not in caplog.text
        assert "PRIVATE_RUN_ID_CANARY" not in caplog.text
        assert "error_type=RuntimeError" in caplog.text

    async def test_owner_task_shutdown_exception_is_redacted(self, tmp_path, monkeypatch, caplog):
        import jarvis.skills.registry as registry_module

        class FailingExit:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc_info):
                raise RuntimeError("PRIVATE_STOP_CANARY /Users/private/path")

        config_path = tmp_path / "mcp_servers.yaml"
        config_path.write_text(
            "servers:\n  - name: mcp-time\n    command: python\n",
            encoding="utf-8",
        )
        registry = SkillRegistry(config_path=config_path)

        async def start_server(_entry):
            owner_stack = registry_module._OWNER_STACK.get()
            assert owner_stack is not None
            await owner_stack.enter_async_context(FailingExit())
            return FakeSession(), []

        monkeypatch.setattr(registry, "_start_server", start_server)
        await registry.start()
        handle = registry._handles["mcp-time"]
        assert handle.state == "up"

        await registry.stop()

        assert "mcp_server_down name=mcp-time error_type=RuntimeError" in caplog.text
        assert "PRIVATE_STOP_CANARY" not in caplog.text
        assert "/Users/private/path" not in caplog.text
        assert handle.last_error == "RuntimeError"

    async def test_stop_guard_error_is_redacted(self, monkeypatch, caplog):
        import asyncio
        import jarvis.skills.registry as registry_module

        registry = SkillRegistry(config_path="unused.yaml")
        handle = registry_module._ServerHandle(
            name="mcp-time", entry={"name": "mcp-time"})

        async def wait_for_owner_stop():
            await handle.stop.wait()

        handle.task = asyncio.create_task(wait_for_owner_stop())
        registry._handles = {handle.name: handle}

        async def fail_wait(*_args, **_kwargs):
            raise RuntimeError("PRIVATE_STOP_WAIT_CANARY /private/worker/path")

        monkeypatch.setattr(registry_module.asyncio, "wait", fail_wait)
        await registry.stop()
        await handle.task

        assert "registry_stop_error error_type=RuntimeError" in caplog.text
        assert "PRIVATE_STOP_WAIT_CANARY" not in caplog.text
        assert "/private/worker/path" not in caplog.text

    async def test_server_scope_restriction(self):
        registry = make_registry()
        result = await registry.call("create_note", {}, server_names=["mcp-time"])
        assert "not available" in result

    async def test_sensitive_turn_blocks_external_mcp_server_before_invocation(self):
        from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn

        registry = make_external_registry()
        session = FakeSession(result=ok_result(structured={"results": []}))
        registry._sessions = {"mcp-web": session}
        holder = SensitiveTurn()
        holder.arm("financial")
        token = current_sensitive_turn.set(holder)
        try:
            result = await registry.call("web_search", {"query": "private"})
        finally:
            current_sensitive_turn.reset(token)

        assert "protected turn" in result
        assert session.calls == []

    async def test_timeout_becomes_failure_string(self, monkeypatch):
        registry = make_registry()

        async def slow(*a, **k):
            import asyncio
            await asyncio.sleep(60)

        session = FakeSession()
        session.call_tool = slow
        registry._sessions = {"mcp-time": session}
        monkeypatch.setattr("jarvis.skills.registry.CALL_TIMEOUT", 0.01)
        result = await registry.call("get_current_time", {})
        assert "timed out" in result
