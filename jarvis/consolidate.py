"""Memory consolidation — K2 of MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md.

The problem this exists for, measured 2026-08-18: Larry's store held 180
facts and ~14 reached the Supervisor. K1's tiering removed 78 system
facts from the competition, but the store still contains three separate
facts meaning "Larry is concise" (`user.preference.verbosity`,
`user.style.conciseness`, `user.style.minimal_explanation`) and four
about plan display. Nothing ever revisits a fact once written, so the
store grows monotonically and duplicates crowd out distinct preferences.

Two rules, both learned the hard way, are enforced here by construction:

1. **Never merge across tiers.** A `preference` and a `project` fact that
   happen to share words are not the same fact, and identity is never a
   merge target at all.

2. **Never lose content that doesn't match the key's topic.** During the
   2026-08-18 cleanup, `user.location: "Spartanburg (prefers Fahrenheit
   for all displays)"` held a *preference* inside a *location* fact —
   deleting or merging by key similarity alone would have silently eaten
   it. `mixed_content_warning()` flags exactly that shape so a human sees
   it before anything is written.

Detection is pure and testable: no DB, no network, no model. Nothing in
this module writes — `propose_merges()` returns proposals and the caller
decides. That is D2's "manual first" recommendation, chosen deliberately
after a working-tree revert cost a day's work: an automatic rewriter that
is subtly wrong is far more expensive than one Larry runs and reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ONE tokenizer and ONE overlap scorer for the whole codebase — reused
# from jarvis.procedures rather than reimplemented. CLAUDE.md's rule:
# "one implementation, not a second one". If the matching behaviour ever
# needs to differ here, that is a reason to parameterise the shared
# function, not to fork it.
from jarvis.procedures import _overlap_score, _tokens

# Above this content-token overlap, two facts in the same tier are
# proposed as duplicates. Deliberately high: a false merge destroys
# information, a missed merge only wastes a slot. Asymmetric costs, so
# the threshold sits on the safe side rather than at the F1 optimum.
DUPLICATE_THRESHOLD = 0.6

# Tiers that may be consolidated at all. `identity` is excluded: it is a
# handful of irreplaceable rows, and today's cleanup showed those rows
# are exactly where hand-review belongs.
CONSOLIDATABLE_TIERS = ("preference", "project", "system")

# Minimum SHARED tokens for two facts to be considered duplicates.
#
# Found on Larry's real store: the symmetric content scorer divides by the
# SMALLER token set, so a one-token fact matches anything containing that
# word at 1.0. `user.voice.default: "Jarvis"` scored 1.0 against
# `user.location.path: "/Users/larryfix/Documents/jarvis-voice-ai-clean/"`
# because the PATH contains "jarvis"; `user.temperature_unit:
# "Fahrenheit"` scored 1.0 against a Celsius BUG REPORT.
#
# A key-similarity guard was tried first and rejected: it removed those
# false positives but also blocked the main use case, since
# `user.style.conciseness` and `user.preference.verbosity` are genuine
# duplicates whose key segments share nothing. Requiring two shared
# CONTENT tokens targets the actual cause — a single coincidental word —
# without penalising differently-named keys. One-token facts therefore
# never cluster, which is correct: "Jarvis" alone is too ambiguous to
# merge on.
MIN_SHARED_TOKENS = 2

# Words whose presence signals a fact is carrying a topic its key does
# not advertise — the Fahrenheit-inside-a-location case.
_TOPIC_MARKERS = {
    "preference": ("prefer", "prefers", "wants", "likes", "always", "never"),
    "units": ("fahrenheit", "celsius", "metric", "imperial"),
    "schedule": ("morning", "evening", "daily", "weekly"),
}


@dataclass
class MergeProposal:
    """One cluster of facts that look like the same fact. Nothing is
    written until a human accepts it."""

    tier: str
    keys: list[str]
    contents: list[str]
    score: float
    warnings: list[str] = field(default_factory=list)

    @property
    def suggested_survivor(self) -> str:
        """The longest content is proposed as the survivor — it most
        likely carries the detail the shorter phrasings dropped. A
        suggestion only; the caller may choose any of `keys`."""
        return max(self.contents, key=len)


def mixed_content_warning(key: str, content: str) -> str | None:
    """Flag a fact whose CONTENT covers a topic its KEY does not.

    The worked example: key `user.location`, content "Spartanburg
    (prefers Fahrenheit for all displays)". Merging that cluster by key
    similarity would have thrown away a preference nobody was looking at.
    Returns a human-readable warning, or None.
    """
    k = (key or "").lower()
    c = (content or "").lower()
    for topic, markers in _TOPIC_MARKERS.items():
        if topic in k:
            continue  # the key already advertises this topic — fine
        if any(m in c for m in markers):
            return (
                f"{key} mentions {topic} ('{next(m for m in markers if m in c)}') "
                f"but its key does not — do not merge without preserving that"
            )
    return None


def propose_merges(
    facts: list[dict],
    threshold: float = DUPLICATE_THRESHOLD,
) -> list[MergeProposal]:
    """Cluster same-tier facts whose CONTENT overlaps above `threshold`.

    `facts` is a list of dicts with `key`, `content`, `tier`. Pure: no
    I/O, no model call.

    Clusters are CLIQUES, not connected components: every member must
    match every other member above `threshold`. The first cut used
    transitive closure (a~b, b~c => {a,b,c}) and on Larry's real store it
    chained 18 unrelated facts into one group — temperature units,
    answer length and permission-asking all merged because each shared
    generic words with the next. Chaining is how a merge tool destroys
    information, so it is excluded by construction.
    """
    proposals: list[MergeProposal] = []

    by_tier: dict[str, list[dict]] = {}
    for f in facts:
        tier = (f.get("tier") or "project").lower()
        if tier not in CONSOLIDATABLE_TIERS:
            continue  # identity and anything unknown are never auto-merged
        by_tier.setdefault(tier, []).append(f)

    for tier, rows in by_tier.items():
        toks = [_tokens(r.get("content", "")) for r in rows]
        n = len(rows)

        pair: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                sc = _overlap_score(toks[i], toks[j])
                if sc < threshold:
                    continue
                # A high ratio on one coincidental word is not a duplicate.
                if len(toks[i] & toks[j]) < MIN_SHARED_TOKENS:
                    continue
                pair[(i, j)] = sc

        def sim(i: int, j: int) -> float:
            return pair.get((i, j) if i < j else (j, i), 0.0)

        # Greedy cliques, strongest pair first. A candidate joins only if
        # it matches EVERY existing member — no chaining.
        used: set[int] = set()
        grouped: list[list[int]] = []
        for (i, j), _sc in sorted(pair.items(), key=lambda kv: -kv[1]):
            if i in used or j in used:
                continue
            members = [i, j]
            for k in range(n):
                if k in used or k in members:
                    continue
                if all(sim(k, m) >= threshold for m in members):
                    members.append(k)
            used.update(members)
            grouped.append(members)

        for members in grouped:
            if len(members) < 2:
                continue
            scores = [sim(a, b) for ai, a in enumerate(members)
                      for b in members[ai + 1:]]
            warnings = []
            for idx in members:
                w = mixed_content_warning(
                    rows[idx].get("key", ""), rows[idx].get("content", "")
                )
                if w:
                    warnings.append(w)
            proposals.append(
                MergeProposal(
                    tier=tier,
                    keys=[rows[i].get("key", "") for i in members],
                    contents=[rows[i].get("content", "") for i in members],
                    score=round(min(scores), 3) if scores else 0.0,
                    warnings=warnings,
                )
            )

    # Biggest clusters first — they free the most room.
    proposals.sort(key=lambda p: (-len(p.keys), p.tier))
    return proposals


def format_report(proposals: list[MergeProposal]) -> str:
    """Human-readable review output. Warnings are printed loudly because
    they mark the cases where an automatic merge would lose something."""
    if not proposals:
        return "No duplicate clusters found."
    out: list[str] = []
    total = sum(len(p.keys) - 1 for p in proposals)
    out.append(
        f"{len(proposals)} cluster(s); merging every one would free "
        f"{total} slot(s).\n"
    )
    for i, p in enumerate(proposals, 1):
        out.append(f"[{i}] tier={p.tier}  overlap>={p.score}  ({len(p.keys)} facts)")
        for k, c in zip(p.keys, p.contents):
            marker = "  keep>" if c == p.suggested_survivor else "       "
            out.append(f"{marker} {k}: {c[:90]}")
        for w in p.warnings:
            out.append(f"    !! {w}")
        out.append("")
    out.append("Nothing has been changed. Review, then delete the keys you")
    out.append("do not want with: python -m jarvis.consolidate --drop <key> ...")
    return "\n".join(out)


# --- CLI (review-only by default) ---------------------------------------


import argparse
import sys

from jarvis.consolidate import format_report, propose_merges
from jarvis.db import get_conn
from jarvis.memory import delete_fact


def _load_facts(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier "
        "FROM memories WHERE kind = 'fact'"
    ).fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m jarvis.consolidate")
    p.add_argument("--drop", nargs="+", metavar="KEY",
                   help="delete these fact keys (the only writing action)")
    p.add_argument("--threshold", type=float, default=None,
                   help="override the duplicate overlap threshold")
    args = p.parse_args(argv)

    with get_conn() as conn:
        if args.drop:
            for key in args.drop:
                ok = delete_fact(conn, key)
                print(f"{'deleted' if ok else 'not found'}: {key}")
            conn.commit()
            return 0

        facts = _load_facts(conn)

    kwargs = {"threshold": args.threshold} if args.threshold is not None else {}
    proposals = propose_merges(facts, **kwargs)
    print(f"{len(facts)} facts stored.\n")
    print(format_report(proposals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
