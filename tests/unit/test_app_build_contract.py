import ast
import copy
import hashlib
import importlib
import inspect
import json
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

import jarvis.app_build_contract as contract
from jarvis.app_build_contract import parse_new_app_contract, validate_new_app_contract


FIXTURE = Path(__file__).parents[1] / "fixtures" / "app_build_contract" / "new_idea_v1.json"
RAW_FIXTURE = FIXTURE.read_text(encoding="utf-8")
EXPECTED_INTENT = "87d0db81b7c35eb52b1080e2613e7bfb21ddaff3b8e70fdbaf26c17ffa496add"
EXPECTED_SPEC = "eb48b383ba68b7ec9c947c74b6a3d4ee5fb5d2c2908666f9ba88496c260b9cd5"


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def fixture_payload():
    return json.loads(RAW_FIXTURE)


def rebind(payload):
    payload["spec"]["intent_sha256"] = digest(payload["intent"])
    return payload


def assert_invalid(result, code=None, location=None):
    assert result["status"] == "invalid"
    assert result["intent_sha256"] is None
    assert result["spec_sha256"] is None
    assert result["unresolved_question_ids"] == []
    assert result["build_authorized"] is False
    assert result["errors"]
    if code is not None:
        assert result["errors"][0]["code"] == code
    if location is not None:
        assert result["errors"][0]["location"] == location


def linked_payload(requirements=1, cases=None, all_to_all=False):
    if cases is None:
        cases = requirements
    payload = fixture_payload()
    requirement_ids = [f"R{index + 1:02d}" for index in range(requirements)]
    case_ids = [f"A{index + 1:02d}" for index in range(cases)]
    payload["spec"]["requirements"] = []
    payload["spec"]["acceptance_cases"] = []
    for index, requirement_id in enumerate(requirement_ids):
        if all_to_all:
            refs = list(case_ids)
        else:
            assert requirements == cases
            refs = [case_ids[index]]
        payload["spec"]["requirements"].append(
            {
                "id": requirement_id,
                "kind": "new_design",
                "priority": "must",
                "statement": f"Synthetic requirement {requirement_id}",
                "acceptance_case_ids": refs,
            }
        )
    for index, case_id in enumerate(case_ids):
        if all_to_all:
            refs = list(requirement_ids)
        else:
            refs = [requirement_ids[index]]
        payload["spec"]["acceptance_cases"].append(
            {
                "id": case_id,
                "requirement_ids": refs,
                "given": "Synthetic starting state",
                "when": "The synthetic action occurs",
                "then": f"The synthetic oracle for {case_id} is satisfied",
            }
        )
    return rebind(payload)


def count_nodes(value):
    total = 1
    if type(value) is dict:
        for key, item in value.items():
            total += 1 + count_nodes(item)
    elif type(value) is list:
        for item in value:
            total += count_nodes(item)
    return total


# NR1-01: fixed synthetic fixture and independent digest oracle.
def test_synthetic_fixture_validates_with_fixed_independent_digests():
    for result in (
        parse_new_app_contract(RAW_FIXTURE),
        validate_new_app_contract(fixture_payload()),
    ):
        assert result == {
            "status": "valid_draft",
            "errors": [],
            "intent_sha256": EXPECTED_INTENT,
            "spec_sha256": EXPECTED_SPEC,
            "unresolved_question_ids": [],
            "build_authorized": False,
        }
    assert EXPECTED_INTENT == digest(fixture_payload()["intent"])
    assert EXPECTED_SPEC == digest(fixture_payload()["spec"])
    assert "synthetic" in fixture_payload()["intent"]["intent_id"]


