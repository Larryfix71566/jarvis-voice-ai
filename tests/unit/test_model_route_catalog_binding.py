"""Independent wire/selection regressions for exact confidential catalog proof."""
from types import SimpleNamespace
from dataclasses import replace

import pytest
import yaml

from jarvis import model_routing
from jarvis.model_execution import ModelExecutionRequest, execute_chat
from jarvis.model_routing import ModelRouteError, describe_route_choice, resolve_model_route_checked
from jarvis.privacy_policy import DataPolicy
from jarvis.saygm import parse_catalog


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch):
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "0")


def catalog(*entries):
    return parse_catalog({"data": list(entries) or [{
        "id": "claude-sonnet-5-TEE", "tier": "confidential",
        "gateway_provider": "chutes", "api_shapes": ["chat.completions"],
    }]})


def policy_path(tmp_path, **saygm_changes):
    data = yaml.safe_load(model_routing.DEFAULT_POLICY_PATH.read_text())
    data["routes"]["saygm"].update(saygm_changes)
    path = tmp_path / "model-access.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


async def test_catalog_proof_binds_actual_outbound_model_endpoint_and_capabilities(monkeypatch):
    monkeypatch.setenv("SAYGM_API_KEY", "fixture-key")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog())
    route = resolve_model_route_checked("memory", explicit_route="saygm")
    created, sent = [], []

    async def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(
            id="fixture", usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content="fixture", tool_calls=[]))],
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    def make_client(**kwargs):
        created.append(kwargs)
        return client

    monkeypatch.setattr("jarvis.llm_client.make_async_client", make_client)
    result = await execute_chat(ModelExecutionRequest(
        workload="memory", task_id="fixture", parent_request_id="parent",
        instructions="Synthetic fixture", data_policy=DataPolicy("confidential"),
    ), route)

    assert created[0]["base_url"] == "https://api.saygm.com/v1"
    assert created[0]["provider"] == "saygm"
    assert created[0]["api_key"] == "fixture-key"
    assert created[0]["model"] == sent[0]["model"] == result.model == "claude-sonnet-5-TEE"
    assert route.route.capabilities == ("text",)
    assert route.route.upstream_provider == "chutes"
    assert result.billing == "saygm_credit"
    assert result.data_policy.level == "confidential"
    assert "tools" not in sent[0] and "stream" not in sent[0]


@pytest.mark.parametrize("reverse", [False, True])
def test_checked_selection_ignores_open_entry_order(monkeypatch, reverse):
    entries = [
        {"id": "claude-sonnet-5", "tier": "frontier", "api_shapes": ["chat.completions"]},
        {"id": "claude-sonnet-5-TEE", "tier": "confidential", "api_shapes": ["chat.completions"]},
    ]
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog(*(entries[::-1] if reverse else entries)))
    route = resolve_model_route_checked("memory", explicit_route="saygm", environ={"SAYGM_API_KEY": "fixture"})
    assert route.model == "claude-sonnet-5-TEE"


def test_checked_catalog_and_execution_use_canonical_approved_endpoint(monkeypatch):
    registry = model_routing._load_model_registry()
    registry["profiles"]["claude-sonnet-5"]["routes"] = {"saygm": {
        "adapter": "saygm_gateway", "billing": "saygm_credit",
        "base_url": "https://api.saygm.com/v1/", "credential_env": "SAYGM_API_KEY",
        "privacy": "approved_external", "capabilities": ["text"],
    }}
    monkeypatch.setattr(model_routing, "_load_model_registry", lambda *_: registry)
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return catalog()

    monkeypatch.setattr("jarvis.saygm.fetch_catalog", fetch)
    route = resolve_model_route_checked("memory", explicit_route="saygm", environ={"SAYGM_API_KEY": "fixture"})
    assert calls == [{"api_key": "fixture", "base_url": route.base_url}]
    assert route.base_url == "https://api.saygm.com/v1"
    assert route.api_key_env == "SAYGM_API_KEY"


@pytest.mark.parametrize("changes", [
    {"base_url": "https://fixture.example.invalid/v1"},
    {"base_url": "http://api.saygm.com/v1"},
    {"base_url": "https://userinfo@api.saygm.com/v1"},
    {"base_url": "https://api.saygm.com:8443/v1"},
    {"base_url": "https://api.saygm.com/v1?secret=1"},
    {"base_url": "https://api.saygm.com/v1#fragment"},
    {"credential_env": "OTHER_PROVIDER_KEY"},
])
def test_unapproved_config_cannot_transmit_credential(tmp_path, monkeypatch, changes):
    path = policy_path(tmp_path, **changes)
    def forbidden(**kwargs):
        raise AssertionError("unapproved endpoint received catalog credentials")
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", forbidden)
    with pytest.raises(ModelRouteError, match="not approved"):
        resolve_model_route_checked("memory", explicit_route="saygm", policy_path=path,
                                    environ={"SAYGM_API_KEY": "fixture"})


