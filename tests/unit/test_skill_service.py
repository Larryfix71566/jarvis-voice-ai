"""Conservative, side-effect-free Skills readiness evaluation."""
from __future__ import annotations

from dataclasses import replace

from jarvis.skill_catalog import inspect_package, list_catalog
from jarvis.skill_service import (
    ToolInventory,
    assess_current_readiness,
    configured_tool_inventory,
    evaluate_readiness,
)


def sample_skill(tmp_path):
    package = tmp_path / "sample-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Read a sample skill.\n---\n"
        "Instructions.\n",
        encoding="utf-8",
    )
    (package / "mortimer.yaml").write_text(
        "schema_version: 1\n"
        "skill_id: sample-skill\n"
        "display_name: Sample\n"
        "category: development\n"
        "version: 1.0.0\n"
        "source: {kind: local, reference: test}\n"
        "capabilities: []\n"
        "required_tools: [repo_read_file]\n"
        "required_credentials: [SAMPLE_API_KEY]\n"
        "reference_paths: []\n"
        "example_ids: []\n"
        "related_workflow_ids: []\n"
        "compatible_with: []\n"
        "process: null\n",
        encoding="utf-8",
    )
    config = tmp_path / "skills.yaml"
    config.write_text("enabled: [sample-skill]\n", encoding="utf-8")
    return inspect_package(package, config_path=config)


def test_configured_tool_inventory_reads_active_manifests_without_runtime_start():
    inventory = configured_tool_inventory()
    assert inventory.names is not None
    assert inventory.complete is True
    assert {"get_weather", "repo_read_file", "repo_search"} <= inventory.names


def test_configured_tool_inventory_rejects_duplicate_config_keys(tmp_path):
    config = tmp_path / "mcp_servers.yaml"
    config.write_text(
        "servers: []\n"
        "servers:\n"
        "  - name: mcp-weather\n",
        encoding="utf-8",
    )

    inventory = configured_tool_inventory(config_path=config, server_root=tmp_path)

    assert inventory.names is None
    assert inventory.complete is False


def test_configured_tool_inventory_marks_duplicate_manifest_keys_incomplete(tmp_path):
    config = tmp_path / "mcp_servers.yaml"
    config.write_text("servers:\n  - name: mcp-weather\n", encoding="utf-8")
    server_root = tmp_path / "servers"
    server = server_root / "mcp_weather"
    server.mkdir(parents=True)
    (server / "skill.yaml").write_text(
        "name: mcp-weather\n"
        "tools: [get_weather]\n"
        "tools: [get_weather, secret_tool]\n",
        encoding="utf-8",
    )

    inventory = configured_tool_inventory(
        config_path=config, server_root=server_root,
    )

    assert inventory.names == frozenset()
    assert inventory.complete is False


def test_configured_tool_inventory_does_not_follow_symlinked_server_directory(tmp_path):
    config = tmp_path / "mcp_servers.yaml"
    config.write_text("servers:\n  - name: mcp-weather\n", encoding="utf-8")
    server_root = tmp_path / "servers"
    external = tmp_path / "external"
    external.mkdir()
    (external / "skill.yaml").write_text(
        "name: mcp-weather\ntools: [get_weather]\n", encoding="utf-8",
    )
    server_root.mkdir()
    (server_root / "mcp_weather").symlink_to(external, target_is_directory=True)

    inventory = configured_tool_inventory(
        config_path=config, server_root=server_root,
    )

    assert inventory.names == frozenset()
    assert inventory.complete is False


def test_configured_tool_inventory_does_not_follow_manifest_symlink(tmp_path):
    config = tmp_path / "mcp_servers.yaml"
    config.write_text("servers:\n  - name: mcp-weather\n", encoding="utf-8")
    server_root = tmp_path / "servers"
    server = server_root / "mcp_weather"
    server.mkdir(parents=True)
    external = tmp_path / "external-skill.yaml"
    external.write_text(
        "name: mcp-weather\ntools: [get_weather]\n", encoding="utf-8",
    )
    (server / "skill.yaml").symlink_to(external)

    inventory = configured_tool_inventory(
        config_path=config, server_root=server_root,
    )

    assert inventory.names == frozenset()
    assert inventory.complete is False


def test_configured_tool_inventory_rejects_symlinked_server_root(tmp_path):
    config = tmp_path / "mcp_servers.yaml"
    config.write_text("servers:\n  - name: mcp-weather\n", encoding="utf-8")
    external_root = tmp_path / "external-servers"
    server = external_root / "mcp_weather"
    server.mkdir(parents=True)
    (server / "skill.yaml").write_text(
        "name: mcp-weather\ntools: [get_weather]\n", encoding="utf-8",
    )
    server_root = tmp_path / "servers"
    server_root.symlink_to(external_root, target_is_directory=True)

    inventory = configured_tool_inventory(
        config_path=config, server_root=server_root,
    )

    assert inventory.names is None
    assert inventory.complete is False


