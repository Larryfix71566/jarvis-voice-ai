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
    ALLOW_LIVE_SELFEDIT_ENV,
    CATEGORY_FLOORS_PROFILE,
    DEFAULT_PROFILE,
    LIVE_ADMIN_URL,
    PROFILES,
    SANDBOX_ADMIN_URL,
    REPLY_PREVIEW_CHARS,
    _category_of,
    _one_line,
    format_category_report,
    case_is_correct,
    gate_failures,
    isolate_selfedit_service,
    resolve_profile,
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


# --- eval profiles (2026-09-05, EVAL_CONFIG_PARITY item D) --------------
#
# Larry's call: parameterized, defaulting to parity, and the configuration
# printed with every result. The failure these guard against is a number
# being attributed to the wrong configuration — which is the whole reason
# 63/70 was believed to describe production for as long as it was.


def test_the_default_profile_is_parity_with_production():
    assert DEFAULT_PROFILE == "parity"
    name, addenda, tools = resolve_profile(None)
    assert name == "parity"
    assert all(addenda.values())
    assert tools is True


def test_the_delegate_only_profile_reproduces_the_old_harness():
    _, addenda, tools = resolve_profile("delegate-only")
    assert not any(addenda.values())
    assert tools is False


def test_a_blank_profile_falls_back_to_the_default():
    assert resolve_profile("")[0] == DEFAULT_PROFILE
    assert resolve_profile("   ")[0] == DEFAULT_PROFILE


def test_an_unknown_profile_is_fatal_rather_than_defaulted():
    # A typo that silently ran parity would credit one configuration's
    # number to another — the exact confusion this plan exists to end.
    with pytest.raises(SystemExit, match="unknown EVAL_PROFILE"):
        resolve_profile("paraty")


def test_addenda_and_tools_are_independent_switches():
    # Four tools ship even with every kill switch off, so "no addenda" and
    # "no tools" are different states and must not be folded together.
    for profile in PROFILES.values():
        assert set(profile) == {"addenda", "tools"}
        assert set(profile["addenda"]) == {
            "voice", "ui_control", "screen", "clipboard"}


def test_resolve_profile_hands_back_a_copy_not_the_table():
    # A caller mutating its flags must not rewrite the profile table for
    # every later run in the same process.
    _, addenda, _ = resolve_profile("parity")
    addenda["voice"] = False
    assert PROFILES["parity"]["addenda"]["voice"] is True


def test_floors_are_skipped_under_a_profile_they_were_not_measured_under():
    # A floor is a claim about a number, and a number from one config says
    # nothing about another. Skipping beats failing against a baseline that
    # never applied.
    summary = summarize_categories([("developer", False)] * 7 +
                                   [("developer", True)] * 15)
    foreign = "delegate-only" if CATEGORY_FLOORS_PROFILE != "delegate-only" \
        else "parity"
    assert gate_failures(1.0, summary, floors={"developer": 0.99},
                         profile=foreign) == []
    breached = gate_failures(1.0, summary, floors={"developer": 0.99},
                             profile=CATEGORY_FLOORS_PROFILE)
    assert len(breached) == 1 and "developer" in breached[0]


def test_the_aggregate_threshold_still_applies_under_a_foreign_profile():
    # Only the per-category floors are configuration-specific.
    summary = summarize_categories([("developer", False)] * 10)
    assert gate_failures(0.10, summary, floors={"developer": 0.99},
                         profile="delegate-only")


# --- self-edit sidecar isolation (2026-09-05) ---------------------------
#
# The first parity run staged, started and cancelled REAL self-edits on
# 127.0.0.1:7861. The temp-db isolation never covered that: the sidecar is
# a separate process reached over HTTP, not a table. These pin the guard,
# and above all that it is opt-OUT — forgetting the flag must cost a
# degraded sub-agent, never a self-edit on the machine running the eval.

import os


def test_the_sidecar_is_sandboxed_by_default(monkeypatch):
    monkeypatch.delenv(ALLOW_LIVE_SELFEDIT_ENV, raising=False)
    monkeypatch.setenv("JARVIS_ADMIN_URL", LIVE_ADMIN_URL)
    assert isolate_selfedit_service() == SANDBOX_ADMIN_URL
    assert os.environ["JARVIS_ADMIN_URL"] == SANDBOX_ADMIN_URL