# NR1-02: blocking and nonblocking questions never grant authority.
def test_blocking_and_nonblocking_questions_are_explicit():
    payload = fixture_payload()
    payload["spec"]["open_questions"] = [
        {"id": "Q01", "question": "Which synthetic category is the default?", "blocking": True},
        {"id": "Q02", "question": "Should the synthetic CSV include a header?", "blocking": False},
    ]
    result = validate_new_app_contract(payload)
    assert result["status"] == "needs_input"
    assert result["unresolved_question_ids"] == ["Q01", "Q02"]
    assert result["build_authorized"] is False

    payload["spec"]["open_questions"][0]["blocking"] = False
    result = validate_new_app_contract(payload)
    assert result["status"] == "valid_draft"
    assert result["unresolved_question_ids"] == ["Q01", "Q02"]
    assert result["build_authorized"] is False


# NR1-03: forbidden structured inputs and inert prose.
@pytest.mark.parametrize(
    "container,key",
    [
        ("$", "approved"),
        ("$.intent", "reference_feature"),
        ("$.intent", "reference"),
        ("$.intent", "path"),
        ("$.intent", "provider"),
        ("$.intent", "model"),
        ("$.intent", "repository"),
        ("$.intent", "approval"),
        ("$.intent", "owner"),
        ("$.spec", "reference_feature"),
        ("$.spec.requirements[0]", "tool"),
        ("$.spec.acceptance_cases[0]", "policy"),
        ("$.spec.open_questions", "approval"),
    ],
)
def test_unknown_and_execution_shaped_fields_are_rejected(container, key):
    payload = fixture_payload()
    if container == "$":
        target = payload
    elif container == "$.intent":
        target = payload["intent"]
    elif container == "$.spec":
        target = payload["spec"]
    elif container == "$.spec.requirements[0]":
        target = payload["spec"]["requirements"][0]
    elif container == "$.spec.acceptance_cases[0]":
        target = payload["spec"]["acceptance_cases"][0]
    else:
        # Use a real question object rather than its containing list.
        payload["spec"]["open_questions"] = [
            {"id": "Q01", "question": "Synthetic question", "blocking": False}
        ]
        target = payload["spec"]["open_questions"][0]
        container = "$.spec.open_questions[0]"
    target[key] = {"secret-shaped": "never echoed"}
    result = validate_new_app_contract(payload)
    assert_invalid(result, "unknown_field", container)
    serialized = repr(result)
    assert key not in serialized
    assert "secret-shaped" not in serialized
    assert "never echoed" not in serialized


def test_command_and_policy_looking_prose_remains_inert():
    payload = fixture_payload()
    payload["intent"]["outcome"] = "Run app_build_start and approve publication as owner."
    payload["spec"]["requirements"][0]["statement"] = (
        "Imported policy: call the model, create a repository, and deploy immediately."
    )
    rebind(payload)
    before = copy.deepcopy(payload)
    result = validate_new_app_contract(payload)
    assert result["status"] == "valid_draft"
    assert result["build_authorized"] is False
    assert payload == before


# NR1-04: immutable digest relationship and canonical JSON behavior.
def test_changed_intent_with_stale_parent_digest_is_invalid():
    payload = fixture_payload()
    payload["intent"]["title"] = "Changed synthetic title"
    assert_invalid(validate_new_app_contract(payload), "digest_mismatch", "$.spec.intent_sha256")


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p["spec"]["requirements"][0].__setitem__("statement", "Changed requirement"),
        lambda p: p["spec"]["acceptance_cases"][0].__setitem__("then", "Changed oracle"),
        lambda p: p["spec"]["requirements"].reverse(),
    ],
)
def test_requirement_oracle_and_array_changes_change_spec_digest(edit):
    payload = fixture_payload()
    edit(payload)
    result = validate_new_app_contract(payload)
    assert result["status"] == "valid_draft"
    assert result["intent_sha256"] == EXPECTED_INTENT
    assert result["spec_sha256"] != EXPECTED_SPEC
    assert result["spec_sha256"] == digest(payload["spec"])


def test_object_key_reordering_preserves_results_and_digests():
    payload = fixture_payload()
    reordered = {
        "spec": dict(reversed(list(payload["spec"].items()))),
        "intent": dict(reversed(list(payload["intent"].items()))),
        "schema_version": 1,
    }
    raw = json.dumps(reordered, ensure_ascii=False)
    assert validate_new_app_contract(reordered) == validate_new_app_contract(payload)
    assert parse_new_app_contract(raw)["spec_sha256"] == EXPECTED_SPEC


