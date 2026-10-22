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


@pytest.mark.parametrize("extra,reason", [
    ("disable-model-invocation: true", "unsupported_frontmatter_fields"),
    ("disable-model-invocation: false", "unsupported_frontmatter_fields"),
    ("allowed-tools: []", "unsupported_frontmatter_fields"),
    ("model: private-canary", "unsupported_frontmatter_fields"),
    ("license: private-canary", "unsupported_frontmatter_fields"),
    ("metadata: null", "metadata_not_mapping"),
    ("metadata: []", "metadata_not_mapping"),
    ("metadata: {agent: null}", "metadata_string_required"),
    ("metadata: {promoted_successes: true}", "metadata_integer_required"),
    ("metadata: {private-canary: x}", "unsupported_metadata_fields"),
    ("name: replacement", "frontmatter_duplicate_key"),
    ("metadata: {agent: a, agent: b}", "frontmatter_duplicate_key"),
    ("metadata: &private-canary {agent: x}", "frontmatter_yaml_features_unsupported"),
    ("metadata: !!map {agent: x}", "frontmatter_yaml_features_unsupported"),
    ("metadata: {source: [x]}", "metadata_string_required"),
])
def test_unsupported_or_malformed_frontmatter_refuses_without_content(tmp_path, extra, reason):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\n" + extra)
    skill, problems = skills.parse_skill(path)
    assert skill is None
    assert problems == [reason]
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


@pytest.mark.parametrize("content,reason", [
    (b"\xff", "frontmatter_missing"),
    (b"---\nname: sample-skill\ndescription: \xff\n---\nb", "skill_encoding_invalid"),
    (b"x" * (128 * 1024 + 1), "skill_file_too_large"),
    (b"---\n#" + b"x" * (16 * 1024) + b"\n---\nbody", "frontmatter_too_large"),
])
def test_invalid_encoding_or_resource_limit_refuses(tmp_path, content, reason):
    path = candidate(tmp_path)
    path.write_bytes(content)
    skill, problems = skills.parse_skill(path)
    assert skill is None and problems == [reason]
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


@pytest.mark.parametrize("front,reason", [
    ("name: sample-skill\ndescription: Safe text\nmetadata: {source: *missing}", "frontmatter_yaml_features_unsupported"),
    ("name: sample-skill\ndescription: Safe text\nmetadata: {source: !private-canary x}", "frontmatter_yaml_features_unsupported"),
    ("[name, description]", "frontmatter_not_mapping"),
    ("? [private-canary]\n: x", "frontmatter_keys_not_strings"),
    ("name: sample-skill\ndescription: Safe text\nmetadata: {agent: " + "x" * 1025 + "}", "metadata_string_too_long"),
])
def test_yaml_shape_and_metadata_resource_refusals_are_safe(tmp_path, front, reason):
    skill, problems = skills.parse_skill(candidate(tmp_path, front))
    assert skill is None and problems == [reason]
    assert "private-canary" not in str(problems)


@pytest.mark.parametrize("entries,reason", [(256, None), (257, "package_entry_limit")])
def test_exact_root_entry_boundary(tmp_path, entries, reason):
    path = candidate(tmp_path)
    for index in range(entries - 1):
        (path.parent / f"reference-{index}.txt").touch()
    skill, problems = skills.parse_skill(path)
    assert problems == ([reason] if reason else [])
    assert (skill is None) == (reason is not None)


@pytest.mark.parametrize("count,reason", [(128, "frontmatter_not_mapping"), (129, "frontmatter_complexity_limit")])
def test_exact_yaml_event_boundary(count, reason):
    import yaml
    from jarvis.skill_compatibility import load_frontmatter
    # The scan permits 128 events; the closed schema still rejects a sequence.
    front = "[" + ", ".join("x" for _ in range(count - 6)) + "]"
    assert len(list(yaml.parse(front))) == count
    assert load_frontmatter(front) == (None, [reason])


