"""Automated memory hygiene — MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md.

Reverses the 2026-08-18 D2 "manual-first" decision at Larry's explicit
direction ("memory optimization/consolidation needs to be automated to
keep memory optimized"). The 2026-08-20 manual cleanup (178 -> 67 live
facts) is this module's calibration corpus: ~80% of the bloat was
mechanically obvious (same tier, high overlap, no mixed-content warning)
and is handled here without a model call (A1); the remaining ~20% needed
Larry's judgment (four real contradictions, one keep-choice the overlap
scorer got backwards, one poisoned summary row) and is queued for him,
never resolved automatically (A2/A3).

Four things this module does, in one sweep:

  A1  Auto-consolidate obvious duplicate clusters (reuses
      jarvis.consolidate's clique detection; archives, never deletes).
  A2  Detect CONTRADICTIONS via one small-model pass (token overlap finds
      similarity, not conflict — that needs reading, which needs a model).
      The model NEVER resolves a contradiction; it only flags one.
  A4  Auto-archive system-tier facts that have aged out (re-derivable from
      the repo; the tier is already excluded from the prompt, so the risk
      of getting this wrong is nil).
  A5  Classify each fact's AUDIENCE (interaction / task-rule / implemented)
      in the SAME batched model call as A2 — Larry's 2026-08-20 insight
      that most stored facts are about how Mortimer talks to him, not
      about how a sub-agent should do a kind of work, and only the first
      of those belongs in the Supervisor's every-turn prompt.

Every write here either archives (never deletes) or queues a
`memory_reviews` row for Larry to resolve — see resolve_review(). Nothing
in A2/A5 acts on a contradiction or a task-rule/implemented verdict
automatically; only A1's mechanical duplicate-cluster case and A4's
system-tier staleness are auto-archived, and both are bounded, logged,
and reversible via `became`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from jarvis.consolidate import propose_merges
from jarvis.db import get_conn, now_iso
from jarvis.memory import (
    MAX_PREFERENCE_FACTS,
    MAX_PROJECT_FACTS,
    archive_fact,
    upsert_fact,
)
from jarvis.procedures import _tokens
from jarvis.usage_ledger import record_completion, provider_from_base_url
from jarvis.memory_model import make_memory_async_client

logger = logging.getLogger(__name__)

KILL_SWITCH_ENV = "JARVIS_MEMORY_SWEEP_ENABLED"

# ⚙ TUNING KNOBS ----------------------------------------------------------
# Above this content-token overlap, a same-tier duplicate cluster is
# auto-archived rather than queued. Deliberately higher than
# jarvis.consolidate's manual-review DUPLICATE_THRESHOLD (0.6): automation
# needs a wider safety margin than a human reviewing a report, and 0.8
# sits above every misjudged case in the 2026-08-20 calibration corpus
# (the cluster-26 mistake scored 0.667).
SWEEP_AUTO_THRESHOLD = 0.8

# Bounded damage per boot: a bug in the sweep can only archive this many
# facts before the next restart, and the backlog drains over a few boots
# rather than in one big-bang pass.
SWEEP_MAX_ARCHIVES = 10

# Fact pairs considered for contradiction detection per sweep, newest
# first. Capped so a stable store converges toward zero model spend.
CONTRADICTION_PAIRS_PER_SWEEP = 20

# Facts considered for audience classification per sweep (A5), newest
# first — bounded for the same reason as the contradiction cap.
AUDIENCE_BATCH_CAP = 30

# system-tier facts not updated in this many days are re-derivable state
# that has aged out (A4). preference/project/identity never auto-stale.
SWEEP_SYSTEM_STALE_DAYS = 45

# MORTIMER_OPTIMIZATION_PLAN.md Phase 2 task 4, "expire unrepeated after N
# days" — an UNPROMOTED observation (jarvis.memory.promote_observations
# never found enough distinct-session evidence for it) whose last_seen_at
# is this many days old is given up on. [guessing] Deliberately shorter
# than SWEEP_SYSTEM_STALE_DAYS's 45: a staging row is an unconfirmed
# candidate, not a settled fact — losing one that never repeated costs
# nothing a future mention can't just re-create.
STAGING_EXPIRY_DAYS = 14

# Contradiction detection only makes sense within these tiers — a
# preference and a project fact sharing words are not in tension just
# because they overlap, and identity is included because that is exactly
# where the 2026-08-20 cleanup found real contradictions (current-location
# vs. Spartanburg-default).
CONTRADICTION_TIERS = ("preference", "identity")

# Same constant, value, and reasoning as jarvis.consolidate's
# MIN_SHARED_TOKENS: a symmetric overlap score divides by the SMALLER
# token set, so a one-token fact can score high against anything
# containing that word by coincidence. Two shared tokens targets the
# actual failure without penalising short, real facts.
MIN_SHARED_TOKENS = 2

VALID_VERDICTS = ("duplicate", "contradictory", "distinct")
VALID_AUDIENCES = ("interaction", "task-rule", "implemented")

CLASSIFY_PROMPT = """You maintain the long-term memory of a personal AI \
assistant named Mortimer, belonging to a user named Larry. You are given \
two kinds of items to classify. Respond with STRICT JSON only:

{"pairs": [{"a": "<key>", "b": "<key>", "verdict": "duplicate|contradictory|distinct"}],
 "audiences": [{"key": "<key>", "audience": "interaction|task-rule|implemented"}]}

For each PAIR (two facts that share vocabulary):
- "duplicate": the two facts say the same thing in different words.
- "contradictory": the two facts genuinely conflict — a reasonable person
  could not hold both at once (e.g. one says answers should be short, the
  other says they should be detailed, with no qualifier reconciling them).
- "distinct": neither of the above — two separate, compatible facts that
  merely share some words.
You are NEVER asked to resolve a contradiction, only to flag one. If you
are not confident, answer "distinct" — a missed contradiction is cheap, a
false one wastes a human's time.

For each FACT, classify its AUDIENCE:
- "interaction": describes how Mortimer should talk to or work WITH Larry
  in ordinary conversation — his name, communication style, standing
  preferences about replies, confirmations, units, location defaults.
  Needed on every voice turn.
- "task-rule": a RULE about how a specific KIND of work must be done
  (git workflow, review-before-storage, research-first, plan-preview) —
  matters only when that kind of work is happening, not every turn.
- "implemented": a feature request or preference about something that has
  since SHIPPED as a real feature (e.g. "show me the model being used" —
  if that is now a visible UI element, the request is stale).
If unsure, answer "interaction" — it is the safe default: an unclassified
fact should keep reaching the prompt rather than silently disappear.

Output JSON only. No markdown, no commentary. Omit any pair or fact you
were not given."""


def enabled() -> bool:
    """Single enforcement point for the kill switch (A6)."""
    value = os.environ.get(KILL_SWITCH_ENV)
    if value is None:
        return True
    return value.strip().lower() not in ("false", "0", "no")


# --------------------------------------------------------------------- #
# A1 — auto-consolidation
# --------------------------------------------------------------------- #


def _load_facts(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier "
        "FROM memories WHERE kind = 'fact' AND archived_at IS NULL"
    ).fetchall()
    return [dict(r) for r in rows]


def _existing_review_key_sets(conn, kind: str) -> list[frozenset]:
    """Every key-set already queued for `kind`, any status. This IS the
    "classified once" cache the plan describes — a pair or fact already
    represented by a memory_reviews row (open, resolved, OR dismissed) is
    never re-queued, so "both true" is a real resolution and a stable
    store converges toward zero model spend."""
    rows = conn.execute(
        "SELECT keys_json FROM memory_reviews WHERE kind = ?", (kind,)
    ).fetchall()
    out: list[frozenset] = []
    for r in rows:
        try:
            out.append(frozenset(json.loads(r["keys_json"])))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def _queue_if_new(conn, kind: str, keys: list[str], detail: str) -> bool:
    key_set = frozenset(keys)
    if key_set in _existing_review_key_sets(conn, kind):
        return False
    conn.execute(
        "INSERT INTO memory_reviews (kind, keys_json, detail, status, "
        "created_at) VALUES (?, ?, ?, 'open', ?)",
        (kind, json.dumps(sorted(keys)), detail, now_iso()),
    )
    return True


def run_auto_consolidation(conn) -> dict:
    """A1. Clusters above SWEEP_AUTO_THRESHOLD with no mixed-content
    warning are auto-archived, keeping the LONGEST content (not the
    scorer's `suggested_survivor` pick — the 2026-08-20 cluster-26
    mistake was the scorer preferring a specific project echo over a
    durable, general rule; length proxies durability better than score).
    Everything else (mixed-content clusters, anything past the per-sweep
    cap) is queued for Larry, never touched.

    Returns {"archived": [keys...], "queued": N}."""
    facts = _load_facts(conn)
    proposals = propose_merges(facts, threshold=SWEEP_AUTO_THRESHOLD)
    archived: list[str] = []
    queued = 0

    for p in proposals:
        if p.warnings:
            # Mixed-content hazard is a hard stop for automation (A6) —
            # e.g. a location fact that also carries a temperature-unit
            # preference. Always queued, never auto-merged.
            if _queue_if_new(
                conn, "cluster", p.keys,
                f"Possible duplicate cluster (tier={p.tier}, overlap>="
                f"{p.score}) — NOT auto-merged: {'; '.join(p.warnings)}",
            ):
                queued += 1
            continue

        if len(archived) >= SWEEP_MAX_ARCHIVES:
            if _queue_if_new(
                conn, "cluster", p.keys,
                f"Duplicate cluster (tier={p.tier}, overlap>={p.score}) "
                f"— sweep archive cap reached this boot, will auto-"
                f"consolidate on a future sweep.",
            ):
                queued += 1
            continue

        kept_idx = max(range(len(p.contents)), key=lambda i: len(p.contents[i]))
        kept_key = p.keys[kept_idx]
        room = SWEEP_MAX_ARCHIVES - len(archived)
        to_archive = [k for i, k in enumerate(p.keys) if i != kept_idx][:room]
        for key in to_archive:
            if archive_fact(conn, key, f"auto-consolidated:{kept_key}"):
                archived.append(key)
        remaining = len(p.keys) - 1 - len(to_archive)
        if remaining > 0:
            if _queue_if_new(
                conn, "cluster", p.keys,
                f"Duplicate cluster (tier={p.tier}, overlap>={p.score}) "
                f"— partially auto-consolidated this boot (cap reached); "
                f"{remaining} member(s) still waiting.",
            ):
                queued += 1

    return {"archived": archived, "queued": queued}


# --------------------------------------------------------------------- #
# A1.5 — capacity enforcement ladder (M3/M9, MORTIMER_MEMORY_CAPACITY_
# PLAN.md): the "live = injected" invariant. Every live fact must reach
# the prompt, so a tier sitting over its cap is a defect this sweep must
# eliminate, not one render_memory_context papers over by silently
# dropping. identity is never a target — CAPACITY_CAPS deliberately omits
# it, matching A1's own never-touch-identity rule.
# --------------------------------------------------------------------- #

# M2's per-tier caps, imported rather than redefined — one set of
# numbers, not two. system's live cap is 0 (M4): a tier CONTEXT_TIERS
# never surfaces to the prompt has no business staying "live"; still
# stored, still searchable via mcp-memory's memory_search (M6).
CAPACITY_CAPS: dict[str, int] = {
    "preference": MAX_PREFERENCE_FACTS,
    "project": MAX_PROJECT_FACTS,
    "system": 0,
}

# Rung (b)'s clustering threshold — deliberately LOWER than A1's
# SWEEP_AUTO_THRESHOLD (0.8). A1 auto-merges near-duplicates without a
# model in the loop; this rung asks a model to REWRITE related-but-not-
# identical facts into one, so the threshold only has to find a
# plausible cluster, and the rewrite step is what has to be trustworthy.
CAPACITY_MERGE_THRESHOLD = 0.55

MERGE_PROMPT = """You maintain the long-term memory of a personal AI \
assistant named Mortimer, belonging to a user named Larry. You are given \
a cluster of related facts (same tier) being merged into one fact \
because the store is over its capacity for that tier. Rewrite them into \
ONE fact that preserves every distinct piece of information across all \
of them.

