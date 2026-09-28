"""Shared synthetic examples for the Skills package and navigation contract."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from jarvis.agent_skills import SKILLS_DIR, load_skills, match_skill
from jarvis.bot.console_protocol import ALLOWED_ACTIONS, validate_request
from jarvis.skill_catalog import inspect_package
from jarvis.skill_selection import select_primary_skill
from scripts.check_skill_selection_fixtures import evaluate_fixture

FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills_workspace"


def _assert_process_graph(kind: str, nodes: list[dict]) -> None:
    """Enforce package graph invariants that JSON Schema cannot express."""
    ids = [node["step_id"] for node in nodes]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("process step IDs must be non-empty and unique")
    by_id = {node["step_id"]: node for node in nodes}
    for node in nodes:
        for edge in node["edges"]:
            if edge["to"] not in by_id:
                raise ValueError("process edge target must exist")
    if kind == "linear":
        expected = [([] if index + 1 == len(ids) else [{"to": ids[index + 1]}])
                    for index in range(len(ids))]
        if [node["edges"] for node in nodes] != expected:
            raise ValueError("linear process edges must follow listed order")
        return

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise ValueError("process graph cannot contain cycles")
        if step_id in visited:
            return
        visiting.add(step_id)
        for edge in by_id[step_id]["edges"]:
            visit(edge["to"])
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in ids:
        visit(step_id)


def _assert_catalog_detail_projection(card: dict, detail: dict) -> None:
    """Keep duplicated catalog summary fields aligned with the detail view."""
    shared_fields = (
        "skill_id", "display_name", "description", "category", "revision",
        "installation", "enabled", "readiness", "readiness_reasons",
        "verification", "example_ids", "blockers",
    )
    mismatched = [field for field in shared_fields if card.get(field) != detail.get(field)]
    if mismatched:
        raise ValueError(f"catalog/detail projection differs for: {', '.join(mismatched)}")


def test_package_metadata_fixture_matches_schema_and_runtime_catalog(tmp_path):
    schema = json.loads((FIXTURES / "schema" / "skill-metadata.schema.json").read_text())
    metadata = json.loads((FIXTURES / "package-metadata.json").read_text())

    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(metadata))
    assert errors == []

    root = tmp_path / metadata["skill_id"]
    root.mkdir()
    (root / "SKILL.md").write_text(
        f"---\nname: {metadata['skill_id']}\ndescription: Synthetic catalog fixture.\n---\n\n# Instructions\nUse only for this fixture.\n",
        encoding="utf-8",
    )
    (root / "mortimer.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")

    entry = inspect_package(root)

    _assert_process_graph(metadata["process"]["kind"], metadata["process"]["nodes"])

    assert entry.skill_id == metadata["skill_id"]
    assert entry.process_kind == metadata["process"]["kind"]
    assert [node["step_id"] for node in entry.process_nodes] == [
        node["step_id"] for node in metadata["process"]["nodes"]
    ]


def test_metadata_schema_refuses_unknown_top_level_fields():
    schema = json.loads((FIXTURES / "schema" / "skill-metadata.schema.json").read_text())
    metadata = json.loads((FIXTURES / "package-metadata.json").read_text())
    metadata["enable_it_now"] = True

    errors = list(Draft202012Validator(schema).iter_errors(metadata))

    assert any(error.validator == "additionalProperties" for error in errors)


@pytest.mark.parametrize("skill_id", ["claude-helper", "anthropic-tools"])
def test_metadata_schema_refuses_reserved_agent_skill_vendor_names(skill_id):
    schema = json.loads((FIXTURES / "schema" / "skill-metadata.schema.json").read_text())
    metadata = json.loads((FIXTURES / "package-metadata.json").read_text())
    metadata["skill_id"] = skill_id

    errors = list(Draft202012Validator(schema).iter_errors(metadata))

    assert any(error.validator == "pattern" and error.path[-1] == "skill_id"
               for error in errors)


def test_workspace_contract_fixtures_match_strict_v1_schemas():
    schema = json.loads(
        (FIXTURES / "schema" / "workspace-contract.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    fixtures = {
        "catalog": ("catalog-response.json", "catalog"),
        "detail": ("skill-detail.json", "detail"),
        "creatorRequest": ("creator-request.json", "creatorRequest"),
    }
    for definition, (filename, schema_name) in fixtures.items():
        document = json.loads((FIXTURES / filename).read_text())
        scoped_schema = {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{schema_name}",
        }
        errors = list(Draft202012Validator(
            scoped_schema, format_checker=FormatChecker(),
        ).iter_errors(document))
        assert errors == [], f"{definition} fixture errors: {errors}"

    events = json.loads((FIXTURES / "activity-events.json").read_text())
    event_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/activityEvent",
    }
    for event in events:
        errors = list(Draft202012Validator(
            event_schema, format_checker=FormatChecker(),
        ).iter_errors(event))
        assert errors == [], f"activity event fixture errors: {errors}"
        if event["type"] == "skill_step_finished" and event["status"] == "passed":
            missing_receipt = {
                **event,
                "evidence_refs": [
                    ref for ref in event["evidence_refs"]
                    if ref["kind"] != "check_receipt_id"
                ],
            }
            assert list(Draft202012Validator(
                event_schema, format_checker=FormatChecker(),
            ).iter_errors(missing_receipt)), (
                "a passed step event requires a trusted check receipt reference"
            )


def test_workspace_fixtures_are_revision_and_event_consistent():
    catalog = json.loads((FIXTURES / "catalog-response.json").read_text())
    detail = json.loads((FIXTURES / "skill-detail.json").read_text())
    request = json.loads((FIXTURES / "creator-request.json").read_text())
    events = json.loads((FIXTURES / "activity-events.json").read_text())

    card = next(item for item in catalog["items"] if item["skill_id"] == detail["skill_id"])
    _assert_catalog_detail_projection(card, detail)
    assert card["revision"] == detail["revision"]
    assert set(card["example_ids"]) == set(detail["example_ids"])
    assert request["expected_catalog_revision"] == catalog["catalog_revision"]
    _assert_process_graph(detail["process_kind"], detail["process_nodes"])
    from jarvis.admin.server import SkillRequestIn, _validated_skill_request

    assert _validated_skill_request(SkillRequestIn(**request))["operation"] == "draft"
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert len({event["event_id"] for event in events}) == len(events)
    assert len({event["run_id"] for event in events}) == 1
    assert all(event["skill_id"] == detail["skill_id"] for event in events)
    assert all(event["skill_revision"] == detail["revision"] for event in events)
    known_steps = {node["step_id"] for node in detail["process_nodes"]}
    assert all(event["step_id"] is None or event["step_id"] in known_steps for event in events)
    assert all(
        event["status"] != "passed" or any(
            ref["kind"] == "check_receipt_id" for ref in event["evidence_refs"]
        )
        for event in events
    )
    assert all(
        event["type"] != "skill_step_finished" or event["status"] != "passed"
        or any(ref["kind"] == "check_receipt_id" for ref in event["evidence_refs"])
        for event in events
    ), "passed fixture events require trusted validator evidence"


def test_catalog_detail_projection_rejects_status_drift():
    catalog = json.loads((FIXTURES / "catalog-response.json").read_text())
    detail = json.loads((FIXTURES / "skill-detail.json").read_text())
    card = catalog["items"][0]
    detail["readiness"] = "ready"

    with pytest.raises(ValueError, match="readiness"):
        _assert_catalog_detail_projection(card, detail)


def test_process_fixture_invariants_reject_broken_graphs():
    detail = json.loads((FIXTURES / "skill-detail.json").read_text())
    nodes = detail["process_nodes"]

    missing_target = json.loads(json.dumps(nodes))
    missing_target[0]["edges"][0]["to"] = "missing-step"
    with pytest.raises(ValueError, match="target must exist"):
        _assert_process_graph("linear", missing_target)

    duplicate_id = json.loads(json.dumps(nodes))
    duplicate_id[1]["step_id"] = duplicate_id[0]["step_id"]
    with pytest.raises(ValueError, match="unique"):
        _assert_process_graph("linear", duplicate_id)

    wrong_linear_order = json.loads(json.dumps(nodes))
    wrong_linear_order[0]["edges"][0]["to"] = wrong_linear_order[2]["step_id"]
    with pytest.raises(ValueError, match="listed order"):
        _assert_process_graph("linear", wrong_linear_order)

    cycle = json.loads(json.dumps(nodes))
    cycle[-1]["edges"] = [{"to": cycle[0]["step_id"]}]
    with pytest.raises(ValueError, match="cycles"):
        _assert_process_graph("branching", cycle)


def test_creator_request_fixture_matches_closed_api_contract():
    schema = json.loads(
        (FIXTURES / "schema" / "workspace-contract.schema.json").read_text()
    )
    document = json.loads((FIXTURES / "creator-request.json").read_text())
    scoped_schema = {
        "$schema": schema["$schema"], "$defs": schema["$defs"],
        "$ref": "#/$defs/creatorRequest",
    }
    validator = Draft202012Validator(
        scoped_schema, format_checker=FormatChecker(),
    )
    assert list(validator.iter_errors(document)) == []
    assert any(validator.iter_errors({**document, "catalog_revision": "a" * 64}))
    assert any(validator.iter_errors({key: value for key, value in document.items()
                                      if key != "expected_catalog_revision"}))
    assert any(validator.iter_errors({**document, "task_brief": None}))


def test_workspace_catalog_contract_rejects_unreviewed_response_fields():
    schema = json.loads(
        (FIXTURES / "schema" / "workspace-contract.schema.json").read_text()
    )
    document = json.loads((FIXTURES / "catalog-response.json").read_text())
    document["items"][0]["instruction_body"] = "must never be part of the catalog"
    scoped_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/catalog",
    }

    errors = list(Draft202012Validator(scoped_schema).iter_errors(document))

    assert any(error.validator == "additionalProperties" for error in errors)


def test_voice_action_fixture_maps_utterances_to_valid_bounded_requests():
    cases = json.loads((FIXTURES / "voice-actions.json").read_text())
    assert {case["action"] for case in cases} <= ALLOWED_ACTIONS
    assert len({case["utterance"] for case in cases}) == len(cases)
    assert {"Show my skills", "Open the skill creator", "Show its process"} <= {
        case["utterance"] for case in cases
    }

    for case in cases:
        request = {
            "type": "console/request",
            "version": 1,
            "session_id": str(uuid.uuid4()),
            "generation": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
            "revision": 0,
            "action": case["action"],
            "args": case.get("args", {}),
        }
        if "target" in case:
            request["target"] = case["target"]
        assert validate_request(request)["action"] == case["action"]


def test_declared_matcher_examples_match_legacy_and_v2_selectors():
    active = load_skills()
    catalog = {skill.name: inspect_package(skill.path.parent) for skill in active}
    fixture_tools = frozenset(
        tool for item in catalog.values() for tool in item.required_tools
    )
    fixture_capabilities = frozenset(
        capability for item in catalog.values() for capability in item.capabilities
    )
    fixture_readiness = {skill_id: "ready" for skill_id in catalog}
    fixture_privacy = frozenset(catalog)
    fixtures = Path(__file__).parents[1] / "fixtures" / "skills_authoring"
    for fixture in sorted(fixtures.glob("*/matcher-cases.json")):
        skill_id = fixture.parent.name
        package = inspect_package(SKILLS_DIR / skill_id)
        cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
        assert {case["id"] for case in cases} == set(package.example_ids)
        assert {case["expect_selected"] for case in cases} == {False, True}
        for case in cases:
            selected = match_skill(case["request"], active)
            assert (selected is not None and selected.name == skill_id) is case["expect_selected"], (
                skill_id, case["id"], getattr(selected, "name", None)
            )
            selection = select_primary_skill(
                case["request"], active, catalog,
                available_tools=fixture_tools,
                available_capabilities=fixture_capabilities,
                readiness=fixture_readiness,
                privacy_compatible_skill_ids=fixture_privacy,
            )
            assert (
                selection.selected is not None and selection.selected.name == skill_id
            ) is case["expect_selected"], (
                "v2", skill_id, case["id"],
                getattr(selection.selected, "name", None), selection.reason,
            )


def test_global_public_selection_corpus_has_exact_legacy_and_v2_outcomes():
    report = evaluate_fixture()

    assert report["provider_calls"] == 0
    assert report["evidence_mode"] == "synthetic_ready_route_and_tool_inventory"
    assert report["summary"] == {
        "case_count": 14,
        "passed": 14,
        "failed": 0,
        "positive_cases": 5,
        "no_skill_cases": 5,
        "overlap_cases": 4,
    }
    assert all(case["passed"] for case in report["cases"])
    assert all(
        case["legacy_skill_id"] == case["expected_skill_id"]
        and case["v2_skill_id"] == case["expected_skill_id"]
        for case in report["cases"]
    )
    assert all(case["v2_supporting_skill_id"] is None for case in report["cases"])


@pytest.mark.parametrize("bad_case", [
    {"utterance": "Open invalid skill", "action": "skill_select"},
    {"utterance": "Search too much", "action": "skills_search", "args": {"query": "x" * 257}},
    {"utterance": "Use unimplemented command", "action": "skill_run_now", "target": "run-a"},
])
def test_voice_fixture_contract_examples_reject_invalid_requests(bad_case):
    request = {
        "type": "console/request",
        "version": 1,
        "session_id": str(uuid.uuid4()),
        "generation": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "revision": 0,
        "action": bad_case["action"],
        "args": bad_case.get("args", {}),
    }
    if "target" in bad_case:
        request["target"] = bad_case["target"]

    with pytest.raises(ValueError):
        validate_request(request)