def test_client_builders_reject_unapproved_handmade_endpoint_before_sdk(monkeypatch):
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog())
    route = resolve_model_route_checked("memory", explicit_route="saygm", environ={"SAYGM_API_KEY": "fixture"})
    route = replace(route, base_url="https://fixture.example.invalid/v1")
    def forbidden(**kwargs):
        raise AssertionError("unapproved endpoint received SDK credentials")
    monkeypatch.setattr("jarvis.llm_client.make_async_client", forbidden)
    monkeypatch.setattr("jarvis.llm_client.make_sync_client", forbidden)
    with pytest.raises(ModelRouteError, match="not approved"):
        model_routing.make_route_client(route)
    with pytest.raises(ModelRouteError, match="not approved"):
        model_routing.make_sync_route_client(route)


def test_approved_external_saygm_requires_exact_catalog_model_and_text_capability(monkeypatch):
    models = catalog(
        {"id": "claude-sonnet-5", "tier": "frontier", "api_shapes": ["chat.completions"]},
        {"id": "claude-sonnet-5-TEE", "tier": "confidential", "api_shapes": ["chat.completions"]},
    )
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: models)
    route = resolve_model_route_checked("research_synthesis", explicit_route="saygm",
                                        environ={"SAYGM_API_KEY": "fixture"})
    assert route.model == "claude-sonnet-5"
    assert route.route.privacy == "approved_external"
    assert route.route.capabilities == ("text",)
    with pytest.raises(ModelRouteError, match="lacks required capabilities: tools"):
        resolve_model_route_checked("developer", explicit_profile="claude-sonnet-5", explicit_route="saygm",
                                    environ={"SAYGM_API_KEY": "fixture"})
    with pytest.raises(ModelRouteError, match="catalog verification is required"):
        model_routing.resolve_model_route("research_synthesis", explicit_route="saygm",
                                         environ={"SAYGM_API_KEY": "fixture"})


def test_approved_external_cannot_silently_switch_to_a_tee_alias(monkeypatch):
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog())
    with pytest.raises(ModelRouteError, match="not present"):
        resolve_model_route_checked("research_synthesis", explicit_route="saygm",
                                    environ={"SAYGM_API_KEY": "fixture"})


@pytest.mark.parametrize("required", ["tools", "images", "streaming"])
def test_tee_and_gateway_labels_cannot_promote_model_capabilities(tmp_path, monkeypatch, required):
    path = policy_path(tmp_path, capabilities=["text", "tools", "images", "streaming"])
    data = yaml.safe_load(path.read_text())
    data["workloads"]["memory"]["capabilities"] = ["text", required]
    path.write_text(yaml.safe_dump(data))
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **_: catalog())
    with pytest.raises(ModelRouteError, match=f"lacks required capabilities: {required}"):
        resolve_model_route_checked("memory", explicit_route="saygm", policy_path=path,
                                    environ={"SAYGM_API_KEY": "fixture"})


def test_config_privacy_label_cannot_replace_catalog_proof(tmp_path):
    path = policy_path(tmp_path, privacy="confidential")
    with pytest.raises(ModelRouteError, match="protected privacy contract"):
        model_routing.resolve_model_route("memory", explicit_route="saygm", policy_path=path,
                                         environ={"SAYGM_API_KEY": "fixture"})


def test_confidential_catalog_cannot_satisfy_local_only(monkeypatch):
    calls = []
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ModelRouteError, match="requires local_only"):
        resolve_model_route_checked("systems", explicit_route="saygm", environ={"SAYGM_API_KEY": "fixture"})
    with pytest.raises(ModelRouteError, match="requires local_only"):
        model_routing.resolve_model_route("systems", explicit_route="saygm",
                                         environ={"SAYGM_API_KEY": "fixture"}, saygm_model=catalog()[0])
    assert calls == []


@pytest.mark.parametrize("profile,route,expected", [
    ("codex-subscription", "subscription", "anthropic"),
    ("claude-opus", "codex_subscription", "openai"),
])
def test_subscription_provider_mismatch_rejects_before_execution(profile, route, expected):
    with pytest.raises(ModelRouteError, match=f"requires a '{expected}' model profile"):
        resolve_model_route_checked("planning", explicit_profile=profile, explicit_route=route)


def test_choice_metadata_is_workload_specific_and_has_no_provider_or_db_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("read-only descriptor probed a provider or preferences")

    monkeypatch.setattr("jarvis.saygm.fetch_catalog", forbidden)
    monkeypatch.setattr("jarvis.model_preferences.list_preferences", forbidden)
    descriptor = describe_route_choice("vision", "claude-opus", "direct_api",
                                       environ={"ANTHROPIC_API_KEY": "private-fixture"})
    assert descriptor["compatible"] is True
    assert descriptor["key_present"] is True
    assert descriptor["credential_env"] == "ANTHROPIC_API_KEY"
    assert set(descriptor["capabilities"]) == {"text", "tools", "images", "streaming"}
    assert descriptor["billing"] == "provider_api"
    assert "private-fixture" not in str(descriptor)
    voice = describe_route_choice("voice_supervisor", "claude-haiku-4-5", "direct_api", environ={})
    assert voice["compatible"] is True and voice["model"] == "claude-haiku-4-5"
    assert describe_route_choice("developer", "claude-haiku-4-5", "direct_api")["compatible"] is False
    private = describe_route_choice("memory", "claude-sonnet-5", "saygm", environ={})
    assert private["compatible"] is False
    assert private["status"] == "catalog_verification_required"
    assert private["privacy"] == "approved_external"
    assert private["verification_required"] is True
    public = describe_route_choice("planning", "claude-opus", "saygm", environ={})
    assert public["compatible"] is False and public["verification_required"] is True
    assert public["capabilities"] == []