Rules:
- Prefer general, durable phrasing over specific, episodic phrasing — a
  rule stated once beats a single dated example of it (the 2026-08-20
  cluster-26 lesson: a specific project echo is not a better survivor
  than a durable general statement, even when it reads more concrete).
- Do not drop any detail that appears in only ONE of the input facts.
- Output ONE sentence, plain text. No markdown, no commentary, no
  preamble — output ONLY the rewritten fact content, nothing else.

Facts:
{facts}"""


def _tier_count(conn, tier: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM memories WHERE kind = 'fact' "
        "AND archived_at IS NULL AND COALESCE(tier, 'project') = ?",
        (tier,),
    ).fetchone()[0]


def _age_out_oldest(conn, tier: str, n: int) -> list[str]:
    """Rung (c) — the mechanical backstop that holds M1's invariant even
    with no API key. Archives the `n` oldest live facts in `tier`,
    oldest-`updated_at`-first. Never touches identity (not a valid `tier`
    argument from this module's own caller)."""
    if n <= 0:
        return []
    rows = conn.execute(
        "SELECT key FROM memories WHERE kind = 'fact' AND archived_at IS NULL "
        "AND COALESCE(tier, 'project') = ? ORDER BY updated_at ASC LIMIT ?",
        (tier, n),
    ).fetchall()
    archived: list[str] = []
    for r in rows:
        if archive_fact(conn, r["key"], "aged-out"):
            archived.append(r["key"])
    return archived


def _best_capacity_cluster(conn, tier: str):
    """The single best (highest-overlap) mergeable cluster for `tier`, or
    None. Mixed-content-hazard clusters are excluded — A1's hard stop
    against automation applies here too; a fact carrying a topic its key
    doesn't advertise is never auto-merged, only ever queued for a human
    (and capacity enforcement queues nothing — M7 — so such a cluster
    simply falls through to rung (c) instead)."""
    facts = [f for f in _load_facts(conn) if f["tier"] == tier]
    proposals = propose_merges(facts, threshold=CAPACITY_MERGE_THRESHOLD)
    for p in proposals:
        if not p.warnings:
            return p
    return None


async def _merge_cluster(
    proposal, settings: Any, client_factory: Callable[[Any], Any] | None = None,
) -> str | None:
    """One small-model call rewriting a MergeProposal's facts into a
    single fact. Returns None on ANY failure (network, empty/malformed
    output) — the caller falls through to rung (c) rather than trusting a
    bad rewrite. Reuses the sweep's existing client-construction pattern
    (jarvis.memory_sweep._classify_batch)."""
    try:
        if client_factory is not None:
            client = client_factory(settings)
            model = getattr(settings, "openai_model", None)
        else:
            client, route = make_memory_async_client(settings)
            model = route.model
        # `settings` may be None when a test-seam `client_factory` supplies
        # its own fake client — getattr rather than assume, so that seam
        # never has to fabricate a whole Settings object.
        facts_block = "\n".join(
            f"- {k}: {c}" for k, c in zip(proposal.keys, proposal.contents)
        )
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": MERGE_PROMPT.format(facts=facts_block)},
            ],
        )
        try:
            record_completion(
                rung="memory_merge",
                provider=provider_from_base_url(str(client.base_url)),
                model=model,
                response=response,
            )
        except Exception:
            pass
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 — a failed merge falls through to age-out
        logger.warning(
            "memory_enforce_merge_failed tier=%s keys=%s",
            proposal.tier, proposal.keys, exc_info=True,
        )
        return None


