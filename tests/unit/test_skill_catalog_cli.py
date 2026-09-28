"""Command-line package validation covers metadata and enabled v2 pins."""
from __future__ import annotations

from pathlib import Path

import yaml

from jarvis import agent_skills, skill_catalog
from jarvis.skill_catalog import inspect_package, validate_skill_inventory


def _package(root: Path, *, manifest: str | None = None) -> Path:
    package = root / "sample-skill"
    package.mkdir(parents=True, exist_ok=True)
    (package / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill.\n---\n\n# Instructions\nUse this sample.\n",
        encoding="utf-8",
    )
    if manifest is not None:
        (package / "mortimer.yaml").write_text(manifest, encoding="utf-8")
    return package


def _manifest(*, extra: str = "") -> str:
    return f"""schema_version: 1
skill_id: sample-skill
display_name: Sample skill
category: general
version: 1.0.0
source: {{kind: authored}}
{extra}capabilities: []
required_tools: []
required_credentials: []
reference_paths: []
example_ids: []
related_workflow_ids: []
compatible_with: []
process:
  kind: linear
  nodes:
    - step_id: do-task
      title: Do task
      description: Complete the synthetic request.
      edges: []
"""


def _write_v2_config(path: Path, enabled: list[str], revisions: dict[str, str]) -> None:
    path.write_text(yaml.safe_dump({
        "schema_version": 2,
        "enabled": enabled,
        "revisions": revisions,
    }, sort_keys=False), encoding="utf-8")


def test_legacy_package_without_companion_metadata_remains_valid(tmp_path):
    _package(tmp_path)
    config = tmp_path / "skills.yaml"
    config.write_text("enabled: [sample-skill]\n", encoding="utf-8")

    assert validate_skill_inventory(tmp_path, config) == []


def test_v2_validation_checks_only_configured_packages_against_exact_pins(tmp_path):
    package = _package(tmp_path, manifest=_manifest())
    digest = inspect_package(package).revision
    config = tmp_path / "skills.yaml"
    _write_v2_config(config, ["sample-skill"], {"sample-skill": "0" * 64})

    assert validate_skill_inventory(tmp_path, config) == [
        "sample-skill: revision_pin_mismatch",
    ]

    _write_v2_config(config, ["sample-skill"], {"sample-skill": digest})
    assert validate_skill_inventory(tmp_path, config) == []


def test_invalid_companion_manifest_and_missing_enabled_package_are_reported(tmp_path):
    _package(tmp_path, manifest=_manifest(extra="unreviewed: true\n"))
    config = tmp_path / "skills.yaml"
    _write_v2_config(config, ["sample-skill", "missing-skill"], {
        "sample-skill": "a" * 64,
        "missing-skill": "b" * 64,
    })

    assert validate_skill_inventory(tmp_path, config) == [
        "sample-skill: unknown_manifest_fields",
        "missing-skill: enabled_package_missing",
    ]


def test_validate_cli_reports_bad_metadata_and_accepts_matching_full_package(
    tmp_path, monkeypatch, capsys,
):
    root = tmp_path / "skills"
    root.mkdir()
    package = _package(root, manifest=_manifest())
    digest = inspect_package(package).revision
    config = tmp_path / "skills.yaml"
    _write_v2_config(config, ["sample-skill"], {"sample-skill": "0" * 64})
    monkeypatch.setattr(agent_skills, "SKILLS_DIR", root)
    monkeypatch.setattr(agent_skills, "SKILLS_CONFIG", config)
    monkeypatch.setattr(skill_catalog, "SKILLS_DIR", root)
    monkeypatch.setattr(skill_catalog, "SKILLS_CONFIG", config)

    assert agent_skills.main(["--validate"]) == 1
    assert "INVALID sample-skill: revision_pin_mismatch" in capsys.readouterr().out

    _write_v2_config(config, ["sample-skill"], {"sample-skill": digest})
    assert agent_skills.main(["--validate"]) == 0
    assert "All skill packages, metadata, and active digest pins are valid." in capsys.readouterr().out


def test_validate_cli_fails_closed_on_malformed_v2_registry_even_when_enforcement_is_off(
    tmp_path, monkeypatch, capsys,
):
    """The operator-facing validator must catch broken pins before rollout.

    Runtime enforcement intentionally remains opt-in during migration, so a
    successful legacy-mode load is not sufficient evidence that a v2 registry
    is structurally safe. Keep the CLI contract explicit for missing/extra
    pins and unknown top-level fields.
    """
    root = tmp_path / "skills"
    root.mkdir()
    package = _package(root, manifest=_manifest())
    digest = inspect_package(package).revision
    config = tmp_path / "skills.yaml"
    monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
    monkeypatch.setattr(agent_skills, "SKILLS_DIR", root)
    monkeypatch.setattr(agent_skills, "SKILLS_CONFIG", config)
    monkeypatch.setattr(skill_catalog, "SKILLS_DIR", root)
    monkeypatch.setattr(skill_catalog, "SKILLS_CONFIG", config)

    for text in (
        "schema_version: 2\nenabled: [sample-skill]\nrevisions: {}\n",
        f"schema_version: 2\nenabled: [sample-skill]\nrevisions: {{sample-skill: {digest}, extra: {'a' * 64}}}\n",
        f"schema_version: 2\nenabled: [sample-skill]\nrevisions: {{sample-skill: {digest}}}\nfuture_field: true\n",
    ):
        config.write_text(text, encoding="utf-8")
        assert agent_skills.main(["--validate"]) == 1
        output = capsys.readouterr().out
        assert "INVALID registry: invalid or unavailable" in output
        assert "All skill packages" not in output


def test_validate_cli_rejects_duplicate_yaml_registry_keys(tmp_path, monkeypatch, capsys):
    """A digest registry must not depend on YAML's last-key-wins behavior."""
    root = tmp_path / "skills"
    root.mkdir()
    package = _package(root, manifest=_manifest())
    digest = inspect_package(package).revision
    config = tmp_path / "skills.yaml"
    monkeypatch.delenv("JARVIS_SKILLS_WORKSPACE_ENABLED", raising=False)
    monkeypatch.setattr(agent_skills, "SKILLS_DIR", root)
    monkeypatch.setattr(agent_skills, "SKILLS_CONFIG", config)
    monkeypatch.setattr(skill_catalog, "SKILLS_DIR", root)
    monkeypatch.setattr(skill_catalog, "SKILLS_CONFIG", config)

    config.write_text(
        "schema_version: 2\n"
        "enabled: [sample-skill]\n"
        "revisions:\n"
        f"  sample-skill: {'0' * 64}\n"
        f"  sample-skill: {digest}\n",
        encoding="utf-8",
    )

    assert agent_skills.main(["--validate"]) == 1
    output = capsys.readouterr().out
    assert "INVALID registry: invalid or unavailable" in output
    assert "All skill packages" not in output
