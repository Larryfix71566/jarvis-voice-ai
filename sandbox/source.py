"""Fetch committed GitHub source into a host-only bare object store."""
from __future__ import annotations

import base64
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess

from sandbox.artifacts import MAX_FILES, MAX_FILE_BYTES, MAX_SOURCE_BYTES, SandboxError
from sandbox.publish import GitHubAPI, REPOSITORY, object_sha
from urllib.parse import quote


class GitSource:
    def __init__(self, home: Path):
        self.root = home / "repositories"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def fetch(self, repository: str, branch: str, token: str) -> tuple[Path, str]:
        if not REPOSITORY.fullmatch(repository):
            raise SandboxError("Invalid source repository")
        if (not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,180}", branch)
                or ".." in branch or "//" in branch or branch.endswith(("/", ".", ".lock"))
                or any(part.startswith(".") for part in branch.split("/"))):
            raise SandboxError("Invalid source branch")
        if not isinstance(token, str) or not token or any(char in token for char in "\r\n"):
            raise SandboxError("GitHub credentials are not configured on the host")
        # Bound the current tree before downloading Git objects. A shallow,
        # pinned fetch avoids downloading unbounded repository history or a
        # different branch revision after the size check.
        api = GitHubAPI(token)
        prefix = "/repos/" + repository
        remote = api.call("GET", prefix + "/git/ref/heads/" + quote(branch, safe=""))
        expected = object_sha(remote["object"]["sha"])
        commit = api.call("GET", prefix + "/git/commits/" + expected)
        if object_sha(commit.get("sha")) != expected:
            raise SandboxError("Source metadata returned a different commit")
        tree = api.call("GET", prefix + "/git/trees/" + object_sha(commit["tree"]["sha"]) + "?recursive=1")
        entries = tree.get("tree")
        if tree.get("truncated") or not isinstance(entries, list) or len(entries) > MAX_FILES * 2:
            raise SandboxError("Source tree exceeds the checkout metadata limit")
        total, count = 0, 0
        for entry in entries:
            if entry.get("type") == "tree":
                continue
            size = entry.get("size")
            if entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
                raise SandboxError("Source contains unsupported links or submodules")
            if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
                raise SandboxError("Source file exceeds the checkout size limit")
            total, count = total + size, count + 1
            if total > MAX_SOURCE_BYTES or count > MAX_FILES:
                raise SandboxError("Source exceeds the checkout size limit")
        key = hashlib.sha256(repository.casefold().encode()).hexdigest()
        directory = self.root / (key + ".git")
        # No global Git configuration, hooks, candidate executable, or working
        # directory is involved. The temporary credential header is confined
        # to the host Git child environment, never its argv or saved config.
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        with (self.root / (key + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not directory.exists():
                directory.mkdir(mode=0o700)
            elif directory.is_symlink() or not directory.is_dir():
                raise SandboxError("Invalid source cache directory")
            # Reinitialization preserves bare objects and repairs a crash
            # after mkdir but before the first init completed.
            self._run(["/usr/bin/git", "init", "--bare", "--template=", str(directory)], env, 30)
            auth = base64.b64encode(("x-access-token:" + token).encode()).decode("ascii")
            fetch_env = {**env, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                         "GIT_CONFIG_VALUE_0": "Authorization: Basic " + auth}
            ref = "refs/remotes/origin/" + branch
            self._run(["/usr/bin/git", "-C", str(directory), "-c", "core.hooksPath=/dev/null",
                       "-c", "credential.helper=", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                       "-c", "http.followRedirects=false", "fetch", "--quiet", "--depth=1", "--no-tags", "--no-recurse-submodules",
                       "https://github.com/" + repository + ".git", "+" + expected + ":" + ref], fetch_env, 300)
            output = self._run(["/usr/bin/git", "-C", str(directory), "rev-parse", "--verify", ref + "^{commit}"], env, 30)
            sha = output.strip()
            if sha != expected:
                raise SandboxError("Source fetch did not return a committed revision")
            return directory, sha

    @staticmethod
    def _run(argv: list[str], env: dict, timeout: int) -> str:
        try:
            result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise SandboxError("Committed source fetch was interrupted") from None
        if result.returncode:
            # Error output can contain details supplied by remote services;
            # never expose a credential-bearing child environment or traceback.
            raise SandboxError("Committed source fetch failed; check host GitHub access")
        return result.stdout
