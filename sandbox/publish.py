"""Host-only, resumable GitHub publication of an independently tested candidate.

No checkout, hooks, filters, shell commands, or guest Git configuration run on
the host. GitHub credentials exist only in the injected host API client.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
from urllib import error, parse, request

from sandbox.artifacts import SECRET, SandboxError
from sandbox.durable import atomic_json

SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
BRANCH = re.compile(r"mortimer/(?:selfedit|app-build)/[a-z0-9][a-z0-9/_-]{0,180}\Z")


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubAPI:
    def __init__(self, token: str):
        if not isinstance(token, str) or not token or any(char in token for char in "\r\n"):
            raise SandboxError("GitHub credentials are not configured on the host")
        self._token = token
        self._opener = request.build_opener(NoRedirect())

    def call(self, method: str, path: str, body=None, *, missing_ok: bool = False):
        if not path.startswith("/repos/") or any(char in path for char in "\r\n"):
            raise SandboxError("Invalid GitHub endpoint")
        payload = None if body is None else json.dumps(body, ensure_ascii=True).encode("ascii")
        headers = {"Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
                   "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "Mortimer-Sandbox-Publisher"}
        req = request.Request("https://api.github.com" + path, data=payload, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=30) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        except error.HTTPError as exc:
            if exc.code == 404 and missing_ok:
                return None
            raise SandboxError(f"GitHub publication failed (HTTP {exc.code}); retry resumes the saved operation") from None
        except (error.URLError, TimeoutError, OSError):
            raise SandboxError("GitHub response was unavailable; retry resumes the saved operation") from None
        if len(data) > 8 * 1024 * 1024:
            raise SandboxError("GitHub response exceeded its size limit")
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise SandboxError("Invalid GitHub response") from None


def object_sha(value) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise SandboxError("GitHub returned an invalid object identifier")
    return value


class Publisher:
    def __init__(self, api):
        self.api = api

    def publish(self, files, verifier, image_id: str, profile, *, repository: str,
                branch: str, base_branch: str, title: str, body: str) -> dict:
        if not REPOSITORY.fullmatch(repository) or not BRANCH.fullmatch(branch) or "//" in branch or branch.endswith("/"):
            raise SandboxError("Invalid publication repository or task branch")
        if (not isinstance(base_branch, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/_.-]{0,180}", base_branch)
                or ".." in base_branch or "//" in base_branch or base_branch.endswith(("/", ".", ".lock")) or branch == base_branch):
            raise SandboxError("Invalid pull-request base branch")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120 or not isinstance(body, str) or len(body) > 50000:
            raise SandboxError("Invalid pull-request title or description")
        if SECRET.search((title + "\n" + body).encode("utf-8")):
            raise SandboxError("Publication description contains a potential credential")
        def call(*args, **kwargs):
            if (files.directory / "cancelled.json").exists():
                raise SandboxError("Publication was cancelled; saved remote object records are retained")
            return self.api.call(*args, **kwargs)

        # The publisher can only consume a successful host receipt. A fresh
        # guest capture additionally detects edits made outside the edit API.
        receipt = verifier.receipt(files, image_id, profile)
        candidate = files.frozen()
        files.assert_unchanged(candidate.fingerprint)
        changed = candidate.changes(files.baseline, files.allowed)
        if not changed:
            raise SandboxError("There are no candidate changes to publish")
        parent = object_sha(receipt["source_commit"])
        expected = {"repository": repository, "branch": branch, "base": base_branch,
                    "candidate": candidate.fingerprint, "parent": parent, "title": title, "body": body}
        path = files.directory / "publication.json"
        with (files.directory / "publication.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.exists():
                state = json.loads(path.read_bytes())
                if any(state.get(key) != value for key, value in expected.items()):
                    raise SandboxError("An earlier publication has different inputs; resume that operation first")
            else:
                state = {"version": 1, **expected, "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "blobs": {}, "status": "starting"}
                with files._locked():
                    journal = files._journal()
                    verification = journal.get("verification") or {}
                    if (journal.get("candidate") != candidate.fingerprint or verification.get("attempt") != receipt["attempt"]
                            or verification.get("passed") is not True):
                        raise SandboxError("Candidate changed before publication could start")
                    atomic_json(path, state)
            prefix = "/repos/" + repository
            if not state.get("tree"):
                base = call("GET", prefix + "/git/commits/" + parent)
                if object_sha(base.get("sha")) != parent:
                    raise SandboxError("GitHub returned a different base commit")
                base_tree = object_sha(base["tree"]["sha"])
                before = {file.path: file for file in files.baseline.files}
                after = {file.path: file for file in candidate.files}
                entries = []
                for name in changed:
                    file = after.get(name)
                    if file is None:
                        entries.append({"path": name, "mode": "100755" if before[name].mode == 0o755 else "100644",
                                        "type": "blob", "sha": None})
                        continue
                    blob_sha = hashlib.sha1(b"blob " + str(len(file.data)).encode() + b"\0" + file.data).hexdigest()
                    if state["blobs"].get(name) != blob_sha:
                        blob = call("POST", prefix + "/git/blobs", {"encoding": "base64",
                            "content": base64.b64encode(file.data).decode("ascii")})
                        if object_sha(blob.get("sha")) != blob_sha:
                            raise SandboxError("GitHub blob does not match the candidate content")
                        state["blobs"][name] = blob_sha
                        atomic_json(path, state)
                    entries.append({"path": name, "mode": "100755" if file.mode == 0o755 else "100644",
                                    "type": "blob", "sha": blob_sha})
                tree = call("POST", prefix + "/git/trees", {"base_tree": base_tree, "tree": entries})
                state.update(tree=object_sha(tree.get("sha")), status="tree_created")
                atomic_json(path, state)
            if not state.get("commit"):
                # Persisted date and fixed author make retries submit the
                # same immutable Git object after a lost create response.
                identity = {"name": "Mortimer Sandbox", "email": "sandbox@example.invalid", "date": state["date"]}
                commit = call("POST", prefix + "/git/commits", {"message": title,
                    "tree": state["tree"], "parents": [parent], "author": identity, "committer": identity})
                state.update(commit=object_sha(commit.get("sha")), status="commit_created")
                atomic_json(path, state)
            ref_path = prefix + "/git/ref/heads/" + parse.quote(branch, safe="")
            remote = call("GET", ref_path, missing_ok=True)
            if remote is None:
                remote = call("POST", prefix + "/git/refs", {"ref": "refs/heads/" + branch, "sha": state["commit"]})
            if remote.get("ref") != "refs/heads/" + branch or object_sha(remote["object"]["sha"]) != state["commit"]:
                raise SandboxError("Task branch already points to different code; refusing to overwrite it")
            state["status"] = "branch_created"
            atomic_json(path, state)
            owner = repository.split("/")[0]
            query = parse.urlencode({"state": "all", "head": owner + ":" + branch, "per_page": 100})
            pulls = call("GET", prefix + "/pulls?" + query)
            if not isinstance(pulls, list) or len(pulls) >= 100:
                raise SandboxError("Cannot safely resolve an existing pull request")
            matching = [pr for pr in pulls if pr.get("head", {}).get("ref") == branch
                        and pr.get("head", {}).get("repo", {}).get("full_name", "").casefold() == repository.casefold()]
            if len(matching) > 1:
                raise SandboxError("Multiple pull requests exist for this task branch")
            if matching:
                pr = matching[0]
                if pr.get("base", {}).get("ref") != base_branch or pr.get("head", {}).get("sha") != state["commit"]:
                    raise SandboxError("Existing pull request no longer matches this publication")
            else:
                pr = call("POST", prefix + "/pulls", {"head": branch, "base": base_branch,
                    "title": title, "body": body, "draft": True})
            number = pr.get("number")
            if type(number) is not int or number < 1:
                raise SandboxError("GitHub returned an invalid pull-request number")
            state.update(status="published", number=number, url=f"https://github.com/{repository}/pull/{number}")
            atomic_json(path, state)
            return {"ok": True, "number": number, "url": state["url"], "commit": state["commit"],
                    "candidate": candidate.fingerprint, "state": pr.get("state", "open")}
