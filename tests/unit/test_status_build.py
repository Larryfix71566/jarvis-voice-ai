"""T2.3 — app_build_status()."""

from __future__ import annotations

import plistlib

from jarvis.status.build import APP_RELATIVE, app_build_status

SHA = "a" * 40


def _bundle(root, info):
    contents = root / APP_RELATIVE / "Contents"
    contents.mkdir(parents=True)
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)


def test_build_status_reads_plist_keys(tmp_path):
    _bundle(tmp_path, {"CFBundleName": "MortimerHost",
                       "MortimerSourceRevision": SHA,
                       "MortimerSourceDirty": "false",
                       "MortimerBuildConfiguration": "release"})
    out = app_build_status(tmp_path, head=lambda root: SHA)
    assert out["ok"] is True
    assert out["exists"] is True
    assert out["modified_at"]  # ISO, local timezone
    assert "+" in out["modified_at"] or "-" in out["modified_at"][10:]
    assert out["MortimerSourceRevision"] == SHA
    assert out["MortimerSourceDirty"] == "false"
    assert out["MortimerBuildConfiguration"] == "release"
    assert out["repo_head"] == SHA
    assert out["matches_repo_head"] is True


def test_build_status_mismatch(tmp_path):
    _bundle(tmp_path, {"MortimerSourceRevision": SHA})
    out = app_build_status(tmp_path, head=lambda root: "b" * 40)
    assert out["matches_repo_head"] is False
    assert out["MortimerBuildConfiguration"] is None


def test_build_status_missing_app(tmp_path):
    out = app_build_status(tmp_path, head=lambda root: None)
    assert out["exists"] is False
    assert out["modified_at"] is None
    assert out["MortimerSourceRevision"] is None
    assert out["matches_repo_head"] is False


def test_build_status_corrupt_plist(tmp_path):
    contents = tmp_path / APP_RELATIVE / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(b"not a plist")
    out = app_build_status(tmp_path, head=lambda root: SHA)
    assert out["ok"] is True
    assert out["plist_error"]
    assert out["matches_repo_head"] is False
