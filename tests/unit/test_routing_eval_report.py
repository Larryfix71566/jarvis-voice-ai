"""Miss-report formatting for the routing eval (tests/evals/routing_eval.py).

Added 2026-09-05. Until then the eval discarded orch.chat()'s return value,
so a MISS line said got=[] and nothing about what the model produced
instead — every explanation of a miss was a guess about text that had
already been generated and thrown away. These pin the formatter that puts
that text back into the report; the eval's live half still needs RUN_LIVE=1
and real model calls, which is exactly why the offline half is worth
pinning.
"""

from __future__ import annotations

import pytest

from tests.evals.routing_eval import (
    ACCURACY_THRESHOLD,
    CATEGORY_FLOORS,
    REPLY_PREVIEW_CHARS,
    _category_of,
    _one_line,
    format_category_report,
    gate_failures,
    summarize_categories,
)


def test_a_missing_reply_is_named_not_blank():
    # A blank line in the report would read as "no output captured", which
    # is the same ambiguity this instrumentation exists to remove.
    assert _one_line(None) == "(empty reply)"
    assert _one_line("") == "(empty reply)"
    assert _one_line("   \n\t  ") == "(empty reply)"


def test_a_multiline_reply_collapses_to_one_line():
    # One line per case keeps a 70-case run scannable; a reply with
    # newlines would otherwise break the column alignment of the report.
    out = _one_line("I've switched\n  the theme.\n\nAnything else?")
    assert out == "I've switched the theme. Anything else?"
    assert "\n" not in out


def test_a_short_reply_survives_verbatim():
    assert _one_line("One moment, checking that now.") == \
        "One moment, checking that now."


def test_an_overlong_reply_is_truncated_with_a_marker():
    long = "x" * (REPLY_PREVIEW_CHARS + 50)
    out = _one_line(long)
    assert out.endswith("…")
    assert len(out) == REPLY_PREVIEW_CHARS + 1
    # The marker must be distinguishable from a reply that merely ends in
    # a period, or a reader cannot tell truncation from a complete answer.
    assert not out.endswith(".")


def test_a_reply_exactly_at_the_cap_is_not_truncated():
    exact = "y" * REPLY_PREVIEW_CHARS
    assert _one_line(exact) == exact


# --- per-category scoring and the gate (2026-09-05) -------------------
#
# ACCURACY_THRESHOLD alone is an aggregate over uneven category sizes, so
# one category can decay for a long time while the total still clears 90%.
# These pin the bucketing, the summary arithmetic, and — most importantly —
# that an EMPTY CATEGORY_FLOORS leaves gating exactly as it was, because
# that is what makes this change safe to land before any run has produced
# the per-category numbers a floor would be based on.


def test_floors_ship_empty_so_this_change_cannot_move_the_gate():
    # If this ever fails, someone populated floors from an estimate rather
    # than an observed run — which is the one thing the comment forbids.
    assert CATEGORY_FLOORS == {}


@pytest.mark.parametrize(
    "expect,category",
    [
        ({"none"}, "none"),
        ({"developer"}, "developer"),
        ({"librarian"}, "librarian"),
        ({"analyst", "scheduler"}, "multi"),
        ({"scheduler", "systems"}, "multi"),
    ],
)
def test_a_case_buckets_by_what_it_expects(expect, category):
    assert _category_of(expect) == category


def test_category_totals_account_for_every_case():
    results = [("developer", False)] * 7 + [("developer", True)] * 15 + \
              [("none", True)] * 23
    summary = summarize_categories(results)
    assert summary["developer"] == (15, 22)
    assert summary["none"] == (23, 23)
    assert sum(total for _, total in summary.values()) == len(results)


def test_an_empty_floor_map_gates_on_the_aggregate_alone():
    # The pre-2026-09-05 behaviour, preserved exactly.
    summary = summarize_categories([("developer", False)] * 7 +
                                   [("developer", True)] * 15)
    assert gate_failures(ACCURACY_THRESHOLD, summary, floors={}) == []
    assert gate_failures(ACCURACY_THRESHOLD - 0.01, summary, floors={})


def test_a_category_under_its_floor_fails_even_when_the_aggregate_passes():
    # The whole point: 90% aggregate, one category at 68%.
    summary = summarize_categories(
        [("developer", False)] * 7 + [("developer", True)] * 15 +
        [("none", True)] * 48
    )
    assert gate_failures(0.90, summary, floors={}) == []
    failures = gate_failures(0.90, summary, floors={"developer": 0.80})
    assert len(failures) == 1
    assert "developer" in failures[0] and "68%" in failures[0]


def test_a_floor_naming_a_category_no_case_produces_is_reported_not_ignored():
    # A renamed agent must not silently disable its own gate.
    summary = summarize_categories([("developer", True)] * 5)
    failures = gate_failures(1.0, summary, floors={"planner": 0.90})
    assert failures == ["planner: floor set but no cases scored"]


def test_the_report_orders_by_size_then_name_and_marks_a_breach():
    summary = summarize_categories(
        [("developer", False)] * 7 + [("developer", True)] * 15 +
        [("none", True)] * 23 + [("analyst", True)] * 5 +
        [("systems", True)] * 5
    )
    report = format_category_report(summary, floors={"developer": 0.80})
    lines = report.splitlines()
    assert lines[0] == "per-category:"
    names = [ln.split()[0] for ln in lines[1:]]
    # none (23) before developer (22); analyst before systems at equal size
    assert names == ["none", "developer", "analyst", "systems"]
    assert "BELOW FLOOR 80%" in [ln for ln in lines if "developer" in ln][0]
    assert "BELOW FLOOR" not in [ln for ln in lines if "none" in ln][0]
