"""Unit tests for jarvis/agents/base.py (SubAgent) — scripted FakeLLM,
deterministic, no network (plan Phase 3 Tests)."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from jarvis.agents.base import (
    STUCK_MESSAGE,
    TIMEOUT_MESSAGE,
    SubAgent,
    load_sub_agents,
)
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_execution import ModelAdmissionController
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, resolve_policy


@pytest.fixture(autouse=True)
def _initialized_non_sensitive_turn():
    # Live sessions always publish their per-turn holder before agents run.
    # Keep ordinary unit cases in that same explicit, non-sensitive state;
    # tests for an armed turn override this holder themselves.
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def make_settings():
    return SimpleNamespace(
        openai_model="test-model",
        openai_api_key="test",
        openai_base_url="http://unused",
        jarvis_timezone="America/New_York",
        # Run-logging plan §5.4: SubAgent.run() reads this to construct
        # its RunLogger. False here so these unit tests (which use tmp
        # cwd / no migrated DB) don't attempt real SQLite writes.
        jarvis_runlog_enabled=False,
        # Procedures-as-hints (memory/procedures plan D20): off by default
        # here for the same reason — no migrated DB in this file's tests.
        # See tests/unit/test_procedures.py and
        # tests/integration/test_procedures_end_to_end.py for coverage of
        # the matching/hint-injection behavior itself.
        jarvis_procedures_enabled=False,
    )


class FakeCompletions:
    def __init__(self, script):
        self._script = list(script)
        self.requests = []

    async def create(self, *, model, messages, tools=None):
        self.requests.append({"messages": messages, "tools": tools})
        action = self._script.pop(0) if self._script else self._last
        self._last = action
        if action[0] == "sleep":
            await asyncio.sleep(action[1])
            action = ("text", "late")
        if action[0] == "text":
            message = SimpleNamespace(content=action[1], tool_calls=None)
        elif action[0] == "tools":
            # Parallel tool calls in ONE assistant message (developer-fix
            # plan F1) — action is ("tools", [(name, args), ...]).
            calls = [
                SimpleNamespace(
                    id=f"call_{len(self.requests)}_{i}",
                    type="function",
                    function=SimpleNamespace(
                        name=name,
                        arguments=args if isinstance(args, str) else json.dumps(args),
                    ),
                )
                for i, (name, args) in enumerate(action[1])
            ]
            message = SimpleNamespace(content=None, tool_calls=calls)
        else:
            raw = action[2] if isinstance(action[2], str) else json.dumps(action[2])
            tool_call = SimpleNamespace(
                id=f"call_{len(self.requests)}",
                type="function",
                function=SimpleNamespace(name=action[1], arguments=raw),
            )
            message = SimpleNamespace(content=None, tool_calls=[tool_call])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    _last = ("text", "fallback")


class FakeLLM:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def openai_tools(self, server_names=None):
        return [{
            "type": "function",
            "function": {"name": "fake_tool", "description": "d",
                         "parameters": {"type": "object", "properties": {}}},
        }]

    async def call(self, name, arguments, server_names=None):
        self.calls.append((name, arguments, server_names))
        return '{"ok": true}'


def make_agent(script, registry=None, name="scheduler", settings=None, **kwargs):
    fake = FakeLLM(script)
    agent = SubAgent(
        name=name,
        display_name=name.title(),
        description="d",
        mcp_servers=["mcp-time"],
        settings=settings or make_settings(),
        registry=registry or FakeRegistry(),
        client_factory=lambda s: fake,
        **kwargs,
    )
    return agent, fake.chat.completions


class TestSubAgentLoop:
    def test_v2_package_snapshot_is_prewarmed_only_when_both_gates_are_on(
        self, monkeypatch,
    ):
        calls = []
        monkeypatch.setenv("JARVIS_SKILLS_SELECTION_V2", "1")
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
        monkeypatch.setattr(
            "jarvis.skill_selection.prewarm_runtime_package_snapshot",
            lambda: calls.append(True) or True,
        )

        make_agent([("text", "unused")])

        assert calls == [True]

        calls.clear()
        monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
        make_agent([("text", "unused")])
        assert calls == []

    async def test_v2_flag_uses_runtime_selector_without_legacy_fallback(
        self, monkeypatch,
    ):
        import jarvis.agents.base as base_module

        agent, completions = make_agent([("text", "completed")])
        monkeypatch.setattr(base_module, "skill_selection_v2_enabled", lambda: True)
        monkeypatch.setattr(
            base_module, "match_skill",
            lambda _task: pytest.fail("v2 opt-in must not silently use the legacy selector"),
        )
        monkeypatch.setattr(
            "jarvis.skill_selection.select_runtime_primary_skill",
            lambda *_args, **_kwargs: SimpleNamespace(
                selected=None, reason="revision_enforcement_disabled", candidates=(),
            ),
        )

        assert await agent.run("ordinary task") == "completed"
        assert all(
            "Reference — skill" not in str(message)
            for message in completions.requests[0]["messages"]
        )

    async def test_explicit_skill_refusal_stops_before_model_call(self, monkeypatch):
        import jarvis.agents.base as base_module

        agent, completions = make_agent([("text", "must not run")])
        monkeypatch.setattr(base_module, "skill_selection_v2_enabled", lambda: True)
        monkeypatch.setattr(base_module, "skills_workspace_enabled", lambda: True)
        monkeypatch.setattr(
            "jarvis.skill_selection.select_runtime_primary_skill",
            lambda *_args, **_kwargs: SimpleNamespace(
                selected=None, reason="readiness_unverified", candidates=(),
            ),
        )

        result = await agent.run("explicit request", explicit_skill_id="some-skill")

        assert result.startswith("REFUSED: the explicitly requested skill")
        assert completions.requests == []

    async def test_explicit_skill_selector_error_refuses_before_model_call(self, monkeypatch):
        import jarvis.agents.base as base_module

        agent, completions = make_agent([("text", "must not run")])
        monkeypatch.setattr(base_module, "skill_selection_v2_enabled", lambda: True)
        monkeypatch.setattr(base_module, "skills_workspace_enabled", lambda: True)

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("private selector diagnostic")

        monkeypatch.setattr(
            "jarvis.skill_selection.select_runtime_primary_skill", unavailable,
        )

        result = await agent.run("explicit request", explicit_skill_id="some-skill")

        assert result == (
            "REFUSED: the explicitly requested skill could not be selected safely "
            "(runtime_evidence_unavailable)."
        )
        assert completions.requests == []

    async def test_sensitive_local_tool_result_stops_external_followup_and_redacts_event(self):
        class SensitiveRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return "Account balance is $1,234.56."

        registry = SensitiveRegistry()
        agent, completions = make_agent(
            [("tool", "fake_tool", {}), ("text", "provider must not see this")],
            registry=registry,
        )
        events = []

        reply = await agent.run("read the local account record", on_event=events.append)

        assert len(completions.requests) == 1
        assert "Protected details were detected" in reply
        assert "$1,234.56" not in reply
        result_events = [event for event in events if event.get("type") == "agent_tool_result"]
        assert len(result_events) == 1
        assert "result" not in result_events[0]
        assert "arguments" not in result_events[0]

    async def test_matching_and_event_callback_errors_do_not_log_payloads(
        self, monkeypatch, caplog,
    ):
        agent, _ = make_agent([("text", "completed")])
        agent._settings.jarvis_procedures_enabled = True

        def fail_with_canary(*_args, **_kwargs):
            raise RuntimeError("PRIVATE_CANARY_match_error_4d2a")

        monkeypatch.setattr("jarvis.agents.base.match_procedure", fail_with_canary)
        monkeypatch.setattr("jarvis.agents.base.match_skill", fail_with_canary)
        monkeypatch.setattr("jarvis.agents.base.match_workflow", fail_with_canary)

        def failing_observer(_event):
            raise RuntimeError("PRIVATE_CANARY_observer_error_4d2a")

        result = await agent.run("PRIVATE_CANARY_task_4d2a", on_event=failing_observer)

        assert result == "completed"
        for canary in (
            "PRIVATE_CANARY_match_error_4d2a",
            "PRIVATE_CANARY_observer_error_4d2a",
            "PRIVATE_CANARY_task_4d2a",
        ):
            assert canary not in caplog.text
        assert "error_type=RuntimeError" in caplog.text

    async def test_skill_and_workflow_injection_logs_omit_local_labels(
        self, monkeypatch, caplog, tmp_path,
    ):
        agent, _ = make_agent([("text", "completed")])
        skill_name = "PRIVATE_SKILL_LABEL_CANARY_18f2"
        workflow_name = "PRIVATE_WORKFLOW_LABEL_CANARY_18f2"
        workflow_source = "/private/PRIVATE_WORKFLOW_SOURCE_CANARY_18f2.yaml"
        from jarvis.agent_skills import Skill

        skill_path = tmp_path / "skill" / "SKILL.md"
        skill = Skill(
            name=skill_name, description="private test skill card", path=skill_path,
            _body="safe skill instructions",
        )

        monkeypatch.setattr(
            "jarvis.agents.base.match_skill",
            lambda _task: skill,
        )
        monkeypatch.setattr(
            "jarvis.agent_skills.parse_skill",
            lambda _path: (skill, []),
        )
        monkeypatch.setattr(
            "jarvis.skill_catalog.inspect_package",
            lambda _directory, **_kwargs: SimpleNamespace(
                enabled=True, revision="a" * 64, reference_paths=(),
            ),
        )
        monkeypatch.setattr(
            "jarvis.agents.base.match_workflow",
            lambda _agent, _task: SimpleNamespace(
                name=workflow_name,
                source=workflow_source,
                as_prompt=lambda: "safe workflow instructions",
            ),
        )

        with caplog.at_level("INFO", logger="jarvis.agents.base"):
            result = await agent.run("ordinary task")

        assert result == "completed"
        assert "skill_injected agent=scheduler" in caplog.text
        assert "workflow_injected agent=scheduler" in caplog.text
        for canary in (skill_name, workflow_name, workflow_source):
            assert canary not in caplog.text

    async def test_subagent_rechecks_v2_revision_pin_before_injection(self, monkeypatch, tmp_path):
        from jarvis.agent_skills import Skill

        skill_path = tmp_path / "skill-package" / "SKILL.md"
        skill_path.parent.mkdir()
        skill_path.write_text("DO_NOT_INJECT_STALE_SKILL", encoding="utf-8")
        skill = Skill(
            name="pinned-skill", description="A pinned test skill",
            path=skill_path, _body="DO_NOT_INJECT_STALE_SKILL",
        )
        monkeypatch.setattr("jarvis.agents.base.match_skill", lambda _task: skill)
        monkeypatch.setattr("jarvis.agents.base.skills_workspace_enabled", lambda: True)
        monkeypatch.setattr(
            "jarvis.agents.base.skill_revision_pins",
            lambda: {"pinned-skill": "0" * 64},
        )
        monkeypatch.setattr(
            "jarvis.skill_catalog.inspect_package",
            lambda *_args, **_kwargs: SimpleNamespace(
                enabled=True, revision="a" * 64, reference_paths=(),
            ),
        )
        agent, completions = make_agent([("text", "completed")])

        assert await agent.run("use pinned-skill") == "completed"
        assert all(
            "DO_NOT_INJECT_STALE_SKILL" not in str(message)
            for message in completions.requests[0]["messages"]
        )

    async def test_selected_skill_snapshot_refuses_body_changed_after_matching(
        self, monkeypatch, tmp_path,
    ):
        import jarvis.agents.base as base_module
        import jarvis.skill_catalog as catalog_module
        from jarvis.agent_skills import parse_skill

        package = tmp_path / "skills" / "snapshot-skill"
        package.mkdir(parents=True)
        skill_path = package / "SKILL.md"
        frontmatter = (
            "---\nname: snapshot-skill\ndescription: A stable snapshot test\n---\n"
        )
        skill_path.write_text(frontmatter + "OLD_SNAPSHOT_BODY_CANARY\n", encoding="utf-8")
        config_path = tmp_path / "skills.yaml"
        config_path.write_text("enabled: [snapshot-skill]\n", encoding="utf-8")
        monkeypatch.setattr(base_module, "SKILLS_CONFIG", config_path)
        monkeypatch.setattr(catalog_module, "SKILLS_CONFIG", config_path)
        monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
        stale_skill, problems = parse_skill(skill_path)
        assert stale_skill is not None and not problems

        def select_then_edit(_task):
            # Simulate a package update after matching has cached SKILL.md but
            # before _loop validates the selected package for injection.
            skill_path.write_text(frontmatter + "NEW_SNAPSHOT_BODY_CANARY\n", encoding="utf-8")
            return stale_skill

        monkeypatch.setattr(base_module, "match_skill", select_then_edit)
        agent, completions = make_agent([("text", "completed")])

        assert await agent.run("use the snapshot skill") == "completed"
        injected = "\n".join(str(message) for message in completions.requests[0]["messages"])
        assert "OLD_SNAPSHOT_BODY_CANARY" not in injected
        assert "NEW_SNAPSHOT_BODY_CANARY" not in injected

    async def test_selected_skill_writes_revision_bound_activity(self, monkeypatch, tmp_path):
        import jarvis.agents.base as base_module
        from jarvis.agent_skills import Skill
        from jarvis.db import get_conn, run_migrations
        from jarvis.runlog.store import RunLogger, get_skill_events
        monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)

        db_path = tmp_path / "skill-trace.db"
        conn = get_conn(db_path)
        run_migrations(conn)
        conn.close()
        package = tmp_path / "skills" / "demo-skill"
        package.mkdir(parents=True)
        skill_file = package / "SKILL.md"
        skill_file.write_text(
            "---\nname: demo-skill\ndescription: A test skill for trace coverage\n---\n"
            "Use the test procedure.\n",
            encoding="utf-8",
        )
        (package / "mortimer.yaml").write_text(
            "schema_version: 1\n"
            "skill_id: demo-skill\n"
            "display_name: Demo skill\n"
            "category: development\n"
            "version: 1.0.0\n"
            "source: {kind: local, reference: test}\n"
            "capabilities: []\n"
            "required_tools: []\n"
            "required_credentials: []\n"
            "reference_paths: []\n"
            "example_ids: []\n"
            "related_workflow_ids: []\n"
            "compatible_with: []\n"
            "process:\n"
            "  kind: linear\n"
            "  nodes:\n"
            "    - step_id: call-tool\n"
            "      title: Call the tool\n"
            "      description: Use the declared test tool.\n"
            "      tools: [fake_tool]\n"
            "      success_criteria: [The tool result is checked.]\n"
            "      edges: []\n",
            encoding="utf-8",
        )
        skill_config = tmp_path / "skills.yaml"
        skill_config.write_text("enabled: [demo-skill]\n", encoding="utf-8")
        monkeypatch.setattr("jarvis.skill_catalog.SKILLS_CONFIG", skill_config)
        monkeypatch.setattr(base_module, "SKILLS_CONFIG", skill_config)
        skill = Skill(
            name="demo-skill", description="A test skill for trace coverage",
            path=skill_file,
        )

        class IsolatedRunLogger(RunLogger):
            def __init__(self, *args, **kwargs):
                kwargs.update(enabled=True, db_path=db_path, root=tmp_path)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(base_module, "RunLogger", IsolatedRunLogger)
        monkeypatch.setattr(base_module, "match_skill", lambda _task: skill)
        agent, _ = make_agent([
            ("tool", "fake_tool", {}), ("text", "completed"),
        ])
        reply = await agent.run("use the demo", run_id="request-demo-1")

        assert reply == "completed"
        trace = get_skill_events("request-demo-1", db_path=db_path)
        assert [event["type"] for event in trace["events"]] == [
            "skill_selected", "skill_step_started", "skill_step_finished",
        ]
        assert {event["skill_id"] for event in trace["events"]} == {"demo-skill"}
        assert len({event["skill_revision"] for event in trace["events"]}) == 1
        step_events = trace["events"][1:]
        assert [event["status"] for event in step_events] == ["running", "unknown"]
        assert {event["step_id"] for event in step_events} == {"call-tool"}
        assert all(
            event["evidence_refs"][0]["kind"] == "tool_call_id"
            for event in step_events
        )
        assert step_events[0]["attempt_id"]
        assert step_events[0]["attempt_id"] == step_events[1]["attempt_id"]
        assert all(
            event["attempt_id"] == event["evidence_refs"][0]["id"]
            for event in step_events
        )

        class FailedToolRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return '{"ok": false, "error": "synthetic failure"}'

        failed_agent, _ = make_agent(
            [("tool", "fake_tool", {}), ("text", "completed")],
            registry=FailedToolRegistry(),
        )
        await failed_agent.run("use the demo", run_id="request-demo-failure")
        failed_trace = get_skill_events(
            "request-demo-failure", db_path=db_path,
        )
        assert [event["status"] for event in failed_trace["events"]] == [
            "unknown", "running", "failed",
        ]
        assert failed_trace["events"][1]["attempt_id"] == failed_trace["events"][2]["attempt_id"]

    async def test_weather_tool_result_records_host_verified_process_step(
        self, monkeypatch, tmp_path,
    ):
        """Only the host-checked structured result can pass this pinned step."""
        import jarvis.agents.base as base_module
        from jarvis.agent_skills import SKILLS_DIR, parse_skill
        from jarvis.db import get_conn, run_migrations
        from jarvis.runlog.store import RunLogger, get_skill_events

        db_path = tmp_path / "weather-verified-step.db"
        conn = get_conn(db_path)
        run_migrations(conn)
        conn.close()

        weather_path = SKILLS_DIR / "current-weather-with-fahrenheit" / "SKILL.md"
        weather_skill, problems = parse_skill(weather_path)
        assert weather_skill is not None and not problems
        monkeypatch.setattr(base_module, "match_skill", lambda _task: weather_skill)

        class WeatherRegistry(FakeRegistry):
            def openai_tools(self, server_names=None):
                return [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get current weather and short forecast.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                                "days": {"type": "integer"},
                            },
                            "required": ["city"],
                        },
                    },
                }]

            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return json.dumps({
                    "city": "Camp Croft",
                    "requested_city": "Camp Croft",
                    "source": "open-meteo",
                    "units": "imperial",
                    "human": "Clear, 72 F; high 78 F, low 61 F.",
                    "current": {
                        "condition": "clear",
                        "temperature_f": 72.0,
                        "temperature_c": 22.2,
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    "daily": [{
                        "date": "2026-09-28",
                        "max_f": 78.0,
                        "min_f": 61.0,
                        "max_c": 25.6,
                        "min_c": 16.1,
                    }],
                })

        class IsolatedRunLogger(RunLogger):
            def __init__(self, *args, **kwargs):
                kwargs.update(enabled=True, db_path=db_path, root=tmp_path)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(base_module, "RunLogger", IsolatedRunLogger)
        settings = make_settings()
        settings.jarvis_runlog_enabled = True
        agent, _ = make_agent(
            [("tool", "get_weather", {"city": "Camp Croft", "days": 1}),
             ("text", "The forecast is clear.")],
            registry=WeatherRegistry(),
            settings=settings,
        )

        reply = await agent.run("Check the weather in Camp Croft", run_id="weather-run")

        assert reply == "The forecast is clear."
        trace = get_skill_events("weather-run", db_path=db_path)
        assert trace is not None
        events = trace["events"]
        assert [event["type"] for event in events] == [
            "skill_selected", "skill_step_started", "skill_step_finished",
        ]
        assert [(event["skill_id"], event["skill_revision"], event["step_id"])
                for event in events[1:]] == [
            ("current-weather-with-fahrenheit",
             "9064f3d61d680d8cbce9c4dda1b2d98b854624fce2b106f89cc7f13b4ace521e",
             "retrieve-conditions"),
            ("current-weather-with-fahrenheit",
             "9064f3d61d680d8cbce9c4dda1b2d98b854624fce2b106f89cc7f13b4ace521e",
             "retrieve-conditions"),
        ]
        started, finished = events[1:]
        assert started["status"] == "running"
        assert finished["status"] == "passed"
        assert started["attempt_id"] == finished["attempt_id"]
        assert finished["evidence_refs"] == [{
            "kind": "check_receipt_id",
            "id": finished["evidence_refs"][0]["id"],
        }]
        serialized = json.dumps(trace)
        assert "Camp Croft" not in serialized
        assert "72.0" not in serialized

    async def test_declared_reference_reaches_model_but_not_logs_or_activity(
        self, monkeypatch, tmp_path, caplog,
    ):
        import jarvis.agents.base as base_module
        from jarvis.agent_skills import Skill
        from jarvis.db import get_conn, run_migrations
        from jarvis.runlog.store import RunLogger, get_run, get_skill_events
        from jarvis.skill_catalog import _package_digest

        db_path = tmp_path / "reference-trace.db"
        conn = get_conn(db_path)
        run_migrations(conn)
        conn.close()
        package = tmp_path / "skills" / "reference-demo"
        reference_dir = package / "references"
        reference_dir.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            "---\nname: reference-demo\ndescription: A test skill for references\n---\n"
            "Use the reference only when useful.\n",
            encoding="utf-8",
        )
        (reference_dir / "guide.md").write_text(
            "REFERENCE_BODY_CANARY_d0bd", encoding="utf-8",
        )
        (package / "mortimer.yaml").write_text(
            "schema_version: 1\n"
            "skill_id: reference-demo\n"
            "display_name: Reference demo\n"
            "category: development\n"
            "version: 1.0.0\n"
            "source: {kind: local, reference: test}\n"
            "capabilities: []\n"
            "required_tools: []\n"
            "required_credentials: []\n"
            "reference_paths: [references/guide.md]\n"
            "example_ids: []\n"
            "related_workflow_ids: []\n"
            "compatible_with: []\n"
            "process: null\n",
            encoding="utf-8",
        )
        skill_config = tmp_path / "skills.yaml"
        digest = _package_digest(package)
        skill_config.write_text(
            "schema_version: 2\n"
            "enabled: [reference-demo]\n"
            f"revisions: {{reference-demo: {digest}}}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(base_module, "SKILLS_CONFIG", skill_config)
        monkeypatch.setattr("jarvis.skill_resources.SKILLS_CONFIG", skill_config)
        monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")

        class IsolatedRunLogger(RunLogger):
            def __init__(self, *args, **kwargs):
                kwargs.update(enabled=True, db_path=db_path, root=tmp_path)
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(base_module, "RunLogger", IsolatedRunLogger)
        monkeypatch.setattr(
            base_module, "match_skill",
            lambda _task: Skill(
                name="reference-demo", description="A test skill for references",
                path=package / "SKILL.md",
            ),
        )
        monkeypatch.setattr(base_module, "skill_revision_pins", lambda: {"reference-demo": digest})
        agent, completions = make_agent([
            ("tool", "skill_reference_read", {"reference_path": "references/guide.md"}),
            ("text", "Reference checked."),
        ])
        emitted = []

        reply = await agent.run(
            "use the reference", run_id="request-reference-1", on_event=emitted.append,
        )

        assert reply == "Reference checked."
        assert len(completions.requests) == 2
        assert any(
            "skill_reference_read" == tool["function"]["name"]
            for tool in completions.requests[0]["tools"]
        )
        tool_message = next(
            message for message in completions.requests[1]["messages"]
            if message.get("role") == "tool"
        )
        assert "REFERENCE_BODY_CANARY_d0bd" in tool_message["content"]
        assert all("REFERENCE_BODY_CANARY_d0bd" not in str(event) for event in emitted)

        trace = get_skill_events("request-reference-1", db_path=db_path)
        assert [event["type"] for event in trace["events"]] == [
            "skill_selected", "skill_resource_read",
        ]
        run_record = get_run(
            "request-reference-1", db_path=db_path, root=tmp_path,
        )
        serialized = json.dumps(run_record, default=str)
        assert "REFERENCE_BODY_CANARY_d0bd" not in serialized
        assert "REFERENCE_BODY_CANARY_d0bd" not in caplog.text

        # Failure to persist the activity receipt must not turn a successful
        # reference read into a failed tool call or interrupt the agent run.
        original_skill_event = IsolatedRunLogger.skill_event

        def fail_resource_trace(self, skill_id, revision, event_type, **kwargs):
            if event_type == "skill_resource_read":
                raise OSError("synthetic activity store outage")
            return original_skill_event(self, skill_id, revision, event_type, **kwargs)

        monkeypatch.setattr(IsolatedRunLogger, "skill_event", fail_resource_trace)
        outage_agent, outage_completions = make_agent([
            ("tool", "skill_reference_read", {"reference_path": "references/guide.md"}),
            ("text", "Reference remains available."),
        ])
        outage_reply = await outage_agent.run(
            "use the reference while activity storage is unavailable",
            run_id="request-reference-trace-outage",
        )
        assert outage_reply == "Reference remains available."
        outage_tool_message = next(
            message for message in outage_completions.requests[1]["messages"]
            if message.get("role") == "tool"
        )
        assert "REFERENCE_BODY_CANARY_d0bd" in outage_tool_message["content"]
        outage_trace = get_skill_events(
            "request-reference-trace-outage", db_path=db_path,
        )
        assert [event["type"] for event in outage_trace["events"]] == [
            "skill_selected",
        ]

    async def test_mutually_compatible_support_skill_is_injected_and_can_read_own_reference(
        self, monkeypatch, tmp_path,
    ):
        import jarvis.agents.base as base_module
        import jarvis.skill_resources as resources_module
        from jarvis.agent_skills import Skill
        from jarvis.skill_catalog import _package_digest

        skills_root = tmp_path / "skills"
        primary_dir = skills_root / "primary-skill"
        support_dir = skills_root / "support-skill"
        (primary_dir / "SKILL.md").parent.mkdir(parents=True)
        (support_dir / "references").mkdir(parents=True)
        primary_file = primary_dir / "SKILL.md"
        support_file = support_dir / "SKILL.md"
        primary_file.write_text(
            "---\nname: primary-skill\ndescription: Primary test procedure\n---\n"
            "PRIMARY_SKILL_BODY\n", encoding="utf-8",
        )
        support_file.write_text(
            "---\nname: support-skill\ndescription: Supporting test reference\n---\n"
            "SUPPORT_SKILL_BODY\n", encoding="utf-8",
        )
        (support_dir / "references" / "guide.md").write_text(
            "SUPPORT_REFERENCE_CONTENT", encoding="utf-8",
        )
        common = (
            "schema_version: 1\ncategory: development\nversion: 1.0.0\n"
            "source: {kind: local, reference: test}\ncapabilities: []\n"
            "required_tools: []\nrequired_credentials: []\n"
            "example_ids: []\nrelated_workflow_ids: []\nprocess: null\n"
        )
        (primary_dir / "mortimer.yaml").write_text(
            "skill_id: primary-skill\ndisplay_name: Primary skill\n"
            "reference_paths: []\ncompatible_with: [support-skill]\n" + common,
            encoding="utf-8",
        )
        (support_dir / "mortimer.yaml").write_text(
            "skill_id: support-skill\ndisplay_name: Support skill\n"
            "reference_paths: [references/guide.md]\n"
            "compatible_with: [primary-skill]\n" + common,
            encoding="utf-8",
        )
        from jarvis.skill_catalog import inspect_package

        revisions = {
            "primary-skill": _package_digest(primary_dir),
            "support-skill": _package_digest(support_dir),
        }
        config = tmp_path / "skills.yaml"
        config.write_text(
            "schema_version: 2\nenabled: [primary-skill, support-skill]\n"
            f"revisions: {revisions}\n", encoding="utf-8",
        )
        # Validate the temporary package definitions before routing them.
        assert inspect_package(primary_dir, config_path=config).revision == revisions["primary-skill"]
        assert inspect_package(support_dir, config_path=config).revision == revisions["support-skill"]
        monkeypatch.setattr(base_module, "SKILLS_CONFIG", config)
        monkeypatch.setattr(resources_module, "SKILLS_CONFIG", config)
        monkeypatch.setattr(base_module, "skills_workspace_enabled", lambda: True)
        monkeypatch.setattr(base_module, "skill_selection_v2_enabled", lambda: True)
        monkeypatch.setattr(base_module, "skill_revision_pins", lambda: revisions)
        monkeypatch.setattr(
            "jarvis.skill_selection.select_runtime_primary_skill",
            lambda *_args, **_kwargs: SimpleNamespace(
                selected=Skill(
                    "primary-skill", "Primary test procedure", primary_file,
                    _body="PRIMARY_SKILL_BODY",
                ),
                supporting=Skill(
                    "support-skill", "Supporting test reference", support_file,
                    _body="SUPPORT_SKILL_BODY",
                ),
                reason="automatic_match", candidates=(),
            ),
        )
        agent, completions = make_agent([
            ("tool", "skill_reference_read", {
                "skill_id": "support-skill",
                "reference_path": "references/guide.md",
            }),
            ("text", "support reference used"),
        ])

        result = await agent.run("use compatible skills")

        assert result == "support reference used"
        first_request = completions.requests[0]
        system_text = "\n".join(
            message["content"] for message in first_request["messages"]
            if message.get("role") == "system"
        )
        assert "PRIMARY_SKILL_BODY" in system_text
        assert "SUPPORT_SKILL_BODY" in system_text
        reference_tool = next(
            tool for tool in first_request["tools"]
            if tool["function"]["name"] == "skill_reference_read"
        )
        assert "skill_id" in reference_tool["function"]["parameters"]["properties"]
        reference_message = next(
            message for message in completions.requests[1]["messages"]
            if message.get("role") == "tool"
        )
        assert "SUPPORT_REFERENCE_CONTENT" in reference_message["content"]

        refused_agent, refused_completions = make_agent([
            ("tool", "skill_reference_read", {
                "skill_id": "unselected-skill",
                "reference_path": "references/guide.md",
            }),
            ("text", "unselected reference refused"),
        ])
        refused_result = await refused_agent.run("try another skill reference")
        assert refused_result.startswith("FAILED:")
        assert "skill_not_selected_for_run" in refused_result
        refused_message = next(
            message for message in refused_completions.requests[1]["messages"]
            if message.get("role") == "tool"
        )
        assert "skill_not_selected_for_run" in refused_message["content"]
        assert "SUPPORT_REFERENCE_CONTENT" not in refused_message["content"]

    async def test_override_refusal_log_omits_profile_and_reason(
        self, monkeypatch, caplog,
    ):
        agent, completions = make_agent([("text", "must not run")])
        profile = "PRIVATE_PROFILE_CANARY_23c1"
        reason = "PRIVATE_ROUTE_REASON_CANARY_23c1"
        monkeypatch.setattr(
            agent, "_resolve_model_profile_details",
            lambda _profile: (None, None, reason, None),
        )

        with caplog.at_level("WARNING", logger="jarvis.agents.base"):
            result = await agent.run(
                "ordinary task", model_profile_override=profile,
            )

        assert result == f"REFUSED: {reason}"
        assert completions.requests == []
        assert "subagent_override_refused agent=scheduler" in caplog.text
        assert profile not in caplog.text
        assert reason not in caplog.text

    async def test_plain_text_reply(self):
        agent, _ = make_agent([("text", "It is 3 PM.")])
        assert await agent.run("what time") == "It is 3 PM."

    async def test_tool_call_executes_scoped_to_own_servers(self):
        registry = FakeRegistry()
        agent, completions = make_agent(
            [("tool", "get_time", {}), ("text", "It is 3 PM.")],
            registry=registry,
        )
        reply = await agent.run("what time")
        assert reply == "It is 3 PM."
        assert registry.calls == [("get_time", {}, ["mcp-time"])]
        assert completions.requests[0]["tools"][0]["function"]["name"] == "fake_tool"

    async def test_routed_tool_loop_uses_shared_execution_and_preserves_history(
        self, monkeypatch,
    ):
        class TimeRegistry(FakeRegistry):
            def openai_tools(self, server_names=None):
                return [{
                    "type": "function",
                    "function": {
                        "name": "get_time", "description": "Get local time",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }]

        registry = TimeRegistry()
        agent, completions = make_agent(
            [("tool", "get_time", {}), ("text", "It is 3 PM.")],
            registry=registry,
        )
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="test", model="model",
            provider="saygm", base_url="https://gateway.example/v1/",
            route=AccessRoute(
                "saygm", "saygm_gateway", "saygm_credit", None, "confidential",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="saygm/model", priority="interactive",
        )
        recorded = []
        monkeypatch.setattr(
            "jarvis.agents.base.record_execution_result",
            lambda *args, **kwargs: recorded.append((args, kwargs)),
        )
        monkeypatch.setattr(
            "jarvis.model_execution._PROCESS_ADMISSION", ModelAdmissionController()
        )
        local_results = []

        def local_sink(run_id, opaque_ref, body, data_policy):
            # A Future is awaitable but is not recognized by
            # asyncio.iscoroutine; the private delivery contract must await
            # it before the specialist returns a status to its caller.
            loop = asyncio.get_running_loop()
            delivered = loop.create_future()

            async def finish_delivery():
                await asyncio.sleep(0)
                local_results.append((run_id, opaque_ref, body, data_policy))
                delivered.set_result(True)

            loop.create_task(finish_delivery())
            return delivered

        reply = await agent.run("what time", private_result_sink=local_sink)
        assert "It is 3 PM." not in reply
        assert "Reference:" in reply
        assert local_results[0][2] == "It is 3 PM."
        assert registry.calls == [("get_time", {}, ["mcp-time"])]
        assert recorded and recorded[0][0][0] == "scheduler"
        assert completions.requests[0]["tools"][0]["function"]["name"] == "get_time"
        next_turn = completions.requests[1]["messages"]
        assert next_turn[-2]["role"] == "assistant"
        assert next_turn[-2]["tool_calls"][0]["function"]["name"] == "get_time"
        assert next_turn[-1] == {
            "role": "tool", "tool_call_id": "call_1", "name": "get_time",
            "content": '{"ok": true}',
        }

    async def test_sensitive_turn_cannot_use_approved_external_routed_agent(self):
        agent, completions = make_agent([("text", "private answer")])
        agent._settings.jarvis_model_routing_enabled = True
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="external", model="model",
            provider="openai", base_url="https://api.example/v1/",
            route=AccessRoute(
                "direct_api", "openai_compatible", "provider_api", "OPENAI_API_KEY",
                "approved_external", capabilities=("text", "tools"),
            ),
            api_key_env="OPENAI_API_KEY", identity="openai/model", priority="interactive",
        )
        holder = SensitiveTurn()
        holder.arm("financial", "turn-1")
        token = current_sensitive_turn.set(holder)
        try:
            result = await agent.run("summarize my private financial records")
        finally:
            current_sensitive_turn.reset(token)

        assert result.startswith("FAILED:")
        assert completions.requests == []

    async def test_sensitive_turn_without_verified_local_route_fails_closed(self):
        agent, completions = make_agent([("text", "private answer")])
        holder = SensitiveTurn()
        holder.arm("financial", "turn-local-only")
        token = current_sensitive_turn.set(holder)
        try:
            result = await agent.run("summarize protected records")
        finally:
            current_sensitive_turn.reset(token)
        assert result.startswith("FAILED: no verified local route")
        assert completions.requests == []

    async def test_confidential_workload_fails_closed_when_routing_is_disabled(self):
        agent, completions = make_agent([("text", "private answer")], name="librarian")
        result = await agent.run("summarize private record")
        assert result.startswith("FAILED: no verified local route")
        assert completions.requests == []

    async def test_confidential_result_is_delivered_locally_and_redacted_to_supervisor(self):
        agent, _ = make_agent([("text", "TOP SECRET RESULT")])
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "confidential",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )
        delivered = []

        async def sink(run_id, opaque_ref, body, data_policy):
            await asyncio.sleep(0)
            delivered.append((run_id, opaque_ref, body, data_policy))
            return True

        reply = await agent.run("inspect protected data", run_id="parent-run",
                                private_result_sink=sink)
        assert len(delivered) == 1
        assert delivered[0][0] == "parent-run"
        assert delivered[0][2] == "TOP SECRET RESULT"
        assert delivered[0][3] == "confidential"
        assert delivered[0][1]
        assert "TOP SECRET RESULT" not in reply
        assert "Reference:" in reply

    async def test_private_route_without_local_sink_does_not_call_provider(self):
        agent, completions = make_agent([("text", "TOP SECRET RESULT")])
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "local_only",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )

        result = await agent.run("inspect protected data")

        assert result.startswith("The protected result could not be delivered")
        assert "TOP SECRET RESULT" not in result
        assert completions.requests == []

    async def test_private_route_without_sink_does_not_construct_provider_client(
        self, monkeypatch,
    ):
        monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
        monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")
        monkeypatch.setenv("JARVIS_MODEL_ROUTE_SCHEDULER", "local")
        constructed = []
        monkeypatch.setattr(
            "jarvis.agents.base.make_route_client",
            lambda route: constructed.append(route) or object(),
        )
        settings = make_settings()
        settings.jarvis_model_routing_enabled = True
        agent = SubAgent(
            name="scheduler", display_name="Scheduler", description="d",
            mcp_servers=[], settings=settings, registry=FakeRegistry(),
            model_profile="claude-sonnet-5",
        )
        assert constructed == []

        result = await agent.run("inspect protected data")

        assert result.startswith("The protected result could not be delivered")
        assert constructed == []

    async def test_user_route_preference_cannot_lower_workload_privacy_floor(
        self, monkeypatch,
    ):
        monkeypatch.setattr(
            "jarvis.model_preferences.list_preferences",
            lambda **_kwargs: [{
                "workload": "librarian", "profile": "external",
                "route": "direct_api", "privacy": "approved_external",
            }],
        )
        assert resolve_policy("librarian").privacy == "approved_external"
        assert resolve_policy("librarian", include_preferences=False).privacy == "confidential"

        agent, completions = make_agent(
            [("text", "TOP SECRET RESULT")], name="librarian",
        )
        agent._settings.jarvis_model_routing_enabled = True
        agent._resolved_route = ResolvedModelRoute(
            workload="librarian", profile_name="external", model="external-model",
            provider="openai", base_url="https://provider.invalid/v1/",
            route=AccessRoute(
                "direct_api", "openai_compatible", "provider_api", "OPENAI_API_KEY",
                "approved_external", capabilities=("text", "tools"),
            ),
            api_key_env="OPENAI_API_KEY", identity="openai/external-model",
            priority="interactive",
        )
        # Simulate an in-process preference/config refresh that would report
        # the weaker route label after the agent captured its workload floor.
        monkeypatch.setattr(
            "jarvis.agents.base.resolve_policy",
            lambda *_args, **_kwargs: SimpleNamespace(privacy="approved_external"),
        )

        result = await agent.run("inspect protected records")

        assert result.startswith("FAILED: no verified local route")
        assert completions.requests == []

    async def test_confidential_result_sink_failure_never_returns_content(self):
        agent, _ = make_agent([("text", "TOP SECRET RESULT")])
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "local_only",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )

        async def failed_sink(*_args):
            raise RuntimeError("transport detail with secret TOP SECRET RESULT")

        reply = await agent.run("inspect protected data", private_result_sink=failed_sink)
        assert "TOP SECRET RESULT" not in reply
        assert reply.startswith("The protected result could not be delivered")

    async def test_confidential_tool_output_is_removed_from_activity_events(self, monkeypatch):
        class ProtectedRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                return '{"record":"TOOL SECRET"}'

        agent, _ = make_agent(
            [("tool", "fake_tool", {"query": "PRIVATE QUERY"}),
             ("text", "FINAL SECRET")],
            registry=ProtectedRegistry(),
        )
        agent._resolved_route = ResolvedModelRoute(
            workload="scheduler", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "confidential",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )
        monkeypatch.setattr("jarvis.agents.base.record_execution_result",
                            lambda *args, **kwargs: None)
        monkeypatch.setattr("jarvis.model_execution._PROCESS_ADMISSION",
                            ModelAdmissionController())
        events = []

        async def sink(*_args):
            return True

        await agent.run("inspect protected record", on_event=events.append,
                        private_result_sink=sink)
        result_event = next(event for event in events
                            if event["type"] == "agent_tool_result")
        assert "result" not in result_event
        assert "arguments" not in result_event
        assert "PRIVATE QUERY" not in repr(events)
        assert "TOOL SECRET" not in repr(events)
        assert "FINAL SECRET" not in repr(events)

    async def test_iteration_cap_says_it_ran_out_of_rounds(self):
        """B (Larry 2026-08-18): exhausting the iteration budget is NOT the
        same failure as "could not be completed". Two real runs whose tool
        calls ALL succeeded returned the generic message, and the
        Supervisor narrated it to the user as "the codebase access is
        blocked" — an invention. The reply must carry the real reason."""
        agent, _ = make_agent([("tool", "fake_tool", {})])
        reply = await agent.run("loop forever")
        assert "ran out of tool-call rounds" in reply
        assert "Nothing was blocked" in reply
        assert reply != STUCK_MESSAGE

    async def test_max_iterations_is_configurable_per_agent(self):
        """A: config/agents.yaml's max_iterations, same shape as timeout_s."""
        agent, completions = make_agent(
            [("tool", "fake_tool", {})], max_iterations=2)
        await agent.run("loop forever")
        assert len(completions.requests) == 2

    async def test_a_real_reply_is_never_clobbered_by_the_exhaustion_message(self):
        """The override only replaces the untouched default."""
        agent, _ = make_agent([("tool", "fake_tool", {}), ("text", "here it is")])
        assert await agent.run("task") == "here it is"

    async def test_timeout_returns_failed_message(self):
        agent, _ = make_agent([("sleep", 5.0)], timeout_s=0.05)
        assert await agent.run("slow task") == TIMEOUT_MESSAGE

    async def test_provider_that_swallows_cancellation_cannot_start_tool_round(
        self, monkeypatch,
    ):
        class SwallowingProvider:
            def __init__(self):
                self.started = asyncio.Event()
                self.requests = 0

            async def create(self, **_kwargs):
                self.requests += 1
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                        content=None,
                        tool_calls=[SimpleNamespace(
                            id="late-call",
                            function=SimpleNamespace(
                                name="fake_tool", arguments="{}",
                            ),
                        )],
                    ))])

        provider = SwallowingProvider()
        registry = FakeRegistry()
        agent, _ = make_agent([("text", "unused")], registry=registry)
        recorded_completions = []
        monkeypatch.setattr(
            "jarvis.agents.base.record_completion",
            lambda *args, **kwargs: recorded_completions.append((args, kwargs)),
        )
        agent._client = SimpleNamespace(
            chat=SimpleNamespace(completions=provider),
        )
        events = []
        task = asyncio.create_task(agent.run("cancel provider", on_event=events.append))
        await asyncio.wait_for(provider.started.wait(), timeout=1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert provider.requests == 1
        assert registry.calls == []
        assert recorded_completions == []
        assert not any(event.get("type") == "agent_tool_result" for event in events)

    async def test_tool_that_swallows_cancellation_cannot_publish_or_continue(
        self, monkeypatch,
    ):
        class SwallowingRegistry(FakeRegistry):
            def __init__(self):
                super().__init__()
                self.started = asyncio.Event()

            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                self.started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    return '{"ok": true, "result": "late"}'

        registry = SwallowingRegistry()
        recorded_tool_results = []
        unknown_outcomes = []
        monkeypatch.setattr(
            "jarvis.agents.base.RunLogger.tool_result",
            lambda *args, **kwargs: recorded_tool_results.append((args, kwargs)),
        )
        monkeypatch.setattr(
            "jarvis.agents.base.RunLogger.tool_outcome_unknown",
            lambda *args, **kwargs: unknown_outcomes.append((args, kwargs)),
        )
        agent, completions = make_agent(
            [("tool", "fake_tool", {}), ("text", "must not run")],
            registry=registry,
        )
        events = []
        task = asyncio.create_task(agent.run("cancel tool", on_event=events.append))
        await asyncio.wait_for(registry.started.wait(), timeout=1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert len(completions.requests) == 1
        assert len(registry.calls) == 1
        assert recorded_tool_results == []
        assert len(unknown_outcomes) == 1
        args, kwargs = unknown_outcomes[0]
        assert args[0].__class__.__name__ == "RunLogger"
        assert args[1:] == ("fake_tool", "call_1")
        assert kwargs == {"reason_code": "cancelled_after_return"}
        assert not any(event.get("type") == "agent_tool_result" for event in events)

    async def test_direct_mode_does_not_execute_replayed_tool_call_identity(self):
        class ReplayingProvider:
            def __init__(self):
                self.requests = []

            async def create(self, **kwargs):
                self.requests.append(kwargs)
                call = SimpleNamespace(
                    id="same-provider-call-id",
                    type="function",
                    function=SimpleNamespace(name="fake_tool", arguments="{}"),
                )
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                    content=None, tool_calls=[call],
                ))])

        provider = ReplayingProvider()
        registry = FakeRegistry()
        agent, _ = make_agent([("text", "unused")], registry=registry)
        agent._client = SimpleNamespace(
            chat=SimpleNamespace(completions=provider),
        )

        reply = await agent.run("repeat tool call")

        assert reply.startswith("FAILED: the provider repeated")
        assert len(provider.requests) == 2
        assert len(registry.calls) == 1

    async def test_events_emitted_in_order(self):
        agent, _ = make_agent(
            [("tool", "fake_tool", {"q": 1}), ("text", "done")])
        events = []
        await agent.run("task", on_event=events.append)
        assert [e["type"] for e in events] == [
            "agent_start", "agent_tool", "agent_tool_result", "agent_done"]
        assert events[0]["task"] == "task"
        assert events[1]["tool"] == "fake_tool"
        assert events[2]["tool"] == "fake_tool"
        assert events[2]["arguments"] == {"q": 1}
        assert events[2]["result"] == '{"ok": true}'

    async def test_tool_result_event_truncates_long_results(self):
        class LongRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                return "x" * 50_000

        agent, _ = make_agent(
            [("tool", "fake_tool", {}), ("text", "done")],
            registry=LongRegistry(),
        )
        events = []
        await agent.run("task", on_event=events.append)
        result_event = next(e for e in events if e["type"] == "agent_tool_result")
        assert len(result_event["result"]) == 20_000

    async def test_client_exception_returns_content_free_reason_code(self, caplog):
        class Boom:
            async def create(self, **kwargs):
                raise RuntimeError("provider echoed PRIVATE REQUEST CONTENT")

        agent, _ = make_agent([("text", "unused")])
        agent._client = SimpleNamespace(
            chat=SimpleNamespace(completions=Boom()))
        reply = await agent.run("task")
        assert reply.startswith("FAILED:")
        assert "PRIVATE REQUEST CONTENT" not in reply
        assert "PRIVATE REQUEST CONTENT" not in caplog.text
        assert "RuntimeError" in reply

    async def test_system_prompt_from_appendix_a(self):
        agent, completions = make_agent([("text", "ok")], name="librarian")
        agent._resolved_route = ResolvedModelRoute(
            workload="librarian", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "confidential",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )
        await agent.run("hi", private_result_sink=lambda *_args: True)
        system = completions.requests[0]["messages"][0]["content"]
        assert system.startswith("You are the Librarian")
        assert "America/New_York" not in system  # librarian prompt has no tz


