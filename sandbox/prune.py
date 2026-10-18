#!/usr/bin/env python3
"""Reclaim disposable sandbox VMs the host no longer needs. Standard library only.

Every development and verification task owns one Tart clone under TART_HOME.
Host evidence (task records, edit journals, verification receipts and check
logs) is kept forever; only the clone is removed, and only through
``Controller.destroy``, which refuses anything Tart still reports as active.
Templates (``mortimer-base``, ``mortimer-image-*``) are not task VMs and are
never candidates.

Rules, applied in order to every task record:

1. Nothing recorded as running or provisioning is touched. Records already
   ``deleted`` have no VM.
2. A record changed within ``GRACE_SECONDS`` is left alone, so a task between
   creation and first start is never raced.
3. A verification VM is disposable as soon as it has stopped. Its receipt and
   logs live on the host; ``Verifier.receipt`` never consults the VM.
4. A development VM is never touched while one of its verification children
   is being created, is running, or changed within the grace period: a long
   validation stops the parent first and must find it again afterwards.
5. A development VM is disposable once its session has ended (published,
   reverted, cancelled, setup failed).
6. A development VM that no session owns (acceptance campaigns and pilots
   drive Images and Verifier directly) is disposable after
   ``ORPHAN_SECONDS`` with no change to it or to any child.
7. A development VM whose session is still open is disposable after
   ``IDLE_SECONDS`` without session activity. Resuming afterwards fails
   closed ("VM missing; cancel it and start a new session"); the edit
   journal stays on the host.
8. When free space on the sandbox volume is below ``LOW_DISK_BYTES``, rule 6
   waits only the grace period and rule 7 uses ``LOW_DISK_IDLE_SECONDS``.
9. Legacy records without a purpose (manual provisioning tasks) follow rule 7
   using the record's own modification time.

``Images.create`` runs a pass before cloning and refuses to clone when less
than ``MIN_FREE_BYTES`` remain afterwards. ``Verifier.verify`` and
``Session.submit`` discard their own VMs as soon as they are finished with
them. The ``com.mortimer.sandbox-prune`` launchd job runs this module daily
for anything those paths missed (host restarts, abandoned sessions).
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import fcntl
import json
import math
import re
import os
from pathlib import Path
import shutil
import sys
import time

try:
    from sandbox.artifacts import SandboxError
    from sandbox.control import Controller, TASK_ID
except ModuleNotFoundError:  # Direct script invocation.
    from artifacts import SandboxError
    from control import Controller, TASK_ID

GIB = 1024 ** 3
GRACE_SECONDS = 60 * 60
ORPHAN_SECONDS = 6 * 60 * 60
IDLE_SECONDS = 7 * 24 * 60 * 60
LOW_DISK_BYTES = 100 * GIB
LOW_DISK_IDLE_SECONDS = 24 * 60 * 60
MIN_FREE_BYTES = 8 * GIB
ENDED_PHASES = frozenset({"published", "reverted", "cancelled", "setup_failed"})
# Controller.destroy accepts exactly these; "deleting" finishes an interrupted delete.
DISPOSABLE = frozenset({"created", "failed", "stopped", "deleting"})


def free_bytes(home: Path) -> int:
    return shutil.disk_usage(home).free


class Pruner:
    def __init__(self, controller, *, grace: int = GRACE_SECONDS, orphan: int = ORPHAN_SECONDS,
                 idle: int = IDLE_SECONDS, low_disk: int = LOW_DISK_BYTES, low_disk_idle: int = LOW_DISK_IDLE_SECONDS):
        self.controller = controller
        self.grace, self.orphan, self.idle = grace, orphan, idle
        self.low_disk, self.low_disk_idle = low_disk, low_disk_idle

    def _sessions(self):
        owners, issues, duplicates = {}, [], set()
        for path in sorted((self.controller.home / "sessions").glob("*/session.json")):
            category = None
            try:
                if path.is_symlink() or path.parent.is_symlink():
                    category = "session_symlink"
                else:
                    record = json.loads(path.read_bytes())
                    if (not isinstance(record, dict) or not isinstance(record.get("task"), str)
                            or not TASK_ID.fullmatch(record["task"])
                            or record.get("id") != path.parent.name
                            or not isinstance(record.get("id"), str)
                            or not re.fullmatch(r"[0-9a-f]{32}", record["id"])
                            or not isinstance(record.get("phase"), str)):
                        category = "session_identity_or_shape"
                    else:
                        updated = record.get("updated_at")
                        if updated is not None and (isinstance(updated, bool) or not math.isfinite(float(updated))):
                            category = "session_timestamp"
                        else:
                            task = record["task"]
                            if task in owners:
                                duplicates.add(task)
                            record["ended"] = (record["phase"] in ENDED_PHASES
                                               or (path.parent / "cancelled.json").exists())
                            owners[task] = record
            except (OSError, ValueError, TypeError, RecursionError):
                category = "session_unreadable_or_invalid"
            if category:
                issues.append({"record": "sessions/" + path.parent.name + "/session.json", "category": category})
        return owners, issues, duplicates

    def sessions(self) -> dict:
        """Known development owners only; unknown relationships are not grants."""
        return self._sessions()[0]

    def low_disk_mode(self) -> bool:
        return free_bytes(self.controller.home) < self.low_disk

    def _records(self):
        records, issues = {}, []
        statuses = {"creating", "created", "running", "provisioning", "stopped", "failed", "deleting", "deleted", "missing"}
        for path in sorted((self.controller.home / "tasks").glob("*/state.json")):
            task = path.parent.name
            if not TASK_ID.fullmatch(task):
                continue
            category = None
            try:
                if path.is_symlink() or path.parent.is_symlink():
                    category = "task_symlink"
                else:
                    state = json.loads(path.read_bytes())
                    if (not isinstance(state, dict) or state.get("vm") != "mortimer-" + task
                            or state.get("id", task) != task
                            or not isinstance(state.get("status"), str) or state["status"] not in statuses
                            or state.get("purpose") not in {None, "development", "verification"}
                            or (state.get("parent_task") is not None and
                                (not isinstance(state["parent_task"], str) or not TASK_ID.fullmatch(state["parent_task"])))):
                        category = "task_identity_or_shape"
                    else:
                        records[task] = (state, path.stat().st_mtime)
            except (OSError, ValueError, TypeError, RecursionError):
                category = "task_unreadable_or_invalid"
            if category:
                issues.append({"record": "tasks/" + task + "/state.json", "category": category})
        return records, issues

    def records(self) -> dict:
        return self._records()[0]

    def plan(self, now: float | None = None) -> list:
        now = time.time() if now is None else now
        low = self.low_disk_mode()
        orphan_limit = self.grace if low else self.orphan
        idle_limit = self.low_disk_idle if low else self.idle
        owners, session_issues, duplicates = self._sessions()
        records, task_issues = self._records()
        self._issues = session_issues + task_issues
        self._retained = []
        children = {}
        for task, (state, changed) in records.items():
            parent = state.get("parent_task")
            if isinstance(parent, str):
                children.setdefault(parent, []).append((state, changed))
        plan = []
        for task, (state, changed) in records.items():
            if state.get("vm") != "mortimer-" + task or state.get("status") not in DISPOSABLE:
                continue
            if now - changed < self.grace:
                continue
            # Verification VMs are disposable stopped copies with host-retained
            # evidence (rule 3). Unknown metadata elsewhere cannot own them.
            # Development/legacy VMs may still have an unreadable owner or
            # verification child: retain them, never infer an orphan grant.
            if state.get("purpose") != "verification" and (self._issues or task in duplicates):
                self._retained.append({"task": task, "vm": state["vm"],
                                       "reason": "unknown_owner_or_child" if self._issues else "ambiguous_owner"})
                continue
            reason = self.reason(state, changed, owners.get(task), children.get(task, []),
                                 now, grace=self.grace, orphan=orphan_limit, idle=idle_limit)
            if reason:
                plan.append({"task": task, "vm": state["vm"], "reason": reason})
        return plan

    @staticmethod
    def reason(state: dict, changed: float, session: dict | None, children: list, now: float,
               *, grace: int, orphan: int, idle: int) -> str | None:
        purpose = state.get("purpose")
        if purpose == "verification":
            return "verification finished; receipt and logs retained on host"
        quiet = now - max([changed, *(child_changed for _, child_changed in children)])
        if any(child.get("status") in {"creating", "created", "running", "provisioning"} for child, _ in children):
            return None  # Rule 4: a validation in progress still needs its parent.
        if quiet < grace:
            return None
        if purpose == "development":
            if session is None:
                return "no session owns this development task; quiet for %d hours" % (quiet // 3600) if quiet >= orphan else None
            if session["ended"]:
                return "session ended (" + str(session.get("phase")) + ")"
            waited = now - float(session.get("updated_at") or changed)
        else:
            waited = quiet
        if waited >= idle:
            return "idle for %d days" % (waited // 86400)
        return None

    @contextmanager
    def deletion_guard(self, task: str, now: float | None = None):
        """Revalidate policy under Controller's start/delete lock.

        Session and file operations may hold their mutation lock before asking
        for the lifecycle lock. Never wait for those locks in reverse order:
        a busy target owner makes cleanup fail closed, including a long validation
        whose saved timestamp has aged past the idle threshold.
        """
        with ExitStack() as leases:
            paths = [self.controller.task_dir(task) / "files.lock"]
            state = self.controller.read(task)
            if state.get("purpose") != "verification":
                owners, session_issues, duplicates = self._sessions()
                _, task_issues = self._records()
                if session_issues or task_issues or task in duplicates:
                    raise SandboxError("Cleanup development ownership or children are unknown; retaining VM")
                owner = owners.get(task)
                if owner is not None:
                    paths.append(self.controller.home / "sessions" / owner["id"] / "session.lock")
            for path in paths:
                if path.is_symlink():
                    raise SandboxError("Cleanup mutation lock is not a regular host path")
                lock = leases.enter_context(path.open("a"))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise SandboxError("Cleanup owner is active; retaining its VM") from None
            # This runs after Tart's stopped-state probe, immediately before
            # deletion, while fresh child registration/start are excluded.
            if not any(item["task"] == task for item in self.plan(now)):
                raise SandboxError("Cleanup eligibility changed; retaining its VM")
            yield

    def run(self, *, dry_run: bool = False, now: float | None = None) -> dict:
        report = {"at": int(time.time()), "dry_run": dry_run, "free_before": free_bytes(self.controller.home),
                  "destroyed": [], "failed": [], "kept": []}
        planned = self.plan(now)
        report["issues"] = list(self._issues)
        report["kept"].extend(self._retained)
        for item in planned:
            if dry_run:
                report["kept"].append(item)
                continue
            try:
                self.controller.destroy(item["task"],
                                        guard=lambda: self.deletion_guard(item["task"], now))
                report["destroyed"].append(item)
            except Exception as exc:  # One stuck VM must not keep every other clone.
                report["failed"].append({**item, "error": str(exc)})
        for issue in self._issues:
            if issue not in report["issues"]:
                report["issues"].append(issue)
        for item in self._retained:
            if item not in report["kept"]:
                report["kept"].append(item)
        report["free_after"] = free_bytes(self.controller.home)
        if not dry_run and (report["destroyed"] or report["failed"] or report["issues"]):
            with (self.controller.home / "prune.log").open("a") as log:
                log.write(json.dumps(report, sort_keys=True) + "\n")
        return report


def reclaim(controller) -> dict | None:
    """Best-effort pass before cloning; a failure here never blocks creation."""
    try:
        return Pruner(controller).run()
    except Exception as exc:
        try:
            with (controller.home / "prune.log").open("a") as log:
                log.write(json.dumps({"at": int(time.time()), "error": str(exc)}) + "\n")
        except OSError:
            pass
        return None


def require_headroom(controller, minimum: int = MIN_FREE_BYTES):
    free = free_bytes(controller.home)
    if free < minimum:
        raise SandboxError("Sandbox volume has %.1f GiB free (minimum %.0f GiB); run sandbox.prune or free space before cloning"
                           % (free / GIB, minimum / GIB))


def discard(controller, task: str) -> str:
    """Delete a finished task's VM without masking the caller's own result."""
    try:
        controller.destroy(task)
        return "deleted"
    except Exception as exc:
        return "retained: " + str(exc)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", type=Path,
                        default=Path(os.environ.get("MORTIMER_SANDBOX_HOME", str(Path.home() / "Documents/Codex/MortimerSandbox"))))
    parser.add_argument("--dry-run", action="store_true", help="report what would be deleted; delete nothing")
    parser.add_argument("--idle-days", type=float, default=IDLE_SECONDS / 86400,
                        help="idle threshold for open sessions and legacy tasks (default %(default)s)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)
    settings_path = args.home / "settings.json"
    if not settings_path.is_file() or settings_path.is_symlink():
        print("Sandbox: no settings.json under " + str(args.home), file=sys.stderr)
        return 1
    settings = json.loads(settings_path.read_bytes())
    controller = Controller(args.home, settings["tart"], settings["softnet"])
    report = Pruner(controller, idle=int(args.idle_days * 86400)).run(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        verb = "would delete" if args.dry_run else "deleted"
        for item in report["kept"] if args.dry_run else report["destroyed"]:
            print("%s %s: %s" % (verb, item["vm"], item["reason"]))
        for item in report["failed"]:
            print("failed %s: %s" % (item["vm"], item["error"]), file=sys.stderr)
        print("%s %d VM(s); %.1f GiB free (was %.1f GiB)" % (
            verb, len(report["kept"] if args.dry_run else report["destroyed"]),
            report["free_after"] / GIB, report["free_before"] / GIB))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SandboxError as exc:
        print("Sandbox: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
