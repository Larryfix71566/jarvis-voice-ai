#!/usr/bin/env python3
"""Skill + roster validator (upgrade plan §3.2).

Validates:
  - every mcp_servers reference in config/agents.yaml resolves to a skill dir
  - every skill dir has a skill.yaml with the required keys and a valid class
  - manifest tools match the @mcp.tool functions in the skill's server.py
  - manifest requires_env entries are set (environment or .env)
  - manifest optional_env entries are forwarded if present, never required
  - manifest requires_env_dynamic sources are recognised (K2, registry._DYNAMIC_SOURCES)
  - optionally (--run-tests): each manifest's test command passes

Exit 0 and prints "SKILLS OK" when clean; exit 1 with a list of errors otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_KEYS = {"name", "version", "class", "tools", "requires_env", "test"}
VALID_CLASSES = {"standard", "privileged"}


def load_env_file(root: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    dotenv = root / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def skill_dir_for(server_name: str) -> str:
    return server_name.replace("-", "_")


def declared_tools(server_py: Path) -> list[str]:
    """Extract tool names from @mcp.tool decorated functions."""
    src = server_py.read_text(encoding="utf-8")
    return re.findall(r"@mcp\.tool\(\)\s*\ndef\s+(\w+)", src)


def validate(root: Path, run_tests: bool = False) -> list[str]:
    errors: list[str] = []

    # K2 (MORTIMER_SECURITY_HARDENING_PLAN.md Step 1d): registry._DYNAMIC_SOURCES
    # is the closed set of recognised requires_env_dynamic sources. Guarded
    # import — Step 2 of that plan is what actually defines it; until then
    # this stays None and the requires_env_dynamic check below is a no-op.
    try:
        sys.path.insert(0, str(root))
        from jarvis.skills.registry import _DYNAMIC_SOURCES
    except (ImportError, AttributeError):
        _DYNAMIC_SOURCES = None
    agents_path = root / "config" / "agents.yaml"
    agents = yaml.safe_load(agents_path.read_text(encoding="utf-8"))
    referenced = {
        srv
        for agent in agents.get("sub_agents", [])
        for srv in agent.get("mcp_servers", [])
    }

    env = {**load_env_file(root), **os.environ}
    skills_root = root / "mcp_servers"
    on_disk = {
        p.name for p in skills_root.iterdir() if p.is_dir() and not p.name.startswith("__")
    }

    # roster references must resolve
    for ref in sorted(referenced):
        if skill_dir_for(ref) not in on_disk:
            errors.append(f"agents.yaml references {ref!r} but {skill_dir_for(ref)}/ does not exist")

    # every skill dir must have a valid manifest
    for dirname in sorted(on_disk):
        sdir = skills_root / dirname
        manifest_path = sdir / "skill.yaml"
        if not manifest_path.exists():
            errors.append(f"{dirname}: missing skill.yaml")
            continue
        m = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        missing = REQUIRED_KEYS - set(m)
        if missing:
            errors.append(f"{dirname}: manifest missing keys {sorted(missing)}")
            continue
        if m["class"] not in VALID_CLASSES:
            errors.append(f"{dirname}: class must be one of {sorted(VALID_CLASSES)}")
        if m["name"] != dirname.replace("_", "-"):
            errors.append(f"{dirname}: manifest name {m['name']!r} does not match dir")
        if not m["tools"]:
            errors.append(f"{dirname}: manifest tools list is empty")

        # manifest tools must match server.py declarations exactly
        actual = set(declared_tools(sdir / "server.py"))
        declared = set(m["tools"])
        if actual != declared:
            errors.append(
                f"{dirname}: tools mismatch — manifest-only {sorted(declared - actual)}, "
                f"server-only {sorted(actual - declared)}"
            )

        for var in m["requires_env"]:
            if not env.get(var):
                errors.append(f"{dirname}: requires_env {var} is not set")

        # optional_env (K2): forwarded to the child if present, never
        # required — no presence check, just a type sanity check so a typo
        # (a bare string instead of a list) fails loudly here instead of
        # silently at spawn time.
        optional_env = m.get("optional_env", [])
        if not isinstance(optional_env, list):
            errors.append(f"{dirname}: optional_env must be a list")

        # requires_env_dynamic (K2, review F16): a variable whose NAME is
        # chosen at runtime (e.g. mcp-screen's vision API key). The source
        # naming it must be one registry.py actually knows how to resolve —
        # an unrecognised source is a hard error HERE, at check time, not a
        # crash the first time the server spawns. Guarded: registry.py only
        # gains _DYNAMIC_SOURCES in Step 2 of this plan, so until then this
        # pass is a no-op rather than a crash.
        for dyn in m.get("requires_env_dynamic", []):
            source = dyn.get("source") if isinstance(dyn, dict) else dyn
            if _DYNAMIC_SOURCES is not None and source not in _DYNAMIC_SOURCES:
                errors.append(
                    f"{dirname}: requires_env_dynamic source {source!r} is not "
                    f"a recognised dynamic source (registry._DYNAMIC_SOURCES)"
                )

        if run_tests:
            proc = subprocess.run(
                m["test"], shell=True, cwd=root, capture_output=True, text=True
            )
            if proc.returncode != 0:
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
                errors.append(f"{dirname}: test command failed\n    " + "\n    ".join(tail))

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-tests", action="store_true", help="run each skill's smoke test")
    args = ap.parse_args()

    # Credential vault (MORTIMER_CREDENTIAL_VAULT_PLAN.md S4 amendment,
    # discovered when the first real migration landed): requires_env
    # credentials now live in the vault, not .env, so this validator must
    # inject them before checking presence — same guarded pattern as
    # scripts/check_env.py. Guarded import: fresh checkouts without deps
    # have no vault to read anyway.
    try:
        sys.path.insert(0, str(ROOT))
        from jarvis.vault import inject_env

        inject_env()
    except ImportError:
        pass

    errors = validate(ROOT, run_tests=args.run_tests)
    if errors:
        print("SKILLS FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    n = len([d for d in (ROOT / "mcp_servers").iterdir() if d.is_dir() and not d.name.startswith("__")])
    print(f"SKILLS OK — {n} skills validated" + (" (tests run)" if args.run_tests else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