class TestToolFailureHandling:
    """MORTIMER_AGENT_TRUST_PLAN.md D1-D5 — the fabrication defect and its
    fix: a failed tool call must never be indistinguishable from data."""

    async def test_body_failure_injects_constraint_message(self):
        # Two tool calls, first fails and second succeeds — a PARTIAL
        # failure, so D4's all-failed override does not fire and D3's
        # constraint-injection behavior can be observed in isolation on the
        # next LLM request.
        calls = iter([
            '{"ok": false, "error": "HTTP 401: Bad credentials"}',
            '{"ok": true, "data": "fine"}',
        ])

        class MixedRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return next(calls)

        registry = MixedRegistry()
        agent, completions = make_agent(
            [("tool", "fake_tool", {}), ("tool", "fake_tool", {}),
             ("text", "reported the failure")],
            registry=registry,
        )
        reply = await agent.run("read a file")
        assert reply == "reported the failure"
        # Second LLM request (after the first, failed tool call) must carry
        # the D3 constraint as its own system message, immediately after
        # the tool's own role:"tool" message.
        second_request_messages = completions.requests[1]["messages"]
        tool_msg_idx = next(
            i for i, m in enumerate(second_request_messages) if m["role"] == "tool"
        )
        constraint = second_request_messages[tool_msg_idx + 1]
        assert constraint["role"] == "system"
        assert "FAILED" in constraint["content"]
        assert "fake_tool" in constraint["content"]
        assert "MUST NOT" in constraint["content"]
        assert "401" in constraint["content"]

    async def test_success_does_not_inject_constraint_message(self):
        agent, completions = make_agent(
            [("tool", "fake_tool", {}), ("text", "done")],
        )
        await agent.run("task")
        second_request_messages = completions.requests[1]["messages"]
        assert not any(
            "MUST NOT" in (m.get("content") or "") for m in second_request_messages
        )

    async def test_all_tools_failed_overrides_reply(self):
        class FailingRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return '{"ok": false, "error": "boom"}'

        agent, _ = make_agent(
            # Confident-sounding reply the model would otherwise return —
            # D4 must override this, not just log a warning alongside it.
            [("tool", "fake_tool", {}),
             ("text", "Here is a detailed and entirely fabricated answer.")],
            registry=FailingRegistry(),
        )
        reply = await agent.run("read a file")
        assert reply.startswith("FAILED: every tool call in this run failed (1/1)")
        assert "boom" in reply

    async def test_partial_failure_does_not_override_reply(self):
        """D4 is scoped to ALL calls failing, never ANY — one working call
        among several failures must NOT trip the override."""
        calls = iter([
            '{"ok": false, "error": "first failed"}',
            '{"ok": true, "data": "second worked"}',
        ])

        class MixedRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return next(calls)

        agent, _ = make_agent(
            [("tool", "fake_tool", {}), ("tool", "fake_tool", {}),
             ("text", "partial answer")],
            registry=MixedRegistry(),
        )
        reply = await agent.run("task")
        assert reply == "partial answer"

    async def test_transport_failure_string_still_classified_failed(self):
        """Registry-level failures (the three TRANSPORT_FAILURE_PREFIXES
        shapes) must still trip D3/D4 — not just JSON body failures."""
        class TransportFailRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return "fake_tool failed: timed out after 30s."

        agent, _ = make_agent(
            [("tool", "fake_tool", {}), ("text", "unused")],
            registry=TransportFailRegistry(),
        )
        reply = await agent.run("task")
        assert reply.startswith("FAILED: every tool call in this run failed (1/1)")
        assert "timed out" in reply


