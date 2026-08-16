"""Procedures-as-hints (MORTIMER_MEMORY_PROCEDURES_PLAN.md Part B, D9-D24).

After a sub-agent run finishes, learn_from_run() matches its task against
existing procedures for that agent and either reinforces a match's
success/failure counters or — only for a successful run with no match —
creates a new candidate procedure via one small LLM call. A candidate
becomes active (eligible to be injected as a hint) after
PROCEDURE_PROMOTE_AFTER net successes; an active procedure whose failures
outweigh its successes is deprecated and stops being injected. At the start
of a delegation, SubAgent._loop (jarvis/agents/base.py) runs the same
match_procedure() function against active procedures only and, on a match,
injects one short hint message before the task.

Safety (D18): a procedure is a hint, never a bypass. Its description is
free text describing what worked, not a replay mechanism — the sub-agent
still calls self._registry.call(...) for every tool, unchanged, and no
existing confirmation gate is touched by this module. This is true by
construction (D17's implementation is a prompt message, not code), not by a
check that could be missed.

Matching (D10): match_procedure() is the single function both the dedup
path (learn_from_run, status=None — any status, including deprecated, so a
recurring task shape after one deprecation reinforces the existing row
instead of spawning a duplicate) and the retrieval path (SubAgent._loop,
status="active") call — using the exact same logic means a new candidate
can never fail to match the record it should increment next time. FTS5
(procedures_fts, migration 0007 in jarvis/db.py) generates the candidate
set cheaply; the accept/reject decision is a plain token-overlap ratio
computed in Python against each candidate's label+description, which is
deterministic and avoids relying on FTS5 bm25's sign/magnitude behavior
(which degrades unpredictably on the small, low-document-count corpus this
table always has — one row per distinct task shape per agent, not one per
run, per §9's own risk note on volume).

Every public function here is best-effort and never raises (§0.3) — a
failure anywhere in this module must never affect a delegation or the
voice pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

from openai import AsyncOpenAI

from jarvis.db import get_conn, now_iso
from jarvis.runlog import get_run

logger = logging.getLogger(__name__)

# ⚙ TUNING KNOB (D23) — clamp bounds applied to every --calibrate branch.
CALIBRATE_THRESHOLD_MIN = 0.20
CALIBRATE_THRESHOLD_MAX = 0.60

# ⚙ TUNING KNOB (D23) — below this many MATCHED pairs, --calibrate refuses
# to compute a threshold from percentiles and reports "insufficient data"
# instead (branch 3).
CALIBRATE_MIN_MATCHED_PAIRS = 5

# ⚙ TUNING KNOB — minimum symmetric token-overlap score (D22) between the
# incoming task's tokens and a candidate procedure's stored task_tokens
# (D21) for a match to count. Value calibrated 2026-08-14 via
# `python -m jarvis.procedures --calibrate` against the logged run corpus
# at that time (MORTIMER_AGENT_TRUST_PLAN.md D23; full populations and
# branch recorded in the plan's §10). Do not hand-tune this value — rerun
# --calibrate as the run corpus grows and update it from that output only.
PROCEDURE_MATCH_THRESHOLD = 0.2

# ⚙ TUNING KNOB — net successes (success_count - failure_count) before a
# candidate becomes active and starts being injected as a hint. Mirrors
# jarvis.memory.PROMOTE_AFTER exactly (D15): one success is noise, three is
# a pattern.
PROCEDURE_PROMOTE_AFTER = 3

# ⚙ TUNING KNOB — failures before an active procedure is deprecated,
# provided failures also outweigh successes (D15) so one bad outlier run
# cannot kill a procedure that has otherwise worked nine times out of ten.
PROCEDURE_DEPRECATE_AFTER = 3

# ⚙ TUNING KNOB — cap on procedures.source_run_ids; oldest dropped first.
MAX_SOURCE_RUN_IDS = 20

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_DESCRIBE_PROMPT = """You summarize how a specialist agent successfully completed a task, so the summary can be reused as a hint the next time a similar task comes up.

