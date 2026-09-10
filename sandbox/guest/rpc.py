#!/usr/bin/env python3
"""File operations inside the VM; invoked from the read-only host input share."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid

# Only shared, host-owned modules. Candidate source never joins sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import Candidate, File, MAX_FILE_BYTES, MAX_FILES, SandboxError, path_key, source_path_allowed

GENERATED_DIRS = {".git", ".venv", "node_modules", ".build", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".sandbox-data"}
GENERATED_PATHS = {"web/dist", "build", "dist", "data", "logs", "models"}


def parent_fd(root: Path, name: str, create: bool = False):
    path_key(name)
    if not source_path_allowed(name):
        raise SandboxError("Forbidden file path")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in name.split("/")[:-1]:
            if create:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_file(root: Path, name: str) -> File:
    parent = parent_fd(root, name)
    try:
        fd = os.open(name.split("/")[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE_BYTES:
                raise SandboxError("Unsupported file type or size")
            data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise SandboxError("File size limit exceeded")
            return File(name, 0o755 if info.st_mode & 0o111 else 0o644, data)
    finally:
        os.close(parent)


def write_file(root: Path, file: File) -> None:
    Candidate((file,))  # Apply file and content rules before creating anything.
    parent = parent_fd(root, file.path, create=True)
    temporary = ".mortimer-write-" + uuid.uuid4().hex
    try:
        destination = file.path.split("/")[-1]
        try:
            info = os.stat(destination, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise SandboxError("Cannot replace a link or special file")
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     file.mode, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            stream.write(file.data)
            stream.flush()
            os.fchmod(stream.fileno(), file.mode)
            os.fsync(stream.fileno())
        os.rename(temporary, destination, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def capture(root: Path, baseline_paths: list[str]) -> Candidate:
    # Scan independently of guest Git/index/.gitignore. Baseline files are
    # always considered, including tracked files in generated directories.
    baseline = set(baseline_paths)
    names = set(baseline)
    for name in baseline:
        if not source_path_allowed(name):
            raise SandboxError("Invalid baseline path")
    for directory, dirs, files in os.walk(root, followlinks=False):
        relative = Path(directory).relative_to(root)
        kept = []
        for child in dirs:
            name = (relative / child).as_posix()
            if (child.casefold() in GENERATED_DIRS or child.casefold().endswith(".egg-info")
                    or path_key(name) in GENERATED_PATHS):
                continue
            if (Path(directory) / child).is_symlink():
                raise SandboxError("Candidate contains a directory link")
            kept.append(child)
        dirs[:] = kept
        for child in files:
            name = (relative / child).as_posix()
            if source_path_allowed(name):
                names.add(name)
            elif not child.casefold().startswith(".env"):
                # Credentials and special private files cannot silently enter
                # a candidate. The generated fake .env is deliberately omitted.
                raise SandboxError("Candidate contains a forbidden file")
        if len(names) > MAX_FILES:
            raise SandboxError("Candidate file count limit exceeded")
    result = []
    for name in sorted(names):
        try:
            result.append(read_file(root, name))
        except FileNotFoundError:
            if name not in baseline:
                raise SandboxError("Candidate changed during capture") from None
    return Candidate(tuple(result))


def dispatch(root: Path, request: dict) -> bytes:
    if request.get("operation") == "read" and set(request) == {"operation", "path"}:
        return Candidate((read_file(root, request["path"]),)).encode()
    if request.get("operation") == "write" and set(request) == {"operation", "candidate"}:
        candidate = Candidate.decode(json.dumps(request["candidate"]).encode())
        if len(candidate.files) != 1:
            raise SandboxError("Write requires exactly one file")
        write_file(root, candidate.files[0])
        return candidate.encode()
    if request.get("operation") == "capture" and set(request) == {"operation", "baseline_paths"}:
        return capture(root, request["baseline_paths"]).encode()
    raise SandboxError("Unknown file operation")


def main():
    if subprocess.check_output(["/usr/sbin/sysctl", "-n", "kern.hv_vmm_present"], text=True).strip() != "1":
        raise SandboxError("File service must run inside a virtual machine")
    request = Path(sys.argv[1])
    if request.parent != Path(__file__).resolve().parent / "requests" or request.is_symlink():
        raise SandboxError("Request must come from the read-only input share")
    if request.stat().st_size > MAX_FILE_BYTES * 2:
        raise SandboxError("Request size limit exceeded")
    sys.stdout.buffer.write(dispatch(Path("/Users/admin/mortimer/source"), json.loads(request.read_bytes())))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No candidate content, request payload, or traceback in RPC errors.
        print("Sandbox file operation failed", file=sys.stderr)
        raise SystemExit(1)
