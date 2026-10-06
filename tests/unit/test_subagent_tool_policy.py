"""Host source labels govern the real SubAgent loop, before every sink."""
import asyncio
import json
from dataclasses import replace

import pytest

from jarvis.agents.base import TIMEOUT_MESSAGE
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits
from jarvis.privacy_policy import DataPolicy, issue_tool_result
from tests.unit.test_subagent import FakeRegistry, make_agent

CANARY = "SYNTHETIC_PRIVATE_TOOL_PAYLOAD_2398"


@pytest.fixture(autouse=True)
def initialized_turn():
    token = current_sensitive_turn.set(SensitiveTurn())
    try:
        yield
    finally:
        current_sensitive_turn.reset(token)


def routed(registry, *, private=False, limits=WorkloadLimits()):
    subject, completions = make_agent(
        [("tool", "fake_tool", {}), ("text", "completed")], registry=registry,
    )
    subject._resolved_route = ResolvedModelRoute(
        "scheduler", "fixture", "fixture", "local" if private else "openai", "",
        AccessRoute("local" if private else "direct_api", "openai_compatible",
                    "local" if private else "provider_api", None,
                    "confidential" if private else "approved_external"),
        None, "fixture/fixture", "interactive", limits=limits,
    )
    return subject, completions


@pytest.mark.parametrize("raw", [
    json.dumps({"ok": True, "body": CANARY, "privacy": "approved_external"}),
    json.dumps({"ok": False, "error": CANARY}),
])
async def test_unclassified_source_cannot_continue_or_publish(raw):
    class Unclassified(FakeRegistry):
        async def call(self, *_args, **_kwargs):
            return raw
    subject, provider = routed(Unclassified())
    events = []
    result = await subject.run("public fixture", events.append)
    assert result.startswith("FAILED: this tool source requires a more private route")
    assert len(provider.requests) == 1
    assert CANARY not in json.dumps(events)
    assert CANARY not in result


async def test_host_classified_public_result_continues_and_preserves_tool_history():
    class Classified(FakeRegistry):
        async def call_classified(self, name, arguments, server_names, *, execution_scope):
            assert execution_scope.tool_name == name
            assert execution_scope.parent_request_id == "public-parent"
            return issue_tool_result(execution_scope, '{"ok":true,"public":"fixture"}',
                source_policy=DataPolicy("approved_external", "verified-public-fixture"),
                source_scope="verified_public_fixture")
    subject, provider = routed(Classified())
    assert await subject.run("public fixture", run_id="public-parent") == "completed"
    assert len(provider.requests) == 2
    assert provider.requests[1]["messages"][-1] == {
        "role": "tool", "tool_call_id": "call_1", "name": "fake_tool",
        "content": '{"ok":true,"public":"fixture"}',
    }


async def test_invalid_envelope_cannot_publish_or_continue():
    class Forged(FakeRegistry):
        async def call_classified(self, *_args, execution_scope):
            original = issue_tool_result(execution_scope, '{"ok":true}',
                source_policy=DataPolicy("approved_external", "fixture"), source_scope="fixture")
            return replace(original, content=CANARY)
    subject, provider = routed(Forged())
    events = []
    result = await subject.run("public fixture", events.append)
    assert "ToolResultBindingError" in result
    assert len(provider.requests) == 1
    assert CANARY not in json.dumps(events)
    assert CANARY not in result


async def test_local_only_source_cannot_continue_on_confidential_external_route():
    class LocalSource(FakeRegistry):
        async def call_classified(self, *_args, execution_scope):
            return issue_tool_result(execution_scope, CANARY,
                source_policy=DataPolicy("local_only", "local-fixture"), source_scope="local_fixture")
    subject, provider = routed(LocalSource(), private=True)
    delivered = []
    result = await subject.run("public fixture", private_result_sink=lambda *args: delivered.append(args))
    assert len(provider.requests) == 1
    assert delivered == []
    assert CANARY not in result


async def test_raw_custom_executor_has_no_implicit_public_grant():
    subject, provider = routed(FakeRegistry())
    result = await subject.run("public fixture", tool_specs_override=FakeRegistry().openai_tools(),
                               tool_executor=lambda _name, _args: {"ok": True, "body": CANARY})
    assert result.startswith("FAILED: this tool source requires a more private route")
    assert len(provider.requests) == 1


async def test_custom_host_executor_can_issue_exact_scoped_result():
    subject, provider = routed(FakeRegistry())
    def trusted(name, arguments, *, execution_scope):
        return issue_tool_result(execution_scope, '{"ok":true}',
            source_policy=DataPolicy("approved_external", "trusted-fixture"), source_scope="fixture")
    result = await subject.run("public fixture", tool_specs_override=FakeRegistry().openai_tools(),
                               tool_executor=trusted)
    assert result == "completed"
    assert len(provider.requests) == 2


async def test_outer_task_deadline_covers_tool_execution(monkeypatch, tmp_path):
    from jarvis import usage_ledger
    monkeypatch.setattr(usage_ledger, "DB_PATH", tmp_path / "deadline.db")
    class SlowTool(FakeRegistry):
        async def call_classified(self, *_args, execution_scope):
            await asyncio.sleep(1)
            pytest.fail("cancelled tool must not finish")
    subject, provider = routed(SlowTool(), limits=WorkloadLimits(deadline_seconds=.15))
    assert await subject.run("public fixture") == TIMEOUT_MESSAGE
    assert len(provider.requests) == 1


async def test_legacy_routing_off_keeps_existing_string_loop():
    class Legacy(FakeRegistry):
        async def call(self, *_args, **_kwargs):
            return '{"ok":true}'
    subject, provider = make_agent([("tool", "fake_tool", {}), ("text", "completed")],
                                    registry=Legacy())
    assert await subject.run("public fixture") == "completed"
    assert len(provider.requests) == 2