Given the agent's name and the task it just completed successfully, produce STRICT JSON only:

{"label": "<3 to 6 word name for this kind of task>",
 "description": "<one short sentence describing what worked, at most 200 characters>"}

Rules:
- Describe the PATTERN of the task, not this one instance's specific details (no names, dates, or other one-off specifics).
- The description is read by the same kind of specialist agent next time a similar task comes up — write it as a hint, not a replay script.
- Output JSON only. No markdown, no commentary."""


# Common function/filler words that show up in both task text and
# LLM-written descriptions ("used the tool to check...") without carrying
# any of the topical signal that should drive a match. Without filtering
# these, a short, generic description's overlap ratio gets diluted by
# words like "used"/"check"/"for" that appear in nearly every description
# regardless of topic, pushing genuinely on-topic matches below threshold.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "used", "use", "uses", "using", "check",
    "checked", "checking", "get", "gets", "getting", "was", "were", "this",
    "that", "from", "into", "onto", "via", "then", "than", "when", "what",
    "which", "who", "how", "will", "would", "could", "should", "please",
    "task", "agent", "specialist", "successfully", "completed", "one",
    "short", "hint", "you", "your",
})


def _tokens(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) >= 3 and t not in _STOPWORDS
    }


def _fts_query_from_tokens(tokens: set[str]) -> str | None:
    if not tokens:
        return None
    # Each token quoted as an FTS5 phrase so punctuation/operators in the
    # source text (AND, OR, NOT, NEAR, hyphens, etc.) can never be parsed
    # as FTS5 query syntax.
    escaped = ['"' + t.replace('"', '""') + '"' for t in tokens]
    return " OR ".join(escaped)


def _overlap_score(a: set[str], b: set[str]) -> float:
    """D22 — symmetric: divide by the SMALLER of the two token sets, not
    always the candidate's, so a longer task that fully contains a
    shorter candidate's tokens (or vice versa) scores 1.0 regardless of
    which side is longer. The old asymmetric version divided by the
    candidate's token count alone, which penalised a verbose task for
    containing extra words — exactly backwards."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _task_tokens_of(row: dict) -> set[str]:
    """D21 — a candidate's match key is its stored task_tokens (the
    tokenized task that CREATED it), never label+description. A row from
    before migration 0008 has task_tokens == '' and is therefore
    unmatchable — see D24's note on the 13 pre-existing rows; this is
    intentional, not a bug to route around here."""
    stored = row["task_tokens"] if "task_tokens" in row.keys() else ""
    return set((stored or "").split())


def match_procedure(
    agent: str,
    task: str,
    status: str | None = "active",
    db_path: str | Path | None = None,
    task_tokens: set[str] | None = None,
) -> dict | None:
    """Find the best-matching procedure for `agent`/`task`, or None.

    status="active" (the default) is what SubAgent._loop's retrieval path
    uses. status=None matches any status (candidate, active, AND
    deprecated) and is what learn_from_run's dedup path uses explicitly —
    callers must never rely on the default for dedup; pass status=None by
    name so the choice is visible at the call site (plan D14 step 2).

    `task_tokens`, if given, is used as-is instead of re-tokenizing `task`
    — learn_from_run passes the exact set it also writes to a new
    candidate's task_tokens column (D21), so the two can never disagree
    about what a given task tokenizes to.

    Never raises — any DB or query failure degrades to "no match" (a
    missed hint/dedup opportunity, not a broken delegation).
    """
    try:
        if task_tokens is None:
            task_tokens = _tokens(task)
        fts_query = _fts_query_from_tokens(task_tokens)
        if fts_query is None:
            return None
        conn = get_conn(db_path)
        try:
            sql = (
                "SELECT p.* FROM procedures_fts "
                "JOIN procedures p ON p.id = procedures_fts.rowid "
                "WHERE procedures_fts MATCH ? AND p.agent = ?"
            )
            params: list[Any] = [fts_query, agent]
            if status is not None:
                sql += " AND p.status = ?"
                params.append(status)
            sql += " ORDER BY procedures_fts.rank LIMIT 10"
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        best_row = None
        best_score = 0.0
        for row in rows:
            # D21: score against the candidate's OWN task_tokens, not
            # label+description — the FTS5 query above still runs against
            # procedures_fts (label/description) purely to generate a
            # cheap candidate set; the accept/reject decision below is
            # task-shape-to-task-shape only.
            candidate_tokens = _task_tokens_of(dict(row))
            score = _overlap_score(candidate_tokens, task_tokens)
            if score > best_score:
                best_score = score
                best_row = row
        if best_row is None or best_score < PROCEDURE_MATCH_THRESHOLD:
            return None
        return dict(best_row)
    except Exception:  # noqa: BLE001 — matching must never break a delegation
        logger.warning("procedures_match_failed agent=%s", agent, exc_info=True)
        return None