def test_an_unset_admin_url_is_still_sandboxed(monkeypatch):
    # The dangerous case: nothing set, so mcp_selfedit would fall back to
    # its DEFAULT_ADMIN_URL and find the real sidecar.
    monkeypatch.delenv(ALLOW_LIVE_SELFEDIT_ENV, raising=False)
    # GC1: delenv on an already absent key records no undo. Register its
    # original state before the guard writes directly to os.environ, or the
    # dummy port leaks into both graph URL tests when this test runs first.
    monkeypatch.setenv("JARVIS_ADMIN_URL", "")
    monkeypatch.delenv("JARVIS_ADMIN_URL")
    assert isolate_selfedit_service() == SANDBOX_ADMIN_URL
    assert os.environ["JARVIS_ADMIN_URL"] == SANDBOX_ADMIN_URL


def test_the_guard_is_opt_out_not_opt_in(monkeypatch):
    monkeypatch.setenv(ALLOW_LIVE_SELFEDIT_ENV, "1")
    monkeypatch.setenv("JARVIS_ADMIN_URL", LIVE_ADMIN_URL)
    assert isolate_selfedit_service() == LIVE_ADMIN_URL
    assert os.environ["JARVIS_ADMIN_URL"] == LIVE_ADMIN_URL


def test_only_an_exact_1_opts_out(monkeypatch):
    # "true", "yes" and a stray space must not disarm the guard by accident.
    for value in ("true", "yes", "0", "", " 1", "1 "):
        monkeypatch.setenv(ALLOW_LIVE_SELFEDIT_ENV, value)
        monkeypatch.setenv("JARVIS_ADMIN_URL", LIVE_ADMIN_URL)
        assert isolate_selfedit_service() == SANDBOX_ADMIN_URL, value


def test_the_sandbox_target_is_not_the_live_sidecar():
    assert SANDBOX_ADMIN_URL != LIVE_ADMIN_URL
    assert "7861" not in SANDBOX_ADMIN_URL


# --- or_tool: two mechanisms, one destination (2026-09-05) --------------
#
# Cases 6 and 10 expected a librarian delegation and got the direct
# `remember` tool, twice over. Both land in the same place — remember calls
# upsert_fact (jarvis/memory.py:652) and mcp_memory reads the same module
# via search_facts — which is why case 8 ("when does my passport expire")
# passes while those two failed. The cases asserted a distinction the
# storage layer does not make, against a prompt that draws the line the
# other way. or_tool accepts both WITHOUT excusing a turn that did nothing.


def test_a_matching_delegation_is_correct():
    assert case_is_correct({"librarian"}, {"librarian"})


def test_expecting_none_means_no_delegation_happened():
    assert case_is_correct({"none"}, set())
    assert not case_is_correct({"none"}, {"librarian"})


def test_the_alternative_tool_counts_when_it_was_actually_called():
    assert case_is_correct({"librarian"}, set(), "remember", ["remember"])


def test_doing_nothing_at_all_still_fails():
    # The whole risk of or_tool: it must not turn "answered from thin air"
    # into a pass. #25 asserted the app registry was empty with tools:
    # (none) — that has to keep failing.
    assert not case_is_correct({"librarian"}, set(), "remember", [])
    assert not case_is_correct({"librarian"}, set(), "remember", None)


def test_the_alternative_tool_does_not_excuse_the_wrong_specialist():
    # Calling remember AND delegating to scheduler is not a pass.
    assert not case_is_correct({"librarian"}, {"scheduler"}, "remember",
                               ["remember"])


def test_without_an_alternative_a_missing_delegation_fails():
    assert not case_is_correct({"librarian"}, set())
    assert not case_is_correct({"librarian"}, set(), None, ["remember"])


def test_a_multi_agent_case_needs_every_expected_agent():
    assert case_is_correct({"analyst", "scheduler"}, {"analyst", "scheduler"})
    assert not case_is_correct({"analyst", "scheduler"}, {"analyst"})
