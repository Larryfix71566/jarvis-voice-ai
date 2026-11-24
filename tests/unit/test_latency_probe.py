"""latency_probe unit tests (plan Phase 7 step 7.3)."""

from scripts.latency_probe import parse_latencies, percentile, render_table

SAMPLE_LOG = """\
[session] abc
[10:00:01] USER: what time is it
[AGENT] Scheduler working: 'current time'
[AGENT] Scheduler calling get_time…
[AGENT] Scheduler done
TURN user_end->llm_done = 800ms
TURN user_end->first_audio = 1800ms
[10:00:09] USER: hello jarvis
TURN user_end->llm_done = 400ms
TURN user_end->first_audio = 700ms
[AGENT] Librarian working: 'save note'
[AGENT] Librarian done
TURN user_end->first_audio = 2600ms
"""


def test_parse_splits_delegated_turns():
    buckets = parse_latencies(SAMPLE_LOG)
    assert buckets["delegated"] == [1800, 2600]
    assert buckets["non-delegated"] == [700]


def test_agent_flag_resets_after_each_turn():
    log = (
        "[AGENT] X working\n"
        "TURN user_end->first_audio = 1000ms\n"
        "TURN user_end->first_audio = 500ms\n"
    )
    buckets = parse_latencies(log)
    assert buckets["delegated"] == [1000]
    assert buckets["non-delegated"] == [500]


def test_percentile_interpolates():
    assert percentile([], 50) is None
    assert percentile([100], 50) == 100
    assert percentile([100, 200, 300, 400], 50) == 250
    assert percentile([100, 200, 300, 400], 90) == 370


def test_render_table_marks_targets():
    table = render_table({"delegated": [2600], "non-delegated": [700]})
    assert "non-delegated" in table
    assert "p50 OK" in table  # 700 <= 1200
    assert "MISS" in table  # delegated 2600 > 2500


def test_acceptance_uses_explicit_turn_identity_and_useful_budget(capsys, monkeypatch):
    import io
    import sys

    from scripts.latency_probe import main

    monkeypatch.setattr(sys, "stdin", io.StringIO(
        '{"turn_id":"a","kind":"acknowledgement","ms":200}\n'
        '{"turn_id":"b","kind":"useful_reply","ms":2000}\n'
        '{"turn_id":"b","kind":"turn_complete","classification":"delegated"}\n'
        '{"turn_id":"a","kind":"turn_complete","classification":"non-delegated"}\n'
        '{"turn_id":"a","kind":"useful_reply","ms":1500}\n'
    ))
    assert main(["latency_probe.py", "--acceptance"]) == 1
    output = capsys.readouterr().out
    assert "Audible acknowledgements (diagnostic only)" in output
    assert "First useful audible reply (acceptance budget)" in output
    assert "non-delegated p50: 1500 ms exceeds target 1200 ms" in output
    assert "delegated p50: 2000 ms exceeds" not in output


def test_acceptance_rejects_empty_legacy_and_acknowledgement_only_windows(capsys, monkeypatch):
    import io
    import sys

    from scripts.latency_probe import main

    for text in (
        "",
        "TURN user_end->first_audio = 200ms\n",
        '{"turn_id":"a","kind":"acknowledgement","ms":200}\n'
        '{"turn_id":"a","kind":"turn_complete","classification":"non-delegated"}\n',
        '{"turn_id":"a","kind":"useful_reply","ms":800}\n',
        '{"turn_id":"a","kind":"useful_reply","ms":800}\n'
        '{"turn_id":"b","kind":"turn_complete","classification":"non-delegated"}\n',
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO(text))
        assert main(["latency_probe.py", "--acceptance"]) == 1
        assert "Invalid latency acceptance window" in capsys.readouterr().err


def test_acceptance_passes_complete_window_without_optional_ack(capsys, monkeypatch):
    import io
    import sys

    from scripts.latency_probe import main

    monkeypatch.setattr(sys, "stdin", io.StringIO(
        '{"turn_id":"a","kind":"useful_reply","ms":800}\n'
        '{"turn_id":"a","kind":"turn_complete","classification":"non-delegated"}\n'
    ))
    assert main(["latency_probe.py", "--acceptance"]) == 0
    assert "800 ms" in capsys.readouterr().out


def test_ci_legacy_budget_can_run_without_samples(monkeypatch):
    import io
    import sys

    from scripts.latency_probe import main

    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main(["latency_probe.py", "--budget"]) == 0


def test_acceptance_rejects_duplicate_conflicting_and_out_of_order_audio():
    import pytest

    from scripts.latency_probe import parse_acceptance

    complete = '{"turn_id":"a","kind":"turn_complete","classification":"delegated"}'
    useful = '{"turn_id":"a","kind":"useful_reply","ms":800}'
    for extra in (
        useful,
        '{"turn_id":"a","kind":"turn_complete","classification":"non-delegated"}',
        '{"turn_id":"a","kind":"acknowledgement","ms":999}',
    ):
        with pytest.raises(ValueError):
            parse_acceptance("\n".join((complete, useful, extra)))
