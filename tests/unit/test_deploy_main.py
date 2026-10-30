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
import shlex
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


def _generated_legacy_rollback(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Render the actual non-held ROLLBACK.sh heredoc into a disposable fixture."""
    source = SCRIPT.read_text(encoding="utf-8")
    opener = '  cat > "$RB/ROLLBACK.sh" <<RBEOF\n'
    assert source.count(opener) == 1
    template = source.split(opener, 1)[1].split("\nRBEOF", 1)[0]
    home = tmp_path / "home"
    checkout = tmp_path / "checkout"
    rollback_dir = home / "MortimerRollback" / "fixture"
    checkout.mkdir()
    rollback_dir.mkdir(parents=True)
    wrapper = tmp_path / "render.sh"
    rollback_script = rollback_dir / "ROLLBACK.sh"
    wrapper.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f"C={shlex.quote(str(checkout))}\n"
        f"RB={shlex.quote(str(rollback_dir))}\n"
        "PRIOR=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        'SERVICES="bot admin"\nUIDN=4242\nSHORT=fixture\nTS=fixture\n'
        f"cat > {shlex.quote(str(rollback_script))} <<RBEOF\n"
        f"{template}\nRBEOF\n"
    )
    rendered = subprocess.run([BASH, str(wrapper)], capture_output=True, text=True, timeout=10)
    assert rendered.returncode == 0, rendered.stderr
    return rollback_script, checkout, rollback_dir


def _fake_rollback_commands(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    call_log = tmp_path / "calls.log"
    for name in ("osascript", "sleep", "pkill", "git", "tar", "rm", "ditto", "launchctl", "open"):
        command = fake_bin / name
        command.write_text('#!/bin/sh\nprintf "%s\\n" "' + name + ' $*" >> "$CALL_LOG"\nexit 0\n')
        command.chmod(command.stat().st_mode | stat.S_IEXEC)
    return fake_bin, call_log


def _seed_rollback_state(checkout: Path, rollback_dir: Path) -> dict[str, bytes]:
    files = {
        checkout / "data" / "jarvis.db": b"current-db",
        checkout / "data" / "jarvis.db-wal": b"current-wal",
        checkout / "data" / "jarvis.db-shm": b"current-shm",
        checkout / "macos" / "MortimerHost" / ".build" / "MortimerHost.app" / "Contents" / "Info.plist": b"current-app",
        rollback_dir / "jarvis.db": b"snapshot-db",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
@pytest.mark.parametrize("args", [
    ("--restore-db",),
    ("unsupported",),
    ("--restore-db", "unsupported"),
    ("unsupported", "--restore-db"),
    ("unsupported", "middle", "--restore-db"),
    ("unsupported", "--restore-db", "after"),
    ("",),
    ("--",),
])
def test_generated_legacy_rollback_rejects_every_argument_before_effects(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    rollback_script, checkout, rollback_dir = _generated_legacy_rollback(tmp_path)
    state = _seed_rollback_state(checkout, rollback_dir)
    fake_bin, call_log = _fake_rollback_commands(tmp_path)
    before = {path: path.read_bytes() for path in state}
    env = {"HOME": str(tmp_path / "home"), "PATH": f"{fake_bin}{os.pathsep}/usr/bin:/bin",
           "CALL_LOG": str(call_log), "LANG": "C"}

    result = subprocess.run([BASH, str(rollback_script), *args], env=env,
                            capture_output=True, text=True, timeout=10)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "rollback accepts no arguments\n"
    assert not call_log.exists(), "argument refusal must precede every external side effect"
    assert {path: path.read_bytes() for path in state} == before


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_generated_legacy_rollback_preserves_no_argument_code_app_path(tmp_path: Path) -> None:
    rollback_script, checkout, rollback_dir = _generated_legacy_rollback(tmp_path)
    _seed_rollback_state(checkout, rollback_dir)
    fake_bin, call_log = _fake_rollback_commands(tmp_path)
    env = {"HOME": str(tmp_path / "home"), "PATH": f"{fake_bin}{os.pathsep}/usr/bin:/bin",
           "CALL_LOG": str(call_log), "LANG": "C"}

    result = subprocess.run([BASH, str(rollback_script)], env=env,
                            capture_output=True, text=True, timeout=10)

    assert result.returncode == 0
    assert result.stderr == ""
    assert call_log.read_text().splitlines() == [
        "osascript -e tell application id \"com.mortimer.host\" to quit",
        "sleep 3",
        "pkill -x MortimerHost",
        "git -C " + str(checkout) + " checkout -q -f --detach aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "tar -C " + str(checkout) + " -xzf " + str(rollback_dir) + "/code.tgz",
        "rm -rf " + str(checkout) + "/macos/MortimerHost/.build/MortimerHost.app",
        "ditto " + str(rollback_dir) + "/MortimerHost.app " + str(checkout) + "/macos/MortimerHost/.build/MortimerHost.app",
        "launchctl kickstart -k gui/4242/com.mortimer.bot",
        "launchctl kickstart -k gui/4242/com.mortimer.admin",
        "sleep 8",
        "open " + str(checkout) + "/macos/MortimerHost/.build/MortimerHost.app",
    ]


def _swift_gate_harness(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    source = SCRIPT.read_text()
    function = source.split('  swift_gate() {', 1)[1].split('  echo "JarvisKit:"', 1)[0]
    script = tmp_path / "gate.sh"
    script.write_text(
        'set -uo pipefail\nV="$FIXTURE"; LOGD="$FIXTURE"; TS=fixture; ERR_RE="(^|: )error: "\n'
        'die() { echo "STOPPED: $*"; exit 1; }\n'
        'swift_gate() {' + function + '\nswift_gate package native\necho AFTER_GATE\n'
    )
    (tmp_path / "package").mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    swift = fake / "swift"
    swift.write_text('#!/bin/sh\nprintf "%s\\n" "$TALLY"\n'
                     'if [ "${WAIT_FOR_PERMIT:-}" = 1 ]; then\n'
                     '  while [ ! -f "$FIXTURE/permit" ]; do sleep .05; done\nfi\n'
                     'exit "$SWIFT_STATUS"\n')
    swift.chmod(0o700)
    env = {"HOME": str(tmp_path), "FIXTURE": str(tmp_path),
           "PATH": str(fake) + os.pathsep + "/usr/bin:/bin", "LANG": "C",
           "TALLY": "Executed 2 tests, with 0 failures", "SWIFT_STATUS": "0"}
    return script, env, tmp_path / "deploy-native-fixture.txt"


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
@pytest.mark.parametrize("status,tally,accepted", [
    (1, "Executed 2 tests, with 0 failures", False),
    (143, "Executed 2 tests, with 0 failures", False),
    (0, "Executed 2 tests, with 0 failures", True),
    (0, "no final tally", False),
    (0, "Executed 2 tests, with 1 failures", False),
])
def test_swift_gate_requires_exit_success_and_final_tally(tmp_path, status, tally, accepted):
    script, env, log = _swift_gate_harness(tmp_path)
    env.update(SWIFT_STATUS=str(status), TALLY=tally)
    result = subprocess.run([BASH, str(script)], env=env, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is accepted
    assert ("AFTER_GATE" in result.stdout) is accepted
    assert tally in log.read_text()


@pytest.mark.skipif(BASH is None, reason="bash is not installed")
def test_swift_gate_preserves_log_while_process_is_still_running(tmp_path):
    script, env, log = _swift_gate_harness(tmp_path)
    env["WAIT_FOR_PERMIT"] = "1"
    proc = subprocess.Popen([BASH, str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    visible = False
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if log.exists() and "Executed 2 tests" in log.read_text():
                visible = True
                break
            time.sleep(.05)
        assert proc.poll() is None, "synthetic child must remain blocked until permitted"
    finally:
        (tmp_path / "permit").touch()
        stdout, stderr = proc.communicate(timeout=10)
    assert visible, "native diagnostics must be durable while a process is stalled"
    assert proc.returncode == 0, stderr
    assert "AFTER_GATE" in stdout
