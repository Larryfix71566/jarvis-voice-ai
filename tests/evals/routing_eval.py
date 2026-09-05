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

# 2026-09-05 — a single aggregate over uneven category sizes hides the
# weakest category until it is the only thing left. The five smallest
# categories here total 25 cases; `developer` alone is 22 and `none` is 23,
# so a category can rot for a long time while the aggregate still clears
# 90%.
#
# DELIBERATELY EMPTY. A floor is a claim about what the eval currently
# scores per category, and no run recording that breakdown exists yet —
# this change is what produces the first one. Populate from an observed
# run, not from an estimate: a floor set above the real number turns the
# gate red on arrival and a floor set below it ratchets nothing. With no
# entries, gating is byte-for-byte what it was before this change.
CATEGORY_FLOORS: dict[str, float] = {}

# 2026-09-05 (MORTIMER_EVAL_CONFIG_PARITY_PLAN.md item D; Larry's call:
# parameterized, defaulting to parity). "parity" is what Mortimer ships
# when no kill switch is set -- all four prompt addenda and all ten tools.
# "delegate-only" is the harness this eval used until today: bare
# SUPERVISOR_PROMPT, delegate_task the only tool the model can see. It is
# kept ONLY so the two can be compared in a controlled way; its number is
# not a production number and never was.
# `addenda` are the prompt flags the Orchestrator forwards to
# build_supervisor_prompt; `tools` decides whether the standard tool menu
# is shown at all. They are separate on purpose: four unconditional tools
# ship even with every kill switch off, so "no addenda" and "no tools" are
# different states, and folding them together would make delegate-only
# impossible to express once any flag was on.
PROFILES: dict[str, dict] = {
    "parity": {
        "addenda": {"voice": True, "ui_control": True,
                    "screen": True, "clipboard": True},
        "tools": True,
    },
    "delegate-only": {
        "addenda": {"voice": False, "ui_control": False,
                    "screen": False, "clipboard": False},
        "tools": False,
    },
}
DEFAULT_PROFILE = "parity"

# Which profile CATEGORY_FLOORS was measured under. A floor is a claim
# about a number, and a number from one configuration says nothing about
# another -- so floors are skipped, loudly, when a different profile runs,
# rather than failing a gate against a baseline that never applied to it.
CATEGORY_FLOORS_PROFILE = DEFAULT_PROFILE


def resolve_profile(name: str | None) -> tuple[str, dict[str, bool], bool]:
    """Name -> (name, addenda flags, show-tools). An unknown name is fatal,
    never silently defaulted: a typo'd profile that quietly ran parity
    would attribute one configuration's number to another."""
    chosen = (name or DEFAULT_PROFILE).strip() or DEFAULT_PROFILE
    if chosen not in PROFILES:
        raise SystemExit(
            f"unknown EVAL_PROFILE {chosen!r}; choose one of "
            f"{', '.join(sorted(PROFILES))}"
        )
    profile = PROFILES[chosen]
    return chosen, dict(profile["addenda"]), bool(profile["tools"])


def _category_of(expect: set[str]) -> str:
    """Bucket a case by what it expects, for per-category scoring.

    Multi-agent cases collapse into one "multi" bucket rather than each
    combination becoming its own: cases.yaml has four of them, one per
    combination, and a floor over a single case can only ever be 0% or
    100%.
    """
    if expect == {"none"}:
        return "none"
    if len(expect) > 1:
        return "multi"
    return next(iter(expect))


def summarize_categories(
    results: list[tuple[str, bool]],
) -> dict[str, tuple[int, int]]:
    """{category: (correct, total)}. Totals sum to len(results)."""
    summary: dict[str, tuple[int, int]] = {}
    for category, ok in results:
        correct, total = summary.get(category, (0, 0))
        summary[category] = (correct + bool(ok), total + 1)
    return summary