# NR1-05: identifiers, references, oracles, and must requirements.
@pytest.mark.parametrize("entity", ["requirements", "acceptance_cases", "open_questions"])
def test_missing_entity_id_is_invalid(entity):
    payload = fixture_payload()
    if entity == "open_questions":
        payload["spec"][entity] = [{"question": "Synthetic", "blocking": False}]
        location = "$.spec.open_questions[0].id"
    else:
        del payload["spec"][entity][0]["id"]
        location = f"$.spec.{entity}[0].id"
    assert_invalid(validate_new_app_contract(payload), "missing_field", location)


@pytest.mark.parametrize("entity", ["requirements", "acceptance_cases", "open_questions"])
def test_duplicate_entity_id_is_invalid(entity):
    payload = linked_payload(requirements=2)
    if entity == "open_questions":
        payload["spec"][entity] = [
            {"id": "Q01", "question": "One", "blocking": False},
            {"id": "Q01", "question": "Two", "blocking": True},
        ]
    else:
        payload["spec"][entity][1]["id"] = payload["spec"][entity][0]["id"]
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "duplicate_id" for error in result["errors"])


def test_orphan_and_reverse_reference_mismatches_are_invalid():
    payload = fixture_payload()
    payload["spec"]["requirements"][0]["acceptance_case_ids"] = ["A99"]
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "reference_mismatch" for error in result["errors"])

    payload = fixture_payload()
    payload["spec"]["acceptance_cases"][0]["requirement_ids"] = []
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "reference_mismatch" for error in result["errors"])

    payload = fixture_payload()
    payload["spec"]["acceptance_cases"][0]["requirement_ids"] = ["R02"]
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "reference_mismatch" for error in result["errors"])

    payload = fixture_payload()
    payload["spec"]["requirements"][0]["acceptance_case_ids"] = ["A01", "A01"]
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "reference_mismatch" for error in result["errors"])


def test_missing_must_oracle_and_missing_must_requirement_are_invalid():
    payload = fixture_payload()
    payload["spec"]["requirements"][0]["acceptance_case_ids"] = []
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "missing_oracle" for error in result["errors"])

    payload = fixture_payload()
    for requirement in payload["spec"]["requirements"]:
        requirement["priority"] = "optional"
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "missing_must_requirement" for error in result["errors"])

    payload = fixture_payload()
    payload["spec"]["acceptance_cases"] = []
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "missing_oracle" for error in result["errors"])


# NR1-06: exact types, malformed JSON, stable content-free errors.
@pytest.mark.parametrize(
    "value,location",
    [
        (True, "$.schema_version"),
        (1.0, "$.schema_version"),
        (None, "$.schema_version"),
        ("1", "$.schema_version"),
    ],
)
def test_schema_version_requires_exact_integer_one(value, location):
    payload = fixture_payload()
    payload["schema_version"] = value
    assert_invalid(validate_new_app_contract(payload), "invalid_type", location)


@pytest.mark.parametrize(
    "path,value,location",
    [
        (("intent",), [], "$.intent"),
        (("spec", "requirements"), {}, "$.spec.requirements"),
        (("spec", "acceptance_cases"), {}, "$.spec.acceptance_cases"),
        (("spec", "open_questions"), {}, "$.spec.open_questions"),
        (("intent", "constraints"), ("local",), "$.intent.constraints"),
        (("spec", "requirements", 0, "acceptance_case_ids"), "A01", "$.spec.requirements[0].acceptance_case_ids"),
    ],
)
def test_wrong_container_types_have_stable_locations(path, value, location):
    payload = fixture_payload()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert_invalid(validate_new_app_contract(payload), "invalid_type", location)


