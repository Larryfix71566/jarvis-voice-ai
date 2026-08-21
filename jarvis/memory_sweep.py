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

from openai import AsyncOpenAI

from jarvis.consolidate import propose_merges
from jarvis.db import get_conn, now_iso
from jarvis.memory import archive_fact, upsert_fact
from jarvis.procedures import _tokens

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
    client = (
        client_factory(settings)
        if client_factory is not None
        else AsyncOpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url,
        )
    )
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
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return _parse_classification(response.choices[0].message.content or "")


def _apply_classification(
    conn,
    pairs: list[tuple[dict, dict]],
    pair_verdicts: dict[frozenset, str],
    audience_candidates: list[dict],
    audiences: dict[str, str],
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
    }
    try:
        conn = get_conn(db_path)
        try:
            a1 = run_auto_consolidation(conn)
            summary["archived"] += len(a1["archived"])
            summary["queued"] += a1["queued"]

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
                )
                summary["contradictions"] += applied["contradictions_queued"]
                summary["queued"] += (
                    applied["task_rule_queued"] + applied["implemented_queued"]
                )

            stale = run_stale_sweep(conn)
            summary["stale_archived"] = len(stale)

            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — a sweep must never break the bot
        logger.exception("memory_sweep_failed")
        return summary

    logger.info(
        "memory_sweep archived=%d queued=%d contradictions=%d "
        "stale_archived=%d",
        summary["archived"], summary["queued"], summary["contradictions"],
        summary["stale_archived"],
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
