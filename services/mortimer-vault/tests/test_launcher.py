"""Launcher contract: repository source and private data stay independent."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("external", [False, True])
def test_launcher_selects_package_and_preserves_data_home(tmp_path, external):
    repo = tmp_path / "checkout with spaces"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / "run_kb.sh"
    shutil.copyfile(Path(__file__).resolve().parents[3] / "scripts/run_kb.sh", launcher)
    package = tmp_path / "external package" if external else repo / "services/mortimer-vault"
    executable = package / ".venv/bin/mortimer-vault"
    executable.parent.mkdir(parents=True)
    executable.write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$MORTIMER_HOME" "$@"\n')
    executable.chmod(0o755)
    data_home = tmp_path / "private data"
    env = {**os.environ, "HOME": str(tmp_path / "unrelated home"), "MORTIMER_HOME": str(data_home)}
    env.pop("MORTIMER_VAULT_DIR", None)
    if external:
        env["MORTIMER_VAULT_DIR"] = str(package)
    result = subprocess.run(["bash", str(launcher)], cwd=tmp_path, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(package.resolve()), str(data_home), "serve"]
    assert not data_home.exists()


def test_launcher_missing_environment_explains_setup(tmp_path):
    repo = tmp_path / "checkout"
    (repo / "scripts").mkdir(parents=True)
    (repo / "services/mortimer-vault").mkdir(parents=True)
    launcher = repo / "scripts/run_kb.sh"
    shutil.copyfile(Path(__file__).resolve().parents[3] / "scripts/run_kb.sh", launcher)
    env = dict(os.environ)
    env.pop("MORTIMER_VAULT_DIR", None)
    result = subprocess.run(["bash", str(launcher)], env=env, text=True, capture_output=True)
    assert result.returncode == 1
    assert "setup_kb.sh" in result.stderr