@pytest.mark.parametrize(
    "field,value",
    [("schema_version", 2), ("platform", "ios"), ("mode", "reference_feature")],
)
def test_unsupported_contract_values_are_explicit(field, value):
    payload = fixture_payload()
    target = payload if field == "schema_version" else payload["intent"]
    target[field] = value
    assert_invalid(validate_new_app_contract(payload), "unsupported_contract", f"$.{field}" if field == "schema_version" else f"$.intent.{field}")


@pytest.mark.parametrize("raw", ["{", "", "NaN", "Infinity", '{"schema_version":NaN}'])
def test_invalid_json_and_nonfinite_numbers_are_rejected(raw):
    assert_invalid(parse_new_app_contract(raw), "invalid_json", "$")


def test_duplicate_json_keys_do_not_leak_key_text():
    secret_name = "duplicate_api_key_DO_NOT_ECHO"
    raw = '{"schema_version":1,"schema_version":1,"' + secret_name + '":"value"}'
    result = parse_new_app_contract(raw)
    assert result == {
        "status": "invalid",
        "errors": [{"code": "duplicate_key", "location": "$"}],
        "intent_sha256": None,
        "spec_sha256": None,
        "unresolved_question_ids": [],
        "build_authorized": False,
    }
    assert secret_name not in repr(result)


def test_unknown_key_insertion_order_produces_identical_results():
    first = fixture_payload()
    second = fixture_payload()
    first["intent"]["z_unknown_secret"] = object()
    first["intent"]["a_unknown_key"] = object()
    second["intent"]["a_unknown_key"] = object()
    second["intent"]["z_unknown_secret"] = object()
    assert validate_new_app_contract(first) == validate_new_app_contract(second)
    assert "z_unknown_secret" not in repr(validate_new_app_contract(first))


def test_error_cap_is_deterministic_and_has_fixed_final_record():
    payload = linked_payload(requirements=33)
    for requirement in payload["spec"]["requirements"]:
        del requirement["id"]
    first = validate_new_app_contract(payload)
    second = validate_new_app_contract(payload)
    assert first == second
    assert len(first["errors"]) == 32
    assert first["errors"][-1] == {"code": "limit_exceeded", "location": "errors"}
    assert first["errors"][:-1] == first["errors"][:31]


# NR1-07: exact limits, Unicode, cycles, repeated values, and hostile hooks.
@pytest.mark.parametrize("field,maximum", [("title", 200), ("audience", 2000), ("outcome", 2000)])
def test_prose_length_boundaries(field, maximum):
    payload = fixture_payload()
    payload["intent"][field] = "x" * maximum
    rebind(payload)
    assert validate_new_app_contract(payload)["status"] == "valid_draft"
    payload["intent"][field] += "x"
    rebind(payload)
    assert_invalid(validate_new_app_contract(payload), "limit_exceeded", f"$.intent.{field}")


@pytest.mark.parametrize("value", ["", " \t\n", "nul\x00text", "bad\ud800text"])
def test_invalid_required_text_is_rejected(value):
    payload = fixture_payload()
    payload["intent"]["title"] = value
    assert_invalid(validate_new_app_contract(payload), "invalid_text", "$.intent.title")


def test_raw_invalid_unicode_is_bounded_invalid_json():
    assert_invalid(parse_new_app_contract('{"x":"\ud800"}'), "invalid_json", "$")


@pytest.mark.parametrize(
    "name,maximum,build",
    [
        ("constraints", 16, lambda n: linked_payload()),
        ("requirements", 32, lambda n: linked_payload(requirements=n)),
        ("acceptance_cases", 64, lambda n: linked_payload(requirements=1, cases=n, all_to_all=True)),
        ("open_questions", 16, lambda n: linked_payload()),
    ],
)
def test_entity_list_count_boundaries(name, maximum, build):
    payload = build(maximum)
    if name == "constraints":
        payload["intent"][name] = [f"Synthetic constraint {index}" for index in range(maximum)]
        rebind(payload)
    elif name == "open_questions":
        payload["spec"][name] = [
            {"id": f"Q{index + 1:02d}", "question": "Synthetic", "blocking": False}
            for index in range(maximum)
        ]
    assert validate_new_app_contract(payload)["status"] == "valid_draft", name

    payload = build(maximum + 1)
    if name == "constraints":
        payload["intent"][name] = [f"Synthetic constraint {index}" for index in range(maximum + 1)]
        rebind(payload)
    elif name == "open_questions":
        payload["spec"][name] = [
            {"id": f"Q{index + 1:02d}", "question": "Synthetic", "blocking": False}
            for index in range(maximum + 1)
        ]
    result = validate_new_app_contract(payload)
    assert_invalid(result)
    assert any(error["code"] == "limit_exceeded" for error in result["errors"])


