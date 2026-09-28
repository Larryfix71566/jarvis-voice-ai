import json

import pytest

from jarvis.skill_authoring_validation import validate_skill_candidate
from sandbox.artifacts import Candidate, File, SandboxError


def _package(slug="sample-skill"):
    skill = f"""---
name: {slug}
description: Help users complete a sample, repeatable task.
---

# Sample skill

Use this skill when the user asks for a sample task.
"""
    manifest = f"""schema_version: 1
skill_id: {slug}
display_name: Sample Skill
category: general
version: 1.0.0
source:
  kind: authored
capabilities: []
required_tools: []
required_credentials: []
reference_paths: []
example_ids: [positive-sample, negative-sample]
related_workflow_ids: []
compatible_with: []
process:
  kind: linear
  nodes:
    - step_id: do-work
      title: Do the work
      description: Complete the requested task.
      inputs: [user_request]
      outputs: [result]
      tools: []
      success_criteria: [result is complete]
      edges: []
"""
    return [
        File(f"skills/{slug}/SKILL.md", 0o644, skill.encode()),
        File(f"skills/{slug}/mortimer.yaml", 0o644, manifest.encode()),
    ]


def _baseline():
    return Candidate((File("config/skills.yaml", 0o644,
                           b"schema_version: 2\nenabled: []\nrevisions: {}\n"),))


def _matcher(slug="sample-skill"):
    cases = {
        "schema_version": 1,
        "cases": [
            {"id": "positive-sample", "request": f"Please use {slug} for this task", "expect_selected": True},
            {"id": "negative-sample", "request": "Tell me an unrelated joke", "expect_selected": False},
        ],
    }
    return File(f"tests/fixtures/skills_authoring/{slug}/matcher-cases.json", 0o644,
                json.dumps(cases).encode())


def test_offline_validation_binds_receipt_to_valid_package_without_registry_change():
    baseline = _baseline()
    candidate = Candidate(baseline.files + tuple(_package()) + (_matcher(),))

    receipt = validate_skill_candidate(candidate, baseline=baseline, slug="sample-skill")

    assert receipt.passed
    result = receipt.as_dict()
    assert result["candidate_digest"]
    assert result["package_revision"]
    assert result["provider_calls"] == 0
    assert {item["name"] for item in result["checks"]} >= {
        "package_schema", "declared_references", "runtime_registry_unchanged",
    }


def test_offline_validation_rejects_out_of_scope_candidate_changes():
    baseline = _baseline()
    candidate = Candidate(tuple(
        File(file.path, file.mode, b"enabled: [sample-skill]\n")
        if file.path == "config/skills.yaml" else file
        for file in baseline.files + tuple(_package()) + (_matcher(),)
    ))

    with pytest.raises(SandboxError):
        validate_skill_candidate(candidate, baseline=baseline, slug="sample-skill")


def test_offline_validation_supports_revision_of_existing_skill_package():
    baseline = Candidate(_baseline().files + tuple(_package()) + (_matcher(),))
    changed = Candidate(baseline.files + (
        File("skills/sample-skill/extra.md", 0o644, b"extra\n"),
    ))

    receipt = validate_skill_candidate(changed, baseline=baseline, slug="sample-skill")

    assert receipt.passed


def test_offline_validation_prevents_creator_self_modification():
    with pytest.raises(ValueError, match="cannot modify its own"):
        validate_skill_candidate(Candidate(()), baseline=Candidate(()), slug="skill-creator")


def test_offline_validation_requires_declared_references_to_exist():
    baseline = _baseline()
    package = [
        File(file.path, file.mode,
             file.data.replace(b"reference_paths: []", b"reference_paths: [references/missing.md]"))
        if file.path.endswith("mortimer.yaml") else file
        for file in _package()
    ]
    candidate = Candidate(baseline.files + tuple(package) + (_matcher(),))

    receipt = validate_skill_candidate(candidate, baseline=baseline, slug="sample-skill")

    assert not receipt.passed
    assert not next(check for check in receipt.checks if check["name"] == "declared_references")["passed"]


def test_offline_validation_rejects_incomplete_matcher_examples():
    baseline = _baseline()
    invalid = File(
        "tests/fixtures/skills_authoring/sample-skill/matcher-cases.json", 0o644,
        b'{"schema_version":1,"cases":[{"id":"positive-sample","request":"x","expect_selected":true}]}'
    )
    candidate = Candidate(baseline.files + tuple(_package()) + (invalid,))

    receipt = validate_skill_candidate(candidate, baseline=baseline, slug="sample-skill")

    assert not receipt.passed
    assert not next(check for check in receipt.checks if check["name"] == "matcher_fixtures")["passed"]


def test_offline_validation_bounds_fixture_file_count_and_size():
    baseline = _baseline()
    package = tuple(_package())
    matcher = _matcher()

    too_many = tuple(
        File(f"tests/fixtures/skills_authoring/sample-skill/extra-{index}.txt",
             0o644, b"fixture\n")
        for index in range(129)
    )
    count_receipt = validate_skill_candidate(
        Candidate(baseline.files + package + (matcher,) + too_many),
        baseline=baseline, slug="sample-skill",
    )
    assert not next(check for check in count_receipt.checks
                    if check["name"] == "fixture_file_count")["passed"]

    oversized = File(
        "tests/fixtures/skills_authoring/sample-skill/extra.txt", 0o644,
        b"x" * (128 * 1024 + 1),
    )
    size_receipt = validate_skill_candidate(
        Candidate(baseline.files + package + (matcher, oversized)),
        baseline=baseline, slug="sample-skill",
    )
    assert not next(check for check in size_receipt.checks
                    if check["name"] == "fixture_text_file_size")["passed"]

    large_fixtures = tuple(
        File(f"tests/fixtures/skills_authoring/sample-skill/large-{index}.txt",
             0o644, b"x" * (128 * 1024))
        for index in range(81)
    )
    aggregate_receipt = validate_skill_candidate(
        Candidate(baseline.files + package + (matcher,) + large_fixtures),
        baseline=baseline, slug="sample-skill",
    )
    assert not next(check for check in aggregate_receipt.checks
                    if check["name"] == "fixture_size")["passed"]


def test_offline_validation_requires_adapted_license_file():
    baseline = _baseline()
    package = [
        File(file.path, file.mode,
             file.data.replace(b"kind: authored", b"kind: adapted\n  license: Apache-2.0\n  license_path: LICENSE.txt"))
        if file.path.endswith("mortimer.yaml") else file
        for file in _package()
    ]
    candidate = Candidate(baseline.files + tuple(package) + (_matcher(),))

    receipt = validate_skill_candidate(candidate, baseline=baseline, slug="sample-skill")

    assert not receipt.passed
    assert not next(check for check in receipt.checks if check["name"] == "license_provenance")["passed"]
