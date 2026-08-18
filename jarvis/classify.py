"""Conversion layer — K6 of MORTIMER_KNOWLEDGE_FRAMEWORK_PLAN.md.

Larry, 2026-08-18: *"add to the plan a conversion layer to get everything
we currently have into the right bucket."*

Four layers are worthless if everything stays in bucket one. This module
reads every stored fact and proposes where it belongs:

    keep-memory    a fact about Larry or his world — stays
    -> workflow    a RULE about how work should be done (K4 seed data)
    -> skill       reusable how-to knowledge (expected to be ~empty:
                   that lives in `procedures`, not memory)
    delete-stale   re-derivable from the repo; occupies a slot for nothing
    needs-review   ambiguous — goes to a human, never to a default

Three disciplines carried from what went wrong on 2026-08-18, each a
direct response to a specific failure:

1. **Detection is pure and this module writes NOTHING.** Same shape as
   jarvis/consolidate.py. A rewriter that is subtly wrong costs more than
   the mess it fixes.
2. **Ambiguity resolves to `needs-review`, never to a confident default.**
   The volatile-state filter's first version deleted "Phase 1 committed"
   because a pattern was too eager; a classifier gets more chances to
   make that mistake, so its bias is toward asking.
3. **Nothing is destroyed.** The caller archives rather than deletes
   (see K6.3). During today's cleanup a fact was over-deleted and had to
   be reconstructed from truncated console output — its tail is still
   incomplete. That must not be the recovery story.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jarvis.memory import _is_volatile_state

# Destinations. Ordered by how confident the signal is, not alphabetically.
KEEP = "keep-memory"
TO_WORKFLOW = "-> workflow"
TO_SKILL = "-> skill"
DELETE_STALE = "delete-stale"
NEEDS_REVIEW = "needs-review"

# --- workflow detection ---------------------------------------------------
#
# A workflow is NORMATIVE and PROCEDURAL: it says how work should be done,
# usually with an ordering or a condition. A preference is a taste
# ("Fahrenheit", "short answers"). The distinction that matters: a
# workflow has a VERB describing an action to take, plus a modal or
# ordering word. "Prefers Fahrenheit" is a taste; "research alternatives
# before modifying code" is a rule with a step order.
_MODAL = re.compile(
    r"\b(must|should|always|never|don'?t|do not|need to|has to|have to|"
    r"required?|ensure|make sure)\b", re.I,
)
_ORDERING = re.compile(
    r"\b(before|after|first|then|once|until|prior to|followed by|"
    r"rather than|instead of)\b", re.I,
)
# Verbs that describe DOING work, as opposed to liking a format.
_PROCESS_VERB = re.compile(
    r"\b(commit|push|merge|review|research|test|verify|confirm|draft|"
    r"plan|implement|execute|run|check|break|split|display|show|ask|"
    r"approve|validate)\w*\b", re.I,
)

# --- skill detection ------------------------------------------------------
#
# Reusable how-to: a named technique or tool sequence someone could follow
# again. Deliberately narrow — the scan of Larry's store found essentially
# none of this in memory, and a loose rule here would mislabel project
# facts as skills.
_HOWTO = re.compile(
    r"\b(how to|steps? (to|for)|procedure for|recipe|technique|"
    r"command|invoke|call the|api call|endpoint)\b", re.I,
)

# --- stale detection ------------------------------------------------------
#
# Re-derivable from the repository or config: storing it can only ever be
# wrong more often than reading the source. `_is_volatile_state` (the
# write-time firewall) already blocks the worst of this; here it catches
# what predates the firewall.
_REDERIVABLE = re.compile(
    r"\b(config/|\.yaml|\.json|\.py\b|directory|file path|repo(sitory)?|"
    r"branch|migration|endpoint list|table schema|installed|version)\b", re.I,
)


@dataclass
class Classification:
    """One fact and where it appears to belong. A proposal, never a
    decision — `reason` exists so Larry can disagree with the evidence
    rather than with a verdict."""

    key: str
    content: str
    tier: str
    destination: str
    reason: str

    @property
    def is_actionable(self) -> bool:
        return self.destination != KEEP


def classify_fact(key: str, content: str, tier: str) -> Classification:
    """Propose a destination for one fact. Pure; never raises."""
    key = key or ""
    content = content or ""
    tier = (tier or "project").lower()

    def result(dest: str, why: str) -> Classification:
        return Classification(key, content, tier, dest, why)

    # identity is never reclassified automatically — 6 rows, irreplaceable,
    # and today's cleanup showed that is exactly where hand-review belongs.
    if tier == "identity":
        return result(KEEP, "identity tier is never auto-reclassified")

    # Stale first: a fact that should not exist need not be sorted.
    if _is_volatile_state(key, content):
        return result(DELETE_STALE, "transient state (volatile-state firewall)")
    if tier == "system" and _REDERIVABLE.search(content):
        return result(
            DELETE_STALE,
            "system tier and re-derivable from the repo — ask the source instead",
        )

    has_modal = bool(_MODAL.search(content))
    has_order = bool(_ORDERING.search(content))
    has_verb = bool(_PROCESS_VERB.search(content))

    # A workflow needs BOTH a process verb and a rule-shaped signal.
    # Requiring two independent signals is what keeps "prefers short
    # answers" (a taste) out of the workflow bucket.
    if has_verb and (has_modal or has_order):
        # Only `preference` proposes a workflow outright. Measured on the
        # real store: every genuine workflow Larry has stated arrived as a
        # preference ("research alternatives before modifying code"),
        # while rule-SHAPED project facts were a bug report and a feature
        # description — `project` says WHAT is being built, not HOW work
        # should be done. Project-tier hits go to review, not extraction.
        if tier == "preference":
            return result(
                TO_WORKFLOW,
                f"process verb + {'modal' if has_modal else 'ordering'} — a rule about how work is done",
            )
        return result(
            NEEDS_REVIEW,
            f"rule-shaped but tier is '{tier}' — project facts describe what is built, not how to work",
        )

    if _HOWTO.search(content):
        return result(
            NEEDS_REVIEW,
            "reads as how-to; skills normally come from procedures, not memory",
        )

    # System facts that aren't obviously re-derivable still probably don't
    # belong in the prompt — but "probably" is not a licence to delete.
    if tier == "system":
        return result(
            NEEDS_REVIEW,
            "system tier: excluded from the prompt already; delete only if truly re-derivable",
        )

    return result(KEEP, "reads as a fact about Larry or his world")


def classify_all(facts: list[dict]) -> list[Classification]:
    """Classify every fact. Pure: `facts` are plain dicts with key,
    content, tier."""
    return [
        classify_fact(f.get("key", ""), f.get("content", ""), f.get("tier", ""))
        for f in facts
    ]


def format_report(results: list[Classification]) -> str:
    """Review output, grouped by destination, actionable buckets first."""
    if not results:
        return "No facts stored."

    order = [DELETE_STALE, TO_WORKFLOW, TO_SKILL, NEEDS_REVIEW, KEEP]
    grouped: dict[str, list[Classification]] = {d: [] for d in order}
    for r in results:
        grouped.setdefault(r.destination, []).append(r)

    out: list[str] = [f"{len(results)} facts classified.\n"]
    for dest in order:
        rows = grouped.get(dest) or []
        if not rows:
            continue
        out.append(f"=== {dest}  ({len(rows)}) ===")
        for r in rows:
            out.append(f"  [{r.tier}] {r.key}")
            out.append(f"        {r.content[:96]}")
            out.append(f"        why: {r.reason}")
        out.append("")

    actionable = sum(1 for r in results if r.is_actionable)
    out.append(f"{actionable} of {len(results)} facts are not plain memory.")
    out.append("")
    out.append("Nothing has been changed. Each destination has its own explicit")
    out.append("command, naming each key — there is deliberately no bulk apply:")
    out.append("  python -m jarvis.consolidate --drop <key> ...   (delete-stale)")
    out.append("  (workflow extraction lands with K4)")
    return "\n".join(out)


# --- CLI (review-only) ----------------------------------------------------


def _load_facts(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT key, content, COALESCE(tier, 'project') AS tier "
        "FROM memories WHERE kind = 'fact'"
    ).fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    from jarvis.db import get_conn

    p = argparse.ArgumentParser(prog="python -m jarvis.classify")
    p.add_argument("--only", choices=[DELETE_STALE, TO_WORKFLOW, TO_SKILL,
                                      NEEDS_REVIEW, KEEP],
                   help="show one destination only")
    p.add_argument("--keys", action="store_true",
                   help="print bare keys (pipe into --drop)")
    args = p.parse_args(argv)

    with get_conn() as conn:
        facts = _load_facts(conn)

    results = classify_all(facts)
    if args.only:
        results = [r for r in results if r.destination == args.only]
    if args.keys:
        for r in results:
            print(r.key)
        return 0
    print(format_report(results))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
