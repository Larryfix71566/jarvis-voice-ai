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
import json
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

    def sessions(self) -> dict:
        """Development task id -> owning session record, with an ``ended`` flag."""
        owners = {}
        for path in (self.controller.home / "sessions").glob("*/session.json"):
            try:
                record = json.loads(path.read_bytes())
            except (OSError, ValueError):
                continue
            task = record.get("task")
            if isinstance(task, str) and TASK_ID.fullmatch(task):
                record["ended"] = (record.get("phase") in ENDED_PHASES
                                   or (path.parent / "cancelled.json").exists())
                owners[task] = record
        return owners

    def low_disk_mode(self) -> bool:
        return free_bytes(self.controller.home) < self.low_disk

    def records(self) -> dict:
        """Task id -> (state, record mtime) for every well-formed task record."""
        records = {}
        for path in sorted((self.controller.home / "tasks").glob("*/state.json")):
            task = path.parent.name
            if not TASK_ID.fullmatch(task) or path.parent.is_symlink():
                continue
            try:
                records[task] = (json.loads(path.read_bytes()), path.stat().st_mtime)
            except (OSError, ValueError):
                continue
        return records

    def plan(self, now: float | None = None) -> list:
        now = time.time() if now is None else now
        low = self.low_disk_mode()
        orphan_limit = self.grace if low else self.orphan
        idle_limit = self.low_disk_idle if low else self.idle
        owners = self.sessions()
        records = self.records()
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

    def run(self, *, dry_run: bool = False, now: float | None = None) -> dict:
        report = {"at": int(time.time()), "dry_run": dry_run, "free_before": free_bytes(self.controller.home),
                  "destroyed": [], "failed": [], "kept": []}
        for item in self.plan(now):
            if dry_run:
                report["kept"].append(item)
                continue
            try:
                self.controller.destroy(item["task"])
                report["destroyed"].append(item)
            except Exception as exc:  # One stuck VM must not keep every other clone.
                report["failed"].append({**item, "error": str(exc)})
        report["free_after"] = free_bytes(self.controller.home)
        if report["destroyed"] or report["failed"]:
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
