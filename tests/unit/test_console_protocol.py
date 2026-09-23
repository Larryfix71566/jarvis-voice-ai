import re
import uuid
import pytest
from jarvis.bot.console_protocol import (
    ACTION_ARG_FIELDS, ALLOWED_ACTIONS, REQUIRED_SECONDARY_TARGET_ACTIONS,
    REQUIRED_TARGET_ACTIONS, validate_request, response, validate_ready,
    validate_inventory,
)


def _native_console_source() -> str:
    source = Path(__file__).parents[2] / "macos" / "JarvisKit" / "Sources" / "JarvisKit" / "ConsoleProtocol.swift"
    return source.read_text()


def _native_registry_source() -> str:
    source = Path(__file__).parents[2] / "macos" / "MortimerHost" / "Sources" / "MortimerHost" / "App" / "ConsoleActionRegistry.swift"
    return source.read_text()


def _native_console_case_map() -> dict[str, str]:
    text = _native_console_source()
    start = text.index("public enum ConsoleAction")
    end = text.index("\n}\n\npublic struct ConsoleHello", start)
    actions: dict[str, str] = {}
    for line in text[start:end].splitlines():
        stripped = line.strip()
        if not stripped.startswith("case "):
            continue
        for declaration in stripped[5:].split(","):
            declaration = declaration.strip()
            if " = " in declaration:
                case_name, raw = declaration.split(" = ", 1)
                actions[case_name] = raw.strip().strip('"')
            elif declaration:
                actions[declaration] = declaration
    return actions


def _native_console_actions() -> set[str]:
    return set(_native_console_case_map().values())


def _native_console_sets() -> tuple[dict[str, set[str]], set[str], set[str]]:
    text = _native_registry_source()
    cases = _native_console_case_map()
    fields_start = text.index("private static let argumentFields")
    fields_end = text.index("\n\n    private static func argumentsAreWellTyped", fields_start)
    fields: dict[str, set[str]] = {}
    for match in re.finditer(r"\.(\w+):\s*\[([^]]*)\]", text[fields_start:fields_end]):
        fields[cases[match.group(1)]] = set(re.findall(r'"([^"]+)"', match.group(2)))

    def parse_set(name: str, end_marker: str | None = None) -> set[str]:
        start = text.index(name)
        end = text.index(end_marker, start) if end_marker else text.rfind("\n}")
        return {cases[case] for case in re.findall(r"\.(\w+)", text[start:end])}

    targets = parse_set("private static let targetActions", "\n\n    private static let secondaryTargetActions")
    secondary = parse_set("private static let secondaryTargetActions")
    return fields, targets, secondary


def req(**overrides):
    base = {"type":"console/request", "version":1,
            "session_id":str(uuid.uuid4()), "generation":str(uuid.uuid4()),
            "request_id":str(uuid.uuid4()), "revision":0,
            "action":"inventory", "args":{}}
    base.update(overrides)
    return base


def test_request_normalizes_and_rejects_unknown_or_nonfinite():
    out = validate_request(req())
    assert out["type"] == "console/request"
    with pytest.raises(ValueError): validate_request(req(extra=True))
    with pytest.raises(ValueError): validate_request(req(args={"x": float("nan")}))
    with pytest.raises(ValueError): validate_request(req(target={"id": 1}))
    with pytest.raises(ValueError): validate_request(req(args={"blob": "x" * 40000}))


