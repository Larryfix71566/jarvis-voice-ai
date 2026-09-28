import hashlib
import json
import plistlib
import subprocess
from types import SimpleNamespace

import pytest

import scripts.verify_skills_workspace_release_evidence as release_evidence
from scripts.mortimer_candidate_fingerprint import worktree_fingerprint
from scripts.verify_skills_workspace_release_evidence import (
    RECEIPTS,
    verify_release_evidence,
)

_verify_app_signature = release_evidence._verify_app_signature


@pytest.fixture(autouse=True)
def _accept_synthetic_app_signature(monkeypatch):
    # The fixture creates a synthetic, unsigned bundle. Signature verification
    # itself is exercised by the explicit fail-closed test below.
    monkeypatch.setattr(release_evidence, "_verify_app_signature", lambda _path: True)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _candidate_receipts(root):
    _git(root, "init", "-b", "candidate")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    source = root / "source.txt"
    source.write_text("candidate\n", encoding="utf-8")
    _git(root, "add", "source.txt")
    _git(root, "commit", "-m", "candidate")
    head = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True,
    ).strip()
    source.write_text("frozen candidate\n", encoding="utf-8")
    digest = worktree_fingerprint(root)
    dirty = bool(subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"], text=True,
    ).strip())
    receipt_dir = root / "docs/acceptance/skills-workspace/receipts"
    receipt_dir.mkdir(parents=True)
    app = root / ".build/MortimerHost.app"
    executable = app / "Contents/MacOS/MortimerHost"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"synthetic app executable")
    info_path = app / "Contents/Info.plist"
    info_path.write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "com.mortimer.host",
        "MortimerCandidateFingerprint": digest,
    }))
    for filename in RECEIPTS:
        receipt = {
            "candidate": {
                "branch": "candidate",
                "head": head,
                "working_tree_dirty": dirty,
                "worktree_fingerprint_sha256": digest,
            },
            "result": {"exit_code": 0},
        }
        if filename == "skill-selection-performance-2026-09-28.json":
            receipt.pop("candidate")
            receipt["candidate_worktree_fingerprint_sha256"] = digest
            receipt["candidate_commit"] = head
            receipt["candidate_branch"] = "candidate"
            receipt["candidate_dirty"] = dirty
        if filename == "mortimerhost-app-bundle-20260928.json":
            receipt["result"].update({
                "embedded_candidate_fingerprint_sha256": digest,
                "bundle_path": str(app),
                "bundle_identifier": "com.mortimer.host",
                "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "executable_bytes": executable.stat().st_size,
            })
        (receipt_dir / filename).write_text(json.dumps(receipt), encoding="utf-8")
    return digest


def test_release_receipt_set_accepts_matching_candidate_identity(tmp_path):
    digest = _candidate_receipts(tmp_path)

    assert verify_release_evidence(tmp_path, fingerprint=digest) == []


def test_release_receipt_set_reports_stale_or_missing_candidate_fields(tmp_path):
    digest = _candidate_receipts(tmp_path)
    receipt_path = (
        tmp_path / "docs/acceptance/skills-workspace/receipts"
        / "sw-b-package-integrity-20260928.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["candidate"]["worktree_fingerprint_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    errors = verify_release_evidence(tmp_path, fingerprint=digest)

    assert "sw-b-package-integrity-20260928.json: candidate fingerprint is stale or missing" in errors


def test_app_bundle_must_embed_the_current_candidate_fingerprint(tmp_path):
    digest = _candidate_receipts(tmp_path)
    receipt_path = (
        tmp_path / "docs/acceptance/skills-workspace/receipts"
        / "mortimerhost-app-bundle-20260928.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["result"]["embedded_candidate_fingerprint_sha256"] = "f" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    errors = verify_release_evidence(tmp_path, fingerprint=digest)

    assert "mortimerhost-app-bundle-20260928.json: embedded app fingerprint does not match candidate" in errors


def test_app_bundle_executable_must_match_receipt(tmp_path):
    digest = _candidate_receipts(tmp_path)
    executable = tmp_path / ".build/MortimerHost.app/Contents/MacOS/MortimerHost"
    executable.write_bytes(b"changed after bundle receipt")

    errors = verify_release_evidence(tmp_path, fingerprint=digest)

    assert "mortimerhost-app-bundle-20260928.json: app executable digest differs from receipt" in errors


def test_release_evidence_rejects_invalid_app_signature(tmp_path, monkeypatch):
    digest = _candidate_receipts(tmp_path)
    monkeypatch.setattr(release_evidence, "_verify_app_signature", lambda _path: False)

    errors = verify_release_evidence(tmp_path, fingerprint=digest)

    assert "mortimerhost-app-bundle-20260928.json: app bundle code signature is invalid or unavailable" in errors


def test_app_signature_verifier_runs_strict_codesign_check(tmp_path, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release_evidence.subprocess, "run", run)

    assert _verify_app_signature(tmp_path / "MortimerHost.app") is True
    assert calls == [(
        ["codesign", "--verify", "--deep", "--strict", str(tmp_path / "MortimerHost.app")],
        {"capture_output": True, "text": True, "check": False},
    )]


def test_candidate_identity_fields_are_required_even_for_top_level_receipt(tmp_path):
    digest = _candidate_receipts(tmp_path)
    receipt_path = (
        tmp_path / "docs/acceptance/skills-workspace/receipts"
        / "skill-selection-performance-2026-09-28.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("candidate_branch")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    errors = verify_release_evidence(tmp_path, fingerprint=digest)

    assert "skill-selection-performance-2026-09-28.json: candidate branch is missing" in errors


def test_required_missing_receipt_fails_closed(tmp_path):
    _candidate_receipts(tmp_path)
    (tmp_path / "docs/acceptance/skills-workspace/receipts" / RECEIPTS[0]).unlink()

    errors = verify_release_evidence(tmp_path)

    assert f"{RECEIPTS[0]}: unreadable receipt (FileNotFoundError)" in errors
