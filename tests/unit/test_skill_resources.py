"""Security and budget tests for revision-bound skill reference reads."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.skill_catalog import inspect_package
from jarvis.skill_resources import SkillReferenceError, read_skill_reference


MANIFEST = """schema_version: 1
skill_id: sample-skill
display_name: Sample skill
category: development
version: 1.0.0
source: {kind: local, reference: fixture}
capabilities: []
required_tools: []
required_credentials: []
reference_paths: [references/guide.md]
example_ids: []
related_workflow_ids: []
compatible_with: []
process: null
"""


def package(tmp_path: Path, *, enabled=True):
    root = tmp_path / "sample-skill"
    references = root / "references"
    references.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Sample skill.\n---\nInstructions.\n",
        encoding="utf-8",
    )
    (root / "mortimer.yaml").write_text(MANIFEST, encoding="utf-8")
    (references / "guide.md").write_text("Reviewed guidance.\n", encoding="utf-8")
    config = tmp_path / "skills.yaml"
    config.write_text("enabled: [sample-skill]\n" if enabled else "enabled: []\n", encoding="utf-8")
    return root, config


def read(root: Path, config: Path, *, path="references/guide.md", revision=None, budget=100):
    current = inspect_package(root, config_path=config).revision
    return read_skill_reference(
        "sample-skill", revision or current, path,
        remaining_chars=budget, directory=root.parent, config_path=config,
    )


def test_reads_only_declared_enabled_revision_and_spends_exact_character_budget(tmp_path):
    root, config = package(tmp_path)
    result = read(root, config, budget=19)
    assert result.text == "Reviewed guidance.\n"
    assert result.remaining_chars == 0
    assert result.revision == inspect_package(root, config_path=config).revision


@pytest.mark.parametrize("path", [
    "../outside.md", "/etc/passwd", "references\\guide.md", "references//guide.md",
    "SKILL.md", "mortimer.yaml", "references/run.py", "references/guide.md/../x.md",
])
def test_rejects_unsafe_or_nontext_reference_paths(tmp_path, path):
    root, config = package(tmp_path)
    with pytest.raises(SkillReferenceError, match="invalid_reference_path"):
        read(root, config, path=path)


def test_rejects_undeclared_paths_disabled_skills_and_stale_revisions(tmp_path):
    root, config = package(tmp_path)
    entry = inspect_package(root, config_path=config)
    with pytest.raises(SkillReferenceError, match="reference_not_declared"):
        read(root, config, path="references/other.md")
    with pytest.raises(SkillReferenceError, match="skill_revision_changed"):
        read(root, config, revision="0" * 64)
    config.write_text("enabled: []\n", encoding="utf-8")
    with pytest.raises(SkillReferenceError, match="skill_not_enabled"):
        read_skill_reference("sample-skill", entry.revision, "references/guide.md",
                             remaining_chars=100, directory=tmp_path, config_path=config)


def test_refuses_budget_overrun_without_truncating_and_rejects_invalid_utf8(tmp_path):
    root, config = package(tmp_path)
    with pytest.raises(SkillReferenceError, match="reference_budget_exceeded"):
        read(root, config, budget=4)
    target = root / "references" / "guide.md"
    target.write_bytes(b"\xff\xfe")
    with pytest.raises(SkillReferenceError, match="reference_invalid_utf8"):
        read(root, config)


def test_refuses_symlinked_reference_and_package_digest_changes(tmp_path):
    root, config = package(tmp_path)
    revision = inspect_package(root, config_path=config).revision
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    target = root / "references" / "guide.md"
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(SkillReferenceError, match="invalid_skill_package"):
        read_skill_reference("sample-skill", revision, "references/guide.md",
                             remaining_chars=100, directory=tmp_path, config_path=config)
