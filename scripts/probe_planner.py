#!/usr/bin/env python3
"""Time a REALISTIC planner call against one model profile.

`check_env.py`'s `model_key_probe` answers "does this credential work?" with
a deliberately tiny chat/completions request. That is the right question for
a credential and the WRONG one for "why does this planner never finish": a
self-edit call carries the full UpgradeAgent system prompt plus (since G5,
2026-08-22) up to 8,000 characters of docs/REPO_MAP.md, and kimi-k3 is an
always-on-thinking model. A key that passes in 400 ms can still take minutes
on the real payload — this script measures that gap instead of assuming it.

Usage:
    python scripts/probe_planner.py                 # registry default
    python scripts/probe_planner.py kimi-k3
    python scripts/probe_planner.py claude-opus --timeout 300

Prints elapsed seconds, token usage when the provider reports it, and the
first line of the reply. Never prints key material. Read-only: it calls the
model directly and touches no session, branch, or database state.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jarvis.agents.upgrade_agent import (  # noqa: E402
    SYSTEM_PROMPT,
    load_model_registry,
    resolve_profile,
)
from jarvis.repo_map import load_repo_map_suffix  # noqa: E402
from jarvis.vault import inject_env  # noqa: E402

# A task shaped like a real self-edit goal: it must read before it can
# answer, which is what makes a thinking model actually think.
PROBE_TASK = (
    "Which file would you need to edit to change the caption character "
    "limit in the console, and what is the single smallest edit? Answer in "
    "two sentences. Do not call any tools."
)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", nargs="?", default=None,
                    help="registry profile name (default: registry default)")
    ap.add_argument("--timeout", type=float, default=180.0,
                    help="seconds before giving up (default 180)")
    ap.add_argument("--no-repo-map", action="store_true",
                    help="omit the repo map, to isolate its cost")
    args = ap.parse_args(argv[1:])

    inject_env()
    registry = load_model_registry()
    prof = resolve_profile(registry, args.profile)
    key_env = prof.get("api_key_env", "OPENAI_API_KEY")
    if not os.environ.get(key_env):
        print(f"FAIL: {key_env} is not set — cannot probe {prof['name']}.")
        return 2

    system = SYSTEM_PROMPT
    if not args.no_repo_map:
        system += load_repo_map_suffix()

    print(f"profile      : {prof['name']} ({prof['model']})")
    print(f"endpoint     : {prof.get('base_url')}")
    print(f"system prompt: {len(system):,} chars"
          f"{'' if args.no_repo_map else ' (incl. repo map)'}")
    print(f"timeout      : {args.timeout:.0f}s")
    print("calling…", flush=True)

    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ[key_env],
        base_url=prof.get("base_url"),
        timeout=args.timeout,
    )
    request = {
        "model": prof["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": PROBE_TASK},
        ],
    }
    # D-003: a profile with temperature: null omits the parameter entirely.
    if prof.get("temperature") is not None:
        request["temperature"] = prof["temperature"]

    started = time.monotonic()
    try:
        resp = client.chat.completions.create(**request)
    except Exception as exc:  # noqa: BLE001 — the failure IS the result here
        elapsed = time.monotonic() - started
        print(f"\nFAILED after {elapsed:.1f}s: {type(exc).__name__}: {exc}")
        return 1
    elapsed = time.monotonic() - started

    usage = getattr(resp, "usage", None)
    reply = (resp.choices[0].message.content or "").strip()
    print(f"\nOK in {elapsed:.1f}s")
    if usage is not None:
        print(f"tokens       : prompt={getattr(usage, 'prompt_tokens', '?')} "
              f"completion={getattr(usage, 'completion_tokens', '?')}")
    print(f"reply (1st line): {reply.splitlines()[0][:160] if reply else '(empty)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