async def run_capacity_enforcement(
    conn,
    settings: Any | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    ignore_boot_cap: bool = False,
) -> dict:
    """M3/M5 — the per-tier ladder that holds M1's invariant: every live
    fact reaches the prompt. Runs as A1.5 in run_sweep, right after
    run_auto_consolidation (rung a) and before A2/A5 classification;
    never touches identity.

    Per tier (preference, project, system), while the tier is over its
    cap:
      (b) merge the single best cluster via one small-model call, when a
          model/key is available and a mergeable cluster exists —
          otherwise this rung is skipped, logged once, and rung (c)
          takes the rest.
      (c) mechanical age-out — archive the oldest facts beyond the cap.
          The backstop that holds the invariant with zero API dependency.
    system's cap is 0 (M4): every live system fact is archived on sight,
    with no merge rung at all — merging facts the prompt never sees would
    waste a model call on pure storage noise.

    `ignore_boot_cap=True` (M5, the `--enforce` CLI) runs the full ladder
    in one pass; otherwise each tier's total archived-this-call count is
    bounded by SWEEP_MAX_ARCHIVES, the same per-boot damage limit A1
    uses, so an unattended boot can only move the store this far before
    the next restart drains the rest.

    Never queues anything for Larry (M7) — capacity is arithmetic, not a
    judgment call; the only queuing left after this rung is A1's
    mixed-content-hazard path and A2/A5's classification, both untouched.
    Returns {tier: {"before", "after", "cap", "merged", "aged_out"}}.
    """
    report: dict[str, dict] = {}
    for tier, cap in CAPACITY_CAPS.items():
        before = _tier_count(conn, tier)
        merged = 0
        aged_out = 0
        merge_skipped = False
        merge_skip_reason = "none"

        if tier == "system":
            # M4: archive on sight, no merge rung — see docstring.
            aged_out = len(_age_out_oldest(conn, tier, before))
        else:
            archive_budget = None if ignore_boot_cap else SWEEP_MAX_ARCHIVES
            spent = 0
            over = before - cap
            while over > 0 and (archive_budget is None or spent < archive_budget):
                proposal = _best_capacity_cluster(conn, tier)
                if proposal is None:
                    merge_skipped = True
                    merge_skip_reason = "no_mergeable_cluster"
                    break
                if settings is None and client_factory is None:
                    try:
                        from jarvis.config import load_settings

                        settings = load_settings()
                    except Exception:  # noqa: BLE001
                        merge_skipped = True
                        merge_skip_reason = "settings_load_failed"
                        logger.warning(
                            "memory_enforce_settings_load_failed tier=%s",
                            tier, exc_info=True,
                        )
                        break
                rewritten = await _merge_cluster(proposal, settings, client_factory)
                if not rewritten:
                    merge_skipped = True
                    merge_skip_reason = "merge_call_failed"
                    break
                kept_key = proposal.keys[0]
                upsert_fact(conn, kept_key, rewritten, None)
                for key in proposal.keys[1:]:
                    if archive_fact(conn, key, f"merged:{kept_key}"):
                        merged += 1
                        spent += 1
                over = _tier_count(conn, tier) - cap

            if merge_skipped:
                logger.info(
                    "memory_enforce_merge_skipped tier=%s reason=%s",
                    tier, merge_skip_reason,
                )

            over = _tier_count(conn, tier) - cap
            # W7 (MORTIMER_WEATHER_FAHRENHEIT_AND_RADAR_PLAN.md, 2026-08-22,
            # from a live regression: an unattended --enforce run with no
            # API key aged out the user's only surviving Fahrenheit
            # preference fact, silently and irreversibly-looking, because
            # mechanical age-out is blind to importance — it archives by
            # AGE, and a stated preference is not distinguishable from a
            # stale scratch note by that measure alone). preference facts
            # are things Larry explicitly told Mortimer; project/system
            # facts are largely re-derivable (git log, repo state). So
            # when the merge rung could not run this pass — for ANY
            # reason merge_skipped covers, not only a missing key, since
            # "no mergeable cluster" leaves the SAME blind-deletion risk
            # for preference — mechanical age-out stops for `preference`
            # specifically rather than silently emptying the overage.
            # The tier is left over cap; that is a visible, recoverable
            # state (the Memory panel's not_reaching_prompt line, M5's
            # `--enforce` re-run once a key is available) — strictly
            # preferable to a preference vanishing without a trace. This
            # is a deliberate, scoped weakening of M1's "live = injected"
            # invariant: do not restore unconditional age-out here to
            # satisfy that invariant — see the plan's self-audit.
            if tier == "preference" and merge_skipped and over > 0:
                logger.warning(
                    "memory_enforce_preference_left_over_cap tier=%s "
                    "over=%d cap=%d reason=merge_rung_unavailable",
                    tier, over, cap,
                )
            elif over > 0:
                remaining_budget = (
                    over if ignore_boot_cap
                    else max(0, (archive_budget or 0) - spent)
                )
                aged_out = len(
                    _age_out_oldest(conn, tier, min(over, remaining_budget))
                )

        after = _tier_count(conn, tier)
        report[tier] = {
            "before": before, "after": after, "cap": cap,
            "merged": merged, "aged_out": aged_out,
        }

    logger.info("memory_enforce %s", report)
    return report


