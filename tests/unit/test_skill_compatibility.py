"""Offline instruction-only compatibility: no models, services or scripts."""
from pathlib import Path
import os

import pytest

from jarvis import agent_skills as skills
from jarvis.skill_catalog import SkillPackageError, inspect_package, list_catalog


def candidate(tmp_path, front="name: sample-skill\ndescription: Safe text", body="Keep all instructions."):
    folder = tmp_path / "sample-skill"
    folder.mkdir(exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(f"---\n{front}\n---\n{body}\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("extra", [
    "disable-model-invocation: true", "disable-model-invocation: false",
    "allowed-tools: []", "model: private-canary", "license: private-canary",
    "metadata: null", "metadata: []", "metadata: {agent: null}",
    "metadata: {promoted_successes: true}", "metadata: {private-canary: x}",
    "name: replacement", "metadata: {agent: a, agent: b}",
    "metadata: &private-canary {agent: x}", "metadata: !!map {agent: x}",
    "metadata: {source: [x]}",
])
def test_unsupported_or_malformed_frontmatter_refuses_without_content(tmp_path, extra):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\n" + extra)
    skill, problems = skills.parse_skill(path)
    assert skill is None
    assert problems
    assert "private-canary" not in str(problems)
    assert str(tmp_path) not in str(problems)


@pytest.mark.parametrize("field,value", [("name", "12"), ("description", "yes"), ("description", "2026-10-22")])
def test_required_fields_are_strings_without_coercion(tmp_path, field, value):
    front = {"name": "sample-skill", "description": "Safe text"}
    front[field] = value
    assert skills.parse_skill(candidate(tmp_path, "\n".join(f"{k}: {v}" for k, v in front.items())))[0] is None


@pytest.mark.parametrize("kind", ["directory", "file", "symlink"])
@pytest.mark.parametrize("name", ["scripts", "ScRiPtS"])
def test_any_root_scripts_entry_refuses_without_reading_it(tmp_path, monkeypatch, kind, name):
    path = candidate(tmp_path)
    scripts = path.parent / name
    if kind == "directory":
        scripts.mkdir()
    elif kind == "file":
        scripts.write_text("private-script-canary")
    else:
        scripts.symlink_to(tmp_path / "missing-target")
    original = Path.open
    def guarded_open(self, *args, **kwargs):
        assert self == path, "parser attempted to read a resource"
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)
    def no_content_reads(*args, **kwargs):
        pytest.fail("script refusal must precede all file-content reads")
    monkeypatch.setattr(os, "open", no_content_reads)
    skill, problems = skills.parse_skill(path)
    assert skill is None
    assert problems == ["unsupported_scripts_entry"]


def test_text_examples_references_and_metadata_are_retained(tmp_path):
    front = "name: sample-skill\ndescription: Safe text\nmetadata:\n  agent: ''\n  source: local\n  concept_from: example\n  promoted_successes: 5\n  promoted_failures: 0"
    body = "# Instructions\n\n```sh\necho example\n```\n\n[Guide](references/guide.md)\n---\nRequired ending."
    path = candidate(tmp_path, front, body)
    (path.parent / "references").mkdir()
    skill, problems = skills.parse_skill(path)
    assert not problems
    assert skill.body() == body
    assert skill.metadata == dict(agent="", source="local", concept_from="example", promoted_successes=5, promoted_failures=0)


@pytest.mark.parametrize("content", [b"\xff", b"x" * (128 * 1024 + 1), b"---\n#" + b"x" * (16 * 1024) + b"\n---\nbody"])
def test_invalid_encoding_or_resource_limit_refuses(tmp_path, content):
    path = candidate(tmp_path)
    path.write_bytes(content)
    skill, problems = skills.parse_skill(path)
    assert skill is None and problems
    assert str(tmp_path) not in str(problems)


def test_deep_yaml_is_a_bounded_refusal(tmp_path):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nmetadata: " + "[" * 1000 + "x" + "]" * 1000)
    assert skills.parse_skill(path)[0] is None


