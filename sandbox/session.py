"""Persistent, serialized workspace sessions shared by self-edit and app builds."""
from __future__ import annotations

import difflib
import fcntl
import json
from pathlib import Path
import re
import time
import uuid

from sandbox.artifacts import SandboxError
from sandbox.durable import atomic_json
from sandbox.files import WorkspaceFiles

SESSION_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_EDITOR_BYTES = 256 * 1024


class Session:
    def __init__(self, controller, images, verifier, profile, allowed, session_id: str):
        if not SESSION_ID.fullmatch(session_id):
            raise SandboxError("Invalid development session")
        self.controller, self.images, self.verifier = controller, images, verifier
        self.profile, self.allowed, self.id = profile, allowed, session_id
        self.directory = controller.home / "sessions" / session_id
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise SandboxError("Unknown development session")

    def _locked(self):
        lock = (self.directory / "session.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX)
        return lock

    def _read(self):
        return json.loads((self.directory / "session.json").read_bytes())

    def _save(self, state):
        state["updated_at"] = int(time.time())
        atomic_json(self.directory / "session.json", state)

    def _has_task(self, state):
        return bool(state.get("task") and (self.controller.home / "tasks" / state["task"] / "state.json").is_file())

    @classmethod
    def create(cls, controller, images, verifier, profile, allowed, *, image_id: str, repo: Path,
               ref: str, repository: str, base_branch: str, kind: str, goal: str, run_id: str | None = None,
               on_created=None):
        if kind not in {"selfedit", "app-build"} or not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
            raise SandboxError("Invalid development goal or workspace type")
        identifier = uuid.uuid4().hex
        directory = controller.home / "sessions" / identifier
        directory.mkdir(parents=True, mode=0o700)
        slug = re.sub(r"[^a-z0-9]+", "-", goal.casefold()).strip("-")[:50] or "update"
        state = {"id": identifier, "version": 1, "kind": kind, "repository": repository,
                 "base_branch": base_branch, "repo": str(repo.resolve()), "ref": ref, "image": image_id,
                 "profile": profile.name, "goal": goal.strip(), "run_id": run_id, "task": uuid.uuid4().hex[:12],
                 "branch": "mortimer/" + kind + "/" + time.strftime("%Y%m%d") + "-" + slug + "-" + identifier[:12],
                 "phase": "creating", "proposals": [], "checks": []}
        atomic_json(directory / "session.json", state)
        session = cls(controller, images, verifier, profile, allowed, identifier)
        try:
            if on_created is not None:
                on_created(session)
            task = images.create(image_id, repo, ref, profile, purpose="development", task_id=state["task"])
            state.update(task=task, phase="starting")
            session._save(state)
            with session._locked():
                session._ensure_running(state)
            state["phase"] = "editing"
            session._save(state)
        except Exception:
            state["phase"] = "setup_failed"
            session._save(state)
            if (controller.home / "tasks" / state["task"] / "state.json").exists() and controller.read(state["task"]).get("status") in {"running", "provisioning"}:
                controller.stop(state["task"])
            raise
        return session

    def _ensure_running(self, state):
        task = state.get("task")
        if not task or state.get("phase") in {"reverted", "setup_failed"} or (self.directory / "cancelled.json").exists():
            raise SandboxError("Development session is not available")
        vm = self.controller.read(task)
        if not self.controller.ready(task):
            vm = self.controller.reconcile(task)
        if vm.get("status") in {"created", "stopped"}:
            self.controller.start(task, provisioning=False, headless=True)
            self.verifier.wait_ready(task)
        elif vm.get("status") != "running":
            raise SandboxError("Development task cannot be resumed")
        elif not self.controller.ready(task):
            self.verifier.wait_ready(task)
        if not self.controller.read(task).get("hydrated"):
            self.images.hydrate(task)
        if (self.directory / "cancelled.json").exists():
            self.controller.cancel(task)
            raise SandboxError("Development session has been cancelled")
        self.controller.mark_ready(task)

    def resume(self) -> dict:
        with self._locked():
            state = self._read()
            if state.get("phase") in {"published", "reverted", "cancelled", "setup_failed"}:
                raise SandboxError("This development session has ended.")
            # An active verifier owns the session lock. Reaching this phase
            # with the lock free means that its host process was interrupted.
            if state.get("phase") == "validating":
                for path in (self.controller.home / "tasks").glob("*/state.json"):
                    child = json.loads(path.read_bytes())
                    if child.get("parent_task") == state["task"] and child.get("purpose") == "verification":
                        if child.get("status") not in {"deleted", "deleting"}:
                            self.controller.cancel(path.parent.name)
                files = self._files(state)
                with files._locked():
                    journal = files._journal()
                    journal["verification"] = None
                    files._save(journal)
                state.update(phase="validation_failed", checks=[],
                    recovery_notice="Verification was interrupted; run validation again before publication.")
                self._save(state)
            self._ensure_running(state)
            if state.get("phase") in {"creating", "starting"}:
                state["phase"] = "editing"
                self._save(state)
            elif state.get("phase") == "publishing":
                state["phase"] = "publication_pending"
                self._save(state)
            return {"ok": True, "session_id": self.id, "sandbox_task": state["task"], "ready": True}

    def _files(self, state):
        return WorkspaceFiles(self.controller, state["task"], self.allowed)

    def _editing(self, state):
        if (self.controller.task_dir(state["task"]) / "publication.json").exists():
            raise SandboxError("Publication has started; retry submission or start a new session before editing")
        self._ensure_running(state)

    def read_file(self, path: str) -> dict:
        with self._locked():
            state = self._read()
            self._ensure_running(state)
            file = self._files(state).read(path)
            if len(file.data) > MAX_EDITOR_BYTES:
                raise SandboxError("File is too large for the text editor")
            try:
                content = file.data.decode("utf-8")
            except UnicodeError:
                raise SandboxError("File is binary; use the artifact workflow") from None
            return {"ok": True, "path": path, "content": content}

    def propose_edit(self, path: str, content: str, rationale: str, visual_intent: str = "") -> dict:
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_EDITOR_BYTES:
            raise SandboxError("Edit is too large for the text editor")
        with self._locked():
            state = self._read()
            self._editing(state)
            files = self._files(state)
            baseline = next((file for file in files.baseline.files if file.path == path), None)
            mode = baseline.mode if baseline else 0o644
            files.write(path, content.encode(), rationale, mode)
            previous = baseline.data.decode("utf-8", errors="replace") if baseline else ""
            diff = "".join(difflib.unified_diff(previous.splitlines(keepends=True), content.splitlines(keepends=True),
                                             fromfile="a/" + path, tofile="b/" + path))
            proposal = {"path": path, "rationale": rationale, "diff": diff, "visual_intent": visual_intent}
            state["proposals"] = [item for item in state["proposals"] if item["path"] != path] + [proposal]
            state.update(checks=[], phase="editing")
            self._save(state)
            return {"ok": True, "path": path, "diff": diff}

    def validate(self) -> dict:
        with self._locked():
            state = self._read()
            self._editing(state)
            state.update(phase="validating", checks=[])
            self._save(state)
            try:
                receipt = self.verifier.verify(self._files(state), Path(state["repo"]), state["image"], self.profile)
                checks = [{"name": check["name"], "ok": check["passed"], "returncode": check["returncode"],
                           "seconds": check["seconds"], "output": "See the saved sandbox check log."}
                          for check in receipt["checks"]]
                state.update(phase="validated" if receipt["passed"] else "validation_failed", checks=checks,
                             candidate=receipt["candidate"], verification_attempt=receipt["attempt"])
                self._save(state)
                return {"ok": receipt["passed"], "checks": checks, "candidate": receipt["candidate"],
                        "sandbox_task": state["task"], "verification_task": receipt["verification_task"]}
            except Exception:
                state["phase"] = "validation_failed"
                self._save(state)
                raise

    def submit(self, publisher, title: str, body: str) -> dict:
        with self._locked():
            state = self._read()
            self._ensure_running(state)
            state["phase"] = "publishing"
            self._save(state)
            try:
                result = publisher.publish(self._files(state), self.verifier, state["image"], self.profile,
                    repository=state["repository"], branch=state["branch"], base_branch=state["base_branch"], title=title, body=body)
                state.update(phase="published", publication=result)
                self._save(state)
                self.controller.stop(state["task"])
                return result
            except Exception:
                state["phase"] = "publication_pending"
                self._save(state)
                raise

    def revert(self) -> dict:
        with self._locked():
            state = self._read()
            if self._has_task(state) and self.controller.read(state["task"]).get("status") != "deleted":
                if self.controller.read(state["task"]).get("status") in {"running", "provisioning"}:
                    self.controller.stop(state["task"])
                self.controller.destroy(state["task"])
            state["phase"] = "reverted"
            self._save(state)
            return {"ok": True, "branch": state["branch"], "sandbox_task": state.get("task"),
                    "message": "Disposable workspace removed; saved review evidence retained."}

    def cancel(self) -> dict:
        # Do not wait behind the long validation/submission mutation lock.
        state = self._read()
        atomic_json(self.directory / "cancelled.json", {"requested_at": int(time.time())})
        if state.get("task"):
            if not (self.controller.home / "tasks" / state["task"] / "state.json").exists():
                return {"ok": True, "cancelled": True, "sandbox_task": state["task"]}
            self.controller.cancel(state["task"])
            if (self.controller.task_dir(state["task"]) / "files.json").exists():
                files = self._files(state)
                with files._locked():
                    journal = files._journal()
                    journal.update(candidate=None, verification=None, revision=journal["revision"] + 1)
                    files._save(journal)
        return {"ok": True, "cancelled": True, "sandbox_task": state.get("task")}

    def status(self) -> dict:
        # Atomic records are safe to read while a long validation holds the
        # mutation lock; UI status must not block behind the test suite.
        state = self._read()
        if (self.directory / "cancelled.json").exists():
            state["phase"] = "cancelled"
        vm = self.controller.read(state["task"]) if self._has_task(state) else {}
        return {**state, "sandbox_task": state.get("task"), "vm_status": vm.get("status"),
                "ready": self.controller.ready(state["task"]) if self._has_task(state) else False,
                "boundary": "Candidate files and commands run inside a disposable offline VM."}