def mark_used(procedure_id: int, db_path: str | Path | None = None) -> None:
    """Record that a procedure was just injected as a hint (D19's
    last_used_at — tracked for future staleness review, D23). Best-effort:
    a failure here must not affect the delegation that just used it."""
    try:
        conn = get_conn(db_path)
        try:
            conn.execute(
                "UPDATE procedures SET last_used_at = ? WHERE id = ?",
                (now_iso(), procedure_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning("procedures_mark_used_failed id=%s", procedure_id,
                        exc_info=True)


def _promote_or_deprecate(row: dict, conn: sqlite3.Connection) -> None:
    """D15's threshold logic. Mutates `row["status"]` in place to match
    what was written, so callers see the post-update status without a
    re-query."""
    status = row["status"]
    success = row["success_count"]
    failure = row["failure_count"]
    new_status = status
    if status == "candidate" and (success - failure) >= PROCEDURE_PROMOTE_AFTER:
        new_status = "active"
    elif (
        status == "active"
        and failure >= PROCEDURE_DEPRECATE_AFTER
        and failure > success
    ):
        new_status = "deprecated"
    # A deprecated row never re-promotes automatically (D15) — no other
    # transition is possible, so nothing else to check.
    if new_status != status:
        conn.execute(
            "UPDATE procedures SET status = ? WHERE id = ?",
            (new_status, row["id"]),
        )
        row["status"] = new_status


def _append_source_run_id(source_run_ids_json: str, run_id: str) -> str:
    try:
        ids = json.loads(source_run_ids_json)
        if not isinstance(ids, list):
            ids = []
    except (json.JSONDecodeError, TypeError):
        ids = []
    ids.append(run_id)
    ids = ids[-MAX_SOURCE_RUN_IDS:]
    return json.dumps(ids)


def _reinforce_match(match: dict, run_status: str, run_id: str, db_path) -> None:
    conn = get_conn(db_path)
    try:
        success = match["success_count"] + (1 if run_status == "ok" else 0)
        failure = match["failure_count"] + (0 if run_status == "ok" else 1)
        source_run_ids = _append_source_run_id(match["source_run_ids"], run_id)
        now = now_iso()
        conn.execute(
            "UPDATE procedures SET success_count = ?, failure_count = ?, "
            "source_run_ids = ?, updated_at = ? WHERE id = ?",
            (success, failure, source_run_ids, now, match["id"]),
        )
        row = dict(match)
        row["success_count"] = success
        row["failure_count"] = failure
        row["source_run_ids"] = source_run_ids
        row["updated_at"] = now
        _promote_or_deprecate(row, conn)
        conn.commit()
    finally:
        conn.close()


def _create_candidate(
    agent: str, label: str, description: str, run_id: str, db_path,
    task_tokens: set[str],
) -> None:
    # D21 — task_tokens is written HERE and only here, from the same
    # _tokens(task) set learn_from_run already computed for its dedup
    # match_procedure() call above — never re-derived from label/
    # description, which is exactly the vocabulary-mismatch bug D21
    # exists to remove.
    now = now_iso()
    conn = get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO procedures (agent, label, description, status, "
            "success_count, failure_count, source_run_ids, created_at, "
            "updated_at, task_tokens) "
            "VALUES (?, ?, ?, 'candidate', 1, 0, ?, ?, ?, ?)",
            (agent, label, description, json.dumps([run_id]), now, now,
             " ".join(sorted(task_tokens))),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_label_description(text: str) -> tuple[str, str] | tuple[None, None]:
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    label = str(data.get("label") or "").strip()
    description = str(data.get("description") or "").strip()
    if not label or not description:
        return None, None
    return label[:100], description[:200]


async def _describe_procedure(
    agent: str,
    task: str,
    settings: Any,
    client_factory: Callable[[Any], Any] | None = None,
) -> tuple[str, str] | tuple[None, None]:
    client = (
        client_factory(settings)
        if client_factory is not None
        else AsyncOpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url,
        )
    )
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _DESCRIBE_PROMPT},
            {"role": "user", "content": f"Agent: {agent}\nTask: {task}"},
        ],
    )
    return _parse_label_description(response.choices[0].message.content or "")


