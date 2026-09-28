"""Sandbox adapter for one approved Agent Skill package revision.

This adapter reuses the installed sandbox Runtime/Session/publisher. It does
not write or activate the live library and is not an admin route by itself; a
trusted host action must decide when to construct it and which slug to bind.
"""
from __future__ import annotations

import json
import re

from jarvis.selfedit.skill_policy import SkillAuthoringPolicy
from jarvis.skill_authoring_validation import validate_skill_candidate
from sandbox.artifacts import SandboxError
from sandbox.durable import atomic_json
from sandbox.workspace import SandboxWorkspace

_REQUIRED_OFFLINE_CHECKS = frozenset({
    "package_file_count",
    "package_size",
    "text_file_size",
    "fixture_file_count",
    "fixture_text_file_size",
    "fixture_size",
    "required_files",
    "non_executable_files",
    "package_schema",
    "complete_instruction_body",
    "declared_references",
    "license_provenance",
    "matcher_fixtures",
    "dependency_profile",
    "runtime_registry_unchanged",
    "public_fixture_text",
})


class SkillAuthoringService(SandboxWorkspace):
    """One slug-bound sandbox workspace using the existing Mortimer profile."""

    def __init__(self, approved_slug: str, *, repository, token, base_branch,
                 runtime_factory=None, expected_job_id: str | None = None):
        policy = SkillAuthoringPolicy(approved_slug)
        self.skill_slug = policy.slug
        self.policy = policy
        self.expected_job_id = expected_job_id
        super().__init__(
            repository=repository,
            token=token,
            kind=f"skill-authoring-{policy.slug}",
            profile="mortimer",
            base_branch=base_branch,
            allowed=policy.is_allowed,
            runtime_factory=runtime_factory,
        )

    def _session(self):
        session = super()._session()
        if (self.expected_job_id is not None
                and session._read().get("run_id") != self.expected_job_id):
            raise SandboxError("creator sandbox job changed")
        return session

    def _submission(self, state):
        title, body = super()._submission(state)
        session = self._session()
        receipt_path = session.directory / "skill-authoring-validation.json"
        try:
            receipt = json.loads(receipt_path.read_bytes())
        except (OSError, ValueError):
            receipt = {}
        title = f"skill: {self.skill_slug} — {state['goal'].splitlines()[0]}"[:120]
        body += (
            f"\n\nSkill package: `skills/{self.skill_slug}/`"
            f"\nOffline creator validator: {receipt.get('package_revision', 'not passed')}"
            "\nThis pull request changes the package only. It does not change"
            " `config/skills.yaml` or request activation. The reviewed registry"
            " revision controls enablement; merge, release, and activation remain"
            " separate human boundaries."
        )
        return title, body

    def validate(self, *, validation_request_id: str | None = None,
                 validation_attempt_id: str | None = None) -> dict:
        """Require both the host-owned package check and normal VM checks."""
        try:
            session = self._session()
            state = session._read()
            files = session._files(state)
            candidate = files._capture()
            receipt_path = session.directory / "skill-authoring-validation.json"
            # A fresh validation attempt supersedes every prior receipt, even
            # when the candidate bytes have not changed. This prevents a new
            # host-side refusal from leaving old evidence publishable.
            receipt_path.unlink(missing_ok=True)
            receipt = validate_skill_candidate(
                candidate, baseline=files.baseline, slug=self.skill_slug,
            )
            if not receipt.passed:
                return {"ok": False, "error": "skill package checks failed", "skill_validation": receipt.as_dict()}
            result = session.validate()
            frozen = files.frozen()
            if frozen.fingerprint != receipt.candidate_digest:
                return {
                    "ok": False,
                    "error": "candidate changed between offline checks and sandbox verification; validate again",
                    "skill_validation": receipt.as_dict(),
                    "sandbox_validation": result,
                }
            if result.get("ok"):
                evidence = receipt.as_dict()
                if validation_request_id and validation_attempt_id:
                    evidence.update(validation_request_id=validation_request_id,
                                    validation_attempt_id=validation_attempt_id,
                                    sandbox_job_id=state.get("run_id"))
                atomic_json(session.directory / "skill-authoring-validation.json", evidence)
            return {**result, "skill_validation": receipt.as_dict()}
        except (OSError, ValueError, KeyError, SandboxError) as exc:
            return {"ok": False, "error": str(exc)}

    def submit(self) -> dict:
        """Reject publication unless both receipts bind the current snapshot."""
        try:
            session = self._session()

            def preflight(files, state):
                candidate = files.frozen()
                receipt_path = session.directory / "skill-authoring-validation.json"
                receipt = json.loads(receipt_path.read_bytes())
                if (not self._offline_receipt_matches(receipt, candidate.fingerprint)
                        or state.get("candidate") != candidate.fingerprint
                        or state.get("phase") not in {"validated", "publication_pending"}):
                    raise SandboxError("a matching offline skill validation and sandbox receipt are required")

            return super().submit(preflight=preflight)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, SandboxError):
            return {"ok": False, "error": "a matching offline skill validation and sandbox receipt are required"}

    def status(self) -> dict:
        """Expose only the package digest when its receipt matches the frozen VM candidate."""
        state = super().status()
        if not state.get("active") and not state.get("phase"):
            return state
        try:
            session = self._runtime().active(self._repository(), self._kind, self._allowed)
            if session is None:
                return state
            current = session._read()
            if (current.get("run_id") != state.get("run_id")
                    or (self.expected_job_id is not None
                        and current.get("run_id") != self.expected_job_id)):
                return state
            receipt_path = session.directory / "skill-authoring-validation.json"
            receipt = json.loads(receipt_path.read_bytes())
            if self._offline_receipt_matches(receipt, state.get("candidate")):
                frozen = session._files(current).frozen()
                if frozen.fingerprint == state.get("candidate"):
                    state["package_revision"] = receipt["package_revision"]
                    if receipt.get("sandbox_job_id") == current.get("run_id"):
                        for key in ("validation_request_id", "validation_attempt_id"):
                            if isinstance(receipt.get(key), str):
                                state[key] = receipt[key]
        except (OSError, ValueError, KeyError, TypeError, AttributeError, SandboxError):
            pass
        return state

    def _offline_receipt_matches(self, receipt, candidate_digest: str) -> bool:
        """Accept only a complete host receipt for this exact candidate/package."""
        if not isinstance(receipt, dict):
            return False
        if (type(receipt.get("schema_version")) is not int
                or receipt.get("schema_version") != 1
                or receipt.get("kind") != "skill_authoring_offline_validation"
                or receipt.get("slug") != self.skill_slug
                or receipt.get("passed") is not True
                or type(receipt.get("provider_calls")) is not int
                or receipt.get("provider_calls") != 0
                or receipt.get("candidate_digest") != candidate_digest
                or not isinstance(receipt.get("package_revision"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", receipt["package_revision"])
                or type(receipt.get("checked_files")) is not int
                or receipt["checked_files"] < 1
                or type(receipt.get("checked_bytes")) is not int
                or receipt["checked_bytes"] < 1):
            return False
        checks = receipt.get("checks")
        if not isinstance(checks, list) or not checks:
            return False
        if not all(
            isinstance(check, dict)
            and isinstance(check.get("name"), str)
            and bool(check["name"])
            and check.get("passed") is True
            and isinstance(check.get("detail"), str)
            for check in checks
        ):
            return False
        check_names = [check["name"] for check in checks]
        return (
            len(set(check_names)) == len(check_names)
            and set(check_names) == _REQUIRED_OFFLINE_CHECKS
        )

    def describe_boundary(self) -> str:
        return (
            f"Skill authoring is confined to skills/{self.skill_slug}/ and "
            f"tests/fixtures/skills_authoring/{self.skill_slug}/. Files are "
            "edited and verified in Mortimer's existing disposable offline VM. "
            "The live registry, validators, sandbox policy, dependencies, sibling "
            "skills, host vault, provider credentials, and activation state are "
            "outside this session. A validated candidate may become a review PR; "
            "merge, release, and activation remain separate human boundaries."
        )
