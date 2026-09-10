"""Frontmatter schema v1: field order, types, strict (write) and tolerant (index) validation (§4)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

FIELD_ORDER = [
    "id",
    "type",
    "created",
    "updated",
    "last_accessed",
    "tags",
    "confidence",
    "source_sessions",
    "schema",
]

TYPES = {"area", "session-digest", "capture", "decision"}
CONFIDENCE = {"high", "medium", "low"}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}

TYPE_TO_FOLDER = {
    "area": "areas",
    "decision": "areas",
    "session-digest": "sessions",
    "capture": "inbox",
}


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_valid_slug(s: str, max_len: int = 64) -> bool:
    return bool(SLUG_RE.match(s)) and len(s) <= max_len


def validate_strict(fm: dict[str, Any]) -> None:
    """Raise ValidationError on any deviation. No coercion. (§4 write path)"""
    unknown = set(fm.keys()) - set(FIELD_ORDER)
    if unknown:
        raise ValidationError(f"unknown frontmatter fields: {sorted(unknown)}")
    missing = set(FIELD_ORDER) - set(fm.keys())
    if missing:
        raise ValidationError(f"missing frontmatter fields: {sorted(missing)}")

    if not isinstance(fm["id"], str) or not fm["id"]:
        raise ValidationError("id must be a non-empty string")

    if fm["type"] not in TYPES:
        raise ValidationError(f"type must be one of {sorted(TYPES)}, got {fm['type']!r}")

    for key in ("created", "updated", "last_accessed"):
        v = fm[key]
        if not isinstance(v, str) or not ISO_RE.match(v):
            raise ValidationError(f"{key} must be ISO 8601 UTC 'YYYY-MM-DDTHH:MM:SSZ', got {v!r}")

    if not isinstance(fm["tags"], list) or not all(isinstance(t, str) for t in fm["tags"]):
        raise ValidationError("tags must be a list of strings")
    for t in fm["tags"]:
        if not is_valid_slug(t):
            raise ValidationError(f"invalid tag slug: {t!r}")

    if fm["confidence"] not in CONFIDENCE:
        raise ValidationError(f"confidence must be one of {sorted(CONFIDENCE)}, got {fm['confidence']!r}")

    if not isinstance(fm["source_sessions"], list) or not all(
        isinstance(s, str) for s in fm["source_sessions"]
    ):
        raise ValidationError("source_sessions must be a list of strings")

    if fm.get("schema") != 1:
        raise ValidationError(f"schema must be 1, got {fm.get('schema')!r}")


def validate_tolerant(fm: dict[str, Any]) -> tuple[bool, str | None]:
    """Never raises. Returns (valid, reason). Used by the indexer (§4 read/index path)."""
    try:
        validate_strict(fm)
        return True, None
    except ValidationError as e:
        return False, e.message
    except Exception as e:  # noqa: BLE001 - indexer must never crash on bad input
        return False, f"unexpected: {e}"