def format_category_report(
    summary: dict[str, tuple[int, int]],
    floors: dict[str, float] | None = None,
) -> str:
    floors = CATEGORY_FLOORS if floors is None else floors
    lines = ["per-category:"]
    for category in sorted(summary, key=lambda c: (-summary[c][1], c)):
        correct, total = summary[category]
        rate = correct / total if total else 0.0
        floor = floors.get(category)
        mark = ""
        if floor is not None and rate < floor:
            mark = f"   BELOW FLOOR {floor:.0%}"
        lines.append(f"  {category:<12} {correct:>3}/{total:<3} {rate:>4.0%}{mark}")
    return "\n".join(lines)


def gate_failures(
    accuracy: float,
    summary: dict[str, tuple[int, int]],
    threshold: float = ACCURACY_THRESHOLD,
    floors: dict[str, float] | None = None,
    profile: str | None = None,
) -> list[str]:
    """Every reason the gate should fail. Empty list means pass.

    `profile` names the configuration that produced these numbers. When it
    differs from the one the floors were measured under, the floors do not
    apply and are skipped; the aggregate threshold still holds.
    """
    floors = CATEGORY_FLOORS if floors is None else floors
    if profile is not None and profile != CATEGORY_FLOORS_PROFILE and floors:
        print(f"category floors skipped: measured under "
              f"{CATEGORY_FLOORS_PROFILE!r}, this run is {profile!r}")
        floors = {}
    failures: list[str] = []
    if accuracy < threshold:
        failures.append(
            f"aggregate {accuracy:.0%} below threshold {threshold:.0%}"
        )
    for category, floor in sorted(floors.items()):
        if category not in summary:
            # A floor naming a category no cases produce is a stale floor,
            # and silently passing it would let a renamed agent disable its
            # own gate.
            failures.append(f"{category}: floor set but no cases scored")
            continue
        correct, total = summary[category]
        rate = correct / total if total else 0.0
        if rate < floor:
            failures.append(
                f"{category} {correct}/{total} = {rate:.0%} below floor {floor:.0%}"
            )
    return failures


REPLY_PREVIEW_CHARS = 400


def _one_line(text: str | None) -> str:
    """Collapse a reply to a single printable line for the miss report.

    Rule 5 caps replies at 40 words, so 400 characters truncates almost
    nothing; the cap exists so a runaway reply cannot bury the summary.
    """
    flat = " ".join((text or "").split())
    if not flat:
        return "(empty reply)"
    if len(flat) <= REPLY_PREVIEW_CHARS:
        return flat
    return flat[:REPLY_PREVIEW_CHARS] + "…"


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