# --------------------------------------------------------------------- #
# A4 — system-tier staleness
# --------------------------------------------------------------------- #


def run_stale_sweep(conn, stale_days: int = SWEEP_SYSTEM_STALE_DAYS) -> list[str]:
    """A4. Only ever touches system-tier facts — re-derivable claims about
    Mortimer's own state that are already excluded from the prompt, so
    getting this wrong costs nothing a `git log`/`git status` can't fix.
    preference/project/identity NEVER auto-stale here."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=stale_days)).isoformat()
    rows = conn.execute(
        "SELECT key FROM memories WHERE kind = 'fact' AND archived_at IS NULL "
        "AND COALESCE(tier, 'project') = 'system' AND updated_at < ?",
        (cutoff,),
    ).fetchall()
    archived: list[str] = []
    for r in rows:
        if archive_fact(conn, r["key"], "auto-stale:aged-out"):
            archived.append(r["key"])
    return archived


def run_staging_expiry(conn, expiry_days: int = STAGING_EXPIRY_DAYS) -> list[str]:
    """MORTIMER_OPTIMIZATION_PLAN.md Phase 2 task 4, "expire unrepeated
    after N days". Deletes observation rows for a key that has (a) gone
    stale (its most recent mention older than expiry_days) and (b) never
    accumulated enough distinct-session evidence to promote — no fact
    exists yet for that key (jarvis.memory.promote_observations' own
    "does a fact already exist" check, mirrored here).

    Deliberately scoped to UNPROMOTED keys only, matching the plan's
    "unrepeated" wording: once a key promotes, its remaining raw
    observation rows are bounded (at most a few, from before promotion)
    and harmless — cleaning those up too is a reasonable future addition,
    not something this pass attempts.

    Plain DELETE, not archive-with-a-`became`-marker like run_stale_sweep's
    facts: observations were never covered by jarvis.memory's archive
    discipline (migration 0013 added archived_at/became to `memories`
    only) — they are raw staging evidence, disposable by design once cold.

    COALESCE(last_seen_at, created_at): jarvis.memory.add_observation
    (the pre-Phase-2 write path, still live when JARVIS_MEMORY_EXTRACTION_V2
    is off) does not set last_seen_at — only jarvis.memory_extraction's
    novelty-gated insert does. Falling back to created_at keeps this sweep
    correct for observations written either way, rather than silently
    never expiring rows the old path wrote.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=expiry_days)).isoformat()
    stale_keys = conn.execute(
        "SELECT DISTINCT key FROM observations "
        "WHERE COALESCE(last_seen_at, created_at) < ?",
        (cutoff,),
    ).fetchall()
    expired: list[str] = []
    for row in stale_keys:
        key = row["key"]
        has_fact = conn.execute(
            "SELECT 1 FROM memories WHERE kind = 'fact' AND key = ?", (key,)
        ).fetchone()
        if has_fact is not None:
            continue  # already promoted -- its evidence rows are harmless
        cur = conn.execute(
            "DELETE FROM observations WHERE key = ? "
            "AND COALESCE(last_seen_at, created_at) < ?",
            (key, cutoff),
        )
        if cur.rowcount:
            expired.append(key)
    if expired:
        logger.info("memory_staging_expiry expired=%s", expired)
    return expired


# --------------------------------------------------------------------- #
# A2 + A5 — contradiction detection and audience classification
# --------------------------------------------------------------------- #


