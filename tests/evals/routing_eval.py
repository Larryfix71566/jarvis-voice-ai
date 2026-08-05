"""Routing accuracy eval (plan Phase 3, step 3.4).

Runs every case in tests/evals/cases.yaml through the real Orchestrator in
delegating mode and measures whether the right sub-agents were delegated to.

Usage (from repo root, keys in .env):
    RUN_LIVE=1 python -m tests.evals.routing_eval

Exit code 0 iff accuracy >= 90% (plan Exit Gate 3). Requires RUN_LIVE=1 —
this eval makes real LLM calls. Temperature is omitted per D-003 (kimi-k2.x
rejects values other than 1); routing decisions are asserted on recorded
delegate_task calls, never on prose.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CASES_PATH = Path(__file__).resolve().parent / "cases.yaml"
ACCURACY_THRESHOLD = 0.90


def _normalize(expect) -> set[str]:
    if isinstance(expect, list):
        return set(expect)
    return {expect}


async def run_eval() -> float:
    # Isolate eval side effects (notes/reminders/conversations) in a temp db
    # BEFORE importing jarvis modules that read JARVIS_DB_PATH.
    os.environ["JARVIS_DB_PATH"] = str(
        Path(tempfile.mkdtemp(prefix="jarvis-eval-")) / "eval.db"
    )

    from jarvis.agents.supervisor import Orchestrator
    from jarvis.config import load_settings
    from jarvis.db import run_migrations
    from jarvis.logging_config import setup_logging
    from jarvis.skills.registry import REPO_ROOT as REG_ROOT
    from jarvis.skills.registry import SkillRegistry

    settings = load_settings()
    setup_logging("WARNING")
    run_migrations()

    registry = SkillRegistry(REG_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()

    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    correct = 0
    try:
        for i, case in enumerate(cases, 1):
            expected = _normalize(case["expect"])
            delegated: list[str] = []

            def on_event(event: dict) -> None:
                if event.get("type") == "delegate_start":
                    delegated.append(event["agent"])

            orch = Orchestrator(settings, registry, str(uuid.uuid4()),
                                on_event=on_event)
            try:
                await orch.chat(case["input"])
            except Exception as exc:  # noqa: BLE001 — record as wrong, continue
                print(f"[{i:2d}/30] ERROR  {case['input']!r}: {exc}")
                continue

            actual = set(delegated)
            ok = actual == expected if expected != {"none"} else not actual
            correct += ok
            mark = "ok " if ok else "MISS"
            print(f"[{i:2d}/30] {mark} expect={sorted(expected)} "
                  f"got={sorted(actual)}  {case['input']!r}")
    finally:
        await registry.stop()

    accuracy = correct / len(cases)
    print(f"\nRouting accuracy: {correct}/{len(cases)} = {accuracy:.0%} "
          f"(threshold {ACCURACY_THRESHOLD:.0%})")
    return accuracy


def main() -> int:
    if os.environ.get("RUN_LIVE") != "1":
        print("routing_eval makes real LLM calls; re-run with RUN_LIVE=1")
        return 2
    accuracy = asyncio.run(run_eval())
    return 0 if accuracy >= ACCURACY_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
