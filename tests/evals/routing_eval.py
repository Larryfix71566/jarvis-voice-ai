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


def _apply_candidate_overrides() -> None:
    """MORTIMER_VOICE_MODEL_BENCH_PLAN.md §4 — run the eval against a
    CANDIDATE voice model without touching .env.

    EVAL_MODEL / EVAL_BASE_URL override OPENAI_MODEL / OPENAI_BASE_URL for
    this process only (env beats .env in pydantic-settings, so no file edit).

    EVAL_KEY_ENV names ANOTHER environment variable whose value becomes
    OPENAI_API_KEY — a name, never a value, because the OpenRouter key lives
    in the vault and the vault never prints values by design; there is
    nothing to paste onto a command line. inject_env() is called first so a
    vault-held key is present to be copied; it is idempotent, and
    load_settings() calling it again later changes nothing.
    """
    wants = any(os.environ.get(k) for k in
                ("EVAL_MODEL", "EVAL_BASE_URL", "EVAL_KEY_ENV"))
    if not wants:
        return
    try:
        from jarvis.vault import inject_env
        inject_env()
    except Exception:  # noqa: BLE001 — .env-only setups still work
        pass
    if os.environ.get("EVAL_MODEL"):
        os.environ["OPENAI_MODEL"] = os.environ["EVAL_MODEL"]
    if os.environ.get("EVAL_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = os.environ["EVAL_BASE_URL"]
    key_env = os.environ.get("EVAL_KEY_ENV", "").strip()
    if key_env:
        value = os.environ.get(key_env, "").strip()
        if value:
            os.environ["OPENAI_API_KEY"] = value
        else:
            print(f"EVAL_KEY_ENV names {key_env!r}, which is empty — "
                  f"the eval will run on the DEFAULT key, not the candidate's")


async def run_eval() -> float:
    # Isolate eval side effects (notes/reminders/conversations) in a temp db
    # BEFORE importing jarvis modules that read JARVIS_DB_PATH.
    os.environ["JARVIS_DB_PATH"] = str(
        Path(tempfile.mkdtemp(prefix="jarvis-eval-")) / "eval.db"
    )
    _apply_candidate_overrides()

    from jarvis.agents.supervisor import Orchestrator
    from jarvis.config import load_settings
    from jarvis.db import run_migrations
    from jarvis.logging_config import setup_logging
    from jarvis.skills.registry import REPO_ROOT as REG_ROOT
    from jarvis.skills.registry import SkillRegistry

    settings = load_settings()
    # Named in the output so a 3-run record is attributable to its candidate
    # — five terminal scrollbacks that all just say "Routing accuracy" are
    # how numbers get credited to the wrong model.
    print(f"eval model: {settings.openai_model}  ({settings.openai_base_url})")
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
                print(f"[{i:2d}/{len(cases)}] ERROR  {case['input']!r}: {exc}")
                continue

            actual = set(delegated)
            ok = actual == expected if expected != {"none"} else not actual
            correct += ok
            mark = "ok " if ok else "MISS"
            print(f"[{i:2d}/{len(cases)}] {mark} expect={sorted(expected)} "
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
