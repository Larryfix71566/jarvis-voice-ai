"""Tests for jarvis.graphs.deliberation_graph (MORTIMER_GRAPH_LAYER_PLAN.md §5 step 6, §7)."""
import copy

import pytest

from jarvis.council.council import build_roster
from jarvis.db import get_conn, run_migrations
from jarvis.graphs.deliberation_graph import build_deliberation_graph, resolve_deliberation_focus
from tests.unit.test_council_roster import (
    _PROPOSALS,
    _REAL_SCORES,
    REAL_ROUND,
    STARTED,
    _score_row,
)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_DB_PATH", str(tmp_path / "g.db"))
    c = get_conn(tmp_path / "g.db")
    run_migrations(c)
    yield c
    c.close()


def _insert_round(conn, round_row):
    conn.execute(
        f"INSERT INTO council_rounds({','.join(round_row)}) "
        f"VALUES ({','.join('?' * len(round_row))})",
        tuple(round_row.values()),
    )


def _insert_score(conn, row):
    conn.execute(
        f"INSERT INTO council_scores({','.join(row)}) "
        f"VALUES ({','.join('?' * len(row))})",
        tuple(row.values()),
    )


def _real_score_rows():
    rows = []
    for judge, values in _REAL_SCORES.items():
        for (label, profile), value in zip(_PROPOSALS, values):
            rows.append(_score_row(
                judge, label, profile, value,
                reason="judge call failed: " if value is None else None,
            ))
    return rows


def _seed_real_round(conn):
    _insert_round(conn, REAL_ROUND)
    rows = _real_score_rows()
    for r in rows:
        _insert_score(conn, r)
    conn.commit()
    return rows


def test_proposal_mean_equals_build_roster_mean(conn):
    rows = _seed_real_round(conn)
    roster = build_roster(REAL_ROUND, rows)
    mean_by_label = {p["label"]: p["mean"] for p in roster["proposers"]}
    g = build_deliberation_graph(conn, since=None)
    rid = REAL_ROUND["round_id"]
    for label, _profile in _PROPOSALS:
        node = g.nodes[f"proposal:{rid}/{label}"]
        assert node.attrs["mean"] == mean_by_label[label]


def test_scored_edges_carry_score_shadow_tier_and_abstain(conn):
    _seed_real_round(conn)
    g = build_deliberation_graph(conn, since=None)
    k3_edges = [e for e in g.edges if e.type == "scored" and e.src == "profile:kimi-k3"]
    assert len(k3_edges) == 4
    for e in k3_edges:
        assert e.attrs["score"] is None
        assert e.attrs["shadow"] == 0
        assert e.attrs["superseded"] is False
        assert e.attrs["abstain_reason"]


def test_superseded_scored_edge_is_flagged(conn):
    rows = _seed_real_round(conn)
    extra_old = _score_row("or-gpt-5.1", "Proposal A", "or-gemini-flash", 5.0,
                            shadow=1, tier="mid")
    extra_old["created_at"] = STARTED
    extra_new = _score_row("or-gpt-5.1", "Proposal A", "or-gemini-flash", 6.0,
                            shadow=1, tier="mid")
    extra_new["created_at"] = "2026-09-01T03:00:00.000000+00:00"
    _insert_score(conn, extra_old)
    _insert_score(conn, extra_new)
    conn.commit()
    g = build_deliberation_graph(conn, since=None)
    rid = REAL_ROUND["round_id"]
    shadow_edges = [e for e in g.edges if e.type == "scored" and e.src == "profile:or-gpt-5.1"
                    and e.dst == f"proposal:{rid}/Proposal A" and e.attrs["shadow"] == 1]
    assert len(shadow_edges) == 2
    superseded = [e for e in shadow_edges if e.attrs["superseded"]]
    kept = [e for e in shadow_edges if not e.attrs["superseded"]]
    assert len(superseded) == 1 and len(kept) == 1
    assert superseded[0].attrs["score"] == 5.0
    assert kept[0].attrs["score"] == 6.0


def test_won_and_in_round_edges(conn):
    _seed_real_round(conn)
    g = build_deliberation_graph(conn, since=None)
    rid = REAL_ROUND["round_id"]
    won = [e for e in g.edges if e.type == "won"]
    assert len(won) == 1
    assert won[0].src == f"proposal:{rid}/Proposal A"
    in_round = [e for e in g.edges if e.type == "in_round"]
    assert len(in_round) == 4


def test_for_run_edge_only_when_run_id_set(conn):
    _seed_real_round(conn)
    round2 = copy.deepcopy(REAL_ROUND)
    round2["round_id"] = "round2id0000000000000000000000"
    round2["run_id"] = "abc"
    _insert_round(conn, round2)
    conn.commit()
    g = build_deliberation_graph(conn, since=None)
    rid1 = REAL_ROUND["round_id"]
    assert not any(e.type == "for_run" and e.src == f"round:{rid1}" for e in g.edges)
    for_run = [e for e in g.edges if e.type == "for_run" and e.src == f"round:{round2['round_id']}"]
    assert len(for_run) == 1
    assert for_run[0].dst == "run:abc"
    assert g.nodes["run:abc"].attrs.get("pruned") is True


def test_round_without_scores_has_no_proposals(conn):
    round2 = copy.deepcopy(REAL_ROUND)
    round2["round_id"] = "toosmallround00000000000000000"
    round2["status"] = "too_small"
    round2["winner_profile"] = None
    round2["winner_label"] = None
    round2["winner_mean"] = None
    _insert_round(conn, round2)
    conn.commit()
    g = build_deliberation_graph(conn, since=None)
    rid = round2["round_id"]
    assert f"round:{rid}" in g.nodes
    assert not any(nid.startswith(f"proposal:{rid}/") for nid in g.nodes)


def test_resolve_focus_order(conn):
    _seed_real_round(conn)
    g = build_deliberation_graph(conn, since=None)
    rid = REAL_ROUND["round_id"]
    assert resolve_deliberation_focus(conn, g, rid) == f"round:{rid}"
    assert resolve_deliberation_focus(conn, g, rid[:8]) == f"round:{rid}"
    assert resolve_deliberation_focus(conn, g, "kimi-k3") == "profile:kimi-k3"
    assert resolve_deliberation_focus(conn, g, "zzz") is None
