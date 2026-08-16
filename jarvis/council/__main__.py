"""D8.2.2 — offline replay CLI, read-only over already-logged rounds.

Usage:
    python -m jarvis.council --replay <round_id> --judges frontier
    python -m jarvis.council --replay <round_id> --judges frontier --dry-run
    python -m jarvis.council --agreement
    python -m jarvis.council --agreement --since 30d

`--replay` re-scores a stored round's proposals with a different judge
tier and reports whether the winner changes. It costs only judge calls —
no proposal generation, no live failure required, and it works on rounds
logged before the question was even asked. It NEVER writes to
council_rounds, never mutates a stored winner, and never triggers a
retry: replay scores are written only with shadow=1 (or, with
`--dry-run`, not written at all).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from jarvis.agents.upgrade_agent import load_model_registry
from jarvis.council import config as council_config
from jarvis.council import council as council_mod
from jarvis.council.agreement import compute_agreement
from jarvis.council.scoring import mean_of, select_winner
from jarvis.council.types import Proposal, Score
from jarvis.db import get_conn
from jarvis.runlog.store import parse_since

_JUDGE_TIER_CHOICES = ("economy", "mid", "frontier")


def _load_round_row(round_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM council_rounds WHERE round_id = ?", (round_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _load_payload(round_id: str, started_at: str, root: Path | None = None) -> list[dict]:
    date = started_at[:10]
    base = root if root is not None else Path(".")
    # council_mod.COUNCIL_LOG_DIR (not a copied name) so tests that
    # monkeypatch it (redirecting logs to a tmp dir) are honored here too.
    path = base / council_mod.COUNCIL_LOG_DIR / date / f"{round_id}.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _proposals_from_payload(records: list[dict]) -> list[Proposal]:
    return [
        Proposal(label=r["label"], profile=r["profile"], content=r["content"])
        for r in records if r.get("type") == "proposal"
    ]


def _context_from_payload(records: list[dict]) -> dict:
    """MORTIMER_LLM_COUNCIL_V2_PLAN.md V2 — replay's judge message needs
    the same failure context the live round's judges saw. Read from the
    round_start record's "context" field (written by _write_payload); a
    payload with no round_start record, or one whose context is missing/
    not a dict, degrades gracefully to {} (sections omitted), never an
    error — old pre-v2 payloads never had this field at all."""
    for r in records:
        if r.get("type") == "round_start":
            ctx = r.get("context")
            return ctx if isinstance(ctx, dict) else {}
    return {}


def _live_scores_from_payload(records: list[dict]) -> list[Score]:
    return [
        Score(
            judge_profile=r["judge_profile"], proposal_label=r["proposal_label"],
            value=r.get("value"), justification=r.get("justification") or "",
            abstain_reason=r.get("abstain_reason"),
        )
        for r in records if r.get("type") == "score" and not r.get("shadow")
    ]


async def _do_replay(round_id: str, judge_tier_name: str, *, dry_run: bool) -> int:
    round_row = _load_round_row(round_id)
    if round_row is None:
        print(f"no such round: {round_id}", file=sys.stderr)
        return 1

    records = _load_payload(round_id, round_row["started_at"])
    proposals = _proposals_from_payload(records)
    if not proposals:
        print(
            f"no stored proposals for round {round_id} "
            "(payload missing or pruned)", file=sys.stderr,
        )
        return 1
    live_scores = _live_scores_from_payload(records)

    registry = load_model_registry()
    profiles_by_name = registry.get("profiles", {})
    # V13 — a replay of an old round must tiebreak with the registry AS
    # IT WAS at convene() time, not as it is now; prefer the stored
    # order and fall back to the live registry only for pre-v2 rounds
    # (NULL column).
    stored_order_raw = round_row.get("registry_order")
    registry_order = None
    if stored_order_raw:
        try:
            registry_order = json.loads(stored_order_raw)
        except (TypeError, ValueError):
            registry_order = None
    if registry_order is None:
        registry_order = list(profiles_by_name.keys())

    proposer_profiles = {p.profile for p in proposals}
    replay_judge_names = council_config.resolve_tier_name_members(
        judge_tier_name, exclude=proposer_profiles,
    )
    if not replay_judge_names:
        print(f"no usable profile for tier {judge_tier_name!r}", file=sys.stderr)
        return 1

    labels = [p.label for p in proposals]
    context = _context_from_payload(records)
    judge_user_content = council_mod._judge_user_message(
        round_row["goal"], context, proposals, round_row.get("placement") or "planner",
    )
    # V9 — replay discards usage: it must never write to council_rounds
    # (D8.2.2's read-only rule), and recording replay token spend is out
    # of scope for this plan.
    replay_scores, _replay_usage = await council_mod._gather_scores(
        replay_judge_names, profiles_by_name, judge_user_content, labels,
        shadow=True,
    )

    live_winner, live_reason = select_winner(proposals, live_scores, registry_order)
    replay_winner, replay_reason = select_winner(proposals, replay_scores, registry_order)
    agree = (
        live_winner is not None and replay_winner is not None
        and live_winner.label == replay_winner.label
    )

    print(f"round_id       {round_id}")
    print(f"goal           {round_row['goal']}")
    print(f"live winner    {live_winner.label if live_winner else None}  ({live_reason})")
    print(f"replay winner  {replay_winner.label if replay_winner else None}  ({replay_reason})")
    print(f"agree          {agree}")
    print()
    print("-- live scores --")
    for lbl in labels:
        print(f"  {lbl}: mean={mean_of(lbl, live_scores)}")
    print("-- replay scores --")
    for lbl in labels:
        print(f"  {lbl}: mean={mean_of(lbl, replay_scores)}")

    if dry_run:
        print()
        print("(--dry-run: nothing written)")
    else:
        profile_tiers = {name: prof.get("tier") for name, prof in profiles_by_name.items()}
        label_to_profile = {p.label: p.profile for p in proposals}
        council_mod._write_score_rows(
            round_id, replay_scores, profile_tiers, label_to_profile, shadow=True,
        )
    return 0


def _fetch_agreement_rows(since_iso: str | None) -> tuple[list[dict], list[dict]]:
    conn = get_conn()
    try:
        if since_iso:
            round_rows = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM council_rounds WHERE started_at >= ?", (since_iso,)
                ).fetchall()
            ]
        else:
            round_rows = [dict(r) for r in conn.execute("SELECT * FROM council_rounds").fetchall()]
        round_ids = [r["round_id"] for r in round_rows]
        score_rows: list[dict] = []
        if round_ids:
            placeholders = ",".join("?" for _ in round_ids)
            score_rows = [
                dict(r) for r in conn.execute(
                    f"SELECT * FROM council_scores WHERE round_id IN ({placeholders})",
                    round_ids,
                ).fetchall()
            ]
        return score_rows, round_rows
    finally:
        conn.close()


def _do_agreement(since: str | None) -> int:
    since_iso = parse_since(since)
    score_rows, round_rows = _fetch_agreement_rows(since_iso)
    report = compute_agreement(score_rows, round_rows)
    print(f"rounds considered      {report.rounds_considered}")
    print(f"winner agreement       {report.winner_agreement}")
    print(f"rank correlation       {report.rank_correlation}")
    print(f"abstention rate        {report.abstention_rate_by_tier}")
    print(f"discrimination         {report.discrimination_by_tier}")
    print(f"disagreement cost      {report.disagreement_cost}")
    print(f"decision               {report.branch}")
    print(f"recommend promote      {report.recommend_promote}")
    # V9 — this finally lets v1 §9's "observed cost per escalated
    # session" be answered from data rather than assertion. Summed over
    # the same round set the report above already considered.
    prompt_sum = 0
    completion_sum = 0
    rounds_with_usage = 0
    for r in round_rows:
        if r.get("prompt_tokens") is not None and r.get("completion_tokens") is not None:
            prompt_sum += r["prompt_tokens"]
            completion_sum += r["completion_tokens"]
            rounds_with_usage += 1
    print(
        f"total tokens          prompt={prompt_sum} completion={completion_sum} "
        f"(rounds with usage: {rounds_with_usage}/{len(round_rows)})"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m jarvis.council")
    parser.add_argument("--replay", metavar="ROUND_ID", default=None)
    parser.add_argument("--judges", choices=_JUDGE_TIER_CHOICES, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--agreement", action="store_true")
    parser.add_argument("--since", default=None, help="Nd | Nh | Nm | ISO-8601 date")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.replay:
        if not args.judges:
            print("--replay requires --judges <economy|mid|frontier>", file=sys.stderr)
            return 2
        return asyncio.run(_do_replay(args.replay, args.judges, dry_run=args.dry_run))
    if args.agreement:
        return _do_agreement(args.since)
    print(
        "nothing to do — pass --replay ROUND_ID --judges TIER, or --agreement",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