@pytest.mark.parametrize("description", ["yes", "2026-10-22", "a: b\nnew line"])
def test_writer_roundtrips_ambiguous_strings_and_empty_agent(tmp_path, description):
    path = skills.write_skill("sample-skill", description, "Body", {"agent": ""}, tmp_path)
    skill, problems = skills.parse_skill(path)
    assert not problems
    assert skill.description == description
    assert skill.metadata == {"agent": ""}


@pytest.mark.parametrize("metadata", [{"unknown": "private-canary"}, {"agent": None}, {"promoted_successes": True}, ["x"]])
def test_refused_authoring_leaves_no_candidate(tmp_path, metadata):
    with pytest.raises(ValueError) as failure:
        skills.write_skill("sample-skill", "Safe text", "Body", metadata, tmp_path)
    assert "private-canary" not in str(failure.value)
    assert not (tmp_path / "sample-skill").exists()


def test_catalog_exposes_safe_unsupported_reason_and_disabled_candidate(tmp_path):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nallowed-tools: private-canary")
    with pytest.raises(SkillPackageError, match="unsupported_frontmatter_fields"):
        inspect_package(path.parent)
    entry = list_catalog(tmp_path)[0]
    assert not entry.enabled and entry.readiness == "blocked"
    assert entry.blockers == ("unsupported_frontmatter_fields",)
    assert "private-canary" not in str(entry)


