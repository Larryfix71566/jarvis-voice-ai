#!/usr/bin/env python3
"""Generate and manage launchd agents for Mortimer's persistent processes
(gap-closure plan GC7). One XML template, values substituted through
xml.sax.saxutils.escape -- a raw `&&` inside a plist <string> is invalid
XML and `launchctl bootstrap` rejects the file outright, so every
substituted value (repo path, every argv element) is escaped."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import xml.sax.saxutils as saxutils
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "scripts" / "launchd" / "com.mortimer.template.plist"

# service -> shell command run inside `bash -c "cd <repo> && <cmd>"`
SERVICES = {
    "vault": "exec ./scripts/run_kb.sh",
    "bot": "./scripts/wait_for.sh 127.0.0.1 8484 30 vault && exec ./scripts/run_bot.sh",
    "extractor": "exec ./scripts/run_memory_extractor.sh",
    "admin": "exec ./scripts/run_admin.sh",
    "costs": "exec ./scripts/run_costs.sh",
}
ALL_SERVICES = (*SERVICES, "backup")  # backup is special-cased below: direct argv, StartCalendarInterval


def _esc(s: object) -> str:
    return saxutils.escape(str(s))


def _args_xml(args: list[str]) -> str:
    return "".join(f"<string>{_esc(a)}</string>" for a in args)


def render(svc: str, repo: Path, hour: int = 3, minute: int = 15) -> str:
    """Render one service's plist. `repo` is a parameter (not the module's
    ROOT) so tests can render against a fake path, including one containing
    a bare `&` -- the escaping must survive that."""
    template = TEMPLATE_PATH.read_text()
    repo_str = str(repo)
    if svc == "backup":
        args_xml = _args_xml([f"{repo_str}/.venv/bin/python", "scripts/backup_db.py"])
        schedule = (
            "<key>StartCalendarInterval</key><dict>"
            f"<key>Hour</key><integer>{int(hour)}</integer>"
            f"<key>Minute</key><integer>{int(minute)}</integer>"
            "</dict>"
        )
    elif svc in SERVICES:
        args_xml = _args_xml(["/bin/bash", "-c", f"cd {repo_str} && {SERVICES[svc]}"])
        schedule = "<key>KeepAlive</key><true/><key>RunAtLoad</key><true/>"
    else:
        raise ValueError(f"unknown service: {svc}")
    out = template
    out = out.replace("__SVC__", _esc(svc))
    out = out.replace("__ARGS__", args_xml)
    out = out.replace("__REPO__", _esc(repo_str))
    out = out.replace("__SCHEDULE__", schedule)
    return out


def _uid() -> int:
    return os.getuid()


def plist_path(svc: str, home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / "Library" / "LaunchAgents" / f"com.mortimer.{svc}.plist"


def write_all(repo: Path, hour: int, minute: int, home: Path | None = None) -> list[Path]:
    plist_path(ALL_SERVICES[0], home).parent.mkdir(parents=True, exist_ok=True)
    written = []
    for svc in ALL_SERVICES:
        p = plist_path(svc, home)
        p.write_text(render(svc, repo, hour, minute))
        written.append(p)
    return written


def install(repo: Path, hour: int, minute: int) -> None:
    write_all(repo, hour, minute)
    for svc in ALL_SERVICES:
        target = f"gui/{_uid()}/com.mortimer.{svc}"
        # bootout first: bootstrap fails if the label is already loaded, and
        # a failed bootout (not currently loaded) is expected, not an error.
        subprocess.run(["launchctl", "bootout", target], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", f"gui/{_uid()}", str(plist_path(svc))], check=False)


def uninstall() -> None:
    for svc in ALL_SERVICES:
        target = f"gui/{_uid()}/com.mortimer.{svc}"
        subprocess.run(["launchctl", "bootout", target], check=False)


def status() -> dict[str, str]:
    out: dict[str, str] = {}
    for svc in ALL_SERVICES:
        target = f"gui/{_uid()}/com.mortimer.{svc}"
        proc = subprocess.run(["launchctl", "print", target], check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            out[svc] = "not loaded"
            continue
        pid = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.startswith("pid ="):
                pid = line.split("=", 1)[1].strip()
                break
        out[svc] = f"loaded (pid {pid})" if pid else "loaded (idle)"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Mortimer's launchd agents (GC7).")
    parser.add_argument("--write", action="store_true", help="write plists only (default action)")
    parser.add_argument("--install", action="store_true", help="write, then bootstrap each service")
    parser.add_argument("--uninstall", action="store_true", help="bootout each service")
    parser.add_argument("--status", action="store_true", help="print loaded/not-loaded per service")
    parser.add_argument("--dry-run", action="store_true", help="print rendered plists, write nothing")
    parser.add_argument("--hour", type=int, default=3, help="backup schedule hour (default 3)")
    parser.add_argument("--minute", type=int, default=15, help="backup schedule minute (default 15)")
    args = parser.parse_args(argv)

    if args.dry_run:
        for svc in ALL_SERVICES:
            print(render(svc, ROOT, args.hour, args.minute))
        return 0
    if args.uninstall:
        uninstall()
        return 0
    if args.status:
        for svc, state in status().items():
            print(f"{svc}: {state}")
        return 0
    if args.install:
        install(ROOT, args.hour, args.minute)
        return 0
    for p in write_all(ROOT, args.hour, args.minute):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
