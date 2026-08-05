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
