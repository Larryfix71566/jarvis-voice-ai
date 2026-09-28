"""Read-only, integrity-checked catalog for Agent Skills packages.

The catalog is descriptive: it never activates a package, reads a reference
into a prompt, or executes a bundled file. `config/skills.yaml` remains the
authority for runtime enablement.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from jarvis.agent_skills import (
    SKILLS_CONFIG,
    SKILLS_DIR,
    enabled_names,
    parse_skill,
    read_skill_registry,
)

MANIFEST = "mortimer.yaml"
MAX_PACKAGE_FILES = 128
MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_TEXT_FILE_BYTES = 128 * 1024
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_LEVEL_FIELDS = frozenset({
    "schema_version", "skill_id", "display_name", "category", "version",
    "source", "capabilities", "required_tools", "required_credentials",
    "reference_paths", "example_ids", "related_workflow_ids", "compatible_with",
    "process",
})
PROCESS_FIELDS = frozenset({"kind", "nodes"})
NODE_FIELDS = frozenset({
    "step_id", "title", "description", "inputs", "outputs", "tools",
    "approval", "success_criteria", "edges",
})


@dataclass(frozen=True)
class SkillCatalogEntry:
    skill_id: str
    display_name: str
    description: str
    category: str
    version: str | None
    revision: str | None
    installation: str
    enabled: bool
    readiness: str
    verification: str
    capabilities: tuple[str, ...]
    required_tools: tuple[str, ...]
    required_credentials: tuple[str, ...]
    reference_paths: tuple[str, ...]
    example_ids: tuple[str, ...]
    related_workflow_ids: tuple[str, ...]
    compatible_with: tuple[str, ...]
    process_kind: str | None
    process_nodes: tuple[dict, ...]
    source: dict
    blockers: tuple[str, ...]

    def as_dict(self) -> dict:
        value = asdict(self)
        value["process_nodes"] = list(self.process_nodes)
        value["blockers"] = list(self.blockers)
        return value


class SkillPackageError(ValueError):
    """Package is not safe or valid for catalog use."""


class _DuplicateManifestKey(ValueError):
    """Internal signal from the strict YAML constructor."""


def _string(value, field: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SkillPackageError(f"invalid_{field}")
    return value.strip()


def _string_list(value, field: str, *, optional: bool = False) -> list[str]:
    if value is None and optional:
        return []
    if not isinstance(value, list) or len(value) > 128:
        raise SkillPackageError(f"invalid_{field}")
    items = [_string(item, field, 128) for item in value]
    if len(items) != len(set(items)):
        raise SkillPackageError(f"duplicate_{field}")
    return items


def _validate_process(value) -> tuple[str | None, tuple[dict, ...]]:
    if value is None:
        return None, ()
    if not isinstance(value, dict) or set(value) - PROCESS_FIELDS:
        raise SkillPackageError("invalid_process")
    kind = value.get("kind")
    if kind not in {"linear", "branching", "guidance"}:
        raise SkillPackageError("invalid_process_kind")
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 32:
        raise SkillPackageError("invalid_process_nodes")
    normalized = []
    identifiers = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) - NODE_FIELDS:
            raise SkillPackageError("invalid_process_node")
        step_id = _string(node.get("step_id"), "step_id", 64)
        if not SLUG.fullmatch(step_id) or step_id in identifiers:
            raise SkillPackageError("invalid_process_step_id")
        identifiers.add(step_id)
        normalized.append({
            "step_id": step_id,
            "title": _string(node.get("title"), "step_title", 120),
            "description": _string(node.get("description"), "step_description", 1200),
            "inputs": _string_list(node.get("inputs", []), "step_inputs"),
            "outputs": _string_list(node.get("outputs", []), "step_outputs"),
            "tools": _string_list(node.get("tools", []), "step_tools"),
            "approval": _string(node["approval"], "step_approval", 600)
                         if node.get("approval") is not None else None,
            "success_criteria": _string_list(node.get("success_criteria", []), "success_criteria"),
            "edges": node.get("edges", []),
        })
        if not isinstance(normalized[-1]["edges"], list) or len(normalized[-1]["edges"]) > 32:
            raise SkillPackageError("invalid_process_edges")
        for edge in normalized[-1]["edges"]:
            if not isinstance(edge, dict) or set(edge) - {"to", "condition"}:
                raise SkillPackageError("invalid_process_edge")
            _string(edge.get("to"), "edge_target", 64)
            if edge.get("condition") is not None:
                _string(edge["condition"], "edge_condition", 240)

    by_id = {node["step_id"]: node for node in normalized}
    for node in normalized:
        for edge in node["edges"]:
            if edge["to"] not in by_id:
                raise SkillPackageError("unknown_process_edge_target")
    if kind == "linear":
        order = [node["step_id"] for node in normalized]
        expected = [
            ([] if index + 1 == len(order) else [{"to": order[index + 1]}])
            for index in range(len(order))
        ]
        if any(node["edges"] != edges for node, edges in zip(normalized, expected)):
            raise SkillPackageError("nonlinear_edges_in_linear_process")
    else:
        visiting, visited = set(), set()

        def visit(step_id):
            if step_id in visiting:
                raise SkillPackageError("cyclic_process")
            if step_id in visited:
                return
            visiting.add(step_id)
            for edge in by_id[step_id]["edges"]:
                visit(edge["to"])
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in by_id:
            visit(step_id)
    return kind, tuple(normalized)


def _manifest(path: Path, skill_id: str) -> dict:
    if path.is_symlink():
        raise SkillPackageError("unsafe_manifest_path")
    if not path.exists():
        return {}
    if not path.is_file():
        raise SkillPackageError("unsafe_manifest_path")
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        raise SkillPackageError("manifest_too_large")
    try:
        import yaml
        class UniqueKeyLoader(yaml.SafeLoader):
            """Reject ambiguous YAML mappings rather than silently overriding."""

        def construct_unique_mapping(loader, node, deep=False):
            loader.flatten_mapping(node)
            mapping = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node, deep=deep)
                try:
                    duplicate = key in mapping
                except TypeError:
                    raise _DuplicateManifestKey("unhashable manifest key") from None
                if duplicate:
                    raise _DuplicateManifestKey("duplicate manifest key")
                mapping[key] = loader.construct_object(value_node, deep=deep)
            return mapping

        UniqueKeyLoader.add_constructor(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            construct_unique_mapping,
        )
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except _DuplicateManifestKey:
        raise SkillPackageError("duplicate_manifest_key") from None
    except Exception as exc:  # noqa: BLE001 - expose only a bounded reason code
        raise SkillPackageError(f"manifest_unreadable_{type(exc).__name__[:40]}") from None
    if not isinstance(data, dict) or set(data) - TOP_LEVEL_FIELDS:
        raise SkillPackageError("unknown_manifest_fields")
    if data.get("schema_version") != 1:
        raise SkillPackageError("unsupported_manifest_schema")
    if data.get("skill_id") != skill_id:
        raise SkillPackageError("manifest_skill_id_mismatch")
    _string(data.get("display_name"), "display_name", 120)
    _string(data.get("category"), "category", 40)
    _string(data.get("version"), "version", 80)
    source = data.get("source")
    if not isinstance(source, dict) or set(source) - {
        "kind", "reference", "immutable_revision", "license", "license_path",
        "source_digest", "adaptation_notes",
    }:
        raise SkillPackageError("invalid_source_provenance")
    _string(source.get("kind"), "source_kind", 40)
    for key, limit in (("reference", 512), ("immutable_revision", 128), ("license", 120),
                       ("license_path", 512), ("source_digest", 64), ("adaptation_notes", 1200)):
        if source.get(key) is not None:
            _string(source[key], f"source_{key}", limit)
    for key in ("capabilities", "required_tools", "required_credentials",
                "reference_paths", "example_ids", "related_workflow_ids", "compatible_with"):
        _string_list(data.get(key, []), key, optional=True)
    for ref in data.get("reference_paths", []):
        reference = PurePosixPath(ref)
        if ("\x00" in ref or "\\" in ref or reference.is_absolute()
                or reference.as_posix() != ref
                or any(part in {"", ".", ".."} for part in reference.parts)
                or reference.parts[0] in {"SKILL.md", MANIFEST}
                or reference.suffix.lower() not in {".md", ".txt"}):
            raise SkillPackageError("unsafe_reference_path")
    process_kind, process_nodes = _validate_process(data.get("process"))
    data["_process_kind"] = process_kind
    data["_process_nodes"] = process_nodes
    return data


def _package_digest(root: Path) -> str:
    resolved_root = root.resolve(strict=True)
    paths = []
    total = 0
    folded = set()
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(dirs):
            child = current_path / name
            if child.is_symlink():
                raise SkillPackageError("symlink_in_package")
        for name in files:
            path = current_path / name
            if path.is_symlink():
                raise SkillPackageError("symlink_in_package")
            if not path.is_file():
                raise SkillPackageError("unsafe_package_file")
            try:
                relative = path.resolve(strict=True).relative_to(resolved_root).as_posix()
            except (OSError, ValueError):
                raise SkillPackageError("package_path_escape") from None
            if relative.casefold() in folded:
                raise SkillPackageError("case_colliding_package_paths")
            folded.add(relative.casefold())
            size = path.stat().st_size
            total += size
            if total > MAX_PACKAGE_BYTES or len(paths) >= MAX_PACKAGE_FILES:
                raise SkillPackageError("package_size_limit")
            if path.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".txt", ".py", ".sh", ".js", ".ts"} and size > MAX_TEXT_FILE_BYTES:
                raise SkillPackageError("text_file_size_limit")
            paths.append((relative, path))
    if "SKILL.md" not in {name for name, _ in paths}:
        raise SkillPackageError("missing_skill_file")
    digest = hashlib.sha256()
    for name, path in sorted(paths):
        encoded_name = name.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def inspect_package(
    directory: Path, config_path: Path | None = None,
) -> SkillCatalogEntry:
    """Inspect one immediate skill package and return safe catalog metadata."""
    if directory.is_symlink() or not directory.is_dir() or not SLUG.fullmatch(directory.name):
        raise SkillPackageError("invalid_skill_directory")
    digest = _package_digest(directory)
    skill_path = directory / "SKILL.md"
    skill, _problems = parse_skill(skill_path)
    if skill is None:
        raise SkillPackageError("invalid_skill_instructions")
    if skill.name != directory.name:
        raise SkillPackageError("skill_directory_name_mismatch")
    metadata = _manifest(directory / MANIFEST, skill.name)
    _validate_declared_references(directory, metadata.get("reference_paths", []))
    enabled = skill.name in enabled_names(config_path or SKILLS_CONFIG)
    process_kind = metadata.get("_process_kind")
    process_nodes = metadata.get("_process_nodes", ())
    blockers = []
    if not metadata:
        blockers.append("reviewed_process_metadata_missing")
    if skill.has_scripts:
        blockers.append("bundled_scripts_are_not_available")
    return SkillCatalogEntry(
        skill_id=skill.name,
        display_name=metadata.get("display_name", skill.name.replace("-", " ").title()),
        description=skill.description,
        category=metadata.get("category", "general"),
        version=metadata.get("version"),
        revision=digest,
        installation="installed",
        enabled=enabled,
        readiness="blocked" if blockers else "unknown",
        verification="not_tested",
        capabilities=tuple(metadata.get("capabilities", [])),
        required_tools=tuple(metadata.get("required_tools", [])),
        required_credentials=tuple(metadata.get("required_credentials", [])),
        reference_paths=tuple(metadata.get("reference_paths", [])),
        example_ids=tuple(metadata.get("example_ids", [])),
        related_workflow_ids=tuple(metadata.get("related_workflow_ids", [])),
        compatible_with=tuple(metadata.get("compatible_with", [])),
        process_kind=process_kind,
        process_nodes=process_nodes,
        source=metadata.get("source", {"kind": "unknown"}),
        blockers=tuple(blockers),
    )


def _validate_declared_references(directory: Path, references: list[str]) -> None:
    """Reject manifest references that the bounded reader cannot serve.

    Keeping declaration validation at package inspection time means the
    catalog never advertises a reference as available when it is missing,
    non-text, non-canonical, or points at a directory. Symlinks anywhere in
    the package have already been rejected by ``_package_digest``.
    """
    root = directory.resolve(strict=True)
    for reference in references:
        candidate = directory.joinpath(*PurePosixPath(reference).parts)
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(root).as_posix()
        except (OSError, ValueError):
            raise SkillPackageError("declared_reference_missing_or_unsafe") from None
        if relative != reference or not candidate.is_file():
            raise SkillPackageError("declared_reference_missing_or_unsafe")


def list_catalog(
    directory: Path | None = None, config_path: Path | None = None,
) -> list[SkillCatalogEntry]:
    """Return valid immediate packages; invalid packages fail independently."""
    root = directory or SKILLS_DIR
    if not root.exists():
        return []
    entries = []
    for package in sorted(root.iterdir(), key=lambda path: path.name):
        if not SLUG.fullmatch(package.name):
            continue
        try:
            entries.append(inspect_package(package, config_path=config_path))
        except (OSError, SkillPackageError) as exc:
            entries.append(SkillCatalogEntry(
                skill_id=package.name,
                display_name=package.name.replace("-", " ").title(),
                description="This skill package needs attention before use.",
                category="general", revision=None, installation="invalid",
                version=None, capabilities=(), required_tools=(), required_credentials=(),
                reference_paths=(), example_ids=(), related_workflow_ids=(), compatible_with=(),
                enabled=False, readiness="blocked", verification="not_tested",
                process_kind=None, process_nodes=(), source={"kind": "unknown"},
                blockers=(str(exc) if isinstance(exc, SkillPackageError) else "package_unreadable",),
            ))
        except Exception:  # noqa: BLE001 — one invalid package must not hide others
            entries.append(SkillCatalogEntry(
                skill_id=package.name,
                display_name=package.name.replace("-", " ").title(),
                description="This skill package needs attention before use.",
                category="general", revision=None, installation="invalid",
                version=None, capabilities=(), required_tools=(), required_credentials=(),
                reference_paths=(), example_ids=(), related_workflow_ids=(), compatible_with=(),
                enabled=False, readiness="blocked", verification="not_tested",
                process_kind=None, process_nodes=(), source={"kind": "unknown"},
                blockers=("invalid_package_metadata",),
            ))
    return entries


def validate_skill_inventory(
    directory: Path | None = None, config_path: Path | None = None,
) -> list[str]:
    """Return safe structural and active-pin errors for the local skill set.

    Legacy skills without ``mortimer.yaml`` remain valid. When a strict v2
    registry is configured, every enabled package must exist, validate, and
    match its exact configured digest even when runtime enforcement is still
    disabled during rollout.
    """
    root = directory or SKILLS_DIR
    entries = list_catalog(root, config_path=config_path)
    names, pins, version, registry_valid = read_skill_registry(config_path)
    issues: list[str] = []
    if not registry_valid:
        issues.append("registry: invalid or unavailable")

    if root.exists():
        for package in root.iterdir():
            if (package.is_dir() or package.is_symlink()) and not SLUG.fullmatch(package.name):
                issues.append(f"{package.name}: invalid_skill_directory")

    by_id = {entry.skill_id: entry for entry in entries}
    for entry in entries:
        if entry.installation != "installed":
            reason = entry.blockers[0] if entry.blockers else "invalid_package"
            issues.append(f"{entry.skill_id}: {reason}")

    if registry_valid and version == 2 and pins is not None:
        for skill_id in names:
            entry = by_id.get(skill_id)
            if entry is None:
                issues.append(f"{skill_id}: enabled_package_missing")
            elif entry.installation != "installed":
                continue
            elif pins.get(skill_id) != entry.revision:
                issues.append(f"{skill_id}: revision_pin_mismatch")

    return issues
