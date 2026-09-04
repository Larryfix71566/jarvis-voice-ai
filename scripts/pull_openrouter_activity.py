#!/usr/bin/env python3
"""pull_openrouter_activity.py — enrich ledger rows from OpenRouter.

MORTIMER_OPTIMIZATION_PLAN.md Phase 0, readiness checklist step 8. Landed
from the plan's Rev 3 draft (docs/plans/optimization_rev3_files/
pull_openrouter_activity.py) with one change from the draft: key
retrieval uses jarvis.vault.inject_env() (the same in-process pattern
scripts/voice_model_bench.py already uses — vault secrets copied into
os.environ, non-empty env always wins) instead of the draft's approach of
shelling out to `python -m jarvis.vault get OPENROUTER_API_KEY` as a
subprocess and parsing its stdout. Both endpoint URLs and every field
name this script reads were re-checked against OpenRouter's current API
docs (openrouter.ai/docs/api-reference/get-a-generation and
.../api/api-reference/credits/get-remaining-credits, fetched 2026-09-01)
before landing — unchanged from the draft, no drift found.

For every openrouter row in the ledger with a gen_id but no reported_cost,
query GET https://openrouter.ai/api/v1/generation?id=<gen_id> and backfill:
  reported_cost, native input/output token counts, cached token count.
Also prints remaining credit balance (GET /api/v1/credits) for the runway
number in the dashboard.

This is also the Phase 0 verifier for assumption A5: after a session with
cache_control breakpoints on routed Claude/Gemini calls, rerun this and
check the cache columns — zeros on second-turn calls mean the discount is
NOT surviving the routed path and those calls belong on the native key.

Key comes from the vault, not .env, per standing policy — see get_key()
below.

Endpoint field names drift — this script treats the generation endpoint's
response defensively and logs unknown shapes instead of crashing. If a
field rename breaks backfill, --raw shows what actually came back.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

# Root-anchored, same pattern as usage_ledger.py/costs_api.py/
# cost_report.py — this script is meant to be run manually or from cron,
# not necessarily from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Running `python scripts/pull_openrouter_activity.py` directly puts only
# scripts/ on sys.path, not the repo root, so `from jarvis.vault import
# inject_env` below fails with ModuleNotFoundError. Same fix already
# applied to scripts/test_prompt_caching.py this session, matching the
# established convention every other scripts/*.py file in this repo uses
# (see scripts/list_voices.py) — caught this time by Larry actually
# running the script rather than by re-deriving it, worth remembering to
# check for up front on the NEXT new script rather than per-incident.
sys.path.insert(0, str(_REPO_ROOT))
DB_PATH = Path(os.environ.get("JARVIS_COSTS_DB") or _REPO_ROOT / "data" / "costs.db")
BASE = "https://openrouter.ai/api/v1"
PRINT_RAW = "--raw" in sys.argv


def get_key() -> str:
    """Vault first (S4 inject_env: non-empty env always wins, so this is
    safe even if OPENROUTER_API_KEY is also in .env), plain env as the
    fallback if the vault is disabled/absent — same precedence
    scripts/voice_model_bench.py's _load_vault() already establishes."""
    try:
        from jarvis.vault import inject_env
        inject_env()
    except Exception as exc:
        print(f"vault inject_env failed ({exc}); falling back to plain env",
              file=sys.stderr)
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        sys.exit("No OPENROUTER_API_KEY available (vault or env).")
    return key


def api_get(path: str, key: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def first_present(d: dict, *names, default=None):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default


def main() -> None:
    key = get_key()

    # runway
    try:
        credits = api_get("/credits", key).get("data", {})
        total = first_present(credits, "total_credits", "total", default=0)
        used = first_present(credits, "total_usage", "usage", default=0)
        print(f"OpenRouter credits: purchased={total} used={used} "
              f"remaining={float(total) - float(used):.2f}")
    except Exception as exc:
        print(f"credits endpoint failed: {exc}", file=sys.stderr)

    if not DB_PATH.exists():
        sys.exit(f"No ledger at {DB_PATH} — run some traffic first.")

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, gen_id FROM llm_calls WHERE provider='openrouter'"
        " AND gen_id IS NOT NULL AND reported_cost IS NULL"
    ).fetchall()
    print(f"{len(rows)} openrouter rows to enrich")

    ok = failed = 0
    for row_id, gen_id in rows:
        try:
            data = api_get(f"/generation?id={gen_id}", key).get("data", {})
            if PRINT_RAW:
                print(json.dumps(data, indent=2)[:2000])
            cost = first_present(data, "total_cost", "cost", "usage")
            n_in = first_present(data, "native_tokens_prompt", "tokens_prompt", default=0)
            n_out = first_present(data, "native_tokens_completion", "tokens_completion", default=0)
            cached = first_present(data, "native_tokens_cached", "cached_tokens", default=0)
            conn.execute(
                "UPDATE llm_calls SET reported_cost=?,"
                " input_tokens=CASE WHEN ?>0 THEN ? ELSE input_tokens END,"
                " output_tokens=CASE WHEN ?>0 THEN ? ELSE output_tokens END,"
                " cache_read_tokens=CASE WHEN ?>0 THEN ? ELSE cache_read_tokens END"
                " WHERE id=?",
                (cost, n_in, n_in, n_out, n_out, cached, cached, row_id),
            )
            ok += 1
            time.sleep(0.2)  # be polite; this endpoint is per-generation
        except Exception as exc:
            failed += 1
            print(f"gen {gen_id}: {exc}", file=sys.stderr)
    conn.commit()

    # A5 verdict on what we have
    hit = conn.execute(
        "SELECT COUNT(*) FROM llm_calls WHERE provider='openrouter'"
        " AND cache_read_tokens > 0"
    ).fetchone()[0]
    tot = conn.execute(
        "SELECT COUNT(*) FROM llm_calls WHERE provider='openrouter'"
        " AND reported_cost IS NOT NULL"
    ).fetchone()[0]
    print(f"enriched={ok} failed={failed}; routed calls with cache reads: {hit}/{tot}")
    if tot >= 10 and hit == 0:
        print("A5 WARNING: zero cache reads on routed calls — if breakpoints"
              " are set, the discount is not passing through; move those"
              " calls to the native key.")


if __name__ == "__main__":
    main()
