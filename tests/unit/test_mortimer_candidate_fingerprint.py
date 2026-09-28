from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.mortimer_candidate_fingerprint import worktree_fingerprint


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True)


def _repo(root: Path) -> Path:
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Fingerprint Test")
    (root / ".gitignore").write_text(".build/\nsecrets.vault\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("value = 1\n", encoding="utf-8")
    _git(root, "add", ".gitignore", "src/main.py")
    _git(root, "commit", "-qm", "baseline")
    return root


def test_fingerprint_binds_tracked_unstaged_and_untracked_files_but_skips_ignored(tmp_path):
    root = _repo(tmp_path / "repo")
    initial = worktree_fingerprint(root)

    (root / "src" / "main.py").write_text("value = 2\n", encoding="utf-8")
    assert worktree_fingerprint(root) != initial
    changed = worktree_fingerprint(root)

    (root / "new.py").write_text("candidate = True\n", encoding="utf-8")
    with_new_source = worktree_fingerprint(root)
    assert with_new_source != changed

    (root / ".build").mkdir()
    (root / ".build" / "output.bin").write_bytes(b"generated")
    (root / "secrets.vault").write_bytes(b"local secret material")
    assert worktree_fingerprint(root) == with_new_source


def test_fingerprint_changes_when_a_tracked_file_is_deleted(tmp_path):
    root = _repo(tmp_path / "repo")
    initial = worktree_fingerprint(root)
    (root / "src" / "main.py").unlink()
    assert worktree_fingerprint(root) != initial


def test_fingerprint_uses_symlink_target_text_without_reading_target(tmp_path):
    root = _repo(tmp_path / "repo")
    external = tmp_path / "outside.txt"
    external.write_text("private target bytes", encoding="utf-8")
    (root / "link.txt").symlink_to(external)
    _git(root, "add", "link.txt")
    _git(root, "commit", "-qm", "add symlink")

    before = worktree_fingerprint(root)
    external.write_text("different target bytes", encoding="utf-8")
    assert worktree_fingerprint(root) == before

    replacement = tmp_path / "other.txt"
    replacement.write_text("also private", encoding="utf-8")
    (root / "link.txt").unlink()
    (root / "link.txt").symlink_to(replacement)
    assert worktree_fingerprint(root) != before


def test_acceptance_receipts_are_excluded_to_avoid_digest_recursion(tmp_path):
    root = _repo(tmp_path / "repo")
    receipt_dir = root / "docs/acceptance/skills-workspace/receipts"
    receipt_dir.mkdir(parents=True)
    tracked_receipt = receipt_dir / "build.json"
    tracked_receipt.write_text('{"fingerprint":"old"}\n', encoding="utf-8")
    _git(root, "add", "docs/acceptance/skills-workspace/receipts/build.json")
    _git(root, "commit", "-qm", "add receipt")

    baseline = worktree_fingerprint(root)
    tracked_receipt.write_text('{"fingerprint":"new"}\n', encoding="utf-8")
    assert worktree_fingerprint(root) == baseline

    (receipt_dir / "later.json").write_text('{"result":"ok"}\n', encoding="utf-8")
    assert worktree_fingerprint(root) == baseline

    source = root / "src/main.py"
    source.write_text("value = 7\n", encoding="utf-8")
    assert worktree_fingerprint(root) != baseline
