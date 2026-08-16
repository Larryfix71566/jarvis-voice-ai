"""D6 scoring parser + D7 deterministic winner selection.

Pure, no I/O, no network (D1's requirement): this module imports nothing
from openai, jarvis.selfedit, or jarvis.agents, so the entire selection
path is unit-testable in isolation. The council size floor (D7) is exposed
as `council_size_ok`, a plain predicate over counts — the caller (council.py)
owns the actual COUNCIL_MIN_PROPOSERS/COUNCIL_MIN_JUDGES constants (D12,
jarvis/council/config.py) and decides not to convene at all rather than
ever calling select_winner with too few members. This keeps select_winner's
documented invariant exact: it returns None only when no proposal received
any valid score.
"""

from __future__ import annotations

import re
import statistics
from typing import Iterable

from jarvis.council.types import Proposal, Score

# ⚙ TUNING KNOB (D12)
COUNCIL_SCORE_MIN = 1.0
COUNCIL_SCORE_MAX = 10.0

# D6 — the parsing rule. MORTIMER_LLM_COUNCIL_V2_PLAN.md V6: the trailing
# `(?=\s|$)` lookahead requires the numeric token to end at whitespace or
# end-of-line, so a malformed two-decimal value like "7.44" or a bare
# trailing dot like "8." cannot be silently mis-read as "7.4"/"8" with the
# remainder leaking into the justification — the whole line fails to
# match instead, and the label falls through to the existing "judge did
# not score this proposal" abstention below. Single-decimal values
# ("7.4"), bare integers ("8"), and integers with an em/en dash
# justification ("8 - fine") are unaffected.
_SCORE_RE = re.compile(
    r"^Proposal ([A-Z]):\s*(\d{1,2}(?:\.\d)?)(?=\s|$)\s*(?:—|-|–)?\s*(.*)$",
    re.MULTILINE,
)


def parse_scores(judge_profile: str, raw: str, labels: list[str]) -> list[Score]:
    """Parse one judge's raw output into exactly one Score per label in
    `labels`. A label the judge did not score, or scored invalidly, yields
    a Score with value=None and a populated abstain_reason. Never returns
    fewer than len(labels) items, and never raises."""
    label_set = set(labels)
    seen: dict[str, Score] = {}
    for match in _SCORE_RE.finditer(raw or ""):
        label_letter, raw_value, justification = match.groups()
        label = f"Proposal {label_letter}"
        if label not in label_set:
            continue  # unknown label — ignored, not an abstention target
        if label in seen:
            continue  # duplicate label from this judge — first occurrence wins
        try:
            value = float(raw_value)
        except ValueError:
            seen[label] = Score(
                judge_profile=judge_profile, proposal_label=label, value=None,
                abstain_reason=f"unparseable score value: {raw_value!r}",
            )
            continue
        if not (COUNCIL_SCORE_MIN <= value <= COUNCIL_SCORE_MAX):
            seen[label] = Score(
                judge_profile=judge_profile, proposal_label=label, value=None,
                abstain_reason=(
                    f"score {value} outside [{COUNCIL_SCORE_MIN}, "
                    f"{COUNCIL_SCORE_MAX}] — not clamped, recorded as abstention"
                ),
            )
            continue
        seen[label] = Score(
            judge_profile=judge_profile, proposal_label=label, value=value,
            justification=justification.strip(),
        )
    out: list[Score] = []
    for label in labels:
        if label in seen:
            out.append(seen[label])
        else:
            out.append(Score(
                judge_profile=judge_profile, proposal_label=label, value=None,
                abstain_reason="judge did not score this proposal "
                               "(no matching SCORES: line found)",
            ))
    return out


def mean_of(label: str, scores: Iterable[Score]) -> float | None:
    """Mean of valid scores for `label`; None if it has none."""
    values = [s.value for s in scores if s.proposal_label == label and s.value is not None]
    if not values:
        return None
    return statistics.fmean(values)


def _min_of(label: str, scores: list[Score]) -> float | None:
    values = [s.value for s in scores if s.proposal_label == label and s.value is not None]
    return min(values) if values else None


def _variance_of(label: str, scores: list[Score]) -> float:
    values = [s.value for s in scores if s.proposal_label == label and s.value is not None]
    if len(values) < 2:
        return 0.0
    return statistics.pvariance(values)


def select_winner(
    proposals: list[Proposal],
    scores: list[Score],
    registry_order: list[str],
) -> tuple[Proposal | None, str]:
    """Apply D7's four rules in order. Returns (winner, reason). Returns
    (None, reason) iff no proposal has at least one valid score.
    `registry_order` is profile names in config order — rule 4's tiebreak.
    Deterministic: identical inputs always yield an identical winner."""
    proposer_profiles = {p.profile for p in proposals}
    # D5 defensive filter: a judge that also proposed in this round can
    # never count toward selection, even if construction failed to keep
    # the roles disjoint. council.py is the primary enforcement point
    # (members are drawn from disjoint pools); this is the pure-function
    # backstop, so a construction bug fails safe rather than silently
    # letting a proposal score itself.
    usable_scores = [s for s in scores if s.judge_profile not in proposer_profiles]

    eligible = [p for p in proposals if mean_of(p.label, usable_scores) is not None]
    if not eligible:
        return None, "no proposal received any valid score"

    def sort_key(p: Proposal) -> tuple[float, float, float, int]:
        mean = mean_of(p.label, usable_scores)
        mn = _min_of(p.label, usable_scores)
        var = _variance_of(p.label, usable_scores)
        assert mean is not None and mn is not None  # guaranteed by `eligible`
        try:
            order = registry_order.index(p.profile)
        except ValueError:
            order = len(registry_order)  # unknown profile sorts last
        # Rule order: highest mean, then highest min, then lowest
        # variance, then lowest registry-order index (earliest wins).
        # Negating the "higher is better" fields lets one ascending sort
        # implement all four rules at once.
        return (-mean, -mn, var, order)

    ranked = sorted(eligible, key=sort_key)
    winner = ranked[0]
    winner_mean = mean_of(winner.label, usable_scores)

    tied_on_mean = [p for p in eligible if mean_of(p.label, usable_scores) == winner_mean]
    if len(tied_on_mean) == 1:
        return winner, f"highest mean score ({winner_mean:.1f})"

    winner_min = _min_of(winner.label, usable_scores)
    tied_on_min = [p for p in tied_on_mean if _min_of(p.label, usable_scores) == winner_min]
    if len(tied_on_min) == 1:
        return winner, f"tied on mean; highest minimum score ({winner_min:.1f})"

    winner_var = _variance_of(winner.label, usable_scores)
    tied_on_var = [p for p in tied_on_min if _variance_of(p.label, usable_scores) == winner_var]
    if len(tied_on_var) == 1:
        return winner, f"tied on mean and minimum; lowest variance ({winner_var:.3f})"

    return winner, "tied on mean, minimum, and variance; broken by registry order"


def council_size_ok(
    num_proposers: int, num_judges: int, *, min_proposers: int, min_judges: int,
) -> bool:
    """D7's council size floor, as a pure predicate: >= min_proposers
    proposers AND >= min_judges judges. council.py calls this BEFORE ever
    constructing a round; a caller that fails this check must not call
    select_winner at all, and records `council_too_small` directly."""
    return num_proposers >= min_proposers and num_judges >= min_judges