@pytest.mark.parametrize("depth,reason", [(4, "frontmatter_not_mapping"), (5, "frontmatter_complexity_limit")])
def test_exact_yaml_depth_boundary(depth, reason):
    from jarvis.skill_compatibility import load_frontmatter
    assert load_frontmatter("[" * depth + "x" + "]" * depth) == (None, [reason])


def test_metadata_exact_character_limit_is_accepted(tmp_path):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nmetadata: {source: " + "x" * 1024 + "}")
    skill, problems = skills.parse_skill(path)
    assert not problems and skill.metadata["source"] == "x" * 1024


def test_frontmatter_byte_limit_refuses_before_yaml(tmp_path, monkeypatch):
    import yaml
    path = candidate(tmp_path, "#" + "x" * (16 * 1024))
    monkeypatch.setattr(yaml, "parse", lambda *a, **k: pytest.fail("oversize frontmatter reached YAML"))
    assert skills.parse_skill(path) == (None, ["frontmatter_too_large"])


@pytest.mark.parametrize("flag", ["O_NOFOLLOW", "O_NONBLOCK"])
def test_missing_platform_read_flags_fail_closed(tmp_path, monkeypatch, flag):
    path = candidate(tmp_path)
    monkeypatch.delattr(os, flag)
    assert skills.parse_skill(path) == (None, ["skill_unreadable"])


def test_failed_fdopen_does_not_leak_reader_descriptor(tmp_path, monkeypatch):
    path = candidate(tmp_path)
    opened = []
    original = os.open
    def record(*args, **kwargs):
        fd = original(*args, **kwargs)
        opened.append(fd)
        return fd
    monkeypatch.setattr(os, "open", record)
    monkeypatch.setattr(os, "fdopen", lambda *a, **k: (_ for _ in ()).throw(OSError("private-canary")))
    assert skills.parse_skill(path) == (None, ["skill_unreadable"])
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_invalid_registry_message_is_not_attributed_to_package(tmp_path, monkeypatch, capsys):
    path = candidate(tmp_path, "name: sample-skill\ndescription: Safe text\nunknown: x")
    path.parent.rename(tmp_path / "registry")
    config = tmp_path / "config.yaml"
    config.write_text("enabled: [\n")
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skills, "SKILLS_CONFIG", config)
    import jarvis.skill_catalog as catalog
    monkeypatch.setattr(catalog, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(catalog, "SKILLS_CONFIG", config)
    assert skills.main(["--validate"]) == 1
    output = capsys.readouterr().out
    assert "INVALID registry: invalid or unavailable" in output
    assert "package-1: invalid or unavailable" not in output


@pytest.mark.parametrize("stage", ["fsync", "link"])
@pytest.mark.parametrize("preexisting_folder", [False, True])
def test_failed_writer_never_publishes_partial_skill(tmp_path, monkeypatch, stage, preexisting_folder):
    folder = tmp_path / "sample-skill"
    if preexisting_folder:
        folder.mkdir()
        (folder / "keep.txt").write_text("unrelated")
    def fail(*args, **kwargs):
        raise OSError("private-canary")
    monkeypatch.setattr(os, stage, fail)
    with pytest.raises(ValueError, match="^skill_write_failed$"):
        skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
    assert not (folder / "SKILL.md").exists()
    if preexisting_folder:
        assert [p.name for p in folder.iterdir()] == ["keep.txt"]
    else:
        assert not folder.exists()


def test_writer_race_preserves_winner_and_hides_path(tmp_path, monkeypatch):
    original_link = os.link
    def race(src, dst, **kwargs):
        (tmp_path / "sample-skill" / "SKILL.md").write_text("concurrent winner")
        return original_link(src, dst, **kwargs)
    monkeypatch.setattr(os, "link", race)
    with pytest.raises(FileExistsError, match="^skill_already_exists$"):
        skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
    folder = tmp_path / "sample-skill"
    assert (folder / "SKILL.md").read_text() == "concurrent winner"
    assert [p.name for p in folder.iterdir()] == ["SKILL.md"]


def test_writer_rejects_changed_serialization_before_creation(tmp_path, monkeypatch):
    import yaml
    monkeypatch.setattr(yaml, "safe_dump", lambda *a, **k: "name: another-skill\ndescription: Safe text\n")
    with pytest.raises(ValueError, match="^skill_serialization_invalid$"):
        skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
    assert not (tmp_path / "sample-skill").exists()


def test_lazy_body_validates_supported_content(tmp_path):
    path = candidate(tmp_path)
    skill = skills.Skill("sample-skill", "Safe text", path)
    assert skill.body() == "Keep all instructions."
    assert skill._body == "Keep all instructions."


@pytest.mark.parametrize("kind", ["control", "mismatched_card", "fifo", "symlink"])
def test_lazy_body_cannot_bypass_parser(tmp_path, monkeypatch, kind):
    path = candidate(tmp_path)
    if kind == "control":
        path.write_text(path.read_text().replace("description:", "allowed-tools: private-canary\ndescription:"))
    if kind in {"fifo", "symlink"}:
        path.unlink()
        if kind == "fifo":
            os.mkfifo(path)
        else:
            path.symlink_to(tmp_path / "missing")
    skill = skills.Skill("wrong-card" if kind == "mismatched_card" else "sample-skill", "Safe text", path)
    # Fail the old unbounded read before it can block on the FIFO.
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("unbounded lazy read"))
    with pytest.raises(ValueError, match="^skill_body_unavailable$"):
        skill.body()