class TestProcedureHintInjection:
    """D11/D17/D20 — the single enforcement point for the procedures kill
    switch lives here, in _loop, not inside match_procedure itself (see
    jarvis/procedures.py's match_procedure docstring)."""

    async def test_disabled_flag_never_calls_match_or_injects_hint(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "jarvis.agents.base.match_procedure",
            lambda *a, **kw: called.append(1) or None,
        )
        settings = make_settings()  # jarvis_procedures_enabled=False by default
        assert settings.jarvis_procedures_enabled is False
        agent, completions = make_agent([("text", "ok")])
        await agent.run("do the thing")
        assert called == []  # match_procedure never called at all
        messages = completions.requests[0]["messages"]
        assert not any("succeeded before" in m.get("content", "") for m in messages)

    async def test_enabled_flag_injects_matched_hint_as_own_system_message(
        self, monkeypatch,
    ):
        settings = make_settings()
        settings.jarvis_procedures_enabled = True
        procedure = {"id": 7, "description": "used get_time for the resolved zone"}
        monkeypatch.setattr(
            "jarvis.agents.base.match_procedure", lambda *a, **kw: procedure,
        )
        monkeypatch.setattr("jarvis.agents.base.mark_used", lambda *a, **kw: None)
        agent, completions = make_agent([("text", "ok")], settings=settings)

        await agent.run("what time is it")

        messages = completions.requests[0]["messages"]
        assert messages[0]["role"] == "system"  # agent's own prompt, untouched
        assert messages[1] == {
            "role": "system",
            "content": "A similar task has succeeded before: "
                       "used get_time for the resolved zone",
        }
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "what time is it"

    async def test_no_match_no_hint_ordinary_two_message_shape(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "hint.db"))
        from jarvis.db import run_migrations

        run_migrations()
        settings = make_settings()
        settings.jarvis_procedures_enabled = True
        agent, completions = make_agent([("text", "ok")], settings=settings)
        # No procedures exist for this agent/db — match_procedure (real,
        # unmocked) returns None; the request must look exactly as it did
        # before this feature existed.
        await agent.run("do the thing")
        messages = completions.requests[0]["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "do the thing"}


class TestLoadSubAgents:
    def test_loads_roster_from_repo_yaml(self):
        agents = load_sub_agents(make_settings(), FakeRegistry(),
                                 client_factory=lambda s: FakeLLM([]))
        assert set(agents) == {"scheduler", "librarian", "analyst", "systems",
                               "developer", "app_builder"}
        # Larry 2026-08-21: every agent carries mcp-screen now.
        assert agents["scheduler"].mcp_servers == [
            "mcp-time", "mcp-reminders", "mcp-screen"]
        assert agents["analyst"].display_name == "Analyst"

    def test_per_agent_timeout_from_yaml(self):
        # MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F3, raised to 300s by
        # MORTIMER_PLANNING_PATHWAY_PLAN.md P1: developer gets its
        # configured 300s; agents without a timeout_s key keep the default.
        from jarvis.agents.base import DEFAULT_TIMEOUT_S

        agents = load_sub_agents(make_settings(), FakeRegistry(),
                                 client_factory=lambda s: FakeLLM([]))
        assert agents["developer"]._timeout_s == 300.0
        assert agents["scheduler"]._timeout_s == DEFAULT_TIMEOUT_S


class FailByNameRegistry(FakeRegistry):
    """Registry whose call() fails for tool names in `failing`."""

    def __init__(self, failing):
        super().__init__()
        self.failing = set(failing)

    async def call(self, name, arguments, server_names=None):
        self.calls.append((name, arguments, server_names))
        if name in self.failing:
            return '{"ok": false, "error": "boom"}'
        return '{"ok": true}'


class TestParallelToolCallProtocol:
    """MORTIMER_DEVELOPER_AGENT_FIX_PLAN.md F1: on a turn with parallel
    tool calls, the D3 constraint must land AFTER the whole tool-response
    block — an interleaved system message orphans the remaining
    tool_call_ids and the next completion call 400s (observed live on
    two Developer runs with 21 parallel repo reads)."""

    def _messages_of_last_request(self, completions):
        return completions.requests[-1]["messages"]

    async def test_mixed_batch_constraint_after_contiguous_tool_block(self):
        registry = FailByNameRegistry({"bad_tool"})
        agent, completions = make_agent(
            [
                ("tools", [("good_tool", {}), ("bad_tool", {}), ("good_tool", {})]),
                ("text", "done"),
            ],
            registry=registry,
        )
        await agent.run("do things")

        messages = self._messages_of_last_request(completions)
        # Find the assistant tool_calls message and verify every one of
        # its tool_call_ids is answered by a CONTIGUOUS run of tool
        # messages, with the system constraint only after the block.
        idx = next(
            i for i, m in enumerate(messages)
            if (m.get("role") if isinstance(m, dict) else None) == "assistant"
            and (m.get("tool_calls") if isinstance(m, dict) else None)
        )
        call_ids = {tc["id"] for tc in messages[idx]["tool_calls"]}
        block = messages[idx + 1 : idx + 1 + len(call_ids)]
        assert [m["role"] for m in block] == ["tool"] * len(call_ids)
        assert {m["tool_call_id"] for m in block} == call_ids
        after = messages[idx + 1 + len(call_ids)]
        assert after["role"] == "system"
        assert "bad_tool" in after["content"]
        # No system message inside the tool block.
        assert all(m["role"] != "system" for m in block)

    async def test_multi_failure_batch_names_every_failed_tool(self):
        registry = FailByNameRegistry({"bad_one", "bad_two"})
        agent, completions = make_agent(
            [
                ("tools", [("bad_one", {}), ("bad_two", {})]),
                ("text", "done"),
            ],
            registry=registry,
        )
        await agent.run("do things")

        messages = self._messages_of_last_request(completions)
        # messages[0] is the agent's own system prompt, whose D6 grounding
        # language also contains "FAILED" — skip it.
        system_msgs = [
            m for m in messages[1:]
            if isinstance(m, dict) and m.get("role") == "system"
            and "FAILED" in str(m.get("content", ""))
        ]
        assert len(system_msgs) == 1  # ONE batch constraint, not one per failure
        content = system_msgs[0]["content"]
        assert "bad_one" in content and "bad_two" in content
        assert "MUST NOT" in content

    async def test_single_failure_keeps_original_template(self):
        registry = FailByNameRegistry({"bad_tool"})
        agent, completions = make_agent(
            [("tool", "bad_tool", {}), ("text", "done")],
            registry=registry,
        )
        await agent.run("do things")

        messages = self._messages_of_last_request(completions)
        # messages[0] is the agent's own system prompt, whose D6 grounding
        # language also contains "FAILED" — skip it.
        system_msgs = [
            m for m in messages[1:]
            if isinstance(m, dict) and m.get("role") == "system"
            and "FAILED" in str(m.get("content", ""))
        ]
        assert len(system_msgs) == 1
        assert "`bad_tool` FAILED" in system_msgs[0]["content"]


class PendingDraftRegistry(FakeRegistry):
    """Registry whose call() returns a `{"ok": true, "pending": true}`
    draft result for tool names in `pending`, and executes (plain ok) for
    everything else."""

    def __init__(self, pending):
        super().__init__()
        self.pending = set(pending)

    async def call(self, name, arguments, server_names=None):
        self.calls.append((name, arguments, server_names))
        if name in self.pending:
            return '{"ok": true, "pending": true, "action_id": 1}'
        return '{"ok": true}'


class TestPendingDraftHandling:
    """MORTIMER_PLANNING_PATHWAY_PLAN.md P2 — the phantom-completion fix:
    a `pending: true` tool result is a DRAFT, not a completed action."""

    async def test_pending_draft_injects_constraint_message(self):
        registry = PendingDraftRegistry({"repo_write_file"})
        agent, completions = make_agent(
            [("tool", "repo_write_file", {}), ("text", "I wrote the file")],
            registry=registry,
        )
        await agent.run("write a spec and commit it")

        second_request_messages = completions.requests[1]["messages"]
        tool_msg_idx = next(
            i for i, m in enumerate(second_request_messages) if m["role"] == "tool"
        )
        constraint = second_request_messages[tool_msg_idx + 1]
        assert constraint["role"] == "system"
        assert "DRAFTS" in constraint["content"]
        assert "pending: true" in constraint["content"]
        assert "NOTHING has been written" in constraint["content"]

    async def test_non_pending_success_does_not_inject_draft_constraint(self):
        agent, completions = make_agent(
            [("tool", "fake_tool", {}), ("text", "done")],
        )
        await agent.run("task")
        second_request_messages = completions.requests[1]["messages"]
        assert not any(
            "DRAFTS" in (m.get("content") or "") for m in second_request_messages
        )

    async def test_backstop_appends_when_draft_never_executed(self):
        registry = PendingDraftRegistry({"repo_write_file"})
        agent, _ = make_agent(
            [("tool", "repo_write_file", {}),
             ("text", "I've written and committed the spec.")],
            registry=registry,
        )
        reply = await agent.run("write a spec and commit it")
        assert reply.startswith("I've written and committed the spec.")
        assert "[1 draft(s) are awaiting your confirmation" in reply
        assert "nothing has been written yet.]" in reply

    async def test_backstop_silent_when_draft_executed(self):
        registry = PendingDraftRegistry({"repo_write_file"})
        agent, _ = make_agent(
            [("tool", "repo_write_file", {}),
             ("tool", "repo_commit_write", {}),
             ("text", "Drafted and committed.")],
            registry=registry,
        )
        reply = await agent.run("write a spec and commit it")
        assert reply == "Drafted and committed."
        assert "draft(s) are awaiting" not in reply

    async def test_backstop_net_counts_multiple_drafts(self):
        class TwoDraftsRegistry(PendingDraftRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                if name == "repo_write_file":
                    return '{"ok": true, "pending": true, "action_id": 1}'
                if name == "repo_commit_write":
                    return '{"ok": true}'
                return '{"ok": true}'

        registry = TwoDraftsRegistry({"repo_write_file"})
        agent, _ = make_agent(
            [
                ("tools", [("repo_write_file", {}), ("repo_write_file", {})]),
                ("tool", "repo_commit_write", {}),
                ("text", "done"),
            ],
            registry=registry,
        )
        reply = await agent.run("write two specs and commit one")
        assert "[1 draft(s) are awaiting your confirmation" in reply

    async def test_backstop_appends_even_when_all_tools_failed(self):
        """The pending-draft count is independent of classify_tool_result's
        ok/fail judgement (P2's accounting reads the `pending` flag on its
        own) — the backstop still amends a D4-overridden reply rather than
        being silently dropped by it."""
        class FailedDraftRegistry(FakeRegistry):
            async def call(self, name, arguments, server_names=None):
                self.calls.append((name, arguments, server_names))
                return '{"ok": false, "pending": true, "error": "boom"}'

        agent, _ = make_agent(
            [("tool", "repo_write_file", {}), ("text", "unused")],
            registry=FailedDraftRegistry(),
        )
        reply = await agent.run("write a spec")
        assert reply.startswith("FAILED: every tool call in this run failed")
        assert "[1 draft(s) are awaiting your confirmation" in reply


# MORTIMER_MODEL_DISCIPLINE_AND_MAC_SHELL_PLAN.md A1 — per-agent model
# profiles. These tests deliberately do NOT pass client_factory (that seam
# always wins and skips profile resolution entirely — the tests above cover
# that path already); they exercise real profile resolution against a
# temp registry file.
class TestModelProfile:
    def _registry_file(self, tmp_path, monkeypatch, key_present=True):
        import yaml
        p = tmp_path / "upgrade_models.yaml"
        p.write_text(yaml.safe_dump({
            "default": "kimi-k2",
            "profiles": [
                {"name": "kimi-k2", "label": "Kimi K2", "provider": "moonshot",
                 "model": "kimi-k2.7-code", "base_url": "https://api.moonshot.ai/v1",
                 "api_key_env": "MOONSHOT_API_KEY"},
            ],
        }))
        monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
        if key_present:
            monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
        else:
            monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
        return p

    def test_resolved_profile_used_as_model(self, tmp_path, monkeypatch):
        self._registry_file(tmp_path, monkeypatch)
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), model_profile="kimi-k2",
        )
        assert agent._model == "kimi-k2.7-code"
        assert agent._client.api_key == "test-key"
        assert str(agent._client.base_url) == "https://api.moonshot.ai/v1/"  # noqa: SLF001
        # Larry 2026-08-19 — the public pair the Agents tab card reads.
        assert agent.model == "kimi-k2.7-code"
        assert agent.model_is_fallback is False

    def test_unknown_profile_falls_back_with_warning(self, tmp_path, monkeypatch, caplog):
        self._registry_file(tmp_path, monkeypatch)
        settings = make_settings()
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=settings,
            registry=FakeRegistry(), model_profile="does-not-exist",
        )
        assert agent._model == settings.openai_model  # fell back
        assert "subagent_model_profile_fallback" in caplog.text
        # The card must show the model actually in use AND mark it as a
        # fallback — otherwise a silent misconfiguration reads on screen
        # as a deliberate assignment.
        assert agent.model == settings.openai_model
        assert agent.model_is_fallback is True

    def test_missing_api_key_falls_back_with_warning(self, tmp_path, monkeypatch, caplog):
        self._registry_file(tmp_path, monkeypatch, key_present=False)
        settings = make_settings()
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=settings,
            registry=FakeRegistry(), model_profile="kimi-k2",
        )
        assert agent._model == settings.openai_model
        assert "subagent_model_profile_fallback" in caplog.text

    def test_no_profile_uses_settings_client(self):
        settings = make_settings()
        agent = SubAgent(
            name="scheduler", display_name="Scheduler", description="d",
            mcp_servers=["mcp-time"], settings=settings, registry=FakeRegistry(),
        )
        assert agent._model == settings.openai_model

    def test_client_factory_skips_profile_resolution_entirely(self, tmp_path, monkeypatch):
        """The test seam always wins — even a bogus profile name must not
        raise or attempt resolution when client_factory is supplied."""
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
            model_profile="totally-bogus-profile-name",
        )
        assert agent._client is fake


