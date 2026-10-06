"""Local data-policy checks performed before model/tool transmission."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import hashlib
import hmac
import json
import math
import re
import secrets
from typing import Any

from jarvis.model_routing import AccessRoute, ModelRouteError


class PrivacyLevel(IntEnum):
    APPROVED_EXTERNAL = 1
    CONFIDENTIAL = 2
    LOCAL_ONLY = 3


_NAMES = {
    "approved_external": PrivacyLevel.APPROVED_EXTERNAL,
    "confidential": PrivacyLevel.CONFIDENTIAL,
    "local_only": PrivacyLevel.LOCAL_ONLY,
}


@dataclass(frozen=True)
class DataPolicy:
    level: str = "confidential"
    source: str = "unlabeled"

    def __post_init__(self) -> None:
        if self.level not in _NAMES:
            raise ValueError(f"unknown privacy level {self.level!r}")


def strictest(*policies: DataPolicy) -> DataPolicy:
    if not policies:
        return DataPolicy()
    selected = max(policies, key=lambda item: _NAMES[item.level])
    return DataPolicy(selected.level, "+".join(item.source for item in policies))


def assert_route_allowed(route: AccessRoute, policy: DataPolicy) -> None:
    """Raise before transmission when a route is less private than required."""
    required = _NAMES[policy.level]
    offered = _NAMES.get(route.privacy)
    if offered is None or offered < required:
        raise ModelRouteError(
            f"route {route.name!r} provides {route.privacy!r}, "
            f"but {policy.source} requires {policy.level!r}"
        )


def inherit_result_policy(input_policy: DataPolicy, *, source: str = "result") -> DataPolicy:
    """Model output/tool result retains the strictest input restriction."""
    return DataPolicy(input_policy.level, source)


_EXECUTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_TOOL_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_RESULT_CHARACTERS = 1_000_000
# Preserve the installed editor's 256 KiB ceiling. Canonical JSON can expand
# each UTF-8 byte to six ASCII escape characters; diffs can contain both files.
_EDITOR_BYTES = 256 * 1024
_LARGE_ARGUMENT_TOOLS = frozenset({'edit_propose', 'selfedit_write'})
_LARGE_RESULT_TOOLS = _LARGE_ARGUMENT_TOOLS | {'file_read', 'selfedit_read'}


def tool_argument_limit(name: str) -> int:
    """Transport bound only; registered schemas and workspace caps still apply."""
    # The editor also accepts an 8,000-character rationale. Non-BMP JSON
    # escapes use twelve ASCII bytes per character; leave room for paths and
    # the bounded creator visual intent without changing their own limits.
    return 6 * _EDITOR_BYTES + 128 * 1024 if type(name) is str and name in _LARGE_ARGUMENT_TOOLS else 16_384


def tool_result_limit(name: str | None = None) -> int:
    return 12 * _EDITOR_BYTES + 128 * 1024 if type(name) is str and name in _LARGE_RESULT_TOOLS else _MAX_RESULT_CHARACTERS


class ToolResultBindingError(ValueError):
    """An untrusted result did not match its host-owned execution scope."""

    def __init__(self) -> None:
        super().__init__("tool_result_binding_invalid")


def _bounded_text(value: object, maximum: int, *, empty: bool = False) -> bool:
    if type(value) is not str or len(value) > maximum or (not empty and not value):
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


def _valid_policy(value: object) -> bool:
    return (
        type(value) is DataPolicy
        and type(value.level) is str
        and value.level in _NAMES
        and _bounded_text(value.source, 4096)
    )


def _json_value(value: object, depth: int = 0) -> bool:
    """Accept JSON values without invoking a caller's repr/serialization hook."""
    if depth > 64:
        return False
    if value is None or type(value) in {bool, int}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError:
            return False
        return True
    if type(value) is list:
        return all(_json_value(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _json_value(key, depth + 1)
            and _json_value(item, depth + 1)
            for key, item in value.items()
        )
    return False


def _json_text(value: object) -> str:
    if not _json_value(value):
        raise ValueError("invalid_tool_result_content")
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError("invalid_tool_result_content") from None


def bounded_tool_arguments(name: str, arguments: dict[str, Any]) -> str:
    """One canonical byte quota for scope, history, output and native IPC."""
    if type(arguments) is not dict:
        raise ValueError('invalid_tool_arguments')
    text = _json_text(arguments)
    if len(text.encode('utf-8')) > tool_argument_limit(name):
        raise ValueError('invalid_tool_arguments')
    return text


@dataclass(frozen=True)
class ToolExecutionScope:
    """Local call identity and input floor; the random key never leaves the host.

    A scope is a per-invocation capability. Reconstructing even the same public
    fields produces a different key, so a result cannot be replayed into it.
    """

    parent_request_id: str
    task_id: str
    tool_call_id: str
    tool_name: str
    argument_digest: str
    input_policy: DataPolicy = field(repr=False)
    _seal_key: bytes = field(default_factory=lambda: secrets.token_bytes(32),
                             init=False, repr=False)

    def __post_init__(self) -> None:
        if not _valid_execution_scope(self):
            raise ValueError("invalid_tool_execution_scope")


def _valid_execution_scope(scope: object) -> bool:
    return (
        type(scope) is ToolExecutionScope
        and all(type(value) is str and _EXECUTION_ID.fullmatch(value)
                for value in (scope.parent_request_id, scope.task_id,
                              scope.tool_call_id))
        and type(scope.tool_name) is str and bool(_TOOL_NAME.fullmatch(scope.tool_name))
        and type(scope.argument_digest) is str and bool(_DIGEST.fullmatch(scope.argument_digest))
        and _valid_policy(scope.input_policy)
        and type(scope._seal_key) is bytes and len(scope._seal_key) == 32
    )


def make_tool_execution_scope(
    parent_request_id: str, task_id: str, tool_call_id: str, tool_name: str,
    arguments: dict[str, Any], input_policy: DataPolicy,
) -> ToolExecutionScope:
    """Create a host-owned scope from exact, canonical JSON arguments."""
    if type(arguments) is not dict:
        raise ValueError("invalid_tool_execution_scope")
    try:
        argument_text = bounded_tool_arguments(tool_name, arguments)
    except ValueError:
        raise ValueError("invalid_tool_execution_scope") from None
    return ToolExecutionScope(
        parent_request_id, task_id, tool_call_id, tool_name,
        hashlib.sha256(argument_text.encode("utf-8")).hexdigest(), input_policy,
    )


@dataclass(frozen=True)
class ToolResultEnvelope:
    """Host-issued provenance kept outside model/provider dictionaries.

    Constructing this dataclass is not authorization. Validation requires the
    authenticating seal from the exact live ToolExecutionScope.
    """

    content: str = field(repr=False)
    policy: DataPolicy = field(repr=False)
    source_scope: str = field(repr=False)
    canonical_refs: tuple[str, ...] = field(repr=False)
    content_digest: str
    parent_request_id: str
    task_id: str
    tool_call_id: str
    tool_name: str
    argument_digest: str
    _seal: str = field(default="", repr=False)


def _valid_source_scope(source_scope: object, canonical_refs: object) -> bool:
    return (
        type(source_scope) is str and bool(_EXECUTION_ID.fullmatch(source_scope))
        and type(canonical_refs) is tuple and len(canonical_refs) <= 256
        and all(_bounded_text(reference, 4096) for reference in canonical_refs)
    )


def _content_digest(content: object, tool_name: str | None = None) -> str:
    if type(content) is not str or len(content) > tool_result_limit(tool_name):
        raise ValueError("invalid_tool_result_content")
    try:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    except UnicodeError:
        raise ValueError("invalid_tool_result_content") from None


def _tool_result_seal(scope: ToolExecutionScope, envelope: ToolResultEnvelope) -> str:
    payload = {
        "version": 1,
        "parent_request_id": envelope.parent_request_id,
        "task_id": envelope.task_id,
        "tool_call_id": envelope.tool_call_id,
        "tool_name": envelope.tool_name,
        "argument_digest": envelope.argument_digest,
        "input_policy": {"level": scope.input_policy.level, "source": scope.input_policy.source},
        "policy": {"level": envelope.policy.level, "source": envelope.policy.source},
        "source_scope": envelope.source_scope,
        "canonical_refs": list(envelope.canonical_refs),
        "content_digest": envelope.content_digest,
    }
    return hmac.new(scope._seal_key, _json_text(payload).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def issue_tool_result(
    scope: ToolExecutionScope, content: str, source_policy: DataPolicy,
    source_scope: str, canonical_refs: tuple[str, ...] = (),
) -> ToolResultEnvelope:
    """Seal trusted local classification, retaining the input privacy floor.

    Only installed host classifiers may issue an approved source policy. JSON
    returned by a provider/tool is content, never classification authority.
    """
    if (not _valid_execution_scope(scope) or not _valid_policy(source_policy)
            or not _valid_source_scope(source_scope, canonical_refs)):
        raise ValueError("invalid_tool_result_envelope")
    effective_policy = strictest(scope.input_policy, source_policy)
    if not _valid_policy(effective_policy):
        raise ValueError("invalid_tool_result_envelope")
    envelope = ToolResultEnvelope(
        content, effective_policy, source_scope,
        canonical_refs, _content_digest(content, scope.tool_name), scope.parent_request_id,
        scope.task_id, scope.tool_call_id, scope.tool_name, scope.argument_digest,
    )
    # Reconstruct once with the seal; no mutable metadata is stored in either
    # frozen object and no key appears in the result.
    return ToolResultEnvelope(
        envelope.content, envelope.policy, envelope.source_scope,
        envelope.canonical_refs, envelope.content_digest,
        envelope.parent_request_id, envelope.task_id, envelope.tool_call_id,
        envelope.tool_name, envelope.argument_digest, _tool_result_seal(scope, envelope),
    )


def validate_tool_result(
    scope: ToolExecutionScope, envelope: ToolResultEnvelope,
) -> tuple[DataPolicy, str]:
    """Return effective policy/content, or one fixed payload-free binding error."""
    try:
        if (not _valid_execution_scope(scope) or type(envelope) is not ToolResultEnvelope
                or not _valid_policy(envelope.policy)
                or not _valid_source_scope(envelope.source_scope, envelope.canonical_refs)
                or (envelope.parent_request_id, envelope.task_id, envelope.tool_call_id,
                    envelope.tool_name, envelope.argument_digest)
                != (scope.parent_request_id, scope.task_id, scope.tool_call_id,
                    scope.tool_name, scope.argument_digest)
                or type(envelope.content_digest) is not str
                or not _DIGEST.fullmatch(envelope.content_digest)
                or _content_digest(envelope.content, scope.tool_name) != envelope.content_digest
                or type(envelope._seal) is not str or not _DIGEST.fullmatch(envelope._seal)
                or not hmac.compare_digest(envelope._seal, _tool_result_seal(scope, envelope))
                or strictest(scope.input_policy, envelope.policy).level != envelope.policy.level):
            raise ToolResultBindingError()
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        raise ToolResultBindingError() from None
    return envelope.policy, envelope.content


def unclassified_tool_result(scope: ToolExecutionScope, value: object) -> ToolResultEnvelope:
    """Unknown newly acquired content defaults confidential without repr hooks."""
    content = value if type(value) is str else _json_text(value)
    return issue_tool_result(
        scope, content, DataPolicy("confidential", "unclassified-tool-result"),
        "unclassified", (),
    )