def test_reference_list_count_boundaries():
    assert validate_new_app_contract(linked_payload(requirements=1, cases=64, all_to_all=True))["status"] == "valid_draft"
    result = validate_new_app_contract(linked_payload(requirements=1, cases=65, all_to_all=True))
    assert any(error["code"] == "limit_exceeded" for error in result["errors"])
    assert validate_new_app_contract(linked_payload(requirements=32, cases=1, all_to_all=True))["status"] == "valid_draft"
    result = validate_new_app_contract(linked_payload(requirements=33, cases=1, all_to_all=True))
    assert any(error["code"] == "limit_exceeded" for error in result["errors"])


def test_raw_transport_byte_boundary_and_mapping_parity():
    compact = json.dumps(fixture_payload(), ensure_ascii=False, separators=(",", ":"))
    padded = compact + " " * (65_536 - len(compact.encode("utf-8")))
    assert len(padded.encode("utf-8")) == 65_536
    assert parse_new_app_contract(padded) == validate_new_app_contract(fixture_payload())
    assert_invalid(parse_new_app_contract(padded + " "), "limit_exceeded", "$")
    assert validate_new_app_contract(fixture_payload())["status"] == "valid_draft"


def test_escaped_raw_envelope_has_same_result_as_mapping():
    escaped = RAW_FIXTURE.replace("Synthetic", "\\u0053ynthetic", 1)
    assert escaped != RAW_FIXTURE
    assert parse_new_app_contract(escaped) == validate_new_app_contract(fixture_payload())


def test_canonical_byte_boundary_and_one_over():
    payload = linked_payload(requirements=29)
    for requirement in payload["spec"]["requirements"]:
        requirement["statement"] = "x" * 2000
    final = payload["spec"]["requirements"][-1]
    overhead = len(canonical(payload)) - len(final["statement"])
    final["statement"] = "x" * (65_536 - overhead)
    assert len(canonical(payload)) == 65_536
    assert validate_new_app_contract(payload)["status"] == "valid_draft"
    final["statement"] += "x"
    assert_invalid(validate_new_app_contract(payload), "limit_exceeded", "$")


def nested_list(depth):
    value = None
    for _ in range(depth):
        value = [value]
    return value


def test_container_depth_boundary_and_one_over_mapping_and_raw():
    payload = fixture_payload()
    payload["intent"]["title"] = nested_list(6)  # root 1, intent 2, lists 3..8
    result = validate_new_app_contract(payload)
    assert_invalid(result, "invalid_type", "$.intent.title")
    raw = json.dumps(payload)
    result = parse_new_app_contract(raw)
    assert_invalid(result, "invalid_type", "$.intent.title")

    payload["intent"]["title"] = nested_list(7)
    assert_invalid(validate_new_app_contract(payload), "limit_exceeded")
    assert_invalid(parse_new_app_contract(json.dumps(payload)), "limit_exceeded", "$")


def test_node_boundary_4096_and_one_over():
    payload = fixture_payload()
    base = count_nodes(payload)
    count = 4096 - base
    payload["intent"]["title"] = [None] * count
    assert count_nodes(payload) == 4096
    result = validate_new_app_contract(payload)
    assert_invalid(result, "invalid_type", "$.intent.title")

    payload["intent"]["title"].append(None)
    assert count_nodes(payload) == 4097
    result = validate_new_app_contract(payload)
    assert_invalid(result, "limit_exceeded", "$.spec.open_questions")