class TestRuntimeModelOverride:
    """F6/F7/F8 (MORTIMER_GATE_V2_AND_MODEL_REQUEST_PLAN.md, 2026-08-22)
    — a per-run NAMED model request via run(model_profile_override=...),
    independent of this agent's own configured `model_profile:`."""

    def _registry_file(self, tmp_path, monkeypatch, key_present=True):
        import yaml
        p = tmp_path / "upgrade_models.yaml"
        p.write_text(yaml.safe_dump({
            "default": "kimi-k2",
            "profiles": [
                {"name": "fable", "label": "Fable", "provider": "anthropic",
                 "model": "claude-fable-5",
                 "base_url": "https://api.anthropic.com/v1/",
                 "api_key_env": "ANTHROPIC_API_KEY"},
            ],
        }))
        monkeypatch.setenv("JARVIS_UPGRADE_MODELS", str(p))
        if key_present:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        else:
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        return p

    def _agent_with_fake_override_client(self, tmp_path, monkeypatch, script):
        """Builds an agent whose DEFAULT client is the normal FakeLLM test
        seam (client_factory), while the client resolve_model_profile's
        override path builds is faked out so an override run never
        touches the real network.

        Phase 1 (MORTIMER_OPTIMIZATION_PLAN.md, Rev 3.2, landing step
        (ii), 2026-09-02): the override path now goes through
        jarvis.llm_client.make_async_client, which — for this fixture's
        "fable" profile (provider: anthropic) — builds a real
        AsyncAnthropicChatShim when native routing is on. That's exactly
        right in production (it's the whole point of this landing step),
        but it means this fixture's FakeAsyncOpenAI is reached only with
        native routing forced OFF; see
        test_override_builds_native_shim_when_anthropic_native_enabled
        below for the native-on case, which asserts the shim type
        directly instead of faking the transport. `openai.AsyncOpenAI` is
        patched (module attribute, looked up at call time inside
        llm_client.py) rather than `base_module.AsyncOpenAI`, which no
        longer exists — base.py imports llm_client now, not AsyncOpenAI
        directly.
        """
        self._registry_file(tmp_path, monkeypatch)
        monkeypatch.setenv("JARVIS_ANTHROPIC_NATIVE", "0")
        import openai

        default_fake = FakeLLM([("text", "default reply")])
        constructed: dict = {}

        class FakeAsyncOpenAI:
            def __init__(self, api_key, base_url):
                constructed["api_key"] = api_key
                constructed["base_url"] = base_url
                self.chat = SimpleNamespace(completions=FakeCompletions(script))

        monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)

        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: default_fake,
        )
        return agent, default_fake, constructed

    async def test_override_resolves_and_runs_on_named_model(self, tmp_path, monkeypatch):
        agent, _default, constructed = self._agent_with_fake_override_client(
            tmp_path, monkeypatch, [("text", "override reply")],
        )
        reply = await agent.run("research radar", model_profile_override="fable")
        assert reply == "override reply"
        assert constructed["api_key"] == "test-key"
        assert constructed["base_url"] == "https://api.anthropic.com/v1/"

    async def test_override_builds_native_shim_when_anthropic_native_enabled(
        self, tmp_path, monkeypatch
    ) -> None:
        """Phase 1 (Rev 3.2, landing step (ii)) mirror of the test above:
        with JARVIS_ANTHROPIC_NATIVE left at its default (unset — on), the
        SAME "fable" (provider: anthropic) override profile must resolve
        to the real prompt-caching shim, not the OpenAI-compat client.
        No network call is made — constructing AsyncAnthropicChatShim
        never touches the network, only .create() would."""
        self._registry_file(tmp_path, monkeypatch)
        monkeypatch.delenv("JARVIS_ANTHROPIC_NATIVE", raising=False)
        from jarvis.anthropic_shim import AsyncAnthropicChatShim

        default_fake = FakeLLM([("text", "default reply")])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: default_fake,
        )
        client, model, refused_reason = agent.resolve_model_profile("fable")
        assert refused_reason == ""
        assert model == "claude-fable-5"
        assert isinstance(client, AsyncAnthropicChatShim)

    async def test_override_failure_refuses_never_falls_back(self, tmp_path, monkeypatch):
        self._registry_file(tmp_path, monkeypatch, key_present=False)
        agent, completions = make_agent([("text", "should never run")], name="developer")
        reply = await agent.run("research radar", model_profile_override="fable")
        assert reply.startswith("REFUSED:")
        assert "fable" in reply
        # Named the agent's own (unaffected) default too — F7's rationale.
        assert make_settings().openai_model in reply
        assert completions.requests == []  # no model call attempted

    async def test_override_unknown_profile_refuses(self, tmp_path, monkeypatch):
        self._registry_file(tmp_path, monkeypatch)
        agent, completions = make_agent([("text", "should never run")], name="developer")
        reply = await agent.run(
            "research radar", model_profile_override="totally-bogus-profile"
        )
        assert reply.startswith("REFUSED:")
        assert completions.requests == []

    async def test_override_ignores_this_agents_on_profile_fallback_warn(
        self, tmp_path, monkeypatch,
    ):
        """F7: an override ALWAYS refuses on failure, even for an agent
        configured on_profile_fallback='warn' (the conversational-agent
        default) — the configured mode governs the agent's OWN default
        profile, never a per-run user instruction."""
        self._registry_file(tmp_path, monkeypatch, key_present=False)
        agent, completions = make_agent(
            [("text", "should never run")], name="scheduler",
            on_profile_fallback="warn",
        )
        reply = await agent.run("research radar", model_profile_override="fable")
        assert reply.startswith("REFUSED:")
        assert completions.requests == []

    async def test_override_does_not_mutate_instance(self, tmp_path, monkeypatch):
        agent, default_fake, _constructed = self._agent_with_fake_override_client(
            tmp_path, monkeypatch, [("text", "override reply")],
        )
        before_client = agent._client  # noqa: SLF001
        before_model = agent._model  # noqa: SLF001

        await agent.run("research radar", model_profile_override="fable")

        assert agent._client is before_client  # noqa: SLF001
        assert agent._model == before_model  # noqa: SLF001
        # A subsequent DEFAULT run (no override) still uses the default
        # client — the override never leaked into instance state.
        reply2 = await agent.run("what time is it")
        assert reply2 == "default reply"

    async def test_run_log_records_override_model(self, tmp_path, monkeypatch):
        """F8: RunLogger gets the OVERRIDE-resolved model, never
        self._model — verified via the model kwarg construction-time
        capture rather than a real DB write (jarvis_runlog_enabled=False
        in make_settings())."""
        agent, _default, _constructed = self._agent_with_fake_override_client(
            tmp_path, monkeypatch, [("text", "override reply")],
        )
        captured_models = []
        import jarvis.agents.base as base_module

        real_runlogger = base_module.RunLogger

        class CapturingRunLogger(real_runlogger):
            def __init__(self, *args, **kwargs):
                captured_models.append(kwargs.get("model"))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(base_module, "RunLogger", CapturingRunLogger)

        await agent.run("research radar", model_profile_override="fable")
        assert captured_models == ["claude-fable-5"]

    async def test_enabled_confidential_workload_redacts_run_log(self, monkeypatch):
        """MAR-D: route privacy applies even when the turn is unlabeled."""
        settings = make_settings()
        settings.jarvis_model_routing_enabled = True
        agent = SubAgent(
            name="librarian", display_name="Librarian", description="d",
            mcp_servers=[], settings=settings, registry=FakeRegistry(),
            client_factory=lambda _settings: FakeLLM([("text", "private result")]),
        )
        agent._resolved_route = ResolvedModelRoute(
            workload="librarian", profile_name="local", model="local-model",
            provider="local", base_url="http://local.invalid/v1/",
            route=AccessRoute(
                "local", "openai_compatible", "none", None, "confidential",
                capabilities=("text", "tools"),
            ),
            api_key_env=None, identity="local/local-model", priority="interactive",
        )
        captured = []
        import jarvis.agents.base as base_module

        real_runlogger = base_module.RunLogger

        class CapturingRunLogger(real_runlogger):
            def __init__(self, *args, **kwargs):
                captured.append(kwargs.get("sensitive"))
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(base_module, "RunLogger", CapturingRunLogger)
        await agent.run(
            "summarize the private record",
            private_result_sink=lambda *_args: True,
        )
        assert captured == [True]


