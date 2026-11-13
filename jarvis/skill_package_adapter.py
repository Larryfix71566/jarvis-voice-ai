"""Offline, inert adapter for already-P0-compatible instruction packages.

WS-03 (2026-10-22 claim). The adapter never executes, imports, fetches or
writes anything. It returns an unregistered, non-materialized, non-loadable
package payload plus a content-free report. It never emits a ready, approved
or active state: every readiness question stays an explicit unknown.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

from jarvis.agent_skills import _split_frontmatter, read_skill_registry
from jarvis.skill_authoring_validation import SkillAuthoringReceipt, validate_skill_candidate
from jarvis.skill_catalog import (
    MANIFEST, MAX_PACKAGE_BYTES, MAX_PACKAGE_FILES, MAX_TEXT_FILE_BYTES, SLUG, TOP_LEVEL_FIELDS,
)
from jarvis.skill_compatibility import (
    NAME_MAX_CHARS, REASONS, RESERVED_WORDS, _StrictLoader, load_frontmatter,
)
from jarvis.skill_service import ToolInventory, configured_tool_inventory
from sandbox.artifacts import (
    SECRET, Candidate, File, SandboxError, check_paths, path_key, source_path_allowed,
)

KIND = "skill_package_compatibility"
SCHEMA_VERSION = 1
ADAPTER_VERSION = "p0-text-v1"
DEFAULT_PROFILE = "p0-instruction-text"
SUPPORTED_PROFILES = frozenset({DEFAULT_PROFILE})
CANCEL_STAGES = ("after_input_checks", "before_validation", "after_validation", "before_return")
DISPOSITIONS = ("supported_unchanged", "explicit_inert_annotation", "unsupported", "unknown")
UNKNOWNS = ("authentication_unknown", "tool_session_unknown",
            "source_privacy_compatibility_unknown", "runtime_readiness_unknown")
OUTCOME_PRODUCED = "package_payload_produced"
OUTCOME_BLOCKED = "blocked"
SIDECAR_NAME = MANIFEST
MATCHER_NAME = "matcher-cases.json"
PROVENANCE_KIND = "imported"
VALIDATOR_CHECKS = (
    "package_file_count", "package_size", "text_file_size", "fixture_file_count",
    "fixture_text_file_size", "fixture_size", "required_files", "non_executable_files", "utf8_text",
    "package_schema", "complete_instruction_body", "declared_references", "license_provenance",
    "matcher_fixtures", "dependency_profile", "runtime_registry_unchanged", "public_fixture_text")
PARSER_DEPENDENCIES = (
    ("jarvis/agent_skills.py", "jarvis.agent_skills"),
    ("jarvis/selfedit/skill_policy.py", "jarvis.selfedit.skill_policy"),
    ("jarvis/skill_authoring_validation.py", "jarvis.skill_authoring_validation"),
    ("jarvis/skill_catalog.py", "jarvis.skill_catalog"),
    ("jarvis/skill_compatibility.py", "jarvis.skill_compatibility"),
    ("jarvis/skill_service.py", "jarvis.skill_service"),
    ("sandbox/artifacts.py", "sandbox.artifacts"),
)
IDENTITY_FIELDS = ("source_digest", "inputs_digest", "baseline_digest", "candidate_digest",
                   "validation_snapshot_digest", "parser_fingerprint", "inventory_digest")

_PATH_CHECK_PREFIX = "skills/package/"
_METADATA_KNOWN = frozenset({"agent", "source", "concept_from", "promoted_successes", "promoted_failures"})
_HOST_CONTROL_KEYS = frozenset({
    "allowed-tools", "disable-model-invocation", "user-invocable", "argument-hint", "model", "hooks",
    "context", "agent", "license", "compatibility", "version", "when_to_use", "paths", "shell",
    "effort", "mode"})
_SIDECAR_DESCRIPTIVE = frozenset({"display_name", "category", "version", "related_workflow_ids",
                                  "compatible_with"})
_SOURCE_KEYS = frozenset({"kind", "reference", "immutable_revision", "license", "license_path",
                          "source_digest", "adaptation_notes"})
_YAML_LEVEL_CODES = frozenset({
    "frontmatter_too_large", "frontmatter_invalid_yaml", "frontmatter_complexity_limit",
    "frontmatter_yaml_features_unsupported", "frontmatter_duplicate_key"})
_NAME_CODES = frozenset({"name_required_string", "name_too_long", "name_invalid_slug", "name_reserved"})
_DESCRIPTION_CODES = frozenset({"description_required_string", "description_too_long"})
_METADATA_CODES = frozenset({"metadata_not_mapping", "metadata_string_required",
                             "metadata_string_too_long", "metadata_integer_required"})
_EXECUTABLE_SUFFIXES = frozenset({
    ".py", ".pyc", ".pyo", ".sh", ".bash", ".zsh", ".fish", ".command", ".js", ".mjs", ".cjs", ".ts",
    ".tsx", ".jsx", ".rb", ".pl", ".php", ".lua", ".ps1", ".psm1", ".bat", ".cmd", ".exe", ".dll",
    ".so", ".dylib", ".bin", ".app", ".class", ".wasm", ".applescript", ".scpt", ".jar"})
_ARCHIVE_SUFFIXES = frozenset({
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz", ".zst", ".7z", ".rar", ".whl",
    ".egg", ".jar", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".skill"})
_ARCHIVE_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c",
                  b"Rar!\x1a\x07", b"\xfd7zXZ\x00", b"\x28\xb5\x2f\xfd")
_DEPENDENCY_NAMES = frozenset({
    "requirements.txt", "requirements-dev.txt", "constraints.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "pipfile", "pipfile.lock", "poetry.lock", "uv.lock", "package.json",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "gemfile", "gemfile.lock",
    "cargo.toml", "cargo.lock", "go.mod", "go.sum", "composer.json", "makefile", "dockerfile",
    ".mcp.json", "mcp.json", "plugin.json"})
_UNKNOWN_CODES = frozenset({
    "undeclared_source_file", "frontmatter_key_unrecognized", "frontmatter_metadata_key_unrecognized",
    "sidecar_field_unrecognized", "skill_file_missing", "license_file_missing",
    "declared_reference_missing", "inventory_incomplete"})

BLOCKER_CODES = frozenset({
    "schema_version_unsupported", "profile_unsupported", "slug_invalid", "slug_reserved",
    "source_file_count_exceeded", "source_aggregate_size_exceeded", "source_file_size_exceeded",
    "reviewed_input_size_exceeded", "reviewed_input_aggregate_size_exceeded",
    "package_file_count_exceeded", "package_aggregate_size_exceeded",
    "path_invalid", "path_forbidden", "hidden_path_refused", "path_collision",
    "file_directory_collision", "symlink_record_refused", "mode_forbidden", "secret_detected",
    "utf8_invalid", "binary_content_refused", "archive_record_refused", "shebang_refused",
    "scripts_path_refused", "executable_suffix_refused", "dependency_manifest_refused",
    "source_sidecar_conflict", "undeclared_source_file",
    "skill_file_missing", "sidecar_missing", "matcher_cases_missing", "license_file_missing",
    "declared_reference_missing", "reference_path_invalid", "reference_suffix_unsupported",
    "license_path_invalid", "license_suffix_unsupported",
    "sidecar_unreadable", "sidecar_not_mapping", "sidecar_schema_unsupported",
    "sidecar_skill_id_mismatch", "sidecar_field_unrecognized", "sidecar_reference_paths_invalid",
    "sidecar_required_tools_invalid", "required_credentials_unsupported", "provenance_missing",
    "provenance_kind_unsupported", "provenance_reference_missing", "provenance_revision_missing",
    "provenance_source_digest_mismatch", "license_identifier_missing", "license_path_missing",
    "skill_frontmatter_incompatible", "frontmatter_control_unsupported",
    "frontmatter_key_unrecognized", "frontmatter_metadata_key_unrecognized",
    "skill_name_slug_mismatch", "frontmatter_missing", "frontmatter_not_mapping",
    "inventory_incomplete", "inventory_changed", "inventory_read_failed",
    "required_tool_not_in_inventory",
    "baseline_registry_missing", "baseline_registry_invalid", "slug_exists_in_registry",
    "slug_exists_in_baseline_package", "slug_exists_in_baseline_fixtures", "baseline_changed",
    "payload_construction_refused", "validation_snapshot_refused", "validator_scope_refused",
    "validator_staging_failed", "validator_failed", "receipt_binding_mismatch", "validation_failed",
    "validation_unrecognized_check_failed", "validation_check_unrecognized",
    "parser_fingerprint_unavailable", "adapter_code_unavailable", "adapter_internal_error",
    "cancelled", "cancel_check_failed",
}) | REASONS | frozenset(f"validation_{n}_failed" for n in VALIDATOR_CHECKS)

_SCOPE_ORDER = ("source_file", "source_file_set", "reviewed_input", "declared_file", "frontmatter",
                "frontmatter_metadata", "sidecar_field", "required_tool")
_PAYLOAD_ROLES = frozenset({"skill_file", "license", "reference"})
_INVALID = "invalid adapter input"


@dataclass(frozen=True)
class ReviewedInputs:
    sidecar: bytes | None
    matcher_cases: bytes | None


@dataclass(frozen=True)
class EvidenceEntry:
    ordinal: int
    path: str
    mode: int
    size: int
    sha256: str


@dataclass(frozen=True)
class SourceEvidence:
    records: tuple[File, ...]
    inventory: tuple[EvidenceEntry, ...]
    sidecar: bytes | None
    matcher_cases: bytes | None


@dataclass(frozen=True)
class PackagePayload:
    slug: str
    files: tuple[File, ...]
    digest: str


@dataclass(frozen=True)
class AdapterResult:
    report_json: bytes
    payload: PackagePayload | None
    test_requirements: tuple[File, ...]
    evidence: SourceEvidence | None

    @property
    def report(self) -> dict:
        return json.loads(self.report_json)

    @property
    def produced(self) -> bool:
        return self.payload is not None


@dataclass
class _Rec:
    ordinal: int
    file: File
    key: str | None
    sha256: str
    codes: set
    role: str = "unclassified"


@dataclass
class _Row:
    scope: str
    ordinal: int
    label: str
    default: str
    codes: set
    size: int | None = None
    sha256: str | None = None


# ---------------------------------------------------------------- digests

def _domain(name: str) -> bytes:
    return b"mortimer.skill_package_compatibility\x00v1\x00" + name.encode("ascii") + b"\x00"


def _field(h, value: bytes) -> None:
    h.update(len(value).to_bytes(8, "big"))
    h.update(value)


def _enc(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def _canonical_order(records) -> list:
    return sorted(records, key=lambda f: (_enc(f.path), str(f.mode).encode("ascii"),
                                          hashlib.sha256(f.data).digest()))


def _canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _dependency_bytes(module_name: str) -> bytes | None:
    try:
        return Path(importlib.import_module(module_name).__file__).read_bytes()
    except (ImportError, AttributeError, TypeError, OSError):
        return None


def _adapter_code_bytes() -> bytes | None:
    try:
        return Path(__file__).read_bytes()
    except OSError:
        return None


def _check_source_files(source_files) -> None:
    if type(source_files) not in (tuple, list):
        raise TypeError(_INVALID)
    for f in source_files:
        if (type(f) is not File or type(f.path) is not str or type(f.mode) is not int
                or type(f.data) is not bytes):
            raise TypeError(_INVALID)


def _source_digest(records: Sequence[File]) -> str:
    h = hashlib.sha256(_domain("source"))
    h.update(len(records).to_bytes(8, "big"))
    for f in _canonical_order(records):
        _field(h, _enc(f.path))
        _field(h, str(f.mode).encode("ascii"))
        _field(h, f.data)
    return h.hexdigest()


def compute_source_digest(source_files: Sequence[File]) -> str:
    _check_source_files(source_files)
    return _source_digest(source_files)


def _inputs_digest(slug: str, profile: str, sidecar: bytes | None, matcher: bytes | None) -> str:
    h = hashlib.sha256(_domain("inputs"))
    _field(h, _enc(slug))
    _field(h, _enc(profile))
    _field(h, ADAPTER_VERSION.encode())
    for name, data in ((SIDECAR_NAME, sidecar), (MATCHER_NAME, matcher)):
        _field(h, name.encode())
        if data is None:
            _field(h, b"absent")
        else:
            _field(h, b"present")
            _field(h, data)
    return h.hexdigest()


def _parser_fingerprint() -> tuple[str, bool]:
    h = hashlib.sha256(_domain("parser"))
    h.update(len(PARSER_DEPENDENCIES).to_bytes(8, "big"))
    available = True
    for label, module in PARSER_DEPENDENCIES:
        _field(h, label.encode("ascii"))
        content = _dependency_bytes(module)
        if content is None:
            _field(h, b"unavailable")
            available = False
        else:
            _field(h, b"sha256")
            _field(h, hashlib.sha256(content).digest())
    return h.hexdigest(), available


def _inventory_digest(before, after) -> str:
    h = hashlib.sha256(_domain("inventory"))
    for phase, facts in (("before", before), ("after", after)):
        _field(h, phase.encode())
        if facts is None:
            _field(h, b"not_observed")
            continue
        complete, names = facts
        _field(h, b"complete" if complete else b"incomplete")
        if names is None:
            _field(h, b"names_unavailable")
        else:
            _field(h, b"names")
            h.update(len(names).to_bytes(8, "big"))
            for n in sorted(names):
                _field(h, _enc(n))
    return h.hexdigest()


def report_digest(report: Mapping[str, object]) -> str:
    body = {k: v for k, v in dict(report).items() if k != "report_digest"}
    return hashlib.sha256(_domain("report") + _canonical_json(body)).hexdigest()


def evidence_reusable(previous: Mapping[str, object], current: Mapping[str, object]) -> bool:
    if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
        return False
    try:
        for report in (previous, current):
            if report.get("kind") != KIND:
                return False
            version = report.get("schema_version")
            if type(version) is not int or version != SCHEMA_VERSION:
                return False
            if report.get("adapter_version") != ADAPTER_VERSION:
                return False
            claimed = report.get("report_digest")
            if not isinstance(claimed, str) or claimed != report_digest(report):
                return False
        for name in IDENTITY_FIELDS:
            if name not in previous or name not in current or previous[name] != current[name]:
                return False
        pv, cv = previous.get("validation"), current.get("validation")
        if not isinstance(pv, Mapping) or not isinstance(cv, Mapping):
            return False
        for name in ("adapter_code_digest", "profile"):
            if name not in pv or name not in cv or pv[name] != cv[name]:
                return False
    except (TypeError, ValueError):
        return False
    return True


# ---------------------------------------------------------------- helpers

def _shebang(data: bytes) -> bool:
    body = data[3:] if data.startswith(b"\xef\xbb\xbf") else data
    return body.lstrip(b" \t\r\n\x0b\x0c").startswith(b"#!")


def _disposition(default: str, codes) -> str:
    if not codes:
        return default
    return "unknown" if set(codes) <= _UNKNOWN_CODES else "unsupported"


def _read_inventory():
    try:
        inv = configured_tool_inventory()
    except Exception:
        return (False, None), True
    if (type(inv) is not ToolInventory or type(inv.complete) is not bool
            or (inv.names is not None and (not isinstance(inv.names, frozenset)
                                           or any(type(n) is not str for n in inv.names)))):
        return (False, None), True
    return (inv.complete, inv.names), False


def _declared_path_codes(ref: str, license_kind: bool) -> set:
    codes = set()
    pure = PurePosixPath(ref)
    parts = ref.split("/")
    if ("\x00" in ref or "\\" in ref or not ref or pure.is_absolute() or pure.as_posix() != ref
            or any(x in {"", ".", ".."} for x in parts) or parts[0] in {"SKILL.md", MANIFEST}):
        codes.add("license_path_invalid" if license_kind else "reference_path_invalid")
    if pure.suffix.lower() not in {".md", ".txt"}:
        codes.add("license_suffix_unsupported" if license_kind else "reference_suffix_unsupported")
    if any(part.casefold() == "scripts" for part in parts):
        codes.add("scripts_path_refused")
    return codes


def _yaml_mapping(text: str):
    return yaml.load(text, Loader=_StrictLoader)


_YAML_ERRORS = (yaml.YAMLError, ValueError, RecursionError, OverflowError, TypeError)


# ---------------------------------------------------------------- adapter

def adapt_instruction_package(
    source_files: Sequence[File], *, reviewed_inputs: ReviewedInputs, baseline: Candidate,
    slug: str, profile: str = DEFAULT_PROFILE, schema_version: object = SCHEMA_VERSION,
    cancel_check: Callable[[], bool] | None = None,
) -> AdapterResult:
    # 1. Types
    _check_source_files(source_files)
    if (type(reviewed_inputs) is not ReviewedInputs
            or any(v is not None and type(v) is not bytes
                   for v in (reviewed_inputs.sidecar, reviewed_inputs.matcher_cases))
            or type(baseline) is not Candidate or type(slug) is not str or type(profile) is not str
            or (cancel_check is not None and not callable(cancel_check))):
        raise TypeError(_INVALID)

    sidecar = reviewed_inputs.sidecar
    matcher = reviewed_inputs.matcher_cases
    agg: set = set()
    state = {"cancelled": None}

    def _cancel(stage: str) -> bool:
        if cancel_check is None or state["cancelled"] is not None:
            return state["cancelled"] is not None
        try:
            value = cancel_check()
        except Exception:
            agg.update({"cancel_check_failed", "cancelled"})
            state["cancelled"] = stage
            return True
        if type(value) is not bool:
            agg.update({"cancel_check_failed", "cancelled"})
            state["cancelled"] = stage
            return True
        if value:
            agg.add("cancelled")
            state["cancelled"] = stage
            return True
        return False

    # 2. Identities
    records = _canonical_order(source_files)
    recs = [_Rec(i, f, None, hashlib.sha256(f.data).hexdigest(), set()) for i, f in enumerate(records)]
    source_digest = _source_digest(records)
    inputs_digest = _inputs_digest(slug, profile, sidecar, matcher)
    baseline_digest = baseline.fingerprint
    parser_fingerprint, parser_ok = _parser_fingerprint()
    if not parser_ok:
        agg.add("parser_fingerprint_unavailable")
    code_bytes = _adapter_code_bytes()
    if code_bytes is None:
        adapter_code_digest = None
        agg.add("adapter_code_unavailable")
    else:
        adapter_code_digest = hashlib.sha256(code_bytes).hexdigest()
    total = sum(len(f.data) for f in records)

    rows: list[_Row] = []

    # 3. Request checks
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        agg.add("schema_version_unsupported")
    if profile not in SUPPORTED_PROFILES:
        agg.add("profile_unsupported")
    slug_ok = bool(SLUG.fullmatch(slug)) and len(slug) <= NAME_MAX_CHARS
    if not slug_ok:
        agg.add("slug_invalid")
    if slug_ok and (slug == "skill-creator" or any(w in slug for w in RESERVED_WORDS)):
        agg.add("slug_reserved")
        slug_ok = False

    # 4. Caps
    caps_ok = True
    count_exceeded = len(records) > MAX_PACKAGE_FILES
    set_row = None
    if count_exceeded:
        caps_ok = False
        set_row = _Row("source_file_set", 0, "source_files", "unknown",
                       {"source_file_count_exceeded"}, total, None)
        rows.append(set_row)
    if total > MAX_PACKAGE_BYTES:
        agg.add("source_aggregate_size_exceeded")
        caps_ok = False
    if not count_exceeded:
        for rec in recs:
            if len(rec.file.data) > MAX_TEXT_FILE_BYTES:
                rec.codes.add("source_file_size_exceeded")
                caps_ok = False
    rev_rows = []
    present_total = 0
    for ordinal, (label, data, missing_code) in enumerate(
            (("sidecar", sidecar, "sidecar_missing"), ("matcher_cases", matcher, "matcher_cases_missing"))):
        row = _Row("reviewed_input", ordinal, label, "supported_unchanged", set(),
                   None if data is None else len(data),
                   None if data is None else hashlib.sha256(data).hexdigest())
        if data is None:
            row.codes.add(missing_code)
        else:
            present_total += len(data)
            if len(data) > MAX_TEXT_FILE_BYTES:
                row.codes.add("reviewed_input_size_exceeded")
                caps_ok = False
        rev_rows.append(row)
        rows.append(row)
    if present_total > MAX_PACKAGE_BYTES:
        agg.add("reviewed_input_aggregate_size_exceeded")
        caps_ok = False

    # 5. Bounded scan
    secret_found = False
    if caps_ok:
        if SECRET.search(_enc(slug)):
            agg.add("secret_detected")
            secret_found = True
        for row, data in zip(rev_rows, (sidecar, matcher)):
            if data is None:
                continue
            if SECRET.search(data):
                row.codes.add("secret_detected")
                secret_found = True
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                row.codes.add("utf8_invalid")
            if b"\x00" in data:
                row.codes.add("binary_content_refused")
            if _shebang(data):
                row.codes.add("shebang_refused")
        for rec in recs:
            p = rec.file.path
            data = rec.file.data
            try:
                rec.key = path_key(p)
            except (SandboxError, UnicodeError):
                rec.codes.add("path_invalid")
            if rec.key:
                parts = rec.key.split("/")
                if not source_path_allowed(_PATH_CHECK_PREFIX + p):
                    rec.codes.add("path_forbidden")
                if any(part.startswith(".") for part in parts):
                    rec.codes.add("hidden_path_refused")
                if "scripts" in parts:
                    rec.codes.add("scripts_path_refused")
                if parts[-1] in _DEPENDENCY_NAMES:
                    rec.codes.add("dependency_manifest_refused")
                suffix = PurePosixPath(parts[-1]).suffix
                if suffix in _EXECUTABLE_SUFFIXES:
                    rec.codes.add("executable_suffix_refused")
                if suffix in _ARCHIVE_SUFFIXES:
                    rec.codes.add("archive_record_refused")
                if rec.key == "mortimer.yaml" or rec.key.startswith("mortimer.yaml/"):
                    rec.codes.add("source_sidecar_conflict")
            elif any(part.casefold() == "scripts" for part in p.split("/")):
                rec.codes.add("scripts_path_refused")
            mode = rec.file.mode
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                rec.codes.add("symlink_record_refused")
            elif mode != 0o644:
                rec.codes.add("mode_forbidden")
            if SECRET.search(data) or SECRET.search(_enc(p)):
                rec.codes.add("secret_detected")
                secret_found = True
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                rec.codes.add("utf8_invalid")
            if b"\x00" in data:
                rec.codes.add("binary_content_refused")
            if data.startswith(_ARCHIVE_MAGIC) or (len(data) >= 262 and data[257:262] == b"ustar"):
                rec.codes.add("archive_record_refused")
            if _shebang(data):
                rec.codes.add("shebang_refused")

        # Collisions
        keyed = [r for r in recs if r.key]
        groups: dict = {}
        for r in keyed:
            groups.setdefault(r.key, []).append(r)
        for members in groups.values():
            if len(members) > 1:
                for r in members:
                    r.codes.add("path_collision")
        spellings: dict = {}
        members_by_dir: dict = {}
        for r in keyed:
            segs = r.file.path.split("/")
            for n in range(1, len(segs)):
                raw = "/".join(segs[:n])
                try:
                    k = path_key(raw)
                except (SandboxError, UnicodeError):
                    continue
                spellings.setdefault(k, set()).add(raw)
                members_by_dir.setdefault(k, []).append(r)
        for k, spelled in spellings.items():
            if len(spelled) > 1:
                for r in members_by_dir[k]:
                    r.codes.add("path_collision")
        for k, members in members_by_dir.items():
            if k in groups:
                for r in members + groups[k]:
                    r.codes.add("file_directory_collision")
        if len(keyed) == len(recs) and not any(
                c in r.codes for r in recs for c in ("path_collision", "file_directory_collision")):
            try:
                check_paths([r.file.path for r in recs])
            except SandboxError:
                agg.add("path_collision")

    # 6.
    _cancel("after_input_checks")

    # 7. Semantic stage
    required_tools = None
    sidecar_parsed = False
    if caps_ok and not secret_found and state["cancelled"] is None:
        locals_out: dict = {}
        try:
            _semantic_stage(recs, rows, rev_rows[0], sidecar, slug, slug_ok, source_digest, baseline,
                            agg, locals_out)
            required_tools = locals_out.get("required_tools")
            sidecar_parsed = locals_out.get("sidecar_parsed", False)
        except Exception:
            agg.add("adapter_internal_error")

    def _all_codes() -> set:
        out = set(agg)
        for r in recs:
            out |= r.codes
        for row in rows:
            out |= row.codes
        return out

    # 8. Inventory before
    before = after = None
    before_failed = after_failed = False
    if state["cancelled"] is None:
        before, before_failed = _read_inventory()
        if before_failed:
            agg.add("inventory_read_failed")
        if before_failed or not before[0] or before[1] is None:
            agg.add("inventory_incomplete")
        if sidecar_parsed and isinstance(required_tools, list):
            for i, tool in enumerate(required_tools):
                row = _Row("required_tool", i, "required_tool", "supported_unchanged", set())
                if before_failed or not before[0] or before[1] is None:
                    row.codes.add("inventory_incomplete")
                elif tool not in before[1]:
                    row.codes.add("required_tool_not_in_inventory")
                rows.append(row)

    # 9.
    _cancel("before_validation")

    # 10. Validation
    snapshot_digest = None
    receipt = None
    validator_refusal = None
    validator_called = False
    payload_c = None
    fixture = None
    if state["cancelled"] is None and not _all_codes():
        payload_files = [File(f"skills/{slug}/{r.file.path}", 0o644, r.file.data)
                         for r in recs if r.role in _PAYLOAD_ROLES]
        payload_files.append(File(f"skills/{slug}/{SIDECAR_NAME}", 0o644, sidecar))
        fixture = File(f"tests/fixtures/skills_authoring/{slug}/{MATCHER_NAME}", 0o644, matcher)
        snapshot = None
        try:
            payload_c = Candidate(tuple(payload_files))
        except SandboxError:
            agg.add("payload_construction_refused")
        if payload_c is not None:
            try:
                snapshot = Candidate(baseline.files + payload_c.files + (fixture,))
                snapshot_digest = snapshot.fingerprint
            except SandboxError:
                agg.add("validation_snapshot_refused")
                validator_refusal = "validation_snapshot_refused"
        if snapshot is not None:
            code = None
            validator_called = True
            try:
                receipt = validate_skill_candidate(snapshot, baseline=baseline, slug=slug)
            except SandboxError:
                code = "validator_scope_refused"
            except OSError:
                code = "validator_staging_failed"
            except Exception:
                code = "validator_failed"
            if code:
                agg.add(code)
                validator_refusal = code
            after, after_failed = _read_inventory()
            if after_failed:
                agg.add("inventory_read_failed")
            if after_failed or not after[0] or after[1] is None:
                agg.add("inventory_incomplete")
            if after != before:
                agg.add("inventory_changed")
        if validator_called and receipt is None and validator_refusal is None:
            agg.add("validator_failed")
            validator_refusal = "validator_failed"
        elif receipt is not None and not isinstance(receipt, SkillAuthoringReceipt):
            agg.add("validator_failed")
            validator_refusal = validator_refusal or "validator_failed"
            receipt = None
        if receipt is not None:
            try:
                if receipt.candidate_digest != snapshot.fingerprint or receipt.slug != slug:
                    agg.add("receipt_binding_mismatch")
                checks = []
                for c in receipt.checks:
                    name = c.get("name") if isinstance(c, dict) else None
                    passed = isinstance(c, dict) and c.get("passed") is True
                    label = name if isinstance(name, str) and name in VALIDATOR_CHECKS else "unrecognized_check"
                    checks.append({"name": label, "passed": passed})
                    if label == "unrecognized_check":
                        agg.add("validation_check_unrecognized")
                    if not passed:
                        agg.add(f"validation_{label}_failed")
                if not (checks and all(c["passed"] for c in checks)):
                    agg.add("validation_failed")
                rd = receipt.as_dict()
                receipt_report = {
                    "kind": str(rd["kind"]), "schema_version": int(rd["schema_version"]),
                    "candidate_digest": str(rd["candidate_digest"]),
                    "package_revision": str(rd["package_revision"]),
                    "checked_files": int(rd["checked_files"]), "checked_bytes": int(rd["checked_bytes"]),
                    "passed": bool(checks) and all(c["passed"] for c in checks),
                    "provider_calls": int(rd["provider_calls"]), "checks": checks}
            except Exception:
                agg.add("validator_failed")
                validator_refusal = validator_refusal or "validator_failed"
                receipt_report = None
        else:
            receipt_report = None
        if baseline.fingerprint != baseline_digest:
            agg.add("baseline_changed")
    else:
        receipt_report = None

    # 11., 12.
    _cancel("after_validation")
    _cancel("before_return")

    # 13. Result
    blockers = sorted(_all_codes())
    cancelled_stage = state["cancelled"]
    produced = not blockers and cancelled_stage is None and payload_c is not None

    final_rows = []
    for rec in recs:
        if count_exceeded:
            break
        default = "unknown" if rec.role == "unclassified" else "supported_unchanged"
        final_rows.append(_Row("source_file", rec.ordinal, rec.role, default, rec.codes,
                               len(rec.file.data), rec.sha256))
    final_rows.extend(rows)
    final_rows.sort(key=lambda r: (_SCOPE_ORDER.index(r.scope), r.ordinal))
    dispositions = [{"scope": r.scope, "ordinal": r.ordinal, "label": r.label,
                     "disposition": _disposition(r.default, r.codes), "codes": sorted(r.codes),
                     "size": r.size, "sha256": r.sha256} for r in final_rows]

    def _inv_report(facts, failed, observed):
        if not observed:
            return None, None
        return facts[0], (None if facts[1] is None else len(facts[1]))

    b_obs = before is not None
    a_obs = after is not None
    b_complete, b_count = _inv_report(before, before_failed, b_obs)
    a_complete, a_count = _inv_report(after, after_failed, a_obs)
    evidence = None
    if caps_ok and not secret_found and cancelled_stage is None:
        evidence = SourceEvidence(
            tuple(r.file for r in recs),
            tuple(EvidenceEntry(r.ordinal, r.file.path, r.file.mode, len(r.file.data), r.sha256)
                  for r in recs),
            sidecar, matcher)

    report = {
        "kind": KIND, "schema_version": SCHEMA_VERSION, "adapter_version": ADAPTER_VERSION,
        "source_digest": source_digest, "inputs_digest": inputs_digest,
        "baseline_digest": baseline_digest,
        "candidate_digest": payload_c.fingerprint if produced else None,
        "validation_snapshot_digest": snapshot_digest,
        "parser_fingerprint": parser_fingerprint,
        "inventory_digest": _inventory_digest(before, after),
        "dispositions": dispositions, "blockers": blockers,
        "validation": {
            "outcome": OUTCOME_PRODUCED if produced else OUTCOME_BLOCKED,
            "profile": profile if profile in SUPPORTED_PROFILES else "unsupported",
            "adapter_code_digest": adapter_code_digest,
            "evidence_returned": evidence is not None,
            "source_record_count": len(records), "source_total_bytes": total,
            "cancelled_stage": cancelled_stage,
            "inventory": {
                "before_observed": b_obs, "before_complete": b_complete, "before_name_count": b_count,
                "after_observed": a_obs, "after_complete": a_complete, "after_name_count": a_count,
                "stable": (before == after) if (b_obs and a_obs) else None},
            "validator_refusal": validator_refusal,
            "receipt": receipt_report,
            "unknowns": list(UNKNOWNS),
        },
    }
    report["report_digest"] = report_digest(report)
    payload = PackagePayload(slug, payload_c.files, payload_c.fingerprint) if produced else None
    return AdapterResult(_canonical_json(report), payload, (fixture,) if produced else (), evidence)


# ---------------------------------------------------------------- semantic stage

def _semantic_stage(recs, rows, sidecar_row, sidecar, slug, slug_ok, source_digest, baseline, agg, out):
    refs: list = []
    license_path = None
    sidecar_data = None

    # (a) Sidecar
    if sidecar is not None and not sidecar_row.codes:
        try:
            parsed = _yaml_mapping(sidecar.decode("utf-8"))
        except (UnicodeError,) + _YAML_ERRORS:
            sidecar_row.codes.add("sidecar_unreadable")
            parsed = None
        if parsed is not None or not sidecar_row.codes:
            if not isinstance(parsed, dict):
                sidecar_row.codes.add("sidecar_not_mapping")
            else:
                sidecar_data = parsed
        if sidecar_data is not None:
            refs, license_path = _sidecar_rows(sidecar_data, rows, slug, source_digest, agg)
            out["sidecar_parsed"] = True
            rt = sidecar_data.get("required_tools")
            if isinstance(rt, list) and all(type(x) is str for x in rt):
                out["required_tools"] = rt

    # (b) Roles
    for rec in recs:
        p = rec.file.path
        if p == "SKILL.md":
            rec.role = "skill_file"
        elif sidecar_data is None:
            rec.role = "unclassified"
        elif license_path is not None and p == license_path:
            rec.role = "license"
        elif p in refs:
            rec.role = "reference"
        else:
            rec.role = "undeclared"
            rec.codes.add("undeclared_source_file")
    paths = {r.file.path for r in recs}
    if "SKILL.md" not in paths:
        rows.append(_Row("declared_file", 0, "skill_file", "unknown", {"skill_file_missing"}))
    if sidecar_data is not None:
        if license_path is not None and not _declared_path_codes(license_path, True) \
                and license_path not in paths:
            rows.append(_Row("declared_file", 1, "license", "unknown", {"license_file_missing"}))
        for i, ref in enumerate(refs):
            if ref not in paths:
                rows.append(_Row("declared_file", 2 + i, "reference", "unknown",
                                 {"declared_reference_missing"}))

        # (c) Payload size
        pay = [r for r in recs if r.role in _PAYLOAD_ROLES]
        if len(pay) + 1 > MAX_PACKAGE_FILES:
            agg.add("package_file_count_exceeded")
        if sum(len(r.file.data) for r in pay) + len(sidecar) > MAX_PACKAGE_BYTES:
            agg.add("package_aggregate_size_exceeded")

    # (d) Frontmatter
    skill_recs = [r for r in recs if r.role == "skill_file"]
    if len(skill_recs) == 1 and not skill_recs[0].codes:
        _frontmatter_rows(skill_recs[0].file.data.decode("utf-8"), rows, slug, agg)

    # (e) Baseline
    reg = next((f.data for f in baseline.files if f.path == "config/skills.yaml"), None)
    if reg is None:
        agg.add("baseline_registry_missing")
    else:
        # Same semantics as the runtime loader: legacy or strict schema-v2 only.
        try:
            names, pins, _version, valid = read_skill_registry(_MemoryRegistry(reg))
        except Exception:
            valid = False
        if not valid:
            agg.add("baseline_registry_invalid")
        elif slug_ok and (slug in names or slug in (pins or {})):
            agg.add("slug_exists_in_registry")
    if slug_ok:
        for f in baseline.files:
            k = path_key(f.path)
            if k.startswith(f"skills/{slug}/"):
                agg.add("slug_exists_in_baseline_package")
            if k.startswith(f"tests/fixtures/skills_authoring/{slug}/"):
                agg.add("slug_exists_in_baseline_fixtures")


class _MemoryRegistry:
    """Read-only, in-memory stand-in for the registry path read_skill_registry expects.

    Lets the adapter apply the runtime loader's exact registry semantics to the
    supplied baseline bytes without writing them anywhere.
    """

    __slots__ = ("_data",)

    def __init__(self, data: bytes):
        self._data = data

    def exists(self) -> bool:
        return True

    def read_text(self, encoding: str = "utf-8") -> str:
        return self._data.decode(encoding)


def _sidecar_rows(data: dict, rows, slug, source_digest, agg):
    refs: list = []
    license_path = None
    index = 0
    for key, value in data.items():
        known = isinstance(key, str) and key in TOP_LEVEL_FIELDS
        label = key if known else "unrecognized"
        default = "explicit_inert_annotation" if known and key in _SIDECAR_DESCRIPTIVE \
            else "supported_unchanged"
        row = _Row("sidecar_field", index, label, default, set())
        index += 1
        rows.append(row)
        if not known:
            row.codes.add("sidecar_field_unrecognized")
            continue
        if key == "schema_version":
            if type(value) is not int or value != 1:
                row.codes.add("sidecar_schema_unsupported")
        elif key == "skill_id":
            if value != slug:
                row.codes.add("sidecar_skill_id_mismatch")
        elif key == "reference_paths":
            if (not isinstance(value, list) or any(type(x) is not str for x in value)
                    or len(set(value)) != len(value)):
                row.codes.add("sidecar_reference_paths_invalid")
            else:
                refs = list(value)
                for ref in value:
                    row.codes |= _declared_path_codes(ref, False)
        elif key == "required_tools":
            if not isinstance(value, list) or any(type(x) is not str for x in value):
                row.codes.add("sidecar_required_tools_invalid")
        elif key == "required_credentials":
            if value not in (None, []):
                row.codes.add("required_credentials_unsupported")
        elif key == "source":
            if not isinstance(value, dict):
                row.codes.add("provenance_missing")
            else:
                if value.get("kind") != PROVENANCE_KIND:
                    row.codes.add("provenance_kind_unsupported")
                for field, code in (("reference", "provenance_reference_missing"),
                                    ("immutable_revision", "provenance_revision_missing"),
                                    ("license", "license_identifier_missing"),
                                    ("license_path", "license_path_missing")):
                    v = value.get(field)
                    if not isinstance(v, str) or not v.strip():
                        row.codes.add(code)
                lp = value.get("license_path")
                if isinstance(lp, str) and lp.strip():
                    license_path = lp
                    row.codes |= _declared_path_codes(lp, True)
                if "source_digest" in value and value["source_digest"] != source_digest:
                    row.codes.add("provenance_source_digest_mismatch")
                for sub in value:
                    if not (isinstance(sub, str) and sub in _SOURCE_KEYS):
                        extra = _Row("sidecar_field", index, "source.unrecognized",
                                     "supported_unchanged", {"sidecar_field_unrecognized"})
                        index += 1
                        rows.append(extra)
    if "schema_version" not in data:
        agg.add("sidecar_schema_unsupported")
    if "skill_id" not in data:
        agg.add("sidecar_skill_id_mismatch")
    if "source" not in data:
        agg.add("provenance_missing")
    return refs, license_path


def _frontmatter_rows(text: str, rows, slug, agg) -> None:
    front, _body = _split_frontmatter(text)
    if not front.strip():
        rows.append(_Row("frontmatter", 0, "frontmatter", "unsupported", {"frontmatter_missing"}))
        agg.add("skill_frontmatter_incompatible")
        return
    fm, problems = load_frontmatter(front)
    problems = [c for c in problems if c in REASONS]
    if problems:
        agg.add("skill_frontmatter_incompatible")
        agg.update(problems)
    mapping = fm
    if mapping is None and not (set(problems) & _YAML_LEVEL_CODES):
        try:
            mapping = _yaml_mapping(front)
        except (yaml.YAMLError, ValueError, RecursionError, OverflowError):
            mapping = None
    if not isinstance(mapping, dict):
        rows.append(_Row("frontmatter", 0, "frontmatter", "unsupported",
                         set(problems) or {"frontmatter_not_mapping"}))
        agg.add("skill_frontmatter_incompatible")
        return
    pset = set(problems)
    meta_index = 0
    for i, (key, value) in enumerate(mapping.items()):
        if key == "name":
            row = _Row("frontmatter", i, "name", "supported_unchanged", pset & _NAME_CODES)
            if isinstance(value, str) and value.strip() and value.strip() != slug:
                row.codes.add("skill_name_slug_mismatch")
        elif key == "description":
            row = _Row("frontmatter", i, "description", "supported_unchanged", pset & _DESCRIPTION_CODES)
        elif key == "metadata":
            row = _Row("frontmatter", i, "metadata", "explicit_inert_annotation", pset & _METADATA_CODES)
            if isinstance(value, dict):
                for mk in value:
                    known = isinstance(mk, str) and mk in _METADATA_KNOWN
                    mrow = _Row("frontmatter_metadata", meta_index,
                                f"metadata.{mk}" if known else "metadata.unrecognized",
                                "explicit_inert_annotation", set())
                    if not known:
                        mrow.codes.add("frontmatter_metadata_key_unrecognized")
                    meta_index += 1
                    rows.append(mrow)
        elif isinstance(key, str) and key in _HOST_CONTROL_KEYS:
            row = _Row("frontmatter", i, key, "supported_unchanged", {"frontmatter_control_unsupported"})
        else:
            row = _Row("frontmatter", i, "unrecognized", "supported_unchanged",
                       {"frontmatter_key_unrecognized"})
        rows.append(row)