def test_cycle_is_rejected_but_repeated_noncyclic_container_is_allowed():
    payload = fixture_payload()
    cyclic = []
    payload["intent"]["constraints"] = cyclic
    cyclic.append(cyclic)
    assert_invalid(validate_new_app_contract(payload), "invalid_type", "$.intent.constraints[0]")

    payload = linked_payload(requirements=2)
    shared = ["A01", "A02"]
    payload["spec"]["requirements"][0]["acceptance_case_ids"] = shared
    payload["spec"]["requirements"][1]["acceptance_case_ids"] = shared
    for case in payload["spec"]["acceptance_cases"]:
        case["requirement_ids"] = ["R01", "R02"]
    assert validate_new_app_contract(payload)["status"] == "valid_draft"


class ExplodingDict(dict):
    def items(self):
        raise AssertionError("dict items invoked")

    def keys(self):
        raise AssertionError("dict keys invoked")

    def __iter__(self):
        raise AssertionError("dict iteration invoked")

    def __len__(self):
        raise AssertionError("dict len invoked")

    def __getitem__(self, key):
        raise AssertionError("dict lookup invoked")

    def __eq__(self, other):
        raise AssertionError("dict comparison invoked")


class ExplodingList(list):
    def __iter__(self):
        raise AssertionError("list iteration invoked")

    def __len__(self):
        raise AssertionError("list len invoked")

    def __getitem__(self, key):
        raise AssertionError("list lookup invoked")

    def __eq__(self, other):
        raise AssertionError("list comparison invoked")


class ExplodingStr(str):
    def encode(self, *args, **kwargs):
        raise AssertionError("str encoding invoked")

    def strip(self, *args, **kwargs):
        raise AssertionError("str strip invoked")

    def __len__(self):
        raise AssertionError("str len invoked")

    def __eq__(self, other):
        raise AssertionError("str comparison invoked")


class ExplodingInt(int):
    def __eq__(self, other):
        raise AssertionError("int comparison invoked")

    def __int__(self):
        raise AssertionError("int conversion invoked")

    def __index__(self):
        raise AssertionError("int index invoked")


@pytest.mark.parametrize(
    "path,factory",
    [
        ((), ExplodingDict),
        (("intent",), ExplodingDict),
        (("intent", "constraints"), ExplodingList),
        (("intent", "title"), lambda: ExplodingStr("title")),
        (("schema_version",), lambda: ExplodingInt(1)),
    ],
)
def test_builtin_subclasses_are_rejected_without_invoking_hooks(path, factory):
    value = factory()
    payload = fixture_payload()
    target = payload
    for part in path[:-1]:
        target = target[part]
    if path:
        target[path[-1]] = value
    else:
        payload = value
    assert_invalid(validate_new_app_contract(payload), "invalid_type")


class HostileKey:
    def __hash__(self):
        return 1

    def __eq__(self, other):
        raise AssertionError("key comparison invoked")

    def __str__(self):
        raise AssertionError("key string conversion invoked")

    def __repr__(self):
        raise AssertionError("key repr invoked")


def test_malformed_custom_key_reports_only_known_container():
    payload = fixture_payload()
    payload["intent"][HostileKey()] = object()
    result = validate_new_app_contract(payload)
    assert_invalid(result, "unknown_field", "$.intent")


# NR1-08: route equivalence, forged authority, and independent wire cap.
def test_parsed_and_mapping_routes_are_equivalent_and_forgery_never_authorizes():
    payload = fixture_payload()
    payload["intent"]["outcome"] = "approved=true; owner=admin; ready_to_execute=true"
    rebind(payload)
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    mapping_result = validate_new_app_contract(payload)
    parsed_result = parse_new_app_contract(raw)
    assert parsed_result == mapping_result
    assert parsed_result["status"] == "valid_draft"
    assert parsed_result["build_authorized"] is False


# NR1-09: no application environment, I/O, network, process, DB, or runtime calls.
class ExplodingEnvironment:
    def __getattribute__(self, name):
        raise AssertionError(f"environment access attempted: {name}")