async def run_eval() -> tuple[float, dict[str, tuple[int, int]]]:
    # Isolate eval side effects (notes/reminders/conversations) in a temp db
    # BEFORE importing jarvis modules that read JARVIS_DB_PATH.
    os.environ["JARVIS_DB_PATH"] = str(
        Path(tempfile.mkdtemp(prefix="jarvis-eval-")) / "eval.db"
    )
    _apply_candidate_overrides()

    from jarvis.agents.supervisor import Orchestrator
    from jarvis.bot.tool_schemas import supervisor_tool_schemas
    from jarvis.bot.voice_switch import catalog_summary, load_voice_catalog
    from jarvis.config import load_settings
    from jarvis.db import run_migrations
    from jarvis.logging_config import setup_logging
    from jarvis.skills.registry import REPO_ROOT as REG_ROOT
    from jarvis.skills.registry import SkillRegistry

    settings = load_settings()
    profile_name, flags, show_tools = resolve_profile(
        os.environ.get("EVAL_PROFILE"))
    # Larry's call: stubs answer "ok" and every tool call is logged. The
    # log is what carries the diagnosis -- that the model reached for
    # ui_control at all is the finding, whatever the stub returns -- so the
    # stub does not have to be production-faithful to be useful, and we are
    # not inventing plausible tool results.
    async def _stub(_arguments: dict) -> str:
        return "ok"

    extra_tools = [
        (schema, _stub)
        for schema in supervisor_tool_schemas(
            None,
            ui_control=flags["ui_control"],
            screen=flags["screen"],
            clipboard=flags["clipboard"],
        )
    ] if show_tools else []
    voice_catalog = (catalog_summary(load_voice_catalog())
                     if flags["voice"] else None)
    # Named in the output so a 3-run record is attributable to its candidate
    # — five terminal scrollbacks that all just say "Routing accuracy" are
    # how numbers get credited to the wrong model.
    print(f"eval model: {settings.openai_model}  ({settings.openai_base_url})")
    # Never print a number without the configuration that produced it.
    print(f"eval profile: {profile_name}  "
          f"({len(extra_tools) + 1} tools visible; addenda: "
          f"{', '.join(k for k, v in flags.items() if v) or 'none'})")
    setup_logging("WARNING")
    run_migrations()

    registry = SkillRegistry(REG_ROOT / "config" / "mcp_servers.yaml")
    await registry.start()

    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    correct = 0
    results: list[tuple[str, bool]] = []
    try:
        for i, case in enumerate(cases, 1):
            expected = _normalize(case["expect"])
            delegated: list[str] = []
            tools_called: list[str] = []

            def on_event(event: dict) -> None:
                if event.get("type") == "delegate_start":
                    delegated.append(event["agent"])
                elif event.get("type") == "supervisor_tool":
                    tools_called.append(event["tool"])

            orch = Orchestrator(settings, registry, str(uuid.uuid4()),
                                on_event=on_event,
                                extra_tools=extra_tools,
                                voice_catalog=voice_catalog,
                                **flags)
            try:
                # 2026-09-05 — the reply was previously discarded. A miss
                # printed only got=[], which says the model did not delegate
                # but not what it did instead, so every diagnosis of a miss
                # was a guess about text that had already been generated and
                # thrown away. Note what this does NOT capture: the
                # Orchestrator emits no event for its own tool calls
                # (on_event reaches only build_delegate_tool,
                # supervisor.py:79), so a turn that called some other tool
                # instead of delegating is invisible here. In this harness
                # that costs nothing -- delegate_task is the only tool the
                # Orchestrator exposes (supervisor.py:196) -- but it will
                # matter the moment the eval runs the production tool set.
                reply = await orch.chat(case["input"])
            except Exception as exc:  # noqa: BLE001 — record as wrong, continue
                print(f"[{i:2d}/{len(cases)}] ERROR  {case['input']!r}: {exc}")
                # Counted as a failure in its category, not dropped: the
                # aggregate already counts it (len(cases) is the
                # denominator), so dropping it here would make the category
                # totals disagree with the aggregate.
                results.append((_category_of(expected), False))
                continue

            actual = set(delegated)
            ok = actual == expected if expected != {"none"} else not actual
            correct += ok
            results.append((_category_of(expected), bool(ok)))
            mark = "ok " if ok else "MISS"
            print(f"[{i:2d}/{len(cases)}] {mark} expect={sorted(expected)} "
                  f"got={sorted(actual)}  {case['input']!r}")
            if not ok:
                # The tool sequence is the half that says WHY: got=[] means
                # nothing was delegated, and this says what was reached for
                # instead -- which nothing anywhere recorded before today.
                print(f"{'':>9}tools: {', '.join(tools_called) or '(none)'}")
                print(f"{'':>9}said: {_one_line(reply)}")
    finally:
        await registry.stop()

    accuracy = correct / len(cases)
    summary = summarize_categories(results)
    print(f"\nRouting accuracy: {correct}/{len(cases)} = {accuracy:.0%} "
          f"(threshold {ACCURACY_THRESHOLD:.0%})")
    print(format_category_report(summary))
    return accuracy, summary


def main() -> int:
    if os.environ.get("RUN_LIVE") != "1":
        print("routing_eval makes real LLM calls; re-run with RUN_LIVE=1")
        return 2
    profile_name, _, _ = resolve_profile(os.environ.get("EVAL_PROFILE"))
    accuracy, summary = asyncio.run(run_eval())
    failures = gate_failures(accuracy, summary, profile=profile_name)
    for reason in failures:
        print(f"GATE FAIL: {reason}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
