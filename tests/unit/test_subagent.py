"""Unit tests for jarvis/agents/base.py (SubAgent) — scripted FakeLLM,
deterministic, no network (plan Phase 3 Tests)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from jarvis.agents.base import (
    STUCK_MESSAGE,
    TIMEOUT_MESSAGE,
    SubAgent,
    load_sub_agents,
)


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

    async def test_iteration_cap_returns_stuck(self):
        agent, _ = make_agent([("tool", "fake_tool", {})])
        reply = await agent.run("loop forever")
        assert reply == STUCK_MESSAGE

    async def test_timeout_returns_failed_message(self):
        agent, _ = make_agent([("sleep", 5.0)], timeout_s=0.05)
        assert await agent.run("slow task") == TIMEOUT_MESSAGE

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

    async def test_client_exception_returns_failed(self):
        class Boom:
            async def create(self, **kwargs):
                raise RuntimeError("api down")

        agent, _ = make_agent([("text", "unused")])
        agent._client = SimpleNamespace(
            chat=SimpleNamespace(completions=Boom()))
        reply = await agent.run("task")
        assert reply.startswith("FAILED:")

    async def test_system_prompt_from_appendix_a(self):
        agent, completions = make_agent([("text", "ok")], name="librarian")
        await agent.run("hi")
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
        assert set(agents) == {"scheduler", "librarian", "analyst", "systems", "developer"}
        assert agents["scheduler"].mcp_servers == ["mcp-time", "mcp-reminders"]
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


# A3 — repo map injection.
class TestRepoMapInjection:
    def test_injected_when_flag_set(self, tmp_path, monkeypatch):
        import jarvis.agents.base as base_module
        repo_root = tmp_path
        (repo_root / "docs").mkdir()
        (repo_root / "docs" / "REPO_MAP.md").write_text("## Test map\n- foo lives in bar\n")
        monkeypatch.setattr(base_module, "__file__", str(repo_root / "jarvis" / "agents" / "base.py"))
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
        import jarvis.agents.base as base_module
        monkeypatch.setattr(base_module, "__file__", str(tmp_path / "jarvis" / "agents" / "base.py"))
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
        repo_root = tmp_path
        (repo_root / "docs").mkdir()
        big = "x" * (base_module.REPO_MAP_MAX_CHARS + 500)
        (repo_root / "docs" / "REPO_MAP.md").write_text(big)
        monkeypatch.setattr(base_module, "__file__", str(repo_root / "jarvis" / "agents" / "base.py"))
        fake = FakeLLM([])
        agent = SubAgent(
            name="developer", display_name="Developer", description="d",
            mcp_servers=["mcp-repo"], settings=make_settings(),
            registry=FakeRegistry(), client_factory=lambda s: fake,
            inject_repo_map=True,
        )
        injected = agent._system_prompt.split("verify with tools before writing):\n")[1]
        assert len(injected) == base_module.REPO_MAP_MAX_CHARS
