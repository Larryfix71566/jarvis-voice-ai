"""Integrity and schema checks for the read-only Agent Skills catalog."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from jarvis.skill_catalog import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_TEXT_FILE_BYTES,
    SkillPackageError,
    inspect_package,
    list_catalog,
)

MANIFEST = """schema_version: 1
skill_id: sample-skill
display_name: Sample skill
category: development
version: 1.0.0
source:
  kind: local
  reference: test-fixture
capabilities: [planning]
required_tools: []
required_credentials: []
reference_paths: []
example_ids: [sample-example]
related_workflow_ids: []
compatible_with: []
process:
  kind: linear
  nodes:
    - step_id: inspect
      title: Inspect
      description: Review the request.
      inputs: [request]
      outputs: [scope]
      tools: []
      success_criteria: [Scope is clear.]
      edges: [{to: finish}]
    - step_id: finish
      title: Finish
      description: Report the result.
      inputs: [scope]
      outputs: [result]
      tools: []
      success_criteria: [Result is reported.]
      edges: []
"""


def package(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "sample-skill"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: A sample skill for catalog tests.\n---\nInstructions.\n",
        encoding="utf-8",
    )
    (root / "mortimer.yaml").write_text(MANIFEST, encoding="utf-8")
    return root


def test_catalog_returns_pinned_read_only_metadata(tmp_path):
    root = package(tmp_path)
    enabled_config = tmp_path / "skills.yaml"
    enabled_config.write_text("enabled: []\n", encoding="utf-8")
    entry = list_catalog(tmp_path, config_path=enabled_config)[0]
    assert entry.skill_id == "sample-skill"
    assert entry.installation == "installed"
    assert entry.enabled is False
    assert entry.readiness == "unknown"
    assert entry.verification == "not_tested"
    assert entry.process_kind == "linear"
    assert [step["step_id"] for step in entry.process_nodes] == ["inspect", "finish"]
    assert entry.revision == inspect_package(root).revision
    before = entry.revision
    path = root / "SKILL.md"
    path.write_text(path.read_text() + "Changed bytes.\n", encoding="utf-8")
    assert inspect_package(root).revision != before


@pytest.mark.parametrize("change,reason", [
    (lambda data: data.replace("schema_version: 1", "schema_version: 2"), "unsupported_manifest_schema"),
    (lambda data: data.replace("skill_id: sample-skill", "skill_id: other-skill"), "manifest_skill_id_mismatch"),
    (lambda data: data.replace("category: development", "category: development\nunreviewed: true"), "unknown_manifest_fields"),
    (lambda data: data.replace("{to: finish}", "{to: missing}"), "unknown_process_edge_target"),
    (lambda data: data.replace("kind: linear", "kind: branching").replace("{to: finish}", "{to: inspect}"), "cyclic_process"),
    (lambda data: data.replace("reference_paths: []", "reference_paths: [../secret.txt]"), "unsafe_reference_path"),
    (lambda data: data.replace("reference_paths: []", "reference_paths: [references//guide.md]"), "unsafe_reference_path"),
    (lambda data: data.replace("reference_paths: []", "reference_paths: [references/run.py]"), "unsafe_reference_path"),
    (lambda data: data.replace("reference_paths: []", "reference_paths: [SKILL.md]"), "unsafe_reference_path"),
])
def test_rejects_invalid_metadata(tmp_path, change, reason):
    root = package(tmp_path)
    manifest = root / "mortimer.yaml"
    manifest.write_text(change(manifest.read_text()), encoding="utf-8")
    with pytest.raises(SkillPackageError, match=reason):
        inspect_package(root)


@pytest.mark.parametrize("resource_setup", [
    lambda root: None,
    lambda root: (root / "references").mkdir(),
    lambda root: (root / "references.md").write_text("not the declared nested file", encoding="utf-8"),
])
def test_declared_reference_must_exist_as_a_regular_package_file(tmp_path, resource_setup):
    root = package(tmp_path)
    manifest = root / "mortimer.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "reference_paths: []", "reference_paths: [references/guide.md]"),
        encoding="utf-8",
    )
    resource_setup(root)
    with pytest.raises(SkillPackageError, match="declared_reference_missing_or_unsafe"):
        inspect_package(root)


def test_declared_reference_is_valid_only_when_exact_path_exists(tmp_path):
    root = package(tmp_path)
    reference = root / "references" / "guide.md"
    reference.parent.mkdir()
    reference.write_text("Reviewed guidance.\n", encoding="utf-8")
    manifest = root / "mortimer.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "reference_paths: []", "reference_paths: [references/guide.md]"),
        encoding="utf-8",
    )
    entry = inspect_package(root)
    assert entry.reference_paths == ("references/guide.md",)


def test_package_digest_rejects_symlink(tmp_path):
    root = package(tmp_path)
    target = tmp_path / "outside.txt"
    target.write_text("external", encoding="utf-8")
    (root / "reference.txt").symlink_to(target)
    with pytest.raises(SkillPackageError, match="symlink_in_package"):
        inspect_package(root)


def test_manifest_duplicate_keys_fail_closed(tmp_path):
    root = package(tmp_path)
    path = root / "mortimer.yaml"
    path.write_text(path.read_text() + "category: unreviewed\n", encoding="utf-8")
    with pytest.raises(SkillPackageError, match="duplicate_manifest_key"):
        inspect_package(root)


def test_package_enforces_file_count_total_bytes_and_text_file_limits(tmp_path):
    root = package(tmp_path / "files")
    for index in range(MAX_PACKAGE_FILES):
        (root / f"extra-{index:03}.bin").write_bytes(b"x")
    with pytest.raises(SkillPackageError, match="package_size_limit"):
        inspect_package(root)

    root = package(tmp_path / "total-bytes")
    (root / "payload.bin").write_bytes(b"x" * (MAX_PACKAGE_BYTES + 1))
    with pytest.raises(SkillPackageError, match="package_size_limit"):
        inspect_package(root)

    root = package(tmp_path / "text-file")
    (root / "large.md").write_bytes(b"x" * (MAX_TEXT_FILE_BYTES + 1))
    with pytest.raises(SkillPackageError, match="text_file_size_limit"):
        inspect_package(root)


def test_list_catalog_keeps_invalid_skill_visible_without_details(tmp_path):
    package(tmp_path)
    invalid = tmp_path / "broken-skill"
    invalid.mkdir()
    (invalid / "SKILL.md").write_text("not a skill", encoding="utf-8")
    enabled_config = tmp_path / "skills.yaml"
    enabled_config.write_text("enabled: []\n", encoding="utf-8")
    entries = {
        entry.skill_id: entry
        for entry in list_catalog(tmp_path, config_path=enabled_config)
    }
    assert set(entries) == {"sample-skill", "broken-skill"}
    assert entries["broken-skill"].installation == "invalid"
    assert entries["broken-skill"].readiness == "blocked"
    assert entries["broken-skill"].revision is None
    assert "not a skill" not in repr(entries["broken-skill"].as_dict())


def test_metadata_file_is_bound_into_digest(tmp_path):
    root = package(tmp_path)
    first = inspect_package(root).revision
    with (root / "mortimer.yaml").open("a") as manifest:
        manifest.write("# reviewed change\n")
    second = inspect_package(root).revision
    assert first != second
    assert len(first) == len(second) == hashlib.sha256().digest_size * 2
