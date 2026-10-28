"""Pure, bounded validation for synthetic no-reference app-build drafts.

This module validates data only.  It does not approve or start a build, acquire
references, select a model, or integrate with any Mortimer runtime service.
"""

import hashlib
import json
import re


_MAX_BYTES = 65_536
_MAX_DEPTH = 8
_MAX_NODES = 4_096
_MAX_ERRORS = 32
_MAX_PROSE = 2_000

_OPAQUE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z", re.ASCII)
_REQUIREMENT_ID = re.compile(r"R[0-9]{2}\Z", re.ASCII)
_CASE_ID = re.compile(r"A[0-9]{2}\Z", re.ASCII)
_QUESTION_ID = re.compile(r"Q[0-9]{2}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)

_FIELDS = {
    "root": ("schema_version", "intent", "spec"),
    "intent": (
        "intent_id",
        "mode",
        "title",
        "audience",
        "outcome",
        "platform",
        "constraints",
    ),
    "spec": (
        "spec_id",
        "intent_sha256",
        "requirements",
        "acceptance_cases",
        "open_questions",
    ),
    "requirement": ("id", "kind", "priority", "statement", "acceptance_case_ids"),
    "case": ("id", "requirement_ids", "given", "when", "then"),
    "question": ("id", "question", "blocking"),
}

_CHILDREN = {
    "root": {"intent": ("object", "intent"), "spec": ("object", "spec")},
    "intent": {"constraints": ("array", None)},
    "spec": {
        "requirements": ("array", "requirement"),
        "acceptance_cases": ("array", "case"),
        "open_questions": ("array", "question"),
    },
    "requirement": {"acceptance_case_ids": ("array", None)},
    "case": {"requirement_ids": ("array", None)},
    "question": {},
}

_ALLOWED_TYPES = (dict, list, str, int, bool, type(None))


class _DuplicateKey(ValueError):
    pass


class _DepthLimit(ValueError):
    pass


class _State:
    def __init__(self):
        self.errors = []
        self.active = set()
        self.nodes = 0

    @property
    def stopped(self):
        return len(self.errors) > _MAX_ERRORS

    def add(self, code, location):
        if not self.stopped:
            self.errors.append({"code": code, "location": location})

    def tick(self):
        self.nodes += 1
        return self.nodes <= _MAX_NODES

    def finish(self):
        if len(self.errors) <= _MAX_ERRORS:
            return self.errors
        return self.errors[: _MAX_ERRORS - 1] + [
            {"code": "limit_exceeded", "location": "errors"}
        ]


def _result(status, errors, intent_sha256=None, spec_sha256=None, questions=None):
    return {
        "status": status,
        "errors": errors,
        "intent_sha256": intent_sha256,
        "spec_sha256": spec_sha256,
        "unresolved_question_ids": [] if questions is None else questions,
        "build_authorized": False,
    }


def _invalid(state):
    return _result("invalid", state.finish())


def _field_path(container, field):
    return f"{container}.{field}"


def _index_path(container, index):
    return f"{container}[{index}]"


def _canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _object_pairs(pairs):
    result = {}
    seen = set()
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey()
        seen.add(key)
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("non-finite JSON number")


def _lexical_depth(raw_json):
    depth = 0
    in_string = False
    escaped = False
    for char in raw_json:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{" or char == "[":
            depth += 1
            if depth > _MAX_DEPTH:
                raise _DepthLimit()
        elif char == "}" or char == "]":
            depth -= 1


def _preflight_text(value, location, state):
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        state.add("invalid_text", location)
        return
    if "\x00" in value:
        state.add("invalid_text", location)


def _preflight(value, location, depth, schema, state):
    """Bound known input without invoking subclass or arbitrary-object hooks."""
    if type(value) not in _ALLOWED_TYPES:
        state.add("invalid_type", location)
        return

    is_container = type(value) is dict or type(value) is list
    if is_container and id(value) in state.active:
        state.add("invalid_type", location)
        return
    if not state.tick():
        state.add("limit_exceeded", location)
        return
    if is_container and depth > _MAX_DEPTH:
        state.add("limit_exceeded", location)
        return
    if type(value) is str:
        _preflight_text(value, location, state)
        return
    if not is_container or state.stopped:
        return

    state.active.add(id(value))
    try:
        if type(value) is dict:
            object_kind = schema[1] if schema is not None and schema[0] == "object" else None
            fields = _FIELDS.get(object_kind)
            children = _CHILDREN.get(object_kind, {})
            for key, item in value.items():
                if not state.tick():
                    state.add("limit_exceeded", location)
                    return
                if type(key) is not str:
                    continue
                if fields is not None and key not in fields:
                    continue
                child_schema = children.get(key) if fields is not None else None
                _preflight(
                    item,
                    _field_path(location, key) if fields is not None else location,
                    depth + 1,
                    child_schema,
                    state,
                )
                if state.stopped:
                    return
        else:
            item_kind = schema[1] if schema is not None and schema[0] == "array" else None
            item_schema = ("object", item_kind) if item_kind is not None else None
            for index, item in enumerate(value):
                _preflight(item, _index_path(location, index), depth + 1, item_schema, state)
                if state.stopped:
                    return
    finally:
        state.active.remove(id(value))


def _object(value, location, kind, state):
    if type(value) is not dict:
        state.add("invalid_type", location)
        return None
    fields = _FIELDS[kind]
    present = {}
    unknown = False
    for key, item in value.items():
        if type(key) is not str or key not in fields:
            unknown = True
        else:
            present[key] = item
    if unknown:
        state.add("unknown_field", location)
    for field in fields:
        if field not in present:
            state.add("missing_field", _field_path(location, field))
    return present


def _text(value, location, state, maximum=_MAX_PROSE):
    if type(value) is not str:
        state.add("invalid_type", location)
        return None
    if not value.strip():
        state.add("invalid_text", location)
    if len(value) > maximum:
        state.add("limit_exceeded", location)
    return value


def _identifier(value, location, pattern, state):
    if type(value) is not str:
        state.add("invalid_type", location)
        return None
    if pattern.fullmatch(value) is None:
        state.add("invalid_id", location)
    return value


def _choice(value, location, choices, state):
    if type(value) is not str:
        state.add("invalid_type", location)
        return None
    if value not in choices:
        state.add("unsupported_contract", location)
    return value


def _id_list(value, location, pattern, maximum, state):
    if type(value) is not list:
        state.add("invalid_type", location)
        return None
    if len(value) > maximum:
        state.add("limit_exceeded", location)
    result = []
    seen = set()
    for index, item in enumerate(value):
        item_location = _index_path(location, index)
        _identifier(item, item_location, pattern, state)
        if type(item) is str:
            if item in seen:
                state.add("reference_mismatch", item_location)
            seen.add(item)
        result.append(item)
    return result


def _validate_intent(value, state):
    location = "$.intent"
    fields = _object(value, location, "intent", state)
    if fields is None:
        return None
    result = {}
    if "intent_id" in fields:
        result["intent_id"] = _identifier(
            fields["intent_id"], _field_path(location, "intent_id"), _OPAQUE_ID, state
        )
    if "mode" in fields:
        result["mode"] = _choice(fields["mode"], _field_path(location, "mode"), ("new_idea",), state)
    for name, maximum in (("title", 200), ("audience", _MAX_PROSE), ("outcome", _MAX_PROSE)):
        if name in fields:
            result[name] = _text(fields[name], _field_path(location, name), state, maximum)
    if "platform" in fields:
        result["platform"] = _choice(
            fields["platform"], _field_path(location, "platform"), ("web_app",), state
        )
    if "constraints" in fields:
        constraints = fields["constraints"]
        if type(constraints) is not list:
            state.add("invalid_type", _field_path(location, "constraints"))
        else:
            if len(constraints) > 16:
                state.add("limit_exceeded", _field_path(location, "constraints"))
            checked = []
            for index, item in enumerate(constraints):
                checked.append(
                    _text(item, _index_path(_field_path(location, "constraints"), index), state)
                )
            result["constraints"] = checked
    return {name: result[name] for name in _FIELDS["intent"] if name in result}


def _validate_requirement(value, index, state):
    location = _index_path("$.spec.requirements", index)
    fields = _object(value, location, "requirement", state)
    if fields is None:
        return None
    result = {}
    if "id" in fields:
        result["id"] = _identifier(fields["id"], _field_path(location, "id"), _REQUIREMENT_ID, state)
    if "kind" in fields:
        result["kind"] = _choice(fields["kind"], _field_path(location, "kind"), ("new_design",), state)
    if "priority" in fields:
        result["priority"] = _choice(
            fields["priority"], _field_path(location, "priority"), ("must", "optional"), state
        )
    if "statement" in fields:
        result["statement"] = _text(fields["statement"], _field_path(location, "statement"), state)
    if "acceptance_case_ids" in fields:
        result["acceptance_case_ids"] = _id_list(
            fields["acceptance_case_ids"],
            _field_path(location, "acceptance_case_ids"),
            _CASE_ID,
            64,
            state,
        )
    return {name: result[name] for name in _FIELDS["requirement"] if name in result}


def _validate_case(value, index, state):
    location = _index_path("$.spec.acceptance_cases", index)
    fields = _object(value, location, "case", state)
    if fields is None:
        return None
    result = {}
    if "id" in fields:
        result["id"] = _identifier(fields["id"], _field_path(location, "id"), _CASE_ID, state)
    if "requirement_ids" in fields:
        result["requirement_ids"] = _id_list(
            fields["requirement_ids"],
            _field_path(location, "requirement_ids"),
            _REQUIREMENT_ID,
            32,
            state,
        )
    for name in ("given", "when", "then"):
        if name in fields:
            result[name] = _text(fields[name], _field_path(location, name), state)
    return {name: result[name] for name in _FIELDS["case"] if name in result}


def _validate_question(value, index, state):
    location = _index_path("$.spec.open_questions", index)
    fields = _object(value, location, "question", state)
    if fields is None:
        return None
    result = {}
    if "id" in fields:
        result["id"] = _identifier(fields["id"], _field_path(location, "id"), _QUESTION_ID, state)
    if "question" in fields:
        result["question"] = _text(fields["question"], _field_path(location, "question"), state)
    if "blocking" in fields:
        blocking = fields["blocking"]
        if type(blocking) is not bool:
            state.add("invalid_type", _field_path(location, "blocking"))
        result["blocking"] = blocking
    return {name: result[name] for name in _FIELDS["question"] if name in result}


def _validate_spec(value, state):
    location = "$.spec"
    fields = _object(value, location, "spec", state)
    if fields is None:
        return None
    result = {}
    if "spec_id" in fields:
        result["spec_id"] = _identifier(fields["spec_id"], _field_path(location, "spec_id"), _OPAQUE_ID, state)
    if "intent_sha256" in fields:
        result["intent_sha256"] = _identifier(
            fields["intent_sha256"], _field_path(location, "intent_sha256"), _SHA256, state
        )
    validators = (
        ("requirements", 32, _validate_requirement),
        ("acceptance_cases", 64, _validate_case),
        ("open_questions", 16, _validate_question),
    )
    for name, maximum, validator in validators:
        if name not in fields:
            continue
        items = fields[name]
        item_location = _field_path(location, name)
        if type(items) is not list:
            state.add("invalid_type", item_location)
            continue
        if len(items) > maximum:
            state.add("limit_exceeded", item_location)
        checked = [validator(item, index, state) for index, item in enumerate(items)]
        result[name] = checked
    return {name: result[name] for name in _FIELDS["spec"] if name in result}


def _unique_ids(items, container, state):
    result = {}
    for index, item in enumerate(items):
        identifier = item["id"]
        if identifier in result:
            state.add("duplicate_id", _field_path(_index_path(container, index), "id"))
        else:
            result[identifier] = (index, item)
    return result


def _validate_links(spec, state):
    requirements = spec["requirements"]
    cases = spec["acceptance_cases"]
    questions = spec["open_questions"]
    requirement_map = _unique_ids(requirements, "$.spec.requirements", state)
    case_map = _unique_ids(cases, "$.spec.acceptance_cases", state)
    _unique_ids(questions, "$.spec.open_questions", state)
    if state.errors:
        return
    if not cases:
        state.add("missing_oracle", "$.spec.acceptance_cases")
    if not any(item["priority"] == "must" for item in requirements):
        state.add("missing_must_requirement", "$.spec.requirements")

    for req_index, requirement in enumerate(requirements):
        req_location = _index_path("$.spec.requirements", req_index)
        refs = requirement["acceptance_case_ids"]
        if requirement["priority"] == "must" and not refs:
            state.add("missing_oracle", _field_path(req_location, "acceptance_case_ids"))
        for ref_index, case_id in enumerate(refs):
            ref_location = _index_path(_field_path(req_location, "acceptance_case_ids"), ref_index)
            target = case_map.get(case_id)
            if target is None:
                state.add("reference_mismatch", ref_location)
            elif requirement["id"] not in target[1]["requirement_ids"]:
                state.add("reference_mismatch", ref_location)

    for case_index, case in enumerate(cases):
        case_location = _index_path("$.spec.acceptance_cases", case_index)
        refs = case["requirement_ids"]
        if not refs:
            state.add("reference_mismatch", _field_path(case_location, "requirement_ids"))
        for ref_index, requirement_id in enumerate(refs):
            ref_location = _index_path(_field_path(case_location, "requirement_ids"), ref_index)
            target = requirement_map.get(requirement_id)
            if target is None:
                state.add("reference_mismatch", ref_location)
            elif case["id"] not in target[1]["acceptance_case_ids"]:
                state.add("reference_mismatch", ref_location)


def parse_new_app_contract(raw_json: str):
    """Parse and validate a bounded raw JSON draft without external effects."""
    if type(raw_json) is not str:
        return _result("invalid", [{"code": "invalid_type", "location": "$"}])
    try:
        raw_bytes = raw_json.encode("utf-8")
    except UnicodeEncodeError:
        return _result("invalid", [{"code": "invalid_json", "location": "$"}])
    if len(raw_bytes) > _MAX_BYTES:
        return _result("invalid", [{"code": "limit_exceeded", "location": "$"}])
    try:
        _lexical_depth(raw_json)
    except _DepthLimit:
        return _result("invalid", [{"code": "limit_exceeded", "location": "$"}])
    try:
        payload = json.loads(
            raw_json,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey:
        return _result("invalid", [{"code": "duplicate_key", "location": "$"}])
    except (json.JSONDecodeError, UnicodeError, RecursionError, ValueError):
        return _result("invalid", [{"code": "invalid_json", "location": "$"}])
    return validate_new_app_contract(payload)


def validate_new_app_contract(payload: dict):
    """Validate a mapping draft and its content digests without mutating it."""
    state = _State()
    _preflight(payload, "$", 1, ("object", "root"), state)
    if state.errors:
        return _invalid(state)

    fields = _object(payload, "$", "root", state)
    if fields is None:
        return _invalid(state)
    result = {}
    if "schema_version" in fields:
        version = fields["schema_version"]
        if type(version) is not int:
            state.add("invalid_type", "$.schema_version")
        elif version != 1:
            state.add("unsupported_contract", "$.schema_version")
        result["schema_version"] = version
    if "intent" in fields:
        result["intent"] = _validate_intent(fields["intent"], state)
    if "spec" in fields:
        result["spec"] = _validate_spec(fields["spec"], state)
    if state.errors:
        return _invalid(state)

    normalized = {name: result[name] for name in _FIELDS["root"]}
    intent_sha256 = _digest(normalized["intent"])
    if normalized["spec"]["intent_sha256"] != intent_sha256:
        state.add("digest_mismatch", "$.spec.intent_sha256")
    _validate_links(normalized["spec"], state)
    if state.errors:
        return _invalid(state)
    if len(_canonical(normalized)) > _MAX_BYTES:
        state.add("limit_exceeded", "$")
        return _invalid(state)

    spec_sha256 = _digest(normalized["spec"])
    question_ids = [item["id"] for item in normalized["spec"]["open_questions"]]
    blocking = any(item["blocking"] for item in normalized["spec"]["open_questions"])
    return _result(
        "needs_input" if blocking else "valid_draft",
        [],
        intent_sha256,
        spec_sha256,
        question_ids,
    )


__all__ = ["parse_new_app_contract", "validate_new_app_contract"]
