"""Narrow host-issued file policy for one sandbox skill-authoring attempt.

The policy is inert unless a trusted host entry point constructs it from an
approved slug and passes it to the existing sandbox Runtime. It never edits
the global self-edit allowlist or grants registry/validator/policy access.
"""
from __future__ import annotations

import re

from sandbox.artifacts import source_path_allowed

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PACKAGE_ROOT = "skills"
_FIXTURE_ROOT = "tests/fixtures/skills_authoring"
_TEXT_SUFFIXES = frozenset({".md", ".txt", ".yaml", ".yml", ".json"})


class SkillAuthoringPolicy:
    """Allow only one named skill package and its public fixture directory.

    Construct this on the host after the user has approved a creator draft.
    This is deliberately separate from the normal self-edit allowlist: it
    grants no access to the registry, sibling skills, tests, sandbox code, or
    execution/policy files.
    """

    def __init__(self, approved_slug: str):
        if not isinstance(approved_slug, str) or not _SLUG.fullmatch(approved_slug):
            raise ValueError("invalid approved skill slug")
        if approved_slug == "skill-creator":
            raise ValueError("the creator cannot modify its own package")
        self.slug = approved_slug
        self.package_prefix = f"{_PACKAGE_ROOT}/{approved_slug}/"
        self.fixture_prefix = f"{_FIXTURE_ROOT}/{approved_slug}/"

    def is_allowed(self, path: str) -> bool:
        """Return whether one repository-relative content file is in scope."""
        if not isinstance(path, str) or not path or "\\" in path or not source_path_allowed(path):
            return False
        if path.startswith(self.package_prefix):
            relative = path[len(self.package_prefix):]
        elif path.startswith(self.fixture_prefix):
            relative = path[len(self.fixture_prefix):]
        else:
            return False
        parts = relative.split("/")
        if any(not part or part in {".", ".."} or part.startswith(".") for part in parts):
            return False
        return parts[-1].lower().endswith(tuple(sorted(_TEXT_SUFFIXES)))
