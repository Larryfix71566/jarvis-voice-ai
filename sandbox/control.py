#!/usr/bin/env python3
"""Host-owned, fail-closed Tart sandbox controller. Standard library only.

No candidate command executes on the host. No GitHub or provider credentials
are sent to the guest. Source imports come from an explicit committed revision.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid

try:
    from sandbox.artifacts import (MAX_SOURCE_BYTES, MAX_FILE_BYTES, MAX_FILES, SECRET,
                                   REVIEWED_TEST_FIXTURES, SandboxError, check_paths, source_path_allowed)
    from sandbox.durable import atomic_bytes, atomic_json
except ModuleNotFoundError:  # Direct script invocation.
    from artifacts import (MAX_SOURCE_BYTES, MAX_FILE_BYTES, MAX_FILES, SECRET,
                           REVIEWED_TEST_FIXTURES, SandboxError, check_paths, source_path_allowed)
    from durable import atomic_bytes, atomic_json

TASK_ID = re.compile(r"[0-9a-f]{12}\Z")
GUEST_ROOT = "/Users/admin/mortimer"
PRIVATE_NETWORKS = ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
                    '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
                    '224.0.0.0/4', '240.0.0.0/4')


def provisioning_network_blocks() -> str:
    # Softnet permits the host gateway by default. Explicit blocks override
    # that exception, including any globally addressed host interfaces.
    interfaces = subprocess.check_output(['/sbin/ifconfig'], text=True, timeout=10)
    addresses = {str(ipaddress.IPv4Address(value)) + '/32'
                 for value in re.findall(r'^\s*inet\s+(\S+)', interfaces, re.MULTILINE)}
    if not addresses:
        raise SandboxError('Cannot determine host IPv4 addresses; refusing provisioning')
    return ','.join([*PRIVATE_NETWORKS, *sorted(addresses)])


def snapshot(repo: Path, ref: str, output: Path) -> dict:
    """Export Git objects, never the host working directory or its symlinks."""
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--verify", ref + "^{commit}"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", sha):
        raise SandboxError("Invalid source commit")
    entries = subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-rz", sha]).split(b"\0")
    files, total = [], 0
    # Write a temporary file so a failed export cannot be mistaken for ready input.
    temporary = output.with_suffix(".partial")
    try:
        with tarfile.open(temporary, "w") as archive:
            for entry in entries:
                if not entry:
                    continue
                meta, raw_path = entry.split(b"\t", 1)
                mode, kind, blob = meta.decode().split()
                name = raw_path.decode("utf-8")
                if not source_path_allowed(name):
                    continue
                if kind != "blob" or mode not in {"100644", "100755"}:
                    raise SandboxError(f"Source contains unsupported link/submodule: {name}")
                size = int(subprocess.check_output(["git", "-C", str(repo), "cat-file", "-s", blob]))
                if size > MAX_FILE_BYTES or total + size > MAX_SOURCE_BYTES or len(files) >= MAX_FILES:
                    raise SandboxError(f"Source size limit exceeded: {name}")
                data = subprocess.check_output(["git", "-C", str(repo), "cat-file", "blob", blob])
                reviewed_fixture = REVIEWED_TEST_FIXTURES.get(name) == hashlib.sha256(data).hexdigest()
                if SECRET.search(data) and not reviewed_fixture:
                    raise SandboxError(f"Potential credential in source: {name}")
                item = tarfile.TarInfo(name)
                item.size, item.mode, item.mtime = len(data), int(mode, 8) & 0o777, 0
                archive.addfile(item, io.BytesIO(data))
                total += len(data)
                files.append(name)
        check_paths(files)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {"source_commit": sha, "source_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "source_files": len(files), "source_bytes": total}


class Controller:
    def __init__(self, home: Path, tart: str, softnet: str):
        self.home = home.expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.tart = str(Path(tart).expanduser().resolve())
        self.softnet = str(Path(softnet).expanduser().resolve())
        self.env = {"PATH": str(Path(self.softnet).parent) + ":/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                    "TART_HOME": str(self.home / "tart"), "LANG": "en_US.UTF-8"}

    def command(self, *args, **kwargs):
        return subprocess.run([self.tart, *args], env=self.env, check=True, **kwargs)

    def task_dir(self, task: str) -> Path:
        if not TASK_ID.fullmatch(task):
            raise SandboxError("Invalid task identifier")
        path = self.home / "tasks" / task
        if path.is_symlink() or not path.is_dir():
            raise SandboxError("Unknown task")
        return path

    def read(self, task: str) -> dict:
        return json.loads((self.task_dir(task) / "state.json").read_text())

    def save(self, task: str, state: dict):
        atomic_json(self.task_dir(task) / "state.json", state)

    def install_file_service(self, task: str):
        """Install reviewed host code, never code from the candidate checkout."""
        inputs, sources = self._file_service(task)
        inputs.mkdir(parents=True, exist_ok=True, mode=0o755)
        for name, data in sources.items():
            installed = inputs / name
            if installed.exists():
                if installed.read_bytes() != data:
                    raise SandboxError("Installed file service has been modified")
            else:
                atomic_bytes(installed, data, mode=0o644)
        (inputs / "requests").mkdir(exist_ok=True, mode=0o755)

    def _file_service(self, task: str):
        root = Path(__file__).resolve().parent
        sources = {"artifacts.py": (root / "artifacts.py").read_bytes(),
                   "rpc.py": (root / "guest" / "rpc.py").read_bytes()}
        version = hashlib.sha256(sources["artifacts.py"] + b"\0" + sources["rpc.py"]).hexdigest()
        # VirtioFS can retain an old inode after atomic replacement. Versions
        # get new immutable paths, including during a running task's upgrade.
        return self.task_dir(task) / "input" / "services" / version, sources

    def doctor(self) -> dict:
        helper = Path(self.softnet)
        info = helper.stat() if helper.exists() else None
        safe_helper = bool(info and info.st_uid == 0 and info.st_mode & stat.S_ISUID
                           and not info.st_mode & 0o022 and os.access(helper, os.X_OK))
        return {"tart": os.access(self.tart, os.X_OK), "isolated_network_helper": safe_helper,
                "state_directory": str(self.home), "max_active_tasks": 1,
                "memory_mib": 8192, "cpu_count": 4,
                "ready_to_boot": os.access(self.tart, os.X_OK) and safe_helper}

    def create(self, repo: Path, ref: str, image: str) -> str:
        task = uuid.uuid4().hex[:12]
        directory = self.home / "tasks" / task
        directory.mkdir(parents=True, mode=0o700)
        inputs = directory / "input"
        inputs.mkdir(mode=0o700)
        state = {"id": task, "vm": "mortimer-" + task, "image": image, "status": "creating"}
        self.save(task, state)
        try:
            state.update(snapshot(repo.resolve(), ref, inputs / "source.tar"))
            for script in (Path(__file__).parent / "guest").glob("*.sh"):
                shutil.copyfile(script, inputs / script.name)
            self.install_file_service(task)
            self.command("clone", image, state["vm"], timeout=7200)
            self.command("set", state["vm"], "--cpu", "4", "--memory", "8192", timeout=30)
            state["status"] = "created"
        except Exception:
            state["status"] = "failed"
            raise
        finally:
            self.save(task, state)
        return task

    def run_args(self, task: str, provisioning: bool, headless: bool) -> list[str]:
        state = self.read(task)
        args = ["run", "--no-clipboard", "--no-audio", "--net-softnet"]
        blocks = provisioning_network_blocks() if provisioning else '0.0.0.0/0'
        args.append('--net-softnet-block=' + blocks)
        if headless:
            args.append("--no-graphics")
        args += ["--dir=" + "input:" + str(self.task_dir(task) / "input") + ":ro", state["vm"]]
        return args

    def start(self, task: str, provisioning: bool = False, headless: bool = False):
        with (self.home / "start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._start_locked(task, provisioning, headless)

    def _start_locked(self, task: str, provisioning: bool, headless: bool):
        state = self.read(task)
        if (self.task_dir(task) / "cancelled.json").exists() or (state.get("parent_task") and
                (self.task_dir(state["parent_task"]) / "cancelled.json").exists()):
            raise SandboxError("Task has been cancelled")
        if not self.doctor()["ready_to_boot"]:
            raise SandboxError("Tart or the root-owned network isolation helper is missing; refusing to boot")
        if self.read(task).get("status") not in {"created", "stopped"}:
            raise SandboxError("Task is not in a startable state")
        for file in (self.home / "tasks").glob("*/state.json"):
            if json.loads(file.read_text()).get("status") in {"running", "provisioning"}:
                raise SandboxError("An active task is recorded; stop it before starting another")
        # Query actual VM state, not just our last saved status, after a restart.
        result = self.command("list", "--format", "json", capture_output=True, text=True, timeout=30)
        if any(vm.get("State", vm.get("state")) == "running" for vm in json.loads(result.stdout)):
            raise SandboxError("One active VM is allowed; stop it before starting another")
        state = self.read(task)
        if provisioning and state.get("prepared"):
            raise SandboxError("A prepared task cannot regain provisioning network access; create a fresh task")
        with (self.task_dir(task) / "vm.log").open("ab") as log:
            process = subprocess.Popen([self.tart, *self.run_args(task, provisioning, headless)],
                                       env=self.env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        state.update(status="provisioning" if provisioning else "running", pid=process.pid,
                     network="provisioning" if provisioning else "offline")
        self.save(task, state)

    def guest(self, task: str, argv: list[str], timeout: int = 1800, capture: bool = False,
              max_output: int = 8 * 1024 * 1024, binary: bool = False, check: bool = True, on_output=None):
        if not 1 <= timeout <= 7200:
            raise SandboxError("Timeout must be between 1 and 7200 seconds")
        state = self.read(task)
        if state["status"] not in {"running", "provisioning"}:
            raise SandboxError("Task must be running")
        if capture:
            return self._capture(task, argv, timeout, max_output, binary, check, on_output)
        try:
            return self.command("exec", state["vm"], *argv, timeout=timeout,
                                capture_output=capture, text=capture)
        except subprocess.TimeoutExpired:
            # Killing the client alone can leave guest code running.
            self.stop(task)
            raise SandboxError("Command timed out; VM stopped") from None

    def _capture(self, task: str, argv: list[str], timeout: int, limit: int, binary: bool = False, check: bool = True, on_output=None):
        if not 1 <= limit <= MAX_SOURCE_BYTES * 2:
            raise SandboxError("Invalid output limit")
        args = [self.tart, "exec", self.read(task)["vm"], *argv]
        process = subprocess.Popen(args, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = {process.stdout: bytearray(), process.stderr: bytearray()}
        deadline, size = time.monotonic() + timeout, 0
        reported_at = float("-inf")
        try:
            with selectors.DefaultSelector() as selector:
                for stream in output:
                    selector.register(stream, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SandboxError("Guest response timed out")
                    for key, _ in selector.select(remaining):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        size += len(chunk)
                        if size > limit:
                            raise SandboxError("Guest response size limit exceeded")
                        output[key.fileobj].extend(chunk)
                        if on_output is not None and time.monotonic() - reported_at >= 1:
                            on_output(bytes(output[process.stdout]), bytes(output[process.stderr]))
                            reported_at = time.monotonic()
            if on_output is not None:
                on_output(bytes(output[process.stdout]), bytes(output[process.stderr]))
            status = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except (SandboxError, subprocess.TimeoutExpired, OSError):
            if process.poll() is None:
                process.kill()
            process.wait()
            self.stop(task)
            raise SandboxError("Guest response exceeded its time or size limit; VM stopped") from None
        finally:
            for stream in output:
                stream.close()
        if status and check:
            raise SandboxError("Guest command failed")
        if binary:
            return subprocess.CompletedProcess(args, status, stdout=bytes(output[process.stdout]),
                                               stderr=bytes(output[process.stderr]))
        return subprocess.CompletedProcess(args, status,
            stdout=output[process.stdout].decode("utf-8", errors="replace"),
            stderr=output[process.stderr].decode("utf-8", errors="replace"))

    def rpc(self, task: str, request: dict) -> bytes:
        state = self.read(task)
        if state.get("status") != "running" or state.get("network") != "offline" or not state.get("prepared"):
            raise SandboxError("File operations require a prepared, offline task")
        if state.get("hydrated") is False:
            raise SandboxError("Fresh task hydration has not completed")
        inputs, sources = self._file_service(task)
        # An explicit upgrade can install the service on older prepared tasks;
        # ordinary requests must use precisely this host controller's version.
        for name, data in sources.items():
            installed = inputs / name
            if not installed.is_file() or installed.read_bytes() != data:
                raise SandboxError("Task file service needs a host-controlled upgrade")
        payload = json.dumps(request, ensure_ascii=True).encode("ascii")
        if len(payload) > MAX_FILE_BYTES * 2:
            raise SandboxError("File request size limit exceeded")
        request_path = inputs / "requests" / (uuid.uuid4().hex + ".json")
        atomic_bytes(request_path, payload, mode=0o644)
        try:
            shared = "/Volumes/My Shared Files/input/services/" + inputs.name
            result = self.guest(task, [*self.worker_prefix(state), "/opt/homebrew/opt/python@3.12/bin/python3.12", "-I",
                shared + "/rpc.py", shared + "/requests/" + request_path.name],
                timeout=120, capture=True, binary=True,
                max_output=MAX_SOURCE_BYTES * 2 if request.get("operation") == "capture" else MAX_FILE_BYTES * 2)
            return result.stdout
        finally:
            request_path.unlink(missing_ok=True)

    def prepare(self, task: str):
        if self.read(task)["status"] != "provisioning":
            raise SandboxError("Start a fresh task with --provision first")
        self.guest(task, ["/bin/bash", "/Volumes/My Shared Files/input/prepare.sh"], timeout=7200)
        # Tart stops the virtual machine rather than shutting down its guest
        # OS. Flush the guest filesystem before recording durable preparation.
        self.guest(task, ["/bin/sync"], timeout=60)
        state = self.read(task)
        state["prepared"] = True
        self.save(task, state)
        self.stop(task)  # Every subsequent start is offline.

    def execute(self, task: str, argv: list[str], timeout: int):
        state = self.read(task)
        if state.get("network") != "offline" or not state.get("prepared"):
            raise SandboxError("Development commands require a prepared, offline task")
        if state.get("hydrated") is False:
            raise SandboxError("Fresh task hydration has not completed")
        if not argv:
            raise SandboxError("A guest command is required")
        script = "cd " + GUEST_ROOT + "/source && source " + GUEST_ROOT + "/development.env && exec " + shlex.join(argv)
        return self.guest(task, [*self.worker_prefix(state), "/bin/bash", "--noprofile", "--norc", "-c", script], timeout=timeout)

    @staticmethod
    def worker_prefix(state: dict) -> list[str]:
        worker = state.get("worker")
        if worker is None:
            if state.get("purpose") in {"development", "verification"}:
                raise SandboxError("Isolated task has no unprivileged worker")
            return []  # Manually prepared foundation tasks predate profiles.
        if worker != "mortimer-dev":
            raise SandboxError("Unexpected candidate worker identity")
        return ["/usr/bin/sudo", "-n", "-H", "-u", worker]

    def stop(self, task: str):
        state = self.read(task)
        if state.get("status") in {"running", "provisioning"}:
            # Preserve completed edits, test products and desktop settings.
            # A hung guest must still be stopped after this bounded grace.
            try:
                self.command("exec", state["vm"], "/bin/sync", timeout=5, capture_output=True)
                state["last_stop_flushed"] = True
            except (subprocess.SubprocessError, OSError):
                state["last_stop_flushed"] = False
        try:
            self.command("stop", state["vm"], timeout=60)
        except subprocess.CalledProcessError:
            # Tart returns an error for an already stopped VM. Reconcile only
            # after independently observing that exact local VM as stopped.
            result = self.command("list", "--source", "local", "--format", "json",
                                  capture_output=True, text=True, timeout=30)
            observed = [vm for vm in json.loads(result.stdout) if vm.get("Name") == state["vm"]]
            if len(observed) != 1 or observed[0].get("State") != "stopped":
                raise
        state["status"] = "stopped"
        self.save(task, state)

    def destroy(self, task: str):
        """Delete only a stopped disposable VM; retain its host evidence."""
        with (self.home / "start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.read(task)
            if state.get("vm") != "mortimer-" + task or state.get("status") not in {"created", "failed", "stopped", "deleting", "deleted"}:
                raise SandboxError("Only a stopped disposable task can be deleted")
            result = self.command("list", "--source", "local", "--format", "json",
                                  capture_output=True, text=True, timeout=30)
            matching = [vm for vm in json.loads(result.stdout) if vm.get("Name") == state["vm"]]
            if matching and (len(matching) != 1 or matching[0].get("State") != "stopped"):
                raise SandboxError("Task VM is still active; refusing deletion")
            state["status"] = "deleting"
            self.save(task, state)
            if matching:
                self.command("delete", state["vm"], timeout=120)
            state.update(status="deleted", deleted_at=int(time.time()))
            self.save(task, state)

    def cancel(self, task: str):
        """Serialize cancellation with VM start, including verification children."""
        with (self.home / "start.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.read(task)
            atomic_json(self.task_dir(task) / "cancelled.json", {"requested_at": int(time.time())})
            targets = [task]
            for path in (self.home / "tasks").glob("*/state.json"):
                state = json.loads(path.read_bytes())
                if state.get("parent_task") == task:
                    targets.append(path.parent.name)
            for target in targets:
                if self.read(target).get("status") in {"running", "provisioning"}:
                    self.stop(target)

    def export(self, task: str) -> Path:
        # Transfer a patch as data. Never unpack a guest-created archive on host.
        script = "cd " + GUEST_ROOT + "/source && git add -N . && git diff --binary HEAD"
        state = self.read(task)
        if state.get("status") != "running" or state.get("network") != "offline":
            raise SandboxError("Export requires an offline running task")
        process = subprocess.Popen([self.tart, "exec", state["vm"], *self.worker_prefix(state),
                                    "/bin/bash", "--noprofile", "--norc", "-c", script],
                                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        chunks, size, deadline = [], 0, time.monotonic() + 60
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise SandboxError("Export timed out")
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise SandboxError("Export size limit exceeded")
                    chunks.append(chunk)
            if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
                raise SandboxError("Guest patch export failed")
        except (SandboxError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
            self.stop(task)
            raise
        finally:
            process.stdout.close()
        data = b"".join(chunks)
        if SECRET.search(data):
            raise SandboxError("Export contains a potential credential")
        output = self.task_dir(task) / "candidate.patch"
        output.write_bytes(data)
        state = self.read(task)
        state["export_sha256"] = hashlib.sha256(data).hexdigest()
        self.save(task, state)
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home() / "Documents/Codex/MortimerSandbox")
    parser.add_argument("--tart", default=os.environ.get("MORTIMER_TART") or shutil.which("tart") or "tart")
    parser.add_argument("--softnet", default="/usr/local/libexec/mortimer-sandbox/softnet")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("doctor")
    create = sub.add_parser("create")
    create.add_argument("--repo", type=Path, required=True)
    create.add_argument("--ref", required=True)
    create.add_argument("--image", required=True)
    for verb in ["start", "prepare", "status", "stop", "destroy", "export", "exec"]:
        cmd = sub.add_parser(verb)
        cmd.add_argument("task")
        if verb == "start":
            cmd.add_argument("--provision", action="store_true")
            cmd.add_argument("--headless", action="store_true")
        if verb == "exec":
            cmd.add_argument("--timeout", type=int, default=1800)
            cmd.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    control = Controller(args.home, args.tart, args.softnet)
    if args.action == "doctor": print(json.dumps(control.doctor(), indent=2))
    elif args.action == "create": print(control.create(args.repo, args.ref, args.image))
    elif args.action == "start": control.start(args.task, args.provision, args.headless)
    elif args.action == "prepare": control.prepare(args.task)
    elif args.action == "status": print(json.dumps(control.read(args.task), indent=2))
    elif args.action == "stop": control.stop(args.task)
    elif args.action == "destroy": control.destroy(args.task)
    elif args.action == "export": print(control.export(args.task))
    elif args.action == "exec": control.execute(args.task, args.command, args.timeout)


if __name__ == "__main__":
    try:
        main()
    except (SandboxError, subprocess.CalledProcessError) as exc:
        print(f"Sandbox: {exc}", file=sys.stderr)
        raise SystemExit(1)
