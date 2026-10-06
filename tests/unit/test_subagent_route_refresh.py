"""Saved selections are live per-run snapshots, with no provider calls."""
import asyncio
from types import SimpleNamespace

import pytest

from jarvis.agents.base import SubAgent
from jarvis.bot.sensitive_turn import SensitiveTurn, current_sensitive_turn
from jarvis.model_preferences import confirm_preference, stage_preference
from jarvis.model_routing import AccessRoute, ResolvedModelRoute, WorkloadLimits


class Recorder:
    def __init__(self, route, key, gate=None):
        self.route, self.key, self.gate = route, key, gate
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.gate is not None:
            await self.gate.wait()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=kwargs["model"], tool_calls=[]))])


@pytest.fixture
def setup_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "preferences.db"))
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key-before")
    token = current_sensitive_turn.set(SensitiveTurn())
    created = []
    gate_by_model = {}

    def factory(route):
        import os
        client = Recorder(route, os.environ.get(route.api_key_env) if route.api_key_env else None,
                          gate_by_model.get(route.model))
        created.append(client)
        return client

    monkeypatch.setattr("jarvis.agents.base.make_route_client", factory)
    settings = SimpleNamespace(
        openai_model="voice-fallback-must-not-run", openai_api_key="test",
        openai_base_url="http://unused", jarvis_timezone="UTC",
        jarvis_runlog_enabled=False, jarvis_procedures_enabled=False,
        jarvis_model_routing_enabled=True,
    )
    try:
        yield settings, created, gate_by_model
    finally:
        current_sensitive_turn.reset(token)


def save(profile):
    draft = stage_preference("developer", profile, "direct_api")
    confirm_preference(draft["draft_id"])


def agent(settings):
    return SubAgent("developer", "Developer", "fixture", [], settings,
                    SimpleNamespace(), model_profile="claude-opus",
                    on_profile_fallback="refuse")


async def run(subject, **kwargs):
    return await subject.run("public synthetic task", tool_specs_override=[], **kwargs)


async def test_saved_profile_beats_constructor_default(setup_routes):
    settings, created, _ = setup_routes
    save("claude-sonnet-5")
    assert await run(agent(settings)) == "claude-sonnet-5"
    assert created[-1].route.profile_name == "claude-sonnet-5"


async def test_existing_agent_reads_next_confirmed_choice(setup_routes):
    settings, created, _ = setup_routes
    subject = agent(settings)
    assert await run(subject) == "claude-opus-5"
    save("claude-sonnet-5")
    assert await run(subject) == "claude-sonnet-5"
    assert created[-1].calls[0]["model"] == "claude-sonnet-5"


async def test_explicit_task_profile_keeps_precedence(setup_routes):
    settings, _, _ = setup_routes
    save("claude-sonnet-5")
    subject = agent(settings)
    assert await run(subject, model_profile_override="claude-opus") == "claude-opus-5"
    assert await run(subject) == "claude-sonnet-5"


async def test_concurrent_runs_keep_their_own_snapshot(setup_routes):
    settings, created, gates = setup_routes
    subject = agent(settings)
    gates["claude-opus-5"] = asyncio.Event()
    first = asyncio.create_task(run(subject))
    async with asyncio.timeout(2):
        while not any(client.calls for client in created):
            await asyncio.sleep(0.001)
    save("claude-sonnet-5")
    assert await run(subject) == "claude-sonnet-5"
    gates["claude-opus-5"].set()
    assert await first == "claude-opus-5"
    assert subject._model == "claude-opus-5"  # no per-run instance mutation


async def test_next_api_run_reads_rotated_credential(setup_routes, monkeypatch):
    settings, created, _ = setup_routes
    subject = agent(settings)
    await run(subject)
    before = created[-1]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key-after")
    await run(subject)
    assert created[-1] is not before
    assert created[-1].key == "synthetic-key-after"


async def test_repaired_startup_selection_can_run_without_fallback(setup_routes, monkeypatch):
    settings, created, _ = setup_routes
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    subject = agent(settings)
    assert (await run(subject)).startswith("REFUSED:")
    assert created == []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-repaired-key")
    save("claude-sonnet-5")
    assert await run(subject) == "claude-sonnet-5"


async def test_unavailable_saved_choice_does_not_use_old_client(setup_routes, monkeypatch):
    settings, created, _ = setup_routes
    subject = agent(settings)
    await run(subject)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert (await run(subject)).startswith("REFUSED:")
    assert len([client for client in created if client.calls]) == 1


