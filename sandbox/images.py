"""Prepared VM templates are cloned, never used as development workspaces."""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from sandbox.artifacts import Candidate, SandboxError
from sandbox.control import snapshot
from sandbox.durable import atomic_bytes, atomic_json
from sandbox.profiles import Profile

IMAGE_ID = re.compile(r"[0-9a-f]{64}\Z")


class Images:
    def __init__(self, controller):
        self.controller = controller
        self.root = controller.home / "images"
        self.root.mkdir(exist_ok=True, mode=0o700)

    def _stopped(self, name: str):
        result = self.controller.command("list", "--source", "local", "--format", "json",
                                         capture_output=True, text=True, timeout=30)
        matching = [vm for vm in json.loads(result.stdout) if vm.get("Name") == name]
        if len(matching) != 1 or matching[0].get("State") != "stopped":
            raise SandboxError("Prepared image must be stopped")

    def register(self, task: str, profile: Profile) -> str:
        """Accept only a newly provisioned VM that never entered development."""
        with (self.root / "images.lock").open("a") as lock, (self.controller.home / "start.lock").open("a") as start_lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            fcntl.flock(start_lock, fcntl.LOCK_EX)
            state = self.controller.read(task)
            if not state.get("prepared") or state.get("status") != "stopped" or state.get("network") != "provisioning":
                raise SandboxError("Only fresh stopped provisioning tasks can become prepared images")
            source = self.controller.task_dir(task) / "input" / "source.tar"
            if hashlib.sha256(source.read_bytes()).hexdigest() != state.get("source_sha256"):
                raise SandboxError("Prepared source archive does not match its record")
            baseline = Candidate.from_snapshot(source)
            dependencies = profile.dependency_key(baseline)
            recipe = self.controller.task_dir(task) / "input" / "prepare.sh"
            recipe_sha = hashlib.sha256(recipe.read_bytes()).hexdigest()
            identity = {"profile": profile.name, "dependencies": dependencies, "recipe": recipe_sha,
                        "source": state["source_commit"], "origin_image": state["image"]}
            image_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            directory = self.root / image_id
            directory.mkdir(exist_ok=True, mode=0o700)
            record_path = directory / "image.json"
            if record_path.exists():
                saved = json.loads(record_path.read_bytes())
                self._stopped(saved["vm"])
                return image_id
            self._stopped(state["vm"])
            name = "mortimer-image-" + image_id[:20]
            # A lost clone response is reconciled on retry by listing the
            # exact destination; never overwrite a pre-existing template.
            intent = directory / "intent.json"
            if intent.exists():
                result = self.controller.command("list", "--source", "local", "--format", "json",
                    capture_output=True, text=True, timeout=30)
                existing = [vm for vm in json.loads(result.stdout) if vm.get("Name") == name]
                if not existing:
                    self.controller.command("clone", state["vm"], name, timeout=600)
                self._stopped(name)
            else:
                atomic_json(intent, {"task": task, "vm": name, **identity})
                self.controller.command("clone", state["vm"], name, timeout=600)
                self._stopped(name)
            atomic_bytes(directory / "baseline.json", baseline.encode())
            atomic_json(record_path, {"id": image_id, "vm": name, **identity})
            return image_id

    def read(self, image_id: str, profile: Profile) -> dict:
        if not IMAGE_ID.fullmatch(image_id):
            raise SandboxError("Invalid prepared image identifier")
        state = json.loads((self.root / image_id / "image.json").read_bytes())
        if state.get("id") != image_id or state.get("profile") != profile.name:
            raise SandboxError("Prepared image does not match the requested profile")
        identity = {key: state.get(key) for key in ["profile", "dependencies", "recipe", "source", "origin_image"]}
        if (hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() != image_id
                or state.get("vm") != "mortimer-image-" + image_id[:20]):
            raise SandboxError("Prepared image record failed its integrity check")
        self._stopped(state["vm"])
        return state

    def create(self, image_id: str, repo: Path, ref: str, profile: Profile, *, purpose: str = "development",
               candidate: Candidate | None = None, task_id: str | None = None, parent_task: str | None = None) -> str:
        if purpose not in {"development", "verification"}:
            raise SandboxError("Invalid sandbox task purpose")
        image = self.read(image_id, profile)
        task = task_id or uuid.uuid4().hex[:12]
        if not re.fullmatch(r"[0-9a-f]{12}", task):
            raise SandboxError("Invalid allocated task identity")
        if parent_task is not None:
            self.controller.read(parent_task)
        directory = self.controller.home / "tasks" / task
        inputs = directory / "input"
        directory.mkdir(parents=True, mode=0o700)
        inputs.mkdir(mode=0o755)
        state = {"id": task, "vm": "mortimer-" + task, "image": image_id,
                 "purpose": purpose, "profile": profile.name, "status": "creating", "prepared": True,
                 "parent_task": parent_task}
        self.controller.save(task, state)
        try:
            state.update(snapshot(repo, ref, inputs / "source.tar"))
            baseline = Candidate.from_snapshot(inputs / "source.tar")
            selected = candidate if candidate is not None else baseline
            profile.validate_source(baseline)
            profile.validate_source(selected)
            if profile.dependency_key(selected) != image["dependencies"]:
                raise SandboxError("Dependencies changed; prepare a new image before developing this source")
            if profile.dependency_key(baseline) != image["dependencies"]:
                raise SandboxError("Source baseline does not match the prepared dependencies")
            atomic_bytes(inputs / "candidate.json", selected.encode())
            atomic_bytes(inputs / "baseline.json", baseline.encode())
            atomic_json(inputs / "hydrate.json", {"candidate": selected.fingerprint, "caches": profile.caches})
            root = Path(__file__).resolve().parent
            for name in ["artifacts.py", "guest/hydrate.py", "guest/worker.sh", "guest/static-web-check.mjs", "guest/desktop-probe.sh"]:
                atomic_bytes(inputs / Path(name).name, (root / name).read_bytes(),
                             mode=0o644 if name.endswith((".mjs", "desktop-probe.sh")) else 0o600)
            self.controller.install_file_service(task)
            self.controller.command("clone", image["vm"], state["vm"], timeout=600)
            self.controller.command("set", state["vm"], "--cpu", "4", "--memory", "8192", timeout=30)
            state.update(status="created", hydrated=False, candidate=selected.fingerprint,
                         profile_sha256=profile.fingerprint)
        except Exception:
            state["status"] = "failed"
            raise
        finally:
            self.controller.save(task, state)
        return task

    def hydrate(self, task: str):
        state = self.controller.read(task)
        if (state.get("status") != "running" or state.get("network") != "offline"
                or state.get("hydrated") is not False or state.get("hydration_started")):
            raise SandboxError("Hydration requires a fresh offline task")
        inputs = "/Volumes/My Shared Files/input"
        state["hydration_started"] = True
        self.controller.save(task, state)
        try:
            self.controller.guest(task, ["/bin/bash", inputs + "/worker.sh"], timeout=60)
            self.controller.guest(task, ["/usr/bin/sudo", "-n", "/opt/homebrew/opt/python@3.12/bin/python3.12",
                                        "-I", inputs + "/hydrate.py"], timeout=180)
            state = self.controller.read(task)
            state.update(hydrated=True, worker="mortimer-dev")
            self.controller.save(task, state)
            baseline = Candidate.from_snapshot(self.controller.task_dir(task) / "input" / "source.tar")
            observed = Candidate.decode(self.controller.rpc(task, {"operation": "capture",
                "baseline_paths": [file.path for file in baseline.files]}))
            if observed.fingerprint != state["candidate"]:
                raise SandboxError("Hydrated source does not match the frozen candidate")
        except Exception:
            self.controller.stop(task)
            state = self.controller.read(task)
            state.update(hydrated=False, hydration_failed=True)
            self.controller.save(task, state)
            raise