def test_configured_tool_inventory_rejects_symlinked_config_file(tmp_path):
    actual_config = tmp_path / "outside-config.yaml"
    actual_config.write_text("servers: []\n", encoding="utf-8")
    config = tmp_path / "mcp_servers.yaml"
    config.symlink_to(actual_config)
    server_root = tmp_path / "servers"
    server_root.mkdir()

    inventory = configured_tool_inventory(
        config_path=config, server_root=server_root,
    )

    assert inventory.names is None
    assert inventory.complete is False


def test_enabled_skill_tool_declarations_match_configured_mcp_manifests():
    inventory = configured_tool_inventory()
    assert inventory.complete and inventory.names is not None
    enabled = [entry for entry in list_catalog() if entry.enabled]
    assert enabled
    assert all(set(entry.required_tools) <= inventory.names for entry in enabled)


def test_missing_declared_tools_and_credentials_are_blockers(tmp_path):
    entry = sample_skill(tmp_path)
    result = evaluate_readiness(
        entry,
        tool_inventory=ToolInventory(frozenset({"get_weather"}), True),
        credential_presence={"SAMPLE_API_KEY": False},
    )
    assert result.state == "blocked"
    assert "required_tool_not_configured:repo_read_file" in result.reason_codes
    assert "required_credential_missing:SAMPLE_API_KEY" in result.reason_codes


def test_partial_positive_evidence_remains_unknown_and_never_claims_authentication(tmp_path):
    entry = sample_skill(tmp_path)
    result = evaluate_readiness(
        entry,
        tool_inventory=ToolInventory(frozenset({"repo_read_file"}), True),
        credential_presence={"SAMPLE_API_KEY": True},
    )
    assert result.state == "unknown"
    assert "tool_runtime_unverified" in result.reason_codes
    assert "credential_authentication_unverified" in result.reason_codes
    assert "revision_pin_unverified" in result.reason_codes
    assert "model_route_compatibility_unverified" in result.reason_codes


def test_only_complete_host_owned_evidence_can_produce_ready(tmp_path):
    entry = sample_skill(tmp_path)
    result = evaluate_readiness(
        entry,
        tool_inventory=ToolInventory(frozenset({"repo_read_file"}), True),
        runtime_tools=frozenset({"repo_read_file"}),
        credential_presence={"SAMPLE_API_KEY": True},
        credential_authentication={"SAMPLE_API_KEY": True},
        revision_pins={"sample-skill": entry.revision},
        revision_pins_complete=True,
        revision_enforcement=True,
        route_compatible=True,
    )
    assert result.state == "ready"
    assert result.reason_codes == ()


def test_verified_credential_failure_is_a_blocker(tmp_path):
    entry = sample_skill(tmp_path)
    result = evaluate_readiness(
        entry,
        tool_inventory=ToolInventory(frozenset({"repo_read_file"}), True),
        runtime_tools=frozenset({"repo_read_file"}),
        credential_presence={"SAMPLE_API_KEY": True},
        credential_authentication={"SAMPLE_API_KEY": False},
        revision_pins={"sample-skill": entry.revision},
        revision_pins_complete=True,
        revision_enforcement=True,
        route_compatible=True,
    )
    assert result.state == "blocked"
    assert "required_credential_authentication_failed:SAMPLE_API_KEY" in result.reason_codes


def test_current_presence_reports_boolean_only_and_disabled_is_blocked(
    tmp_path, monkeypatch,
):
    entry = sample_skill(tmp_path)
    monkeypatch.setenv("SAMPLE_API_KEY", "SECRET_CANARY")
    result = assess_current_readiness(entry)
    assert result.state == "unknown"
    assert "SECRET_CANARY" not in repr(result)

    disabled = replace(entry, enabled=False)
    result = evaluate_readiness(
        disabled,
        tool_inventory=ToolInventory(frozenset({"repo_read_file"}), True),
        credential_presence={"SAMPLE_API_KEY": True},
    )
    assert result.state == "blocked"
    assert "skill_disabled" in result.reason_codes


def test_known_missing_or_mismatched_revision_pin_blocks(tmp_path):
    entry = sample_skill(tmp_path)
    common = {
        "tool_inventory": ToolInventory(frozenset({"repo_read_file"}), True),
        "runtime_tools": frozenset({"repo_read_file"}),
        "credential_presence": {"SAMPLE_API_KEY": True},
        "credential_authentication": {"SAMPLE_API_KEY": True},
        "revision_enforcement": True,
        "route_compatible": True,
    }
    missing = evaluate_readiness(
        entry, revision_pins={}, revision_pins_complete=True, **common,
    )
    mismatch = evaluate_readiness(
        entry, revision_pins={"sample-skill": "0" * 64}, **common,
    )
    assert missing.state == mismatch.state == "blocked"
    assert "revision_pin_missing" in missing.reason_codes
    assert "revision_digest_mismatch" in mismatch.reason_codes


def test_incomplete_static_inventory_does_not_false_block(tmp_path):
    entry = sample_skill(tmp_path)
    result = evaluate_readiness(
        entry,
        tool_inventory=ToolInventory(frozenset(), False),
        credential_presence={"SAMPLE_API_KEY": True},
    )
    assert result.state == "unknown"
    assert "tool_inventory_incomplete" in result.reason_codes
    assert not any(reason.startswith("required_tool_not_configured:")
                   for reason in result.reason_codes)
