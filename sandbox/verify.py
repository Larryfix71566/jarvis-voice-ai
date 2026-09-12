"""Independent VM verification bound to host-owned candidate and profile data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

from sandbox.artifacts import Candidate, SECRET, SandboxError
from sandbox.control import GUEST_INPUT, GUEST_ROOT
from sandbox.durable import atomic_bytes, atomic_json
from sandbox.files import WorkspaceFiles


# GC1b: retain Larry's 900-second full-unit gate after moving it into the VM.
VALIDATE_PYTEST_TIMEOUT_S = 900

def runner_fingerprint() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ["artifacts.py", "control.py", "durable.py", "files.py", "images.py", "profiles.py",
                 "verify.py", "guest/hydrate.py", "guest/worker.sh", "guest/rpc.py", "guest/static-web-check.mjs",
                 "guest/desktop-probe.sh"]:
        digest.update(name.encode() + b"\0" + (root / name).read_bytes() + b"\0")
    return digest.hexdigest()


class Verifier:
    def __init__(self, controller, images):
        self.controller, self.images = controller, images

    def wait_ready(self, task: str, timeout: int = 90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.controller.command("exec", self.controller.read(task)["vm"], "/usr/bin/true",
                                        timeout=10, capture_output=True)
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                time.sleep(2)
        self.controller.stop(task)
        raise SandboxError("VM did not become ready")

    def desktop_probe(self, task: str, directory: Path, timeout: int = 180) -> dict:
        """Fail closed unless the worker owns a visible desktop (closure C5.1)."""
        state = self.controller.read(task)
        if not state.get("hydrated") or state.get("network") != "offline" or state.get("worker") != "mortimer-dev":
            raise SandboxError("Desktop probe requires a hydrated offline worker")
        started = time.monotonic()
        result = self.controller.guest(task, [*self.controller.worker_prefix(state), "/bin/bash",
                                              GUEST_INPUT + "/desktop-probe.sh"],
                                       timeout=timeout, capture=True, check=False, binary=True, max_output=256 * 1024)
        data = SECRET.sub(b"[redacted credential-shaped value]", result.stdout + b"\n" + result.stderr)
        atomic_bytes(directory / "desktop-probe.log", data)
        record = {"returncode": result.returncode, "passed": result.returncode == 0 and b"desktop=visible" in data,
                  "seconds": round(time.monotonic() - started, 3), "log_sha256": hashlib.sha256(data).hexdigest()}
        if not record["passed"]:
            raise SandboxError("Guest desktop is not attached; native checks cannot run (see desktop-probe.log)")
        return record

    def run_check(self, task: str, name: str, argv: tuple[str, ...], directory: Path, timeout: int) -> dict:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        script = "cd " + GUEST_ROOT + "/source && source " + GUEST_ROOT + "/development.env && exec " + shlex.join(argv)
        started = time.monotonic()
        def remaining():
            budget = int(started + timeout - time.monotonic())
            if budget < 1:
                self.controller.stop(task)
                raise SandboxError("Check runtime budget exhausted")
            return budget
        state = self.controller.read(task)
        if not state.get("hydrated") or state.get("network") != "offline" or state.get("worker") != "mortimer-dev":
            raise SandboxError("Checks require a hydrated offline worker")
        if argv and argv[0] in {"swift", "/usr/bin/swift"}:
            # Worker Keychain preferences can disappear between setup, long
            # test runs and restarts. Re-select the disposable store
            # immediately before native checks. It is the worker's login
            # keychain (closure C5): loginwindow unlocks it at auto-login,
            # its password is a guest-only secret, and the desktop probe has
            # already proven it accepts writes without a prompt.
            keychain = "/Users/mortimer-dev/Library/Keychains/login.keychain-db"
            for arguments in [("list-keychains", "-d", "user", "-s", keychain),
                              ("default-keychain", "-d", "user", "-s", keychain)]:
                selection = self.controller.guest(task, [*self.controller.worker_prefix(state), "/usr/bin/security", *arguments],
                                                  timeout=min(remaining(), 15), capture=True, check=False, binary=True)
                if selection.returncode != 0:
                    # Keep the evidence: a bare "guest command failed" left
                    # attempt 01ff3480 (closure C5 record) undiagnosable.
                    data = SECRET.sub(b"[redacted credential-shaped value]",
                                      b"security " + " ".join(arguments).encode() + b" exited " + str(selection.returncode).encode()
                                      + b"\n" + selection.stdout + b"\n" + selection.stderr)
                    atomic_bytes(directory / (name + ".log"), data)
                    raise SandboxError("Keychain selection failed before " + name + " (see " + name + ".log)")
        def progress(stdout, stderr):
            # Only complete lines are exposed while a process is running, so
            # a credential split across chunks is redacted as one value.
            complete = lambda data: data[:data.rfind(b"\n") + 1]
            data = SECRET.sub(b"[redacted credential-shaped value]", complete(stdout) + b"\n" + complete(stderr))
            atomic_bytes(directory / (name + ".log"), data)
        result = self.controller.guest(task, [*self.controller.worker_prefix(state), "/bin/bash", "--noprofile", "--norc", "-c", script],
            timeout=remaining(), capture=True, check=False, binary=True, max_output=2 * 1024 * 1024,
            on_output=progress)
        data = SECRET.sub(b"[redacted credential-shaped value]", result.stdout + b"\n" + result.stderr)
        atomic_bytes(directory / (name + ".log"), data)
        return {"name": name, "argv": list(argv), "returncode": result.returncode,
                "passed": result.returncode == 0, "seconds": round(time.monotonic() - started, 3),
                "log_sha256": hashlib.sha256(data).hexdigest()}

    def verify(self, files: WorkspaceFiles, repo: Path, image_id: str, profile, *, timeout: int = 7200) -> dict:
        if not 1 <= timeout <= 7200 or not profile.checks:
            raise SandboxError("Invalid verification budget or missing required checks")
        ref = self.controller.read(files.task).get("source_commit")
        if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{40,64}", ref):
            raise SandboxError("Development task has no immutable source revision")
        candidate = files.freeze()
        revision = files.status()["revision"]
        attempt = uuid.uuid4().hex
        directory = files.directory / "verification" / attempt
        directory.mkdir(parents=True, mode=0o700)
        receipt = {"version": 1, "attempt": attempt, "candidate": candidate.fingerprint,
                   "baseline": files.baseline.fingerprint, "source_commit": ref, "image": image_id, "profile": profile.fingerprint,
                   "runner": runner_fingerprint(), "development_task": files.task, "checks": [],
                   "passed": False, "status": "starting"}
        atomic_json(directory / "receipt.json", receipt)
        deadline = time.monotonic() + timeout
        verification_task = None
        try:
            self.controller.stop(files.task)
            verification_task = self.images.create(image_id, repo, ref, profile,
                                                     purpose="verification", candidate=candidate, parent_task=files.task)
            receipt.update(verification_task=verification_task, status="hydrating")
            atomic_json(directory / "receipt.json", receipt)
            # Native AppKit tests need a real desktop surface for window
            # visibility, focus and animation assertions. Profiles opt in
            # explicitly; network, audio and clipboard isolation are unchanged.
            self.controller.start(verification_task, provisioning=False,
                                  headless=not profile.requires_graphics)
            self.wait_ready(verification_task)
            self.images.hydrate(verification_task)
            if profile.requires_graphics:
                # worker.sh configures the disposable worker for auto-login.
                # Restart once so AppKit checks run inside that worker's real
                # WindowServer session instead of the provisioning admin login.
                self.controller.stop(verification_task)
                self.controller.start(verification_task, provisioning=False, headless=False)
                self.wait_ready(verification_task)
                # Closure C5.1 (gap G20): graphics allocation alone proves
                # nothing; a probe window must report itself visible in the
                # worker's own session before any AppKit check runs.
                receipt["desktop_probe"] = self.desktop_probe(verification_task, directory)
                atomic_json(directory / "receipt.json", receipt)
            for index, argv in enumerate(profile.seeds):
                remaining = int(deadline - time.monotonic())
                if remaining < 1:
                    raise SandboxError("Verification runtime budget exhausted")
                seed = self.run_check(verification_task, "seed-" + str(index), argv, directory, min(remaining, 180))
                if not seed["passed"]:
                    raise SandboxError("Synthetic state initialization failed")
            receipt["status"] = "checking"
            for name, argv in profile.checks:
                remaining = int(deadline - time.monotonic())
                if remaining < 1:
                    raise SandboxError("Verification runtime budget exhausted")
                budget = (VALIDATE_PYTEST_TIMEOUT_S
                          if profile.name == "mortimer" and name in {"backend", "baseline-backend"}
                          else 1800)
                receipt["checks"].append(self.run_check(verification_task, name, argv, directory, min(remaining, budget)))
                atomic_json(directory / "receipt.json", receipt)
            observed = Candidate.decode(self.controller.rpc(verification_task, {"operation": "capture",
                "baseline_paths": [file.path for file in files.baseline.files]}))
            receipt["source_unchanged"] = observed.fingerprint == candidate.fingerprint
            receipt["passed"] = receipt["source_unchanged"] and all(check["passed"] for check in receipt["checks"])
            receipt["status"] = "passed" if receipt["passed"] else "failed"
        except Exception:
            receipt.update(passed=False, status="interrupted_or_failed")
            raise
        finally:
            try:
                if verification_task is not None:
                    self.controller.stop(verification_task)
            except Exception:
                receipt.update(passed=False, status="stop_failed")
                raise
            finally:
                atomic_json(directory / "receipt.json", receipt)
                with files._locked():
                    journal = files._journal()
                    if journal.get("candidate") == candidate.fingerprint and journal.get("revision") == revision:
                        journal["verification"] = {"attempt": attempt, "passed": receipt["passed"]}
                        files._save(journal)
        return receipt

    def receipt(self, files: WorkspaceFiles, image_id: str, profile) -> dict:
        """Fail closed after edits, profile/runner changes, or incomplete checks."""
        journal = files.status()
        reference = journal.get("verification")
        if not isinstance(reference, dict) or reference.get("passed") is not True:
            raise SandboxError("Candidate has no successful independent verification")
        attempt = reference.get("attempt")
        if not isinstance(attempt, str) or len(attempt) != 32 or any(c not in "0123456789abcdef" for c in attempt):
            raise SandboxError("Invalid verification reference")
        receipt = json.loads((files.directory / "verification" / attempt / "receipt.json").read_bytes())
        expected = {"candidate": files.frozen().fingerprint, "baseline": files.baseline.fingerprint,
                    "source_commit": self.controller.read(files.task).get("source_commit"),
                    "image": image_id, "profile": profile.fingerprint, "runner": runner_fingerprint(),
                    "development_task": files.task, "passed": True, "status": "passed", "source_unchanged": True}
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise SandboxError("Verification does not match the current candidate and runner")
        checks = receipt.get("checks", [])
        if [(check.get("name"), tuple(check.get("argv", []))) for check in checks] != list(profile.checks):
            raise SandboxError("Verification omitted or replaced a required check")
        if any(check.get("passed") is not True or check.get("returncode") != 0 for check in checks):
            raise SandboxError("A required verification check did not pass")
        directory = files.directory / "verification" / attempt
        for check in checks:
            # Names have already matched the installed host profile exactly.
            if hashlib.sha256((directory / (check["name"] + ".log")).read_bytes()).hexdigest() != check.get("log_sha256"):
                raise SandboxError("Verification evidence does not match its receipt")
        return receipt