@pytest.mark.parametrize("mode", ["--validate", "--list", "--explain"])
def test_cli_compatibility_diagnostics_do_not_echo_invalid_paths(tmp_path, monkeypatch, capsys, mode):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nprivate-canary: x")
    path.parent.rename(tmp_path / "private-canary-folder")
    config = tmp_path / "registry.yaml"
    config.write_text("enabled: []\n")
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skills, "SKILLS_CONFIG", config)
    import jarvis.skill_catalog as catalog
    monkeypatch.setattr(catalog, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(catalog, "SKILLS_CONFIG", config)
    skills.main([mode, "safe task"] if mode == "--explain" else [mode])
    output = capsys.readouterr().out
    assert "private-canary" not in output
    assert "INVALID" in output


@pytest.mark.parametrize("workspace", [False, True])
def test_legacy_and_workspace_loader_isolate_blocked_candidate(tmp_path, monkeypatch, caplog, workspace):
    root = tmp_path / "skills"
    root.mkdir()
    good = skills.write_skill("valid-skill", "Safe task instructions", "Valid instructions", directory=root)
    blocked = candidate(root, "name: sample-skill\ndescription: Safe text\nallowed-tools: private-canary")
    config = tmp_path / "registry.yaml"
    good_digest = inspect_package(good.parent).revision
    if workspace:
        config.write_text("schema_version: 2\nenabled: [valid-skill, sample-skill]\nrevisions:\n  valid-skill: " + good_digest + "\n  sample-skill: " + "a" * 64 + "\n")
    else:
        config.write_text("enabled: [valid-skill, sample-skill]\n")
    monkeypatch.setenv("JARVIS_AGENT_SKILLS_ENABLED", "true")
    monkeypatch.setattr(skills, "skills_workspace_enabled", lambda: workspace)
    result = skills.load_skills(root, config)
    assert [item.name for item in result] == ["valid-skill"]
    assert "private-canary" not in caplog.text
    assert str(blocked) not in caplog.text


def test_integrity_reason_still_precedes_script_compatibility(tmp_path):
    path = candidate(tmp_path)
    (path.parent / "scripts").symlink_to(tmp_path / "missing")
    with pytest.raises(SkillPackageError, match="symlink_in_package"):
        inspect_package(path.parent)


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_non_regular_skill_file_refuses_without_blocking(tmp_path, kind):
    path = candidate(tmp_path)
    path.unlink()
    if kind == "symlink":
        path.symlink_to(tmp_path / "missing")
    else:
        os.mkfifo(path)
    assert skills.parse_skill(path)[0] is None


def test_file_and_frontmatter_limits_are_inclusive(tmp_path):
    from jarvis.skill_compatibility import MAX_FRONTMATTER_BYTES, MAX_SKILL_BYTES
    prefix = "name: sample-skill\ndescription: Safe text\n#"
    front = prefix + "x" * (MAX_FRONTMATTER_BYTES - len(prefix) - 1)
    path = candidate(tmp_path, front)
    assert skills.parse_skill(path)[0] is not None
    raw = path.read_bytes()
    path.write_bytes(raw + b"x" * (MAX_SKILL_BYTES - len(raw)))
    assert skills.parse_skill(path)[0] is not None
    path.write_bytes(path.read_bytes() + b"x")
    assert skills.parse_skill(path) == (None, ["skill_file_too_large"])


def test_oversized_authoring_refuses_before_creating_directory(tmp_path):
    with pytest.raises(ValueError, match="skill_file_too_large"):
        skills.write_skill("sample-skill", "Safe text", "x" * (128 * 1024), directory=tmp_path)
    assert not (tmp_path / "sample-skill").exists()


def test_readiness_retains_compatibility_blocker_without_tools(tmp_path):
    from jarvis.skill_service import evaluate_readiness, ToolInventory
    candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nallowed-tools: private-canary")
    entry = list_catalog(tmp_path)[0]
    result = evaluate_readiness(entry, tool_inventory=ToolInventory(names=frozenset(), complete=True), credential_presence={})
    assert "private-canary" not in str(result)
    assert result.state == "blocked"
    assert "unsupported_frontmatter_fields" in result.reason_codes


@pytest.mark.parametrize("explicit", [False, True])
def test_real_v2_snapshot_cannot_select_blocked_package(tmp_path, monkeypatch, explicit):
    from types import SimpleNamespace
    from jarvis import skill_selection as selection
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe task instructions\ndisable-model-invocation: true")
    config = tmp_path / "registry.yaml"
    config.write_text("schema_version: 2\nenabled: [sample-skill]\nrevisions:\n  sample-skill: " + "a" * 64 + "\n")
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skills, "SKILLS_CONFIG", config)
    monkeypatch.setenv("JARVIS_AGENT_SKILLS_ENABLED", "true")
    monkeypatch.setenv("JARVIS_SKILLS_WORKSPACE_ENABLED", "1")
    monkeypatch.setenv("JARVIS_SKILLS_SELECTION_V2", "1")
    selection.clear_runtime_package_snapshot()
    try:
        result = selection.select_runtime_primary_skill(
            "safe task instructions", registry=SimpleNamespace(tools_for=lambda _names: []),
            server_names=[], resolved_route=SimpleNamespace(route=SimpleNamespace(
                capabilities=("text",), privacy="local_only")),
            private_route=True, sensitive_task=False,
            explicit_skill_id="sample-skill" if explicit else None,
        )
        assert result.selected is None
        assert result.reason == ("explicit_skill_unavailable" if explicit else "no_eligible_skill")
        assert path.exists()  # refusal preserves original source
    finally:
        selection.clear_runtime_package_snapshot()


def test_promotion_without_agent_preserves_empty_string(tmp_path):
    path = skills.skill_from_procedure({"id": 1, "label": "safe task", "description": "yes"}, tmp_path)
    skill, problems = skills.parse_skill(path)
    assert not problems and skill.metadata["agent"] == ""


@pytest.mark.parametrize("front", [
    "name: sample-skill\ndescription: Safe text\nmetadata: {source: *missing}",
    "name: sample-skill\ndescription: Safe text\nmetadata: {source: !private-canary x}",
    "[name, description]", "? [private-canary]\n: x",
    "name: sample-skill\ndescription: Safe text\nmetadata: {agent: " + "x" * 1025 + "}",
])
def test_yaml_shape_and_metadata_resource_refusals_are_safe(tmp_path, front):
    skill, problems = skills.parse_skill(candidate(tmp_path, front))
    assert skill is None and problems
    assert "private-canary" not in str(problems)
