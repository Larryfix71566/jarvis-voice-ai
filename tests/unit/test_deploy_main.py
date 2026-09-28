"""scripts/deploy_main.sh (DEPLOY-MAIN): human-only, and safe to run from the
checkout it replaces.

It moved into the repo from the git-ignored closure-checks/DEPLOY-MAIN.sh on
2026-09-26 (Larry's decision of 2026-09-25), because Mortimer names it after
every merge. Phase C checks production out at the target. When the script is
run from production, that replaces the running file, and bash reads a script
as it goes. The script is one function called on its last line, so bash has
parsed all of it before anything runs. These tests replace the file mid-run
and check that the new bytes are never executed. The control test shows the
same replacement does hijack a plain script.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from jarvis.selfedit.allowlist import DENIED, Allowlist

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "deploy_main.sh"
SERVICE_HEALTH = REPO_ROOT / "scripts" / "service_health.py"
BASH = shutil.which("bash")

# What the checkout "replaces" the script with: blank lines past any offset
# bash could have reached in the original, then a line that must never run.
REPLACEMENT = "\n" * 65536 + "echo INJECTED; exit 7\n"

# A stand-in git. `fetch` replaces $DEPLOY_SCRIPT, as the phase C checkout
# would, and succeeds; rev-parse and log answer; merge-base says the target
# lacks #80, which is the script's first refusal after the fetch.
FAKE_GIT = """#!/bin/sh
case " $* " in
  *" fetch "*) printf '%s' "$REPLACEMENT" > "$DEPLOY_SCRIPT"; exit 0;;
  *" rev-parse "*) echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; exit 0;;
  *" log "*) echo "origin/main: aaaaaaa 09-26 00:00 stand-in"; exit 0;;
  *" merge-base "*) exit 1;;
esac
exit 0
"""


def _run(script: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    git = fake / "git"
    git.write_text(FAKE_GIT)
    git.chmod(git.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"HOME": str(home), "PATH": f"{fake}{os.pathsep}/usr/bin{os.pathsep}/bin",
           "DEPLOY_SCRIPT": str(script), "REPLACEMENT": REPLACEMENT,
           "LANG": "C", "TMPDIR": str(tmp_path)}
    return subprocess.run([BASH, str(script)], env=env, capture_output=True,
                          text=True, timeout=60)


def test_deploy_main_is_human_only() -> None:
    allowlist = Allowlist.load(REPO_ROOT / "config" / "self_edit_allowlist.json")
    assert allowlist.tier("scripts/deploy_main.sh") == DENIED


def test_service_health_is_human_only() -> None:
    allowlist = Allowlist.load(REPO_ROOT / "config" / "self_edit_allowlist.json")
    assert allowlist.tier("scripts/service_health.py") == DENIED


def test_phase_d_does_not_curl_the_sidecar_or_bot_directly() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'hcode http://127.0.0.1:7861' not in source
    assert 'hcode http://127.0.0.1:7860' not in source
    assert 'scripts/service_health.py admin' in source
    assert 'scripts/service_health.py bot' in source


def test_service_health_prints_only_status_codes_against_local_stub(tmp_path: Path) -> None:
    import http.server
    import threading

    received: list[tuple[str, str | None]] = []
    token = "jvt_local-test-token"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get("Authorization")))
            if getattr(server, "redirect_mode", False):
                code = 307
                self.send_response(code)
                self.send_header("Location", "http://external.invalid/should-not-follow")
                self.end_headers()
                return
            code = 200 if self.headers.get("Authorization") == f"Bearer {token}" else 401
            self.send_response(code)
            self.end_headers()

        def log_message(self, _format: str, *args) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.redirect_mode = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {
            "HOME": str(tmp_path),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONPATH": str(REPO_ROOT),
            "JARVIS_VAULT_ENABLED": "false",
            "JARVIS_ADMIN_PORT": str(server.server_port),
            "JARVIS_SERVICE_TOKEN": token,
            # A misconfigured ambient proxy must not receive the token or
            # prevent direct loopback checks.
            "HTTP_PROXY": "http://127.0.0.1:1",
            "http_proxy": "http://127.0.0.1:1",
            "ALL_PROXY": "http://127.0.0.1:1",
            "all_proxy": "http://127.0.0.1:1",
        }
        result = subprocess.run(
            [sys.executable, str(SERVICE_HEALTH), "admin"],
            env=env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == "200\n"
        assert result.stderr == ""
        assert token not in result.stdout + result.stderr
        assert received == [("/api/health", f"Bearer {token}")]

        server.redirect_mode = True
        result = subprocess.run(
            [sys.executable, str(SERVICE_HEALTH), "admin"],
            env=env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == "307\n"
        assert result.stderr == ""
        assert token not in result.stdout + result.stderr
        assert received[-1] == ("/api/health", f"Bearer {token}")
        assert len(received) == 2, "the 307 Location must not be followed"

        env.pop("JARVIS_SERVICE_TOKEN")
        server.redirect_mode = False
        result = subprocess.run(
            [sys.executable, str(SERVICE_HEALTH), "admin"],
            env=env, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout == "401\n"
        assert result.stderr == ""
        assert received[-1] == ("/api/health", None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_deploy_main_parses() -> None:
    result = subprocess.run([BASH, "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_a_replaced_plain_script_runs_the_new_bytes(tmp_path: Path) -> None:
    # Control: without the function, the replacement is what bash runs next.
    script = tmp_path / "plain.sh"
    script.write_text("#!/bin/bash\ngit fetch -q origin\necho AFTER\n")
    result = _run(script, tmp_path)
    assert "INJECTED" in result.stdout
    assert "AFTER" not in result.stdout
    assert result.returncode == 7


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_deploy_main_never_runs_the_file_that_replaced_it(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout" / "scripts"
    checkout.mkdir(parents=True)
    script = checkout / "deploy_main.sh"
    shutil.copyfile(SCRIPT, script)
    result = _run(script, tmp_path)
    assert script.read_text() == REPLACEMENT  # the file really was replaced mid-run
    assert "INJECTED" not in result.stdout
    assert "STOPPED: origin/main does not contain #80 (88b206f)" in result.stdout
    assert result.returncode == 1
    # The log goes beside the rollback snapshots, not into the checkout.
    logs = list((tmp_path / "home" / "MortimerRollback" / "logs").glob("deploy-main-*.log"))
    assert len(logs) == 1
    # Bash exits before its process-substitution tee child is guaranteed to
    # flush the last bytes to disk. Wait briefly for the log receipt.
    for _ in range(100):
        if "STOPPED: origin/main does not contain #80" in logs[0].read_text():
            break
        time.sleep(0.01)
    assert "STOPPED: origin/main does not contain #80" in logs[0].read_text()
    assert not (tmp_path / "checkout" / "closure-checks").exists()