@pytest.mark.parametrize("resources,allowed", [(255, True), (256, False)])
def test_writer_final_entry_count_matches_parser_limit(tmp_path, resources, allowed):
    folder = tmp_path / "sample-skill"
    folder.mkdir()
    for index in range(resources):
        (folder / f"reference-{index}.txt").touch()
    if allowed:
        path = skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
        skill, problems = skills.parse_skill(path)
        assert skill is not None and not problems
        assert len(list(folder.iterdir())) == 256
    else:
        with pytest.raises(ValueError, match="^package_entry_limit$"):
            skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
        assert len(list(folder.iterdir())) == resources


def test_writer_partial_io_failure_removes_only_its_staging_file(tmp_path, monkeypatch):
    original = os.fdopen
    class PartialWrite:
        def __init__(self, fd):
            self.output = original(fd, "wb")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.output.close()
        def write(self, content):
            self.output.write(content[:16])
            raise OSError("private-canary")
    monkeypatch.setattr(os, "fdopen", lambda fd, mode: PartialWrite(fd))
    with pytest.raises(ValueError, match="^skill_write_failed$"):
        skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
    assert not (tmp_path / "sample-skill").exists()


def test_writer_publishes_complete_content_at_the_atomic_link(tmp_path, monkeypatch):
    original = os.link
    def inspect_link(src, dst, **kwargs):
        folder = tmp_path / "sample-skill"
        assert not (folder / "SKILL.md").exists()
        staged = (folder / src).read_text()
        assert staged.endswith("Required ending.\n")
        assert "name: sample-skill" in staged
        return original(src, dst, **kwargs)
    monkeypatch.setattr(os, "link", inspect_link)
    path = skills.write_skill("sample-skill", "Safe text", "Required ending.", directory=tmp_path)
    assert [p.name for p in path.parent.iterdir()] == ["SKILL.md"]


def test_serialization_delimiter_check_precedes_directory_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "_split_frontmatter", lambda _text: ("changed", "Body"))
    with pytest.raises(ValueError, match="^skill_serialization_invalid$"):
        skills.write_skill("sample-skill", "Safe text", "Body", directory=tmp_path)
    assert not (tmp_path / "sample-skill").exists()


def test_individually_valid_unicode_fields_still_obey_aggregate_byte_cap(tmp_path):
    text = "\U0001f600" * 1024
    with pytest.raises(ValueError, match="^frontmatter_too_large$"):
        skills.write_skill("sample-skill", text, "Body", dict(agent=text, source=text, concept_from=text), tmp_path)
    assert not (tmp_path / "sample-skill").exists()
