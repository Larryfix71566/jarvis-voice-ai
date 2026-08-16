"""D1.1 — the council module's public API, typed. Read by council.py,
scoring.py, agreement.py, the escalation hook in upgrade_agent.py, and the
admin endpoints. Fixed here, not left to the implementer (MORTIMER_LLM_
COUNCIL_PLAN.md D1.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Proposal:
    label: str            # "Proposal A" — assigned by council.py, never by a model
    profile: str           # registry profile name, e.g. "kimi-k2"
    content: str            # the proposed approach, prose only, never file contents


@dataclass(frozen=True)
class Score:
    judge_profile: str
    proposal_label: str
    value: float | None   # None == abstained
    justification: str = ""
    abstain_reason: str | None = None   # non-None iff value is None


@dataclass(frozen=True)
class RoundResult:
    round_id: str
    winner: Proposal | None      # None iff the round failed
    winner_mean: float | None
    select_reason: str           # which D7 branch decided it, or why it failed
    proposals: list[Proposal] = field(default_factory=list)
    # MORTIMER_LLM_COUNCIL_V2_PLAN.md V7: live scores only. The shadow
    # pass (D8.2.1) runs off this result's return path and writes its
    # own rows/JSONL records independently — it never merges into this
    # field, so callers of convene() never see shadow data here.
    scores: list[Score] = field(default_factory=list)
    abstentions: int = 0
    tier: int = 1