def test_request_matches_native_target_and_argument_contract():
    assert ALLOWED_ACTIONS == _native_console_actions()
    native_fields, native_targets, native_secondary = _native_console_sets()
    assert {key: set(value) for key, value in ACTION_ARG_FIELDS.items() if value} == native_fields
    assert REQUIRED_TARGET_ACTIONS == native_targets
    assert REQUIRED_SECONDARY_TARGET_ACTIONS == native_secondary
    with pytest.raises(ValueError):
        validate_request(req(action="result_mode", args={"mode": "sources"}))
    for action, target in (("compare_set", "result-a"),
                           ("graph_path", "node-a")):
        with pytest.raises(ValueError):
            validate_request(req(action=action, target=target))
        accepted_pair = validate_request(req(action=action, target=target,
                                             secondary_target="peer-b"))
        assert accepted_pair["secondary_target"] == "peer-b"
    with pytest.raises(ValueError):
        validate_request(req(action="atlas_move", target="card-a"))

    assert validate_request(req(action="atlas_move", target="card-a",
                                args={"row": 2, "column": 1}))['action'] == "atlas_move"
    assert validate_request(req(action="atlas_move", target="card-a",
                                secondary_target="card-b",
                                args={"relation": "left"}))['action'] == "atlas_move"
    with pytest.raises(ValueError):
        validate_request(req(action="atlas_move", target="card-a", args={"row": 2}))
    with pytest.raises(ValueError):
        validate_request(req(action="graph_search", args={"query": "x" * 201}))
    assert validate_request(req(action="graph_focus", target="node-a",
                                args={"depth": 3}))['args']["depth"] == 3
    with pytest.raises(ValueError):
        validate_request(req(action="graph_focus", target="node-a", args={"depth": 5}))
    with pytest.raises(ValueError):
        validate_request(req(action="view_set", args={"mode": 2}))
    with pytest.raises(ValueError):
        validate_request(req(action="input_question", args={"question": 2}))
    with pytest.raises(ValueError):
        validate_request(req(action="appearance_set", args={"layout": "2"}))
    with pytest.raises(ValueError):
        validate_request(req(action="shared_content", args={"attachment_ids": []}))
    accepted = validate_request(req(action="view_set", args={"mode": "atlas"}))
    assert accepted["args"]["mode"] == "atlas"


def test_response_is_bounded_and_status_closed():
    out = response(request_id=req()["request_id"], session_id=req()["session_id"],
                   generation=req()["generation"], status="ok", code="done", summary="x" * 500)
    assert len(out["summary"]) == 240
    with pytest.raises(ValueError):
        response(request_id=req()["request_id"], session_id=req()["session_id"],
                 generation=req()["generation"], status="done", code="x", summary="x")


def test_ready_requires_the_hello_session_and_generation():
    session_id = str(uuid.uuid4())
    generation = str(uuid.uuid4())
    ready = validate_ready({
        "type": "console/ready", "version": 1,
        "session_id": session_id, "generation": generation,
        "actions": ["view_set"], "input_types": ["text/plain"],
    }, session_id=session_id, generation=generation)
    assert ready["actions"] == ["view_set"]
    with pytest.raises(ValueError):
        validate_ready({
            "type": "console/ready", "version": 1,
            "session_id": str(uuid.uuid4()), "generation": generation,
            "actions": [], "input_types": [],
        }, session_id=session_id, generation=generation)


def test_inventory_requires_current_identity_and_bounded_object():
    session_id = str(uuid.uuid4())
    generation = str(uuid.uuid4())
    snapshot = validate_inventory({
        "type": "console/inventory", "version": 1,
        "session_id": session_id, "generation": generation,
        "revision": 7, "data": {"mode": "atlas", "results": []},
    }, session_id=session_id, generation=generation)
    assert snapshot["revision"] == 7
    assert snapshot["data"]["mode"] == "atlas"
    with pytest.raises(ValueError):
        validate_inventory({
            "type": "console/inventory", "version": 1,
            "session_id": str(uuid.uuid4()), "generation": generation,
            "revision": 7, "data": {},
        }, session_id=session_id, generation=generation)
    with pytest.raises(ValueError):
        validate_inventory({
            "type": "console/inventory", "version": 1,
            "session_id": session_id, "generation": generation,
            "revision": -1, "data": {},
        }, session_id=session_id, generation=generation)
import json
from pathlib import Path


def test_shared_protocol_fixture_decodes():
    fixture = Path(__file__).parents[1] / "fixtures" / "command_console" / "protocol.json"
    message = validate_request(json.loads(fixture.read_text()))
    assert message["action"] == "inventory" and message["revision"] == 0


def test_voice_fixture_covers_every_locked_acceptance_phrase():
    fixture = Path(__file__).parents[1] / "fixtures" / "command_console" / "voice_cases.json"
    cases = json.loads(fixture.read_text())
    utterances = {case["utterance"] for case in cases}
    required = {
        "Show the memory graph", "Focus this node", "Show its sources",
        "Put this research on the other screen", "Bring everything back",
        "Make the sidecar text larger", "Move that card to row two column one",
        "Copy the second paragraph", "Copy this graph as an image", "Share this",
        "Paste my image", "Use these two images to explain the difference",
        "Cancel that upload", "Clear shared content and start a fresh conversation",
    }
    assert required <= utterances
    assert all(case["action"] in ALLOWED_ACTIONS for case in cases)
    assert all(case.get("follow_up_action") in ALLOWED_ACTIONS
               for case in cases if case.get("follow_up_action"))
    for case in cases:
        validate_request(req(action=case["action"], target=case.get("target"),
                             args=case.get("args", {})))
