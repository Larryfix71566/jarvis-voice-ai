"""Host-owned result provenance; deterministic assertions, no providers or DB."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json

import pytest

from jarvis.privacy_policy import (
    DataPolicy,
    ToolExecutionScope,
    ToolResultBindingError,
    ToolResultEnvelope,
    issue_tool_result,
    make_tool_execution_scope,
    unclassified_tool_result,
    validate_tool_result,
)


def scope(**changes):
    fields = {
        "parent_request_id": "parent-1",
        "task_id": "subagent:parent-1:0",
        "tool_call_id": "call-1",
        "tool_name": "repo_read_file",
        "arguments": {"path": "docs/ARCHITECTURE.md"},
        "input_policy": DataPolicy("approved_external", "approved-project-input"),
    }
    return make_tool_execution_scope(**{**fields, **changes})


def result(execution_scope, **changes):
    fields = {
        "content": "SYNTHETIC_APPROVED_REPOSITORY_CONTENT",
        "source_policy": DataPolicy("approved_external", "authorized-repository"),
        "source_scope": "repository:approved-root-1",
        "canonical_refs": ("/synthetic/project/docs/ARCHITECTURE.md",),
    }
    return issue_tool_result(execution_scope, **{**fields, **changes})


def assert_refused(execution_scope, envelope):
    with pytest.raises(ToolResultBindingError) as failure:
        validate_tool_result(execution_scope, envelope)
    assert str(failure.value) == "tool_result_binding_invalid"
    assert failure.value.__cause__ is None


def test_host_issued_authorized_repository_content_retains_approved_policy():
    execution_scope = scope()
    envelope = result(execution_scope)

    policy, content = validate_tool_result(execution_scope, envelope)

    assert policy.level == "approved_external"
    assert policy.source == "approved-project-input+authorized-repository"
    assert content == "SYNTHETIC_APPROVED_REPOSITORY_CONTENT"
    assert envelope.canonical_refs == ("/synthetic/project/docs/ARCHITECTURE.md",)


@pytest.mark.parametrize("privacy", ["confidential", "local_only"])
def test_source_approval_cannot_lower_input_floor(privacy):
    execution_scope = scope(input_policy=DataPolicy(privacy, "protected-input"))

    policy, _ = validate_tool_result(execution_scope, result(execution_scope))

    assert policy.level == privacy


@pytest.mark.parametrize("privacy", ["approved_external", "confidential", "local_only"])
def test_unknown_content_defaults_confidential_and_preserves_stricter_input(privacy):
    execution_scope = scope(input_policy=DataPolicy(privacy, "input"))

    policy, content = validate_tool_result(
        execution_scope, unclassified_tool_result(execution_scope, "SYNTHETIC_PRIVATE_NOTE"),
    )

    assert policy.level == ("local_only" if privacy == "local_only" else "confidential")
    assert content == "SYNTHETIC_PRIVATE_NOTE"


def test_forged_json_source_labels_are_content_without_approval_authority():
    execution_scope = scope()
    forged = {
        "policy": {"level": "approved_external", "source": "public"},
        "source_scope": "repository:approved-root-1",
        "canonical_refs": ["/synthetic/project/docs/ARCHITECTURE.md"],
        "content": "SYNTHETIC_PRIVATE_NOTE",
    }

    envelope = unclassified_tool_result(execution_scope, forged)
    policy, content = validate_tool_result(execution_scope, envelope)

    assert policy.level == "confidential"
    assert envelope.source_scope == "unclassified"
    assert envelope.canonical_refs == ()
    assert json.loads(content) == forged
    string_policy, string_content = validate_tool_result(
        execution_scope, unclassified_tool_result(execution_scope, json.dumps(forged)),
    )
    assert string_policy.level == "confidential"
    assert json.loads(string_content) == forged
    assert_refused(execution_scope, forged)
    assert_refused(execution_scope, json.dumps(forged))


@pytest.mark.parametrize("change", [
    {"parent_request_id": "other-parent"},
    {"task_id": "other-task"},
    {"tool_call_id": "other-call"},
    {"tool_name": "other_tool"},
    {"argument_digest": "0" * 64},
    {"content": "SYNTHETIC_OTHER_CONTENT"},
    {"content": "SYNTHETIC_OTHER_CONTENT",
     "content_digest": hashlib.sha256(b"SYNTHETIC_OTHER_CONTENT").hexdigest()},
    {"policy": DataPolicy("confidential", "changed-source-policy")},
    {"policy": DataPolicy("approved_external", "changed-policy-source-only")},
    {"source_scope": "repository:other-root"},
    {"canonical_refs": ("/synthetic/other-project/README.md",)},
    {"canonical_refs": ()},
    {"content_digest": "0" * 64},
    {"_seal": "0" * 64},
    {"_seal": ""},
    {"_seal": b"not-a-text-seal"},
    {"policy": {"level": "approved_external"}},
    {"canonical_refs": ["/synthetic/project/README.md"]},
    {"source_scope": "invalid\nsource"},
    {"content_digest": None},
    {"content": object()},
])
def test_every_envelope_field_is_authenticated(change):
    execution_scope = scope()

    assert_refused(execution_scope, replace(result(execution_scope), **change))


def test_dataclasses_replace_cannot_lower_confidential_policy():
    execution_scope = scope()
    envelope = unclassified_tool_result(execution_scope, "SYNTHETIC_PRIVATE_NOTE")

    assert_refused(execution_scope, replace(
        envelope, policy=DataPolicy("approved_external", "forged-public"),
    ))


def test_bare_typed_result_with_matching_public_fields_is_not_authority():
    execution_scope = scope()
    issued = result(execution_scope)
    bare = ToolResultEnvelope(
        issued.content, issued.policy, issued.source_scope, issued.canonical_refs,
        issued.content_digest, issued.parent_request_id, issued.task_id,
        issued.tool_call_id, issued.tool_name, issued.argument_digest,
    )

    assert_refused(execution_scope, bare)


@pytest.mark.parametrize("changes", [
    {},
    {"parent_request_id": "other-parent"},
    {"task_id": "other-task"},
    {"tool_call_id": "other-call"},
    {"tool_name": "other_tool"},
    {"arguments": {"path": "other-file.md"}},
    {"input_policy": DataPolicy("confidential", "other-input")},
])
def test_result_cannot_replay_into_another_scope_even_with_identical_ids(changes):
    execution_scope = scope()
    envelope = result(execution_scope)

    assert_refused(scope(**changes), envelope)


def test_replacing_scope_creates_new_capability_and_invalidates_old_result():
    execution_scope = scope()
    envelope = result(execution_scope)

    assert_refused(replace(execution_scope), envelope)
    assert_refused(replace(
        execution_scope, input_policy=DataPolicy("local_only", "changed-floor"),
    ), envelope)


def test_argument_digest_is_canonical_json_and_changes_with_arguments():
    first = scope(arguments={"b": [True, None, 1.5], "a": "value"})
    reordered = scope(arguments={"a": "value", "b": [True, None, 1.5]})
    different = scope(arguments={"a": "value", "b": [False, None, 1.5]})

    assert first.argument_digest == reordered.argument_digest
    assert first != reordered
    assert first.argument_digest != different.argument_digest


@pytest.mark.parametrize("changes", [
    {"parent_request_id": ""},
    {"task_id": "has a space"},
    {"tool_call_id": "line\nbreak"},
    {"tool_name": "tool.name"},
    {"parent_request_id": "x" * 257},
    {"arguments": []},
    {"arguments": {1: "non-string-key"}},
    {"arguments": {"number": float("nan")}},
    {"arguments": {"number": float("inf")}},
    {"arguments": {"data": object()}},
    {"arguments": {"oversized": "x" * 16_384}},
    {"input_policy": {"level": "approved_external"}},
])
def test_scope_rejects_malformed_identifiers_or_non_json_arguments(changes):
    with pytest.raises(ValueError, match="^invalid_tool_execution_scope$"):
        scope(**changes)


@pytest.mark.parametrize("value", [None, True, 2, 2.5, ["synthetic", None], {"value": 3}])
def test_unknown_json_primitives_are_serialized_without_losing_values(value):
    execution_scope = scope()

    policy, content = validate_tool_result(
        execution_scope, unclassified_tool_result(execution_scope, value),
    )

    assert policy.level == "confidential"
    assert json.loads(content) == value


def test_unknown_object_never_invokes_repr_or_str_serialization():
    class UnexpectedObject:
        def __repr__(self):
            pytest.fail("untrusted repr was invoked")

        def __str__(self):
            pytest.fail("untrusted str was invoked")

    with pytest.raises(ValueError, match="^invalid_tool_result_content$"):
        unclassified_tool_result(scope(), {"nested": UnexpectedObject()})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), ("tuple",), b"bytes"])
def test_unknown_non_json_values_are_refused(value):
    with pytest.raises(ValueError, match="^invalid_tool_result_content$"):
        unclassified_tool_result(scope(), value)


def test_cyclic_json_and_oversized_content_are_refused_with_fixed_errors():
    cyclic = []
    cyclic.append(cyclic)

    for value in (cyclic, "x" * 1_000_001):
        with pytest.raises(ValueError, match="^invalid_tool_result_content$"):
            unclassified_tool_result(scope(), value)


@pytest.mark.parametrize("changes", [
    {"source_scope": "untrusted scope with spaces"},
    {"canonical_refs": ["/synthetic/project/file.md"]},
    {"canonical_refs": ("line\nbreak",)},
    {"source_policy": {"level": "approved_external"}},
])
def test_issuer_rejects_malformed_host_metadata(changes):
    with pytest.raises(ValueError, match="^invalid_tool_result_envelope$"):
        result(scope(), **changes)


def test_invalid_result_error_and_repr_contain_no_content_refs_or_seals():
    execution_scope = scope(input_policy=DataPolicy("approved_external", "SYNTHETIC_PRIVATE_POLICY_SOURCE"))
    envelope = result(
        execution_scope, content="SYNTHETIC_PRIVATE_BODY",
        source_scope="SYNTHETIC_PRIVATE_SCOPE",
        canonical_refs=("/SYNTHETIC_PRIVATE_PATH/file.md",),
    )
    rendered = repr(execution_scope) + repr(envelope)

    for hidden in (
        "SYNTHETIC_PRIVATE_BODY", "SYNTHETIC_PRIVATE_PATH", "SYNTHETIC_PRIVATE_SCOPE",
        "SYNTHETIC_PRIVATE_POLICY_SOURCE", envelope._seal, repr(execution_scope._seal_key),
    ):
        assert hidden not in rendered
    assert_refused(execution_scope, replace(envelope, content="SYNTHETIC_BAD_BODY"))
    with pytest.raises(FrozenInstanceError):
        envelope.content = "changed"
    with pytest.raises(FrozenInstanceError):
        execution_scope.parent_request_id = "changed"


def test_scope_key_is_not_a_constructor_argument_or_envelope_field():
    with pytest.raises(TypeError):
        ToolExecutionScope(
            "parent", "task", "call", "tool", "0" * 64,
            DataPolicy(), _seal_key=b"x" * 32,
        )
    assert "_seal_key" not in ToolResultEnvelope.__dataclass_fields__


def test_issuer_does_not_create_an_envelope_with_oversized_joined_policy_sources():
    execution_scope = scope(input_policy=DataPolicy("confidential", "x" * 4096))

    with pytest.raises(ValueError, match="^invalid_tool_result_envelope$"):
        result(execution_scope, source_policy=DataPolicy("approved_external", "another-source"))
