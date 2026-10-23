"""Pure, bounded validation for Mortimer's instruction-only SKILL.md subset.

Package text is untrusted data. Reasons are fixed codes, never source excerpts.
This module grants no tools, execution, activation or host-specific semantics.
"""
from __future__ import annotations

import re

import yaml

MAX_SKILL_BYTES = 128 * 1024
MAX_FRONTMATTER_BYTES = 16 * 1024
MAX_METADATA_STRING_CHARS = 1024
MAX_YAML_EVENTS = 128
MAX_YAML_DEPTH = 4
MAX_ROOT_ENTRIES = 256
NAME_MAX_CHARS = 64
DESCRIPTION_MAX_CHARS = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_WORDS = ("anthropic", "claude")

REASONS = frozenset({
    "skill_unreadable", "skill_file_type_unsupported", "skill_file_too_large",
    "skill_encoding_invalid", "frontmatter_missing", "frontmatter_too_large",
    "frontmatter_invalid_yaml", "frontmatter_complexity_limit",
    "frontmatter_yaml_features_unsupported", "frontmatter_duplicate_key",
    "frontmatter_not_mapping", "frontmatter_keys_not_strings",
    "unsupported_frontmatter_fields", "name_required_string", "name_too_long",
    "name_invalid_slug", "name_reserved", "description_required_string",
    "description_too_long", "metadata_not_mapping", "unsupported_metadata_fields",
    "metadata_string_required", "metadata_string_too_long", "metadata_integer_required",
    "unsupported_scripts_entry", "package_entry_limit", "body_required_string",
})


class _InvalidYaml(ValueError):
    pass


class _StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag != "tag:yaml.org,2002:str":
                raise _InvalidYaml("frontmatter_keys_not_strings")
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise _InvalidYaml("frontmatter_duplicate_key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_frontmatter(front: str) -> tuple[dict | None, list[str]]:
    """Reject YAML expansion/features before constructing bounded values."""
    if len(front.encode("utf-8")) > MAX_FRONTMATTER_BYTES:
        return None, ["frontmatter_too_large"]
    try:
        depth = 0
        for count, event in enumerate(yaml.parse(front), 1):
            if count > MAX_YAML_EVENTS:
                return None, ["frontmatter_complexity_limit"]
            if (isinstance(event, yaml.events.AliasEvent)
                    or getattr(event, "anchor", None) is not None
                    or getattr(event, "tag", None) is not None):
                return None, ["frontmatter_yaml_features_unsupported"]
            if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
                depth += 1
                if depth > MAX_YAML_DEPTH:
                    return None, ["frontmatter_complexity_limit"]
            elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                depth -= 1
        data = yaml.load(front, Loader=_StrictLoader)
    except _InvalidYaml as exc:
        return None, [str(exc)]  # constructed only from the fixed literals above
    except (yaml.YAMLError, ValueError, RecursionError, OverflowError):
        return None, ["frontmatter_invalid_yaml"]
    problems = validate_frontmatter(data)
    return (None, problems) if problems else (data, [])


def validate_frontmatter(data: object) -> list[str]:
    """Closed P0 field/type matrix; no scalar coercion or unknown-key discard."""
    if not isinstance(data, dict):
        return ["frontmatter_not_mapping"]
    problems = []
    if any(not isinstance(key, str) for key in data):
        problems.append("frontmatter_keys_not_strings")
    if set(data) - {"name", "description", "metadata"}:
        problems.append("unsupported_frontmatter_fields")
    name, description = data.get("name"), data.get("description")
    if not isinstance(name, str) or not name.strip():
        problems.append("name_required_string")
    else:
        name = name.strip()
        if len(name) > NAME_MAX_CHARS:
            problems.append("name_too_long")
        if not NAME_RE.fullmatch(name):
            problems.append("name_invalid_slug")
        if any(word in name for word in RESERVED_WORDS):
            problems.append("name_reserved")
    if not isinstance(description, str) or not description.strip():
        problems.append("description_required_string")
    elif len(description.strip()) > DESCRIPTION_MAX_CHARS:
        problems.append("description_too_long")
    if "metadata" in data:
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            problems.append("metadata_not_mapping")
        else:
            strings = {"agent", "source", "concept_from"}
            integers = {"promoted_successes", "promoted_failures"}
            if set(metadata) - strings - integers:
                problems.append("unsupported_metadata_fields")
            for key in strings & metadata.keys():
                value = metadata[key]
                if not isinstance(value, str):
                    problems.append("metadata_string_required")
                elif len(value) > MAX_METADATA_STRING_CHARS:
                    problems.append("metadata_string_too_long")
            for key in integers & metadata.keys():
                if type(metadata[key]) is not int:
                    problems.append("metadata_integer_required")
    return list(dict.fromkeys(problems))


def compatibility_reason(problems: list[str]) -> str:
    """Only fixed refusal codes cross into catalog/readiness diagnostics."""
    return next((reason for reason in problems if reason in REASONS), "invalid_skill_instructions")