def _select_contradiction_pairs(conn) -> list[tuple[dict, dict]]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier, updated_at "
        "FROM memories WHERE kind = 'fact' AND archived_at IS NULL "
        f"AND COALESCE(tier, 'project') IN "
        f"({','.join('?' for _ in CONTRADICTION_TIERS)}) "
        "ORDER BY updated_at DESC",
        CONTRADICTION_TIERS,
    ).fetchall()
    rows = [dict(r) for r in rows]
    seen = _existing_review_key_sets(conn, "contradiction")
    toks = [_tokens(r["content"]) for r in rows]

    pairs: list[tuple[dict, dict]] = []
    n = len(rows)
    for i in range(n):
        for j in range(i + 1, n):
            if rows[i]["tier"] != rows[j]["tier"]:
                continue  # never cross-tier (A6/consolidate discipline)
            shared = toks[i] & toks[j]
            if len(shared) < MIN_SHARED_TOKENS:
                continue
            if frozenset((rows[i]["key"], rows[j]["key"])) in seen:
                continue
            pairs.append((rows[i], rows[j]))
            if len(pairs) >= CONTRADICTION_PAIRS_PER_SWEEP:
                return pairs
    return pairs


def _select_audience_candidates(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier, updated_at "
        "FROM memories WHERE kind = 'fact' AND archived_at IS NULL "
        "AND audience IS NULL AND COALESCE(tier, 'project') != 'system' "
        "ORDER BY updated_at DESC LIMIT ?",
        (AUDIENCE_BATCH_CAP,),
    ).fetchall()
    return [dict(r) for r in rows]