# A3 — repo map injection.
class TestRepoMapInjection:
    def test_injected_when_flag_set(self, tmp_path, monkeypatch):
        # G5: path resolution now lives in jarvis.repo_map (shared with
        # UpgradeAgent), so the fixture repo root is pointed at via THAT
        # module's __file__, not base_module's.
        import jarvis.repo_map as repo_map_module
        repo_root = tmp_path
        (repo_root / "docs").mkdir()
        (repo_root / "docs" / "REPO_MAP.md").write_text("## Test map\n- foo lives in bar\n")
        monkeypatch.setattr(repo_map_module, "__file__", str(repo_root / "jarvis" / "repo_map.py"))
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
            inject_repo_map=True,
        )
        assert "Test map" in agent._system_prompt
        assert "foo lives in bar" in agent._system_prompt

    def test_skipped_silently_when_missing(self, tmp_path, monkeypatch):
        import jarvis.repo_map as repo_map_module
        monkeypatch.setattr(repo_map_module, "__file__", str(tmp_path / "jarvis" / "repo_map.py"))
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
            inject_repo_map=True,
        )
        assert "Repository map" not in agent._system_prompt

    def test_not_injected_when_flag_unset(self):
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
        )
        assert "Repository map" not in agent._system_prompt

    def test_truncated_at_cap(self, tmp_path, monkeypatch):
        import jarvis.agents.base as base_module
        import jarvis.repo_map as repo_map_module
        repo_root = tmp_path
        (repo_root / "docs").mkdir()
        big = "x" * (base_module.REPO_MAP_MAX_CHARS + 500)
        (repo_root / "docs" / "REPO_MAP.md").write_text(big)
        monkeypatch.setattr(repo_map_module, "__file__", str(repo_root / "jarvis" / "repo_map.py"))
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
            inject_repo_map=True,
        )
        injected = agent._system_prompt.split("verify with tools before writing):\n")[1]
        assert len(injected) == base_module.REPO_MAP_MAX_CHARS


