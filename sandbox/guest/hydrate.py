#!/usr/bin/env python3
"""Replace source/state in a fresh VM clone while retaining installed tools."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import Candidate, SandboxError, check_paths

CACHES = {".venv", "services/mortimer-vault/.venv", "web/node_modules",
          "macos/JarvisKit/.build", "macos/MortimerHost/.build"}
PROTECTED = {".venv": "python", "services/mortimer-vault/.venv": "knowledge-python", "web/node_modules": "web/node_modules"}
TEST_ROOTS = ("tests/", "services/mortimer-vault/tests/", "macos/JarvisKit/Tests/", "macos/MortimerHost/Tests/")


def ownership(path: Path, uid: int, gid: int):
    for directory, dirs, files in os.walk(path, followlinks=False):
        os.chown(directory, uid, gid)
        for name in files:
            os.chown(Path(directory) / name, uid, gid, follow_symlinks=False)


def verification_tree(root: Path, baseline: Candidate, candidate: Candidate, caches: list[str]):
    """Materialize an independent baseline source tree for baseline checks.

    Baseline checks must execute the baseline application and tests. Linking
    non-test files to the candidate made intentional contract changes appear
    as baseline regressions. Candidate checks run separately in ``source``.
    """
    checks = root / "verification"
    checks.mkdir()
    before = {file.path: file for file in baseline.files}
    after = {file.path: file for file in candidate.files}
    names = set(before)
    check_paths(names)
    for name in sorted(names):
        destination = checks / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(before[name].data)
        destination.chmod(before[name].mode)
    for name in caches:
        destination = checks / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = root / "dependencies" / PROTECTED[name] if name in PROTECTED else root / "source" / name
        if name.endswith("/.build"):
            swift_dependencies(root, target, destination)
        else:
            destination.symlink_to(target, target_is_directory=True)


def swift_dependencies(root: Path, source: Path, destination: Path):
    # Compiler products embed absolute module-cache paths. Sharing those
    # products across candidate and baseline roots causes duplicate modules
    # and can accidentally reuse candidate test binaries. Copy only resolved
    # dependency inputs; each test tree gets an independent clean build.
    destination.mkdir()
    for name in ["artifacts", "checkouts", "repositories"]:
        shutil.copytree(source / name, destination / name, symlinks=True)
    state = (source / "workspace-state.json").read_text()
    state = state.replace(str(root / "source"), str(root / "verification"))
    (destination / "workspace-state.json").write_text(state)
    owner = source.stat()
    ownership(destination, owner.st_uid, owner.st_gid)


def hydrate(root: Path, candidate: Candidate, caches: list[str], worker_uid: int, worker_gid: int):
    source = root / "source"
    if source.is_symlink() or not source.is_dir() or not set(caches) <= CACHES or len(caches) != len(set(caches)):
        raise SandboxError("Invalid fresh-image layout")
    holding = root / "hydration-cache"
    holding.mkdir()  # An interrupted hydration must be discarded, never reused.
    preserved = []
    for index, name in enumerate(caches):
        cache = source / name
        if cache.is_symlink() or not cache.is_dir():
            raise SandboxError("Prepared dependency cache is missing")
        destination = holding / str(index)
        cache.rename(destination)
        preserved.append((name, destination))
    shutil.rmtree(source)
    source.mkdir()
    for file in candidate.files:
        destination = source / file.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(file.data)
        destination.chmod(file.mode)
    ownership(source, worker_uid, worker_gid)
    dependencies = root / "dependencies"
    dependencies.mkdir()
    for name, cache in preserved:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise SandboxError("Candidate overlaps a prepared dependency cache")
        if name.endswith("/.build"):
            cache.rename(destination)
            ownership(destination, worker_uid, worker_gid)
        else:
            installed = dependencies / PROTECTED[name]
            installed.parent.mkdir(parents=True, exist_ok=True)
            cache.rename(installed)
            destination.symlink_to(installed, target_is_directory=True)
            # Keep installed interpreters and packages owned by the image's
            # admin, with no group/other write permission for candidate code.
            # Required checks use these protected paths, not replaceable links
            # beneath the candidate's writable source directory.
            for directory, dirs, files in os.walk(installed, followlinks=False):
                os.chmod(directory, os.stat(directory).st_mode & ~0o022)
                for child in files:
                    item = Path(directory) / child
                    if not item.is_symlink():
                        os.chmod(item, item.stat().st_mode & ~0o022)
            if name == "web/node_modules":
                # TypeScript and Vite need build caches, while installed
                # package code stays protected. Preserve the node_modules
                # directory name so Node/TypeScript can resolve sibling deps.
                for cache_name in [".tmp", ".vite", ".vite-temp"]:
                    writable = installed / cache_name
                    if writable.is_symlink():
                        raise SandboxError("Unexpected build cache link")
                    writable.mkdir(exist_ok=True)
                    os.chown(writable, worker_uid, worker_gid)
    holding.rmdir()
    for name in ["state", "logs", "reports"]:
        path = root / name
        if path.is_symlink():
            raise SandboxError("Unexpected state directory link")
        if path.exists():
            shutil.rmtree(path)
        path.mkdir()
        os.chown(path, worker_uid, worker_gid)
    environment = root / "development.env"
    with environment.open("a") as stream:
        stream.write("\nexport HOME=/Users/mortimer-dev\n")
        stream.write("export PLAYWRIGHT_BROWSERS_PATH=/Users/admin/mortimer/browser-engines\n")
    shutil.copyfile(environment, source / ".env")
    os.chown(source / ".env", worker_uid, worker_gid)


def main():
    if subprocess.check_output(["/usr/sbin/sysctl", "-n", "kern.hv_vmm_present"], text=True).strip() != "1" or os.geteuid() != 0:
        raise SandboxError("Hydration requires the privileged VM controller")
    inputs = Path(__file__).resolve().parent
    settings = json.loads((inputs / "hydrate.json").read_bytes())
    candidate = Candidate.decode((inputs / "candidate.json").read_bytes())
    baseline = Candidate.decode((inputs / "baseline.json").read_bytes())
    if settings.get("candidate") != candidate.fingerprint:
        raise SandboxError("Hydration candidate does not match the host record")
    worker = pwd.getpwnam("mortimer-dev")
    if worker.pw_uid != 502 or worker.pw_gid != 20:
        raise SandboxError("Unexpected worker identity")
    hydrate(Path("/Users/admin/mortimer"), candidate, settings["caches"], worker.pw_uid, worker.pw_gid)
    verification_tree(Path("/Users/admin/mortimer"), baseline, candidate, settings["caches"])
    root = "/Users/admin/mortimer/source"
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/Users/mortimer-dev",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    for command in [["init", "-q"], ["add", "."], ["commit", "-qm", "Imported frozen candidate"]]:
        subprocess.run(["/usr/bin/sudo", "-n", "-u", "mortimer-dev", "/usr/bin/git", "-C", root,
            "-c", "core.hooksPath=/dev/null", "-c", "user.name=Mortimer Sandbox",
            "-c", "user.email=sandbox@example.invalid", *command], check=True, env=env, timeout=60)
    subprocess.run(["/bin/sync"], check=True, timeout=30)
    print(json.dumps({"candidate": candidate.fingerprint, "worker": "mortimer-dev"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Sandbox hydration failed; discard this task", file=sys.stderr)
        raise SystemExit(1)
