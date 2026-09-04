"""Guard test for scripts/mortimer.sh (gap-closure plan GC7): two process
managers must never fight over the same processes, so mortimer.sh refuses
to run when launchd already owns the bot service."""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MORTIMER_SH = REPO_ROOT / "scripts" / "mortimer.sh"


def test_mortimer_sh_is_valid_bash():
    proc = subprocess.run(["bash", "-n", str(MORTIMER_SH)], capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()


def test_mortimer_sh_has_launchd_guard():
    text = MORTIMER_SH.read_text()
    assert "com.mortimer.bot" in text
    assert "launchd_gen.py --status" in text