class TestRefuseMode:
    """MORTIMER_KEY_VALIDITY_PLAN.md K5. Verified 2026-08-19:
    `on_profile_fallback` was read by scripts/check_env.py — which warns
    that a refuse-mode agent with no key "refuses every delegation" — and by
    NOTHING in jarvis/. The preflight was reassuring the reader about a
    guarantee that did not exist; the agent fell back to the voice model
    exactly as if the setting were absent. A check that reports on
    unimplemented behaviour is worse than no check."""

    def _agent(self, tmp_path, monkeypatch, mode, profile="does-not-exist"):
        reg = TestModelProfile()._registry_file(tmp_path, monkeypatch)
        return SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), model_profile=profile,
            on_profile_fallback=mode,
        ), reg

    async def test_refuse_mode_refuses_instead_of_running_on_the_fallback(
            self, tmp_path, monkeypatch, caplog):
        agent, _ = self._agent(tmp_path, monkeypatch, "refuse")
        assert agent.refuses
        caplog.clear()
        result = await agent.run("implement the plan")
        assert result.startswith("REFUSED:")
        # The reason must be stated, not merely signalled: Golden Rule 1 and
        # rule 11 both require a cause the Supervisor can relay, and a bare
        # "REFUSED:" is how the model ends up inventing one.
        assert "could not be resolved" in result
        assert "does-not-exist" in result
        assert "subagent_refused agent=developer" in caplog.text
        assert "does-not-exist" not in caplog.text
        # Review finding 8 (L1): the user is never handed a terminal command.
        assert "scripts/" not in result and "python " not in result
        assert "status tools" in result

    async def test_warn_mode_still_falls_back_silently(
            self, tmp_path, monkeypatch):
        """The default must not change: voice has to boot on a fresh
        checkout with one key."""
        agent, _ = self._agent(tmp_path, monkeypatch, "warn")
        assert agent.refuses == ""
        assert agent.model_is_fallback is True

    async def test_a_resolved_profile_never_refuses(self, tmp_path, monkeypatch):
        agent, _ = self._agent(tmp_path, monkeypatch, "refuse", profile="kimi-k2")
        assert agent.refuses == ""
        assert agent.model_is_fallback is False


