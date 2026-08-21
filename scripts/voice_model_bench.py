"""Voice model bench (MORTIMER_VOICE_MODEL_BENCH_PLAN.md §3, V1 — the shortlist).

Answers one narrow question per candidate before any accuracy run is spent
on it: is it fast enough, and does it call tools correctly? Benches against
the REAL Supervisor system prompt (SUPERVISOR_PROMPT, fully rendered — agent
catalog, voice addendum, a real memory context) and the REAL `delegate_task`
tool schema built from config/agents.yaml. A bench against a toy prompt
measures a different, smaller model than production actually runs.

This is a SHORTLIST tool, not the decision. §1's hard latency gate is the
live `scripts/latency_probe.py` targets on a real voice session — this
script's TTFT numbers cannot substitute for that, because the pipeline's
STT/TTS overhead is constant across every candidate and only the live probe
sees it. A candidate that looks fast here still has to clear that bar.

Nothing here executes a delegation. The tool-fidelity check inspects the
SHAPE of the tool call the model produces (right function, an agent_name
the roster actually has, a non-empty task) — it never calls the handler,
which would spend a second model's worth of tokens on a sub-agent for a
question this script isn't asking.

Usage (from repo root, keys in .env or vault):

    python scripts/voice_model_bench.py                # full bench, ~$1
    python scripts/voice_model_bench.py --dry-run       # no network calls;
                                                         # prints the exact
                                                         # system prompt and
                                                         # schema, verifies
                                                         # wiring for free
    python scripts/voice_model_bench.py --only haiku-baseline,sonnet-4-5

Never edits .env or config/upgrade_models.yaml — every candidate is reached
by overriding OPENAI_MODEL/OPENAI_BASE_URL/the relevant key env in this
process only (same "environment override, never a file edit" rule the plan
states for the accuracy runs in §4). Never prints a key value.

Output: one table on stdout, plus machine-readable JSON at
logs/bench/voice-model-<date>.json so the run is auditable later without
re-spending the money.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Running `python scripts/voice_model_bench.py` puts scripts/ on sys.path,
# not the repo root — same REPO_ROOT anchor convention as check_keys.py and
# check_env.py, so `import jarvis` works regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Isolate side effects (a real run touches memory/conversation reads via
# render_memory_context) in a temp db BEFORE importing jarvis modules that
# read JARVIS_DB_PATH — same ordering routing_eval.py uses, and for the
# same reason: an eval/bench run must never touch data/jarvis.db.
os.environ.setdefault(
    "JARVIS_DB_PATH",
    str(Path(tempfile.mkdtemp(prefix="jarvis-bench-")) / "bench.db"),
)

REPS = 5  # first discarded (connection warm-up); 4 timed
FIDELITY_CASES: list[dict[str, Any]] = [
    {"input": "remind me to water the plants in 3 hours", "expect": "scheduler"},
    {"input": "what's the weather in Berlin", "expect": "analyst"},
    {"input": "commit these changes", "expect": "developer"},
]
CANONICAL_UTTERANCE = FIDELITY_CASES[0]["input"]

# Plan §2. Edit freely — this is taste as much as analysis. `api_key_env`
# for the two direct-Anthropic rows is OPENAI_API_KEY, not ANTHROPIC_API_KEY:
# .env.example documents that in this deployment shape, OPENAI_BASE_URL
# points at Anthropic and OPENAI_API_KEY holds the Anthropic credential —
# the same (key, endpoint) pairing check_keys.py/check_env.py already probe.
# Frontier models (Opus/Fable/GPT-5.2) are deliberately excluded from round
# one per the plan's §2 reasoning.
CANDIDATES: list[dict[str, str]] = [
    {
        "name": "haiku-baseline",
        "route": "direct (current)",
        "model": "claude-haiku-4-5",
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
    },
    {
        "name": "sonnet-4-5",
        "route": "direct",
        "model": "claude-sonnet-4-5",
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
    },
    {
        "name": "gemini-3.7-flash",
        "route": "openrouter",
        "model": "google/gemini-3.7-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "name": "gpt-5-mini",
        "route": "openrouter",
        "model": "openai/gpt-5-mini",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "name": "kimi-k2.5",
        "route": "openrouter",
        "model": "moonshotai/kimi-k2.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
]


def _load_vault() -> str:
    """Best-effort vault read, same pattern as check_keys.py. Never fatal —
    a bench run with no vault still works against plain .env/shell keys."""
    try:
        from jarvis.vault import inject_env, load_secrets
        n = len(load_secrets())
        inject_env()
        return f"vault read ok ({n} secrets)"
    except Exception as exc:  # noqa: BLE001
        return f"vault NOT read ({type(exc).__name__}) - .env only"


def build_turn() -> tuple[str, dict, dict[str, Any]]:
    """Assemble the REAL system prompt + REAL delegate_task schema, exactly
    as the Orchestrator would for a live voice turn. Returns
    (system_prompt, delegate_tool_schema, sub_agent_names)."""
    from jarvis.agents.base import load_sub_agents
    from jarvis.agents.delegate import build_delegate_tool
    from jarvis.config import load_settings
    from jarvis.db import run_migrations
    from jarvis.memory import render_memory_context
    from jarvis.prompts import SUPERVISOR_PROMPT, render_agent_catalog
    from jarvis.skills.registry import REPO_ROOT as REG_ROOT
    from jarvis.skills.registry import SkillRegistry

    # Same isolated-temp-db ordering as routing_eval.py's run_eval(): a
    # migrated-but-empty db renders memory_context as "(no memories yet)",
    # matching what render_memory_context() falls back to anyway on a
    # missing table — this just avoids the spurious
    # memory_context_read_failed log line on every bench run.
    run_migrations()
    settings = load_settings()
    # Unstarted deliberately: load_sub_agents only needs a registry object
    # to hand each SubAgent a reference for delegations THIS script never
    # makes (the fidelity check inspects tool-call shape, never runs the
    # handler) — starting it would spawn every MCP server for nothing.
    registry = SkillRegistry(REG_ROOT / "config" / "mcp_servers.yaml")
    sub_agents = load_sub_agents(settings, registry)
    schema, _handler = build_delegate_tool(sub_agents)
    agent_catalog = render_agent_catalog([
        {"name": a.name, "display_name": a.display_name,
         "description": a.description}
        for a in sub_agents.values()
    ])
    system_prompt = SUPERVISOR_PROMPT.format(
        jarvis_name=settings.jarvis_name,
        user_name=settings.jarvis_user_name,
        timezone=settings.jarvis_timezone,
        agent_catalog=agent_catalog,
        voice_catalog="(none configured yet)",
        memory_context=render_memory_context(),
    )
    return system_prompt, schema, set(sub_agents)


async def _timed_stream(client, model: str, messages: list[dict], tools: list[dict]) -> dict:
    """One streaming rep. Returns TTFT (first content or tool-call delta),
    total wall time, and a rough tokens/sec (chars/4, since not every
    provider reports usage on a streaming response)."""
    start = time.perf_counter()
    ttft: float | None = None
    chars = 0
    stream = await client.chat.completions.create(
        model=model, messages=messages, tools=tools, stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        tool_calls = getattr(delta, "tool_calls", None)
        if (content or tool_calls) and ttft is None:
            ttft = time.perf_counter() - start
        if content:
            chars += len(content)
    total = time.perf_counter() - start
    approx_tokens = chars / 4
    return {
        "ttft_ms": None if ttft is None else round(ttft * 1000, 1),
        "total_ms": round(total * 1000, 1),
        "tokens_per_sec_approx": (
            None if total <= 0 or approx_tokens == 0
            else round(approx_tokens / total, 1)
        ),
    }


async def _fidelity_check(client, model: str, system_prompt: str, schema: dict,
                           known_agents: set[str]) -> list[dict]:
    """3 non-streaming calls. A model that malforms delegate_task regardless
    of speed is disqualified here — this is the OpenRouter upstream-routing-
    variance risk the plan names, made measurable rather than assumed."""
    results = []
    for case in FIDELITY_CASES:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": case["input"]},
        ]
        ok = False
        detail = ""
        try:
            response = await client.chat.completions.create(
                model=model, messages=messages, tools=[schema],
            )
            calls = list(response.choices[0].message.tool_calls or [])
            if not calls:
                ok = False
                detail = "no tool call produced"
            else:
                call = calls[0]
                if call.function.name != "delegate_task":
                    detail = f"called {call.function.name!r}, not delegate_task"
                else:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    agent_name = args.get("agent_name")
                    task = args.get("task")
                    if agent_name not in known_agents:
                        detail = f"agent_name {agent_name!r} not in roster"
                    elif not task or not str(task).strip():
                        detail = "task was empty"
                    elif agent_name != case["expect"]:
                        detail = f"routed to {agent_name!r}, expected {case['expect']!r}"
                    else:
                        ok = True
                        detail = "valid delegate_task call, correct agent"
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {str(exc)[:120]}"
        results.append({"input": case["input"], "expect": case["expect"],
                         "ok": ok, "detail": detail})
    return results


async def bench_candidate(candidate: dict, system_prompt: str, schema: dict,
                           known_agents: set[str]) -> dict:
    from openai import AsyncOpenAI

    key = os.environ.get(candidate["api_key_env"], "").strip()
    if not key:
        return {**candidate, "skipped": f"{candidate['api_key_env']} not set"}

    client = AsyncOpenAI(api_key=key, base_url=candidate["base_url"], timeout=60.0)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": CANONICAL_UTTERANCE},
    ]

    reps = []
    for i in range(REPS):
        try:
            rep = await _timed_stream(client, candidate["model"], messages, [schema])
        except Exception as exc:  # noqa: BLE001
            rep = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
        if i > 0:  # discard the first as connection warm-up
            reps.append(rep)

    ok_reps = [r for r in reps if "error" not in r]
    ttfts = [r["ttft_ms"] for r in ok_reps if r["ttft_ms"] is not None]
    totals = [r["total_ms"] for r in ok_reps if r["total_ms"] is not None]

    fidelity = await _fidelity_check(
        client, candidate["model"], system_prompt, schema, known_agents)

    return {
        **candidate,
        "reps": reps,
        "ttft_ms_mean": None if not ttfts else round(sum(ttfts) / len(ttfts), 1),
        "total_ms_mean": None if not totals else round(sum(totals) / len(totals), 1),
        "fidelity": fidelity,
        "fidelity_pass": sum(1 for f in fidelity if f["ok"]),
        "fidelity_total": len(fidelity),
    }


def render_table(results: list[dict]) -> str:
    lines = [
        f"{'candidate':<18} {'route':<16} {'ttft p mean':>12} "
        f"{'total mean':>12} {'fidelity':>10}"
    ]
    for r in results:
        if r.get("skipped"):
            lines.append(f"{r['name']:<18} {r['route']:<16} SKIPPED: {r['skipped']}")
            continue
        ttft = "-" if r["ttft_ms_mean"] is None else f"{r['ttft_ms_mean']:.0f} ms"
        total = "-" if r["total_ms_mean"] is None else f"{r['total_ms_mean']:.0f} ms"
        fid = f"{r['fidelity_pass']}/{r['fidelity_total']}"
        lines.append(
            f"{r['name']:<18} {r['route']:<16} {ttft:>12} {total:>12} {fid:>10}"
        )
    return "\n".join(lines)


async def run_bench(only: set[str] | None) -> list[dict]:
    system_prompt, schema, known_agents = build_turn()
    results = []
    for candidate in CANDIDATES:
        if only and candidate["name"] not in only:
            continue
        print(f"benching {candidate['name']} ({candidate['model']})...", file=sys.stderr)
        result = await bench_candidate(candidate, system_prompt, schema, known_agents)
        results.append(result)
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="build the real prompt+schema, print them, "
                              "make no network calls")
    parser.add_argument("--only", default=None,
                         help="comma-separated candidate names to bench")
    args = parser.parse_args(argv[1:])

    vault_note = _load_vault()
    print(f"voice_model_bench — {vault_note}", file=sys.stderr)

    if args.dry_run:
        system_prompt, schema, known_agents = build_turn()
        print(f"--- system prompt ({len(system_prompt)} chars) ---")
        print(system_prompt)
        print("--- delegate_task schema ---")
        print(json.dumps(schema, indent=2))
        print(f"--- roster: {sorted(known_agents)} ---")
        print("\ndry run only — no model was called, nothing was spent.")
        return 0

    only = set(args.only.split(",")) if args.only else None
    results = asyncio.run(run_bench(only))

    print()
    print(render_table(results))
    print()
    for r in results:
        if r.get("skipped"):
            continue
        for f in r["fidelity"]:
            if not f["ok"]:
                print(f"  {r['name']}: FIDELITY MISS on {f['input']!r} — {f['detail']}")

    out_dir = REPO_ROOT / "logs" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = out_dir / f"voice-model-{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"JSON written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
