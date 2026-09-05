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

from tests.evals.routing_eval import REPLY_PREVIEW_CHARS, _one_line


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
