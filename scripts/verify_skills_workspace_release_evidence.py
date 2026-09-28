#!/usr/bin/env python3
"""Fail closed when local Skills Workspace release evidence is stale or inconsistent.

This verifies candidate identity binding only. A passing result is not evidence
that manual, voice, accessibility, provider, display, or deployment gates pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.mortimer_candidate_fingerprint import worktree_fingerprint

RECEIPTS = (
    "sw-b-package-integrity-20260928.json",
    "sw-c-selection-quality-20260928.json",
    "sw-e-protected-png-20260928.json",
    "skill-store-navigation-performance-2026-09-28.json",
    "skill-selection-performance-2026-09-28.json",
    "mortimerhost-app-bundle-20260928.json",
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("git_candidate_identity_unavailable")
    return result.stdout.strip()


def _candidate_fingerprint(receipt: dict[str, Any]) -> str | None:
    candidate = receipt.get("candidate")
    if isinstance(candidate, dict):
        value = candidate.get("worktree_fingerprint_sha256")
        return value if isinstance(value, str) else None
    value = receipt.get("candidate_worktree_fingerprint_sha256")
    return value if isinstance(value, str) else None


def _verify_app_signature(bundle_path: Path) -> bool:
    """Verify the recorded app artifact still has a valid code signature."""
    try:
        result = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(bundle_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def verify_release_evidence(root: Path, fingerprint: str | None = None) -> list[str]:
    """Return actionable errors for required candidate-bound evidence files."""
    root = root.resolve(strict=True)
    errors: list[str] = []
    try:
        expected_fingerprint = fingerprint or worktree_fingerprint(root)
        head = _git(root, "rev-parse", "HEAD")
        branch = _git(root, "branch", "--show-current")
        dirty = bool(_git(root, "status", "--porcelain"))
    except (OSError, ValueError) as exc:
        return [f"candidate identity unavailable: {exc}"]

    receipt_dir = root / "docs/acceptance/skills-workspace/receipts"
    for filename in RECEIPTS:
        path = receipt_dir / filename
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{filename}: unreadable receipt ({type(exc).__name__})")
            continue
        if not isinstance(receipt, dict):
            errors.append(f"{filename}: receipt root must be an object")
            continue

        candidate = receipt.get("candidate")
        if not isinstance(candidate, dict):
            candidate = {}
        actual_fingerprint = _candidate_fingerprint(receipt)
        if actual_fingerprint != expected_fingerprint:
            errors.append(f"{filename}: candidate fingerprint is stale or missing")
        receipt_head = candidate.get("head", receipt.get("candidate_commit"))
        if receipt_head is None:
            errors.append(f"{filename}: candidate HEAD is missing")
        elif receipt_head != head:
            errors.append(f"{filename}: candidate HEAD differs from current HEAD")
        receipt_branch = candidate.get("branch", receipt.get("candidate_branch"))
        if receipt_branch is None:
            errors.append(f"{filename}: candidate branch is missing")
        elif receipt_branch != branch:
            errors.append(f"{filename}: candidate branch differs from current branch")
        receipt_dirty = candidate.get("working_tree_dirty", receipt.get("candidate_dirty"))
        if not isinstance(receipt_dirty, bool):
            errors.append(f"{filename}: candidate dirty-state is missing or invalid")
        elif receipt_dirty is not dirty:
            errors.append(f"{filename}: dirty-tree state differs from current worktree")

        if filename == "mortimerhost-app-bundle-20260928.json":
            result = receipt.get("result")
            embedded = result.get("embedded_candidate_fingerprint_sha256") if isinstance(result, dict) else None
            if embedded != expected_fingerprint:
                errors.append(f"{filename}: embedded app fingerprint does not match candidate")
            if not isinstance(result, dict) or result.get("exit_code") != 0:
                errors.append(f"{filename}: app bundle receipt does not record a successful build")
                continue
            try:
                bundle_value = result["bundle_path"]
                bundle_path = Path(bundle_value)
                if not bundle_path.is_absolute():
                    bundle_path = root / bundle_path
                bundle_path = bundle_path.resolve(strict=True)
                bundle_path.relative_to(root)
                executable = bundle_path / "Contents/MacOS/MortimerHost"
                info_plist = bundle_path / "Contents/Info.plist"
                executable_bytes = executable.read_bytes()
                with info_plist.open("rb") as stream:
                    info = plistlib.load(stream)
            except (KeyError, OSError, ValueError, plistlib.InvalidFileException):
                errors.append(f"{filename}: app bundle artifact is missing or outside candidate")
                continue
            if hashlib.sha256(executable_bytes).hexdigest() != result.get("executable_sha256"):
                errors.append(f"{filename}: app executable digest differs from receipt")
            if len(executable_bytes) != result.get("executable_bytes"):
                errors.append(f"{filename}: app executable size differs from receipt")
            if info.get("MortimerCandidateFingerprint") != expected_fingerprint:
                errors.append(f"{filename}: app bundle plist fingerprint does not match candidate")
            if info.get("CFBundleIdentifier") != result.get("bundle_identifier"):
                errors.append(f"{filename}: app bundle identifier differs from receipt")
            if not _verify_app_signature(bundle_path):
                errors.append(f"{filename}: app bundle code signature is invalid or unavailable")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = verify_release_evidence(args.root)
    if errors:
        print("Skills Workspace release evidence is not current:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Candidate-bound Skills Workspace release evidence is current.")
    print("Manual, provider, accessibility, display, and deployment acceptance remain separate gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