def _parse_classification(text: str) -> dict[str, dict]:
    """Strict-JSON parse. Unparseable input, or a verdict/audience outside
    the known set, is an explicit ABSTENTION — never a guess:
    verdict -> "distinct" (the cheap-miss default), audience ->
    "interaction" (the fail-open default). Pure and total; never raises."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"pairs": {}, "audiences": {}}
    if not isinstance(data, dict):
        return {"pairs": {}, "audiences": {}}

    pairs_out: dict[frozenset, str] = {}
    for item in data.get("pairs") or []:
        if not isinstance(item, dict):
            continue
        a, b = item.get("a"), item.get("b")
        if not a or not b:
            continue
        verdict = item.get("verdict")
        if verdict not in VALID_VERDICTS:
            verdict = "distinct"
        pairs_out[frozenset((a, b))] = verdict

    audiences_out: dict[str, str] = {}
    for item in data.get("audiences") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key:
            continue
        audience = item.get("audience")
        if audience not in VALID_AUDIENCES:
            audience = "interaction"
        audiences_out[key] = audience

    return {"pairs": pairs_out, "audiences": audiences_out}


async def _classify_batch(
    pairs: list[tuple[dict, dict]],
    audience_candidates: list[dict],
    settings: Any,
    client_factory: Callable[[Any], Any] | None = None,
) -> dict[str, dict]:
    if not pairs and not audience_candidates:
        return {"pairs": {}, "audiences": {}}
    if client_factory is not None:
        client = client_factory(settings)
        model = getattr(settings, "openai_model", None)
    else:
        client, route = make_memory_async_client(settings)
        model = route.model
    payload = {
        "pairs": [
            {"a": a["key"], "a_content": a["content"], "b": b["key"], "b_content": b["content"]}
            for a, b in pairs
        ],
        "facts": [
            {"key": f["key"], "content": f["content"]} for f in audience_candidates
        ],
    }
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    try:
        record_completion(
            rung="memory_classify",
            provider=provider_from_base_url(str(client.base_url)),
            model=model,
            response=response,
        )
    except Exception:
        pass
    return _parse_classification(response.choices[0].message.content or "")


def _apply_classification(
    conn,
    pairs: list[tuple[dict, dict]],
    pair_verdicts: dict[frozenset, str],
    audience_candidates: list[dict],
    audiences: dict[str, str],
    *,
    automated: bool = False,
) -> dict:
    contradictions_queued = 0
    for a, b in pairs:
        verdict = pair_verdicts.get(frozenset((a["key"], b["key"])), "distinct")
        if verdict != "contradictory":
            continue  # duplicate/distinct: A1 handles real duplicates
        if _queue_if_new(
            conn, "contradiction", [a["key"], b["key"]],
            f"Possible contradiction — {a['key']}: "
            f"{a['content'][:120]!r} vs {b['key']}: {b['content'][:120]!r}",
        ):
            contradictions_queued += 1

    task_rule_queued = 0
    implemented_queued = 0
    interaction_set = 0
    identity_forced = 0
    for f in audience_candidates:
        audience = audiences.get(f["key"], "interaction")
        if f["tier"] == "identity":
            # A5 mechanical override: identity is ALWAYS 'interaction',
            # never the model's judgment call — same discipline as A1
            # never auto-merging identity.
            audience = "interaction"
            identity_forced += 1
        if audience == "interaction":
            conn.execute(
                "UPDATE memories SET audience = 'interaction' "
                "WHERE key = ? AND kind = 'fact'", (f["key"],),
            )
            interaction_set += 1
        elif audience == "task-rule":
            if automated:
                # B phase: the typed automation queue owns routine audience
                # decisions when enabled. Apply only presentation metadata;
                # never create a workflow or archive content without an
                # explicit user action.
                conn.execute(
                    "UPDATE memories SET audience = 'task-rule', memory_type = 'task_rule' "
                    "WHERE key = ? AND kind = 'fact'", (f["key"],),
                )
                continue
            # Deliberately leaves memories.audience NULL — fail-open, so
            # the fact keeps reaching the prompt until Larry confirms the
            # conversion (resolve_review's "convert_workflow" action).
            if _queue_if_new(
                conn, "audience", [f["key"]],
                f"{f['key']} looks like a task rule, not a conversation "
                f"preference: {f['content'][:160]!r}. Convert to a "
                f"workflow (sub-agent prompt), or keep as-is?",
            ):
                task_rule_queued += 1
        elif audience == "implemented":
            if automated:
                conn.execute(
                    "UPDATE memories SET audience = 'implemented' "
                    "WHERE key = ? AND kind = 'fact'", (f["key"],),
                )
                continue
            if _queue_if_new(
                conn, "audience", [f["key"]],
                f"{f['key']} looks like a shipped feature request: "
                f"{f['content'][:160]!r}. Archive as implemented, or "
                f"keep as-is?",
            ):
                implemented_queued += 1

    return {
        "contradictions_queued": contradictions_queued,
        "task_rule_queued": task_rule_queued,
        "implemented_queued": implemented_queued,
        "interaction_set": interaction_set,
        "identity_forced": identity_forced,
    }


# --------------------------------------------------------------------- #
# A3 — the confirmation loop (read + resolve)
# --------------------------------------------------------------------- #


def list_open_reviews(conn=None) -> list[dict]:
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT id, kind, keys_json, detail, status, created_at "
            "FROM memory_reviews WHERE status = 'open' ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["keys"] = json.loads(d["keys_json"])
            except (json.JSONDecodeError, TypeError):
                d["keys"] = []
            out.append(d)
        return out
    finally:
        if own_connection:
            conn.close()


def open_review_count(conn=None) -> int:
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM memory_reviews WHERE status = 'open'"
        ).fetchone()[0]
    finally:
        if own_connection:
            conn.close()


def resolve_review(
    conn, review_id: int, action: str, rewrite_content: str | None = None,
) -> dict:
    """A3. Larry resolves what the sweep would not.

    kind='cluster'/'contradiction' (2+ keys): keep_a | keep_b | rewrite | dismiss.
    kind='audience' (1 key): convert_workflow | archive_implemented |
      keep_interaction | dismiss.

    Dismissed != resolved: the row's status changes, but the underlying
    fact(s) are untouched — "they're both true" is a valid resolution,
    and the pair/fact never re-queues because _existing_review_key_sets
    reads every status, not just 'open'.
    """
    row = conn.execute(
        "SELECT * FROM memory_reviews WHERE id = ?", (review_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no review with id {review_id}")
    keys = json.loads(row["keys_json"])
    kind = row["kind"]
    now = now_iso()

    if action == "dismiss":
        conn.execute(
            "UPDATE memory_reviews SET status = 'dismissed', resolved_at = ? "
            "WHERE id = ?", (now, review_id),
        )
        return {"action": "dismiss"}

    if kind in ("cluster", "contradiction"):
        if action in ("keep_a", "keep_b") and len(keys) >= 2:
            survivor = keys[0] if action == "keep_a" else keys[1]
            for key in keys:
                if key != survivor:
                    archive_fact(conn, key, f"reviewed:kept:{survivor}")
        elif action == "rewrite" and rewrite_content:
            survivor = keys[0]
            upsert_fact(conn, survivor, rewrite_content, None)
            for key in keys[1:]:
                archive_fact(conn, key, f"reviewed:rewritten:{survivor}")
        else:
            raise ValueError(f"unsupported action {action!r} for kind {kind!r}")
    elif kind == "audience":
        key = keys[0]
        if action == "convert_workflow":
            from jarvis.classify import extract_workflow

            try:
                extract_workflow(conn, key)
            except SystemExit as exc:
                # extract_workflow raises SystemExit for its CLI usage
                # (no live fact / slug collision) — translate to a normal
                # exception so this doesn't crash the sidecar's request
                # handler, which does not expect SystemExit from a
                # library call.
                raise ValueError(str(exc)) from exc
        elif action == "archive_implemented":
            archive_fact(conn, key, "deleted:implemented")
        elif action == "keep_interaction":
            conn.execute(
                "UPDATE memories SET audience = 'interaction' "
                "WHERE key = ? AND kind = 'fact'", (key,),
            )
        else:
            raise ValueError(f"unsupported action {action!r} for kind 'audience'")
    else:
        raise ValueError(f"unknown review kind {kind!r}")

    conn.execute(
        "UPDATE memory_reviews SET status = 'resolved', resolved_at = ? "
        "WHERE id = ?", (now, review_id),
    )
    return {"action": action}


# --------------------------------------------------------------------- #
# Entry point + background thread
# --------------------------------------------------------------------- #


async def run_sweep(
    db_path: str | None = None,
    settings: Any | None = None,
    client_factory: Callable[[Any], Any] | None = None,
) -> dict:
    """A1 + A2 + A4 + A5 in one pass. Never raises — best-effort, exactly
    the discipline every other startup pass in this codebase follows
    (key-health probe, runlog prune, screen-log prune)."""
    if not enabled():
        return {"enabled": False}

    summary = {
        "archived": 0, "queued": 0, "contradictions": 0, "stale_archived": 0,
        "capacity_enforced": 0, "staging_expired": 0,
    }
    try:
        conn = get_conn(db_path)
        try:
            a1 = run_auto_consolidation(conn)
            summary["archived"] += len(a1["archived"])
            summary["queued"] += a1["queued"]

            # A1.5 (M3/M9) — capacity enforcement ladder. Runs bounded
            # (ignore_boot_cap=False) on the unattended sweep path; the
            # --enforce CLI below calls this same function unbounded.
            enforcement = await run_capacity_enforcement(
                conn, settings, client_factory,
            )
            capacity_moved = sum(
                t["merged"] + t["aged_out"] for t in enforcement.values()
            )
            summary["archived"] += capacity_moved
            summary["capacity_enforced"] = capacity_moved

            pairs = _select_contradiction_pairs(conn)
            audience_candidates = _select_audience_candidates(conn)
            if pairs or audience_candidates:
                if settings is None:
                    from jarvis.config import load_settings

                    settings = load_settings()
                classification = await _classify_batch(
                    pairs, audience_candidates, settings, client_factory,
                )
                applied = _apply_classification(
                    conn, pairs, classification["pairs"],
                    audience_candidates, classification["audiences"],
                    automated=os.environ.get("JARVIS_MEMORY_AUTOMATION_ENABLED", "false").lower()
                    in {"1", "true", "yes"},
                )
                summary["contradictions"] += applied["contradictions_queued"]
                summary["queued"] += (
                    applied["task_rule_queued"] + applied["implemented_queued"]
                )

            stale = run_stale_sweep(conn)
            summary["stale_archived"] = len(stale)

            expired = run_staging_expiry(conn)
            summary["staging_expired"] = len(expired)

            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — a sweep must never break the bot
        logger.exception("memory_sweep_failed")
        return summary

    logger.info(
        "memory_sweep archived=%d queued=%d contradictions=%d "
        "stale_archived=%d capacity_enforced=%d staging_expired=%d",
        summary["archived"], summary["queued"], summary["contradictions"],
        summary["stale_archived"], summary["capacity_enforced"],
        summary["staging_expired"],
    )
    return summary


def start_background_sweep(db_path: str | None = None) -> threading.Thread | None:
    """Fire run_sweep on a detached daemon thread. Called once at bot
    startup, beside the run-log prune and key-health probe
    (jarvis/bot/pipeline.py) — same pattern, same reason: a cleanup pass
    must never delay boot. Daemon so a hung model call can never keep the
    process alive at shutdown."""
    if not enabled():
        return None

    def _runner() -> None:
        try:
            asyncio.run(run_sweep(db_path=db_path))
        except Exception:  # noqa: BLE001
            logger.exception("memory_sweep_thread_failed")

    thread = threading.Thread(target=_runner, name="memory-sweep", daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------- #
# M5 — one-shot rein-in CLI
# --------------------------------------------------------------------- #


async def _run_enforce_cli() -> dict:
    """`python -m jarvis.memory_sweep --enforce` — runs the FULL capacity
    ladder immediately, ignoring SWEEP_MAX_ARCHIVES (that cap protects
    unattended boots; an explicit CLI invocation is attended). Answers
    M5's "can it be reined in from its current state?" in one supervised
    command, with every demotion reversible via `became`."""
    conn = get_conn()
    try:
        before = {
            tier: _tier_count(conn, tier) for tier in CAPACITY_CAPS
        }
        report = await run_capacity_enforcement(conn, ignore_boot_cap=True)
        conn.commit()
    finally:
        conn.close()

    print("Capacity enforcement — before -> after (cap):\n")
    for tier, r in report.items():
        line = (
            f"  {tier:<11} {r['before']:>3} -> {r['after']:>3}  "
            f"(cap {r['cap']}, merged {r['merged']}, aged-out {r['aged_out']})"
        )
        # W7 — a preference tier left over cap because the merge rung
        # couldn't run is not a quiet log line here; --enforce is an
        # attended, explicit invocation and the operator should see it.
        if tier == "preference" and r["after"] > r["cap"]:
            line += (
                f"  ⚠ still {r['after'] - r['cap']} over cap — no model "
                "available to merge; nothing was aged out"
            )
        print(line)
    total_before = sum(before.values())
    total_after = sum(r["after"] for r in report.values())
    print(f"\ntotal (capped tiers): {total_before} -> {total_after}")
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="python -m jarvis.memory_sweep")
    p.add_argument(
        "--enforce", action="store_true",
        help="run the full per-tier capacity enforcement ladder now, "
             "ignoring the per-boot archive cap (M5)",
    )
    args = p.parse_args(argv)

    if args.enforce:
        asyncio.run(_run_enforce_cli())
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
