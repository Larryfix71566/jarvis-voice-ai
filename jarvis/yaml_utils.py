"""Strict YAML loading helpers for trusted Mortimer configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class DuplicateYAMLKeyError(yaml.YAMLError):
    """Raised when a YAML mapping has ambiguous or unhashable keys."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode,
                              deep: bool = False) -> dict[Any, Any]:
    explicit_keys: set[Any] = set()
    for key_node, _value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in explicit_keys
        except TypeError:
            raise DuplicateYAMLKeyError("unhashable YAML mapping key") from None
        if duplicate:
            raise DuplicateYAMLKeyError("duplicate YAML mapping key")
        explicit_keys.add(key)

    # Preserve normal YAML merge-key precedence: explicit keys override
    # inherited defaults, while duplicate keys written at the same mapping
    # level have already been rejected above.
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            mapping[key] = loader.construct_object(value_node, deep=deep)
        except TypeError:
            raise DuplicateYAMLKeyError("unhashable YAML mapping key") from None
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping,
)


def load_unique_yaml(text: str) -> Any:
    """Load safe YAML and reject duplicate explicit mapping keys at every depth."""
    return yaml.load(text, Loader=_UniqueKeyLoader)


def load_unique_yaml_file(path: Path) -> Any:
    """Read UTF-8 YAML from a file with duplicate-key rejection."""
    return load_unique_yaml(path.read_text(encoding="utf-8"))