async def test_unreadable_saved_preferences_cannot_restore_startup_default(setup_routes, monkeypatch):
    settings, created, _ = setup_routes
    subject = agent(settings)
    save("claude-sonnet-5")
    def unreadable(**_kwargs):
        raise OSError("synthetic private database location")
    monkeypatch.setattr("jarvis.model_preferences.list_preferences", unreadable)
    assert (await run(subject)).startswith("REFUSED:")
    assert subject.model == "unavailable"
    assert created == []


async def test_disabled_routing_does_not_reuse_a_live_routed_client(setup_routes, monkeypatch):
    settings, created, _ = setup_routes
    subject = agent(settings)
    await run(subject)
    settings.jarvis_model_routing_enabled = False
    monkeypatch.delenv("JARVIS_MODEL_ROUTING_ENABLED")
    assert (await run(subject)).startswith("REFUSED: model routing was disabled")
    assert len([client for client in created if client.calls]) == 1


async def test_task_deadline_includes_per_run_route_verification(setup_routes, monkeypatch):
    import time
    from dataclasses import replace
    from jarvis.model_routing import resolve_model_route_checked
    settings, created, _ = setup_routes
    resolved = replace(resolve_model_route_checked("developer"),
                       limits=WorkloadLimits(deadline_seconds=.01))
    def delayed_resolution(*_args, **_kwargs):
        time.sleep(.04)
        return resolved
    monkeypatch.setattr("jarvis.agents.base.resolve_model_route_checked", delayed_resolution)
    subject = agent(settings)
    assert (await run(subject)).startswith("FAILED:")
    assert created == []


def test_model_disclosure_reads_current_choice_without_client(setup_routes):
    settings, created, _ = setup_routes
    subject = agent(settings)
    save("claude-sonnet-5")
    assert subject.model == "claude-sonnet-5"
    assert subject.api_key_env == "ANTHROPIC_API_KEY"
    assert subject.refuses == ""
    assert subject.model_is_fallback is False
    assert created == []


async def test_native_owner_is_reused_and_quarantine_cannot_be_bypassed(
    setup_routes, monkeypatch,
):
    settings, created, _ = setup_routes
    native_route = ResolvedModelRoute(
        "developer", "native", "native-fixture", "subscription", "",
        AccessRoute("subscription", "subscription_runtime", "subscription", None,
                    "approved_external"), None, "anthropic/native-fixture", "interactive",
    )
    monkeypatch.setattr("jarvis.agents.base.resolve_model_route_checked",
                        lambda *_args, **_kwargs: native_route)
    subject = agent(settings)
    assert await run(subject) == "native-fixture"
    assert await run(subject) == "native-fixture"
    assert len(created) == 1
    assert len(created[0].calls) == 2
    created[0].cleanup_unverified = True
    assert (await run(subject)).startswith("FAILED:")
    assert len(created) == 1
    assert len(created[0].calls) == 2


async def test_actual_stateless_native_cleanup_failure_retains_owner(setup_routes, monkeypatch):
    from jarvis.subscription import SubscriptionTextClient, SubscriptionRuntimeError

    settings, _, _ = setup_routes
    native_route = ResolvedModelRoute(
        'developer', 'native', 'native-fixture', 'subscription', '',
        AccessRoute('subscription', 'subscription_runtime', 'subscription', None,
                    'approved_external'), None, 'anthropic/native-fixture', 'interactive')
    created = []
    def factory(_route):
        client = SubscriptionTextClient('native-fixture')
        created.append(client)
        return client
    async def fail(*args, **kwargs):
        raise SubscriptionRuntimeError('SYNTHETIC_PRIVATE_CLEANUP_17419', category='cleanup')
    monkeypatch.setattr('jarvis.agents.base.resolve_model_route_checked', lambda *a, **kw: native_route)
    monkeypatch.setattr('jarvis.agents.base.make_route_client', factory)
    monkeypatch.setattr('jarvis.agents.base.execute_chat', fail)
    subject = agent(settings)
    first = await run(subject)
    assert first.startswith('FAILED:') and 'SYNTHETIC_PRIVATE' not in first
    assert subject._native_cleanup_quarantined == {id(created[0])}
    assert (await run(subject)).startswith('FAILED:')
    assert len(created) == 1
