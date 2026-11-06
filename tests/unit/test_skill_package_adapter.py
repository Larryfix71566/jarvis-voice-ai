import hashlib
import json
import socket
import subprocess
import sys
import tempfile  # noqa: F401  (validator staging is patched through its own module)
from pathlib import Path

import pytest
import yaml

import jarvis.skill_authoring_validation as validation
import jarvis.skill_package_adapter as adapter
from jarvis.agent_skills import read_skill_registry
from jarvis.skill_authoring_validation import SkillAuthoringReceipt
from jarvis.skill_service import ToolInventory
from sandbox.artifacts import Candidate, File, SandboxError

REPO = Path(__file__).resolve().parents[2]
SLUG = "sample-import"
SKILL_MD = (b"---\nname: sample-import\ndescription: Summarize a sample imported checklist for the user.\n---\n\n"
            b"# Sample import\n\nBODY-MARKER-7Q follow the checklist in the guide.\n\n```bash\n#!/bin/sh\necho inert example\n```\n")
LICENSE = b"MIT License\n\nLICENSE-MARKER-9Z Copyright (c) 2026 Example Authors\n"
GUIDE = b"# Guide\r\n\r\nGUIDE-MARKER-3K step one: read the request.  \r\n"
REGISTRY = b"schema_version: 2\nenabled: []\nrevisions: {}\n"
OTHER = b"---\nname: other-skill\ndescription: Another synthetic skill.\n---\n\nBody.\n"
INV = ToolInventory(frozenset({"status_models"}), True)
_DEFAULT = object()
DESC_LINE = b"description: Summarize a sample imported checklist for the user.\n"


def _canaries():
    return ["ghp_" + "Q" * 36, "sk-" + "z" * 30, "-----BEGIN " + "PRIVATE KEY-----"]


def _source(**replace):
    files = {"SKILL.md": SKILL_MD, "LICENSE.txt": LICENSE, "references/guide.md": GUIDE}
    files.update(replace)
    return [File(p, 0o644, d) for p, d in files.items() if d is not None]


def _sidecar_dict():
    return {"schema_version": 1, "skill_id": SLUG, "display_name": "Sample Import", "category": "general",
            "version": "1.0.0",
            "source": {"kind": "imported", "reference": "example/sample-import",
                       "immutable_revision": "0123456789abcdef0123456789abcdef01234567",
                       "license": "MIT", "license_path": "LICENSE.txt"},
            "capabilities": [], "required_tools": [], "required_credentials": [],
            "reference_paths": ["references/guide.md"], "example_ids": ["positive-sample", "negative-sample"],
            "related_workflow_ids": [], "compatible_with": [],
            "process": {"kind": "linear", "nodes": [{"step_id": "do-work", "title": "Do the work",
                "description": "Complete the requested task.", "inputs": ["user_request"], "outputs": ["result"],
                "tools": [], "success_criteria": ["result is complete"], "edges": []}]}}


def _sidecar(mutate=None):
    d = _sidecar_dict()
    if mutate:
        mutate(d)
    return yaml.safe_dump(d, sort_keys=False).encode()


def _matcher(ids=("positive-sample", "negative-sample"), request="Please summarize the sample imported checklist"):
    return json.dumps({"schema_version": 1, "cases": [
        {"id": ids[0], "request": request, "expect_selected": True},
        {"id": ids[1], "request": "Tell me an unrelated joke", "expect_selected": False}]}).encode()


def _baseline(registry=REGISTRY, extra=()):
    return Candidate((File("config/skills.yaml", 0o644, registry),
                      File("skills/other-skill/SKILL.md", 0o644, OTHER)) + tuple(extra))


def _run(source=None, *, sidecar=_DEFAULT, matcher=_DEFAULT, baseline=None, slug=SLUG, **kw):
    return adapter.adapt_instruction_package(
        tuple(_source() if source is None else source),
        reviewed_inputs=adapter.ReviewedInputs(
            sidecar=_sidecar() if sidecar is _DEFAULT else sidecar,
            matcher_cases=_matcher() if matcher is _DEFAULT else matcher),
        baseline=baseline if baseline is not None else _baseline(), slug=slug, **kw)


def _rows(result, scope):
    return [r for r in result.report["dispositions"] if r["scope"] == scope]


def _assert_content_free(result, *needles):
    text = result.report_json.decode("ascii")
    for n in (*needles, "BODY-MARKER-7Q", "LICENSE-MARKER-9Z", "GUIDE-MARKER-3K", "SKILL.md", "LICENSE.txt",
              "references/", "mortimer.yaml", str(REPO), "mortimer-skill-validation-", '"detail"',
              '"ready"', '"approved"', '"active"'):
        assert n not in text
    assert set(result.report["blockers"]) <= adapter.BLOCKER_CODES
    assert all(r["disposition"] in adapter.DISPOSITIONS for r in result.report["dispositions"])


def _blocked(result, code):
    assert result.payload is None and result.test_requirements == ()
    assert result.report["candidate_digest"] is None
    assert code in result.report["blockers"]
    assert result.report["validation"]["outcome"] == "blocked"
    _assert_content_free(result)


def _skill_with(line: bytes) -> bytes:
    return SKILL_MD.replace(DESC_LINE, DESC_LINE + line)