def test_loaded_choice_catalog_avoids_reloads_and_filters_subscription_provider(monkeypatch):
    access = model_routing.load_access_config()
    registry = model_routing._load_model_registry()
    def forbidden(*args, **kwargs):
        raise AssertionError("preloaded descriptor reloaded configuration")
    monkeypatch.setattr(model_routing, "load_access_config", forbidden)
    monkeypatch.setattr(model_routing, "_load_model_registry", forbidden)
    claude = registry["profiles"]["claude-opus"]
    codex = registry["profiles"]["codex-subscription"]
    assert "subscription" in model_routing.available_routes(claude, access["routes"])
    assert "codex_subscription" not in model_routing.available_routes(claude, access["routes"])
    assert "codex_subscription" in model_routing.available_routes(codex, access["routes"])
    assert "subscription" not in model_routing.available_routes(codex, access["routes"])
    descriptor = describe_route_choice("planning", "claude-opus", "subscription",
                                       access_config=access, registry=registry, environ={})
    assert descriptor["applicable"] is True and descriptor["compatible"] is True
    unsupported = describe_route_choice("developer", "claude-opus", "subscription",
                                        access_config=access, registry=registry, environ={})
    assert unsupported["applicable"] is True and unsupported["compatible"] is False
    wrong_provider = describe_route_choice("planning", "claude-opus", "codex_subscription",
                                           access_config=access, registry=registry, environ={})
    assert wrong_provider["applicable"] is False and wrong_provider["compatible"] is False


@pytest.mark.parametrize("workload", ["librarian", "memory", "systems"])
def test_legacy_saved_preference_cannot_lower_configured_privacy_before_client(tmp_path, monkeypatch, workload):
    from jarvis.db import get_conn, run_migrations
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "legacy-prefs.db"))
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    with get_conn() as conn:
        run_migrations(conn)
        conn.execute(
            "INSERT INTO model_route_preferences(workload, profile, route, privacy, updated_at) "
            "VALUES (?, 'claude-sonnet-5', 'direct_api', 'approved_external', '2026-09-01')",
            (workload,),
        )
        conn.commit()
    with pytest.raises(ModelRouteError, match="saved preference.*below.*configured"):
        resolve_model_route_checked(workload, environ={})
    assert model_routing.resolve_policy(workload, include_preferences=False).privacy != "approved_external"


async def test_actual_extract_and_settle_factories_refuse_legacy_weaker_preference(tmp_path, monkeypatch):
    from jarvis.db import get_conn, run_migrations
    from jarvis import memory_extraction, memory_model, memory_sweep
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "legacy-memory-prefs.db"))
    monkeypatch.setenv("JARVIS_MODEL_PREFERENCES_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MODEL_ROUTING_ENABLED", "1")
    monkeypatch.setenv("JARVIS_MEMORY_AUTO_SETTLE", "1")
    canary = "PRIVATE_MEMORY_FLOOR_CANARY"
    created = []
    def forbidden(*args, **kwargs):
        created.append(True)
        raise AssertionError("weaker preference reached provider construction")
    monkeypatch.setattr(memory_model, "make_async_client", forbidden)
    monkeypatch.setattr(memory_model, "make_route_client", forbidden)
    monkeypatch.setattr("jarvis.saygm.fetch_catalog", forbidden)
    settings = SimpleNamespace(jarvis_model_routing_enabled=True, jarvis_memory_profile="claude-sonnet-5")
    with get_conn() as conn:
        run_migrations(conn)
        conn.execute(
            "INSERT INTO model_route_preferences(workload, profile, route, privacy, updated_at) "
            "VALUES ('memory', 'claude-sonnet-5', 'direct_api', 'approved_external', '2026-09-01')")
        conn.execute(
            "INSERT INTO memory_reviews(kind, keys_json, detail, status, created_at) "
            "VALUES ('contradiction', '[\"a\",\"b\"]', 'fixture', 'open', '2026-09-01')")
        conn.commit()
        with pytest.raises(memory_model.MemoryModelUnavailable, match="saved preference.*below"):
            await memory_extraction.extract_candidates(settings, "fixture-session", canary, "fixture reply")
        monkeypatch.setattr(memory_sweep, "_fact_evidence", lambda _conn, key: {
            "key": key, "content": canary, "exchanges": [], "complete": False,
        })
        result = await memory_sweep.settle_open_reviews(conn, settings)
        assert result["left_open"] == 1 and result["settled"] == 0
    assert created == []