async def learn_from_run(
    run_id: str,
    agent: str,
    db_path: str | Path | None = None,
    client_factory: Callable[[Any], Any] | None = None,
) -> None:
    """Implements D14 exactly, in order:

    1. Read the run via jarvis.runlog.get_run (reuses the existing reader).
    2. Dedup match against ANY status (status=None) — see match_procedure's
       docstring for why this differs from the retrieval path's default.
    3. A match: reinforce its counters, apply the D15 promotion/deprecation
       check.
    4. No match and the run did not succeed: do nothing (D16 — a candidate
       is only ever created from a successful run).
    5. No match and the run succeeded: one small LLM call to describe the
       new procedure, then insert it as a candidate.

    D20's single enforcement point for the kill switch: settings are loaded
    fresh here (this function has no Settings parameter per its locked
    signature, and delegate.py's spawn site deliberately does not reach
    into SubAgent's private _settings to check the flag for it — see
    jarvis/agents/delegate.py). client_factory is an optional testability
    hook, the same pattern jarvis.memory.update_memory_from_session uses,
    so tests do not need to monkeypatch AsyncOpenAI globally.
    """
    try:
        from jarvis.config import load_settings

        settings = load_settings()
        if not settings.jarvis_procedures_enabled:
            return

        detail = get_run(run_id, db_path=db_path)
        if detail is None:
            return
        run = detail["run"]
        task = run["task"]
        run_status = run["status"]

        # D21 — tokenized exactly once here; both the dedup match below
        # and _create_candidate's task_tokens column (if a candidate ends
        # up being created) use this SAME set, so they can never disagree
        # about what this task tokenizes to.
        task_tokens = _tokens(task)

        match = match_procedure(
            agent, task, status=None, db_path=db_path, task_tokens=task_tokens,
        )
        if match is not None:
            _reinforce_match(match, run_status, run_id, db_path)
            return

        if run_status != "ok":
            return  # D16: failed runs never originate a new candidate

        label, description = await _describe_procedure(
            agent, task, settings, client_factory=client_factory,
        )
        if label is None:
            return
        _create_candidate(agent, label, description, run_id, db_path, task_tokens)
    except Exception:  # noqa: BLE001 — learning must never break a delegation
        logger.warning(
            "procedures_learn_failed run_id=%s agent=%s", run_id, agent,
            exc_info=True,
        )


# ============================================================================
# D23 — CLI: `python -m jarvis.procedures --explain "<task>" [--agent NAME]`
#            `python -m jarvis.procedures --calibrate`
#
# Both are read-only diagnostics; neither writes to the procedures table.
# ============================================================================


def _clamp_threshold(value: float) -> float:
    return max(CALIBRATE_THRESHOLD_MIN, min(CALIBRATE_THRESHOLD_MAX, value))