@pytest.fixture(autouse=True)
def static_inventory(monkeypatch):
    # Test-only: deterministic static inventory at both bindings.
    monkeypatch.setattr(adapter, "configured_tool_inventory", lambda: INV)
    monkeypatch.setattr(validation, "configured_tool_inventory", lambda: INV)


# ---------------------------------------------------------------- happy path

def test_valid_package_produces_package_only_payload_with_exact_bytes():
    result = _run()
    assert result.produced, result.report["blockers"]
    assert result.report["validation"]["outcome"] == "package_payload_produced"
    assert result.report["blockers"] == []
    expected = {"skills/sample-import/SKILL.md": SKILL_MD, "skills/sample-import/LICENSE.txt": LICENSE,
                "skills/sample-import/references/guide.md": GUIDE,
                "skills/sample-import/mortimer.yaml": _sidecar()}
    assert {f.path: f.data for f in result.payload.files} == expected
    assert all(f.mode == 0o644 for f in result.payload.files)
    assert not any(f.path.startswith(("config/", "tests/")) for f in result.payload.files)
    assert result.payload.digest == result.report["candidate_digest"] == Candidate(result.payload.files).fingerprint
    assert result.test_requirements == (
        File("tests/fixtures/skills_authoring/sample-import/matcher-cases.json", 0o644, _matcher()),)
    _assert_content_free(result)


def test_validation_snapshot_is_baseline_plus_package_plus_fixture():
    b = _baseline()
    result = _run(baseline=b)
    assert result.produced
    report = result.report
    snap = Candidate(b.files + result.payload.files + result.test_requirements).fingerprint
    receipt = report["validation"]["receipt"]
    assert report["validation_snapshot_digest"] == snap == receipt["candidate_digest"]
    assert snap != report["candidate_digest"]
    checks = {c["name"]: c["passed"] for c in receipt["checks"]}
    assert checks["runtime_registry_unchanged"] is True
    assert set(checks) <= set(adapter.VALIDATOR_CHECKS)
    assert receipt["passed"] is True and receipt["provider_calls"] == 0


def test_baseline_and_registry_unchanged_after_adaptation():
    b = _baseline()
    fp = b.fingerprint
    result = _run(baseline=b)
    assert b.fingerprint == fp == result.report["baseline_digest"]
    assert next(f.data for f in b.files if f.path == "config/skills.yaml") == REGISTRY


def test_evidence_retains_original_bytes_and_manifest_digest():
    result = _run()
    ev = result.evidence
    assert ev.records == tuple(sorted(_source(), key=lambda f: f.path))
    for i, entry in enumerate(ev.inventory):
        assert entry.ordinal == i
        assert entry.sha256 == hashlib.sha256(ev.records[i].data).hexdigest()
    assert result.report["source_digest"] == adapter.compute_source_digest(_source())
    assert ev.sidecar == _sidecar() and ev.matcher_cases == _matcher()


def test_report_is_deterministic_and_order_independent():
    r1, r2 = _run(), _run()
    r3 = _run(list(reversed(_source())))
    assert r1.report_json == r2.report_json == r3.report_json
    assert r1.payload.digest == r2.payload.digest == r3.payload.digest
    assert adapter.evidence_reusable(r1.report, r2.report) is True