def test_librarian_budget_is_ten():
    """T1.4 (2026-09-22): the 09-18 memory-graph run needed 13 tool calls
    against the default 5 and ran out."""
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[2]
    agents = yaml.safe_load((root / "config" / "agents.yaml").read_text())["sub_agents"]
    librarian = next(a for a in agents if a["name"] == "librarian")
    assert librarian["max_iterations"] == 10


class TestClock:
    """Phase 2 D5 (MORTIMER_VOICE_WORKFLOWS_PLAN.md): live-data agents get
    the date, time and timezone on every run."""

    def test_clock_note_names_date_time_and_zone(self):
        from datetime import datetime, timezone

        from jarvis.agents.base import clock_note

        note = clock_note("America/New_York", datetime(2026, 9, 25, 1, 40, tzinfo=timezone.utc))
        assert note.startswith("Now: Thursday, 24 September 2026, 9:40 PM EDT (America/New_York).")
        assert '"tonight" mean this date' in note

    def test_bad_timezone_falls_back_to_utc(self):
        from datetime import datetime, timezone

        from jarvis.agents.base import clock_note

        assert "(UTC)" in clock_note("Not/AZone", datetime(2026, 9, 5, 13, 5, tzinfo=timezone.utc))

    async def test_clock_agent_gets_the_note_just_before_the_task(self):
        agent, completions = make_agent([("text", "ok")], name="analyst", clock=True)
        await agent.run("any NFL games tonight")
        messages = completions.requests[0]["messages"]
        assert messages[-1] == {"role": "user", "content": "any NFL games tonight"}
        assert messages[-2]["role"] == "system" and messages[-2]["content"].startswith("Now: ")

    async def test_agents_without_clock_are_unchanged(self):
        agent, completions = make_agent([("text", "ok")])
        await agent.run("what time")
        assert not any(m["content"].startswith("Now: ")
                       for m in completions.requests[0]["messages"] if m["role"] == "system")

    def test_analyst_has_the_clock_and_mcp_time(self):
        agents = load_sub_agents(make_settings(), FakeRegistry(),
                                 client_factory=lambda s: FakeLLM([]))
        assert agents["analyst"].clock is True
        assert agents["analyst"].mcp_servers == ["mcp-web", "mcp-screen", "mcp-time"]
        assert [n for n, a in agents.items() if a.clock] == ["analyst"]
