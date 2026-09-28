"""Host-owned, offline checks for one frozen skill-authoring candidate.

This module treats candidate content only as inert UTF-8 data. It never imports,
executes, or evaluates package files and it never calls a model provider.
"""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jarvis.agent_skills import parse_skill
from jarvis.skill_catalog import (
    MAX_PACKAGE_BYTES,
    MAX_PACKAGE_FILES,
    MAX_TEXT_FILE_BYTES,
    SkillPackageError,
    inspect_package,
)
from jarvis.skill_service import configured_tool_inventory
from sandbox.artifacts import Candidate


@dataclass(frozen=True)
class SkillAuthoringReceipt:
    slug: str
    candidate_digest: str
    package_revision: str
    checked_files: int
    checked_bytes: int
    checks: tuple[dict, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(item["passed"] for item in self.checks)

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "kind": "skill_authoring_offline_validation",
            "slug": self.slug,
            "candidate_digest": self.candidate_digest,
            "package_revision": self.package_revision,
            "checked_files": self.checked_files,
            "checked_bytes": self.checked_bytes,
            "passed": self.passed,
            "checks": list(self.checks),
            "provider_calls": 0,
        }


def validate_skill_candidate(
    candidate: Candidate, *, baseline: Candidate, slug: str,
) -> SkillAuthoringReceipt:
    """Validate a complete Candidate snapshot for one skill package revision.

    The candidate may contain a new package or an update to the same slug, and
    may include only its scoped public fixture files. The creator cannot edit
    itself. Package syntax and references are delegated to the same strict
    catalog validator used by Mortimer.
    """
    from jarvis.selfedit.skill_policy import SkillAuthoringPolicy

    policy = SkillAuthoringPolicy(slug)
    package_prefix = f"skills/{slug}/"
    fixture_prefix = f"tests/fixtures/skills_authoring/{slug}/"
    if slug == "skill-creator":
        raise ValueError("the creator cannot modify its own package")
    candidate.changes(baseline, policy.is_allowed)
    package_files = [file for file in candidate.files
                     if file.path.startswith(package_prefix)]
    fixture_files = [file for file in candidate.files
                     if file.path.startswith(fixture_prefix)]
    package_bytes = sum(len(file.data) for file in package_files)
    fixture_bytes = sum(len(file.data) for file in fixture_files)
    checks: list[dict] = []
    metadata: dict = {}

    def record(name: str, passed: bool, detail: str):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    record("package_file_count", 0 < len(package_files) <= MAX_PACKAGE_FILES,
           "package file count is within the catalog limit" if 0 < len(package_files) <= MAX_PACKAGE_FILES else "package must contain 1 to 128 files")
    record("package_size", package_bytes <= MAX_PACKAGE_BYTES,
           "package size is within the catalog limit" if package_bytes <= MAX_PACKAGE_BYTES else "package exceeds the 10 MiB catalog limit")
    oversized = [file.path for file in package_files if len(file.data) > MAX_TEXT_FILE_BYTES]
    record("text_file_size", not oversized,
           "all package text files are within the catalog limit" if not oversized else "one or more package files exceed 128 KiB")
    record("fixture_file_count", len(fixture_files) <= MAX_PACKAGE_FILES,
           "fixture file count is within the catalog limit" if len(fixture_files) <= MAX_PACKAGE_FILES else "fixture directory exceeds the 128-file limit")
    oversized_fixtures = [file.path for file in fixture_files
                          if len(file.data) > MAX_TEXT_FILE_BYTES]
    record("fixture_text_file_size", not oversized_fixtures,
           "all fixture text files are within the catalog limit" if not oversized_fixtures else "one or more fixture files exceed 128 KiB")
    record("fixture_size", fixture_bytes <= MAX_PACKAGE_BYTES,
           "fixture directory size is within the catalog limit" if fixture_bytes <= MAX_PACKAGE_BYTES else "fixture directory exceeds the 10 MiB catalog limit")
    record("required_files", {package_prefix + "SKILL.md", package_prefix + "mortimer.yaml"}.issubset({f.path for f in package_files}),
           "SKILL.md and mortimer.yaml are present" if {package_prefix + "SKILL.md", package_prefix + "mortimer.yaml"}.issubset({f.path for f in package_files}) else "SKILL.md and mortimer.yaml are required")
    nonstandard_modes = [file.path for file in package_files + fixture_files if file.mode != 0o644]
    record("non_executable_files", not nonstandard_modes,
           "package and fixture files are non-executable" if not nonstandard_modes else "skill packages and fixtures must not contain executable files")

    package_revision = ""
    if all(item["passed"] for item in checks):
        with tempfile.TemporaryDirectory(prefix="mortimer-skill-validation-") as tmp:
            package_root = Path(tmp) / slug
            package_root.mkdir()
            for file in package_files:
                relative = file.path[len(package_prefix):]
                target = package_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    content = file.data.decode("utf-8")
                except UnicodeError:
                    record("utf8_text", False, "all package files must be UTF-8 text")
                    break
                target.write_text(content, encoding="utf-8", newline="")
            else:
                try:
                    item = inspect_package(package_root, config_path=Path(tmp) / "disabled-skills.yaml")
                    skill, _problems = parse_skill(package_root / "SKILL.md")
                    package_revision = item.revision or ""
                    record("package_schema", item.installation == "installed" and bool(item.revision),
                           "strict package metadata, process graph, and package identity are valid" if item.revision else "strict package validation failed")
                    record("complete_instruction_body", skill is not None and bool(skill._body.strip()),
                           "the skill has a complete non-empty instruction body" if skill is not None and skill._body.strip() else "SKILL.md must contain a non-empty body after frontmatter")
                    declared = set(item.reference_paths)
                    present = {f.path[len(package_prefix):] for f in package_files}
                    missing = sorted(declared - present)
                    record("declared_references", not missing,
                           "all declared reference files are present" if not missing else "declared reference file is missing")
                    import yaml
                    metadata = yaml.safe_load((package_root / "mortimer.yaml").read_text(encoding="utf-8"))
                except (OSError, SkillPackageError, ValueError):
                    record("package_schema", False, "strict package metadata, process graph, or resource validation failed")
                    # The shared catalog validator deliberately rejects a
                    # missing/unsafe declared reference before returning its
                    # metadata. Preserve a distinct, deterministic receipt
                    # check for that failure rather than hiding it inside the
                    # broader schema result.
                    record("declared_references", False,
                           "declared package references are missing, unsafe, or could not be verified")

    source = metadata.get("source", {}) if isinstance(metadata, dict) else {}
    license_path = source.get("license_path") if isinstance(source, dict) else None
    license_name = source.get("license") if isinstance(source, dict) else None
    source_kind = source.get("kind") if isinstance(source, dict) else None
    package_names = {file.path[len(package_prefix):] for file in package_files}
    licensed = (
        isinstance(license_name, str) and bool(license_name)
        and isinstance(license_path, str) and license_path in package_names
    )
    license_ok = source_kind == "authored" or licensed
    if license_path is not None and license_path not in package_names:
        license_ok = False
    record("license_provenance", license_ok,
           "source license is declared and included when required" if license_ok else "adapted/imported content must include its declared license file and identifier")

    fixture_file = fixture_prefix + "matcher-cases.json"
    fixture_record = next((file for file in fixture_files if file.path == fixture_file), None)
    fixture_ids: set[str] = set()
    matcher_ok = False
    if fixture_record is not None:
        try:
            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON field")
                    result[key] = value
                return result

            payload = json.loads(fixture_record.data.decode("utf-8"), object_pairs_hook=unique_pairs)
            cases = payload.get("cases") if isinstance(payload, dict) and set(payload) == {"schema_version", "cases"} and payload.get("schema_version") == 1 else None
            if isinstance(cases, list) and 2 <= len(cases) <= 32:
                valid_cases = True
                outcomes: set[bool] = set()
                for case in cases:
                    if (not isinstance(case, dict) or set(case) != {"id", "request", "expect_selected"}
                            or not isinstance(case.get("id"), str)
                            or not isinstance(case.get("request"), str)
                            or not 1 <= len(case["request"].strip()) <= 1000
                            or type(case.get("expect_selected")) is not bool):
                        valid_cases = False
                        break
                    case_id = case["id"]
                    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case_id) or case_id in fixture_ids:
                        valid_cases = False
                        break
                    fixture_ids.add(case_id)
                    outcomes.add(case["expect_selected"])
                matcher_ok = valid_cases and outcomes == {False, True}
        except (UnicodeError, ValueError, TypeError, AttributeError):
            matcher_ok = False
    declared_ids = set(metadata.get("example_ids", [])) if isinstance(metadata, dict) else set()
    matcher_ok = matcher_ok and fixture_ids == declared_ids
    record("matcher_fixtures", matcher_ok,
           "fixture contains declared positive and negative matcher cases" if matcher_ok else "matcher-cases.json must contain 2–32 unique positive/negative cases matching manifest example_ids")

    required_tools = set(metadata.get("required_tools", [])) if isinstance(metadata, dict) else set()
    inventory = configured_tool_inventory()
    dependency_ok = not required_tools or (
        inventory.complete and inventory.names is not None and required_tools.issubset(inventory.names)
    )
    executable_or_dependency_files = [
        file.path for file in package_files
        if file.path.startswith(package_prefix + "scripts/")
        or Path(file.path).suffix.lower() in {".py", ".sh", ".js", ".ts", ".mjs", ".cjs"}
    ]
    dependency_ok = dependency_ok and not executable_or_dependency_files
    record("dependency_profile", dependency_ok,
           "declared tools are present in the static host inventory and the package has no executable dependencies" if dependency_ok else "required tools are unavailable/unverified or the package contains executable dependency files")

    baseline_registry = next((file.data for file in baseline.files
                              if file.path == "config/skills.yaml"), None)
    candidate_registry = next((file.data for file in candidate.files
                               if file.path == "config/skills.yaml"), None)
    registry_unchanged = baseline_registry is not None and candidate_registry == baseline_registry
    record("runtime_registry_unchanged", registry_unchanged,
           "candidate does not alter skill enablement or pinned revisions" if registry_unchanged else "the protected skill registry must remain unchanged")

    # Fixtures are inert reviewed examples. Enforce the same bounded text
    # profile as package files before decoding any fixture payload.
    fixture_ok = fixture_bytes <= MAX_PACKAGE_BYTES and len(fixture_files) <= MAX_PACKAGE_FILES
    for file in fixture_files:
        if len(file.data) > MAX_TEXT_FILE_BYTES:
            fixture_ok = False
            break
        try:
            file.data.decode("utf-8")
        except UnicodeError:
            fixture_ok = False
            break
    record("public_fixture_text", fixture_ok,
           "scoped fixtures are UTF-8 text" if fixture_ok else "fixtures must be UTF-8 text")

    # Bind the receipt to the immutable candidate identity and the exact
    # package bytes used by the validator. No model statement is evidence.
    return SkillAuthoringReceipt(
        slug=slug,
        candidate_digest=candidate.fingerprint,
        package_revision=package_revision,
        checked_files=len(package_files) + len(fixture_files),
        checked_bytes=package_bytes + sum(len(file.data) for file in fixture_files),
        checks=tuple(checks),
    )