def test_adapter_writes_nothing_live_and_starts_no_process_or_network(monkeypatch):
    def listing():
        out = []
        for sub in ("skills", "tests/fixtures/skills_authoring"):
            root = REPO / sub
            out.append(sorted(str(p.relative_to(REPO)) for p in root.rglob("*")))
        return out, hashlib.sha256((REPO / "config/skills.yaml").read_bytes()).hexdigest()

    before = listing()

    def boom(*a, **k):
        raise AssertionError("forbidden")

    monkeypatch.setattr(subprocess.Popen, "__init__", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    result = _run()
    assert result.produced
    assert listing() == before
    assert not (REPO / "skills" / SLUG).exists()
    assert not (REPO / "tests/fixtures/skills_authoring" / SLUG).exists()


def test_report_never_emits_ready_or_grant_and_lists_unknowns():
    result = _run()
    assert result.report["validation"]["unknowns"] == list(adapter.UNKNOWNS)
    _assert_content_free(result)


def test_inert_code_example_in_prose_is_accepted():
    result = _run()
    assert result.produced
    row = next(r for r in _rows(result, "source_file") if r["label"] == "skill_file")
    assert row["disposition"] == "supported_unchanged" and row["codes"] == []


# ---------------------------------------------------------------- controls and metadata

@pytest.mark.parametrize("line,key", [(b"allowed-tools: Read\n", "allowed-tools"),
                                      (b"disable-model-invocation: true\n", "disable-model-invocation"),
                                      (b"license: MIT\n", "license")])
def test_host_invocation_flag_blocks_with_unsupported_disposition(line, key):
    r = _run(_source(**{"SKILL.md": _skill_with(line)}))
    _blocked(r, "frontmatter_control_unsupported")
    assert "unsupported_frontmatter_fields" in r.report["blockers"]
    assert "skill_frontmatter_incompatible" in r.report["blockers"]
    rows = [x for x in _rows(r, "frontmatter") if x["label"] == key]
    assert rows and rows[0]["disposition"] == "unsupported"
    assert r.report["validation"]["receipt"] is None


def test_unknown_frontmatter_key_is_unknown_and_blocks():
    r = _run(_source(**{"SKILL.md": _skill_with(b"x-required-runtime: node\n")}))
    _blocked(r, "frontmatter_key_unrecognized")
    row = next(x for x in _rows(r, "frontmatter") if x["label"] == "unrecognized")
    assert row["disposition"] == "unknown" and row["codes"] == ["frontmatter_key_unrecognized"]
    text = r.report_json.decode()
    assert "x-required-runtime" not in text and "node" not in text


def test_unknown_metadata_key_blocks():
    r = _run(_source(**{"SKILL.md": _skill_with(b"metadata:\n  requires: gpu\n")}))
    _blocked(r, "unsupported_metadata_fields")
    row = next(x for x in _rows(r, "frontmatter_metadata") if x["label"] == "metadata.unrecognized")
    assert row["disposition"] == "unknown"


def test_known_metadata_is_inert_annotation():
    r = _run(_source(**{"SKILL.md": _skill_with(b"metadata:\n  agent: test\n")}))
    assert r.produced, r.report["blockers"]
    row = next(x for x in _rows(r, "frontmatter_metadata") if x["label"] == "metadata.agent")
    assert row["disposition"] == "explicit_inert_annotation"


def test_unknown_sidecar_field_blocks():
    r = _run(sidecar=_sidecar(lambda d: d.__setitem__("runtime", "node")))
    _blocked(r, "sidecar_field_unrecognized")
    row = next(x for x in _rows(r, "sidecar_field") if x["label"] == "unrecognized")
    assert row["disposition"] == "unknown"


def test_unknown_source_subkey_blocks():
    r = _run(sidecar=_sidecar(lambda d: d["source"].__setitem__("mirror", "x")))
    _blocked(r, "sidecar_field_unrecognized")
    assert any(x["label"] == "source.unrecognized" for x in _rows(r, "sidecar_field"))


def test_required_credentials_block():
    r = _run(sidecar=_sidecar(lambda d: d.__setitem__("required_credentials", ["EXAMPLE_TOKEN"])))
    _blocked(r, "required_credentials_unsupported")
    assert "EXAMPLE_TOKEN" not in r.report_json.decode()


def test_sidecar_descriptive_fields_are_inert_annotations():
    r = _run(sidecar=_sidecar(lambda d: d.__setitem__("required_tools", ["status_models"])))
    assert r.produced, r.report["blockers"]
    by = {x["label"]: x["disposition"] for x in _rows(r, "sidecar_field")}
    assert by["display_name"] == "explicit_inert_annotation"
    assert by["category"] == "explicit_inert_annotation"
    assert by["required_tools"] == "supported_unchanged"


# ---------------------------------------------------------------- scripts, executables, binary

@pytest.mark.parametrize("path", ["scripts/run.sh", "Scripts/notes.md", "references/SCRIPTS/helper.MD",
                                  "docs/ScRiPtS/x.txt"])
def test_scripts_component_blocks_case_insensitively(path):
    src = _source() + [File(path, 0o644, b"text\n")]
    r = _run(src)
    _blocked(r, "scripts_path_refused")
    rows = _rows(r, "source_file")
    assert len(rows) == 4
    assert any("scripts_path_refused" in x["codes"] and x["disposition"] == "unsupported" for x in rows)


def test_declared_reference_under_scripts_still_blocks():
    src = _source() + [File("references/scripts/notes.md", 0o644, b"notes\n")]
    sc = _sidecar(lambda d: d.__setitem__("reference_paths", ["references/guide.md", "references/scripts/notes.md"]))
    r = _run(src, sidecar=sc)
    _blocked(r, "scripts_path_refused")
    row = next(x for x in _rows(r, "source_file") if "scripts_path_refused" in x["codes"])
    assert row["label"] == "reference" and row["disposition"] == "unsupported"


@pytest.mark.parametrize("variant", ["guide", "license_bom"])
def test_shebang_after_leading_whitespace_blocks_declared_reference(variant):
    if variant == "guide":
        r = _run(_source(**{"references/guide.md": b"  \n\t#!/usr/bin/env python\nprint(1)\n"}))
        label = "reference"
    else:
        r = _run(_source(**{"LICENSE.txt": b"\xef\xbb\xbf#!/bin/sh\n"}))
        label = "license"
    _blocked(r, "shebang_refused")
    row = next(x for x in _rows(r, "source_file") if "shebang_refused" in x["codes"])
    assert row["label"] == label


def test_executable_binary_dependency_files_block_with_complete_dispositions():
    extra = [File("tool.py", 0o644, b"print(1)\n"), File("image.png", 0o644, b"\x89PNG\x00\x01"),
             File("package.json", 0o644, b"{}\n"), File("bundle.zip", 0o644, b"PK\x03\x04rest")]
    r = _run(_source() + extra)
    blockers = set(r.report["blockers"])
    assert {"executable_suffix_refused", "binary_content_refused", "dependency_manifest_refused",
            "archive_record_refused", "undeclared_source_file"} <= blockers
    assert len(_rows(r, "source_file")) == 7
    assert "tool" not in sys.modules
    _blocked(r, "executable_suffix_refused")


def test_declared_dependency_manifest_blocks():
    src = _source() + [File("requirements.txt", 0o644, b"requests\n")]
    sc = _sidecar(lambda d: d.__setitem__("reference_paths", ["references/guide.md", "requirements.txt"]))
    r = _run(src, sidecar=sc)
    _blocked(r, "dependency_manifest_refused")
    row = next(x for x in _rows(r, "source_file") if "dependency_manifest_refused" in x["codes"])
    assert row["label"] == "reference"


def test_archive_magic_in_markdown_blocks():
    _blocked(_run(_source(**{"references/guide.md": b"PK\x03\x04abc"})), "archive_record_refused")


def test_undeclared_text_file_blocks_as_unknown():
    r = _run(_source() + [File("notes.md", 0o644, b"notes\n")])
    _blocked(r, "undeclared_source_file")
    row = next(x for x in _rows(r, "source_file") if x["label"] == "undeclared")
    assert row["disposition"] == "unknown" and row["codes"] == ["undeclared_source_file"]


def test_source_supplied_sidecar_conflicts():
    _blocked(_run(_source() + [File("mortimer.yaml", 0o644, b"a: 1\n")]), "source_sidecar_conflict")


def test_reference_and_license_suffix_rules():
    src = _source() + [File("references/guide.html", 0o644, b"<p>x</p>\n")]
    sc = _sidecar(lambda d: d.__setitem__("reference_paths", ["references/guide.html"]))
    _blocked(_run(src, sidecar=sc), "reference_suffix_unsupported")

    src = _source(**{"LICENSE.txt": None}) + [File("LICENSE", 0o644, LICENSE)]
    sc = _sidecar(lambda d: d["source"].__setitem__("license_path", "LICENSE"))
    _blocked(_run(src, sidecar=sc), "license_suffix_unsupported")

    src = _source(**{"LICENSE.txt": None}) + [File("LICENSE.TXT", 0o644, LICENSE)]
    sc = _sidecar(lambda d: d["source"].__setitem__("license_path", "LICENSE.TXT"))
    r = _run(src, sidecar=sc)
    assert r.produced, r.report["blockers"]


# ---------------------------------------------------------------- missing resources and inventory

def test_missing_sidecar_blocks():
    r = _run(sidecar=None)
    _blocked(r, "sidecar_missing")
    assert _rows(r, "reviewed_input")[0]["size"] is None


def test_missing_matcher_blocks():
    _blocked(_run(matcher=None), "matcher_cases_missing")


def test_missing_license_file_blocks():
    r = _run(_source(**{"LICENSE.txt": None}))
    _blocked(r, "license_file_missing")
    row = next(x for x in _rows(r, "declared_file") if x["ordinal"] == 1)
    assert row["disposition"] == "unknown"


def test_missing_declared_reference_blocks():
    r = _run(_source(**{"references/guide.md": None}))
    _blocked(r, "declared_reference_missing")
    assert any(x["ordinal"] == 2 for x in _rows(r, "declared_file"))


def test_missing_skill_file_blocks():
    _blocked(_run(_source(**{"SKILL.md": None})), "skill_file_missing")


def _del(*path):
    def mutate(d):
        node = d
        for p in path[:-1]:
            node = node[p]
        del node[path[-1]]
    return mutate


@pytest.mark.parametrize("mutate,code", [
    (lambda d: d["source"].__setitem__("kind", "authored"), "provenance_kind_unsupported"),
    (_del("source", "immutable_revision"), "provenance_revision_missing"),
    (_del("source", "reference"), "provenance_reference_missing"),
    (_del("source", "license"), "license_identifier_missing"),
    (_del("source", "license_path"), "license_path_missing"),
    (lambda d: d["source"].__setitem__("source_digest", "0" * 64), "provenance_source_digest_mismatch"),
])
def test_provenance_requirements(mutate, code):
    _blocked(_run(sidecar=_sidecar(mutate)), code)


def test_matching_source_digest_in_provenance_is_accepted():
    digest = adapter.compute_source_digest(_source())
    r = _run(sidecar=_sidecar(lambda d: d["source"].__setitem__("source_digest", digest)))
    assert r.produced, r.report["blockers"]


def test_required_tool_present_in_static_inventory_is_supported():
    r = _run(sidecar=_sidecar(lambda d: d.__setitem__("required_tools", ["status_models"])))
    assert r.produced, r.report["blockers"]
    assert _rows(r, "required_tool")[0]["disposition"] == "supported_unchanged"
    assert "status_models" not in r.report_json.decode()


def test_required_tool_not_in_inventory_blocks():
    r = _run(sidecar=_sidecar(lambda d: d.__setitem__("required_tools", ["weather_lookup"])))
    _blocked(r, "required_tool_not_in_inventory")
    assert _rows(r, "required_tool")[0]["disposition"] == "unsupported"


@pytest.mark.parametrize("inv", [ToolInventory(frozenset(), False), ToolInventory(None, False)])
def test_incomplete_inventory_blocks_even_without_required_tools(monkeypatch, inv):
    monkeypatch.setattr(adapter, "configured_tool_inventory", lambda: inv)
    r = _run()
    _blocked(r, "inventory_incomplete")
    assert r.report["validation"]["inventory"]["before_complete"] is False


def test_inventory_change_between_reads_blocks(monkeypatch):
    calls = []

    def reader():
        calls.append(1)
        return INV if len(calls) == 1 else ToolInventory(frozenset({"status_models", "x_tool"}), True)

    monkeypatch.setattr(adapter, "configured_tool_inventory", reader)
    r = _run()
    _blocked(r, "inventory_changed")
    assert r.report["validation"]["inventory"]["stable"] is False
    assert r.report["validation"]["receipt"] is not None
    assert r.report["candidate_digest"] is None


def test_inventory_read_failure_blocks(monkeypatch):
    def reader():
        raise RuntimeError("private detail")

    monkeypatch.setattr(adapter, "configured_tool_inventory", reader)
    r = _run()
    _blocked(r, "inventory_read_failed")
    assert "inventory_incomplete" in r.report["blockers"]
    assert "private detail" not in r.report_json.decode()


# ---------------------------------------------------------------- refusals before materialization

def test_invalid_utf8_blocks():
    r = _run(_source(**{"references/guide.md": b"\xff\xfe"}))
    _blocked(r, "utf8_invalid")
    assert r.report["validation"]["receipt"] is None
    assert r.evidence is not None


@pytest.mark.parametrize("skill,code", [
    (SKILL_MD.replace(b"name: sample-import", b"name: [unclosed"), "frontmatter_invalid_yaml"),
    (SKILL_MD.replace(b"name: sample-import\n", b"name: sample-import\nname: sample-import\n"),
     "frontmatter_duplicate_key"),
    (b"# No frontmatter\n\nBody text.\n", "frontmatter_missing"),
])
def test_malformed_frontmatter_blocks(skill, code):
    r = _run(_source(**{"SKILL.md": skill}))
    _blocked(r, code)
    assert "skill_frontmatter_incompatible" in r.report["blockers"]


@pytest.mark.parametrize("sidecar,code", [
    (b"schema_version: 1\nschema_version: 1\n", "sidecar_unreadable"),
    (b"- a\n", "sidecar_not_mapping"),
    (b"key: [unclosed\n", "sidecar_unreadable"),
])
def test_malformed_or_duplicate_sidecar_blocks(sidecar, code):
    _blocked(_run(sidecar=sidecar), code)


def test_invalid_matcher_maps_validator_failure_to_fixed_codes():
    r = _run(matcher=_matcher(ids=("other-a", "other-b")))
    _blocked(r, "validation_failed")
    assert "validation_matcher_fixtures_failed" in r.report["blockers"]
    checks = r.report["validation"]["receipt"]["checks"]
    assert {"name": "matcher_fixtures", "passed": False} in checks
    assert all("detail" not in c for c in checks)


@pytest.mark.parametrize("path", ["../escape.md", "references/../x.md", "/abs.md", "a\\b.md", "c:d.md",
                                  "bad\x01.md"])
def test_path_traversal_and_invalid_paths_block(path):
    _blocked(_run(_source() + [File(path, 0o644, b"x\n")]), "path_invalid")


def test_forbidden_and_hidden_paths_block():
    _blocked(_run(_source() + [File(".env.md", 0o644, b"x\n")]), "path_forbidden")
    _blocked(_run(_source() + [File("references/.hidden.md", 0o644, b"x\n")]), "hidden_path_refused")
    _blocked(_run(_source() + [File("id.pem", 0o644, b"x\n")]), "path_forbidden")


def test_case_and_unicode_collisions_block():
    r = _run(_source() + [File("references/GUIDE.md", 0o644, b"x\n")])
    _blocked(r, "path_collision")
    assert sum("path_collision" in x["codes"] for x in _rows(r, "source_file")) == 2

    nfc, nfd = "references/café.md", "references/café.md"
    r = _run(_source() + [File(nfc, 0o644, b"x\n"), File(nfd, 0o644, b"y\n")])
    _blocked(r, "path_collision")

    r = _run(_source() + [File("References/x.md", 0o644, b"x\n")])
    _blocked(r, "path_collision")
    assert sum("path_collision" in x["codes"] for x in _rows(r, "source_file")) == 2


def test_file_directory_collision_blocks():
    r = _run(_source() + [File("references", 0o644, b"x\n")])
    _blocked(r, "file_directory_collision")
    assert sum("file_directory_collision" in x["codes"] for x in _rows(r, "source_file")) == 2


@pytest.mark.parametrize("mode,code", [(0o755, "mode_forbidden"), (0o600, "mode_forbidden"),
                                       (0o100644, "mode_forbidden"), (0o120777, "symlink_record_refused")])
def test_forbidden_modes_and_symlink_records_block(mode, code):
    src = _source() + [File("references/extra.md", mode, b"x\n")]
    _blocked(_run(src), code)


def test_source_count_cap():
    src = [File("SKILL.md", 0o644, SKILL_MD)] + [File(f"r{i}.md", 0o644, b"x\n") for i in range(128)]
    r = _run(src)
    _blocked(r, "source_file_count_exceeded")
    assert r.evidence is None
    assert len(_rows(r, "source_file_set")) == 1 and not _rows(r, "source_file")


def test_source_per_file_cap():
    r = _run(_source(**{"references/guide.md": b"a" * (128 * 1024 + 1)}))
    _blocked(r, "source_file_size_exceeded")
    assert r.evidence is None


def test_source_aggregate_cap():
    src = _source() + [File(f"references/big{i}.md", 0o644, b"a" * (128 * 1024)) for i in range(81)]
    r = _run(src)
    _blocked(r, "source_aggregate_size_exceeded")
    assert r.evidence is None


def test_reviewed_input_cap():
    r = _run(sidecar=b"a" * (128 * 1024 + 1))
    _blocked(r, "reviewed_input_size_exceeded")
    assert r.evidence is None


def test_payload_file_count_cap():
    refs = [f"references/r{i}.md" for i in range(126)]
    src = [File("SKILL.md", 0o644, SKILL_MD), File("LICENSE.txt", 0o644, LICENSE)] + \
        [File(p, 0o644, b"x\n") for p in refs]
    r = _run(src, sidecar=_sidecar(lambda d: d.__setitem__("reference_paths", refs)))
    _blocked(r, "package_file_count_exceeded")
    assert r.report["validation"]["receipt"] is None


def test_payload_aggregate_cap():
    refs = [f"references/r{i}.md" for i in range(80)]
    src = [File("SKILL.md", 0o644, SKILL_MD), File("LICENSE.txt", 0o644, LICENSE)]
    for i in range(79):
        src.append(File(refs[i], 0o644, b"a" * 131072))
    src.append(File(refs[79], 0o644, b"a" * (131072 - len(SKILL_MD) - len(LICENSE))))
    assert sum(len(f.data) for f in src) == adapter.MAX_PACKAGE_BYTES
    r = _run(src, sidecar=_sidecar(lambda d: d.__setitem__("reference_paths", refs)))
    _blocked(r, "package_aggregate_size_exceeded")
    assert "source_aggregate_size_exceeded" not in r.report["blockers"]


@pytest.mark.parametrize("canary", _canaries())
@pytest.mark.parametrize("where", ["skill_body", "reference", "undeclared", "adaptation_notes",
                                   "matcher_request", "path_name"])
def test_secret_canaries_refuse_with_digests_ordinals_and_codes_only(where, canary):
    kw = {}
    src = None
    if where == "skill_body":
        src = _source(**{"SKILL.md": SKILL_MD + canary.encode() + b"\n"})
    elif where == "reference":
        src = _source(**{"references/guide.md": GUIDE + canary.encode()})
    elif where == "undeclared":
        src = _source() + [File("notes.md", 0o644, canary.encode())]
    elif where == "adaptation_notes":
        kw["sidecar"] = _sidecar(lambda d: d["source"].__setitem__("adaptation_notes", canary))
    elif where == "matcher_request":
        kw["matcher"] = _matcher(request=canary)
    else:
        src = _source() + [File(f"references/{canary}.md", 0o644, b"x\n")]
    r = _run(src, **kw)
    _blocked(r, "secret_detected")
    assert r.evidence is None
    assert r.report["validation"]["receipt"] is None
    assert r.report["validation_snapshot_digest"] is None
    assert canary not in r.report_json.decode()
    keys = {"scope", "ordinal", "label", "disposition", "codes", "size", "sha256"}
    assert all(set(row) == keys for row in r.report["dispositions"])


def test_secret_shaped_slug_refuses():
    slug = "sk-" + "a" * 30
    r = _run(slug=slug)
    _blocked(r, "secret_detected")
    assert slug not in r.report_json.decode()


# ---------------------------------------------------------------- slug, baseline, validator failures

def test_existing_slug_in_registry_blocks():
    reg = b"schema_version: 2\nenabled: [sample-import]\nrevisions:\n  sample-import: " + b"a" * 64 + b"\n"
    _blocked(_run(baseline=_baseline(registry=reg)), "slug_exists_in_registry")


def test_existing_slug_package_in_baseline_blocks():
    b = _baseline(extra=[File("skills/sample-import/SKILL.md", 0o644, OTHER)])
    _blocked(_run(baseline=b), "slug_exists_in_baseline_package")
    b = _baseline(extra=[File("tests/fixtures/skills_authoring/sample-import/matcher-cases.json", 0o644, b"{}")])
    _blocked(_run(baseline=b), "slug_exists_in_baseline_fixtures")


def test_baseline_registry_missing_or_invalid_blocks():
    b = Candidate((File("skills/other-skill/SKILL.md", 0o644, OTHER),))
    _blocked(_run(baseline=b), "baseline_registry_missing")
    _blocked(_run(baseline=_baseline(registry=b"enabled: [unclosed\n")), "baseline_registry_invalid")


# Review of #300 (2026-11-05): the baseline registry must follow the runtime reader's semantics.
INVALID_REGISTRIES = [
    b"{schema_version: 2, enabled: false, revisions: false}\n",
    b"{schema_version: 2, enabled: [], revisions: {}, extra: true}\n",
    b"{schema_version: 999, enabled: [], revisions: {}}\n",
    b"{schema_version: 2, enabled: [true], revisions: {}}\n",
    b"{schema_version: 2, enabled: [other-skill], revisions: {}}\n",
]


@pytest.mark.parametrize("raw", INVALID_REGISTRIES)
def test_registry_rejected_by_runtime_reader_blocks(raw, tmp_path):
    path = tmp_path / "skills.yaml"
    path.write_bytes(raw)
    assert read_skill_registry(path)[3] is False
    _blocked(_run(baseline=_baseline(registry=raw)), "baseline_registry_invalid")


@pytest.mark.parametrize("raw", [
    REGISTRY,
    b"schema_version: 2\nenabled: [other-skill]\nrevisions:\n  other-skill: " + b"b" * 64 + b"\n",
    b"enabled: [other-skill]\n",
    b"{}\n",
])
def test_registry_accepted_by_runtime_reader_still_produces(raw, tmp_path):
    path = tmp_path / "skills.yaml"
    path.write_bytes(raw)
    assert read_skill_registry(path)[3] is True
    r = _run(baseline=_baseline(registry=raw))
    assert r.payload is not None and r.report["blockers"] == []


def test_existing_slug_in_legacy_registry_blocks():
    _blocked(_run(baseline=_baseline(registry=b"enabled: [' sample-import ']\n")), "slug_exists_in_registry")


def test_baseline_registry_is_read_in_memory(monkeypatch):
    seen = []

    def spy(config_path=None):
        seen.append(config_path)
        return read_skill_registry(config_path)

    monkeypatch.setattr(adapter, "read_skill_registry", spy)
    assert _run().payload is not None
    assert len(seen) == 1 and not isinstance(seen[0], Path)
    assert seen[0].read_text(encoding="utf-8") == REGISTRY.decode()


@pytest.mark.parametrize("returned", [None, object(), {"checks": [{"name": "package_schema", "passed": True}]}])
def test_missing_or_foreign_receipt_blocks(monkeypatch, returned):
    monkeypatch.setattr(adapter, "validate_skill_candidate", lambda candidate, *, baseline, slug: returned)
    r = _run()
    _blocked(r, "validator_failed")
    assert r.report["validation"]["receipt"] is None


def test_unrecognized_passing_check_blocks(monkeypatch):
    def future(candidate, *, baseline, slug):
        return SkillAuthoringReceipt(slug, candidate.fingerprint, "", 1, 1,
                                     ({"name": "future_unknown", "passed": True},))

    monkeypatch.setattr(adapter, "validate_skill_candidate", future)
    r = _run()
    _blocked(r, "validation_check_unrecognized")
    assert r.report["validation"]["receipt"]["checks"] == [{"name": "unrecognized_check", "passed": True}]
    assert "future_unknown" not in r.report_json.decode()


@pytest.mark.parametrize("slug,code", [("Bad_Slug", "slug_invalid"), ("skill-creator", "slug_reserved"),
                                       ("my-claude-tool", "slug_reserved")])
def test_invalid_and_reserved_slugs_block(slug, code):
    _blocked(_run(slug=slug), code)


def test_validator_staging_failure_blocks_without_detail(monkeypatch):
    def raiser(*a, **k):
        raise OSError("disk /private/tmp/x")

    monkeypatch.setattr(validation.tempfile, "TemporaryDirectory", raiser)
    r = _run()
    _blocked(r, "validator_staging_failed")
    assert r.report["validation"]["validator_refusal"] == "validator_staging_failed"
    assert "/private/tmp" not in r.report_json.decode()
    assert r.report["validation_snapshot_digest"] is not None


def test_validator_scope_and_generic_failures_map_to_fixed_codes(monkeypatch):
    def scope(*a, **k):
        raise SandboxError("x")

    monkeypatch.setattr(adapter, "validate_skill_candidate", scope)
    _blocked(_run(), "validator_scope_refused")

    def generic(*a, **k):
        raise RuntimeError("raw detail canary")

    monkeypatch.setattr(adapter, "validate_skill_candidate", generic)
    r = _run()
    _blocked(r, "validator_failed")
    assert "raw detail canary" not in r.report_json.decode()


def test_unrecognized_validator_check_and_receipt_binding(monkeypatch):
    def weird(candidate, *, baseline, slug):
        return SkillAuthoringReceipt(slug, candidate.fingerprint, "", 1, 1,
                                     ({"name": "weird<check>", "passed": False, "detail": "leak-canary"},))

    monkeypatch.setattr(adapter, "validate_skill_candidate", weird)
    r = _run()
    _blocked(r, "validation_unrecognized_check_failed")
    assert "validation_failed" in r.report["blockers"]
    assert r.report["validation"]["receipt"]["checks"] == [{"name": "unrecognized_check", "passed": False}]
    text = r.report_json.decode()
    assert "leak-canary" not in text and "weird" not in text

    def mismatch(candidate, *, baseline, slug):
        return SkillAuthoringReceipt(slug, "0" * 64, "", 1, 1, ({"name": "package_schema", "passed": True},))

    monkeypatch.setattr(adapter, "validate_skill_candidate", mismatch)
    _blocked(_run(), "receipt_binding_mismatch")


# ---------------------------------------------------------------- cancellation and schema

@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_cancellation_at_each_stage_returns_no_payload(n):
    calls = []

    def cb():
        calls.append(1)
        return len(calls) == n

    r = _run(cancel_check=cb)
    assert r.report["validation"]["cancelled_stage"] == adapter.CANCEL_STAGES[n - 1]
    assert len(calls) == n
    _blocked(r, "cancelled")
    assert r.evidence is None
    receipt = r.report["validation"]["receipt"]
    assert (receipt is not None) == (n >= 3)
    if n == 1:
        assert r.report["validation"]["inventory"]["before_observed"] is False


def test_cancel_check_called_four_times_on_success():
    calls = []
    r = _run(cancel_check=lambda: calls.append(1) or False)
    assert r.produced, r.report["blockers"]
    assert len(calls) == 4


def _raise_cb():
    raise RuntimeError("cb detail")


@pytest.mark.parametrize("cb", [_raise_cb, lambda: 1, lambda: None])
def test_cancel_check_failure_blocks(cb):
    r = _run(cancel_check=cb)
    _blocked(r, "cancel_check_failed")
    assert "cancelled" in r.report["blockers"]
    assert "cb detail" not in r.report_json.decode()


@pytest.mark.parametrize("version", [2, True])
def test_unknown_schema_version_refuses(version):
    _blocked(_run(schema_version=version), "schema_version_unsupported")


def test_unsupported_profile_refuses():
    r = _run(profile="p1-scripts")
    _blocked(r, "profile_unsupported")
    assert r.report["validation"]["profile"] == "unsupported"


def test_type_misuse_raises_fixed_type_error():
    ri = adapter.ReviewedInputs(sidecar=_sidecar(), matcher_cases=_matcher())
    with pytest.raises(TypeError, match="invalid adapter input"):
        adapter.adapt_instruction_package((f for f in _source()), reviewed_inputs=ri,
                                          baseline=_baseline(), slug=SLUG)
    with pytest.raises(TypeError, match="invalid adapter input"):
        adapter.adapt_instruction_package([File("SKILL.md", True, b"")], reviewed_inputs=ri,
                                          baseline=_baseline(), slug=SLUG)
    with pytest.raises(TypeError, match="invalid adapter input"):
        adapter.adapt_instruction_package(_source(), reviewed_inputs=ri, baseline=None, slug=SLUG)
    with pytest.raises(TypeError, match="invalid adapter input"):
        adapter.adapt_instruction_package(
            _source(), reviewed_inputs=adapter.ReviewedInputs(sidecar="text", matcher_cases=_matcher()),
            baseline=_baseline(), slug=SLUG)


# ---------------------------------------------------------------- identity drift and reuse

def _package_two():
    skill = SKILL_MD.replace(b"name: sample-import", b"name: sample-import-two")
    sc = _sidecar(lambda d: d.__setitem__("skill_id", "sample-import-two"))
    return _source(**{"SKILL.md": skill}), sc


def test_evidence_reuse_invalidated_by_each_identity_change(monkeypatch):
    base = _run().report
    two_src, two_sc = _package_two()
    variants = [
        ("source_digest", lambda: _run(_source(**{"references/guide.md": GUIDE + b"x"}))),
        ("source_digest", lambda: _run(_source(**{"LICENSE.txt": LICENSE + b"x"}))),
        ("inputs_digest", lambda: _run(sidecar=_sidecar(lambda d: d.__setitem__("display_name", "Other")))),
        ("inputs_digest", lambda: _run(matcher=_matcher(request="Please summarize the sample imported list"))),
        ("baseline_digest", lambda: _run(baseline=_baseline(registry=REGISTRY + b"# c\n"))),
        ("inputs_digest", lambda: _run(two_src, sidecar=two_sc, slug="sample-import-two")),
    ]
    for field, make in variants:
        cur = make().report
        assert cur[field] != base[field], field
        assert not adapter.evidence_reusable(base, cur)

    changed = ToolInventory(frozenset({"status_models", "other_tool"}), True)
    monkeypatch.setattr(adapter, "configured_tool_inventory", lambda: changed)
    monkeypatch.setattr(validation, "configured_tool_inventory", lambda: changed)
    cur = _run().report
    assert cur["inventory_digest"] != base["inventory_digest"]
    assert not adapter.evidence_reusable(base, cur)
    monkeypatch.setattr(adapter, "configured_tool_inventory", lambda: INV)
    monkeypatch.setattr(validation, "configured_tool_inventory", lambda: INV)

    orig = adapter._dependency_bytes
    monkeypatch.setattr(adapter, "_dependency_bytes",
                        lambda m: b"changed" if m == "jarvis.skill_catalog" else orig(m))
    cur = _run().report
    assert cur["parser_fingerprint"] != base["parser_fingerprint"]
    assert not adapter.evidence_reusable(base, cur)
    monkeypatch.setattr(adapter, "_dependency_bytes", orig)

    monkeypatch.setattr(adapter, "_adapter_code_bytes", lambda: b"x")
    cur = _run().report
    assert cur["validation"]["adapter_code_digest"] != base["validation"]["adapter_code_digest"]
    assert not adapter.evidence_reusable(base, cur)


def test_blocked_results_still_bind_inputs():
    r1 = _run(matcher=None)
    r2 = _run(matcher=None, sidecar=_sidecar(lambda d: d.__setitem__("display_name", "Other")))
    assert r1.report["inputs_digest"] != r2.report["inputs_digest"]
    assert not r1.produced and not r2.produced
    assert not adapter.evidence_reusable(r1.report, r2.report)


def test_evidence_reusable_fails_closed_on_unknown_schema_or_tamper():
    prev = _run().report
    assert adapter.evidence_reusable(dict(prev, schema_version=2), prev) is False
    assert adapter.evidence_reusable(dict(prev, schema_version=True), prev) is False
    assert adapter.evidence_reusable(dict(prev, blockers=["cancelled"]), prev) is False
    assert adapter.evidence_reusable(prev, "x") is False
    assert adapter.evidence_reusable(prev, prev) is True


def test_parser_fingerprint_unavailable_blocks(monkeypatch):
    orig = adapter._dependency_bytes
    monkeypatch.setattr(adapter, "_dependency_bytes", lambda m: None if m == "sandbox.artifacts" else orig(m))
    _blocked(_run(), "parser_fingerprint_unavailable")


def test_report_digest_matches_canonical_framing():
    r = _run()
    assert r.report["report_digest"] == adapter.report_digest(r.report)
    assert r.report_json == json.dumps(r.report, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True).encode()
