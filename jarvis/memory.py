"""Persistent memory (upgrade plan U2.5).

Two layers over the existing per-session ``conversations`` transcript log:

- **facts** — keyed, durable statements about the user and their world
  (``user.name``, ``user.preference.*``, ``project.*`` …). Upserted by key;
  newer information replaces older.
- **summary** — exactly one running summary row, rewritten after each
  processed session so older context compacts instead of growing forever.

The Supervisor prompt injects :func:`render_memory_context` at pipeline
build time, so every new session starts already knowing the user's name,
preferences, and what was previously discussed. After a session ends,
:func:`update_memory_from_session` reads that session's transcript and asks
the LLM for a strict-JSON memory update (new/changed facts + rewritten
summary). Memory is advisory context only — it can never trigger actions,
and a failure anywhere in this module must never break the voice pipeline
(every public function degrades to a safe empty result).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from typing import Any, Callable

from openai import AsyncOpenAI

from jarvis.config import Settings
from jarvis.db import get_conn, now_iso
from jarvis.sensitive import detect_financial
from jarvis.usage_ledger import record_completion, provider_from_base_url

logger = logging.getLogger(__name__)

MAX_FACT_CHARS = 200

# K1 (MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md) — memory tiers, by DURABILITY.
#
# The flat pool was the defect: measured 2026-08-18, the store held 180
# facts and ~14 reached the Supervisor, because 78 facts about Mortimer's
# own configuration competed for the same 30 slots as durable facts about
# Larry. Tiering does not raise the total budget — it decides who is
# allowed to compete for it.
#
#   identity   — name, location, timezone. NEVER dropped, and exempt from
#                the char budget: it is a handful of rows and losing them
#                is the worst failure this system has.
#   preference — how Larry wants to be worked with. Generous cap;
#                duplicates are K2 consolidation's job, not eviction's.
#   project    — current work and live context. Ages out normally.
#   system     — facts about Mortimer itself. EXCLUDED from the prompt by
#                default: re-derivable from the repo, and the single
#                biggest consumer of slots that belonged to real
#                preferences. Still stored, still visible in the console,
#                just not competing.
MEMORY_TIERS = ("identity", "preference", "project", "system")
CONTEXT_TIERS = ("identity", "preference", "project")  # system deliberately absent
DEFAULT_TIER = "project"  # unknown/legacy rows land in the middle, never identity

# M1/M2 (MORTIMER_MEMORY_CAPACITY_PLAN.md, 2026-08-21) — "live = injected"
# invariant: every live fact must reach the prompt, so over-capacity is a
# state jarvis.memory_sweep's capacity-enforcement ladder eliminates, not
# one this renderer papers over by silently dropping. These numbers are
# sized so a FULL store (every tier at its cap) fits inside
# MAX_CONTEXT_CHARS: 8ish identity + 30 preference + 8 project facts at the
# observed ~90 chars/fact is ~2,800 chars, comfortably under 3,000 — a
# prompt already ~10KB deep can afford that. The old flat MAX_FACTS = 30
# global cap is DELETED here: it overlapped with these per-tier caps (the
# combination is how the panel once showed an unexplainable "261 / 30"),
# and the per-tier numbers are now the one set of caps that matters.
# MAX_PREFERENCE_FACTS: 15 -> 30 (2026-08-31, Larry has >15 real standing
# preferences) -> 60 (2026-09-03, MORTIMER_OPTIMIZATION_PLAN.md Phase 4
# Rev 3.4 Stage A). The 30 cap was dropping 25 of 55 live preference facts
# from EVERY session — measured against Larry's real store — and the ones
# it dropped were his least-recently-UPDATED working-style preferences
# (user.style.status, user.style.approval, user.style.verification, ...),
# i.e. exactly the standing instructions that are stable BECAUSE they never
# need restating. The cap was originally a token-cost defence; since Phase 1
# the whole block sits inside the Supervisor's cached prefix and is rendered
# once per session, so the true cost of the 25 restored facts is ~700 cached
# tokens ~= $0.0003/session. What remains is a model-attention argument,
# which is a guess in both directions — so it is now instrumented instead of
# assumed (Stage A3's restated-fact rate) and revertible by this constant.
MAX_PREFERENCE_FACTS = 60
# Deliberately NOT raised: project is the growth tier (it accumulates a fact
# per active piece of work), and on-demand recall via the librarian's
# memory_search is what Phase 4 Stage B is for. Raising this one is how the
# prefix grows without bound.
MAX_PROJECT_FACTS = 8
MAX_SUMMARY_CHARS = 600
# 3000 -> 8000 (2026-08-31) -> 12000 (2026-09-03, Phase 4 Rev 3.4 Stage A).
# Load-bearing, not headroom-for-its-own-sake: measured against Larry's
# real store, raising MAX_PREFERENCE_FACTS alone renders 9,818 chars over
# 71 facts (~138 chars/fact) — the old 8,000 budget would have truncated
# it and silently re-imposed the cap A1 just lifted. Effect on the cached
# Supervisor prefix: memory block 6,269 -> 9,818 chars (1,567 -> 2,454
# approx tokens), whole prefix ~7,850 -> ~8,740 tokens, still far above
# Haiku 4.5's 4,096-token cache floor. Note the direction: this phase only
# ever GROWS the prefix, so the floor cannot be crossed from above — the
# risk it does carry is prompt-attention, which Stage A3 measures.
MAX_CONTEXT_CHARS = 12000
MAX_TRANSCRIPT_ROWS = 60
MAX_ROW_CHARS = 300

# Reliable-memory plan D5: names the timeout already used at every call site
# of update_memory_from_session (pipeline.py teardown, and the periodic
# MemorySweepWatcher — jarvis/bot/memory_watcher.py). Not a Settings field:
# this is an internal safety bound, not something a user needs to tune
# (mirrors CALL_TIMEOUT in jarvis/skills/registry.py).
MEMORY_EXTRACTION_TIMEOUT_S = 30

# U2.6 tendency learning: a behavioral pattern must be observed in this many
# distinct sessions before it is promoted to a user.style.* fact and starts
# shaping behavior. One odd session must never teach Jarvis a bad habit.
PROMOTE_AFTER = 3

EMPTY_CONTEXT = "(no memories yet)"

EXTRACTION_PROMPT = """You maintain the long-term memory of a personal AI assistant.
You are given the previous running summary (possibly empty) and the transcript
of one conversation session. Produce a memory update as STRICT JSON only:

{"facts": [{"key": "<dotted.key>", "value": "<one short statement>"}],
 "observations": [{"key": "user.style.<pattern>", "value": "<what was observed>"}],
 "summary": "<rewritten running summary, at most 500 characters>"}

Rules:
- Facts are durable, keyed statements worth remembering across sessions:
  the user's name, preferences, people, projects, standing decisions.
  Keys are lowercase dotted paths, e.g. "user.name", "user.preference.music",
  "project.jarvis". Resend a key with a new value to correct it.
- Anything the user EXPLICITLY states about how they want things done
  ("I prefer short answers", "stop doing that", "always ask me first")
  is a fact with a user.style.* key — record it immediately in facts,
  not observations. Explicit statements override everything inferred.
- Observations are INFERRED behavioral tendencies: how the user phrases
  requests, what they react well or badly to, formats they pick,
  pacing, tone. Keys are "user.style.<pattern>". Observations are
  evidence, not truth — record them even when unsure; they only become
  active after recurring across sessions.
- NEVER record facts or observations about the assistant's own capabilities,
  access rights, or restrictions (e.g. "cannot edit code", "no repository
  access"). Capabilities change with every software update; remembered
  restrictions become stale lies that contradict the current system prompt.
- Do NOT record one-off requests, small talk, or anything time-bound
  (that is what reminders and notes are for).
- The summary must stand alone: it replaces the previous summary, so carry
  forward anything still relevant and fold in this session's essentials.
- If the session contains nothing worth remembering, return
  {"facts": [], "observations": [], "summary": "<previous summary unchanged>"}.
- Output JSON only. No markdown, no commentary."""


# MORTIMER_OPTIMIZATION_PLAN.md Phase 2 kill switch. Default ON: the new
# per-exchange worker (jarvis/memory_extraction_worker.py +
# jarvis/memory_extraction.py) is authoritative for facts/observations,
# and this module's own extraction narrows to summary-only (see
# SUMMARY_ONLY_PROMPT and update_memory_from_session's
# extract_facts_and_observations parameter below) so the same session
# transcript is never re-derived into facts by two independent paths at
# once -- the exact near-duplicate-under-a-different-key mess Phase 2's
# novelty gate exists to prevent in the first place. Set to a falsy value
# (false/0/no/off) to roll back to pre-Phase-2 behavior instantly, with
# zero code change, if the new worker needs to be pulled.
def memory_extraction_v2_enabled() -> bool:
    raw = os.environ.get("JARVIS_MEMORY_EXTRACTION_V2", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


# Summary-only counterpart to EXTRACTION_PROMPT, used by
# update_memory_from_session when extract_facts_and_observations=False
# (Phase 2 kill switch ON) -- facts/observations extraction has moved to
# jarvis/memory_extraction.py's per-exchange path, but a running summary
# is inherently a whole-session digest, which only this whole-session
# path can produce. Always outputs an empty facts list (never omitted)
# so _parse_update's existing shape check (facts must be a list) keeps
# working unchanged -- one parser for both prompts, not a second one.
SUMMARY_ONLY_PROMPT = """You maintain a short running summary of an ongoing conversation between a
personal AI assistant and its user. You are given the previous running
summary (possibly empty) and the transcript of one conversation session.
Produce STRICT JSON only:

{"facts": [], "summary": "<rewritten running summary, at most 500 characters>"}

Rules:
- The summary must stand alone: it replaces the previous summary, so carry
  forward anything still relevant and fold in this session's essentials.
- Do not record durable facts here -- that extraction happens elsewhere;
  "facts" must always be the empty list.
- If the session contains nothing worth summarizing, return
  {"facts": [], "summary": "<previous summary unchanged>"}.
- Output JSON only. No markdown, no commentary."""


# Upgrade plan Phase 5b: injection/exfiltration scanning on memory writes.
#
# render_memory_context() output goes straight into the Supervisor's system
# prompt. Content reaches memories/observations via the extraction LLM,
# which reads full session transcripts — and those transcripts can contain
# text quoted verbatim from mcp_web search results, or anything the user
# read aloud from an untrusted source. Nothing screened that path before
# this phase.
#
# Hand-rolled patterns, not a maintained library: keeps dependencies at
# zero (the alternative outsources an adversarial, evolving pattern list to
# a package that itself becomes an attack surface), at the cost of being
# less comprehensive than a maintained scanner. Per the plan, adding a
# dependency on hermes-agent for this was explicitly rejected — its module
# paths are unstable across releases and this module must never import it.
# Revisit if false negatives become a real problem in practice.
#
# Weighted toward NOT over-blocking (plan risk note): patterns require
# fairly specific phrasing, not single trigger words, so ordinary facts
# about the user's preferences, projects, and people don't collide with
# them.

# Zero-width and bidirectional-override code points used to hide text from
# a human reader while an LLM still processes it (a known prompt-injection
# vector — e.g. hiding "ignore previous instructions" inside invisible
# characters around ordinary-looking text).
_DANGEROUS_UNICODE = frozenset(
    "​‌‍‎‏"  # zero-width space/joiners, LTR/RTL marks
    "‪‫‬‭‮"  # bidi embedding/override controls
    "⁠⁦⁧⁨⁩"  # word joiner, bidi isolates
    "﻿"                          # BOM / zero-width no-break space
)

# (compiled pattern, rejection reason) — matched case-insensitively against
# the whole text. Phrasing-based, not single keywords, to avoid flagging
# ordinary facts that happen to contain a word like "system" or "ignore".
_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore (all |any )?(the )?(previous|prior|above) instructions"),
     "prompt-injection pattern (ignore previous instructions)"),
    (re.compile(r"disregard (all |any )?(the )?(previous|prior|above)"),
     "prompt-injection pattern (disregard previous)"),
    (re.compile(r"\bnew (system )?instructions?\s*:"),
     "prompt-injection pattern (new instructions:)"),
    (re.compile(r"\byou are now\b.{0,40}\b(a|an)\b"),
     "prompt-injection pattern (role override)"),
    (re.compile(r"reveal (your |the )?(system prompt|instructions|hidden prompt)"),
     "prompt-injection pattern (reveal system prompt)"),
    (re.compile(r"print (your |the )?(system prompt|instructions)"),
     "prompt-injection pattern (print system prompt)"),
    (re.compile(r"\bforget (everything|all)( you know)?\b"),
     "prompt-injection pattern (forget everything)"),
]

# (compiled pattern, rejection reason) — matched case-sensitively (secrets
# have specific casing/format); these flag exfiltration content rather than
# ordinary facts.
_CREDENTIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-(ant-)?[A-Za-z0-9_-]{20,}"), "possible API key literal"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "possible AWS access key literal"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "possible GitHub token literal"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "possible private key literal"),
    (re.compile(r"\bsend (this|the following|it|that) to https?://"),
     "exfiltration pattern (send to URL)"),
    (re.compile(r"https?://\S+[?&](token|api[_-]?key|password|secret)="),
     "exfiltration pattern (credential in URL)"),
]


# Capability-claim firewall (render-time counterpart to EXTRACTION_PROMPT's
# "NEVER record facts about the assistant's own capabilities" rule).
#
# The prompt rule is advisory: it asks the extraction LLM not to write these
# facts. This is the enforcement half — even if a claim gets stored (by an
# older build, a model that ignored the instruction, or a manual write), it
# never reaches the Supervisor's system prompt. That matters because a
# remembered restriction becomes a stale lie the moment the software gains
# the capability, and the Supervisor will then repeat it to the user with
# full confidence.
#
# Deliberately narrow, requiring BOTH conditions:
#   1. the KEY is scoped to the assistant, not the user
#   2. the VALUE asserts an inability
# A user.* fact is never filtered, however it is phrased — "user.style.honesty:
# Cannot stand evasive answers" is a real preference about the user and must
# survive. Filtering on the value alone would eat it.

_ASSISTANT_KEY_PREFIXES = ("mortimer.", "assistant.", "jarvis.")

_LIMITATION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\bcan(?:no|')?t\b"),
    re.compile(r"\bcannot\b"),
    re.compile(r"\bunable to\b"),
    re.compile(r"\bno access\b"),
    re.compile(r"\bnot able to\b"),
    re.compile(r"\bdoes not have\b"),
    re.compile(r"\bdoesn't have\b"),
    re.compile(r"\blacks? (?:the )?(?:ability|access|permission)\b"),
    re.compile(r"\bis not allowed\b"),
    re.compile(r"\bhas no\b"),
)


# Volatile-state firewall (Larry 2026-08-18): "these were never the intent
# of the memory function in the first place and should not have been
# saved."
#
# The store had accumulated `project.mortimer.branch.current:
# "feat/plan-review-and-docs, 19 commits ahead of main"`,
# `"47 uncommitted files"`, `"Main branch, 32 files modified"` — all true
# once, all false within hours, and none of them re-checked because memory
# has no expiry. Worse, they are re-derivable on demand: `git status`
# answers them correctly every time, so storing a snapshot can only ever
# be wrong more often than asking.
#
# Rejected at WRITE time rather than filtered at read time, because a fact
# that should never exist should not occupy a row. Prompt guidance alone
# would be a wish — this is its mechanical backstop, matching the Golden
# Rules discipline in jarvis/prompts.py.
# NB (2026-08-18, caught on the first real run): the first version of the
# third pattern was `\d+\+?\s+(?:un)?committed`, which also matched
# "Phase 1 committed" — a DECISION, not a snapshot — and deleted two facts
# it should have kept. Every pattern below now requires a countable NOUN
# ("files", "commits") next to the number, never a bare participle, so
# progress notes survive and only readings-that-expire are rejected.
_VOLATILE_PATTERNS = (
    re.compile(r"\b\d+\+?\s+uncommitted\b"),
    re.compile(r"\buncommitted\s+files?\b"),
    re.compile(r"\b\d+\+?\s+(?:modified|changed|staged|untracked)\s+files?\b"),
    re.compile(r"\b\d+\+?\s+files?\s+(?:modified|changed|staged|uncommitted)\b"),
    re.compile(r"\bcommits?\s+(?:ahead|behind)\b"),
    re.compile(r"\b\d+\s+commits\b"),  # plural only: "1 committed" is not this
    re.compile(r"\bhead\s+(?:is\s+)?at\s+[0-9a-f]{7,}\b"),
)

# Keys whose whole purpose is to snapshot something git already knows.
_VOLATILE_KEY_HINTS = (
    "repo_state", "repo.state", "current_branch", "branch.current",
    "uncommitted", "working_tree", "git_status",
)


def _is_volatile_state(key: str, value: str) -> bool:
    """True when a fact snapshots transient repo/system state.

    Deliberately narrow: it matches counts-of-things and branch positions,
    not ordinary project facts. "Feature branch X created; Phase 1
    committed" describes a decision and is kept; "19 commits ahead of
    main" is a reading that expires and is not. Pure and total; never
    raises.
    """
    key_l = (key or "").strip().lower()
    if any(h in key_l for h in _VOLATILE_KEY_HINTS):
        return True
    value_l = (value or "").lower()
    return any(p.search(value_l) for p in _VOLATILE_PATTERNS)


def _is_capability_claim(key: str, value: str) -> bool:
    """True when a stored fact asserts a limitation of the assistant itself.

    Requires an assistant-scoped key AND a limitation phrase in the value —
    see the note above for why both, and why user.* is never matched.
    Pure and total; never raises.
    """
    if not key:
        return False
    key_l = key.strip().lower()
    if not key_l.startswith(_ASSISTANT_KEY_PREFIXES):
        return False
    value_l = (value or "").lower()
    return any(p.search(value_l) for p in _LIMITATION_PATTERNS)


# T4a K3 — the memory gate's financial refusal. This is a LOG/DIAGNOSTIC
# reason in the style of the _CREDENTIAL_PATTERNS reasons above, not spoken
# copy: jarvis/bot/remember_tool.py:19-22 (D8) forbids surfacing a scan
# rejection reason to the LLM, which would otherwise rewrite the content to
# evade the filter. T4b replaces the refusal with a route to the tier.
FINANCIAL_REJECTION = "financial detail — not stored (sensitive tier not yet enabled)"


def scan_memory_content(text: str) -> str | None:
    """Return a short rejection reason if `text` is unsafe to persist as
    memory (prompt injection, credential/exfiltration pattern, financial
    detail, or invisible Unicode), else None. Pure and total — never raises."""
    if not text:
        return None
    if any(ch in _DANGEROUS_UNICODE for ch in text):
        return "invisible or bidirectional unicode detected"
    for pattern, reason in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            return reason
    if detect_financial(text) is not None:
        return FINANCIAL_REJECTION
    lowered = text.lower()
    for pattern, reason in _INJECTION_PATTERNS:
        if pattern.search(lowered):
            return reason
    return None


def render_memory_context(
    conn: sqlite3.Connection | None = None, *, stats: dict | None = None,
) -> str:
    """Build the memory block for the Supervisor system prompt.

    `stats` (Phase 4 Rev 3.4 Stage A2): an optional dict, filled in place
    with what this render actually produced —
    {"chars", "approx_tokens", "facts", "dropped_tier_cap",
     "dropped_char_budget", "summary_dropped"} — from counts the function
    already computes for its warnings below. Keyword-only and optional so
    the three existing call sites (bot/pipeline.py, agents/supervisor.py,
    admin/server.py) are unaffected; pipeline.py passes one and logs it, so
    the size of the cached prefix's memory half is visible against Haiku's
    4,096-token cache floor without reading warnings out of a log.

    Facts first (most actionable), then the running summary, total size
    capped at MAX_CONTEXT_CHARS. Returns EMPTY_CONTEXT when nothing is
    stored or when the read fails.

    Phase 5c capacity policy — prioritization, not pure recency: facts
    keyed ``user.*`` (explicit statements the user made about themselves —
    name, preferences, standing instructions) are ordered ahead of every
    other fact type, most-recent-first within each tier. This means a
    ``user.*`` fact survives the per-tier cap even if it is older than a
    flood of less-important facts recorded since. Chosen over consolidation
    (would require an EXTRACTION_PROMPT change -> routing eval) and pure
    surfacing (no prevention, only visibility — that piece lives in the
    Phase 5e memory panel instead). Every truncation point below is logged,
    never silent — this is the failure mode the plan calls out as the worst
    of the five identified in the memory system.
    """
    own_connection = conn is None
    conn = conn or get_conn()
    if stats is not None:
        # Populated up front so an early return (read failure / empty store)
        # still leaves the caller with a well-formed dict rather than a
        # half-filled one it has to guard every key of.
        stats.update({
            "chars": len(EMPTY_CONTEXT), "approx_tokens": len(EMPTY_CONTEXT) // 4,
            "facts": 0, "dropped_tier_cap": 0, "dropped_char_budget": 0,
            "summary_dropped": False,
        })
    try:
        # K1: order by tier rank first, then recency within the tier.
        # COALESCE covers pre-0012 rows and anything written before the
        # writer learned about tiers — they behave as 'project'.
        #
        # A5 (MORTIMER_MEMORY_AUTOCONSOLIDATION_PLAN.md, Larry 2026-08-20):
        # audience segmentation. A fact classified 'task-rule' or
        # 'implemented' by the sweep's LLM pass belongs in a sub-agent's
        # workflow prompt or nowhere, not here — but only once a human has
        # confirmed the conversion (A3's review queue). NULL/'interaction'
        # is the fail-open default: an unclassified fact keeps reaching
        # the prompt rather than silently vanishing while it waits for the
        # next sweep, which would be the worse failure.
        fact_rows = conn.execute(
            "SELECT key, content, COALESCE(tier, ?) AS tier FROM memories "
            "WHERE kind = 'fact' AND archived_at IS NULL "
            "AND COALESCE(tier, ?) IN (?, ?, ?) "
            "AND COALESCE(audience, 'interaction') = 'interaction' "
            "ORDER BY CASE COALESCE(tier, ?) "
            "  WHEN 'identity' THEN 0 WHEN 'preference' THEN 1 ELSE 2 END, "
            "updated_at DESC",
            (DEFAULT_TIER, DEFAULT_TIER, *CONTEXT_TIERS, DEFAULT_TIER),
        ).fetchall()
        summary_row = conn.execute(
            "SELECT content FROM memories WHERE kind = 'summary' "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    except Exception:  # noqa: BLE001 — memory must never break the pipeline
        logger.exception("memory_context_read_failed")
        return EMPTY_CONTEXT
    finally:
        if own_connection:
            conn.close()

    # Capability-claim firewall: drop assistant self-limitation facts before
    # anything else, so a stale "cannot edit code" can never reach the
    # Supervisor prompt. Applied before the per-tier cap so a filtered fact
    # does not consume a slot a real fact could have used.
    kept_rows = []
    firewalled: list[str] = []
    for row in fact_rows:
        if _is_capability_claim(row["key"], row["content"]):
            firewalled.append(row["key"])
        else:
            kept_rows.append(row)
    if firewalled:
        logger.warning(
            "memory_context_facts_dropped reason=capability_claim count=%d keys=%s",
            len(firewalled), firewalled[:10],
        )
    fact_rows = kept_rows

    # K1: cap PER TIER, not across the whole pool. identity has no cap —
    # it is small and irreplaceable. A drop is still always logged, with
    # the tier named, so "what fell out" stays answerable.
    per_tier_cap = {"preference": MAX_PREFERENCE_FACTS, "project": MAX_PROJECT_FACTS}
    seen: dict[str, int] = {}
    capped_rows = []
    tier_dropped: list[str] = []
    for row in fact_rows:
        tier = row["tier"] or DEFAULT_TIER
        seen[tier] = seen.get(tier, 0) + 1
        cap = per_tier_cap.get(tier)
        if cap is not None and seen[tier] > cap:
            tier_dropped.append(f"{tier}:{row['key']}")
            continue
        capped_rows.append(row)
    if tier_dropped:
        logger.warning(
            "memory_context_facts_dropped reason=tier_cap count=%d keys=%s",
            len(tier_dropped), tier_dropped[:10],
        )
    if stats is not None:
        stats["dropped_tier_cap"] = len(tier_dropped)

    lines: list[str] = []
    budget_dropped: list[str] = []
    for i, row in enumerate(capped_rows):
        line = f"- {row['key']}: {row['content'][:MAX_FACT_CHARS]}"
        # K1: identity is exempt — it is ordered first and is a handful of
        # rows, and silently losing the user's name or location to a char
        # budget is the worst outcome this function can produce.
        if (row["tier"] or DEFAULT_TIER) != "identity" and (
            sum(len(l) for l in lines) + len(line) > MAX_CONTEXT_CHARS
        ):
            budget_dropped = [r["key"] for r in capped_rows[i:]]
            break
        lines.append(line)
    if budget_dropped:
        logger.warning(
            "memory_context_facts_dropped reason=char_budget count=%d keys=%s",
            len(budget_dropped), budget_dropped[:10],
        )
    if stats is not None:
        stats["dropped_char_budget"] = len(budget_dropped)
        stats["facts"] = len(lines)

    if summary_row is not None:
        summary = summary_row["content"][:MAX_SUMMARY_CHARS]
        remaining = MAX_CONTEXT_CHARS - sum(len(l) for l in lines)
        if remaining > 80:
            lines.append(f"Previously discussed: {summary[:remaining]}")
        else:
            logger.warning("memory_context_summary_dropped reason=char_budget")
            if stats is not None:
                stats["summary_dropped"] = True
    rendered = "\n".join(lines) if lines else EMPTY_CONTEXT
    if stats is not None:
        stats["chars"] = len(rendered)
        # //4 is the same rough chars-per-token rule the plan's own prefix
        # estimates use; this is a watch number, never a billing number.
        stats["approx_tokens"] = len(rendered) // 4
    return rendered


def archive_fact(conn, key: str, became: str) -> bool:
    """K6.3 — retire a fact WITHOUT destroying it.

    `became` records what it turned into ("workflow:research-first",
    "deleted:stale") so a misclassification is reversible by reading the
    row rather than reconstructing text from a console transcript. Use
    this for every conversion; `delete_fact` remains for genuine garbage
    the user has explicitly identified.
    """
    cur = conn.execute(
        "UPDATE memories SET archived_at = ?, became = ? "
        "WHERE key = ? AND kind = 'fact' AND archived_at IS NULL",
        (now_iso(), became, key),
    )
    return cur.rowcount > 0


MAX_SEARCH_RESULTS = 25


def search_facts(
    conn: sqlite3.Connection | None, query: str, limit: int = 10
) -> list[dict]:
    """M6 (MORTIMER_MEMORY_CAPACITY_PLAN.md) — the recall path for demoted
    facts. Aggressive per-tier capping (M2) and system-tier archive-on-
    sight (M4) are only safe if nothing becomes unreachable; this is
    Hermes' "don't inject what you can look up" discipline applied to
    Mortimer's own fact store, and mcp-memory's `memory_search` tool is
    its voice-facing surface.

    LIKE over key+content, ACROSS live and archived facts — an archived
    fact is still fully searchable, which is the whole point of archiving
    instead of deleting. Deliberately LIKE, not FTS5: the memories table
    is small (hundreds of rows, not the conversations table's history),
    so a virtual table + triggers here would be over-engineering.
    Bounded by MAX_SEARCH_RESULTS regardless of caller-requested `limit`.
    Pure and total for a bad/empty query — returns []."""
    query = (query or "").strip()
    if not query:
        return []
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        limit = max(1, min(int(limit), MAX_SEARCH_RESULTS))
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT key, content, COALESCE(tier, 'project') AS tier, "
            "updated_at, (archived_at IS NOT NULL) AS archived "
            "FROM memories WHERE kind = 'fact' "
            "AND (key LIKE ? OR content LIKE ?) "
            "ORDER BY archived_at IS NOT NULL, updated_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [
            {
                "key": r["key"],
                "content": r["content"],
                "tier": r["tier"],
                "updated_at": r["updated_at"],
                "archived": bool(r["archived"]),
            }
            for r in rows
        ]
    finally:
        if own_connection:
            conn.close()


def infer_tier(key: str) -> str:
    """K1 — which tier a fact key belongs to.

    MUST stay in agreement with migration 0012's backfill in jarvis/db.py:
    that migration classified the rows that already existed, this
    classifies every row written afterwards, and a disagreement would mean
    a fact's tier depends on whether it predates the migration. Same
    conservative bias: anything unrecognized becomes DEFAULT_TIER
    ('project'), never 'identity' (which is never evicted) and never
    'system' (which is hidden from the prompt) — a misclassification must
    not be able to pin junk forever or silently hide something real.
    """
    k = (key or "").strip().lower()
    if (".mortimer." in k or k.startswith("mortimer.")
            or ".jarvis." in k or k.startswith("jarvis.")
            or ".system." in k or k.startswith("system.")):
        return "system"
    if (k == "user.name" or k.startswith("user.identity.")
            or k.startswith("user.location") or k.startswith("user.timezone")
            or k.startswith("user.contact.")):
        return "identity"
    if (k.startswith("user.preference.") or k.startswith("user.style.")
            or k.startswith("user.frustration")):
        return "preference"
    return DEFAULT_TIER


def upsert_fact(
    conn: sqlite3.Connection, key: str, value: str, session_id: str | None
) -> None:
    """Insert or replace one keyed fact. Rejects and logs (never raises)
    if the key or value trips the Phase 5b content scan."""
    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=fact key=%s reason=%s session=%s",
            key, reason, session_id,
        )
        return
    if _is_volatile_state(key, value):
        logger.warning(
            "memory_write_rejected kind=fact key=%s reason=volatile_state session=%s",
            key, session_id,
        )
        return
    now = now_iso()
    conn.execute(
        "INSERT INTO memories (kind, key, content, source_session_id, "
        "created_at, updated_at, tier) VALUES ('fact', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(key) WHERE kind = 'fact' "
        "DO UPDATE SET content = excluded.content, "
        "source_session_id = excluded.source_session_id, "
        "updated_at = excluded.updated_at, "
        "tier = COALESCE(memories.tier, excluded.tier)",
        (key, value[:MAX_FACT_CHARS], session_id, now, now, infer_tier(key)),
    )


def set_summary(
    conn: sqlite3.Connection, summary: str, session_id: str | None
) -> None:
    """Rewrite the single running-summary row. Rejects and logs (never
    raises) if the summary trips the Phase 5b content scan — the previous
    summary is left in place rather than being overwritten with unsafe
    content."""
    reason = scan_memory_content(summary)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=summary reason=%s session=%s",
            reason, session_id,
        )
        return
    now = now_iso()
    existing = conn.execute(
        "SELECT id FROM memories WHERE kind = 'summary' LIMIT 1"
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO memories (kind, key, content, source_session_id, "
            "created_at, updated_at) VALUES ('summary', NULL, ?, ?, ?, ?)",
            (summary[:MAX_SUMMARY_CHARS], session_id, now, now),
        )
    else:
        conn.execute(
            "UPDATE memories SET content = ?, source_session_id = ?, "
            "updated_at = ? WHERE id = ?",
            (summary[:MAX_SUMMARY_CHARS], session_id, now, existing["id"]),
        )


def add_observation(
    conn: sqlite3.Connection, key: str, value: str, session_id: str | None
) -> None:
    """Record one observed instance of an inferred behavioral tendency.
    Rejects and logs (never raises) if the key or value trips the Phase 5b
    content scan."""
    reason = scan_memory_content(key) or scan_memory_content(value)
    if reason is not None:
        logger.warning(
            "memory_write_rejected kind=observation key=%s reason=%s "
            "session=%s", key, reason, session_id,
        )
        return
    conn.execute(
        "INSERT INTO observations (key, content, source_session_id, "
        "created_at) VALUES (?, ?, ?, ?)",
        (key, value[:MAX_FACT_CHARS], session_id, now_iso()),
    )


def promote_observations(conn: sqlite3.Connection) -> list[str]:
    """Promote tendencies with enough evidence to user.style.* facts.

    A pattern promotes when its key has at least PROMOTE_AFTER observations
    from DISTINCT sessions. Promotion can only CREATE a fact — it never
    overwrites one. Once a fact exists for a key (typically from an explicit
    user statement), only another explicit statement may change it; inferred
    evidence never clobbers what the user actually said.
    """
    rows = conn.execute(
        "SELECT key, COUNT(DISTINCT source_session_id) AS sessions "
        "FROM observations GROUP BY key"
    ).fetchall()
    promoted: list[str] = []
    for row in rows:
        if row["sessions"] < PROMOTE_AFTER:
            continue
        fact = conn.execute(
            "SELECT 1 FROM memories WHERE kind = 'fact' AND key = ?",
            (row["key"],),
        ).fetchone()
        if fact is not None:
            continue  # explicit fact stands; inference never overwrites it
        latest = conn.execute(
            "SELECT content FROM observations WHERE key = ? "
            "ORDER BY id DESC LIMIT 1",
            (row["key"],),
        ).fetchone()
        upsert_fact(conn, row["key"], latest["content"], None)
        promoted.append(row["key"])
    return promoted


# Upgrade plan Phase 5e: read helpers for the admin sidecar's memory panel.
# Unlike render_memory_context (capped, prioritized, meant for the
# Supervisor's prompt), these are uncapped/unfiltered — the panel is meant
# to show everything so the user can actually audit and correct what
# Mortimer has learned, not just what fit in this turn's context budget.


def list_facts(conn: sqlite3.Connection | None = None) -> list[dict]:
    """All facts, most-recently-updated first. Uncapped (contrast with
    render_memory_context's per-tier caps) — the panel shows everything."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT key, content, source_session_id, updated_at, "
            "COALESCE(tier, 'project') AS tier, "
            "COALESCE(audience, 'interaction') AS audience "
            "FROM memories WHERE kind = 'fact' AND archived_at IS NULL "
            "ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if own_connection:
            conn.close()


def get_summary_text(conn: sqlite3.Connection | None = None) -> str:
    """The current running summary, or '' if none exists yet."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        row = conn.execute(
            "SELECT content FROM memories WHERE kind = 'summary' "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return row["content"] if row is not None else ""
    finally:
        if own_connection:
            conn.close()


def list_observation_groups(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Observed tendencies grouped by key, with distinct-session evidence
    counts and promotion status. Mirrors promote_observations' own grouping
    query exactly, so the panel's "N/PROMOTE_AFTER sessions" readout can
    never disagree with what actually triggers promotion."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT key, COUNT(DISTINCT source_session_id) AS sessions "
            "FROM observations GROUP BY key ORDER BY sessions DESC, key"
        ).fetchall()
        groups: list[dict] = []
        for row in rows:
            latest = conn.execute(
                "SELECT content FROM observations WHERE key = ? "
                "ORDER BY id DESC LIMIT 1",
                (row["key"],),
            ).fetchone()
            promoted = conn.execute(
                "SELECT 1 FROM memories WHERE kind = 'fact' AND key = ?",
                (row["key"],),
            ).fetchone() is not None
            groups.append({
                "key": row["key"],
                "sessions": row["sessions"],
                "promote_after": PROMOTE_AFTER,
                "latest_content": latest["content"] if latest else "",
                "promoted": promoted,
            })
        return groups
    finally:
        if own_connection:
            conn.close()


def memory_usage(conn: sqlite3.Connection | None = None) -> dict:
    """Capacity readout pairing with K1's per-tier caps (M2,
    MORTIMER_MEMORY_CAPACITY_PLAN.md) — how close each capped tier is to
    the cap that jarvis.memory_sweep's enforcement ladder exists to hold.

    Replaces the old single flat `fact_count`/`max_facts`/`over_capacity`
    triple (which compared the WHOLE store, across all tiers, against one
    global MAX_FACTS — the thing that produced an unexplainable "261 / 30"
    reading once tiering existed but capacity policy hadn't caught up).
    `over_capacity` is now true only when a CAPPED tier (preference,
    project) exceeds its own cap — identity is never capped and system is
    reported for visibility only, matching CONTEXT_TIERS."""
    own_connection = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT COALESCE(tier, ?) AS tier, COUNT(*) AS n FROM memories "
            "WHERE kind = 'fact' AND archived_at IS NULL GROUP BY 1",
            (DEFAULT_TIER,),
        ).fetchall()
        # MORTIMER_OPTIMIZATION_PLAN.md Phase 4 Rev 3.4 Stage A3 — the
        # recall-failure proxy, as a RATE the memory panel can show:
        # restated known facts per session over the last 7 days. Both
        # halves are windowed the same way so the ratio means something;
        # sessions come from `conversations` because that is what counts a
        # session whether or not it produced any memory write at all.
        # Tolerant of a pre-0019 database (the table is created by the
        # migration, which the panel's process may not have run yet).
        try:
            restated_7d = conn.execute(
                "SELECT COUNT(*) FROM memory_recall_events "
                "WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
            sessions_7d = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM conversations "
                "WHERE created_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
        except Exception:  # noqa: BLE001 — a readout must not break the panel
            restated_7d, sessions_7d = 0, 0
    finally:
        if own_connection:
            conn.close()
    tiers = {t: 0 for t in MEMORY_TIERS}
    for row in rows:
        tiers[row["tier"]] = row["n"]
    fact_count = sum(tiers.values())
    caps = {"preference": MAX_PREFERENCE_FACTS, "project": MAX_PROJECT_FACTS}
    over_capacity = any(tiers[t] > cap for t, cap in caps.items())
    return {
        "fact_count": fact_count,
        "tiers": tiers,
        "caps": caps,
        "max_context_chars": MAX_CONTEXT_CHARS,
        "over_capacity": over_capacity,
        # Stage A3. The gate for Phase 4 Stage B is restated_7d/sessions_7d
        # >= 0.1; the raw pair is reported rather than the quotient so a
        # low-session week cannot make the ratio look alarming on its own.
        "restated_7d": restated_7d,
        "sessions_7d": sessions_7d,
    }


def delete_fact(conn: sqlite3.Connection, key: str) -> bool:
    """Forget one fact and its accumulated observations ('forget that' path)."""
    cur = conn.execute(
        "DELETE FROM memories WHERE kind = 'fact' AND key = ?", (key,)
    )
    conn.execute("DELETE FROM observations WHERE key = ?", (key,))
    return cur.rowcount > 0


def _session_transcript(
    conn: sqlite3.Connection, session_id: str
) -> tuple[list[sqlite3.Row], str]:
    """(recent rows for the session, previous summary or '')."""
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (session_id, MAX_TRANSCRIPT_ROWS),
    ).fetchall()
    rows.reverse()
    summary_row = conn.execute(
        "SELECT content FROM memories WHERE kind = 'summary' "
        "ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    return rows, (summary_row["content"] if summary_row else "")


def _parse_update(text: str) -> dict | None:
    """Strict-JSON parse with a markdown-fence fallback. None on failure."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    facts = data.get("facts")
    summary = data.get("summary")
    if not isinstance(facts, list) or not isinstance(summary, str):
        return None
    clean_facts = [
        (str(f["key"]).strip(), str(f["value"]).strip())
        for f in facts
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ]
    observations = data.get("observations") or []
    clean_observations = [
        (str(o["key"]).strip(), str(o["value"]).strip())
        for o in observations
        if isinstance(o, dict) and o.get("key") and o.get("value")
    ]
    return {
        "facts": clean_facts,
        "observations": clean_observations,
        "summary": summary.strip(),
    }


async def update_memory_from_session(
    settings: Settings,
    session_id: str,
    client_factory: Callable[[Settings], Any] | None = None,
    extract_facts_and_observations: bool = True,
) -> bool:
    """Fold one finished session into long-term memory. Never raises.

    Returns True when a parsed update was applied. Skips sessions with no
    user utterances (nothing to learn) and any failure mode (LLM error,
    malformed JSON) leaves memory untouched.

    extract_facts_and_observations (Phase 2 kill switch, default True):
    every existing call site and every existing test relies on this
    default to keep behaving exactly as before. The two live call sites
    (jarvis/bot/memory_watcher.py's MemorySweepWatcher.tick_once and
    jarvis/bot/pipeline.py's session-teardown fold-in) instead pass
    `not memory_extraction_v2_enabled()` explicitly, so this function
    itself never reads the env var -- one place (memory_extraction_v2_
    enabled) decides the policy, this parameter just carries it in.
    False switches to SUMMARY_ONLY_PROMPT and skips the upsert_fact/
    add_observation/promote_observations writes below; the summary
    still regenerates on the same whole-session cadence as always.
    """
    try:
        with get_conn() as conn:
            rows, previous_summary = _session_transcript(conn, session_id)
        if not any(r["role"] == "user" for r in rows):
            return False

        transcript = "\n".join(
            f"{r['role'].upper()}: {r['content'][:MAX_ROW_CHARS]}" for r in rows
        )
        client = (
            client_factory(settings)
            if client_factory is not None
            else AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        )
        prompt = EXTRACTION_PROMPT if extract_facts_and_observations else SUMMARY_ONLY_PROMPT
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
                        f"Session transcript:\n{transcript}"
                    ),
                },
            ],
        )
        try:
            record_completion(
                rung="memory_extraction",
                provider=provider_from_base_url(str(client.base_url)),
                model=settings.openai_model,
                response=response,
                session_id=session_id,
            )
        except Exception:
            pass
        update = _parse_update(response.choices[0].message.content or "")
        if update is None:
            logger.warning("memory_update_unparseable session=%s", session_id)
            return False

        with get_conn() as conn:
            promoted: list[str] = []
            if extract_facts_and_observations:
                for key, value in update["facts"]:
                    upsert_fact(conn, key, value, session_id)
                for key, value in update["observations"]:
                    add_observation(conn, key, value, session_id)
                promoted = promote_observations(conn)
            if update["summary"]:
                set_summary(conn, update["summary"], session_id)
        logger.info(
            "memory_updated session=%s facts=%d observations=%d promoted=%s "
            "v2_writes_skipped=%s",
            session_id, len(update["facts"]), len(update["observations"]),
            promoted, not extract_facts_and_observations,
        )
        return True
    except Exception:  # noqa: BLE001 — memory must never break the pipeline
        logger.exception("memory_update_failed session=%s", session_id)
        return False