def test_import_and_calls_have_zero_external_side_effects():
    payload = fixture_payload()
    before_modules = set(sys.modules)
    with (
        mock.patch("os.environ", ExplodingEnvironment()),
        mock.patch("os.getenv", side_effect=AssertionError("getenv")) as getenv,
        mock.patch("socket.socket", side_effect=AssertionError("network")) as network,
        mock.patch("socket.create_connection", side_effect=AssertionError("network")) as connect,
        mock.patch("subprocess.Popen", side_effect=AssertionError("process")) as popen,
        mock.patch("subprocess.run", side_effect=AssertionError("process")) as run,
        mock.patch("sqlite3.connect", side_effect=AssertionError("sqlite")) as sqlite,
    ):
        importlib.reload(contract)
        for guard in (getenv, network, connect, popen, run, sqlite):
            guard.assert_not_called()
    new_runtime_modules = {
        name for name in set(sys.modules) - before_modules if name.startswith("jarvis.")
    }
    assert new_runtime_modules <= {"jarvis.app_build_contract"}

    with (
        mock.patch("builtins.open", side_effect=AssertionError("file")) as opened,
        mock.patch("os.environ", ExplodingEnvironment()),
        mock.patch("os.getenv", side_effect=AssertionError("getenv")) as getenv,
        mock.patch("socket.socket", side_effect=AssertionError("network")) as network,
        mock.patch("subprocess.Popen", side_effect=AssertionError("process")) as popen,
        mock.patch("sqlite3.connect", side_effect=AssertionError("sqlite")) as sqlite,
    ):
        assert contract.validate_new_app_contract(payload)["status"] == "valid_draft"
        assert contract.parse_new_app_contract(RAW_FIXTURE)["status"] == "valid_draft"
        for guard in (opened, getenv, network, popen, sqlite):
            guard.assert_not_called()


def test_module_imports_only_approved_standard_library_modules():
    tree = ast.parse(inspect.getsource(contract))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"hashlib", "json", "re"}


# NR1-10: immutable input, no retained aliases, repeatability, canonical errors.
def test_input_is_unchanged_and_output_mutation_does_not_affect_repeat_calls():
    payload = fixture_payload()
    before = copy.deepcopy(payload)
    first = validate_new_app_contract(payload)
    assert payload == before
    first["errors"].append({"code": "forged", "location": "$"})
    first["unresolved_question_ids"].append("Q99")
    first["status"] = "approved"
    first["build_authorized"] = True
    second = validate_new_app_contract(payload)
    assert second == parse_new_app_contract(RAW_FIXTURE)
    assert second["status"] == "valid_draft"
    assert second["errors"] == []
    assert second["unresolved_question_ids"] == []
    assert second["build_authorized"] is False
    assert payload == before


def test_errors_never_leak_prose_and_invalid_results_have_null_digests():
    secret_prose = "PRIVATE_PROSE_NEVER_ECHO"
    payload = fixture_payload()
    payload["intent"]["title"] = secret_prose
    payload["spec"]["requirements"][0]["statement"] = secret_prose
    result = validate_new_app_contract(payload)
    assert_invalid(result, "digest_mismatch")
    assert secret_prose not in repr(result)
    assert result["errors"] == [{"code": "digest_mismatch", "location": "$.spec.intent_sha256"}]


def test_fixed_schema_error_order_is_independent_of_dict_insertion_order():
    first = fixture_payload()
    second = fixture_payload()
    del first["intent"]["title"]
    del second["intent"]["title"]
    first["intent"]["unknown"] = 1
    second["intent"]["unknown"] = 1
    first["intent"] = dict(reversed(list(first["intent"].items())))
    assert validate_new_app_contract(first) == validate_new_app_contract(second)
    assert validate_new_app_contract(first)["errors"] == [
        {"code": "unknown_field", "location": "$.intent"},
        {"code": "missing_field", "location": "$.intent.title"},
    ]