def _percentile(data: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy's default method), stdlib
    only. `data` need not be pre-sorted. Undefined (raises) on an empty
    list — callers must check emptiness first; this mirrors the plan's
    own requirement that percentiles are only meaningful once a
    population exists."""
    s = sorted(data)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] * (c - k) + s[c] * (k - f)


def _explain(agent: str | None, task: str, db_path: str | Path | None = None) -> None:
    """D23 `--explain`: print every stored procedure (optionally scoped to
    one agent), its score against `task`, the shared tokens, and whether
    it passed PROCEDURE_MATCH_THRESHOLD — the same score match_procedure
    would compute, made visible instead of silently discarded."""
    task_tokens = _tokens(task)
    print(f"task tokens ({len(task_tokens)}): {sorted(task_tokens)}")
    print(f"threshold: {PROCEDURE_MATCH_THRESHOLD}")
    print()

    conn = get_conn(db_path)
    try:
        sql = "SELECT * FROM procedures"
        params: list[Any] = []
        if agent:
            sql += " WHERE agent = ?"
            params.append(agent)
        sql += " ORDER BY agent, id"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    if not rows:
        scope = f" for agent={agent!r}" if agent else ""
        print(f"no stored procedures{scope}")
        return

    for row in rows:
        candidate_tokens = _task_tokens_of(row)
        score = _overlap_score(candidate_tokens, task_tokens)
        shared = sorted(candidate_tokens & task_tokens)
        passed = score >= PROCEDURE_MATCH_THRESHOLD
        print(
            f"[{row['status']:>10}] id={row['id']:<4} agent={row['agent']:<12} "
            f"score={score:.3f} {'PASS' if passed else 'fail':<4} "
            f"label={row['label']!r}"
        )
        print(f"{'':>13}shared_tokens={shared}")
        if not candidate_tokens:
            print(f"{'':>13}(empty task_tokens — pre-migration-0008 row, "
                  "permanently unmatchable; see D24)")


def _load_successful_runs(
    db_path: str | Path | None = None, root: Path | None = None,
) -> list[dict]:
    """D23 data source: agent_runs supplies run_id/agent/task/status;
    each run's ordered tool-call sequence is read back from its own
    payload JSONL file (logs/agents/<date>/<run_id>.jsonl, pointed to by
    agent_runs.payload_path) — the same file jarvis.runlog.store.RunLogger
    wrote tool_call records into. Only status='ok' runs are loaded — both
    MATCHED and UNMATCHED populations are defined over successful runs
    only (plan D23)."""
    root = root if root is not None else Path(".")
    conn = get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT run_id, agent, task, payload_path FROM agent_runs "
            "WHERE status = 'ok'"
        ).fetchall()
    finally:
        conn.close()

    out: list[dict] = []
    for row in rows:
        tools: list[str] = []
        payload_path = row["payload_path"]
        if payload_path:
            full_path = root / payload_path
            if full_path.exists():
                try:
                    for line in full_path.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        if record.get("type") == "tool_call":
                            tools.append(str(record.get("tool") or ""))
                except (OSError, json.JSONDecodeError):
                    tools = []  # unreadable payload — treat as no tool calls
        out.append({
            "run_id": row["run_id"], "agent": row["agent"],
            "task": row["task"], "tools": tools,
        })
    return out


def _calibrate_populations(runs: list[dict]) -> tuple[list[float], list[float]]:
    """D23: for every same-agent pair of successful runs, classify as
    MATCHED (identical, non-empty, ORDERED tool sequence) or UNMATCHED
    (both non-empty, sharing no tool at all) and score each pair as
    _overlap_score(_tokens(task_a), _tokens(task_b)) — the exact function
    match_procedure uses at request time, so the calibration measures the
    real scoring path, not a proxy for it. Pairs with an empty tool
    sequence on either side are excluded from BOTH populations: two
    no-tool runs sharing "no tool" is not evidence of dissimilarity, and
    two no-tool runs cannot be shown to share a sequence either."""
    by_agent: dict[str, list[dict]] = {}
    for run in runs:
        by_agent.setdefault(run["agent"], []).append(run)

    matched: list[float] = []
    unmatched: list[float] = []
    for agent_runs in by_agent.values():
        for i in range(len(agent_runs)):
            for j in range(i + 1, len(agent_runs)):
                a, b = agent_runs[i], agent_runs[j]
                seq_a, seq_b = a["tools"], b["tools"]
                if not seq_a or not seq_b:
                    continue
                score = _overlap_score(_tokens(a["task"]), _tokens(b["task"]))
                if seq_a == seq_b:
                    matched.append(score)
                elif not (set(seq_a) & set(seq_b)):
                    unmatched.append(score)
    return matched, unmatched


def _pick_threshold(matched: list[float], unmatched: list[float]) -> tuple[float, str]:
    """D23's three-branch rule, applied in the plan's exact order. Returns
    (clamped_threshold, human-readable branch description for §10)."""
    if matched and unmatched:
        p25_m = _percentile(matched, 25)
        p90_u = _percentile(unmatched, 90)
        if p25_m > p90_u:
            value = round(p25_m - 0.01, 2)
            return _clamp_threshold(value), (
                f"branch 1 (clean separation): p25(MATCHED)={p25_m:.3f} > "
                f"p90(UNMATCHED)={p90_u:.3f} -> round(p25(MATCHED)-0.01, 2)"
            )
        ranges_overlap = not (
            max(matched) < min(unmatched) or min(matched) > max(unmatched)
        )
        if ranges_overlap:
            value = round((p25_m + p90_u) / 2, 2)
            return _clamp_threshold(value), (
                f"branch 2 (overlap): midpoint of p25(MATCHED)={p25_m:.3f} "
                f"and p90(UNMATCHED)={p90_u:.3f}"
            )
    # Either population is empty, or (non-empty but) neither branch 1's
    # separation test nor branch 2's range-overlap test applied — in every
    # such case the corpus does not support a computed threshold.
    n = len(matched)
    return _clamp_threshold(0.35), f"branch 3 (insufficient data, N={n})"


def _summary_line(label: str, data: list[float]) -> str:
    if not data:
        return f"{label}: n=0"
    return (
        f"{label}: n={len(data)} min={min(data):.3f} "
        f"p10={_percentile(data, 10):.3f} p25={_percentile(data, 25):.3f} "
        f"median={_percentile(data, 50):.3f} p75={_percentile(data, 75):.3f} "
        f"p90={_percentile(data, 90):.3f} max={max(data):.3f}"
    )


def _calibrate(db_path: str | Path | None = None, root: Path | None = None) -> None:
    """D23 `--calibrate`: prints both populations' percentile tables, the
    branch that applied, and the resulting threshold. Does NOT write
    PROCEDURE_MATCH_THRESHOLD — "the implementer does not choose a number;
    the implementer runs this and reads one off" (plan D23), i.e. the
    printed value is what a human then puts in source, deliberately not
    automated so a §10 record of the populations always accompanies the
    change."""
    runs = _load_successful_runs(db_path=db_path, root=root)
    matched, unmatched = _calibrate_populations(runs)
    print(_summary_line("MATCHED", matched))
    print(_summary_line("UNMATCHED", unmatched))
    threshold, branch = _pick_threshold(matched, unmatched)
    print(f"branch applied: {branch}")
    print(f"selected PROCEDURE_MATCH_THRESHOLD: {threshold}")
    print(f"current value in source: {PROCEDURE_MATCH_THRESHOLD}")


def _cli_main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m jarvis.procedures",
        description="D23 diagnostics for procedure matching.",
    )
    parser.add_argument(
        "--explain", metavar="TASK",
        help="Show every stored procedure's score against TASK.",
    )
    parser.add_argument(
        "--agent", metavar="NAME",
        help="Scope --explain to one agent's procedures.",
    )
    parser.add_argument(
        "--calibrate", action="store_true",
        help="Score the logged run corpus and report the deterministic "
             "threshold the D23 rule would pick.",
    )
    args = parser.parse_args(argv)

    if args.calibrate:
        _calibrate()
        return 0
    if args.explain is not None:
        _explain(args.agent, args.explain)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_cli_main(sys.argv[1:]))
